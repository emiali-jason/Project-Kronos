"""Synthetic rehearsal proves mechanics ONLY, never market usefulness/authority."""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw
from pypdf import PdfReader
import pytest

from kronos.theta.contracts import (
    AuthorityBundle, CANONICAL, ExpiryTarget, SUBJECTS, ThetaError, answer_template,
    digest, encode, parse, validate_answer,
)
from kronos.theta.store import ThetaStore, sealed
from kronos.theta.workflow import ThetaWorkflow

NOW = datetime(2026, 10, 11, 10, tzinfo=UTC)


def chart():
    image = Image.new("RGB", (1100, 520), "#102436")
    draw = ImageDraw.Draw(image)
    draw.text((35, 25), "SYNTHETIC ENGINEERING REHEARSAL - NOT MARKET EVIDENCE", fill="white")
    for x in range(80, 1020, 45):
        height = 230 + (x % 150)
        draw.line((x, height - 25, x, height + 35), fill="#8becb4", width=2)
        draw.rectangle((x - 9, height, x + 9, height + 20), fill="#8becb4")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def authority(subjects, now):
    return AuthorityBundle(tuple(ExpiryTarget(
        subject=s, canonical_subject=CANONICAL[s], horizon=h,
        option_expiry=date, expires_at=date + "T23:00:00+05:30",
        underlying_future="SYNTHETIC-MCX-" + s + "-" + future,
        futures_expiry=future, settlement_reference="SYNTHETIC_EXCHANGE_PRICE_ID_" + h,
        authority_reference="SYNTHETIC-OWNER-TEST-ONLY",
        exchange_evidence_reference="SYNTHETIC-EXCHANGE-TEST-ONLY")
        for s in subjects for h, date, future in (("E1", "2026-10-25", "2026-10-30"),
                                                 ("E2", "2026-11-25", "2026-11-30"))),
        "2026-10-01T00:00:00Z", "2026-12-01T00:00:00Z",
        "SYNTHETIC-METHODOLOGY-TEST-ONLY", "Synthetic fixture only. Describe visible structure. No analytical or operational authority.")


@pytest.fixture
def workflow(tmp_path):
    root = tmp_path.resolve()
    workflow = ThetaWorkflow(ThetaStore(root / "evidence"), inbox=root / "answers",
                             outbox=root / "questions", authority_provider=authority,
                             clock=lambda: NOW)
    for s in SUBJECTS:
        workflow.intake_chart(subject=s, label="SYNTHETIC " + s, media_type="image/png",
                              information_cutoff="2026-10-11T09:00:00Z", payload=chart())
    return workflow


def valid_answer(workflow, identity):
    question = workflow.store.question(identity)
    answer = answer_template(question)
    answer.update(answer_id="SYNTHETIC-ANSWER-" + identity[-12:],
                  analyzed_at=NOW.isoformat(), information_cutoff=NOW.isoformat(),
                  analyst={"identity": "SYNTHETIC Analyst", "model": "SYNTHETIC Astra",
                           "provenance": "Synthetic engineering rehearsal only"})
    for index, forecast in enumerate(answer["forecasts"]):
        forecast.update(lower=str(100 + index), upper=str(120 + index), confidence_pct="78.00")
        forecast["analysis"] = {k: {"classification": "HYPOTHESIS", "text": "Synthetic " + k + " <script>never execute</script>"}
                                for k in forecast["analysis"]}
        forecast["sources"] = [{"title": "Synthetic source", "url": "https://example.com/synthetic",
            "published_at": None, "accessed_at": NOW.isoformat(), "evidence": "Synthetic only"}]
    return answer


def place(workflow, identity, value):
    payload = json.dumps(value, indent=2, ensure_ascii=False).encode() + b"\n"
    (workflow.inbox / (identity + "_ANSWERS.json")).write_bytes(payload)
    return payload


