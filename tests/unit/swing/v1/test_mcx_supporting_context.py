from __future__ import annotations

import base64
from datetime import UTC, date, datetime
import json
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Preformatted, SimpleDocTemplate

from kronos.application.swing_mcx_supporting_context import McxSupportingContextWorkflow
from kronos.configuration.pdf_visual_review import PdfVisualReviewConfiguration
from kronos.swing.v1.mcx_supporting_context import (
    AlignmentState,
    DirectionState,
    ENERGY_PANELS,
    EvidenceQuality,
    MCX_CONTEXT_ANSWER_SCHEMA,
    METALS_PANELS,
    McxContextFamily,
    McxContextPanelObservation,
    McxContextSlot,
    McxSupportingContextStore,
    PanelValidation,
    StructuralCondition,
    build_context_record,
    canonical_mcx_context_timeframe,
)
from kronos.swing.v1.mcx_supporting_context_pdf import (
    McxContextPanelValidationError,
    McxContextPdfStore,
    McxContextPdfTransport,
)
from kronos.swing.v1.pdf_visual_review import BEGIN_GOVERNED_ANSWER_DATA, END_GOVERNED_ANSWER_DATA, PdfReviewTransportError
from tests.unit.swing.test_run_publication import checkpoint, scenario


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
DAY = date(2026, 8, 24)
MORNING = datetime(2026, 8, 24, 9, 15, tzinfo=UTC)


class _Calendar:
    def __init__(self, trading: bool = True) -> None: self.trading = trading
    def is_trading_date(self, exchange: str, day: date) -> bool:
        return self.trading and exchange == "MCX" and day == DAY


def _transport(tmp_path: Path, now: datetime = MORNING):
    config = PdfVisualReviewConfiguration(tmp_path / "questions", tmp_path / "answers")
    pdf_store = McxContextPdfStore(tmp_path / "pdf")
    transport = McxContextPdfTransport(config, pdf_store, clock=lambda: now)
    store = McxSupportingContextStore(tmp_path / "records")
    workflow = McxSupportingContextWorkflow(store, transport, calendar=_Calendar(), clock=lambda: now)
    return workflow, transport, store


def _stage(workflow: McxSupportingContextWorkflow, slot: McxContextSlot) -> None:
    for family in McxContextFamily:
        workflow.stage_image(slot=slot, family=family, content_type="image/png", payload=PNG)


def _payload(pack, *, captured_at: datetime = MORNING) -> dict[str, object]:
    def panel(item):
        return {
            "panel_id": item.panel_id,
            "observed_identity": item.expected_identity,
            "observed_timeframe": item.expected_timeframe,
            "validation": "MATCH",
            "direction": "RANGE",
            "evidence_quality": "CLEAR",
            "structural_condition": "CONSOLIDATING",
        }
    return {
        "schema": MCX_CONTEXT_ANSWER_SCHEMA,
        "manifest": {
            "question_pack_identity": pack.question_pack_identity,
            "trading_date": pack.trading_date.isoformat(),
            "slot": pack.slot.value,
            "answer_schema": MCX_CONTEXT_ANSWER_SCHEMA,
            "answer_pack_identity": "CHART-ANALYST-ANSWER-1",
            "captured_at": captured_at.isoformat(),
        },
        "families": [
            {"family": "METALS", "panels": [panel(item) for item in METALS_PANELS]},
            {"family": "ENERGY", "panels": [panel(item) for item in ENERGY_PANELS],
             "wti_brent_alignment": "ALIGNED", "natural_gas_alignment": "DIVERGENT"},
        ],
    }


_REAL_VISIBLE_IDENTITIES = {
    "M1": "US Dollar Index Futures",
    "M2": "US Government Bonds 10 YR Yield",
    "M3": "US Government Bonds 30 YR",
    "M4": "U.S. Dollar / Indian Rupee",
    "M5": "Copper Futures",
    "M6": "USD/CNH",
    "M7": "CSI 300 Index Futures",
    "M8": "Gold Futures",
    "E1": "Natural Gas Futures",
    "E2": "Natural Gas Futures",
    "E3": "U.S. Dollar / Indian Rupee",
    "E4": "Light Crude Oil Futures",
    "E5": "Crude Oil Brent Cash",
    "E6": "U.S. Dollar Index",
}
_REAL_VISIBLE_TIMEFRAMES = {"E2": "4h", "E3": "1h", "E6": "1h"}


