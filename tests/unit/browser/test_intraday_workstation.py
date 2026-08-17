from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from zoneinfo import ZoneInfo

from kronos.application.intraday_workstation import (
    IntradayEvidenceBundle,
    IntradayEvidenceWorkstation,
)
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server
from kronos.intraday.composition import compose_core_slice1_facts
from kronos.intraday.context import build_slice1e_context
from kronos.intraday.persistence import LocalIntradayFactualEvidenceStore
from kronos.intraday.structure import barriers_from_slice1e, build_structural_evidence
from kronos.intraday.telemetry import ExplicitTelemetryReferences, build_shadow_telemetry
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from tests.unit.application.test_swing_opportunities import _Provider
from tests.unit.intraday.test_composition import (
    CREATED,
    DAY,
    OBSERVED,
    _calendar,
    _inputs,
    _instrument_registry,
)
from tests.unit.intraday.test_context import _Calendar, _schedule


IST = ZoneInfo("Asia/Kolkata")


def _workstation(tmp_path: Path) -> IntradayEvidenceWorkstation:
    registry = _instrument_registry()
    calendar = _calendar()
    _, candles, provenance = _inputs(registry, calendar)
    composition = compose_core_slice1_facts(
        instrument_registry=registry,
        canonical_instrument_id="NIFTY",
        calendar_source=calendar,
        exchange="NSE",
        trading_date=DAY,
        observed_at=OBSERVED,
        run_created_at=CREATED,
        provider_candles=candles,
        provenance=provenance,
        evidence_store=LocalIntradayFactualEvidenceStore(tmp_path / "facts"),
    )
    fifteen = composition.evidence[2].reconciliation
    context = build_slice1e_context(
        run=composition.run,
        instrument=composition.instrument,
        current_trading_date=DAY,
        calendar=_Calendar(_schedule()),
        previous_session_candles=(HistoricalCandle(
            datetime(2026, 8, 14, 0, 0, tzinfo=IST),
            100.0, 110.0, 90.0, 106.0, 1_000_000,
        ),),
        provenance=provenance[fifteen.timeframe],
        current_price=Decimal("101"),
    )
    structure = build_structural_evidence(
        run=composition.run,
        reconciliation=fifteen,
        barriers=barriers_from_slice1e(context),
    )
    five = composition.evidence[3].reconciliation
    telemetry = build_shadow_telemetry(
        run=composition.run,
        reconciliation=five,
        references=ExplicitTelemetryReferences(
            selected_reference=Decimal("100"), selected_reference_identity="P",
            next_barrier=Decimal("110"), next_barrier_identity="PDH",
            structural_reward_reference=Decimal("110"),
            structural_reward_reference_identity="PDH",
            structural_risk_reference=Decimal("99"),
            structural_risk_reference_identity="PDL-LOCAL",
        ),
    )
    return IntradayEvidenceWorkstation(
        registry,
        (IntradayEvidenceBundle(
            composition=composition,
            slice1e_context=context,
            structural_evidence=(structure,),
            shadow_telemetry=(telemetry,),
        ),),
    )


def _request(server, path: str) -> tuple[int, str]:  # type: ignore[no-untyped-def]
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read().decode("utf-8")
    connection.close()
    return response.status, body


def _server(tmp_path: Path, workstation: IntradayEvidenceWorkstation | None = None):  # type: ignore[no-untyped-def]
    application = SwingOpportunitiesApplication(_Provider)
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path / "swing")),
        intraday_workstation=workstation,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_intraday_route_renders_governed_evidence_without_trading_conclusion(
    tmp_path: Path,
) -> None:
    server, thread = _server(tmp_path, _workstation(tmp_path))
    try:
        status, rendered = _request(server, "/intraday?instrument=NIFTY")
        assert status == 200
        assert "ENGINEERING / EVIDENCE" in rendered
        assert "NO TRADING CONCLUSION — EVIDENCE WORKSTATION" in rendered
        assert "NIFTY" in rendered
        assert "Provider Binding (separate)" in rendered
        assert "NSE-20260817-REGULAR" in rendered
        assert all(f"{timeframe} Evidence" in rendered for timeframe in ("1D", "1H", "15M", "5M"))
        assert "CURRENT INCOMPLETE OBSERVATION" in rendered
        assert "CLASSIC_PIVOT_POINTS_V1" in rendered
        assert "CPR_V1" in rendered
        assert "STRUCTURAL_BARRIER" in rendered
        assert "RECENT_VOLUME_COMPARISON" in rendered
        assert "STRUCTURAL_REWARD_RISK_MEASUREMENT" in rendered
        assert "KITE-HISTORICAL:NIFTY:5M" in rendered
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_intraday_route_fails_closed_when_publications_or_selection_are_absent(
    tmp_path: Path,
) -> None:
    server, thread = _server(tmp_path)
    try:
        status, rendered = _request(server, "/intraday")
        assert status == 200
        assert "UNAVAILABLE — no governed DOMAIN-001 publication" in rendered
        assert "No retained governed composition" not in rendered
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    workstation = _workstation(tmp_path)
    snapshot = workstation.snapshot("NOT-IN-REGISTRY")
    assert snapshot.selected_instrument is None
    assert snapshot.evidence is None


def test_intraday_projection_rejects_cross_run_or_unpublished_evidence(tmp_path: Path) -> None:
    workstation = _workstation(tmp_path)
    snapshot = workstation.snapshot("NIFTY")
    assert snapshot.availability == "AVAILABLE"
    assert tuple(
        item.canonical.canonical_instrument_id for item in snapshot.instruments
    ) == ("NIFTY",)