def accepted(workflow, subjects=SUBJECTS):
    identity = workflow.create_question(subjects)
    answer = valid_answer(workflow, identity)
    raw = place(workflow, identity, answer)
    workflow.import_answer(identity)
    return identity, answer, raw


def test_five_by_two_lossless_restart_and_original_chart(workflow):
    identity, answer, raw = accepted(workflow)
    restart = ThetaWorkflow(ThetaStore(workflow.store.root), inbox=workflow.inbox,
                            outbox=workflow.outbox, clock=lambda: NOW)
    rows = restart.summary()
    assert len(rows) == 5 and sum(len(r["forecasts"]) for r in rows) == 10
    assert all(r["status"] == "ACCEPTED_EXTERNAL_EVIDENCE" for r in rows)
    detail = restart.detail(identity)
    assert detail["answer"] == answer
    assert detail["answer"]["forecasts"][0]["confidence_pct"] == "78.00"
    assert restart.chart_bytes(detail["receipt"]["answer_sha256"]) == raw
    assert restart.chart_bytes(detail["question"]["charts"][0]["sha256"]) == chart()
    assert all(f["target"]["underlying_future"].endswith("2026-11-30")
               for f in detail["answer"]["forecasts"] if f["target"]["horizon"] == "E2")


def test_missing_owner_never_generates_question_but_keeps_charts(workflow):
    workflow.authority_provider = None
    with pytest.raises(ThetaError, match="NOT_ESTABLISHED"):
        workflow.create_question(SUBJECTS)
    assert all(r["status"] == "TARGET_AND_METHODOLOGY_NOT_ESTABLISHED" for r in workflow.summary())
    assert not (workflow.store.root / "questions").exists()


def test_owner_resolution_failure_is_sanitized_unavailable(workflow):
    def failure(*_):
        raise RuntimeError("private owner exception detail")
    workflow.authority_provider = failure
    with pytest.raises(ThetaError, match="THETA_TARGET_AUTHORITY_UNAVAILABLE") as error:
        workflow.create_question(SUBJECTS)
    assert "private owner exception detail" not in str(error.value)
    assert not (workflow.store.root / "questions").exists()


@pytest.mark.parametrize("e1,e2,valid", [
    ("2026-11-25", "20261025", False),
    ("20261025", "2026-11-25", True),
])
def test_owner_expiry_order_uses_calendar_dates_not_text(e1, e2, valid):
    from dataclasses import replace
    from datetime import date
    bundle = authority(("GOLDM",), NOW)
    targets = tuple(replace(target, option_expiry=value,
        expires_at=date.fromisoformat(value).isoformat() + "T23:00:00+05:30",
        futures_expiry="2026-11-30")
        for target, value in zip(bundle.targets, (e1, e2), strict=True))
    bundle = replace(bundle, targets=targets)
    if valid:
        retained = bundle.for_subjects(("GOLDM",), NOW)
        assert retained[0]["option_expiry"] == e1  # No silent representation repair.
        assert retained[1]["option_expiry"] == e2
    else:
        with pytest.raises(ThetaError, match="TARGET_AUTHORITY_STALE"):
            bundle.for_subjects(("GOLDM",), NOW)


def test_partial_subject_pack_not_complete_five_subjects(workflow):
    identity, _, _ = accepted(workflow, ("COPPER",))
    rows = workflow.summary()
    assert sum(len(r["forecasts"]) for r in rows) == 2
    assert workflow.detail(identity)["question"]["subjects"] == ["COPPER"]
    assert rows[0]["status"] == "CHART_READY"


