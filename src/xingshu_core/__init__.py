"""Read-only runnable validation core for XINGSHU candidate records."""

from .decisions import Decision, ValidationIssue, ValidationResult
from .validator import validate_file, validate_record

__version__ = "0.4.0.dev0"

__all__ = [
    "Decision",
    "ValidationIssue",
    "ValidationResult",
    "__version__",
    "validate_file",
    "validate_record",
]
