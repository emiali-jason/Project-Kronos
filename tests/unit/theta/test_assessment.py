"""TE-05C synthetic documentary assessment qualification.

All values are disposable and explicitly NOT FOR GENUINE FORECASTING.
"""
from copy import deepcopy
from datetime import timedelta
import inspect
import json

import pytest

from kronos.theta.assessment import (
    ASSESSMENT_DESCRIPTOR, CRITERIA, RESEARCH_DESCRIPTOR, SCHEMA_ID,
    ThetaAssessmentEngine,
)
from kronos.theta.combined_intake import CombinedAnswerIntake
from kronos.theta.contracts import SUBJECTS, ThetaError, digest, encode, stamp
from kronos.theta.contracts_v3 import make_question_batch_v3, make_question_v3
from kronos.theta.methodology import ASSESSMENT_ID, ASSESSMENT_SHA256, RESEARCH_ID, RESEARCH_SHA256
from kronos.theta.methodology import DECISION_NAME, MANIFEST_NAME, ROOT as METHODOLOGY_ROOT
from kronos.theta.store import ThetaStore, sealed, unseal
from kronos.theta.workflow import ThetaWorkflow
from tests.unit.theta.test_combined_intake import fixture_at, place, run, snapshot
from tests.unit.theta.test_methodology_publication import effective_after, genuine_fixture, publication
from tests.unit.theta.test_producer_v3 import completed, generated
from tests.unit.theta.test_workflow import chart


def _statement(text, evidence):
    return {"classification": "HYPOTHESIS", "text": text,
            "evidence_ids": list(evidence), "source_ids": ["SOURCE-1"] if evidence else []}


