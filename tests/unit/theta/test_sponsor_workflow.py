"""TE-06A two-button orchestration with disposable synthetic evidence only."""

from contextlib import contextmanager
from datetime import timedelta
from io import BytesIO
import json
from threading import Event, Thread
from urllib.parse import urlencode
from zipfile import ZipFile

import pytest

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.browser.product_routes import ProductBrowserRoutes
from kronos.browser.server import create_browser_server
from kronos.browser.theta_routes import ThetaBrowserRoutes
from kronos.theta.assessment import ThetaAssessmentEngine
from kronos.theta.contracts import SUBJECTS, ThetaError, digest
from kronos.theta.methodology import ThetaMethodologyPublication
from kronos.theta.orchestration import ThetaSponsorWorkflow
from kronos.theta.producer_v3 import V3QuestionProducer
from kronos.theta.store import ThetaStore
from kronos.theta.workflow import ThetaWorkflow
from tests.unit.theta.test_assessment import documented_child
from tests.unit.theta.test_combined_intake import authority_adapter, snapshot
from tests.unit.theta.test_methodology_publication import publication, genuine_fixture
from tests.unit.theta.test_producer_v3 import completed
from tests.unit.theta.test_rehearsal import request
from tests.unit.theta.test_workflow import chart


def fixture(root):
    producer, clock = genuine_fixture(root)
    # Exact approved publications/target owner with visibly synthetic charts.
    # This marks every transport SYNTHETIC / NOT FOR GENUINE FORECASTING.
    producer.workflow.qualification_mode = True
    engine = ThetaAssessmentEngine(producer.intake, publication())
    return ThetaSponsorWorkflow(producer, engine), producer, clock


def answer_for(producer, clock, *, invalid_subject=None):
    batch_id = producer.selected()["batch_id"]
    batch, questions = producer.intake._batch(batch_id)
    value = completed(batch, questions)
    analyzed = clock[0] + timedelta(hours=2)
    for subject, child in value["answers"].items():
        child["analyzed_at"] = analyzed.isoformat()
        documented_child(child)
    if invalid_subject is not None:
        value["answers"][invalid_subject]["forecasts"]["E1"]["confidence_pct"] = "101"
    producer.workflow.inbox.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, indent=2).encode() + b"\n"
    (producer.workflow.inbox / (batch_id + "_ANSWERS.json")).write_bytes(raw)
    clock[0] += timedelta(hours=3)
    return value, raw


def create(application):
    return application.create_question_pack(application.input_state_sha256())


@contextmanager
def running(application):
    provider_calls = []
    def forbidden_provider():
        provider_calls.append("FORBIDDEN")
        raise AssertionError("TE-06A rehearsal must not construct a Provider")
    swing = SwingOpportunitiesApplication(forbidden_provider)
    routes = ProductBrowserRoutes((ThetaBrowserRoutes(
        application.workflow, sponsor_workflow=application),))
    server = create_browser_server(swing, port=0, product_routes=routes)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
        assert not thread.is_alive() and not provider_calls


def test_create_one_exact_five_subject_transport_and_idempotent_t0(tmp_path):
    application, producer, clock = fixture(tmp_path.resolve())
    first = create(application)
    result = first["result"]
    assert result["complete"] and set(result["questions"]) == set(SUBJECTS)
    assert len(set(result["questions"].values())) == 5
    raw = (producer.workflow.outbox / result["filename"]).read_bytes()
    assert digest(raw) == result["zip_sha256"]
    with ZipFile(BytesIO(raw)) as archive:
        names = archive.namelist()
        assert len([n for n in names if n.endswith("QUESTION.pdf")]) == 5
        assert len([n for n in names if n == "shared/GLOBAL_MACRO.png"]) == 1
        assert len([n for n in names if n.endswith("/charts/")]) == 0
        assert "combined-answer-template.json" in names
        assert "combined-answer.schema.json" in names
        assert "producer-instructions.txt" in names and "manifest.json" in names
        assert b"SYNTHETIC - NOT FOR GENUINE FORECASTING" in archive.read("README.txt")
    batch, questions = producer.intake._batch(result["batch_id"])
    original_t0 = {s: q["information_cutoff"] for s, q in questions.items()}
    before = snapshot(producer.store.root)
    clock[0] += timedelta(minutes=10)
    replay = create(application)
    _, restored = producer.intake._batch(batch["batch_id"])
    assert replay == first
    assert {s: q["information_cutoff"] for s, q in restored.items()} == original_t0
    assert snapshot(producer.store.root) == before


