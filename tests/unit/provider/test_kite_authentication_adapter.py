from __future__ import annotations

from collections.abc import Callable, Mapping
import gc
import pickle

import pytest

from kronos.configuration.credentials import OneUseSecretLease, SecretLeaseError
from kronos.configuration.principals import PrincipalBindingResult
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
from kronos.provider.kite.composition import OperationLedgerRecorder
from kronos.provider.kite.live_activation import RemainingBudget
from kronos.provider.models.authentication import GovernedAuthenticationOperation


_API_KEY = "adapter-api-key"
_API_SECRET = "adapter-api-secret"
_REQUEST_TOKEN = "adapter-request-token"
_ACCESS_TOKEN = "adapter-access-token"
_PRINCIPAL = "KRONOS123"


class _FakeSession:
    def __init__(self, close_effect: BaseException | None = None) -> None:
        self.close_count = 0
        self.close_effect = close_effect

    def close(self) -> None:
        self.close_count += 1
        if self.close_effect is not None:
            raise self.close_effect


class _FakeKiteClient:
    instances: list["_FakeKiteClient"] = []
    exchange_effect: object = {"access_token": _ACCESS_TOKEN}
    profile_effects: list[object] = [{"user_id": _PRINCIPAL}]
    close_effect: BaseException | None = None

    def __init__(self, **arguments: object) -> None:
        self.arguments = arguments
        self.reqsession = _FakeSession(type(self).close_effect)
        self.exchange_count = 0
        self.profile_count = 0
        self.invalidate_count = 0
        self.login_count = 0
        self.request_token_matched = False
        self.api_secret_matched = False
        self.session_expiry_hook: Callable[[], None] | None = None
        type(self).instances.append(self)

    def set_session_expiry_hook(self, hook: Callable[[], None]) -> None:
        self.session_expiry_hook = hook

    def login_url(self) -> str:
        self.login_count += 1
        return "https://kite.zerodha.com/connect/login?v=3&api_key=redacted"

    def generate_session(
        self,
        request_token: str,
        api_secret: str,
    ) -> object:
        self.exchange_count += 1
        self.request_token_matched = request_token == _REQUEST_TOKEN
        self.api_secret_matched = api_secret == _API_SECRET
        effect = type(self).exchange_effect
        type(self).exchange_effect = None
        if isinstance(effect, BaseException):
            raise effect
        return effect

    def profile(self) -> object:
        self.profile_count += 1
        effects = type(self).profile_effects
        effect = effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect

    def invalidate_access_token(self) -> object:
        self.invalidate_count += 1
        raise AssertionError("remote invalidation is prohibited")

    def expire_session(self) -> None:
        assert self.session_expiry_hook is not None
        self.session_expiry_hook()


class _FakeRequestToken:
    __slots__ = ("_token", "closed", "use_count")

    def __init__(self, token: str = _REQUEST_TOKEN) -> None:
        self._token: str | None = token
        self.use_count = 0
        self.closed = False

    def consume_for_call(self, operation: Callable[[str], object]) -> object:
        if self.closed or self._token is None:
            raise RuntimeError("REQUEST_TOKEN_UNAVAILABLE")
        self.use_count += 1
        token = self._token
        try:
            return operation(token)
        finally:
            self._token = None
            self.closed = True

    def close(self) -> None:
        self._token = None
        self.closed = True

    def __repr__(self) -> str:
        return "<_FakeRequestToken redacted>"


@pytest.fixture(autouse=True)
def _fake_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeKiteClient.instances = []
    _FakeKiteClient.exchange_effect = {
        "access_token": _ACCESS_TOKEN,
        "exchanges": ["OUTSIDE_EDD001"],
        "products": ["OUTSIDE_EDD001"],
        "order_types": ["OUTSIDE_EDD001"],
    }
    _FakeKiteClient.profile_effects = [{"user_id": _PRINCIPAL}]
    _FakeKiteClient.close_effect = None
    monkeypatch.setattr(client_module, "_KiteConnect", _FakeKiteClient)


