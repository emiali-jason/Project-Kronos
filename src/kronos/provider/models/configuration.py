"""Provider-facing representations of Configuration-owned meanings."""

from dataclasses import dataclass
from enum import StrEnum


class ConfigurationEligibilityState(StrEnum):
    """Configuration Eligibility as consumed by Provider."""

    ELIGIBLE = "CONFIGURATION_ELIGIBLE"
    INELIGIBLE = "CONFIGURATION_INELIGIBLE"


class OperationalConfigurationValidityState(StrEnum):
    """Operational Configuration Validity as consumed by Provider."""

    VALID = "OPERATIONAL_CONFIGURATION_VALID"
    INVALID = "OPERATIONAL_CONFIGURATION_INVALID"


@dataclass(frozen=True, slots=True)
class RuntimeConfiguration:
    """Non-secret Runtime Configuration meaning supplied to Provider."""

    provider: str
    operational_context: str

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("runtime configuration requires a provider")
        if not self.operational_context.strip():
            raise ValueError("runtime configuration requires an operational context")


@dataclass(frozen=True, slots=True)
class ConfigurationEligibility:
    """Configuration-owned eligibility and its non-sensitive reason."""

    state: ConfigurationEligibilityState
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class OperationalConfigurationValidity:
    """Configuration-owned operational validity and its non-sensitive reason."""

    state: OperationalConfigurationValidityState
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ConfigurationBoundaryInput:
    """The complete non-secret input consumed at the Provider boundary."""

    runtime: RuntimeConfiguration
    eligibility: ConfigurationEligibility
    validity: OperationalConfigurationValidity

    @property
    def usable(self) -> bool:
        """Whether Configuration has made the supplied meaning eligible."""

        return (
            self.eligibility.state is ConfigurationEligibilityState.ELIGIBLE
            and self.validity.state is OperationalConfigurationValidityState.VALID
        )
