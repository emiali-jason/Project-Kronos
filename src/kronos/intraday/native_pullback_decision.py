"""Typed source manifests and immutable prospective Native decisions (policy V1)."""
from decimal import Decimal
from enum import StrEnum
import json
import re

from kronos.intraday.native_pullback_policy import APPROVED_POLICY, POLICY_ID, VERSION, CHECKSUM, Reason, select_cycle
from kronos.intraday.wo10_futures_contract import PROGRAMME, digest, encoded, normalize, moment

CONTRACT = "1.1.0"
SOURCE_PREFIX = "NATIVE-STRUCTURAL-SOURCE-"
MANIFEST_PREFIX = "NATIVE-TARGET-MANIFEST-"
CLASSES = ("SETUP_NATIVE_TARGET", "PDH_PDL", "CLASSIC_PIVOTS", "CURRENT_SESSION_EXTREMES", "GOVERNED_15M_BARRIERS")


class ReferenceKind(StrEnum):
    NATIVE = "SETUP_NATIVE_CANDLE_LEVEL"
    PRIOR = "PRIOR_SESSION_LEVEL"
    PIVOT = "DERIVED_PIVOT_LEVEL"
    SESSION = "CURRENT_SESSION_LEVEL"
    BARRIER = "GOVERNED_STRUCTURAL_BARRIER"


def source_document(facts, mapping, result, run_identity, *, mcx_binding=None, machine_bundle=None):
    """Seal owner-validated inputs, retaining their original typed wire identities."""
    from kronos.intraday.probables_v2_persistence import _to_wire
    from kronos.intraday.probables_v2_refresh import DiscoveryProbablesV2Facts, DiscoveryProbablesV2FactsV2
    from kronos.intraday.probables_v2 import DiscoveryProbablesEvidenceV2, ProbableMemberResultV2
    if type(facts) not in {DiscoveryProbablesV2Facts, DiscoveryProbablesV2FactsV2} or type(mapping) is not DiscoveryProbablesEvidenceV2 or type(result) is not ProbableMemberResultV2:
        raise ValueError(Reason.INTEGRITY.value)
    for x in (facts, mapping, result):
        x.__post_init__()
    if (facts.canonical_subject_identity != result.canonical_subject_identity
            or facts.observation_boundary != result.analysis_boundary
            or mapping.mapping_identity != result.source_mapping_identity
            or facts.facts_identity not in mapping.provenance
            or mapping.semantic_evidence.evidence_identity != result.semantic_evidence_identity
            or mapping.completed_evidence.selection_identity != result.completed_evidence_selection_identity
            or facts.current_schedule.session_id != result.market_session_identity):
        raise ValueError(Reason.BOUNDARY.value)
    population={c.candle_identity:c for c in (*facts.previous_daily,*facts.previous_one_hour,*facts.current_one_hour,*facts.current_fifteen_minute,*facts.current_five_minute)}
    if any(population.get(x.candle.candle_identity)!=x.candle for x in mapping.completed_evidence.selected_candles):
        raise ValueError(Reason.INTEGRITY.value)
    if mapping.completed_evidence.current_market_session_identity!=facts.current_schedule.session_id or mapping.completed_evidence.previous_market_session_identity!=facts.previous_schedule.session_id:
        raise ValueError(Reason.SESSION.value)
    if machine_bundle is not None:
        machine_bundle.__post_init__()
        if machine_bundle.bundle_identity!=facts.discovery_bundle_identity or machine_bundle.canonical_identity!=facts.canonical_subject_identity or machine_bundle.observation_boundary!=facts.observation_boundary:
            raise ValueError(Reason.INTEGRITY.value)
    binding = None
    if result.canonical_subject_identity.startswith("MCX-"):
        from kronos.instrument.active_derivative import active_derivative_binding_bytes
        if mcx_binding is None or machine_bundle is None:
            raise ValueError(Reason.MCX.value)
        mcx_binding.__post_init__()
        machine_bundle.__post_init__()
        if (mcx_binding.canonical_subject_id != result.canonical_subject_identity
                or not mcx_binding.active_binding.active_at(result.analysis_boundary)
                or machine_bundle.bundle_identity != facts.discovery_bundle_identity
                or mcx_binding.binding_identity not in machine_bundle.source_identities
                or mcx_binding.integrity_identity not in machine_bundle.provenance
                or mcx_binding.domain008_session_identity != facts.current_schedule.session_id):
            raise ValueError(Reason.MCX.value)
        binding = active_derivative_binding_bytes(mcx_binding).decode("utf-8")
    return dict(facts=_to_wire(facts), mapping=_to_wire(mapping), result=_to_wire(result),
                run_identity=run_identity, mcx_binding=binding, machine_bundle=_to_wire(machine_bundle))


