import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests/fixtures/v0.2/evidence-proportional-adoption"
QUALITY_FIELDS = ("quality", "relevance", "freshness", "independence", "coverage")


def load(name):
    return json.loads((FIXTURES / name).read_text())


def classify(request):
    gates = [name for name, state in request["non_waivable_gate_states"].items() if state != "not_applicable"]
    evidence = request["evidence_summary"]
    missing = [name for name in QUALITY_FIELDS if evidence[name] in {"weak", "unknown"}]
    route = ["privacy", "risk", "owner_decision"]
    reasons = []
    if request["privacy_boundary_state"] in {"violated", "unknown"}:
        result = "needs_review"
        reasons.append("privacy_boundary_unresolved")
        route.insert(0, "privacy")
    elif request["origin_type"] in {"mixed", "unknown"} or request["intended_scope"] == "unknown":
        result = "needs_review"
        reasons.append("classification_input_uncertain")
    elif request["context_delta"] in {"high", "unknown"}:
        result = "needs_review"
        reasons.append("context_delta_unresolved")
        route.insert(0, "context_delta")
    elif request["intended_scope"] in {"personal_instance", "project_private"}:
        result = "class_3"
        reasons.append("personal_scope_only")
        route.insert(0, "personal_only")
    elif request["origin_type"] == "validated_case_pattern" and not missing and request["context_delta"] == "low":
        result = "class_2"
        reasons.append("validated_pattern_evidence_adequate")
        route[:0] = ["generalization", "schema_api", "compatibility"]
    else:
        result = "class_1"
        reasons.append("evidence_not_ready_for_generalization")
        route[:0] = ["discovery", "case_validation", "generalization"]
    if request["risk_level"] in {"high", "critical", "unknown"}:
        reasons.append("enhanced_risk_review_required")
    return {
        "result_id": "result:" + request["request_id"],
        "request_ref": request["request_id"],
        "recommended_class": result,
        "confidence": "low" if result == "needs_review" else "medium",
        "reason_codes": reasons,
        "required_review_route": list(dict.fromkeys(route)),
        "non_waivable_gates": gates,
        "missing_evidence": missing,
        "reclassification_triggers": ["evidence_expired", "environment_changed", "risk_increased"],
        "authorization_effect": "none",
        "governance_effect": "none",
        "activation_effect": "none",
    }


class EvidenceProportionalAdoptionTests(unittest.TestCase):
    def test_fixed_classification_results(self):
        for path in sorted(FIXTURES.glob("*.json")):
            fixture = json.loads(path.read_text())
            result = classify(fixture["request"])
            self.assertEqual(fixture["expected_class"], result["recommended_class"], path.name)
            self.assertEqual("none", result["authorization_effect"])
            self.assertEqual("none", result["governance_effect"])
            self.assertEqual("none", result["activation_effect"])

    def test_non_waivable_gates_are_preserved(self):
        fixture = load("high-risk-gates-preserved.json")
        result = classify(fixture["request"])
        required = {name for name, state in fixture["request"]["non_waivable_gate_states"].items() if state != "not_applicable"}
        self.assertTrue(required.issubset(set(result["non_waivable_gates"])))
        self.assertIn("enhanced_risk_review_required", result["reason_codes"])

    def test_stale_evidence_does_not_reach_class_2(self):
        result = classify(load("stale-evidence-conservative.json")["request"])
        self.assertNotEqual("class_2", result["recommended_class"])
        self.assertIn("freshness", result["missing_evidence"])


if __name__ == "__main__":
    unittest.main()
