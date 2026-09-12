import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xingshu_core.schema_registry import (
    CONTEXT_BRIDGE_SCHEMA_REFS,
    SCHEMA_REFS,
    SchemaRegistry,
    SchemaRegistryError,
    repository_root,
    resolve_schema_root,
)


LEGACY_REFS = {
    "memory_entry": "schemas/v0.3/memory-entry.schema.json",
    "knowledge_object": "schemas/v0.3/knowledge-object.schema.json",
    "migration_provenance": "schemas/v0.3/migration-provenance.schema.json",
}
CANDIDATE_REFS = {
    "context_candidate": "schemas/candidate/context-bridge/context-candidate.schema.json",
    "context_registration_proposal": "schemas/candidate/context-bridge/context-registration-proposal.schema.json",
    "context_validation_artifact": "schemas/candidate/context-bridge/context-validation-artifact.schema.json",
    "human_authorization_evidence": "schemas/candidate/context-bridge/human-authorization-evidence.schema.json",
    "registered_context_reference": "schemas/candidate/context-bridge/registered-context-reference.schema.json",
    "context_reference_transition": "schemas/candidate/context-bridge/context-reference-transition.schema.json",
    "source_adapter_manifest": "schemas/candidate/context-bridge/source-adapter-contract.schema.json",
    "source_adapter_request": "schemas/candidate/context-bridge/source-adapter-contract.schema.json",
    "source_adapter_result": "schemas/candidate/context-bridge/source-adapter-contract.schema.json",
    "source_adapter_error": "schemas/candidate/context-bridge/source-adapter-contract.schema.json",
    "trusted_client_profile": "schemas/candidate/context-bridge/trusted-client-profile.schema.json",
    "runtime_binding": "schemas/candidate/context-bridge/runtime-binding.schema.json",
    "resolve_context_request": "schemas/candidate/context-bridge/resolve-context.schema.json",
    "resolve_context_result": "schemas/candidate/context-bridge/resolve-context.schema.json",
    "resolve_context_error": "schemas/candidate/context-bridge/resolve-context.schema.json",
    "derived_provider_metadata": "schemas/candidate/context-bridge/derived-provider-metadata.schema.json",
}


class SchemaRegistryTests(unittest.TestCase):
    def test_default_registry_discovers_all_v03_schemas(self):
        registry = SchemaRegistry()
        self.assertEqual(SCHEMA_REFS, registry.discover())
        self.assertEqual(repository_root() / "schemas", registry.schema_root)

    def test_schema_refs_remain_canonical_repository_paths(self):
        registry = SchemaRegistry()
        for record_type, expected_ref in SCHEMA_REFS.items():
            self.assertEqual(expected_ref, registry.schema_ref_for(record_type))
            self.assertTrue(registry.schema_path_for(record_type).is_file())

    def test_environment_override_accepts_schema_or_repository_root(self):
        schema_root = repository_root() / "schemas"
        with patch.dict(os.environ, {"XINGSHU_SCHEMA_ROOT": str(schema_root)}):
            self.assertEqual(schema_root, resolve_schema_root())
        with patch.dict(os.environ, {"XINGSHU_SCHEMA_ROOT": str(repository_root())}):
            self.assertEqual(schema_root, resolve_schema_root())

    def test_invalid_schema_root_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SchemaRegistryError):
                SchemaRegistry(Path(directory))

    def test_unknown_record_type_fails_closed(self):
        with self.assertRaises(SchemaRegistryError):
            SchemaRegistry().schema_ref_for("unknown_record")

    def test_missing_schema_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "v0.3").mkdir()
            with patch.dict(os.environ, {"XINGSHU_SCHEMA_ROOT": str(root)}):
                registry = SchemaRegistry()
                with self.assertRaises(SchemaRegistryError):
                    registry.schema_path_for("memory_entry")

    def test_schema_reference_escape_fails_closed(self):
        with patch.dict(SCHEMA_REFS, {"escape": "schemas/../outside.json"}):
            with self.assertRaises(SchemaRegistryError):
                SchemaRegistry().schema_path_for("escape")


class ContextBridgeRegistryIntegrationTests(unittest.TestCase):
    def test_candidate_discovery_does_not_expand_legacy_refs(self):
        registry = SchemaRegistry()
        self.assertEqual(LEGACY_REFS, SCHEMA_REFS)
        self.assertEqual(LEGACY_REFS, registry.discover())
        self.assertEqual(CANDIDATE_REFS, registry.discover_context_bridge())
        self.assertEqual(LEGACY_REFS, registry.discover())
        self.assertEqual(tuple(LEGACY_REFS), registry.supported_record_types)
        self.assertTrue(set(LEGACY_REFS).isdisjoint(CANDIDATE_REFS))

    def test_sixteen_internal_routes_resolve_to_eleven_real_schemas(self):
        registry = SchemaRegistry()
        self.assertEqual(CANDIDATE_REFS, CONTEXT_BRIDGE_SCHEMA_REFS)
        self.assertEqual(16, len(CANDIDATE_REFS))
        self.assertEqual(11, len(set(CANDIDATE_REFS.values())))
        self.assertEqual(tuple(CANDIDATE_REFS), registry.supported_context_bridge_record_types)
        for route, ref in CANDIDATE_REFS.items():
            with self.subTest(route=route):
                self.assertEqual(ref, registry.schema_ref_for(route))
                self.assertEqual(repository_root() / ref, registry.schema_path_for(route))
                self.assertTrue(registry.schema_path_for(route).is_file())
                schema = registry.load_schema(route)
                strict = registry.validator_for(route)
                self.assertEqual(schema, strict.schema)
                self.assertIsNotNone(strict.format_checker)
                self.assertTrue(list(strict.iter_errors({})))
        self.assertEqual(11, len({registry.schema_path_for(route) for route in CANDIDATE_REFS}))

    def test_internal_resolve_error_loads_without_public_discovery(self):
        registry = SchemaRegistry()
        self.assertEqual("schemas/candidate/context-bridge/resolve-context.schema.json", registry.schema_ref_for("resolve_context_error"))
        self.assertEqual(registry.load_schema("resolve_context_result"), registry.load_schema("resolve_context_error"))
        self.assertIsNotNone(registry.validator_for("resolve_context_error"))
        self.assertNotIn("resolve_context_error", registry.discover())
        # Registry 的内部知晓不声明 CLI 或通用验证器公开支持。

    def test_unknown_candidate_route_fails_closed_at_each_registry_entry(self):
        registry = SchemaRegistry()
        for method in (registry.schema_ref_for, registry.schema_path_for, registry.load_schema, registry.validator_for):
            with self.subTest(method=method.__name__), self.assertRaises(SchemaRegistryError):
                method("synthetic_unknown_route")

    def test_same_registry_supports_repeated_legacy_and_candidate_use(self):
        registry = SchemaRegistry()
        for _ in range(2):
            self.assertEqual(CANDIDATE_REFS, registry.discover_context_bridge())
            self.assertEqual(LEGACY_REFS, registry.discover())
            for route, ref in {**LEGACY_REFS, **CANDIDATE_REFS}.items():
                with self.subTest(route=route):
                    self.assertEqual(ref, registry.schema_ref_for(route))
                    self.assertEqual(registry.load_schema(route), registry.validator_for(route).schema)


if __name__ == "__main__":
    unittest.main()
