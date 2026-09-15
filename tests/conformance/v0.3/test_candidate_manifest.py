import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
MANIFEST = yaml.safe_load((ROOT / "CORE_MANIFEST.yaml").read_text())
V02_CAPABILITY_VERSIONS = {
    "state_separation": "0.2.1",
    "evidence_lifecycle": "0.2",
    "evidence_proportional_adoption": "0.2",
    "pre_execution_assessment": "0.2",
}
V03_CAPABILITIES = {
    "knowledge_memory_lifecycle",
    "knowledge_object_model",
    "migration_provenance",
}
V04_CAPABILITY = "runnable_validation_cli"

CONTEXT_BRIDGE_SCHEMA_REFS = (
    "schemas/candidate/context-bridge/context-candidate.schema.json",
    "schemas/candidate/context-bridge/context-registration-proposal.schema.json",
    "schemas/candidate/context-bridge/context-validation-artifact.schema.json",
    "schemas/candidate/context-bridge/human-authorization-evidence.schema.json",
    "schemas/candidate/context-bridge/registered-context-reference.schema.json",
    "schemas/candidate/context-bridge/context-reference-transition.schema.json",
    "schemas/candidate/context-bridge/source-adapter-contract.schema.json",
    "schemas/candidate/context-bridge/trusted-client-profile.schema.json",
    "schemas/candidate/context-bridge/runtime-binding.schema.json",
    "schemas/candidate/context-bridge/resolve-context.schema.json",
    "schemas/candidate/context-bridge/derived-provider-metadata.schema.json",
)
CONTEXT_BRIDGE_TEST_REFS = (
    "tests/conformance/context-bridge/test_contract_schemas.py",
    "tests/runtime/test_context_bridge_validation.py",
    "tests/runtime/test_source_adapter_validation.py",
    "tests/runtime/test_authority_validation.py",
    "tests/runtime/test_resolve_context_validation.py",
    "tests/runtime/test_schema_registry.py",
    "tests/runtime/test_validator.py",
    "tests/runtime/test_cli.py",
    "tests/compatibility/context-bridge/test_non_interference.py",
    "tests/conformance/v0.3/test_candidate_manifest.py",
    "tests/compatibility/v0.2-v0.3/test_non_interference.py",
)


class CandidateManifestTests(unittest.TestCase):
    def test_v02_capabilities_are_preserved(self):
        self.assertTrue(V02_CAPABILITY_VERSIONS.keys() <= MANIFEST["capabilities"].keys())
        for name, expected_version in V02_CAPABILITY_VERSIONS.items():
            self.assertEqual(
                expected_version, MANIFEST["capabilities"][name]["version"]
            )

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

    def test_v04_runnable_validation_is_an_additive_disabled_candidate(self):
        item = MANIFEST["capabilities"][V04_CAPABILITY]
        self.assertEqual("0.4", item["version"])
        self.assertEqual("candidate", item["status"])
        self.assertFalse(item["enabled_by_default"])
        self.assertEqual("additive_optional", item["backward_compatibility"])
        self.assertEqual("none", item["governance_effect"])
        self.assertEqual("none", item["authorization_effect"])
        self.assertEqual("none", item["activation_effect"])
        self.assertTrue((ROOT / item["spec_ref"]).is_file())
        for ref in item["schema_refs"] + item["test_refs"]:
            self.assertTrue((ROOT / ref).is_file(), ref)


