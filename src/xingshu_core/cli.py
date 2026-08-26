"""Command-line interface for the read-only XINGSHU validator."""

from __future__ import annotations

import argparse
import json
import re
import sys
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .decisions import Decision
from .schema_registry import SchemaRegistry, SchemaRegistryError, repository_root
from .validator import validate_file


class CLIUsageError(ValueError):
    """Raised for command-line usage problems that map to exit code 4."""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CLIUsageError(message)


def _version_tuple(value: str) -> tuple[int, int, int]:
    parts = [int(part) for part in re.findall(r"\d+", value)[:3]]
    return tuple((parts + [0, 0, 0])[:3])


def _doctor_report() -> tuple[dict[str, Any], int]:
    checks: list[dict[str, str]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "status": "pass" if passed else "fail", "detail": detail})

    python_version = ".".join(str(part) for part in sys.version_info[:3])
    add("python_version", sys.version_info >= (3, 11), python_version)

    try:
        jsonschema_version = package_version("jsonschema")
        parsed = _version_tuple(jsonschema_version)
        add("jsonschema_version", (4, 23, 0) <= parsed < (5, 0, 0), jsonschema_version)
    except PackageNotFoundError:
        add("jsonschema_version", False, "not installed")

    root = repository_root()
    add("repository_root", root.is_dir(), str(root))

    try:
        registry = SchemaRegistry()
        add("schema_root", True, str(registry.schema_root))
        discovered = registry.discover()
        add("v0.3_schemas", len(discovered) == 3, ", ".join(sorted(discovered)))
    except SchemaRegistryError as exc:
        add("schema_root", False, str(exc))
        add("v0.3_schemas", False, "unavailable")

    manifest = root / "CORE_MANIFEST.yaml"
    try:
        manifest_text = manifest.read_text(encoding="utf-8")
        manifest_ok = "manifest_version:" in manifest_text and "capabilities:" in manifest_text
        add("manifest", manifest_ok, str(manifest))
    except OSError:
        add("manifest", False, "unavailable")

    ready = all(item["status"] == "pass" for item in checks)
    report = {
        "decision": Decision.PASS.value if ready else Decision.ERROR.value,
        "status": "ready" if ready else "not_ready",
        "version": __version__,
        "checks": checks,
        "errors": [] if ready else [
            {"code": "doctor_check_failed", "path": item["name"], "message": "doctor check failed"}
            for item in checks
            if item["status"] == "fail"
        ],
    }
    return report, 0 if ready else 4


def _print_doctor_human(report: dict[str, Any]) -> None:
    print(report["decision"].upper())
    print(f"status: {report['status']}")
    for check in report["checks"]:
        print(f"{check['name']}: {check['status'].upper()} ({check['detail']})")


def _print_validation_human(result: Any) -> None:
    print(result.decision.value.upper())
    print(f"record_type: {result.record_type or 'unknown'}")
    print(f"status: {result.status}")
    if result.schema_version:
        print(f"schema_version: {result.schema_version}")
    if result.schema_ref:
        print(f"schema_ref: {result.schema_ref}")
    for issue in result.errors:
        print(f"error: {issue.code} at {issue.path}: {issue.message}")


def build_parser() -> SafeArgumentParser:
    parser = SafeArgumentParser(prog="xingshu", description="Read-only XINGSHU JSON validator")
    parser.add_argument("--version", action="version", version=f"XINGSHU-Core {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="check local validator readiness")
    doctor.add_argument("--json", action="store_true", dest="json_output")

    validate = subparsers.add_parser("validate", help="validate one XINGSHU JSON file")
    validate.add_argument("file", type=Path)
    validate.add_argument("--json", action="store_true", dest="json_output")
    validate.add_argument(
        "--type",
        dest="record_type_override",
        choices=("memory_entry", "knowledge_object", "migration_provenance"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except CLIUsageError as exc:
        print("ERROR", file=sys.stderr)
        print("status: input_error", file=sys.stderr)
        print(f"message: {exc}", file=sys.stderr)
        return 4

    if args.command == "doctor":
        report, exit_code = _doctor_report()
        if args.json_output:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            _print_doctor_human(report)
        return exit_code

    result = validate_file(args.file, args.record_type_override)
    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        _print_validation_human(result)
    return result.exit_code
