"""WO-09B successor engine qualification; no runtime or production evidence."""

from __future__ import annotations

from copy import deepcopy
from itertools import product
from datetime import UTC, datetime
from hashlib import sha256

import pytest

from kronos.swing.v1.analytical_promotion import Kr370CriterionIdentity, Kr370CriterionResult
from kronos.swing.v1.analytical_promotion_v2 import (
    CONTRACT, SCHEMA, SCHEMA_SEAL, SCHEMA_SEAL_SHA256, V2PromotionRecord,
    LocalV2PromotionStore, _validate_confirmation, _validate_mcx,
    _state, create_record,
)
from kronos.swing.v1.models import V1Direction
from kronos.validation.kr370 import Kr370CriterionState
from kronos.swing.v1.review_evidence_binding import canonical
from tests.unit.swing.v1.test_analytical_promotion import _scenario

NOW = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)
D = "a" * 64
E = "b" * 64
F = "c" * 64


def source(*, direction="LONG", market="NSE", asset_class=None, instrument=None):
    requirement, facts, *_ = _scenario(direction=V1Direction(direction))
    if asset_class is None: asset_class = "NSE_EQUITY" if market == "NSE" else "MCX_COMMODITY"
    if instrument is None: instrument = requirement.canonical_instrument if market == "NSE" else "GOLDM"
    roles = ["NATIVE_NSE"] if market == "NSE" else ["NATIVE_MCX", "SUPPORTING_REFERENCE"]
    request_bindings = [dict(role=role, request_identity=f"request-{role}", request_sha256=D,
        review_pack_identity="pack", review_pack_sha256=D) for role in roles]
    contracts = [dict(role=role,
        question_contract_identity=("SWING-V1-VISUAL-QUESTION-SET-V3" if role=="NATIVE_NSE" else
            "KRONOS-SWING-MCX-NATIVE-VISUAL-QUESTIONS-V2" if role=="NATIVE_MCX" else
            "KRONOS-SWING-MCX-REFERENCE-VISUAL-QUESTIONS-V2"),
        question_contract_version="3.2" if role=="NATIVE_NSE" else "2.0",
        answer_contract_identity=("KRONOS-SWING-NSE-REVIEW-ANSWER-V2" if role=="NATIVE_NSE" else
            "KRONOS-SWING-MCX-NATIVE-VISUAL-ANSWER-V2" if role=="NATIVE_MCX" else
            "KRONOS-SWING-MCX-REFERENCE-VISUAL-ANSWER-V2"),
        answer_contract_version="2.0",
        structured_evidence_schema=("KRONOS-SWING-V1-VISUAL-EVIDENCE-V3.2" if role=="NATIVE_NSE" else
            "KRONOS-SWING-MCX-NATIVE-VISUAL-EVIDENCE-V2" if role=="NATIVE_MCX" else
            "KRONOS-SWING-MCX-REFERENCE-VISUAL-EVIDENCE-V2"),
        structured_evidence_version="3.2" if role=="NATIVE_NSE" else "2.0") for role in roles]
    visuals = [dict(role=role, timeframe=tf, subject_identity="subject",
        reference_market="COMEX" if role == "SUPPORTING_REFERENCE" else None,
        reference_symbol="COMEX:GC1!" if role == "SUPPORTING_REFERENCE" else None,
        chart_revision_identity="revision", chart_sha256=D,
        structured_evidence_schema=next(c["structured_evidence_schema"] for c in contracts if c["role"]==role),
        structured_evidence_version=next(c["structured_evidence_version"] for c in contracts if c["role"]==role),
        structured_evidence_sha256=E, evidence_integrity_sha256=F)
        for role in roles for tf in (["1W", "1D", "4H", "1H"] if market == "NSE" else
                                    ["1D", "4H", "1H"])]
    acceptance = dict(commit_identity="commit", receipt_identity="receipt",
        receipt_schema="KRONOS-SWING-REVIEW-EVIDENCE-RECEIPT-V2", receipt_version="2.0", receipt_integrity_sha256=D,
        request_publication_identity="publication", review_cycle_identity="cycle",
        review_pack_identity="pack", review_pack_sha256=D,
        request_bindings=request_bindings, answer_identity="answer", answer_pdf_sha256=E,
        visual_contracts=contracts, visual_bindings=visuals)
    s = dict(native_run_identity=requirement.native_run_identity,
        committed_run_manifest_identity=D, market=market, asset_class=asset_class,
        canonical_instrument=instrument, direction=direction,
        native_opportunity_identity=requirement.thesis.opportunity_identity.value,
        native_assessment_sha256=D, native_requirement_sha256=E,
        analysis_boundary="2026-09-21T09:00:00.000000Z",
        observation_boundaries=[dict(timeframe=tf, boundary="2026-09-21T08:00:00.000000Z")
            for tf in ("1W", "1D", "4H", "1H")],
        machine_snapshot_identity=facts.provider_source_identity,
        machine_fact_bindings=[dict(timeframe=tf, integrity_sha256=F)
            for tf in ("1W", "1D", "4H", "1H")],
        e01_fact_integrity_sha256=D, e03_fact_integrity_sha256=E, acceptance=acceptance)
    return s