def _real_visible_payload(pack) -> dict[str, object]:
    payload = _payload(pack)
    for family in payload["families"]:
        for panel in family["panels"]:
            panel_id = panel["panel_id"]
            panel["observed_identity"] = _REAL_VISIBLE_IDENTITIES[panel_id]
            panel["observed_timeframe"] = _REAL_VISIBLE_TIMEFRAMES.get(
                panel_id, panel["observed_timeframe"],
            )
    return payload


def _answer(path: Path, payload: dict[str, object]) -> None:
    styles = getSampleStyleSheet()
    SimpleDocTemplate(str(path), pagesize=A4).build([
        Preformatted(BEGIN_GOVERNED_ANSWER_DATA + "\n" + json.dumps(payload, indent=2) + "\n" + END_GOVERNED_ANSWER_DATA, styles["Code"])
    ])


def _atomic_context(tmp_path, checkpoint, *, fault=None):
    from hashlib import sha256
    from kronos.application.swing_opportunities import SwingOpportunitiesApplication
    from kronos.swing.v1.review_evidence_binding import canonical, ReviewMutationPrecondition
    from kronos.swing.v1.review_evidence_store import ReviewEvidenceStore
    from tests.unit.application.test_swing_opportunities import _Provider

    workflow, transport, historical = _transport(tmp_path)
    workflow.intake_store = ReviewEvidenceStore(tmp_path / "native-review", fault=fault)
    application = SwingOpportunitiesApplication(_Provider, run_publication=checkpoint[0])

    def state(slot):
        pack = transport.store.current(DAY, slot)
        chain = workflow.intake_store.context_acceptance_history(DAY, slot)
        return dict(expected_committed_run_manifest=checkpoint[0].current().reference["sha256"],
            expected_run_identity=checkpoint[0].current().native.run_identity,
            expected_candidate_identity=None,
            expected_review_cycle_identity=None if pack is None else pack.question_pack_identity,
            expected_request_identity=None if pack is None else pack.question_pack_identity,
            expected_revision_set_digest=sha256(canonical([
                None if (image := transport.store.current_image(DAY, slot, family)) is None
                else [family.value, image.image_sha256, image.staged_at.isoformat()]
                for family in McxContextFamily])).hexdigest(),
            expected_acceptance_receipt_id=None if not chain else chain[0].receipts[0].receipt_id)

    def submit(slot, *, expected=None):
        expected = state(slot) if expected is None else expected
        return workflow.upload_answer_atomic(slot,
            precondition=ReviewMutationPrecondition.create(dict(expected, mutation_identity="EXPLICIT-TEST")),
            current_state=lambda: state(slot), publication_guard=application.publication_mutation_guard)
    return workflow, transport, historical, state, submit


