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
)
from kronos.swing.v1.mcx_supporting_context_pdf import McxContextPdfStore, McxContextPdfTransport
from kronos.swing.v1.pdf_visual_review import BEGIN_GOVERNED_ANSWER_DATA, END_GOVERNED_ANSWER_DATA, PdfReviewTransportError


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


def _answer(path: Path, payload: dict[str, object]) -> None:
    styles = getSampleStyleSheet()
    SimpleDocTemplate(str(path), pagesize=A4).build([
        Preformatted(BEGIN_GOVERNED_ANSWER_DATA + "\n" + json.dumps(payload, indent=2) + "\n" + END_GOVERNED_ANSWER_DATA, styles["Code"])
    ])


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