REASONS = (
    "NATIVE_1H_DIRECTIONALLY_PROGRESSING", "COMPLETED_1H_CLOSE_ACCEPTED_BEYOND_CPR",
    "E01_PATH_CLEAR", "CLEAN_DIRECTIONAL", "E03_NOT_MATERIALLY_EXTENDED")
UNSAT = (
    "NATIVE_1H_STALLING", "COMPLETED_1H_CLOSE_NOT_ACCEPTED_BEYOND_CPR",
    "E01_IMMEDIATE_PATH_BLOCKED", "MESSY_CHOPPY", "E03_MATERIALLY_EXTENDED")


def criteria(n=5, *, unavailable=None):
    return tuple(Kr370CriterionResult(identity,
        Kr370CriterionState.UNAVAILABLE if i == unavailable else
        Kr370CriterionState.SATISFIED if i < n else Kr370CriterionState.UNSATISFIED,
        ("GOVERNED_1H_CPR_UNAVAILABLE" if i == 1 else "NATIVE_1H_PROGRESSION_UNAVAILABLE")
        if i == unavailable else REASONS[i] if i < n else UNSAT[i], (D,))
        for i, identity in enumerate(Kr370CriterionIdentity))


def nse(*, direction="LONG", states=("OUTPERFORMING", "OUTPERFORMING"),
        validity="VALID", run=None, instrument=None):
    if validity != "VALID":
        binding = dict(validation_state=validity, observed_payload_sha256=None, payload=None)
        reason = {"MISSING":"NSE_CONTEXT_MISSING", "INVALID":"NSE_CONTEXT_INVALID",
                  "STALE":"NSE_CONTEXT_STALE", "MISMATCHED":"NSE_CONTEXT_BINDING_MISMATCH"}[validity]
        return dict(kind="NSE_NIFTY", state="WITHHELD", reason_codes=[reason],
                    nse_binding=binding, mcx_binding=None)
    horizons = []
    for tf, state in zip(("1D", "4H"), states, strict=True):
        supportive = state == ("OUTPERFORMING" if direction == "LONG" else "UNDERPERFORMING")
        context = ("SUPPORTIVE_CONTEXT" if supportive else "NEUTRAL_CONTEXT" if state == "EQUAL"
                   else "UNAVAILABLE" if state == "UNAVAILABLE" else "CONTRADICTORY_CONTEXT")
        available = state != "UNAVAILABLE"
        horizons.append(dict(timeframe=tf,
            common_start_boundary="2026-09-20T09:00:00.000000Z" if available else None,
            latest_common_completed_boundary="2026-09-21T09:00:00.000000Z" if available else None,
            stock_source_identity="stock" if available else None,
            benchmark_source_identity="nifty" if available else None,
            stock_provenance=["stock"] if available else [],
            benchmark_provenance=["nifty"] if available else [], relative_state=state,
            directional_context=context, reason_codes=[] if available else ["INSUFFICIENT_HISTORY"]))
    s=source(direction=direction)
    p=dict(schema="KRONOS-SWING-V1-NIFTY-RELATIVE-CONTEXT-V1",
           policy_identity="SWING-PHASE1-V1-RELATIVE-CONTEXT-POLICY",policy_version="1",
           context_run_integrity_sha256=D,context_record_integrity_sha256=E,
           run_identity=run or s["native_run_identity"],canonical_instrument=instrument or s["canonical_instrument"],
           benchmark_identity="NIFTY",horizons=horizons)
    binding=dict(validation_state="VALID",observed_payload_sha256=E,payload=p)
    conf=dict(kind="NSE_NIFTY",state="WITHHELD",reason_codes=[],nse_binding=binding,mcx_binding=None)
    state_and_reasons = __import__("kronos.swing.v1.analytical_promotion_v2",fromlist=["_validate_nse"])._validate_nse(binding,s)
    conf["state"],conf["reason_codes"] = state_and_reasons
    return conf


