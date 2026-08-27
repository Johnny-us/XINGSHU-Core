"""Pure conformance checks for Evidence Scope and Freshness.

The caller supplies already parsed metadata, a use context, an explicit
evaluation time, and trusted results for material free-text constraints.
This module performs no I/O, network access, authorization, or mutation.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any


Record = Mapping[str, Any]
_KNOWN_REVIEW_TRIGGERS = {
    "time_elapsed",
    "subject_changed",
    "version_changed",
    "environment_changed",
    "governance_changed",
    "new_conflicting_evidence",
    "method_invalidated",
    "scope_changed",
    "manual_review_required",
}


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.utcoffset() is None:
        return None
    return parsed


def evaluate_evidence_use(
    evidence: Record,
    use_context: Record,
    evaluation_time: str,
    trusted_constraint_results: Mapping[str, str] | None = None,
) -> list[str]:
    """Return stable blockers for a proposed current-evidence use."""

    blockers: list[str] = []

    def block(code: str) -> None:
        if code not in blockers:
            blockers.append(code)

    scope = evidence.get("validation_scope")
    subject = evidence.get("subject_ref")
    requested_subject = use_context.get("subject_ref")
    if not all(isinstance(value, Mapping) for value in (scope, subject, requested_subject)):
        return ["evidence_comparison_unknown"]

    scoped_subject = scope.get("subject_identity")
    if not isinstance(scoped_subject, Mapping):
        return ["evidence_comparison_unknown"]

    for field, code in (
        ("subject_id", "evidence_subject_mismatch"),
        ("subject_type", "evidence_subject_type_mismatch"),
    ):
        values = (
            subject.get(field),
            scoped_subject.get(field),
            requested_subject.get(field),
        )
        if not all(isinstance(value, str) and value for value in values):
            block("evidence_comparison_unknown")
        elif len(set(values)) != 1:
            block(code)

    versions = (
        subject.get("subject_version"),
        scoped_subject.get("subject_version"),
        requested_subject.get("subject_version"),
    )
    if any(value is not None for value in versions):
        if not all(isinstance(value, str) and value for value in versions):
            block("evidence_comparison_unknown")
        elif len(set(versions)) != 1:
            block("evidence_subject_version_mismatch")

    claim_ref = use_context.get("claim_ref")
    scoped_claims = scope.get("claim_refs")
    evidence_claims = evidence.get("claim_refs")
    if not isinstance(claim_ref, str) or not claim_ref:
        block("evidence_comparison_unknown")
    elif not all(isinstance(value, list) for value in (scoped_claims, evidence_claims)):
        block("evidence_comparison_unknown")
    elif any(
        not isinstance(value, str) or not value
        for collection in (scoped_claims, evidence_claims)
        for value in collection
    ):
        block("evidence_comparison_unknown")
    elif claim_ref not in scoped_claims or claim_ref not in evidence_claims:
        block("evidence_claim_out_of_scope")

    state_domain = use_context.get("state_domain")
    state_domains = scope.get("state_domains")
    if not isinstance(state_domain, str) or not isinstance(state_domains, list):
        block("evidence_comparison_unknown")
    elif any(not isinstance(value, str) or not value for value in state_domains):
        block("evidence_comparison_unknown")
    elif state_domain not in state_domains:
        block("evidence_state_domain_mismatch")

    environment = use_context.get("environment_class")
    scoped_environment = scope.get("environment_class")
    if not all(isinstance(value, str) and value for value in (environment, scoped_environment)):
        block("evidence_comparison_unknown")
    elif environment != scoped_environment:
        block("evidence_environment_mismatch")

    use_time = _parse_timestamp(evaluation_time)
    time_window = scope.get("time_window")
    freshness = evidence.get("freshness")
    if use_time is None or not isinstance(time_window, Mapping) or not isinstance(freshness, Mapping):
        block("evidence_comparison_unknown")
    else:
        window_start = _parse_timestamp(time_window.get("start"))
        window_end_value = time_window.get("end")
        window_end = _parse_timestamp(window_end_value) if window_end_value is not None else None
        if window_start is None or (window_end_value is not None and window_end is None):
            block("evidence_comparison_unknown")
        elif use_time < window_start or (window_end is not None and use_time > window_end):
            block("evidence_time_window_mismatch")

        evaluated_at = _parse_timestamp(freshness.get("evaluated_at"))
        valid_until_value = freshness.get("valid_until")
        review_after_value = freshness.get("review_after")
        valid_until = _parse_timestamp(valid_until_value) if valid_until_value is not None else None
        review_after = _parse_timestamp(review_after_value) if review_after_value is not None else None
        if (
            evaluated_at is None
            or (valid_until_value is not None and valid_until is None)
            or (review_after_value is not None and review_after is None)
        ):
            block("evidence_comparison_unknown")
        else:
            if use_time < evaluated_at:
                block("evidence_comparison_unknown")
            if valid_until is not None and use_time >= valid_until:
                block("evidence_expired")
            if review_after is not None and use_time >= review_after:
                block("evidence_review_due")

    if evidence.get("evidence_state") != "current":
        block("evidence_not_current")

    triggered = use_context.get("triggered_review_types")
    review_triggers = evidence.get("review_triggers")
    if not isinstance(triggered, list) or not isinstance(review_triggers, list):
        block("evidence_comparison_unknown")
    else:
        if any(not isinstance(value, str) or value not in _KNOWN_REVIEW_TRIGGERS for value in triggered):
            block("evidence_comparison_unknown")
        configured = set()
        for item in review_triggers:
            if not isinstance(item, Mapping) or item.get("trigger_type") not in _KNOWN_REVIEW_TRIGGERS:
                block("evidence_comparison_unknown")
                continue
            configured.add(item["trigger_type"])
        if configured.intersection(triggered):
            block("evidence_review_triggered")

    if trusted_constraint_results is None:
        constraint_results: Mapping[str, str] = {}
    elif isinstance(trusted_constraint_results, Mapping):
        constraint_results = trusted_constraint_results
    else:
        block("evidence_comparison_unknown")
        constraint_results = {}
    for field in ("version_constraints", "scope_limitations"):
        constraints = scope.get(field)
        if not isinstance(constraints, list):
            block("evidence_comparison_unknown")
            continue
        if any(not isinstance(value, str) or not value for value in constraints):
            block("evidence_comparison_unknown")
            continue
        if not constraints:
            continue
        result = constraint_results.get(field)
        if result == "fail":
            block("evidence_constraint_failed")
        elif result != "pass":
            block("evidence_constraint_unresolved")

    return blockers