def decode_source(source):
    from kronos.intraday.probables_v2_persistence import _from_wire
    if "failure" in source:
        m,r=(_from_wire(source[k]) for k in ("mapping","result"))
        if unavailable_source(m,r,source["run_identity"],source["failure"])!=source:raise ValueError(Reason.INTEGRITY.value)
        return None,m,r,None
    if set(source) != {"facts", "mapping", "result", "run_identity", "mcx_binding", "machine_bundle"}:
        raise ValueError(Reason.INTEGRITY.value)
    f,m,r = (_from_wire(source[k]) for k in ("facts","mapping","result"))
    binding = None
    if source["mcx_binding"] is not None:
        from kronos.instrument.active_derivative import parse_active_derivative_binding
        binding = parse_active_derivative_binding(source["mcx_binding"].encode("utf-8"))
    if source_document(f,m,r,source["run_identity"],mcx_binding=binding,machine_bundle=_from_wire(source["machine_bundle"])) != source:
        raise ValueError(Reason.INTEGRITY.value)
    return f,m,r,binding


def candle_reference(candle, field, structure, source_id):
    return dict(kind=ReferenceKind.NATIVE.value, source_identity=source_id,
        source_evidence_identity=candle.candle_identity, source_integrity=candle.integrity_identity,
        candle_identity=candle.candle_identity, field=field, price=str(getattr(candle,field.lower())),
        structure_identity=structure,timeframe=candle.timeframe.value,
        origin_session=candle.market_session_identity,origin_date=candle.candle_start.date().isoformat())


def _row(group, reference=None, *, role=None, applicability="APPLICABLE", availability="AVAILABLE", entry=None, native=None, direction=None):
    forward = None if reference is None or entry is None else (Decimal(reference["price"]) > entry if direction=="LONG" else Decimal(reference["price"]) < entry)
    inside = forward and (Decimal(reference["price"]) < native if direction=="LONG" else Decimal(reference["price"]) > native)
    included = bool(inside) and group != "SETUP_NATIVE_TARGET"
    reason = ("SETUP_NATIVE_TARGET" if group=="SETUP_NATIVE_TARGET" else "NEAREST_FORWARD_RESOLVER_INPUT" if included
              else "NON_FORWARD" if forward is False else "NOT_BETWEEN_ENTRY_AND_NATIVE_TARGET" if forward
              else "EXISTING_GOVERNED_AUTHORITY_NOT_ESTABLISHED" if applicability=="NOT_APPLICABLE" else "SOURCE_UNAVAILABLE")
    return dict(source_class=group,applicability=applicability,availability=availability,role=role,
                reference=reference,forward=forward,included=included,reason=reason)


