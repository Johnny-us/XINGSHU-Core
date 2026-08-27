import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_FIXTURES = ROOT / "tests/fixtures/v0.2/evidence-lifecycle"
V021_FIXTURES = ROOT / "tests/fixtures/v0.2.1/state-separation"
V03_FIXTURES = ROOT / "tests/fixtures/v0.3/memory-entry"

sys.path.insert(0, str(ROOT / "tests/support"))
from evidence_scope_freshness import evaluate_evidence_use  # noqa: E402
from strict_schema_validation import (  # noqa: E402
    assert_datetime_checker_available,
    strict_validator,
)


def load(path):
    return json.loads(path.read_text())


def current_evidence():
    return load(EVIDENCE_FIXTURES / "current-valid.json")


def matching_use_context():
    return {
        "subject_ref": {
            "subject_id": "subject-alpha",
            "subject_type": "synthetic-service",
            "subject_version": "1.0",
        },
        "claim_ref": "claim:available",
        "state_domain": "execution",
        "environment_class": "isolated_test",
        "triggered_review_types": [],
    }


def trusted_constraints():
    return {"version_constraints": "pass"}


class StrictDateTimeValidationTests(unittest.TestCase):
    def test_date_time_checker_is_available_and_effective(self):
        checker = assert_datetime_checker_available()
        self.assertTrue(checker.conforms("2026-01-01T00:00:00Z", "date-time"))
        self.assertFalse(checker.conforms("not-a-date", "date-time"))

    def test_valid_z_and_offset_rfc3339_values_pass(self):
        schema = load(ROOT / "schemas/v0.2/evidence-lifecycle.schema.json")
        validator = strict_validator(schema)
        record = current_evidence()
        self.assertEqual([], list(validator.iter_errors(record)))
        record["created_at"] = "2026-01-01T08:00:00+08:00"
        self.assertEqual([], list(validator.iter_errors(record)))

    def test_invalid_date_times_fail_across_candidate_versions(self):
        cases = [
            (
                ROOT / "schemas/v0.2/evidence-lifecycle.schema.json",
                EVIDENCE_FIXTURES / "current-valid.json",
            ),
            (
                ROOT / "schemas/v0.2.1/state-separation.schema.json",
                V021_FIXTURES / "runtime-verified-valid.json",
            ),
            (
                ROOT / "schemas/v0.3/memory-entry.schema.json",
                V03_FIXTURES / "active-current-valid.json",
            ),
        ]
        invalid_values = (
            "not-a-date",
            "2026-02-30T00:00:00Z",
            "2026-01-01T00:00:00",
        )
        for schema_path, fixture_path in cases:
            validator = strict_validator(load(schema_path))
            for value in invalid_values:
                with self.subTest(schema=schema_path.parent.name, value=value):
                    record = load(fixture_path)
                    record["created_at"] = value
                    self.assertTrue(list(validator.iter_errors(record)))


class EvidenceScopeFreshnessTests(unittest.TestCase):
    def evaluate(
        self,
        evidence=None,
        context=None,
        evaluation_time="2026-01-01T12:00:00Z",
        constraints=None,
    ):
        return evaluate_evidence_use(
            evidence or current_evidence(),
            context or matching_use_context(),
            evaluation_time,
            trusted_constraints() if constraints is None else constraints,
        )

    def test_fully_matching_current_evidence_passes(self):
        self.assertEqual([], self.evaluate())

    def test_subject_identity_mismatches_fail_closed(self):
        mutations = (
            ("subject_id", "subject-other", "evidence_subject_mismatch"),
            ("subject_type", "other-type", "evidence_subject_type_mismatch"),
            ("subject_version", "2.0", "evidence_subject_version_mismatch"),
        )
        for field, value, expected in mutations:
            with self.subTest(field=field):
                context = matching_use_context()
                context["subject_ref"][field] = value
                self.assertIn(expected, self.evaluate(context=context))

    def test_claim_domain_and_environment_mismatches_fail_closed(self):
        mutations = (
            ("claim_ref", "claim:other", "evidence_claim_out_of_scope"),
            ("state_domain", "configuration", "evidence_state_domain_mismatch"),
            ("environment_class", "remote_service", "evidence_environment_mismatch"),
        )
        for field, value, expected in mutations:
            with self.subTest(field=field):
                context = matching_use_context()
                context[field] = value
                self.assertIn(expected, self.evaluate(context=context))

    def test_time_window_mismatches_fail_closed(self):
        for evaluation_time in (
            "2025-12-31T23:59:59Z",
            "2026-01-02T00:00:01Z",
        ):
            with self.subTest(evaluation_time=evaluation_time):
                self.assertIn(
                    "evidence_time_window_mismatch",
                    self.evaluate(evaluation_time=evaluation_time),
                )

    def test_non_current_evidence_states_fail_closed(self):
        for state in ("stale", "historical", "invalid", "unknown"):
            with self.subTest(state=state):
                evidence = current_evidence()
                evidence["evidence_state"] = state
                self.assertIn("evidence_not_current", self.evaluate(evidence=evidence))

    def test_expired_and_review_due_evidence_fail_closed(self):
        evidence = current_evidence()
        evidence["freshness"]["valid_until"] = "2026-01-01T06:00:00Z"
        self.assertIn("evidence_expired", self.evaluate(evidence=evidence))

        evidence = current_evidence()
        evidence["freshness"]["review_after"] = "2026-01-01T06:00:00Z"
        self.assertIn("evidence_review_due", self.evaluate(evidence=evidence))

    def test_triggered_review_condition_fails_closed(self):
        context = matching_use_context()
        context["triggered_review_types"] = ["time_elapsed"]
        self.assertIn("evidence_review_triggered", self.evaluate(context=context))

    def test_free_text_constraints_require_trusted_results(self):
        self.assertIn("evidence_constraint_unresolved", self.evaluate(constraints={}))

        evidence = current_evidence()
        evidence["validation_scope"]["scope_limitations"] = ["synthetic-only"]
        self.assertIn(
            "evidence_constraint_unresolved",
            self.evaluate(
                evidence=evidence,
                constraints={"version_constraints": "pass"},
            ),
        )

        self.assertIn(
            "evidence_constraint_failed",
            self.evaluate(constraints={"version_constraints": "fail"}),
        )

    def test_unknown_critical_comparison_fails_closed(self):
        context = matching_use_context()
        del context["state_domain"]
        self.assertIn("evidence_comparison_unknown", self.evaluate(context=context))

        self.assertIn(
            "evidence_comparison_unknown",
            self.evaluate(evaluation_time="not-a-date"),
        )

        self.assertIn(
            "evidence_comparison_unknown",
            self.evaluate(constraints="pass"),
        )


if __name__ == "__main__":
    unittest.main()
