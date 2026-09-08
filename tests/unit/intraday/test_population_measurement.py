"""WO-06D source, immutable population and dependence qualification; offline only."""
from dataclasses import replace
from datetime import datetime, timedelta, UTC
import json
from pathlib import Path

import pytest

from kronos.intraday.population_measurement import (
    MeasurementPopulation, PopulationMember, PopulationSlice, longitudinal_population,
)
from kronos.application.intraday_population_measurement import (
    IntradayPopulationMeasurement, PopulationMeasurementStore,
)
from kronos.intraday.probables_v2 import ProbablesV2Error
from kronos.intraday.probables_v2_persistence import ProbablesV2Store, _artifact_bytes
from tests.unit.intraday.test_assessment_observation import fixture
from tests.unit.intraday.test_assessment_capture import capture


def population(positive=False):
    run, mapping = fixture()
    return MeasurementPopulation(run, (mapping,), capture(run)[0] if positive else None)


def slice_at(index, state="LONG_PROBABLE", direction="LONG", phase="OPENING", session="NSE-DAY-1"):
    admitted = state.endswith("PROBABLE")
    return PopulationSlice(f"RUN-{index}", datetime(2026,9,1,4,tzinfo=UTC)+timedelta(minutes=index),
        (PopulationMember("NSE-EQ-RELIANCE", session, state, direction if admitted else None,
            phase if admitted else None, f"OBS-{index}" if admitted else None),))


def test_single_persistence_phase_disappearance_reentry_direction_session():
    runs = [slice_at(0), slice_at(1), slice_at(2,phase="STRUCTURE"),
        slice_at(3,state="NOT_ADMITTED"), slice_at(4),
        slice_at(5,state="SHORT_PROBABLE",direction="SHORT"),
        slice_at(6,state="SHORT_PROBABLE",direction="SHORT",session="NSE-DAY-2")]
    rows = longitudinal_population(runs)
    assert [r.states for r in rows] == [("NEW_ADMISSION",),("PERSISTED",),
        ("PERSISTED","PHASE_CHANGED"),("DISAPPEARED",),("REENTERED",),
        ("DIRECTION_CHANGED",),("NEW_ADMISSION","SESSION_CHANGED")]
    assert rows[0].episode_identity == rows[1].episode_identity == rows[2].episode_identity
    assert len({r.episode_identity for r in rows if r.episode_identity}) == 4
    assert sum(r.observation_identity is not None for r in rows) == 6
    assert rows[3].episode_identity is None
    assert rows[4].episode_identity != rows[0].episode_identity
    assert rows == longitudinal_population(reversed(runs))
    assert rows == longitudinal_population([*runs, runs[1]])


def test_unavailable_is_missing_population_not_loss():
    rows=longitudinal_population([slice_at(0),slice_at(1,state="UNAVAILABLE"),slice_at(2)])
    assert rows[1].states == ("DISAPPEARED",)
    assert rows[2].states == ("REENTERED",)
    assert rows[2].episode_identity != rows[0].episode_identity


def test_conflicting_run_rejected():
    with pytest.raises(ProbablesV2Error,match="RUN_CONFLICT"):
        longitudinal_population([slice_at(0),slice_at(0,phase="STRUCTURE")])


def test_equal_time_distinct_runs_rejected():
    with pytest.raises(ProbablesV2Error,match="ORDER_AMBIGUOUS"):
        longitudinal_population([slice_at(0),replace(slice_at(0),run_identity="OTHER")])


def test_coverage_change_not_silently_called_disappearance():
    other=replace(slice_at(1),members=(replace(slice_at(1).members[0],subject="OTHER"),))
    with pytest.raises(ProbablesV2Error,match="COVERAGE_CHANGED"):
        longitudinal_population([slice_at(0),other])


@pytest.mark.parametrize("positive",[False,True])
def test_full_source_roundtrip_assessment_and_no_price_fallback(tmp_path,positive):
    value=population(positive)
    assert len(value.observations)==value.denominators["admitted"]==1
    assert value.denominators["missing_measurement"]==int(not positive)
    encoded=value.encode()
    assert MeasurementPopulation.decode(encoded)==value
    assert MeasurementPopulation.decode(encoded).encode()==encoded
    store=PopulationMeasurementStore(tmp_path)
    path=store.retain(value);before=path.read_bytes()
    assert store.retain(value)==path and path.read_bytes()==before
    restored=PopulationMeasurementStore(tmp_path).load(value.run.run_identity)
    assert restored==value
    record=value.admission_records()[0]
    assert record["publication_timestamp"]=="NOT_RETAINED"
    if positive:
        assert record["assessment_price"]=="123.45"
        assert record["assessment_time"]!=record["analysis_boundary"]
        assert record["assessment_observation_identity"]
    else:
        assert record["assessment_authority"]=="PRICE_NOT_RETAINED"
        assert record["assessment_price"] is record["assessment_time"] is None
    assert all(f["retention"]=="EXACTLY_RETAINED" for f in record["semantic_features"])


