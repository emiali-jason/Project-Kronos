from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Event, Thread
from zoneinfo import ZoneInfo

from kronos.application.intraday_discovery_operation import (
    DiscoveryOperationFailure,
    DiscoveryOperationStage,
    DiscoveryOperationState,
    create_discovery_operation_request,
)
from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.browser.intraday_views import (
    _render_discovery_detail,
    render_intraday_triage,
)
from kronos.intraday.discovery import DiscoveryError, DiscoveryFailure
from kronos.intraday.probables import ProbablesError, ProbablesFailure
from kronos.intraday.reconciliation import (
    Availability,
    RECONCILIATION_IDENTITY,
    RECONCILIATION_VERSION,
)
from kronos.intraday.reconciliation_persistence import IntradayReconciliationStore
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import HistoricalCandle, HistoricalInterval
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from tests.unit.provider.test_shared_provider_runtime import _authenticate, _shared


IST = ZoneInfo("Asia/Kolkata")
OBSERVED = datetime(2026, 8, 24, 10, 17, tzinfo=IST)
SEMANTIC_BOUNDARY = datetime(2026, 8, 24, 11, 17, tzinfo=IST)
UNIVERSE_VALID_FROM = datetime(2026, 8, 22, 0, 0, tzinfo=IST)


def _configured_shared(
    *,
    block: Event | None = None,
    proceed: Event | None = None,
):  # type: ignore[no-untyped-def]
    reconciliation = IntradayReconciliationStore().load(
        publication_identity=RECONCILIATION_IDENTITY,
        publication_version=RECONCILIATION_VERSION,
    )
    records = tuple(
        InstrumentRecord(
            provider="KITE",
            exchange=member.exchange,
            segment=("INDICES" if member.sponsor_label in {"NIFTY", "BANKNIFTY"} else "NSE"),
            trading_symbol=member.provider_symbol,
            name=member.sponsor_label,
            instrument_type="EQ",
            expiry=None,
            tick_size=Decimal("0.05"),
            lot_size=1,
        )
        for member in reconciliation.members
        if member.dimensions.machine_fact_consumability is Availability.AVAILABLE
        and member.provider_symbol is not None
    )
    shared, runtime, factory_calls = _shared()
    request_count = [0]

    def instrument_records(exchange):  # type: ignore[no-untyped-def]
        return tuple(item for item in records if item.exchange == exchange)

    def historical_candles(request):  # type: ignore[no-untyped-def]
        request_count[0] += 1
        if block is not None and request_count[0] == 1:
            block.set()
            assert proceed is not None and proceed.wait(timeout=3)
        if request.interval is HistoricalInterval.DAY:
            return (_candle(request.start),)
        step = {
            HistoricalInterval.SIXTY_MINUTE: timedelta(hours=1),
            HistoricalInterval.FIFTEEN_MINUTE: timedelta(minutes=15),
            HistoricalInterval.FIVE_MINUTE: timedelta(minutes=5),
        }[request.interval]
        values = []
        cursor = request.start
        while cursor <= request.end:
            values.append(_candle(cursor))
            cursor += step
        return tuple(values)

    runtime.capability.instrument_records = instrument_records  # type: ignore[method-assign]
    runtime.capability.historical_candles = historical_candles  # type: ignore[method-assign]
    return shared, runtime, factory_calls, request_count


def _candle(timestamp: datetime) -> HistoricalCandle:
    return HistoricalCandle(timestamp, 100.0, 102.0, 99.0, 101.0, 1000)


def _request(name: str):  # type: ignore[no-untyped-def]
    return create_discovery_operation_request(
        observation_boundary=OBSERVED,
        request_identity=name,
        requested_at=OBSERVED,
    )


def _request_at(name: str, observed_at: datetime):  # type: ignore[no-untyped-def]
    return create_discovery_operation_request(
        observation_boundary=observed_at,
        request_identity=name,
        requested_at=observed_at,
    )


