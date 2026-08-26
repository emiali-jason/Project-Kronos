from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_probables import _member, _run
from tests.unit.intraday.test_review import _application, _png


class _Workstation:
    def snapshot(self):  # type: ignore[no-untyped-def]
        return SimpleNamespace(probables=None)


def test_intraday_review_browser_flow_is_bounded_and_get_is_side_effect_free(tmp_path: Path) -> None:
    run = _run((_member("WIPRO"),))
    current = [run]
    application = _application(tmp_path, current)
    routes = IntradayBrowserRoutes(_Workstation(), review=application)

    initial = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    assert initial is not None
    assert "Intraday Native Review" in initial.body
    assert "WIPRO" in initial.body and "LONG" in initial.body
    assert "START REVIEW" in initial.body
    assert "CREATE PDF" not in initial.body
    assert '<button class="primary" type="submit" disabled>CREATE ALL REVIEW PDF</button>' in initial.body
    assert "UPLOAD ALL ANSWERS · NOT YET COMMISSIONED" in initial.body
    assert application.snapshot().candidates[0].cycle_identity is None

    result = run.results[0].result_identity
    started = routes.handle_post(
        BrowserPostRequest("/intraday/review/start", {"result": [result]}, "", b""),
        _snapshot,
    )
    assert started is not None and "CHART REQUIRED" in started.body
    cycle = application.snapshot().candidates[0].cycle_identity
    assert cycle is not None
    assert "TRADINGVIEW 4-CHART IMAGE" in started.body
    assert "Required: 1D · 1H · 15M · 5M" in started.body
    assert "PROBABLE CONTEXT" in started.body
    assert "CREATE PDF" not in started.body

    uploaded = routes.handle_post(
        BrowserPostRequest("/intraday/review/chart", {"cycle": [cycle]}, "image/png", _png(7)),
        _snapshot,
    )
    assert uploaded is not None and "CHART READY · REV 001" in uploaded.body
    assert "CREATE PDF" in uploaded.body
    assert '<button class="primary" type="submit">CREATE ALL REVIEW PDF</button>' in uploaded.body

    batch = routes.handle_post(
        BrowserPostRequest("/intraday/review/question-packs", {}, "", b""),
        _snapshot,
    )
    assert batch is not None
    assert "CREATE ALL REVIEW PDF · COMPLETE" in batch.body
    assert "Created <strong>1</strong>" in batch.body
    assert "INTRADAY_REVIEW_BATCH_" in batch.body

    created = routes.handle_post(
        BrowserPostRequest("/intraday/review/question-pack", {"cycle": [cycle]}, "", b""),
        _snapshot,
    )
    assert created is not None and "Question Pack</span><strong>CREATED" in created.body
    assert "Answer import NOT ACTIVE" in created.body
    assert "Readiness" not in created.body and "PAPER" not in created.body


def test_intraday_review_route_rejects_cross_binding_and_invalid_body(tmp_path: Path) -> None:
    run = _run((_member("WIPRO"), _member("LICI")))
    current = [run]
    application = _application(tmp_path, current)
    routes = IntradayBrowserRoutes(_Workstation(), review=application)
    wipro = next(item for item in run.results if item.canonical_subject_identity == "WIPRO")
    lici = next(item for item in run.results if item.canonical_subject_identity == "LICI")
    cycle = application.start_review(wipro.result_identity)

    rejected = routes.handle_post(
        BrowserPostRequest("/intraday/review/start", {"result": [lici.result_identity]}, "", b"unexpected"),
        _snapshot,
    )
    assert rejected is not None and rejected.status.value == 400
    missing = routes.handle_post(
        BrowserPostRequest("/intraday/review/chart", {"cycle": ["INTRADAY-REVIEW-CYCLE-NOT-WIPRO"]}, "image/png", _png(3)),
        _snapshot,
    )
    assert missing is not None and missing.status.value == 409
    snapshot = application.snapshot()
    assert next(item for item in snapshot.candidates if item.canonical_subject_identity == "LICI").cycle_identity is None
    assert next(item for item in snapshot.candidates if item.canonical_subject_identity == "WIPRO").chart_revision_identity is None


def test_intraday_review_clipboard_targets_are_candidate_bound_and_share_upload_path(tmp_path: Path) -> None:
    run = _run((_member("WIPRO"), _member("LICI")))
    current = [run]
    application = _application(tmp_path, current)
    routes = IntradayBrowserRoutes(_Workstation(), review=application)
    for candidate in application.snapshot().candidates:
        application.start_review(candidate.probable_result_identity)

    rendered = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    assert rendered is not None
    snapshot = application.snapshot()
    for candidate in snapshot.candidates:
        assert candidate.cycle_identity is not None
        assert rendered.body.count(
            "/intraday/review/chart?cycle=" + candidate.cycle_identity
        ) == 1
        assert (
            "Paste TradingView 1D 1H 15M 5M chart composite for "
            + candidate.canonical_subject_identity
        ) in rendered.body
    assert rendered.body.count('class="intraday-drop" role="button" tabindex="0"') == 2
    assert "document.addEventListener('paste'" not in rendered.body
    assert "target.addEventListener('paste'" in rendered.body
    assert "['image/png','image/jpeg'].includes(value.type)" in rendered.body
    assert "uploadReviewChart(target,item.getAsFile())" in rendered.body
    assert "input.addEventListener('change',()=>uploadReviewChart(target,input.files[0]))" in rendered.body
    assert ":focus-visible" in rendered.body

    rejected = routes.handle_post(
        BrowserPostRequest("/intraday/review/question-packs", {"cycle": ["unexpected"]}, "", b""),
        _snapshot,
    )
    assert rejected is not None and rejected.status.value == 400
