"""Provider-agnostic authentication contract."""

from typing import Protocol

from kronos.provider.models.configuration import ConfigurationBoundaryInput
from kronos.provider.models.context import AuthenticationOutcome


class AuthenticationProvider(Protocol):
    """Contract for provider authentication capabilities."""

    def authenticate(
        self,
        configuration: ConfigurationBoundaryInput,
    ) -> AuthenticationOutcome:
        """Produce exactly one Authentication Outcome for one activity."""
