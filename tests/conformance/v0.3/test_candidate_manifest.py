import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = yaml.safe_load((ROOT / "CORE_MANIFEST.yaml").read_text())
V02_CAPABILITIES = {
    "state_separation",
    "evidence_lifecycle",
    "evidence_proportional_adoption",
    "pre_execution_assessment",
}
V03_CAPABILITIES = {
    "knowledge_memory_lifecycle",
    "knowledge_object_model",
    "migration_provenance",
}
V04_CAPABILITY = "runnable_validation_cli"


class CandidateManifestTests(unittest.TestCase):
    def test_v02_capabilities_are_preserved(self):
        self.assertTrue(V02_CAPABILITIES.issubset(MANIFEST["capabilities"]))
        for name in V02_CAPABILITIES:
            self.assertEqual("0.2", MANIFEST["capabilities"][name]["version"])

    def test_v03_capabilities_are_additive_disabled_candidates(self):
        self.assertEqual("0.2", MANIFEST["manifest_version"])
        for name in V03_CAPABILITIES:
            item = MANIFEST["capabilities"][name]
            self.assertEqual("0.3", item["version"])
            self.assertEqual("candidate", item["status"])
            self.assertFalse(item["enabled_by_default"])
            self.assertEqual("none", item["governance_effect"])
            self.assertEqual("none", item["authorization_effect"])
            self.assertEqual("none", item["activation_effect"])
            self.assertTrue((ROOT / item["spec_ref"]).is_file())
            for ref in item["schema_refs"] + item["test_refs"]:
                self.assertTrue((ROOT / ref).is_file(), ref)

    def test_no_capability_is_enabled_by_default(self):
        self.assertFalse(any(item["enabled_by_default"] for item in MANIFEST["capabilities"].values()))

    def test_v04_runnable_cli_is_a_disabled_non_effect_candidate(self):
        item = MANIFEST["capabilities"][V04_CAPABILITY]
        self.assertEqual("0.4", item["version"])
        self.assertEqual("candidate", item["status"])
        self.assertFalse(item["enabled_by_default"])
        self.assertEqual("none", item["governance_effect"])
        self.assertEqual("none", item["authorization_effect"])
        self.assertEqual("none", item["activation_effect"])
        self.assertTrue((ROOT / item["spec_ref"]).is_file())
        for ref in item["schema_refs"] + item["test_refs"]:
            self.assertTrue((ROOT / ref).is_file(), ref)


if __name__ == "__main__":
    unittest.main()
