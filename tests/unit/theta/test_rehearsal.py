"""Disposable HTTP/startup rehearsal; synthetic mechanics, not commissioning."""

import base64
from contextlib import contextmanager
from http.client import HTTPConnection
from io import BytesIO
import json
import os
import re
from threading import Thread
from urllib.parse import urlencode
from zipfile import ZipFile

import pytest

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.browser.product_routes import default_product_browser_routes
from kronos.browser.server import create_browser_server
from kronos.theta.contracts import SUBJECTS, digest
from kronos.theta.store import ThetaStore
from kronos.theta.workflow import ThetaWorkflow
from tests.unit.theta.test_workflow import NOW, authority, chart, place, valid_answer, workflow


@contextmanager
def running(workflow):
    provider_calls = []

    def forbidden_provider():
        provider_calls.append("FORBIDDEN")
        raise AssertionError("Synthetic rehearsal must never construct a Provider")

    application = SwingOpportunitiesApplication(forbidden_provider)
    server = create_browser_server(application, port=0,
        product_routes=default_product_browser_routes(theta_workflow=workflow))
    server._theta_legacy_test_workflow = workflow
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert server._domain_closed
        assert not provider_calls


def request(server, method, path, *, value=None, origin=None):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    address = f"127.0.0.1:{server.server_port}"
    headers = {"Host": address}
    body = None
    if method == "POST":
        headers["Origin"] = origin or "http://" + address
        if path.endswith("/chart"):
            headers["Content-Type"] = "application/json"
            body = json.dumps(value).encode()
        else:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            body = urlencode(value, doseq=True).encode()
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def question(server):
    # Explicit retained-V1 fixture: TE-02's real Sponsor POST is qualified in
    # test_question_packs.py. Historical V1 HTTP admission/restoration stays here.
    identity = server._theta_legacy_test_workflow.create_question(SUBJECTS)
    status, headers, binary = request(server, "GET", "/theta-earners/question-pack?" +
                                     urlencode({"question": identity, "kind": "zip"}))
    assert status == 200 and headers["Content-Type"] == "application/zip"
    with ZipFile(BytesIO(binary)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert all(digest(archive.read(name)) == checksum for name, checksum in manifest.items())
        retained = json.loads(archive.read("question.json"))
        assert retained["question_id"] == identity
        assert retained["subjects"] == list(SUBJECTS)
        assert len(retained["targets"]) == 10
        assert len(retained["charts"]) == 5
        assert len(json.loads(archive.read("answer-template.json"))["forecasts"]) == 10
    return identity


def intake(server, identity):
    return request(server, "POST", "/theta-earners/import", value={"question": identity})


def test_http_five_subject_round_trip_clean_restart_and_immutable_replay(tmp_path):
    root = tmp_path.resolve()
    workflow = ThetaWorkflow(ThetaStore(root / "theta"), inbox=root / "manual-inbox",
        outbox=root / "question-outbox", authority_provider=authority, clock=lambda: NOW)
    with running(workflow) as server:
        assert "NO CURRENT THETA ANALYSIS AVAILABLE" in request(server, "GET", "/theta-earners")[2].decode()
        for subject in SUBJECTS:
            value = {"subject": subject, "label": "SYNTHETIC " + subject,
                "media_type": "image/png", "information_cutoff": NOW.isoformat(),
                "chart_base64": base64.b64encode(chart()).decode()}
            status, _, body = request(server, "POST", "/theta-earners/chart", value=value)
            assert status == 200 and json.loads(body)["chart_id"].startswith("TEC-")
        identity = question(server)
        answer = valid_answer(workflow, identity)  # Simulated external return, explicitly synthetic.
        raw = place(workflow, identity, answer)  # Sponsor's designated local-path handoff.
        assert intake(server, identity)[0] == 200
        assert intake(server, identity)[0] == 200
        assert request(server, "GET", "/theta-earners")[2].count(b"Confidence: 78.00%") == 10
        for subject in SUBJECTS:
            status, _, body = request(server, "GET", "/theta-earners/detail?" +
                                     urlencode({"question": identity, "subject": subject}))
            assert status == 200 and digest(raw).encode() in body
            assert b"SELECTED PROSPECTIVE EVIDENCE" in body
            assert body.count(b"Confidence: 78.00%") == 2
        for path in ("/intraday", "/swing/opportunities"):
            status, _, body = request(server, "GET", path)
            assert status == 200 and b"Confidence: 78.00%" not in body
        assert request(server, "POST", "/theta-earners/import", value={"question": identity},
                       origin="http://malicious.invalid")[0] == 403

    original_receipt = (workflow.store.root / "accepted" / (identity + ".json")).read_bytes()
    original_pointer = (workflow.store.root / "current.json").read_bytes()
    # A newer orphan/prepared artifact and changed mtimes must not acquire authority.
    orphan = workflow.store.root / "questions" / ("TEQ-" + "0" * 64 + ".json")
    orphan.write_bytes(b'{"SYNTHETIC_PREPARED_NOT_ACCEPTED":true}')
    os.utime(orphan, (2_000_000_000, 2_000_000_000))
    os.utime(workflow.store.root / "questions" / (identity + ".json"), (1, 1))
    restored = ThetaWorkflow(ThetaStore(workflow.store.root), inbox=workflow.inbox,
        outbox=workflow.outbox, clock=lambda: NOW)  # No retained in-memory owner/Answer state.
    with running(restored) as server:
        assert request(server, "GET", "/theta-earners")[2].count(b"Confidence: 78.00%") == 10
        assert request(server, "GET", "/theta-earners/answer?" +
                       urlencode({"question": identity}))[2] == raw
        assert intake(server, identity)[0] == 200
        answer["forecasts"][0]["confidence_pct"] = "79.00"
        place(restored, identity, answer)
        assert intake(server, identity)[0] == 409
        assert request(server, "GET", "/theta-earners/answer?" +
                       urlencode({"question": identity}))[2] == raw
        assert request(server, "GET", "/theta-earners/detail?" +
                       urlencode({"question": identity, "subject": "COPPER"}))[0] == 200
    assert (restored.store.root / "accepted" / (identity + ".json")).read_bytes() == original_receipt
    assert (restored.store.root / "current.json").read_bytes() == original_pointer


@pytest.mark.parametrize("case", ["malformed", "incomplete", "wrong_subject", "wrong_question", "e1_e2_conflict"])
def test_http_invalid_return_never_becomes_current(workflow, case):
    with running(workflow) as server:
        identity = question(server)
        answer = valid_answer(workflow, identity)
        if case == "incomplete":
            answer["forecasts"].pop()
        elif case == "wrong_subject":
            answer["forecasts"][0]["target"]["subject"] = "COPPER"
        elif case == "wrong_question":
            answer["question_id"] = "TEQ-" + "0" * 64
        elif case == "e1_e2_conflict":
            answer["forecasts"][0]["target"]["horizon"] = "E2"
        raw = place(workflow, identity, answer)
        if case == "malformed":
            raw = b'{"SYNTHETIC_MALFORMED":'
            (workflow.inbox / (identity + "_ANSWERS.json")).write_bytes(raw)
        assert intake(server, identity)[0] == 409
        assert b"Confidence: 78.00%" not in request(server, "GET", "/theta-earners")[2]
        assert not (workflow.store.root / "accepted" / (identity + ".json")).exists()
        assert (workflow.inbox / (identity + "_ANSWERS.json")).read_bytes() == raw


@pytest.mark.parametrize("family", ["blob", "question", "receipt", "pointer"])
@pytest.mark.parametrize("damage", ["corrupt", "missing"])
def test_http_restart_damaged_selected_evidence_fails_closed(workflow, family, damage):
    with running(workflow) as server:
        identity = question(server)
        raw = place(workflow, identity, valid_answer(workflow, identity))
        assert intake(server, identity)[0] == 200
    targets = {"blob": workflow.store.root / "blobs" / digest(raw),
        "question": workflow.store.root / "questions" / (identity + ".json"),
        "receipt": workflow.store.root / "accepted" / (identity + ".json"),
        "pointer": workflow.store.root / "current.json"}
    if damage == "missing":
        targets[family].unlink()  # Only this disposable synthetic test root.
    else:
        targets[family].write_bytes(b'{"SYNTHETIC_CORRUPTION":true}')
    restored = ThetaWorkflow(ThetaStore(workflow.store.root), inbox=workflow.inbox,
        outbox=workflow.outbox, clock=lambda: NOW)
    with running(restored) as server:
        assert b"Confidence: 78.00%" not in request(server, "GET", "/theta-earners")[2]
        assert request(server, "GET", "/theta-earners/detail?" +
                       urlencode({"question": identity, "subject": "COPPER"}))[0] == 409


def test_default_composition_keeps_uncommissioned_owner_unavailable(tmp_path):
    workflow = ThetaWorkflow(ThetaStore(tmp_path.resolve() / "theta"),
        inbox=tmp_path.resolve() / "answers", outbox=tmp_path.resolve() / "questions", clock=lambda: NOW)
    for subject in SUBJECTS:
        workflow.intake_chart(subject=subject, label="SYNTHETIC " + subject, media_type="image/png",
            information_cutoff=NOW.isoformat(), payload=chart())
    with running(workflow) as server:
        assert request(server, "POST", "/theta-earners/question", value={"subject": list(SUBJECTS)})[0] == 409
        assert b"NO CURRENT THETA ANALYSIS AVAILABLE" in request(server, "GET", "/theta-earners")[2]
        assert b"target and methodology checks remain required" in request(server, "GET", "/theta-earners/new-analysis")[2]
        assert not (workflow.store.root / "questions").exists()
