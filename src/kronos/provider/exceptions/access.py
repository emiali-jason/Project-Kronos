"""Redacted Provider Access failures."""

from enum import StrEnum


class ProviderAccessPreconditionCode(StrEnum):
    """Configuration-owned reasons that prevent Authentication Activity."""

    PROVIDER_MISMATCH = "PROVIDER_MISMATCH"
    CONFIGURATION_INELIGIBLE = "CONFIGURATION_INELIGIBLE"


class ProviderAccessPreconditionError(RuntimeError):
    """A precondition failure that is not an Authentication Outcome."""

    def __init__(self, code: ProviderAccessPreconditionCode) -> None:
        self.code = code
        super().__init__(f"Provider access precondition failed: {code.value}")
