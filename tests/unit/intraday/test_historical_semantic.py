from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_qualification import (
    reconstruct_previous_session_facts,
    select_historical_session,
)
from kronos.intraday.historical_semantic import (
    HISTORICAL_CANDLE_PAYLOAD_IDENTITY,
    SEMANTIC_QUALIFICATION_EVIDENCE_IDENTITY,
    SemanticDirection,
    SemanticEvidenceError,
    SemanticFactFamily,
    create_governed_historical_candle_payload,
    derive_semantic_qualification_evidence,
    semantic_artifact_bytes,
)
from kronos.intraday.historical_semantic_persistence import HistoricalSemanticStore
from kronos.market.schedule import (
    MarketDaySchedule,
    MarketWindow,
    TradingDayStatus,
)


IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 8, 17)
PREVIOUS_DAY = date(2026, 8, 14)
BOUNDARY = datetime(2026, 8, 17, 15, 30, tzinfo=IST)
OPERATION = "INTRADAY-HISTORICAL-QUALIFICATION-OPERATION-WO06S-FIXTURE"


def _schedule(day: date) -> MarketDaySchedule:
    return MarketDaySchedule(
        exchange="NSE",
        trading_date=day,
        session_id=f"NSE:{day.isoformat()}",
        timezone="Asia/Kolkata",
        status=TradingDayStatus.TRADING,
        windows=(
            MarketWindow(
                opens_at=datetime.combine(day, time(9, 15), IST),
                closes_at=datetime.combine(day, time(15, 30), IST),
            ),
        ),
        source_identity="KRONOS-MARKET-CALENDAR-V1/WO06S-FIXTURE",
        source_version="1",
    )


class _Calendar:
    def schedule_for(self, exchange: str, trading_date: date):  # type: ignore[no-untyped-def]
        return _schedule(DAY) if exchange == "NSE" and trading_date == DAY else None

    def previous_trading_schedule(self, exchange: str, before_date: date):  # type: ignore[no-untyped-def]
        return (
            _schedule(PREVIOUS_DAY)
            if exchange == "NSE" and before_date == DAY
            else None
        )


def _previous():  # type: ignore[no-untyped-def]
    selection = select_historical_session(
        calendar=_Calendar(),
        exchange="NSE",
        target_trading_date=DAY,
        observation_boundary_identity="WO-06S-FIXTURE-BOUNDARY",
        observation_boundary=BOUNDARY,
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    )
    return reconstruct_previous_session_facts(
        canonical_identity="RELIANCE",
        session=selection,
        previous_daily_candle_identity="GOVERNED-1D-RELIANCE-2026-08-14",
        completed_at=datetime(2026, 8, 14, 15, 30, tzinfo=IST),
        high=Decimal("100"),
        low=Decimal("90"),
        close=Decimal("95"),
        source_integrity_identity="INTEGRITY-DAILY-RELIANCE-2026-08-14",
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    )


def _candle(
    *,
    timeframe: IntradayTimeframe,
    start: datetime,
    high: str,
    low: str,
    close: str,
    volume: int,
):  # type: ignore[no-untyped-def]
    minutes = {
        IntradayTimeframe.DAILY: 375,
        IntradayTimeframe.ONE_HOUR: 60,
        IntradayTimeframe.FIFTEEN_MINUTES: 15,
        IntradayTimeframe.FIVE_MINUTES: 5,
    }[timeframe]
    return create_governed_historical_candle_payload(
        canonical_subject_identity="RELIANCE",
        exchange="NSE",
        market_identity="NSE_CAPITAL_MARKET",
        market_session_identity="NSE:2026-08-17",
        timeframe=timeframe,
        candle_start=start,
        candle_end=start + timedelta(minutes=minutes),
        open=Decimal(close),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
        observation_boundary=BOUNDARY,
        provider_source_identity="DOMAIN-006:KITE:HISTORICAL",
        source_operation_identity=OPERATION,
        provenance=("KRONOS-WO-06S-SEMANTIC-EVIDENCE-001",),
    )


def _payloads(
    *, hourly: str = "LONG", fifteen: str = "LONG"
):  # type: ignore[no-untyped-def]
    def pair(
        timeframe: IntradayTimeframe,
        starts: tuple[datetime, datetime],
        direction: str,
        volumes: tuple[int, int],
    ):
        values = (
            (("102", "98", "100"), ("104", "100", "103"))
            if direction == "LONG"
            else (("104", "100", "103"), ("102", "98", "99"))
        )
        return tuple(
            _candle(
                timeframe=timeframe,
                start=start,
                high=values[index][0],
                low=values[index][1],
                close=values[index][2],
                volume=volumes[index],
            )
            for index, start in enumerate(starts)
        )

    return (
        _candle(
            timeframe=IntradayTimeframe.DAILY,
            start=datetime(2026, 8, 17, 9, 15, tzinfo=IST),
            high="101",
            low="93",
            close="98",
            volume=1_000,
        ),
        *pair(
            IntradayTimeframe.ONE_HOUR,
            (
                datetime(2026, 8, 17, 13, 15, tzinfo=IST),
                datetime(2026, 8, 17, 14, 15, tzinfo=IST),
            ),
            hourly,
            (100, 120),
        ),
        *pair(
            IntradayTimeframe.FIFTEEN_MINUTES,
            (
                datetime(2026, 8, 17, 15, 0, tzinfo=IST),
                datetime(2026, 8, 17, 15, 15, tzinfo=IST),
            ),
            fifteen,
            (130, 140),
        ),
        *pair(
            IntradayTimeframe.FIVE_MINUTES,
            (
                datetime(2026, 8, 17, 15, 20, tzinfo=IST),
                datetime(2026, 8, 17, 15, 25, tzinfo=IST),
            ),
            "LONG",
            (150, 200),
        ),
    )


