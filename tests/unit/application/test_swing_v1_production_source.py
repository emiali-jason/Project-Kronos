from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from kronos.application.swing_v1_production import (
    AuthoritativeTradeGeometryReferences,
    LocalProductionSourceStore,
    ProductionTradeConstructionSource,
    build_trade_construction_input,
    compose_execution_context,
    produce_waiting_for_risk_lifecycle,
)
from kronos.application.swing_v1_review import (
    Step31EligibilityHandoff,
    Step31EligibleInstrument,
)
from kronos.instrument import (
    InstrumentContextStatus,
    canonical_price_precision,
    publish_instrument_context,
)
from kronos.market import (
    AuthoritativeMarketScheduleFacts,
    MarketAvailability,
    MarketSessionWindow,
    McxMarketScheduleAdapter,
    NseMarketScheduleAdapter,
    ScheduleFreshness,
    ScheduleIntegrity,
)
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.v1.chart_analyst_v2_layer2 import integrate_chart_analyst_v2_layer2
from kronos.swing.v1.step32 import LocalStep32Store, RiskState
from kronos.swing.v1.trade_construction import (
    LocalTradeCandidateStore,
    TradeConstructionStatus,
)
from tests.unit.swing.v1.test_chart_analyst_v2_layer2 import (
    _IMAGE_HASH,
    _context,
)


_NOW = datetime.fromisoformat("2026-08-13T12:00:00+05:30")


def _schedule(exchange: str = "NSE", availability: MarketAvailability = MarketAvailability.OPEN):  # type: ignore[no-untyped-def]
    facts = AuthoritativeMarketScheduleFacts(
        market_identity=f"{exchange}-CASH" if exchange == "NSE" else "MCX-COMMODITY",
        exchange=exchange,
        trading_date=_NOW.date(),
        calendar_identity=f"{exchange}-TRADING-CALENDAR",
        calendar_version="2026.08",
        session_identity=f"{exchange}-REGULAR-20260813",
        session_type="REGULAR",
        session_open=datetime.fromisoformat("2026-08-13T09:15:00+05:30"),
        session_close=datetime.fromisoformat("2026-08-13T15:30:00+05:30"),
        timezone="Asia/Kolkata",
        market_availability=availability,
        as_of=_NOW,
        source_identity=f"{exchange}-AUTHORITATIVE-CALENDAR",
        source_boundary=_NOW,
        freshness_status=ScheduleFreshness.CURRENT,
        integrity_status=ScheduleIntegrity.VALID,
        provenance=(f"{exchange}-SESSION-SOURCE",),
    )
    adapter = NseMarketScheduleAdapter() if exchange == "NSE" else McxMarketScheduleAdapter()
    return adapter.normalize(facts)


@pytest.mark.parametrize(
    ("value", "expected"),
    (("1", 0), ("0.5", 1), ("0.05", 2), ("0.0025", 4), ("0.0500", 2)),
)
def test_price_precision_is_exact_decimal(value: str, expected: int) -> None:
    assert canonical_price_precision(value) == expected


@pytest.mark.parametrize("value", (None, "invalid", "0", "-0.05"))
def test_invalid_price_precision_is_unavailable(value: object) -> None:
    assert canonical_price_precision(value) is None


def test_instrument_facts_preserve_tick_lot_and_exclude_provider_token() -> None:
    record = InstrumentRecord(
        "KITE", "NSE", "NSE", "NAUKRI", "NAUKRI", "EQ", None,
        Decimal("0.0500"), 1,
    )
    context = publish_instrument_context("NAUKRI", "NSE_CASH_EQUITY", record)
    assert context.status is InstrumentContextStatus.COMPLETE
    assert context.tick_size == Decimal("0.0500")
    assert context.lot_size == 1
    assert context.price_precision == 2
    assert "instrument_token" not in repr(context)
    assert "exchange_token" not in repr(context)


