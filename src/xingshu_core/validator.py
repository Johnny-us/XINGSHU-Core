"""Read-only validation for legacy records and explicit candidate objects."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from jsonschema.exceptions import ValidationError

from .decisions import Decision, ValidationIssue, ValidationResult
from .schema_registry import SchemaRegistry, SchemaRegistryError
from .context_bridge_validation import validate_context_bridge_object
from .source_adapter_validation import validate_source_adapter_object
from .authority_validation import validate_authority_object
from .resolve_context_validation import validate_resolve_context_object


# 公开范围固定，不从 Registry（结构注册表）的发现结果推导。
_CANDIDATE_VALIDATORS = {
    "context_candidate": validate_context_bridge_object,
    "context_registration_proposal": validate_context_bridge_object,
    "context_validation_artifact": validate_context_bridge_object,
    "human_authorization_evidence": validate_context_bridge_object,
    "registered_context_reference": validate_context_bridge_object,
    "context_reference_transition": validate_context_bridge_object,
    "source_adapter_manifest": validate_source_adapter_object,
    "source_adapter_request": validate_source_adapter_object,
    "source_adapter_result": validate_source_adapter_object,
    "source_adapter_error": validate_source_adapter_object,
    "trusted_client_profile": validate_authority_object,
    "runtime_binding": validate_authority_object,
    "resolve_context_request": validate_resolve_context_object,
    "resolve_context_result": validate_resolve_context_object,
    "derived_provider_metadata": None,
}

_PUBLIC_ROUTES = (
    "memory_entry", "knowledge_object", "migration_provenance",
    *_CANDIDATE_VALIDATORS,
)

_INTEGRATION_DIAGNOSTICS = {
    "candidate_discriminator_conflict": (
        Decision.REJECT, "$", "top-level discriminator representation is ambiguous",
    ),
    "candidate_unsupported_route": (
        Decision.REJECT, "$/object_kind", "object kind is not supported by public validation",
    ),
    "candidate_route_mismatch": (
        Decision.REJECT, "$/object_kind", "object kind does not match the requested route",
    ),
    "candidate_schema_invalid": (
        Decision.REJECT, "$", "object violates the frozen candidate schema",
    ),
    "candidate_validation_unavailable": (
        Decision.ERROR, "$", "candidate validation is unavailable",
    ),
    "validation_resource_limit_exceeded": (
        Decision.ERROR, "$", "validation could not complete within available processing resources",
    ),
}


def _integration_result(code: str) -> ValidationResult:
    decision, path, message = _INTEGRATION_DIAGNOSTICS[code]
    return ValidationResult(
        decision, "rejected" if decision is Decision.REJECT else "validation_unavailable",
        None, None, None, (ValidationIssue(code, path, message),),
    )


def _candidate_result(
    record: Mapping[str, Any], route: str, registry: SchemaRegistry | None,
) -> ValidationResult:
    active_registry = registry if registry is not None else SchemaRegistry()
    validate_object = _CANDIDATE_VALIDATORS[route]
    if validate_object is not None:
        # 单次分流；直接保留专用单对象结果，不重复验证或尝试其他路线。
        return validate_object(record, route, registry=active_registry)

    # 派生元数据只检查冻结 Schema（结构合同），不增加来源或权限判断。
    invalid = next(active_registry.validator_for(route).iter_errors(record), None) is not None
    return ValidationResult(
        Decision.REJECT if invalid else Decision.PASS,
        "rejected" if invalid else "object_valid",
        "derived_provider_metadata",
        "context-bridge-candidate",
        "schemas/candidate/context-bridge/derived-provider-metadata.schema.json",
        _integration_result("candidate_schema_invalid").errors if invalid else (),
    )


FORBIDDEN_KEYS = {
    "payload",
    "raw_payload",
    "content",
    "body",
    "secret",
    "credential",
    "token",
    "cookie",
    "local_path",
    "absolute_path",
    "email",
    "account_id",
    "device_id",
    "personal_identity",
    "chat_text",
}


def _pointer(parts: Iterable[Any]) -> str:
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "$" if not escaped else "$/" + "/".join(escaped)


def _safe_schema_message(error: ValidationError) -> str:
    messages = {
        "required": "required field is missing",
        "additionalProperties": "unexpected field is not allowed",
        "enum": "value is not an allowed enum",
        "const": "value does not match the required constant",
        "type": "value has an invalid type",
        "minItems": "array has too few items",
        "maxItems": "array has too many items",
        "uniqueItems": "array items must be unique",
        "minLength": "string is too short",
        "maxLength": "string is too long",
        "pattern": "string does not match the required pattern",
        "format": "value does not match the required format",
    }
    return messages.get(str(error.validator), "value violates a schema constraint")


def _schema_issues(errors: Iterable[ValidationError]) -> tuple[ValidationIssue, ...]:
    ordered = sorted(
        errors,
        key=lambda item: (
            tuple(str(part) for part in item.absolute_path),
            str(item.validator),
        ),
    )
    issues: list[ValidationIssue] = []
    for error in ordered:
        parts = list(error.absolute_path)
        field = str(parts[-1]) if parts else None
        if error.validator == "required" and isinstance(error.instance, Mapping):
            missing = [name for name in error.validator_value if name not in error.instance]
            if missing:
                field = str(missing[0])
                parts.append(field)
        issues.append(
            ValidationIssue(
                code=f"schema_{error.validator or 'invalid'}",
                path=_pointer(parts),
                field=field,
                message=_safe_schema_message(error),
            )
        )
    return tuple(issues)


def _forbidden_key_issues(
    value: Any, path: tuple[Any, ...] = ()
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = path + (key,)
            if key in FORBIDDEN_KEYS:
                issues.append(
                    ValidationIssue(
                        code="privacy_boundary_violation",
                        path=_pointer(child_path),
                        field=str(key),
                        message="forbidden payload or private-data field is present",
                    )
                )
            issues.extend(_forbidden_key_issues(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(_forbidden_key_issues(child, path + (index,)))
    return issues


def _result(
    decision: Decision,
    status: str,
    record: Mapping[str, Any] | None,
    schema_ref: str | None,
    issues: Iterable[ValidationIssue] = (),
) -> ValidationResult:
    return ValidationResult(
        decision=decision,
        status=status,
        record_type=(
            str(record.get("record_type"))
            if record and record.get("record_type")
            else None
        ),
        schema_version=(
            str(record.get("schema_version"))
            if record and record.get("schema_version")
            else None
        ),
        schema_ref=schema_ref,
        errors=tuple(issues),
    )


def _memory_result(
    record: Mapping[str, Any], schema_ref: str
) -> ValidationResult:
    state = record["conclusion_state"]
    if state == "candidate":
        issue = ValidationIssue(
            code="promotion_review_required",
            path="$/conclusion_state",
            field="conclusion_state",
            message="candidate memory requires review",
        )
        return _result(Decision.NEEDS_REVIEW, "needs_review", record, schema_ref, (issue,))
    if state == "active":
        issues: list[ValidationIssue] = []
        if record["evidence_state"] != "current":
            issues.append(
                ValidationIssue(
                    code="evidence_not_current",
                    path="$/evidence_state",
                    field="evidence_state",
                    message="supporting evidence is not current",
                )
            )
        if not record["current_loading_allowed"]:
            issues.append(
                ValidationIssue(
                    code="current_loading_not_allowed",
                    path="$/current_loading_allowed",
                    field="current_loading_allowed",
                    message="record is not allowed for current loading",
                )
            )
        if record["source_verification"]["status"] != "verified":
            issues.append(
                ValidationIssue(
                    code="source_not_verified",
                    path="$/source_verification/status",
                    field="status",
                    message="source verification is incomplete",
                )
            )
        if record["dedup_conflict_review"]["status"] not in {"clear", "merged"}:
            issues.append(
                ValidationIssue(
                    code="dedup_or_conflict_unresolved",
                    path="$/dedup_conflict_review/status",
                    field="status",
                    message="deduplication or conflict review is unresolved",
                )
            )
        if record["promotion_review"]["status"] != "approved":
            issues.append(
                ValidationIssue(
                    code="promotion_not_approved",
                    path="$/promotion_review/status",
                    field="status",
                    message="Promotion Review is not approved",
                )
            )
        if issues:
            return _result(
                Decision.NEEDS_REVIEW,
                "needs_review",
                record,
                schema_ref,
                issues,
            )
        return _result(Decision.PASS, "current_valid", record, schema_ref)
    if state in {"superseded", "deprecated", "historical"}:
        if record["current_loading_allowed"]:
            issue = ValidationIssue(
                code="historical_loaded_as_current",
                path="$/current_loading_allowed",
                field="current_loading_allowed",
                message="non-current conclusion cannot be loaded as current",
            )
            return _result(Decision.REJECT, "rejected", record, schema_ref, (issue,))
        return _result(Decision.PASS, "history_only", record, schema_ref)
    issue = ValidationIssue(
        code="conclusion_requires_review",
        path="$/conclusion_state",
        field="conclusion_state",
        message="conclusion is not current",
    )
    return _result(Decision.NEEDS_REVIEW, "needs_review", record, schema_ref, (issue,))


def _knowledge_result(
    record: Mapping[str, Any], schema_ref: str
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    reuse = record.get("reuse_claim")
    if reuse:
        if reuse["scope_match"] != "match":
            issues.append(
                ValidationIssue(
                    code="reuse_scope_mismatch",
                    path="$/reuse_claim/scope_match",
                    field="scope_match",
                    message="reuse scope does not match",
                )
            )
        if reuse["origin_platform"] != reuse["target_platform"] and reuse["local_path_reused"]:
            issues.append(
                ValidationIssue(
                    code="cross_platform_path_reuse",
                    path="$/reuse_claim/local_path_reused",
                    field="local_path_reused",
                    message="platform-specific local path cannot be reused",
                )
            )
    if (
        record["document_state"] in {"superseded", "deprecated", "historical"}
        and record["current_loading_allowed"]
    ):
        issues.append(
            ValidationIssue(
                code="historical_loaded_as_current",
                path="$/current_loading_allowed",
                field="current_loading_allowed",
                message="non-current knowledge cannot be loaded as current",
            )
        )
    if issues:
        return _result(Decision.REJECT, "rejected", record, schema_ref, issues)
    return _result(Decision.PASS, "accepted", record, schema_ref)


def _migration_result(
    record: Mapping[str, Any], schema_ref: str
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    inventory = [item["source_id"] for item in record["source_inventory"]]
    if len(inventory) != len(set(inventory)):
        issues.append(
            ValidationIssue(
                code="duplicate_source_id",
                path="$/source_inventory",
                field="source_inventory",
                message="source inventory IDs must be unique",
            )
        )
    accounted = {item["source_id"] for item in record["mappings"]}
    accounted.update(item["source_id"] for item in record["omitted_items"])
    if set(inventory) != accounted:
        issues.append(
            ValidationIssue(
                code="source_without_mapping_or_omission",
                path="$/source_inventory",
                field="source_inventory",
                message="every source needs a mapping or omission record",
            )
        )
    if not accounted.issubset(set(inventory)):
        issues.append(
            ValidationIssue(
                code="unknown_source_reference",
                path="$/mappings",
                field="mappings",
                message="mapping or omission references an unknown source",
            )
        )
    if record["migration_state"] == "migrated" and record["unresolved_conflicts"]:
        issues.append(
            ValidationIssue(
                code="migrated_with_unresolved_conflict",
                path="$/unresolved_conflicts",
                field="unresolved_conflicts",
                message="migrated record cannot retain unresolved conflicts",
            )
        )
    if record["migration_state"] == "migrated" and not record["source_unchanged"]:
        if not record.get("source_change_basis_refs"):
            issues.append(
                ValidationIssue(
                    code="source_change_basis_missing",
                    path="$/source_change_basis_refs",
                    field="source_change_basis_refs",
                    message="source-changing migration needs an external basis reference",
                )
            )
    if issues:
        return _result(Decision.REJECT, "rejected", record, schema_ref, issues)
    if record["migration_state"] in {"needs_review", "unknown"}:
        issue = ValidationIssue(
            code="migration_requires_review",
            path="$/migration_state",
            field="migration_state",
            message="migration state requires review",
        )
        return _result(Decision.NEEDS_REVIEW, "needs_review", record, schema_ref, (issue,))
    return _result(Decision.PASS, "accepted", record, schema_ref)


SEMANTIC_VALIDATORS = {
    "memory_entry": _memory_result,
    "knowledge_object": _knowledge_result,
    "migration_provenance": _migration_result,
}


def validate_record(
    record: Any,
    record_type_override: str | None = None,
    registry: SchemaRegistry | None = None,
) -> ValidationResult:
    """Validate a parsed record; raw duplicate keys cannot be recovered here."""

    if not isinstance(record, Mapping):
        issue = ValidationIssue(
            code="record_not_object",
            path="$",
            message="top-level JSON value must be an object",
        )
        return _result(Decision.REJECT, "rejected", None, None, (issue,))
    try:
        has_kind = "object_kind" in record
        has_type = "record_type" in record
        if has_kind and has_type:
            return _integration_result("candidate_discriminator_conflict")
        if has_kind:
            route = record["object_kind"]
            if type(route) is not str or route not in _CANDIDATE_VALIDATORS:
                return _integration_result("candidate_unsupported_route")
            if record_type_override is not None and (
                type(record_type_override) is not str or record_type_override != route
            ):
                return _integration_result("candidate_route_mismatch")
            return _candidate_result(record, route, registry)
        if type(record_type_override) is str and record_type_override in _CANDIDATE_VALIDATORS:
            return _integration_result("candidate_route_mismatch")
    except (MemoryError, RecursionError):
        return _integration_result("validation_resource_limit_exceeded")
    except Exception:
        return _integration_result("candidate_validation_unavailable")

    record_type = record_type_override or record.get("record_type")
    if record_type not in SEMANTIC_VALIDATORS:
        issue = ValidationIssue(
            code="unknown_record_type",
            path="$/record_type",
            field="record_type",
            message="record_type is missing or unsupported",
        )
        return _result(Decision.REJECT, "rejected", record, None, (issue,))
    try:
        active_registry = registry if registry is not None else SchemaRegistry()
        schema_ref = active_registry.schema_ref_for(str(record_type))
        validator = active_registry.validator_for(str(record_type))
    except SchemaRegistryError:
        issue = ValidationIssue(
            code="schema_registry_error",
            path="$",
            message="canonical schema registry is unavailable",
        )
        return _result(Decision.ERROR, "tool_error", record, None, (issue,))

    privacy_issues = _forbidden_key_issues(record)
    if privacy_issues:
        return _result(Decision.REJECT, "rejected", record, schema_ref, privacy_issues)
    schema_issues = _schema_issues(validator.iter_errors(record))
    if schema_issues:
        return _result(Decision.REJECT, "rejected", record, schema_ref, schema_issues)
    return SEMANTIC_VALIDATORS[str(record_type)](record, schema_ref)


class _JSONObject:
    """私有解析节点；重复计数与用户键空间隔离，值仍为后值覆盖。"""

    __slots__ = ("value", "object_kind_count", "record_type_count")

    def __init__(self, pairs: list[tuple[str, Any]]) -> None:
        self.value: dict[str, Any] = {}
        self.object_kind_count = 0
        self.record_type_count = 0
        for key, value in pairs:
            self.value[key] = value
            self.object_kind_count += key == "object_kind"
            self.record_type_count += key == "record_type"


def _ordinary_json(root: Any) -> Any:
    """使用显式栈还原普通 dict/list，不把私有节点传入验证器。"""
    holder = [root]
    stack: list[Any] = [holder]
    while stack:
        container = stack.pop()
        for key in range(len(container)) if isinstance(container, list) else container:
            child = container[key]
            if isinstance(child, _JSONObject):
                child = child.value
                container[key] = child
                stack.append(child)
            elif isinstance(child, list):
                stack.append(child)
    return holder[0]


def validate_file(
    file_path: str | Path,
    record_type_override: str | None = None,
    registry: SchemaRegistry | None = None,
) -> ValidationResult:
    """Read and validate one JSON file without modifying it."""

    try:
        path = Path(file_path)
        if not path.is_file():
            issue = ValidationIssue(
                code="input_file_missing",
                path="$",
                message="input file does not exist",
            )
            return _result(Decision.ERROR, "input_error", None, None, (issue,))
        record = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_JSONObject)
    except (MemoryError, RecursionError):
        return _integration_result("validation_resource_limit_exceeded")
    except json.JSONDecodeError as exc:
        issue = ValidationIssue(
            code="invalid_json",
            path="$",
            message=f"JSON parsing failed at line {exc.lineno} column {exc.colno}",
        )
        return _result(Decision.ERROR, "input_error", None, None, (issue,))
    except (OSError, UnicodeError):
        issue = ValidationIssue(
            code="input_read_error",
            path="$",
            message="input file could not be read",
        )
        return _result(Decision.ERROR, "input_error", None, None, (issue,))
    except ValueError:
        issue = ValidationIssue("invalid_json", "$", "JSON parsing failed")
        return _result(Decision.ERROR, "input_error", None, None, (issue,))
    except Exception:
        return _integration_result("candidate_validation_unavailable")

    try:
        if isinstance(record, _JSONObject) and (
            record.object_kind_count >= 2
            or (record.object_kind_count and record.record_type_count)
        ):
            return _integration_result("candidate_discriminator_conflict")
        record = _ordinary_json(record)
    except (MemoryError, RecursionError):
        return _integration_result("validation_resource_limit_exceeded")
    except Exception:
        return _integration_result("candidate_validation_unavailable")
    return validate_record(record, record_type_override, registry)
