import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/support"))
from strict_schema_validation import strict_validator  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/v0.3/knowledge-object"
SCHEMA = json.loads((ROOT / "schemas/v0.3/knowledge-object.schema.json").read_text())
VALIDATOR = strict_validator(SCHEMA)
FORBIDDEN_KEYS = {
    "payload", "raw_payload", "secret", "credential", "token", "cookie", "local_path",
    "absolute_path", "email", "account_id", "device_id", "personal_identity", "chat_text",
}


def load(name):
    return json.loads((FIXTURES / name).read_text())


def all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_keys(child)


def semantic_errors(record):
    errors = []
    if FORBIDDEN_KEYS.intersection(all_keys(record)):
        errors.append("privacy_boundary_violation")
    reuse = record.get("reuse_claim")
    if reuse:
        if reuse["scope_match"] != "match":
            errors.append("reuse_scope_mismatch")
        if reuse["origin_platform"] != reuse["target_platform"] and reuse["local_path_reused"]:
            errors.append("cross_platform_path_reuse")
    if record["document_state"] in {"superseded", "deprecated", "historical"} and record["current_loading_allowed"]:
        errors.append("historical_loaded_as_current")
    return errors


def evaluate(record):
    if list(VALIDATOR.iter_errors(record)) or semantic_errors(record):
        return "rejected"
    return "accepted"


class KnowledgeObjectTests(unittest.TestCase):
    def test_valid_main_object(self):
        record = load("main-valid.json")
        self.assertEqual("accepted", evaluate(record))
        self.assertEqual("active", record["document_state"])
        self.assertEqual("pending_verification", record["runtime_validation_state"])

    def test_derived_view_cannot_overwrite_source(self):
        self.assertEqual("rejected", evaluate(load("derived-view-overwrites-source-invalid.json")))

    def test_derived_view_cannot_be_source_of_truth(self):
        record = load("main-valid.json")
        record["origin_form"] = "derived_view"
        record["relationships"]["derived_from"] = ["knowledge:synthetic-source"]
        self.assertEqual("rejected", evaluate(record))

    def test_appendix_cannot_be_second_source_of_truth(self):
        self.assertEqual("rejected", evaluate(load("appendix-becomes-second-source-of-truth-invalid.json")))

    def test_cross_platform_path_reuse_is_rejected(self):
        self.assertEqual("rejected", evaluate(load("cross-platform-path-reuse-invalid.json")))

    def test_unknown_role_fails_closed(self):
        record = load("main-valid.json")
        record["document_role"] = "alternate_main"
        self.assertEqual("rejected", evaluate(record))


if __name__ == "__main__":
    unittest.main()
