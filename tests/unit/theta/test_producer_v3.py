"""TE-04C synthetic commissioning only. Kernel-isolated, no running runtime."""
from copy import deepcopy
from datetime import timedelta
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

from pypdf import PdfReader
import pytest

from kronos.theta.contracts import SUBJECTS, ThetaError, digest, encode
from kronos.theta.contracts_v3 import combined_answer_schema, combined_answer_template
from kronos.theta.producer_v3 import V3QuestionProducer, transport_v3, mandate_v3
from kronos.theta.schema_v3 import producer_instructions, RULES
from kronos.theta.store import ThetaStore
from kronos.theta.workflow import ThetaWorkflow
from tests.unit.theta.test_combined_intake import authority_adapter, snapshot
from tests.unit.theta.test_question_packs import composite, manifest_valid
from tests.unit.theta.test_workflow import chart
from tests.unit.theta.v3_fixture import synthetic_contracts, T0, RECEIPT


def fixture(root, *, readable=False):
    clock = [T0 - timedelta(minutes=10)]
    wf = ThetaWorkflow(ThetaStore(root / "evidence"), inbox=root / "CHATGPT ANSWERS",
        outbox=root / "KRONOS QUESTIONS", clock=lambda: clock[0], qualification_mode=True)
    for role in (*SUBJECTS, "GLOBAL_MACRO"):
        wf.intake_chart(subject=role, label="SYNTHETIC " + role,
            information_cutoff=clock[0].isoformat(), media_type="image/png",
            payload=composite(role) if readable else chart())
    clock[0] = T0
    q = synthetic_contracts()[0]["GOLDM"]
    method = {"descriptor": q["binding"]["methodology"], "instructions": q["methodology_instructions"]}
    return V3QuestionProducer(wf, authority_adapter(), synthetic_methodology=method), clock


@pytest.fixture
def producer(tmp_path):
    return fixture(tmp_path.resolve())


def generated(p):
    result = p.create()
    batch, qs = p.intake._batch(result["batch_id"])
    raw = (p.workflow.outbox / result["filename"]).read_bytes()
    return result, batch, qs, raw, manifest_valid(raw)


def completed(batch, questions):
    # Preserve the genuine producer's prefilled fields; only fill Analyst slots
    # from the already-qualified synthetic contract fixture.
    answer = combined_answer_template(batch, questions)
    fixture = synthetic_contracts()[2]
    answer["answer_package_id"] = "SYNTHETIC-TE04C-ANSWER-PACKAGE"
    for subject, child in answer["answers"].items():
        old = fixture["answers"][subject]
        for k in ("answer_id", "analyzed_at", "analyst", "research"):
            child[k] = deepcopy(old[k])
        child["research"]["chart_observations"][0]["chart_reference"] = deepcopy(child["binding"]["commodity_chart"])
        for h, f in child["forecasts"].items():
            f.update({k: deepcopy(v) for k, v in old["forecasts"][h].items() if k != "target"})
    return answer


def test_five_questions_exact_charts_targets_template_schema_and_zip(producer):
    p, _ = producer
    result, batch, qs, raw, files = generated(p)
    assert result["complete"] and len({q["question_id"] for q in qs.values()}) == 5
    assert len([n for n in files if n.startswith("shared/")]) == 1
    assert len([n for n in files if n.endswith("QUESTION.pdf")]) == 5
    assert len([n for n in files if "template" in n]) == 1
    assert json.loads(files["combined-answer-template.json"]) == combined_answer_template(batch, qs)
    assert json.loads(files["combined-answer.schema.json"]) == combined_answer_schema(batch, qs)
    assert files["producer-instructions.txt"].decode() == producer_instructions()
    charts, originals = {}, {}
    for subject, q in qs.items():
        assert q["schema_version"] == "3.0.0" and q["synthetic"]
        assert q["created_at"] == q["information_cutoff"] == T0.isoformat()
        actual = p.target_authority.v3_inputs(subject, T0)
        assert q["targets"] == actual["targets"]
        assert q["binding"]["target_authority"] == actual["target_authority"]
        assert q["binding"]["methodology"] == p.synthetic_methodology["descriptor"]
        assert json.loads(files[f"individual/{subject}/question.json"]) == q
        for key in ("commodity_chart", "macro_chart"):
            b = q["binding"][key]
            charts[b["subject"]] = p.store.chart(b["chart_id"])
            originals[b["sha256"]] = p.store.load_blob(b["sha256"])
            name = "shared/GLOBAL_MACRO.png" if key == "macro_chart" else f"individual/{subject}/charts/{subject}.png"
            assert files[name] == originals[b["sha256"]]
    assert transport_v3(batch, qs, charts, originals) == raw
    assert p.selected()["current"]
    assert "question_batch" not in p.store.current()  # Legacy Browser not enrolled.