def documented_child(child):
    """Replace fixture research with an all-DOCUMENTED structured witness."""
    t0, analyzed = stamp(child["information_cutoff"]), stamp(child["analyzed_at"])
    source = {"source_id": "SOURCE-1", "publisher": "Fixture publisher",
        "title": "Disposable documentary source", "source_kind": "UNKNOWN",
        "url": "https://example.com/theta-te05c", "reference": None,
        "published_at": None, "available_at": (t0 - timedelta(hours=1)).isoformat(),
        "accessed_at": (analyzed - timedelta(minutes=30)).isoformat(),
        "availability_evidence": "Disposable archive witness", "observation_period": "Fixture period",
        "lineage": {"status": "UNKNOWN", "original_information_id": None,
                    "derivative_source_ids": []},
        "archive_version_locator": None, "relevance": "Documentary fixture", "linked_evidence_ids": []}
    observations = []
    for horizon in ("E1", "E2"):
        for role in ("REFERENCE", "MCX"):
            observations.append({"observation_id": f"OBS-{horizon}-{role}",
                "chart_reference": deepcopy(child["binding"]["commodity_chart"]),
                "panel_locator": "Fixture panel", "role": role,
                "displayed_instrument": "Fixture instrument", "timeframe": "1D",
                "availability": "AVAILABLE", "observation_text": "Visible fixture observation",
                "classification": "HYPOTHESIS", "visible_as_of": t0.isoformat(),
                "completion": "COMPLETED", "unavailable_reason": None, "horizons": [horizon]})
    evidence = []
    assumptions, limitations, relationships, events = [], [], [], []
    for horizon in ("E1", "E2"):
        assumption, limitation = "ASSUMPTION-" + horizon, "LIMITATION-" + horizon
        for kind, observations_used in (("SUPPORT", [f"OBS-{horizon}-REFERENCE"]),
                                        ("OPPOSE", []),
                                        ("RECON", [f"OBS-{horizon}-REFERENCE", f"OBS-{horizon}-MCX"])):
            identity = f"CLAIM-{horizon}-{kind}"
            evidence.append({"evidence_id": identity, "statement": "Disposable " + kind.lower() + " claim",
                "classification": "HYPOTHESIS", "source_ids": ["SOURCE-1"],
                "observation_ids": observations_used, "horizons": [horizon],
                "assumption_ids": [assumption]})
        assumptions.append({"identity": assumption, "statement": "Disposable declared assumption",
            "scope": "HORIZON", "horizons": [horizon],
            "supporting_evidence_ids": [f"CLAIM-{horizon}-SUPPORT"],
            "affected_references": [{"kind": "FORECAST", "identity": horizon}],
            "unresolved_consequence": "Uncertain fixture consequence"})
        limitations.append({"identity": limitation, "statement": "Disposable declared limitation",
            "scope": "HORIZON", "horizons": [horizon],
            "supporting_evidence_ids": [f"CLAIM-{horizon}-SUPPORT"],
            "affected_references": [{"kind": "EVIDENCE", "identity": f"CLAIM-{horizon}-SUPPORT"}],
            "unresolved_consequence": "Bounded fixture limitation"})
        for relation_kind, claim_kind in (("SUPPORT", "SUPPORT"), ("OPPOSITION", "OPPOSE")):
            relationships.append({"relation_id": f"REL-{horizon}-{relation_kind}",
                "references": [{"kind": "FORECAST", "identity": horizon},
                               {"kind": "EVIDENCE", "identity": f"CLAIM-{horizon}-{claim_kind}"}],
                "relationship_type": relation_kind, "horizons": [horizon],
                "explanation": "Disposable typed relationship", "unresolved_limitation": None,
                "limitation_ids": [limitation]})
        relationships.append({"relation_id": f"REL-{horizon}-RECONCILIATION",
            "references": [{"kind": "OBSERVATION", "identity": f"OBS-{horizon}-REFERENCE"},
                           {"kind": "OBSERVATION", "identity": f"OBS-{horizon}-MCX"},
                           {"kind": "EVIDENCE", "identity": f"CLAIM-{horizon}-RECON"}],
            "relationship_type": "RECONCILIATION", "horizons": [horizon],
            "explanation": "Disposable chart/research reconciliation", "unresolved_limitation": None,
            "limitation_ids": [limitation]})
        events.append({"event_id": "EVENT-" + horizon, "description": "Disposable scheduled event",
            "availability": "AVAILABLE",
            "scheduled_window": {"start": (t0 + timedelta(days=1)).isoformat(),
                                 "end": (t0 + timedelta(days=1, hours=1)).isoformat()},
            "schedule_source_id": "SOURCE-1", "schedule_known_at": t0.isoformat(),
            "horizons": [horizon], "evidence_ids": [f"CLAIM-{horizon}-SUPPORT"],
            "possible_impact": "Unknown fixture impact", "limitations": "Outcome unavailable at T0"})
        forecast = child["forecasts"][horizon]
        claims = [f"CLAIM-{horizon}-{kind}" for kind in ("SUPPORT", "OPPOSE", "RECON")]
        forecast.update(material_evidence_ids=claims, material_source_ids=["SOURCE-1"],
                        assumption_ids=[assumption], limitation_ids=[limitation],
                        rationale=_statement("Horizon rationale", [claims[0], claims[2]]),
                        counterevidence=_statement("Reviewed counterevidence", [claims[1]]),
                        uncertainty=_statement("Horizon uncertainty", [claims[0]]),
                        path_risk=_statement("Horizon path risk", [claims[0]]),
                        confidence_justification=_statement("Confidence explanation", [claims[0]]))
    source["linked_evidence_ids"] = [item["evidence_id"] for item in evidence]
    sections = {
        "chart_assessment": ["CLAIM-E1-RECON", "CLAIM-E2-RECON"],
        "reference_mcx_assessment": ["CLAIM-E1-RECON", "CLAIM-E2-RECON"],
        "bullish_evidence": ["CLAIM-E1-SUPPORT", "CLAIM-E2-SUPPORT"],
        "bearish_evidence": ["CLAIM-E1-OPPOSE", "CLAIM-E2-OPPOSE"],
        "macro_fundamental_research": ["CLAIM-E1-SUPPORT", "CLAIM-E2-SUPPORT"],
        "commodity_research": ["CLAIM-E1-SUPPORT", "CLAIM-E2-SUPPORT"],
        "reconciliation": ["CLAIM-E1-RECON", "CLAIM-E2-RECON"],
        "counterevidence": ["CLAIM-E1-OPPOSE", "CLAIM-E2-OPPOSE"],
        "uncertainty": ["CLAIM-E1-SUPPORT", "CLAIM-E2-SUPPORT"],
    }
    child["research"] = {name: {"availability": "AVAILABLE", "classification": "HYPOTHESIS",
        "text": "Disposable " + name, "reason": None, "evidence_ids": ids}
        for name, ids in sections.items()}
    child["research"].update(chart_observations=observations, evidence_items=evidence,
        relationships=relationships, scheduled_events=events, assumptions=assumptions,
        limitations=limitations, sources=[source])


