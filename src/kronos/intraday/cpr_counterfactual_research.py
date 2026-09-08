"""WO-06E isolated matched CPR research; no producer or trading authority.

Both arms use the same reviewed decision transcription. Only the two CPR gates
vary. Research decisions never masquerade as persisted Probables artifacts.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from hashlib import sha256
from inspect import getsource
from typing import Mapping

from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import (
    DiscoveryProbablesEvidenceV2, ProbableReasonV2, IntradayAnalysisPhase,
    SemanticDirection, OpeningRelationship, NiftyApplicability, NiftyRelationship,
    PROBABLES_V2_CORRECTION_METHODOLOGY_VERSION, _coherent_direction,
    load_mcx_commissioning_publication, McxCommissioningState,
    _evaluate_member, _mcx_commissioning_provenance,
)
from kronos.intraday.completed_evidence import EvidenceSessionRole
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.population_measurement import (
    MeasurementPopulation, PopulationMember, PopulationSlice, ADMITTED, identity,
)
from kronos.intraday.qualification import (
    NarrowCprFact, PreviousCompletedDailyCandle, create_narrow_cpr_fact,
)
from kronos.intraday.source_binding import require_cpr_source_binding

SCHEMA = "WO06E-MATCHED-CPR-RESEARCH-V1"
VERSIONS = frozenset(("2.0.0", "2.1.0", "2.2.0"))


class CprResearchError(ValueError):
    """Bounded research rejection; never grants producer authority."""


@dataclass(frozen=True)
class Decision:
    state: ProbableState
    direction: SemanticDirection | None
    reasons: tuple[ProbableReasonV2, ...]

    @property
    def admitted(self) -> bool:
        return self.state in ADMITTED

    def record(self) -> dict:
        return dict(state=self.state.value,
            direction=None if self.direction is None else self.direction.value,
            reasons=[r.value for r in self.reasons])


def _decision_result(value, state, direction, reasons):
    return Decision(state, direction, reasons)


REVIEWED_EVALUATOR_SHA256 = '74efc219c1116add4b37b02fc6c0f065f5c33d3681dbf090ba5eb1911390c93c'


def _decision(value: DiscoveryProbablesEvidenceV2, *, require_cpr: bool) -> Decision:
    semantic = value.semantic_evidence
    if value.completed_evidence.market_identity == "MCX":
        commissioning = load_mcx_commissioning_publication().subject(
            value.canonical_subject_identity
        )
        if commissioning.state is McxCommissioningState.HELD:
            return _decision_result(
                value, ProbableState.UNAVAILABLE, None,
                (ProbableReasonV2.MCX_V2_EMPIRICAL_COMMISSIONING_REQUIRED,),
            )
    if value.phase is IntradayAnalysisPhase.OPENING:
        assert value.opening_semantic is not None and value.nifty_relative is not None
        opening = value.opening_semantic.fact
        direction = opening.opening_direction
        if (
            value.nifty_relative.fact.applicability is NiftyApplicability.APPLICABLE
            and value.nifty_relative.relationship is NiftyRelationship.UNAVAILABLE
        ):
            return _decision_result(
                value, ProbableState.UNAVAILABLE, None,
                (ProbableReasonV2.NIFTY_CONTEXT_UNAVAILABLE,),
            )
        if require_cpr and not semantic.narrow_cpr_qualified:
            return _decision_result(
                value, ProbableState.NOT_ADMITTED, direction,
                (ProbableReasonV2.NARROW_CPR_NOT_SATISFIED,),
            )
        if direction is SemanticDirection.NON_DIRECTIONAL:
            return _decision_result(
                value, ProbableState.NOT_ADMITTED, direction,
                (ProbableReasonV2.OPENING_NON_DIRECTIONAL,),
            )
        reasons: list[ProbableReasonV2] = []
        if opening.prior_one_hour_relationship is OpeningRelationship.CONFLICTING:
            reasons.append(ProbableReasonV2.PRIOR_1H_CONFLICTING_NO_DIRECTION_FLIP)
        # Historical publications preserve the extra 5M support gate exactly.
        # The correction uses the already validated combined relationship below.
        if (
            value.methodology_version != PROBABLES_V2_CORRECTION_METHODOLOGY_VERSION
            and opening.five_minute_relationship is not OpeningRelationship.SUPPORTING
        ):
            reasons.append(ProbableReasonV2.OPENING_5M_NOT_SUPPORTING)
        if value.nifty_relative.relationship is NiftyRelationship.CONFLICTING:
            reasons.append(ProbableReasonV2.NIFTY_CONTEXT_CONFLICTING_NO_DIRECTION_FLIP)
        if not reasons and value.opening_semantic.combined_relationship is not OpeningRelationship.SUPPORTING:
            reasons.append(ProbableReasonV2.OPENING_RELATIONSHIP_NOT_SUPPORTING)
        if reasons:
            return _decision_result(value, ProbableState.NOT_ADMITTED, direction, tuple(reasons))
        state = (
            ProbableState.LONG_PROBABLE
            if direction is SemanticDirection.LONG
            else ProbableState.SHORT_PROBABLE
        )
        return _decision_result(
            value, state, direction,
            (ProbableReasonV2.V2_CONDITIONS_SATISFIED,),
        )
    hourly = semantic.fact("1H_REGIME")
    fifteen = semantic.fact("15M_STRUCTURE")
    if require_cpr and not semantic.narrow_cpr_qualified:
        return _decision_result(
            value, ProbableState.NOT_ADMITTED, _coherent_direction(hourly.direction, fifteen.direction),
            (ProbableReasonV2.NARROW_CPR_NOT_SATISFIED,),
        )
    if hourly.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}:
        return _decision_result(
            value, ProbableState.NOT_ADMITTED, hourly.direction,
            (ProbableReasonV2.ONE_HOUR_NON_DIRECTIONAL,),
        )
    if fifteen.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}:
        return _decision_result(
            value, ProbableState.NOT_ADMITTED, fifteen.direction,
            (ProbableReasonV2.FIFTEEN_MINUTE_NON_DIRECTIONAL,),
        )
    if hourly.direction is not fifteen.direction:
        return _decision_result(
            value, ProbableState.NOT_ADMITTED, SemanticDirection.CONFLICTING,
            (ProbableReasonV2.DIRECTION_CONFLICTING,),
        )
    state = (
        ProbableState.LONG_PROBABLE
        if hourly.direction is SemanticDirection.LONG
        else ProbableState.SHORT_PROBABLE
    )
    return _decision_result(
        value, state, hourly.direction,
        (ProbableReasonV2.V2_CONDITIONS_SATISFIED,),
    )


def _validate_cpr(mapping, fact):
    if fact is None:
        raise CprResearchError("CPR_FACT_NOT_RETAINED")
    require_cpr_source_binding(mapping.completed_evidence, fact)
    source, = mapping.completed_evidence.candles(
        IntradayTimeframe.DAILY, EvidenceSessionRole.PREVIOUS_SESSION_DAILY)
    # Exact retained formula only, never a substitute Assessment Price. Alternate
    # arithmetic fails eligibility; no rounding tolerance or threshold relaxation.
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        rebuilt = create_narrow_cpr_fact(PreviousCompletedDailyCandle(
            canonical_subject_identity=fact.canonical_subject_identity,
            previous_session_identity=fact.previous_session_identity,
            observation_session_identity=fact.observation_session_identity,
            source_daily_candle_identity=fact.source_daily_candle_identity,
            completed_at=source.candle_end, observation_boundary=fact.observation_boundary,
            high=fact.previous_daily_high, low=fact.previous_daily_low,
            close=fact.previous_daily_close, completed=True,
            source_integrity_identity=fact.source_integrity_identity, provenance=fact.provenance))
    if rebuilt != fact:
        raise CprResearchError("CPR_FORMULA_NOT_REPRODUCED")
    semantic = mapping.semantic_evidence
    if (semantic.narrow_cpr_fact_identity != fact.fact_identity
        or semantic.narrow_cpr_qualified != fact.narrow_cpr_kgs_v0):
        raise CprResearchError("CPR_SEMANTIC_BINDING_MISMATCH")


def compare_population(population: MeasurementPopulation,
                       facts: Mapping[str, NarrowCprFact]) -> tuple[dict, ...]:
    """Complete denominator, including every ineligible/unavailable source row.

    Facts use exact fact identities from validated retained envelopes. No latest
    fact fallback or persistence. Availability and historical versions stay frozen.
    """
    if type(population) is not MeasurementPopulation:
        raise CprResearchError("POPULATION_INVALID")
    population.__post_init__()
    if sha256(getsource(_evaluate_member).encode()).hexdigest() != REVIEWED_EVALUATOR_SHA256:
        raise CprResearchError("EVALUATOR_REVIEW_REQUIRED")
    mapped = {m.mapping_identity:m for m in population.mappings}
    rows = []
    for result in population.run.results:
        baseline = Decision(result.state, result.direction, result.reasons)
        subject = result.canonical_subject_identity
        row = dict(run=population.run.run_identity, source_result=result.result_identity,
            subject=subject, session=result.market_session_identity,
            boundary=result.analysis_boundary.isoformat(), phase=None if result.phase is None else result.phase.value,
            direction=None if result.direction is None else result.direction.value,
            methodology=result.methodology_version,
            methodology_publication=result.methodology_publication_identity,
            methodology_checksum=result.methodology_checksum,
            source_mapping=result.source_mapping_identity,
            subject_type=("MCX" if subject.startswith("MCX-") else "NIFTY" if subject=="NSE-INDEX-NIFTY"
                else "BANKNIFTY" if subject=="NSE-INDEX-BANKNIFTY" else "NSE_EQUITY"),
            baseline=baseline.record(), counterfactual=None, eligible=False,
            exclusion_reason=None, narrow=None, trading_date=None, classification="OTHER_GOVERNED_STATE")
        if result.state is ProbableState.UNAVAILABLE:
            row["exclusion_reason"] = "GOVERNED_UNAVAILABLE:" + ",".join(r.value for r in result.reasons)
            # Current commissioning cannot retroactively admit old held MCX rows.
            row["counterfactual"] = baseline.record()
            rows.append(row)
            continue
        mapping = mapped.get(result.source_mapping_identity)
        if mapping is None:
            row["exclusion_reason"] = "SOURCE_MAPPING_NOT_RETAINED"
            rows.append(row)
            continue
        try:
            if mapping.methodology_version not in VERSIONS:
                raise CprResearchError("HISTORICAL_METHODOLOGY_UNSUPPORTED")
            fact = facts.get(mapping.semantic_evidence.narrow_cpr_fact_identity)
            _validate_cpr(mapping, fact)
            if mapping.completed_evidence.market_identity == "MCX":
                publication = load_mcx_commissioning_publication()
                if (result.analysis_boundary < publication.effective_boundary or
                    not set(_mcx_commissioning_provenance(mapping)).issubset(result.provenance)):
                    raise CprResearchError("HISTORICAL_MCX_AUTHORITY_NOT_REPRODUCED")
            reproduced = _decision(mapping, require_cpr=True)
            governed = _evaluate_member(mapping)
            if (reproduced != baseline or
                Decision(governed.state, governed.direction, governed.reasons) != baseline):
                raise CprResearchError("HISTORICAL_BASELINE_NOT_REPRODUCED")
            alternative = _decision(mapping, require_cpr=False)
            if baseline.admitted and alternative != baseline:
                raise CprResearchError("COUNTERFACTUAL_REMOVED_OR_CHANGED_ADMISSION")
        except (ValueError, RuntimeError) as error:
            row["exclusion_reason"] = (str(error) if isinstance(error, CprResearchError)
                else "SOURCE_BINDING_OR_INTEGRITY_INVALID")
            rows.append(row)
            continue
        with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
            prior_range_pct = (fact.previous_daily_high-fact.previous_daily_low)/fact.previous_daily_close*100
        dates = {c.candle.candle_start.date().isoformat() for c in mapping.completed_evidence.selected_candles
            if c.original_market_session_identity == mapping.completed_evidence.current_market_session_identity}
        row.update(trading_date=next(iter(dates)) if len(dates)==1 else None,
            eligible=True, counterfactual=alternative.record(), narrow=fact.narrow_cpr_kgs_v0,
            cpr_fact=fact.fact_identity, cpr_integrity=fact.integrity_identity,
            source_daily=fact.source_daily_candle_identity,
            previous_session=fact.previous_session_identity,
            half_width=str(fact.cpr_half_width), half_width_pct=str(fact.cpr_half_width_pct),
            total_width_pct=str(fact.cpr_total_width_pct), prior_range_pct=str(prior_range_pct),
            classification=("ADMITTED_WITH_CPR_AND_WITHOUT_CPR" if baseline.admitted else
                "REJECTED_WITH_CPR_ADMITTED_WITHOUT_CPR" if alternative.admitted else "REJECTED_BOTH"))
        rows.append(row)
    return tuple(rows)


def counts(rows) -> dict:
    rows = tuple(rows)
    eligible = [r for r in rows if r["eligible"]]
    admitted = lambda r: r["state"] in {s.value for s in ADMITTED}
    baseline = sum(admitted(r["baseline"]) for r in eligible)
    alternative = sum(admitted(r["counterfactual"]) for r in eligible)
    added = sum(not admitted(r["baseline"]) and admitted(r["counterfactual"]) for r in eligible)
    removed = sum(admitted(r["baseline"]) and not admitted(r["counterfactual"]) for r in eligible)
    return dict(raw=len(rows), eligible=len(eligible), ineligible=len(rows)-len(eligible),
        baseline_admitted=baseline, no_cpr_admitted=alternative, additional=added,
        removed=removed, unchanged_admitted=baseline-removed,
        unchanged_rejected=len(eligible)-baseline-added,
        narrow=sum(r["narrow"] for r in eligible),
        non_narrow=sum(not r["narrow"] for r in eligible), sole_cpr=added,
        cpr_plus_other=sum(not r["narrow"] and r["classification"]=="REJECTED_BOTH" for r in eligible))


def stratify(rows, field) -> dict:
    rows = tuple(rows)
    return {str(key):counts(r for r in rows if r[field]==key)
        for key in sorted({r[field] for r in rows}, key=str)}


def research_slice(population: MeasurementPopulation, rows, *, counterfactual: bool) -> PopulationSlice:
    """Full-denominator input to WO-06D's proposed dependence policy.

    Unverifiable comparisons block grouping rather than assuming rejection.
    Returned identities are research-only, never producer artifacts/currentization.
    """
    rows = tuple(rows)
    original = {r.result_identity:r for r in population.run.results}
    if len(rows)!=len(original) or {r["source_result"] for r in rows}!=set(original):
        raise CprResearchError("RESEARCH_POPULATION_INCOMPLETE")
    members=[]
    for row in rows:
        source = original[row["source_result"]]
        result = row["counterfactual" if counterfactual else "baseline"]
        if (row["run"]!=population.run.run_identity or result is None
            or row["subject"]!=source.canonical_subject_identity
            or row["session"]!=source.market_session_identity or row["phase"]!=(None if source.phase is None else source.phase.value)):
            raise CprResearchError("RESEARCH_POPULATION_UNVERIFIABLE")
        admitted = result["state"] in {s.value for s in ADMITTED}
        members.append(PopulationMember(row["subject"],row["session"],result["state"],
            result["direction"],row["phase"],
            identity("WO06E-RESEARCH-OBSERVATION-",[SCHEMA,row["run"],row["source_result"],counterfactual])
            if admitted else None))
    return PopulationSlice(population.run.run_identity,population.run.analysis_boundary,tuple(members))