def index():
    return dict(kind="ASSET_CLASS_EXEMPT",state="NOT_REQUIRED_BY_ASSET_CLASS",
                reason_codes=["NOT_REQUIRED_BY_ASSET_CLASS"],nse_binding=None,mcx_binding=None)


def mcx(*, m1="MATCHED",coverage="SUFFICIENT",m2=("AGREES","AGREES","AGREES"),
        m3="SUPPORTS",limits=(),status=("OBSERVED",)*3):
    p=dict(registered_mapping=dict(native_family="GOLDM",reference_name="COMEX Gold",
           reference_market="COMEX",reference_symbol="COMEX:GC1!"),native_candidate_reference=E,
           pair_binding_sha256=D,native_request_identity="request-NATIVE_MCX",native_request_sha256=D,
           reference_request_identity="request-SUPPORTING_REFERENCE",reference_request_sha256=D,
           comparison_schema="KRONOS-SWING-MCX-PAIR-COMPARISON-EVIDENCE-V1",
           comparison_version="1.0",comparison_artifact_sha256=D,comparison_integrity_sha256=F,
           m1=dict(question_id="M1_COMPARISON_VALIDITY",observation_status=status[0],
                   mapping_state=m1,coverage_state=coverage),
           m2=dict(question_id="M2_STRUCTURAL_AGREEMENT",observation_status=status[1],
                   by_timeframe=[dict(timeframe=tf,relationship=r) for tf,r in zip(("1D","4H","1H"),m2,strict=True)]),
           m3=dict(question_id="M3_DIVERGENCE_LIMITATIONS",observation_status=status[2],
                   relationship_to_native_direction=m3,affected_timeframes=[],limitations=list(limits)))
    binding=dict(validation_state="VALID",observed_payload_sha256=D,payload=p)
    st,reasons=_validate_mcx(binding,source(market="MCX"))
    return dict(kind="MCX_GLOBAL_REFERENCE",state=st,reason_codes=reasons,
                nse_binding=None,mcx_binding=binding)


@pytest.mark.parametrize("direction",("LONG","SHORT"))
@pytest.mark.parametrize("n,expected",[(0,"NO_FOCUS"),(1,"NO_FOCUS"),(2,"NO_FOCUS"),
    (3,"NEAR_READY"),(4,"BUY_READY"),(5,"BUY_NOW")])
def test_unweighted_state_table(direction,n,expected):
    c=nse(direction=direction,states=("OUTPERFORMING","OUTPERFORMING") if direction=="LONG" else
          ("UNDERPERFORMING","UNDERPERFORMING"))
    expected = expected.replace("BUY_","SELL_") if direction=="SHORT" else expected
    assert _state(direction,n,c["state"]) == expected
    if n < 4:
        # Frozen K4 makes these pure count-map cases unreachable as an
        # EVALUATED real record: MESSY_CHOPPY is itself a hard gate.
        record=create_record(source=source(direction=direction),criteria=criteria(n),
                             confirmation=c,created_at=NOW)
        assert record.value["evaluation_disposition"] == "HARD_GATED"
        assert record.value["promotion_state"] is None
        return
    record=create_record(source=source(direction=direction),criteria=criteria(n),confirmation=c,created_at=NOW)
    v=record.value
    assert v["promotion_state"] == expected
    assert v["satisfied_count"]==n and v["missing_count"]==5-n
    assert v["confirmation_pending"] is False