def test_conflicting_immutable_population(tmp_path):
    store=PopulationMeasurementStore(tmp_path);store.retain(population())
    with pytest.raises(ProbablesV2Error):store.retain(population(True))
    assert store.load(population().run.run_identity)==population()


@pytest.mark.parametrize("mutation",["hash","source","membership","extra","schema"])
def test_corrupt_or_foreign_bundle_rejected(mutation):
    doc=json.loads(population().encode())
    if mutation=="hash":doc["identity"]="wrong"
    if mutation=="source":doc["population"]["run"]["artifact_identity"]="wrong"
    if mutation=="membership":doc["population"]["mappings"]=[]
    if mutation=="extra":doc["extra"]="untrusted"
    if mutation=="schema":doc["population"]["schema"]="unknown"
    with pytest.raises(ProbablesV2Error):MeasurementPopulation.decode(json.dumps(doc).encode())


def test_missing_or_duplicate_mapping_rejected():
    run,mapping=fixture()
    for mappings in [(),(mapping,mapping)]:
        with pytest.raises(ProbablesV2Error):MeasurementPopulation(run,mappings,None)


def test_unrelated_mapping_rejected():
    run,_=fixture();_,foreign=fixture(subject="NSE-EQ-FOREIGN")
    with pytest.raises(ProbablesV2Error):MeasurementPopulation(run,(foreign,),None)


@pytest.mark.parametrize("component",["../outside","/tmp/outside","INTRADAY-PROBABLES-V2-RUN-../../X"])
def test_path_rejected(tmp_path,component):
    with pytest.raises(ProbablesV2Error):PopulationMeasurementStore(tmp_path).load(component)


def test_symlink_ancestor_rejected(tmp_path):
    real=tmp_path/"real";real.mkdir();link=tmp_path/"link";link.symlink_to(real,target_is_directory=True)
    with pytest.raises(ProbablesV2Error):PopulationMeasurementStore(link).retain(population())


def test_existing_prospective_capture_is_every_admission_raw_measurement(tmp_path):
    run,mapping=fixture();store=ProbablesV2Store(tmp_path)
    proof=capture(run,fault="failure")[0]
    store.retain_complete(run=run,mappings=(mapping,),assessment_observations=proof)
    before={str(p):p.read_bytes() for p in tmp_path.rglob("*.json")}
    reader=IntradayPopulationMeasurement(store)
    result=reader.current()
    assert result.assessment==proof and result.denominators["missing_measurement"]==1
    assert len(result.observation_identities)==1
    assert reader.history()==(result,)
    assert {str(p):p.read_bytes() for p in tmp_path.rglob("*.json")}==before
    assert result.denominators["reviewed"]=="DOWNSTREAM_EVIDENCE_NOT_JOINED"
    assert result.denominators["not_traded"]=="NOT_ESTABLISHED"


def test_legacy_projection_never_backfills(tmp_path):
    run,mapping=fixture();store=ProbablesV2Store(tmp_path)
    store.retain_complete(run=run,mappings=(mapping,))
    # Reconstruct old standalone run history without a capture companion/pointer.
    (tmp_path/"probables-v2"/"assessment-observations-v1"/(run.run_identity+".json")).unlink()
    (tmp_path/"refresh-v2"/"CURRENT-PROBABLES-V2.json").unlink()
    before={str(p):p.read_bytes() for p in tmp_path.rglob("*.json")}
    value=IntradayPopulationMeasurement(store).population(run.run_identity)
    assert value.assessment is None and value.denominators["missing_measurement"]==1
    assert {str(p):p.read_bytes() for p in tmp_path.rglob("*.json")}==before


def test_source_missing_fails_closed(tmp_path):
    run,mapping=fixture();store=ProbablesV2Store(tmp_path);store.retain_complete(run=run,mappings=(mapping,))
    (tmp_path/"probables-v2"/"mappings"/(mapping.mapping_identity+".json")).unlink()
    with pytest.raises(ProbablesV2Error):IntradayPopulationMeasurement(store).population(run.run_identity)


def test_no_review_or_trading_selection_dependency():
    value=population();before=value.encode()
    downstream={"reviewed":[],"traded":["OTHER"],"rejected_later":["NSE-EQ-RELIANCE"]}
    assert value.denominators["admitted"]==1 and value.encode()==before
    downstream["traded"].append("NSE-EQ-RELIANCE")
    assert value.denominators["admitted"]==1 and value.encode()==before


