from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest

from kronos.configuration import loader
from kronos.configuration.exceptions import ConfigurationError
from kronos.configuration.settings import CAR016_KITE_REDIRECT_URL, Settings


def _settings(
    *,
    provider: str = "KITE",
    api_key: str = "unit-api-key",
    access_token: str = "unit-access-token",
) -> Settings:
    return Settings(
        provider=provider,
        kite_api_key=api_key,
        kite_api_secret="unit-api-secret",
        kite_access_token=access_token,
        kite_redirect_url="http://localhost:8000/callback",
    )


def test_settings_repr_redacts_all_kite_secrets() -> None:
    settings = _settings()

    rendered = repr(settings)

    assert "unit-api-key" not in rendered
    assert "unit-api-secret" not in rendered
    assert "unit-access-token" not in rendered


def test_settings_remains_immutable() -> None:
    settings = _settings()

    with pytest.raises(FrozenInstanceError):
        settings.provider = "OTHER"  # type: ignore[misc]


def test_ep004_does_not_require_api_secret_or_redirect_url() -> None:
    settings = Settings(
        provider="KITE",
        kite_api_key="unit-api-key",
        kite_api_secret="",
        kite_access_token="unit-access-token",
        kite_redirect_url="",
    )

    settings.validate_kite_connectivity()


def test_edd001_authentication_requires_configuration_owned_material() -> None:
    settings = Settings(
        provider="KITE",
        kite_api_key="unit-api-key",
        kite_api_secret="unit-api-secret",
        kite_access_token="",
        kite_redirect_url="https://local.test/kite/callback",
    )

    settings.validate_kite_authentication()


@pytest.mark.parametrize(
    ("provider", "api_key", "api_secret", "redirect_url", "expected_name"),
    [
        (
            "OTHER",
            "unit-api-key",
            "unit-api-secret",
            "https://local.test/kite/callback",
            "KRONOS_PROVIDER",
        ),
        (
            "KITE",
            "",
            "unit-api-secret",
            "https://local.test/kite/callback",
            "KRONOS_KITE_API_KEY",
        ),
        (
            "KITE",
            "unit-api-key",
            "",
            "https://local.test/kite/callback",
            "KRONOS_KITE_API_SECRET",
        ),
        (
            "KITE",
            "unit-api-key",
            "unit-api-secret",
            "",
            "KRONOS_KITE_REDIRECT_URL",
        ),
    ],
)
def test_kite_authentication_validation_is_stable_and_redacted(
    provider: str,
    api_key: str,
    api_secret: str,
    redirect_url: str,
    expected_name: str,
) -> None:
    settings = Settings(
        provider=provider,
        kite_api_key=api_key,
        kite_api_secret=api_secret,
        kite_access_token="",
        kite_redirect_url=redirect_url,
    )

    with pytest.raises(ConfigurationError) as captured:
        settings.validate_kite_authentication()

    assert expected_name in str(captured.value)
    assert "unit-api-key" not in str(captured.value)
    assert "unit-api-secret" not in str(captured.value)


@pytest.mark.parametrize(
    ("provider", "api_key", "access_token", "expected_name"),
    [
        ("OTHER", "unit-api-key", "unit-access-token", "KRONOS_PROVIDER"),
        ("KITE", "", "unit-access-token", "KRONOS_KITE_API_KEY"),
        ("KITE", "unit-api-key", "", "KRONOS_KITE_ACCESS_TOKEN"),
    ],
)
def test_kite_connectivity_validation_is_stable_and_redacted(
    provider: str,
    api_key: str,
    access_token: str,
    expected_name: str,
) -> None:
    settings = _settings(
        provider=provider,
        api_key=api_key,
        access_token=access_token,
    )

    with pytest.raises(ConfigurationError) as captured:
        settings.validate_kite_connectivity()

    assert expected_name in str(captured.value)
    assert "unit-api-key" not in str(captured.value)
    assert "unit-access-token" not in str(captured.value)