@pytest.mark.parametrize("direction,states,expected",[
    ("LONG",("OUTPERFORMING","OUTPERFORMING"),"BUY_NOW"),
    ("SHORT",("UNDERPERFORMING","UNDERPERFORMING"),"SELL_NOW"),
    ("LONG",("EQUAL","OUTPERFORMING"),"BUY_READY"),
    ("LONG",("UNDERPERFORMING","OUTPERFORMING"),"BUY_READY"),
    ("SHORT",("OUTPERFORMING","UNDERPERFORMING"),"SELL_READY"),
    ("LONG",("OUTPERFORMING","UNAVAILABLE"),"BUY_READY"),
])
def test_nse_confirmation(direction,states,expected):
    record=create_record(source=source(direction=direction),criteria=criteria(),
        confirmation=nse(direction=direction,states=states),created_at=NOW)
    assert record.value["promotion_state"]==expected
    assert record.value["confirmation_pending"] == expected.endswith("READY")
    assert record.value["missing_count"]==0


@pytest.mark.parametrize("validity",["MISSING","INVALID","STALE","MISMATCHED"])
def test_nse_unavailable_is_not_missing_criterion(validity):
    record=create_record(source=source(),criteria=criteria(),confirmation=nse(validity=validity),created_at=NOW)
    assert (record.value["promotion_state"],record.value["missing_count"],
            record.value["confirmation_pending"])==("BUY_READY",0,True)


def test_index_exemption_does_not_claim_support():
    s=source(asset_class="NSE_INDEX",instrument="NIFTY")
    record=create_record(source=s,criteria=criteria(),confirmation=index(),created_at=NOW)
    assert record.value["promotion_state"]=="BUY_NOW"
    assert record.value["confirmation"]["state"]=="NOT_REQUIRED_BY_ASSET_CLASS"
    assert record.value["confirmation_pending"] is False


@pytest.mark.parametrize("changes",[
    {},{"m1":"UNDETERMINED"},{"coverage":"PARTIAL"},
    {"m2":("PARTLY_AGREES","AGREES","AGREES")},
    {"m2":("AGREES","PARTLY_AGREES","AGREES")},
    {"m2":("AGREES","AGREES","PARTLY_AGREES")},
    {"m2":("AGREES","AGREES","CONFLICTS")},
    {"m2":("AGREES","AGREES","NOT_COMPARABLE")},
    {"m3":"NO_MATERIAL_DIVERGENCE"},{"m3":"CHALLENGES"},
    {"m3":"MIXED"},{"m3":"NOT_ESTABLISHED"},
    {"limits":("DIFFERENT_SESSIONS",)},
    {"limits":("CURRENCY_OR_BASIS_DIFFERENCE",)},
    *({"limits":(x,)} for x in ("INCOMPLETE_BAR","EXPIRY_OR_ROLL",
       "CONTINUOUS_BACK_ADJUSTMENT_UNKNOWN","CONTRACT_IDENTITY_UNCLEAR",
       "MISSING_EVIDENCE","OTHER_VISIBLE_LIMITATION")),
    {"status":("OBSERVED","UNAVAILABLE","OBSERVED")},
])
def test_mcx_exact_confirmation_truth_table(changes):
    conf=mcx(**changes)
    record=create_record(source=source(market="MCX"),criteria=criteria(),
                         confirmation=conf,created_at=NOW)
    positive=(not changes or changes=={"m2":("AGREES","AGREES","PARTLY_AGREES")} or
              changes=={"m3":"NO_MATERIAL_DIVERGENCE"} or
              changes.get("limits") in {("DIFFERENT_SESSIONS",),("CURRENCY_OR_BASIS_DIFFERENCE",)})
    assert record.value["promotion_state"] == ("BUY_NOW" if positive else "BUY_READY")
    assert record.value["confirmation_pending"] is (not positive)


@pytest.mark.parametrize("hard,unavailable,disposition",[
    (None,0,"NOT_EVALUABLE"),("NATIVE_THESIS_INVALIDATED_OR_STRUCTURAL_FAILURE",None,"HARD_GATED"),
    ("NSE_WEEKLY_OPPOSING",0,"HARD_GATED")])
def test_closed_disposition_has_no_promotion(hard,unavailable,disposition):
    r=create_record(source=source(),criteria=criteria(unavailable=unavailable),
                    confirmation=nse(),created_at=NOW,hard_gate_reason=hard)
    v=r.value
    assert v["evaluation_disposition"]==disposition
    assert v["promotion_state"] is None and v["satisfied_count"] is None
    assert v["missing_count"] is None and v["reason_codes"]


