from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from threading import Event, Thread
from zoneinfo import ZoneInfo

import pytest

from kronos.application.intraday_discovery_operation import (
    DiscoveryOperationFailure,
    DiscoveryOperationState,
)
from kronos.application.intraday_runtime import create_intraday_runtime
from kronos.browser.intraday_probables_v2_control import (
    IntradayProbablesV2OperationalControl,
)
from kronos.intraday.probables_v2 import (
    PROBABLES_V2_METHODOLOGY_CHECKSUM,
    PROBABLES_V2_METHODOLOGY_IDENTITY,
    PROBABLES_V2_METHODOLOGY_VERSION,
    PROBABLES_V2_SUCCESSOR_METHODOLOGY_VERSION,
    PROBABLES_V2_SUCCESSOR_METHODOLOGY_CHECKSUM,
    PROBABLES_V2_SUCCESSOR_PUBLICATION_IDENTITY,
    PROBABLES_V2_PUBLICATION_IDENTITY,
)
from kronos.intraday.completed_evidence import (
    EvidenceSessionRole,
    IntradayAnalysisPhase,
)
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.discovery import DiscoveryReason
from kronos.intraday.discovery_runtime import DiscoveryMemberFactError
from kronos.intraday.discovery_source import _completed_intraday
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.refresh_v2 import (
    REFRESH_V2_OPERATION_TYPE,
    REFRESH_V2_REQUEST_IDENTITY,
    REFRESH_V2_REQUEST_VERSION,
    RefreshV2Outcome,
)
from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus
from kronos.provider.contracts.market_data import HistoricalCandle
from tests.unit.application.test_intraday_discovery_operation import (
    SEMANTIC_BOUNDARY,
    _authenticate,
    _configured_shared,
    _request_at,
)


IST = ZoneInfo("Asia/Kolkata")


def _payload(
    identity: str = "V2-CONTROL-ONE",
    *,
    boundary: datetime = SEMANTIC_BOUNDARY,
) -> dict[str, str]:
    serialized_boundary = boundary.isoformat()
    return {
        "request_identity": identity,
        "observation_boundary": serialized_boundary,
        "request_created_at": serialized_boundary,
        "source_class": "SPONSOR_BROWSER_CONTROL",
        "contract_identity": REFRESH_V2_REQUEST_IDENTITY,
        "contract_version": REFRESH_V2_REQUEST_VERSION,
        "methodology_identity": PROBABLES_V2_METHODOLOGY_IDENTITY,
        "methodology_version": PROBABLES_V2_SUCCESSOR_METHODOLOGY_VERSION,
        "methodology_publication_identity": PROBABLES_V2_SUCCESSOR_PUBLICATION_IDENTITY,
        "methodology_checksum": PROBABLES_V2_SUCCESSOR_METHODOLOGY_CHECKSUM,
        "operation_type": REFRESH_V2_OPERATION_TYPE,
    }


def _control(
    tmp_path: Path,
    *,
    authenticated: bool = True,
    boundary: datetime = SEMANTIC_BOUNDARY,
):  # type: ignore[no-untyped-def]
    shared, _, factory_calls, provider_requests = _configured_shared()
    if authenticated:
        _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: boundary,
    )
    control = IntradayProbablesV2OperationalControl(
        composition.discovery_v2_operation,
        composition.probables_v2_application,
        composition.refresh_v2_provenance_store,
        clock=lambda: boundary,
        process_identity=lambda: "KRONOS-BACKEND-PID-TEST",
    )
    return shared, composition, control, factory_calls, provider_requests


def test_exact_v2_binding_rejects_before_provider_acquisition(tmp_path: Path) -> None:
    _, _, control, factory_calls, provider_requests = _control(
        tmp_path, authenticated=False
    )
    wrong = {**_payload(), "methodology_checksum": "WRONG"}

    result = control.execute_document(wrong)

    assert result["outcome"] == RefreshV2Outcome.REJECTED.value
    assert result["failure"] == "INTRADAY_PROBABLES_V2_METHODOLOGY_BINDING_INVALID"
    assert factory_calls == []
    assert provider_requests == [0]


