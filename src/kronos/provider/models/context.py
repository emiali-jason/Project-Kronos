"""Provider-owned authenticated-context meanings and evidence."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final


class AuthenticationOutcomeKind(StrEnum):
    """The only outcomes produced by one Authentication Activity."""

    SUCCESS = "AUTHENTICATION_SUCCESS"
    REJECTED = "AUTHENTICATION_REJECTED"
    FAILED = "AUTHENTICATION_FAILED"


class ProviderEvidenceKind(StrEnum):
    """Non-sensitive Provider boundary evidence meanings."""

    AUTHENTICATION_ACTIVITY = "AUTHENTICATION_ACTIVITY"
    AUTHENTICATION_OUTCOME = "AUTHENTICATION_OUTCOME"
    CONTEXT_ESTABLISHED = "CONTEXT_ESTABLISHED"
    CONTEXT_VALIDITY_CHANGED = "CONTEXT_VALIDITY_CHANGED"
    CONTEXT_INVALIDATED = "CONTEXT_INVALIDATED"
    CONTEXT_TERMINATED = "CONTEXT_TERMINATED"


class ContextLifecycleReason(StrEnum):
    """Stable, non-sensitive lifecycle reason categories."""

    PROVIDER_DECISION = "PROVIDER_DECISION"
    AUTHENTICATION_INCOMPLETE = "AUTHENTICATION_INCOMPLETE"
    AUTHENTICATION_TECHNICAL_FAILURE = "AUTHENTICATION_TECHNICAL_FAILURE"
    PROVIDER_OPERATIONALLY_UNAVAILABLE = "PROVIDER_OPERATIONALLY_UNAVAILABLE"
    CONFIGURATION_CHANGED = "CONFIGURATION_CHANGED"
    CONTEXT_NO_LONGER_VALID = "CONTEXT_NO_LONGER_VALID"
    CONTEXT_EXPIRED = "CONTEXT_EXPIRED"
    INVALID_PROVIDER_TOKEN = "INVALID_PROVIDER_TOKEN"
    PROVIDER_SIDE_INVALIDATION = "PROVIDER_SIDE_INVALIDATION"
    EXPLICIT_TERMINATION = "EXPLICIT_TERMINATION"


@dataclass(frozen=True, slots=True)
class ProviderProvenance:
    """Attributable, non-sensitive Provider provenance."""

    provider: str
    activity_id: str

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider provenance requires a provider")
        if not self.activity_id.strip():
            raise ValueError("provider provenance requires an activity id")


@dataclass(frozen=True, slots=True)
class AuthenticationOutcome:
    """One Provider-owned result for one Authentication Activity."""

    kind: AuthenticationOutcomeKind
    provenance: ProviderProvenance
    reason: ContextLifecycleReason | None = None
    verified: bool = False
    valid_until: datetime | None = None

    def __post_init__(self) -> None:
        if self.kind is AuthenticationOutcomeKind.SUCCESS and not self.verified:
            raise ValueError("Authentication Success requires verified provider evidence")

    @property
    def succeeded(self) -> bool:
        """Whether this outcome established the right to establish context."""

        return self.kind is AuthenticationOutcomeKind.SUCCESS and self.verified


class ContextValidity(StrEnum):
    """Validity of a bounded Authenticated Provider Context."""

    VALID = "CONTEXT_VALID"
    INVALID = "CONTEXT_INVALID"
    TERMINATED = "CONTEXT_TERMINATED"


class ContextReuseEligibility(StrEnum):
    """Whether the current context remains eligible for reuse."""

    ELIGIBLE = "CONTEXT_REUSE_ELIGIBLE"
    INELIGIBLE = "CONTEXT_REUSE_INELIGIBLE"


@dataclass(frozen=True)
class AuthenticatedProviderContext:
    """Read-only representation of a bounded provider context."""

    validity: ContextValidity
    reuse_eligibility: ContextReuseEligibility
    provider: str = ""
    context_id: str = ""
    provenance: ProviderProvenance | None = None
    valid_until: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProviderAuditEvidence:
    """Non-sensitive, read-only evidence for one Provider boundary meaning."""

    kind: ProviderEvidenceKind
    provenance: ProviderProvenance
    context_id: str | None = None
    outcome: AuthenticationOutcomeKind | None = None
    reason: ContextLifecycleReason | None = None

    def __post_init__(self) -> None:
        if self.context_id is not None and not self.context_id.strip():
            raise ValueError("context id cannot be blank when supplied")


AUTHENTICATION_SUCCESS: Final = AuthenticationOutcomeKind.SUCCESS
