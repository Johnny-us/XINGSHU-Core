import json
import unittest
from pathlib import Path

from xingshu_core import validate_record


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests/fixtures/v0.3/knowledge-object"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def evaluate(record):
    return validate_record(record).status


class KnowledgeObjectTests(unittest.TestCase):
    def test_valid_main_object(self):
        record = load("main-valid.json")
        self.assertEqual("accepted", evaluate(record))
        self.assertEqual("active", record["document_state"])
        self.assertEqual("pending_verification", record["runtime_validation_state"])

    def test_derived_view_cannot_overwrite_source(self):
        self.assertEqual("rejected", evaluate(load("derived-view-overwrites-source-invalid.json")))

    def test_derived_view_cannot_be_source_of_truth(self):
        record = load("main-valid.json")
        record["origin_form"] = "derived_view"
        record["relationships"]["derived_from"] = ["knowledge:synthetic-source"]
        self.assertEqual("rejected", evaluate(record))

    def test_appendix_cannot_be_second_source_of_truth(self):
        self.assertEqual("rejected", evaluate(load("appendix-becomes-second-source-of-truth-invalid.json")))

    def test_cross_platform_path_reuse_is_rejected(self):
        self.assertEqual("rejected", evaluate(load("cross-platform-path-reuse-invalid.json")))

    def test_unknown_role_fails_closed(self):
        record = load("main-valid.json")
        record["document_role"] = "alternate_main"
        self.assertEqual("rejected", evaluate(record))


if __name__ == "__main__":
    unittest.main()
