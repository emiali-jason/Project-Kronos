"""WO-06C: prospective missing provenance and isolated positive proof contracts."""
from dataclasses import asdict, replace
from datetime import timedelta, datetime, time
from decimal import Decimal
from functools import lru_cache
from hashlib import sha256

import pytest

from kronos.intraday.assessment_observation import (
    AdmissionPriceProof, AdmissionAssessment, ProbablesAssessmentObservations,
    AssessmentPriceAuthority as Authority, create_missing_assessment_observations,
    validate_assessment_run,
)
from kronos.intraday.probables_v2 import ProbablesV2Error, _identity, create_probables_v2_methodology
from kronos.intraday.probables_v2_persistence import (
    ProbablesV2Store, _artifact_bytes, _artifact_from_bytes,
    AssessmentBoundProbablesV2Pointer, create_current_probables_v2_pointer,
)
from tests.unit.intraday.test_opening_admission_correction import opening_mapping, run_mapping
from tests.unit.intraday.test_probables_v2 import _later_mapping, CURRENT_DAY, IST


@lru_cache
def fixture(direction="LONG", subject="NSE-EQ-RELIANCE", version="2.2.0"):
    methodology = create_probables_v2_methodology(version=version)
    mapping = opening_mapping(methodology, direction=direction, subject=subject)
    return run_mapping(mapping, methodology), mapping


def manifest(run, observations):
    base = create_missing_assessment_observations(run)
    core = asdict(base)
    core.pop("evidence_identity"); core.pop("integrity_identity")
    core["observations"] = observations
    return ProbablesAssessmentObservations(
        evidence_identity=_identity("INTRADAY-ASSESSMENT-OBSERVATIONS-", core),
        integrity_identity=_identity("INTEGRITY-INTRADAY-ASSESSMENT-OBSERVATIONS-", core), **core)


def proof_for(item, **changes):
    # Deliberate deterministic proof fixture, NOT a commissioned source adapter.
    core = dict(canonical_subject_identity=item.canonical_subject_identity,
        run_identity=item.run_identity, admission_identity=item.admission_identity,
        source_mapping_identity=item.source_mapping_identity,
        market_session_identity=item.market_session_identity,
        source_identity="ISOLATED-DESIGNATED-OBSERVATION",
        source_artifact_digest="ISOLATED-SOURCE-DIGEST",
        authority_publication_identity="ISOLATED-AUTHORITY-FIXTURE-NOT-PRODUCTION",
        price=Decimal("123.45"), observation_time=item.analysis_boundary-timedelta(seconds=2),
        available_at=item.analysis_boundary-timedelta(seconds=1),
        source_type="GOVERNED_ADMISSION_PRICE_OBSERVATION")
    core.update(changes)
    return AdmissionPriceProof(integrity_identity=_identity("INTEGRITY-ADMISSION-PRICE-PROOF-", core), **core)


def positive(item, proof=None, classification=Authority.EXACT_PRICE_PERSISTED, **changes):
    proof = proof or proof_for(item)
    core = dict(classification=classification, assessment_price=proof.price,
        assessment_time=proof.observation_time, assessment_source_identity=proof.source_identity,
        proof=proof, reason="ISOLATED_GOVERNED_PROOF",
        derivation_rule=("EXACT_DESIGNATED_OBSERVATION_PRICE_AND_TIME"
            if classification is Authority.EXACT_PRICE_DERIVABLE_FROM_SAME_GOVERNED_ASSESSMENT_EVIDENCE else None))
    core.update(changes)
    return replace(item, **core)


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
@pytest.mark.parametrize("classification", [Authority.EXACT_PRICE_PERSISTED,
    Authority.EXACT_PRICE_DERIVABLE_FROM_SAME_GOVERNED_ASSESSMENT_EVIDENCE])
def test_exact_positive_contract_roundtrip(direction, classification):
    run, _ = fixture(direction)
    item = create_missing_assessment_observations(run).observations[0]
    observed = positive(item, classification=classification)
    value = manifest(run, (observed,))
    validate_assessment_run(value, run)
    restored = _artifact_from_bytes(_artifact_bytes(value))
    assert restored == value
    assert restored.observations[0].assessment_time == run.analysis_boundary-timedelta(seconds=2)
    assert restored.observations[0].assessment_price == Decimal("123.45")
    assert _artifact_bytes(restored) == _artifact_bytes(value)


@pytest.mark.parametrize("field,value", [("assessment_price",None), ("assessment_time",None),
    ("assessment_source_identity",None), ("assessment_price",Decimal("124")),
    ("proof",None), ("derivation_rule","15M_CLOSE")])
def test_partial_or_conflicting_pair_rejected(field,value):
    item=create_missing_assessment_observations(fixture()[0]).observations[0]
    with pytest.raises(ProbablesV2Error): replace(positive(item), **{field:value})


@pytest.mark.parametrize("field,value", [("canonical_subject_identity","NSE-EQ-FOREIGN"),
    ("market_session_identity","WRONG-DAY"), ("source_mapping_identity","FOREIGN-MAPPING"),
    ("run_identity","FOREIGN-RUN"), ("admission_identity","FOREIGN-ADMISSION")])
