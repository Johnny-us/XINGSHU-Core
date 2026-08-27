"""Production strict JSON Schema validation for the v0.4 candidate.

The factory is deliberately fail-closed: a validator is never created unless
the RFC 3339 ``date-time`` checker accepts valid timestamps and rejects the
known invalid forms used by the candidate contract.
"""

from __future__ import annotations

import importlib.util
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
    """Return a checker only when RFC 3339 validation is demonstrably active."""

    if importlib.util.find_spec("rfc3339_validator") is None:
        raise RuntimeError("rfc3339_validator_unavailable")
    candidate = checker or FormatChecker()
    if not candidate.conforms(_VALID_DATE_TIME, "date-time"):
        raise RuntimeError("date_time_checker_rejects_valid_rfc3339")
    if not candidate.conforms(_VALID_OFFSET_DATE_TIME, "date-time"):
        raise RuntimeError("date_time_checker_rejects_valid_offset")
    if any(candidate.conforms(value, "date-time") for value in _INVALID_DATE_TIMES):
        raise RuntimeError("date_time_checker_ineffective")
    return candidate


def strict_validator(schema: Mapping[str, Any]) -> Draft202012Validator:
    """Create a Draft 2020-12 validator with an effective FormatChecker."""

    Draft202012Validator.check_schema(schema)
    checker = assert_datetime_checker_available()
    return Draft202012Validator(schema, format_checker=checker)
