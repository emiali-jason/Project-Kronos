from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.instrument.runtime import (
    create_canonical_instrument,
    create_provider_assertion,
    create_provider_binding_directive,
    publish_runtime_instruments,
)
from kronos.intraday.candles import expected_candle_boundaries
from kronos.intraday.composition import (
    CoreSlice1CompositionError,
    CoreSlice1Failure,
    compose_core_slice1_facts,
)
from kronos.intraday.contracts import CandleCompletion, IntradayTimeframe, SourceProvenance
from kronos.intraday.instrument import adapt_runtime_instrument
from kronos.intraday.persistence import LocalIntradayFactualEvidenceStore
from kronos.market.calendar import (
    MARKET_CALENDAR_SCHEMA,
    MarketCalendarPublisher,
    seal_market_calendar_document,
)
from kronos.provider.contracts.market_data import HistoricalCandle


IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 8, 17)
OBSERVED = datetime(2026, 8, 17, 10, 17, tzinfo=IST)
CREATED = datetime(2026, 8, 17, 10, 16, tzinfo=IST)
TIMEFRAMES = (
    IntradayTimeframe.DAILY,
    IntradayTimeframe.ONE_HOUR,
    IntradayTimeframe.FIFTEEN_MINUTES,
    IntradayTimeframe.FIVE_MINUTES,
)


def _instrument_registry(*, bound: bool = True):  # type: ignore[no-untyped-def]
    canonical = create_canonical_instrument(
        canonical_instrument_id="NIFTY",
        exchange="NSE",
        segment="INDICES",
        instrument_type="EQ",
        canonical_tick_size=Decimal("0.05"),
        canonical_lot_size=1,
        canonical_source_identity="GOVERNED-CANONICAL-UNIVERSE-V1",
        source_boundary=OBSERVED - timedelta(days=1),
        valid_through=OBSERVED + timedelta(days=1),
    )
    if not bound:
        return publish_runtime_instruments(
            canonical_instruments=(canonical,),
            provider_assertions=(),
            binding_directives=(),
            observed_at=OBSERVED,
        )
    assertion = create_provider_assertion(
        provider="KITE",
        provider_symbol="NIFTY 50",
        provider_instrument_token=256265,
        exchange="NSE",
        segment="INDICES",
        instrument_type="EQ",
        asserted_tick_size=Decimal("0.05"),
        asserted_lot_size=1,
        binding_source_identity="KITE-INSTRUMENT-MASTER-20260817",
        source_boundary=OBSERVED - timedelta(hours=1),
        valid_through=OBSERVED + timedelta(days=1),
    )
    directive = create_provider_binding_directive(
        canonical_instrument_id="NIFTY",
        provider="KITE",
        provider_symbol="NIFTY 50",
        directive_source_identity="GOVERNED-PROVIDER-BINDINGS-V1",
    )
    return publish_runtime_instruments(
        canonical_instruments=(canonical,),
        provider_assertions=(assertion,),
        binding_directives=(directive,),
        observed_at=OBSERVED,
    )


def _calendar(*, day: str = "2026-08-17") -> MarketCalendarPublisher:
    source_boundary = OBSERVED - timedelta(days=1)
    document = {
        "schema_identity": MARKET_CALENDAR_SCHEMA,
        "market_identity": "NSE-CASH",
        "exchange": "NSE",
        "exchange_timezone": "Asia/Kolkata",
        "calendar_version": "2026.08.17",
        "source_identity": "NSE-OFFICIAL-PUBLICATION-20260816",
        "source_boundary": source_boundary.isoformat(),
        "valid_through": (OBSERVED + timedelta(days=7)).isoformat(),
        "entries": [
            {
                "trading_date": day,
                "trading_disposition": "TRADING",
                "session_id": f"NSE-{day.replace('-', '')}-REGULAR",
                "session_type": "REGULAR",
                "special_session": False,
                "windows": [
                    {
                        "opens_at": f"{day}T09:15:00+05:30",
                        "closes_at": f"{day}T15:30:00+05:30",
                    }
                ],
                "market_availability": "AVAILABLE",
            }
        ],
    }
    return MarketCalendarPublisher.from_bytes(
        seal_market_calendar_document(document),
        observed_at=OBSERVED,
    )


def _inputs(registry, calendar):  # type: ignore[no-untyped-def]
    instrument = adapt_runtime_instrument(registry.require_consumable("NIFTY"))
    schedule = calendar.schedule_for("NSE", DAY)
    assert schedule is not None
    candles: dict[IntradayTimeframe, tuple[HistoricalCandle, ...]] = {}
    provenance: dict[IntradayTimeframe, SourceProvenance] = {}
    for timeframe in TIMEFRAMES:
        boundaries = expected_candle_boundaries(schedule, timeframe)
        if timeframe is IntradayTimeframe.DAILY:
            timestamps = (datetime(2026, 8, 17, 0, 0, tzinfo=IST),)
        else:
            timestamps = tuple(
                item.start
                for item in boundaries
                if item.start <= OBSERVED
            )
        candles[timeframe] = tuple(
            HistoricalCandle(timestamp, 100.0, 102.0, 99.0, 101.0, 1000)
            for timestamp in timestamps
        )
        provenance[timeframe] = SourceProvenance(
            provider="KITE",
            source_identity=f"KITE-HISTORICAL:NIFTY:{timeframe.value}:{DAY}",
            retrieved_at=OBSERVED,
            source_version="KITE-HISTORICAL-V1",
        )
    return instrument, candles, provenance