def test_loader_reads_access_token_through_configuration_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(loader, "load_dotenv", lambda: None)
    monkeypatch.setenv("KRONOS_PROVIDER", "KITE")
    monkeypatch.setenv("KRONOS_KITE_API_KEY", "unit-api-key")
    monkeypatch.setenv("KRONOS_KITE_API_SECRET", "unit-api-secret")
    monkeypatch.setenv("KRONOS_KITE_ACCESS_TOKEN", "unit-access-token")
    monkeypatch.setenv(
        "KRONOS_KITE_REDIRECT_URL",
        "http://localhost:8000/callback",
    )

    settings = loader.load_settings()

    assert settings.kite_access_token == "unit-access-token"
    settings.validate_kite_connectivity()


def _car016_settings(
    *,
    provider: str = "KITE",
    api_key: str = "unit-api-key",
    redirect_url: str = CAR016_KITE_REDIRECT_URL,
    credential_ref: str = "kite-primary",
    registration_ref: str = "sponsor-primary",
    legacy_secret: str = "",
) -> Settings:
    return Settings(
        provider=provider,
        kite_api_key=api_key,
        kite_api_secret=legacy_secret,
        kite_access_token="",
        kite_redirect_url=redirect_url,
        kite_credential_ref=credential_ref,
        kite_intended_registration_ref=registration_ref,
    )


def test_car016_configuration_uses_protected_references_not_plaintext_secret() -> None:
    settings = _car016_settings(legacy_secret="plaintext-must-not-satisfy-path")

    settings.validate_car016_provider_authentication()
    configuration = settings.provider_authentication_configuration()

    assert configuration.provider == "KITE"
    assert configuration.redirect_uri == CAR016_KITE_REDIRECT_URL
    assert configuration.credential_ref == "kite-primary"
    assert configuration.intended_registration_ref == "sponsor-primary"
    assert "plaintext-must-not-satisfy-path" not in repr(configuration)


@pytest.mark.parametrize(
    (
        "provider",
        "api_key",
        "redirect_url",
        "credential_ref",
        "registration_ref",
        "name",
    ),
    [
        (
            "OTHER",
            "unit",
            CAR016_KITE_REDIRECT_URL,
            "cred",
            "principal",
            "KRONOS_PROVIDER",
        ),
        (
            "KITE",
            "",
            CAR016_KITE_REDIRECT_URL,
            "cred",
            "principal",
            "KRONOS_KITE_API_KEY",
        ),
        (
            "KITE",
            "unit",
            "http://localhost:8765/kite/callback",
            "cred",
            "principal",
            "KRONOS_KITE_REDIRECT_URL",
        ),
        (
            "KITE",
            "unit",
            CAR016_KITE_REDIRECT_URL,
            "",
            "principal",
            "KRONOS_KITE_CREDENTIAL_REF",
        ),
        (
            "KITE",
            "unit",
            CAR016_KITE_REDIRECT_URL,
            "bad ref",
            "principal",
            "KRONOS_KITE_CREDENTIAL_REF",
        ),
        (
            "KITE",
            "unit",
            CAR016_KITE_REDIRECT_URL,
            "cred",
            "",
            "KRONOS_KITE_INTENDED_REGISTRATION_REF",
        ),
    ],
)
def test_car016_configuration_validation_is_fail_closed_and_sanitized(
    provider: str,
    api_key: str,
    redirect_url: str,
    credential_ref: str,
    registration_ref: str,
    name: str,
) -> None:
    settings = _car016_settings(
        provider=provider,
        api_key=api_key,
        redirect_url=redirect_url,
        credential_ref=credential_ref,
        registration_ref=registration_ref,
        legacy_secret="plaintext-secret",
    )

    with pytest.raises(ConfigurationError) as captured:
        settings.validate_car016_provider_authentication()

    assert name in str(captured.value)
    assert "plaintext-secret" not in str(captured.value)


