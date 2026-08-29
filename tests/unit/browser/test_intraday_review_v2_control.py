from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
from types import SimpleNamespace

from kronos.application.intraday_review_v2 import IntradayReviewV2Application
from kronos.browser.intraday_review_v2_control import (
    REVIEW_V2_STATUS_ROUTE,
    IntradayReviewV2OperationalControl,
)
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from kronos.intraday.review_v2_operation import (
    REVIEW_V2_CREATE_REQUEST_IDENTITY,
    REVIEW_V2_CREATE_REQUEST_VERSION,
    REVIEW_V2_CREATE_ROUTE,
)
from kronos.intraday.review_v2_operation_persistence import (
    ReviewV2OperationProvenanceStore,
)
from kronos.intraday.review_v2 import REVIEW_V2_CHART_ROUTE
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_probables_v2 import _opening_inputs, _run
from tests.unit.intraday.test_probables import _member, _run as _run_v1
from tests.unit.intraday.test_review import _application
from tests.unit.intraday.test_review import _png


class _Workstation:
    def __init__(self, run) -> None:  # type: ignore[no-untyped-def]
        self._run = run

    def snapshot(self):  # type: ignore[no-untyped-def]
        return SimpleNamespace(
            probables=None,
            probables_v2=SimpleNamespace(run=self._run),
        )


def _control(tmp_path: Path):  # type: ignore[no-untyped-def]
    *_, mapping = _opening_inputs()
    run = _run(mapping)
    probables = ProbablesV2Store(tmp_path.resolve())
    probables.retain_complete(run=run, mappings=(mapping,))
    review = IntradayReviewV2Store((tmp_path / "review-v2").resolve())
    application = IntradayReviewV2Application(
        probables_store=probables,
        review_store=review,
    )
    clock_values = [run.analysis_boundary + timedelta(seconds=index) for index in range(20)]
    control = IntradayReviewV2OperationalControl(
        application,
        ReviewV2OperationProvenanceStore(review.root),
        clock=lambda: clock_values.pop(0),
        process_identity=lambda: "KRONOS-BACKEND-PID-TEST",
    )
    return run, application, control


def _payload(run, request_identity: str = "REVIEW-V2-REQUEST-001"):  # type: ignore[no-untyped-def]
    return {
        "request_identity": request_identity,
        "probables_run_identity": run.run_identity,
        "expected_methodology_identity": run.methodology.methodology_identity,
        "expected_methodology_version": run.methodology.methodology_version,
        "expected_methodology_publication_identity": run.methodology.publication_identity,
        "expected_methodology_checksum": run.methodology.payload_checksum,
        "requested_at": (run.analysis_boundary + timedelta(seconds=1)).isoformat(),
        "source": "SPONSOR_BROWSER_CONTROL",
        "contract_identity": REVIEW_V2_CREATE_REQUEST_IDENTITY,
        "contract_version": REVIEW_V2_CREATE_REQUEST_VERSION,
    }


def test_exact_run_control_creates_only_phase_a_and_is_idempotent(tmp_path: Path) -> None:
    run, application, control = _control(tmp_path)

    first = control.execute_document(_payload(run))
    second = control.execute_document(_payload(run))
    snapshot = application.snapshot()

    assert first["outcome"] == "COMPLETE"
    assert first["cycle_count"] == first["chart_required_count"] == 1
    assert first["review_pack_count"] == first["question_pack_count"] == 0
    assert second["idempotent"] is True
    assert second["cycle_identities"] == first["cycle_identities"]
    assert len(snapshot.candidates) == 1
    candidate = snapshot.candidates[0]
    assert candidate.review_state == "REVIEW_CYCLE_EXISTS"
    assert candidate.chart_state == "CHART_REQUIRED"
    assert candidate.review_pack_state == "ABSENT"
    assert candidate.question_pack_state == "ABSENT"
    assert candidate.answer_state == "NOT_IMPORTED"
    assert not (application.review_store.root / "chart-revisions").exists()
    assert not (application.review_store.root / "question-packs").exists()
    assert not (application.review_store.root / "question-batches").exists()
    assert control.status_document()["state"] == "COMPLETE"


def test_identity_conflict_unknown_run_and_methodology_mismatch_fail_closed(
    tmp_path: Path,
) -> None:
    run, application, control = _control(tmp_path)
    assert control.execute_document(_payload(run))["outcome"] == "COMPLETE"

    conflict_payload = {**_payload(run), "expected_methodology_checksum": "WRONG"}
    conflict = control.execute_document(conflict_payload)
    assert conflict["outcome"] == "REJECTED"
    assert conflict["failure_reason"] == "INTRADAY_REVIEW_V2_REQUEST_IDENTITY_CONFLICT"

    unknown_payload = {
        **_payload(run, "REVIEW-V2-REQUEST-UNKNOWN"),
        "probables_run_identity": "INTRADAY-PROBABLES-V2-RUN-UNKNOWN",
    }
    unknown = control.execute_document(unknown_payload)
    assert unknown["outcome"] == "FAILED"
    assert unknown["failure_reason"] == "INTRADAY_REVIEW_ARTIFACT_UNAVAILABLE"
    assert len(application.snapshot().candidates) == 1

    mismatch_payload = {
        **_payload(run, "REVIEW-V2-REQUEST-MISMATCH"),
        "expected_methodology_checksum": "WRONG",
    }
    mismatch = control.execute_document(mismatch_payload)
    assert mismatch["outcome"] == "FAILED"
    assert mismatch["failure_reason"] == "INTRADAY_REVIEW_INTEGRITY_INVALID"


