from pathlib import Path

from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.views import render_v1_review
from kronos.swing.v1 import LocalTradingViewEvidenceStore
from tests.unit.browser.test_browser_views import _ready
from tests.unit.swing.v1.test_pdf_visual_review import _workflow


def test_native_review_pdf_controls_and_a_to_z_presentation(tmp_path: Path) -> None:
    workflow, _ = _workflow(tmp_path, candidate_count=7)
    snapshot = workflow.snapshot()
    original = tuple(item.canonical_instrument for item in snapshot.requirements)
    html = render_v1_review(
        _ready(),
        SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ).snapshot(),
        snapshot,
    )

    assert "REFRESH REVIEW" in html
    assert "CREATE ALL REVIEW PDF" in html
    assert html.count("CREATE PDF") == 7
    assert "/swing/v1/native-review-pack" in html
    assert tuple(sorted(original)) == tuple(
        sorted(original, key=lambda item: html.index(f">{item}<"))
    )
    assert "ANALYZE ALL" not in html
    assert "ANALYZE NATIVE REVIEW" not in html


def test_generated_pack_switches_control_to_upload_answer(tmp_path: Path) -> None:
    workflow, _ = _workflow(tmp_path)
    record = workflow.generate_review_pack()
    html = render_v1_review(
        _ready(),
        SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ).snapshot(),
        workflow.snapshot(),
    )

    assert "UPLOAD ANSWER" in html
    assert "/swing/v1/native-review-answer" in html
    assert record.question_filename in html
    assert "WAITING FOR CHART ANALYST" in html