def test_plaintext_secret_alone_cannot_satisfy_car016() -> None:
    settings = _car016_settings(
        credential_ref="",
        registration_ref="",
        legacy_secret="legacy-plaintext-secret",
    )

    with pytest.raises(ConfigurationError, match="KRONOS_KITE_CREDENTIAL_REF"):
        settings.validate_car016_provider_authentication()


def test_car016_loader_does_not_read_plaintext_secret_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(loader, "load_dotenv", lambda: None)
    monkeypatch.setenv("KRONOS_PROVIDER", "KITE")
    monkeypatch.setenv("KRONOS_KITE_API_KEY", "unit-api-key")
    monkeypatch.setenv("KRONOS_KITE_API_SECRET", "must-not-be-loaded")
    monkeypatch.setenv("KRONOS_KITE_CREDENTIAL_REF", "kite-primary")
    monkeypatch.setenv("KRONOS_KITE_INTENDED_REGISTRATION_REF", "sponsor-primary")
    monkeypatch.delenv("KRONOS_KITE_REDIRECT_URL", raising=False)

    configuration = loader.load_provider_authentication_configuration(
        application_config_path=tmp_path / "missing.json"
    )

    assert configuration.provider == "KITE"
    assert configuration.redirect_uri == CAR016_KITE_REDIRECT_URL
    assert configuration.credential_ref == "kite-primary"
    assert "must-not-be-loaded" not in repr(configuration)


def _application_configuration() -> dict[str, str]:
    return {
        "KRONOS_PROVIDER": "KITE",
        "KRONOS_KITE_REDIRECT_URL": CAR016_KITE_REDIRECT_URL,
        "KRONOS_KITE_CREDENTIAL_REF": "KITE-API-SECRET-PRIMARY",
        "KRONOS_KITE_INTENDED_REGISTRATION_REF": (
            "KITE-INTENDED-PRINCIPAL-PRIMARY"
        ),
        "KRONOS_PROVIDER_CONFIGURATION_REF": (
            "ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY"
        ),
        "KRONOS_KITE_APPLICATION_REGISTRATION_REF": (
            "ZERODHA-KITE-APP-REGISTRATION-PRIMARY"
        ),
    }


def _write_application_configuration(path: Path, values: object) -> None:
    path.write_text(json.dumps(values), encoding="utf-8")


class _ApiKeyLease:
    def __init__(self) -> None:
        self.closed = False

    def reveal_for_call(self, operation):  # type: ignore[no-untyped-def]
        try:
            return operation("unit-api-key")
        finally:
            self.close()

    def close(self) -> None:
        self.closed = True


class _ApiKeySource:
    def __init__(self) -> None:
        self.references: list[str] = []
        self.lease = _ApiKeyLease()

    def acquire(self, reference: str) -> _ApiKeyLease:
        self.references.append(reference)
        return self.lease


class _UnavailableApiKeySource:
    def acquire(self, _reference: str) -> _ApiKeyLease:
        raise RuntimeError("raw protected backend detail")


def test_gui_process_loads_durable_non_secret_configuration_without_environment(
    tmp_path: Path,
) -> None:
    path = tmp_path / "provider-authentication.json"
    _write_application_configuration(path, _application_configuration())
    api_key_source = _ApiKeySource()

    configuration = loader.load_provider_authentication_configuration(
        application_config_path=path,
        environment={},
        api_key_source=api_key_source,
    )

    assert configuration.provider == "KITE"
    assert configuration.redirect_uri == CAR016_KITE_REDIRECT_URL
    assert configuration.credential_ref == "KITE-API-SECRET-PRIMARY"
    assert (
        configuration.intended_registration_ref
        == "KITE-INTENDED-PRINCIPAL-PRIMARY"
    )
    assert "unit-api-key" not in repr(configuration)
    assert api_key_source.references == [
        "ZERODHA-KITE-APP-REGISTRATION-PRIMARY"
    ]
    assert api_key_source.lease.closed is True


