"""Authority Context（授权上下文）的纯确定性候选校验。

PASS 只表示所供对象与证据自洽，不认证 caller、session、Owner 或控制平面。
若调用者控制全部参数，无法区分真实输入与自洽伪造。Binding 不激活 Runtime，
准入不等于 Resolve 成功或可直接返回正文。只允许既有 Registry 加载 Schema；
不读取 Source、Runtime、Provider，不执行传输，不使用隐式当前时间。
governance_effect=none; authorization_effect=none; activation_effect=none.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any

from .decisions import Decision, ValidationIssue, ValidationResult
from .schema_registry import SchemaRegistry

__all__ = ["validate_authority_object", "validate_reference_authority"]

_PROFILE = "trusted_client_profile"
_REFERENCE = "registered_context_reference"
_BINDING = "runtime_binding"
_ROUTES = (_PROFILE, _BINDING, _REFERENCE)
_ABSENT = object()
_JSON_LIMIT = 16_777_216
_TOTAL_LIMIT = 50_331_648
_TIME_LIMIT = 256
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}")
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}")
_TIME = re.compile(r"(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?([Zz]|[+-]\d{2}:\d{2})")
_OPERATIONS = ("get_reference", "resolve_context")
_TRANSPORTS = ("in_process", "stdio", "loopback_http", "tool_api")
_MESSAGES = {
    "authority_invalid_object": "input violates the closed input contract",
    "authority_unsupported_route": "unsupported authority route",
    "authority_route_mismatch": "object kind does not match the expected route",
    "authority_schema_invalid": "object violates the frozen schema",
    "authority_exact_input_mismatch": "exact bytes do not represent the supplied object",
    "authority_fingerprint_mismatch": "exact object fingerprint does not match",
    "authority_identity_mismatch": "object identities do not match",
    "authority_client_not_allowed": "client is not explicitly allowed",
    "authority_profile_not_active": "profile is not active",
    "authority_profile_expired": "profile is expired at the supplied evaluation time",
    "authority_reference_not_active": "reference is not active",
    "authority_runtime_binding_mismatch": "runtime binding does not match the supplied selection or scope",
    "authority_entry_scope_mismatch": "bound entries are not an exact ordered subset",
    "authority_operation_not_allowed": "operation is not allowed by the binding",
    "authority_context_missing": "required authority context is missing",
    "authority_timestamp_inconsistent": "explicit event timestamps are inconsistent",
    "authority_validation_unavailable": "strict authority validation is unavailable",
    "authority_resource_limit_exceeded": "validation could not complete within the private processing budget",
}


def _copy(value: Any, active: set[int]) -> Any:
    """仅复制 JSON 值和内置有序数组，不执行自定义 Sequence。"""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, Mapping) or type(value) in (list, tuple):
        identity = id(value)
        if identity in active:
            raise ValueError("cyclic input")
        active.add(identity)
        try:
            if isinstance(value, Mapping):
                if any(type(key) is not str for key in value):
                    raise ValueError("non-string key")
                return {key: _copy(child, active) for key, child in value.items()}
            return [_copy(child, active) for child in value]
        finally:
            active.remove(identity)
    raise ValueError("non-JSON value")


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_same(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    if type(left) is bool or type(right) is bool:
        return type(left) is type(right) and left == right
    if type(left) in (int, float, Decimal) and type(right) in (int, float, Decimal):
        return Decimal(left) == Decimal(right)
    return type(left) is type(right) and left == right


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _constant(value: str) -> Any:
    raise ValueError("non-finite number")


class _Checks:
    def __init__(self, registry: SchemaRegistry | None) -> None:
        self.registry = registry
        self.issues: list[tuple[Decision, ValidationIssue]] = []
        self.refs: dict[str, str] = {}

    def add(self, code: str, path: str, decision: Decision = Decision.REJECT) -> None:
        item = (decision, ValidationIssue(code, path, _MESSAGES[code]))
        if item not in self.issues:
            self.issues.append(item)

    def missing(self, path: str) -> None:
        self.add("authority_context_missing", path, Decision.NEEDS_REVIEW)

    def resource(self, path: str) -> None:
        self.add("authority_resource_limit_exceeded", path, Decision.ERROR)

    def unavailable(self, path: str) -> None:
        self.add("authority_validation_unavailable", path, Decision.ERROR)

    def reg(self) -> SchemaRegistry:
        if self.registry is None:
            self.registry = SchemaRegistry()
        return self.registry

    def closed(self, value: Any, allowed: tuple[str, ...], required: tuple[str, ...],
               path: str, *, contract: bool = False) -> dict[str, Any]:
        """先当前层键名，后读取已知值；未知值从不读取。"""
        if value is _ABSENT:
            self.missing(path)
            return {}
        if not isinstance(value, Mapping):
            self.add("authority_invalid_object", path)
            return {}
        try:
            if any(type(k) is not str or k not in allowed for k in value):
                self.add("authority_schema_invalid" if contract else "authority_invalid_object", path)
            result = {}
            for key in allowed:
                if key in value:
                    result[key] = value[key]
                elif key in required:
                    self.missing(path + "/" + key)
            return result
        except (RecursionError, MemoryError):
            self.resource(path)
        except Exception:
            self.add("authority_invalid_object", path)
        return {}

    def object(self, record: Any, route: str, path: str) -> dict[str, Any] | None:
        if record is None:
            self.missing(path)
            return None
        if not isinstance(record, Mapping):
            self.add("authority_invalid_object", path)
            return None
        try:
            if record.get("object_kind") != route:
                self.add("authority_route_mismatch", path + "/object_kind")
                return None
        except Exception:
            self.add("authority_invalid_object", path)
            return None
        try:
            reg = self.reg()
            validator = reg.validator_for(route)
            schema = reg.load_schema(route)
            self.refs[route] = reg.schema_ref_for(route)
        except Exception:
            self.unavailable(path)
            return None
        properties = schema["properties"]
        raw = self.closed(record, tuple(properties), (), path, contract=True)
        copied = {}
        for key, value in raw.items():
            # 局部数组公共上限直接来自原 Schema，先长度后元素；不另造限制。
            maximum = properties[key].get("maxItems")
            if maximum is not None and type(value) in (list, tuple) and len(value) > maximum:
                self.add("authority_schema_invalid", path + "/" + key)
                return None
            try:
                copied[key] = _copy(value, {id(record)})
            except (RecursionError, MemoryError):
                self.resource(path + "/" + key)
                return None
            except Exception:
                self.add("authority_invalid_object", path + "/" + key)
                return None
        times = (("created_at", "expires_at", "revoked_at") if route == _PROFILE else
                 ("created_at",) if route == _BINDING else ("registered_at",))
        schema_input = copied.copy()
        for key in times:
            value = copied.get(key)
            if type(value) is str and len(value) > _TIME_LIMIT:
                self.resource(path + "/" + key)
                # 已记录 ERROR，原字段绝不交给时间解析器。仅用固定占位值检查
                # 其他独立 Schema 条件，保留原对象供字节关联；不能因此得到 PASS。
                schema_input[key] = "2000-01-01T00:00:00Z"
        try:
            if next(validator.iter_errors(schema_input), None) is not None:
                self.add("authority_schema_invalid", path)
                return None
        except (RecursionError, MemoryError):
            self.resource(path)
            return None
        except Exception:
            self.unavailable(path)
            return None
        return copied

    def token(self, value: Any, path: str, *, fingerprint: bool = False,
              choices: tuple[str, ...] | None = None) -> Any:
        if value is _ABSENT:
            return value
        if type(value) is not str or (value not in choices if choices is not None else
                (_FINGERPRINT if fingerprint else _IDENTIFIER).fullmatch(value) is None):
            self.add("authority_invalid_object", path)
            return _ABSENT
        return value

    def exact(self, value: Any, record: dict[str, Any] | None, path: str) -> Any:
        if value is _ABSENT:
            return _ABSENT
        if type(value) is not bytes:
            self.add("authority_invalid_object", path)
            return _ABSENT
        if len(value) > _JSON_LIMIT:
            self.resource(path)
            return _ABSENT
        fingerprint = "sha256:" + hashlib.sha256(value).hexdigest()
        try:
            text = value.decode("utf-8", errors="strict")
            if text.startswith("\ufeff"):
                raise ValueError("BOM")
            parsed = json.loads(text, object_pairs_hook=_pairs, parse_int=Decimal,
                                parse_float=Decimal, parse_constant=_constant)
            if not isinstance(parsed, dict) or (record is not None and not _same(parsed, record)):
                self.add("authority_exact_input_mismatch", path)
        except (RecursionError, MemoryError):
            self.resource(path)
        except Exception:
            self.add("authority_exact_input_mismatch", path)
        return fingerprint

    def equal(self, a: Any, b: Any, path: str, code: str) -> None:
        if a is not _ABSENT and b is not _ABSENT and not _same(a, b):
            self.add(code, path)

    def time(self, value: Any, path: str, *, context: bool = False) -> Fraction | None:
        if value is _ABSENT:
            return None
        if type(value) is not str:
            self.add("authority_invalid_object", path)
            return None
        if len(value) > _TIME_LIMIT:
            self.resource(path)
            return None
        try:
            reg = self.reg()
            validator = reg.validator_for(_PROFILE)
            if context:
                definition = reg.load_schema(_PROFILE)["$defs"]["timestamp"]
                valid = validator.evolve(schema=definition).is_valid(value)
            else:
                if validator.format_checker is None:
                    raise RuntimeError("strict timestamp checker unavailable")
                valid = validator.format_checker.conforms(value, "date-time")
            if not valid:
                self.add("authority_invalid_object" if context else "authority_schema_invalid", path)
                return None
            match = _TIME.fullmatch(value)
            if match is None:
                raise RuntimeError("timestamp comparison unavailable")
            year, month, day, hour, minute, second = map(int, match.groups()[:6])
            seconds = date(year, month, day).toordinal() * 86400 + hour * 3600 + minute * 60 + second
            fraction, offset = match.groups()[6:]
            if offset not in ("Z", "z"):
                seconds -= (1 if offset[0] == "+" else -1) * (int(offset[1:3]) * 3600 + int(offset[4:6]) * 60)
            return Fraction(seconds) + (Fraction("0." + fraction) if fraction else 0)
        except (RecursionError, MemoryError):
            self.resource(path)
        except Exception:
            self.unavailable(path)
        return None

    def finish(self, route: str | None, status: str) -> ValidationResult:
        decision = Decision.PASS
        for level, label in ((Decision.REJECT, "rejected"), (Decision.ERROR, "validation_unavailable"),
                             (Decision.NEEDS_REVIEW, "incomplete_authority_context")):
            if any(d == level for d, _ in self.issues):
                decision, status = level, label
                break
        return ValidationResult(decision, status, route, "context-bridge-candidate" if route else None,
                                self.refs.get(route), tuple(issue for _, issue in self.issues))


def _field(record: dict[str, Any] | None, key: str) -> Any:
    return record.get(key, _ABSENT) if record is not None else _ABSENT


def validate_authority_object(record: Mapping[str, Any], expected_route: str,
                              registry: SchemaRegistry | None = None) -> ValidationResult:
    """单对象只证明结构，不进行授权链、到期或当前 Source 检查。"""
    checks = _Checks(registry)
    if type(expected_route) is not str or expected_route not in _ROUTES:
        checks.add("authority_unsupported_route", "$")
        return checks.finish(None, "object_valid")
    if record is None:
        checks.add("authority_invalid_object", "$")
    else:
        checks.object(record, expected_route, "$")
    return checks.finish(expected_route, "object_valid")


def validate_reference_authority(reference: Any, client_profile: Any, runtime_binding: Any, *,
                                 authority_context: Mapping[str, Any] | None = None,
                                 registry: SchemaRegistry | None = None) -> ValidationResult:
    """验证显式 operation 的静态准入；不认证上下文，不执行 Resolve 或 Runtime。"""
    checks = _Checks(registry)
    r = checks.object(reference, _REFERENCE, "$/reference")
    p = checks.object(client_profile, _PROFILE, "$/client_profile")
    b = checks.object(runtime_binding, _BINDING, "$/runtime_binding")
    root = "$/authority_context"
    keys = ("object_bytes", "control_plane_selection", "operation", "evaluated_at")
    context = checks.closed(_ABSENT if authority_context is None else authority_context, keys, keys, root)
    names = (_PROFILE, _REFERENCE, _BINDING)
    blobs = checks.closed(context.get("object_bytes", _ABSENT), names, names, root + "/object_bytes")
    selection_keys = ("client_id", "binding_fingerprint", "transport_binding_id", "transport_class")
    selection = checks.closed(context.get("control_plane_selection", _ABSENT), selection_keys, selection_keys,
                              root + "/control_plane_selection")
    selected = {k: checks.token(selection.get(k, _ABSENT), root + "/control_plane_selection/" + k,
                               fingerprint=k == "binding_fingerprint", choices=_TRANSPORTS if k == "transport_class" else None)
                for k in selection_keys}
    operation = checks.token(context.get("operation", _ABSENT), root + "/operation", choices=_OPERATIONS)
    if sum(len(v) for v in blobs.values() if type(v) is bytes) > _TOTAL_LIMIT:
        checks.resource(root + "/object_bytes")
    fingerprints = {name: checks.exact(blobs.get(name, _ABSENT), record, root + "/object_bytes/" + name)
                    for name, record in ((_PROFILE, p), (_REFERENCE, r), (_BINDING, b))}
    for left, right, path, code in (
        (_field(b, "trusted_client_profile_id"), _field(p, "profile_id"), "$/runtime_binding/trusted_client_profile_id", "authority_identity_mismatch"),
        (_field(b, "reference_id"), _field(r, "reference_id"), "$/runtime_binding/reference_id", "authority_identity_mismatch"),
        (selected["client_id"], _field(p, "client_id"), root + "/control_plane_selection/client_id", "authority_identity_mismatch"),
        (_field(b, "trusted_client_profile_fingerprint"), fingerprints[_PROFILE], "$/runtime_binding/trusted_client_profile_fingerprint", "authority_fingerprint_mismatch"),
        (_field(b, "reference_fingerprint"), fingerprints[_REFERENCE], "$/runtime_binding/reference_fingerprint", "authority_fingerprint_mismatch"),
        (selected["binding_fingerprint"], fingerprints[_BINDING], root + "/control_plane_selection/binding_fingerprint", "authority_fingerprint_mismatch"),
        (_field(b, "bound_access_scope"), _field(r, "access_scope"), "$/runtime_binding/bound_access_scope", "authority_runtime_binding_mismatch"),
        (selected["transport_binding_id"], _field(b, "transport_binding_id"), root + "/control_plane_selection/transport_binding_id", "authority_runtime_binding_mismatch"),
        (selected["transport_class"], _field(b, "transport_class"), root + "/control_plane_selection/transport_class", "authority_runtime_binding_mismatch"),
    ):
        checks.equal(left, right, path, code)
    if r is not None:
        if r["status"] != "active":
            checks.add("authority_reference_not_active", "$/reference/status")
        if not r["allowed_clients"] or (p is not None and p["client_id"] not in r["allowed_clients"]):
            checks.add("authority_client_not_allowed", "$/reference/allowed_clients")
    if p is not None and p["profile_status"] != "active":
        checks.add("authority_profile_not_active", "$/client_profile/profile_status")
    if b is not None and operation is not _ABSENT and operation not in b["allowed_operations"]:
        checks.add("authority_operation_not_allowed", root + "/operation")
    if r is not None and b is not None:
        entries = iter(r["source_entry_points"])
        if not all(any(entry == chosen for entry in entries) for chosen in b["bound_entry_points"]):
            checks.add("authority_entry_scope_mismatch", "$/runtime_binding/bound_entry_points")
    times = {
        "profile": (_field(p, "created_at"), "$/client_profile/created_at"),
        "reference": (_field(r, "registered_at"), "$/reference/registered_at"),
        "binding": (_field(b, "created_at"), "$/runtime_binding/created_at"),
        "evaluated": (context.get("evaluated_at", _ABSENT), root + "/evaluated_at"),
        "expires": (_field(p, "expires_at"), "$/client_profile/expires_at"),
        "revoked": (_field(p, "revoked_at"), "$/client_profile/revoked_at"),
    }
    instants = {key: checks.time(value, path, context=key == "evaluated") for key, (value, path) in times.items()}
    for earlier, later in (("profile", "binding"), ("reference", "binding"), ("binding", "evaluated"),
                           ("profile", "evaluated"), ("reference", "evaluated"), ("profile", "expires"),
                           ("profile", "revoked"), ("revoked", "evaluated")):
        a, z = instants[earlier], instants[later]
        if a is not None and z is not None and a > z:
            checks.add("authority_timestamp_inconsistent", times[later][1])
    evaluated, expires = instants["evaluated"], instants["expires"]
    if evaluated is not None and expires is not None and evaluated >= expires:
        checks.add("authority_profile_expired", "$/client_profile/expires_at")
    return checks.finish(_BINDING, "authority_context_eligible")
