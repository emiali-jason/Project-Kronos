"""WO-05A: real operation boundaries with isolated Provider doubles only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.application.intraday_discovery import IntradayDiscoveryApplication
from kronos.application.intraday_discovery_operation import (
    create_discovery_operation_request,
)
from kronos.browser.intraday_discovery_control import IntradayDiscoveryOperationalControl
from kronos.intraday.analysis_time import AnalysisTimeAdmissionError, admit_analysis_time
from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.discovery import DiscoveryFailure, discovery_run_bytes
from kronos.intraday.discovery_persistence import NativeDiscoveryStore
from kronos.intraday.discovery_runtime import (
    DiscoveryMemberFactError, DiscoveryRunBoundary, IntradayNativeDiscoveryService,
)
from kronos.intraday.discovery_source import _completed_intraday
from kronos.intraday.market_context import CurrentMarketCalendarScheduleSource
from kronos.intraday.refresh_v2 import _identity
from kronos.intraday.refresh_v2_persistence import _decoded, _encoded
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.market_data import HistoricalCandle
from tests.unit.intraday.test_discovery_runtime import _publications, _Facts
from tests.unit.intraday.test_probables_v2_refresh_control import _control, _payload

IST = ZoneInfo("Asia/Kolkata")
REQUESTED = datetime(2026, 8, 24, 9, 30, tzinfo=IST)
TRUSTED = REQUESTED - timedelta(minutes=1)


def _native(tmp_path, clock):
    universe, reconciliation = _publications()
    source = _Facts(reconciliation)
    store = NativeDiscoveryStore(tmp_path.resolve())
    service = IntradayNativeDiscoveryService(
        universe=universe, reconciliation=reconciliation, factual_source=source,
        store=store, clock=clock,
    )
    app = IntradayDiscoveryApplication(
        universe=universe, reconciliation=reconciliation, store=store, service=service,
    )
    return service, app, source, store


def _boundary(value):
    return DiscoveryRunBoundary(value, "WO05A-FIXTURE-SESSION", "WO05A-FIXTURE-BOUNDARY")


@pytest.mark.parametrize("offset", [timedelta(microseconds=1), timedelta(minutes=1), timedelta(days=1)])
def test_no_future_grace_period(offset):
    with pytest.raises(AnalysisTimeAdmissionError) as caught:
        admit_analysis_time(TRUSTED + offset, lambda: TRUSTED)
    assert caught.value.failure is DiscoveryFailure.OBSERVATION_BOUNDARY_FUTURE
    assert caught.value.requested_boundary == TRUSTED + offset
    assert caught.value.trusted_admission_time == TRUSTED


@pytest.mark.parametrize("requested", [REQUESTED, REQUESTED.astimezone(timezone.utc), REQUESTED - timedelta(hours=3)])
def test_equality_equivalent_offset_and_history_are_admitted_without_replacement(requested):
    assert admit_analysis_time(requested, lambda: REQUESTED) is REQUESTED


def test_naive_request_and_bad_clock_fail_closed():
    with pytest.raises(AnalysisTimeAdmissionError) as caught:
        admit_analysis_time(REQUESTED.replace(tzinfo=None), lambda: REQUESTED)
    assert caught.value.failure is DiscoveryFailure.OBSERVATION_BOUNDARY_INVALID
    for clock in (lambda: REQUESTED.replace(tzinfo=None), lambda: None):
        with pytest.raises(AnalysisTimeAdmissionError) as caught:
            admit_analysis_time(REQUESTED, clock)
        assert caught.value.failure is DiscoveryFailure.TRUSTED_TIME_UNAVAILABLE


def test_clock_exception_is_sanitized():
    def broken():
        raise RuntimeError("PRIVATE-CLOCK-DETAIL")
    with pytest.raises(AnalysisTimeAdmissionError) as caught:
        admit_analysis_time(REQUESTED, broken)
    assert str(caught.value) == "TRUSTED_TIME_UNAVAILABLE"


@pytest.mark.parametrize("path", ["v2-control", "legacy-control", "v2-operation", "legacy-operation"])
def test_every_operation_path_rejects_before_any_acquisition(tmp_path, path, monkeypatch):
    _, composition, control, _, historical_requests = _control(tmp_path, boundary=TRUSTED)
    operation = composition.discovery_v2_operation if path.startswith("v2") else composition.discovery_operation
    touched = []
    def forbidden(*args, **kwargs):
        touched.append("ACQUISITION")
        raise AssertionError("Future boundary reached acquisition")
    monkeypatch.setattr(operation, "_acquire_lease", forbidden)
    monkeypatch.setattr(operation, "_source_factory", forbidden)
    monkeypatch.setattr("kronos.application.intraday_discovery_operation.ProviderInstrumentMasterAcquisitionService", forbidden)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    if path == "v2-control":
        result = control.execute_document(_payload("FUTURE", boundary=REQUESTED))
        assert result["outcome"] == "REJECTED"
        retained = composition.refresh_v2_provenance_store.load_for_request("FUTURE")
        assert retained.observation_boundary == REQUESTED
        assert retained.received_at == TRUSTED
        assert retained.trusted_admission_time == TRUSTED
        assert retained.operation_started_at is None
        assert retained.resulting_discovery_identity is None
        assert retained.resulting_probables_identity is None
        assert retained.contract_version == "1.2.0"
        assert _decoded(_encoded(retained)) == retained
    elif path == "legacy-control":
        result = IntradayDiscoveryOperationalControl(operation, composition.discovery_application).execute_document({
            "request_identity": "FUTURE", "observation_boundary": REQUESTED.isoformat(),
        })
        assert result["trusted_admission_time"] == TRUSTED.isoformat()
        assert result["run_identity"] is None
    else:
        outcome = operation.execute(create_discovery_operation_request(
            observation_boundary=REQUESTED, request_identity="FUTURE",
        ))
        result = {"failure": outcome.failure.value}
        assert outcome.observation_boundary == REQUESTED
        assert outcome.trusted_admission_time == TRUSTED
        assert outcome.run_identity is None
        assert outcome.probables_invocation_count == 0
        assert not outcome.persistence_complete and not outcome.snapshot_updated
    assert result["failure"] == "OBSERVATION_BOUNDARY_FUTURE"
    assert historical_requests == [0] and touched == []
    assert operation.active_operation_identity is None
    assert composition.discovery_application.snapshot().last_successful_run_identity is None
    assert all(Path(p).read_bytes() == value for p, value in before.items())
    new_paths = {str(p) for p in tmp_path.rglob("*.json")} - set(before)
    assert all("request-provenance" in p for p in new_paths)


@pytest.mark.parametrize("through_application", [False, True])
def test_direct_native_service_and_application_reject_before_source(tmp_path, through_application):
    service, app, source, _ = _native(tmp_path, lambda: TRUSTED)
    invoke = app.run_discovery if through_application else service.execute
    with pytest.raises(AnalysisTimeAdmissionError) as caught:
        invoke(_boundary(REQUESTED))
    assert caught.value.failure is DiscoveryFailure.OBSERVATION_BOUNDARY_FUTURE
    assert source.labels == [] and list(tmp_path.rglob("*.json")) == []


@pytest.mark.parametrize("timeframe", list(IntradayTimeframe))
def test_guard_preserves_governed_completion_edges(tmp_path, timeframe):
    schedule = CurrentMarketCalendarScheduleSource(
        MarketCalendarPublisher(), observed_at=TRUSTED, canonical_instrument_id="RELIANCE",
    ).schedule_for("NSE", REQUESTED.date())
    edge = expected_candle_boundaries(schedule, timeframe)[0]
    endpoint = edge.end
    trusted = endpoint - timedelta(microseconds=1)
    with pytest.raises(AnalysisTimeAdmissionError):
        admit_analysis_time(endpoint, lambda: trusted)
    assert admit_analysis_time(endpoint, lambda: endpoint) == endpoint
    service, _, source, _ = _native(tmp_path / "future", lambda: trusted)
    with pytest.raises(AnalysisTimeAdmissionError):
        service.execute(_boundary(endpoint))
    assert source.labels == []
    current, _, current_source, _ = _native(tmp_path / "current", lambda: endpoint)
    assert current.execute(_boundary(endpoint)).run.observation_boundary == endpoint
    assert current_source.labels
    # DOMAIN-008/candle code remains the sole endpoint authority, including Daily.
    assert expected_candle_boundaries(schedule, timeframe)[0] == edge


def test_premature_fifteen_minute_completion_cannot_be_reached(tmp_path):
    schedule = CurrentMarketCalendarScheduleSource(
        MarketCalendarPublisher(), observed_at=TRUSTED, canonical_instrument_id="RELIANCE",
    ).schedule_for("NSE", REQUESTED.date())
    candle = HistoricalCandle(REQUESTED.replace(minute=15), 100., 102., 99., 101., 100)
    with pytest.raises(DiscoveryMemberFactError):
        _completed_intraday(candles=(candle,), schedule=schedule,
            timeframe=IntradayTimeframe.FIFTEEN_MINUTES, observed_at=TRUSTED)
    assert _completed_intraday(candles=(candle,), schedule=schedule,
        timeframe=IntradayTimeframe.FIFTEEN_MINUTES, observed_at=REQUESTED) == (candle,)
    service, _, source, _ = _native(tmp_path, lambda: TRUSTED)
    with pytest.raises(AnalysisTimeAdmissionError):
        service.execute(_boundary(REQUESTED))
    assert source.labels == []  # Pure completion primitive remains lawful; operation cannot reach it early.


@pytest.mark.parametrize("requested, trusted", [
    (REQUESTED, REQUESTED),
    (REQUESTED.replace(hour=10, minute=0), REQUESTED.replace(hour=13, minute=0)),
])
def test_equal_and_historical_operations_retain_requested_time_and_replay(tmp_path, requested, trusted):
    _, c, control, _, requests = _control(tmp_path, boundary=trusted)
    payload = _payload("VALID-TIME", boundary=requested)
    result = control.execute_document(payload)
    assert result["outcome"] == "SUCCESS"
    assert requests[0] > 0
    record = c.refresh_v2_provenance_store.load_for_request("VALID-TIME")
    assert record.observation_boundary == requested
    assert record.trusted_admission_time == trusted
    run = c.probables_v2_application.store.load_current_run()
    assert run.analysis_boundary == requested
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    reads = requests[0]
    assert control.execute_document(payload) == {**result, "idempotent": True}
    assert requests[0] == reads
    assert all(Path(p).read_bytes() == value for p, value in before.items())
    assert c.probables_v2_application.store.load_run(run.run_identity) == run


def test_historical_native_identity_does_not_depend_on_admission_clock(tmp_path):
    first, _, _, store = _native(tmp_path / "first", lambda: REQUESTED)
    second, _, _, _ = _native(tmp_path / "second", lambda: REQUESTED.replace(hour=13))
    a = first.execute(_boundary(REQUESTED)).run
    b = second.execute(_boundary(REQUESTED)).run
    assert discovery_run_bytes(a) == discovery_run_bytes(b)
    assert store.load_run(run_identity=a.run_identity) == a


def test_concurrent_clocks_are_instance_bound(tmp_path):
    future, _, source, _ = _native(tmp_path / "future", lambda: TRUSTED)
    current, _, _, _ = _native(tmp_path / "current", lambda: REQUESTED)
    def invoke(service):
        try:
            return service.execute(_boundary(REQUESTED)).run
        except AnalysisTimeAdmissionError as error:
            return error.failure
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(invoke, [future, current]))
    assert a is DiscoveryFailure.OBSERVATION_BOUNDARY_FUTURE
    assert b.observation_boundary == REQUESTED
    assert source.labels == []


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0"])
def test_old_provenance_restores_without_fabricated_admission_time(tmp_path, version):
    _, c, control, _, _ = _control(tmp_path, boundary=TRUSTED)
    control.execute_document(_payload("FUTURE-OLD", boundary=REQUESTED))
    record = c.refresh_v2_provenance_store.load_for_request("FUTURE-OLD")
    values = json.loads(_encoded(record))
    values.pop("trusted_admission_time")
    values["contract_version"] = version
    values["failure"] = "HISTORICAL-FAILURE"
    core = {k: v for k, v in values.items() if k not in {"provenance_identity", "integrity_identity"}}
    if version == "1.0.0":
        core.pop("replay_envelope_identity")
        core.pop("failure_detail_identity")
    values["provenance_identity"] = _identity("INTRADAY-PROBABLES-V2-REQUEST-PROVENANCE-", core)
    values["integrity_identity"] = _identity("INTEGRITY-INTRADAY-PROBABLES-V2-REQUEST-PROVENANCE-", core)
    encoded = (json.dumps(values, sort_keys=True, separators=(",", ":")) + "\n").encode()
    restored = _decoded(encoded)
    assert restored.trusted_admission_time is None
    assert _encoded(restored) == encoded


def test_admission_time_tampering_rejects(tmp_path):
    _, c, control, _, _ = _control(tmp_path, boundary=TRUSTED)
    control.execute_document(_payload("TAMPER", boundary=REQUESTED))
    record = c.refresh_v2_provenance_store.load_for_request("TAMPER")
    encoded = _encoded(record)
    tampered = json.loads(encoded)
    tampered["trusted_admission_time"] = REQUESTED.isoformat()
    with pytest.raises(ValueError):
        _decoded(json.dumps(tampered).encode())


def test_v2_browser_route_returns_typed_bad_request_before_provider(tmp_path):
    from kronos.browser.intraday_routes import IntradayBrowserRoutes
    from kronos.browser.product_routes import BrowserPostRequest
    from tests.unit.browser.test_product_route_isolation import _snapshot
    _, c, control, _, requests = _control(tmp_path, boundary=TRUSTED)
    routes = IntradayBrowserRoutes(c.workstation, probables_v2_control=control)
    response = routes.handle_post(BrowserPostRequest(
        path="/control/intraday-discovery/v2", query={},
        content_type="application/json",
        body=json.dumps(_payload("BROWSER-FUTURE", boundary=REQUESTED)).encode(),
    ), _snapshot)
    assert response.status == 400
    document = json.loads(response.body)
    assert document["outcome"] == "REJECTED"
    assert document["failure"] == "OBSERVATION_BOUNDARY_FUTURE"
    assert document["trusted_admission_time"] == TRUSTED.isoformat()
    assert requests == [0]


def test_legacy_browser_http_rejects_future_without_acquisition(tmp_path):
    from tests.unit.browser.test_intraday_discovery_control import (
        _running_control, _request, _headers, _close, OBSERVED,
    )
    server, thread, _, _, _, _, _, requests = _running_control(tmp_path, authenticate=True)
    try:
        status, _, body = _request(server, "POST", "/control/intraday-discovery",
            body=json.dumps({"request_identity": "BROWSER-FUTURE",
                "observation_boundary": (OBSERVED + timedelta(minutes=1)).isoformat(),
            }).encode(), headers=_headers(server))
        document = json.loads(body)
        assert status == 200  # Legacy transport returns a typed result body.
        assert document["state"] == "FAILED"
        assert document["failure"] == "OBSERVATION_BOUNDARY_FUTURE"
        assert document["run_identity"] is None
        assert requests == [0]
    finally:
        _close(server, thread)


def test_exact_0930_opening_assessment_uses_completed_intraday_and_prior_hour(tmp_path):
    from kronos.intraday.completed_evidence import EvidenceSessionRole, IntradayAnalysisPhase
    _, c, control, _, requests = _control(tmp_path, boundary=REQUESTED)
    result = control.execute_document(_payload("FIRST-LAWFUL-OPENING", boundary=REQUESTED))
    assert result["outcome"] == "SUCCESS"
    assert result["trusted_admission_time"] == REQUESTED.isoformat()
    run = c.probables_v2_application.snapshot().run
    assert run.analysis_boundary == REQUESTED
    mappings = [c.probables_v2_application.store.load_mapping(item.source_mapping_identity)
        for item in run.results if item.source_mapping_identity is not None]
    assert mappings
    for mapping in mappings:
        assert mapping.phase is IntradayAnalysisPhase.OPENING
        evidence = mapping.completed_evidence
        fifteen = evidence.candles(IntradayTimeframe.FIFTEEN_MINUTES,
            EvidenceSessionRole.CURRENT_SESSION_15M)
        assert [(x.candle_start, x.candle_end, x.completion_state) for x in fifteen] == [
            (REQUESTED.replace(minute=15), REQUESTED, "COMPLETE")]
        five = evidence.candles(IntradayTimeframe.FIVE_MINUTES,
            EvidenceSessionRole.CURRENT_SESSION_5M)
        assert [(x.candle_start, x.candle_end, x.completion_state) for x in five] == [
            (REQUESTED.replace(minute=start), REQUESTED.replace(minute=end), "COMPLETE")
            for start, end in ((15, 20), (20, 25), (25, 30))]
        assert evidence.candles(IntradayTimeframe.ONE_HOUR,
            EvidenceSessionRole.CURRENT_SESSION_1H_PRIMARY) == ()
        prior = evidence.candles(IntradayTimeframe.ONE_HOUR,
            EvidenceSessionRole.PRIOR_SESSION_1H_CONTEXT)
        assert len(prior) == 2
        assert all(x.completion_state == "COMPLETE" and x.candle_end.date() < REQUESTED.date()
            for x in prior)
    assert requests[0] > 0  # Isolated Provider double; lawful processing actually ran.
    schedule = CurrentMarketCalendarScheduleSource(MarketCalendarPublisher(),
        observed_at=REQUESTED, canonical_instrument_id="RELIANCE",
    ).schedule_for("NSE", REQUESTED.date())
    forming = HistoricalCandle(REQUESTED.replace(minute=15), 100., 102., 99., 101., 100)
    assert _completed_intraday(candles=(forming,), schedule=schedule,
        timeframe=IntradayTimeframe.ONE_HOUR, observed_at=REQUESTED,
        allow_domain008_empty=True) == ()
