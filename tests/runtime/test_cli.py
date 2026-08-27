import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
