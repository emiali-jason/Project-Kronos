from dataclasses import dataclass, field

from kronos.configuration.exceptions import ConfigurationError


@dataclass(frozen=True, slots=True)
class Settings:
    """Strongly named KRONOS runtime configuration."""

    provider: str
    kite_api_key: str = field(repr=False)
    kite_api_secret: str = field(repr=False)
    kite_access_token: str = field(repr=False)
    kite_redirect_url: str

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
