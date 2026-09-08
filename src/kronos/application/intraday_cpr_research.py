"""Read-only WO-06E retained-evidence research, intentionally absent from runtime.

No retain/currentize/acquire/export operation. Callers may keep the compact result
in temporary research working storage under the Sponsor's retention policy.
"""
from collections import Counter
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path

from kronos.application.intraday_population_measurement import IntradayPopulationMeasurement
from kronos.intraday.cpr_counterfactual_research import (
    SCHEMA, CprResearchError, compare_population, counts, stratify, research_slice,
)
from kronos.intraday.population_measurement import longitudinal_population, EPISODE_POLICY, identity
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.probables_v2_diagnostics_persistence import ProbablesV2DiagnosticsStore


def distribution(values) -> dict:
    """Linear interpolated sample quantiles: rank q*(n-1), no normality assumption."""
    values = sorted(Decimal(v) for v in values)
    if not values:
        return dict(count=0, minimum=None, q1=None, median=None, q3=None, maximum=None)
    def quantile(numerator):
        rank = Decimal(numerator)*(len(values)-1)/4
        lower = int(rank)
        return values[lower] + (values[min(lower+1,len(values)-1)]-values[lower])*(rank-lower)
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        return dict(count=len(values), minimum=str(values[0]), q1=str(quantile(1)),
            median=str(quantile(2)), q3=str(quantile(3)), maximum=str(values[-1]))


def _width_summary(rows):
    return dict(half_width=distribution(r["half_width"] for r in rows),
        half_width_pct=distribution(r["half_width_pct"] for r in rows),
        total_width_pct=distribution(r["total_width_pct"] for r in rows),
        prior_range_pct=distribution(r["prior_range_pct"] for r in rows),
        narrow_prior_range_pct=distribution(r["prior_range_pct"] for r in rows if r["narrow"]),
        non_narrow_prior_range_pct=distribution(r["prior_range_pct"] for r in rows if not r["narrow"]))


def analyze_retained(root: Path) -> dict:
    populations = IntradayPopulationMeasurement(ProbablesV2Store(root)).history()
    envelopes = [ProbablesV2DiagnosticsStore(root).load_envelope(p.stem)
        for p in sorted((root/"refresh-v2/diagnostics/replay-envelopes").glob("*.json"))]
    rows=[]; runs=[]; baseline_slices=[]; alternative_slices=[]; grouping_errors=[]
    for population in populations:
        run=population.run
        matching=[e for e in envelopes if e.discovery_run.run_identity==run.source_discovery_run_identity
            and e.methodology_version==run.methodology.methodology_version]
        if len(matching)>1:
            raise CprResearchError("REPLAY_ENVELOPE_AMBIGUOUS")
        facts={}
        if matching:
            for value in matching[0].probables_v2_facts:
                fact=value.previous_session_facts.narrow_cpr
                if fact.fact_identity in facts and facts[fact.fact_identity]!=fact:
                    raise CprResearchError("CPR_FACT_CONFLICT")
                facts[fact.fact_identity]=fact
        paired=compare_population(population,facts)
        rows.extend(paired)
        runs.append(dict(run=run.run_identity,boundary=run.analysis_boundary.isoformat(),
            methodology=run.methodology.methodology_version,
            envelope=matching[0].envelope_identity if matching else None,
            denominators=population.denominators, comparison=counts(paired)))
        try:
            baseline_slices.append(research_slice(population,paired,counterfactual=False))
            alternative_slices.append(research_slice(population,paired,counterfactual=True))
        except CprResearchError as error:
            grouping_errors.append(dict(run=run.run_identity,reason=str(error)))
    eligible=[r for r in rows if r["eligible"]]
    unique_daily={}
    for row in eligible:
        key=(row["subject"],row["previous_session"])
        prior=unique_daily.get(key)
        if prior and any(prior[k]!=row[k] for k in ("half_width_pct","prior_range_pct","narrow")):
            raise CprResearchError("CPR_DAILY_CONFLICT")
        unique_daily[key]=row
    dependencies={"policy":EPISODE_POLICY,"independence_claim":"NONE","errors":grouping_errors}
    if not grouping_errors:
        for label,slices in (("baseline",baseline_slices),("no_cpr",alternative_slices)):
            transitions=longitudinal_population(slices)
            dependencies[label]=dict(
                admitted_raw=sum(t.observation_identity is not None for t in transitions),
                episodes=len({t.episode_identity for t in transitions if t.episode_identity}),
                transitions=dict(Counter(s for t in transitions for s in t.states)))
    # A calendar session is never split between earlier/later samples. This is a
    # descriptive partition only; no outcomes, trained threshold or holdout claim.
    sessions=sorted({r["session"] for r in eligible})
    dates=sorted({r["trading_date"] for r in eligible if r["trading_date"] is not None})
    earlier=dates[:(len(dates)+1)//2]
    later=dates[(len(dates)+1)//2:]
    chronological=dict(dates=dates, earlier_dates=earlier, later_dates=later,
        earlier=counts(r for r in rows if r["trading_date"] in earlier),
        later=counts(r for r in rows if r["trading_date"] in later),
        unknown_date=counts(r for r in rows if r["trading_date"] is None),
        meaningful_outcome_evaluation="NOT_ESTABLISHED", grouping="COMPLETE_SUBJECT_SESSION")
    result=dict(schema=SCHEMA,authority="RESEARCH_ONLY",runs=runs,counts=counts(rows),
        exclusions=dict(Counter(r["exclusion_reason"] for r in rows if not r["eligible"])),
        phase=stratify(rows,"phase"),direction=stratify(rows,"direction"),
        subject_type=stratify(rows,"subject_type"),subject=stratify(rows,"subject"),
        session=stratify(rows,"session"),methodology=stratify(rows,"methodology"),
        width_raw=_width_summary(eligible),width_distinct_daily=_width_summary(list(unique_daily.values())),
        distinct_daily=len(unique_daily),dependencies=dependencies,chronological=chronological,
        width_by_subject_type={key:_width_summary([r for r in eligible if r["subject_type"]==key])
            for key in sorted({r["subject_type"] for r in eligible})},
        nse_counts=counts(r for r in rows if r["subject_type"]!="MCX"),
        width_nse=_width_summary([r for r in eligible if r["subject_type"]!="MCX"]),
        subject_session_direction_groups={label:len({(r["subject"],r["session"],r[label]["direction"])
            for r in eligible if r[label]["state"].endswith("_PROBABLE")})
            for label in ("baseline","counterfactual")},
        sessions=sessions, historical_price_outcome="NOT_ESTABLISHED",
        baseline_missing_assessment=sum(p.denominators["missing_measurement"] for p in populations),
        rows=rows)
    result["research_identity"]=identity("WO06E-RESEARCH-",result)
    return result
