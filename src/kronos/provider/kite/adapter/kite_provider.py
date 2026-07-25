"""Kite provider skeleton."""

from kronos.provider.contracts import Provider
from kronos.provider.contracts import AuthenticationProvider


class KiteProvider(Provider):
    """Kite provider boundary that delegates authentication."""

    def __init__(self, authentication: AuthenticationProvider) -> None:
        self._authentication = authentication

    def authenticate(self) -> None:
        self._authentication.authenticate()
