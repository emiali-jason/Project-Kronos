from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
import pickle
from threading import Event, Thread
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.configuration.apple_keychain import AppleKeychainCredentialError
from kronos.configuration.credentials import CredentialRetrievalOutcome
from kronos.configuration.principals import PrincipalBindingResult
from kronos.instrument.catalogue import load_canonical_instrument_catalogue
from kronos.instrument.runtime import (
    ExecutionContextAvailability,
    ProviderBindingStatus,
    create_canonical_instrument,
    create_provider_assertion,
    create_provider_binding_directive,
    publish_runtime_instruments,
)
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.instrument_master import (
    KITE_INSTRUMENT_MASTER_OPERATION,
    ProviderInstrumentMasterSourceRecord,
)
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
    HistoricalDataError,
    HistoricalInterval,
)
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from kronos.provider.models.authentication import (
    AuthenticatedContextState,
    AuthenticationAttemptState,
    ProviderAvailabilityState,
)
from kronos.provider.runtime import (
    ProviderRuntimeAccessError,
    ProviderRuntimeFailure,
    SharedAuthenticatedProviderRuntime,
    SharedProviderRuntimeLifecycle,
)


IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 8, 18, 10, 0, tzinfo=IST)
VALID_THROUGH = NOW + timedelta(hours=6)
INSTRUMENT = InstrumentRecord(
    "KITE",
    "NSE",
    "INDICES",
    "NIFTY 50",
    "NIFTY 50",
    "EQ",
    None,
    Decimal("0.05"),
    1,
)


class _Capability:
    def __init__(self) -> None:
        self.active = True
        self.calls = 0
        self.operations = frozenset(ReadOnlyProviderOperation)

    def instrument_records(self, exchange: str):  # type: ignore[no-untyped-def]
        assert exchange == "NSE"
        return (INSTRUMENT,)

    def instrument_master_records(self):  # type: ignore[no-untyped-def]
        self.calls += 1
        return (ProviderInstrumentMasterSourceRecord(
            provider="KITE",
            provider_instrument_token=256265,
            exchange_token=1001,
            trading_symbol="NIFTY 50",
            name="NIFTY 50",
            last_price=Decimal("0"),
            expiry=None,
            strike=Decimal("0"),
            tick_size=Decimal("0.05"),
            lot_size=1,
            instrument_type="EQ",
            segment="INDICES",
            exchange="NSE",
        ),)

    def instrument_assertions(
        self,
        exchange: str,
        *,
        source_boundary: datetime,
        valid_through: datetime,
    ):  # type: ignore[no-untyped-def]
        assert exchange == "NSE"
        return (create_provider_assertion(
            provider="KITE",
            provider_symbol="NIFTY 50",
            provider_instrument_token=256265,
            exchange="NSE",
            segment="INDICES",
            instrument_type="EQ",
            asserted_tick_size=Decimal("0.05"),
            asserted_lot_size=1,
            binding_source_identity="KITE-INSTRUMENT-MASTER-FACTUAL-V1",
            source_boundary=source_boundary,
            valid_through=valid_through,
        ),)

    def historical_candles(self, request):  # type: ignore[no-untyped-def]
        assert request.instrument == INSTRUMENT
        self.calls += 1
        return (HistoricalCandle(
            timestamp=request.start,
            open=100.0,
            high=102.0,
            low=99.0,
            close=101.0,
            volume=10,
        ),)

    def quote(self, _instrument):  # type: ignore[no-untyped-def]
        raise AssertionError("unused")

    def ltp(self, _instrument):  # type: ignore[no-untyped-def]
        raise AssertionError("unused")

    def ohlc(self, _instrument):  # type: ignore[no-untyped-def]
        raise AssertionError("unused")

    def open_monitoring_session(self, _consumer):  # type: ignore[no-untyped-def]
        raise AssertionError("unused")


