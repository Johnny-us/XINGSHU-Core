"""Read-only runnable validation core for XINGSHU candidate records."""

from .decisions import Decision, ValidationIssue, ValidationResult
from .validator import validate_file, validate_record
from .context_bridge_validation import (
    validate_context_bridge_object,
    validate_registration_validation,
    validate_registration_chain,
    validate_reference_transition,
)
from .source_adapter_validation import (
    validate_source_adapter_object,
    validate_source_adapter_exchange,
)
from .authority_validation import validate_authority_object, validate_reference_authority
from .resolve_context_validation import (
    validate_resolve_context_object,
    validate_resolve_context_exchange,
)

__version__ = "0.4.0.dev0"

__all__ = [
    "Decision",
    "ValidationIssue",
    "ValidationResult",
    "__version__",
    "validate_file",
    "validate_record",
    "validate_context_bridge_object",
    "validate_registration_validation",
    "validate_registration_chain",
    "validate_reference_transition",
    "validate_source_adapter_object",
    "validate_source_adapter_exchange",
    "validate_authority_object",
    "validate_reference_authority",
    "validate_resolve_context_object",
    "validate_resolve_context_exchange",
]
