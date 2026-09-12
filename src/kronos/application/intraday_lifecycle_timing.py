"""WO-11 adapter over the existing factual acquisition and 5M semantic owners.

No Discovery publication, Native reselection, quote pricing or historical fill.
Acquisition is lazy and limited to a Sponsor-authorized track's timing source.
"""
from kronos.intraday.wo11_lifecycle_contract import require, record, instant, price
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.completed_evidence import build_completed_evidence_selection, IntradayAnalysisPhase
from kronos.intraday.probables_v2 import build_semantic_qualification_evidence_v2
from kronos.intraday.wo15 import adapt_five_minute_progression, Wo15ProgressionSemantics, WO15_POLICY_CHECKSUM
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.discovery_runtime import DiscoveryRunBoundary
from kronos.intraday.discovery_source import governed_market_session_identities


def qualify_timing(track, facts, *, acquired_at):
    d = require(track, "WO11_TRACK_V1"); i = d["intake"]
    facts.__post_init__()
    if (facts.canonical_subject_identity != i["subject"]
            or facts.current_schedule.session_id != i["session_identity"]
            or facts.observation_boundary > acquired_at):
        raise ValueError("WO11_TIMING_SOURCE_BINDING_INVALID")
    selection = build_completed_evidence_selection(canonical_subject_identity=i["subject"],
        analysis_boundary=facts.observation_boundary, current_schedule=facts.current_schedule,
        previous_schedule=facts.previous_schedule, previous_daily=facts.previous_daily,
        previous_one_hour=facts.previous_one_hour, current_one_hour=facts.current_one_hour,
        current_fifteen_minute=facts.current_fifteen_minute, current_five_minute=facts.current_five_minute,
        provenance=("WO11_TIMING_ADAPTER_V1", facts.facts_identity),
        schedule_compatibility=getattr(facts, "schedule_compatibility", None))
    opening = nifty = None
    if selection.phase is IntradayAnalysisPhase.OPENING:
        from kronos.intraday.nifty_relative_context import build_nifty_relative_context
        from kronos.intraday.opening_semantic import build_opening_semantic_evidence
        candle = selection.candles(IntradayTimeframe.FIFTEEN_MINUTES)[0]
        direction = "LONG" if candle.close > candle.open else "SHORT" if candle.close < candle.open else "NON_DIRECTIONAL"
        nifty = build_nifty_relative_context(canonical_subject_identity=i["subject"],
            subject_schedule=facts.current_schedule, benchmark_schedule=None, subject_exchange=facts.subject_exchange,
            opening_direction=direction, analysis_boundary=facts.observation_boundary,
            subject_candle=candle, benchmark_candle=None, subject_session_open=candle.open,
            benchmark_session_open=None, provenance=("WO11_TIMING_NO_BENCHMARK_AUTHORITY",))
        opening = build_opening_semantic_evidence(selection=selection,
            narrow_cpr_fact=facts.previous_session_facts.narrow_cpr, nifty_relative_evidence=nifty,
            provenance=("WO11_TIMING_ADAPTER_V1",))
    semantic = build_semantic_qualification_evidence_v2(selection=selection,
        narrow_cpr_fact=facts.previous_session_facts.narrow_cpr,
        opening_semantic=opening, nifty_relative=nifty, provenance=("WO11_TIMING_ADAPTER_V1",))
    fact = semantic.fact("5M_PROGRESSION")
    progression = adapt_five_minute_progression(fact, inherited_direction=SemanticDirection(i["direction"]))
    candles = selection.candles(IntradayTimeframe.FIVE_MINUTES)
    if not candles:
        raise ValueError("WO11_COMPLETED_5M_UNAVAILABLE")
    candle = candles[-1]
    if (candle.candle_end <= instant(d["armed_at"]) or candle.candle_end > acquired_at
            or candle.candle_identity not in fact.source_evidence_identities):
        raise ValueError("WO11_POST_ARM_TIMING_REQUIRED")
    aligned = progression.semantics is Wo15ProgressionSemantics.ALIGNED
    close_qualified = candle.close > price(i["canonical_entry"]) if i["direction"] == "LONG" else candle.close < price(i["canonical_entry"])
    return record("WO11_TIMING_V1", authorization_identity=d["authorization_identity"],
        qualified=aligned and close_qualified, completed_at=candle.candle_end, qualified_at=acquired_at,
        source=facts, selection=selection, progression=progression, semantic=semantic,
        canonical_entry=i["canonical_entry"], historical_timing_policy_checksum=WO15_POLICY_CHECKSUM,
        algorithm="EXISTING_ALIGNED_PULLBACK_STRICT_COMPLETED_CLOSE_NO_RETEST")


class GovernedLifecycleTimingSource:
    def __init__(self, *, factory, calendar, reconciliation, resolutions, clock):
        self.factory, self.calendar, self.reconciliation = factory, calendar, reconciliation
        self.resolutions, self.clock = resolutions, clock

    def __call__(self, track):
        i = track.data["intake"]; now = self.clock()
        rows = [m for m in self.reconciliation.members if m.canonical_identity == i["subject"]]
        if len(rows) != 1:
            raise ValueError("WO11_TIMING_SUBJECT_NOT_RESOLVED")
        resolutions = self.resolutions()
        if i["contract"]["active_mcx"] is not None:
            if resolutions is None:
                raise ValueError("WO11_MCX_TIMING_BINDING_UNAVAILABLE")
            binding = resolutions.for_subject(i["subject"]).binding
            if binding is None or binding.binding_identity != i["contract"]["active_mcx"]["active_binding"]["binding_identity"]:
                raise ValueError("WO11_MCX_TIMING_BINDING_CHANGED")
        session, boundary = governed_market_session_identities(calendar_publisher=self.calendar,
            reconciliation=self.reconciliation, observed_at=now, active_derivative_resolutions=resolutions)
        source = self.factory(resolutions)
        acquired = source.acquire(member=rows[0], boundary=DiscoveryRunBoundary(now, session, boundary))
        if acquired.probables_v2_facts is None:
            raise ValueError("WO11_TIMING_FACTS_UNAVAILABLE")
        return qualify_timing(track, acquired.probables_v2_facts, acquired_at=self.clock())