class _Runtime:
    def __init__(self, *, matched: bool = True) -> None:
        self.capability = _Capability()
        self.matched = matched
        self.begin_count = 0
        self.end_count = 0
        self.context_state = AuthenticatedContextState.ABSENT

    def begin_login(self):  # type: ignore[no-untyped-def]
        self.begin_count += 1
        return object()

    def complete_callback(self, _attempt):  # type: ignore[no-untyped-def]
        if self.matched:
            self.context_state = AuthenticatedContextState.ACTIVE
            return SimpleNamespace(
                state=AuthenticationAttemptState.SUCCEEDED,
                binding_result=PrincipalBindingResult.MATCHED,
            )
        return SimpleNamespace(
            state=AuthenticationAttemptState.FAILED,
            binding_result=PrincipalBindingResult.MISMATCHED,
        )

    def session_status(self):  # type: ignore[no-untyped-def]
        return SimpleNamespace(
            context_state=self.context_state,
            provider_availability=ProviderAvailabilityState.NOT_VERIFIED,
        )

    def current_context(self):  # type: ignore[no-untyped-def]
        if self.context_state is not AuthenticatedContextState.ACTIVE:
            return None
        return SimpleNamespace(
            provider="KITE",
            context_id="AUTH-CONTEXT-OPAQUE-1",
            valid_until=VALID_THROUGH,
        )

    def authenticated_read_only_capability(self):  # type: ignore[no-untyped-def]
        if self.context_state is not AuthenticatedContextState.ACTIVE:
            return None
        return self.capability

    def end_kronos_session(self) -> None:
        self.end_count += 1
        self.capability.active = False
        self.context_state = AuthenticatedContextState.ENDED


def _shared(
    runtime: _Runtime | None = None,
) -> tuple[SharedAuthenticatedProviderRuntime, _Runtime, list[int]]:
    selected = runtime or _Runtime()
    factory_calls: list[int] = []
    identities = iter(f"LEASE-{number}" for number in range(1, 50))

    def factory():  # type: ignore[no-untyped-def]
        factory_calls.append(1)
        return selected

    shared = SharedAuthenticatedProviderRuntime(
        factory,
        provider_identity="KITE",
        clock=lambda: NOW,
        identity_factory=lambda: next(identities),
    )
    return shared, selected, factory_calls


def _authenticate(shared: SharedAuthenticatedProviderRuntime) -> None:
    attempt = shared.begin_login()
    shared.complete_callback(attempt)


def _historical_request() -> HistoricalCandleRequest:
    return HistoricalCandleRequest(
        instrument=INSTRUMENT,
        start=NOW - timedelta(minutes=5),
        end=NOW,
        interval=HistoricalInterval.FIVE_MINUTE,
    )


def _lease(shared: SharedAuthenticatedProviderRuntime, consumer: str):  # type: ignore[no-untyped-def]
    return shared.acquire_lease(
        consumer_identity=consumer,
        operations=frozenset({ReadOnlyProviderOperation.HISTORICAL_DATA}),
    )


def test_one_context_and_swing_only_compatibility_consumer() -> None:
    shared, runtime, factory_calls = _shared()
    facade = shared.compatibility_facade(
        consumer_identity="SWING",
        operations=frozenset({ReadOnlyProviderOperation.HISTORICAL_DATA}),
    )

    attempt = facade.begin_login()
    facade.complete_callback(attempt)
    lease = facade.authenticated_read_only_capability()

    assert lease is not None and lease.active
    assert lease.historical_candles(_historical_request())[0].close == 101.0
    assert runtime.begin_count == 1
    assert factory_calls == [1]
    with pytest.raises(
        ProviderRuntimeAccessError,
        match=ProviderRuntimeFailure.CONTEXT_ALREADY_ACTIVE.value,
    ):
        shared.begin_login()
    assert factory_calls == [1]


def test_provider_construction_is_single_flight_and_status_remains_responsive() -> None:
    entered = Event()
    release = Event()
    runtime = _Runtime()
    factory_calls: list[int] = []
    result: list[object] = []

    def factory():  # type: ignore[no-untyped-def]
        factory_calls.append(1)
        entered.set()
        assert release.wait(timeout=2.0)
        return runtime

    shared = SharedAuthenticatedProviderRuntime(
        factory,
        provider_identity="KITE",
        clock=lambda: NOW,
    )
    construction = Thread(target=lambda: result.append(shared.begin_login()))
    construction.start()
    assert entered.wait(timeout=2.0)

    status: list[dict[str, object]] = []
    status_read = Thread(target=lambda: status.append(shared.read_only_status()))
    status_read.start()
    status_read.join(timeout=0.2)
    try:
        assert not status_read.is_alive()
        assert status[0]["retained_lifecycle"] == "ABSENT"
        assert status[0]["capability_state"] == "ABSENT"
        with pytest.raises(
            ProviderRuntimeAccessError,
            match=ProviderRuntimeFailure.CONTEXT_ALREADY_ACTIVE.value,
        ):
            shared.begin_login()
        assert factory_calls == [1]
    finally:
        release.set()
        construction.join(timeout=2.0)
        status_read.join(timeout=2.0)

    assert not construction.is_alive()
    assert len(result) == 1
    assert runtime.begin_count == 1