class ContextBridgeCandidateManifestTests(unittest.TestCase):
    def test_manifest_identity_and_inactive_baseline_are_preserved(self):
        self.assertEqual({
            "manifest_version": "0.2",
            "system_id": "xingshu-core",
            "release_stage": "candidate",
            "governance_effect": "none",
            "activation_state": "not_active",
            "baseline": {
                "tag": "v0.1.0-candidate",
                "commit": "5a110478cb731ad02769949ac72b60c1a4a76557",
                "tree": "a22196d91ebcd343150ee4e5bd79765e4fa022e2",
            },
            "schema_dialect": "https://json-schema.org/draft/2020-12/schema",
            "unknown_capability_behavior": "ignore_if_disabled_fail_closed_if_requested",
        }, {key: value for key, value in MANIFEST.items() if key != "capabilities"})

    def test_context_bridge_has_exact_optional_validation_metadata(self):
        item = MANIFEST["capabilities"]["context_bridge_validation"]
        self.assertEqual({
            "version": "0.1",
            "status": "candidate",
            "enabled_by_default": False,
            "spec_ref": "docs/CLI.md",
            "dependencies": {"runnable_validation_cli": ">=0.4"},
            "backward_compatibility": "additive_optional",
            "governance_effect": "none",
            "authorization_effect": "none",
            "activation_effect": "none",
            "rollback_behavior": "disable_capability_and_stop_invoking_context_bridge_validation",
        }, {key: value for key, value in item.items() if key not in {"schema_refs", "test_refs"}})
        self.assertIs(False, item["enabled_by_default"])
        self.assertTrue((ROOT / item["spec_ref"]).is_file())
        # 回退仅停止选择和调用该可选验证能力，不删除数据或改变运行时状态。

    def test_context_bridge_has_exact_eleven_unique_existing_schemas(self):
        refs = MANIFEST["capabilities"]["context_bridge_validation"]["schema_refs"]
        self.assertEqual(list(CONTEXT_BRIDGE_SCHEMA_REFS), refs)
        self.assertEqual(11, len(refs))
        self.assertEqual(11, len(set(refs)))
        for ref in refs:
            with self.subTest(ref=ref):
                self.assertTrue((ROOT / ref).is_file())

    def test_context_bridge_references_only_eleven_executable_tests(self):
        refs = MANIFEST["capabilities"]["context_bridge_validation"]["test_refs"]
        self.assertEqual(list(CONTEXT_BRIDGE_TEST_REFS), refs)
        self.assertEqual(11, len(refs))
        self.assertEqual(11, len(set(refs)))
        for ref in refs:
            with self.subTest(ref=ref):
                path = Path(ref)
                self.assertTrue((ROOT / path).is_file())
                self.assertEqual("tests", path.parts[0])
                self.assertTrue(path.name.startswith("test_"))
                self.assertEqual(".py", path.suffix)
                self.assertTrue({"fixtures", "support", "docs", "src"}.isdisjoint(path.parts))


class LocalRuntimeCandidateMetadataTests(unittest.TestCase):
    """P4F：只验证候选元数据，不改变冻结的 Runtime 执行测试。"""

    def test_runtime_is_a_separate_disabled_non_effect_capability(self):
        item = MANIFEST["capabilities"]["local_read_only_context_runtime"]
        self.assertEqual("0.1", item["version"])
        self.assertEqual("candidate", item["status"])
        self.assertIs(False, item["enabled_by_default"])
        self.assertEqual("not_active", MANIFEST["activation_state"])
        for effect in ("governance_effect", "authorization_effect", "activation_effect"):
            self.assertEqual("none", item[effect])
        self.assertEqual("additive_optional", item["backward_compatibility"])
        self.assertEqual({"context_bridge_validation": ">=0.1"}, item["dependencies"])
        self.assertEqual("docs/LOCAL_READ_ONLY_CONTEXT_RUNTIME.md", item["spec_ref"])
        self.assertTrue(set(item["schema_refs"]) <= set(CONTEXT_BRIDGE_SCHEMA_REFS))
        self.assertEqual(len(item["schema_refs"]), len(set(item["schema_refs"])))
        for ref in [item["spec_ref"], *item["schema_refs"], *item["test_refs"]]:
            self.assertTrue((ROOT / ref).is_file(), ref)
        # ContextBridgeCandidateManifestTests 继续独立固定既有验证能力的完整语义。
        self.assertIsNot(item, MANIFEST["capabilities"]["context_bridge_validation"])

    def test_runtime_docs_match_candidate_state_and_separate_entry(self):
        runtime_doc = (ROOT / "docs/LOCAL_READ_ONLY_CONTEXT_RUNTIME.md").read_text()
        metadata = yaml.safe_load(runtime_doc.split("---", 2)[1])
        self.assertEqual("candidate", metadata["status"])
        self.assertEqual("0.1", metadata["version"])
        self.assertIs(False, metadata["enabled_by_default"])
        self.assertEqual("not_active", metadata["activation_state"])
        for effect in ("governance_effect", "authorization_effect", "activation_effect"):
            self.assertEqual("none", metadata[effect])
        cli_doc = (ROOT / "docs/CLI.md").read_text()
        for doc in (runtime_doc, cli_doc):
            self.assertIn("python -m xingshu_core.runtime_cli resolve-local", doc)
            self.assertIn("xingshu doctor", doc)
            self.assertIn("xingshu validate", doc)
            self.assertIn("/absolute/path/to/synthetic-vault", doc)
        test_doc = (ROOT / "tests/README.md").read_text()
        for ref in MANIFEST["capabilities"]["local_read_only_context_runtime"]["test_refs"]:
            self.assertIn(str(Path(ref).relative_to("tests")), test_doc)

    def test_runtime_documentation_does_not_assert_release_or_isolation(self):
        claims = re.compile(r"active runtime|production ready|stable runtime|production security|fully secure|"
                            r"Obsidian integrated|automatic AI memory|cross-app memory already working", re.I)
        for name in ("docs/LOCAL_READ_ONLY_CONTEXT_RUNTIME.md", "docs/CLI.md"):
            for line in (ROOT / name).read_text().splitlines():
                if claims.search(line):
                    self.assertRegex(line.lower(), r"不|未|无|\bnot\b|\bno\b", name)