def test_context_verification_is_actual_and_startup_has_no_side_effect(tmp_path: Path) -> None:
    shared, _, factory_calls, request_count = _configured_shared()
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: OBSERVED,
    )

    assert composition.discovery_operation.operation_available is False
    assert composition.discovery_operation.actual_context_state == "ABSENT"
    assert composition.discovery_operation.last_result is None
    assert request_count == [0]
    assert factory_calls == []

    result = composition.discovery_operation.execute(_request("NO-CONTEXT"))
    assert result.state is DiscoveryOperationState.FAILED
    assert result.failure is DiscoveryOperationFailure.CONTEXT_UNAVAILABLE
    assert result.context_state == "ABSENT"
    assert result.probables_invocation_count == 0
    assert result.probables_run_identity is None
    assert request_count == [0]
    assert factory_calls == []


def test_one_refresh_resolves_and_processes_all_five_mcx_subjects(
    tmp_path: Path,
) -> None:
    from tests.unit.instrument.test_active_derivative_selection import _rows

    shared, runtime, _, request_count = _configured_shared()
    runtime.capability.instrument_master_records = lambda: _rows()  # type: ignore[method-assign]
    _authenticate(shared)
    boundary = datetime(2026, 8, 26, 10, 17, tzinfo=IST)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: boundary,
    )

    result = composition.discovery_operation.execute(
        _request_at("MCX-FIVE", boundary)
    )
    resolutions = composition.discovery_operation.last_active_derivative_resolutions

    assert result.state is DiscoveryOperationState.COMPLETE
    assert result.universe_count == result.pre_evaluable_count == 98
    assert result.prerequisite_unavailable_count == 0
    assert result.machine_fact_successes == 98
    assert result.machine_fact_failures == 0
    assert result.historical_request_count == request_count[0] == 392
    assert composition.discovery_operation.last_instrument_master_read_count == 1
    assert resolutions is not None and len(resolutions.successful_bindings) == 5
    assert {item.analytical_subject for item in resolutions.successful_bindings} == {
        "GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE"
    }
    snapshot = composition.discovery_application.snapshot("MCX-SUBJECT-GOLDM")
    mcx = tuple(item for item in snapshot.members if item.market_family == "MCX")
    assert len(mcx) == 5
    assert all(item.prerequisite_ready and item.analysis_contract for item in mcx)
    main_page = render_intraday_triage(snapshot)
    detail_page = _render_discovery_detail(snapshot)
    assert "GOLDM26SEPFUT" not in main_page
    assert "Analysis contract" in detail_page
    assert "GOLDM26SEPFUT" in detail_page
    assert "Provider Token" not in detail_page

    provider_reads = runtime.capability.calls
    historical_reads = request_count[0]
    restored = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: boundary,
    ).discovery_application.snapshot()
    restored_mcx = tuple(
        item for item in restored.members if item.market_family == "MCX"
    )
    assert runtime.capability.calls == provider_reads == 0
    assert request_count[0] == historical_reads
    assert tuple(
        (item.sponsor_label, item.analysis_contract, item.active_binding_identity)
        for item in restored_mcx
    ) == tuple(
        (item.sponsor_label, item.analysis_contract, item.active_binding_identity)
        for item in mcx
    )

def test_explicit_operation_reuses_one_context_and_is_idempotent(tmp_path: Path) -> None:
    shared, _, factory_calls, request_count = _configured_shared()
    _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: OBSERVED,
    )
    assert request_count == [0]
    assert shared.active_lease_count == 0

    lease = composition.provider_access.acquire_discovery_lease()
    assert lease.operations == frozenset({
        ReadOnlyProviderOperation.INSTRUMENTS,
        ReadOnlyProviderOperation.HISTORICAL_DATA,
    })
    assert not hasattr(lease, "place_order")
    assert not hasattr(lease, "begin_login")
    lease.release()

    request = _request("CONTROLLED-ONE")
    result = composition.discovery_operation.execute(request)
    duplicate = composition.discovery_operation.execute(request)

    assert result is duplicate
    assert result.state is DiscoveryOperationState.COMPLETE
    assert result.context_state == "ACTIVE"
    assert result.universe_count == 98
    assert result.pre_evaluable_count == 98
    assert result.prerequisite_unavailable_count == 0
    assert result.machine_fact_successes == 93
    assert result.machine_fact_failures == 5
    assert result.historical_request_count == request_count[0] == 372
    assert result.persistence_complete and result.snapshot_updated
    assert result.run_identity is not None
    assert result.probables_run_identity is not None
    assert result.probables_mapping_identity is not None
    assert result.probables_invocation_count == 1
    assert result.probables_provider_request_count == 0
    assert shared.active_lease_count == 0
    assert factory_calls == [1]
    snapshot = composition.discovery_application.snapshot("RELIANCE")
    assert snapshot.last_successful_run_identity == result.run_identity
    assert snapshot.machine_fact_success_count == 93
    assert snapshot.candidate_admitted_count == 0
    assert snapshot.candidate_not_admitted_count == 0
    assert snapshot.probables is not None
    assert snapshot.probables.last_successful_run_identity == (
        result.probables_run_identity
    )
    assert snapshot.probables.run is not None
    assert snapshot.probables.run.source_run_identity == result.run_identity
    assert snapshot.probables.run.observation_boundary == result.observation_boundary
    assert composition.probables_application.snapshot().run == (
        composition.probables_application._store.load_run(
            run_identity=result.probables_run_identity
        )
    )
    calls_before_render = request_count[0]
    rendered = render_intraday_triage(snapshot)
    assert request_count[0] == calls_before_render
    assert "Provider Token" not in rendered
    assert "PLACE ORDER" not in rendered
    assert "token" not in repr(result).lower()


