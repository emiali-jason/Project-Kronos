"""TE-06B exact, inert retained V3 Outlook projection; synthetic evidence only."""

from copy import deepcopy
from datetime import timedelta
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from kronos.browser.product_routes import BrowserGetRequest
from kronos.browser.theta_routes import ThetaBrowserRoutes
from kronos.browser.theta_theme import OUTLOOK_STYLES
from kronos.theta.assessment import ThetaAssessmentEngine
from kronos.theta.contracts import SUBJECTS
from kronos.theta.orchestration import ThetaSponsorWorkflow
from kronos.theta.producer_v3 import V3QuestionProducer
from kronos.theta.store import ThetaStore, sealed
from kronos.theta.workflow import ThetaWorkflow
from tests.unit.theta.test_assessment import limited_c3
from tests.unit.theta.test_combined_intake import snapshot
from tests.unit.theta.test_methodology_publication import publication
from tests.unit.theta.test_rehearsal import request
from tests.unit.theta.test_sponsor_workflow import fixture, create, answer_for, running
from tests.unit.theta.test_workflow import chart
from tests.unit.theta.test_view_separation import Elements


def page(app, path="/theta-earners", query=None):
    from tests.unit.theta.test_browser import snapshot as shell
    return ThetaBrowserRoutes(app.workflow, sponsor_workflow=app).handle_get(
        BrowserGetRequest(path, query or {}), shell)


def accepted(root, *, partial=False):
    app, producer, clock = fixture(root)
    create(app)
    answer, raw = answer_for(producer, clock, invalid_subject="COPPER" if partial else None)
    operation = app.import_astra_answers(producer.selected()["batch_id"])
    return app, producer, clock, answer, raw, operation


def mixed_assessments(app, operation):
    """Explicit retained synthetic record fixtures; no production policy change."""
    identity = operation["result"]["assessments"]["SILVERM"]["assessment_id"]
    record = deepcopy(app.assessment.restore_assessment(identity)["assessment"])
    record["horizons"]["E2"]["result"] = "LIMITED"
    record["horizons"]["E2"]["criteria"][2]["result"] = "LIMITED"
    record["horizons"]["E2"]["criteria"][2]["reason_code"] = "THETA_ASSESSMENT_SYNTHETIC_DOCUMENTARY_LIMITATION"
    # Only a disposable synthetic test store; retained historical evidence is
    # never patched by the application. Fixtures isolate projection from evaluation.
    (app.store.root / "v3-assessments" / (identity + ".json")).write_bytes(sealed(record))
    identity = operation["result"]["assessments"]["NATURALGAS"]["assessment_id"]
    record = deepcopy(app.assessment.restore_assessment(identity)["assessment"])
    record["horizons"]["E2"]["result"] = "NOT_EVALUABLE"
    for criterion in record["horizons"]["E2"]["criteria"]:
        criterion["result"] = "NOT_EVALUABLE"
        criterion["reason_code"] = "THETA_ASSESSMENT_SYNTHETIC_HORIZON_UNAVAILABLE"
    (app.store.root / "v3-assessments" / (identity + ".json")).write_bytes(sealed(record))


def test_empty_outlook_has_exact_five_subjects_and_separate_default_navigation(tmp_path):
    app, _, _ = fixture(tmp_path.resolve())
    before = snapshot(app.store.root)
    body = page(app).body
    assert body.count('data-theta-subject=') == 5
    assert 'NO CURRENT THETA ANALYSIS AVAILABLE' in body
    assert 'href="/theta-earners/new-analysis">START NEW ANALYSIS' in body
    assert 'aria-current="page" href="/theta-earners">OUTLOOK' in body
    assert 'theta-workflow-primary' not in body and 'data-upload-url=' not in body
    assert 'Confidence:' not in body and 'SYNTHETIC — NOT FOR GENUINE FORECASTING' in body
    assert snapshot(app.store.root) == before


