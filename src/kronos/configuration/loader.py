import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Mapping

from dotenv import load_dotenv

from kronos.configuration.apple_keychain import (
    AppleKeychainApiKeySource,
    run_security_framework_subprocess,
)
from kronos.configuration.credentials import SecureCredentialSource
from kronos.configuration.exceptions import ConfigurationError
from kronos.configuration.settings import (
    CAR016_KITE_REDIRECT_URL,
    GOVERNED_KITE_APPLICATION_REGISTRATION_REF,
    GOVERNED_PROVIDER_CONFIGURATION_REF,
    GovernedProviderAuthenticationConfiguration,
    Settings,
)
from kronos.provider.models.authentication import ProviderAuthenticationConfiguration


DEFAULT_PROVIDER = "KITE"
DEFAULT_KITE_REDIRECT_URL = "http://localhost:8000/callback"
PROVIDER_AUTHENTICATION_APPLICATION_CONFIG = "provider-authentication.json"
_APPLICATION_CONFIG_KEYS = frozenset(
    {
        "KRONOS_PROVIDER",
        "KRONOS_KITE_REDIRECT_URL",
        "KRONOS_KITE_CREDENTIAL_REF",
        "KRONOS_KITE_INTENDED_REGISTRATION_REF",
        "KRONOS_PROVIDER_CONFIGURATION_REF",
        "KRONOS_KITE_APPLICATION_REGISTRATION_REF",
    }
)
_PROTECTED_CONFIG_KEYS = frozenset(
    {
        "KRONOS_KITE_API_KEY",
        "KRONOS_KITE_API_SECRET",
        "KRONOS_KITE_ACCESS_TOKEN",
        "KRONOS_KITE_REQUEST_TOKEN",
        "KRONOS_KITE_CALLBACK_TOKEN",
    }
)
_APPROVED_APPLICATION_CONFIG = {
    "KRONOS_PROVIDER": "KITE",
    "KRONOS_KITE_REDIRECT_URL": CAR016_KITE_REDIRECT_URL,
    "KRONOS_KITE_CREDENTIAL_REF": "KITE-API-SECRET-PRIMARY",
    "KRONOS_KITE_INTENDED_REGISTRATION_REF": (
        "KITE-INTENDED-PRINCIPAL-PRIMARY"
    ),
    "KRONOS_PROVIDER_CONFIGURATION_REF": GOVERNED_PROVIDER_CONFIGURATION_REF,
    "KRONOS_KITE_APPLICATION_REGISTRATION_REF": (
        GOVERNED_KITE_APPLICATION_REGISTRATION_REF
    ),
}


def provider_authentication_application_config_path(
    *,
    home: Path | None = None,
) -> Path:
    """Return the stable per-user location for non-secret app configuration."""

    root = Path.home() if home is None else home
    return (
        root
        / "Library"
        / "Application Support"
        / "Project-KRONOS"
        / PROVIDER_AUTHENTICATION_APPLICATION_CONFIG
    )


def provision_provider_authentication_application_config(
    *,
    path: Path | None = None,
) -> Path:
    """Atomically write only the approved non-secret application record."""

    target = (
        provider_authentication_application_config_path()
        if path is None
        else path
    )
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = json.dumps(
        _APPROVED_APPLICATION_CONFIG,
        indent=2,
        sort_keys=True,
    ) + "\n"
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, target)
    except OSError as error:
        if temporary_name:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
        raise ConfigurationError(
            "PROVIDER_AUTHENTICATION_APPLICATION_CONFIGURATION_WRITE_FAILED"
        ) from error
    return target


def provider_authentication_application_config_ready(
    *,
    path: Path | None = None,
) -> bool:
    """Validate the exact non-secret record without reading credentials."""

    target = (
        provider_authentication_application_config_path()
        if path is None
        else path
    )
    try:
        return _read_provider_authentication_application_config(target) == (
            _APPROVED_APPLICATION_CONFIG
        )
    except ConfigurationError:
        return False


