from __future__ import annotations

import json
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace

from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
from kronos.application.intraday_lifecycle import IntradayLifecycleApplication
from kronos.application.intraday_wo17 import (
    IntradayWo17Application,
    IntradayWo17RestorationService,
)
from kronos.browser.intraday_wo17_control import IntradayWo17OperationalControl
from kronos.browser.intraday_routes import IntradayBrowserRoutes
from kronos.browser.intraday_wo17_control import WO17_PRODUCT_ROUTE
from kronos.browser.product_routes import BrowserGetRequest
from kronos.intraday.probables_v2 import (
    ProbablesUnavailableMemberV2,
    ProbableReasonV2,
    evaluate_probables_v2_run,
)
from kronos.intraday.probables_v2_persistence import ProbablesV2Store

from tests.unit.browser.test_intraday_wo17_control import _Workstation, _control
from tests.unit.browser.test_intraday_probables_v2_control import _routes
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_probables_v2 import (
    PROVENANCE,
    SOURCE_RUN,
    _opening_inputs,
    _run,
)
from tests.unit.intraday.test_wo11_lifecycle_application import fixture


def _reject_store_read(root: Path):
    original = Path.read_bytes

    def reject(path: Path) -> bytes:
        if path.is_relative_to(root):
            raise AssertionError(f"GET read durable Intraday state: {path}")
        return original(path)

    return reject