def limited_c3(child, horizon):
    child["research"]["relationships"] = [r for r in child["research"]["relationships"]
        if r["relation_id"] != f"REL-{horizon}-OPPOSITION"]


def empty_events(child, _horizon=None):
    child["research"]["scheduled_events"] = []


def limited_c7(child, horizon):
    child["research"]["scheduled_events"] = [event for event in child["research"]["scheduled_events"]
        if event["event_id"] != "EVENT-" + horizon]


def accepted_scenario(root, *, mutations=None, methodology_change=None):
    p, clock = genuine_fixture(root)
    _, batch, questions, _, _ = generated(p)
    if methodology_change:
        revised = {}
        for subject, old in questions.items():
            binding = deepcopy(old["binding"])
            binding["methodology"][methodology_change[0]] = methodology_change[1]
            revised[subject] = make_question_v3(binding=binding, targets=old["targets"],
                created_at=old["created_at"], authority_valid_through=old["authority_valid_through"],
                methodology_instructions=old["methodology_instructions"], synthetic=False)
        questions, batch = revised, make_question_batch_v3(revised)
        p.intake.retain_question_batch(batch, questions)
    answer = completed(batch, questions)
    analyzed = clock[0] + timedelta(hours=2)
    for subject, child in answer["answers"].items():
        child["analyzed_at"] = analyzed.isoformat()
        documented_child(child)
        if mutations and subject in mutations:
            mutations[subject](child)
    p.workflow.inbox.mkdir(exist_ok=True)
    raw = json.dumps(answer, ensure_ascii=False, indent=2).encode()
    (p.workflow.inbox / (batch["batch_id"] + "_ANSWERS.json")).write_bytes(raw)
    clock[0] += timedelta(hours=3)
    accepted = p.intake.import_combined_astra_answer(batch["batch_id"])
    assert accepted["package_status"] == "COMPLETE", accepted
    return p, clock, questions, answer, raw, accepted, ThetaAssessmentEngine(p.intake, publication())


def criterion(result, horizon, identity):
    return next(item for item in result["assessment"]["horizons"][horizon]["criteria"]
                if item["criterion_id"] == identity)


