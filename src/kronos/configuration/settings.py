from dataclasses import dataclass, field

from kronos.configuration.exceptions import ConfigurationError


@dataclass(frozen=True, slots=True)
class Settings:
    """Strongly named KRONOS runtime configuration."""

    provider: str
    kite_api_key: str = field(repr=False)
    kite_api_secret: str = field(repr=False)
    kite_redirect_url: str

    def __post_init__(self) -> None:
        if not self.provider:
            raise ConfigurationError("KRONOS_PROVIDER must not be empty")
        if not self.kite_redirect_url:
            raise ConfigurationError("KRONOS_KITE_REDIRECT_URL must not be empty")