def test_success_is_append_only_reloadable_and_idempotent(tmp_path: Path) -> None:
    _, composition, control, _, provider_requests = _control(tmp_path)
    request = _payload()

    first = control.execute_document(request)
    reads = provider_requests[0]
    duplicate = control.execute_document(request)
    retained = composition.refresh_v2_provenance_store.load_for_request(
        request["request_identity"]
    )

    assert first["outcome"] == "SUCCESS"
    assert first["resulting_discovery_identity"]
    assert first["resulting_probables_identity"]
    assert duplicate == {**first, "idempotent": True}
    assert provider_requests == [reads]
    assert retained is not None
    assert retained.provenance_identity == first["provenance_identity"]
    assert retained.outcome is RefreshV2Outcome.SUCCESS
    assert retained.remote_address_class == "LOOPBACK_ADMITTED"
    assert retained.origin_validation == "PASSED_BY_SHARED_BROWSER_ADMISSION"
    assert "token" not in repr(retained).lower()


def test_same_identity_different_content_fails_closed(tmp_path: Path) -> None:
    _, _, control, _, provider_requests = _control(tmp_path)
    request = _payload()
    control.execute_document(request)
    reads = provider_requests[0]
    conflict = {
        **request,
        "observation_boundary": request["observation_boundary"].replace("11:17", "11:18"),
    }

    result = control.execute_document(conflict)

    assert result["outcome"] == "REJECTED"
    assert result["failure"] == "INTRADAY_PROBABLES_V2_REQUEST_IDENTITY_CONFLICT"
    assert provider_requests == [reads]


def test_v1_and_v2_pointers_are_version_isolated(tmp_path: Path) -> None:
    _, composition, control, _, _ = _control(tmp_path)
    v1_pointer = tmp_path / "refresh-v1" / "current-state.json"
    v2_pointer = tmp_path / "refresh-v2" / "CURRENT-PROBABLES-V2.json"

    v2 = control.execute_document(_payload())
    assert v2["outcome"] == "SUCCESS"
    assert not v1_pointer.exists()
    v2_bytes = v2_pointer.read_bytes()

    v1 = composition.discovery_operation.execute(
        _request_at("LEGACY-V1-ISOLATION", SEMANTIC_BOUNDARY)
    )
    assert v1.state is DiscoveryOperationState.COMPLETE
    assert v1_pointer.exists()
    assert v2_pointer.read_bytes() == v2_bytes


def test_active_v2_refresh_rejects_concurrent_v1_before_second_provider_read(
    tmp_path: Path,
) -> None:
    blocked, proceed = Event(), Event()
    shared, _, _, provider_requests = _configured_shared(
        block=blocked,
        proceed=proceed,
    )
    _authenticate(shared)
    composition = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: SEMANTIC_BOUNDARY,
    )
    control = IntradayProbablesV2OperationalControl(
        composition.discovery_v2_operation,
        composition.probables_v2_application,
        composition.refresh_v2_provenance_store,
        clock=lambda: SEMANTIC_BOUNDARY,
        process_identity=lambda: "KRONOS-BACKEND-PID-TEST",
    )
    outcomes: list[dict[str, object]] = []
    thread = Thread(
        target=lambda: outcomes.append(
            control.execute_document(_payload("V2-CONCURRENCY-ACTIVE"))
        )
    )
    thread.start()
    assert blocked.wait(timeout=3)

    v1 = composition.discovery_operation.execute(
        _request_at("V1-CONCURRENT-WITH-V2", SEMANTIC_BOUNDARY)
    )

    assert v1.state is DiscoveryOperationState.CONFLICT
    assert v1.failure is DiscoveryOperationFailure.OPERATION_CONFLICT
    assert provider_requests == [1]

    proceed.set()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert len(outcomes) == 1 and outcomes[0]["outcome"] == "SUCCESS"
    assert provider_requests == [465]


def test_failed_later_v2_preserves_last_success(tmp_path: Path) -> None:
    shared, composition, control, _, provider_requests = _control(tmp_path)
    success = control.execute_document(_payload("V2-SUCCESS"))
    reads = provider_requests[0]
    shared.invalidate("CONTROLLED_TEST_CONTEXT_LOSS")

    failed = control.execute_document(_payload("V2-AFTER-LOSS"))
    snapshot = composition.probables_v2_application.snapshot()

    assert failed["outcome"] == "FAILED"
    assert failed["failure"] == "CONTEXT_UNAVAILABLE"
    assert provider_requests == [reads]
    assert snapshot.last_successful_run_identity == success["resulting_probables_identity"]
    assert snapshot.current_failure is None


