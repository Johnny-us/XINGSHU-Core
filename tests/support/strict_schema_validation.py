"""Strict JSON Schema validation for portable conformance tests.

This module is test support only. It makes JSON Schema format assertions
effective and refuses to construct a validator when RFC 3339 date-time
checking is unavailable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


_VALID_DATE_TIME = "2026-01-01T00:00:00Z"
_VALID_OFFSET_DATE_TIME = "2026-01-01T08:00:00+08:00"
_INVALID_DATE_TIMES = (
    "not-a-date",
    "2026-02-30T00:00:00Z",
    "2026-01-01T00:00:00",
)


def assert_datetime_checker_available(
    checker: FormatChecker | None = None,
) -> FormatChecker:
    """Return a checker only when date-time format validation is effective."""

    candidate = checker or FormatChecker()
    if not candidate.conforms(_VALID_DATE_TIME, "date-time"):
        raise RuntimeError("date_time_checker_rejects_valid_rfc3339")
    if not candidate.conforms(_VALID_OFFSET_DATE_TIME, "date-time"):
        raise RuntimeError("date_time_checker_rejects_valid_offset")
    if any(candidate.conforms(value, "date-time") for value in _INVALID_DATE_TIMES):
        raise RuntimeError("date_time_checker_unavailable_or_ineffective")
    return candidate


def strict_validator(schema: Mapping[str, Any]) -> Draft202012Validator:
    """Create a Draft 2020-12 validator with verified format checking."""

    Draft202012Validator.check_schema(schema)
    checker = assert_datetime_checker_available()
    return Draft202012Validator(schema, format_checker=checker)
