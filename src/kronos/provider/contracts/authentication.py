"""Compatibility name for the authoritative authentication lifecycle contract.

The former single-call ``authenticate(configuration)`` contract is deliberately
absent.  Supported Provider integrations must use the bounded lifecycle owned
by ``ProviderAuthenticationService``.
"""

from typing import Protocol

from kronos.provider.contracts.provider_authentication import (
    ProviderAuthenticationService,
)
from kronos.provider.models.context import AuthenticatedProviderContext


class AuthenticationProvider(ProviderAuthenticationService, Protocol):
    """Authoritative lifecycle plus its sanitized context projection."""

    def current_context(self) -> AuthenticatedProviderContext | None:
        """Return only the established sanitized context projection."""


__all__ = ["AuthenticationProvider"]