def target_manifest(facts, *, cycle, direction, source_id, additional_levels=()):
    candles = {c.candle_identity:c for c in facts.current_fifteen_minute}
    q, impulse = candles[cycle.qualification_identity], candles[cycle.impulse.candle_identity]
    long = direction == "LONG"
    entry, native = (q.high,impulse.high) if long else (q.low,impulse.low)
    ref = candle_reference(impulse,"HIGH" if long else "LOW",cycle.identity,source_id)
    rows = [_row(CLASSES[0],ref,role="PRIOR_IMPULSE_HIGH" if long else "PRIOR_IMPULSE_LOW",entry=entry,native=native,direction=direction)]
    previous = facts.previous_session_facts
    daily = facts.previous_daily
    valid_prior = (len(daily)==1 and daily[0].market_session_identity==facts.previous_schedule.session_id
        and previous.previous_daily_candle_identity==daily[0].candle_identity
        and previous.target_session_identity==facts.current_schedule.session_id
        and previous.previous_session_identity==facts.previous_schedule.session_id)
    if valid_prior:
        day = daily[0]
        valid_prior = (day.high,day.low,day.close)==(previous.high,previous.low,previous.close)
    if not valid_prior:
        rows += [_row(g,availability="UNAVAILABLE") for g in CLASSES[1:3]]
    else:
        for name,field in (("PDH","HIGH"),("PDL","LOW")):
            ref = candle_reference(day,field,cycle.identity,source_id)
            ref["kind"] = ReferenceKind.PRIOR.value
            rows.append(_row(CLASSES[1],ref,role=name,entry=entry,native=native,direction=direction))
        h,l,c = day.high,day.low,day.close
        p,span = (h+l+c)/Decimal(3),h-l
        levels = {"R1":2*p-l,"R2":p+span,"R3":p+2*span,"R4":p+3*span,
                  "S1":2*p-h,"S2":p-span,"S3":p-2*span,"S4":p-3*span}
        for name,price in levels.items():
            ref = dict(kind=ReferenceKind.PIVOT.value,source_identity=source_id,
                source_evidence_identity=previous.facts_identity,source_integrity=previous.integrity_identity,
                candle_identity=None,field=name,price=str(price),structure_identity=cycle.identity,timeframe="1D",
                origin_session=day.market_session_identity,origin_date=day.candle_start.date().isoformat())
            rows.append(_row(CLASSES[2],ref,role="PIVOT_RESISTANCE" if name.startswith("R") else "PIVOT_SUPPORT",entry=entry,native=native,direction=direction))
    # No new session-extreme or barrier selector is commissioned here. Optional
    # exact owner facts must be supplied as a complete class, never target-picked.
    for group,kind in ((CLASSES[3],ReferenceKind.SESSION),(CLASSES[4],ReferenceKind.BARRIER)):
        members=[x for x in additional_levels if x["source_class"]==group]
        if not members:
            rows.append(_row(group,applicability="NOT_APPLICABLE",availability="NOT_ESTABLISHED"))
        else:
            for member in members:
                ref=member["reference"]
                if ref["kind"] != kind.value or not member.get("class_complete"):
                    rows.append(_row(group,availability="UNAVAILABLE"))
                else:
                    rows.append(_row(group,ref,role=member["role"],entry=entry,native=native,direction=direction))
    completeness = ("INCOMPLETE" if any(x["applicability"]=="APPLICABLE" and x["availability"]!="AVAILABLE" for x in rows)
                    else "COMPLETE_WITH_TARGETS" if any(x["included"] for x in rows)
                    else "COMPLETE_NO_APPLICABLE_FORWARD_CONSTRAINTS")
    core=dict(rows=rows,completeness=completeness,policy=APPROVED_POLICY)
    return dict(**normalize(core),identity=MANIFEST_PREFIX+digest(core))


