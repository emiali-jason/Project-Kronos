from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from enum import StrEnum
import json
from pathlib import Path
from threading import Thread

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import pytest

from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_visual_v3 import SwingVisualV3ReviewCycle
from kronos.application.swing_visual_v3_live import SwingVisualV3LiveWorkflow
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server
from kronos.configuration.pdf_visual_review import PdfVisualReviewConfiguration
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.native_readiness_v3 import NativeLayer2ReadinessV3Store
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.swing.v1.pdf_visual_review import (
    BEGIN_GOVERNED_ANSWER_DATA,
    END_GOVERNED_ANSWER_DATA,
    PdfReviewTransportError,
)
from kronos.swing.v1.pdf_visual_review_v3_live import (
    VisualV3PdfRecordStore,
    VisualV3PdfReviewTransport,
)
from kronos.swing.v1.visual_evidence_v3 import (
    LocalVisualEvidenceV3Store,
    VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
    VISUAL_QUESTION_SET_V3_ID,
    VISUAL_QUESTION_SET_V3_VERSION,
)
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.browser.test_browser_server import _request as _browser_request
from tests.unit.swing.v1.test_native_review import _evidence_run
from tests.unit.swing.v1.test_pdf_visual_review import NOW, _workflow
from tests.unit.swing.v1.test_visual_evidence_v3 import _response