class ObsidianBridgeCandidateMetadataTests(unittest.TestCase):
    SCHEMAS = [
        "schemas/candidate/context-bridge/registered-context-reference.schema.json",
        "schemas/candidate/context-bridge/trusted-client-profile.schema.json",
        "schemas/candidate/context-bridge/runtime-binding.schema.json",
        "schemas/candidate/context-bridge/source-adapter-contract.schema.json",
        "schemas/candidate/context-bridge/resolve-context.schema.json",
    ]
    TESTS = [
        "tests/runtime/test_obsidian_bridge.py",
        "tests/runtime/test_obsidian_bridge_localfs_integration.py",
        "tests/runtime/test_runtime_host.py",
        "tests/conformance/v0.3/test_candidate_manifest.py",
        "tests/compatibility/v0.2-v0.3/test_non_interference.py",
    ]

    def test_obsidian_has_exact_separate_candidate_metadata_and_existing_refs(self):
        item = MANIFEST["capabilities"]["obsidian_context_bridge"]
        self.assertEqual({
            "version": "0.1", "status": "candidate", "enabled_by_default": False,
            "spec_ref": "docs/OBSIDIAN_CONTEXT_BRIDGE.md",
            "schema_refs": self.SCHEMAS, "test_refs": self.TESTS,
            "dependencies": {"local_read_only_context_runtime": ">=0.1"},
            "backward_compatibility": "additive_optional",
            "governance_effect": "none", "authorization_effect": "none", "activation_effect": "none",
            "rollback_behavior": "disable_capability_and_stop_invoking_obsidian_bridge",
        }, item)
        self.assertIs(False, item["enabled_by_default"])
        self.assertEqual("candidate", MANIFEST["release_stage"])
        self.assertEqual("not_active", MANIFEST["activation_state"])
        for ref in [item["spec_ref"], *self.SCHEMAS, *self.TESTS]:
            self.assertTrue((ROOT / ref).is_file(), ref)
        self.assertTrue(set(self.SCHEMAS) <= set(CONTEXT_BRIDGE_SCHEMA_REFS))
        for ref in self.TESTS:
            self.assertTrue(Path(ref).name.startswith("test_"))
            self.assertTrue({"support", "fixtures"}.isdisjoint(Path(ref).parts))

    def test_p4_runtime_metadata_remains_exact_and_independent(self):
        self.assertEqual({
            "version": "0.1", "status": "candidate", "enabled_by_default": False,
            "spec_ref": "docs/LOCAL_READ_ONLY_CONTEXT_RUNTIME.md",
            "schema_refs": self.SCHEMAS,
            "test_refs": [
                "tests/conformance/context-runtime/test_runtime_contract.py",
                "tests/runtime/test_local_filesystem_adapter.py",
                "tests/runtime/test_filesystem_security.py",
                "tests/runtime/test_context_runtime.py",
                "tests/runtime/test_context_runtime_localfs_integration.py",
                "tests/runtime/test_runtime_host.py", "tests/runtime/test_runtime_cli.py",
                "tests/conformance/v0.3/test_candidate_manifest.py",
                "tests/compatibility/v0.2-v0.3/test_non_interference.py",
            ],
            "dependencies": {"context_bridge_validation": ">=0.1"},
            "backward_compatibility": "additive_optional",
            "governance_effect": "none", "authorization_effect": "none", "activation_effect": "none",
            "rollback_behavior": "disable_capability_and_stop_invoking_local_runtime_host",
        }, MANIFEST["capabilities"]["local_read_only_context_runtime"])

    def test_obsidian_docs_report_candidate_implementation_without_activation(self):
        doc = (ROOT / "docs/OBSIDIAN_CONTEXT_BRIDGE.md").read_text()
        metadata = yaml.safe_load(doc.split("---", 2)[1])
        self.assertEqual("candidate", metadata["status"])
        self.assertEqual("candidate_implemented", metadata["implementation_state"])
        self.assertEqual("synthetic_vault_real_io", metadata["validation_scope"])
        self.assertIs(False, metadata["enabled_by_default"])
        self.assertEqual("not_active", metadata["activation_state"])
        for field in ("governance_effect", "authorization_effect", "activation_effect"):
            self.assertEqual("none", metadata[field])
        self.assertIn("resolve_obsidian()", doc)
        self.assertIn("python -m xingshu_core.runtime_cli resolve-local", doc)
        self.assertIn("Personal Instance Adoption", doc)
        registry = (ROOT / "tests/README.md").read_text()
        for ref in self.TESTS:
            self.assertIn(str(Path(ref).relative_to("tests")), registry)


if __name__ == "__main__":
    unittest.main()
