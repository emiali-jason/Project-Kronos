"""Provider-agnostic authentication contract."""

from typing import Protocol


class AuthenticationProvider(Protocol):
    """Contract for provider authentication capabilities."""
