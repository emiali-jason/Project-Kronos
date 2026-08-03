from dataclasses import dataclass, field
import re

from kronos.configuration.exceptions import ConfigurationError
from kronos.provider.models.authentication import ProviderAuthenticationConfiguration


CAR016_KITE_REDIRECT_URL = "http://127.0.0.1:8765/kite/callback"
_PROTECTED_REFERENCE_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")


@dataclass(frozen=True, slots=True)
class Settings:
    """Strongly named KRONOS runtime configuration."""

    provider: str
    kite_api_key: str = field(repr=False)
    kite_api_secret: str = field(repr=False)
    kite_access_token: str = field(repr=False)
    kite_redirect_url: str
    kite_credential_ref: str = ""
    kite_intended_registration_ref: str = ""

    def __post_init__(self) -> None:
        if not self.provider:
            raise ConfigurationError("KRONOS_PROVIDER must not be empty")

    def validate_kite_connectivity(self) -> None:
        """Validate the Configuration-owned inputs required by EP-004."""

        if self.provider.upper() != "KITE":
            raise ConfigurationError("KRONOS_PROVIDER must be KITE for EP-004")
        if not self.kite_api_key:
            raise ConfigurationError("KRONOS_KITE_API_KEY must not be empty")
        if not self.kite_access_token:
            raise ConfigurationError("KRONOS_KITE_ACCESS_TOKEN must not be empty")

    def validate_kite_authentication(self) -> None:
        """Validate the preserved legacy Kite authentication path."""

        if self.provider.upper() != "KITE":
            raise ConfigurationError("KRONOS_PROVIDER must be KITE for EDD-001")
        if not self.kite_api_key:
            raise ConfigurationError("KRONOS_KITE_API_KEY must not be empty")
        if not self.kite_api_secret:
            raise ConfigurationError("KRONOS_KITE_API_SECRET must not be empty")
        if not self.kite_redirect_url:
            raise ConfigurationError("KRONOS_KITE_REDIRECT_URL must not be empty")

    def validate_car016_provider_authentication(self) -> None:
        """Validate non-secret Configuration references for CAR-016."""

        if self.provider.upper() != "KITE":
            raise ConfigurationError("KRONOS_PROVIDER must be KITE for CAR-016")
        if not self.kite_api_key:
            raise ConfigurationError("KRONOS_KITE_API_KEY must not be empty")
        if self.kite_redirect_url != CAR016_KITE_REDIRECT_URL:
            raise ConfigurationError(
                "KRONOS_KITE_REDIRECT_URL must match the CAR-016 callback"
            )
        if not _valid_protected_reference(self.kite_credential_ref):
            raise ConfigurationError(
                "KRONOS_KITE_CREDENTIAL_REF must be a protected reference"
            )
        if not _valid_protected_reference(self.kite_intended_registration_ref):
            raise ConfigurationError(
                "KRONOS_KITE_INTENDED_REGISTRATION_REF must be a protected reference"
            )

    def provider_authentication_configuration(
        self,
    ) -> ProviderAuthenticationConfiguration:
        """Project the CAR-016 configuration without the legacy API secret."""

        self.validate_car016_provider_authentication()
        return ProviderAuthenticationConfiguration(
            provider=self.provider.upper(),
            _api_key=self.kite_api_key,
            redirect_uri=self.kite_redirect_url,
            intended_registration_ref=self.kite_intended_registration_ref,
            credential_ref=self.kite_credential_ref,
        )


def _valid_protected_reference(value: object) -> bool:
    return (
        isinstance(value, str)
        and _PROTECTED_REFERENCE_PATTERN.fullmatch(value) is not None
    )
