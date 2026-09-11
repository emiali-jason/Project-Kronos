"""Translate verified Native selections to unchanged WO-13 geometry inputs."""
from kronos.intraday.wo10_construction import adapt_wo09
from kronos.intraday.wo13_handoff import Wo13SetupFamily
from kronos.intraday.wo13_geometry import (Wo13StructuralRole, Wo13PriceAuthority, Wo13TargetCandidateKind,
    create_wo13_structural_price_fact, create_wo13_target_candidate)
from kronos.intraday.wo13_pullback import (create_wo13_pullback_fact_reference,
    create_wo13_pullback_geometry_evidence, construct_wo13_pullback_geometry)
from kronos.intraday.wo13_breakout import (create_wo13_breakout_fact_reference,
    create_wo13_breakout_geometry_evidence, construct_wo13_breakout_geometry)
from kronos.intraday.wo13_targets import create_wo13_target_constraint_population, Wo13TargetPopulationCompleteness
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.universe import IntradayMarketFamily


def adapt_native(selection, handoff, readiness, pointer, *, now):
    selection.__post_init__(); d = selection.data
    if d["target_completeness"] == "INCOMPLETE":
        raise ValueError("TARGET_POPULATION_INCOMPLETE")
    adapter = adapt_wo09(handoff, readiness, pointer, now=now, session_identity=d["session"],
        setup_family=(Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION if d["setup_family"] == "PULLBACK"
                      else Wo13SetupFamily.INTRADAY_RANGE_BREAKOUT),
        setup_evidence_identity=d["setup_identity"] if d["contract_version"] == "1.1.0" else d["machine_identity"],
        native_selection=selection if d["contract_version"] == "1.1.0" else None, instrument_identity=d["instrument_identity"])
    authority = {IntradayMarketFamily.NSE_EQUITY: Wo13PriceAuthority.NSE_EQUITY_UNDERLYING,
                 IntradayMarketFamily.NSE_INDEX: Wo13PriceAuthority.NSE_INDEX_UNDERLYING,
                 IntradayMarketFamily.MCX: Wo13PriceAuthority.MCX_ACTIVE_CONTRACT}[adapter.market_family]
    def fact(role, ref):
        return create_wo13_structural_price_fact(canonical_subject_identity=d["subject"], market_family=adapter.market_family,
            timeframe=IntradayTimeframe(ref["timeframe"]), price=ref["price"], structural_role=Wo13StructuralRole(role),
            price_authority=authority, structure_identity=ref["structure_identity"],
            source_evidence_identity=(ref["source_evidence_identity"] + ":" + ref["field"] if d["contract_version"] == "1.1.0" else ref["candle_identity"]),
            source_evidence_integrity=(ref["source_integrity"] if d["contract_version"] == "1.1.0" else ref["candle_integrity"]),
            analysis_boundary=adapter.analysis_boundary, instrument_identity=d["instrument_identity"],
            actual_contract_identity=d["exact_contract"], roll_lineage_identity=d["roll_lineage"], market_session_identity=ref.get("origin_session", d["session"]))
    facts = {r: fact(r, ref) for r, ref in d["roles"].items() if not r.startswith("ORIGIN_")}
    long = d["direction"] == "LONG"
    if d["setup_family"] == "PULLBACK":
        q = facts["QUALIFICATION_CANDLE_HIGH" if long else "QUALIFICATION_CANDLE_LOW"]
        p = facts["PULLBACK_STRUCTURAL_LOW" if long else "PULLBACK_STRUCTURAL_HIGH"]
        i = facts["PRIOR_IMPULSE_HIGH" if long else "PRIOR_IMPULSE_LOW"]
        ref = create_wo13_pullback_fact_reference
        evidence = create_wo13_pullback_geometry_evidence(handoff=adapter, market_session_identity=d["session"],
            qualification_references=(ref(q),), qualification_candles=(q,), pullback_references=(ref(p),),
            governing_pullback_structures=(p,), prior_impulse_references=(ref(i),), prior_impulse_extremes=(i,))
        geometry = construct_wo13_pullback_geometry(evidence)
    else:
        high, low = facts["RANGE_HIGH"], facts["RANGE_LOW"]
        q = facts["QUALIFICATION_CANDLE_LOW" if long else "QUALIFICATION_CANDLE_HIGH"]
        def ref(f):
            return create_wo13_breakout_fact_reference(fact=f, breakout_cycle_identity=d["setup_identity"],
                                                      breakout_direction=adapter.inherited_direction)
        evidence = create_wo13_breakout_geometry_evidence(handoff=adapter, breakout_direction=adapter.inherited_direction,
            market_session_identity=d["session"], original_range_identity=d["original_range_identity"],
            range_high_references=(ref(high),), range_high_facts=(high,), range_low_references=(ref(low),),
            range_low_facts=(low,), qualification_references=(ref(q),), qualification_candles=(q,))
        geometry = construct_wo13_breakout_geometry(evidence)
    target_rows = ([t for t in d["target_manifest"]["rows"] if t["included"]]
                   if d["contract_version"] == "1.1.0" else d["targets"])
    targets = tuple(create_wo13_target_candidate(entry_reference=geometry.entry_reference.selected_fact,
        candidate=fact(t["role"], t["reference"]), direction=adapter.inherited_direction,
        kind=Wo13TargetCandidateKind.STRUCTURAL_CONSTRAINT) for t in target_rows)
    population = create_wo13_target_constraint_population(setup_geometry=geometry, candidates=targets,
        completeness=Wo13TargetPopulationCompleteness.COMPLETE)
    return adapter, evidence, population