def _candidate():  # type: ignore[no-untyped-def]
    adapter = create_kite_authentication_adapter(_API_KEY)
    token = _FakeRequestToken()
    secret = OneUseSecretLease(_API_SECRET)
    candidate = adapter.exchange_once(token, secret)
    return adapter, candidate, token, secret, _FakeKiteClient.instances[0]


def test_exchange_once_produces_only_one_opaque_unpublished_candidate() -> None:
    adapter, candidate, token, secret, client = _candidate()

    assert client.arguments == {"api_key": _API_KEY, "debug": False}
    assert client.exchange_count == 1
    assert client.profile_count == 0
    assert client.invalidate_count == 0
    assert client.request_token_matched is True
    assert client.api_secret_matched is True
    assert token.use_count == 1
    assert token.closed is True
    assert secret.used is True
    assert secret.closed is True
    assert repr(candidate) == "<_KiteCandidateContext redacted>"
    assert repr(adapter) == "<KiteAuthenticationAdapter redacted>"
    rendered = repr(candidate) + repr(adapter)
    assert _API_SECRET not in rendered
    assert _REQUEST_TOKEN not in rendered
    assert _ACCESS_TOKEN not in rendered
    assert _PRINCIPAL not in rendered
    for prohibited in ("access_token", "sdk", "client", "candidate"):
        assert not hasattr(candidate, prohibited)
    with pytest.raises(TypeError):
        pickle.dumps(candidate)


def test_exchange_failure_cannot_be_retried_on_the_same_adapter() -> None:
    _FakeKiteClient.exchange_effect = RuntimeError("raw first failure")
    adapter = create_kite_authentication_adapter(_API_KEY)

    with pytest.raises(ProviderConnectivityError):
        adapter.exchange_once(_FakeRequestToken(), OneUseSecretLease(_API_SECRET))
    with pytest.raises(ProviderConnectivityError) as second:
        adapter.exchange_once(_FakeRequestToken(), OneUseSecretLease(_API_SECRET))

    client = _FakeKiteClient.instances[0]
    assert client.exchange_count == 1
    assert second.value.code is ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
    assert "raw first failure" not in str(second.value)