def build_decision(source, *, created_at):
    from kronos.intraday.native_structural_selection import create_native_selection
    f,m,r,binding = decode_source(source)
    direction=r.direction.value if r.direction is not None else "UNAVAILABLE"
    cycle,reasons=((None,(source["failure"],)) if f is None else
        select_cycle(f.current_fifteen_minute,subject=r.canonical_subject_identity,
        direction=direction,session=f.current_schedule.session_id,boundary=r.analysis_boundary))
    sid=SOURCE_PREFIX+digest(source)
    roles={}
    manifest=None
    if cycle:
        cs={c.candle_identity:c for c in f.current_fifteen_minute}
        long=direction=="LONG"
        assignments={"ORIGIN_LOW" if long else "ORIGIN_HIGH":(cycle.origin.candle_identity,"LOW" if long else "HIGH"),
            "PRIOR_IMPULSE_HIGH" if long else "PRIOR_IMPULSE_LOW":(cycle.impulse.candle_identity,"HIGH" if long else "LOW"),
            "PULLBACK_STRUCTURAL_LOW" if long else "PULLBACK_STRUCTURAL_HIGH":(cycle.pullback.candle_identity,"LOW" if long else "HIGH"),
            "QUALIFICATION_CANDLE_HIGH":(cycle.qualification_identity,"HIGH"),
            "QUALIFICATION_CANDLE_LOW":(cycle.qualification_identity,"LOW")}
        roles={k:candle_reference(cs[c],field,cycle.identity,sid) for k,(c,field) in assignments.items()}
        manifest=target_manifest(f,cycle=cycle,direction=direction,source_id=sid)
        if manifest["completeness"]=="INCOMPLETE":reasons=(Reason.TARGETS.value,)
    values=dict(programme_identity=PROGRAMME,contract_version=CONTRACT,policy_identity=POLICY_ID,
        policy_version=VERSION,policy_checksum=CHECKSUM,subject=r.canonical_subject_identity,direction=direction,
        result="PULLBACK" if cycle and not reasons else "NOT_ESTABLISHED",reasons=list(reasons),
        setup_family="PULLBACK" if cycle else None,setup_identity=None if cycle is None else cycle.identity,
        cycle=None if cycle is None else normalize(cycle),roles=roles,analysis_cycle=source["run_identity"],
        analysis_boundary=normalize(r.analysis_boundary),session=r.market_session_identity,
        trading_date=r.analysis_boundary.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata")).date().isoformat(),machine_identity=r.semantic_evidence_identity,
        machine_integrity=m.semantic_evidence.integrity_identity,instrument_identity=r.canonical_subject_identity if binding is None else binding.active_binding.derivative_contract_id,
        exact_contract=None if binding is None else binding.active_binding.derivative_contract_id,
        roll_lineage=None if binding is None else binding.binding_identity,created_at=normalize(created_at),
        native_source_identity=sid,source_integrity=digest(source),probable_result_identity=r.result_identity,
        completed_evidence_identity=r.completed_evidence_selection_identity,target_manifest=manifest,
        target_population_identity=None if manifest is None else manifest["identity"],
        target_completeness="INCOMPLETE" if manifest is None else manifest["completeness"])
    return create_native_selection(**values)


