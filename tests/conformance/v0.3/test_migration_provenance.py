import json
import unittest
from pathlib import Path

from xingshu_core import validate_record


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests/fixtures/v0.3/migration-provenance"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def evaluate(record):
    return validate_record(record).status


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