def test_wrong_binding_with_identical_price_rejected(field,value):
    item=create_missing_assessment_observations(fixture()[0]).observations[0]
    with pytest.raises(ProbablesV2Error): positive(item,proof_for(item,**{field:value}))


@pytest.mark.parametrize("source", ["REVIEW", "CHART", "ANSWER", "LATER_LTP", "WO10",
    "BROKER", "ENTRY", "EOD", "15M_CLOSE", "5M_CLOSE", "VWAP", "ANALYSIS_BOUNDARY"])
def test_uncommissioned_substitutes_rejected(source):
    item=create_missing_assessment_observations(fixture()[0]).observations[0]
    with pytest.raises(ProbablesV2Error): proof_for(item,source_type=source)


@pytest.mark.parametrize("field", ["observation_time","available_at"])
def test_future_evidence_rejected(field):
    item=create_missing_assessment_observations(fixture()[0]).observations[0]
    with pytest.raises(ProbablesV2Error):
        positive(item,proof_for(item,**{field:item.analysis_boundary+timedelta(seconds=1)}))


@pytest.mark.parametrize("field", ["price","observation_time"])
def test_incomplete_source_observation_rejected(field):
    item=create_missing_assessment_observations(fixture()[0]).observations[0]
    with pytest.raises(ProbablesV2Error): proof_for(item,**{field:None})


@pytest.mark.parametrize("subject", ["NSE-EQ-RELIANCE", "NSE-INDEX-NIFTY", "NSE-INDEX-BANKNIFTY"])
@pytest.mark.parametrize("direction", ["LONG","SHORT"])
def test_subjects_and_direction_never_select_a_price(subject,direction):
    run,_=fixture(direction,subject)
    value=create_missing_assessment_observations(run)
    assert len(value.observations)==1
    item=value.observations[0]
    assert item.canonical_subject_identity==subject and item.direction==direction
    assert item.classification is Authority.PRICE_NOT_RETAINED
    assert item.assessment_price is item.assessment_time is item.proof is None
    with pytest.raises(ProbablesV2Error):
        positive(item,proof_for(item,canonical_subject_identity="DERIVATIVE-PROXY"))


@pytest.mark.parametrize("version", ["2.0.0","2.1.0","2.2.0"])
def test_prospective_manifest_restores_and_replays_without_changing_run(tmp_path,version):
    run,mapping=fixture(version=version)
    old=_artifact_bytes(run)
    store=ProbablesV2Store(tmp_path)
    store.retain_complete(run=run,mappings=(mapping,))
    assert type(store.load_current()) is AssessmentBoundProbablesV2Pointer
    before={p:sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob("*.json")}
    store.retain_complete(run=run,mappings=(mapping,))
    assert before=={p:sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob("*.json")}
    restored=ProbablesV2Store(tmp_path)
    assert _artifact_bytes(restored.load_current_run())==old
    assert restored.load_assessment_observations(run.run_identity)==create_missing_assessment_observations(run)


def test_existing_run_is_never_backfilled(tmp_path):
    run,mapping=fixture()
    store=ProbablesV2Store(tmp_path)
    store.retain_run(run)  # Existing pre-WO06C run; no assessment fields.
    old=_artifact_bytes(run)
    store.retain_complete(run=run,mappings=(mapping,))
    assert store.load_assessment_observations(run.run_identity) is None
    assert store.load_current()==create_current_probables_v2_pointer(run)
    assert _artifact_bytes(store.load_current_run())==old
    assert not (tmp_path/"probables-v2/assessment-observations-v1").exists()


@pytest.mark.parametrize("mutation", ["delete","tamper"])
def test_prospective_manifest_loss_or_tamper_rejected(tmp_path,mutation):
    run,mapping=fixture();store=ProbablesV2Store(tmp_path)
    store.retain_complete(run=run,mappings=(mapping,))
    path=tmp_path/"probables-v2/assessment-observations-v1"/(run.run_identity+".json")
    if mutation=="delete":path.unlink()
    else:path.write_bytes(path.read_bytes().replace(b"PRICE_NOT_RETAINED",b"EXACT_PRICE_PERSISTED"))
    with pytest.raises(ProbablesV2Error): ProbablesV2Store(tmp_path).load_current_run()
    with pytest.raises(ProbablesV2Error): store.retain_complete(run=run,mappings=(mapping,))


def test_manifest_write_failure_preserves_current_pointer(tmp_path,monkeypatch):
    run,mapping=fixture();store=ProbablesV2Store(tmp_path)
    store.retain_complete(run=run,mappings=(mapping,))
    pointer=store.load_current()
    other,other_mapping=fixture("SHORT")
    original=store._retain_typed
    def fail(family,identity,value):
        if family=="assessments":raise OSError("isolated persistence failure")
        return original(family,identity,value)
    monkeypatch.setattr(store,"_retain_typed",fail)
    with pytest.raises(OSError):store.retain_complete(run=other,mappings=(other_mapping,))
    assert store.load_current()==pointer
    assert store.load_current_run()==run