def validate_decision(d):
    required={"programme_identity","contract_version","policy_identity","policy_version","policy_checksum","subject","direction","result","reasons",
        "setup_family","setup_identity","cycle","roles","analysis_cycle","analysis_boundary","session","trading_date","machine_identity","machine_integrity",
        "instrument_identity","exact_contract","roll_lineage","created_at","native_source_identity","source_integrity","probable_result_identity",
        "completed_evidence_identity","target_manifest","target_population_identity","target_completeness"}
    if set(d)!=required or d["contract_version"]!=CONTRACT or tuple(d[k] for k in ("policy_identity","policy_version","policy_checksum"))!=APPROVED_POLICY:
        raise ValueError("STRUCTURAL_CONTRACT_AUTHORITY_INVALID")
    if (d["programme_identity"]!=PROGRAMME or d["result"] not in {"PULLBACK","NOT_ESTABLISHED"}
            or d["direction"] not in {"LONG","SHORT","NON_DIRECTIONAL","UNAVAILABLE"} or d["setup_family"] not in {None,"PULLBACK"}
            or type(d["reasons"]) is not list or any(x not in set(Reason) for x in d["reasons"])
            or len(set(d["reasons"]))!=len(d["reasons"])
            or (d["result"]=="NOT_ESTABLISHED")!=bool(d["reasons"])):
        raise ValueError("STRUCTURAL_CONTRACT_AUTHORITY_INVALID")
    for k in ("subject","analysis_cycle","session","machine_identity","machine_integrity","instrument_identity","native_source_identity","source_integrity","probable_result_identity","completed_evidence_identity"):
        if type(d[k]) is not str or not d[k]:raise ValueError("STRUCTURAL_CONTRACT_VALUE_INVALID:"+k)
    if moment(d["created_at"])<moment(d["analysis_boundary"]):raise ValueError("STRUCTURAL_CREATED_BEFORE_BOUNDARY")
    mcx=d["subject"].startswith("MCX-")
    if mcx and d["result"]=="PULLBACK" and (not d["exact_contract"] or not d["roll_lineage"]):raise ValueError(Reason.MCX.value)
    if not mcx and (d["exact_contract"] is not None or d["roll_lineage"] is not None):raise ValueError(Reason.MCX.value)
    from zoneinfo import ZoneInfo
    if d["trading_date"] != moment(d["analysis_boundary"]).astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat():raise ValueError(Reason.SESSION.value)
    if d["instrument_identity"] != (d["exact_contract"] if mcx and d["exact_contract"] else d["subject"]):raise ValueError(Reason.INTEGRITY.value)
    if not re.fullmatch(r"[a-f0-9]{64}",d["source_integrity"]):raise ValueError(Reason.INTEGRITY.value)
    if d["native_source_identity"] != SOURCE_PREFIX+d["source_integrity"]:raise ValueError(Reason.INTEGRITY.value)
    if d["cycle"] is None:
        if d["roles"] or d["setup_identity"] is not None or d["setup_family"] is not None or d["target_manifest"] is not None or d["target_population_identity"] is not None or d["target_completeness"]!="INCOMPLETE":raise ValueError(Reason.INTEGRITY.value)
    else:
        long=d["direction"]=="LONG"
        required_roles={"QUALIFICATION_CANDLE_HIGH","QUALIFICATION_CANDLE_LOW", "ORIGIN_LOW" if long else "ORIGIN_HIGH",
            "PRIOR_IMPULSE_HIGH" if long else "PRIOR_IMPULSE_LOW", "PULLBACK_STRUCTURAL_LOW" if long else "PULLBACK_STRUCTURAL_HIGH"}
        if set(d["roles"])!=required_roles or d["cycle"]["identity"]!=d["setup_identity"] or d["setup_family"]!="PULLBACK":raise ValueError("STRUCTURAL_REQUIRED_ROLE_SET_INVALID")
    if d["result"]=="PULLBACK" and (d["direction"] not in {"LONG","SHORT"} or not d["cycle"] or not d["roles"] or d["target_completeness"]=="INCOMPLETE"):
        raise ValueError("STRUCTURAL_REQUIRED_ROLE_SET_INVALID")
    manifest=d["target_manifest"]
    if manifest is not None:
        if set(manifest)!={"rows","completeness","policy","identity"} or manifest["identity"]!=MANIFEST_PREFIX+digest({k:v for k,v in manifest.items() if k!="identity"}):raise ValueError(Reason.INTEGRITY.value)
        if manifest["identity"]!=d["target_population_identity"] or manifest["completeness"]!=d["target_completeness"]:raise ValueError(Reason.TARGETS.value)
        if {x["source_class"] for x in manifest["rows"]}!=set(CLASSES) or manifest["policy"]!=list(APPROVED_POLICY):raise ValueError(Reason.TARGETS.value)
        if manifest["completeness"] not in {"COMPLETE_WITH_TARGETS","COMPLETE_NO_APPLICABLE_FORWARD_CONSTRAINTS","INCOMPLETE"}:raise ValueError(Reason.TARGETS.value)
        for row in manifest["rows"]:
            if set(row)!={"source_class","applicability","availability","role","reference","forward","included","reason"}:raise ValueError(Reason.TARGETS.value)
            if row["applicability"] not in {"APPLICABLE","NOT_APPLICABLE"} or row["availability"] not in {"AVAILABLE","UNAVAILABLE","NOT_ESTABLISHED"} or type(row["included"]) is not bool:raise ValueError(Reason.TARGETS.value)


