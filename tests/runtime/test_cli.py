import json
import copy
import io
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from xingshu_core import cli, validator as generic
from xingshu_core.schema_registry import SchemaRegistry


ROOT = Path(__file__).resolve().parents[2]


def run_cli(*arguments):
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "xingshu_core", *arguments],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


class CLIRuntimeTests(unittest.TestCase):
    def test_version(self):
        result = run_cli("--version")
        self.assertEqual(0, result.returncode)
        self.assertEqual("XINGSHU-Core 0.4.0.dev0", result.stdout.strip())

    def test_doctor_human_and_json(self):
        human = run_cli("doctor")
        self.assertEqual(0, human.returncode, human.stderr)
        self.assertIn("PASS", human.stdout)
        machine = run_cli("doctor", "--json")
        self.assertEqual(0, machine.returncode, machine.stderr)
        report = json.loads(machine.stdout)
        self.assertEqual("pass", report["decision"])
        self.assertEqual("ready", report["status"])

    def test_valid_memory_returns_zero(self):
        result = run_cli("validate", "examples/v0.4/memory-valid.json")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("PASS", result.stdout)
        self.assertIn("status: current_valid", result.stdout)

    def test_stale_memory_returns_two(self):
        result = run_cli("validate", "examples/v0.4/memory-needs-review.json")
        self.assertEqual(2, result.returncode)
        self.assertIn("NEEDS_REVIEW", result.stdout)

    def test_schema_invalid_memory_returns_three(self):
        fixture = "tests/fixtures/v0.3/memory-entry/memory-candidate-without-source-invalid.json"
        result = run_cli("validate", fixture)
        self.assertEqual(3, result.returncode)
        self.assertIn("REJECT", result.stdout)

    def test_invalid_rfc3339_created_at_returns_reject_at_cli_boundary(self):
        base = json.loads((ROOT / "examples/v0.4/memory-valid.json").read_text())
        invalid_values = (
            "not-a-date",
            "2026-02-30T00:00:00Z",
            "2026-01-01T00:00:00",
        )
        with tempfile.TemporaryDirectory() as directory:
            for invalid_value in invalid_values:
                with self.subTest(created_at=invalid_value):
                    path = Path(directory) / "invalid-rfc3339.json"
                    record = dict(base)
                    record["created_at"] = invalid_value
                    path.write_text(json.dumps(record), encoding="utf-8")
                    result = run_cli("validate", str(path), "--json")
                    self.assertEqual(3, result.returncode, result.stderr)
                    payload = json.loads(result.stdout)
                    self.assertEqual("reject", payload["decision"])
                    self.assertIn(
                        "schema_format",
                        {error["code"] for error in payload["errors"]},
                    )

    def test_valid_migration_returns_zero(self):
        result = run_cli("validate", "examples/v0.4/migration-valid.json")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("status: accepted", result.stdout)

    def test_malformed_json_returns_four(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "malformed.json"
            path.write_text('{"record_type":', encoding="utf-8")
            result = run_cli("validate", str(path))
        self.assertEqual(4, result.returncode)
        self.assertIn("invalid_json", result.stdout)

    def test_missing_file_returns_four(self):
        result = run_cli("validate", "examples/v0.4/not-present.json")
        self.assertEqual(4, result.returncode)
        self.assertIn("input_file_missing", result.stdout)

    def test_unknown_record_type_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unknown.json"
            path.write_text(
                json.dumps({"schema_version": "0.3", "record_type": "unknown_object"}),
                encoding="utf-8",
            )
            result = run_cli("validate", str(path), "--json")
        self.assertEqual(3, result.returncode)
        self.assertEqual("reject", json.loads(result.stdout)["decision"])

    def test_json_validation_output_is_parseable_without_payload(self):
        result = run_cli("validate", "examples/v0.4/memory-valid.json", "--json")
        self.assertEqual(0, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual("pass", payload["decision"])
        self.assertEqual("memory_entry", payload["record_type"])
        self.assertNotIn("conclusion_summary", result.stdout)

    def test_validation_does_not_modify_input_file(self):
        path = ROOT / "examples/v0.4/memory-valid.json"
        before = path.read_bytes()
        result = run_cli("validate", str(path))
        after = path.read_bytes()
        self.assertEqual(0, result.returncode)
        self.assertEqual(before, after)

    def test_unknown_command_returns_error_exit_code(self):
        result = run_cli("unknown-command")
        self.assertEqual(4, result.returncode)
        self.assertIn("ERROR", result.stderr)


PUBLIC_CANDIDATE_ROUTES = (
    "context_candidate", "context_registration_proposal", "context_validation_artifact",
    "human_authorization_evidence", "registered_context_reference", "context_reference_transition",
    "source_adapter_manifest", "source_adapter_request", "source_adapter_result", "source_adapter_error",
    "trusted_client_profile", "runtime_binding", "resolve_context_request", "resolve_context_result",
    "derived_provider_metadata",
)
CLI_FAMILIES = (
    ("context_candidate", "context_bridge_schema_invalid", "context_bridge_validation_unavailable"),
    ("source_adapter_manifest", "source_adapter_schema_invalid", "source_adapter_validation_unavailable"),
    ("trusted_client_profile", "authority_schema_invalid", "authority_validation_unavailable"),
    ("resolve_context_request", "resolve_schema_invalid", "resolve_validation_unavailable"),
    ("derived_provider_metadata", "candidate_schema_invalid", "candidate_validation_unavailable"),
)
SENTINELS = (
    "SYNTHETIC_P3_PRIVATE_TEXT_SENTINEL",
    "SYNTHETIC_P3_PRIVATE_LOCATOR_SENTINEL",
    "SYNTHETIC_P3_PRIVATE_ID_SENTINEL",
)


class CandidateCLIIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 只加载 P3A 固定样本组装函数；不执行 conformance（结构一致性）测试。
        cls.objects = runpy.run_path(str(ROOT / "tests/conformance/context-bridge/test_contract_schemas.py"))["positive_objects"]()

    def raw_cli(self, raw, *arguments, in_process=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic-cli-record.json"
            path.write_text(raw, encoding="utf-8")
            before = path.read_bytes()
            if in_process:
                stdout, stderr = io.StringIO(), io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = cli.main(["validate", str(path), *arguments])
                result = subprocess.CompletedProcess([], code, stdout.getvalue(), stderr.getvalue())
            else:
                result = run_cli("validate", str(path), *arguments)
            self.assertEqual(before, path.read_bytes())
            return result

    def assert_json_failure(self, result, code, exit_code=3, decision="reject", status="rejected"):
        self.assertEqual(exit_code, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(decision, report["decision"])
        self.assertEqual(status, report["status"])
        self.assertEqual([code], [issue["code"] for issue in report["errors"]])
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, result.stdout + result.stderr)

    def test_all_fifteen_candidate_routes_validate_from_files(self):
        for route in PUBLIC_CANDIDATE_ROUTES:
            with self.subTest(route=route):
                record = self.objects[route]
                before = copy.deepcopy(record)
                result = self.raw_cli(json.dumps(record), "--type", route, "--json")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("", result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual("pass", report["decision"])
                self.assertEqual(route, report["record_type"])
                self.assertEqual("context-bridge-candidate", report["schema_version"])
                self.assertEqual("error_envelope_valid" if route == "source_adapter_error" else "object_valid", report["status"])
                self.assertEqual([], report["errors"])
                self.assertEqual(before, record)
        # 单对象 PASS 不是登记、准入、来源观察、解析成功或运行时激活证明。

    def test_candidate_human_output_reports_object_contract_only(self):
        record = copy.deepcopy(self.objects["registered_context_reference"])
        record.update(status="paused", allowed_clients=[])
        result = self.raw_cli(json.dumps(record))
        self.assertEqual(0, result.returncode)
        self.assertIn("PASS\n", result.stdout)
        self.assertIn("status: object_valid", result.stdout)
        self.assertNotIn(record["canonical_name"], result.stdout)

    def test_schema_failures_preserve_family_diagnostics(self):
        for route, code, _ in CLI_FAMILIES:
            with self.subTest(route=route):
                record = copy.deepcopy(self.objects[route])
                record["synthetic_extra"] = SENTINELS[0]
                self.assert_json_failure(self.raw_cli(json.dumps(record), "--json"), code)

    def test_specialized_and_derived_unavailability_remain_distinct(self):
        registry = SchemaRegistry()
        for route, _, code in CLI_FAMILIES:
            # 真正调用 CLI -> validate_file -> 专用函数，故障仅注入 Registry 边界。
            with self.subTest(route=route), patch.object(generic, "SchemaRegistry", return_value=registry), patch.object(registry, "validator_for", side_effect=RuntimeError(SENTINELS[0])):
                result = self.raw_cli(json.dumps(self.objects[route]), "--json", in_process=True)
            self.assert_json_failure(result, code, 4, "error", "validation_unavailable")

    def test_generic_integration_failure_codes_reach_cli_unchanged(self):
        for failure, code in (
            (RuntimeError(SENTINELS[0]), "candidate_validation_unavailable"),
            (MemoryError(SENTINELS[0]), "validation_resource_limit_exceeded"),
            (RecursionError(SENTINELS[0]), "validation_resource_limit_exceeded"),
        ):
            with self.subTest(failure=type(failure).__name__), patch.object(generic, "SchemaRegistry", side_effect=failure):
                result = self.raw_cli(json.dumps(self.objects["context_candidate"]), "--json", in_process=True)
            self.assert_json_failure(result, code, 4, "error", "validation_unavailable")

    def test_specialized_resource_code_reaches_cli_unchanged(self):
        record = copy.deepcopy(self.objects["trusted_client_profile"])
        record["created_at"] = "2" * 257
        self.assert_json_failure(self.raw_cli(json.dumps(record), "--json"), "authority_resource_limit_exceeded", 4, "error", "validation_unavailable")

    def test_internal_error_in_file_is_unsupported(self):
        record = self.objects["resolve_context_error"]
        self.assert_json_failure(self.raw_cli(json.dumps(record), "--json"), "candidate_unsupported_route")

    def test_explicit_internal_error_type_is_usage_error(self):
        result = self.raw_cli(json.dumps(self.objects["resolve_context_error"]), "--type", "resolve_context_error", "--json")
        self.assertEqual(4, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertEqual("ERROR\nstatus: input_error\nmessage: invalid command-line usage\n", result.stderr)

    def test_root_duplicate_and_mixed_discriminators_are_rejected(self):
        raw = json.dumps(self.objects["context_candidate"])
        for prefix in ('"object_kind":"context_candidate",', '"object_kind":"synthetic_unknown",', '"record_type":"memory_entry",', '"record_type":"memory_entry","record_type":"knowledge_object",'):
            with self.subTest(prefix=prefix):
                self.assert_json_failure(self.raw_cli("{" + prefix + raw[1:], "--json"), "candidate_discriminator_conflict")
        # 仅固定根级 discriminator；不赋予嵌套重复字段新语义。

    def test_unknown_kind_and_explicit_mismatch_have_distinct_codes(self):
        self.assert_json_failure(self.raw_cli(json.dumps({"object_kind": SENTINELS[2]}), "--json"), "candidate_unsupported_route")
        self.assert_json_failure(self.raw_cli(json.dumps(self.objects["context_candidate"]), "--type", "runtime_binding", "--json"), "candidate_route_mismatch")

    def test_legacy_duplicate_type_keeps_last_value_and_exit_behavior(self):
        for path, route, status in (
            ("examples/v0.4/memory-valid.json", "memory_entry", "current_valid"),
            ("tests/fixtures/v0.3/knowledge-object/main-valid.json", "knowledge_object", "accepted"),
            ("examples/v0.4/migration-valid.json", "migration_provenance", "accepted"),
        ):
            with self.subTest(route=route):
                raw = (ROOT / path).read_text(encoding="utf-8")
                result = self.raw_cli('{"record_type":"synthetic_unsupported",' + raw.lstrip()[1:], "--json")
                self.assertEqual(0, result.returncode)
                report = json.loads(result.stdout)
                self.assertEqual(("pass", status, route), (report["decision"], report["status"], report["record_type"]))
                self.assert_json_failure(self.raw_cli(raw.rstrip()[:-1] + ',"record_type":"synthetic_unsupported"}', "--json"), "unknown_record_type")

    def test_human_and_json_diagnostics_do_not_echo_private_values(self):
        for sentinel in SENTINELS:
            with self.subTest(sentinel=sentinel):
                record = copy.deepcopy(self.objects["context_candidate"])
                record["synthetic_extra"] = sentinel
                for arguments in ((), ("--json",)):
                    result = self.raw_cli(json.dumps(record), *arguments)
                    self.assertEqual(3, result.returncode)
                    self.assertIn("context_bridge_schema_invalid", result.stdout)
                    self.assertNotIn(sentinel, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
