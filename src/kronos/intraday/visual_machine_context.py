"""Exact retained machine context for WO-07C; no acquisition or contract selection."""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from kronos.instrument.semantic_v2 import ActiveDerivativeContractBinding, ProviderMappingDirectiveV2
from kronos.provider.instrument_master import ProviderInstrumentRecord
from kronos.intraday.historical_semantic import GovernedHistoricalCandlePayload
from kronos.market.schedule import MarketSchedule


@dataclass(frozen=True, slots=True)
class UsdinrFuturesContext:
    state: str
    reason: str
    facts: tuple[tuple[str, str], ...] = ()
    authority: str = "MACHINE_CONTEXT_RESEARCH_ONLY"

    @property
    def integrity_identity(self):
        return "WO07C-USDINR-" + sha256(json.dumps((self.state, self.reason, self.facts, self.authority), separators=(",", ":")).encode()).hexdigest()


def usdinr_futures_context(*, boundary, binding=None, directive=None, record=None,
                          candle=None, schedule=None):
    """Require an already-governed exact contract. Never select, roll or fetch one.

    Existing MCX-only selection is not currency contract authority. When no
    separately governed binding exists, the operational projection is unavailable.
    Legacy currency evidence IDs alone cannot establish futures context.
    """
    unavailable = lambda reason: UsdinrFuturesContext("NOT_ESTABLISHED", reason)
    if not isinstance(boundary, datetime) or boundary.tzinfo is None:
        return unavailable("BOUNDARY_UNAVAILABLE")
    if any(x is None for x in (binding, directive, record, candle, schedule)):
        return unavailable("EXACT_FUTURES_EVIDENCE_UNAVAILABLE")
    if (type(binding) is not ActiveDerivativeContractBinding
        or type(directive) is not ProviderMappingDirectiveV2
        or type(record) is not ProviderInstrumentRecord
        or type(candle) is not GovernedHistoricalCandlePayload
        or type(schedule) is not MarketSchedule):
        return unavailable("SOURCE_TYPE_INVALID")
    # Revalidate immutable retained artifacts, including their integrity fields.
    try:
        for item in (binding, directive, record, candle):
            item.__post_init__()
    except (ValueError, RuntimeError):
        return unavailable("SOURCE_INTEGRITY_INVALID")
    if (record.provider, record.exchange, record.segment, record.instrument_type, record.name) != ("KITE", "CDS", "CDS-FUT", "FUT", "USDINR"):
        return unavailable("USDINR_FUTURES_SOURCE_MISMATCH")
    if (record.expiry != binding.contract_expiry
        or directive.provider != record.provider
        or directive.provider_record_identity != record.provider_record_identity
        or directive.provider_symbol != record.trading_symbol
        or directive.canonical_object_id != binding.derivative_contract_id
        or binding.provider_reference_identity != directive.directive_identity
        or candle.canonical_subject_identity != binding.derivative_contract_id
        or candle.provider_source_identity != directive.directive_identity
        or candle.exchange != record.exchange):
        return unavailable("EXACT_CONTRACT_OR_SOURCE_MISMATCH")
    if (not binding.active_at(boundary) or not directive.active_at(boundary)
        or record.expiry < boundary.astimezone(ZoneInfo("Asia/Kolkata")).date()):
        return unavailable("CONTRACT_NOT_ACTIVE")
    if (candle.completion_state != "COMPLETE" or candle.candle_end > boundary
        or candle.available_at > boundary or candle.observation_boundary > boundary
        or candle.market_session_identity != schedule.session_identity
        or schedule.trading_date != boundary.astimezone(ZoneInfo(schedule.timezone)).date()
        or schedule.exchange != record.exchange
        or schedule.market_identity != candle.market_identity
        or schedule.market_availability.value == "UNAVAILABLE"
        or schedule.as_of > boundary or schedule.source_boundary > boundary
        or schedule.freshness_status.value != "CURRENT" or schedule.integrity_status.value != "VALID"
        or not any(w.window_open <= candle.candle_start < candle.candle_end <= w.window_close for w in schedule.windows)):
        return unavailable("COMPLETED_SESSION_EVIDENCE_UNAVAILABLE")
    from kronos.intraday.candles import expected_candle_boundaries
    from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus
    from kronos.intraday.contracts import CandleBoundary
    day = MarketDaySchedule(schedule.exchange, schedule.trading_date, schedule.session_identity,
        schedule.timezone, TradingDayStatus.TRADING,
        tuple(MarketWindow(w.window_open, w.window_close) for w in schedule.windows),
        schedule.source_identity, schedule.calendar_version)
    if CandleBoundary(schedule.trading_date, schedule.session_identity, candle.timeframe,
                      candle.candle_start, candle.candle_end) not in expected_candle_boundaries(day, candle.timeframe):
        return unavailable("COMPLETED_CANDLE_INTERVAL_MISMATCH")
    facts = (
        ("instrument", "USDINR FUTURES"), ("provider", "KITE"),
        ("contract", binding.derivative_contract_id), ("expiry", record.expiry.isoformat()),
        ("binding", binding.binding_identity), ("source", directive.directive_identity),
        ("provider_record", record.provider_record_identity),
        ("candle", candle.candle_identity), ("candle_integrity", candle.integrity_identity),
        ("time", candle.candle_end.isoformat()), ("timeframe", candle.timeframe.value),
        ("completed_close", str(candle.close)),
    )
    return UsdinrFuturesContext("AVAILABLE", "EXACT_GOVERNED_FUTURES_CONTEXT", facts)