def test_v2_execution_produces_v2_only(tmp_path: Path) -> None:
    _, composition, control, _, provider_requests = _control(tmp_path)

    result = control.execute_document(_payload())
    v2 = composition.probables_v2_application.snapshot()

    assert result["outcome"] == "SUCCESS"
    assert v2.run is not None
    assert v2.run.methodology.methodology_identity == PROBABLES_V2_METHODOLOGY_IDENTITY
    assert v2.run.methodology.methodology_version == PROBABLES_V2_SUCCESSOR_METHODOLOGY_VERSION
    assert composition.probables_application.snapshot().run is None
    assert composition.discovery_operation.last_result is None
    assert provider_requests == [465]


def test_v2_opening_allows_zero_completed_current_hour_and_restores_exactly(
    tmp_path: Path,
) -> None:
    boundary = datetime(2026, 8, 24, 9, 35, tzinfo=IST)
    shared, composition, control, _, provider_requests = _control(
        tmp_path,
        boundary=boundary,
    )

    result = control.execute_document(_payload("V2-OPENING-ZERO-1H", boundary=boundary))
    run = composition.probables_v2_application.snapshot().run

    assert result["outcome"] == "SUCCESS"
    assert run is not None
    retained_result = next(
        item for item in run.results if item.source_mapping_identity is not None
    )
    mapping = ProbablesV2Store(tmp_path.resolve()).load_mapping(
        retained_result.source_mapping_identity
    )
    assert mapping.phase is IntradayAnalysisPhase.OPENING
    assert mapping.completed_evidence.candles(
        IntradayTimeframe.ONE_HOUR,
        EvidenceSessionRole.CURRENT_SESSION_1H_PRIMARY,
    ) == ()
    assert len(mapping.completed_evidence.candles(
        IntradayTimeframe.ONE_HOUR,
        EvidenceSessionRole.PRIOR_SESSION_1H_CONTEXT,
    )) >= 2
    reads = provider_requests[0]

    restored = create_intraday_runtime(
        shared,
        evidence_root=tmp_path.resolve(),
        clock=lambda: boundary,
    ).probables_v2_application.snapshot().run

    assert restored == run
    assert provider_requests == [reads]


def test_current_hour_empty_set_is_v2_only_and_missing_completed_hour_fails_closed() -> None:
    trading_day = date(2026, 8, 24)
    opened = datetime.combine(trading_day, time(9, 15), IST)
    schedule = MarketDaySchedule(
        exchange="NSE",
        trading_date=trading_day,
        session_id="NSE:2026-08-24:REGULAR",
        timezone="Asia/Kolkata",
        status=TradingDayStatus.TRADING,
        windows=(MarketWindow(
            opens_at=opened,
            closes_at=datetime.combine(trading_day, time(15, 30), IST),
        ),),
        source_identity="KRONOS-MARKET-CALENDAR-V1/TEST",
        source_version="1",
    )
    opening_boundary = datetime.combine(trading_day, time(9, 35), IST)
    forming = HistoricalCandle(opened, 100.0, 102.0, 99.0, 101.0, 1000)

    assert _completed_intraday(
        candles=(forming,),
        schedule=schedule,
        timeframe=IntradayTimeframe.ONE_HOUR,
        observed_at=opening_boundary,
        allow_domain008_empty=True,
    ) == ()

    with pytest.raises(DiscoveryMemberFactError) as legacy_error:
        _completed_intraday(
            candles=(forming,),
            schedule=schedule,
            timeframe=IntradayTimeframe.ONE_HOUR,
            observed_at=opening_boundary,
        )
    assert legacy_error.value.reason is DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE

    first_completed_boundary = datetime.combine(trading_day, time(10, 20), IST)
    with pytest.raises(DiscoveryMemberFactError) as missing_error:
        _completed_intraday(
            candles=(),
            schedule=schedule,
            timeframe=IntradayTimeframe.ONE_HOUR,
            observed_at=first_completed_boundary,
            allow_domain008_empty=True,
        )
    assert missing_error.value.reason is DiscoveryReason.MACHINE_FACT_BUNDLE_INCOMPLETE
