"""Bounded renderer, immutable artifact lineage and startup recovery proof."""
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Spacer
from reportlab.pdfbase.pdfmetrics import stringWidth
import pytest

from kronos.swing.v1.pdf_contract_layout_v3 import (
    contract_block, measured_lines, USABLE_WIDTH, PAGE_MARGIN, FONT_SIZE, LINE_HEIGHT,
)
from kronos.swing.v1.pdf_visual_review_v3_recovery import (
    generate_successor, render_successor_bytes, supersede_selected_artifact,
    artifact_projection, validate_successor,
)
from kronos.swing.v1.pdf_visual_review_v3_live import _primitive
from kronos.application.swing_visual_v3_live import SwingVisualV3LiveWorkflow
from tests.unit.browser.test_swing_visual_v3_live import _live
from tests.unit.browser.test_runtime01 import server_for
from tests.unit.provider.test_connection_governance import governance, GENERATION
from tests.unit.intraday.test_live_shadow import service
from tests.unit.intraday.test_live_shadow_epochs import restart, inventory
from kronos.browser.runtime_state import complete_startup
from tests.unit.swing.v1.pdf_layout_assertions import text_bounds


@pytest.mark.parametrize("value", [
    "short", "x" * 500, "KRONOS-VERY-LONG-IDENTITY-" * 80,
    "A truthful bounded explanation of visible context. " * 25,
    json.dumps({"a": "long " * 50, "b": "identity" * 70}),
    "  ", "", "first\nsecond\nthird",
])
def test_wrap_preserves_every_non_newline_character_and_measured_width(value):
    lines = measured_lines(value)
    assert "".join(lines) == value.replace("\n", "")
    assert all(stringWidth(line, "Courier", FONT_SIZE) <= USABLE_WIDTH for line in lines)


def test_too_narrow_block_fails_closed():
    with pytest.raises(ValueError, match="WIDTH_INVALID"):
        measured_lines("text", width=0)