def test_duplicate_or_wrong_run_manifest_rejected():
    run,_=fixture();base=create_missing_assessment_observations(run)
    with pytest.raises(ProbablesV2Error):manifest(run,base.observations*2)
    with pytest.raises(ProbablesV2Error):validate_assessment_run(base,fixture("SHORT")[0])


@pytest.mark.parametrize("hours,fifteens,clock", [(0,2,time(10,30)),(1,4,time(11,0)),(2,8,time(12,0))])
def test_later_phases_do_not_choose_a_close(hours,fifteens,clock):
    mapping=_later_mapping(fifteens,hours,boundary=datetime.combine(CURRENT_DAY,clock,IST))
    run=run_mapping(mapping,create_probables_v2_methodology())
    base=create_missing_assessment_observations(run)
    assert base.observations
    assert all(item.classification is Authority.PRICE_NOT_RETAINED for item in base.observations)


def test_missing_classification_cannot_carry_values():
    item=create_missing_assessment_observations(fixture()[0]).observations[0]
    with pytest.raises(ProbablesV2Error):replace(item,assessment_price=Decimal("123"))
    with pytest.raises(ProbablesV2Error):replace(item,assessment_time=item.analysis_boundary)


def test_no_admissions_still_persist_explicit_empty_manifest(tmp_path):
    methodology=create_probables_v2_methodology()
    mapping=opening_mapping(methodology,prior="CONFLICTING",five="CONFLICTING",nifty="CONFLICTING")
    run=run_mapping(mapping,methodology)
    store=ProbablesV2Store(tmp_path);store.retain_complete(run=run,mappings=(mapping,))
    assert store.load_assessment_observations(run.run_identity).observations==()
    assert store.load_current_run()==run



def test_distinct_runs_preserve_repeated_subject_admissions():
    from kronos.intraday.probables_v2 import evaluate_probables_v2_run
    run,mapping=fixture()
    other=evaluate_probables_v2_run(source_discovery_run_identity=run.source_discovery_run_identity,
        universe_identity=run.universe_identity,universe_version=run.universe_version,
        reconciliation_identity=run.reconciliation_identity,reconciliation_version=run.reconciliation_version,
        market_session_identity=run.market_session_identity,analysis_boundary=run.analysis_boundary,
        member_evidence=(mapping,),unavailable_members=(),provenance=("ISOLATED-SECOND-ADMISSION",),
        methodology=run.methodology)
    left=create_missing_assessment_observations(run).observations[0]
    right=create_missing_assessment_observations(other).observations[0]
    assert left.canonical_subject_identity==right.canonical_subject_identity
    assert (left.run_identity,left.admission_identity)!=(right.run_identity,right.admission_identity)


@pytest.mark.parametrize("subject",["MCX-SUBJECT-CRUDE","MCX-SUBJECT-COPPER"])
def test_native_mcx_price_proof_cannot_use_reference(subject):
    from tests.unit.intraday.test_probables_v2 import _opening_inputs,_run
    *_,mapping=_opening_inputs(subject=subject,subject_exchange="MCX")
    run=_run(mapping)
    item=create_missing_assessment_observations(run).observations[0]
    assert item.canonical_subject_identity==subject
    assert item.assessment_price is None
    with pytest.raises(ProbablesV2Error):positive(item,proof_for(item,canonical_subject_identity="NYMEX:CL1!"))


def test_proof_tamper_is_not_repaired_by_outer_hash():
    item=create_missing_assessment_observations(fixture()[0]).observations[0]
    proof=proof_for(item)
    object.__setattr__(proof,"price",Decimal("777"))
    with pytest.raises(ProbablesV2Error):positive(item,proof)


def test_0930_pipeline_retains_missing_price_without_changing_admission(tmp_path):
    from tests.unit.intraday.test_analysis_time import REQUESTED
    from tests.unit.intraday.test_probables_v2_refresh_control import _control,_payload
    _,composition,control,_,_= _control(tmp_path,boundary=REQUESTED)
    result=control.execute_document(_payload("WO06C-0930",boundary=REQUESTED))
    assert result["outcome"]=="SUCCESS"
    run=composition.probables_v2_application.snapshot().run
    value=composition.probables_v2_application.store.load_assessment_observations(run.run_identity)
    assert value is not None
    assert len(value.observations)==run.diagnostics.total_probables
    assert all(item.classification is Authority.PRICE_NOT_RETAINED for item in value.observations)
    assert all(item.assessment_time is None for item in value.observations)


@pytest.mark.parametrize("price", [Decimal("NaN"),Decimal("Infinity"),float("nan"),"123.45"])
def test_price_representation_must_be_exact_finite_decimal(price):
    item=create_missing_assessment_observations(fixture()[0]).observations[0]
    with pytest.raises(ProbablesV2Error):proof_for(item,price=price)


@pytest.mark.parametrize("price", [Decimal("0"),Decimal("-1")])
def test_measurement_contract_does_not_invent_a_positive_price_policy(price):
    item=create_missing_assessment_observations(fixture()[0]).observations[0]
    assert positive(item,proof_for(item,price=price)).assessment_price==price