def load_decision_source(store, decision, handoff):
    """Validate exact references. Never search for or reselect a cycle in WO-10."""
    d=decision.data
    p=store.root/"sources"/(d["native_source_identity"]+".json")
    if not re.fullmatch(SOURCE_PREFIX+r"[a-f0-9]{64}",d["native_source_identity"]):raise ValueError(Reason.INTEGRITY.value)
    source=json.loads(p.read_bytes())
    if digest(source)!=d["source_integrity"] or SOURCE_PREFIX+digest(source)!=d["native_source_identity"]:raise ValueError(Reason.INTEGRITY.value)
    f,m,r,binding=decode_source(source)
    expected=dict(subject=r.canonical_subject_identity,direction=r.direction.value if r.direction is not None else "UNAVAILABLE",analysis_cycle=source["run_identity"],
        analysis_boundary=normalize(r.analysis_boundary),session=r.market_session_identity,machine_identity=r.semantic_evidence_identity,
        machine_integrity=m.semantic_evidence.integrity_identity,probable_result_identity=r.result_identity,completed_evidence_identity=r.completed_evidence_selection_identity)
    if any(d[k]!=v for k,v in expected.items()):raise ValueError(Reason.BOUNDARY.value)
    if binding and (d["exact_contract"]!=binding.active_binding.derivative_contract_id or d["roll_lineage"]!=binding.binding_identity):raise ValueError(Reason.MCX.value)
    if f is None:
        if d["result"]!="NOT_ESTABLISHED" or d["reasons"]!=[source["failure"]]:raise ValueError(Reason.INTEGRITY.value)
        return source
    cs={c.candle_identity:c for c in (*f.current_fifteen_minute,*f.previous_daily)}
    for ref in d["roles"].values():
        candle=cs.get(ref["candle_identity"])
        if candle is None or ref!=candle_reference(candle,ref["field"],d["setup_identity"],d["native_source_identity"]):raise ValueError(Reason.INTEGRITY.value)
    if d["target_manifest"] is not None:
        # Only arithmetic/source evaluation is repeated; no candle-role selection.
        from kronos.intraday.native_pullback_policy import Cycle, Pivot
        raw=d["cycle"]
        pivots={k:Pivot(**{**raw[k],"price":Decimal(raw[k]["price"]),"confirmation_end":moment(raw[k]["confirmation_end"])}) for k in ("origin","impulse","pullback")}
        cycle=Cycle(**{**raw,**pivots,"qualification_end":moment(raw["qualification_end"])})
        validate_selected_cycle(f,cycle,d)
        if target_manifest(f,cycle=cycle,direction=d["direction"],source_id=d["native_source_identity"])!=d["target_manifest"]:raise ValueError(Reason.TARGETS.value)
    return source


def retain_decision(store, source, *, created_at):
    from kronos.intraday.wo09_persistence import Wo09Store
    selection = build_decision(source, created_at=created_at)
    Wo09Store._retain(store.root / "sources" / (selection.data["native_source_identity"] + ".json"), encoded(source))
    store.retain(selection, approved_policies={APPROVED_POLICY}, cycle_identity=source["run_identity"])
    return selection