def test_construction_timeout_releases_single_flight_for_explicit_retry() -> None:
    runtime = _Runtime()
    factory_calls: list[int] = []

    def factory():  # type: ignore[no-untyped-def]
        factory_calls.append(1)
        if len(factory_calls) == 1:
            raise AppleKeychainCredentialError(
                CredentialRetrievalOutcome.TIMED_OUT
            )
        return runtime

    shared = SharedAuthenticatedProviderRuntime(
        factory,
        provider_identity="KITE",
        clock=lambda: NOW,
    )

    with pytest.raises(AppleKeychainCredentialError) as captured:
        shared.begin_login()

    assert captured.value.outcome is CredentialRetrievalOutcome.TIMED_OUT
    assert runtime.begin_count == 0
    assert shared.read_only_status()["retained_lifecycle"] == "ABSENT"
    assert shared.read_only_status()["capability_state"] == "ABSENT"

    attempt = shared.begin_login()
    assert attempt is not None
    assert factory_calls == [1, 1]
    assert runtime.begin_count == 1


def test_expired_construction_generation_cannot_publish_late_provider() -> None:
    entered = Event()
    release = Event()
    stale = _Runtime()
    current = _Runtime()
    factory_calls: list[int] = []
    stale_failure: list[BaseException] = []

    def factory():  # type: ignore[no-untyped-def]
        factory_calls.append(1)
        if len(factory_calls) == 1:
            entered.set()
            assert release.wait(timeout=2.0)
            return stale
        return current

    shared = SharedAuthenticatedProviderRuntime(
        factory,
        provider_identity="KITE",
        clock=lambda: NOW,
    )

    def begin_stale() -> None:
        try:
            shared.begin_login()
        except BaseException as error:
            stale_failure.append(error)

    first = Thread(target=begin_stale)
    first.start()
    assert entered.wait(timeout=2.0)
    shared.invalidate("CONSTRUCTION_EXPIRED")

    try:
        with pytest.raises(
            ProviderRuntimeAccessError,
            match=ProviderRuntimeFailure.CONTEXT_ALREADY_ACTIVE.value,
        ):
            shared.begin_login()
        assert factory_calls == [1]
    finally:
        release.set()
        first.join(timeout=2.0)

    current_attempt = shared.begin_login()

    assert not first.is_alive()
    assert len(stale_failure) == 1
    assert isinstance(stale_failure[0], ProviderRuntimeAccessError)
    assert stale.end_count == 1
    assert stale.begin_count == 0
    assert current.begin_count == 1
    assert factory_calls == [1, 1]

    shared.complete_callback(current_attempt)
    assert shared.lifecycle_state is SharedProviderRuntimeLifecycle.ACTIVE


def test_intraday_only_consumer_is_operation_minimized() -> None:
    shared, _, _ = _shared()
    _authenticate(shared)

    intraday = create_intraday_runtime(shared)
    lease = intraday.provider_access.acquire_historical_lease()

    assert lease.operations == frozenset({
        ReadOnlyProviderOperation.INSTRUMENTS,
        ReadOnlyProviderOperation.INSTRUMENT_ASSERTIONS,
        ReadOnlyProviderOperation.HISTORICAL_DATA,
    })
    assert lease.historical_candles(_historical_request())
    assert not hasattr(lease, "place_order")
    assert not hasattr(lease, "begin_login")
    assert not hasattr(lease, "end_kronos_session")
    assert not hasattr(lease, "instrument_master_records")


def test_domain_006_master_read_uses_active_shared_context_without_product_accessor() -> None:
    shared, runtime, factory_calls = _shared()
    assert not shared.provider_instrument_master_operation_available
    _authenticate(shared)
    assert shared.provider_instrument_master_operation_available

    records = shared.acquire_provider_instrument_master_records(
        operation_identity=KITE_INSTRUMENT_MASTER_OPERATION
    )

    assert records[0].trading_symbol == "NIFTY 50"
    assert runtime.capability.calls == 1
    assert runtime.begin_count == 1
    assert factory_calls == [1]
    with pytest.raises(ProviderRuntimeAccessError) as captured:
        shared.acquire_provider_instrument_master_records(
            operation_identity="UNAUTHORIZED"
        )
    assert captured.value.failure is ProviderRuntimeFailure.OPERATION_NOT_AUTHORIZED


