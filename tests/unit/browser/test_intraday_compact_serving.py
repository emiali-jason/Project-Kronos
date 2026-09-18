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
