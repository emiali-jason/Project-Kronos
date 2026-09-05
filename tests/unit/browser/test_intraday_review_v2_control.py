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
from kronos.intraday.review_v2 import (
    REVIEW_V2_ANSWER_IMPORT_ROUTE,
    REVIEW_V2_CHART_ROUTE,
)
from kronos.intraday.review_v2_transport import (
    REVIEW_V2_QUESTION_TRANSPORT_ROUTE,
    IntradayReviewV2Transport,
)
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_probables_v2 import _opening_inputs, _run
from tests.unit.intraday.test_probables import _member, _run as _run_v1
from tests.unit.intraday.test_review import _application
from tests.unit.intraday.test_review import _png
from tests.unit.intraday.test_review_v2 import (
    _completed_batch_payload,
    _retain_later_current_run,
    _resolver,
)


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
        transport=IntradayReviewV2Transport(
            question_outbox=(tmp_path / "questions").resolve(),
            answer_inbox=(tmp_path / "answers").resolve(),
        ),
        visual_identity_resolver=_resolver(run.analysis_boundary),
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
    already_current = control.execute_document(
        _payload(run, "REVIEW-V2-REQUEST-002")
    )
    snapshot = application.snapshot()

    assert first["outcome"] == "COMPLETE"
    assert first["cycle_count"] == first["chart_required_count"] == 1
    assert first["review_pack_count"] == first["question_pack_count"] == 0
    assert second["idempotent"] is True
    assert second["currentization_state"] == "REQUEST_REPLAY"
    assert second["cycle_identities"] == first["cycle_identities"]
    assert already_current["outcome"] == "COMPLETE"
    assert already_current["idempotent"] is True
    assert already_current["currentization_state"] == "ALREADY_CURRENT"
    assert already_current["cycle_identities"] == first["cycle_identities"]
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
    assert unknown["failure_stage"] == "PROBABLES_CURRENTNESS"
    assert unknown["failure_reason"] == "INTRADAY_REVIEW_NOT_CURRENT"
    assert len(application.snapshot().candidates) == 1

    mismatch_payload = {
        **_payload(run, "REVIEW-V2-REQUEST-MISMATCH"),
        "expected_methodology_checksum": "WRONG",
    }
    mismatch = control.execute_document(mismatch_payload)
    assert mismatch["outcome"] == "FAILED"
    assert mismatch["failure_stage"] == "PROBABLES_CURRENTNESS"
    assert mismatch["failure_reason"] == "INTRADAY_REVIEW_NOT_CURRENT"


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

    assert page is not None and "LOAD FRESH REVIEW" in page.body
    assert "NEW PROBABLES AVAILABLE" in page.body
    assert run.run_identity in page.body
    assert "PHASE-A REVIEW · PROBABLES V2/V2.1" in page.body
    assert application.snapshot().candidates == ()
    assert status is not None and json.loads(status.body)["state"] == "NOT_YET_RUN"
    status_document = json.loads(status.body)
    assert status_document["currentness_state"] == "REVIEW_ABSENT"
    assert status_document["current_probables_run_identity"] == run.run_identity
    assert status_document["current_probables_pointer_integrity"] is not None
    assert status_document["current_probables_candidate_population_identity"].startswith(
        "INTRADAY-REVIEW-V2-CANDIDATE-POPULATION-"
    )
    assert status_document["current_probables_candidate_count"] == 1
    assert status_document["is_review_current"] is False

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
    assert "REVIEW CURRENT" in restored.body
    assert "LOAD FRESH REVIEW" not in restored.body


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


def test_browser_detects_new_current_probables_from_store_not_workstation_cache(
    tmp_path: Path,
) -> None:
    run_a, application, control = _control(tmp_path / "v2")
    v1 = _application(tmp_path / "v1", [_run_v1((_member("V1-FIXTURE"),))])
    assert control.execute_document(_payload(run_a))["outcome"] == "COMPLETE"
    run_b = _retain_later_current_run(application)
    routes = IntradayBrowserRoutes(
        _Workstation(run_a),
        review=v1,
        review_v2_control=control,
    )

    page = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    assert page is not None
    assert "NEW PROBABLES AVAILABLE" in page.body
    assert "LOAD FRESH REVIEW" in page.body
    assert run_a.run_identity in page.body
    assert run_b.run_identity in page.body
    status = control.status_document()
    assert status["currentness_state"] == "NEW_PROBABLES_AVAILABLE"
    assert status["current_probables_run_identity"] == run_b.run_identity
    assert status["current_review_probables_run_identity"] == run_a.run_identity
    assert status["current_probables_candidate_count"] == 1
    assert status["current_review_candidate_count"] == 1

    stale = routes.handle_post(
        BrowserPostRequest(
            REVIEW_V2_CREATE_ROUTE,
            {},
            "application/json",
            json.dumps(_payload(run_a, "REVIEW-V2-STALE-BROWSER")).encode(),
        ),
        _snapshot,
    )
    assert stale is not None and stale.status.value == 503
    assert json.loads(stale.body)["failure_reason"] == "INTRADAY_REVIEW_NOT_CURRENT"
    assert application.review_store.load_current().probables_run_identity == run_a.run_identity  # type: ignore[union-attr]

    loaded = routes.handle_post(
        BrowserPostRequest(
            REVIEW_V2_CREATE_ROUTE,
            {},
            "application/json",
            json.dumps(_payload(run_b, "REVIEW-V2-CURRENT-BROWSER")).encode(),
        ),
        _snapshot,
    )
    assert loaded is not None and loaded.status.value == 200
    assert json.loads(loaded.body)["currentization_state"] == "CURRENTIZED"
    restored = routes.handle_get(
        BrowserGetRequest("/intraday/review", {}), _snapshot
    )
    assert restored is not None
    assert "REVIEW CURRENT" in restored.body
    assert "LOAD FRESH REVIEW" not in restored.body
    assert "CHART REQUIRED" in restored.body