def test_domain_006_master_operation_availability_is_sanitized_and_fail_closed() -> None:
    shared, runtime, _ = _shared()
    runtime.capability.instrument_master_records = None  # type: ignore[assignment]
    _authenticate(shared)

    assert shared.lifecycle_state is SharedProviderRuntimeLifecycle.ACTIVE
    assert not shared.provider_instrument_master_operation_available
    with pytest.raises(ProviderRuntimeAccessError) as captured:
        shared.acquire_provider_instrument_master_records(
            operation_identity=KITE_INSTRUMENT_MASTER_OPERATION
        )
    assert captured.value.failure is ProviderRuntimeFailure.CAPABILITY_UNAVAILABLE


def test_swing_and_intraday_leases_are_independent_and_concurrent() -> None:
    shared, runtime, _ = _shared()
    _authenticate(shared)
    swing_facade = shared.compatibility_facade(
        consumer_identity="SWING",
        operations=frozenset({ReadOnlyProviderOperation.HISTORICAL_DATA}),
    )
    swing = swing_facade.authenticated_read_only_capability()
    assert swing is not None
    intraday = _lease(shared, "INTRADAY")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(
            lambda lease: lease.historical_candles(_historical_request()),
            (swing, intraday),
        ))
    assert all(result[0].close == 101.0 for result in results)
    assert runtime.capability.calls == 2

    intraday.release()
    assert not intraday.active
    assert swing.active
    assert swing.historical_candles(_historical_request())

    replacement = _lease(shared, "INTRADAY")
    swing_facade.release_product_lease()
    assert not swing.active
    assert replacement.active
    assert replacement.historical_candles(_historical_request())


def test_expiry_and_invalidation_revoke_all_retained_lease_objects() -> None:
    shared, runtime, _ = _shared()
    _authenticate(shared)
    first = _lease(shared, "SWING")
    second = _lease(shared, "INTRADAY")

    runtime.context_state = AuthenticatedContextState.EXPIRED
    runtime.capability.active = False

    assert shared.lifecycle_state is SharedProviderRuntimeLifecycle.EXPIRED
    assert not first.active and not second.active
    with pytest.raises(HistoricalDataError, match="CAPABILITY_UNAVAILABLE"):
        first.historical_candles(_historical_request())

    next_shared, next_runtime, _ = _shared()
    _authenticate(next_shared)
    lease = _lease(next_shared, "SWING")
    next_shared.invalidate("PROVIDER_CONTEXT_INVALIDATED")
    assert next_shared.lifecycle_state is SharedProviderRuntimeLifecycle.INVALIDATED
    assert not lease.active
    assert next_runtime.end_count == 1


def test_end_session_revokes_every_lease_and_disposes_context_once() -> None:
    shared, runtime, _ = _shared()
    _authenticate(shared)
    swing = _lease(shared, "SWING")
    intraday = _lease(shared, "INTRADAY")

    shared.end_kronos_session()
    shared.end_kronos_session()

    assert shared.lifecycle_state is SharedProviderRuntimeLifecycle.DISPOSED
    assert not swing.active and not intraday.active
    assert runtime.end_count == 1
    assert shared.active_lease_count == 0


def test_ending_state_fails_closed_before_shared_disposal_completes() -> None:
    entered = Event()
    proceed = Event()

    class _BlockingRuntime(_Runtime):
        def end_kronos_session(self) -> None:
            entered.set()
            assert proceed.wait(timeout=2.0)
            super().end_kronos_session()

    shared, runtime, _ = _shared(_BlockingRuntime())
    _authenticate(shared)
    lease = _lease(shared, "SWING")
    thread = Thread(target=shared.end_kronos_session)
    thread.start()
    assert entered.wait(timeout=2.0)

    assert shared.lifecycle_state is SharedProviderRuntimeLifecycle.ENDING
    assert shared.read_only_status()["cleanup_state"] == "PENDING"
    assert shared.read_only_status()["owned_work_count"] == 1
    assert not lease.active
    with pytest.raises(HistoricalDataError, match="CAPABILITY_UNAVAILABLE"):
        lease.historical_candles(_historical_request())

    proceed.set()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert shared.lifecycle_state is SharedProviderRuntimeLifecycle.DISPOSED
    assert shared.read_only_status()["cleanup_state"] == "COMPLETE"
    assert runtime.end_count == 1


