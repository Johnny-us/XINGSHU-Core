"""LocalFS v0.1 Candidate（本地文件系统只读候选）；仅实现单文件 read。

仅供所有者控制的宿主构造。根目录和绑定不来自请求；本适配器不执行
Authority / Resolve（权限 / 解析）编排，也不授予根目录下所有文件的权限。
宿主仍须在调用前授权精确入口。只接受已落地的本地普通 Markdown 文件，
不适用于网络挂载或会触发下载的占位文件；不建立网络连接或后台任务。

路径组件不跟随符号链接，固定根设备/inode，拒绝跨设备及多硬链接文件。
同句柄前后状态检查降低 TOCTOU（检查与使用竞态）风险，不是针对恶意
同权限进程的原子快照保证。只读指应用不写回，不承诺操作系统不更新 atime。
"""

from __future__ import annotations

import copy
import errno
import hashlib
import os
import stat
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from datetime import datetime, timezone
from typing import Any

from .decisions import Decision
from .runtime_contracts import SourceAdapterExecution, TrustedClock
from .schema_registry import SchemaRegistry
from .source_adapter_validation import validate_source_adapter_object


_NATIVE_OPEN = os.open
_NATIVE_STAT = os.stat
_VERSION = "context-bridge-candidate"


class _AdapterExecutionError(RuntimeError):
    """无法准确构造协议错误时的固定私有失败，不保留原始异常消息。"""

    def __init__(self) -> None:
        super().__init__("Local filesystem adapter execution unavailable.")


class _SourceFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


def _check_platform() -> None:
    flags = ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK", "O_NOCTTY")
    if (os.name != "posix" or not all(hasattr(os, name) for name in flags)
            or _NATIVE_OPEN not in os.supports_dir_fd
            or _NATIVE_STAT not in os.supports_dir_fd
            or _NATIVE_STAT not in os.supports_follow_symlinks):
        raise _AdapterExecutionError()


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _stability(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_nlink)


def _opened(stack: ExitStack, name: str, flags: int, *, parent: int | None = None) -> int:
    fd = os.open(name, flags, dir_fd=parent)
    stack.callback(os.close, fd)
    return fd