def test_complete_mixed_denominator_and_frozen_rejection_reason():
    from kronos.intraday.probables_v2 import (
        evaluate_probables_v2_run, ProbablesUnavailableMemberV2, ProbableReasonV2,
    )
    from tests.unit.intraday.test_opening_admission_correction import opening_mapping
    run, admitted = fixture()
    rejected = opening_mapping(run.methodology, subject="NSE-EQ-REJECTED", narrow=False)
    unavailable = ProbablesUnavailableMemberV2("MEMBER-MISSING", "NSE-EQ-MISSING",
        admitted.market_session_identity, run.analysis_boundary,
        ProbableReasonV2.SOURCE_DISCOVERY_UNAVAILABLE,run.source_discovery_run_identity,("FIXTURE",))
    mixed=evaluate_probables_v2_run(source_discovery_run_identity=run.source_discovery_run_identity,
        universe_identity=run.universe_identity,universe_version=run.universe_version,
        reconciliation_identity=run.reconciliation_identity,reconciliation_version=run.reconciliation_version,
        market_session_identity=run.market_session_identity,analysis_boundary=run.analysis_boundary,
        member_evidence=(admitted,rejected),unavailable_members=(unavailable,),provenance=run.provenance,
        methodology=run.methodology)
    value=MeasurementPopulation(mixed,(admitted,rejected),None)
    assert value.denominators["governed_population"]==3
    assert value.denominators["probables_evaluable"]==2
    assert value.denominators["probables_unavailable"]==1
    assert value.denominators["admission_evaluated"]==2
    assert value.denominators["admitted"]==value.denominators["missing_measurement"]==1
    assert value.denominators["not_admitted"]==1
    assert len(value.run.results)==3 and len(value.observations)==1
    assert MeasurementPopulation.decode(value.encode())==value
    assert any(ProbableReasonV2.NARROW_CPR_NOT_SATISFIED in r.reasons for r in value.run.results)


@pytest.mark.parametrize("direction",["LONG","SHORT"])
def test_long_short_and_foreign_assessment(direction):
    run,mapping=fixture(direction);proof=capture(run)[0]
    value=MeasurementPopulation(run,(mapping,),proof)
    assert value.admission_records()[0]["direction"]==direction
    wrong_run,wrong_mapping=fixture("SHORT" if direction=="LONG" else "LONG")
    with pytest.raises(ProbablesV2Error):MeasurementPopulation(wrong_run,(wrong_mapping,),proof)


def test_measurement_absence_is_not_zero():
    assert population().denominators["discovery_factually_evaluable"]=="NOT_RETAINED"
    with pytest.raises(ProbablesV2Error):replace(population(),discovery="not-a-source")


def test_duplicate_subject_and_direction_state_conflict():
    p=slice_at(0)
    with pytest.raises(ProbablesV2Error):replace(p,members=p.members+p.members)
    with pytest.raises(ProbablesV2Error):replace(p.members[0],direction="SHORT")


def test_missing_store_artifact_is_typed(tmp_path):
    with pytest.raises(ProbablesV2Error,match="SOURCE_MISSING"):
        PopulationMeasurementStore(tmp_path).load(population().run.run_identity)


@pytest.mark.parametrize("conflict", [False, True])
def test_competing_first_writes_never_overwrite(tmp_path, monkeypatch, conflict):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    import kronos.application.intraday_population_measurement as application
    barrier = Barrier(2)
    link = application.os.link
    def concurrent_link(source, destination):
        barrier.wait(timeout=5)
        return link(source, destination)
    monkeypatch.setattr(application.os, "link", concurrent_link)
    values = (population(False), population(conflict))
    def retain(value):
        try:
            PopulationMeasurementStore(tmp_path).retain(value)
            return "RETAINED"
        except ProbablesV2Error as error:
            assert str(error) == "MEASUREMENT_IMMUTABLE_CONFLICT"
            return "CONFLICT"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(retain, values))
    assert results.count("RETAINED") == (1 if conflict else 2)
    restored = PopulationMeasurementStore(tmp_path).load(values[0].run.run_identity)
    assert restored in values
    assert len(list((tmp_path / "population-measurement-v1").iterdir())) == 1


def test_failed_atomic_publication_leaves_no_partial_artifact(tmp_path, monkeypatch):
    import kronos.application.intraday_population_measurement as application
    def fail(*args):
        raise OSError("isolated injected storage failure")
    monkeypatch.setattr(application.os, "link", fail)
    with pytest.raises(OSError):
        PopulationMeasurementStore(tmp_path).retain(population())
    assert list((tmp_path / "population-measurement-v1").iterdir()) == []
