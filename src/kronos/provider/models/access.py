"""Provider availability and usability meanings for EDD-001."""

from dataclasses import dataclass
from enum import StrEnum


class ProviderOperationalAvailability(StrEnum):
    """Availability relevant to establishing or maintaining context."""

    NOT_ESTABLISHED = "PROVIDER_OPERATIONAL_NOT_ESTABLISHED"
    AVAILABLE = "PROVIDER_OPERATIONAL_AVAILABLE"
    UNAVAILABLE = "PROVIDER_OPERATIONAL_UNAVAILABLE"


class ProviderUsabilityState(StrEnum):
    """Whether eligible Configuration can be used for Provider access."""

    USABLE = "PROVIDER_USABLE"
    UNUSABLE = "PROVIDER_UNUSABLE"


@dataclass(frozen=True, slots=True)
class ProviderAvailability:
    """Provider availability relevant only to the context boundary."""

    operational: ProviderOperationalAvailability
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderUsability:
    """Provider-owned usability of supplied eligible Configuration."""

    state: ProviderUsabilityState
    reason: str | None = None
