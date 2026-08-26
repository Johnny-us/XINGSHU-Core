import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from xingshu_core.schema_registry import (
    SCHEMA_REFS,
    SchemaRegistry,
    SchemaRegistryError,
    repository_root,
    resolve_schema_root,
)


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


if __name__ == "__main__":
    unittest.main()