def test_reference_zero_geometry_is_preserved_but_not_execution_complete() -> None:
    record = InstrumentRecord(
        "KITE", "NSE", "INDICES", "NIFTY 50", "NIFTY 50", "EQ", None,
        Decimal("0.0"), 0,
    )

    context = publish_instrument_context("NIFTY", "NSE_INDEX", record)

    assert context.status is InstrumentContextStatus.INCOMPLETE
    assert context.tick_size == Decimal("0.0")
    assert context.lot_size == 0
    assert context.price_precision is None
    assert compose_execution_context(context, _schedule()) is None


def test_zero_geometry_for_executable_equity_fails_closed() -> None:
    record = InstrumentRecord(
        "KITE", "NSE", "NSE", "NAUKRI", "NAUKRI", "EQ", None,
        Decimal("0"), 0,
    )

    context = publish_instrument_context("NAUKRI", "NSE_CASH_EQUITY", record)

    assert context.status is InstrumentContextStatus.INCOMPLETE
    assert compose_execution_context(context, _schedule()) is None


def test_nse_and_mcx_schedules_remain_isolated_and_ticks_have_no_authority() -> None:
    nse = _schedule("NSE")
    mcx = _schedule("MCX")
    assert nse.exchange == "NSE" and mcx.exchange == "MCX"
    assert nse.calendar_identity != mcx.calendar_identity
    assert not hasattr(nse, "tick_received")
    with pytest.raises(ValueError, match="MARKET_SCHEDULE_EXCHANGE_MISMATCH"):
        NseMarketScheduleAdapter().normalize(
            AuthoritativeMarketScheduleFacts(
                market_identity="MCX-COMMODITY",
                exchange="MCX",
                trading_date=_NOW.date(),
                calendar_identity="MCX-CALENDAR",
                calendar_version="1",
                session_identity="MCX-SESSION",
                session_type="REGULAR",
                session_open=_NOW,
                session_close=_NOW,
                timezone="Asia/Kolkata",
                market_availability=MarketAvailability.OPEN,
                as_of=_NOW,
                source_identity="MCX-SOURCE",
                source_boundary=_NOW,
                freshness_status=ScheduleFreshness.CURRENT,
                integrity_status=ScheduleIntegrity.VALID,
                provenance=("MCX-SOURCE",),
            )
        )


def _source() -> ProductionTradeConstructionSource:
    run, requirement, assessments, response = _context()
    layer2 = integrate_chart_analyst_v2_layer2(
        requirement, assessments, response, source_image_sha256=_IMAGE_HASH
    )
    assessment = assessments[0]
    identity = requirement.probable_setups[0].assessment_identity
    eligible = Step31EligibleInstrument(
        canonical_instrument=assessment.canonical_identity,
        layer1_run_identity=run.run_identity,
        swing_analysis_run_identity=requirement.swing_analysis_run_identity,
        observation_boundary=assessment.observation_boundary,
        probable_assessment_identities=(identity,),
        source_image_sha256=_IMAGE_HASH,
        readiness_state=layer2.readiness.state,
        readiness_policy_identity=layer2.readiness.policy_identity,
        readiness_reason=layer2.readiness.primary_reason,
    )
    handoff = Step31EligibilityHandoff(
        requirement.swing_analysis_run_identity,
        run.run_identity,
        (eligible,),
    )
    instrument = publish_instrument_context(
        assessment.canonical_identity,
        "NSE_CASH_EQUITY",
        InstrumentRecord(
            "KITE", "NSE", "NSE", assessment.canonical_identity,
            assessment.canonical_identity, "EQ", None, Decimal("0.05"), 1,
        ),
    )
    candle = HistoricalCandle(
        assessment.observation_boundary, 99.0, 100.0, 96.0, 99.0, 1000
    )
    return ProductionTradeConstructionSource(
        handoff,
        eligible,
        assessment,
        layer2,
        candle,
        _IMAGE_HASH,
        instrument,
        _schedule(),
        AuthoritativeTradeGeometryReferences(
            Decimal("94"), Decimal("105"), Decimal("112"), Decimal("88"),
            Decimal("100"), Decimal("90"),
            ("LAYER1-EVIDENCE", "LAYER2-EVIDENCE"),
        ),
    )