class LocalFilesystemSourceAdapter:
    """可信宿主显式提供全部绑定、时钟和观察 ID 工厂；不隐式寻找根目录。

root 必须是绝对物理目录路径，所有组件均不能是符号链接；不 resolve、
展开或重写路径。构造只读取目录元数据，不读取文件正文，不持有长期句柄。
每次请求最多一个文件。max_depth 指根下中间目录数量，硬上限为 32。
公开方法仅 manifest/execute；配置及输出不能替代宿主权限门禁。
"""

    def __init__(self, *, root: str | os.PathLike[str], adapter_id: str,
                 source_id: str, scope_id: str, clock: TrustedClock,
                 observation_id_factory: Callable[[], str], hard_max_bytes: int = 1048576) -> None:
        try:
            _check_platform()
            root_value = os.fspath(root)
            if (type(root_value) is not str or not root_value.startswith("/")
                    or "\0" in root_value or root_value == "/"
                    or any(part in ("", ".", "..") for part in root_value[1:].split("/"))):
                raise _AdapterExecutionError()
            if type(hard_max_bytes) is not int or not 1 <= hard_max_bytes <= 1048576:
                raise _AdapterExecutionError()
            if not callable(clock) or not callable(observation_id_factory):
                raise _AdapterExecutionError()
            self._root = root_value
            self._adapter_id, self._source_id, self._scope_id = adapter_id, source_id, scope_id
            self._clock, self._id_factory, self._hard_max_bytes = clock, observation_id_factory, hard_max_bytes
            self._registry = SchemaRegistry()
            self._require_valid(self.manifest(), "source_adapter_manifest")
            # 复用既有请求合同检查宿主身份字段，不复制标识符验证规则。
            self._require_valid({
                "schema_version": _VERSION, "object_kind": "source_adapter_request",
                "request_id": "construction-check", "adapter_id": adapter_id,
                "source_id": source_id, "scope_id": scope_id, "operation": "read",
                "target_locator": "synthetic.md", "requested_limits": {"max_items": 1, "max_bytes": 1},
            }, "source_adapter_request")
            with ExitStack() as stack:
                self._root_identity = _identity(os.fstat(self._open_root(stack)))
        except Exception:
            pass
        else:
            return
        raise _AdapterExecutionError()

    def __repr__(self) -> str:
        return "LocalFilesystemSourceAdapter()"

    def manifest(self) -> Mapping[str, Any]:
        return {
            "schema_version": _VERSION, "object_kind": "source_adapter_manifest",
            "adapter_id": self._adapter_id, "adapter_contract_version": "localfs-v0.1",
            "supported_operations": ["read"], "supported_content_types": ["text/markdown"],
            "default_encoding": "utf-8", "binary_supported": False,
            "hard_limits": {"max_items": 1, "max_bytes": self._hard_max_bytes, "max_depth": 32},
        }

    def _require_valid(self, record: Mapping[str, Any], route: str) -> None:
        checked = validate_source_adapter_object(record, route, self._registry)
        if checked.decision is not Decision.PASS:
            raise _AdapterExecutionError()

    def _time(self) -> str:
        value = self._clock()
        if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
            raise _AdapterExecutionError()
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _open_root(self, stack: ExitStack) -> int:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        current = _opened(stack, "/", flags)
        for part in self._root[1:].split("/"):
            current = _opened(stack, part, flags, parent=current)
        if not stat.S_ISDIR(os.fstat(current).st_mode):
            raise _SourceFailure("containment_failed")
        return current

    @staticmethod
    def _parts(locator: Any) -> list[str]:
        if (type(locator) is not str or not locator or locator.startswith("/")
                or any(char in locator for char in ("\0", "\\", ":", "~", "$", "%"))):
            raise _SourceFailure("invalid_locator")
        parts = locator.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise _SourceFailure("invalid_locator")
        if not parts[-1].endswith(".md"):
            raise _SourceFailure("unsupported_content_type")
        return parts

    def _read(self, parts: list[str], limit: int) -> bytes:
        _check_platform()
        with ExitStack() as stack:
            parent = self._open_root(stack)
            if _identity(os.fstat(parent)) != self._root_identity:
                raise _SourceFailure("containment_failed")
            for part in parts[:-1]:
                parent = _opened(stack, part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, parent=parent)
                info = os.fstat(parent)
                if not stat.S_ISDIR(info.st_mode) or info.st_dev != self._root_identity[0]:
                    raise _SourceFailure("containment_failed")
            entry = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            self._check_file(entry)
            fd = _opened(stack, parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOCTTY, parent=parent)
            before = os.fstat(fd)
            self._check_file(before)
            if _identity(entry) != _identity(before):
                raise _SourceFailure("source_unavailable")
            if before.st_size > limit:
                raise _SourceFailure("limit_exceeded")
            chunks: list[bytes] = []
            count = 0
            while count <= limit:
                chunk = os.read(fd, min(65536, limit + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
            after = os.fstat(fd)
            if count > limit:
                raise _SourceFailure("limit_exceeded")
            if _stability(before) != _stability(after) or count != after.st_size:
                raise _SourceFailure("source_unavailable")
            self._check_file(after)
            current = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            if _identity(current) != _identity(after):
                raise _SourceFailure("source_unavailable")
            if _identity(os.fstat(self._open_root(stack))) != self._root_identity:
                raise _SourceFailure("containment_failed")
            # 只拼接 os.read 直接返回的 bytes；不是正文的重新编码。
            return b"".join(chunks)

    def _check_file(self, info: os.stat_result) -> None:
        if stat.S_ISLNK(info.st_mode) or info.st_dev != self._root_identity[0]:
            raise _SourceFailure("containment_failed")
        if not stat.S_ISREG(info.st_mode):
            raise _SourceFailure("unsupported_content_type")
        if info.st_nlink > 1:
            raise _SourceFailure("containment_failed")

    def _error(self, request: Mapping[str, Any], code: str) -> SourceAdapterExecution:
        response = {
            "schema_version": _VERSION, "object_kind": "source_adapter_error",
            "request_id": request["request_id"], "adapter_id": self._adapter_id,
            "operation": request["operation"], "error_code": code,
            "retryable": False, "observed_at": self._time(),
        }
        self._require_valid(response, "source_adapter_error")
        return SourceAdapterExecution(response=response, exact_content_bytes=None)

    def execute(self, request: Mapping[str, Any]) -> SourceAdapterExecution:
        """不修改请求；无法准确表达的错误以固定私有异常结束，不伪造协议。"""
        query = None
        try:
            if not isinstance(request, Mapping):
                raise _AdapterExecutionError()
            query = copy.deepcopy(dict(request))
            if any(query.get(key) != value for key, value in (
                    ("adapter_id", self._adapter_id), ("source_id", self._source_id), ("scope_id", self._scope_id))):
                # 冻结错误枚举没有绑定失配代码，不能伪装成来源失败。
                raise _AdapterExecutionError()
            if query.get("operation") != "read":
                raise _SourceFailure("unsupported_operation")
            parts = self._parts(query.get("target_locator"))
            self._require_valid(query, "source_adapter_request")
            limits = query["requested_limits"]
            if (limits["max_items"] > 1 or limits["max_bytes"] > self._hard_max_bytes
                    or limits.get("max_depth", 32) > 32
                    or len(parts) - 1 > limits.get("max_depth", 32)):
                # P2C 要求请求只能收窄 Manifest 上限，不能改写原请求后宣称通过。
                raise _SourceFailure("limit_exceeded")
            limit = min(limits["max_bytes"], self._hard_max_bytes)
            try:
                raw = self._read(parts, limit)
            except OSError as failure:
                code = {errno.ENOENT: "not_found", errno.ELOOP: "containment_failed",
                        errno.ENOTDIR: "containment_failed"}.get(failure.errno, "source_unavailable")
                raise _SourceFailure(code) from None
            try:
                text = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                raise _SourceFailure("unsupported_encoding") from None
            observed_at = self._time()
            try:
                observation_id = self._id_factory()
            except Exception:
                raise _SourceFailure("provenance_unavailable") from None
            fingerprint = "sha256:" + hashlib.sha256(raw).hexdigest()
            response = {
                "schema_version": _VERSION, "object_kind": "source_adapter_result", "ok": True,
                "request_id": query["request_id"], "adapter_id": self._adapter_id,
                "source_id": self._source_id, "scope_id": self._scope_id, "operation": "read",
                "provenance": {"source_id": self._source_id, "scope_id": self._scope_id,
                               "adapter_id": self._adapter_id, "operation": "read", "observed_at": observed_at,
                               "observation_id": observation_id, "content_fingerprint": fingerprint},
                "applied_limits": {"max_items": 1, "max_bytes": limit, "observed_items": 1,
                                   "observed_bytes": len(raw), "truncated": False},
                "payload": {"payload_kind": "read", "locator": query["target_locator"],
                            "content_type": "text/markdown", "encoding": "utf-8", "byte_count": len(raw),
                            "text": text, "content_fingerprint": fingerprint, "truncated": False},
            }
            self._require_valid(response, "source_adapter_result")
            return SourceAdapterExecution(response=response, exact_content_bytes=raw)
        except _SourceFailure as failure:
            code = failure.code
        except Exception:
            code = None
        if code is not None and query is not None:
            try:
                return self._error(query, code)
            except Exception:
                pass
        # 离开原异常处理块再抛出，避免原始异常链在格式化时泄露路径或正文。
        raise _AdapterExecutionError()
