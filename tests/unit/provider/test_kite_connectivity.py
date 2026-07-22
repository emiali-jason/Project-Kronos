import logging
from collections.abc import Callable

import pytest

from kronos.configuration.settings import Settings
from kronos.provider.adapters.kite import client as client_module
from kronos.provider.adapters.kite import connectivity as adapter_module
from kronos.provider.adapters.kite.connectivity import (
    KiteConnectivityAdapter,
    create_kite_connectivity_adapter,
)
from kronos.provider.exceptions.connectivity import (
    ProviderConnectivityError,
    ProviderErrorCode,
)
from kronos.provider.models.availability import ProviderAvailabilityState
from kronos.provider.services.connectivity import KiteConnectivityService


class _FakeSession:
    def __init__(self) -> None:
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


class _FakeKiteClient:
    instances: list["_FakeKiteClient"] = []
    profile_effect: object = {"sensitive": "discard-me"}

    def __init__(self, **arguments: object) -> None:
        self.arguments = arguments
        self.reqsession = _FakeSession()
        self.profile_count = 0
        type(self).instances.append(self)

    def profile(self) -> object:
        self.profile_count += 1
        effect = type(self).profile_effect
        if isinstance(effect, BaseException):
            raise effect
        return effect


class _FakeAdapter:
    def __init__(
        self,
        error: ProviderConnectivityError | None = None,
        close_error: ProviderConnectivityError | None = None,
    ) -> None:
        self.error = error
        self.close_error = close_error
        self.probe_count = 0
        self.close_count = 0

    def probe(self) -> None:
        self.probe_count += 1
        if self.error is not None:
            raise self.error

    def close(self) -> None:
        self.close_count += 1
        if self.close_error is not None:
            raise self.close_error


def _settings(
    *,
    api_key: str = "unit-api-key",
    access_token: str = "unit-access-token",
) -> Settings:
    return Settings(
        provider="KITE",
        kite_api_key=api_key,
        kite_api_secret="unit-api-secret",
        kite_access_token=access_token,
        kite_redirect_url="http://localhost:8000/callback",
    )


@pytest.fixture(autouse=True)
def _reset_fake_client() -> None:
    _FakeKiteClient.instances = []
    _FakeKiteClient.profile_effect = {"sensitive": "discard-me"}


def _install_fake_sdk_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "_KiteConnect", _FakeKiteClient)


def test_factory_uses_locked_sdk_default_and_profile_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_sdk_client(monkeypatch)

    adapter = create_kite_connectivity_adapter(
        "unit-api-key",
        "unit-access-token",
    )
    result = adapter.probe()

    client = _FakeKiteClient.instances[0]
    assert client.arguments == {
        "api_key": "unit-api-key",
        "access_token": "unit-access-token",
        "debug": False,
    }
    assert "timeout" not in client.arguments
    assert client.profile_count == 1
    assert result is None


def test_sdk_session_cleanup_is_isolated_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_sdk_client(monkeypatch)
    adapter = create_kite_connectivity_adapter(
        "unit-api-key",
        "unit-access-token",
    )
    session = _FakeKiteClient.instances[0].reqsession

    adapter.close()
    adapter.close()

    assert session.close_count == 1


def test_sdk_session_cleanup_failure_is_redacted_and_remains_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_sdk_client(monkeypatch)
    adapter = create_kite_connectivity_adapter(
        "unit-api-key",
        "unit-access-token",
    )
    session = _FakeKiteClient.instances[0].reqsession

    def fail_close() -> None:
        raise RuntimeError("unit-access-token")

    monkeypatch.setattr(session, "close", fail_close)

    with pytest.raises(ProviderConnectivityError) as captured:
        adapter.close()

    assert captured.value.code is ProviderErrorCode.SHUTDOWN_FAILURE
    assert "unit-access-token" not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    adapter.close()


def test_sdk_constructor_failure_does_not_escape_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingKiteClient:
        def __init__(self, **_arguments: object) -> None:
            raise RuntimeError("unit-access-token")

    monkeypatch.setattr(client_module, "_KiteConnect", FailingKiteClient)

    with pytest.raises(ProviderConnectivityError) as captured:
        create_kite_connectivity_adapter(
            "unit-api-key",
            "unit-access-token",
        )

    assert captured.value.code is ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
    assert "unit-access-token" not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


class _FakeTokenError(Exception):
    pass


class _FakePermissionError(Exception):
    pass


class _FakeTimeoutError(Exception):
    pass


class _FakeConnectionError(Exception):
    pass


class _FakeDataError(Exception):
    pass


class _FakeKiteError(Exception):
    def __init__(self, code: int) -> None:
        self.code = code