def test_principal_mismatch_and_unverified_candidate_are_never_exposed() -> None:
    shared, _, _ = _shared(_Runtime(matched=False))
    attempt = shared.begin_login()

    with pytest.raises(ProviderRuntimeAccessError, match="CONTEXT_UNAVAILABLE"):
        _lease(shared, "INTRADAY")

    outcome = shared.complete_callback(attempt)
    assert outcome.binding_result is PrincipalBindingResult.MISMATCHED
    assert shared.lifecycle_state is SharedProviderRuntimeLifecycle.ABSENT
    with pytest.raises(ProviderRuntimeAccessError, match="CONTEXT_UNAVAILABLE"):
        _lease(shared, "INTRADAY")


def test_lease_and_runtime_are_redacted_nonserializable_and_have_no_mutation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    shared, _, _ = _shared()
    _authenticate(shared)
    lease = _lease(shared, "SWING")

    assert repr(shared) == "<SharedAuthenticatedProviderRuntime sanitized>"
    assert repr(lease) == "<ReadOnlyProviderLease redacted>"
    rendered = f"{shared!r} {lease!r}"
    assert all(secret not in rendered.lower() for secret in (
        "api_secret",
        "access_token",
        "request_token",
        "credential",
    ))
    with pytest.raises(TypeError, match="SERIALIZATION_PROHIBITED"):
        pickle.dumps(shared)
    with pytest.raises(TypeError, match="SERIALIZATION_PROHIBITED"):
        pickle.dumps(lease)
    assert not any(name in dir(lease) for name in (
        "orders",
        "place_order",
        "modify_order",
        "cancel_order",
        "positions",
    ))
    assert caplog.text == ""


def test_provider_assertion_is_deterministic_and_domain_001_binds_fail_closed() -> None:
    shared, _, _ = _shared()
    _authenticate(shared)
    intraday = create_intraday_runtime(shared)
    lease = intraday.provider_access.acquire_historical_lease()

    first = lease.instrument_assertions(
        "NSE",
        source_boundary=NOW,
        valid_through=VALID_THROUGH,
    )[0]
    second = lease.instrument_assertions(
        "NSE",
        source_boundary=NOW,
        valid_through=VALID_THROUGH,
    )[0]
    assert first == second
    assert first.provider_instrument_token == 256265

    canonical = create_canonical_instrument(
        canonical_instrument_id="NIFTY",
        exchange="NSE",
        segment="INDICES",
        instrument_type="EQ",
        canonical_tick_size=Decimal("0.05"),
        canonical_lot_size=1,
        canonical_source_identity="GOVERNED-CANONICAL-UNIVERSE-V1",
        source_boundary=NOW - timedelta(days=1),
        valid_through=VALID_THROUGH,
    )
    directive = create_provider_binding_directive(
        canonical_instrument_id="NIFTY",
        provider="KITE",
        provider_symbol="NIFTY 50",
        directive_source_identity="GOVERNED-PROVIDER-BINDINGS-V1",
    )
    bound = publish_runtime_instruments(
        canonical_instruments=(canonical,),
        provider_assertions=(first,),
        binding_directives=(directive,),
        observed_at=NOW,
    ).lookup("NIFTY")
    assert bound.binding_status is ProviderBindingStatus.BOUND
    assert bound.execution_context is ExecutionContextAvailability.COMPLETE

    wrong = create_provider_assertion(
        provider="KITE",
        provider_symbol="NIFTY 50",
        provider_instrument_token=256265,
        exchange="NSE",
        segment="NSE",
        instrument_type="EQ",
        asserted_tick_size=Decimal("0.05"),
        asserted_lot_size=1,
        binding_source_identity="KITE-INSTRUMENT-MASTER-WRONG",
        source_boundary=NOW,
        valid_through=VALID_THROUGH,
    )
    rejected = publish_runtime_instruments(
        canonical_instruments=(canonical,),
        provider_assertions=(wrong,),
        binding_directives=(directive,),
        observed_at=NOW,
    ).lookup("NIFTY")
    assert rejected.binding_status is ProviderBindingStatus.UNAVAILABLE
    assert rejected.execution_context is ExecutionContextAvailability.INCOMPLETE