def test_digest_schema_corruption_and_immutable_exact_input(tmp_path):
    s=source()
    r=create_record(source=s,criteria=criteria(),confirmation=nse(),created_at=NOW)
    assert r.value["schema"]==SCHEMA and r.identity.startswith(CONTRACT+":2:")
    assert SCHEMA_SEAL_SHA256==sha256(canonical(SCHEMA_SEAL)).hexdigest()
    store=LocalV2PromotionStore(tmp_path/"v2")
    path=store.retain(r,current=lambda captured: captured==s)
    assert path==tmp_path/"v2"/s["native_run_identity"]/(r.value["input_sha256"]+".json")
    assert store.retain(r,current=lambda captured: captured==s)==path
    assert store.load_exact(s,r.value["input_sha256"],current=lambda captured: captured==s)==r
    assert sorted(x.name for x in path.parent.iterdir())==[path.name]
    with pytest.raises(ValueError,match="V2_SOURCE_STALE"):
        store.load_exact(s,r.value["input_sha256"],current=lambda captured: False)
    stale=[True,False]
    with pytest.raises(ValueError,match="V2_PUBLICATION_CHANGED"):
        store.load_exact(s,r.value["input_sha256"],current=lambda captured: stale.pop(0))
    bad=deepcopy(r.value);bad["promotion_state"]="BUY_READY"
    with pytest.raises(ValueError,match="V2_SCHEMA_INVALID"):
        V2PromotionRecord(canonical(bad))
    bad["integrity_sha256"]=sha256(canonical({k:v for k,v in bad.items()
                               if k not in {"record_identity","integrity_sha256"}})).hexdigest()
    bad["record_identity"]=f"{CONTRACT}:2:{bad['integrity_sha256']}"
    with pytest.raises(ValueError,match="V2_SCHEMA_INVALID"):
        V2PromotionRecord(canonical(bad))
    bad=deepcopy(r.value);bad["unknown"]=1
    with pytest.raises(ValueError,match="V2_SCHEMA_INVALID"):
        V2PromotionRecord(canonical(bad))
    with pytest.raises(ValueError,match="V2_SCHEMA_INVALID"):
        V2PromotionRecord(r.payload.replace(b'"schema":',b'"schema":"duplicate","schema":',1))


def test_v1_module_unmodified_by_v2_store(tmp_path):
    from kronos.swing.v1.analytical_promotion import KR370_PROMOTION_SCHEMA, LocalKr370AnalyticalPromotionStore
    assert KR370_PROMOTION_SCHEMA=="KRONOS-KR-370-ANALYTICAL-PROMOTION-RECORD-V1"
    r=create_record(source=source(),criteria=criteria(),confirmation=nse(),created_at=NOW)
    LocalV2PromotionStore(tmp_path/"v2").retain(r,current=lambda _:True)
    assert not (tmp_path/"v1").exists()
    assert LocalKr370AnalyticalPromotionStore(tmp_path/"v1").root==tmp_path/"v1"


from tests.unit.browser.test_swing_review_intake_binding import native_intake, _accepted_native


@pytest.mark.parametrize("native_intake",["NSE","GOLDM"],indirect=True)
def test_governed_inputs_bind_current_receipt_without_downstream_publication(native_intake,tmp_path):
    from kronos.swing.v1.analytical_promotion_v2 import evaluate_governed
    from tests.unit.swing.v1.test_analytical_promotion import _path, _extension
    workflow=native_intake
    market,instrument,publication,_,_,commit=_accepted_native(workflow,tmp_path)
    requirement=workflow._requirements(market,(instrument,))[0]
    _,facts,_=workflow._context()
    completed=workflow.live.cycle.completed_for(facts.run_identity,instrument) if market=="NSE" else None
    request=publication.mapping if market=="NSE" else None
    result=evaluate_governed(requirement=requirement,facts=facts,
        path_clearance=_path(facts,requirement,True),
        extension=_extension(facts,requirement,False),store=workflow.store,
        commit_identity=commit.identity,receipt_identity=commit.receipts[0].receipt_id,
        current_manifest=lambda:"a"*64,created_at=NOW,
        visual=completed.responses if completed is not None else None,nse_request=request)
    assert result.value["source"]["market"]==market
    assert result.value["source"]["acceptance"]["receipt_identity"]==commit.receipts[0].receipt_id
    assert result.value["authority_flags"]["execution"] is False


@pytest.mark.parametrize("relationships",list(product(
    ("AGREES","PARTLY_AGREES","CONFLICTS","NOT_COMPARABLE"),repeat=3)))
