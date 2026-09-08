"""WO-06F read-only adapter. Existing WO-06E result is an input, not rerun.

No runtime composition, Provider adapter, publication, or filesystem write seam.
Source roots are caller-owned; report serialization belongs to the research job.
"""
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from kronos.application.intraday_population_measurement import IntradayPopulationMeasurement
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.probables_v2_diagnostics_persistence import ProbablesV2DiagnosticsStore
from kronos.intraday.mcx_history import parse_retained_mcx_candle
from kronos.intraday.population_measurement import identity
from kronos.intraday.technical_context_research import (
    Window, TF, POLICY, NE, ResearchError, sma, vwap, volume, movement, native_binding, joined, comparison,
)

EXPECTED = dict(raw=882, eligible=572, baseline_admitted=33, no_cpr_admitted=107,
                additional=74, removed=0, sole_cpr=74, cpr_plus_other=329)
ACCEPTED_CPR_IDENTITY = "WO06E-RESEARCH-1d118f57ed95cc58a4d304e97a635ed1dc72cad5f6262a90d6bd7eddb314b015"
PAIRS = ("SMA20_VWAP_5M", "SMA50_VWAP_5M", "CPR_WIDTH_VWAP_5M",
         "STRUCTURE15M_VOLUME5M", "NIFTY_SMA20_5M", "NIFTY_VWAP_5M")


def verify_original(original):
    body = dict(original)
    key = body.pop("research_identity", None)
    if key != ACCEPTED_CPR_IDENTITY or key != identity("WO06E-RESEARCH-", body):
        raise ResearchError("CPR_INPUT_INTEGRITY_INVALID")
    if any(original["counts"].get(k) != v for k, v in EXPECTED.items()):
        raise ResearchError("CPR_COHORT_CHANGED")
    rows = original["rows"]
    if len(rows) != 882 or len({r["source_result"] for r in rows}) != 882:
        raise ResearchError("CPR_ROW_MEMBERSHIP_INVALID")
    return key


def project(facts, mapping, retained, subject_type):
    if (facts.canonical_subject_identity != mapping.canonical_subject_identity
            or facts.observation_boundary != mapping.analysis_boundary):
        raise ResearchError("FACT_MAPPING_BINDING_INVALID")
    operation = "INTRADAY-DISCOVERY-V2-SEMANTIC:" + facts.discovery_bundle_identity
    windows = {}
    for key, candles, schedule, tf in (
        ("1D", facts.previous_daily, facts.previous_schedule, TF.DAILY),
        ("prior1H", facts.previous_one_hour, facts.previous_schedule, TF.ONE_HOUR),
        ("1H", facts.current_one_hour, facts.current_schedule, TF.ONE_HOUR),
        ("15M", facts.current_fifteen_minute, facts.current_schedule, TF.FIFTEEN_MINUTES),
        ("5M", facts.current_five_minute, facts.current_schedule, TF.FIVE_MINUTES),
    ):
        windows[key] = Window(facts.canonical_subject_identity, tf, facts.observation_boundary,
                              operation, schedule, tuple(candles))
    native = {}
    smas = {}
    for tf, sequence in (("1D", [windows["1D"]]), ("1H", [windows["prior1H"], windows["1H"]]),
                          ("15M", [windows["15M"]]), ("5M", [windows["5M"]])):
        bound = native_binding(joined(sequence), retained) if subject_type == "MCX" else dict(state="NOT_APPLICABLE")
        native[tf] = bound
        smas[tf] = (sma(sequence) if bound["state"] != NE else
                    dict(availability=NE, reason=bound["reason"], periods={}, strict_stack=NE))
    bearing = subject_type in {"NSE_EQUITY", "MCX"}
    bound5 = native["5M"]["state"] != NE
    vw = vwap(windows["5M"], volume_bearing=bearing) if bound5 else dict(availability=NE, side=NE, reason=native["5M"]["reason"])
    vol = volume(windows["5M"], volume_bearing=bearing) if bound5 else dict(availability=NE, change=NE)
    relative = mapping.nifty_relative
    nifty = str(relative.relationship) if relative is not None else "NOT_APPLICABLE_OR_NOT_RETAINED"
    local = movement(windows["15M"]) if native["15M"]["state"] != NE else dict(direction=NE)
    return dict(facts_identity=facts.facts_identity, facts_integrity=facts.integrity_identity,
                source_mapping=mapping.mapping_identity, native_binding=native, sma=smas, vwap=vw, volume=vol,
                structure_15m=local, published_participation=mapping.semantic_evidence.participation_state,
                published_facts=[dict(family=str(f.family), direction=str(f.direction), role=str(f.evidence_role),
                                      identity=f.fact_identity, attributes=dict(f.attributes)) for f in mapping.semantic_evidence.facts],
                nifty_relationship=nifty, break_retest_return_through=NE, explicit_range=NE,
                missing_structure_reason="NO_EXACT_COHORT_BOUND_BARRIER_EVENT_OR_EXPLICIT_RANGE_ARTIFACT")


def features(row):
    p = row.get("technical")
    if not p:
        return {k: "INELIGIBLE" for k in PAIRS}
    periods = p["sma"]["5M"]["periods"]
    s20 = periods.get("20", {}).get("price_side", NE)
    s50 = periods.get("50", {}).get("price_side", NE)
    vs = p["vwap"].get("side", NE)
    # NIFTY relationship vocabulary is retained verbatim; no unsupported sign mapping.
    return dict(SMA20_VWAP_5M=comparison(s20, vs), SMA50_VWAP_5M=comparison(s50, vs),
                CPR_WIDTH_VWAP_5M=str(row["narrow"])+":"+vs,
                STRUCTURE15M_VOLUME5M=p["structure_15m"]["direction"]+":"+p["volume"]["change"],
                NIFTY_SMA20_5M=p["nifty_relationship"]+":"+s20,
                NIFTY_VWAP_5M=p["nifty_relationship"]+":"+vs)