def test_provider_assertion_lease_fails_closed_when_unauthorized_released_or_expired() -> None:
    shared, runtime, factory_calls = _shared()
    _authenticate(shared)
    unauthorized = _lease(shared, "INTRADAY")
    with pytest.raises(
        ProviderRuntimeAccessError,
        match=ProviderRuntimeFailure.OPERATION_NOT_AUTHORIZED.value,
    ):
        unauthorized.instrument_assertions(
            "NSE", source_boundary=NOW, valid_through=VALID_THROUGH
        )

    authorized = shared.acquire_lease(
        consumer_identity="INTRADAY",
        operations=frozenset({ReadOnlyProviderOperation.INSTRUMENT_ASSERTIONS}),
    )
    assertion = authorized.instrument_assertions(
        "NSE", source_boundary=NOW, valid_through=VALID_THROUGH
    )[0]
    assert assertion.provider == "KITE"
    assert assertion.assertion_identity
    assert factory_calls == [1]

    authorized.release()
    with pytest.raises(
        ProviderRuntimeAccessError,
        match=ProviderRuntimeFailure.LEASE_RELEASED.value,
    ):
        authorized.instrument_assertions(
            "NSE", source_boundary=NOW, valid_through=VALID_THROUGH
        )

    expiring = shared.acquire_lease(
        consumer_identity="INTRADAY",
        operations=frozenset({ReadOnlyProviderOperation.INSTRUMENT_ASSERTIONS}),
    )
    runtime.context_state = AuthenticatedContextState.EXPIRED
    runtime.capability.active = False
    with pytest.raises(
        ProviderRuntimeAccessError,
        match=ProviderRuntimeFailure.CONTEXT_EXPIRED.value,
    ):
        expiring.instrument_assertions(
            "NSE", source_boundary=NOW, valid_through=VALID_THROUGH
        )


def test_shared_runtime_assertion_binds_through_production_domain_001_catalogue() -> None:
    shared, runtime, _ = _shared()
    catalogue_now = datetime(2026, 8, 18, 19, 0, tzinfo=IST)
    catalogue_valid_through = catalogue_now + timedelta(hours=1)
    runtime.capability.instrument_assertions = lambda exchange, **_: (  # type: ignore[method-assign]
        create_provider_assertion(
            provider="KITE",
            provider_symbol="RELIANCE",
            provider_instrument_token=738561,
            exchange=exchange,
            segment="NSE",
            instrument_type="EQ",
            asserted_tick_size=Decimal("0.1"),
            asserted_lot_size=1,
            binding_source_identity="KITE-INSTRUMENT-MASTER-FACTUAL-V1",
            source_boundary=catalogue_now,
            valid_through=catalogue_valid_through,
        ),
    )
    _authenticate(shared)
    lease = create_intraday_runtime(shared).provider_access.acquire_historical_lease()
    assertions = lease.instrument_assertions(
        "NSE",
        source_boundary=catalogue_now,
        valid_through=catalogue_valid_through,
    )

    published = load_canonical_instrument_catalogue().runtime_registry(
        provider_assertions=assertions,
        observed_at=catalogue_now,
    ).require_consumable("RELIANCE")

    assert published.binding_status is ProviderBindingStatus.BOUND
    assert published.provider_binding is not None
    assert published.provider_binding.provider_instrument_token == 738561


def test_restart_requires_new_authentication_and_does_not_restore_objects() -> None:
    first, runtime, _ = _shared()
    _authenticate(first)
    lease = _lease(first, "SWING")
    first.end_kronos_session()

    restarted, _, factory_calls = _shared(runtime)

    assert not lease.active
    assert restarted.lifecycle_state is SharedProviderRuntimeLifecycle.ABSENT
    assert factory_calls == []
    with pytest.raises(ProviderRuntimeAccessError, match="CONTEXT_UNAVAILABLE"):
        _lease(restarted, "INTRADAY")


