from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
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
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from kronos.provider.contracts.instrument_master import (
    ProviderInstrumentDiagnosticPhase,
    ProviderInstrumentFieldFamily,
    ProviderInstrumentMasterError,
    ProviderInstrumentValidationRule,
    ProviderInstrumentValueClassification,
)
from kronos.provider.contracts.monitoring import MonitoringError, MonitoringFailure
from kronos.provider.exceptions.connectivity import (
    ProviderConnectivityError,
    ProviderErrorCode,
)
from kronos.provider.kite.composition import OperationLedgerRecorder
from kronos.provider.kite.live_activation import RemainingBudget
from kronos.provider.adapters.kite import monitoring as monitoring_module
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
    instrument_effects: list[object] = []

    def __init__(self, **arguments: object) -> None:
        self.arguments = arguments
        self.api_key = arguments.get("api_key")
        self.access_token = arguments.get("access_token")
        self.reqsession = _FakeSession(type(self).close_effect)
        self.exchange_count = 0
        self.profile_count = 0
        self.invalidate_count = 0
        self.instruments_count = 0
        self.instrument_exchanges: list[str | None] = []
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
        if isinstance(effect, dict):
            self.access_token = effect.get("access_token")
        return effect

    def profile(self) -> object:
        self.profile_count += 1
        effects = type(self).profile_effects
        effect = effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect

    def instruments(self, exchange: str | None = None) -> object:
        self.instruments_count += 1
        self.instrument_exchanges.append(exchange)
        effect = type(self).instrument_effects.pop(0)
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
    _FakeKiteClient.instrument_effects = []
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


def test_matched_candidate_issues_one_opaque_read_only_capability() -> None:
    _, candidate, _, _, client = _candidate()

    with pytest.raises(ProviderConnectivityError):
        candidate.issue_read_only_capability()

    evidence = candidate.principal_evidence()
    assert evidence.compare_expected(_PRINCIPAL) is PrincipalBindingResult.MATCHED
    capability = candidate.issue_read_only_capability()

    assert capability.operations == frozenset(ReadOnlyProviderOperation)
    assert capability.active is True
    assert repr(capability) == "<AuthenticatedReadOnlyProviderCapability redacted>"
    assert client.profile_count == 1
    for prohibited in (
        "api_secret",
        "access_token",
        "client",
        "sdk_client",
        "place_order",
        "modify_order",
        "cancel_order",
    ):
        assert not hasattr(capability, prohibited)
    with pytest.raises(TypeError):
        pickle.dumps(capability)
    with pytest.raises(ProviderConnectivityError):
        candidate.issue_read_only_capability()

    candidate.dispose_local()
    assert capability.active is False
    assert client.reqsession.close_count == 1
    assert client.invalidate_count == 0


def test_capability_publishes_deterministic_instrument_assertion_from_private_map() -> None:
    _FakeKiteClient.instrument_effects = [[{
        "instrument_token": 256265,
        "exchange": "NSE",
        "segment": "INDICES",
        "tradingsymbol": "NIFTY 50",
        "name": "NIFTY 50",
        "instrument_type": "EQ",
        "expiry": None,
        "tick_size": Decimal("0.05"),
        "lot_size": 1,
    }], [{
        "instrument_token": 256265,
        "exchange": "NSE",
        "segment": "INDICES",
        "tradingsymbol": "NIFTY 50",
        "name": "NIFTY 50",
        "instrument_type": "EQ",
        "expiry": None,
        "tick_size": Decimal("0.05"),
        "lot_size": 1,
    }]]
    _, candidate, _, _, _ = _candidate()
    candidate.principal_evidence().compare_expected(_PRINCIPAL)
    capability = candidate.issue_read_only_capability()
    boundary = datetime(2026, 8, 18, 4, 30, tzinfo=timezone.utc)

    first = capability.instrument_assertions(
        "NSE",
        source_boundary=boundary,
        valid_through=boundary + timedelta(days=1),
    )
    second = capability.instrument_assertions(
        "NSE",
        source_boundary=boundary,
        valid_through=boundary + timedelta(days=1),
    )

    assert first == second
    assert first[0].provider_instrument_token == 256265
    assert first[0].binding_source_identity.startswith("KITE-INSTRUMENT-MASTER-")
    assert not hasattr(capability, "instrument_token")


