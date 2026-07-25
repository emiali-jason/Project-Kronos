"""Provider-owned authenticated context meanings."""

from dataclasses import dataclass
from enum import Enum


class ContextValidity(Enum):
    """Validity of a bounded Authenticated Provider Context."""

    VALID = "CONTEXT_VALID"
    INVALID = "CONTEXT_INVALID"
    TERMINATED = "CONTEXT_TERMINATED"


class ContextReuseEligibility(Enum):
    """Whether the current context remains eligible for reuse."""

    ELIGIBLE = "CONTEXT_REUSE_ELIGIBLE"
    INELIGIBLE = "CONTEXT_REUSE_INELIGIBLE"


@dataclass(frozen=True)
class AuthenticatedProviderContext:
    """Read-only representation of a bounded provider context."""

    validity: ContextValidity
    reuse_eligibility: ContextReuseEligibility