def summarize(rows):
    technical = [r["technical"] for r in rows if r.get("technical")]
    result = dict(observations=len(rows), eligible=len(technical),
                  subject_session_groups=len({(r["subject"], r["session"]) for r in rows}),
                  independence_claim="NONE", matrices={k: dict(Counter(features(r)[k] for r in rows)) for k in PAIRS})
    result["availability"] = {
        "vwap": dict(Counter(p["vwap"]["availability"] for p in technical)),
        "volume": dict(Counter(p["volume"]["availability"] for p in technical)),
        "published_participation": dict(Counter(p["published_participation"] for p in technical)),
    }
    result["sma"] = {tf: {str(period): dict(
        availability=dict(Counter(p["sma"][tf]["periods"].get(str(period), {}).get("availability", NE) for p in technical)),
        slope=dict(Counter(p["sma"][tf]["periods"].get(str(period), {}).get("slope", NE) for p in technical)),
        price_side=dict(Counter(p["sma"][tf]["periods"].get(str(period), {}).get("price_side", NE) for p in technical)),
    ) for period in (20, 50, 200)} for tf in ("1D", "1H", "15M", "5M")}
    result["vwap_side"] = dict(Counter(p["vwap"].get("side", NE) for p in technical))
    result["vwap_slope"] = dict(Counter(p["vwap"].get("slope", NE) for p in technical))
    result["volume_normalization"] = dict(Counter(p["volume"].get("normalization", NE) for p in technical))
    return result


def analyze(root: Path, original: dict):
    original_identity = verify_original(original)
    populations = IntradayPopulationMeasurement(ProbablesV2Store(root)).history()
    if {p.run.run_identity for p in populations} != {r["run"] for r in original["rows"]}:
        raise ResearchError("SOURCE_RUN_MEMBERSHIP_CHANGED")
    envelopes = [ProbablesV2DiagnosticsStore(root).load_envelope(p.stem)
                 for p in sorted((root/"refresh-v2/diagnostics/replay-envelopes").glob("*.json"))]
    original_rows = {r["source_result"]: r for r in original["rows"]}
    retained = defaultdict(list)
    for path in sorted((root/"mcx-contract-history-v1").rglob("*.json")):
        m = parse_retained_mcx_candle(path.read_bytes())
        retained[(m.canonical_subject_identity, m.source_operation_identity, m.timeframe, m.candle_start, m.candle_end)].append(m)
    rows = []
    for population in populations:
        run = population.run
        matches = [e for e in envelopes if e.discovery_run.run_identity == run.source_discovery_run_identity
                   and e.methodology_version == run.methodology.methodology_version]
        if len(matches) > 1:
            raise ResearchError("REPLAY_AMBIGUOUS")
        facts = {f.canonical_subject_identity: f for f in matches[0].probables_v2_facts} if matches else {}
        if matches and len(facts) != len(matches[0].probables_v2_facts):
            raise ResearchError("FACT_DUPLICATE")
        mappings = {m.mapping_identity: m for m in population.mappings}
        for source in run.results:
            r = original_rows.get(source.result_identity)
            if (r is None or r["run"] != run.run_identity or r["subject"] != source.canonical_subject_identity
                    or r["source_mapping"] != source.source_mapping_identity
                    or r["baseline"]["state"] != source.state.value
                    or r["boundary"] != source.analysis_boundary.isoformat()):
                raise ResearchError("SOURCE_RESULT_BINDING_INVALID")
            output = dict(r)
            if r["eligible"]:
                f = facts.get(r["subject"])
                if f is None or f.previous_session_facts.narrow_cpr.fact_identity != r["cpr_fact"]:
                    raise ResearchError("CPR_FACT_BINDING_INVALID")
                output["technical"] = project(f, mappings[r["source_mapping"]], retained, r["subject_type"])
            rows.append(output)
    if len(rows) != 882:
        raise ResearchError("DENOMINATOR_CHANGED")
    rows.sort(key=lambda r: (r["boundary"], r["run"], r["subject"]))
    subsets = dict(all=rows, eligible=[r for r in rows if r["eligible"]],
                   baseline=[r for r in rows if r["baseline"]["state"].endswith("_PROBABLE")],
                   sole_blockers=[r for r in rows if not r["baseline"]["state"].endswith("_PROBABLE")
                                  and r["counterfactual"]["state"].endswith("_PROBABLE")])
    result = dict(policy=POLICY, authority="RESEARCH_ONLY", original_identity=original_identity,
                  original_counts=original["counts"], original_dependencies=original["dependencies"],
                  groups={k: summarize(v) for k, v in subsets.items()},
                  strata={key: {str(value): {label: summarize([r for r in subset if r[key] == value])
                                        for label, subset in subsets.items()}
                                for value in sorted({r[key] for r in rows}, key=str)}
                          for key in ("phase", "direction", "subject_type", "subject")}, rows=rows,
                  predictive_value=NE, assessment_price_backfills=0, production_authority="NONE")
    result["research_identity"] = identity("WO06F-RESEARCH-", result)
    return result
