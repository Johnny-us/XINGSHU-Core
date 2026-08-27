import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests/support"))
from strict_schema_validation import strict_validator  # noqa: E402

MANIFEST = yaml.safe_load((ROOT / "CORE_MANIFEST.yaml").read_text())
V03_CAPABILITIES = {
    "knowledge_memory_lifecycle",
    "knowledge_object_model",
    "migration_provenance",
}
V04_CAPABILITY = "runnable_validation_cli"
DISABLED_UNSUPPORTED_CAPABILITIES = V03_CAPABILITIES | {V04_CAPABILITY}
SUPPORTED_CAPABILITY_VERSIONS = {
    "state_separation": "0.2.1",
    "evidence_lifecycle": "0.2",
    "evidence_proportional_adoption": "0.2",
    "pre_execution_assessment": "0.2",
}


def load(path):
    return json.loads(path.read_text())


def object_sha256(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def fixture_set_sha256(*directories):
    digest = hashlib.sha256()
    paths = []
    for directory in directories:
        paths.extend(directory.glob("*.json"))
    for path in sorted(paths, key=lambda item: str(item.relative_to(ROOT))):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class MinimalLimitedConsumer:
    """Test-only routing harness for v0.2/v0.2.1 capabilities."""

    def __init__(self):
        self.parser_calls = []

    def evaluate_manifest(self, manifest, requested_capability=None):
        if manifest.get("manifest_version") != "0.2":
            return {"mode": "blocked", "error_code": "unsupported_manifest_version"}
        if (
            manifest.get("unknown_capability_behavior")
            != "ignore_if_disabled_fail_closed_if_requested"
        ):
            return {"mode": "blocked", "error_code": "unknown_behavior_unresolved"}

        capabilities = manifest.get("capabilities")
        if not isinstance(capabilities, dict):
            return {"mode": "blocked", "error_code": "capabilities_unresolved"}
        if any(item.get("enabled_by_default") is not False for item in capabilities.values()):
            return {"mode": "blocked", "error_code": "unsafe_default"}

        for name, expected_version in SUPPORTED_CAPABILITY_VERSIONS.items():
            item = capabilities.get(name)
            if not isinstance(item, dict) or item.get("version") != expected_version:
                return {"mode": "blocked", "error_code": "supported_version_mismatch"}

        if requested_capability is not None:
            if requested_capability not in SUPPORTED_CAPABILITY_VERSIONS:
                return {"mode": "blocked", "error_code": "unsupported_capability"}
            return {
                "mode": "supported_capability_selected",
                "selected_capability": requested_capability,
                "automatic_activation": False,
                "automatic_adoption": False,
                "automatic_migration": False,
            }

        ignored = {
            name
            for name, item in capabilities.items()
            if name not in SUPPORTED_CAPABILITY_VERSIONS
            and item.get("enabled_by_default") is False
        }
        return {
            "mode": "continue_v0.2_v0.2.1",
            "ignored_capabilities": ignored,
            "automatic_activation": False,
            "automatic_adoption": False,
            "automatic_migration": False,
        }

    def route_record(self, record, capability, selected=False):
        identity = {
            "schema_version": record.get("schema_version"),
            "record_type": record.get("record_type"),
            "record_id": record.get("record_id"),
            "sha256": object_sha256(record),
        }
        if capability not in SUPPORTED_CAPABILITY_VERSIONS or not selected:
            return {"status": "not_routed", "identity": identity}
        self.parser_calls.append(capability)
        return {"status": "routed_to_supported_parser", "identity": identity}


class V03NonInterferenceTests(unittest.TestCase):
    def test_v03_manifest_capabilities_remain_disabled_additive_candidates(self):
        self.assertEqual("0.2", MANIFEST["manifest_version"])
        self.assertEqual(
            "ignore_if_disabled_fail_closed_if_requested",
            MANIFEST["unknown_capability_behavior"],
        )
        for name in V03_CAPABILITIES:
            with self.subTest(capability=name):
                item = MANIFEST["capabilities"][name]
                self.assertEqual("0.3", item["version"])
                self.assertEqual("candidate", item["status"])
                self.assertFalse(item["enabled_by_default"])
                self.assertEqual("additive_optional", item["backward_compatibility"])
                self.assertEqual("none", item["governance_effect"])
                self.assertEqual("none", item["authorization_effect"])
                self.assertEqual("none", item["activation_effect"])

    def test_v04_manifest_capability_remains_disabled_additive_candidate(self):
        item = MANIFEST["capabilities"][V04_CAPABILITY]
        self.assertEqual("0.4", item["version"])
        self.assertEqual("candidate", item["status"])
        self.assertFalse(item["enabled_by_default"])
        self.assertEqual("additive_optional", item["backward_compatibility"])
        self.assertEqual("none", item["governance_effect"])
        self.assertEqual("none", item["authorization_effect"])
        self.assertEqual("none", item["activation_effect"])

    def test_limited_consumer_ignores_unrequested_disabled_v03(self):
        consumer = MinimalLimitedConsumer()
        result = consumer.evaluate_manifest(MANIFEST)
        self.assertEqual("continue_v0.2_v0.2.1", result["mode"])
        self.assertEqual(DISABLED_UNSUPPORTED_CAPABILITIES, result["ignored_capabilities"])
        self.assertFalse(result["automatic_activation"])
        self.assertFalse(result["automatic_adoption"])
        self.assertFalse(result["automatic_migration"])

    def test_requested_unsupported_v03_capability_fails_closed(self):
        consumer = MinimalLimitedConsumer()
        for capability in V03_CAPABILITIES:
            with self.subTest(capability=capability):
                result = consumer.evaluate_manifest(
                    MANIFEST, requested_capability=capability
                )
                self.assertEqual("blocked", result["mode"])
                self.assertEqual("unsupported_capability", result["error_code"])

    def test_requested_unsupported_v04_capability_fails_closed(self):
        result = MinimalLimitedConsumer().evaluate_manifest(
            MANIFEST, requested_capability=V04_CAPABILITY
        )
        self.assertEqual("blocked", result["mode"])
        self.assertEqual("unsupported_capability", result["error_code"])

    def test_disabled_v03_records_are_not_routed_or_rewritten(self):
        cases = (
            (
                "knowledge_memory_lifecycle",
                ROOT / "tests/fixtures/v0.3/memory-entry/active-current-valid.json",
            ),
            (
                "knowledge_object_model",
                ROOT / "tests/fixtures/v0.3/knowledge-object/main-valid.json",
            ),
            (
                "migration_provenance",
                ROOT
                / "tests/fixtures/v0.3/migration-provenance/migrated-but-runtime-unverified-valid.json",
            ),
        )
        consumer = MinimalLimitedConsumer()
        for capability, path in cases:
            with self.subTest(capability=capability):
                record = load(path)
                before = copy.deepcopy(record)
                result = consumer.route_record(record, capability, selected=False)
                self.assertEqual("not_routed", result["status"])
                self.assertEqual("0.3", result["identity"]["schema_version"])
                self.assertEqual(object_sha256(before), result["identity"]["sha256"])
                self.assertEqual(before, record)
        self.assertEqual([], consumer.parser_calls)

    def test_disabling_v03_preserves_v02_and_v021_behavior_and_fixtures(self):
        old_directory = ROOT / "tests/fixtures/v0.2/state-separation"
        revised_directory = ROOT / "tests/fixtures/v0.2.1/state-separation"
        before_hash = fixture_set_sha256(old_directory, revised_directory)

        old_schema = load(ROOT / "schemas/v0.2/state-separation.schema.json")
        revised_schema = load(ROOT / "schemas/v0.2.1/state-separation.schema.json")
        old_record = load(old_directory / "source-valid.json")
        revised_record = load(revised_directory / "execute-required-valid.json")
        before_results = (
            list(strict_validator(old_schema).iter_errors(old_record)),
            list(strict_validator(revised_schema).iter_errors(revised_record)),
        )

        result = MinimalLimitedConsumer().evaluate_manifest(MANIFEST)
        after_results = (
            list(strict_validator(old_schema).iter_errors(old_record)),
            list(strict_validator(revised_schema).iter_errors(revised_record)),
        )
        after_hash = fixture_set_sha256(old_directory, revised_directory)

        self.assertEqual("continue_v0.2_v0.2.1", result["mode"])
        self.assertEqual(([], []), before_results)
        self.assertEqual(before_results, after_results)
        self.assertEqual(before_hash, after_hash)

    def test_rollback_is_non_routing_not_reverse_migration(self):
        record = load(ROOT / "tests/fixtures/v0.3/knowledge-object/main-valid.json")
        before = copy.deepcopy(record)
        consumer = MinimalLimitedConsumer()
        result = consumer.route_record(
            record, "knowledge_object_model", selected=False
        )

        self.assertEqual("not_routed", result["status"])
        self.assertEqual("0.3", record["schema_version"])
        self.assertEqual(before, record)
        self.assertNotIn("transformed_record", result)
        self.assertEqual([], consumer.parser_calls)


if __name__ == "__main__":
    unittest.main()
