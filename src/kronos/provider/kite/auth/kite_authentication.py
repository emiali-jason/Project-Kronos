"""Kite authentication skeleton."""

from collections.abc import Callable
from typing import Optional

from kronos.provider.contracts import AuthenticationProvider


class KiteAuthentication(AuthenticationProvider):
    """Kite authentication boundary with an injected activity."""

    def __init__(self, authentication_activity: Optional[Callable[[], None]] = None) -> None:
        self._authentication_activity = authentication_activity

    def authenticate(self) -> None:
        if self._authentication_activity is None:
            raise NotImplementedError
        self._authentication_activity()