def _semantic(*, hourly: str = "LONG", fifteen: str = "LONG"):  # type: ignore[no-untyped-def]
    return derive_semantic_qualification_evidence(
        candle_payloads=_payloads(hourly=hourly, fifteen=fifteen),
        previous_session_facts=_previous(),
        source_bundle_identity="INTRADAY-HISTORICAL-FACT-BUNDLE-WO06S-FIXTURE",
        source_operation_identity=OPERATION,
        provenance=("KRONOS-WO-06S-SEMANTIC-EVIDENCE-001",),
    )


def test_contracts_retain_exact_completed_ohlcv_without_provider_token() -> None:
    candle = _payloads()[0]
    assert candle.schema_identity == HISTORICAL_CANDLE_PAYLOAD_IDENTITY
    assert candle.open == Decimal("98")
    assert candle.high == Decimal("101")
    assert candle.low == Decimal("93")
    assert candle.close == Decimal("98")
    assert candle.volume == 1_000
    assert candle.completion_state == "COMPLETE"
    assert candle.available_at == candle.candle_end <= candle.observation_boundary
    encoded = semantic_artifact_bytes(candle).lower()
    assert b"instrument_token" not in encoded
    assert b"access_token" not in encoded
    assert b"api_secret" not in encoded


def test_semantic_derivation_is_threshold_free_and_complete() -> None:
    evidence = _semantic()
    assert evidence.schema_identity == SEMANTIC_QUALIFICATION_EVIDENCE_IDENTITY
    assert len(evidence.facts) == 9
    facts = {item.family: item for item in evidence.facts}
    assert set(facts) == set(SemanticFactFamily)
    assert facts[SemanticFactFamily.HOURLY_REGIME].direction is SemanticDirection.LONG
    assert (
        facts[SemanticFactFamily.FIFTEEN_MINUTE_STRUCTURE].direction
        is SemanticDirection.LONG
    )
    assert (
        facts[SemanticFactFamily.DIRECTIONAL_COHERENCE].direction
        is SemanticDirection.LONG
    )
    assert dict(facts[SemanticFactFamily.VOLUME_PARTICIPATION].attributes) == {
        "current_vs_previous_completed_volume": "ABOVE"
    }
    assert facts[SemanticFactFamily.FIVE_MINUTE_PROGRESSION].direction is SemanticDirection.LONG
    assert dict(facts[SemanticFactFamily.PDH_PDL_RELATIONSHIP].attributes) == {
        "PDH": "ABOVE",
        "PDL": "ABOVE",
    }
    assert len(facts[SemanticFactFamily.CLASSIC_PIVOT_RELATIONSHIPS].attributes) == 9


@pytest.mark.parametrize(
    ("hourly", "fifteen", "expected"),
    (
        ("LONG", "LONG", SemanticDirection.LONG),
        ("SHORT", "SHORT", SemanticDirection.SHORT),
        ("LONG", "SHORT", SemanticDirection.CONFLICTING),
    ),
)
def test_directional_coherence_is_explicit_not_not_long(
    hourly: str, fifteen: str, expected: SemanticDirection
) -> None:
    evidence = _semantic(hourly=hourly, fifteen=fifteen)
    fact = next(
        item
        for item in evidence.facts
        if item.family is SemanticFactFamily.DIRECTIONAL_COHERENCE
    )
    assert fact.direction is expected


def test_persistence_is_explicit_idempotent_reloadable_and_tamper_evident(
    tmp_path: Path,
) -> None:
    store = HistoricalSemanticStore(tmp_path)
    candle = _payloads()[0]
    evidence = _semantic()
    candle_path = store.retain(candle)
    evidence_path = store.retain(evidence)
    assert store.retain(candle) == candle_path
    assert store.retain(evidence) == evidence_path
    assert store.load(
        artifact_type="GovernedHistoricalCandlePayload",
        artifact_identity=candle.candle_identity,
    ) == candle
    assert store.load(
        artifact_type="SemanticQualificationEvidence",
        artifact_identity=evidence.evidence_identity,
    ) == evidence
    assert store.identities_for_operation(
        artifact_type="SemanticQualificationEvidence",
        operation_identity=OPERATION,
    ) == (evidence.evidence_identity,)
    evidence_path.write_bytes(evidence_path.read_bytes().replace(b"RELIANCE", b"TAMPERED"))
    with pytest.raises(SemanticEvidenceError, match="INTEGRITY"):
        store.load(
            artifact_type="SemanticQualificationEvidence",
            artifact_identity=evidence.evidence_identity,
        )


def test_incomplete_or_future_candle_cannot_enter_semantic_evidence() -> None:
    candle = _payloads()[0]
    with pytest.raises(SemanticEvidenceError):
        replace(candle, completion_state="INCOMPLETE")
    with pytest.raises(SemanticEvidenceError):
        replace(
            candle,
            candle_end=BOUNDARY + timedelta(minutes=5),
            available_at=BOUNDARY + timedelta(minutes=5),
        )
