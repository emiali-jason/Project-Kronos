from dataclasses import dataclass
from enum import StrEnum

from kronos.provider.exceptions.connectivity import ProviderErrorCode


class ProviderAvailabilityState(StrEnum):
    """Provider-internal technical availability for EP-004."""

    NOT_INITIALIZED = "NOT_INITIALIZED"
    AVAILABLE = "AVAILABLE"
    CONFIGURATION_INVALID = "CONFIGURATION_INVALID"
    AUTHENTICATION_REJECTED = "AUTHENTICATION_REJECTED"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ProviderAvailability:
    """SDK-free result of one Provider connectivity operation."""

    state: ProviderAvailabilityState
    error_code: ProviderErrorCode | None = None