def _fingerprint(root: Path) -> tuple[tuple[str, bytes], ...]:
    return tuple(
        (str(path.relative_to(root)), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def test_probables_latest_evaluable_is_prepared_once(tmp_path, monkeypatch) -> None:
    *_, mapping = _opening_inputs()
    evaluable = _run(mapping)
    boundary = evaluable.analysis_boundary.replace(minute=45)
    unavailable_member = ProbablesUnavailableMemberV2(
        universe_member_identity=mapping.universe_member_identity,
        canonical_subject_identity=mapping.canonical_subject_identity,
        market_session_identity=evaluable.market_session_identity,
        analysis_boundary=boundary,
        reason=ProbableReasonV2.MANDATORY_EVIDENCE_UNAVAILABLE,
        source_identity=SOURCE_RUN,
        provenance=PROVENANCE,
    )
    unavailable = evaluate_probables_v2_run(
        source_discovery_run_identity=SOURCE_RUN,
        universe_identity=evaluable.universe_identity,
        universe_version=evaluable.universe_version,
        reconciliation_identity=evaluable.reconciliation_identity,
        reconciliation_version=evaluable.reconciliation_version,
        market_session_identity=evaluable.market_session_identity,
        analysis_boundary=boundary,
        member_evidence=(),
        unavailable_members=(unavailable_member,),
        provenance=PROVENANCE,
    )
    store = ProbablesV2Store(tmp_path.resolve())
    store.retain_complete(run=evaluable, mappings=(mapping,))
    store.retain_complete(run=unavailable, mappings=())
    application = IntradayProbablesV2Application(store=store)
    monkeypatch.setattr(
        store,
        "load_latest_evaluable_run",
        lambda: (_ for _ in ()).throw(AssertionError("request-time history scan")),
    )

    assert application.snapshot().run == unavailable
    assert application.latest_evaluable_run() == evaluable
    assert application.latest_evaluable_run() is application.latest_evaluable_run()


def test_probables_historical_run_without_current_pointer_stays_unprepared(
    tmp_path, monkeypatch
) -> None:
    *_, mapping = _opening_inputs()
    historical = _run(mapping)
    store = ProbablesV2Store(tmp_path.resolve())
    store.retain_run(historical)
    before = _fingerprint(tmp_path)
    monkeypatch.setattr(
        store,
        "load_latest_evaluable_run",
        lambda: (_ for _ in ()).throw(AssertionError("historical fallback scan")),
    )

    application = IntradayProbablesV2Application(store=store)

    assert application.snapshot().run is None
    assert application.latest_evaluable_run() is None
    assert _fingerprint(tmp_path) == before


def test_intraday_main_page_get_performs_zero_store_io(tmp_path, monkeypatch) -> None:
    routes, composition, _, _ = _routes(tmp_path)
    first_snapshot = composition.workstation.snapshot()
    second_snapshot = composition.workstation.snapshot()
    before = _fingerprint(tmp_path)
    monkeypatch.setattr(Path, "read_bytes", _reject_store_read(tmp_path))

    page = routes.handle_get(BrowserGetRequest("/intraday", {}), _snapshot)

    assert page is not None and "Intraday Opportunities" in page.body
    assert first_snapshot.members is second_snapshot.members
    monkeypatch.undo()
    assert _fingerprint(tmp_path) == before


def test_wo17_status_uses_prepared_generation_and_performs_zero_io(
    tmp_path, monkeypatch
) -> None:
    control, store, request = _control(tmp_path)
    control.application.execute(request)
    before = _fingerprint(store.root)
    monkeypatch.setattr(Path, "read_bytes", _reject_store_read(store.root))

    first = control.status_document()
    second = control.status_document()
    page = IntradayBrowserRoutes(
        _Workstation(), wo17_control=control
    ).handle_get(BrowserGetRequest(WO17_PRODUCT_ROUTE, {}), _snapshot)

    assert first["restoration_state"] == "LOADED"
    assert first["current_positions"] is second["current_positions"]
    assert first["current_positions"][0]["position_state"] == "PAPER_ARMED"
    assert json.dumps(first)
    assert page is not None and request.canonical_subject_identity in page.body
    monkeypatch.undo()
    assert _fingerprint(store.root) == before


def test_wo17_blocked_preparation_does_not_block_status_or_swing(
    tmp_path, monkeypatch
) -> None:
    from kronos.application.shared_monitoring import SharedSwingMonitoringHub

    control, _, request = _control(tmp_path)
    control.application.execute(request)
    entered = Event()
    release = Event()
    original = control._restoration_service.restore  # noqa: SLF001

    def blocked_restore():
        entered.set()
        assert release.wait(2)
        return original()

    monkeypatch.setattr(control._restoration_service, "restore", blocked_restore)  # noqa: SLF001
    worker = Thread(target=lambda: control.application.execute(request), daemon=True)
    worker.start()
    assert entered.wait(1)
    result: list[dict[str, object]] = []
    reader = Thread(target=lambda: result.append(control.status_document()), daemon=True)
    reader.start()
    reader.join(0.2)

    assert not reader.is_alive()
    assert result[0]["current_positions"][0]["position_state"] == "PAPER_ARMED"
    assert SharedSwingMonitoringHub().status_document()["owner_count"] == 0
    release.set()
    worker.join(2)
    assert not worker.is_alive()


def test_wo17_corruption_is_reported_at_preparation_boundary(tmp_path) -> None:
    control, store, request = _control(tmp_path)
    control.application.execute(request)
    pointer = next((store.root / "current").glob("CURRENT-WO17-*.json"))
    pointer.write_text("{}")
    restarted = IntradayWo17OperationalControl(
        IntradayWo17Application(store=store),
        IntradayWo17RestorationService(store=store),
        wo16_store=control._wo16_store,  # noqa: SLF001
    )

    status = restarted.status_document()
    assert status["restoration_state"] == "CORRUPT"
    assert status["failure_reason"] == "WO17_RESTORATION_FAILED"
    assert status["current_positions"] == []


def test_wo11_lifecycle_projection_is_prepared_and_zero_io(
    tmp_path, monkeypatch
) -> None:
    application, handoff, *_ = fixture(tmp_path, monkeypatch)
    application.action(
        handoff_identity=handoff.identity,
        action="OBSERVE",
        action_identity="PF04-PREPARED-PROJECTION",
    )
    before = _fingerprint(application.store.root)
    monkeypatch.setattr(
        Path, "read_bytes", _reject_store_read(application.store.root)
    )

    first = application.projection()
    second = application.projection()
    page = IntradayBrowserRoutes(
        _Workstation(),
        lifecycle_control=SimpleNamespace(application=application),
    ).handle_get(BrowserGetRequest("/intraday/active", {}), _snapshot)

    assert first == second
    assert first["cards"][0]["terminal"] is False
    assert page is not None and "ACTIVE" in page.body
    monkeypatch.undo()
    assert _fingerprint(application.store.root) == before


def test_wo11_corrupt_preparation_is_visible_and_fail_closed(
    tmp_path, monkeypatch
) -> None:
    application, handoff, *_ = fixture(tmp_path, monkeypatch)
    current = application.action(
        handoff_identity=handoff.identity,
        action="OBSERVE",
        action_identity="PF04-CORRUPT-PREPARATION",
    )
    path = application.store.root / "records" / (
        current.data["authorization_identity"] + ".json"
    )
    path.write_text("{}")

    restarted = IntradayLifecycleApplication(
        futures=application.futures,
        store=application.store,
        clock=application.clock,
        session_source=application.session_source,
        timing_source=application.timing_source,
        operational_guard=application.operational_guard,
    )

    assert restarted.projection() == {
        "cards": [],
        "last_failure": "WO11_RESTORATION_FAILED",
        "live": "LIVE_POSITION_NOT_COMMISSIONED_V1",
    }

# PF-10: populate the canonical controls omitted by the earlier compact fixture.
def _pf10_populated_pages(tmp_path, monkeypatch, subjects=("NTPC", "TITAN"), *, large=False):
    from datetime import timedelta
    from kronos.application.intraday_runtime import create_intraday_runtime
    from kronos.browser.intraday_probables_v2_control import IntradayProbablesV2OperationalControl
    from kronos.browser.intraday_review_v2_control import IntradayReviewV2OperationalControl
    from kronos.browser.intraday_visual_reconciliation_v2_control import IntradayVisualReconciliationV2OperationalControl
    from kronos.intraday.probables_v2 import create_probables_v2_methodology
    from kronos.intraday.review_v2_transport import IntradayReviewV2Transport
    from tests.unit.intraday.test_review_v2_individual_inbox import _fixture, _completed
    from tests.unit.intraday.test_opening_admission_correction import opening_mapping
    from tests.unit.intraday.chart_input_fixtures import configure_fixture_calendar, observe_fixture_uploads
    from tests.unit.provider.test_shared_provider_runtime import _shared
    from tests.unit.browser.test_intraday_review_v2_control import _payload
    from tests.unit.intraday.test_review import _png
    _, seed = _fixture(tmp_path / "fixture-authority", subjects)
    monkeypatch.setattr("kronos.application.intraday_runtime.load_visual_identity_resolver",
                        lambda **kw: seed._visual_identity_resolver)
    methodology = create_probables_v2_methodology()
    mappings = tuple(opening_mapping(methodology, subject="NSE-EQ-" + name)
                     for name in subjects)
    boundary = mappings[0].analysis_boundary
    shared, provider, factory = _shared()
    runtime = create_intraday_runtime(shared, evidence_root=(tmp_path / "runtime").resolve(),
                                     clock=lambda: boundary)
    run = runtime.probables_v2_application.refresh_analysis(
        source_discovery_run_identity=SOURCE_RUN,
        universe_identity="KRONOS-INTRADAY-NATIVE-UNIVERSE-V1", universe_version="1.0.0",
        reconciliation_identity="KRONOS-INTRADAY-RECONCILIATION-V1", reconciliation_version="1.0.0",
        market_session_identity=mappings[0].market_session_identity,
        analysis_boundary=boundary, member_evidence=mappings, unavailable_members=(), provenance=PROVENANCE)
    app = runtime.review_v2_application
    app._clock = lambda: boundary + timedelta(minutes=1)
    app._transport = IntradayReviewV2Transport(question_outbox=(tmp_path / "questions").resolve(),
                                              answer_inbox=(tmp_path / "answers").resolve())
    app._paired.transport = app._transport
    configure_fixture_calendar(app)
    observe_fixture_uploads(app)
    control = IntradayReviewV2OperationalControl(app, runtime.review_v2_operation_store,
        clock=lambda: boundary, process_identity=lambda: "PF10-ISOLATED-PID")
    assert control.execute_document(_payload(run))["outcome"] == "COMPLETE"
    for i, candidate in enumerate(app.snapshot().candidates):
        payload = _pf10_large_png(i) if large else _png(i + 35)
        app.upload_chart(candidate.cycle_identity, media_type="image/png", payload=payload)
        question = app.create_individual_question_transport(candidate.cycle_identity)
        imported = app.import_combined_answer(_completed(question.answer_template_path))
        assert imported.imported_count == 1
    app.create_all_question_transports()
    reconciliation = runtime.visual_reconciliation_v2_application.reconcile_all_ready()
    assert reconciliation["success_count"] == len(subjects), reconciliation
    probables = IntradayProbablesV2OperationalControl(runtime.discovery_v2_operation,
        runtime.probables_v2_application, runtime.refresh_v2_provenance_store,
        clock=lambda: boundary, process_identity=lambda: "PF10-ISOLATED-PID")
    routes = IntradayBrowserRoutes(runtime.workstation, probables_v2_control=probables,
        review_v2_control=control,
        visual_reconciliation_v2_control=IntradayVisualReconciliationV2OperationalControl(
            runtime.visual_reconciliation_v2_application))
    assert provider.begin_count == 0 and factory == []
    return runtime, routes


def _pf10_large_png(seed):
    import random, struct, zlib
    random = random.Random(seed)
    raw = b"".join(b"\0" + random.randbytes(512 * 3) for _ in range(256))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 512, 256, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_pf10_populated_canonical_page_captures_each_byte_source_once(tmp_path, monkeypatch):
    from collections import Counter
    runtime, routes = _pf10_populated_pages(tmp_path, monkeypatch)
    app = runtime.review_v2_application
    before = _fingerprint(tmp_path)
    monkeypatch.setattr(routes._review, "snapshot", lambda: (_ for _ in ()).throw(AssertionError("unused legacy")))
    monkeypatch.setattr(routes._reconciliation, "snapshot", lambda: (_ for _ in ()).throw(AssertionError("unused legacy")))
    original = Path.open
    reads = Counter()
    def opening(path, mode="r", *a, **kw):
        assert not any(flag in mode for flag in "wax+"), "GET attempted a write"
        if path.is_relative_to(tmp_path) and mode == "rb":
            reads[path] += 1
        return original(path, mode, *a, **kw)
    monkeypatch.setattr(Path, "open", opening)
    for path in ("/intraday", "/intraday/review"):
        reads.clear()
        result = routes.handle_get(BrowserGetRequest(path, {}), _snapshot)
        assert result.status == 200
        assert reads and max(reads.values()) == 1, reads
        assert not any("fixture-authority" in str(p) for p in reads)
    monkeypatch.setattr(Path, "open", original)
    assert _fingerprint(tmp_path) == before
    assert runtime.visual_reconciliation_v2_application.status().reconciled_count == 2


def test_pf10_page_scope_releases_objects_and_rejects_capacity(tmp_path, monkeypatch):
    import weakref
    from kronos.application.intraday_review_v2 import IntradayPageUnavailable, _CurrentPageRead
    runtime, routes = _pf10_populated_pages(tmp_path, monkeypatch)
    app = runtime.review_v2_application
    with app.page_read_scope() as capture:
        app.snapshot()
        reference = weakref.ref(capture)
        assert capture.byte_count > 0 and capture.values
    assert not capture.payloads and not capture.values and capture.byte_count == capture.value_bytes == 0
    del capture
    assert reference() is None
    for _ in range(4): assert app._page_slots.acquire(blocking=False)
    try:
        response = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
        assert response.status == 503 and "CAPACITY" in response.body
    finally:
        for _ in range(4): app._page_slots.release()
    monkeypatch.setattr(_CurrentPageRead, "MAX_BYTES", 128)
    response = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    assert response.status == 503 and "CAPACITY" in response.body


def test_pf10_reentrant_publication_cannot_escape_as_prepared_success(tmp_path, monkeypatch):
    import pytest
    from kronos.application.intraday_review_v2 import IntradayPageUnavailable
    runtime, _ = _pf10_populated_pages(tmp_path, monkeypatch)
    app = runtime.review_v2_application
    pointer = app.probables_store.load_current()
    with pytest.raises(IntradayPageUnavailable, match="SOURCE_CHANGED"):
        with app.page_read_scope():
            before = app.snapshot()
            app.probables_store.save_current(pointer)
            app.snapshot()
    with app.page_read_scope():
        assert app.snapshot() == before


def test_pf10_concurrent_publication_serializes_without_rebuilding_hooks(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    runtime, routes = _pf10_populated_pages(tmp_path, monkeypatch)
    app = runtime.review_v2_application
    started, finished = Event(), Event()
    pointer = app.probables_store.load_current()
    def publish():
        started.set()
        app.probables_store.save_current(pointer)
        finished.set()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with app.page_read_scope():
            snapshot = app.snapshot()
            future = pool.submit(publish)
            assert started.wait(1)
            assert not finished.wait(.05)
            assert app.snapshot() is snapshot
        future.result(timeout=2)
    assert finished.is_set()
    assert routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot).status == 200


def test_pf10_opportunities_rejects_cross_publication_page(tmp_path, monkeypatch):
    from tests.unit.intraday.test_review_v2 import _retain_later_current_run
    runtime, routes = _pf10_populated_pages(tmp_path, monkeypatch)
    original = routes._workstation.snapshot
    def raced(*args, **kwargs):
        result = original(*args, **kwargs)
        _retain_later_current_run(runtime.review_v2_application)
        return result
    monkeypatch.setattr(routes._workstation, "snapshot", raced)
    response = routes.handle_get(BrowserGetRequest("/intraday", {}), _snapshot)
    assert response.status == 503 and "SOURCE_CHANGED" in response.body


def test_pf10_blocked_capture_leaves_shared_status_and_swing_responsive(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from time import perf_counter
    from kronos.application.swing_opportunities import SwingOpportunitiesApplication
    from kronos.browser.views import render_opportunities
    from tests.unit.application.test_swing_opportunities import _Provider
    from kronos.application.intraday_review_v2 import _CurrentPageRead
    runtime, routes = _pf10_populated_pages(tmp_path, monkeypatch)
    swing = SwingOpportunitiesApplication(_Provider)
    entered, release = Event(), Event()
    original = _CurrentPageRead.read
    def blocked(self, path, loader=None):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        return original(self, path, loader)
    monkeypatch.setattr(_CurrentPageRead, "read", blocked)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(routes.handle_get, BrowserGetRequest("/intraday/review", {}), _snapshot)
        try:
            assert entered.wait(2)
            def independent():
                start = perf_counter()
                state = swing.snapshot()
                page = render_opportunities(state)
                assert page and state is not None
                return perf_counter()-start
            assert pool.submit(independent).result(timeout=1) < 1
        finally:
            release.set()
        assert future.result(timeout=3).status == 200


def test_pf10_concurrent_readers_release_every_capture_and_preserve_files(tmp_path, monkeypatch):
    import weakref
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from kronos.application.intraday_review_v2 import _CurrentPageRead
    runtime, routes = _pf10_populated_pages(tmp_path, monkeypatch)
    before = _fingerprint(tmp_path)
    references = []
    original = _CurrentPageRead.__init__
    def initialized(self):
        original(self)
        references.append(weakref.ref(self))
    monkeypatch.setattr(_CurrentPageRead, "__init__", initialized)
    barrier = Barrier(4)
    def client(index):
        for _ in range(12):
            barrier.wait(timeout=3)
            response = routes.handle_get(BrowserGetRequest(("/intraday", "/intraday/review")[index%2], {}), _snapshot)
            assert response.status == 200
            barrier.wait(timeout=3)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(client, range(4)))
    assert len(references) == 48
    assert all(reference() is None for reference in references)
    assert _fingerprint(tmp_path) == before


def test_pf10_all_page_capacity_dimensions_are_fail_closed(tmp_path, monkeypatch):
    from kronos.application.intraday_review_v2 import _CurrentPageRead
    runtime, routes = _pf10_populated_pages(tmp_path, monkeypatch)
    for name in ("MAX_FILES", "MAX_VALUES", "MAX_VALUE_BYTES", "MAX_OBJECTS"):
        with monkeypatch.context() as patch:
            patch.setattr(_CurrentPageRead, name, 1)
            response = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
            assert response.status == 503 and "CAPACITY" in response.body
        assert routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot).status == 200