def test_pdf_zip_deterministic_and_exact_ten_targets(workflow, request):
    identity = workflow.create_question(SUBJECTS)
    assert any("published_at may remain null when unknown" in instruction
               for instruction in workflow.store.question(identity)["instructions"])
    pdf = workflow.transport(identity, "pdf")
    reader = PdfReader(BytesIO(pdf), strict=True)
    text = "\n".join(p.extract_text() for p in reader.pages)
    assert identity in text and "Confidence" in text
    assert all(s in text for s in SUBJECTS)
    assert sum(len(p.images) for p in reader.pages) == 5
    archive = workflow.transport(identity, "zip")
    with ZipFile(BytesIO(archive)) as z:
        manifest = json.loads(z.read("manifest.json"))
        assert all(digest(z.read(name)) == checksum for name, checksum in manifest.items())
        template = json.loads(z.read("answer-template.json"))
        assert len(template["forecasts"]) == 10
        assert z.read("questions.pdf") == pdf
        with pytest.raises(ThetaError):
            validate_answer(z.read("answer-template.json"), workflow.store.question(identity), received_at=NOW)
    assert workflow.create_question(SUBJECTS) == identity
    assert workflow.transport(identity, "zip") == archive
    from tests.unit.theta.conftest import qualification_output
    output = qualification_output(request)
    if output:
        (output / "synthetic-questions.pdf").write_bytes(pdf)
        (output / "synthetic-questions.zip").write_bytes(archive)


@pytest.mark.parametrize("mutation", [
    lambda a: a.update(question_id="TEQ-" + "0" * 64),
    lambda a: a.update(question_sha256="0" * 64),
    lambda a: a["forecasts"].pop(),
    lambda a: a["forecasts"][0]["target"].update(subject="COPPER"),
    lambda a: a["forecasts"][0]["target"].update(horizon="E2"),
    lambda a: a["forecasts"][0]["target"].update(settlement_reference="DUE_DATE_RATE"),
    lambda a: a["forecasts"][0]["target"].update(underlying_future="nearest-contract"),
    lambda a: a["forecasts"][0].update(lower="200", upper="100"),
    lambda a: a["forecasts"][0].update(lower=100.0),
    lambda a: a["forecasts"][0].update(lower=True),
    lambda a: a["forecasts"][0].update(lower="NaN"),
    lambda a: a["forecasts"][0].update(confidence_pct="100.01"),
    lambda a: a["forecasts"][0].update(confidence_pct="-0.01"),
    lambda a: a["forecasts"][0].update(chart_sha256="0" * 64),
    lambda a: a.update(analyzed_at="2026-10-11T10:00:00"),
    lambda a: a.update(analyzed_at="2026-10-12T10:00:00Z"),
    lambda a: a.update(information_cutoff="2026-10-10T00:00:00Z"),
    lambda a: a["forecasts"][0]["analysis"]["reasoning"].update(classification="OPERATIONAL_AUTHORITY"),
    lambda a: a["forecasts"][0]["sources"][0].update(url="javascript:alert(1)"),
    lambda a: a["forecasts"][0]["sources"][0].update(accessed_at="2026-10-12T00:00:00Z"),
    lambda a: a.update(extra="not permitted"),
])
def test_invalid_answer_never_published(workflow, mutation):
    identity = workflow.create_question(SUBJECTS)
    answer = valid_answer(workflow, identity)
    mutation(answer)
    raw = place(workflow, identity, answer)
    with pytest.raises(ThetaError):
        workflow.import_answer(identity)
    assert (workflow.inbox / (identity + "_ANSWERS.json")).read_bytes() == raw
    assert all(r["status"] == "ANSWER_PENDING" and not r["forecasts"] for r in workflow.summary())


@pytest.mark.parametrize("confidence", ["0", "100", "78.0000"])
def test_confidence_no_threshold_and_exact_string(workflow, confidence):
    identity = workflow.create_question(("GOLDM",))
    answer = valid_answer(workflow, identity)
    for f in answer["forecasts"]:
        f.update(confidence_pct=confidence, lower="-100.00", upper="0.00")
    place(workflow, identity, answer)
    workflow.import_answer(identity)
    assert workflow.summary()[0]["forecasts"][0]["confidence_pct"] == confidence


