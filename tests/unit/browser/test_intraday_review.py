from __future__ import annotations

from dataclasses import replace
import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.intraday_views import render_intraday_review
from kronos.browser.views import _chart_upload_script
from kronos.browser.product_routes import BrowserGetRequest, BrowserPostRequest
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_probables import _member, _run
from tests.unit.intraday.test_review import _application, _png
from tests.unit.intraday.test_review_answer import _document
from kronos.intraday.review_answer import answer_pack_filename, answer_pack_template


class _Workstation:
    def snapshot(self):  # type: ignore[no-untyped-def]
        return SimpleNamespace(probables=None)


def _store_fingerprint(root: Path) -> tuple[tuple[str, str], ...]:
    if not root.exists():
        return ()
    return tuple(
        (str(path.relative_to(root)), sha256(path.read_bytes()).hexdigest())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def test_intraday_review_browser_flow_is_bounded_and_get_is_side_effect_free(tmp_path: Path) -> None:
    run = _run((_member("WIPRO"),))
    current = [run]
    application = _application(tmp_path, current)
    routes = IntradayBrowserRoutes(_Workstation(), review=application)

    before = _store_fingerprint(application.store.root)
    initial = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    assert initial is not None
    assert "Intraday Native Review" in initial.body
    assert "WIPRO" in initial.body and "LONG" in initial.body
    assert "START REVIEW" not in initial.body
    assert "CHART REQUIRED" in initial.body
    assert "TRADINGVIEW 4-CHART IMAGE" in initial.body
    assert "Required: 1D · 1H · 15M · 5M" in initial.body
    assert 'data-upload-url="/intraday/review/chart?result=' in initial.body
    assert "CREATE PDF" not in initial.body
    assert '<button class="primary" type="submit" disabled>CREATE ALL REVIEW PDF</button>' in initial.body
    assert "UPLOAD ALL ANSWERS" in initial.body
    assert 'action="/intraday/review/answers"' in initial.body
    assert application.snapshot().candidates[0].cycle_identity is None
    assert _store_fingerprint(application.store.root) == before

    result = run.results[0].result_identity
    uploaded = routes.handle_post(
        BrowserPostRequest("/intraday/review/chart", {"result": [result]}, "image/png", _png(7)),
        _snapshot,
    )
    assert uploaded is not None and "CHART READY · REV 001" in uploaded.body
    cycle = application.snapshot().candidates[0].cycle_identity
    assert cycle is not None
    assert "PROBABLE CONTEXT" in uploaded.body
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
    assert "Governed JSON Answer Pack import ACTIVE" in created.body
    assert "UPLOAD ANSWER" in created.body
    assert "Readiness" in created.body and "NOT READY" in created.body
    assert "PAPER" not in created.body and "NO ENTRY, TRADE, RISK OR BROKER AUTHORITY" in created.body


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
    rendered = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    assert rendered is not None
    snapshot = application.snapshot()
    for candidate in snapshot.candidates:
        assert candidate.cycle_identity is None
        assert rendered.body.count(
            'data-upload-url="/intraday/review/chart?result='
            + candidate.probable_result_identity
            + '"'
        ) == 1
        assert (
            "Paste TradingView 1D 1H 15M 5M chart composite for "
            + candidate.canonical_subject_identity
        ) in rendered.body
    assert rendered.body.count('class="intraday-drop" role="button" tabindex="0"') == 2
    assert rendered.body.count('id="intraday-chart-slot-') == 2
    assert rendered.body.count('class="intraday-chart-input" type="file"') == 2
    assert rendered.body.count('data-target="intraday-chart-slot-') == 2
    assert "intraday-paste-receiver" not in rendered.body
    assert "activeReviewPasteTarget" not in rendered.body
    assert "document.addEventListener('paste'" not in rendered.body
    assert "target.addEventListener('click',()=>target.focus())" in rendered.body
    assert "target.addEventListener('paste'" in rendered.body
    assert "event.clipboardData&&Array.from(event.clipboardData.items||[])" in rendered.body
    assert "item.kind==='file'&&acceptedCharts.has(item.type)" in rendered.body
    assert "receiveChart(target,image.getAsFile())" in rendered.body
    assert "fetch(target.dataset.uploadUrl" in rendered.body
    assert "No supported chart image was found" in rendered.body
    assert "input.addEventListener('change'" in rendered.body
    assert "document.getElementById(input.dataset.target)" in rendered.body
    assert "if(target&&file)receiveChart(target,file)" in rendered.body
    assert "location.reload()" in rendered.body
    assert rendered.body.count("document.write(await response.text())") == 1
    assert "Chart could not be accepted." in rendered.body
    assert "intraday-replace-chart" in rendered.body
    assert "target.classList.add('replace-ready');target.focus()" in rendered.body
    assert ":focus-visible" in rendered.body

    swing_script = _chart_upload_script()
    for shared_behavior in (
        "target.addEventListener('click',()=>target.focus())",
        "target.addEventListener('paste',event=>{",
        "event.clipboardData&&Array.from(event.clipboardData.items||[])",
        "item.kind==='file'&&acceptedCharts.has(item.type)",
        "receiveChart(target,image.getAsFile())",
        "fetch(target.dataset.uploadUrl",
        "document.getElementById(input.dataset.target)",
        "if(target&&file)receiveChart(target,file)",
        "target.classList.add('replace-ready');target.focus()",
    ):
        assert shared_behavior in swing_script
        assert shared_behavior in rendered.body

    rejected = routes.handle_post(
        BrowserPostRequest("/intraday/review/question-packs", {"cycle": ["unexpected"]}, "", b""),
        _snapshot,
    )
    assert rejected is not None and rejected.status.value == 400


def test_intraday_chart_intake_preserves_swing_lifecycle_through_replacement_and_restore(
    tmp_path: Path,
) -> None:
    run = _run((_member("WIPRO"), _member("LICI")))
    current = [run]
    application = _application(tmp_path, current)
    routes = IntradayBrowserRoutes(_Workstation(), review=application)
    wipro = next(item for item in run.results if item.canonical_subject_identity == "WIPRO")
    lici = next(item for item in run.results if item.canonical_subject_identity == "LICI")

    required = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    assert required is not None
    assert "CHART REQUIRED" in required.body
    assert "TRADINGVIEW 4-CHART IMAGE · MISSING" in required.body
    assert "intraday-replace-chart" in required.body  # registration exists; no rendered button yet
    assert '<button class="intraday-replace-chart"' not in required.body

    first = routes.handle_post(
        BrowserPostRequest(
            "/intraday/review/chart", {"result": [wipro.result_identity]},
            "image/png", _png(41),
        ),
        _snapshot,
    )
    assert first is not None and first.status.value == 200
    assert "CHART READY · REV 001" in first.body
    assert "TRADINGVIEW 4-CHART IMAGE · RECEIVED" in first.body
    assert 'class="intraday-drop received" role="button" tabindex="0"' in first.body
    assert '<button class="intraday-replace-chart"' in first.body
    assert ">Replace</button>" in first.body
    assert first.body.count('data-upload-url="/intraday/review/chart?result=' + wipro.result_identity + '"') == 1

    replacement = routes.handle_post(
        BrowserPostRequest(
            "/intraday/review/chart", {"result": [wipro.result_identity]},
            "image/png", _png(42),
        ),
        _snapshot,
    )
    assert replacement is not None and replacement.status.value == 200
    assert "CHART READY · REV 002" in replacement.body
    assert "Chart Revision · REV 002" in replacement.body

    reloaded = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    assert reloaded is not None and "CHART READY · REV 002" in reloaded.body
    assert routes.handle_get(BrowserGetRequest("/unrelated", {}), _snapshot) is None
    returned = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    assert returned is not None and "CHART READY · REV 002" in returned.body

    restored_application = _application(tmp_path, current)
    restored_routes = IntradayBrowserRoutes(_Workstation(), review=restored_application)
    restored = restored_routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    assert restored is not None and "CHART READY · REV 002" in restored.body
    restored_candidates = {
        item.canonical_subject_identity: item
        for item in restored_application.snapshot().candidates
    }
    assert restored_candidates["WIPRO"].chart_revision_ordinal == 2
    assert restored_candidates["LICI"].chart_revision_identity is None

    existing_lici_cycle = restored_application.start_review(lici.result_identity)
    other = restored_routes.handle_post(
        BrowserPostRequest(
            "/intraday/review/chart", {"result": [lici.result_identity]},
            "image/png", _png(43),
        ),
        _snapshot,
    )
    assert other is not None and other.status.value == 200
    isolated = {
        item.canonical_subject_identity: item
        for item in restored_application.snapshot().candidates
    }
    assert isolated["WIPRO"].chart_revision_ordinal == 2
    assert isolated["LICI"].chart_revision_ordinal == 1
    assert isolated["LICI"].cycle_identity == existing_lici_cycle.cycle_identity
    assert isolated["WIPRO"].cycle_identity != isolated["LICI"].cycle_identity


def test_intraday_review_rejects_non_image_transport_without_creating_a_cycle(
    tmp_path: Path,
) -> None:
    run = _run((_member("WIPRO"), _member("LICI")))
    current = [run]
    application = _application(tmp_path, current)
    routes = IntradayBrowserRoutes(_Workstation(), review=application)
    wipro = next(item for item in run.results if item.canonical_subject_identity == "WIPRO")
    before = _store_fingerprint(application.store.root)

    for media_type, payload in (
        ("text/plain", b"https://www.tradingview.com/chart/"),
        ("text/html", b"<img src='https://example.invalid/chart.png'>"),
        ("image/gif", b"GIF89a"),
        ("image/webp", b"RIFFxxxxWEBP"),
    ):
        response = routes.handle_post(
            BrowserPostRequest(
                "/intraday/review/chart",
                {"result": [wipro.result_identity]},
                media_type,
                payload,
            ),
            _snapshot,
        )
        assert response is not None and response.status.value == 400

    assert all(item.cycle_identity is None for item in application.snapshot().candidates)
    assert _store_fingerprint(application.store.root) == before


def test_intraday_review_renders_sponsor_names_alphabetically_without_reordering_probables(
    tmp_path: Path,
) -> None:
    source_order = ("SRF", "INDIGO", "COALINDIA", "RBLBANK", "MAZDOCK", "RVNL")
    run = _run(tuple(_member(identity) for identity in source_order))
    current = [run]
    application = _application(tmp_path, current)
    routes = IntradayBrowserRoutes(_Workstation(), review=application)

    expected = ("COALINDIA", "INDIGO", "MAZDOCK", "RBLBANK", "RVNL", "SRF")
    by_identity = {
        item.canonical_subject_identity: item for item in application.snapshot().candidates
    }
    unordered = replace(
        application.snapshot(), candidates=tuple(by_identity[identity] for identity in source_order)
    )
    rendered = render_intraday_review(_snapshot(), unordered)
    assert tuple(item.canonical_subject_identity for item in unordered.candidates) == source_order
    positions = tuple(rendered.index(f"<h2>{identity}</h2>") for identity in expected)
    assert positions == tuple(sorted(positions))

    first = next(item for item in run.results if item.canonical_subject_identity == "COALINDIA")
    response = routes.handle_post(
        BrowserPostRequest(
            "/intraday/review/chart",
            {"result": [first.result_identity]},
            "image/png",
            _png(31),
        ),
        _snapshot,
    )
    assert response is not None and response.status.value == 200
    snapshots = {item.canonical_subject_identity: item for item in application.snapshot().candidates}
    assert snapshots["COALINDIA"].chart_revision_ordinal == 1
    assert all(
        item.chart_revision_identity is None
        for identity, item in snapshots.items()
        if identity != "COALINDIA"
    )


def test_intraday_review_individual_and_batch_answer_controls_project_visual_evidence(tmp_path: Path) -> None:
    run = _run((_member("WIPRO"),))
    current = [run]
    application = _application(tmp_path, current)
    routes = IntradayBrowserRoutes(_Workstation(), review=application)
    cycle = application.start_review(run.results[0].result_identity)
    application.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(9))
    pack, _ = application.create_question_pack(cycle.cycle_identity)

    missing = routes.handle_post(
        BrowserPostRequest("/intraday/review/answer", {"cycle": [cycle.cycle_identity]}, "", b""),
        _snapshot,
    )
    assert missing is not None and "INDIVIDUAL ANSWER IMPORT" in missing.body
    assert "MISSING" in missing.body

    imported = routes.handle_post(
        BrowserPostRequest(
            "/intraday/review/answer", {"cycle": [cycle.cycle_identity]},
            "application/json", json.dumps(_document(pack)).encode(),
        ),
        _snapshot,
    )
    assert imported is not None and "IMPORTED Q1-Q10 VISUAL EVIDENCE" in imported.body
    assert imported.body.count("<th>Q") >= 1
    assert "Observed visible identity · WIPRO" in imported.body
    assert not (tmp_path / "answers" / answer_pack_filename(pack)).exists()
    assert len(tuple((tmp_path / "evidence" / "answer-transports").glob("*.json"))) == 1

    batch = routes.handle_post(
        BrowserPostRequest("/intraday/review/answers", {}, "", b""), _snapshot,
    )
    assert batch is not None and "UPLOAD ALL ANSWERS · Eligible 1" in batch.body
    assert "Already imported 1" in batch.body
    assert routes.owns_post("/intraday/review/answer")
    assert routes.owns_post("/intraday/review/answers")