def test_exact_policy_admission_and_five_child_rehearsal(tmp_path):
    changes = {"SILVERM": lambda child: limited_c3(child, "E2"),
               "COPPER": empty_events}
    p, _, questions, answer, raw, accepted, engine = accepted_scenario(tmp_path, mutations=changes)
    original_receipts = {s: deepcopy(p.intake.accepted_evidence(row["receipt_id"])["receipt"])
                         for s, row in accepted["children"].items()}
    results = {s: engine.assess_accepted_theta_answer(row["answer_id"])
               for s, row in accepted["children"].items()}
    assert results["GOLDM"]["assessment"]["horizons"]["E1"]["result"] == "DOCUMENTED"
    assert results["GOLDM"]["assessment"]["horizons"]["E2"]["result"] == "DOCUMENTED"
    assert results["SILVERM"]["assessment"]["horizons"]["E1"]["result"] == "DOCUMENTED"
    assert results["SILVERM"]["assessment"]["horizons"]["E2"]["result"] == "LIMITED"
    assert all(results["COPPER"]["assessment"]["horizons"][h]["result"] == "LIMITED"
               for h in ("E1", "E2"))
    for subject, result in results.items():
        record = result["assessment"]
        assert result["disposition"] == "CREATED" and result["currentness"] in {"CURRENT", "HISTORICAL"}
        assert record["schema_identity"] == SCHEMA_ID
        assert record["assessment_methodology"] == ASSESSMENT_DESCRIPTOR
        assert record["research_methodology"] == RESEARCH_DESCRIPTOR
        assert set(record["horizons"]) == {"E1", "E2"} and "result" not in record
        assert [c["criterion_id"] for c in record["horizons"]["E1"]["criteria"]] == list(CRITERIA)
        assert "score" not in encode(record).decode().lower()
        assert p.intake.accepted_evidence(accepted["children"][subject]["receipt_id"])["receipt"] == original_receipts[subject]
    assert p.intake.accepted_evidence(accepted["children"]["GOLDM"]["receipt_id"])["package_raw"] == raw
    assert answer["answers"]["GOLDM"]["forecasts"]["E1"]["confidence_pct"] == "82.00"


@pytest.mark.parametrize("identity,mutation", [
    ("C1", lambda c: c["forecasts"]["E1"].update(material_source_ids=[])),
    ("C2", lambda c: c["research"]["macro_fundamental_research"].update(
        evidence_ids=["CLAIM-E2-SUPPORT"])),
    ("C3", lambda c: limited_c3(c, "E1")),
    ("C4", lambda c: (c["forecasts"]["E1"].update(assumption_ids=[], limitation_ids=[]),
        [e.update(assumption_ids=[]) for e in c["research"]["evidence_items"] if "E1" in e["horizons"]],
        [r.update(limitation_ids=[]) for r in c["research"]["relationships"] if "E1" in r["horizons"]],
        c["research"].update(assumptions=[a for a in c["research"]["assumptions"] if "E1" not in a["horizons"]],
                             limitations=[a for a in c["research"]["limitations"] if "E1" not in a["horizons"]]))),
    ("C6", lambda c: next(o for o in c["research"]["chart_observations"]
                          if o["observation_id"] == "OBS-E1-MCX").update(
        availability="UNAVAILABLE", observation_text=None, classification=None,
        displayed_instrument=None, timeframe=None, completion="UNKNOWN",
        unavailable_reason="Unavailable in fixture")),
    ("C7", lambda c: limited_c7(c, "E1")),
    ("C8", lambda c: c["forecasts"]["E1"].update(path_risk=_statement("Path risk unlinked", []))),
    ("C9", lambda c: c["research"]["relationships"].append({
        "relation_id": "REL-E1-UNRESOLVED", "references": [
            {"kind": "FORECAST", "identity": "E1"},
            {"kind": "EVIDENCE", "identity": "CLAIM-E1-OPPOSE"}],
        "relationship_type": "UNRESOLVED_CONTRADICTION", "horizons": ["E1"],
        "explanation": "Declared unresolved fixture contradiction",
        "unresolved_limitation": "Not resolved at T0", "limitation_ids": ["LIMITATION-E1"]})),
])
def test_each_documentary_limited_predicate_is_horizon_local(tmp_path, identity, mutation):
    _, _, _, _, _, accepted, engine = accepted_scenario(tmp_path,
        mutations={"GOLDM": mutation})
    result = engine.assess_accepted_theta_answer(accepted["children"]["GOLDM"]["answer_id"])
    assert criterion(result, "E1", identity)["result"] == "LIMITED"
    assert criterion(result, "E2", identity)["result"] == "DOCUMENTED"
    assert result["assessment"]["horizons"]["E1"]["result"] == "LIMITED"