def test_completed_discovery_semantics_map_to_exact_probables_run(
    tmp_path: Path,
) -> None:
    shared, _, factory_calls, request_count = _configured_shared()
    _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: SEMANTIC_BOUNDARY,
    )

    result = composition.discovery_operation.execute(
        _request_at("SEMANTIC-EVIDENCE", SEMANTIC_BOUNDARY)
    )
    probable = composition.probables_application.snapshot()

    assert result.state is DiscoveryOperationState.COMPLETE
    assert result.run_identity is not None
    assert result.probables_run_identity is not None
    assert result.probables_invocation_count == 1
    assert result.probables_provider_request_count == 0
    assert probable.run is not None
    assert probable.run.run_identity == result.probables_run_identity
    assert probable.run.source_run_identity == result.run_identity
    assert probable.run.observation_boundary == result.observation_boundary
    assert probable.run.universe_identity == (
        composition.discovery_operation._universe.publication_identity
    )
    assert probable.run.reconciliation_identity == (
        composition.discovery_operation._reconciliation.publication_identity
    )
    assert probable.run.diagnostics.evaluable_count == 93
    assert probable.run.diagnostics.unavailable_count == 5
    assert all(
        item.lineage.semantic_evidence_identity is not None
        for item in probable.run.results
        if item.canonical_subject_identity.startswith(("NSE-", "NSE_"))
    )
    assert request_count == [372]
    assert factory_calls == [1]


def test_active_operation_blocks_same_and_different_identity(tmp_path: Path) -> None:
    blocked, proceed = Event(), Event()
    shared, _, factory_calls, request_count = _configured_shared(
        block=blocked,
        proceed=proceed,
    )
    _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: OBSERVED,
    )
    first_request = _request("ACTIVE")
    outcome = []
    thread = Thread(
        target=lambda: outcome.append(
            composition.discovery_operation.execute(first_request)
        )
    )
    thread.start()
    assert blocked.wait(timeout=3)

    same = composition.discovery_operation.execute(first_request)
    different = composition.discovery_operation.execute(_request("DIFFERENT"))
    assert same.state is different.state is DiscoveryOperationState.CONFLICT
    assert same.failure is different.failure is DiscoveryOperationFailure.OPERATION_CONFLICT
    assert request_count == [1]

    proceed.set()
    thread.join(timeout=5)
    assert len(outcome) == 1
    assert outcome[0].state is DiscoveryOperationState.COMPLETE
    assert request_count == [372]
    assert factory_calls == [1]


def test_raw_provider_failure_becomes_bounded_member_failures(tmp_path: Path) -> None:
    shared, runtime, factory_calls, request_count = _configured_shared()

    def unsafe_failure(_request):  # type: ignore[no-untyped-def]
        request_count[0] += 1
        raise RuntimeError("access_token=PRIVATE provider_record={raw}")

    runtime.capability.historical_candles = unsafe_failure  # type: ignore[method-assign]
    _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: OBSERVED,
    )

    result = composition.discovery_operation.execute(_request("SANITIZED"))

    assert result.state is DiscoveryOperationState.COMPLETE
    assert result.machine_fact_successes == 0
    assert result.machine_fact_failures == 98
    assert result.historical_request_count == request_count[0] == 93
    assert "access_token" not in repr(result)
    assert "provider_record" not in repr(result)
    assert factory_calls == [1]


