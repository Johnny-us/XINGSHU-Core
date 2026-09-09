"""Resolve Context（上下文解析）的候选纯确定性证据校验。

governance_effect=none; authorization_effect=none; activation_effect=none.
PASS 只表示所供对象、授权上下文与观察证据一致，不认证 caller、Runtime、
Provider，不证明真实 I/O、Source 所有权、原生包含关系或正文保存行为。
错误交换 PASS 不表示 Resolve 成功。只允许既有 Registry 加载 Schema。
不解释正文或查询提示，不执行来源操作，不使用隐式当前时间。
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
from datetime import date
from fractions import Fraction
from typing import Any

from .authority_validation import validate_reference_authority
from .decisions import Decision, ValidationIssue, ValidationResult
from .schema_registry import SchemaRegistry
from .source_adapter_validation import validate_source_adapter_exchange

__all__ = ["validate_resolve_context_object", "validate_resolve_context_exchange"]

_ROUTES = ("resolve_context_request", "resolve_context_result", "resolve_context_error")
_R, _P, _B = "registered_context_reference", "trusted_client_profile", "runtime_binding"
_ABSENT = object()
_BYTE_LIMIT = 16_777_216
_TIME_LIMIT = 256
_TIME = re.compile(r"(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?([Zz]|[+-]\d{2}:\d{2})")
_MESSAGES = {
    "resolve_invalid_object": "input violates the closed input contract",
    "resolve_unsupported_route": "unsupported resolve context route",
    "resolve_route_mismatch": "object kind does not match the expected route",
    "resolve_schema_invalid": "object violates the frozen resolve schema",
    "resolve_request_linkage_mismatch": "response linkage does not match the request",
    "resolve_reference_mismatch": "reference linkage does not match the supplied evidence",
    "resolve_binding_mismatch": "binding linkage does not match the supplied evidence",
    "resolve_authority_not_eligible": "authority does not permit a positive resolve result",
    "resolve_entry_selection_mismatch": "entries violate the required ordered selection",
    "resolve_limit_mismatch": "resolve counts or limits do not agree",
    "resolve_payload_mismatch": "payload does not match the linked read evidence",
    "resolve_payload_fingerprint_mismatch": "payload fingerprint does not match exact content bytes",
    "resolve_freshness_mismatch": "freshness fields do not match the supplied resolution evidence",
    "resolve_provenance_mismatch": "provenance does not match the supplied resolution evidence",
    "resolve_source_observation_mismatch": "source observation does not match the required linkage",
    "resolve_error_evidence_mismatch": "error reason does not match the supplied evidence",
    "resolve_context_missing": "required resolution proof is incomplete or unsupported",
    "resolve_timestamp_inconsistent": "explicit event timestamps are inconsistent",
    "resolve_validation_unavailable": "strict resolve validation is unavailable",
    "resolve_resource_limit_exceeded": "validation could not complete within the private processing budget",
}


def _fingerprint(blob: bytes) -> str:
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _field(record: Any, key: str) -> Any:
    return record.get(key, _ABSENT) if type(record) is dict else _ABSENT


def _subset(selected: list[Any], entries: list[Any]) -> bool:
    remaining = iter(entries)
    return all(any(value == entry for entry in remaining) for value in selected)


class _Admission(Exception):
    """已记录安全诊断；不携带输入或原始异常。"""


class _Checks:
    def __init__(self, registry: SchemaRegistry | None) -> None:
        self.registry = registry
        self.issues: list[tuple[Decision, ValidationIssue]] = []
        self.refs: dict[str, str] = {}
        self.text_bytes = {"source": 0, "resolve": 0, "authority": 0}

    def add(self, code: str, path: str, level: Decision = Decision.REJECT) -> None:
        item = (level, ValidationIssue(code, path, _MESSAGES[code]))
        if item not in self.issues:
            self.issues.append(item)

    def missing(self, path: str) -> None:
        self.add("resolve_context_missing", path, Decision.NEEDS_REVIEW)

    def resource(self) -> None:
        self.add("resolve_resource_limit_exceeded", "$/resolution_context", Decision.ERROR)

    def unavailable(self, path: str) -> None:
        self.add("resolve_validation_unavailable", path, Decision.ERROR)

    def reg(self) -> SchemaRegistry:
        if self.registry is None:
            self.registry = SchemaRegistry()
        return self.registry

    def keys(self, value: Mapping[str, Any], allowed: Any, path: str,
             code: str = "resolve_invalid_object") -> tuple[str, ...]:
        admitted: list[str] = []
        # 封闭层的最大键数已知；异常 Mapping 不能以重复键无限迭代消耗预算。
        for key in value:
            if len(admitted) >= len(allowed) or type(key) is not str or key not in allowed or key in admitted:
                self.add(code, path)
                raise _Admission
            admitted.append(key)
        return tuple(admitted)

    def closed(self, value: Any, keys: tuple[str, ...], required: tuple[str, ...],
               path: str) -> dict[str, Any]:
        if value is _ABSENT:
            self.missing(path)
            return {}
        if not isinstance(value, Mapping):
            self.add("resolve_invalid_object", path)
            return {}
        try:
            # 当前层未知键一经发现即停止，绝不访问其 value/items/repr。
            present = self.keys(value, keys, path)
            result = {}
            for k in keys:
                if k in present:
                    result[k] = value[k]
                elif k in required:
                    self.missing(path)
            return result
        except _Admission:
            return {}
        except (RecursionError, MemoryError):
            self.resource()
        except Exception:
            self.add("resolve_invalid_object", path)
        return {}

    def _parts(self, node: dict[str, Any], schema: dict[str, Any]) -> list[dict[str, Any]]:
        if "$ref" in node:
            ref = node["$ref"]
            if not ref.startswith("#/$defs/"):
                raise RuntimeError("nonlocal schema reference")
            return self._parts(schema["$defs"][ref.split("/")[-1]], schema)
        parts = [node]
        for keyword in ("allOf", "oneOf", "anyOf"):
            for child in node.get(keyword, ()):
                parts.extend(self._parts(child, schema))
        return parts

    def _copy(self, value: Any, node: dict[str, Any], schema: dict[str, Any],
              active: set[int], path: str, lane: str, *, time_field: bool = False,
              body_field: bool = False) -> Any:
        parts = self._parts(node, schema)
        if isinstance(value, Mapping):
            if id(value) in active:
                self.add("resolve_invalid_object", path)
                raise _Admission
            properties = {k: v for part in parts for k, v in part.get("properties", {}).items()}
            present = self.keys(value, properties, path, "resolve_schema_invalid")
            tags = {}
            # oneOf 的成功载荷先按正式 discriminator 收窄字段集，再读取子值。
            for discriminator in ("object_kind", "payload_kind"):
                if discriminator in properties and discriminator in present:
                    tag = value[discriminator]
                    tags[discriminator] = tag
                    if type(tag) is not str:
                        self.add("resolve_invalid_object", path)
                        raise _Admission
                    choices = [p for p in parts if p.get("properties", {}).get(discriminator, {}).get("const", _ABSENT) == tag]
                    if choices:
                        properties = choices[0]["properties"]
                        if any(k not in properties for k in present):
                            self.add("resolve_schema_invalid", path)
                            raise _Admission
            active.add(id(value))
            try:
                copied, failed = {}, False
                for k, child in properties.items():
                    if k in present:
                        try:
                            child_value = tags[k] if k in tags else value[k]
                            copied[k] = self._copy(child_value, child, schema, active, path, lane,
                                                   time_field=k.endswith("_at"), body_field=k == "text")
                        except _Admission:
                            failed = True
                if failed:
                    raise _Admission
                return copied
            finally:
                active.remove(id(value))
        if type(value) in (list, tuple):
            if id(value) in active:
                self.add("resolve_invalid_object", path)
                raise _Admission
            ceilings = [p["maxItems"] for p in parts if "maxItems" in p]
            if not any("items" in p for p in parts):
                self.add("resolve_schema_invalid", path)
                raise _Admission
            if ceilings and len(value) > min(ceilings):
                self.add("resolve_schema_invalid", path)
                raise _Admission
            item = next(p["items"] for p in parts if "items" in p)
            active.add(id(value))
            try:
                return [self._copy(v, item, schema, active, path, lane) for v in value]
            finally:
                active.remove(id(value))
        if type(value) is str:
            ceilings = [p["maxLength"] for p in parts if "maxLength" in p]
            if ceilings and len(value) > min(ceilings):
                self.add("resolve_schema_invalid", path)
                raise _Admission
            if time_field and len(value) > _TIME_LIMIT:
                self.resource()
                raise _Admission
            if body_field and lane in ("source", "resolve"):
                # 先廉价长度界，再有界分段编码；不构造巨大 UTF-8 临时副本。
                if self.text_bytes[lane] + len(value) > _BYTE_LIMIT:
                    self.resource()
                    raise _Admission
                for start in range(0, len(value), 4096):
                    self.text_bytes[lane] += len(value[start:start + 4096].encode("utf-8"))
                    if self.text_bytes[lane] > _BYTE_LIMIT:
                        self.resource()
                        raise _Admission
            return value
        if value is None or type(value) in (bool, int):
            return value
        if type(value) is float and math.isfinite(value):
            return value
        self.add("resolve_invalid_object", path)
        raise _Admission

    def object(self, record: Any, route: str, path: str, lane: str = "authority") -> dict[str, Any] | None:
        if record is _ABSENT:
            self.missing(path)
            return None
        if not isinstance(record, Mapping):
            self.add("resolve_invalid_object", path)
            return None
        try:
            reg = self.reg()
            schema = reg.load_schema(route)
            validator = reg.validator_for(route)
            self.refs[route] = reg.schema_ref_for(route)
            candidates = self._parts(schema, schema)
            node = next(p for p in candidates if p.get("properties", {}).get("object_kind", {}).get("const") == route)
        except Exception:
            self.unavailable(path)
            return None
        try:
            copied = self._copy(record, node, schema, set(), path, lane)
            if copied.get("object_kind") != route:
                self.add("resolve_route_mismatch", path)
                return None
        except _Admission:
            return None
        except (RecursionError, MemoryError):
            self.resource()
            return None
        except Exception:
            self.add("resolve_invalid_object", path)
            return None
        try:
            if next(validator.iter_errors(copied), None) is not None:
                self.add("resolve_schema_invalid", path)
                return None
            return copied
        except (RecursionError, MemoryError):
            self.resource()
        except Exception:
            self.unavailable(path)
        return None

    def equal(self, left: Any, right: Any, code: str, path: str) -> None:
        if left is not _ABSENT and right is not _ABSENT and left != right:
            self.add(code, path)

    def scalar(self, value: Any, definition: str, path: str) -> Any:
        if value is _ABSENT:
            self.missing(path)
            return _ABSENT
        if type(value) is not str:
            self.add("resolve_invalid_object", path)
            return _ABSENT
        if definition == "timestamp" and len(value) > _TIME_LIMIT:
            self.resource()
            return _ABSENT
        try:
            reg = self.reg()
            schema = reg.load_schema(_ROUTES[0])
            if not reg.validator_for(_ROUTES[0]).evolve(schema=schema["$defs"][definition]).is_valid(value):
                self.add("resolve_invalid_object", path)
                return _ABSENT
            return value
        except Exception:
            self.unavailable(path)
            return _ABSENT

    def time(self, value: Any, path: str) -> Fraction | None:
        value = self.scalar(value, "timestamp", path)
        if value is _ABSENT:
            return None
        try:
            match = _TIME.fullmatch(value)
            if match is None:
                raise ValueError
            y, m, d, h, minute, second = map(int, match.groups()[:6])
            total = date(y, m, d).toordinal() * 86400 + h * 3600 + minute * 60 + second
            fraction, offset = match.groups()[6:]
            if offset not in ("Z", "z"):
                total -= (1 if offset[0] == "+" else -1) * (int(offset[1:3]) * 3600 + int(offset[4:6]) * 60)
            return Fraction(total) + (Fraction("0." + fraction) if fraction else 0)
        except Exception:
            self.unavailable(path)
            return None

    def ordered(self, earlier: Any, later: Any, path: str) -> None:
        a, b = self.time(earlier, path), self.time(later, path)
        if a is not None and b is not None and a > b:
            self.add("resolve_timestamp_inconsistent", path)

    def finish(self, route: str | None, status: str) -> ValidationResult:
        decision = Decision.PASS
        for level, label in ((Decision.REJECT, "rejected"), (Decision.ERROR, "validation_unavailable"),
                             (Decision.NEEDS_REVIEW, "incomplete_resolution_context")):
            if any(d == level for d, _ in self.issues):
                decision, status = level, label
                break
        return ValidationResult(decision, status, route, "context-bridge-candidate" if route else None,
                                self.refs.get(route), tuple(i for _, i in self.issues))


def _authority_context(c: _Checks, raw: Any) -> dict[str, Any]:
    path = "$/resolution_context/authority_context"
    keys = ("object_bytes", "control_plane_selection", "operation", "evaluated_at")
    ctx = c.closed(raw, keys, keys, path)
    blobs = c.closed(ctx.get("object_bytes", _ABSENT), (_P, _R, _B), (_P, _R, _B), path)
    for key, value in tuple(blobs.items()):
        if type(value) is not bytes:
            c.add("resolve_invalid_object", path)
            del blobs[key]
    fields = ("client_id", "binding_fingerprint", "transport_binding_id", "transport_class")
    selection = c.closed(ctx.get("control_plane_selection", _ABSENT), fields, fields, path)
    # 只传原样标量和 bytes 给 P2D；不复制其 token/expiry/fingerprint 规则。
    for key, value in tuple(selection.items()):
        if type(value) is not str:
            c.add("resolve_invalid_object", path)
            del selection[key]
    clean: dict[str, Any] = {"object_bytes": blobs, "control_plane_selection": selection}
    for key in ("operation", "evaluated_at"):
        if key in ctx:
            if type(ctx[key]) is not str:
                c.add("resolve_invalid_object", path)
            else:
                clean[key] = ctx[key]
    c.equal(clean.get("operation", _ABSENT), "resolve_context", "resolve_authority_not_eligible", path)
    return clean


def _p2d(c: _Checks, r: Any, p: Any, b: Any, ctx: dict[str, Any]) -> ValidationResult | None:
    try:
        result = validate_reference_authority(r, p, b, authority_context=ctx, registry=c.reg())
        if result.decision == Decision.ERROR:
            c.unavailable("$/resolution_context/authority_context")
        elif result.decision == Decision.NEEDS_REVIEW:
            c.missing("$/resolution_context/authority_context")
        # 顶层 REJECT 可能同时含缺失/资源问题；错误原因匹配不能丢失它们。
        for issue in result.errors:
            if issue.code == "authority_context_missing":
                c.missing("$/resolution_context/authority_context")
            elif issue.code == "authority_resource_limit_exceeded":
                c.resource()
            elif issue.code == "authority_validation_unavailable":
                c.unavailable("$/resolution_context/authority_context")
            elif issue.code in ("authority_invalid_object", "authority_schema_invalid", "authority_route_mismatch", "authority_exact_input_mismatch"):
                c.add("resolve_invalid_object", "$/resolution_context/authority_context")
            elif issue.code == "authority_timestamp_inconsistent":
                c.add("resolve_timestamp_inconsistent", "$/resolution_context/authority_context")
        return result
    except (RecursionError, MemoryError):
        c.resource()
    except Exception:
        c.unavailable("$/resolution_context/authority_context")
    return None


def _eligible(c: _Checks, result: ValidationResult | None) -> None:
    if result is None:
        return
    if result.decision == Decision.REJECT:
        c.add("resolve_authority_not_eligible", "$/resolution_context/authority_context")
    elif result.decision == Decision.ERROR:
        c.unavailable("$/resolution_context/authority_context")
    elif result.decision == Decision.NEEDS_REVIEW:
        c.missing("$/resolution_context/authority_context")
    elif result.status != "authority_context_eligible":
        c.add("resolve_authority_not_eligible", "$/resolution_context/authority_context")


def _exchanges(c: _Checks, raw: Any) -> list[dict[str, Any]] | None:
    path = "$/resolution_context/source_exchanges"
    if raw is _ABSENT:
        return None
    if type(raw) not in (list, tuple):
        c.add("resolve_invalid_object", path)
        return None
    if len(raw) > 128:
        c.resource()
        return None
    admitted = []
    total = 0
    required = ("manifest", "request", "response", "expected_scope_id")
    for item in raw:
        ex = c.closed(item, required + ("exact_content_bytes",), required, path)
        if "exact_content_bytes" in ex:
            blob = ex["exact_content_bytes"]
            if type(blob) is not bytes:
                c.add("resolve_invalid_object", path)
                ex.pop("exact_content_bytes")
            else:
                total += len(blob)
        admitted.append(ex)
    # 在任何 Source 文本复制/编码或 P2C 调用之前检查整个 bytes 容器。
    if total > _BYTE_LIMIT:
        c.resource()
        return None
    for ex in admitted:
        for name in ("manifest", "request", "response"):
            record = ex.get(name, _ABSENT)
            route = "source_adapter_" + name
            if name == "response":
                route = _response_route(record, source=True)
            ex[name] = c.object(record, route, path, "source")
        scope = ex.get("expected_scope_id", _ABSENT)
        # 使用 P2C 已有 scope_id 定义，不将 access_scope 解释成 scope ID。
        if scope is not _ABSENT:
            try:
                reg = c.reg()
                schema = reg.load_schema("source_adapter_request")
                if type(scope) is not str or not reg.validator_for("source_adapter_request").evolve(schema=schema["$defs"]["object_id"]).is_valid(scope):
                    c.add("resolve_invalid_object", path)
            except Exception:
                c.unavailable(path)
        try:
            ex["checked"] = validate_source_adapter_exchange(
                ex.get("manifest"), ex.get("request"), ex.get("response"),
                exact_content_bytes=ex.get("exact_content_bytes"), registry=c.reg(),
            )
        except (RecursionError, MemoryError):
            c.resource()
        except Exception:
            c.unavailable(path)
    return admitted


def _response_route(record: Any, *, source: bool = False) -> str:
    prefix = "source_adapter_" if source else "resolve_context_"
    # 只为选择封闭路线读取 discriminator；先核对根键，未知值完全不访问。
    common = ("schema_version", "object_kind", "request_id", "error_code", "retryable", "observed_at")
    allowed = common + (("adapter_id", "operation", "source_id", "scope_id", "ok", "provenance",
                         "applied_limits", "payload", "provider_metadata", "field") if source else
                        ("reference_id", "reference_fingerprint", "binding_id", "trust_label", "freshness",
                         "provenance", "applied_limits", "minimum_disclosure", "payload_persistence", "payload"))
    try:
        if isinstance(record, Mapping):
            present = []
            for key in record:
                if len(present) >= len(allowed) or type(key) is not str or key not in allowed or key in present:
                    return prefix + "result"
                present.append(key)
            if "object_kind" in present:
                tag = record["object_kind"]
                if type(tag) is str and tag == prefix + "error":
                    return prefix + "error"
    except Exception:
        pass
    return prefix + "result"


def _source_links(c: _Checks, ex: dict[str, Any], r: Any, entries: Any, *, positive: bool) -> None:
    path = "$/resolution_context/source_exchanges"
    request, response = ex.get("request"), ex.get("response")
    c.equal(_field(request, "source_id"), _field(r, "source_id"), "resolve_source_observation_mismatch", path)
    c.equal(_field(request, "scope_id"), ex.get("expected_scope_id", _ABSENT), "resolve_source_observation_mismatch", path)
    if request is not None:
        if request["operation"] != "read":
            c.add("resolve_source_observation_mismatch", path)
        if entries is not None and request.get("target_locator") not in entries:
            c.add("resolve_entry_selection_mismatch", path)
    if positive and response is not None and response["object_kind"] == "source_adapter_result":
        c.equal(response["source_id"], _field(r, "source_id"), "resolve_source_observation_mismatch", path)
        c.equal(response["provenance"]["source_id"], _field(r, "source_id"), "resolve_source_observation_mismatch", path)


def _source_decision(c: _Checks, ex: dict[str, Any], *, error: bool = False) -> None:
    path = "$/resolution_context/source_exchanges"
    result = ex.get("checked")
    if result is None:
        c.unavailable(path)
    elif result.decision == Decision.ERROR:
        c.unavailable(path)
    elif result.decision == Decision.NEEDS_REVIEW:
        c.missing(path)
    elif result.decision != Decision.PASS or result.status != ("exchange_error_valid" if error else "exchange_valid"):
        c.add("resolve_error_evidence_mismatch" if error else "resolve_source_observation_mismatch", path)


def _positive(c: _Checks, q: Any, out: dict[str, Any], ctx: dict[str, Any], r: Any, b: Any,
              auth: dict[str, Any], authority: ValidationResult | None, entries: Any,
              exchanges: list[dict[str, Any]] | None) -> None:
    _eligible(c, authority)
    c.equal(out["binding_id"], _field(b, "binding_id"), "resolve_binding_mismatch", "$/response/binding_id")
    # 哈希前 P2D 已执行其自有 exact-object 准入；拒绝/缺失不升级为授权。
    blob = auth["object_bytes"].get(_R)
    if type(blob) is bytes and len(blob) <= _BYTE_LIMIT:
        c.equal(out["reference_fingerprint"], _fingerprint(blob), "resolve_reference_mismatch", "$/response/reference_fingerprint")
    payload, applied = out["payload"], out["applied_limits"]
    c.equal(applied["returned_items"], len(payload), "resolve_limit_mismatch", "$/response/applied_limits")
    c.equal(applied["returned_bytes"], sum(i["byte_count"] for i in payload), "resolve_limit_mismatch", "$/response/applied_limits")
    for dimension in ("items", "bytes"):
        if applied["returned_" + dimension] > applied["max_" + dimension]:
            c.add("resolve_limit_mismatch", "$/response/applied_limits")
        if q is not None and applied["max_" + dimension] > q["requested_limits"]["max_" + dimension]:
            c.add("resolve_limit_mismatch", "$/response/applied_limits")
    actual = [item["entry_point"] for item in payload]
    c.equal(out["provenance"]["source_id"], _field(r, "source_id"), "resolve_provenance_mismatch", "$/response/provenance")
    if entries is not None:
        if not _subset(out["provenance"]["entry_points"], entries) or any(e not in entries for e in actual):
            c.add("resolve_entry_selection_mismatch", "$/response/provenance")
    keys = ("observation_id", "verification_evidence_id", "observed_at", "verified_at")
    event = c.closed(ctx.get("resolution_event", _ABSENT), keys, keys, "$/resolution_context/resolution_event")
    for key in keys:
        if key in event:
            event[key] = c.scalar(event[key], "timestamp" if key.endswith("_at") else "stable_identifier", "$/resolution_context/resolution_event")
    for section, key, code in (
        ("provenance", "observation_id", "resolve_provenance_mismatch"),
        ("provenance", "observed_at", "resolve_provenance_mismatch"),
        ("freshness", "verification_evidence_id", "resolve_freshness_mismatch"),
        ("freshness", "verified_at", "resolve_freshness_mismatch"),
    ):
        c.equal(out[section][key], event.get(key, _ABSENT), code, "$/response/" + section)
    c.ordered(event.get("observed_at", _ABSENT), event.get("verified_at", _ABSENT), "$/resolution_context/resolution_event")
    c.ordered(event.get("verified_at", _ABSENT), ctx.get("resolved_at", _ABSENT), "$/resolution_context/resolved_at")
    profile = len(payload) <= 8 and len(set(actual)) == len(actual)
    if not profile or exchanges is None or len(exchanges) != len(payload):
        c.missing("$/resolution_context/source_exchanges")
        profile = False
    if profile:
        c.equal(out["provenance"]["entry_points"], actual, "resolve_provenance_mismatch", "$/response/provenance")
        if entries is not None and not _subset(actual, entries):
            c.add("resolve_entry_selection_mismatch", "$/response/payload")
    exact = []
    for index, ex in enumerate(exchanges or ()):
        _source_links(c, ex, r, entries, positive=True)
        _source_decision(c, ex)
        response, request, content = ex.get("response"), ex.get("request"), ex.get("exact_content_bytes")
        if content is None:
            c.missing("$/resolution_context/source_exchanges")
        if response is not None and response["object_kind"] == "source_adapter_result":
            when = response["provenance"]["observed_at"]
            c.ordered(auth.get("evaluated_at", _ABSENT), when, "$/resolution_context/source_exchanges")
            c.ordered(when, event.get("observed_at", _ABSENT), "$/resolution_context/source_exchanges")
        if not profile or response is None or request is None or response.get("operation") != "read" or response["object_kind"] != "source_adapter_result":
            continue
        item, read = payload[index], response["payload"]
        c.equal(item["entry_point"], request.get("target_locator", _ABSENT), "resolve_payload_mismatch", "$/response/payload")
        for key in ("text", "content_type", "encoding"):
            c.equal(item[key], read[key], "resolve_payload_mismatch", "$/response/payload")
        if type(content) is bytes:
            c.equal(item["byte_count"], len(content), "resolve_payload_mismatch", "$/response/payload")
            c.equal(item["content_fingerprint"], _fingerprint(content), "resolve_payload_fingerprint_mismatch", "$/response/payload")
            exact.append(content)
    if profile and len(exact) == len(payload):
        if len(exact) == 1:
            fingerprint = payload[0]["content_fingerprint"]
        else:
            # 仅本候选证据模式的有序分帧，不声称公共协议已有唯一聚合算法。
            digest = hashlib.sha256()
            digest.update(b"XINGSHU-RESOLVE-CONTENT-V1\x00")
            digest.update(len(exact).to_bytes(4, "big"))
            for content in exact:
                digest.update(len(content).to_bytes(8, "big"))
                digest.update(content)
            fingerprint = "sha256:" + digest.hexdigest()
        c.equal(out["provenance"]["content_fingerprint"], fingerprint, "resolve_provenance_mismatch", "$/response/provenance")


def _error(c: _Checks, out: dict[str, Any], ctx: dict[str, Any], r: Any, p: Any, b: Any,
           auth: dict[str, Any], authority: ValidationResult | None, entries: Any,
           exchanges: list[dict[str, Any]] | None) -> None:
    path = "$/response/error_code"
    if "resolution_event" in ctx:
        c.add("resolve_invalid_object", "$/resolution_context/resolution_event")
    c.ordered(out["observed_at"], ctx.get("resolved_at", _ABSENT), "$/response/observed_at")
    c.ordered(auth.get("evaluated_at", _ABSENT), out["observed_at"], "$/response/observed_at")
    code = out["error_code"]
    source_mode = code in ("limit_exceeded", "provenance_mismatch") or (code == "source_unavailable" and _field(r, "status") != "source_unavailable")
    if not source_mode:
        if exchanges:
            c.add("resolve_invalid_object", "$/resolution_context/source_exchanges")
        pairs = {(i.code, i.path) for i in authority.errors} if authority is not None else set()
        def has(name: str, location: str) -> bool:
            return (name, location) in pairs
        stale = (_field(b, "reference_id") is not _ABSENT and _field(b, "reference_id") == _field(r, "reference_id") and
                 has("authority_fingerprint_mismatch", "$/runtime_binding/reference_fingerprint"))
        binding_pairs = {
            ("authority_identity_mismatch", "$/runtime_binding/trusted_client_profile_id"),
            ("authority_identity_mismatch", "$/runtime_binding/reference_id"),
            ("authority_identity_mismatch", "$/authority_context/control_plane_selection/client_id"),
            ("authority_fingerprint_mismatch", "$/runtime_binding/trusted_client_profile_fingerprint"),
            ("authority_fingerprint_mismatch", "$/authority_context/control_plane_selection/binding_fingerprint"),
            ("authority_runtime_binding_mismatch", "$/runtime_binding/bound_access_scope"),
            ("authority_runtime_binding_mismatch", "$/authority_context/control_plane_selection/transport_binding_id"),
            ("authority_runtime_binding_mismatch", "$/authority_context/control_plane_selection/transport_class"),
            ("authority_entry_scope_mismatch", "$/runtime_binding/bound_entry_points"),
        }
        binding = bool(pairs & binding_pairs) or (not stale and has("authority_fingerprint_mismatch", "$/runtime_binding/reference_fingerprint"))
        # 原因的三态只描述本错误类，不是新增公共 Decision/status。先判断可用
        # 有效对象已经否定的原因；其他 bytes 缺失/校验不可用不得抹掉该矛盾。
        status = _field(r, "status")
        operation = auth.get("operation", _ABSENT)
        selected_client = auth.get("control_plane_selection", {}).get("client_id", _ABSENT)
        client_known = (r is not None and p is not None and b is not None and
                        selected_client == p["client_id"] and
                        b["trusted_client_profile_id"] == p["profile_id"])
        different_reference = r is not None and b is not None and b["reference_id"] != r["reference_id"]
        r_bytes = auth.get("object_bytes", {}).get(_R)
        # exact R 的解析/对象一致性仍归 P2D；没有重做 JSON 解析或授权门禁。
        exact_r_known = (r is not None and authority is not None and authority.decision != Decision.ERROR and
                         type(r_bytes) is bytes and len(r_bytes) <= _BYTE_LIMIT and not any(
                             issue.code in ("authority_exact_input_mismatch", "authority_invalid_object",
                                            "authority_schema_invalid", "authority_validation_unavailable")
                             for issue in authority.errors))
        binding_known = (r is not None and p is not None and b is not None and authority is not None and
                         authority.decision != Decision.ERROR and
                         all(type(auth.get("object_bytes", {}).get(k)) is bytes for k in (_R, _P, _B)) and
                         all(k in auth.get("control_plane_selection", {}) for k in
                             ("client_id", "binding_fingerprint", "transport_binding_id", "transport_class")) and
                         not any(issue.code in ("authority_invalid_object", "authority_schema_invalid",
                                                "authority_route_mismatch", "authority_exact_input_mismatch",
                                                "authority_validation_unavailable", "authority_resource_limit_exceeded")
                                 for issue in authority.errors))
        earlier_refusals = binding_pairs | {
            ("authority_fingerprint_mismatch", "$/runtime_binding/reference_fingerprint"),
            ("authority_client_not_allowed", "$/reference/allowed_clients"),
            ("authority_reference_not_active", "$/reference/status"),
            ("authority_profile_not_active", "$/client_profile/profile_status"),
            ("authority_profile_expired", "$/client_profile/expires_at"),
            ("authority_operation_not_allowed", "$/authority_context/operation"),
        }
        contradicted = {
            "reference_not_active": r is not None and status not in ("paused", "revoked", "archived"),
            "stale_locator": r is not None and status != "stale_locator",
            "client_not_allowed": client_known and p["client_id"] in r["allowed_clients"],
            "stale_reference": different_reference or (
                b is not None and exact_r_known and b["reference_fingerprint"] == _fingerprint(r_bytes)),
            "binding_mismatch": not binding and (stale or binding_known),
            "unsupported_request": b is not None and operation == "resolve_context" and "resolve_context" in b["allowed_operations"],
            "freshness_verification_required": (r is not None and status != "active") or bool(pairs & earlier_refusals),
        }.get(code, False)
        supported = {
            "client_not_allowed": client_known and has("authority_client_not_allowed", "$/reference/allowed_clients"),
            "reference_not_active": _field(r, "status") in ("paused", "revoked", "archived") and has("authority_reference_not_active", "$/reference/status"),
            "stale_locator": _field(r, "status") == "stale_locator" and has("authority_reference_not_active", "$/reference/status"),
            "source_unavailable": _field(r, "status") == "source_unavailable" and has("authority_reference_not_active", "$/reference/status"),
            "stale_reference": stale,
            "binding_mismatch": binding,
            "unsupported_request": has("authority_operation_not_allowed", "$/authority_context/operation"),
        }.get(code, False)
        # P2D 完整准入通过也能否定冻结的授权拒绝原因；freshness 则仍无
        # 客观正向原因证明。client 身份未绑定时不借助其他缺失项猜测身份。
        if (not supported and code != "freshness_verification_required" and authority is not None and
                authority.decision == Decision.PASS and authority.status == "authority_context_eligible"):
            contradicted = True
        evidence = "CONTRADICTED" if contradicted else "SUPPORTED" if supported else "UNRESOLVED"
        if evidence == "CONTRADICTED":
            c.add("resolve_error_evidence_mismatch", path)
        elif evidence == "UNRESOLVED":
            c.missing(path)
        return
    _eligible(c, authority)
    if exchanges is None or not exchanges:
        c.missing("$/resolution_context/source_exchanges")
        return
    if len(exchanges) != 1:
        c.add("resolve_invalid_object", "$/resolution_context/source_exchanges")
        return
    ex = exchanges[0]
    _source_links(c, ex, r, entries, positive=False)
    response, request, result = ex.get("response"), ex.get("request"), ex.get("checked")
    if code != "provenance_mismatch":
        _source_decision(c, ex, error=True)
        if response is not None and response["object_kind"] != "source_adapter_error":
            c.add("resolve_error_evidence_mismatch", path)
        if response is not None and response["object_kind"] == "source_adapter_error":
            c.equal(response["error_code"], code, "resolve_error_evidence_mismatch", path)
            c.equal(response["retryable"], out["retryable"], "resolve_error_evidence_mismatch", "$/response/retryable")
            c.equal(response["observed_at"], out["observed_at"], "resolve_error_evidence_mismatch", "$/response/observed_at")
        return
    allowed = {("source_adapter_provenance_mismatch", "$/response/provenance/" + k)
               for k in ("source_id", "scope_id", "adapter_id", "operation")}
    allowed.add(("source_adapter_fingerprint_mismatch", "$/response/provenance/content_fingerprint"))
    if response is not None and response["object_kind"] != "source_adapter_result":
        c.add("resolve_error_evidence_mismatch", path)
    if result is None:
        c.unavailable(path)
        return
    if result.decision == Decision.ERROR:
        c.unavailable(path)
        return
    if result.decision == Decision.NEEDS_REVIEW:
        c.missing(path)
        return
    observed = {(i.code, i.path) for i in result.errors}
    if not observed or not observed <= allowed or response is None or response["object_kind"] != "source_adapter_result":
        c.add("resolve_error_evidence_mismatch", path)
        return
    # P2C 发现局部 provenance 矛盾会提前返回；这里绑定该畸形观察到本请求，
    # 不要求/伪造 exchange_valid，也不把其他 P2C REJECT 泛化成业务原因。
    c.equal(_field(request, "adapter_id"), _field(ex.get("manifest"), "adapter_id"),
            "resolve_error_evidence_mismatch", path)
    for key in ("request_id", "adapter_id", "operation", "source_id", "scope_id"):
        c.equal(response[key], _field(request, key), "resolve_error_evidence_mismatch", path)
    if response["operation"] != "read":
        c.add("resolve_error_evidence_mismatch", path)
    else:
        c.equal(response["payload"]["locator"], _field(request, "target_locator"), "resolve_error_evidence_mismatch", path)
        content = ex.get("exact_content_bytes")
        if content is None:
            c.missing("$/resolution_context/source_exchanges")
        elif content != response["payload"]["text"].encode("utf-8"):
            c.add("resolve_error_evidence_mismatch", path)
    when = response["provenance"]["observed_at"]
    c.ordered(auth.get("evaluated_at", _ABSENT), when, "$/response/observed_at")
    c.ordered(when, out["observed_at"], "$/response/observed_at")


def validate_resolve_context_object(record: Mapping[str, Any], expected_route: str,
                                    registry: SchemaRegistry | None = None) -> ValidationResult:
    """三路线单对象仅证明严格结构；不证明交换、授权、错误原因或实际读取。"""
    c = _Checks(registry)
    if type(expected_route) is not str or expected_route not in _ROUTES:
        c.add("resolve_unsupported_route", "$")
        return c.finish(None, "object_valid")
    c.object(record, expected_route, "$", "resolve")
    return c.finish(expected_route, "object_valid")


def validate_resolve_context_exchange(request: Any, response: Any, *,
                                      resolution_context: Mapping[str, Any] | None = None,
                                      registry: SchemaRegistry | None = None) -> ValidationResult:
    """检查冻结的候选证据模式；未支持的转换为不完整，明确失配为拒绝。

    上下文预期由 Owner 控制路径注入，本函数无法认证其供应者。正向 PASS
    不证明现实 I/O/新鲜度/身份；错误 PASS 不证明 Resolve 成功或全局重试政策。
    """
    c = _Checks(registry)
    route = _response_route(response)
    try:
        q = c.object(_ABSENT if request is None else request, _ROUTES[0], "$/request", "resolve")
        out = c.object(_ABSENT if response is None else response, route, "$/response", "resolve")
        required = ("reference", "runtime_binding", "client_profile", "authority_context", "resolved_at")
        ctx = c.closed(_ABSENT if resolution_context is None else resolution_context,
                       required + ("source_exchanges", "resolution_event"), required, "$/resolution_context")
        r = c.object(ctx.get("reference", _ABSENT), _R, "$/resolution_context/reference")
        p = c.object(ctx.get("client_profile", _ABSENT), _P, "$/resolution_context/client_profile")
        b = c.object(ctx.get("runtime_binding", _ABSENT), _B, "$/resolution_context/runtime_binding")
        auth = _authority_context(c, ctx.get("authority_context", _ABSENT))
        c.time(ctx.get("resolved_at", _ABSENT), "$/resolution_context/resolved_at")
        authority = _p2d(c, r, p, b, auth)
        c.equal(_field(q, "reference_id"), _field(r, "reference_id"), "resolve_reference_mismatch", "$/request/reference_id")
        for key in ("request_id", "reference_id"):
            c.equal(_field(out, key), _field(q, key), "resolve_request_linkage_mismatch", "$/response/" + key)
        c.equal(_field(out, "reference_id"), _field(r, "reference_id"), "resolve_reference_mismatch", "$/response/reference_id")
        entries = b["bound_entry_points"] if b is not None else None
        if q is not None and "entry_selection" in q:
            if entries is not None and not _subset(q["entry_selection"], entries):
                c.add("resolve_entry_selection_mismatch", "$/request/entry_selection")
            entries = q["entry_selection"]
        # Error 的禁用字段在读取任何 Source 子对象之前拒绝。
        if route == _ROUTES[2] and "resolution_event" in ctx:
            c.add("resolve_invalid_object", "$/resolution_context/resolution_event")
        raw_exchanges = ctx.get("source_exchanges", _ABSENT)
        authority_error = out is not None and route == _ROUTES[2] and (
            out["error_code"] not in ("source_unavailable", "limit_exceeded", "provenance_mismatch")
            or (out["error_code"] == "source_unavailable" and _field(r, "status") == "source_unavailable"))
        if authority_error and raw_exchanges is not _ABSENT:
            # 模式禁止的 Source 数据在元素读取前处理，不为了解释授权错误处理正文。
            if type(raw_exchanges) not in (list, tuple) or len(raw_exchanges):
                c.add("resolve_invalid_object", "$/resolution_context/source_exchanges")
            exchanges = []
        else:
            exchanges = _exchanges(c, raw_exchanges)
        if out is not None:
            if route == _ROUTES[1]:
                _positive(c, q, out, ctx, r, b, auth, authority, entries, exchanges)
            else:
                _error(c, out, ctx, r, p, b, auth, authority, entries, exchanges)
    except (RecursionError, MemoryError):
        c.resource()
    except Exception:
        c.unavailable("$/resolution_context")
    return c.finish(route, "resolve_error_valid" if route == _ROUTES[2] else "resolve_exchange_valid")