def test_production_adapter_builds_and_persists_waiting_for_risk(tmp_path) -> None:  # type: ignore[no-untyped-def]
    source = _source()
    item = build_trade_construction_input(source)
    assert item.execution_context is not None
    result = produce_waiting_for_risk_lifecycle(
        source,
        candidate_store=LocalTradeCandidateStore(tmp_path / "candidates"),
        step32_store=LocalStep32Store(tmp_path / "step32"),
        source_store=LocalProductionSourceStore(tmp_path / "sources"),
        clock=_NOW,
    )
    assert result.candidate.construction_status is TradeConstructionStatus.COMPLETE
    assert result.risk is not None and result.risk.state is RiskState.UNAVAILABLE
    assert result.waiting_for_risk
    assert list((tmp_path / "candidates").rglob("*.json"))
    assert len(list((tmp_path / "step32").rglob("*.json"))) == 3
    source_path = next((tmp_path / "sources").rglob("*.json"))
    recovered = LocalProductionSourceStore(tmp_path / "sources").load(
        source.instrument_context.identity,
        source.market_schedule.identity,
    )
    assert source_path.stat().st_mode & 0o777 == 0o600
    assert recovered.instrument_context == source.instrument_context
    assert recovered.market_schedule == source.market_schedule


def test_multi_window_schedule_survives_restart_without_legacy_flattening(tmp_path) -> None:  # type: ignore[no-untyped-def]
    source = _source()
    windows = (
        MarketSessionWindow(
            "NSE-SPECIAL-20260813:WINDOW:1",
            1,
            datetime.fromisoformat("2026-08-13T09:15:00+05:30"),
            datetime.fromisoformat("2026-08-13T10:00:00+05:30"),
        ),
        MarketSessionWindow(
            "NSE-SPECIAL-20260813:WINDOW:2",
            2,
            datetime.fromisoformat("2026-08-13T11:30:00+05:30"),
            datetime.fromisoformat("2026-08-13T12:30:00+05:30"),
        ),
    )
    schedule = NseMarketScheduleAdapter().normalize(AuthoritativeMarketScheduleFacts(
        market_identity="NSE-CASH",
        exchange="NSE",
        trading_date=_NOW.date(),
        calendar_identity="NSE-TRADING-CALENDAR",
        calendar_version="2026.08.1",
        session_identity="NSE-SPECIAL-20260813",
        session_type="SPECIAL_LIVE_DR",
        session_open=None,
        session_close=None,
        timezone="Asia/Kolkata",
        market_availability=MarketAvailability.CLOSED,
        as_of=datetime.fromisoformat("2026-08-13T12:30:00+05:30"),
        source_identity="NSE-AUTHORITATIVE-CALENDAR",
        source_boundary=_NOW,
        freshness_status=ScheduleFreshness.CURRENT,
        integrity_status=ScheduleIntegrity.VALID,
        provenance=("NSE-SPECIAL-SOURCE",),
        windows=windows,
    ))
    store = LocalProductionSourceStore(tmp_path / "sources")

    store.retain(source.instrument_context, schedule)
    recovered = store.load(source.instrument_context.identity, schedule.identity)

    assert recovered.market_schedule == schedule
    assert recovered.market_schedule.windows == windows
    assert recovered.market_schedule.session_open is None
    assert recovered.market_schedule.session_close is None


def test_missing_market_or_instrument_fact_fails_closed() -> None:
    source = _source()
    unavailable = replace(source.market_schedule, market_availability=MarketAvailability.UNAVAILABLE)
    assert compose_execution_context(source.instrument_context, unavailable) is None
    incomplete = publish_instrument_context(
        "NAUKRI", "NSE_CASH_EQUITY",
        InstrumentRecord("KITE", "NSE", "NSE", "NAUKRI", "NAUKRI", "EQ", None),
    )
    assert compose_execution_context(incomplete, source.market_schedule) is None
