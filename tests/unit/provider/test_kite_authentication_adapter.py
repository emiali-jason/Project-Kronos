from collections.abc import Mapping

import pytest

from kronos.provider.adapters.kite import authentication as adapter_module
from kronos.provider.adapters.kite import client as client_module
from kronos.provider.adapters.kite.authentication import (
    KiteContextEvidence,
    create_kite_authentication_adapter,
)
from kronos.provider.exceptions.connectivity import (
    ProviderConnectivityError,
    ProviderErrorCode,
)


_API_KEY = "adapter-api-key"
_API_SECRET = "adapter-api-secret"
_REQUEST_TOKEN = "adapter-request-token"
_ACCESS_TOKEN = "adapter-access-token"


class _FakeKiteClient:
    instances: list["_FakeKiteClient"] = []
    exchange_effect: object = {
        "access_token": _ACCESS_TOKEN,
        "exchanges": ["OUTSIDE_EDD001"],
        "products": ["OUTSIDE_EDD001"],
        "order_types": ["OUTSIDE_EDD001"],
    }
    profile_effect: object = {"user_id": "discarded"}
    termination_effect: object = True

    def __init__(self, **arguments: object) -> None:
        self.arguments = arguments
        self.request_token: str | None = None
        self.api_secret: str | None = None
        self.invalidate_count = 0
        self.session_expiry_hook: object = None
        type(self).instances.append(self)

    def set_session_expiry_hook(self, hook: object) -> None:
        self.session_expiry_hook = hook

    def login_url(self) -> str:
        return "https://kite.zerodha.com/connect/login?v=3&api_key=redacted"

    def generate_session(
        self,
        request_token: str,
        api_secret: str,
    ) -> object:
        self.request_token = request_token
        self.api_secret = api_secret
        effect = type(self).exchange_effect
        if isinstance(effect, BaseException):
            raise effect
        if isinstance(effect, Mapping):
            access_token = effect.get("access_token")
            if isinstance(access_token, str):
                self.access_token = access_token
        return effect

    def profile(self) -> object:
        effect = type(self).profile_effect
        if isinstance(effect, BaseException):
            raise effect
        return effect

    def invalidate_access_token(self) -> object:
        self.invalidate_count += 1
        effect = type(self).termination_effect
        if isinstance(effect, BaseException):
            raise effect
        return effect

    def expire_session(self) -> None:
        assert callable(self.session_expiry_hook)
        self.session_expiry_hook()


@pytest.fixture(autouse=True)
def _fake_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeKiteClient.instances = []
    _FakeKiteClient.exchange_effect = {
        "access_token": _ACCESS_TOKEN,
        "exchanges": ["OUTSIDE_EDD001"],
        "products": ["OUTSIDE_EDD001"],
        "order_types": ["OUTSIDE_EDD001"],
    }
    _FakeKiteClient.profile_effect = {"user_id": "discarded"}
    _FakeKiteClient.termination_effect = True
    monkeypatch.setattr(client_module, "_KiteConnect", _FakeKiteClient)


def test_adapter_executes_only_login_exchange_validation_and_logout() -> None:
    adapter = create_kite_authentication_adapter(_API_KEY, _API_SECRET)

    login_url = adapter.login_url()
    adapter.exchange(_REQUEST_TOKEN)
    evidence = adapter.context_evidence()
    adapter.terminate()

    client = _FakeKiteClient.instances[0]
    assert client.arguments == {"api_key": _API_KEY, "debug": False}
    assert login_url.startswith("https://kite.zerodha.com/connect/login")
    assert client.request_token == _REQUEST_TOKEN
    assert client.api_secret == _API_SECRET
    assert evidence is KiteContextEvidence.VALID
    assert client.invalidate_count == 1
    assert "OUTSIDE_EDD001" not in repr(adapter)
    assert _ACCESS_TOKEN not in repr(adapter)


def test_incomplete_exchange_never_verifies_authentication() -> None:
    _FakeKiteClient.exchange_effect = {"user_id": "no-access-token"}
    adapter = create_kite_authentication_adapter(_API_KEY, _API_SECRET)

    with pytest.raises(ProviderConnectivityError) as captured:
        adapter.exchange(_REQUEST_TOKEN)

    assert captured.value.code is ProviderErrorCode.UNEXPECTED_RESPONSE
    assert _API_SECRET not in str(captured.value)
    assert _REQUEST_TOKEN not in str(captured.value)
    assert _ACCESS_TOKEN not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_invalid_token_is_context_invalidation_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTokenError(Exception):
        pass

    monkeypatch.setattr(adapter_module, "_TokenException", FakeTokenError)
    adapter = create_kite_authentication_adapter(_API_KEY, _API_SECRET)
    adapter.exchange(_REQUEST_TOKEN)
    _FakeKiteClient.profile_effect = FakeTokenError(_ACCESS_TOKEN)

    assert adapter.context_evidence() is KiteContextEvidence.INVALID


def test_official_session_expiry_hook_is_context_invalidation_evidence() -> None:
    adapter = create_kite_authentication_adapter(_API_KEY, _API_SECRET)
    adapter.exchange(_REQUEST_TOKEN)
    _FakeKiteClient.instances[0].expire_session()

    assert adapter.context_evidence() is KiteContextEvidence.INVALID


def test_transport_failure_is_operational_unavailability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeConnectionError(Exception):
        pass

    monkeypatch.setattr(
        adapter_module,
        "_RequestsConnectionError",
        FakeConnectionError,
    )
    adapter = create_kite_authentication_adapter(_API_KEY, _API_SECRET)
    adapter.exchange(_REQUEST_TOKEN)
    _FakeKiteClient.profile_effect = FakeConnectionError(_ACCESS_TOKEN)

    assert adapter.context_evidence() is KiteContextEvidence.UNAVAILABLE


def test_sdk_failure_is_redacted() -> None:
    _FakeKiteClient.exchange_effect = RuntimeError(
        f"{_API_SECRET}:{_REQUEST_TOKEN}:{_ACCESS_TOKEN}"
    )
    adapter = create_kite_authentication_adapter(_API_KEY, _API_SECRET)

    with pytest.raises(ProviderConnectivityError) as captured:
        adapter.exchange(_REQUEST_TOKEN)

    rendered = str(captured.value)
    assert _API_SECRET not in rendered
    assert _REQUEST_TOKEN not in rendered
    assert _ACCESS_TOKEN not in rendered
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