def test_capability_acquires_complete_instrument_master_without_exchange_filter() -> None:
    _FakeKiteClient.instrument_effects = [[{
        "instrument_token": 738561,
        "exchange_token": 2885,
        "exchange": "NSE",
        "segment": "NSE",
        "tradingsymbol": "RELIANCE",
        "name": "RELIANCE INDUSTRIES",
        "instrument_type": "EQ",
        "expiry": None,
        "strike": Decimal("0"),
        "last_price": Decimal("0"),
        "tick_size": Decimal("0.05"),
        "lot_size": 1,
    }, {
        "instrument_token": 123456,
        "exchange_token": 482,
        "exchange": "MCX",
        "segment": "MCX-FUT",
        "tradingsymbol": "GOLDM26AUGFUT",
        "name": "GOLDM",
        "instrument_type": "FUT",
        "expiry": datetime(2026, 8, 28),
        "strike": Decimal("0"),
        "last_price": Decimal("0"),
        "tick_size": Decimal("1"),
        "lot_size": 100,
    }]]
    _, candidate, _, _, client = _candidate()
    candidate.principal_evidence().compare_expected(_PRINCIPAL)
    capability = candidate.issue_read_only_capability()

    records = capability.instrument_master_records()

    assert client.instrument_exchanges == [None]
    assert tuple(item.exchange for item in records) == ("NSE", "MCX")
    assert records[1].name == "GOLDM"
    assert records[1].instrument_type == "FUT"
    assert records[1].expiry == datetime(2026, 8, 28).date()
    assert records[1].provider_instrument_token == 123456
    assert "123456" not in repr(records[1])
    assert not hasattr(capability, "instrument_tokens")


def _instrument_master_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "instrument_token": 738561,
        "exchange_token": 2885,
        "tradingsymbol": "RELIANCE",
        "name": "RELIANCE INDUSTRIES",
        "last_price": Decimal("0"),
        "expiry": None,
        "strike": Decimal("0"),
        "tick_size": Decimal("0.05"),
        "lot_size": 1,
        "instrument_type": "EQ",
        "segment": "NSE",
        "exchange": "NSE",
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("mutation", "rule", "field", "classification"),
    [
        (
            lambda row: row.pop("tradingsymbol"),
            ProviderInstrumentValidationRule.SYMBOL_REQUIRED,
            ProviderInstrumentFieldFamily.SYMBOL,
            ProviderInstrumentValueClassification.MISSING,
        ),
        (
            lambda row: row.update(tick_size=None),
            ProviderInstrumentValidationRule.TICK_REQUIRED,
            ProviderInstrumentFieldFamily.TICK_SIZE,
            ProviderInstrumentValueClassification.NULL,
        ),
        (
            lambda row: row.update(lot_size=None),
            ProviderInstrumentValidationRule.LOT_REQUIRED,
            ProviderInstrumentFieldFamily.LOT_SIZE,
            ProviderInstrumentValueClassification.NULL,
        ),
        (
            lambda row: row.update(exchange=""),
            ProviderInstrumentValidationRule.EXCHANGE_REQUIRED,
            ProviderInstrumentFieldFamily.EXCHANGE,
            ProviderInstrumentValueClassification.EMPTY,
        ),
        (
            lambda row: row.update(segment=""),
            ProviderInstrumentValidationRule.SEGMENT_REQUIRED,
            ProviderInstrumentFieldFamily.SEGMENT,
            ProviderInstrumentValueClassification.EMPTY,
        ),
        (
            lambda row: row.update(expiry="2026-08-28"),
            ProviderInstrumentValidationRule.EXPIRY_SHAPE_INVALID,
            ProviderInstrumentFieldFamily.EXPIRY,
            ProviderInstrumentValueClassification.MALFORMED,
        ),
        (
            lambda row: row.update(strike="not-a-decimal"),
            ProviderInstrumentValidationRule.STRIKE_INVALID,
            ProviderInstrumentFieldFamily.STRIKE,
            ProviderInstrumentValueClassification.MALFORMED,
        ),
        (
            lambda row: row.update(strike=Decimal("-1")),
            ProviderInstrumentValidationRule.STRIKE_INVALID,
            ProviderInstrumentFieldFamily.STRIKE,
            ProviderInstrumentValueClassification.NEGATIVE,
        ),
        (
            lambda row: row.update(strike=Decimal("NaN")),
            ProviderInstrumentValidationRule.STRIKE_INVALID,
            ProviderInstrumentFieldFamily.STRIKE,
            ProviderInstrumentValueClassification.NON_FINITE,
        ),
    ],
)
def test_instrument_master_normalization_reports_only_safe_schema_context(
    mutation: Callable[[dict[str, object]], object],
    rule: ProviderInstrumentValidationRule,
    field: ProviderInstrumentFieldFamily,
    classification: ProviderInstrumentValueClassification,
) -> None:
    row = _instrument_master_row()
    mutation(row)

    with pytest.raises(ProviderInstrumentMasterError) as captured:
        adapter_module._normalize_instrument_master_records([row])

    diagnostic = captured.value.diagnostic
    assert diagnostic is not None
    assert diagnostic.phase is ProviderInstrumentDiagnosticPhase.PROVIDER_NORMALIZATION
    assert diagnostic.rule is rule
    assert diagnostic.field_family is field
    assert diagnostic.value_classification is classification
    assert diagnostic.input_ordinal == 1
    assert diagnostic.affected_count == 1
    assert diagnostic.record_locator is not None
    rendered = repr(captured.value) + repr(diagnostic) + str(captured.value)
    for prohibited in ("738561", "RELIANCE", "not-a-decimal"):
        assert prohibited not in rendered


