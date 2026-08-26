"""Read-only schema and semantic validation for XINGSHU v0.3 records."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from jsonschema.exceptions import ValidationError

from .decisions import Decision, ValidationIssue, ValidationResult
from .schema_registry import SchemaRegistry, SchemaRegistryError


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
        key=lambda item: (tuple(str(part) for part in item.absolute_path), str(item.validator)),
    )
    issues = []
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


def _forbidden_key_issues(value: Any, path: tuple[Any, ...] = ()) -> list[ValidationIssue]:
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
        record_type=str(record.get("record_type")) if record and record.get("record_type") else None,
        schema_version=str(record.get("schema_version")) if record and record.get("schema_version") else None,
        schema_ref=schema_ref,
        errors=tuple(issues),
    )


def _memory_result(record: Mapping[str, Any], schema_ref: str) -> ValidationResult:
    state = record["conclusion_state"]
    if state == "candidate":
        issue = ValidationIssue(
            "promotion_review_required", "$/conclusion_state", "candidate memory requires review", "conclusion_state"
        )
        return _result(Decision.NEEDS_REVIEW, "needs_review", record, schema_ref, (issue,))
    if state == "active":
        issues = []
        if record["evidence_state"] != "current":
            issues.append(ValidationIssue("evidence_not_current", "$/evidence_state", "supporting evidence is not current", "evidence_state"))
        if not record["current_loading_allowed"]:
            issues.append(ValidationIssue("current_loading_not_allowed", "$/current_loading_allowed", "record is not allowed for current loading", "current_loading_allowed"))
        if record["source_verification"]["status"] != "verified":
            issues.append(ValidationIssue("source_not_verified", "$/source_verification/status", "source verification is incomplete", "status"))
        if record["dedup_conflict_review"]["status"] not in {"clear", "merged"}:
            issues.append(ValidationIssue("dedup_or_conflict_unresolved", "$/dedup_conflict_review/status", "deduplication or conflict review is unresolved", "status"))
        if record["promotion_review"]["status"] != "approved":
            issues.append(ValidationIssue("promotion_not_approved", "$/promotion_review/status", "Promotion Review is not approved", "status"))
        if issues:
            return _result(Decision.NEEDS_REVIEW, "needs_review", record, schema_ref, issues)
        return _result(Decision.PASS, "current_valid", record, schema_ref)
    if state in {"superseded", "deprecated", "historical"}:
        if record["current_loading_allowed"]:
            issue = ValidationIssue(
                "historical_loaded_as_current",
                "$/current_loading_allowed",
                "non-current conclusion cannot be loaded as current",
                "current_loading_allowed",
            )
            return _result(Decision.REJECT, "rejected", record, schema_ref, (issue,))
        return _result(Decision.PASS, "history_only", record, schema_ref)
    issue = ValidationIssue(
        "conclusion_requires_review", "$/conclusion_state", "conclusion is not current", "conclusion_state"
    )
    return _result(Decision.NEEDS_REVIEW, "needs_review", record, schema_ref, (issue,))


def _knowledge_result(record: Mapping[str, Any], schema_ref: str) -> ValidationResult:
    issues: list[ValidationIssue] = []
    reuse = record.get("reuse_claim")
    if reuse:
        if reuse["scope_match"] != "match":
            issues.append(ValidationIssue("reuse_scope_mismatch", "$/reuse_claim/scope_match", "reuse scope does not match", "scope_match"))
        if reuse["origin_platform"] != reuse["target_platform"] and reuse["local_path_reused"]:
            issues.append(ValidationIssue("cross_platform_path_reuse", "$/reuse_claim/local_path_reused", "platform-specific local path cannot be reused", "local_path_reused"))
    if record["document_state"] in {"superseded", "deprecated", "historical"} and record["current_loading_allowed"]:
        issues.append(ValidationIssue("historical_loaded_as_current", "$/current_loading_allowed", "non-current knowledge cannot be loaded as current", "current_loading_allowed"))
    if issues:
        return _result(Decision.REJECT, "rejected", record, schema_ref, issues)
    return _result(Decision.PASS, "accepted", record, schema_ref)


def _migration_result(record: Mapping[str, Any], schema_ref: str) -> ValidationResult:
    issues: list[ValidationIssue] = []
    inventory = [item["source_id"] for item in record["source_inventory"]]
    if len(inventory) != len(set(inventory)):
        issues.append(ValidationIssue("duplicate_source_id", "$/source_inventory", "source inventory IDs must be unique"))
    accounted = {item["source_id"] for item in record["mappings"]}
    accounted.update(item["source_id"] for item in record["omitted_items"])
    if set(inventory) != accounted:
        issues.append(ValidationIssue("source_without_mapping_or_omission", "$/source_inventory", "every source needs a mapping or omission record"))
    if not accounted.issubset(set(inventory)):
        issues.append(ValidationIssue("unknown_source_reference", "$/mappings", "mapping or omission references an unknown source"))
    if record["migration_state"] == "migrated" and record["unresolved_conflicts"]:
        issues.append(ValidationIssue("migrated_with_unresolved_conflict", "$/unresolved_conflicts", "migrated record cannot retain unresolved conflicts"))
    if record["migration_state"] == "migrated" and not record["source_unchanged"]:
        if not record.get("source_change_basis_refs"):
            issues.append(ValidationIssue("source_change_basis_missing", "$/source_change_basis_refs", "source-changing migration needs an external basis reference"))
    if issues:
        return _result(Decision.REJECT, "rejected", record, schema_ref, issues)
    if record["migration_state"] in {"needs_review", "unknown"}:
        issue = ValidationIssue("migration_requires_review", "$/migration_state", "migration state requires review", "migration_state")
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
    """Validate one parsed JSON record without changing it or accessing the network."""

    if not isinstance(record, Mapping):
        issue = ValidationIssue("record_not_object", "$", "top-level JSON value must be an object")
        return _result(Decision.REJECT, "rejected", None, None, (issue,))
    record_type = record_type_override or record.get("record_type")
    if record_type not in SEMANTIC_VALIDATORS:
        issue = ValidationIssue("unknown_record_type", "$/record_type", "record_type is missing or unsupported", "record_type")
        return _result(Decision.REJECT, "rejected", record, None, (issue,))
    try:
        active_registry = registry or SchemaRegistry()
        schema_ref = active_registry.schema_ref_for(str(record_type))
        validator = active_registry.validator_for(str(record_type))
    except SchemaRegistryError:
        issue = ValidationIssue("schema_registry_error", "$", "canonical schema registry is unavailable")
        return _result(Decision.ERROR, "tool_error", record, None, (issue,))
    privacy_issues = _forbidden_key_issues(record)
    if privacy_issues:
        return _result(Decision.REJECT, "rejected", record, schema_ref, privacy_issues)
    schema_issues = _schema_issues(validator.iter_errors(record))
    if schema_issues:
        return _result(Decision.REJECT, "rejected", record, schema_ref, schema_issues)
    return SEMANTIC_VALIDATORS[str(record_type)](record, schema_ref)


def validate_file(
    file_path: str | Path,
    record_type_override: str | None = None,
    registry: SchemaRegistry | None = None,
) -> ValidationResult:
    """Read and validate one JSON file without modifying it."""

    path = Path(file_path)
    if not path.is_file():
        issue = ValidationIssue("input_file_missing", str(path), "input file does not exist")
        return _result(Decision.ERROR, "input_error", None, None, (issue,))
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issue = ValidationIssue(
            "invalid_json",
            str(path),
            f"JSON parsing failed at line {exc.lineno} column {exc.colno}",
        )
        return _result(Decision.ERROR, "input_error", None, None, (issue,))
    except OSError:
        issue = ValidationIssue("input_read_error", str(path), "input file could not be read")
        return _result(Decision.ERROR, "input_error", None, None, (issue,))
    return validate_record(record, record_type_override, registry)