def test_c5_accepted_chronology_and_later_valid_retrieval(tmp_path):
    _, _, _, answer, _, accepted, engine = accepted_scenario(tmp_path)
    child = answer["answers"]["GOLDM"]
    source = child["research"]["sources"][0]
    assert stamp(source["available_at"]) <= stamp(child["information_cutoff"]) < stamp(source["accessed_at"])
    result = engine.assess_accepted_theta_answer(accepted["children"]["GOLDM"]["answer_id"])
    assert criterion(result, "E1", "C5")["result"] == "DOCUMENTED"


def test_event_timing_before_across_and_after_expiry_is_retained(tmp_path):
    def mutate(child):
        base = deepcopy(next(e for e in child["research"]["scheduled_events"] if e["event_id"] == "EVENT-E1"))
        expiry = stamp(child["forecasts"]["E1"]["target"]["expires_at"])
        across = deepcopy(base); across["event_id"] = "EVENT-E1-ACROSS"
        across["scheduled_window"] = {"start": (expiry - timedelta(hours=1)).isoformat(),
                                      "end": (expiry + timedelta(hours=1)).isoformat()}
        after = deepcopy(base); after["event_id"] = "EVENT-E1-AFTER"
        after["scheduled_window"] = {"start": (expiry + timedelta(days=1)).isoformat(),
                                     "end": (expiry + timedelta(days=1, hours=1)).isoformat()}
        child["research"]["scheduled_events"].extend([across, after])
    _, _, _, _, _, accepted, engine = accepted_scenario(tmp_path, mutations={"GOLDM": mutate})
    result = engine.assess_accepted_theta_answer(accepted["children"]["GOLDM"]["answer_id"])
    timing = {item["event_id"]: item["position"] for item in criterion(result, "E1", "C7")["event_timing"]}
    assert set(timing.values()) == {"BEFORE_EXPIRY", "ACROSS_EXPIRY", "AFTER_EXPIRY"}


@pytest.mark.parametrize("field,value", [
    ("identity", "FOREIGN-ASSESSMENT-POLICY"), ("version", "9.0.0"),
    ("descriptor_sha256", "f" * 64),
])
def test_wrong_assessment_publication_identity_version_or_bytes_rejects(tmp_path, field, value):
    p, _, _, _, _, accepted, _ = accepted_scenario(tmp_path / "scenario")
    root = (tmp_path / "publication").resolve(); root.mkdir()
    for name in (RESEARCH_ID + ".json", ASSESSMENT_ID + ".json", DECISION_NAME, MANIFEST_NAME):
        (root / name).write_bytes((METHODOLOGY_ROOT / name).read_bytes())
    if field == "descriptor_sha256":
        decision = json.loads((root / DECISION_NAME).read_bytes())
        decision["methodologies"][ASSESSMENT_ID]["sha256"] = value
        (root / DECISION_NAME).write_bytes(encode(decision))
    else:
        policy = json.loads((root / (ASSESSMENT_ID + ".json")).read_bytes())
        policy[field] = value
        (root / (ASSESSMENT_ID + ".json")).write_bytes(encode(policy))
    engine = ThetaAssessmentEngine(p.intake, type(publication())(root))
    result = engine.assess_accepted_theta_answer(accepted["children"]["GOLDM"]["answer_id"])
    assert result["assessment"]["assessment_admission"] == "NOT_EVALUABLE"
    assert result["assessment"]["verification_claim"] is None


@pytest.mark.parametrize("field,value", [
    ("identity", "FOREIGN-RESEARCH-METHOD"), ("version", "9.0.0"), ("sha256", "f" * 64),
])
def test_wrong_question_policy_binding_is_not_evaluable(tmp_path, field, value):
    _, _, _, _, _, accepted, engine = accepted_scenario(tmp_path,
        methodology_change=(field, value))
    result = engine.assess_accepted_theta_answer(accepted["children"]["GOLDM"]["answer_id"])
    assert result["assessment"]["assessment_admission"] == "NOT_EVALUABLE"
    assert all(result["assessment"]["horizons"][h]["result"] == "NOT_EVALUABLE"
               for h in ("E1", "E2"))
    assert result["assessment"]["accepted_answer"]["answer_id"] == accepted["children"]["GOLDM"]["answer_id"]