def test_failed_later_operation_preserves_last_success_and_restart(tmp_path: Path) -> None:
    shared, _, _, _ = _configured_shared()
    _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: OBSERVED,
    )
    success = composition.discovery_operation.execute(_request("SUCCESS"))
    assert success.run_identity is not None
    assert success.probables_run_identity is not None
    shared.invalidate("CONTROLLED_CONTEXT_LOSS")

    failed = composition.discovery_operation.execute(_request("AFTER-LOSS"))
    snapshot = composition.discovery_application.snapshot("RELIANCE")
    assert failed.failure is DiscoveryOperationFailure.CONTEXT_UNAVAILABLE
    assert snapshot.last_successful_run_identity == success.run_identity
    assert snapshot.current_failure == DiscoveryOperationFailure.CONTEXT_UNAVAILABLE.value
    assert snapshot.probables is not None
    assert snapshot.probables.last_successful_run_identity == (
        success.probables_run_identity
    )
    assert snapshot.probables.current_failure is None

    restarted_shared, _, factory_calls = _shared()
    restarted = create_intraday_runtime(
        restarted_shared,
        evidence_root=tmp_path.resolve(),
        last_successful_discovery_run_identity=success.run_identity,
        clock=lambda: OBSERVED,
    )
    restored = restarted.discovery_application.snapshot("RELIANCE")
    assert restored.last_successful_run_identity == success.run_identity
    assert restored.machine_fact_success_count == 93
    assert restored.probables is not None
    assert restored.probables.last_successful_run_identity == (
        success.probables_run_identity
    )
    assert restored.current_failure == DiscoveryOperationFailure.CONTEXT_UNAVAILABLE.value
    assert restarted.discovery_operation.actual_context_state == "ABSENT"
    assert factory_calls == []


def test_probables_failure_preserves_discovery_and_prior_probables_success(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    shared, _, _, request_count = _configured_shared()
    _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: OBSERVED,
    )
    success = composition.discovery_operation.execute(_request("PROBABLES-A"))
    assert success.run_identity is not None
    assert success.probables_run_identity is not None

    invocation_count = [0]

    def fail_probables(**_kwargs):  # type: ignore[no-untyped-def]
        invocation_count[0] += 1
        raise ProbablesError(ProbablesFailure.INTEGRITY_INVALID)

    monkeypatch.setattr(
        composition.probables_application,
        "refresh_analysis",
        fail_probables,
    )
    failed = composition.discovery_operation.execute(_request("PROBABLES-B"))
    snapshot = composition.discovery_application.snapshot()

    assert failed.state is DiscoveryOperationState.FAILED
    assert failed.stage is DiscoveryOperationStage.PROBABLES_INVOCATION
    assert failed.failure is DiscoveryOperationFailure.PROBABLES_REFRESH_FAILURE
    assert failed.run_identity == success.run_identity
    assert failed.probables_run_identity is None
    assert failed.persistence_complete and failed.snapshot_updated
    assert invocation_count == [1]
    assert request_count == [744]
    assert snapshot.last_successful_run_identity == success.run_identity
    assert snapshot.current_failure is None
    assert snapshot.probables is not None
    assert snapshot.probables.last_successful_run_identity == (
        success.probables_run_identity
    )
    assert snapshot.probables.current_failure == (
        DiscoveryOperationFailure.PROBABLES_REFRESH_FAILURE.value
    )


