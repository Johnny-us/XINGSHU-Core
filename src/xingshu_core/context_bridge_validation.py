"""Context Bridge（上下文桥）的候选纯校验，默认不启用任何能力。

governance_effect=none; authorization_effect=none; activation_effect=none.
PASS 仅表示显式对象与证据在所执行的检查内一致，不认证真人或编排层，
不证明来源当前可用、包含关系、全局禁止覆盖、完整历史或原子持久化。
只由既有 Registry 加载 Schema；不读取来源、策略文件、数据库或当前时间。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any

from .decisions import Decision, ValidationIssue, ValidationResult
from .schema_registry import SchemaRegistry
from .source_adapter_validation import (
    validate_source_adapter_exchange,
    validate_source_adapter_object,
)

__all__ = [
    "validate_context_bridge_object",
    "validate_registration_validation",
    "validate_registration_chain",
    "validate_reference_transition",
]

_ROUTES = (
    "context_candidate", "context_registration_proposal", "context_validation_artifact",
    "human_authorization_evidence", "registered_context_reference", "context_reference_transition",
)
_JSON_BYTES = 16_777_216
_OPAQUE_BYTES = 1_048_576
_ID_COUNT = 10_000
_ABSENT = object()
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}")
_TIME = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})"
    r"(?:\.(\d+))?([Zz]|[+-]\d{2}:\d{2})"
)

# 固定消息与代码。禁止将输入 ID、未知键、异常、V.issue_codes 拼入诊断。
_MESSAGES = {
    "context_bridge_invalid_object": "input does not satisfy the closed input contract",
    "context_bridge_unsupported_route": "unsupported context bridge route",
    "context_bridge_route_mismatch": "object kind does not match the expected route",
    "context_bridge_schema_invalid": "object violates the frozen schema",
    "context_bridge_validation_unavailable": "strict validation is unavailable",
    "context_bridge_resource_limit_exceeded": "validation could not complete within the private processing budget",
    "context_bridge_missing_context": "required evidence or contract object is missing",
    "context_bridge_exact_input_mismatch": "exact bytes do not represent the supplied object",
    "context_bridge_fingerprint_mismatch": "exact evidence fingerprint does not match",
    "context_bridge_identity_mismatch": "object identities do not match",
    "context_bridge_source_linkage_mismatch": "source linkage does not match",
    "context_bridge_validation_outcome_not_pass": "validation outcome does not permit a positive chain result",
    "context_bridge_review_evidence_mismatch": "review evidence fingerprint does not match",
    "context_bridge_policy_mismatch": "policy identity or evidence does not match",
    "context_bridge_snapshot_mismatch": "snapshot evidence does not match",
    "context_bridge_source_observation_mismatch": "source observation does not match the required exchange or entry",
    "context_bridge_source_observation_not_successful": "source error evidence is not a successful observation",
    "context_bridge_timestamp_inconsistent": "explicit event timestamps are inconsistent",
    "context_bridge_authorization_projection_mismatch": "registration projection does not match the authorization",
    "context_bridge_entry_selection_mismatch": "selected entries are not an exact ordered subset",
    "context_bridge_reference_already_exists": "reference identity already exists in the supplied index",
    "context_bridge_transition_state_mismatch": "transition state does not match the supplied reference",
    "context_bridge_immutable_binding_changed": "transition changes a field other than lifecycle status",
    "context_bridge_transition_replay_detected": "transition identity already exists in the supplied history",
}


def _copy(value: Any, active: set[int], *, allow_bytes: bool = False) -> Any:
    """复制 JSON 容器；上下文字节保持不可变，不执行其中的指令。"""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if allow_bytes and type(value) is bytes:
        return value
    sequence = (type(value) in (list, tuple) if allow_bytes else
                isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)))
    if isinstance(value, Mapping) or sequence:
        identity = id(value)
        if identity in active:
            raise ValueError("cyclic input")
        active.add(identity)
        try:
            if isinstance(value, Mapping):
                if any(type(key) is not str for key in value):
                    raise ValueError("non-string key")
                return {key: _copy(child, active, allow_bytes=allow_bytes) for key, child in value.items()}
            return [_copy(child, active, allow_bytes=allow_bytes) for child in value]
        finally:
            active.remove(identity)
    raise ValueError("non-JSON input")


def _same(left: Any, right: Any) -> bool:
    """逻辑比较保留存在性、数组顺序和布尔类型，不损失数值精度。"""
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_same(left[k], right[k]) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    if type(left) is bool or type(right) is bool:
        return type(left) is type(right) and left == right
    numbers = (int, float, Decimal)
    if type(left) in numbers and type(right) in numbers:
        # Decimal(float) 保留原二进制值，不用 str(float) 掩盖舍入差异。
        return Decimal(left) == Decimal(right)
    return type(left) is type(right) and left == right


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> Any:
    raise ValueError("non-finite JSON constant")


class _Checks:
    """单次调用的局部诊断累积器；没有持久状态或新的 Registry。"""

    def __init__(self, registry: SchemaRegistry | None) -> None:
        self.registry = registry
        self.findings: list[tuple[Decision, ValidationIssue]] = []
        self.refs: dict[str, str] = {}

    def add(self, code: str, path: str, decision: Decision = Decision.REJECT) -> None:
        # path 仅由代码中已知字段和数字下标生成，不接收输入键或值。
        issue = ValidationIssue(code, path, _MESSAGES[code], None)
        item = (decision, issue)
        if item not in self.findings:
            self.findings.append(item)

    def missing(self, path: str) -> None:
        self.add("context_bridge_missing_context", path, Decision.NEEDS_REVIEW)

    def unavailable(self, path: str) -> None:
        self.add("context_bridge_validation_unavailable", path, Decision.ERROR)

    def resource(self, path: str) -> None:
        self.add("context_bridge_resource_limit_exceeded", path, Decision.ERROR)

    def get_registry(self) -> SchemaRegistry:
        if self.registry is None:
            self.registry = SchemaRegistry()
        return self.registry

    def snapshot(self, value: Any, path: str, *, context: bool = False) -> Any:
        try:
            return _copy(value, set(), allow_bytes=context)
        except (RecursionError, MemoryError):
            self.resource(path)
        except Exception:
            self.add("context_bridge_invalid_object", path)
        return _ABSENT

    def contract(self, record: Any, route: str, path: str) -> dict[str, Any] | None:
        if record is None or record is _ABSENT:
            self.missing(path)
            return None
        value = self.snapshot(record, path)
        if value is _ABSENT:
            return None
        if not isinstance(value, dict):
            self.add("context_bridge_invalid_object", path)
            return None
        if value.get("object_kind") != route:
            self.add("context_bridge_route_mismatch", path + "/object_kind")
            return None
        try:
            reg = self.get_registry()
            self.refs[route] = reg.schema_ref_for(route)
            invalid = next(reg.validator_for(route).iter_errors(value), None) is not None
        except (RecursionError, MemoryError):
            self.resource(path)
            return None
        except Exception:
            self.unavailable(path)
            return None
        if invalid:
            self.add("context_bridge_schema_invalid", path)
            return None
        return value

    def closed(self, value: Any, allowed: tuple[str, ...], required: tuple[str, ...], path: str) -> dict[str, Any]:
        """仅检查当前层键名并读取已知字段；不遍历未知值或递归复制证据。"""
        if value is _ABSENT:
            self.missing(path)
            return {}
        if not isinstance(value, Mapping):
            self.add("context_bridge_invalid_object", path)
            return {}
        try:
            if any(type(key) is not str or key not in allowed for key in value):
                self.add("context_bridge_invalid_object", path)
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
            self.add("context_bridge_invalid_object", path)
        return {}

    def token(self, value: Any, path: str, *, fingerprint: bool = False) -> str | None:
        if value is _ABSENT:
            return None  # closed() 已记录缺失项。
        pattern = _FINGERPRINT if fingerprint else _ID
        if type(value) is not str or pattern.fullmatch(value) is None:
            self.add("context_bridge_invalid_object", path)
            return None
        return value

    def bounded_bytes(self, value: Any, path: str, limit: int = _JSON_BYTES, *, empty: bool = False) -> bytes | None:
        if value is _ABSENT:
            return None
        if type(value) is not bytes:
            self.add("context_bridge_invalid_object", path)
            return None
        if len(value) > limit:
            self.resource(path)
            return None
        if not value and not empty:
            self.add("context_bridge_invalid_object", path)
            return None
        return value

    def exact(self, value: Any, record: dict[str, Any] | None, path: str, *, route: str | None = None) -> str | None:
        blob = self.bounded_bytes(value, path)
        if blob is None:
            return None
        fingerprint = "sha256:" + hashlib.sha256(blob).hexdigest()
        try:
            text = blob.decode("utf-8", errors="strict")
            if text.startswith("\ufeff"):
                raise ValueError("BOM")
            parsed = json.loads(text, object_pairs_hook=_unique_pairs,
                                parse_int=Decimal, parse_float=Decimal, parse_constant=_invalid_constant)
            if not isinstance(parsed, dict):
                raise ValueError("object required")
            if route is not None:
                self.contract(parsed, route, path)
            if record is not None and not _same(parsed, record):
                self.add("context_bridge_exact_input_mismatch", path)
        except (RecursionError, MemoryError):
            self.resource(path)
        except Exception:
            self.add("context_bridge_exact_input_mismatch", path)
        return fingerprint

    def ids(self, value: Any, path: str) -> list[str] | None:
        if value is _ABSENT:
            return None
        if type(value) not in (list, tuple):
            self.add("context_bridge_invalid_object", path)
            return None
        if len(value) > _ID_COUNT:
            self.resource(path)
            return None
        result: list[str] = []
        seen: set[str] = set()
        for i, item in enumerate(value):
            token = self.token(item, f"{path}/{i}")
            if token is not None:
                if token in seen:
                    self.add("context_bridge_invalid_object", path)
                seen.add(token)
                result.append(token)
        return result

    def equal(self, left: Any, right: Any, path: str, code: str) -> None:
        if left is not _ABSENT and right is not _ABSENT and not _same(left, right):
            self.add(code, path)

    def group(self, pairs: list[tuple[Any, str]], code: str) -> None:
        present = [(value, path) for value, path in pairs if value is not _ABSENT]
        for value, path in present[1:]:
            self.equal(value, present[0][0], path, code)

    def timestamp(self, value: Any, path: str) -> Fraction | None:
        if value is _ABSENT:
            return None
        if type(value) is not str:
            self.add("context_bridge_invalid_object", path)
            return None
        try:
            checker = self.get_registry().validator_for("context_validation_artifact").format_checker
            if checker is None:
                raise RuntimeError("format checker missing")
            if not checker.conforms(value, "date-time"):
                self.add("context_bridge_schema_invalid", path)
                return None
            match = _TIME.fullmatch(value)
            if match is None:
                raise RuntimeError("timestamp comparison unavailable")
            year, month, day, hour, minute, second = map(int, match.groups()[:6])
            seconds = date(year, month, day).toordinal() * 86400 + hour * 3600 + minute * 60 + second
            fraction = match.group(7)
            offset = match.group(8)
            if offset not in ("Z", "z"):
                direction = 1 if offset[0] == "+" else -1
                seconds -= direction * (int(offset[1:3]) * 3600 + int(offset[4:6]) * 60)
            return Fraction(seconds) + (Fraction("0." + fraction) if fraction else 0)
        except (RecursionError, MemoryError):
            self.resource(path)
        except Exception:
            self.unavailable(path)
        return None

    def ordered_time(self, earlier: Any, later: Any, earlier_path: str, later_path: str) -> None:
        first = self.timestamp(earlier, earlier_path)
        last = self.timestamp(later, later_path)
        if first is not None and last is not None and first > last:
            self.add("context_bridge_timestamp_inconsistent", later_path)

    def finish(self, route: str | None, success_status: str) -> ValidationResult:
        decision, status = Decision.PASS, success_status
        for candidate, label in ((Decision.REJECT, "rejected"), (Decision.ERROR, "validation_unavailable"),
                                 (Decision.NEEDS_REVIEW, "incomplete_chain")):
            if any(level == candidate for level, _ in self.findings):
                decision, status = candidate, label
                break
        return ValidationResult(decision, status, route,
                                "context-bridge-candidate" if route in _ROUTES else None,
                                self.refs.get(route), tuple(issue for _, issue in self.findings))


def _field(record: dict[str, Any] | None, name: str) -> Any:
    return record.get(name, _ABSENT) if record is not None else _ABSENT


def _digest(blob: bytes | None) -> Any:
    return "sha256:" + hashlib.sha256(blob).hexdigest() if blob is not None else _ABSENT


def _context(checks: _Checks, supplied: Any, *, transition: bool, registration: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    path = "$/evidence_context"
    value = _ABSENT if supplied is None else supplied
    allowed = (("object_bytes", "transition_history") if transition else
               ("object_bytes", "review_evidence_bytes", "policy", "existing_snapshot", "source_observations"))
    required = ("object_bytes",) if transition else allowed
    context = checks.closed(value, allowed, required, path)
    names = (("previous_reference", "new_reference") if transition else
             ("candidate", "proposal", "validation_artifact"))
    mandatory = names if transition or registration else names[:2]
    representations = checks.closed(context.get("object_bytes", _ABSENT), names, mandatory, path + "/object_bytes")
    return context, representations


def _policy_snapshot(checks: _Checks, context: dict[str, Any], validation: dict[str, Any] | None,
                     reference: dict[str, Any] | None, registration: bool) -> None:
    base = "$/evidence_context"
    review = checks.bounded_bytes(context.get("review_evidence_bytes", _ABSENT), base + "/review_evidence_bytes", _OPAQUE_BYTES)
    checks.equal(_field(validation, "review_evidence_fingerprint"), _digest(review), "$/validation_artifact/review_evidence_fingerprint", "context_bridge_review_evidence_mismatch")
    keys = ("policy_id", "policy_version", "policy_bytes", "expected_policy_fingerprint")
    policy = checks.closed(context.get("policy", _ABSENT), keys, keys, base + "/policy")
    for key, v_field in (("policy_id", "validation_policy_id"), ("policy_version", "validation_policy_version")):
        token = checks.token(policy.get(key, _ABSENT), base + "/policy/" + key)
        checks.equal(_field(validation, v_field), token if token is not None else _ABSENT,
                     "$/validation_artifact/" + v_field, "context_bridge_policy_mismatch")
    policy_blob = checks.bounded_bytes(policy.get("policy_bytes", _ABSENT), base + "/policy/policy_bytes", _OPAQUE_BYTES)
    policy_fp = checks.token(policy.get("expected_policy_fingerprint", _ABSENT), base + "/policy/expected_policy_fingerprint", fingerprint=True)
    checks.equal(_digest(policy_blob), policy_fp if policy_fp is not None else _ABSENT, base + "/policy/expected_policy_fingerprint", "context_bridge_policy_mismatch")
    required = ("snapshot_bytes", "id_index") if registration else ("snapshot_bytes",)
    snapshot = checks.closed(context.get("existing_snapshot", _ABSENT), ("snapshot_bytes", "id_index"), required, base + "/existing_snapshot")
    snapshot_blob = checks.bounded_bytes(snapshot.get("snapshot_bytes", _ABSENT), base + "/existing_snapshot/snapshot_bytes")
    snapshot_fp = _digest(snapshot_blob)
    checks.equal(_field(validation, "existing_reference_snapshot_fingerprint"), snapshot_fp,
                 "$/validation_artifact/existing_reference_snapshot_fingerprint", "context_bridge_snapshot_mismatch")
    if "id_index" in snapshot:
        path = base + "/existing_snapshot/id_index"
        index = checks.closed(snapshot["id_index"], ("snapshot_fingerprint", "reference_ids"), ("snapshot_fingerprint", "reference_ids"), path)
        index_fp = checks.token(index.get("snapshot_fingerprint", _ABSENT), path + "/snapshot_fingerprint", fingerprint=True)
        checks.equal(index_fp if index_fp is not None else _ABSENT, snapshot_fp, path + "/snapshot_fingerprint", "context_bridge_snapshot_mismatch")
        ids = checks.ids(index.get("reference_ids", _ABSENT), path + "/reference_ids")
        if reference is not None and ids is not None and reference["reference_id"] in ids:
            checks.add("context_bridge_reference_already_exists", "$/reference/reference_id")


def _observations(checks: _Checks, context: dict[str, Any], candidate: dict[str, Any] | None,
                  proposal: dict[str, Any] | None, validation: dict[str, Any] | None) -> None:
    root = "$/evidence_context/source_observations"
    supplied = context.get("source_observations", _ABSENT)
    entries = _field(proposal, "suggested_source_entry_points")
    fingerprints = _field(validation, "source_observation_fingerprints")
    counts = [(len(value), path) for value, path in (
        (entries, "$/proposal/suggested_source_entry_points"),
        (fingerprints, "$/validation_artifact/source_observation_fingerprints"),
        (supplied, root),
    ) if type(value) in (list, tuple)]
    checks.group(counts, "context_bridge_source_observation_mismatch")
    if supplied is _ABSENT:
        return
    if type(supplied) not in (list, tuple):
        checks.add("context_bridge_invalid_object", root)
        return
    if len(supplied) > 8:
        checks.resource(root)
        return
    if not supplied:
        checks.add("context_bridge_source_observation_mismatch", root)
    required = ("entry_index", "evidence_bytes", "manifest", "request", "response", "expected_scope_id")
    for i, raw in enumerate(supplied):
        path = f"{root}/{i}"
        observation = checks.closed(raw, required + ("exact_content_bytes",), required, path)
        if "entry_index" in observation:
            if type(observation["entry_index"]) is not int or observation["entry_index"] != i:
                checks.add("context_bridge_source_observation_mismatch", path + "/entry_index")
        scope = checks.token(observation.get("expected_scope_id", _ABSENT), path + "/expected_scope_id")
        valid: dict[str, dict[str, Any]] = {}
        try:
            reg = checks.get_registry()
            # P2C 负责对象与交换规则；部分上下文缺失时仍检查其他可用对象。
            for name in ("manifest", "request", "response"):
                item = observation.get(name, _ABSENT)
                if item is _ABSENT:
                    continue
                # 只有通过外层容器与预算准入后，才复制本条观察的合同对象。
                item = checks.snapshot(item, path + "/" + name, context=True)
                observation[name] = None if item is _ABSENT else item
                if item is _ABSENT:
                    continue
                route = "source_adapter_" + name
                if name == "response":
                    route = "source_adapter_error" if isinstance(item, dict) and item.get("object_kind") == "source_adapter_error" else "source_adapter_result"
                result = validate_source_adapter_object(item, route, reg)
                if result.decision == Decision.PASS:
                    valid[name] = item
                    if route == "source_adapter_error":
                        checks.add("context_bridge_source_observation_not_successful", path + "/response")
                elif result.decision == Decision.ERROR:
                    checks.unavailable(path + "/" + name)
                else:
                    checks.add("context_bridge_source_observation_mismatch", path + "/" + name)
            content = None
            if "exact_content_bytes" in observation:
                content = checks.bounded_bytes(observation["exact_content_bytes"], path + "/exact_content_bytes", empty=True)
            # 正文字节不可处理时已记录错误，仍由 P2C 检查独立的交换关联。
            # None 不替代原始字节证据，也不会消除本次调用的预算或格式错误。
            result = validate_source_adapter_exchange(
                observation.get("manifest"), observation.get("request"), observation.get("response"),
                exact_content_bytes=content, registry=reg,
            )
            if result.decision == Decision.REJECT:
                checks.add("context_bridge_source_observation_mismatch", path)
            elif result.decision == Decision.ERROR:
                checks.unavailable(path)
            elif result.decision == Decision.NEEDS_REVIEW:
                checks.missing(path)
            elif result.status != "exchange_valid":
                checks.add("context_bridge_source_observation_not_successful", path + "/response")
        except (RecursionError, MemoryError):
            checks.resource(path)
        except Exception:
            checks.unavailable(path)
        response = valid.get("response")
        fp = checks.exact(observation.get("evidence_bytes", _ABSENT), response, path + "/evidence_bytes")
        if isinstance(fingerprints, list) and i < len(fingerprints):
            checks.equal(fingerprints[i], fp if fp is not None else _ABSENT,
                         f"$/validation_artifact/source_observation_fingerprints/{i}", "context_bridge_source_observation_mismatch")
        request = valid.get("request")
        if request is not None:
            # capabilities 没有目标，不能满足逐入口观察；不对 list 子项推断包含关系。
            if "target_locator" not in request:
                checks.add("context_bridge_source_observation_mismatch", path + "/request/target_locator")
            elif isinstance(entries, list) and i < len(entries):
                checks.equal(request["target_locator"], entries[i], path + "/request/target_locator", "context_bridge_source_observation_mismatch")
            checks.equal(request["source_id"], _field(candidate, "source_id"), path + "/request/source_id", "context_bridge_source_linkage_mismatch")
            checks.equal(request["scope_id"], scope if scope is not None else _ABSENT, path + "/request/scope_id", "context_bridge_source_linkage_mismatch")
        if response is not None and response["object_kind"] == "source_adapter_result":
            checks.ordered_time(response["provenance"]["observed_at"], _field(validation, "source_revalidated_at"),
                                path + "/response/provenance/observed_at", "$/validation_artifact/source_revalidated_at")


def _registration(checks: _Checks, candidate: Any, proposal: Any, validation: Any,
                  authorization: Any, reference: Any, context: dict[str, Any], blobs: dict[str, Any], *, full: bool) -> None:
    inputs = ((candidate, "candidate"), (proposal, "proposal"), (validation, "validation_artifact"))
    digests = {name: checks.exact(blobs[name], record, "$/evidence_context/object_bytes/" + name)
               for record, name in inputs if name in blobs}
    def bindings(field: str, records: tuple[tuple[Any, str], ...], *, digest: str | None = None) -> None:
        pairs = [(_field(record, field), f"$/{name}/{field}") for record, name in records]
        if digest is not None and digests.get(digest) is not None:
            pairs.insert(0, (digests[digest], "$/evidence_context/object_bytes/" + digest))
        checks.group(pairs, "context_bridge_fingerprint_mismatch" if digest else "context_bridge_identity_mismatch")
    bindings("candidate_id", ((candidate, "candidate"), (proposal, "proposal"), (validation, "validation_artifact"), (authorization, "authorization")))
    bindings("proposal_id", ((proposal, "proposal"), (validation, "validation_artifact"), (authorization, "authorization")))
    bindings("candidate_fingerprint", ((proposal, "proposal"), (validation, "validation_artifact"), (authorization, "authorization")), digest="candidate")
    bindings("proposal_fingerprint", ((validation, "validation_artifact"), (authorization, "authorization")), digest="proposal")
    if validation is not None and validation["validation_outcome"] != "pass":
        level = Decision.REJECT if full or validation["validation_outcome"] == "reject" else Decision.NEEDS_REVIEW
        checks.add("context_bridge_validation_outcome_not_pass", "$/validation_artifact/validation_outcome", level)
    _policy_snapshot(checks, context, validation, reference, full)
    _observations(checks, context, candidate, proposal, validation)
    checks.ordered_time(_field(validation, "source_revalidated_at"), _field(validation, "validated_at"),
                        "$/validation_artifact/source_revalidated_at", "$/validation_artifact/validated_at")
    if not full:
        return
    bindings("validation_artifact_id", ((validation, "validation_artifact"), (authorization, "authorization")))
    checks.equal(_field(authorization, "validation_artifact_fingerprint"), digests.get("validation_artifact") or _ABSENT,
                 "$/authorization/validation_artifact_fingerprint", "context_bridge_fingerprint_mismatch")
    for field in ("context_type", "source_id"):
        checks.equal(_field(authorization, field), _field(candidate, field), "$/authorization/" + field, "context_bridge_source_linkage_mismatch")
    checks.equal(_field(authorization, "final_source_locator"), _field(candidate, "source_locator"),
                 "$/authorization/final_source_locator", "context_bridge_source_linkage_mismatch")
    projection = (
        ("registration_authorization_id", "authorization_id"), ("context_type", "context_type"),
        ("source_id", "source_id"), ("status", "initial_status"), ("retrieval_hint", "retrieval_hint"),
        ("canonical_name", "final_canonical_name"), ("source_locator", "final_source_locator"),
        ("source_entry_points", "final_source_entry_points"), ("access_scope", "final_access_scope"),
        ("allowed_clients", "final_allowed_clients"), ("freshness_policy", "final_freshness_policy"),
        ("provenance_policy", "final_provenance_policy"),
    )
    for r_field, h_field in projection:
        checks.equal(_field(reference, r_field), _field(authorization, h_field), "$/reference/" + r_field, "context_bridge_authorization_projection_mismatch")
    if authorization is not None and reference is not None:
        if ("final_aliases" in authorization) != ("aliases" in reference) or not _same(authorization.get("final_aliases"), reference.get("aliases")):
            checks.add("context_bridge_authorization_projection_mismatch", "$/reference/aliases")
    if authorization is not None and proposal is not None:
        entries = iter(proposal["suggested_source_entry_points"])
        if not all(any(entry == selection for entry in entries) for selection in authorization["final_source_entry_points"]):
            checks.add("context_bridge_entry_selection_mismatch", "$/authorization/final_source_entry_points")
    checks.ordered_time(_field(validation, "validated_at"), _field(authorization, "authorized_at"), "$/validation_artifact/validated_at", "$/authorization/authorized_at")
    checks.ordered_time(_field(authorization, "authorized_at"), _field(reference, "registered_at"), "$/authorization/authorized_at", "$/reference/registered_at")


def validate_context_bridge_object(record: Mapping[str, Any], expected_route: str,
                                   registry: SchemaRegistry | None = None) -> ValidationResult:
    """单对象只返回 object_valid；不证明完整链、人工真实性或执行权限。"""
    checks = _Checks(registry)
    if type(expected_route) is not str or expected_route not in _ROUTES:
        checks.add("context_bridge_unsupported_route", "$")
        return checks.finish(None, "object_valid")
    # 单对象 None 是非法对象；链入口中的 None 则表示必要上下文缺失。
    if record is None:
        checks.add("context_bridge_invalid_object", "$")
    else:
        checks.contract(record, expected_route, "$")
    return checks.finish(expected_route, "object_valid")


def validate_registration_validation(candidate: Any, proposal: Any, validation_artifact: Any,
                                     *, evidence_context: Mapping[str, Any] | None = None,
                                     registry: SchemaRegistry | None = None) -> ValidationResult:
    """检查 C/P/V 声明与显式证据。V 精确字节可选；不证明人工授权。"""
    checks = _Checks(registry)
    c = checks.contract(candidate, _ROUTES[0], "$/candidate")
    p = checks.contract(proposal, _ROUTES[1], "$/proposal")
    v = checks.contract(validation_artifact, _ROUTES[2], "$/validation_artifact")
    context, blobs = _context(checks, evidence_context, transition=False)
    _registration(checks, c, p, v, None, None, context, blobs, full=False)
    return checks.finish(_ROUTES[2], "validation_chain_valid")


def validate_registration_chain(candidate: Any, proposal: Any, validation_artifact: Any,
                                authorization: Any, reference: Any, *,
                                evidence_context: Mapping[str, Any] | None = None,
                                registry: SchemaRegistry | None = None) -> ValidationResult:
    """检查登记链与所供 ID 索引；不认证真人、证明全局禁止覆盖或持久化。

    C/P/V 字节和 id_index 必需。最终人工选择可不同于建议，入口只能保序缩小。
    """
    checks = _Checks(registry)
    c = checks.contract(candidate, _ROUTES[0], "$/candidate")
    p = checks.contract(proposal, _ROUTES[1], "$/proposal")
    v = checks.contract(validation_artifact, _ROUTES[2], "$/validation_artifact")
    h = checks.contract(authorization, _ROUTES[3], "$/authorization")
    r = checks.contract(reference, _ROUTES[4], "$/reference")
    context, blobs = _context(checks, evidence_context, transition=False, registration=True)
    _registration(checks, c, p, v, h, r, context, blobs, full=True)
    return checks.finish(_ROUTES[4], "registration_chain_valid")


def validate_reference_transition(previous_reference: Any, new_reference: Any, transition: Any,
                                  *, evidence_context: Mapping[str, Any] | None = None,
                                  registry: SchemaRegistry | None = None) -> ValidationResult:
    """校验单次转换。历史可选，缺失时 PASS 不包含历史重放或现实当前状态证明。

    只接受 status 变化，其余字段连同存在性保持不变；合法图由冻结 Schema 负责。
    """
    checks = _Checks(registry)
    previous = checks.contract(previous_reference, _ROUTES[4], "$/previous_reference")
    new = checks.contract(new_reference, _ROUTES[4], "$/new_reference")
    event = checks.contract(transition, _ROUTES[5], "$/transition")
    context, blobs = _context(checks, evidence_context, transition=True)
    for name, record, fingerprint_field in (
        ("previous_reference", previous, "previous_reference_fingerprint"),
        ("new_reference", new, "new_reference_fingerprint"),
    ):
        if name in blobs:
            fp = checks.exact(blobs[name], record, "$/evidence_context/object_bytes/" + name)
            checks.equal(_field(event, fingerprint_field), fp if fp is not None else _ABSENT,
                         "$/transition/" + fingerprint_field, "context_bridge_fingerprint_mismatch")
    checks.group([(_field(record, "reference_id"), path + "/reference_id") for record, path in (
        (previous, "$/previous_reference"), (new, "$/new_reference"), (event, "$/transition"),
    )], "context_bridge_identity_mismatch")
    checks.equal(_field(previous, "status"), _field(event, "from_status"), "$/transition/from_status", "context_bridge_transition_state_mismatch")
    checks.equal(_field(new, "status"), _field(event, "to_status"), "$/transition/to_status", "context_bridge_transition_state_mismatch")
    if previous is not None and new is not None:
        if not _same({k: v for k, v in previous.items() if k != "status"}, {k: v for k, v in new.items() if k != "status"}):
            checks.add("context_bridge_immutable_binding_changed", "$/new_reference")
    checks.ordered_time(_field(previous, "registered_at"), _field(event, "transitioned_at"), "$/previous_reference/registered_at", "$/transition/transitioned_at")
    if "transition_history" in context:
        path = "$/evidence_context/transition_history"
        history = checks.closed(context["transition_history"], ("transition_ids", "current_reference_bytes", "last_transitioned_at"),
                                ("transition_ids", "current_reference_bytes"), path)
        ids = checks.ids(history.get("transition_ids", _ABSENT), path + "/transition_ids")
        if event is not None and ids is not None and event["transition_id"] in ids:
            checks.add("context_bridge_transition_replay_detected", "$/transition/transition_id")
        # 独立验证所供历史对象，即使 previous 缺失也不掩盖已知格式矛盾。
        current_fp = checks.exact(history.get("current_reference_bytes", _ABSENT), previous,
                                  path + "/current_reference_bytes", route=_ROUTES[4])
        checks.equal(_field(event, "previous_reference_fingerprint"), current_fp if current_fp is not None else _ABSENT,
                     path + "/current_reference_bytes", "context_bridge_fingerprint_mismatch")
        if "last_transitioned_at" in history:
            checks.ordered_time(history["last_transitioned_at"], _field(event, "transitioned_at"), path + "/last_transitioned_at", "$/transition/transitioned_at")
    return checks.finish(_ROUTES[5], "transition_valid")
