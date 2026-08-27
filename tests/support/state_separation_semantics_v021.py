"""Conformance reference semantics for State Separation v0.2.1.

The normative source is the public specification. This helper performs only
pure, provider-neutral checks over parsed objects supplied by tests. It does
not resolve network references, execute actions, or create authorization.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


Record = Mapping[str, Any]


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def state_record_errors(record: Record) -> list[str]:
    """Return intra-object errors without conflating runtime and outcome."""

    errors: list[str] = []
    if record.get("record_type") != "state_record":
        return errors
    if record.get("state_kind") == "runtime":
        if record.get("validation_state") in {"verified", "stably_verified"}:
            # Valid runtime/readback verification is not an outcome claim.
            pass
        if "verification_outcome" in record:
            errors.append("runtime_cannot_claim_outcome_verification")
    return errors


def execute_transition_errors(
    transition: Record,
    assessments: Mapping[str, Record],
    actions: Mapping[str, Record],
) -> list[str]:
    """Validate the G1 assessment/action/authorization chain for execute."""

    errors: list[str] = []
    if transition.get("record_type") != "state_transition":
        return errors
    if transition.get("transition_type") != "execute":
        return errors

    assessment_ref = transition.get("assessment_ref")
    if not isinstance(assessment_ref, str) or not assessment_ref:
        return ["assessment_missing"]

    assessment = assessments.get(assessment_ref)
    if not assessment or assessment.get("record_type") != "assessment_result":
        return ["assessment_unresolved"]

    action_ref = assessment.get("action_ref")
    action = actions.get(action_ref) if isinstance(action_ref, str) else None
    if not action or action.get("record_type") != "action_request":
        errors.append("action_unresolved")
    elif action.get("record_id") != action_ref:
        errors.append("action_reference_mismatch")

    if assessment.get("target_state_ref") != transition.get("to_state_ref"):
        errors.append("assessment_target_mismatch")
    if action:
        observed_state_ref = action.get("target_ref", {}).get("observed_state_ref")
        if observed_state_ref and observed_state_ref != transition.get("from_state_ref"):
            errors.append("action_transition_mismatch")

    occurred_at = _parse_timestamp(transition.get("occurred_at"))
    valid_until = _parse_timestamp(assessment.get("valid_until"))
    if occurred_at is None or valid_until is None:
        errors.append("assessment_time_unknown")
    elif occurred_at > valid_until:
        errors.append("assessment_expired")

    if assessment.get("assessment_outcome") != "ready_for_execution":
        errors.append("assessment_not_ready")

    for name in (
        "risk_evaluation",
        "privacy_evaluation",
        "reversibility_evaluation",
        "evidence_plan_evaluation",
    ):
        if assessment.get(name, {}).get("result") != "pass":
            errors.append(f"{name}_not_passed")
    if assessment.get("stop_condition_state") != "clear":
        errors.append("stop_condition_not_clear")
    if assessment.get("unmet_conditions"):
        errors.append("assessment_has_unmet_conditions")

    for condition in transition.get("condition_results", []):
        if condition.get("condition_id") == "assessment-current" and condition.get("result") != "pass":
            errors.append("assessment_condition_not_satisfied")

    authorization = assessment.get("authorization_evaluation", {})
    status = authorization.get("status")
    transition_refs = transition.get("authorization_refs", [])
    assessment_refs = authorization.get("authorization_refs", [])
    authorization_required = None
    if action:
        authorization_required = action.get("authorization_requirement", {}).get("required")

    if authorization_required is True and status != "valid":
        errors.append("authorization_requirement_mismatch")
    elif authorization_required is False and status != "not_required":
        errors.append("authorization_requirement_mismatch")
    elif authorization_required not in {True, False}:
        errors.append("authorization_requirement_unknown")

    if status == "not_required":
        if authorization.get("scope_match") != "not_applicable":
            errors.append("authorization_scope_unknown")
        if authorization.get("freshness") != "not_applicable":
            errors.append("authorization_freshness_unknown")
        if transition_refs:
            errors.append("authorization_refs_unexpected")
    elif status == "valid":
        if not assessment_refs or not transition_refs:
            errors.append("authorization_missing")
        elif set(transition_refs) != set(assessment_refs):
            errors.append("authorization_reference_mismatch")
        if authorization.get("scope_match") != "match":
            errors.append("authorization_out_of_scope")
        if authorization.get("freshness") != "current":
            errors.append("authorization_stale")
    elif status in {"required", "missing", "stale", "out_of_scope", "unknown"}:
        errors.append(f"authorization_{status}")
    else:
        errors.append("authorization_status_unknown")

    return errors