def test_pre_policy_answer_is_not_silently_assessed(tmp_path):
    scenario = fixture_at(tmp_path)
    place(scenario); accepted = run(scenario)
    engine = ThetaAssessmentEngine(scenario[0], publication())
    result = engine.assess_accepted_theta_answer(accepted["children"]["GOLDM"]["answer_id"])
    assert result["assessment"]["assessment_admission"] == "NOT_EVALUABLE"
    assert criterion(result, "E1", "C5")["result"] == "NOT_EVALUABLE"


def test_arbitrary_or_unknown_input_cannot_be_assessed_or_persisted(tmp_path):
    p, _, _, _, _, _, engine = accepted_scenario(tmp_path)
    before = snapshot(p.store.root)
    result = engine.assess_accepted_theta_answer("ARBITRARY-JSON")
    assert result["assessment"] is None and result["disposition"] == "NOT_EVALUABLE"
    assert snapshot(p.store.root) == before
    invalid = engine.assess_accepted_theta_answer({"answer_id": "ARBITRARY-JSON"})
    assert invalid["assessment"] is None and invalid["disposition"] == "NOT_EVALUABLE"
    assert not any(name.startswith("v3-assessments/") for name in before)


def test_broken_trusted_graph_returns_not_evaluable_without_assessment_publication(tmp_path):
    p, _, _, _, _, accepted, engine = accepted_scenario(tmp_path)
    row = accepted["children"]["GOLDM"]
    evidence = p.intake.accepted_evidence(row["receipt_id"])
    blob = p.store.root / "blobs" / digest(evidence["child_raw"])
    blob.write_bytes(b"corrupt")
    result = engine.assess_accepted_theta_answer(row["answer_id"])
    assert result["assessment"] is None and result["disposition"] == "NOT_EVALUABLE"
    assert not (p.store.root / "v3-assessments").exists()


def test_replay_restart_restores_without_reassessment_or_new_timestamp(tmp_path, monkeypatch):
    p, clock, _, _, _, accepted, engine = accepted_scenario(tmp_path)
    answer_id = accepted["children"]["GOLDM"]["answer_id"]
    first = engine.assess_accepted_theta_answer(answer_id)
    before = snapshot(p.store.root); clock[0] += timedelta(days=1)
    monkeypatch.setattr(engine, "_policy", lambda *_: (_ for _ in ()).throw(AssertionError("re-evaluated")))
    replay = engine.assess_accepted_theta_answer(answer_id)
    assert replay["disposition"] == "REPLAY" and replay["assessment"] == first["assessment"]
    assert snapshot(p.store.root) == before
    fresh_intake = CombinedAnswerIntake(ThetaWorkflow(ThetaStore(p.store.root), inbox=p.workflow.inbox,
        outbox=p.workflow.outbox, clock=lambda: clock[0]), current_authorities=p.intake.current_authorities)
    fresh = ThetaAssessmentEngine(fresh_intake, publication())
    monkeypatch.setattr(fresh, "_policy", lambda *_: (_ for _ in ()).throw(AssertionError("re-evaluated")))
    restored = fresh.restore_assessment(first["assessment"]["assessment_id"])
    assert restored["disposition"] == "RESTORED" and restored["assessment"] == first["assessment"]
    assert snapshot(p.store.root) == before


def test_currentness_is_projected_without_mutating_historical_assessment(tmp_path):
    p, clock, _, _, _, accepted, engine = accepted_scenario(tmp_path)
    row = accepted["children"]["GOLDM"]
    first = engine.assess_accepted_theta_answer(row["answer_id"])
    immutable = deepcopy(first["assessment"])
    clock[0] += timedelta(minutes=1)
    p.workflow.intake_chart(subject="GOLDM", label="Replacement fixture",
        information_cutoff=clock[0].isoformat(), media_type="image/png", payload=chart())
    restored = engine.restore_assessment(immutable["assessment_id"])
    assert restored["currentness"] == "STALE" and restored["assessment"] == immutable