def test_core_slice1_end_to_end_factual_composition_and_restart(
    tmp_path: Path,
) -> None:
    registry = _instrument_registry()
    calendar = _calendar()
    instrument, candles, provenance = _inputs(registry, calendar)
    store = LocalIntradayFactualEvidenceStore(tmp_path)

    result = compose_core_slice1_facts(
        instrument_registry=registry,
        canonical_instrument_id="NIFTY",
        calendar_source=calendar,
        exchange="NSE",
        trading_date=DAY,
        observed_at=OBSERVED,
        run_created_at=CREATED,
        provider_candles=candles,
        provenance=provenance,
        evidence_store=store,
    )

    assert result.instrument == instrument
    assert result.instrument.canonical_instrument_id == "NIFTY"
    assert result.instrument.provider_symbol == "NIFTY 50"
    assert result.instrument.provider_instrument_token == 256265
    assert result.market_session.schedule is not None
    assert result.market_session.schedule.session_id == "NSE-20260817-REGULAR"
    assert tuple(item.reconciliation.timeframe for item in result.evidence) == TIMEFRAMES
    by_timeframe = {item.reconciliation.timeframe: item for item in result.evidence}
    assert by_timeframe[IntradayTimeframe.DAILY].reconciliation.structural_candles == ()
    for timeframe in (
        IntradayTimeframe.ONE_HOUR,
        IntradayTimeframe.FIFTEEN_MINUTES,
        IntradayTimeframe.FIVE_MINUTES,
    ):
        reconciliation = by_timeframe[timeframe].reconciliation
        assert reconciliation.structural_candles
        assert reconciliation.observations[-1].completion is CandleCompletion.INCOMPLETE
        assert reconciliation.observations[-1] not in reconciliation.structural_candles
        assert reconciliation.missing_boundaries == ()

    restarted = LocalIntradayFactualEvidenceStore(tmp_path)
    for evidence in result.evidence:
        assert restarted.load(
            run_id=result.run.run_id,
            mapping_identity=instrument.mapping_identity,
            timeframe=evidence.reconciliation.timeframe,
            evidence_id=evidence.evidence_id,
        ) == evidence
    assert len(list(tmp_path.rglob("*.json"))) == 4
    for prohibited in ("setup", "readiness", "trade_plan", "entry", "risk", "sponsor"):
        assert not hasattr(result, prohibited)


def test_composition_fails_closed_for_unavailable_instrument_or_schedule(
    tmp_path: Path,
) -> None:
    registry = _instrument_registry()
    calendar = _calendar()
    _, candles, provenance = _inputs(registry, calendar)
    arguments = {
        "canonical_instrument_id": "NIFTY",
        "exchange": "NSE",
        "trading_date": DAY,
        "observed_at": OBSERVED,
        "run_created_at": CREATED,
        "provider_candles": candles,
        "provenance": provenance,
        "evidence_store": LocalIntradayFactualEvidenceStore(tmp_path),
    }
    with pytest.raises(CoreSlice1CompositionError) as instrument_failure:
        compose_core_slice1_facts(
            instrument_registry=_instrument_registry(bound=False),
            calendar_source=calendar,
            **arguments,
        )
    assert instrument_failure.value.failure is CoreSlice1Failure.INSTRUMENT_UNAVAILABLE

    with pytest.raises(CoreSlice1CompositionError) as market_failure:
        compose_core_slice1_facts(
            instrument_registry=registry,
            calendar_source=_calendar(day="2026-08-18"),
            **arguments,
        )
    assert market_failure.value.failure is CoreSlice1Failure.MARKET_SCHEDULE_UNAVAILABLE


def test_missing_completed_candle_is_persisted_but_has_no_structural_authority(
    tmp_path: Path,
) -> None:
    registry = _instrument_registry()
    calendar = _calendar()
    instrument, candles, provenance = _inputs(registry, calendar)
    five_minute = candles[IntradayTimeframe.FIVE_MINUTES]
    candles[IntradayTimeframe.FIVE_MINUTES] = five_minute[:2] + five_minute[3:]
    store = LocalIntradayFactualEvidenceStore(tmp_path)

    with pytest.raises(CoreSlice1CompositionError) as captured:
        compose_core_slice1_facts(
            instrument_registry=registry,
            canonical_instrument_id="NIFTY",
            calendar_source=calendar,
            exchange="NSE",
            trading_date=DAY,
            observed_at=OBSERVED,
            run_created_at=CREATED,
            provider_candles=candles,
            provenance=provenance,
            evidence_store=store,
        )
    assert captured.value.failure is CoreSlice1Failure.DATA_INCOMPLETE
    five_minute_path = next((tmp_path).glob(
        f"*/{instrument.mapping_identity}/{IntradayTimeframe.FIVE_MINUTES.value}/*.json"
    ))
    payload = json.loads(five_minute_path.read_text(encoding="utf-8"))
    assert payload["evidence"]["result"] == "DATA_INCOMPLETE"
    assert payload["evidence"]["structural_candle_ids"] == []
    assert payload["evidence"]["backfill_required"] is True


def test_calendar_publication_integrity_failure_stops_before_composition() -> None:
    publisher = _calendar()
    document = json.loads(
        seal_market_calendar_document({
            "schema_identity": MARKET_CALENDAR_SCHEMA,
            "market_identity": "NSE-CASH",
            "exchange": "NSE",
            "exchange_timezone": "Asia/Kolkata",
            "calendar_version": "2026.08.17",
            "source_identity": "NSE-OFFICIAL-PUBLICATION-20260816",
            "source_boundary": (OBSERVED - timedelta(days=1)).isoformat(),
            "valid_through": (OBSERVED + timedelta(days=1)).isoformat(),
            "entries": [],
        })
    )
    document["market_identity"] = "TAMPERED"
    with pytest.raises(ValueError, match="MARKET_CALENDAR_INTEGRITY_MISMATCH"):
        MarketCalendarPublisher.from_bytes(
            json.dumps(document).encode(),
            observed_at=publisher.observed_at,
        )
