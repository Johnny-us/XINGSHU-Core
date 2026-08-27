import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/support"))
from strict_schema_validation import strict_validator  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/v0.3/migration-provenance"
SCHEMA = json.loads((ROOT / "schemas/v0.3/migration-provenance.schema.json").read_text())
VALIDATOR = strict_validator(SCHEMA)
FORBIDDEN_KEYS = {
    "payload", "raw_payload", "content", "body", "secret", "credential", "token",
    "cookie", "local_path", "absolute_path", "email", "account_id", "device_id",
    "personal_identity", "chat_text",
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
    inventory = [item["source_id"] for item in record["source_inventory"]]
    if len(inventory) != len(set(inventory)):
        errors.append("duplicate_source_id")
    accounted = {item["source_id"] for item in record["mappings"]}
    accounted.update(item["source_id"] for item in record["omitted_items"])
    if set(inventory) != accounted:
        errors.append("source_without_mapping_or_omission")
    if not accounted.issubset(set(inventory)):
        errors.append("unknown_source_reference")
    if record["migration_state"] == "migrated" and record["unresolved_conflicts"]:
        errors.append("migrated_with_unresolved_conflict")
    if record["migration_state"] == "migrated" and not record["source_unchanged"]:
        if not record.get("source_change_basis_refs"):
            errors.append("source_change_basis_missing")
    return errors


def evaluate(record):
    if list(VALIDATOR.iter_errors(record)) or semantic_errors(record):
        return "rejected"
    if record["migration_state"] in {"needs_review", "unknown"}:
        return "needs_review"
    return "accepted"


class MigrationProvenanceTests(unittest.TestCase):
    def test_migration_complete_is_not_runtime_verified(self):
        record = load("migrated-but-runtime-unverified-valid.json")
        self.assertEqual("accepted", evaluate(record))
        self.assertEqual("migrated", record["migration_state"])
        self.assertEqual("pending_verification", record["runtime_validation_state"])
        self.assertNotEqual("verified", record["runtime_validation_state"])

    def test_unaccounted_source_is_rejected(self):
        self.assertEqual("rejected", evaluate(load("migration-drops-source-without-provenance-invalid.json")))

    def test_source_change_without_external_basis_is_rejected(self):
        self.assertEqual("rejected", evaluate(load("migrated-source-change-without-basis-invalid.json")))

    def test_source_change_with_external_basis_is_valid_without_authorization_effect(self):
        record = load("migrated-source-change-with-basis-valid.json")
        self.assertEqual("accepted", evaluate(record))
        self.assertFalse(record["source_unchanged"])
        self.assertTrue(record["source_change_basis_refs"])
        self.assertEqual("none", record["authorization_effect"])

    def test_unknown_migration_state_fails_closed(self):
        record = load("migrated-but-runtime-unverified-valid.json")
        record["migration_state"] = "mostly_done"
        self.assertEqual("rejected", evaluate(record))


if __name__ == "__main__":
    unittest.main()