def test_idempotence_conflict_and_global_answer_identity(workflow):
    identity, answer, raw = accepted(workflow)
    assert workflow.import_answer(identity) == digest(raw)
    answer["forecasts"][0]["confidence_pct"] = "79"
    place(workflow, identity, answer)
    with pytest.raises(ThetaError, match="ANSWER_CONFLICT"):
        workflow.import_answer(identity)
    assert workflow.store.load_blob(digest(raw)) == raw


def test_new_chart_invalidates_current_without_rewriting_old(workflow):
    identity, _, raw = accepted(workflow)
    workflow.intake_chart(subject="GOLDM", label="New Sponsor chart declaration", media_type="image/png",
                          information_cutoff=NOW.isoformat(), payload=chart())
    rows = workflow.summary()
    assert not rows[0]["forecasts"] and len(rows[1]["forecasts"]) == 2
    assert "GOLDM" not in workflow.detail(identity)["current_subjects"]
    assert workflow.store.load_blob(digest(raw)) == raw
    assert workflow.import_answer(identity) == digest(raw)  # Historical no-op, never reselect.
    assert not workflow.summary()[0]["forecasts"]


def test_expired_not_current_no_e2_relabeling(workflow):
    identity, _, raw = accepted(workflow)
    workflow.clock = lambda: NOW + timedelta(days=20)
    assert all(r["status"] == "EXPIRED_HISTORICAL_ONLY" and not r["forecasts"] for r in workflow.summary())
    assert workflow.detail(identity)["current_subjects"] == []
    assert workflow.import_answer(identity) == digest(raw)
    assert not workflow.summary()[0]["forecasts"]


def test_pending_superseded_question_cannot_publish(workflow):
    identity = workflow.create_question(SUBJECTS)
    place(workflow, identity, valid_answer(workflow, identity))
    workflow.intake_chart(subject="GOLDM", label="New chart", media_type="image/png",
                          information_cutoff=NOW.isoformat(), payload=chart())
    with pytest.raises(ThetaError, match="SUPERSEDED"):
        workflow.import_answer(identity)


def test_stale_authority_not_current_and_duplicate_never_resurrects(workflow):
    from dataclasses import replace
    workflow.authority_provider = lambda subjects, now: replace(authority(subjects, now),
        valid_through=(NOW + timedelta(hours=1)).isoformat())
    identity, _, raw = accepted(workflow)
    workflow.clock = lambda: NOW + timedelta(hours=2)
    assert all(r["status"].startswith("TARGET_AUTHORITY_STALE") and not r["forecasts"] for r in workflow.summary())
    assert not workflow.detail(identity)["current_subjects"]
    assert workflow.import_answer(identity) == digest(raw)


def test_global_answer_identity_conflict_keeps_original(workflow):
    first, original, raw = accepted(workflow)
    workflow.intake_chart(subject="COPPER", label="New chart", media_type="image/png",
                          information_cutoff=NOW.isoformat(), payload=chart())
    second = workflow.create_question(("COPPER",))
    answer = valid_answer(workflow, second)
    answer["answer_id"] = original["answer_id"]
    place(workflow, second, answer)
    with pytest.raises(ThetaError, match="IMMUTABLE_CONFLICT"):
        workflow.import_answer(second)
    assert workflow.detail(first)["answer"] == original and workflow.store.load_blob(digest(raw)) == raw


def test_render_failure_never_selects_or_retains_question(workflow, monkeypatch):
    import kronos.theta.workflow as module
    monkeypatch.setattr(module, "render_transport", lambda *_: (_ for _ in ()).throw(RuntimeError("synthetic renderer failure")))
    with pytest.raises(ThetaError, match="RENDER_INVALID"):
        workflow.create_question(SUBJECTS)
    assert all(r.get("question_id") is None for r in workflow.summary())
    assert not (workflow.store.root / "questions").exists()


def test_hardlinked_answer_not_admitted(workflow, tmp_path):
    import os
    identity = workflow.create_question(("COPPER",))
    outside = tmp_path / "outside.json"
    outside.write_bytes(encode(valid_answer(workflow, identity)))
    os.link(outside, workflow.inbox / (identity + "_ANSWERS.json"))
    with pytest.raises(ThetaError, match="ARTIFACT_INVALID"):
        workflow.import_answer(identity)