def test_exact_all_five_values_assessment_and_detail_navigation(tmp_path, monkeypatch):
    app, _, _, answers, _, operation = accepted(tmp_path.resolve())
    mixed_assessments(app, operation)
    def forbidden(*args, **kwargs):
        raise AssertionError("Outlook must not evaluate or import")
    monkeypatch.setattr(app.assessment, "assess_accepted_theta_answer", forbidden)
    monkeypatch.setattr(app.intake, "import_combined_astra_answer", forbidden)
    before = snapshot(app.store.root)
    rows, body = app.outlook(), page(app).body
    assert body.count('data-theta-subject=') == 5
    assert 'ASTRA FORECAST' in body and 'KRONOS DOCUMENTARY ASSESSMENT' in body
    assert 'no-touch probability' in body and 'OTM probability' in body
    for row in rows:
        s, evidence = row["subject"], row["evidence"]
        assert row["currentness"] == "CURRENT"
        assert evidence["answer"] == answers["answers"][s]
        for h in ("E1", "E2"):
            forecast = evidence["answer"]["forecasts"][h]
            target = evidence["question"]["targets"][h]
            assert f'{forecast["lower"]} – {forecast["upper"]}</strong>' in body
            assert f'Confidence: {forecast["confidence_pct"]}%' in body
            assert f'datetime="{target["option_expiry"]}"' in body
            assert forecast["target"] == target
        location = '/theta-earners/detail?' + urlencode({"question": evidence["question"]["question_id"], "subject": s})
        url = urlsplit(location)
        detail = page(app, url.path, parse_qs(url.query))
        assert detail.status == 200 and '← BACK TO OUTLOOK' in detail.body
        assert '/theta-earners/detail-chart?' in detail.body
        for role, binding in (("COMMODITY", "commodity_chart"), ("GLOBAL_MACRO", "macro_chart")):
            original_chart = page(app, '/theta-earners/detail-chart', {
                "question": [evidence["question"]["question_id"]], "subject": [s], "role": [role]})
            assert original_chart.body == app.store.load_blob(evidence["question"]["binding"][binding]["sha256"])
        original = page(app, '/theta-earners/answer', {"question": [evidence["question"]["question_id"]]})
        assert original.body == evidence["raw"]
    assert rows[1]["assessment"]["horizons"]["E1"]["result"] == "DOCUMENTED"
    assert rows[1]["assessment"]["horizons"]["E2"]["result"] == "LIMITED"
    assert rows[4]["assessment"]["horizons"]["E2"]["result"] == "NOT_EVALUABLE"
    assert snapshot(app.store.root) == before


def test_five_row_refinement_exact_badges_analysis_times_and_detail_links(tmp_path, monkeypatch):
    app, _, _, _, _, operation = accepted(tmp_path.resolve())
    mixed_assessments(app, operation)
    def forbidden(*args, **kwargs):
        raise AssertionError("Presentation must not import or assess")
    monkeypatch.setattr(app.assessment, "assess_accepted_theta_answer", forbidden)
    monkeypatch.setattr(app.intake, "import_combined_astra_answer", forbidden)
    before = snapshot(app.store.root)
    rows, body = app.outlook(), page(app).body
    elements = Elements(body).elements
    badges = [a for tag, a in elements if a.get("class") == "theta-assessment-badge"]
    assert len(badges) == 10
    assert [a["data-state"] for a in badges] == [
        row["assessment"]["horizons"][h]["result"] for row in rows for h in ("E1", "E2")]
    assert all(a["aria-label"] == "KRONOS documentary assessment: " + a["data-state"] for a in badges)
    assert [a["data-theta-subject"] for _, a in elements if "data-theta-subject" in a] == list(SUBJECTS)
    assert body.count("View Details →</a>") == 5
    assert body.count("Confidence is Astra’s stated terminal-range-containment confidence.") == 1
    assert body.count("DOCUMENTED / LIMITED / NOT_EVALUABLE describe") == 1
    for row in rows:
        q = row["evidence"]["question"]
        subject = row["subject"]
        anchors = [a for tag, a in elements if tag == "a" and a.get("class") in {"theta-subject", "theta-view-details"}
                   and (a.get("aria-label") == "View Details for " + subject or a["href"].endswith("subject=" + subject))]
        assert len(anchors) == 2 and anchors[0]["href"] == anchors[1]["href"]
        address = urlsplit(anchors[0]["href"])
        assert parse_qs(address.query) == {"question": [q["question_id"]], "subject": [subject]}
        assert f'datetime="{row["evidence"]["answer"]["analyzed_at"]}"' in body
        assert row["currentness"] == "CURRENT"
    assert snapshot(app.store.root) == before