def test_replay_restart_preserves_t0_and_bytes_without_read_side_effect(producer):
    p, clock = producer
    first, _, qs, raw, _ = generated(p)
    clock[0] += timedelta(minutes=30)
    before = snapshot(p.store.root)
    assert p.create() == first
    assert snapshot(p.store.root) == before
    fresh = V3QuestionProducer(ThetaWorkflow(ThetaStore(p.store.root), outbox=p.workflow.outbox,
        clock=lambda: clock[0], qualification_mode=True), authority_adapter(),
        synthetic_methodology=p.synthetic_methodology)
    assert fresh.selected() == p.selected()
    assert fresh.create() == first
    assert snapshot(p.store.root) == before
    assert (p.workflow.outbox / first["filename"]).read_bytes() == raw


@pytest.mark.parametrize("role", [*SUBJECTS, "GLOBAL_MACRO"])
def test_role_replacement_stales_only_bound_questions_and_new_t0(producer, role):
    p, clock = producer
    first, _, old, raw, _ = generated(p)
    clock[0] += timedelta(minutes=20)
    p.workflow.intake_chart(subject=role, label="SYNTHETIC replaced " + role,
        information_cutoff=clock[0].isoformat(), media_type="image/png", payload=chart())
    status = p.selected()
    affected = set(SUBJECTS) if role == "GLOBAL_MACRO" else {role}
    assert {s for s, v in status["currentness"].items() if v == "STALE"} == affected
    assert not status["current"]
    second, _, new, _, _ = generated(p)
    assert second["batch_id"] != first["batch_id"]
    for s in SUBJECTS:
        assert (new[s]["question_id"] != old[s]["question_id"]) == (s in affected)
        assert new[s]["information_cutoff"] == (clock[0] if s in affected else T0).isoformat()
    assert (p.workflow.outbox / first["filename"]).read_bytes() == raw


@pytest.mark.parametrize("field", ["descriptor", "instructions"])
def test_methodology_input_change_changes_identity_without_historical_rewrite(producer, field):
    p, clock = producer
    first = p.create()
    clock[0] += timedelta(minutes=5)
    if field == "descriptor":
        p.synthetic_methodology[field]["sha256"] = digest(b"SYNTHETIC replacement fixture")
        assert not p.selected()["current"]
    else:
        p.synthetic_methodology[field] += " Explicit synthetic successor."
    second = p.create()
    assert first["batch_id"] != second["batch_id"]
    assert all(first["questions"][s] != second["questions"][s] for s in SUBJECTS)


def test_changed_exact_target_never_reuses_old_question(producer, monkeypatch):
    p, clock = producer
    old = p.create()
    original = p.target_authority.v3_inputs
    def revised(subject, at):
        value = original(subject, at)
        # Explicit synthetic fault injection tests identity sensitivity only;
        # does NOT claim a new reviewed owner publication.
        value["targets"]["E1"]["authority_reference"] = "SYNTHETIC-CHANGED-REFERENCE"
        return value
    monkeypatch.setattr(p.target_authority, "v3_inputs", revised)
    assert not p.selected()["current"]
    clock[0] += timedelta(minutes=2)
    new = p.create()
    assert all(old["questions"][s] != new["questions"][s] for s in SUBJECTS)


