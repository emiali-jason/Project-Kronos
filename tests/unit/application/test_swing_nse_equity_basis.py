"""NSE equity reference/follow-up basis: absent, affected and unknown."""
from datetime import date, datetime, timedelta, timezone

import pytest

from kronos.application.swing_nse_equity_basis import (
    NseEquityActionReport, NseEquityBasisStore,
)
from kronos.application.swing_research_control import SwingResearchControl
from types import SimpleNamespace
from kronos.swing.v1.prospective_research import (
    FollowupCandle, GovernedSession, candle_record, evaluate, milestone, origin,
)


NOW = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
SOURCE = "https://www.nseindia.com/companies-listing/corporate-filings-actions"
HEADER = b"SYMBOL,SERIES,PURPOSE,EX-DATE\n"


def _report(csv_bytes=HEADER, rows=0, start=date(2026, 9, 29)):
    from hashlib import sha256
    attestation = {"symbol": "RELIANCE", "series": "EQ", "coverage_start": start.isoformat(),
        "coverage_end": "2026-10-01", "source_url": SOURCE,
        "source_sha256": sha256(csv_bytes).hexdigest(), "all_results_row_count": rows,
        "captured_at": NOW.isoformat(), "attested_at": NOW.isoformat(),
        "received_at": NOW.isoformat(), "all_results": True, "purpose_filter": "ALL",
        "authority": "SPONSOR_OR_DATA_OWNER_COMPLETENESS_ATTESTATION_V1",
        "attested_by": "ISOLATED-OWNER", "capture_identity": "FIXTURE",
        "calendar_identity": "ISOLATED", "calendar_sha256": "a" * 64}
    return NseEquityActionReport(
        "RELIANCE", "EQ", start, date(2026, 10, 1),
        NOW, SOURCE, csv_bytes, rows, True, attestation)


def _research_facts():
    admitted = datetime(2026, 9, 29, 5, tzinfo=timezone.utc)
    event = admitted + timedelta(minutes=10)
    binding = {"canonical_instrument": "RELIANCE", "exchange": "NSE",
               "provider": "KITE", "segment": "NSE", "trading_symbol": "RELIANCE",
               "instrument_type": "EQ", "expiry": None}
    source = origin(continuity_identity="SWO-RELIANCE", market="NSE",
                    instrument="RELIANCE", contract_identity="CONTRACT-RELIANCE",
                    expiry=None, contract_binding=binding, direction="LONG",
                    admitted_at=admitted, source_identity="CONTINUITY-RELIANCE",
                    source_version="1", source_sha256="a" * 64,
                    origin_run_identity="RUN-RELIANCE",
                    origin_assessment_sha256="b" * 64,
                    native_setup_identity="ESTABLISHED_TREND_STRUCTURAL_HOLD")
    m = milestone(source, count=4, readiness_state="READY",
                  source_identity="V2-RELIANCE", source_version="2",
                  source_sha256="c" * 64, occurred_at=event,
                  reference_price="100", price_observation_identity="TICK-1",
                  price_observed_at=event - timedelta(seconds=1),
                  price_received_at=event, price_source="KITE_CONNECT_WEBSOCKET")
    opening = datetime(2026, 10, 1, 4, tzinfo=timezone.utc)
    session = GovernedSession("NSE-2026-10-01", "NSE", date(2026, 10, 1),
                              opening, opening + timedelta(hours=6))
    candle = candle_record(FollowupCandle(
        "CONTRACT-RELIANCE", session.identity, "PROVIDER-1", "1", NOW,
        "105", "107", "95", True, price_basis_verified=False))
    return source, m, session, candle