def _inventory(root):
    from hashlib import sha256
    return {str(path.relative_to(root)): (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()}


def test_wo07_context_atomic_acceptance_replay_restart_and_pure_reads(tmp_path, checkpoint):
    from kronos.swing.v1.review_evidence_store import ReviewEvidenceStore
    workflow, transport, historical, state, submit = _atomic_context(tmp_path, checkpoint)
    _stage(workflow, McxContextSlot.MORNING)
    pack = workflow.create_question_pack(McxContextSlot.MORNING)
    answer_path = transport.configuration.answer_directory / pack.expected_answer_filename
    _answer(answer_path, _real_visible_payload(pack))
    committed = submit(McxContextSlot.MORNING)
    assert len(committed.receipts) == 1
    assert historical.records() == ()
    records = workflow.intake_store.context_records(DAY, McxContextSlot.MORNING)
    assert tuple(item.family for item in records) == tuple(McxContextFamily)
    assert records[0].panels[2].observed_identity == "US Government Bonds 30 YR"
    assert records[1].panels[1].observed_timeframe == "4h"
    before = _inventory(tmp_path)
    assert submit(McxContextSlot.MORNING) == committed
    assert _inventory(tmp_path) == before
    # The retained PDF, not its working copy, is the acceptance authority.
    answer_path.unlink()
    workflow.intake_store = ReviewEvidenceStore(tmp_path / "native-review")
    before = _inventory(tmp_path)
    for _ in range(3):
        assert workflow.intake_store.context_records(DAY, McxContextSlot.MORNING) == records
        assert all(item.revision == 1 for item in workflow.snapshot().slots[0].families)
        assert workflow.context_for("GOLDM", assessment_boundary=MORNING) == records[0]
        assert workflow.context_for("SAIL", assessment_boundary=MORNING) is None
    assert _inventory(tmp_path) == before


def test_wo07_context_snapshot_reads_one_complete_family_bundle(tmp_path, checkpoint, monkeypatch):
    workflow, transport, _, _, submit = _atomic_context(tmp_path, checkpoint)
    _stage(workflow, McxContextSlot.MORNING)
    pack = workflow.create_question_pack(McxContextSlot.MORNING)
    _answer(transport.configuration.answer_directory / pack.expected_answer_filename, _payload(pack))
    submit(McxContextSlot.MORNING)
    reads = []
    original = workflow._records

    def read_bundle(*, trading_date, slot=None, family=None):
        # A separate family lookup could observe different pointer generations.
        assert family is None
        reads.append(slot)
        return original(trading_date=trading_date, slot=slot)

    monkeypatch.setattr(workflow, "_records", read_bundle)
    pointer_reads = []
    load = workflow.intake_store.load_current_acceptance
    def load_pointer(key):
        pointer_reads.append(key)
        return load(key)
    monkeypatch.setattr(workflow.intake_store, "load_current_acceptance", load_pointer)
    before = _inventory(tmp_path)
    snapshot = workflow.snapshot()
    assert reads == [McxContextSlot.MORNING, McxContextSlot.EVENING]
    assert len(pointer_reads) == 2  # one exact pointer per complete slot, not per family
    assert tuple(item.revision for item in snapshot.slots[0].families) == (1, 1)
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize("fault_at", [
    "before_acceptance_retention", "after_acceptance_artifact_0",
    "after_acceptance_artifact_1", "after_acceptance_artifact_2",
    "after_acceptance_artifact_3", "after_acceptance_receipt_0",
    "after_acceptance_manifest", "before_acceptance_pointer",
    "after_acceptance_pointer", "before_acceptance_acknowledgement",
])
def test_wo07_context_fault_never_exposes_one_family(tmp_path, checkpoint, fault_at):
    def fault(stage):
        if stage == fault_at:
            raise OSError("controlled interruption")
    workflow, transport, historical, state, submit = _atomic_context(tmp_path, checkpoint, fault=fault)
    _stage(workflow, McxContextSlot.MORNING)
    pack = workflow.create_question_pack(McxContextSlot.MORNING)
    _answer(transport.configuration.answer_directory / pack.expected_answer_filename, _payload(pack))
    with pytest.raises(OSError, match="controlled interruption"):
        submit(McxContextSlot.MORNING)
    committed = fault_at in {"after_acceptance_pointer", "before_acceptance_acknowledgement"}
    assert len(workflow.intake_store.context_records(DAY, McxContextSlot.MORNING)) == (2 if committed else 0)
    assert historical.records() == ()
    before = _inventory(tmp_path)
    workflow.snapshot()
    assert _inventory(tmp_path) == before


def test_wo07_context_stale_image_and_stale_request_rejected(tmp_path, checkpoint):
    from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError
    workflow, transport, historical, state, submit = _atomic_context(tmp_path, checkpoint)
    slot = McxContextSlot.MORNING
    _stage(workflow, slot)
    pack = workflow.create_question_pack(slot)
    _answer(transport.configuration.answer_directory / pack.expected_answer_filename, _payload(pack))
    old = state(slot)
    workflow.remove_image(slot=slot, family=McxContextFamily.ENERGY)
    before = _inventory(tmp_path)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_BINDING_STALE"):
        submit(slot, expected=old)
    assert _inventory(tmp_path) == before
    _stage(workflow, slot)
    old = state(slot)
    workflow.create_question_pack(slot)
    before = _inventory(tmp_path)
    with pytest.raises(ReviewEvidenceError, match="REVIEW_BINDING_STALE"):
        submit(slot, expected=old)
    assert _inventory(tmp_path) == before


def test_wo07_context_capture_hashes_validated_bytes_once(tmp_path, monkeypatch):
    from hashlib import sha256
    workflow, transport, _ = _transport(tmp_path)
    _stage(workflow, McxContextSlot.MORNING)
    pack = workflow.create_question_pack(McxContextSlot.MORNING)
    path = transport.configuration.answer_directory / pack.expected_answer_filename
    _answer(path, _payload(pack))
    original = path.read_bytes()
    from kronos.swing.v1 import pdf_visual_review_v3_live as pdf
    extract = pdf.extract_successor_answer_pdf
    def replace_after_capture(raw):
        path.write_bytes(b"changed working Answer after capture")
        return extract(raw)
    monkeypatch.setattr(pdf, "extract_successor_answer_pdf", replace_after_capture)
    result = transport.capture_and_validate(pack)
    assert result.pdf_bytes == original
    assert result.answer.answer_sha256 == sha256(original).hexdigest()


def test_morning_and_evening_question_answer_revision_and_restart(tmp_path: Path) -> None:
    workflow, transport, store = _transport(tmp_path)
    _stage(workflow, McxContextSlot.MORNING)
    morning = workflow.create_question_pack(McxContextSlot.MORNING)
    assert morning.question_path.endswith("_QUESTIONS.pdf")
    assert Path(morning.question_path).parent == transport.configuration.question_directory
    text = "\n".join(page.extract_text() or "" for page in PdfReader(morning.question_path).pages)
    assert "SUPPORTING EVIDENCE ONLY" in text
    assert "US Government Bonds 30Y Yield 1D" in text
    assert "Q9 WTI/Brent alignment" in text
    assert morning.question_pack_identity.removeprefix("MCX-CONTEXT-PACK-")[:12] in morning.question_filename
    _answer(transport.configuration.answer_directory / morning.expected_answer_filename, _payload(morning))
    records = workflow.upload_answer(McxContextSlot.MORNING)
    assert tuple(item.family for item in records) == tuple(McxContextFamily)
    assert all(item.revision == 1 for item in records)

    # Exact retry is idempotent; a corrected Answer identity creates REV2.
    records2 = workflow.upload_answer(McxContextSlot.MORNING)
    assert all(item.revision == 1 for item in records2)
    corrected = _payload(morning)
    corrected["manifest"]["answer_pack_identity"] = "CHART-ANALYST-ANSWER-2"
    _answer(transport.configuration.answer_directory / morning.expected_answer_filename, corrected)
    records2 = workflow.upload_answer(McxContextSlot.MORNING)
    assert all(item.revision == 2 for item in records2)
    assert len(store.records(trading_date=DAY)) == 4

    evening_time = datetime(2026, 8, 24, 18, 0, tzinfo=UTC)
    workflow._clock = lambda: evening_time
    transport._clock = lambda: evening_time
    _stage(workflow, McxContextSlot.EVENING)
    evening = workflow.create_question_pack(McxContextSlot.EVENING)
    _answer(transport.configuration.answer_directory / evening.expected_answer_filename, _payload(evening, captured_at=evening_time))
    workflow.upload_answer(McxContextSlot.EVENING)
    assert all(item.slot is McxContextSlot.MORNING for item in store.records(slot=McxContextSlot.MORNING))

    restored = McxSupportingContextStore(store.root)
    assert len(restored.records(trading_date=DAY)) == 6


def test_real_visible_labels_import_and_restore_as_unchanged_raw_evidence(tmp_path: Path) -> None:
    workflow, transport, store = _transport(tmp_path)
    _stage(workflow, McxContextSlot.MORNING)
    pack = workflow.create_question_pack(McxContextSlot.MORNING)
    payload = _real_visible_payload(pack)
    _answer(
        transport.configuration.answer_directory / pack.expected_answer_filename,
        payload,
    )

    records = workflow.upload_answer(McxContextSlot.MORNING)
    assert len(records) == 2
    observations = {
        item.panel_id: item
        for record in records
        for item in record.panels
    }
    assert set(observations) == set(_REAL_VISIBLE_IDENTITIES)
    for panel_id, expected_visible_identity in _REAL_VISIBLE_IDENTITIES.items():
        assert observations[panel_id].observed_identity == expected_visible_identity
    for panel_id, expected_visible_timeframe in _REAL_VISIBLE_TIMEFRAMES.items():
        assert observations[panel_id].observed_timeframe == expected_visible_timeframe

    restored = McxSupportingContextStore(store.root).records(
        trading_date=DAY, slot=McxContextSlot.MORNING,
    )
    assert {item.family: item for item in restored} == {
        item.family: item for item in records
    }
    restored_observations = {
        item.panel_id: item for record in restored for item in record.panels
    }
    assert restored_observations["E2"].observed_identity == "Natural Gas Futures"
    assert restored_observations["E2"].observed_timeframe == "4h"


@pytest.mark.parametrize(
    "family_index,panel_index,value,field,panel_id",
    [
        (0, 0, "Gold Futures", "observed_identity", "M1"),
        (0, 4, "Natural Gas Futures", "observed_identity", "M5"),
        (1, 3, "Gold Futures", "observed_identity", "E4"),
        (1, 1, "1H", "observed_timeframe", "E2"),
        (0, 7, "4H", "observed_timeframe", "M8"),
    ],
)
def test_unapproved_identity_and_timeframe_values_fail_closed_with_exact_diagnostic(
    tmp_path: Path,
    family_index: int,
    panel_index: int,
    value: str,
    field: str,
    panel_id: str,
) -> None:
    workflow, transport, store = _transport(tmp_path)
    _stage(workflow, McxContextSlot.MORNING)
    pack = workflow.create_question_pack(McxContextSlot.MORNING)
    payload = _real_visible_payload(pack)
    payload["families"][family_index]["panels"][panel_index][field] = value
    _answer(
        transport.configuration.answer_directory / pack.expected_answer_filename,
        payload,
    )
    with pytest.raises(McxContextPanelValidationError) as captured:
        workflow.upload_answer(McxContextSlot.MORNING)
    failure = captured.value.failure
    assert failure.panel_id == panel_id
    assert failure.failed_field.value == (
        "IDENTITY" if field == "observed_identity" else "TIMEFRAME"
    )
    assert failure.observed == value
    status = workflow.snapshot().slots[0].last_error
    assert status is not None
    assert status.panel_id == panel_id
    assert status.failed_field == failure.failed_field.value
    assert status.observed == value
    assert store.records() == ()


@pytest.mark.parametrize(
    "raw,canonical", [("1D", "1D"), ("1d", "1D"), ("1H", "1H"),
                      ("1h", "1H"), ("4H", "4H"), ("4h", "4H")],
)
def test_timeframe_normalization_accepts_only_bounded_case_equivalents(
    raw: str, canonical: str,
) -> None:
    assert canonical_mcx_context_timeframe(raw) == canonical


@pytest.mark.parametrize("raw", ["15m", "DAY", "4hr", " 1H", "1H ", ""])
def test_timeframe_normalization_rejects_unknown_or_semantically_different_values(raw: str) -> None:
    assert canonical_mcx_context_timeframe(raw) is None


def test_staged_images_coexist_replace_remove_and_restore_without_cross_slot_mutation(tmp_path: Path) -> None:
    workflow, transport, _ = _transport(tmp_path)
    _stage(workflow, McxContextSlot.MORNING)
    _stage(workflow, McxContextSlot.EVENING)
    morning_metals = transport.store.current_image(
        DAY, McxContextSlot.MORNING, McxContextFamily.METALS,
    )
    morning_energy = transport.store.current_image(
        DAY, McxContextSlot.MORNING, McxContextFamily.ENERGY,
    )
    evening_metals = transport.store.current_image(
        DAY, McxContextSlot.EVENING, McxContextFamily.METALS,
    )
    assert morning_metals is not None and morning_energy is not None
    assert evening_metals is not None

    replacement = PNG + b"replacement"
    replaced = workflow.stage_image(
        slot=McxContextSlot.MORNING, family=McxContextFamily.METALS,
        content_type="image/png", payload=replacement,
    )
    assert replaced.image_sha256 != morning_metals.image_sha256
    assert transport.store.current_image(
        DAY, McxContextSlot.MORNING, McxContextFamily.ENERGY,
    ) == morning_energy
    assert transport.store.current_image(
        DAY, McxContextSlot.EVENING, McxContextFamily.METALS,
    ) == evening_metals

    restored = McxContextPdfStore(transport.store.root)
    assert restored.current_image(
        DAY, McxContextSlot.MORNING, McxContextFamily.METALS,
    ) == replaced
    assert restored.image_bytes(replaced) == replacement

    workflow.remove_image(
        slot=McxContextSlot.MORNING, family=McxContextFamily.METALS,
    )
    assert restored.current_image(
        DAY, McxContextSlot.MORNING, McxContextFamily.METALS,
    ) is None
    assert Path(replaced.path).read_bytes() == replacement
    assert restored.current_image(
        DAY, McxContextSlot.EVENING, McxContextFamily.METALS,
    ) == evening_metals


def test_question_pack_uses_the_current_replaced_images(tmp_path: Path) -> None:
    workflow, _, _ = _transport(tmp_path)
    _stage(workflow, McxContextSlot.MORNING)
    replacement = PNG + b"replacement"
    replaced = workflow.stage_image(
        slot=McxContextSlot.MORNING, family=McxContextFamily.METALS,
        content_type="image/png", payload=replacement,
    )
    pack = workflow.create_question_pack(McxContextSlot.MORNING)
    assert pack.images[0] == replaced
    assert pack.images[1].family is McxContextFamily.ENERGY


def test_temporal_binding_is_same_date_family_exact_and_never_retroactive(tmp_path: Path) -> None:
    store = McxSupportingContextStore(tmp_path)
    observations = tuple(McxContextPanelObservation(
        item.panel_id, item.expected_identity, item.expected_timeframe,
        PanelValidation.MATCH, DirectionState.RANGE, EvidenceQuality.CLEAR,
        StructuralCondition.CONSOLIDATING,
    ) for item in METALS_PANELS)
    morning = build_context_record(
        trading_date=DAY, slot=McxContextSlot.MORNING, family=McxContextFamily.METALS,
        revision=1, question_pack_identity="Q1", answer_pack_identity="A1",
        captured_at=MORNING, imported_at=datetime(2026, 8, 24, 9, 30, tzinfo=UTC), panels=observations,
    )
    evening = build_context_record(
        trading_date=DAY, slot=McxContextSlot.EVENING, family=McxContextFamily.METALS,
        revision=1, question_pack_identity="Q2", answer_pack_identity="A2",
        captured_at=datetime(2026, 8, 24, 18, tzinfo=UTC),
        imported_at=datetime(2026, 8, 24, 18, 15, tzinfo=UTC), panels=observations,
    )
    store.retain(morning); store.retain(evening)
    assert store.latest_valid(DAY, McxContextFamily.METALS, boundary=datetime(2026, 8, 24, 9, 0, tzinfo=UTC)) is None
    assert store.latest_valid(DAY, McxContextFamily.METALS, boundary=datetime(2026, 8, 24, 11, 0, tzinfo=UTC)) == morning
    assert store.latest_valid(DAY, McxContextFamily.METALS, boundary=datetime(2026, 8, 24, 19, 0, tzinfo=UTC)) == evening


@pytest.mark.parametrize("mutation,reason", [
    (lambda value: value["families"][0]["panels"].pop(), "MCX_CONTEXT_PANEL_COUNT_INVALID"),
    (lambda value: value["families"][0]["panels"][0].update(observed_identity="WRONG"), "MCX_CONTEXT_PANEL_INVALID_INCOMPLETE"),
    (lambda value: value["families"][0]["panels"][0].update(observed_timeframe="4H"), "MCX_CONTEXT_PANEL_INVALID_INCOMPLETE"),
    (lambda value: value["families"][0]["panels"][0].update(evidence_quality="UNREADABLE"), "MCX_CONTEXT_PANEL_INVALID_INCOMPLETE"),
    (lambda value: value["manifest"].update(trading_date="2026-08-25"), "MCX_CONTEXT_ANSWER_BINDING_MISMATCH"),
    (lambda value: value["manifest"].update(slot="EVENING"), "MCX_CONTEXT_ANSWER_BINDING_MISMATCH"),
    (lambda value: value["manifest"].update(question_pack_identity="WRONG"), "MCX_CONTEXT_ANSWER_NOT_FOUND"),
    (lambda value: value["families"][1]["panels"][0].update(direction="BULLISH"), "MCX_CONTEXT_PANEL_ENUM_INVALID"),
])
def test_answer_import_fails_closed_for_every_governed_mismatch(tmp_path: Path, mutation, reason: str) -> None:
    workflow, transport, store = _transport(tmp_path); _stage(workflow, McxContextSlot.MORNING)
    pack = workflow.create_question_pack(McxContextSlot.MORNING); payload = _payload(pack); mutation(payload)
    _answer(transport.configuration.answer_directory / pack.expected_answer_filename, payload)
    with pytest.raises((PdfReviewTransportError, ValueError), match=reason):
        workflow.upload_answer(McxContextSlot.MORNING)
    assert store.records() == ()


def test_non_trading_date_creates_no_false_required_context(tmp_path: Path) -> None:
    workflow, _, _ = _transport(tmp_path); workflow.calendar = _Calendar(False)
    snapshot = workflow.snapshot()
    assert not snapshot.trading_date_required
    assert all(item.availability.value == "NOT_REQUIRED" for slot in snapshot.slots for item in slot.families)


def test_context_records_have_no_analytical_or_execution_fields() -> None:
    fields = set(McxSupportingContextStore.__dict__)
    assert not fields.intersection({"readiness", "kr370", "trade_plan", "risk", "kr380", "broker"})