def test_refinement_styles_are_v3_outlook_only(tmp_path):
    app, producer, _, _, _, _ = accepted(tmp_path.resolve())
    before = snapshot(app.store.root)
    assert OUTLOOK_STYLES in page(app).body
    assert OUTLOOK_STYLES not in page(app, "/theta-earners/new-analysis").body
    for subject, question in producer.store.current()["v3_questions"].items():
        detail = page(app, "/theta-earners/detail", {"question": [question], "subject": [subject]})
        assert detail.status == 200 and OUTLOOK_STYLES not in detail.body
        assert "theta-view-details" not in detail.body
    from tests.unit.theta.test_browser import snapshot as shell
    legacy = ThetaBrowserRoutes(app.workflow).handle_get(BrowserGetRequest("/theta-earners", {}), shell)
    assert OUTLOOK_STYLES not in legacy.body
    assert "font-size:clamp(16px,1.35vw,19px)" in OUTLOOK_STYLES
    assert "padding:9px 12px" in OUTLOOK_STYLES
    assert "@media(min-width:761px){.theta-outlook .theta-summary tr:has([data-theta-horizon]){height:112px}}" in OUTLOOK_STYLES
    assert snapshot(app.store.root) == before


def test_partial_and_corrupt_assessment_preserve_forecasts_without_historical_substitution(tmp_path):
    app, _, _, _, _, operation = accepted(tmp_path.resolve(), partial=True)
    identity = operation["result"]["assessments"]["GOLDM"]["assessment_id"]
    (app.store.root / "v3-assessments" / (identity + ".json")).write_bytes(b"corrupt synthetic fixture")
    before = snapshot(app.store.root)
    rows, body = app.outlook(), page(app).body
    assert len([r for r in rows if r["evidence"]]) == 4
    assert rows[2]["evidence"] is None and rows[2]["reason"] == operation["result"]["intake"]["children"]["COPPER"]["reason"]
    assert rows[0]["evidence"] is not None and rows[0]["assessment"] is None
    assert 'Retained assessment unavailable' in body and body.count('Confidence:') == 8
    assert 'CURRENT FORECAST UNAVAILABLE' in body and 'subject=COPPER' not in body
    assert snapshot(app.store.root) == before


@pytest.mark.parametrize("change", ["chart", "macro", "expiry", "owner"])
def test_currentness_comes_from_te04b_and_never_uses_operation_snapshot(tmp_path, change):
    app, producer, clock, _, _, _ = accepted(tmp_path.resolve())
    if change in {"chart", "macro"}:
        role = "COPPER" if change == "chart" else "GLOBAL_MACRO"
        app.workflow.intake_chart(subject=role, label="SYNTHETIC replacement",
            media_type="image/png", information_cutoff=clock[0].isoformat(), payload=chart())
    elif change == "expiry":
        clock[0] += timedelta(days=100)
    else:
        producer.intake.current_authorities = lambda *_: None
    before = snapshot(app.store.root)
    rows = app.outlook()
    assert all(r["currentness"] == "STALE" for r in rows if change != "chart" or r["subject"] == "COPPER")
    assert sum(r["evidence"] is not None for r in rows) == (4 if change == "chart" else 0)
    assert snapshot(app.store.root) == before