@pytest.mark.parametrize(
    "overrides",
    [
        {"tick_size": Decimal("0")},
        {"lot_size": 0},
        {"expiry": None},
        {"expiry": date(2026, 8, 28)},
        {"expiry": datetime(2026, 8, 28, 12, 0)},
        {
            "exchange": "NEW-EXCHANGE-VOCABULARY",
            "segment": "NEW-SEGMENT-VOCABULARY",
            "instrument_type": "NEW-TYPE-VOCABULARY",
        },
    ],
)
def test_instrument_master_normalization_acceptance_semantics_are_unchanged(
    overrides: dict[str, object],
) -> None:
    records = adapter_module._normalize_instrument_master_records(
        [_instrument_master_row(**overrides)]
    )

    assert len(records) == 1
    if isinstance(overrides.get("expiry"), datetime):
        assert records[0].expiry == date(2026, 8, 28)


def test_duplicate_provider_tokens_remain_valid_distinct_provider_records() -> None:
    records = adapter_module._normalize_instrument_master_records([
        _instrument_master_row(),
        _instrument_master_row(tradingsymbol="RELIANCE-ALTERNATE"),
    ])

    assert len(records) == 2
    assert records[0].provider_instrument_token == records[1].provider_instrument_token
    assert records[0].trading_symbol != records[1].trading_symbol


_MISSING_IDENTITY_COMPONENT = object()