def test_browser_absent_current_probables_is_inert_and_hides_intake_control(
    tmp_path: Path,
) -> None:
    run, original, _ = _control(tmp_path / "source")
    original.create_eligible_cycles(run)
    prior_pointer = original.review_store.load_current()
    application = IntradayReviewV2Application(
        probables_store=ProbablesV2Store((tmp_path / "empty-probables").resolve()),
        review_store=original.review_store,
    )
    control = IntradayReviewV2OperationalControl(
        application,
        ReviewV2OperationProvenanceStore(original.review_store.root),
        process_identity=lambda: "KRONOS-BACKEND-PID-TEST",
    )
    v1 = _application(tmp_path / "v1", [_run_v1((_member("V1-FIXTURE"),))])
    routes = IntradayBrowserRoutes(
        _Workstation(run),
        review=v1,
        review_v2_control=control,
    )

    page = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    assert page is not None
    assert "NO CURRENT PROBABLES AVAILABLE" in page.body
    assert "LOAD FRESH REVIEW" not in page.body
    assert application.review_store.load_current() == prior_pointer
    assert control.status_document()["last_operation"] is None


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


def test_browser_creates_one_v2_combined_question_transport_after_chart_ready(
    tmp_path: Path,
) -> None:
    run, application, control = _control(tmp_path / "v2")
    v1 = _application(tmp_path / "v1", [_run_v1((_member("V1-FIXTURE"),))])
    routes = IntradayBrowserRoutes(
        _Workstation(run), review=v1, review_v2_control=control
    )
    assert control.execute_document(_payload(run))["outcome"] == "COMPLETE"
    cycle = application.snapshot().candidates[0].cycle_identity
    uploaded = routes.handle_post(
        BrowserPostRequest(
            REVIEW_V2_CHART_ROUTE,
            {"cycle": [cycle]},
            "image/png",
            _png(81),
        ),
        _snapshot,
    )
    assert uploaded is not None and uploaded.status.value == 200
    assert "CREATE V2 COMBINED QUESTION PDF" in uploaded.body

    created = routes.handle_post(
        BrowserPostRequest(
            REVIEW_V2_QUESTION_TRANSPORT_ROUTE,
            {},
            "application/x-www-form-urlencoded",
            b"",
        ),
        _snapshot,
    )
    assert created is not None and created.status.value == 200
    assert "V2 QUESTION TRANSPORT READY" in created.body
    assert "CURRENT QUESTION PACK:" in created.body
    assert "EXPECTED ANSWER:" in created.body
    assert "CANDIDATES: 1" in created.body
    snapshot = application.snapshot()
    assert snapshot.review_batch_identity is not None
    assert snapshot.question_transport_identity is not None


def test_browser_imports_one_exact_v2_batch_and_projects_visual_readiness(
    tmp_path: Path,
) -> None:
    run, application, control = _control(tmp_path / "v2")
    v1 = _application(tmp_path / "v1", [_run_v1((_member("V1-FIXTURE"),))])
    routes = IntradayBrowserRoutes(
        _Workstation(run), review=v1, review_v2_control=control
    )
    assert control.execute_document(_payload(run))["outcome"] == "COMPLETE"
    cycle = application.snapshot().candidates[0].cycle_identity
    application.upload_chart(
        cycle, media_type="image/png", payload=_png(93)
    )
    transport = application.create_combined_question_transport()
    payload = _completed_batch_payload(
        transport.answer_template_path, "Reliance Industries Ltd"
    )
    response = routes.handle_post(
        BrowserPostRequest(
            REVIEW_V2_ANSWER_IMPORT_ROUTE,
            {},
            "application/json",
            payload,
        ),
        _snapshot,
    )
    assert response is not None and response.status.value == 200
    assert "Answer · IMPORTED" in response.body
    assert "Visual Identity · MATCH" in response.body
    assert "Visual Evidence · READY" in response.body
    assert "Reliance Industries Ltd" in response.body
    assert "NSE-EQ-RELIANCE" in response.body

    rejected = routes.handle_post(
        BrowserPostRequest(
            REVIEW_V2_ANSWER_IMPORT_ROUTE,
            {"filename": ["not-authority.json"]},
            "application/json",
            payload,
        ),
        _snapshot,
    )
    assert rejected is not None and rejected.status.value == 400
