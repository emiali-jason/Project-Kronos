"""Provider-agnostic provider contract."""

from typing import Optional, Protocol

from kronos.provider.models.context import AuthenticatedProviderContext


class Provider(Protocol):
    """Base contract implemented by a provider integration."""

    def authenticate(self) -> AuthenticatedProviderContext:
        """Authenticate and establish one bounded provider context."""

    def current_context(self) -> Optional[AuthenticatedProviderContext]:
        """Expose the current provider-owned context."""

    def invalidate_context(self) -> None:
        """Invalidate the current provider-owned context."""

    def terminate_context(self) -> None:
        """Terminate the current provider-owned context."""

    def context_reuse_eligible(self) -> bool:
        """Report whether the current context may be reused."""
