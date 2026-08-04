import os

from dotenv import load_dotenv

from kronos.configuration.settings import (
    CAR016_KITE_REDIRECT_URL,
    GovernedProviderAuthenticationConfiguration,
    Settings,
)
from kronos.provider.models.authentication import ProviderAuthenticationConfiguration


DEFAULT_PROVIDER = "KITE"
DEFAULT_KITE_REDIRECT_URL = "http://localhost:8000/callback"
def load_settings() -> Settings:
    """Load KRONOS configuration from the environment and an optional `.env`."""

    load_dotenv()

    return Settings(
        provider=os.getenv("KRONOS_PROVIDER", DEFAULT_PROVIDER).strip(),
        kite_api_key=os.getenv("KRONOS_KITE_API_KEY", ""),
        kite_api_secret=os.getenv("KRONOS_KITE_API_SECRET", ""),
        kite_access_token=os.getenv("KRONOS_KITE_ACCESS_TOKEN", ""),
        kite_redirect_url=os.getenv(
            "KRONOS_KITE_REDIRECT_URL",
            DEFAULT_KITE_REDIRECT_URL,
        ).strip(),
        kite_credential_ref=os.getenv("KRONOS_KITE_CREDENTIAL_REF", "").strip(),
        kite_intended_registration_ref=os.getenv(
            "KRONOS_KITE_INTENDED_REGISTRATION_REF",
            "",
        ).strip(),
        provider_configuration_ref=os.getenv(
            "KRONOS_PROVIDER_CONFIGURATION_REF",
            "",
        ).strip(),
        kite_application_registration_ref=os.getenv(
            "KRONOS_KITE_APPLICATION_REGISTRATION_REF",
            "",
        ).strip(),
    )


def load_provider_authentication_configuration() -> ProviderAuthenticationConfiguration:
    """Load CAR-016 references without reading the plaintext API-secret key."""

    load_dotenv()
    settings = Settings(
        provider=os.getenv("KRONOS_PROVIDER", DEFAULT_PROVIDER).strip(),
        kite_api_key=os.getenv("KRONOS_KITE_API_KEY", ""),
        kite_api_secret="",
        kite_access_token="",
        kite_redirect_url=os.getenv(
            "KRONOS_KITE_REDIRECT_URL",
            CAR016_KITE_REDIRECT_URL,
        ).strip(),
        kite_credential_ref=os.getenv("KRONOS_KITE_CREDENTIAL_REF", "").strip(),
        kite_intended_registration_ref=os.getenv(
            "KRONOS_KITE_INTENDED_REGISTRATION_REF",
            "",
        ).strip(),
    )
    return settings.provider_authentication_configuration()


def load_governed_provider_authentication_configuration(
    environment: object = None,
) -> GovernedProviderAuthenticationConfiguration:
    """Load the exact allow-list without invoking dotenv or reading secrets."""

    source = os.environ if environment is None else environment
    getter = getattr(source, "get", None)
    if not callable(getter):
        raise TypeError("GOVERNED_CONFIGURATION_SOURCE_INVALID")
    settings = Settings(
        provider=getter("KRONOS_PROVIDER", "").strip(),
        kite_api_key=getter("KRONOS_KITE_API_KEY", ""),
        kite_api_secret="",
        kite_access_token="",
        kite_redirect_url=getter("KRONOS_KITE_REDIRECT_URL", "").strip(),
        kite_credential_ref=getter("KRONOS_KITE_CREDENTIAL_REF", "").strip(),
        kite_intended_registration_ref=getter(
            "KRONOS_KITE_INTENDED_REGISTRATION_REF",
            "",
        ).strip(),
        provider_configuration_ref=getter(
            "KRONOS_PROVIDER_CONFIGURATION_REF",
            "",
        ).strip(),
        kite_application_registration_ref=getter(
            "KRONOS_KITE_APPLICATION_REGISTRATION_REF",
            "",
        ).strip(),
    )
    return settings.governed_provider_authentication_configuration()