def test_all_mcx_horizon_relationship_combinations(relationships):
    conf=mcx(m2=relationships)
    assert (conf["state"]=="ESTABLISHED") is (
        relationships[0]=="AGREES" and relationships[1]=="AGREES" and
        relationships[2] in {"AGREES","PARTLY_AGREES"})


@pytest.mark.parametrize("criterion",range(5))
def test_each_unavailable_criterion_blocks_promotion(criterion):
    items=list(criteria())
    items[criterion]=Kr370CriterionResult(items[criterion].identity,
        Kr370CriterionState.UNAVAILABLE,
        ("GOVERNED_1H_CPR_UNAVAILABLE" if criterion==1 else
         "E01_UNAVAILABLE" if criterion==2 else
         "NATIVE_1H_SETUP_QUALITY_UNAVAILABLE" if criterion==3 else
         "E03_UNAVAILABLE" if criterion==4 else
         "NATIVE_1H_PROGRESSION_UNAVAILABLE"),(D,))
    record=create_record(source=source(),criteria=tuple(items),confirmation=nse(),created_at=NOW)
    assert record.value["evaluation_disposition"]=="NOT_EVALUABLE"
    assert record.value["promotion_state"] is None


@pytest.mark.parametrize("gate",[
    "NATIVE_THESIS_INVALIDATED_OR_STRUCTURAL_FAILURE","NSE_WEEKLY_OPPOSING",
    "NSE_WEEKLY_UNAVAILABLE_MANDATORY","NATIVE_MANDATORY_VISUAL_EVIDENCE_INVALID",
    "NATIVE_1H_MESSY_CHOPPY","AFFIRMATIVE_GOVERNED_DIRECTIONAL_CONFLICT"])
def test_each_hard_gate_blocks_even_five_satisfied(gate):
    record=create_record(source=source(),criteria=criteria(),confirmation=nse(),
                         created_at=NOW,hard_gate_reason=gate)
    assert record.value["evaluation_disposition"]=="HARD_GATED"
    assert record.value["reason_codes"]==[gate]
    assert record.value["promotion_state"] is None


def test_current_pointer_race_does_not_publish_stale_record(tmp_path):
    s=source(); r=create_record(source=s,criteria=criteria(),confirmation=nse(),created_at=NOW)
    calls=[True,False]
    with pytest.raises(ValueError,match="V2_PUBLICATION_CHANGED"):
        LocalV2PromotionStore(tmp_path/"v2").retain(r,current=lambda _:calls.pop(0))
    # The immutable output can remain as an orphan; it is never selected as
    # current without the governing owner's currentness proof.
    assert len(list((tmp_path/"v2").rglob("*.json")))==0


def test_recomputed_digest_cannot_erase_required_confirmation(tmp_path):
    s=source();r=create_record(source=s,criteria=criteria(),confirmation=nse(validity="MISSING"),created_at=NOW)
    bad=deepcopy(r.value)
    bad["confirmation_pending"]=False
    bad["integrity_sha256"]=sha256(canonical({k:v for k,v in bad.items()
                               if k not in {"record_identity","integrity_sha256"}})).hexdigest()
    bad["record_identity"]=f"{CONTRACT}:2:{bad['integrity_sha256']}"
    with pytest.raises(ValueError,match="V2_SCHEMA_INVALID"):
        V2PromotionRecord(canonical(bad))


def test_criterion_reason_cannot_disguise_intrinsic_hard_gate():
    items=list(criteria())
    items[0]=Kr370CriterionResult(items[0].identity,Kr370CriterionState.UNSATISFIED,
                                 "NATIVE_1H_STRUCTURAL_FAILURE",(D,))
    record=create_record(source=source(),criteria=tuple(items),confirmation=nse(),created_at=NOW)
    assert record.value["evaluation_disposition"] == "HARD_GATED"
    assert record.value["reason_codes"] == ["NATIVE_THESIS_INVALIDATED_OR_STRUCTURAL_FAILURE"]
    malformed=list(criteria())
    malformed[3]=Kr370CriterionResult(malformed[3].identity,Kr370CriterionState.SATISFIED,
                                      "MESSY_CHOPPY",(D,))
    with pytest.raises(ValueError,match="V2_SCHEMA_INVALID"):
        create_record(source=source(),criteria=tuple(malformed),confirmation=nse(),created_at=NOW)
