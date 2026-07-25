"""Provider-owned authenticated context contract."""

from typing import Optional, Protocol

from kronos.provider.models.context import AuthenticatedProviderContext


class ProviderContext(Protocol):
    """Contract for ownership of an Authenticated Provider Context."""

    def establish(self) -> AuthenticatedProviderContext:
        """Establish exactly one bounded provider context."""

    def current(self) -> Optional[AuthenticatedProviderContext]:
        """Expose the current provider context, when present."""

    def invalidate(self) -> None:
        """Invalidate the current provider context."""

    def terminate(self) -> None:
        """Terminate the current provider context."""

    def reuse_eligible(self) -> bool:
        """Report whether the current context remains eligible for reuse."""