def test_late_answer_no_retrospective_forecast(workflow):
    identity = workflow.create_question(SUBJECTS)
    place(workflow, identity, valid_answer(workflow, identity))
    workflow.clock = lambda: NOW + timedelta(days=20)
    with pytest.raises(ThetaError, match="EXPIRED"):
        workflow.import_answer(identity)


@pytest.mark.parametrize("family", ["blobs", "questions", "accepted", "current"])
def test_tampering_fails_closed_without_fallback(workflow, family):
    identity, _, raw = accepted(workflow)
    path = (workflow.store.root / "current.json" if family == "current" else
            workflow.store.root / family / (digest(raw) if family == "blobs" else identity + ".json"))
    path.write_bytes(b'{"corrupted":true}')
    with pytest.raises((ThetaError, KeyError)):
        workflow.summary()


def test_missing_accepted_blob_not_pending(workflow):
    _, _, raw = accepted(workflow)
    (workflow.store.root / "blobs" / digest(raw)).unlink()
    with pytest.raises(ThetaError, match="INTEGRITY"):
        workflow.summary()


def test_deleted_pointer_is_not_empty_new_workspace(workflow):
    accepted(workflow)
    (workflow.store.root / "current.json").unlink()
    with pytest.raises(ThetaError, match="INTEGRITY"):
        workflow.summary()


def test_concurrent_identical_imports_commit_once(workflow):
    from concurrent.futures import ThreadPoolExecutor
    identity = workflow.create_question(SUBJECTS)
    raw = place(workflow, identity, valid_answer(workflow, identity))
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: workflow.import_answer(identity), range(8)))
    assert set(results) == {digest(raw)}
    assert len(list((workflow.store.root / "accepted").iterdir())) == 1


def test_symlink_intake_rejected(workflow, tmp_path):
    identity = workflow.create_question(("COPPER",))
    outside = tmp_path / "outside.json"
    outside.write_bytes(encode(valid_answer(workflow, identity)))
    (workflow.inbox / (identity + "_ANSWERS.json")).symlink_to(outside)
    with pytest.raises(OSError):
        workflow.import_answer(identity)
    assert workflow.summary()[2]["status"] == "ANSWER_PENDING"


def test_symlink_store_component_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    unsafe = tmp_path / "unsafe"
    unsafe.symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        with ThetaStore(unsafe).transaction():
            pass


def test_duplicate_json_keys_no_silent_repair():
    with pytest.raises(ThetaError):
        parse(b'{"x":1,"x":2}')


def test_publication_failure_leaves_no_selected_question(workflow, monkeypatch):
    original = workflow.store.select
    monkeypatch.setattr(workflow.store, "select", lambda _: (_ for _ in ()).throw(OSError("fixture failure")))
    with pytest.raises(OSError):
        workflow.create_question(SUBJECTS)
    monkeypatch.setattr(workflow.store, "select", original)
    assert all(r.get("question_id") is None for r in workflow.summary())
    assert workflow.create_question(SUBJECTS)


def test_append_outcome_does_not_rewrite_forecast(workflow):
    identity, answer, raw = accepted(workflow)
    selection = (workflow.store.root / "current.json").read_bytes()
    workflow.clock = lambda: NOW + timedelta(days=20)
    target = answer["forecasts"][0]["target"]
    for terminal, expected in (("100", "PASS"), ("120", "PASS"), ("120.01", "FAIL")):
        outcome = workflow.append_outcome(identity, target=target, terminal=terminal,
            observed_at="2026-10-26T00:00:00Z", authority_reference="SYNTHETIC terminal evidence")
        assert expected in workflow.store.load("outcomes", outcome + ".json").decode()
    assert workflow.store.load_blob(digest(raw)) == raw
    assert (workflow.store.root / "current.json").read_bytes() == selection