def test_invalidated_callback_keeps_worker_owned_and_cannot_publish_late_success() -> None:
    entered = Event()
    release = Event()

    class BlockedRuntime(_Runtime):
        def complete_callback(self, attempt):  # type: ignore[no-untyped-def]
            entered.set()
            assert release.wait(timeout=2.0)
            return super().complete_callback(attempt)

    stale = BlockedRuntime()
    current = _Runtime()
    providers = iter((stale, current))
    factory_calls: list[int] = []

    def factory():  # type: ignore[no-untyped-def]
        factory_calls.append(1)
        return next(providers)

    shared = SharedAuthenticatedProviderRuntime(
        factory, provider_identity="KITE", clock=lambda: NOW,
    )
    attempt = shared.begin_login()
    failures: list[BaseException] = []

    def complete() -> None:
        try:
            shared.complete_callback(attempt)
        except BaseException as error:
            failures.append(error)

    thread = Thread(target=complete)
    thread.start()
    assert entered.wait(timeout=2.0)
    try:
        shared.invalidate("AUTHENTICATION_GENERATION_EXPIRED")
        with pytest.raises(
            ProviderRuntimeAccessError,
            match=ProviderRuntimeFailure.CONTEXT_ALREADY_ACTIVE.value,
        ):
            shared.begin_login()
        assert factory_calls == [1]
        assert shared.read_only_status()["capability_state"] == "ABSENT"
    finally:
        release.set()
        thread.join(timeout=2.0)

    assert not thread.is_alive()
    assert len(failures) == 1
    assert isinstance(failures[0], ProviderRuntimeAccessError)
    assert shared.read_only_status()["capability_state"] == "ABSENT"
    assert stale.end_count == 1
    next_attempt = shared.begin_login()
    shared.complete_callback(next_attempt)
    assert shared.lifecycle_state is SharedProviderRuntimeLifecycle.ACTIVE
    assert factory_calls == [1, 1]


def test_failed_provider_cleanup_retains_ownership_and_denies_retry() -> None:
    class UnclosedRuntime(_Runtime):
        def end_kronos_session(self) -> None:
            self.end_count += 1
            raise RuntimeError("INJECTED_LOCAL_DISPOSAL_FAILURE")

    shared, provider, factory_calls = _shared(UnclosedRuntime())
    shared.begin_login()
    shared.end_kronos_session()
    assert provider.end_count == 1
    status = shared.read_only_status()
    assert status["capability_state"] == "ABSENT"
    assert status["retained_lifecycle"] == "ENDING"
    assert status["cleanup_state"] == "FAILED"
    assert status["owned_work_count"] == 0
    assert status["unresolved_cleanup_count"] == 1
    shared.end_kronos_session()
    assert shared.read_only_status()["retained_lifecycle"] == "ENDING"
    assert provider.end_count == 1
    with pytest.raises(
        ProviderRuntimeAccessError,
        match=ProviderRuntimeFailure.CONTEXT_ALREADY_ACTIVE.value,
    ):
        shared.begin_login()
    assert factory_calls == [1]


def test_repeated_runtime_cycles_leave_no_cleanup_owner_or_lease():
    providers = [_Runtime() for _ in range(20)]
    factory_calls = []
    shared = SharedAuthenticatedProviderRuntime(
        lambda: (factory_calls.append(1), providers[len(factory_calls) - 1])[1],
        provider_identity="KITE",
        clock=lambda: NOW,
    )
    for provider in providers:
        _authenticate(shared)
        swing = _lease(shared, "SWING")
        intraday = _lease(shared, "INTRADAY")
        shared.end_kronos_session()
        assert not swing.active and not intraday.active
        status = shared.read_only_status()
        assert status["cleanup_state"] == "COMPLETE"
        assert status["owned_work_count"] == 0
        assert status["unresolved_cleanup_count"] == 0
        assert status["retained_lease_count"] == 0
        assert provider.end_count == 1
    assert len(factory_calls) == 20


def test_deadline_expired_factory_result_is_disposed_without_beginning_login() -> None:
    from kronos.provider.services.provider_authentication import (
        ConnectionAttemptDeadline,
        connection_deadline_scope,
    )

    monotonic = [10.0]
    deadline = ConnectionAttemptDeadline(
        generation=1,
        timeout_seconds=5.0,
        monotonic_clock=lambda: monotonic[0],
    )
    provider = _Runtime()

    def factory():  # type: ignore[no-untyped-def]
        monotonic[0] += 6.0
        return provider

    shared = SharedAuthenticatedProviderRuntime(
        factory, provider_identity="KITE", clock=lambda: NOW,
    )
    with connection_deadline_scope(deadline):
        with pytest.raises(TimeoutError):
            shared.begin_login()
    assert provider.begin_count == 0
    assert provider.end_count == 1
    assert shared.read_only_status()["capability_state"] == "ABSENT"