@pytest.mark.parametrize(
    ("alias", "exception_factory", "expected"),
    [
        (
            "_TokenException",
            lambda: _FakeTokenError("unit-access-token"),
            ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED,
        ),
        (
            "_PermissionException",
            lambda: _FakePermissionError("unit-access-token"),
            ProviderErrorCode.AUTHENTICATION_REJECTED,
        ),
        (
            "_RequestsTimeout",
            lambda: _FakeTimeoutError("unit-access-token"),
            ProviderErrorCode.NETWORK_TIMEOUT,
        ),
        (
            "_RequestsConnectionError",
            lambda: _FakeConnectionError("unit-access-token"),
            ProviderErrorCode.CONNECTION_FAILURE,
        ),
        (
            "_DataException",
            lambda: _FakeDataError("unit-access-token"),
            ProviderErrorCode.UNEXPECTED_RESPONSE,
        ),
        (
            "_KiteException",
            lambda: _FakeKiteError(429),
            ProviderErrorCode.RATE_LIMITED,
        ),
        (
            "_KiteException",
            lambda: _FakeKiteError(503),
            ProviderErrorCode.PROVIDER_SERVICE_FAILURE,
        ),
    ],
)
def test_adapter_maps_sdk_failures_without_exposing_text(
    monkeypatch: pytest.MonkeyPatch,
    alias: str,
    exception_factory: Callable[[], Exception],
    expected: ProviderErrorCode,
) -> None:
    _install_fake_sdk_client(monkeypatch)
    fake_exception_type = type(exception_factory())
    monkeypatch.setattr(adapter_module, alias, fake_exception_type)
    _FakeKiteClient.profile_effect = exception_factory()
    adapter = create_kite_connectivity_adapter(
        "unit-api-key",
        "unit-access-token",
    )

    with pytest.raises(ProviderConnectivityError) as captured:
        adapter.probe()

    assert captured.value.code is expected
    assert "unit-access-token" not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_unexpected_profile_shape_is_rejected_and_discarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_sdk_client(monkeypatch)
    _FakeKiteClient.profile_effect = ["not", "a", "mapping"]
    adapter = create_kite_connectivity_adapter(
        "unit-api-key",
        "unit-access-token",
    )

    with pytest.raises(ProviderConnectivityError) as captured:
        adapter.probe()

    assert captured.value.code is ProviderErrorCode.UNEXPECTED_RESPONSE


def test_service_performs_one_attempt_and_discards_profile(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_adapter = _FakeAdapter()
    service = KiteConnectivityService(
        _settings(),
        adapter_factory=lambda _api_key, _access_token: fake_adapter,
    )

    with caplog.at_level(logging.INFO):
        result = service.probe()

    assert result.state is ProviderAvailabilityState.AVAILABLE
    assert result.error_code is None
    assert fake_adapter.probe_count == 1
    assert "unit-api-key" not in caplog.text
    assert "unit-api-secret" not in caplog.text
    assert "unit-access-token" not in caplog.text


def test_service_rejects_invalid_configuration_without_factory_call() -> None:
    factory_called = False

    def factory(_api_key: str, _access_token: str) -> KiteConnectivityAdapter:
        nonlocal factory_called
        factory_called = True
        raise AssertionError

    service = KiteConnectivityService(
        _settings(access_token=""),
        adapter_factory=factory,
    )

    result = service.probe()

    assert result.state is ProviderAvailabilityState.CONFIGURATION_INVALID
    assert result.error_code is ProviderErrorCode.CONFIGURATION_INVALID
    assert factory_called is False


@pytest.mark.parametrize(
    ("error_code", "expected_state"),
    [
        (
            ProviderErrorCode.AUTHENTICATION_REJECTED,
            ProviderAvailabilityState.AUTHENTICATION_REJECTED,
        ),
        (
            ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED,
            ProviderAvailabilityState.AUTHENTICATION_REJECTED,
        ),
        (
            ProviderErrorCode.NETWORK_TIMEOUT,
            ProviderAvailabilityState.TEMPORARILY_UNAVAILABLE,
        ),
        (
            ProviderErrorCode.RATE_LIMITED,
            ProviderAvailabilityState.TEMPORARILY_UNAVAILABLE,
        ),
        (
            ProviderErrorCode.INTERNAL_ADAPTER_DEFECT,
            ProviderAvailabilityState.TEMPORARILY_UNAVAILABLE,
        ),
    ],
)
def test_service_maps_errors_to_five_state_model(
    error_code: ProviderErrorCode,
    expected_state: ProviderAvailabilityState,
) -> None:
    fake_adapter = _FakeAdapter(ProviderConnectivityError(error_code))
    service = KiteConnectivityService(
        _settings(),
        adapter_factory=lambda _api_key, _access_token: fake_adapter,
    )

    result = service.probe()

    assert result.state is expected_state
    assert result.error_code is error_code
    assert fake_adapter.probe_count == 1


def test_service_shutdown_is_idempotent() -> None:
    fake_adapter = _FakeAdapter()
    service = KiteConnectivityService(
        _settings(),
        adapter_factory=lambda _api_key, _access_token: fake_adapter,
    )
    service.probe()

    first = service.shutdown()
    second = service.shutdown()

    assert first.state is ProviderAvailabilityState.NOT_INITIALIZED
    assert second.state is ProviderAvailabilityState.NOT_INITIALIZED
    assert fake_adapter.close_count == 1


def test_cleanup_failure_is_separate_from_primary_probe_result() -> None:
    fake_adapter = _FakeAdapter(
        close_error=ProviderConnectivityError(ProviderErrorCode.SHUTDOWN_FAILURE),
    )
    service = KiteConnectivityService(
        _settings(),
        adapter_factory=lambda _api_key, _access_token: fake_adapter,
    )

    probe_result = service.probe()
    shutdown_result = service.shutdown()

    assert probe_result.state is ProviderAvailabilityState.AVAILABLE
    assert probe_result.error_code is None
    assert shutdown_result.state is ProviderAvailabilityState.NOT_INITIALIZED
    assert shutdown_result.error_code is ProviderErrorCode.SHUTDOWN_FAILURE
    assert fake_adapter.probe_count == 1
    assert fake_adapter.close_count == 1