@pytest.mark.parametrize(
    ("exception_name", "expected_code"),
    [
        ("_TokenException", ProviderErrorCode.ACCESS_TOKEN_INVALID_OR_EXPIRED),
        ("_PermissionException", ProviderErrorCode.AUTHENTICATION_REJECTED),
        ("_RequestsTimeout", ProviderErrorCode.NETWORK_TIMEOUT),
        ("_RequestsConnectionError", ProviderErrorCode.CONNECTION_FAILURE),
        ("_NetworkException", ProviderErrorCode.PROVIDER_SERVICE_FAILURE),
        ("_KiteException", ProviderErrorCode.PROVIDER_SERVICE_FAILURE),
    ],
)
def test_sdk_exchange_exception_categories_are_sanitized(
    exception_name: str,
    expected_code: ProviderErrorCode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSdkError(Exception):
        code = 503

    monkeypatch.setattr(adapter_module, exception_name, FakeSdkError)
    _FakeKiteClient.exchange_effect = FakeSdkError("raw sdk material")
    adapter = create_kite_authentication_adapter(_API_KEY)

    with pytest.raises(ProviderConnectivityError) as captured:
        adapter.exchange_once(_FakeRequestToken(), OneUseSecretLease(_API_SECRET))

    assert captured.value.code is expected_code
    assert "raw sdk material" not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert _FakeKiteClient.instances[0].exchange_count == 1


def test_rate_limit_sdk_exception_is_distinct_and_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeNetworkError(Exception):
        code = 429

    monkeypatch.setattr(adapter_module, "_NetworkException", FakeNetworkError)
    _FakeKiteClient.exchange_effect = FakeNetworkError("raw rate detail")
    adapter = create_kite_authentication_adapter(_API_KEY)

    with pytest.raises(ProviderConnectivityError) as captured:
        adapter.exchange_once(_FakeRequestToken(), OneUseSecretLease(_API_SECRET))

    assert captured.value.code is ProviderErrorCode.RATE_LIMITED
    assert _FakeKiteClient.instances[0].exchange_count == 1


@pytest.mark.parametrize("response", [None, {}, {"access_token": ""}, []])
def test_malformed_exchange_payload_is_rejected_and_not_retained(
    response: object,
) -> None:
    _FakeKiteClient.exchange_effect = response
    adapter = create_kite_authentication_adapter(_API_KEY)

    with pytest.raises(ProviderConnectivityError) as captured:
        adapter.exchange_once(_FakeRequestToken(), OneUseSecretLease(_API_SECRET))

    assert captured.value.code is ProviderErrorCode.UNEXPECTED_RESPONSE
    assert _FakeKiteClient.exchange_effect is None
    assert _FakeKiteClient.instances[0].exchange_count == 1


@pytest.mark.parametrize(
    ("provider_principal", "expected_principal", "outcome"),
    [
        (_PRINCIPAL, _PRINCIPAL, PrincipalBindingResult.MATCHED),
        (_PRINCIPAL, "KRONOS456", PrincipalBindingResult.MISMATCHED),
        (None, _PRINCIPAL, PrincipalBindingResult.UNCONFIRMED),
        (" lower", "lower", PrincipalBindingResult.UNCONFIRMED),
        ("lower ", "lower", PrincipalBindingResult.UNCONFIRMED),
        ("with-hyphen", "with-hyphen", PrincipalBindingResult.UNCONFIRMED),
        ("MixedCase1", "mixedcase1", PrincipalBindingResult.MISMATCHED),
        (_PRINCIPAL, "invalid expected", PrincipalBindingResult.UNCONFIRMED),
    ],
)
def test_principal_evidence_uses_exact_canonical_case_sensitive_comparison(
    provider_principal: object,
    expected_principal: str,
    outcome: PrincipalBindingResult,
) -> None:
    _FakeKiteClient.profile_effects = [{"user_id": provider_principal}]
    _, candidate, _, _, client = _candidate()

    evidence = candidate.principal_evidence()
    result = evidence.compare_expected(expected_principal)

    assert result is outcome
    assert client.profile_count == 1
    assert client.invalidate_count == 0
    assert _FakeKiteClient.profile_effects == []
    if provider_principal is not None:
        assert provider_principal not in gc.get_referents(evidence)
        assert provider_principal not in gc.get_referents(candidate)
    with pytest.raises(RuntimeError, match="PRINCIPAL_EVIDENCE_UNAVAILABLE"):
        evidence.compare_expected(expected_principal)


@pytest.mark.parametrize("profile", [None, [], "raw", {"other": "field"}])
def test_malformed_profile_produces_unconfirmed_minimum_evidence(
    profile: object,
) -> None:
    _FakeKiteClient.profile_effects = [profile]
    _, candidate, _, _, client = _candidate()

    evidence = candidate.principal_evidence()

    assert (
        evidence.compare_expected(_PRINCIPAL)
        is PrincipalBindingResult.UNCONFIRMED
    )
    assert client.profile_count == 1


def test_principal_transport_failure_is_unavailable_not_availability_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeConnectionError(Exception):
        pass

    monkeypatch.setattr(
        adapter_module,
        "_RequestsConnectionError",
        FakeConnectionError,
    )
    _FakeKiteClient.profile_effects = [FakeConnectionError("raw principal failure")]
    _, candidate, _, _, client = _candidate()

    evidence = candidate.principal_evidence()

    assert evidence.compare_expected(_PRINCIPAL) is PrincipalBindingResult.UNAVAILABLE
    assert client.profile_count == 1
    assert "raw principal failure" not in repr(evidence)


def test_principal_and_availability_profile_operations_are_separate() -> None:
    _FakeKiteClient.profile_effects = [
        {"user_id": _PRINCIPAL, "raw": "discarded-principal-payload"},
        {"raw": "discarded-availability-payload"},
    ]
    _, candidate, _, _, client = _candidate()

    evidence = candidate.principal_evidence()
    binding = evidence.compare_expected(_PRINCIPAL)

    assert binding is PrincipalBindingResult.MATCHED
    assert client.profile_count == 1

    availability = candidate.verify_provider_availability()

    assert availability is KiteContextEvidence.VALID
    assert client.profile_count == 2
    assert client.exchange_count == 1
    assert client.invalidate_count == 0
    rendered = repr(candidate) + repr(evidence)
    assert "discarded-principal-payload" not in rendered
    assert "discarded-availability-payload" not in rendered


@pytest.mark.parametrize(
    ("effect", "expected"),
    [
        ({"user_id": "ignored"}, KiteContextEvidence.VALID),
        (None, None),
    ],
)
def test_availability_mapping_is_explicit_and_sanitized(
    effect: object,
    expected: KiteContextEvidence | None,
) -> None:
    _FakeKiteClient.profile_effects = [effect]
    _, candidate, _, _, client = _candidate()

    if expected is None:
        with pytest.raises(ProviderConnectivityError) as captured:
            candidate.verify_provider_availability()
        assert captured.value.code is ProviderErrorCode.UNEXPECTED_RESPONSE
    else:
        assert candidate.verify_provider_availability() is expected

    assert client.profile_count == 1


def test_invalid_token_is_distinct_availability_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTokenError(Exception):
        pass

    monkeypatch.setattr(adapter_module, "_TokenException", FakeTokenError)
    _FakeKiteClient.profile_effects = [FakeTokenError("raw token detail")]
    _, candidate, _, _, client = _candidate()

    assert candidate.verify_provider_availability() is KiteContextEvidence.INVALID
    assert client.profile_count == 1


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
    _FakeKiteClient.profile_effects = [FakeConnectionError("raw transport detail")]
    _, candidate, _, _, client = _candidate()

    assert (
        candidate.verify_provider_availability()
        is KiteContextEvidence.UNAVAILABLE
    )
    assert client.profile_count == 1


def test_official_session_expiry_hook_invalidates_candidate_locally() -> None:
    _, candidate, _, _, client = _candidate()
    client.expire_session()

    assert candidate.verify_provider_availability() is KiteContextEvidence.INVALID
    assert client.profile_count == 0
    assert client.invalidate_count == 0


def test_local_disposal_closes_once_and_never_invalidates_remote_token() -> None:
    _, candidate, _, _, client = _candidate()

    candidate.dispose_local()
    candidate.dispose_local()

    assert client.reqsession.close_count == 1
    assert client.invalidate_count == 0
    assert client.profile_count == 0
    with pytest.raises(ProviderConnectivityError) as captured:
        candidate.principal_evidence()
    assert captured.value.code is ProviderErrorCode.INTERNAL_ADAPTER_DEFECT


def test_local_cleanup_failure_is_sanitized_and_remains_locally_terminal() -> None:
    _FakeKiteClient.close_effect = RuntimeError("raw local session detail")
    _, candidate, _, _, client = _candidate()

    with pytest.raises(ProviderConnectivityError) as captured:
        candidate.dispose_local()

    assert captured.value.code is ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
    assert "raw local session detail" not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert client.reqsession.close_count == 1
    assert client.invalidate_count == 0
    candidate.dispose_local()
    assert client.reqsession.close_count == 1


def test_legacy_bridge_preserves_current_caller_without_remote_invalidation() -> None:
    adapter = create_kite_authentication_adapter(_API_KEY, _API_SECRET)

    login_url = adapter.login_url()
    candidate = adapter.exchange(_REQUEST_TOKEN)
    evidence = adapter.context_evidence()
    adapter.terminate()

    client = _FakeKiteClient.instances[0]
    assert login_url.startswith("https://kite.zerodha.com/connect/login")
    assert repr(candidate) == "<_KiteCandidateContext redacted>"
    assert evidence is KiteContextEvidence.VALID
    assert client.login_count == 1
    assert client.exchange_count == 1
    assert client.profile_count == 1
    assert client.reqsession.close_count == 1
    assert client.invalidate_count == 0


def test_sdk_exchange_failure_is_controlled_and_redacted() -> None:
    raw = f"{_API_SECRET}:{_REQUEST_TOKEN}:{_ACCESS_TOKEN}"
    _FakeKiteClient.exchange_effect = RuntimeError(raw)
    adapter = create_kite_authentication_adapter(_API_KEY)

    with pytest.raises(ProviderConnectivityError) as captured:
        adapter.exchange_once(_FakeRequestToken(), OneUseSecretLease(_API_SECRET))

    assert captured.value.code is ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
    assert _API_SECRET not in str(captured.value)
    assert _REQUEST_TOKEN not in str(captured.value)
    assert _ACCESS_TOKEN not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_secret_and_token_are_closed_when_exchange_fails() -> None:
    _FakeKiteClient.exchange_effect = RuntimeError("synthetic failure")
    token = _FakeRequestToken()
    secret = OneUseSecretLease(_API_SECRET)
    adapter = create_kite_authentication_adapter(_API_KEY)

    with pytest.raises(ProviderConnectivityError):
        adapter.exchange_once(token, secret)

    assert token.closed is True
    assert token.use_count == 1
    assert secret.closed is True
    assert secret.used is True
    with pytest.raises(SecretLeaseError):
        secret.reveal_for_call(lambda _value: None)


def test_governed_adapter_records_exact_operations_with_remaining_budget() -> None:
    recorder = OperationLedgerRecorder()
    budgets = iter((120.0, 80.0, 40.0))
    adapter = create_kite_authentication_adapter(
        _API_KEY,
        operation_recorder=recorder.record,
        remaining_budget=lambda: RemainingBudget(next(budgets)),
    )

    adapter.login_url()
    candidate = adapter.exchange_once(
        _FakeRequestToken(),
        OneUseSecretLease(_API_SECRET),
    )
    evidence = candidate.principal_evidence()
    evidence.compare_expected(_PRINCIPAL)
    candidate.dispose_local()

    ledger = recorder.snapshot()
    assert ledger.count_for(GovernedAuthenticationOperation.LOGIN_URL_GENERATION) == 1
    assert ledger.count_for(GovernedAuthenticationOperation.SESSION_EXCHANGE) == 1
    assert ledger.count_for(
        GovernedAuthenticationOperation.PRINCIPAL_PROFILE_VERIFICATION
    ) == 1
    assert ledger.count_for(
        GovernedAuthenticationOperation.PROVIDER_AVAILABILITY_VERIFICATION
    ) == 0
    client = _FakeKiteClient.instances[0]
    assert client.login_count == 1
    assert client.exchange_count == 1
    assert client.profile_count == 1
    assert client.timeout == 40.0


def test_exhausted_budget_prevents_sdk_operation() -> None:
    recorder = OperationLedgerRecorder()
    adapter = create_kite_authentication_adapter(
        _API_KEY,
        operation_recorder=recorder.record,
        remaining_budget=lambda: RemainingBudget(0.0),
    )

    with pytest.raises(ProviderConnectivityError) as captured:
        adapter.login_url()

    assert captured.value.code is ProviderErrorCode.INTERNAL_ADAPTER_DEFECT
    assert _FakeKiteClient.instances[0].login_count == 0
    assert recorder.snapshot().count_for(
        GovernedAuthenticationOperation.LOGIN_URL_GENERATION
    ) == 0


def test_governed_candidate_blocks_withheld_availability_before_profile() -> None:
    recorder = OperationLedgerRecorder()
    adapter = create_kite_authentication_adapter(
        _API_KEY,
        operation_recorder=recorder.record,
        remaining_budget=lambda: RemainingBudget(120.0),
    )
    candidate = adapter.exchange_once(
        _FakeRequestToken(),
        OneUseSecretLease(_API_SECRET),
    )

    with pytest.raises(ProviderConnectivityError):
        candidate.verify_provider_availability()

    assert _FakeKiteClient.instances[0].profile_count == 0
    assert recorder.snapshot().count_for(
        GovernedAuthenticationOperation.PROVIDER_AVAILABILITY_VERIFICATION
    ) == 0
    candidate.dispose_local()
