"""WO-07 controlled temporary-root publication and failure qualification."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from contextlib import contextmanager
import multiprocessing

import pytest
from reportlab.pdfgen.canvas import Canvas
from PIL import Image as PillowImage, ImageDraw
from pypdf import PdfReader

from kronos.swing.v1.review_evidence_binding import (
    NseReviewRequestMapping, ReviewAcceptanceReceipt, ReviewEvidenceError, canonical, nse_pre_render_digest,
)
from kronos.swing.v1.review_evidence_store import ReviewEvidenceStore
from swing.v1.test_review_evidence_binding import nse_mapping
from swing.v1.test_mcx_native_visual_contract import retained_mappings, answer_for
from kronos.swing.v1.mcx_native_visual_contract import mcx_question_pack_from_mappings
from kronos.swing.v1.pdf_visual_review_v3_live import render_mcx_successor_question_pdf, extract_successor_answer_pdf
from kronos.swing.v1.pdf_visual_review import BEGIN_GOVERNED_ANSWER_DATA, END_GOVERNED_ANSWER_DATA


def test_mcx_renderer_binds_both_logical_contracts_and_original_composites(tmp_path):
    native, reference = retained_mappings()
    mappings, charts = [], {}
    for mapping, label in ((native, "NATIVE MCX SYNTHETIC"), (reference, "SUPPORTING REFERENCE SYNTHETIC")):
        image = PillowImage.new("RGB", (900, 450), "white")
        draw = ImageDraw.Draw(image)
        draw.text((20, 20), label, fill="black")
        for index, tf in enumerate(("1D", "4H", "1H")):
            draw.rectangle((index * 300 + 10, 80, index * 300 + 290, 400), outline="blue", width=3)
            draw.text((index * 300 + 25, 100), tf + " - NO MARKET DATA", fill="black")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        content = buffer.getvalue()
        digest = sha256(content).hexdigest()
        charts[digest] = content
        value = mapping.value
        for response in value["subjects"][0]["responses"]:
            response["chart_revision_sha256"] = digest
        mappings.append(type(mapping).create(value))
    result = render_mcx_successor_question_pdf(*mappings, charts)
    n, r, pdf = result
    assert n.value["request_sha256"] == mappings[0].value["request_sha256"]
    assert r.value["request_sha256"] == mappings[1].value["request_sha256"]
    assert render_mcx_successor_question_pdf(*mappings, charts) == result
    path = tmp_path / "mcx-render.pdf"
    path.write_bytes(pdf)
    reader = PdfReader(BytesIO(pdf), strict=True)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    for mapping in (n, r):
        assert mapping.value["request_sha256"] in text
        assert mapping.value["request_identity"] in text
        assert mapping.value["question_contract_identity"] in text
    assert "PARTIAL_COMPONENT_IDENTITY requires UNIDENTIFIED_PLOTTED_STRUCTURE" in text.replace("\n", " ")
    assert sum(len(page.images) for page in reader.pages) == 2
    publication = publish_mcx(ReviewEvidenceStore(tmp_path / "store"), result)
    assert publication.native == n and publication.reference == r
    with pytest.raises(ReviewEvidenceError, match="REVIEW_ARTIFACT_DIGEST_MISMATCH"):
        render_mcx_successor_question_pdf(*mappings, {key: b"wrong" for key in charts})


def test_successor_pdf_extraction_preserves_duplicate_keys_for_rejection():
    def pdf_for(text):
        buffer = BytesIO()
        pdf = Canvas(buffer, invariant=1)
        for index, line in enumerate(text.splitlines()):
            pdf.drawString(20, 800 - 15 * index, line)
        pdf.save()
        return buffer.getvalue()
    body = BEGIN_GOVERNED_ANSWER_DATA + '\n{"schema":"A","schema":"B"}\n' + END_GOVERNED_ANSWER_DATA
    with pytest.raises(ReviewEvidenceError, match="REVIEW_DUPLICATE_KEY"):
        extract_successor_answer_pdf(pdf_for(body))
    valid = BEGIN_GOVERNED_ANSWER_DATA + '\n{"schema":"A"}\n' + END_GOVERNED_ANSWER_DATA
    assert extract_successor_answer_pdf(pdf_for(valid)) == b'{"schema":"A"}'
    with pytest.raises(ReviewEvidenceError, match="REVIEW_ACCEPTANCE_INCOMPLETE"):
        extract_successor_answer_pdf(pdf_for(valid + "\n" + valid))


def mcx_publication_fixture(bundle="MCX-BUNDLE-1", *, changed_native=False):
    native, reference = retained_mappings(bundle=bundle)
    if changed_native:
        changed = native.value
        changed["subjects"][0]["responses"][0]["chart_revision_sha256"] = "e" * 64
        native = type(native).create(changed)
    buffer = BytesIO()
    pdf = Canvas(buffer, invariant=1)
    pdf.setFont("Courier", 7)
    lines = ["SYNTHETIC CONTRACT FIXTURE — NO MARKET EVIDENCE"]
    for mapping in (native.value, reference.value):
        for key in ("question_contract_identity", "question_contract_version", "answer_contract_identity", "answer_contract_version",
                    "request_identity", "request_sha256", "review_pack_identity", "request_bundle_identity", "review_cycle_identity"):
            lines.append(mapping[key])
        for subject in mapping["subjects"]:
            lines.extend(subject[key] for key in ("subject_reference", "native_candidate_reference"))
            for response in subject["responses"]:
                lines.extend(response[key] for key in ("timeframe", "expected_chart_identity", "chart_revision_identity", "chart_revision_sha256"))
    for index, line in enumerate(lines):
        if index and index % 65 == 0:
            pdf.showPage()
            pdf.setFont("Courier", 7)
        pdf.drawString(20, 800 - (index % 65) * 11, line)
    pdf.save()
    payload = buffer.getvalue()
    return (*(type(mapping).create({**mapping.value, "review_pack_sha256": sha256(payload).hexdigest()})
              for mapping in (native, reference)), payload)


def publish_mcx(store, fixture=None, predecessor=None, **kwargs):
    return store.publish_mcx_request(*(fixture or mcx_publication_fixture()),
        publication_timestamp="2026-09-15T00:01:00.000000Z", expected_predecessor=predecessor,
        recheck=lambda n, r: None, **kwargs)


def test_mcx_pair_pdf_manifest_replay_and_answer_resolution_are_one_committed_graph(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    assert store.load_current_mcx_request() is None
    assert not store.root.exists()
    fixture = mcx_publication_fixture()
    publication = publish_mcx(store, fixture)
    native, reference, pdf = fixture
    assert publication.value["native_mapping_artifact_sha256"] == sha256(native.payload).hexdigest()
    assert publication.value["reference_mapping_artifact_sha256"] == sha256(reference.payload).hexdigest()
    assert publication.value["question_pdf_sha256"] == sha256(pdf).hexdigest()
    assert native.value["review_pack_sha256"] == reference.value["review_pack_sha256"] == sha256(pdf).hexdigest()
    before = inventory(tmp_path)
    for _ in range(3):
        assert ReviewEvidenceStore(tmp_path).load_current_mcx_request() == publication
    assert publish_mcx(store, fixture) == publication
    assert inventory(tmp_path) == before
    request = mcx_question_pack_from_mappings(native, reference)
    answer = answer_for(request)
    assert store.validate_mcx_answer_for_publication(canonical(answer), publication.identity) == answer
    # Neither independently valid foreign echo can resolve against this bundle.
    other_n, other_r, _ = mcx_publication_fixture("OTHER")
    answer["supporting_reference_answer"]["request_reference"] = mcx_question_pack_from_mappings(other_n, other_r).value["supporting_reference_pack"]["request_reference"]
    with pytest.raises(ReviewEvidenceError, match="MCX_REQUEST_MISMATCH"):
        store.validate_mcx_answer_for_publication(canonical(answer), publication.identity)
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("phase,visible", [
    ("before_retention", False), ("after_pdf_retention", False), ("after_native_mapping_retention", False),
    ("after_reference_mapping_retention", False), ("after_manifest_retention", False),
    ("before_pointer_replace", False), ("after_pointer_replace", True), ("before_acknowledgement", True)])
def test_mcx_atomic_partial_retention_never_exposes_half_bundle(tmp_path, phase, visible):
    store = ReviewEvidenceStore(tmp_path)
    old = publish_mcx(store)
    fixture = mcx_publication_fixture("MCX-BUNDLE-2")
    def fail(point):
        if phase == point:
            raise RuntimeError("isolated fault")
    with pytest.raises(RuntimeError, match="isolated fault"):
        publish_mcx(ReviewEvidenceStore(tmp_path, fault=fail), fixture, old.identity)
    restarted = ReviewEvidenceStore(tmp_path)
    before = inventory(tmp_path)
    result = restarted.load_current_mcx_request()
    assert result.native.value["request_bundle_identity"] == ("MCX-BUNDLE-2" if visible else "MCX-BUNDLE-1")
    assert result.reference.value["request_bundle_identity"] == result.native.value["request_bundle_identity"]
    assert inventory(tmp_path) == before
    assert restarted.recover_mcx_request() == result
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("field", ["native_mapping_relative_path", "reference_mapping_relative_path", "question_pdf_relative_path", "manifest"])
def test_mcx_tamper_fails_without_recovery_fallback_or_get_write(tmp_path, field):
    store = ReviewEvidenceStore(tmp_path)
    result = publish_mcx(store)
    path = store.root / ("request-publications/" + result.identity + ".json" if field == "manifest" else result.value[field])
    path.write_bytes(path.read_bytes() + b" ")
    before = inventory(tmp_path)
    with pytest.raises(ReviewEvidenceError):
        store.load_current_mcx_request()
    with pytest.raises(ReviewEvidenceError):
        store.recover_mcx_request()
    assert inventory(tmp_path) == before


def test_mcx_conflicting_reuse_and_uncommitted_answer_rejected(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    old = publish_mcx(store)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_ANSWER_IDENTITY_CONFLICT"):
        publish_mcx(store, mcx_publication_fixture(changed_native=True), old.identity)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_BINDING_STALE"):
        store.validate_mcx_answer_for_publication(b"{}", "UNCOMMITTED")
    assert store.load_current_mcx_request() == old


def test_nse_and_mcx_request_authority_are_independent(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    nse = publish(store)
    mcx = publish_mcx(store)
    assert store.load_current_request() == nse
    assert store.load_current_mcx_request() == mcx


def publication_fixture(identity="NSE-REQUEST-1"):
    value = nse_mapping().value
    value["request_identity"] = identity
    value["review_pack_identity"] = "PACK-" + identity
    value["request_sha256"] = nse_pre_render_digest(value)
    buffer = BytesIO()
    pdf = Canvas(buffer, invariant=1)
    pdf.setFont("Courier", 8)
    for index, key in enumerate(("request_identity", "request_sha256", "review_pack_identity", "answer_schema")):
        pdf.drawString(20, 800 - index * 20, value[key])
    pdf.save()
    payload = buffer.getvalue()
    value["review_pack_sha256"] = sha256(payload).hexdigest()
    return NseReviewRequestMapping.create(value), payload


def publish(store, fixture=None, predecessor=None, recheck=lambda mapping: None):
    mapping, pdf = fixture or publication_fixture()
    return store.publish_nse_request(mapping, pdf, publication_timestamp="2026-09-15T00:01:00.000000Z",
                                     expected_predecessor=predecessor, recheck=recheck)


def inventory(root):
    return {str(path.relative_to(root)): (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()}


def test_request_mapping_and_pdf_have_non_circular_complete_publication(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    assert not store.root.exists()
    assert store.load_current_request() is None
    assert not store.root.exists()
    mapping, pdf = publication_fixture()
    result = publish(store, (mapping, pdf))
    assert result.mapping.payload == mapping.payload
    assert result.value["question_pdf_artifact"]["sha256"] == sha256(pdf).hexdigest()
    assert result.value["request_mapping_artifact"]["sha256"] == sha256(mapping.payload).hexdigest()
    assert store.load_current_request() == result
    assert ReviewEvidenceStore(tmp_path).load_current_request() == result
    before = inventory(tmp_path)
    for _ in range(4):
        assert store.load_current_request() == result
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("phase,successor_visible", [
    ("before_retention", False), ("after_pdf_retention", False), ("after_mapping_retention", False),
    ("after_manifest_retention", False), ("before_pointer_replace", False),
    ("after_pointer_replace", True), ("before_acknowledgement", True),
])
def test_every_request_publication_fault_has_whole_predecessor_or_successor(tmp_path, phase, successor_visible):
    store = ReviewEvidenceStore(tmp_path)
    old = publish(store)
    new = publication_fixture("NSE-REQUEST-2")
    def fail(point):
        if point == phase:
            raise RuntimeError("controlled fault")
    broken = ReviewEvidenceStore(tmp_path, fault=fail)
    with pytest.raises(RuntimeError, match="controlled fault"):
        publish(broken, new, old.identity)
    restarted = ReviewEvidenceStore(tmp_path)
    current = restarted.load_current_request()
    assert current.mapping.value["request_identity"] == ("NSE-REQUEST-2" if successor_visible else "NSE-REQUEST-1")
    before = inventory(tmp_path)
    restarted.load_current_request()
    assert inventory(tmp_path) == before
    recovered = restarted.recover_request()
    assert recovered == current
    accepted = publish(restarted, new, old.identity)
    assert restarted.load_current_request() == accepted


def test_identical_replay_preserves_manifest_and_timestamp_without_writes(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    fixture = publication_fixture()
    original = publish(store, fixture)
    before = inventory(tmp_path)
    replay = store.publish_nse_request(*fixture, publication_timestamp="2026-09-15T02:00:00.000000Z",
                                      expected_predecessor=None, recheck=lambda mapping: None)
    assert replay == original
    assert inventory(tmp_path) == before


def test_reused_request_identity_with_different_bytes_is_conflict(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    original = publish(store)
    mapping, pdf = publication_fixture()
    changed = mapping.value
    changed["subjects"][0]["native_assessment_sha256"] = "f" * 64
    changed_mapping = NseReviewRequestMapping.create(changed)
    # To isolate identity conflict, regenerate the controlled PDF for the changed
    # pre-render digest; unlike production this is a synthetic test fixture.
    buffer = BytesIO()
    canvas = Canvas(buffer, invariant=1)
    for index, key in enumerate(("request_identity", "request_sha256", "review_pack_identity", "answer_schema")):
        canvas.drawString(10, 800 - 20 * index, changed_mapping.value[key])
    canvas.save()
    pdf = buffer.getvalue()
    changed["review_pack_sha256"] = sha256(pdf).hexdigest()
    changed_mapping = NseReviewRequestMapping.create(changed)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_ANSWER_IDENTITY_CONFLICT"):
        publish(store, (changed_mapping, pdf), original.identity)
    assert store.load_current_request() == original


@pytest.mark.parametrize("artifact", ["request_mapping_artifact", "question_pdf_artifact"])
def test_retained_artifact_corruption_fails_without_fallback_or_repair(tmp_path, artifact):
    store = ReviewEvidenceStore(tmp_path)
    accepted = publish(store)
    path = store.root / accepted.value[artifact]["relative_path"]
    path.write_bytes(path.read_bytes() + b" ")  # isolated controlled corruption
    before = inventory(tmp_path)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_ARTIFACT_DIGEST_MISMATCH"):
        store.load_current_request()
    assert inventory(tmp_path) == before


def test_changed_pdf_hash_does_not_change_request_hash_but_requires_new_publication(tmp_path):
    mapping, pdf = publication_fixture()
    changed = mapping.value
    changed["review_pack_sha256"] = "f" * 64
    assert nse_pre_render_digest(changed) == mapping.value["request_sha256"]
    with pytest.raises(ReviewEvidenceError, match="REVIEW_ARTIFACT_DIGEST_MISMATCH"):
        publish(ReviewEvidenceStore(tmp_path), (NseReviewRequestMapping.create(changed), pdf))
    assert not (tmp_path / "review-evidence-v1").exists()


def test_stale_commit_recheck_never_publishes_a_prepared_request(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    old = publish(store)
    count = 0
    def recheck(mapping):
        nonlocal count
        count += 1
        if count == 3:
            raise ReviewEvidenceError("REVIEW_BINDING_STALE")
    with pytest.raises(ReviewEvidenceError, match="REVIEW_BINDING_STALE"):
        publish(store, publication_fixture("SECOND"), old.identity, recheck)
    assert count == 3
    assert store.load_current_request() == old


def test_pending_residue_is_never_promoted_by_read_or_explicit_recovery(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    store.root.mkdir()
    (store.root / ".prepared-orphan").write_bytes(b"not a committed publication")
    before = inventory(tmp_path)
    assert store.load_current_request() is None
    assert inventory(tmp_path) == before
    assert store.recover_request() is None
    assert store.load_current_request() is None


def _compete(root, ready, release, queue, suffix):
    store = ReviewEvidenceStore(Path(root))
    fixture = publication_fixture(suffix)
    ready.set()
    release.wait(10)
    try:
        result = publish(store, fixture)
        queue.put(("accepted", result.identity))
    except ReviewEvidenceError as error:
        queue.put((error.code, None))


def test_stable_lock_serializes_competing_processes_without_partial_selection(tmp_path):
    context = multiprocessing.get_context("spawn")
    ready = [context.Event(), context.Event()]
    release = context.Event()
    queue = context.Queue()
    processes = [context.Process(target=_compete, args=(str(tmp_path), ready[index], release, queue, f"REQUEST-{index}")) for index in range(2)]
    for process in processes:
        process.start()
    assert all(event.wait(10) for event in ready)
    release.set()
    outcomes = [queue.get(timeout=10) for _ in processes]
    for process in processes:
        process.join(10)
        assert process.exitcode == 0
    assert sorted(item[0] for item in outcomes) == ["REVIEW_BINDING_STALE", "accepted"]
    store = ReviewEvidenceStore(tmp_path)
    assert store.load_current_request().identity == next(item[1] for item in outcomes if item[0] == "accepted")
    inode = (store.root / "intake.lock").stat().st_ino
    with store.intake_lock():
        pass
    assert (store.root / "intake.lock").stat().st_ino == inode


def acceptance_fixture(instruments=("CANBK", "M&M"), *, mcx=False, suffix="1", prior=None):
    from swing.v1.test_review_evidence_binding import receipt_body
    artifacts = {}
    receipts = []
    answer = b"%PDF-1.4\ncontrolled accepted answer " + suffix.encode()
    checksum = sha256(answer).hexdigest()
    answer_path = "answers/" + checksum + ".pdf"
    artifacts[answer_path] = answer
    for index, instrument in enumerate(instruments):
        body = receipt_body()
        body["binding"].update(canonical_instrument=instrument, candidate_identity="CANDIDATE-" + instrument,
                               market="MCX" if mcx else "NSE")
        body["answer"].update(answer_identity="ANSWER-" + suffix, pdf_sha256=checksum,
                              byte_length=len(answer), retained_relative_path=answer_path)
        body["predecessor_receipt_id"] = prior.receipts[index].receipt_id if prior else None
        body["chart_revisions"], body["structured_evidence"], body["contracts"] = [], [], []
        roles = ("NATIVE_MCX", "SUPPORTING_REFERENCE") if mcx else ("NATIVE_NSE",)
        for role in roles:
            body["contracts"].append({"role": role, "question_contract_identity": "QUESTIONS-" + role,
                "question_contract_version": "1.0", "answer_contract_identity": "ANSWERS-" + role,
                "answer_contract_version": "1.0", "structured_evidence_schema": "EVIDENCE-" + role, "structured_evidence_version": "1.0"})
            for tf in (("1D", "4H", "1H") if mcx else ("1W", "1D", "4H", "1H")):
                chart = (instrument + role + tf).encode()
                chart_hash = sha256(chart).hexdigest()
                chart_path = "charts/" + chart_hash + ".png"
                structured = canonical({"controlled": instrument + role + tf + suffix})
                structured_hash = sha256(structured).hexdigest()
                structured_path = "structured/" + structured_hash + ".json"
                artifacts[chart_path], artifacts[structured_path] = chart, structured
                body["chart_revisions"].append({"role": role, "subject_identity": instrument,
                    "reference_market": "COMEX" if role == "SUPPORTING_REFERENCE" else None,
                    "reference_symbol": "COMEX:GC1!" if role == "SUPPORTING_REFERENCE" else None,
                    "timeframe_or_panel_identity": tf, "revision_identity": "REV-" + tf,
                    "sha256": chart_hash, "retained_relative_path": chart_path})
                body["structured_evidence"].append({"role": role, "subject_identity": instrument,
                    "timeframe_or_family_identity": tf, "schema": "EVIDENCE-" + role, "version": "1.0",
                    "sha256": structured_hash, "retained_relative_path": structured_path})
        receipts.append(ReviewAcceptanceReceipt.create(body))
    return tuple(receipts), artifacts


def accept(store, fixture, prior=None):
    return store.publish_acceptance(*fixture, request_publication_identity="CONTROLLED-VERIFIED-PUBLICATION",
        expected_predecessor=prior.identity if prior else None,
        committed_at="2026-09-15T00:02:00.000000Z", recheck=lambda receipts, publication: None)


def handoff(store, accepted, *, restore=lambda receipt: None,
            consume=lambda receipt: ("READINESS-CONTROLLED", "PROMOTION-CONTROLLED"), recheck=None):
    @contextmanager
    def guard():
        yield "EXACT-CONTROLLED-WO05-SNAPSHOT"

    def check(snapshot, receipt):
        assert snapshot == "EXACT-CONTROLLED-WO05-SNAPSHOT"
        assert receipt == accepted.receipts[0]
        if recheck is not None:
            recheck(snapshot, receipt)
    return store.handoff_committed(accepted.identity, accepted.receipts[0].receipt_id,
        consumer_identity="CONTROLLED-V3-CONSUMER", consumer_version="3.1",
        clock=lambda: "2026-09-15T00:03:00.000000Z", publication_guard=guard,
        recheck=check, restore=restore, consume=consume)


def attempts(store, accepted):
    return store.downstream_attempts(accepted.identity, accepted.receipts[0].receipt_id,
        "CONTROLLED-V3-CONSUMER", "3.1")


@pytest.mark.parametrize("restore_output", [False, True])
def test_guard_scope_downstream_callbacks_are_outside_both_guards(tmp_path, restore_output):
    from kronos.swing.v1.review_evidence_store import _INTAKE_HELD
    store = ReviewEvidenceStore(tmp_path)
    accepted = accept(store, acceptance_fixture(("CANBK",)))
    held = False
    calls = []

    @contextmanager
    def guard():
        nonlocal held
        assert not held
        held = True
        try:
            yield "CONTROLLED"
        finally:
            held = False

    def restore(receipt):
        assert not held, "restore ran under WO-05 publication guard"
        assert not _INTAKE_HELD.get(), "restore ran under WO-07 intake lock"
        calls.append("restore")
        return ("READINESS", "PROMOTION") if restore_output else None

    def consume(receipt):
        assert not held, "consume ran under WO-05 publication guard"
        assert not _INTAKE_HELD.get(), "consume ran under WO-07 intake lock"
        calls.append("consume")
        return ("READINESS", "PROMOTION")

    result = store.handoff_committed(accepted.identity, accepted.receipts[0].receipt_id,
        consumer_identity="CONTROLLED", consumer_version="3.1",
        clock=lambda: "2026-09-15T00:03:00.000000Z", publication_guard=guard,
        recheck=lambda *_: None, restore=restore, consume=consume)
    assert result.value["state"] == "SUCCEEDED"
    assert calls == (["restore"] if restore_output else ["restore", "consume"])
    assert not held and not _INTAKE_HELD.get()


def test_guard_scope_handoff_never_decodes_json_under_publication_guard(tmp_path, monkeypatch):
    import json
    store = ReviewEvidenceStore(tmp_path)
    accepted = accept(store, acceptance_fixture(("CANBK",)))
    held = False
    decode = json.loads

    def observed_decode(*args, **kwargs):
        assert not held, "JSON decoding ran under WO-05 publication guard"
        return decode(*args, **kwargs)

    @contextmanager
    def guard():
        nonlocal held
        held = True
        try:
            yield "CONTROLLED"
        finally:
            held = False

    monkeypatch.setattr(json, "loads", observed_decode)
    result = store.handoff_committed(accepted.identity, accepted.receipts[0].receipt_id,
        consumer_identity="CONTROLLED", consumer_version="3.1",
        clock=lambda: "2026-09-15T00:03:00.000000Z", publication_guard=guard,
        recheck=lambda *_: None, restore=lambda _: None,
        consume=lambda _: ("READINESS", "PROMOTION"))
    assert result.value["state"] == "SUCCEEDED"


def test_guard_scope_concurrent_handoff_cannot_dispatch_same_receipt(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    accepted = accept(store, acceptance_fixture(("CANBK",)))
    calls = []

    def consume(receipt):
        calls.append(receipt.receipt_id)
        # Deterministically enter a second store instance while dispatch one is
        # active. No sleep or time-based abandonment is involved.
        with pytest.raises(ReviewEvidenceError, match="REVIEW_PUBLICATION_CONFLICT"):
            handoff(ReviewEvidenceStore(tmp_path), accepted,
                    consume=lambda _: pytest.fail("duplicate consumer"))
        return ("READINESS", "PROMOTION")

    result = handoff(store, accepted, consume=consume)
    assert result.value["state"] == "SUCCEEDED"
    assert calls == [accepted.receipts[0].receipt_id]
    assert [item.value["state"] for item in attempts(store, accepted)] == ["SUCCEEDED", "RUNNING"]


def test_guard_scope_successor_during_dispatch_rejects_completion(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    accepted = accept(store, acceptance_fixture(("CANBK",)))
    successor = []

    def consume(_receipt):
        successor.append(accept(store, acceptance_fixture(("CANBK",), suffix="2", prior=accepted), accepted))
        return ("OLD-READINESS", "OLD-PROMOTION")

    with pytest.raises(ReviewEvidenceError, match="REVIEW_BINDING_STALE"):
        handoff(store, accepted, consume=consume)
    assert store.load_current_acceptance(accepted.value["package_key"]) == successor[0]
    assert [item.value["state"] for item in attempts(store, accepted)] == ["RUNNING"]


def test_guard_scope_run_change_during_dispatch_rejects_completion(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    accepted = accept(store, acceptance_fixture(("CANBK",)))
    current = ["ORIGINAL-RUN"]

    @contextmanager
    def guard():
        yield current[0]

    def consume(_receipt):
        current[0] = "SUCCESSOR-RUN"
        return ("OLD-READINESS", "OLD-PROMOTION")

    with pytest.raises(ReviewEvidenceError, match="REVIEW_BINDING_STALE"):
        store.handoff_committed(accepted.identity, accepted.receipts[0].receipt_id,
            consumer_identity="CONTROLLED-V3-CONSUMER", consumer_version="3.1",
            clock=lambda: "2026-09-15T00:03:00.000000Z", publication_guard=guard,
            recheck=lambda *_: None, restore=lambda _: None, consume=consume)
    assert [item.value["state"] for item in attempts(store, accepted)] == ["RUNNING"]


def test_downstream_failure_preserves_acceptance_and_retry_restores_exact_output(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    accepted = accept(store, acceptance_fixture(("CANBK",)))
    original = inventory(tmp_path)
    def fail(receipt):
        assert store.load_current_acceptance(accepted.value["package_key"]) == accepted
        raise ValueError("PRIVATE DIAGNOSTIC MUST NOT BE RETAINED")
    failed = handoff(store, accepted, consume=fail)
    assert failed.value["state"] == "FAILED"
    assert failed.value["reason_code"] == "REVIEW_DOWNSTREAM_PROCESSING_FAILED"
    assert b"PRIVATE" not in failed.payload
    assert all(inventory(tmp_path)[key] == value for key, value in original.items())
    calls = []
    def consume(receipt):
        calls.append(receipt.receipt_id)
        return ("EXACT-READINESS", "EXACT-PROMOTION")
    succeeded = handoff(store, accepted, consume=consume)
    assert succeeded.value["state"] == "SUCCEEDED"
    assert calls == [accepted.receipts[0].receipt_id]
    before = inventory(tmp_path)
    assert handoff(ReviewEvidenceStore(tmp_path), accepted, restore=lambda receipt: (
        "EXACT-READINESS", "EXACT-PROMOTION"), consume=fail) == succeeded
    assert inventory(tmp_path) == before
    assert [item.value["state"] for item in attempts(store, accepted)] == ["SUCCEEDED", "RUNNING", "FAILED", "RUNNING"]


@pytest.mark.parametrize("instrument", ["GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS"])
def test_mcx_handoff_is_unsupported_without_any_consumer_or_restore_call(tmp_path, instrument):
    store = ReviewEvidenceStore(tmp_path)
    accepted = accept(store, acceptance_fixture((instrument,), mcx=True))
    def forbidden(receipt):
        pytest.fail("MCX must not reach the NSE downstream consumer or restoration")
    result = handoff(store, accepted, restore=forbidden, consume=forbidden)
    assert result.value["state"] == "UNSUPPORTED_CONTRACT"
    assert result.value["output_identities"] == []
    assert store.load_current_acceptance(accepted.value["package_key"]) == accepted
    before = inventory(tmp_path)
    assert handoff(ReviewEvidenceStore(tmp_path), accepted, restore=forbidden, consume=forbidden) == result
    assert attempts(store, accepted) == (result,)
    assert inventory(tmp_path) == before


def test_handoff_after_output_crash_restores_before_repeating_consumer(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    accepted = accept(store, acceptance_fixture(("CANBK",)))
    outputs, calls = [], []
    def consume(receipt):
        calls.append(receipt.receipt_id)
        outputs.extend(("CONTROLLED-EXACT-READINESS", "CONTROLLED-EXACT-PROMOTION"))
        return tuple(outputs)
    def crash(point):
        if point == "after_downstream_output":
            raise RuntimeError("controlled process interruption")
    with pytest.raises(RuntimeError, match="controlled process interruption"):
        handoff(ReviewEvidenceStore(tmp_path, fault=crash), accepted, consume=consume)
    assert attempts(store, accepted)[0].value["state"] == "RUNNING"
    before = inventory(tmp_path)
    assert attempts(store, accepted)[0].value["state"] == "RUNNING"
    assert inventory(tmp_path) == before
    result = handoff(store, accepted, restore=lambda receipt: tuple(outputs), consume=consume)
    assert result.value["state"] == "SUCCEEDED"
    assert calls == [accepted.receipts[0].receipt_id]


def test_uncommitted_or_superseded_receipt_cannot_dispatch(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    accepted = accept(store, acceptance_fixture(("CANBK",)))
    fixture = acceptance_fixture(("CANBK",), suffix="2", prior=accepted)
    def crash(point):
        if point == "before_acceptance_pointer":
            raise RuntimeError("controlled uncommitted residue")
    with pytest.raises(RuntimeError):
        accept(ReviewEvidenceStore(tmp_path, fault=crash), fixture, accepted)
    loose = next(path for path in (store.root / "acceptance-commits").glob("*.json")
                 if path.stem != accepted.identity)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_ACCEPTANCE_INCOMPLETE"):
        store.resolve_committed_receipt(loose.stem, fixture[0][0].receipt_id)
    successor = accept(store, fixture, accepted)
    before = inventory(tmp_path)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_BINDING_STALE"):
        handoff(store, accepted)
    assert store.resolve_committed_receipt(accepted.identity, accepted.receipts[0].receipt_id) == accepted.receipts[0]
    assert store.load_current_acceptance(successor.value["package_key"]) == successor
    assert inventory(tmp_path) == before


def test_corrupt_attempt_or_missing_success_output_never_repeats_consumer(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    accepted = accept(store, acceptance_fixture(("CANBK",)))
    result = handoff(store, accepted)
    def forbidden(receipt):
        pytest.fail("success may not silently be recomputed")
    before = inventory(tmp_path)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_ARTIFACT_DIGEST_MISMATCH"):
        handoff(store, accepted, restore=lambda receipt: None, consume=forbidden)
    assert inventory(tmp_path) == before
    path = store.root / "downstream-attempts" / (result.identity + ".json")
    path.write_bytes(path.read_bytes() + b" ")
    corrupt = inventory(tmp_path)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_ARTIFACT_DIGEST_MISMATCH"):
        attempts(store, accepted)
    assert inventory(tmp_path) == corrupt


def test_acceptance_is_whole_batch_and_replay_preserves_acceptance_time(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    fixture = acceptance_fixture()
    result = accept(store, fixture)
    assert len(result.receipts) == 2
    assert store.load_current_acceptance(result.value["package_key"]) == result
    before = inventory(tmp_path)
    assert accept(store, fixture) == result
    assert inventory(tmp_path) == before
    new = accept(store, acceptance_fixture(suffix="2", prior=result), result)
    assert all(item.body["predecessor_receipt_id"] == old.receipt_id for item, old in zip(new.receipts, result.receipts))
    assert store.load_acceptance(result.identity) == result


def test_native_new_question_pack_preserves_same_run_successor_ancestry(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    original = accept(store, acceptance_fixture())
    proposed, artifacts = acceptance_fixture(suffix="2", prior=original)
    changed = []
    for receipt in proposed:
        body = receipt.body
        body["binding"].update(review_pack_identity="EXPLICIT-NEW-PACK", request_identity="EXPLICIT-NEW-REQUEST")
        changed.append(ReviewAcceptanceReceipt.create(body))
    successor = accept(store, (tuple(changed), artifacts), original)
    assert original.value["package_key"] == successor.value["package_key"]
    assert store.native_acceptance_history("NSE", original.receipts[0].binding.value["analytical_run_identity"]) == (successor, original)
    assert all(new.body["predecessor_receipt_id"] == old.receipt_id
               for new, old in zip(successor.receipts, original.receipts, strict=True))
    assert store.load_acceptance(original.identity) == original
    # A previously used Answer identity cannot be recycled through another pack.
    recycled, artifacts = acceptance_fixture(suffix="1", prior=successor)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_ANSWER_IDENTITY_CONFLICT"):
        accept(store, (recycled, artifacts), successor)


def test_individual_package_does_not_break_other_candidates_receipt_lineage(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    first = accept(store, acceptance_fixture())
    selected, artifacts = acceptance_fixture(("CANBK",), suffix="2", prior=first)
    second = accept(store, (selected, artifacts), first)
    proposed, artifacts = acceptance_fixture(("M&M",), suffix="3")
    body = proposed[0].body
    body["predecessor_receipt_id"] = first.receipts[1].receipt_id
    third = accept(store, ((ReviewAcceptanceReceipt.create(body),), artifacts), second)
    assert store.acceptance_history(first.value["package_key"]) == (third, second, first)


@pytest.mark.parametrize("phase,visible", [
    ("before_acceptance_retention", False), ("after_acceptance_artifact_0", False),
    ("after_acceptance_artifact_1", False), ("after_acceptance_artifact_8", False),
    ("after_acceptance_receipt_0", False), ("after_acceptance_receipt_1", False),
    ("after_acceptance_manifest", False), ("before_acceptance_pointer", False),
    ("after_acceptance_pointer", True), ("before_acceptance_acknowledgement", True),
])
def test_acceptance_faults_never_publish_one_candidate_of_a_batch(tmp_path, phase, visible):
    store = ReviewEvidenceStore(tmp_path)
    old = accept(store, acceptance_fixture())
    fixture = acceptance_fixture(suffix="2", prior=old)
    def fail(point):
        if point == phase:
            raise RuntimeError("controlled acceptance fault")
    with pytest.raises(RuntimeError, match="controlled acceptance fault"):
        accept(ReviewEvidenceStore(tmp_path, fault=fail), fixture, old)
    current = store.load_current_acceptance(old.value["package_key"])
    assert len(current.receipts) == 2
    assert all(item.body["answer"]["answer_identity"] == ("ANSWER-2" if visible else "ANSWER-1") for item in current.receipts)
    before = inventory(tmp_path)
    assert store.load_current_acceptance(old.value["package_key"]) == current
    assert inventory(tmp_path) == before
    assert accept(store, fixture, old).receipts == fixture[0]


def test_mcx_requires_both_roles_and_all_six_structured_responses(tmp_path):
    store = ReviewEvidenceStore(tmp_path)
    fixture = acceptance_fixture(("GOLDM",), mcx=True)
    accepted = accept(store, fixture)
    assert len(accepted.receipts[0].body["structured_evidence"]) == 6
    incomplete, artifacts = acceptance_fixture(("GOLDM",), mcx=True, suffix="2", prior=accepted)
    body = incomplete[0].body
    body["structured_evidence"].pop()
    bad = ReviewAcceptanceReceipt.create(body)
    required = {path for path, checksum in store._receipt_artifacts(bad)}
    with pytest.raises(ReviewEvidenceError, match="REVIEW_ACCEPTANCE_INCOMPLETE"):
        accept(store, ((bad,), {path: data for path, data in artifacts.items() if path in required}), accepted)
    assert store.load_current_acceptance(accepted.value["package_key"]) == accepted


def test_acceptance_survives_working_answer_loss_but_retained_tamper_fails(tmp_path):
    store = ReviewEvidenceStore(tmp_path / "retained")
    fixture = acceptance_fixture()
    working = tmp_path / "answer.pdf"
    working.write_bytes(next(iter(fixture[1].values())))
    accepted = accept(store, fixture)
    working.unlink()
    assert store.load_acceptance(accepted.identity) == accepted
    path = store.root / accepted.receipts[0].body["answer"]["retained_relative_path"]
    path.write_bytes(b"%PDF-corrupt")
    before = inventory(store.root)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_ARTIFACT_DIGEST_MISMATCH"):
        store.load_acceptance(accepted.identity)
    assert inventory(store.root) == before