def test_changed_chart_requires_current_page_and_creates_only_affected_successor(tmp_path):
    application, producer, clock = fixture(tmp_path.resolve())
    old_state = application.input_state_sha256()
    first = application.create_question_pack(old_state)["result"]
    clock[0] += timedelta(minutes=5)
    producer.workflow.intake_chart(subject="COPPER", label="SYNTHETIC replacement COPPER",
        media_type="image/png", information_cutoff=clock[0].isoformat(), payload=chart())
    with pytest.raises(ThetaError, match="THETA_SPONSOR_INPUT_STATE_STALE"):
        application.create_question_pack(old_state)
    second = create(application)["result"]
    assert second["batch_id"] != first["batch_id"]
    assert second["questions"]["COPPER"] != first["questions"]["COPPER"]
    assert all(second["questions"][s] == first["questions"][s]
               for s in set(SUBJECTS) - {"COPPER"})


def test_complete_import_assesses_each_accepted_child_and_restart_is_read_only(tmp_path):
    application, producer, clock = fixture(tmp_path.resolve())
    create(application)
    _, raw = answer_for(producer, clock)
    batch_id = producer.selected()["batch_id"]
    result = application.import_astra_answers(batch_id)["result"]
    assert result["intake"]["package_status"] == "COMPLETE"
    assert all(row["status"] == "ACCEPTED" and row["receipt_id"]
               for row in result["intake"]["children"].values())
    assert all(a["E1"] == a["E2"] == "DOCUMENTED"
               for a in result["assessments"].values())
    for subject, child in result["intake"]["children"].items():
        assert producer.intake.accepted_evidence(child["receipt_id"])["package_raw"] == raw
        assert result["assessments"][subject]["assessment_id"].startswith("TAS-")
    before = snapshot(producer.store.root)
    fresh_workflow = ThetaWorkflow(ThetaStore(producer.store.root),
        inbox=producer.workflow.inbox, outbox=producer.workflow.outbox,
        clock=lambda: clock[0], qualification_mode=True)
    fresh_producer = V3QuestionProducer(fresh_workflow, authority_adapter(),
        published_methodology=ThetaMethodologyPublication())
    fresh = ThetaSponsorWorkflow(fresh_producer,
        ThetaAssessmentEngine(fresh_producer.intake, publication()))
    status = fresh.restore_status()
    assert status["import_operation"]["result"] == result
    assert status["selected_question_pack"]["batch_id"] == batch_id
    assert snapshot(producer.store.root) == before


def test_partial_four_of_five_never_substitutes_and_only_four_are_assessed(tmp_path):
    application, producer, clock = fixture(tmp_path.resolve())
    create(application)
    answer_for(producer, clock, invalid_subject="COPPER")
    result = application.import_astra_answers(producer.selected()["batch_id"])["result"]
    assert result["intake"]["package_status"] == "PARTIAL"
    assert result["intake"]["children"]["COPPER"]["status"] == "REJECTED"
    assert result["intake"]["children"]["COPPER"]["receipt_id"] is None
    assert result["assessments"]["COPPER"] is None
    assert sum(a is not None for a in result["assessments"].values()) == 4
    assert all(result["intake"]["children"][s]["status"] == "ACCEPTED"
               for s in set(SUBJECTS) - {"COPPER"})


def test_assessment_failure_does_not_rollback_answer_acceptance(tmp_path, monkeypatch):
    application, producer, clock = fixture(tmp_path.resolve())
    create(application); answer_for(producer, clock)
    def injected(_answer_id):
        raise OSError("synthetic assessment failure")
    monkeypatch.setattr(application.assessment, "assess_accepted_theta_answer", injected)
    result = application.import_astra_answers(producer.selected()["batch_id"])["result"]
    assert result["intake"]["package_status"] == "COMPLETE"
    assert all(row["receipt_id"] for row in result["intake"]["children"].values())
    assert all(a["E1"] == a["E2"] == "NOT_EVALUABLE"
               and a["reason"] == "THETA_ASSESSMENT_OPERATION_UNAVAILABLE"
               for a in result["assessments"].values())


