import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

from xingshu_core.strict_validation import (
    assert_datetime_checker_available,
    strict_validator,
)


DATE_TIME_SCHEMA = {"type": "string", "format": "date-time"}


class StrictValidationTests(unittest.TestCase):
    def test_checker_self_test_accepts_rfc3339_and_rejects_invalid_values(self):
        checker = assert_datetime_checker_available()
        self.assertTrue(checker.conforms("2026-01-01T00:00:00Z", "date-time"))
        self.assertTrue(checker.conforms("2026-01-01T08:00:00+08:00", "date-time"))
        self.assertFalse(checker.conforms("not-a-date", "date-time"))
        self.assertFalse(checker.conforms("2026-02-30T00:00:00Z", "date-time"))
        self.assertFalse(checker.conforms("2026-01-01T00:00:00", "date-time"))

    def test_factory_uses_draft_2020_12_and_rejects_invalid_date_times(self):
        validator = strict_validator(DATE_TIME_SCHEMA)
        self.assertIsInstance(validator, Draft202012Validator)
        self.assertEqual([], list(validator.iter_errors("2026-01-01T00:00:00Z")))
        self.assertEqual([], list(validator.iter_errors("2026-01-01T08:00:00+08:00")))
        for value in ("not-a-date", "2026-02-30T00:00:00Z", "2026-01-01T00:00:00"):
            with self.subTest(value=value):
                self.assertTrue(list(validator.iter_errors(value)))

    def test_schema_is_checked_before_validator_creation(self):
        with self.assertRaises(Exception):
            strict_validator({"type": "not-a-real-json-schema-type"})

    def test_missing_checker_dependency_fails_closed(self):
        with patch("xingshu_core.strict_validation.importlib.util.find_spec", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "rfc3339_validator_unavailable"):
                assert_datetime_checker_available(FormatChecker())


if __name__ == "__main__":
    unittest.main()
