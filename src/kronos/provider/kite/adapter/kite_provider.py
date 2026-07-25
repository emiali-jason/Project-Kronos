"""Kite provider skeleton."""

from typing import Optional

from kronos.provider.contracts import Provider
from kronos.provider.contracts import AuthenticationProvider
from kronos.provider.contracts import ProviderContext
from kronos.provider.models.context import AuthenticatedProviderContext


class KiteProvider(Provider):
    """Kite provider boundary that delegates authentication."""

    def __init__(
        self,
        authentication: AuthenticationProvider,
        context: ProviderContext,
    ) -> None:
        self._authentication = authentication
        self._context = context

    def authenticate(self) -> AuthenticatedProviderContext:
        self._authentication.authenticate()
        return self._context.establish()

    def current_context(self) -> Optional[AuthenticatedProviderContext]:
        return self._context.current()

    def invalidate_context(self) -> None:
        self._context.invalidate()

    def terminate_context(self) -> None:
        self._context.terminate()

    def context_reuse_eligible(self) -> bool:
        return self._context.reuse_eligible()
