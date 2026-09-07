"""WO-06B evidence integrity only; no analytical or calendar authority."""
from __future__ import annotations

from kronos.intraday.completed_evidence import (
    CompletedEvidenceSelection, EvidenceSessionRole, is_completed_evidence_selection,
)
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import GovernedHistoricalCandlePayload
from kronos.intraday.qualification import NarrowCprFact

LEGACY_SOURCE_BINDING_VERSION = "1.0.0"
SOURCE_BINDING_VERSION = "1.1.0"
SOURCE_BINDING_IDENTITY = "KRONOS-INTRADAY-EVIDENCE-SOURCE-BINDING"


class SourceBindingError(ValueError):
    """A bounded identity, provenance or source-integrity rejection."""


def strict_source_binding(version: str) -> bool:
    if version not in (LEGACY_SOURCE_BINDING_VERSION, SOURCE_BINDING_VERSION):
        raise SourceBindingError("SOURCE_BINDING_VERSION_INVALID")
    return version == SOURCE_BINDING_VERSION


def require_candle_integrity(candle: GovernedHistoricalCandlePayload) -> None:
    if type(candle) is not GovernedHistoricalCandlePayload:
        raise SourceBindingError("SOURCE_CANDLE_INTEGRITY_INVALID")
    try:
        candle.__post_init__()
    except (ValueError, TypeError, AttributeError) as error:
        raise SourceBindingError("SOURCE_CANDLE_INTEGRITY_INVALID") from error


def require_cpr_source_binding(
    selection: CompletedEvidenceSelection, fact: NarrowCprFact,
) -> None:
    """Consume the exact previous Daily selected under DOMAIN-008 authority.

    The selected source, not date-minus-one arithmetic, defines the required
    previous session. Earlier same-session CPR remains lawful for that source.
    """
    if not is_completed_evidence_selection(selection) or type(fact) is not NarrowCprFact:
        raise SourceBindingError("CPR_SOURCE_BINDING_UNAVAILABLE")
    try:
        selection.__post_init__()
        fact.__post_init__()
    except (ValueError, RuntimeError, TypeError, AttributeError) as error:
        raise SourceBindingError("CPR_SOURCE_INTEGRITY_INVALID") from error
    daily = selection.candles(
        IntradayTimeframe.DAILY, EvidenceSessionRole.PREVIOUS_SESSION_DAILY,
    )
    if len(daily) != 1:
        raise SourceBindingError("CPR_SOURCE_BINDING_UNAVAILABLE")
    source = daily[0]
    require_candle_integrity(source)
    if (
        fact.canonical_subject_identity != selection.canonical_subject_identity
        or source.canonical_subject_identity != selection.canonical_subject_identity
        or source.market_session_identity != selection.previous_market_session_identity
        or fact.previous_session_identity != source.market_session_identity
        or fact.observation_session_identity != selection.current_market_session_identity
        or fact.source_daily_candle_identity != source.candle_identity
        or fact.source_integrity_identity != source.integrity_identity
        or fact.observation_boundary > selection.analysis_boundary
        or source.available_at > fact.observation_boundary
        or (fact.previous_daily_high, fact.previous_daily_low, fact.previous_daily_close)
        != (source.high, source.low, source.close)
    ):
        raise SourceBindingError("CPR_SOURCE_BINDING_MISMATCH")