def test_intraday_review_explicit_reconciliation_control_projects_typed_state(tmp_path: Path) -> None:
    run = _run((_member("WIPRO"),))
    current = [run]
    application = _application(tmp_path, current)
    routes = IntradayBrowserRoutes(_Workstation(), review=application)
    cycle = application.start_review(run.results[0].result_identity)
    application.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(21))
    pack, _ = application.create_question_pack(cycle.cycle_identity)
    application.upload_answer(
        cycle.cycle_identity, media_type="application/json",
        payload=json.dumps(_document(pack)).encode(),
    )

    before = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    assert before is not None and "RECONCILE REVIEW" in before.body
    assert "RECONCILE ALL READY REVIEWS" in before.body
    assert "NOT ESTABLISHED" in before.body

    response = routes.handle_post(
        BrowserPostRequest(
            "/intraday/review/reconcile", {"cycle": [cycle.cycle_identity]}, "", b""
        ),
        _snapshot,
    )
    assert response is not None and response.status.value == 200
    assert "INDIVIDUAL RECONCILIATION" in response.body
    assert "REVIEW COMPLETE" in response.body
    assert "ANALYTICALLY READY" in response.body
    assert "PROMOTED" in response.body
    assert "NATIVE / VISUAL RECONCILIATION FACTS" in response.body
    assert "ENTRY" not in response.body.replace("NO ENTRY", "")
    assert routes.owns_post("/intraday/review/reconcile")
    assert routes.owns_post("/intraday/review/reconcile-all")