@pytest.mark.parametrize(
    (
        "provider_field",
        "value",
        "accepted",
        "field_family",
        "classification",
    ),
    [
        ("instrument_token", 101, True, None, None),
        (
            "instrument_token",
            0,
            False,
            ProviderInstrumentFieldFamily.INSTRUMENT_TOKEN,
            ProviderInstrumentValueClassification.INVALID,
        ),
        (
            "instrument_token",
            -1,
            False,
            ProviderInstrumentFieldFamily.INSTRUMENT_TOKEN,
            ProviderInstrumentValueClassification.NEGATIVE,
        ),
        (
            "instrument_token",
            None,
            False,
            ProviderInstrumentFieldFamily.INSTRUMENT_TOKEN,
            ProviderInstrumentValueClassification.NULL,
        ),
        (
            "instrument_token",
            "101",
            False,
            ProviderInstrumentFieldFamily.INSTRUMENT_TOKEN,
            ProviderInstrumentValueClassification.MALFORMED,
        ),
        (
            "instrument_token",
            101.0,
            False,
            ProviderInstrumentFieldFamily.INSTRUMENT_TOKEN,
            ProviderInstrumentValueClassification.MALFORMED,
        ),
        (
            "instrument_token",
            True,
            False,
            ProviderInstrumentFieldFamily.INSTRUMENT_TOKEN,
            ProviderInstrumentValueClassification.MALFORMED,
        ),
        (
            "instrument_token",
            _MISSING_IDENTITY_COMPONENT,
            False,
            ProviderInstrumentFieldFamily.INSTRUMENT_TOKEN,
            ProviderInstrumentValueClassification.MISSING,
        ),
        ("exchange_token", 202, True, None, None),
        ("exchange_token", 0, True, None, None),
        (
            "exchange_token",
            -1,
            False,
            ProviderInstrumentFieldFamily.EXCHANGE_TOKEN,
            ProviderInstrumentValueClassification.NEGATIVE,
        ),
        ("exchange_token", None, True, None, None),
        (
            "exchange_token",
            "202",
            True,
            None,
            None,
        ),
        (
            "exchange_token",
            "0",
            True,
            None,
            None,
        ),
        (
            "exchange_token",
            "0202",
            False,
            ProviderInstrumentFieldFamily.EXCHANGE_TOKEN,
            ProviderInstrumentValueClassification.MALFORMED,
        ),
        (
            "exchange_token",
            "-202",
            False,
            ProviderInstrumentFieldFamily.EXCHANGE_TOKEN,
            ProviderInstrumentValueClassification.MALFORMED,
        ),
        (
            "exchange_token",
            "202.0",
            False,
            ProviderInstrumentFieldFamily.EXCHANGE_TOKEN,
            ProviderInstrumentValueClassification.MALFORMED,
        ),
        (
            "exchange_token",
            "2e2",
            False,
            ProviderInstrumentFieldFamily.EXCHANGE_TOKEN,
            ProviderInstrumentValueClassification.MALFORMED,
        ),
        (
            "exchange_token",
            "ABC202",
            False,
            ProviderInstrumentFieldFamily.EXCHANGE_TOKEN,
            ProviderInstrumentValueClassification.MALFORMED,
        ),
        (
            "exchange_token",
            "",
            False,
            ProviderInstrumentFieldFamily.EXCHANGE_TOKEN,
            ProviderInstrumentValueClassification.MALFORMED,
        ),
        (
            "exchange_token",
            " 202 ",
            False,
            ProviderInstrumentFieldFamily.EXCHANGE_TOKEN,
            ProviderInstrumentValueClassification.MALFORMED,
        ),
        (
            "exchange_token",
            202.0,
            False,
            ProviderInstrumentFieldFamily.EXCHANGE_TOKEN,
            ProviderInstrumentValueClassification.MALFORMED,
        ),
        (
            "exchange_token",
            True,
            False,
            ProviderInstrumentFieldFamily.EXCHANGE_TOKEN,
            ProviderInstrumentValueClassification.MALFORMED,
        ),
        ("exchange_token", _MISSING_IDENTITY_COMPONENT, True, None, None),
    ],
    ids=(
        "instrument-valid-integer",
        "instrument-zero",
        "instrument-negative",
        "instrument-null",
        "instrument-string",
        "instrument-float",
        "instrument-boolean",
        "instrument-missing",
        "exchange-valid-integer",
        "exchange-zero",
        "exchange-negative",
        "exchange-null",
        "exchange-positive-digit-string",
        "exchange-zero-string",
        "exchange-leading-zero-string",
        "exchange-negative-string",
        "exchange-float-string",
        "exchange-scientific-string",
        "exchange-nonnumeric-string",
        "exchange-empty-string",
        "exchange-whitespace-string",
        "exchange-float",
        "exchange-boolean",
        "exchange-missing",
    ),
)
def test_identity_component_diagnostics_preserve_existing_shape_semantics(
    provider_field: str,
    value: object,
    accepted: bool,
    field_family: ProviderInstrumentFieldFamily | None,
    classification: ProviderInstrumentValueClassification | None,
) -> None:
    row = _instrument_master_row()
    if value is _MISSING_IDENTITY_COMPONENT:
        row.pop(provider_field)
    else:
        row[provider_field] = value

    if accepted:
        records = adapter_module._normalize_instrument_master_records([row])
        assert len(records) == 1
        if provider_field == "exchange_token":
            expected = (
                None
                if value is _MISSING_IDENTITY_COMPONENT
                else int(value)
                if type(value) is str
                else value
            )
            assert records[0].exchange_token == expected
            assert type(records[0].exchange_token) is (
                type(None) if expected is None else int
            )
        return

    with pytest.raises(ProviderInstrumentMasterError) as captured:
        adapter_module._normalize_instrument_master_records([row])

    diagnostic = captured.value.diagnostic
    assert diagnostic is not None
    assert diagnostic.phase is ProviderInstrumentDiagnosticPhase.PROVIDER_NORMALIZATION
    assert diagnostic.rule is (
        ProviderInstrumentValidationRule.PROVIDER_RECORD_IDENTITY_INVALID
    )
    assert diagnostic.field_family is field_family
    assert diagnostic.value_classification is classification
    assert diagnostic.input_ordinal == 1
    assert diagnostic.affected_count == 1
    assert diagnostic.record_locator is not None