def test_exact_import_replay_and_changed_bytes_conflict_preserve_first_acceptance(tmp_path):
    application, producer, clock = fixture(tmp_path.resolve())
    create(application)
    answer, original = answer_for(producer, clock)
    batch_id = producer.selected()["batch_id"]
    first = application.import_astra_answers(batch_id)["result"]
    receipts = {s: row["receipt_id"] for s, row in first["intake"]["children"].items()}
    replay = application.import_astra_answers(batch_id)["result"]
    assert replay["intake"]["package_status"] == "REPLAY"
    assert all(row["status"] == "REPLAY" for row in replay["intake"]["children"].values())
    assert all(a["disposition"] == "REPLAY" for a in replay["assessments"].values())

    # Same immutable package identity, different bytes: TE-04B fails closed.
    answer["answers"]["GOLDM"]["forecasts"]["E1"]["rationale"]["text"] += " changed"
    changed = json.dumps(answer, ensure_ascii=False, indent=2).encode() + b"\n"
    (producer.workflow.inbox / (batch_id + "_ANSWERS.json")).write_bytes(changed)
    conflict = application.import_astra_answers(batch_id)["result"]
    assert conflict["intake"]["package_status"] == "REJECTED"
    assert all(a is None for a in conflict["assessments"].values())
    for subject, receipt_id in receipts.items():
        assert producer.intake.accepted_evidence(receipt_id)["package_raw"] == original


def test_invalid_wrapper_replay_conflict_stale_and_gate_are_bounded(tmp_path, monkeypatch):
    application, producer, clock = fixture(tmp_path.resolve())
    create(application)
    batch_id = producer.selected()["batch_id"]
    producer.workflow.inbox.mkdir(parents=True, exist_ok=True)
    path = producer.workflow.inbox / (batch_id + "_ANSWERS.json")
    path.write_bytes(b'{}')
    rejected = application.import_astra_answers(batch_id)["result"]
    assert rejected["intake"]["package_status"] == "REJECTED"
    assert all(a is None for a in rejected["assessments"].values())

    # A changed chart makes this exact selected batch stale before any intake.
    clock[0] += timedelta(minutes=1)
    producer.workflow.intake_chart(subject="GOLDM", label="SYNTHETIC stale test",
        media_type="image/png", information_cutoff=clock[0].isoformat(), payload=chart())
    with pytest.raises(ThetaError, match="THETA_SPONSOR_BATCH_STALE"):
        application.import_astra_answers(batch_id)

    # The narrow in-process gate rejects an overlapping second button action.
    started, release = Event(), Event()
    real = producer.create
    def held():
        started.set(); release.wait(timeout=5); return real()
    monkeypatch.setattr(producer, "create", held)
    outcome = []
    thread = Thread(target=lambda: outcome.append(create(application)))
    thread.start(); assert started.wait(timeout=2)
    with pytest.raises(ThetaError, match="THETA_SPONSOR_OPERATION_BUSY"):
        create(application)
    release.set(); thread.join(timeout=5)
    assert not thread.is_alive() and outcome


def test_actual_http_two_buttons_full_round_trip_origin_and_download(tmp_path):
    application, producer, clock = fixture(tmp_path.resolve())
    with running(application) as server:
        status, _, body = request(server, "GET", "/theta-earners")
        assert status == 200 and b'aria-current="page" href="/theta-earners">OUTLOOK' in body
        status, _, body = request(server, "GET", "/theta-earners/new-analysis")
        text = body.decode()
        assert status == 200 and text.count('class="theta-workflow-primary"') == 2
        assert "CREATE THETA QUESTION PACK" in text and "IMPORT ASTRA ANSWERS" in text
        assert "Validate and import local Answer" not in text
        assert text.count('name="subject"') == 0
        token = application.input_state_sha256()
        status, headers, body = request(server, "POST", "/theta-earners/question",
                                  value={"input_state_sha256": token})
        assert status == 303 and headers["Location"] == "/theta-earners/new-analysis" and not body
        body = request(server, "GET", headers["Location"])[2]
        assert b"QUESTION PACK READY" in body
        selected = producer.selected()
        status, headers, binary = request(server, "GET", "/theta-earners/question-pack?" +
            urlencode({"question": selected["batch_id"], "kind": "zip"}))
        assert status == 200 and headers["Content-Type"] == "application/zip"
        assert digest(binary) == selected["zip_sha256"]
        answer_for(producer, clock)
        status, headers, body = request(server, "POST", "/theta-earners/import",
            value={"question_batch_id": selected["batch_id"]})
        assert status == 303 and headers["Location"] == "/theta-earners/new-analysis" and not body
        body = request(server, "GET", headers["Location"])[2]
        assert b"PACKAGE = COMPLETE" in body and body.count(b"DOCUMENTED") >= 10
        assert b"QUESTION PACKS: 5 / 5" in body and b"ANSWERS ACCEPTED: 5 / 5" in body
        assert request(server, "POST", "/theta-earners/import",
            value={"question_batch_id": selected["batch_id"]},
            origin="http://foreign.invalid")[0] == 403
        # Refresh is projection-only and restores the retained operation.
        assert b"PACKAGE = COMPLETE" in request(server, "GET", "/theta-earners/new-analysis")[2]
