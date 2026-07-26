"""Provider Access and Provider Context contracts."""

from collections.abc import Sequence
from typing import Protocol

from kronos.provider.models.access import ProviderAvailability, ProviderUsability
from kronos.provider.models.configuration import ConfigurationBoundaryInput
from kronos.provider.models.context import (
    AuthenticatedProviderContext,
    AuthenticationOutcome,
    ContextLifecycleReason,
    ProviderAuditEvidence,
)


class AuthenticationActivity(Protocol):
    """Provider-owned activity producing exactly one Authentication Outcome."""

    def __call__(self, configuration: ConfigurationBoundaryInput) -> AuthenticationOutcome:
        """Perform one bounded Authentication Activity."""


class ProviderAccess(Protocol):
    """Complete EDD-001 Provider Access boundary."""

    def authenticate(
        self,
        configuration: ConfigurationBoundaryInput,
    ) -> AuthenticationOutcome:
        """Produce one Authentication Outcome for one activity."""

    def current_context(self) -> AuthenticatedProviderContext | None:
        """Return the current bounded context, if established."""

    def validate_context(self) -> ProviderAuditEvidence | None:
        """Apply authoritative Provider evidence to Context Validity."""

    def invalidate_context(
        self,
        reason: ContextLifecycleReason = ContextLifecycleReason.CONTEXT_NO_LONGER_VALID,
    ) -> ProviderAuditEvidence | None:
        """Invalidate the current context and return non-sensitive evidence."""

    def terminate_context(
        self,
        reason: ContextLifecycleReason = ContextLifecycleReason.EXPLICIT_TERMINATION,
    ) -> ProviderAuditEvidence | None:
        """Terminate the current context and return non-sensitive evidence."""

    def availability(self) -> ProviderAvailability:
        """Return context-bound Provider Operational Availability."""

    def usability(
        self,
        configuration: ConfigurationBoundaryInput,
    ) -> ProviderUsability:
        """Return Provider Usability without creating capability authority."""

    def evidence(self) -> Sequence[ProviderAuditEvidence]:
        """Return read-only, non-sensitive boundary evidence."""
