"""Provider-agnostic provider contract."""

from typing import Optional, Protocol

from kronos.provider.models.configuration import ConfigurationBoundaryInput
from kronos.provider.models.context import (
    AuthenticationOutcome,
    AuthenticatedProviderContext,
    ContextLifecycleReason,
    ProviderAuditEvidence,
)


class Provider(Protocol):
    """Base contract implemented by a provider integration."""

    def authenticate(
        self,
        configuration: ConfigurationBoundaryInput,
    ) -> AuthenticationOutcome:
        """Perform one Authentication Activity and return its Outcome."""

    def current_context(self) -> Optional[AuthenticatedProviderContext]:
        """Expose the current provider-owned context."""

    def invalidate_context(
        self,
        reason: ContextLifecycleReason = ContextLifecycleReason.CONTEXT_NO_LONGER_VALID,
    ) -> ProviderAuditEvidence | None:
        """Invalidate the current provider-owned context."""

    def terminate_context(
        self,
        reason: ContextLifecycleReason = ContextLifecycleReason.EXPLICIT_TERMINATION,
    ) -> ProviderAuditEvidence | None:
        """Terminate the current provider-owned context."""

    def context_reuse_eligible(self) -> bool:
        """Report whether the current context may be reused."""
