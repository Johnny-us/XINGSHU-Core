import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
OLD_FIXTURES = ROOT / "tests/fixtures/v0.2/state-separation"
NEW_FIXTURES = ROOT / "tests/fixtures/v0.2.1/state-separation"
OLD_SCHEMA = json.loads((ROOT / "schemas/v0.2/state-separation.schema.json").read_text())
NEW_SCHEMA = json.loads((ROOT / "schemas/v0.2.1/state-separation.schema.json").read_text())
OLD_VALIDATOR = Draft202012Validator(OLD_SCHEMA)
NEW_VALIDATOR = Draft202012Validator(NEW_SCHEMA)
ORIGINAL_V02_FIXTURE_SET_SHA256 = (
    "2dec455d3bb2cceeba03c77a24ced94949a85c50b39c21680ff5c0dbff26a152"
)


def load(directory, name):
    return json.loads((directory / name).read_text())


def fixture_set_sha256(directory):
    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.json")):
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def select_validator(record, v021_selected):
    version = record.get("schema_version")
    if version == "0.2":
        return OLD_VALIDATOR
    if version == "0.2.1" and v021_selected:
        return NEW_VALIDATOR
    return None


class StateSeparationCompatibilityTests(unittest.TestCase):
    def test_v02_valid_records_continue_to_use_v02_schema(self):
        # Cases 13 and 16: v0.2 stays valid and needs no assessment_ref.
        for name in [
            "source-valid.json",
            "runtime-valid.json",
            "transition-source-runtime-valid.json",
            "transition-runtime-observed-valid.json",
            "transition-observed-decision-valid.json",
        ]:
            with self.subTest(name=name):
                record = load(OLD_FIXTURES, name)
                self.assertEqual([], list(OLD_VALIDATOR.iter_errors(record)))
        transition = load(OLD_FIXTURES, "transition-source-runtime-valid.json")
        self.assertNotIn("assessment_ref", transition)

    def test_v021_execute_is_valid_only_under_v021_schema(self):
        # Cases 14 and 15: version identities are not interchangeable.
        record = load(NEW_FIXTURES, "execute-required-valid.json")
        self.assertEqual([], list(NEW_VALIDATOR.iter_errors(record)))
        self.assertTrue(list(OLD_VALIDATOR.iter_errors(record)))

    def test_v02_record_is_not_reinterpreted_as_v021(self):
        record = load(OLD_FIXTURES, "transition-source-runtime-valid.json")
        self.assertTrue(list(NEW_VALIDATOR.iter_errors(record)))

    def test_withdrawing_v021_preserves_v02_without_downgrade(self):
        # Case 17: unsupported v0.2.1 fails closed; v0.2 remains selectable.
        old_record = load(OLD_FIXTURES, "transition-source-runtime-valid.json")
        new_record = load(NEW_FIXTURES, "execute-required-valid.json")
        self.assertIs(OLD_VALIDATOR, select_validator(old_record, v021_selected=False))
        self.assertIsNone(select_validator(new_record, v021_selected=False))
        self.assertIs(NEW_VALIDATOR, select_validator(new_record, v021_selected=True))

    def test_original_v02_fixtures_are_unchanged(self):
        # Case 18: fixed aggregate protects the original fixture set.
        self.assertEqual(
            ORIGINAL_V02_FIXTURE_SET_SHA256, fixture_set_sha256(OLD_FIXTURES)
        )


if __name__ == "__main__":
    unittest.main()
