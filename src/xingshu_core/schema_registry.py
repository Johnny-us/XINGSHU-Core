"""Discovery and loading of the canonical repository schemas."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


SCHEMA_REFS = {
    "memory_entry": "schemas/v0.3/memory-entry.schema.json",
    "knowledge_object": "schemas/v0.3/knowledge-object.schema.json",
    "migration_provenance": "schemas/v0.3/migration-provenance.schema.json",
}


class SchemaRegistryError(RuntimeError):
    """Raised when the canonical schema registry cannot be used."""


def repository_root() -> Path:
    """Return the checkout root for the supported editable-install mode."""

    return Path(__file__).resolve().parents[2]


def resolve_schema_root(explicit: str | Path | None = None) -> Path:
    """Resolve the one canonical schema directory without copying schemas."""

    configured = explicit or os.environ.get("XINGSHU_SCHEMA_ROOT")
    candidate = Path(configured).expanduser() if configured else repository_root() / "schemas"
    candidate = candidate.resolve()
    if (candidate / "v0.3").is_dir():
        return candidate
    if (candidate / "schemas" / "v0.3").is_dir():
        return candidate / "schemas"
    raise SchemaRegistryError("canonical schema root is unavailable")


class SchemaRegistry:
    """Load validators for supported record types from ``schemas/v0.3``."""

    def __init__(self, schema_root: str | Path | None = None) -> None:
        self.schema_root = resolve_schema_root(schema_root)
        self._schemas: dict[str, dict[str, Any]] = {}
        self._validators: dict[str, Draft202012Validator] = {}

    @property
    def supported_record_types(self) -> tuple[str, ...]:
        return tuple(SCHEMA_REFS)

    def schema_ref_for(self, record_type: str) -> str:
        try:
            return SCHEMA_REFS[record_type]
        except KeyError as exc:
            raise SchemaRegistryError("unsupported record type") from exc

    def schema_path_for(self, record_type: str) -> Path:
        ref = self.schema_ref_for(record_type)
        relative = Path(ref).relative_to("schemas")
        path = (self.schema_root / relative).resolve()
        if self.schema_root not in path.parents:
            raise SchemaRegistryError("schema path escapes the canonical root")
        if not path.is_file():
            raise SchemaRegistryError("required schema file is unavailable")
        return path

    def load_schema(self, record_type: str) -> dict[str, Any]:
        if record_type not in self._schemas:
            path = self.schema_path_for(record_type)
            try:
                schema = json.loads(path.read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)
            except (OSError, json.JSONDecodeError, SchemaError, TypeError) as exc:
                raise SchemaRegistryError("schema could not be loaded") from exc
            self._schemas[record_type] = schema
        return self._schemas[record_type]

    def validator_for(self, record_type: str) -> Draft202012Validator:
        if record_type not in self._validators:
            self._validators[record_type] = Draft202012Validator(
                self.load_schema(record_type)
            )
        return self._validators[record_type]

    def discover(self) -> dict[str, str]:
        """Return supported record types whose canonical schemas load."""

        discovered = {}
        for record_type in self.supported_record_types:
            self.load_schema(record_type)
            discovered[record_type] = self.schema_ref_for(record_type)
        return discovered
