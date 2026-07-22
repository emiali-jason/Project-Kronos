from dataclasses import FrozenInstanceError

import pytest

from kronos.configuration import loader
from kronos.configuration.exceptions import ConfigurationError
from kronos.configuration.settings import Settings


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