@pytest.mark.parametrize("change", ["chart", "methodology", "target"])
def test_inputs_changed_during_render_cannot_publish_or_select(producer, monkeypatch, change):
    import kronos.theta.producer_v3 as module
    p, clock = producer
    real_render = module.transport_v3
    before = p.store.current()
    def render(*args):
        payload = real_render(*args)
        if change == "chart":
            clock[0] += timedelta(minutes=1)
            p.workflow.intake_chart(subject="GOLDM", label="SYNTHETIC raced chart",
                information_cutoff=clock[0].isoformat(), media_type="image/png", payload=chart())
        elif change == "methodology":
            p.synthetic_methodology["instructions"] += " Synthetic revised instructions."
        else:
            original = p.target_authority.v3_inputs
            def changed(s, at):
                v = original(s, at)
                v["targets"]["E1"]["authority_reference"] = "SYNTHETIC-CHANGED"
                return v
            monkeypatch.setattr(p.target_authority, "v3_inputs", changed)
        return payload
    monkeypatch.setattr(module, "transport_v3", render)
    with pytest.raises(ThetaError, match="THETA_INTAKE_BINDING_STALE"):
        p.create()
    assert not p.workflow.outbox.exists()
    assert "v3_question_batch" not in p.store.current()


def test_path_ancestor_symlink_fails_closed(producer, tmp_path):
    p, _ = producer
    other = tmp_path / "outside"
    other.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(other, target_is_directory=True)
    p.workflow.outbox = alias / "questions"
    with pytest.raises((ThetaError, OSError)):
        p.create()
    assert not list(other.iterdir()) and "v3_question_batch" not in p.store.current()


def test_expired_currentness_and_insufficient_owner_coverage_fail_closed(producer):
    p, clock = producer
    p.create()
    clock[0] += timedelta(days=30)
    assert not p.selected()["current"]
    with pytest.raises(ThetaError, match="THETA_TARGET_AUTHORITY_UNAVAILABLE"):
        p.create()


@pytest.mark.parametrize("mode,method", [(False, True), (False, False), (True, False)])
def test_methodology_hold_no_publication(producer, mode, method):
    p, _ = producer
    p.workflow.qualification_mode = mode
    if not method:
        p.synthetic_methodology = None
    before = snapshot(p.store.root)
    with pytest.raises(ThetaError, match="THETA_METHODOLOGY_UNAVAILABLE"):
        p.create()
    assert snapshot(p.store.root) == before and not p.workflow.outbox.exists()


@pytest.mark.parametrize("role", [*SUBJECTS, "GLOBAL_MACRO"])
def test_missing_mandatory_chart_fails_before_publication(producer, role):
    p, _ = producer
    selection = p.store.current()
    slot = selection["macro"] if role == "GLOBAL_MACRO" else selection["subjects"][role]
    slot.update(chart_id=None, revision_id=None)
    p.store.select(selection)
    with pytest.raises(ThetaError):
        p.create()
    assert not p.workflow.outbox.exists() and "v3_question_batch" not in p.store.current()


def test_unreviewed_target_authority_fails_closed(producer):
    from kronos.theta.target_authority import OwnerOptionAuthority, ThetaTargetAuthorityAdapter
    p, _ = producer
    p.target_authority = ThetaTargetAuthorityAdapter(OwnerOptionAuthority())
    with pytest.raises(ThetaError, match="THETA_TARGET_OWNER_QUALIFICATION_REQUIRED"):
        p.create()
    assert not p.workflow.outbox.exists()