def test_immutable_conflict_and_corrupt_record_fail_closed(tmp_path):
    p, _, _, _, _, accepted, engine = accepted_scenario(tmp_path)
    row = accepted["children"]["GOLDM"]
    first = engine.assess_accepted_theta_answer(row["answer_id"])["assessment"]
    changed = deepcopy(first); changed["horizons"]["E1"]["criteria"][0]["result"] = "LIMITED"
    with pytest.raises(ThetaError, match="THETA_IMMUTABLE_CONFLICT"):
        p.store.retain("v3-assessments", first["assessment_id"] + ".json", sealed(changed))
    path = p.store.root / "v3-assessments" / (first["assessment_id"] + ".json")
    path.write_bytes(b"corrupt")
    with pytest.raises(ThetaError, match="THETA_ASSESSMENT_RESTORE_INVALID"):
        engine.restore_assessment(first["assessment_id"])


def test_persistence_failure_never_publishes_valid_assessment(tmp_path, monkeypatch):
    p, _, _, _, _, accepted, engine = accepted_scenario(tmp_path)
    real = p.store.retain
    def fail(family, name, payload):
        if family == "v3-assessments":
            raise OSError("synthetic crash")
        return real(family, name, payload)
    monkeypatch.setattr(p.store, "retain", fail)
    result = engine.assess_accepted_theta_answer(accepted["children"]["GOLDM"]["answer_id"])
    assert result["assessment"] is None and result["disposition"] == "NOT_EVALUABLE"
    assert not (p.store.root / "v3-assessments").exists()


def test_c9_limited_never_rejects_or_rewrites_forecast(tmp_path):
    mutation = lambda child: child["research"]["relationships"].append({
        "relation_id": "REL-E1-UNRESOLVED", "references": [
            {"kind": "FORECAST", "identity": "E1"},
            {"kind": "EVIDENCE", "identity": "CLAIM-E1-OPPOSE"}],
        "relationship_type": "UNRESOLVED_CONTRADICTION", "horizons": ["E1"],
        "explanation": "Declared unresolved fixture contradiction",
        "unresolved_limitation": "Not resolved at T0", "limitation_ids": ["LIMITATION-E1"]})
    p, _, _, answer, raw, accepted, engine = accepted_scenario(tmp_path, mutations={"GOLDM": mutation})
    before = deepcopy(answer["answers"]["GOLDM"]["forecasts"])
    result = engine.assess_accepted_theta_answer(accepted["children"]["GOLDM"]["answer_id"])
    assert criterion(result, "E1", "C9")["reason_code"] == "THETA_ASSESSMENT_C9_DECLARED_UNRESOLVED_CONTRADICTION"
    assert accepted["children"]["GOLDM"]["status"] == "ACCEPTED"
    assert p.intake.accepted_evidence(accepted["children"]["GOLDM"]["receipt_id"])["package_raw"] == raw
    assert answer["answers"]["GOLDM"]["forecasts"] == before


def test_application_surface_and_static_boundaries():
    methods = {name for name, value in inspect.getmembers(ThetaAssessmentEngine, inspect.isfunction)
               if not name.startswith("_")}
    assert methods == {"assess_accepted_theta_answer", "restore_assessment"}
    source = inspect.getsource(inspect.getmodule(ThetaAssessmentEngine))
    for forbidden in ("requests", "kite", "broker", "openai", "ocr", "margin", "pnl"):
        assert forbidden not in source.lower()
    assert ASSESSMENT_DESCRIPTOR == {"identity": ASSESSMENT_ID, "version": "1.0.0",
                                     "sha256": ASSESSMENT_SHA256}
    assert RESEARCH_DESCRIPTOR == {"identity": RESEARCH_ID, "version": "1.0.0",
                                   "sha256": RESEARCH_SHA256}