def test_publication_validity_fails_closed_before_provider_acquisition(
    tmp_path: Path,
) -> None:
    shared, _, factory_calls, request_count = _configured_shared()
    _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: OBSERVED,
    )
    valid_from = composition.discovery_operation._universe.valid_from
    before_validity = datetime(2026, 8, 21, 15, 30, tzinfo=IST)

    result = composition.discovery_operation.execute(
        _request_at("PUBLICATION-STALE", before_validity)
    )

    assert valid_from == UNIVERSE_VALID_FROM
    assert result.state is DiscoveryOperationState.FAILED
    assert result.stage is DiscoveryOperationStage.UNIVERSE_RESOLUTION
    assert result.failure is DiscoveryOperationFailure.PUBLICATION_STALE
    assert result.historical_request_count == 0
    assert result.run_identity is None
    assert not result.persistence_complete
    assert not result.snapshot_updated
    assert request_count == [0]
    assert factory_calls == [1]
    assert composition.discovery_application.snapshot().last_successful_run_identity is None
    rendered = repr(result)
    assert "access_token" not in rendered
    assert "provider_record" not in rendered
    assert "traceback" not in rendered.lower()


def test_publication_validity_gate_defers_at_and_after_valid_from_to_domain_008(
    tmp_path: Path,
) -> None:
    shared, _, factory_calls, request_count = _configured_shared()
    _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: OBSERVED,
    )

    at_validity = composition.discovery_operation.execute(
        _request_at("AT-VALID-FROM", UNIVERSE_VALID_FROM)
    )
    after_validity = composition.discovery_operation.execute(
        _request_at("AFTER-VALID-FROM", UNIVERSE_VALID_FROM + timedelta(hours=12))
    )

    for result in (at_validity, after_validity):
        assert result.stage is DiscoveryOperationStage.OBSERVATION_BOUNDARY
        assert result.failure is DiscoveryOperationFailure.MARKET_SESSION_UNAVAILABLE
        assert result.failure is not DiscoveryOperationFailure.PUBLICATION_STALE
        assert result.historical_request_count == 0
    assert result.run_identity is None
    assert request_count == [0]
    assert factory_calls == [1]
    assert composition.discovery_operation._universe.valid_from == UNIVERSE_VALID_FROM


def test_existing_typed_discovery_failures_survive_operation_boundary(
    tmp_path: Path,
) -> None:
    failures = (
        DiscoveryFailure.PUBLICATION_STALE,
        DiscoveryFailure.SOURCE_STALE,
        DiscoveryFailure.INTEGRITY_INVALID,
        DiscoveryFailure.MARKET_SESSION_UNAVAILABLE,
        DiscoveryFailure.MACHINE_FACT_BUNDLE_INCOMPLETE,
        DiscoveryFailure.OBSERVATION_BOUNDARY_INVALID,
        DiscoveryFailure.INCOMPLETE_CANDLE_NOT_AUTHORIZED,
    )
    for index, governed_failure in enumerate(failures):
        shared, _, factory_calls, request_count = _configured_shared()
        _authenticate(shared)
        composition = create_intraday_runtime(
            shared,
            evidence_root=(tmp_path / str(index)).resolve(),
            clock=lambda: OBSERVED,
        )

        def typed_boundary(_observed_at, failure=governed_failure):  # type: ignore[no-untyped-def]
            raise DiscoveryError(failure)

        composition.discovery_operation._boundary = typed_boundary  # type: ignore[method-assign]
        result = composition.discovery_operation.execute(
            _request(f"TYPED-{index}")
        )

        assert result.stage is DiscoveryOperationStage.OBSERVATION_BOUNDARY
        assert result.failure.value == governed_failure.value
        assert result.historical_request_count == 0
        assert request_count == [0]
        assert factory_calls == [1]


def test_publication_stale_preserves_last_successful_application_truth(
    tmp_path: Path,
) -> None:
    shared, _, factory_calls, request_count = _configured_shared()
    _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: OBSERVED,
    )
    success = composition.discovery_operation.execute(_request("VALID-SUCCESS"))
    stale = composition.discovery_operation.execute(
        _request_at(
            "STALE-AFTER-SUCCESS",
            datetime(2026, 8, 21, 15, 30, tzinfo=IST),
        )
    )
    snapshot = composition.discovery_application.snapshot()

    assert success.run_identity is not None
    assert stale.failure is DiscoveryOperationFailure.PUBLICATION_STALE
    assert stale.run_identity is None
    assert snapshot.last_successful_run_identity == success.run_identity
    assert snapshot.current_failure == DiscoveryOperationFailure.PUBLICATION_STALE.value
    assert request_count == [372]
    assert factory_calls == [1]