@pytest.mark.parametrize("failure", ["foreign_bytes", "symlink", "render", "publication", "corrupt_original"])
def test_fail_closed_publication(producer, monkeypatch, tmp_path, failure):
    import kronos.theta.producer_v3 as module
    p, _ = producer
    if failure in {"foreign_bytes", "symlink"}:
        first = p.create()
        path = p.workflow.outbox / first["filename"]
        path.unlink()
        if failure == "foreign_bytes":
            path.write_bytes(b"unrelated retained bytes")
        else:
            target = tmp_path / "foreign"
            target.write_bytes(b"unrelated retained bytes")
            path.symlink_to(target)
    elif failure == "render":
        monkeypatch.setattr(module, "transport_v3", lambda *a: (_ for _ in ()).throw(ValueError("injected")))
    elif failure == "publication":
        monkeypatch.setattr(module, "write_at", lambda *a: (_ for _ in ()).throw(OSError("injected")))
    else:
        sha = p.workflow._role_chart(p.store.current(), "GOLDM")["chart"]["sha256"]
        (p.store.root / "blobs" / sha).write_bytes(b"corrupt")
    before = p.store.current()
    with pytest.raises((ValueError, OSError)):
        p.create()
    assert p.store.current() == before
    if failure == "foreign_bytes":
        assert path.read_bytes() == b"unrelated retained bytes"
    if failure == "symlink":
        assert target.read_bytes() == b"unrelated retained bytes"


@pytest.mark.parametrize("replace_one", [False, True])
def test_generated_questions_consumed_by_unchanged_te04b(producer, replace_one):
    p, clock = producer
    if replace_one:
        p.create()
        clock[0] += timedelta(minutes=10)
        p.workflow.intake_chart(subject="GOLDM", label="SYNTHETIC later replacement",
            information_cutoff=clock[0].isoformat(), media_type="image/png", payload=chart())
    _, batch, qs, _, _ = generated(p)
    assert len({q["information_cutoff"] for q in qs.values()}) == (2 if replace_one else 1)
    answer = completed(batch, qs)
    p.workflow.inbox.mkdir()
    raw = json.dumps(answer, indent=2, ensure_ascii=False).encode()
    (p.workflow.inbox / (batch["batch_id"] + "_ANSWERS.json")).write_bytes(raw)
    clock[0] = RECEIPT
    result = p.intake.import_combined_astra_answer(batch["batch_id"])
    assert result["package_status"] == "COMPLETE", result
    for s, child in result["children"].items():
        assert child["status"] == "ACCEPTED" and child["currentness"] == "CURRENT"
        e = p.intake.accepted_evidence(child["receipt_id"])
        assert e["package_raw"] == raw and e["receipt"]["binding"] == qs[s]["binding"]
    before = snapshot(p.store.root)
    assert p.intake.restore_import(result["attempt_id"]) == result
    assert snapshot(p.store.root) == before


def test_jpeg_original_is_preserved_exactly(producer):
    from PIL import Image
    p, clock = producer
    buffer = BytesIO()
    Image.open(BytesIO(chart())).convert("RGB").save(buffer, "JPEG")
    original = buffer.getvalue()
    p.workflow.intake_chart(subject="GOLDM", label="SYNTHETIC JPEG",
        information_cutoff=clock[0].isoformat(), media_type="image/jpeg", payload=original)
    _, _, qs, _, files = generated(p)
    assert files["individual/GOLDM/charts/GOLDM.jpg"] == original
    assert qs["GOLDM"]["binding"]["commodity_chart"]["sha256"] == digest(original)


