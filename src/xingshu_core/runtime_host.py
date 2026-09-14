"""P4E Candidate（候选）：所有者显式配置的单次本地只读宿主。

配置入口属于可信控制面，不是普通 Resolve 请求；文件可解析不等于授权。
资格仍由冻结 Runtime 中的 P2D/P2C/P2E 检查。不发现来源、不修复记录，
不建立缓存、长期会话或操作系统身份认证；调用者须保护宿主输入和进程。
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .context_runtime import resolve_registered_context
from .local_filesystem_adapter import LocalFilesystemSourceAdapter
from .runtime_contracts import (
    RuntimeContext, RuntimeExecutionResult, RuntimeFailureCategory, RuntimeLocalFailure,
    RuntimeResultKind, TrustedClock,
)

__all__ = ["LocalRuntimeHostConfig", "HostInputError", "resolve_local"]


@dataclass(frozen=True, slots=True, kw_only=True)
class LocalRuntimeHostConfig:
    """仅限宿主的配置；路径不进入协议，repr 不暴露任何配置值。

source_root 必须是显式绝对物理路径，交给冻结 LocalFS 检查，不展开或
规范化。身份与传输选择只从所提供的 Profile/Binding/Reference 唯一派生。
hard_max_bytes 是适配器硬上限，不改写请求文件中的 requested_limits。
"""

    reference_file: str | os.PathLike[str] = field(repr=False)
    client_profile_file: str | os.PathLike[str] = field(repr=False)
    runtime_binding_file: str | os.PathLike[str] = field(repr=False)
    request_file: str | os.PathLike[str] = field(repr=False)
    source_root: str | os.PathLike[str] = field(repr=False)
    scope_id: str = field(repr=False)
    adapter_id: str = field(repr=False)
    hard_max_bytes: int = field(default=1048576, repr=False)


class HostInputError(Exception):
    """固定安全宿主错误，不接受路径、正文或底层异常详情。"""

    def __init__(self) -> None:
        super().__init__("Runtime host input could not be accepted.")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for key, value in pairs:
        if key in record:
            raise HostInputError()
        record[key] = value
    return record


def _reject_constant(_value: str) -> Any:
    raise HostInputError()


def _load_json(path: str | os.PathLike[str]) -> tuple[dict[str, Any], bytes]:
    """每个显式输入只二进制读取一次；保留原始字节，所有层级拒绝重复键。

严格 UTF-8，不剥离 BOM/空白，不接受非 JSON 的 NaN/Infinity，不修复字段。
"""
    try:
        with open(path, "rb") as stream:
            raw = stream.read()
        record = json.loads(raw.decode("utf-8", errors="strict"),
                            object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        if type(record) is dict:
            return record, raw
    except Exception:
        pass
    # 在异常处理块之外抛出，避免携带原始路径/JSON 异常链。
    raise HostInputError()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _observation_id() -> str:
    return "p4e-localfs-" + uuid4().hex


def resolve_local(config: LocalRuntimeHostConfig, *, clock: TrustedClock | None = None,
                  observation_id_factory: Callable[[], str] | None = None) -> RuntimeExecutionResult:
    """显式加载四个文件，构建真实适配器/上下文，并且只调用一次 Runtime。

clock 与 observation_id_factory 仅供可信宿主注入；CLI 不提供覆盖参数。
加载/构造失败抛固定 HostInputError；Runtime 异常保持本地执行不可用语义。
"""
    try:
        if type(config) is not LocalRuntimeHostConfig:
            raise HostInputError()
        reference, reference_bytes = _load_json(config.reference_file)
        profile, profile_bytes = _load_json(config.client_profile_file)
        binding, binding_bytes = _load_json(config.runtime_binding_file)
        request, _ = _load_json(config.request_file)
        trusted_clock = _utc_now if clock is None else clock
        id_factory = _observation_id if observation_id_factory is None else observation_id_factory
        adapter = LocalFilesystemSourceAdapter(
            root=config.source_root, adapter_id=config.adapter_id, source_id=reference["source_id"],
            scope_id=config.scope_id, clock=trusted_clock, observation_id_factory=id_factory,
            hard_max_bytes=config.hard_max_bytes,
        )
        context = RuntimeContext(
            reference=reference, reference_bytes=reference_bytes,
            client_profile=profile, client_profile_bytes=profile_bytes,
            runtime_binding=binding, runtime_binding_bytes=binding_bytes,
            selected_client_id=profile["client_id"], source_id=reference["source_id"],
            scope_id=config.scope_id, adapter_id=config.adapter_id,
            selected_transport_binding_id=binding["transport_binding_id"],
            selected_transport_class=binding["transport_class"], adapter=adapter, clock=trusted_clock,
        )
    except Exception:
        pass
    else:
        try:
            return resolve_registered_context(request, context=context)
        except Exception:
            return RuntimeExecutionResult(
                kind=RuntimeResultKind.LOCAL_EXECUTION_FAILURE,
                local_failure=RuntimeLocalFailure(category=RuntimeFailureCategory.EXECUTION_UNAVAILABLE),
            )
    raise HostInputError()