def test_application_configuration_location_is_independent_of_working_directory(
    tmp_path: Path,
) -> None:
    path = loader.provider_authentication_application_config_path(home=tmp_path)

    assert path == (
        tmp_path
        / "Library"
        / "Application Support"
        / "Project-KRONOS"
        / "provider-authentication.json"
    )


def test_provisioner_atomically_writes_only_approved_non_secret_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "app" / "provider-authentication.json"

    written = loader.provision_provider_authentication_application_config(
        path=path
    )
    values = json.loads(path.read_text(encoding="utf-8"))

    assert written == path
    assert values == _application_configuration()
    assert path.stat().st_mode & 0o777 == 0o600
    assert not any(
        name in values
        for name in (
            "KRONOS_KITE_API_KEY",
            "KRONOS_KITE_API_SECRET",
            "KRONOS_KITE_ACCESS_TOKEN",
            "KRONOS_KITE_REQUEST_TOKEN",
            "KRONOS_KITE_CALLBACK_TOKEN",
        )
    )
    assert loader.provider_authentication_application_config_ready(path=path)


def test_durable_application_configuration_does_not_accept_ambient_override(
    tmp_path: Path,
) -> None:
    path = tmp_path / "provider-authentication.json"
    _write_application_configuration(path, _application_configuration())
    api_key_source = _ApiKeySource()

    configuration = loader.load_provider_authentication_configuration(
        application_config_path=path,
        environment={
            "KRONOS_PROVIDER": "OTHER",
            "KRONOS_KITE_API_KEY": "ambient-key-must-not-be-used",
        },
        api_key_source=api_key_source,
    )

    assert configuration.provider == "KITE"
    assert api_key_source.references == [
        "ZERODHA-KITE-APP-REGISTRATION-PRIMARY"
    ]
    assert "ambient-key-must-not-be-used" not in repr(configuration)


@pytest.mark.parametrize(
    "protected_key",
    [
        "KRONOS_KITE_API_KEY",
        "KRONOS_KITE_API_SECRET",
        "KRONOS_KITE_ACCESS_TOKEN",
        "KRONOS_KITE_REQUEST_TOKEN",
        "KRONOS_KITE_CALLBACK_TOKEN",
    ],
)
def test_protected_material_is_rejected_from_application_configuration(
    tmp_path: Path,
    protected_key: str,
) -> None:
    path = tmp_path / "provider-authentication.json"
    values = _application_configuration()
    values[protected_key] = "must-not-be-persisted"
    _write_application_configuration(path, values)

    with pytest.raises(
        ConfigurationError,
        match="PROVIDER_AUTHENTICATION_PROTECTED_CONFIGURATION_PROHIBITED",
    ) as captured:
        loader.load_provider_authentication_configuration(
            application_config_path=path,
            environment={},
        )

    assert "must-not-be-persisted" not in str(captured.value)


@pytest.mark.parametrize(
    "values",
    [
        {"KRONOS_PROVIDER": "KITE"},
        [],
        "not-a-record",
    ],
)
def test_incomplete_or_invalid_application_configuration_fails_sanitized(
    tmp_path: Path,
    values: object,
) -> None:
    path = tmp_path / "provider-authentication.json"
    _write_application_configuration(path, values)

    with pytest.raises(
        ConfigurationError,
        match="PROVIDER_AUTHENTICATION_APPLICATION_CONFIGURATION_INVALID",
    ):
        loader.load_provider_authentication_configuration(
            application_config_path=path,
            environment={},
        )


def test_missing_application_configuration_fails_sanitized(tmp_path: Path) -> None:
    with pytest.raises(
        ConfigurationError,
        match="PROVIDER_AUTHENTICATION_APPLICATION_CONFIGURATION_UNAVAILABLE",
    ):
        loader.load_provider_authentication_configuration(
            application_config_path=tmp_path / "missing.json",
            environment={},
        )


