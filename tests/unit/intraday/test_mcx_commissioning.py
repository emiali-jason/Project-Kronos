from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.mcx_commissioning import (
    McxCommissioningError,
    McxCommissioningState,
    load_mcx_commissioning_publication,
)
from kronos.intraday.mcx_history import (
    MCX_CONTINUOUS_CONSTRUCTION,
    MCX_HISTORY_AUTHORITY,
    MCX_HISTORY_CANDLE_IDENTITY,
    MCX_HISTORY_CANDLE_VERSION,
    McxHistoryError,
    RetainedMcxContractCandle,
    _identity,
    build_continuous_analytical_view,
    create_retained_mcx_candles,
    parse_retained_mcx_candle,
    retained_mcx_candle_bytes,
)
from kronos.intraday.mcx_history_persistence import McxContractHistoryStore
from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus
from kronos.provider.contracts.market_data import HistoricalCandle
from tests.unit.instrument.test_active_derivative_selection import _resolve


IST = ZoneInfo("Asia/Kolkata")


def test_subject_registry_is_evidence_bound_and_unknown_fails_closed() -> None:
    publication = load_mcx_commissioning_publication()
    states = {
        item.canonical_subject_identity: item.state for item in publication.entries
    }
    assert states == {
        "MCX-SUBJECT-COPPER": McxCommissioningState.COMMISSIONED,
        "MCX-SUBJECT-CRUDE": McxCommissioningState.COMMISSIONED,
        "MCX-SUBJECT-GOLDM": McxCommissioningState.COMMISSIONED,
        "MCX-SUBJECT-NATGAS": McxCommissioningState.HELD,
        "MCX-SUBJECT-SILVERM": McxCommissioningState.COMMISSIONED,
    }
    assert all(item.qualification_evidence_identity for item in publication.entries)
    assert all(item.qualification_integrity_identity for item in publication.entries)
    assert publication.authority == "MCX_SUBJECT_ANALYTICAL_COMMISSIONING_ONLY"
    with pytest.raises(McxCommissioningError, match="MCX_SUBJECT_COMMISSIONING_UNKNOWN"):
        publication.subject("MCX-SUBJECT-UNKNOWN")


def test_already_acquired_completed_candle_is_retained_without_token() -> None:
    observed = datetime(2026, 8, 26, 10, 10, tzinfo=IST)
    binding = _resolve(observed).for_subject("GOLDM").binding
    assert binding is not None
    schedule = _schedule(date(2026, 8, 26))
    retained = create_retained_mcx_candles(
        active_binding=binding,
        timeframe=IntradayTimeframe.FIVE_MINUTES,
        schedule=schedule,
        candles=(HistoricalCandle(
            datetime(2026, 8, 26, 10, 0, tzinfo=IST),
            100.0, 102.0, 99.0, 101.0, 1000,
        ),),
        observation_boundary=observed,
        source_operation_identity="DISCOVERY-BUNDLE-TEST",
    )
    assert len(retained) == 1
    encoded = retained_mcx_candle_bytes(retained[0])
    assert parse_retained_mcx_candle(encoded) == retained[0]
    assert b"instrument_token" not in encoded
    assert b"provider_instrument_token" not in encoded
    assert retained[0].canonical_contract_identity.startswith("MCX-FUT-GOLDM-")


def test_forming_candle_is_rejected() -> None:
    observed = datetime(2026, 8, 26, 10, 3, tzinfo=IST)
    binding = _resolve(observed).for_subject("GOLDM").binding
    assert binding is not None
    with pytest.raises(McxHistoryError, match="MCX_RETENTION_FORMING_CANDLE_REJECTED"):
        create_retained_mcx_candles(
            active_binding=binding,
            timeframe=IntradayTimeframe.FIVE_MINUTES,
            schedule=_schedule(date(2026, 8, 26)),
            candles=(HistoricalCandle(
                datetime(2026, 8, 26, 10, 0, tzinfo=IST),
                100.0, 102.0, 99.0, 101.0, 1000,
            ),),
            observation_boundary=observed,
            source_operation_identity="DISCOVERY-BUNDLE-TEST",
        )


def test_append_only_reload_conflict_and_corruption_fail_closed(tmp_path: Path) -> None:
    candle = _retained("GOLDM", "2026-08-31", 0)
    store = McxContractHistoryStore(tmp_path.resolve())
    path = store.retain(candle)
    assert store.retain(candle) == path
    assert store.load(
        canonical_subject_identity=candle.canonical_subject_identity,
        canonical_contract_identity=candle.canonical_contract_identity,
        timeframe=candle.timeframe.value,
        candle_identity=candle.candle_identity,
    ) == candle
    path.write_bytes(b"{}\n")
    with pytest.raises(McxHistoryError, match="MCX_HISTORY_IMMUTABILITY_CONFLICT"):
        store.retain(candle)
    with pytest.raises(McxHistoryError, match="MCX_RETAINED_CANDLE"):
        store.load(
            canonical_subject_identity=candle.canonical_subject_identity,
            canonical_contract_identity=candle.canonical_contract_identity,
            timeframe=candle.timeframe.value,
            candle_identity=candle.candle_identity,
        )