def test_pdf_mandate_parity(producer):
    p, _ = producer
    _, batch, qs, _, files = generated(p)
    for s, q in qs.items():
        pdf = PdfReader(BytesIO(files[f"individual/{s}/THETA_{s}_QUESTION.pdf"]))
        text = " ".join(" ".join(page.extract_text().split()) for page in pdf.pages)
        for rule in RULES.values():
            assert " ".join(rule.split()).replace("–", "-") in text.replace("–", "-")
        for value in (s, "3.0.0", "Research depth", "NOT FOR GENUINE FORECASTING", "combined-answer.schema.json"):
            assert value in text
        for h in ("E1", "E2"):
            assert q["targets"][h]["price_unit"] in text
            assert q["targets"][h]["underlying_future"] in text
        assert "published_at alone may remain null" not in text
        assert "Return each Answer to its own canonical Question/template" not in text
        assert batch["batch_id"] + "_ANSWERS.json" in text.replace(" ", "")
        assert "/Users/" not in text and "/private/" not in text
    assert all((title, text) in mandate_v3() for title, text in __import__(
        "kronos.theta.question_pack", fromlist=["COMMON"]).COMMON if title not in {
            "Required response and exact machine template", "Cross-commodity consistency and analytical boundary"})


def test_representative_rehearsal_and_artifacts(tmp_path, request):
    value = request.config.getoption("--theta-v3-producer-output")
    root = tmp_path.resolve() if value is None else Path(value)
    assert root.is_absolute() and (value is None or root.name == "theta-te04c-qualification")
    if value is not None:
        # Re-render exact retained TE-02 evidence with the default renderer.
        # This explicit closure proof reads synthetic artifacts only; no migration.
        from kronos.theta.question_pack import render_question
        legacy_root = Path("output/pdf/theta-te02-synthetic-v2/theta-te01-qualification")
        historical = []
        for old_path in sorted(legacy_root.glob("*_QUESTION.zip")):
            with ZipFile(old_path) as old_zip:
                old_q = json.loads(old_zip.read("question.json"))
                images = {digest(old_zip.read(n)): old_zip.read(n) for n in old_zip.namelist() if n.startswith("charts/")}
                actual_pdf = render_question(old_q, images)
                assert actual_pdf == old_zip.read("questions.pdf")
                historical.append({"question_id": old_q["question_id"], "pdf_sha256": digest(actual_pdf)})
        assert len(historical) == 5
        root.mkdir(parents=True, exist_ok=False)
    p, clock = fixture(root, readable=True)
    result, batch, qs, raw, files = generated(p)
    p.workflow.inbox.mkdir()
    answer = completed(batch, qs)
    answer_raw = json.dumps(answer, indent=2, ensure_ascii=False).encode()
    (p.workflow.inbox / (batch["batch_id"] + "_ANSWERS.json")).write_bytes(answer_raw)
    clock[0] = RECEIPT
    accepted = p.intake.import_combined_astra_answer(batch["batch_id"])
    assert accepted["package_status"] == "COMPLETE", accepted
    fresh = V3QuestionProducer(ThetaWorkflow(ThetaStore(p.store.root), inbox=p.workflow.inbox,
        outbox=p.workflow.outbox, clock=lambda: clock[0], qualification_mode=True),
        authority_adapter(), synthetic_methodology=p.synthetic_methodology)
    assert fresh.intake.restore_import(accepted["attempt_id"]) == accepted
    if value is not None:
        for s in SUBJECTS:
            (root / f"SYNTHETIC_THETA_{s}_QUESTION.pdf").write_bytes(files[f"individual/{s}/THETA_{s}_QUESTION.pdf"])
        for name in ("combined-answer-template.json", "combined-answer.schema.json", "producer-instructions.txt"):
            (root / name).write_bytes(files[name])
        (root / "rehearsal-report.json").write_bytes(encode({"label": "SYNTHETIC - NOT FOR GENUINE FORECASTING",
            "producer": result, "intake": accepted, "restart_restoration": "PASS",
            "pdf_pages": {s: len(PdfReader(BytesIO(files[f"individual/{s}/THETA_{s}_QUESTION.pdf"])).pages) for s in SUBJECTS},
            "targets": {s: q["targets"] for s, q in qs.items()}, "historical_pdf_byte_equality": historical,
            "provider_calls": 0, "broker_operations": 0}))
