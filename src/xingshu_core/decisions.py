"""Stable validation decisions and CLI exit codes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Decision(str, Enum):
    """Top-level decisions returned by the runnable validator."""

    PASS = "pass"
    NEEDS_REVIEW = "needs_review"
    REJECT = "reject"
    ERROR = "error"


EXIT_CODES = {
    Decision.PASS: 0,
    Decision.NEEDS_REVIEW: 2,
    Decision.REJECT: 3,
    Decision.ERROR: 4,
}


@dataclass(frozen=True)
class ValidationIssue:
    """A minimal error or review reason that never includes the full payload."""

    code: str
    path: str
    message: str
    field: str | None = None

    def to_dict(self) -> dict[str, str]:
        value = {"code": self.code, "path": self.path, "message": self.message}
        if self.field is not None:
            value["field"] = self.field
        return value


@dataclass(frozen=True)
class ValidationResult:
    """Unified result returned by library and CLI validation."""

    decision: Decision
    status: str
    record_type: str | None
    schema_version: str | None
    schema_ref: str | None
    errors: tuple[ValidationIssue, ...] = field(default_factory=tuple)

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.decision]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "status": self.status,
            "record_type": self.record_type,
            "schema_version": self.schema_version,
            "schema_ref": self.schema_ref,
            "errors": [issue.to_dict() for issue in self.errors],
        }
