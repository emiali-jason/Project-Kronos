"""WO-06E read-only context inventory of the exact original research cohort."""
from collections import Counter
from pathlib import Path
from decimal import Decimal, Context, ROUND_HALF_EVEN, localcontext

from kronos.application.intraday_cpr_research import analyze_retained, distribution
from kronos.application.intraday_population_measurement import IntradayPopulationMeasurement
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.probables_v2_diagnostics_persistence import ProbablesV2DiagnosticsStore
from kronos.intraday.cpr_context_research import NOT_ESTABLISHED, POLICY, CprContextError, width_range_statistics
from kronos.intraday.population_measurement import identity

FEATURES = ("cpr_direction", "cpr_relationship", "price_location", "virgin_cpr",
            "two_day_narrow", "three_day_narrow", "atr_normalization")


def missing_context(mapping, facts):
    """Inventory the verified one-Daily V2 source contract, not legacy artifacts.

    A future expanded contract requires explicit adapter review, rather than
    being silently flattened into this historical inventory. No candle close is
    relabelled as an already-authoritative price relationship or Assessment Price.
    """
    if (mapping.canonical_subject_identity != facts.canonical_subject_identity
            or mapping.analysis_boundary != facts.observation_boundary
            or len(facts.previous_daily) != 1):
        raise CprContextError("CONTEXT_SOURCE_REVIEW_REQUIRED")
    allowed = {"1D_CONTEXT", "1H_REGIME", "15M_STRUCTURE", "5M_PROGRESSION",
               "DIRECTIONAL_COHERENCE", "OPENING_15M", "NIFTY_RELATIVE_CONTEXT"}
    if any(f.family not in allowed for f in mapping.semantic_evidence.facts):
        raise CprContextError("CONTEXT_SEMANTIC_REVIEW_REQUIRED")
    return {name: dict(value=NOT_ESTABLISHED, availability="NOT_RETAINED",
                      reason=("NO_SAME_RUN_PRIOR_CPR_SOURCE" if name in {
                          "cpr_direction", "cpr_relationship", "two_day_narrow", "three_day_narrow"}
                              else "NO_PROVED_COMPLETE_VIRGIN_HISTORY" if name == "virgin_cpr"
                              else "NO_RETAINED_AUTHORITATIVE_PRICE_RELATIONSHIP" if name == "price_location"
                              else "NO_EXACT_ATR_EVIDENCE")) for name in FEATURES}


def _group(rows):
    return dict(count=len(rows), narrow=dict(Counter(str(r["narrow"]) for r in rows)),
                features={k: dict(Counter(r["context"][k]["value"] for r in rows)) for k in FEATURES},
                half_width_pct=distribution(r["half_width_pct"] for r in rows),
                prior_range_pct=distribution(r["prior_range_pct"] for r in rows))


def _normalization(rows):
    ratios = [str(Decimal(r["total_width_pct"])/Decimal(r["prior_range_pct"]))
              for r in rows if Decimal(r["prior_range_pct"]) > 0]
    return dict(**width_range_statistics(rows), full_width_over_previous_range=distribution(ratios),
                zero_range_excluded=len(rows)-len(ratios))


def analyze_context(root: Path):
    # Preserve the original function/result identity; never mutate its rows.
    original = analyze_retained(root)
    populations = IntradayPopulationMeasurement(ProbablesV2Store(root)).history()
    envelopes = [ProbablesV2DiagnosticsStore(root).load_envelope(p.stem)
                 for p in sorted((root/"refresh-v2/diagnostics/replay-envelopes").glob("*.json"))]
    mappings = {m.mapping_identity: m for p in populations for m in p.mappings}
    joined = {}
    for p in populations:
        matches = [e for e in envelopes if e.discovery_run.run_identity == p.run.source_discovery_run_identity
                   and e.methodology_version == p.run.methodology.methodology_version]
        if len(matches) > 1:
            raise CprContextError("CONTEXT_ENVELOPE_AMBIGUOUS")
        if matches:
            for f in matches[0].probables_v2_facts:
                key = (p.run.run_identity, f.canonical_subject_identity)
                if key in joined:
                    raise CprContextError("CONTEXT_FACT_DUPLICATE")
                joined[key] = f
    rows = []
    for r in original["rows"]:
        if not r["eligible"]:
            continue
        f = joined.get((r["run"], r["subject"]))
        if f is None or f.previous_session_facts.narrow_cpr.fact_identity != r["cpr_fact"]:
            raise CprContextError("CONTEXT_CPR_BINDING_INVALID")
        context = missing_context(mappings[r["source_mapping"]], f)
        context["virgin_cpr"]["availability"] = "NOT_ESTABLISHED"
        rows.append(dict(r, context=context))
    subsets = {"all": rows,
               "baseline": [r for r in rows if r["baseline"]["state"].endswith("_PROBABLE")],
               "sole_blockers": [r for r in rows if not r["baseline"]["state"].endswith("_PROBABLE")
                                 and r["counterfactual"]["state"].endswith("_PROBABLE")]}
    groups = {k: _group(v) for k, v in subsets.items()}
    strata = {key: {value: {label: _group([r for r in subset if r[key] == value])
                           for label, subset in subsets.items()}
                    for value in sorted({r[key] for r in rows})}
              for key in ("phase", "direction", "subject", "subject_type")}
    normal = {}
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        for market in ("NSE", "MCX"):
            selected = [r for r in rows if (r["subject_type"] == "MCX") == (market == "MCX")]
            distinct = {(r["subject"], r["previous_session"]): r for r in selected}
            normal[market] = dict(raw=_normalization(selected), distinct_daily=_normalization(list(distinct.values())))
    result = dict(policy=POLICY, authority="RESEARCH_ONLY", original_research_identity=original["research_identity"],
                  original_counts=original["counts"], original_dependencies=original["dependencies"],
                  groups=groups, strata=strata, normalization=normal, rows=rows,
                  combined_context="NOT_ESTABLISHED", predictive_value="NOT_ESTABLISHED",
                  price_anchor="NO_ASSESSMENT_PRICE_RECONSTRUCTION")
    result["research_identity"] = identity("WO06E-CONTEXT-", result)
    return result