def test_unavailable_api_key_source_fails_with_sanitized_configuration_code(
    tmp_path: Path,
) -> None:
    path = tmp_path / "provider-authentication.json"
    _write_application_configuration(path, _application_configuration())

    with pytest.raises(
        ConfigurationError,
        match="PROVIDER_AUTHENTICATION_API_KEY_UNAVAILABLE",
    ) as captured:
        loader.load_provider_authentication_configuration(
            application_config_path=path,
            environment={},
            api_key_source=_UnavailableApiKeySource(),
        )

    assert "raw protected backend detail" not in str(captured.value)


def test_legacy_loader_behavior_remains_available_outside_car016(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(loader, "load_dotenv", lambda: None)
    monkeypatch.setenv("KRONOS_PROVIDER", "KITE")
    monkeypatch.setenv("KRONOS_KITE_API_KEY", "unit-api-key")
    monkeypatch.setenv("KRONOS_KITE_API_SECRET", "legacy-secret")
    monkeypatch.setenv("KRONOS_KITE_REDIRECT_URL", "http://localhost:8000/callback")

    settings = loader.load_settings()

    assert settings.kite_api_secret == "legacy-secret"
    settings.validate_kite_authentication()


def test_governed_loader_bypasses_dotenv_and_binds_exact_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dotenv_calls = 0

    def forbidden_dotenv() -> None:
        nonlocal dotenv_calls
        dotenv_calls += 1

    monkeypatch.setattr(loader, "load_dotenv", forbidden_dotenv)
    environment = {
        "KRONOS_PROVIDER": "KITE",
        "KRONOS_KITE_API_KEY": "unit-api-key",
        "KRONOS_KITE_REDIRECT_URL": CAR016_KITE_REDIRECT_URL,
        "KRONOS_KITE_CREDENTIAL_REF": "KITE-API-SECRET-PRIMARY",
        "KRONOS_KITE_INTENDED_REGISTRATION_REF": (
            "KITE-INTENDED-PRINCIPAL-PRIMARY"
        ),
        "KRONOS_PROVIDER_CONFIGURATION_REF": (
            "ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY"
        ),
        "KRONOS_KITE_APPLICATION_REGISTRATION_REF": (
            "ZERODHA-KITE-APP-REGISTRATION-PRIMARY"
        ),
        "KRONOS_KITE_API_SECRET": "must-not-be-read",
        "KRONOS_KITE_ACCESS_TOKEN": "must-not-be-read",
    }

    governed = loader.load_governed_provider_authentication_configuration(
        environment
    )

    assert dotenv_calls == 0
    assert governed.provider_identity == "ZERODHA_KITE"
    assert governed.authentication.provider == "KITE"
    assert (
        governed.provider_configuration_ref
        == "ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY"
    )
    assert (
        governed.application_registration_ref
        == "ZERODHA-KITE-APP-REGISTRATION-PRIMARY"
    )
    assert "must-not-be-read" not in repr(governed)


@pytest.mark.parametrize(
    "field",
    [
        "KRONOS_PROVIDER_CONFIGURATION_REF",
        "KRONOS_KITE_APPLICATION_REGISTRATION_REF",
    ],
)
def test_governed_loader_fails_closed_on_identity_mismatch(field: str) -> None:
    environment = {
        "KRONOS_PROVIDER": "KITE",
        "KRONOS_KITE_API_KEY": "unit-api-key",
        "KRONOS_KITE_REDIRECT_URL": CAR016_KITE_REDIRECT_URL,
        "KRONOS_KITE_CREDENTIAL_REF": "KITE-API-SECRET-PRIMARY",
        "KRONOS_KITE_INTENDED_REGISTRATION_REF": (
            "KITE-INTENDED-PRINCIPAL-PRIMARY"
        ),
        "KRONOS_PROVIDER_CONFIGURATION_REF": (
            "ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY"
        ),
        "KRONOS_KITE_APPLICATION_REGISTRATION_REF": (
            "ZERODHA-KITE-APP-REGISTRATION-PRIMARY"
        ),
    }
    environment[field] = "WRONG"

    with pytest.raises(ConfigurationError):
        loader.load_governed_provider_authentication_configuration(environment)
