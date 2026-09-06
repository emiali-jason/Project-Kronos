from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

import pytest

from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.application.swing_visual_v3_live import SwingVisualV3LiveWorkflow
from kronos.browser.server import KronosBrowserServer, create_browser_server
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.pdf_visual_review import PdfReviewTransportError
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.browser.test_browser_server import _request
from tests.unit.browser.test_swing_visual_v3_live import _live
from tests.unit.swing.v1.test_native_review import _evidence_run


def _bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }


@pytest.mark.parametrize("damage", ("missing", "changed", "unparseable"))
def test_invalid_saved_pdf_does_not_stop_browser_or_become_valid(
    tmp_path: Path, damage: str,
) -> None:
    native, facts, live = _live(tmp_path)
    record = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    pdf = Path(record.question_path)
    if damage == "missing":
        pdf.unlink()
    elif damage == "changed":
        pdf.write_bytes(pdf.read_bytes() + b"changed")
    else:
        # A matching digest must not bypass independent PDF parsing/binding.
        pdf.write_bytes(b"%PDF-1.4\ninvalid object tree\n%%EOF")
        stored = live.transport.record_store.root / "review-packs" / f"{record.review_pack_id}.json"
        payload = json.loads(stored.read_text())
        payload["record"]["question_pdf_sha256"] = sha256(pdf.read_bytes()).hexdigest()
        for candidate in payload["record"]["candidate_packs"]:
            candidate["question_pdf_sha256"] = payload["record"]["question_pdf_sha256"]
        stored.write_text(json.dumps(payload))
    before = _bytes(tmp_path)
    restored = SwingVisualV3LiveWorkflow(live.cycle, live.transport)
    snapshot = restored.snapshot(facts.run_identity)
    assert snapshot.restoration_error == "VISUAL_V3_RESTORATION_UNAVAILABLE"
    assert snapshot.review_pack is None
    assert snapshot.answer_imports == ()
    assert not snapshot.current_run
    with pytest.raises(PdfReviewTransportError, match="PDF_BINDING_INVALID"):
        live.transport.record_store.load_current()
    with pytest.raises(PdfReviewTransportError, match="RESTORATION_UNAVAILABLE"):
        restored.upload(native.snapshot(), facts, native.original_chart_bytes)
    restored.restore(native.snapshot(), facts, native.original_chart_bytes)
    assert restored.cycle.completed_snapshot() == ()
    assert _bytes(tmp_path) == before

    run = _evidence_run()[1]
    application = SwingOpportunitiesApplication(
        _Provider,
        initial_snapshot=replace(_ready(), swing_analysis_run_identity=run.run_identity),
    )
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    server = create_browser_server(
        application, port=0, native_review=native, visual_v3_live=restored,
        v1_review=SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path / "legacy")),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert server.native_review_version() == "V3"
        assert _request(server, "GET", "/status")[0] == 200
        assert _request(server, "GET", "/swing/opportunities")[0] == 200
        status, _, page = _request(server, "GET", "/swing/v1-review")
        assert status == 200
        assert "SAVED V3 REVIEW UNAVAILABLE" in page
        assert 'action="/swing/v1/native-review-answer"' not in page
        assert str(pdf) not in page
        assert "Traceback" not in page
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_restoration_failure_cannot_fall_back_to_historical_v2() -> None:
    # No native/V2 selection may be consulted while persisted V3 is invalid.
    server = SimpleNamespace(
        visual_v3_live=SimpleNamespace(restoration_error="VISUAL_V3_RESTORATION_UNAVAILABLE")
    )
    assert KronosBrowserServer.native_review_version(server) == "V3"


def test_valid_new_pack_recovers_without_rewriting_invalid_history(tmp_path: Path) -> None:
    native, facts, live = _live(tmp_path)
    old = live.generate(native.snapshot(), facts, native.original_chart_bytes)
    pdf = Path(old.question_path)
    pdf.write_bytes(b"retained damaged PDF")
    stored = live.transport.record_store.root / "review-packs" / f"{old.review_pack_id}.json"
    old_record = stored.read_bytes()
    restored = SwingVisualV3LiveWorkflow(live.cycle, live.transport)
    assert restored.restoration_error is not None
    new = restored.generate(native.snapshot(), facts, native.original_chart_bytes)
    assert new.review_pack_id != old.review_pack_id
    assert restored.restoration_error is None
    assert restored.transport.record_store.load_current() == new
    assert pdf.read_bytes() == b"retained damaged PDF"
    assert stored.read_bytes() == old_record