@pytest.mark.parametrize("family", ("GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE"))
def test_family_expiry_replay_needs_no_current_master_or_provider(
    tmp_path: Path, family: str,
) -> None:
    old = _retained(family, "2026-08-31", 0)
    new = _retained(family, "2026-09-30", 1)
    store = McxContractHistoryStore(tmp_path.resolve())
    store.retain_many((old, new))
    view = store.reconstruct(
        canonical_subject_identity=f"MCX-SUBJECT-{family}",
        contract_identities=(old.canonical_contract_identity, new.canonical_contract_identity),
    )
    assert view.construction_method == MCX_CONTINUOUS_CONSTRUCTION
    assert view.back_adjustment == "NONE"
    assert view.provider_request_count == 0
    assert view.executable is False
    assert len(view.roll_boundaries) == 1
    assert view.roll_boundaries[0].market_gap_authority == "NOT_ESTABLISHED_BY_ROLL"
    assert {item.canonical_contract_identity for item in view.candles} == {
        old.canonical_contract_identity, new.canonical_contract_identity,
    }


def test_continuous_view_preserves_missing_contract_segments(tmp_path: Path) -> None:
    candle = _retained("GOLDM", "2026-09-30", 1)
    missing = "MCX-FUT-GOLDM-2026-08-31"
    store = McxContractHistoryStore(tmp_path.resolve())
    store.retain(candle)
    view = store.reconstruct(
        canonical_subject_identity="MCX-SUBJECT-GOLDM",
        contract_identities=(missing, candle.canonical_contract_identity),
    )
    assert view.missing_segment_identities == (f"MISSING-CONTRACT-SEGMENT:{missing}",)
    assert view.provider_request_count == 0


def _schedule(day: date) -> MarketDaySchedule:
    return MarketDaySchedule(
        exchange="MCX",
        trading_date=day,
        session_id=f"MCX:{day.isoformat()}:TEST",
        timezone="Asia/Kolkata",
        status=TradingDayStatus.TRADING,
        windows=(MarketWindow(
            datetime.combine(day, time(10, 0), IST),
            datetime.combine(day, time(17, 0), IST),
        ),),
        source_identity="KRONOS-MARKET-CALENDAR-V1/TEST",
        source_version="1",
    )


def _retained(family: str, expiry: str, offset: int) -> RetainedMcxContractCandle:
    start = datetime(2026, 8, 27 + offset, 10, 0, tzinfo=IST)
    values = {
        "canonical_subject_identity": f"MCX-SUBJECT-{family}",
        "canonical_contract_identity": f"MCX-FUT-{family}-{expiry}",
        "provider_record_identity": f"PROVIDER-INSTRUMENT-RECORD-{family}-{offset}",
        "historical_binding_identity": f"ACTIVE-DERIVATIVE-BINDING-{family}-{offset}",
        "domain008_session_identity": f"MCX-SESSION-{offset}",
        "calendar_identity": "KRONOS-MARKET-CALENDAR-V1/TEST",
        "calendar_version": "1",
        "timeframe": IntradayTimeframe.FIVE_MINUTES,
        "source_timestamp": start,
        "candle_start": start,
        "candle_end": start + timedelta(minutes=5),
        "completion_boundary": start + timedelta(minutes=5),
        "open": Decimal("100"),
        "high": Decimal("102"),
        "low": Decimal("99"),
        "close": Decimal("101"),
        "volume": 1000,
        "observation_boundary": start + timedelta(minutes=10),
        "source_operation_identity": f"DISCOVERY-BUNDLE-{offset}",
        "provider_source_identity": "DOMAIN-006:KITE:HISTORICAL",
        "provenance": ("TEST-GOVERNED-FACT", "SENSITIVE_PROVIDER_LOCATOR_EXCLUDED"),
        "authority": MCX_HISTORY_AUTHORITY,
        "contract_identity": MCX_HISTORY_CANDLE_IDENTITY,
        "contract_version": MCX_HISTORY_CANDLE_VERSION,
    }
    return RetainedMcxContractCandle(
        candle_identity=_identity("INTRADAY-MCX-CONTRACT-CANDLE-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-CONTRACT-CANDLE-", values),
        **values,
    )