def _read_provider_authentication_application_config(path: Path) -> dict[str, str]:
    """Read one strict non-secret application configuration record."""

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise ConfigurationError(
            "PROVIDER_AUTHENTICATION_APPLICATION_CONFIGURATION_UNAVAILABLE"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ConfigurationError(
            "PROVIDER_AUTHENTICATION_APPLICATION_CONFIGURATION_INVALID"
        )
    if metadata.st_size > 16_384:
        raise ConfigurationError(
            "PROVIDER_AUTHENTICATION_APPLICATION_CONFIGURATION_INVALID"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConfigurationError(
            "PROVIDER_AUTHENTICATION_APPLICATION_CONFIGURATION_INVALID"
        ) from error
    if not isinstance(raw, dict) or set(raw) != _APPLICATION_CONFIG_KEYS:
        prohibited = (
            set(raw) & _PROTECTED_CONFIG_KEYS
            if isinstance(raw, dict)
            else set()
        )
        code = (
            "PROVIDER_AUTHENTICATION_PROTECTED_CONFIGURATION_PROHIBITED"
            if prohibited
            else "PROVIDER_AUTHENTICATION_APPLICATION_CONFIGURATION_INVALID"
        )
        raise ConfigurationError(code)
    if any(not isinstance(value, str) for value in raw.values()):
        raise ConfigurationError(
            "PROVIDER_AUTHENTICATION_APPLICATION_CONFIGURATION_INVALID"
        )
    return {key: value for key, value in raw.items()}


def _provider_authentication_source(
    *,
    application_config_path: Path | None,
    environment: Mapping[str, str] | None,
) -> tuple[dict[str, str], bool]:
    path = (
        provider_authentication_application_config_path()
        if application_config_path is None
        else application_config_path
    )
    source = _read_provider_authentication_application_config(path)
    if source:
        return source, True
    ambient = os.environ if environment is None else environment
    for key in _APPLICATION_CONFIG_KEYS:
        value = ambient.get(key)
        if value is not None:
            source[key] = value
    if not source:
        raise ConfigurationError(
            "PROVIDER_AUTHENTICATION_APPLICATION_CONFIGURATION_UNAVAILABLE"
        )
    return source, False


def _provider_authentication_configuration(
    source: Mapping[str, str],
    api_key: str,
) -> ProviderAuthenticationConfiguration:
    settings = Settings(
        provider=source.get("KRONOS_PROVIDER", DEFAULT_PROVIDER).strip(),
        kite_api_key=api_key,
        kite_api_secret="",
        kite_access_token="",
        kite_redirect_url=source.get(
            "KRONOS_KITE_REDIRECT_URL",
            CAR016_KITE_REDIRECT_URL,
        ).strip(),
        kite_credential_ref=source.get(
            "KRONOS_KITE_CREDENTIAL_REF",
            "",
        ).strip(),
        kite_intended_registration_ref=source.get(
            "KRONOS_KITE_INTENDED_REGISTRATION_REF",
            "",
        ).strip(),
    )
    return settings.provider_authentication_configuration()


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


def load_provider_authentication_configuration(
    *,
    application_config_path: Path | None = None,
    environment: Mapping[str, str] | None = None,
    api_key_source: SecureCredentialSource | None = None,
) -> ProviderAuthenticationConfiguration:
    """Load app configuration while keeping credentials in protected custody."""

    source, from_application_config = _provider_authentication_source(
        application_config_path=application_config_path,
        environment=environment,
    )
    ambient = os.environ if environment is None else environment
    environment_api_key = (
        ""
        if from_application_config
        else ambient.get("KRONOS_KITE_API_KEY", "")
    )
    if environment_api_key:
        return _provider_authentication_configuration(source, environment_api_key)

    registration_ref = source.get(
        "KRONOS_KITE_APPLICATION_REGISTRATION_REF",
        "",
    ).strip()
    if registration_ref != GOVERNED_KITE_APPLICATION_REGISTRATION_REF:
        raise ConfigurationError(
            "PROVIDER_AUTHENTICATION_APPLICATION_REGISTRATION_INVALID"
        )
    if (
        source.get("KRONOS_PROVIDER_CONFIGURATION_REF", "").strip()
        != GOVERNED_PROVIDER_CONFIGURATION_REF
    ):
        raise ConfigurationError(
            "PROVIDER_AUTHENTICATION_PROVIDER_CONFIGURATION_INVALID"
        )
    provider = source.get("KRONOS_PROVIDER", DEFAULT_PROVIDER).strip()
    protected_source = api_key_source or AppleKeychainApiKeySource(
        provider=provider,
        runner=run_security_framework_subprocess,
    )
    try:
        lease = protected_source.acquire(registration_ref)
    except Exception:
        raise ConfigurationError(
            "PROVIDER_AUTHENTICATION_API_KEY_UNAVAILABLE"
        ) from None
    try:
        try:
            return lease.reveal_for_call(
                lambda api_key: _provider_authentication_configuration(
                    source,
                    api_key,
                )
            )
        except ConfigurationError:
            raise
        except Exception:
            raise ConfigurationError(
                "PROVIDER_AUTHENTICATION_API_KEY_UNAVAILABLE"
            ) from None
    finally:
        lease.close()


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