def test_verified_absence_enables_comparable_equity_prices(tmp_path):
    store = NseEquityBasisStore(tmp_path / "basis")
    identity = store.retain(_report())
    assert store.retain(_report()) == identity
    source, m, session, candle = _research_facts()
    state, evidence = store.basis("RELIANCE", "EQ", date(2026, 9, 29),
                                  date(2026, 10, 1))
    result = evaluate(m, source, horizon=1, sessions=(session,),
                      candles={session.identity: candle}, as_of=NOW,
                      equity_basis_state=state, equity_basis_identity=evidence)
    assert state == "VERIFIED_NO_ACTION" and evidence == identity
    assert result.data["status"] == "WITH_PREDICTION"
    assert result.data["actual_close"] == "105"
    assert result.data["equity_basis_identity"] == identity


def test_reported_action_or_missing_coverage_withholds_outcome(tmp_path):
    store = NseEquityBasisStore(tmp_path / "basis")
    source, m, session, candle = _research_facts()
    unknown, identity = store.basis("RELIANCE", "EQ", date(2026, 9, 29),
                                    date(2026, 10, 1))
    result = evaluate(m, source, horizon=1, sessions=(session,),
                      candles={session.identity: candle}, as_of=NOW,
                      equity_basis_state=unknown, equity_basis_identity=identity)
    assert result.data["status"] == "UNAVAILABLE"
    assert result.data["reason"] == "PRICE_BASIS_EVIDENCE_UNAVAILABLE"
    csv_bytes = HEADER + b"RELIANCE,EQ,Bonus,30-Sep-2026\n"
    store.retain(_report(csv_bytes, 1))
    affected, evidence = store.basis("RELIANCE", "EQ", date(2026, 9, 29),
                                     date(2026, 10, 1))
    result = evaluate(m, source, horizon=1, sessions=(session,),
                      candles={session.identity: candle}, as_of=NOW,
                      equity_basis_state=affected, equity_basis_identity=evidence)
    assert affected == "AFFECTED"
    assert result.data["status"] == "UNAVAILABLE"
    assert result.data["reason"] == "CORPORATE_ACTION_BASIS_UNAVAILABLE"
    assert result.data["actual_close"] is None


def test_incomplete_or_wrong_scope_report_cannot_verify_absence(tmp_path):
    with pytest.raises(ValueError, match="TRUNCATED"):
        _report(HEADER, 1)
    with pytest.raises(ValueError, match="SCOPE"):
        _report(HEADER + b"OTHER,EQ,Split,30-Sep-2026\n", 1)
    store = NseEquityBasisStore(tmp_path / "basis")
    store.retain(_report())
    assert store.basis("RELIANCE", "EQ", date(2026, 9, 28),
                       date(2026, 10, 1)) == ("UNKNOWN", None)
    assert store.basis("RELIANCE", "EQ", date(2026, 9, 29),
                       date(2026, 10, 1), as_of=NOW - timedelta(hours=1)) == ("UNKNOWN", None)
    # A later, narrower official report cannot silently contradict the
    # older full-range absence certificate.
    store.retain(_report(HEADER + b"RELIANCE,EQ,Split,30-Sep-2026\n", 1, start=date(2026, 9, 30)))
    assert store.basis("RELIANCE", "EQ", date(2026, 9, 29),
                       date(2026, 10, 1)) == ("UNKNOWN", None)


def test_action_after_due_session_does_not_withhold_earlier_horizon(tmp_path):
    store = NseEquityBasisStore(tmp_path / "basis")
    store.retain(_report(HEADER + b"RELIANCE,EQ,Split,01-Oct-2026\n", 1))
    source, m, later_session, _ = _research_facts()
    opening = datetime(2026, 9, 30, 4, tzinfo=timezone.utc)
    due = GovernedSession("NSE-2026-09-30", "NSE", date(2026, 9, 30),
                          opening, opening + timedelta(hours=6))
    control = SwingResearchControl(
        application=SimpleNamespace(), intake=None, research=SimpleNamespace(),
        capture=SimpleNamespace(), calendar=None, equity_basis=store)
    try:
        assert control._basis_for(m, source, (due, later_session), 1, NOW)[0] == "VERIFIED_NO_ACTION"
        assert control._basis_for(m, source, (due, later_session), 2, NOW)[0] == "AFFECTED"
    finally:
        control.close()