def test_unsupported_exchange_token_shape_is_isolated_without_value_exposure() -> None:
    row = _instrument_master_row(exchange_token="SDK-CSV-TEXT-SHAPE")

    with pytest.raises(ProviderInstrumentMasterError) as captured:
        adapter_module._normalize_instrument_master_records([row])

    diagnostic = captured.value.diagnostic
    assert diagnostic is not None
    assert diagnostic.field_family is ProviderInstrumentFieldFamily.EXCHANGE_TOKEN
    assert diagnostic.value_classification is (
        ProviderInstrumentValueClassification.MALFORMED
    )
    rendered = repr(captured.value) + repr(diagnostic) + str(captured.value)
    assert "SDK-CSV-TEXT-SHAPE" not in rendered


def test_kite_sdk_numeric_text_exchange_token_normalizes_before_contract() -> None:
    records = adapter_module._normalize_instrument_master_records([
        _instrument_master_row(
            instrument_token=101,
            exchange_token="202",
        )
    ])

    assert len(records) == 1
    assert records[0].provider_instrument_token == 101
    assert records[0].exchange_token == 202
    assert type(records[0].exchange_token) is int


def test_capability_publishes_reliance_when_exchange_contains_zero_geometry() -> None:
    _FakeKiteClient.instrument_effects = [[{
        "instrument_token": 256265,
        "exchange": "NSE",
        "segment": "INDICES",
        "tradingsymbol": "NIFTY 50",
        "name": "NIFTY 50",
        "instrument_type": "EQ",
        "expiry": None,
        "tick_size": Decimal("0"),
        "lot_size": 0,
    }, {
        "instrument_token": 738561,
        "exchange": "NSE",
        "segment": "NSE",
        "tradingsymbol": "RELIANCE",
        "name": "RELIANCE INDUSTRIES",
        "instrument_type": "EQ",
        "expiry": None,
        "tick_size": Decimal("0.05"),
        "lot_size": 1,
    }]]
    _, candidate, _, _, _ = _candidate()
    candidate.principal_evidence().compare_expected(_PRINCIPAL)
    capability = candidate.issue_read_only_capability()
    boundary = datetime(2026, 8, 18, 4, 30, tzinfo=timezone.utc)

    assertions = capability.instrument_assertions(
        "NSE",
        source_boundary=boundary,
        valid_through=boundary + timedelta(days=1),
    )

    index = next(item for item in assertions if item.provider_symbol == "NIFTY 50")
    reliance = next(item for item in assertions if item.provider_symbol == "RELIANCE")
    assert index.asserted_tick_size is None
    assert index.asserted_lot_size is None
    assert reliance.provider == "KITE"
    assert reliance.provider_instrument_token == 738561
    assert reliance.asserted_tick_size == Decimal("0.05")
    assert reliance.asserted_lot_size == 1
    assert reliance.binding_source_identity.startswith("KITE-INSTRUMENT-MASTER-")
    assert reliance.source_boundary == boundary
    assert reliance.valid_through == boundary + timedelta(days=1)
    assert reliance.assertion_identity
    assert not hasattr(capability, "instrument_token")


def test_authenticated_capability_opens_monitoring_without_exposing_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSocket:
        pass

    class Consumer:
        def on_market_tick(self, _tick: object) -> None: pass
        def on_order_update(self, _update: object) -> None: pass
        def on_connection_state(self, _state: object) -> None: pass

    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(
        monitoring_module,
        "_create_socket",
        lambda api_key, access_token: seen.append((api_key, access_token)) or FakeSocket(),
    )
    _, candidate, _, _, _ = _candidate()
    candidate.principal_evidence().compare_expected(_PRINCIPAL)
    capability = candidate.issue_read_only_capability()
    session = capability.open_monitoring_session(Consumer())

    assert repr(session) == "<KiteReadOnlyMonitoringSession redacted>"
    assert seen == [(_API_KEY, _ACCESS_TOKEN)]
    assert not hasattr(session, "access_token")

    candidate.dispose_local()
    with pytest.raises(MonitoringError) as error:
        capability.open_monitoring_session(Consumer())
    assert error.value.failure is MonitoringFailure.CAPABILITY_UNAVAILABLE


def test_session_expiry_invalidates_read_only_capability_without_exposure() -> None:
    _, candidate, _, _, client = _candidate()
    evidence = candidate.principal_evidence()
    assert evidence.compare_expected(_PRINCIPAL) is PrincipalBindingResult.MATCHED
    capability = candidate.issue_read_only_capability()

    client.expire_session()

    assert capability.active is False
    assert client.invalidate_count == 0


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
