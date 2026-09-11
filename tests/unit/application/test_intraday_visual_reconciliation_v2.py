from datetime import timedelta

from kronos.application.intraday_visual_reconciliation_v2 import (
    IntradayVisualReconciliationV2Application,
)
from kronos.browser.intraday_views import _review_v2_candidate
from kronos.browser.intraday_visual_reconciliation_v2_control import (
    IntradayVisualReconciliationV2OperationalControl,
)
from kronos.browser.product_routes import BrowserPostRequest
from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
from kronos.intraday.visual_reconciliation_v2_persistence import VisualReconciliationStore
from tests.unit.intraday.test_review import _png
from tests.unit.intraday.test_review_v2_individual_inbox import (
    _completed,
    _fixture,
)
from tests.unit.browser.test_intraday_review_workflow import _routes
from tests.unit.browser.test_product_route_isolation import _snapshot


def _application(tmp_path):
    run, review = _fixture(tmp_path, ("BDL",), correspondence=True)
    cycle = review.snapshot().candidates[0]
    review.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(77))
    transport = review.create_individual_question_transport(cycle.cycle_identity)
    answer = review._transport.answer_inbox / transport.transport.expected_answer_filename
    answer.write_bytes(_completed(transport.answer_template_path))
    assert review.import_expected_answer(cycle.cycle_identity).imported_count == 1
    return run, review, IntradayVisualReconciliationV2Application(
        review=review,
        review_store=review.review_store,
        paired_store=IntradayMcxPairedReviewStore((tmp_path / "paired").resolve()),
        store=VisualReconciliationStore((tmp_path / "wo07f").resolve()),
        clock=lambda: run.analysis_boundary + timedelta(minutes=2),
    )


def test_current_projection_is_read_only_and_exact(tmp_path):
    _, review, application = _application(tmp_path)
    before = tuple(application.store.root.rglob("*"))
    projected = application.evaluate_current_read_only()
    assert projected == (
        {
            "canonical_subject_identity": "NSE-EQ-BDL",
            "outcome": "CONFIRMED",
            "reason_codes": (),
            "downstream_eligibility": "ELIGIBLE_FOR_WO10_EVALUATION",
        },
    )
    status = application.status()
    assert status.current_review_pointer == review.snapshot().current_pointer_identity
    assert status.eligible_count == 1
    assert status.reconciled_count == 0
    assert tuple(application.store.root.rglob("*")) == before


def test_explicit_batch_is_candidate_isolated_persisted_and_idempotent(tmp_path):
    _, review, application = _application(tmp_path)
    result = application.reconcile_all_ready()
    assert result["outcome"] == "COMPLETED"
    assert result["success_count"] == 1
    assert result["results"][0]["outcome"] == "CONFIRMED"
    status = application.status()
    assert status.reconciled_count == 1
    assert status.candidates[0].outcome == "CONFIRMED"
    assert application.reconcile_all_ready()["results"][0]["state"] == "ALREADY_RECONCILED"
    assert review.snapshot().candidates[0].answer_state == "IMPORTED"


def test_review_card_shows_truthful_outcome_conditions_and_eligibility(tmp_path):
    _, review, application = _application(tmp_path)
    application.reconcile_all_ready()
    candidate = review.snapshot().candidates[0]
    status = application.status().document()["candidates"][0]
    html = _review_v2_candidate(candidate, 1, "run", status)
    assert "WO-07F · <strong>CONFIRMED</strong>" in html
    assert "ELIGIBLE_FOR_WO10_EVALUATION" in html
    assert "BUY" not in html and "SELL" not in html


def test_reconcile_all_route_dispatches_only_to_wo07f(tmp_path):
    _, _, _, routes = _routes(tmp_path)

    class Application:
        calls = 0

        def reconcile_all_ready(self):
            self.calls += 1
            return {"outcome": "COMPLETED", "results": ()}

    application = Application()
    control = object.__new__(IntradayVisualReconciliationV2OperationalControl)
    control._application = application
    routes._visual_reconciliation_v2_control = control
    response = routes.handle_post(
        BrowserPostRequest(
            "/intraday/review/reconcile-all", {}, "application/json", b""
        ),
        _snapshot,
    )
    assert response.status == 200
    assert application.calls == 1


def test_partial_batch_retry_preserves_success_and_adds_only_new_result(tmp_path):
    run, review = _fixture(tmp_path, ("BDL", "NTPC"), correspondence=True)
    candidates = review.snapshot().candidates
    for marker, candidate in enumerate(candidates, start=80):
        review.upload_chart(
            candidate.cycle_identity, media_type="image/png", payload=_png(marker)
        )
    first_transport = review.create_individual_question_transport(
        candidates[0].cycle_identity
    )
    first_answer = (
        review._transport.answer_inbox
        / first_transport.transport.expected_answer_filename
    )
    first_answer.write_bytes(_completed(first_transport.answer_template_path))
    assert review.import_expected_answer(candidates[0].cycle_identity).imported_count == 1
    application = IntradayVisualReconciliationV2Application(
        review=review,
        review_store=review.review_store,
        paired_store=IntradayMcxPairedReviewStore((tmp_path / "paired").resolve()),
        store=VisualReconciliationStore((tmp_path / "wo07f").resolve()),
        clock=lambda: run.analysis_boundary + timedelta(minutes=2),
    )

    partial = application.reconcile_all_ready()
    assert partial["outcome"] == "PARTIAL"
    assert partial["success_count"] == 1
    assert len(application.store.list_records()) == 1

    second_transport = review.create_individual_question_transport(
        candidates[1].cycle_identity
    )
    second_answer = (
        review._transport.answer_inbox
        / second_transport.transport.expected_answer_filename
    )
    second_answer.write_bytes(_completed(second_transport.answer_template_path))
    assert review.import_expected_answer(candidates[1].cycle_identity).imported_count == 1
    replay = application.reconcile_all_ready()
    assert [item["state"] for item in replay["results"]] == [
        "ALREADY_RECONCILED",
        "RECONCILED",
    ]
    assert len(application.store.list_records()) == 2