def validate_selected_cycle(facts, cycle, d):
    """Check the retained exact cycle only; no alternative-cycle selection at intake."""
    from kronos.intraday.native_pullback_policy import confirmed_pivots
    cs=facts.current_fifteen_minute
    indices=(cycle.origin.index,cycle.impulse.index,cycle.pullback.index)
    if not 0<indices[0]<indices[1]<indices[2]<cycle.qualification_index-1<len(cs)-1:
        raise ValueError(Reason.INTEGRITY.value)
    long=d["direction"]=="LONG"
    for p,kind in zip((cycle.origin,cycle.impulse,cycle.pullback),('LOW','HIGH','LOW') if long else ('HIGH','LOW','HIGH')):
        # Only inspect this pivot's immediate neighbours, not the source population.
        local=confirmed_pivots(cs[p.index-1:p.index+2])
        candidates=[x for x in local if x.kind==kind]
        if len(candidates)!=1:
            raise ValueError(Reason.INTEGRITY.value)
        from dataclasses import replace
        if replace(candidates[0],index=p.index)!=p:raise ValueError(Reason.INTEGRITY.value)
    q=cs[cycle.qualification_index]
    expected_cycle="NATIVE-STRUCTURAL-CYCLE-"+digest(dict(subject=d["subject"],direction=d["direction"],session=d["session"],
        origin=cycle.origin.identity,impulse=cycle.impulse.identity,pullback=cycle.pullback.identity,qualification=q.candle_identity,
        analysis_boundary=moment(d["analysis_boundary"]),policy_identity=POLICY_ID,policy_version=VERSION))
    if cycle.identity!=expected_cycle or cycle.qualification_identity!=q.candle_identity or cycle.qualification_end!=q.candle_end:raise ValueError(Reason.INTEGRITY.value)
    if not (cycle.impulse.price>cycle.origin.price and cycle.pullback.price>cycle.origin.price if long else cycle.impulse.price<cycle.origin.price and cycle.pullback.price<cycle.origin.price):raise ValueError(Reason.INVALIDATED.value)
    for index in range(cycle.origin.index+1,cycle.qualification_index+1):
        c=cs[index]
        if (c.low<=cycle.origin.price if long else c.high>=cycle.origin.price):raise ValueError(Reason.INVALIDATED.value)
        if index>cycle.pullback.index+1:
            qualifies=c.close>cs[index-1].high if long else c.close<cs[index-1].low
            if qualifies!=(index==cycle.qualification_index):raise ValueError(Reason.RESUMPTION.value)
    assigned={"ORIGIN_LOW" if long else "ORIGIN_HIGH":cycle.origin.candle_identity,
        "PRIOR_IMPULSE_HIGH" if long else "PRIOR_IMPULSE_LOW":cycle.impulse.candle_identity,
        "PULLBACK_STRUCTURAL_LOW" if long else "PULLBACK_STRUCTURAL_HIGH":cycle.pullback.candle_identity,
        "QUALIFICATION_CANDLE_HIGH":q.candle_identity,"QUALIFICATION_CANDLE_LOW":q.candle_identity}
    if any(ref["candle_identity"]!=assigned[role] or ref["field"]!=role.rsplit('_',1)[-1] for role,ref in d["roles"].items()):raise ValueError(Reason.INTEGRITY.value)


def unavailable_source(mapping,result,run_identity,reason):
    from kronos.intraday.probables_v2_persistence import _to_wire
    from kronos.intraday.probables_v2 import DiscoveryProbablesEvidenceV2,ProbableMemberResultV2
    if type(mapping) is not DiscoveryProbablesEvidenceV2 or type(result) is not ProbableMemberResultV2 or reason not in set(Reason):raise ValueError(Reason.INTEGRITY.value)
    mapping.__post_init__();result.__post_init__()
    if mapping.mapping_identity!=result.source_mapping_identity or mapping.semantic_evidence.evidence_identity!=result.semantic_evidence_identity:raise ValueError(Reason.BOUNDARY.value)
    return dict(mapping=_to_wire(mapping),result=_to_wire(result),run_identity=run_identity,failure=reason)