@pytest.mark.parametrize("remaining", [0, LINE_HEIGHT - 0.01, LINE_HEIGHT, 2 * LINE_HEIGHT])
def test_whole_line_page_break_threshold(remaining):
    block = contract_block("\n".join(["line"] * 10))
    pieces = block.split(USABLE_WIDTH, remaining)
    if remaining < LINE_HEIGHT:
        assert pieces == []
    else:
        assert len(pieces[0].lines) == int(remaining // LINE_HEIGHT)
        assert pieces[0].lines + pieces[1].lines == block.lines


@pytest.mark.parametrize("near_bottom", [False, True])
def test_long_blocks_paginate_without_clipping_or_missing_values(near_bottom):
    value = json.dumps({str(i): "ORDERLY_PULLBACK " * 20 for i in range(35)}, indent=2)
    def render():
        output = BytesIO()
        doc = SimpleDocTemplate(output, pagesize=A4, invariant=1,
                                leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
                                topMargin=PAGE_MARGIN, bottomMargin=PAGE_MARGIN)
        story = ([Spacer(1, 650)] if near_bottom else []) + [contract_block(value)]
        doc.build(story)
        return output.getvalue()
    data = render()
    assert data == render()
    reader = PdfReader(BytesIO(data), strict=True)
    assert len(reader.pages) > 1
    extracted = "".join(p.extract_text() for p in reader.pages)
    assert "".join(extracted.split()) == "".join(value.split())
    for page in reader.pages:
        for text, x, y, right, size in text_bounds(page):
            assert PAGE_MARGIN <= x <= right <= A4[0] - PAGE_MARGIN
            assert PAGE_MARGIN <= y - 0.25 * size
            assert y + size <= A4[1] - PAGE_MARGIN



@pytest.fixture
def recovery_case(tmp_path):
    native, facts, live = _live(tmp_path)
    original = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    prepared, _ = live._prepare(native.snapshot(), facts, native.original_chart_bytes,
                                None, request_timestamp=original.created_at)
    old = Path(original.question_path)
    old.write_bytes(b"%PDF-1.4\nMALFORMED STALE KRONOS-V3-REVIEW-" + b"A" * 32)
    digest = sha256(old.read_bytes()).hexdigest()
    original = replace(original, question_pdf_sha256=digest, candidate_packs=tuple(
        replace(c, question_pdf_sha256=digest) for c in original.candidate_packs))
    store = live.transport.record_store
    canonical = store.root / "review-packs" / f"{original.review_pack_id}.json"
    payload = json.loads(canonical.read_text()); payload["record"] = _primitive(original)
    canonical.write_text(json.dumps(payload))
    successor = generate_successor(original, prepared, tmp_path / "RECOVERY_QUESTIONS.pdf")
    args = dict(prepared=prepared,
                sources=[{"path": str(canonical), "sha256": sha256(canonical.read_bytes()).hexdigest()}],
                authorization="ISOLATED_SPONSOR_RECOVERY_FIXTURE", visual_qa_sha256="b" * 64,
                created_at=original.created_at + timedelta(days=1),
                embedded_wrong_identity="KRONOS-V3-REVIEW-" + "A" * 32,
                structural_failure="ISOLATED_MALFORMED_PDF")
    return native, facts, live, original, successor, args


def publish(case):
    _, _, live, original, successor, args = case
    return supersede_selected_artifact(live.transport.record_store, original, successor, **args)


def test_exact_restoration_idempotent_lineage_and_runtime_health(recovery_case, tmp_path):
    native, facts, live, original, successor, args = recovery_case
    store = live.transport.record_store
    before = inventory(store.root)
    old_bytes = Path(original.question_path).read_bytes()
    result = publish(recovery_case)
    assert result["predecessor_sha256"] == original.question_pdf_sha256
    assert result["successor_sha256"] == successor.question_pdf_sha256
    assert store.load_current() == successor
    assert Path(original.question_path).read_bytes() == old_bytes
    for name, value in before.items():
        if not name.endswith("current-review-pack.json"):
            assert inventory(store.root)[name] == value
    assert len(list((store.root / "review-packs").glob("*.json"))) == 1
    assert len(list((store.root / "selection-history").glob("*.json"))) == 1
    after = inventory(store.root)
    assert publish(recovery_case) == result
    assert inventory(store.root) == after
    restored = SwingVisualV3LiveWorkflow(live.cycle, live.transport)
    assert restored.restoration_error is None
    restored.restore(native.snapshot(), facts, native.original_chart_bytes)
    assert restored.cycle.completed_snapshot() == ()
    assert store.replay(args["prepared"], original.scope, original.skipped) == successor
    assert inventory(store.root) == after
    old_shadow, _, _ = service(tmp_path / "shadow")
    shadow_before = inventory(tmp_path / "shadow")
    current = restart(tmp_path / "shadow", old_shadow, changed=False)
    server = server_for(governance(tmp_path / "governance", maintenance=GENERATION))
    server.visual_v3_live = restored
    complete_startup(server, current)
    assert server.connection_governance.startup_state == "READY"
    assert not server.connection_governance.maintenance_active
    assert current.status()["acceptance_disposition"] == "EXISTING_ACCEPTANCE_RESTORED"
    assert inventory(tmp_path / "shadow") == shadow_before
    assert server.swing_monitoring_hub.active_session_count == 0
    after = inventory(tmp_path)
    complete_startup(server, current)
    assert inventory(tmp_path) == after


@pytest.mark.parametrize("fault", ["original", "successor", "source", "checksum", "missing", "identity"])
def test_restoration_rejects_tampering_without_repair(recovery_case, fault):
    _, facts, live, original, successor, args = recovery_case
    result = publish(recovery_case)
    store = live.transport.record_store
    path = store.root / "artifact-recoveries" / f"{result['checksum']}.json"
    if fault == "original":
        Path(original.question_path).write_bytes(b"changed")
    elif fault == "successor":
        Path(successor.question_path).write_bytes(b"changed")
    elif fault == "source":
        Path(args["sources"][0]["path"]).write_bytes(b"{}")
    elif fault == "missing":
        path.unlink()
    else:
        data = json.loads(path.read_text())
        data["checksum" if fault == "checksum" else "review_pack_id"] = "c" * 64
        path.write_text(json.dumps(data))
    before = inventory(store.root)
    restored = SwingVisualV3LiveWorkflow(live.cycle, live.transport)
    assert restored.restoration_error == "VISUAL_V3_RESTORATION_UNAVAILABLE"
    assert inventory(store.root) == before


@pytest.mark.parametrize("fault", ["timestamp", "population", "order", "version"])
def test_source_conflict_prevents_render(recovery_case, fault, tmp_path):
    _, _, _, original, _, args = recovery_case
    prepared = args["prepared"]
    if fault == "timestamp":
        prepared = tuple(tuple(replace(q, request_timestamp=q.request_timestamp + timedelta(seconds=1)) for q in group) for group in prepared)
    elif fault == "population":
        prepared = ()
    elif fault == "order":
        prepared = tuple(tuple(reversed(group)) for group in prepared)
    else:
        prepared = tuple(tuple(replace(q, question_set_version="3.0") for q in group) for group in prepared)
    with pytest.raises(ValueError):
        generate_successor(original, prepared, tmp_path / "BAD_QUESTIONS.pdf")
    assert not (tmp_path / "BAD_QUESTIONS.pdf").exists()


def test_existing_successor_and_original_paths_never_overwritten(recovery_case):
    _, _, _, original, successor, args = recovery_case
    for path in (original.question_path, successor.question_path):
        before = Path(path).read_bytes()
        with pytest.raises((ValueError, FileExistsError)):
            generate_successor(original, args["prepared"], Path(path))
        assert Path(path).read_bytes() == before


def test_different_valid_pdf_cannot_substitute_for_exact_render(recovery_case):
    _, _, live, original, successor, args = recovery_case
    path = Path(successor.question_path)
    path.write_bytes(path.read_bytes() + b"\nextra bytes")
    altered = artifact_projection(original, path, sha256(path.read_bytes()).hexdigest())
    validate_successor(altered)
    before = inventory(live.transport.record_store.root)
    with pytest.raises(ValueError, match="CONTENT_CONFLICT"):
        supersede_selected_artifact(live.transport.record_store, original, altered, **args)
    assert inventory(live.transport.record_store.root) == before


def test_failed_pointer_commit_preserves_predecessor_and_retry_is_safe(recovery_case, monkeypatch):
    _, _, live, original, successor, _ = recovery_case
    import kronos.swing.v1.pdf_visual_review_v3_recovery as module
    real = module._atomic_json
    monkeypatch.setattr(module, "_atomic_json", lambda *a, **k: (_ for _ in ()).throw(OSError("fixture")))
    with pytest.raises(OSError):
        publish(recovery_case)
    pointer = json.loads((live.transport.record_store.root / "current-review-pack.json").read_text())
    assert "artifact_recovery_sha256" not in pointer
    monkeypatch.setattr(module, "_atomic_json", real)
    publish(recovery_case)
    assert live.transport.record_store.load_current() == successor
