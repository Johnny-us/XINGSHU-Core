"""Exercise the public example itself; no private fixtures, tools or network."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublicProbeExampleTests(unittest.TestCase):
    def test_public_example_negative_matrix(self):
        result = subprocess.run(
            [sys.executable, "-B", "-I", "-S", str(ROOT / "examples/public-probe-contract/verify.py")],
            capture_output=True, text=True, timeout=15, check=True,
        )
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(len(report["checks"]), 26)
        self.assertTrue(all(check["pass"] for check in report["checks"]))
        self.assertEqual(report["actual_network_calls"], 0)
        self.assertIs(report["actual_owner_approval"], False)
        self.assertIs(report["real_ai_reply"], False)

    def test_examples_have_no_personal_paths_or_host_sender(self):
        for folder in ("macos-local-runner", "public-probe-contract"):
            for path in (ROOT / "examples" / folder).rglob("*"):
                if path.is_file():
                    text = path.read_text(encoding="utf-8")
                    self.assertNotIn("/Users/", text)
                    self.assertNotIn("GoogleDrive-", text)
                    self.assertNotIn("chatgpt.com/g/", text)
                    self.assertNotIn("send_message_to_thread", text)
                    self.assertNotIn("mcp__codex_app", text)


if __name__ == "__main__":
    unittest.main()