def test_expired_deadline_rejects_lease_publication_and_preserves_committed_success() -> None:
    from kronos.provider.services.provider_authentication import (
        ConnectionAttemptDeadline,
        connection_deadline_scope,
    )

    monotonic = [10.0]
    deadline = ConnectionAttemptDeadline(
        generation=1,
        timeout_seconds=5.0,
        monotonic_clock=lambda: monotonic[0],
    )
    shared, _, _ = _shared()
    with connection_deadline_scope(deadline):
        _authenticate(shared)
    monotonic[0] = 16.0
    assert shared.read_only_status()["capability_state"] == "UNAVAILABLE"
    with pytest.raises(ProviderRuntimeAccessError):
        _lease(shared, "SWING")

    committed = ConnectionAttemptDeadline(
        generation=2,
        timeout_seconds=5.0,
        monotonic_clock=lambda: monotonic[0],
    )
    other, _, _ = _shared()
    with connection_deadline_scope(committed):
        _authenticate(other)
        committed.commit(lambda: None)
    monotonic[0] = 100.0
    assert other.read_only_status()["capability_state"] == "RETAINED_UNEXPIRED"
    assert _lease(other, "SWING").active


def test_duplicate_begin_between_navigation_and_callback_preserves_pending_owner() -> None:
    shared, provider, factory_calls = _shared()
    attempt = shared.begin_login()
    with pytest.raises(
        ProviderRuntimeAccessError,
        match=ProviderRuntimeFailure.CONTEXT_ALREADY_ACTIVE.value,
    ):
        shared.begin_login()
    with pytest.raises(
        ProviderRuntimeAccessError,
        match=ProviderRuntimeFailure.CONTEXT_UNAVAILABLE.value,
    ):
        shared.complete_callback(object())
    assert provider.begin_count == 1
    assert provider.end_count == 0
    assert factory_calls == [1]
    shared.complete_callback(attempt)
    assert shared.lifecycle_state is SharedProviderRuntimeLifecycle.ACTIVE


def test_delayed_old_deadline_projection_cannot_invalidate_replacement_context():
    from kronos.provider.services.provider_authentication import (
        ConnectionAttemptDeadline,
        connection_deadline_scope,
    )
    from threading import current_thread

    first_provider, replacement_provider = _Runtime(), _Runtime()
    providers = iter((first_provider, replacement_provider))
    shared = SharedAuthenticatedProviderRuntime(
        lambda: next(providers), provider_identity="KITE", clock=lambda: NOW,
    )
    expired = ConnectionAttemptDeadline(generation=1, monotonic_clock=lambda: 0.0)
    with connection_deadline_scope(expired):
        _authenticate(shared)
        stale_lease = _lease(shared, "SWING")
    expired.finish("FAILED")
    expired.worker_finished()

    sampled, release = Event(), Event()
    original_snapshot = expired.snapshot

    def delayed_snapshot():
        projection = original_snapshot()
        if current_thread().name == "stale-deadline-lease-projection":
            sampled.set()
            assert release.wait(2.0), "stale deadline projection was not released"
        return projection

    expired.snapshot = delayed_snapshot
    old_results, errors = [], []

    def inspect_old_lease():
        try:
            old_results.append(stale_lease.active)
        except BaseException as error:
            errors.append(error)

    reader = Thread(target=inspect_old_lease, name="stale-deadline-lease-projection")
    reader.start()
    try:
        assert sampled.wait(2.0)
        shared.end_kronos_session()
        replacement = ConnectionAttemptDeadline(
            generation=2, monotonic_clock=lambda: 0.0,
        )
        with connection_deadline_scope(replacement):
            _authenticate(shared)
            replacement.commit(lambda: None)
            current_lease = _lease(shared, "INTRADAY")
        replacement.worker_finished()
        assert current_lease.active
        release.set()
        reader.join(timeout=2.0)
        assert not reader.is_alive()
        assert not errors
        assert old_results == [False]
        assert current_lease.active
        assert shared.lifecycle_state is SharedProviderRuntimeLifecycle.ACTIVE
        assert shared.read_only_status()["capability_state"] == "RETAINED_UNEXPIRED"
        assert replacement_provider.end_count == 0
    finally:
        release.set()
        reader.join(timeout=2.0)
        shared.end_kronos_session()
