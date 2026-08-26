import json
import os
import unittest
from pathlib import Path

import yaml


TEST_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = TEST_ROOT / "tests/fixtures/v0.2/compatibility"
REPO_UNDER_TEST = Path(os.environ.get("XINGSHU_REPO_UNDER_TEST", TEST_ROOT)).resolve()


def manifest_behavior(path, requested_capability=None):
    if not path.is_file():
        return {"mode": "v0.1", "new_behavior": False}
    manifest = yaml.safe_load(path.read_text())
    if manifest.get("manifest_version") != "0.2":
        return {"mode": "blocked", "error_code": "unsupported_version", "new_behavior": False}
    capabilities = manifest.get("capabilities", {})
    if requested_capability and requested_capability not in capabilities:
        return {"mode": "blocked", "error_code": "unknown_enum", "new_behavior": False}
    if requested_capability and not capabilities[requested_capability].get("enabled_by_default", False):
        return {"mode": "disabled", "new_behavior": False}
    if any(item.get("enabled_by_default") is True for item in capabilities.values()):
        return {"mode": "blocked", "error_code": "unsafe_default", "new_behavior": False}
    return {"mode": "v0.2-candidate-disabled", "new_behavior": False}


class CompatibilityTests(unittest.TestCase):
    def test_repository_under_test_uses_safe_discovery(self):
        result = manifest_behavior(REPO_UNDER_TEST / "CORE_MANIFEST.yaml")
        self.assertFalse(result["new_behavior"])
        if not (REPO_UNDER_TEST / "CORE_MANIFEST.yaml").exists():
            self.assertEqual("v0.1", result["mode"])

    def test_manifest_absent_and_capabilities_disabled(self):
        absent = manifest_behavior(FIXTURES / "v0.1-manifest-absent/CORE_MANIFEST.yaml")
        self.assertEqual({"mode": "v0.1", "new_behavior": False}, absent)
        disabled = manifest_behavior(FIXTURES / "v0.2-capabilities-disabled/CORE_MANIFEST.yaml")
        self.assertEqual("v0.2-candidate-disabled", disabled["mode"])
        self.assertFalse(disabled["new_behavior"])

    def test_unknown_capability_handling_fails_closed_when_requested(self):
        ignored = manifest_behavior(FIXTURES / "v0.2-unknown-disabled-capability/CORE_MANIFEST.yaml")
        self.assertEqual("v0.2-candidate-disabled", ignored["mode"])
        requested = manifest_behavior(FIXTURES / "v0.2-unknown-requested-capability/CORE_MANIFEST.yaml", "unrecognized_required_capability")
        self.assertEqual("blocked", requested["mode"])
        self.assertEqual("unknown_enum", requested["error_code"])

    def test_unsupported_manifest_version_fails_closed(self):
        result = manifest_behavior(FIXTURES / "v0.2-unsupported-manifest-version/CORE_MANIFEST.yaml")
        self.assertEqual("blocked", result["mode"])
        self.assertEqual("unsupported_version", result["error_code"])

    def test_old_and_new_consumer_expectations(self):
        old_to_new = json.loads((FIXTURES / "v0.1-consumer-v0.2-repository.json").read_text())
        new_to_old = json.loads((FIXTURES / "v0.2-consumer-v0.1-repository.json").read_text())
        self.assertEqual("ignore_optional_v0_2_files", old_to_new["expected_behavior"])
        self.assertEqual("fallback_to_v0_1", new_to_old["expected_behavior"])
        self.assertFalse(old_to_new["automatic_activation"])
        self.assertFalse(new_to_old["automatic_activation"])

    def test_personal_sentinel_is_unchanged(self):
        before = json.loads((FIXTURES / "personal-sentinel-before.json").read_text())
        after = json.loads((FIXTURES / "personal-sentinel-after.json").read_text())
        self.assertEqual(before, after)
        self.assertEqual("synthetic_only", before["guard_mode"])
        self.assertFalse(before["automatic_sync"])


if __name__ == "__main__":
    unittest.main()