def test_browser_get_is_inert_and_explicit_json_post_uses_v2_control(
    tmp_path: Path,
) -> None:
    run, application, control = _control(tmp_path / "v2")
    v1 = _application(tmp_path / "v1", [_run_v1((_member("V1-FIXTURE"),))])
    routes = IntradayBrowserRoutes(
        _Workstation(run),
        review=v1,
        review_v2_control=control,
    )

    page = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    status = routes.handle_get(BrowserGetRequest(REVIEW_V2_STATUS_ROUTE, {}), _snapshot)

    assert page is not None and "CREATE V2 REVIEW CYCLES" in page.body
    assert run.run_identity in page.body
    assert "PHASE-A REVIEW · PROBABLES V2/V2.1" in page.body
    assert application.snapshot().candidates == ()
    assert status is not None and json.loads(status.body)["state"] == "NOT_YET_RUN"

    response = routes.handle_post(
        BrowserPostRequest(
            REVIEW_V2_CREATE_ROUTE,
            {},
            "application/json",
            json.dumps(_payload(run)).encode(),
        ),
        _snapshot,
    )
    assert response is not None and response.status.value == 200
    assert json.loads(response.body)["cycle_count"] == 1
    restored = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    assert restored is not None
    assert "REVIEW CYCLE EXISTS" in restored.body
    assert "CHART REQUIRED" in restored.body
    assert "Review Pack · ABSENT" in restored.body
    assert "Question Pack · ABSENT" in restored.body


def test_malformed_request_and_held_only_population_create_no_pointer(
    tmp_path: Path,
) -> None:
    run, application, control = _control(tmp_path)
    malformed = control.execute_document({"request_identity": "BAD"})
    assert malformed["outcome"] == "REJECTED"
    assert application.review_store.load_current() is None

    # The application-level held/unavailable exclusion remains covered by the
    # V2 Review suite; an exact unknown run cannot silently fall back either.
    unknown = control.execute_document({
        **_payload(run, "REVIEW-V2-NO-FALLBACK"),
        "probables_run_identity": "INTRADAY-PROBABLES-V2-RUN-NOT-PRESENT",
    })
    assert unknown["outcome"] == "FAILED"
    assert application.review_store.load_current() is None


def test_concurrent_conflict_fails_closed_and_remains_retryable(tmp_path: Path) -> None:
    run, application, control = _control(tmp_path)
    request = _payload(run, "REVIEW-V2-CONCURRENT-001")

    assert control._operation_lock.acquire(blocking=False)  # noqa: SLF001
    try:
        conflict = control.execute_document(request)
    finally:
        control._operation_lock.release()  # noqa: SLF001

    assert conflict["outcome"] == "REJECTED"
    assert conflict["failure_stage"] == "CONCURRENCY"
    assert conflict["failure_reason"] == "INTRADAY_REVIEW_V2_OPERATION_CONFLICT"
    assert application.review_store.load_current() is None

    completed = control.execute_document(request)
    assert completed["outcome"] == "COMPLETE"
    assert completed["cycle_count"] == 1


def test_v2_browser_chart_route_is_exact_cycle_bound_and_uses_proven_transport(
    tmp_path: Path,
) -> None:
    run, application, control = _control(tmp_path / "v2")
    v1 = _application(tmp_path / "v1", [_run_v1((_member("V1-FIXTURE"),))])
    routes = IntradayBrowserRoutes(
        _Workstation(run), review=v1, review_v2_control=control
    )
    assert control.execute_document(_payload(run))["outcome"] == "COMPLETE"
    cycle = application.snapshot().candidates[0].cycle_identity

    page = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    assert page is not None
    assert (
        f'data-upload-url="{REVIEW_V2_CHART_ROUTE}?cycle={cycle}"'
        in page.body
    )
    assert "PASTE / UPLOAD CHART" in page.body
    assert "target.addEventListener('paste'" in page.body
    assert "fetch(target.dataset.uploadUrl" in page.body

    uploaded = routes.handle_post(
        BrowserPostRequest(
            REVIEW_V2_CHART_ROUTE,
            {"cycle": [cycle]},
            "image/png",
            _png(61),
        ),
        _snapshot,
    )
    assert uploaded is not None and uploaded.status.value == 200
    assert "CHART READY" in uploaded.body
    assert "Chart Revision · REV 001" in uploaded.body
    assert control.status_document()["chart_required_count"] == 0

    wrong = routes.handle_post(
        BrowserPostRequest(
            REVIEW_V2_CHART_ROUTE,
            {"cycle": ["INTRADAY-REVIEW-V2-CYCLE-WRONG"]},
            "image/png",
            _png(62),
        ),
        _snapshot,
    )
    assert wrong is not None and wrong.status.value == 409
    invalid = routes.handle_post(
        BrowserPostRequest(
            REVIEW_V2_CHART_ROUTE,
            {"cycle": [cycle]},
            "image/png",
            b"corrupt",
        ),
        _snapshot,
    )
    assert invalid is not None and invalid.status.value == 400