def _live(tmp_path: Path) -> tuple[NativeReviewWorkflow, object, SwingVisualV3LiveWorkflow]:
    native, _ = _workflow(tmp_path / "native")
    facts = _evidence_run()[0]
    cycle = SwingVisualV3ReviewCycle(
        LocalVisualEvidenceV3Store((tmp_path / "visual-v3").resolve()),
        NativeLayer2ReadinessV3Store((tmp_path / "readiness-v3").resolve()),
    )
    configuration = PdfVisualReviewConfiguration(
        tmp_path / "V3 QUESTIONS", tmp_path / "V3 ANSWERS"
    )
    live = SwingVisualV3LiveWorkflow(
        cycle,
        VisualV3PdfReviewTransport(
            configuration,
            VisualV3PdfRecordStore((tmp_path / "v3-pdf-records").resolve()),
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
    )
    return native, facts, live


def _payload(live: SwingVisualV3LiveWorkflow, native, facts, record):  # type: ignore[no-untyped-def]
    prepared, _ = live._prepare_for_record(  # noqa: SLF001 - exact live Pack proof
        native.snapshot(), facts, native.original_chart_bytes, record
    )
    candidates = []
    for requests in prepared:
        instrument = requests[0].requirement.canonical_instrument
        candidates.append({
            "canonical_instrument": instrument,
            "observed_chart_instrument": instrument,
            "chart_revision_sha256": requests[0].chart_revision_sha256,
            "responses": [_primitive(_response(request)) for request in requests],
        })
    return {
        "schema": VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
        "manifest": {
            "review_pack_id": record.review_pack_id,
            "native_run_identity": record.native_run_identity,
            "question_set_identity": VISUAL_QUESTION_SET_V3_ID,
            "question_set_version": VISUAL_QUESTION_SET_V3_VERSION,
            "answer_schema": VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
            "candidate_population": [
                {
                    "canonical_instrument": item.canonical_instrument,
                    "chart_revision_sha256": item.chart_revisions[0][1],
                }
                for item in record.candidate_packs
            ],
        },
        "candidates": candidates,
    }


def _answer_pdf(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = canvas.Canvas(str(path), pagesize=A4)
    y = A4[1] - 30
    document.setFont("Courier", 3.8)
    lines = [
        BEGIN_GOVERNED_ANSWER_DATA,
        *json.dumps(payload, indent=1, sort_keys=True).splitlines(),
        END_GOVERNED_ANSWER_DATA,
    ]
    for line in lines:
        if y < 24:
            document.showPage()
            document.setFont("Courier", 3.8)
            y = A4[1] - 30
        document.drawString(16, y, line)
        y -= 4.5
    document.save()


def _primitive(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return _primitive(asdict(value))
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def test_new_live_cycle_generates_only_v3_pack_with_exact_machine_bindings(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(
        native.snapshot(), facts, native.original_chart_bytes
    )

    assert record.question_set_identity == VISUAL_QUESTION_SET_V3_ID
    assert record.question_set_version == VISUAL_QUESTION_SET_V3_VERSION
    assert record.answer_schema == VISUAL_EVIDENCE_V3_ANSWER_SCHEMA
    assert Path(record.question_path).is_file()
    assert native.snapshot().review_pack_record is None
    assert all(len(item.machine_fact_bindings) == 4 for item in record.candidate_packs)


def test_production_server_constructs_explicit_v3_lifecycle_when_not_injected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native, facts, _ = _live(tmp_path)
    configuration = PdfVisualReviewConfiguration(
        tmp_path / "SERVER V3 QUESTIONS", tmp_path / "SERVER V3 ANSWERS"
    )
    monkeypatch.setattr(
        "kronos.browser.server.load_or_provision_pdf_visual_review_configuration",
        lambda: configuration,
    )
    run = _evidence_run()[1]
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=native,
    )
    try:
        assert type(server.visual_v3) is SwingVisualV3ReviewCycle
        assert type(server.visual_v3_live) is SwingVisualV3LiveWorkflow
        assert server.visual_v3_live.cycle is server.visual_v3
        assert server.native_review_version() == "V3"
    finally:
        server.server_close()


def test_v3_answer_persists_v3_evidence_and_readiness_without_v2_store(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    answer = live.transport.configuration.answer_directory / record.expected_answer_filename
    _answer_pdf(answer, _payload(live, native, facts, record))

    imports = live.upload(native.snapshot(), facts, native.original_chart_bytes)

    assert imports[-1].consumed
    assert len(live.cycle.completed_snapshot()) == len(record.candidate_packs)
    assert len(tuple((tmp_path / "visual-v3").rglob("*.json"))) == 4 * len(
        record.candidate_packs
    )
    assert len(tuple((tmp_path / "readiness-v3").rglob("*.json"))) == len(
        record.candidate_packs
    )
    assert not tuple(native.evidence_root.rglob("*visual-v2*"))


def test_v2_answer_is_rejected_for_v3_pack_without_fallback(tmp_path: Path) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    payload = _payload(live, native, facts, record)
    payload["schema"] = "KRONOS-SWING-V1-GOVERNED-PDF-ANSWER-V0"
    answer = live.transport.configuration.answer_directory / record.expected_answer_filename
    _answer_pdf(answer, payload)

    with pytest.raises(PdfReviewTransportError, match="ANSWER_VERSION_MISMATCH"):
        live.upload(native.snapshot(), facts, native.original_chart_bytes)
    assert not live.cycle.completed_snapshot()
    assert native.snapshot().review_pack_record is None


def test_v3_answer_is_rejected_for_historical_v2_pack(tmp_path: Path) -> None:
    native, transport = _workflow(tmp_path / "historical-v2")
    record = native.generate_review_pack()
    answer = transport.configuration.answer_directory / record.expected_answer_filename
    _answer_pdf(answer, {
        "schema": VISUAL_EVIDENCE_V3_ANSWER_SCHEMA,
        "manifest": {},
        "candidates": [],
    })

    with pytest.raises(PdfReviewTransportError):
        native.upload_review_answer()
    assert not native.snapshot().readiness_records


def test_wrong_run_machine_snapshot_fails_closed_before_pack_creation(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    wrong = object.__new__(type(facts))
    for field in facts.__dataclass_fields__:
        object.__setattr__(wrong, field, getattr(facts, field))
    object.__setattr__(wrong, "run_identity", "SWING-RUN-" + "F" * 32)

    with pytest.raises(PdfReviewTransportError, match="SAME_RUN_BINDING_INVALID"):
        live.generate(native.snapshot(), wrong, native.original_chart_bytes)
    assert live.snapshot(native.snapshot().native_run_identity).review_pack is None


def test_production_server_selects_v3_and_restores_exact_completed_cycle(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    answer = live.transport.configuration.answer_directory / record.expected_answer_filename
    _answer_pdf(answer, _payload(live, native, facts, record))
    live.upload(native.snapshot(), facts, native.original_chart_bytes)
    run = _evidence_run()[1]
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=native,
        visual_v3_live=live,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert server.native_review_version() == "V3"
        status, _, opportunities = _browser_request(
            server, "GET", "/swing/opportunities"
        )
        assert status == 200
        assert "1H PDH/PDL" not in opportunities
        assert "Confluence Zone" not in opportunities
        status, _, review = _browser_request(server, "GET", "/swing/v1-review")
        assert status == 200
        assert "SWING-V1-VISUAL-QUESTION-SET-V3 3.0" in review
        assert "V3 REVIEW EVIDENCE IMPORTED" in review
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    restored_cycle = SwingVisualV3ReviewCycle(
        LocalVisualEvidenceV3Store((tmp_path / "visual-v3").resolve()),
        NativeLayer2ReadinessV3Store((tmp_path / "readiness-v3").resolve()),
    )
    restored = SwingVisualV3LiveWorkflow(
        restored_cycle,
        VisualV3PdfReviewTransport(
            live.transport.configuration,
            VisualV3PdfRecordStore((tmp_path / "v3-pdf-records").resolve()),
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
    )
    restored.restore(native.snapshot(), facts, native.original_chart_bytes)
    assert len(restored.cycle.completed_snapshot()) == len(record.candidate_packs)


def test_historical_v2_pack_remains_v2_when_no_same_run_v3_pack(
    tmp_path: Path,
) -> None:
    native, facts, live = _live(tmp_path)
    v2_pack = native.generate_review_pack()
    run = _evidence_run()[1]
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=native,
        visual_v3_live=live,
    )
    try:
        assert v2_pack.question_set_identity != VISUAL_QUESTION_SET_V3_ID
        assert server.native_review_version() == "V2"
        assert not server.visual_v3.completed_snapshot()
    finally:
        server.server_close()