def test_successor_does_not_substitute_superseded_answer_and_history_stays_readable(tmp_path):
    app, producer, clock, _, _, _ = accepted(tmp_path.resolve())
    old = app.outlook()[2]["evidence"]
    app.workflow.intake_chart(subject="COPPER", label="SYNTHETIC successor",
        media_type="image/png", information_cutoff=clock[0].isoformat(), payload=chart())
    clock[0] += timedelta(minutes=1)
    create(app)
    before = snapshot(app.store.root)
    rows = app.outlook()
    assert sum(r["evidence"] is not None for r in rows) == 4
    assert rows[2]["evidence"] is None and rows[2]["reason"] == "NO_ACCEPTED_ANSWER"
    restored = app.retained_answer(old["question"]["question_id"], "COPPER")
    assert restored["currentness"] == "SUPERSEDED" and restored["raw"] == old["raw"]
    assert snapshot(app.store.root) == before


def test_restart_restores_exact_projection_without_new_assessment(tmp_path, monkeypatch):
    app, producer, clock, _, _, operation = accepted(tmp_path.resolve())
    mixed_assessments(app, operation)
    before, original = snapshot(app.store.root), page(app).body
    wf = ThetaWorkflow(ThetaStore(app.store.root), inbox=app.workflow.inbox,
        outbox=app.workflow.outbox, clock=lambda: clock[0], qualification_mode=True)
    p = V3QuestionProducer(wf, producer.target_authority, published_methodology=publication())
    restored = ThetaSponsorWorkflow(p, ThetaAssessmentEngine(p.intake, publication()))
    monkeypatch.setattr(restored.assessment, "assess_accepted_theta_answer",
        lambda *_: pytest.fail("GET must not reevaluate"))
    assert page(restored).body == original
    assert snapshot(app.store.root) == before


def test_chart_successor_during_projection_excludes_stale_snapshot(tmp_path, monkeypatch):
    app, _, clock, _, _, _ = accepted(tmp_path.resolve())
    restore = app.assessment.restore_assessment
    replaced = []
    def change_after_restore(identity):
        result = restore(identity)
        if not replaced:
            app.workflow.intake_chart(subject="GOLDM", label="SYNTHETIC concurrent replacement",
                media_type="image/png", information_cutoff=clock[0].isoformat(), payload=chart())
            replaced.append(True)
        return result
    monkeypatch.setattr(app.assessment, "restore_assessment", change_after_restore)
    rows = app.outlook()
    assert rows[0]["currentness"] == "STALE" and rows[0]["evidence"] is None
    assert sum(r["evidence"] is not None for r in rows) == 4


def test_actual_http_import_to_outlook_exact_projection_and_inert_get(tmp_path):
    app, producer, clock = fixture(tmp_path.resolve())
    with running(app) as server:
        assert b'NO CURRENT THETA ANALYSIS AVAILABLE' in request(server, 'GET', '/theta-earners')[2]
        assert request(server, 'POST', '/theta-earners/question',
            value={"input_state_sha256": app.input_state_sha256()})[0] == 303
        answer_for(producer, clock)
        assert request(server, 'POST', '/theta-earners/import',
            value={"question_batch_id": producer.selected()["batch_id"]})[0] == 303
        before = snapshot(app.store.root)
        status, _, body = request(server, 'GET', '/theta-earners')
        assert status == 200 and body.count('ACCEPTED · CURRENT'.encode()) == 5
        badges = [a for _, a in Elements(body.decode()).elements if a.get("class") == "theta-assessment-badge"]
        assert body.count(b'Confidence:') == 10 and len(badges) == 10
        assert all(a["data-state"] == "DOCUMENTED" for a in badges)
        new = request(server, 'GET', '/theta-earners/new-analysis')[2]
        assert new.count(b'class="theta-workflow-primary"') == 2 and new.count(b'data-upload-url=') == 6
        assert snapshot(app.store.root) == before
