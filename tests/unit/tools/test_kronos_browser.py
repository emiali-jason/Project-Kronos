from pathlib import Path
from datetime import timedelta
from types import SimpleNamespace
import shutil

from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.common.maintenance import DrainStartupContext
from kronos.application.intraday_notifications import IntradayNotifications
from kronos.browser.runtime_state import complete_startup
from tools import kronos_browser
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from kronos.provider.runtime import (
    SharedAuthenticatedProviderRuntime, ProviderRuntimeAccessError,
    ProviderRuntimeFailure,
)
from kronos.swing.v1.mcx_contract_profile import McxFamily
from application.test_swing_mcx_observation import setup as observation_fixture
from provider.test_shared_provider_runtime import _Runtime, _authenticate
import pytest


@pytest.fixture(autouse=True)
def isolated_composition_authority(monkeypatch):
    # Tests compose fake servers in the kernel-isolated test home; no production bypass.
    monkeypatch.setattr("tools.runtime_source_gate.qualify_startup", lambda *_: "a" * 40)
    monkeypatch.setattr("kronos.browser.runtime_state.complete_startup", lambda *_: None)
    class _IntradayNotifications:
        def __init__(self, **_kwargs):
            pass
        def bind_maintenance_admission(self, admission):
            self.maintenance_admission = admission
        def bind(self, _probables):
            pass
        def close(self, **_kwargs):
            pass
    monkeypatch.setattr(
        "kronos.application.intraday_notifications.IntradayNotifications",
        _IntradayNotifications,
    )


@pytest.mark.parametrize("family", list(McxFamily))
def test_launcher_uses_loopback_server_and_opens_swing_workspace(monkeypatch, tmp_path, family) -> None:
    events: list[object] = []
    control = object()
    checkpoint = DrainStartupContext("a" * 64, "EMPTY", 0, "b" * 64)
    monkeypatch.setattr(kronos_browser, "consume_startup_context", lambda *_args, **_kwargs: checkpoint)

    class _Notifications:
        def __init__(self, **kwargs):
            assert kwargs["expected_checkpoint"] == checkpoint.notification_checkpoint()
            events.append("checkpoint-bound")

        def bind_maintenance_admission(self, admission):
            self.maintenance_admission = admission

        def bind(self, _probables):
            events.append("notification-bind")

    monkeypatch.setattr(
        "kronos.application.intraday_notifications.IntradayNotifications",
        _Notifications,
    )
    monkeypatch.setattr(
        "kronos.browser.runtime_state.complete_startup",
        lambda *_args: events.append("ready"),
    )

    class _Server:
        server_port = 9123
        swing_monitoring_hub = SharedSwingMonitoringHub()
        notification_centre = object()
        telegram = None
        maintenance_admission = MaintenanceAdmissionCoordinator()
        def serve_forever(self, **kwargs):  # type: ignore[no-untyped-def]
            events.append(("serve", kwargs))
        def server_close(self):
            events.append("close")

    server = _Server()

    class _Application:
        def authenticated_read_only_capability(self):
            return None

    monkeypatch.setattr(
        kronos_browser,
        "SwingOpportunitiesApplication",
        lambda factory, **kwargs: events.append((factory, kwargs)) or _Application(),
    )
    monkeypatch.setattr(
        kronos_browser.BrowserBackendRestartControl,
        "create",
        lambda: control,
    )
    monkeypatch.setattr(
        kronos_browser,
        "create_browser_server",
        lambda app, port, restart_control, product_routes,
        provider_instrument_master_operation, intraday_discovery_control,
        intraday_historical_control, provider_login_navigation,
        mcx_v1_composition_factory: (
            events.append((
                app,
                port,
                restart_control,
                product_routes,
                provider_instrument_master_operation,
                intraday_discovery_control,
                intraday_historical_control,
                provider_login_navigation,
                mcx_v1_composition_factory,
            )) or server
        ),
    )
    housekeeping = SimpleNamespace(
        production_activation=True,
        bind_maintenance_admission=lambda admission: events.append(
            ("housekeeping-admission", admission)),
    )
    monkeypatch.setattr(
        kronos_browser,
        "_compose_housekeeping",
        lambda _server, _runtime: housekeeping,
    )
    monkeypatch.setattr(
        kronos_browser.webbrowser,
        "open_new_tab",
        lambda url: events.append(url) or True,
    )
    assert kronos_browser.main(["--port", "9123"]) == 0
    assert events.index("checkpoint-bound") < events.index("notification-bind") < events.index("ready")
    assert "http://127.0.0.1:9123/swing/opportunities" in events
    assert "close" in events
    server_event = next(
        item for item in events if isinstance(item, tuple) and len(item) == 9
    )
    operation = server_event[4]
    intraday_control = server_event[5]
    historical_control = server_event[6]
    assert callable(server_event[8])
    application_event = next(
        item
        for item in events
        if isinstance(item, tuple)
        and len(item) == 2
        and callable(item[0])
        and isinstance(item[1], dict)
    )
    swing_factory = application_event[0]
    assert isinstance(
        application_event[1]["analysis_process_owner"],
        kronos_browser.SwingAnalysisProcessOwner,
    )
    assert swing_factory.__closure__ is not None
    assert any(
        cell.cell_contents is operation._runtime
        for cell in swing_factory.__closure__
    )
    assert intraday_control.operation_service._runtime is operation._runtime
    assert historical_control.historical_invocation.operation_service is (
        historical_control.operation_service
    )
    assert historical_control.operation_service._runtime is operation._runtime
    assert historical_control.operation_service.last_result is None
    assert historical_control.operation_service.active_operation_identity is None
    assert server.housekeeping is housekeeping
    assert housekeeping.production_activation is True
    assert ("housekeeping-admission", server.maintenance_admission) in events
    assert server.intraday_lifecycle._maintenance_admission is server.maintenance_admission
    assert server.intraday_wo17_monitoring._maintenance_admission is server.maintenance_admission
    assert server.intraday_notifications.maintenance_admission is server.maintenance_admission
    provider_factory = (
        server.provider_runtime
        ._SharedAuthenticatedProviderRuntime__provider_factory
    )
    assert provider_factory.__closure__ is not None
    assert "http://127.0.0.1:9123/swing/opportunities" in {
        cell.cell_contents for cell in provider_factory.__closure__
        if isinstance(cell.cell_contents, str)
    }
    source = Path(kronos_browser.__file__).read_text(encoding="utf-8")
    assert source.count("SharedAuthenticatedProviderRuntime(") == 1

    # Exercise the grant supplied by actual canonical composition, rather than
    # giving the observation fixture an unrestricted Provider capability.
    grants = []
    facade_factory = SharedAuthenticatedProviderRuntime.compatibility_facade
    def capture_grant(runtime, **kwargs):
        grants.append(kwargs)
        return facade_factory(runtime, **kwargs)
    monkeypatch.setattr(SharedAuthenticatedProviderRuntime, "compatibility_facade", capture_grant)
    swing_factory()
    assert len(grants) == 1 and grants[0]["consumer_identity"] == "SWING"
    operations = grants[0]["operations"]
    f, shared = _authenticated_observation(tmp_path, family)
    facade = shared.compatibility_facade(**grants[0])
    lease = facade.authenticated_read_only_capability()
    assert lease.operations == operations
    assert facade.authenticated_read_only_capability() is lease
    assert shared.active_lease_count == 1
    f.owner.capability = lambda: lease
    record = f.owner.observe(**f.args)["record"]
    assert record["state"] == "OBSERVED" and record["cleanup"]["complete"]
    assert operations == frozenset({
        ReadOnlyProviderOperation.INSTRUMENTS,
        ReadOnlyProviderOperation.INSTRUMENT_ASSERTIONS,
        ReadOnlyProviderOperation.HISTORICAL_DATA,
        ReadOnlyProviderOperation.QUOTE,
        ReadOnlyProviderOperation.LTP,
        ReadOnlyProviderOperation.OHLC,
        ReadOnlyProviderOperation.MONITORING,
    })
    assert record["selection"]["instrument"]["trading_symbol"] == f.instrument.trading_symbol
    assert record["mapping"]["provider_instrument_token"] == 202
    assert record["observation"]["subscription"]["provider_instrument_token"] == 202
    assert f.cap.calls == ["records", "assertions", "session"]
    assert f.cap.sockets[0].closed and f.cap.sockets[0].tokens == []
    assert f.hub.status_document()["owner_count"] == 0
    assert f.admission.snapshot()["owners"] == {}
    assert shared.active_lease_count == 1  # observation does not replace/release Swing's lease
    lease.release()
    assert shared.active_lease_count == 0
    shared.end_kronos_session()


def _authenticated_observation(tmp_path, family=McxFamily.CRUDEOIL):
    """Existing owning fixtures with actual authentication and lease enforcement."""
    f = observation_fixture(tmp_path, family=family)
    provider = _Runtime()
    provider.capability = f.cap
    f.cap.operations = frozenset(ReadOnlyProviderOperation)
    provider.current_context = lambda: SimpleNamespace(
        provider="KITE", context_id="ISOLATED-CONTEXT",
        valid_until=f.clock() + timedelta(hours=1),
    )
    shared = SharedAuthenticatedProviderRuntime(
        lambda: provider, provider_identity="KITE", clock=f.clock,
    )
    _authenticate(shared)
    return f, shared


def test_observation_without_assertion_grant_fails_before_subscription(tmp_path):
    f, shared = _authenticated_observation(tmp_path)
    lease = shared.acquire_lease(consumer_identity="UNGRANTED-TEST-OWNER", operations=frozenset({
        ReadOnlyProviderOperation.INSTRUMENTS, ReadOnlyProviderOperation.MONITORING,
    }))
    f.owner.capability = lambda: lease
    record = f.owner.observe(**f.args)["record"]
    assert record["state"] == "FAILED"
    assert record["error_type"] == "ProviderRuntimeAccessError"
    assert record["mapping"] is None and record["observation"] is None
    assert record["cleanup"]["complete"]
    assert f.cap.calls == ["records"] and not f.cap.sessions
    assert f.hub.status_document()["owner_count"] == 0
    assert f.admission.snapshot()["owners"] == {}
    with pytest.raises(ProviderRuntimeAccessError) as rejected:
        lease.full_quotes((), request_identity="UNGRANTED-QUOTE")
    assert rejected.value.failure is ProviderRuntimeFailure.OPERATION_NOT_AUTHORIZED
    assert f.cap.calls == ["records"]
    lease.release()
    shared.end_kronos_session()


def test_swing_grant_cannot_exceed_authenticated_provider_capability(tmp_path):
    f, shared = _authenticated_observation(tmp_path)
    f.cap.operations = frozenset({ReadOnlyProviderOperation.INSTRUMENTS})
    with pytest.raises(ProviderRuntimeAccessError) as rejected:
        shared.acquire_lease(consumer_identity="SWING", operations=frozenset({
            ReadOnlyProviderOperation.INSTRUMENTS, ReadOnlyProviderOperation.INSTRUMENT_ASSERTIONS,
        }))
    assert rejected.value.failure is ProviderRuntimeFailure.OPERATION_NOT_AUTHORIZED
    assert shared.active_lease_count == 0 and not f.cap.calls
    shared.end_kronos_session()


def test_developer_no_browser_mode_does_not_open_browser(monkeypatch) -> None:
    control = object()
    class _Server:
        server_port = 9123
        swing_monitoring_hub = SharedSwingMonitoringHub()
        notification_centre = object()
        telegram = None
        maintenance_admission = MaintenanceAdmissionCoordinator()
        def serve_forever(self, **_kwargs): pass  # type: ignore[no-untyped-def]
        def server_close(self): pass

    class _Application:
        def authenticated_read_only_capability(self):
            return None

    monkeypatch.setattr(
        kronos_browser,
        "SwingOpportunitiesApplication",
        lambda _factory, **_kwargs: _Application(),
    )
    monkeypatch.setattr(
        kronos_browser.BrowserBackendRestartControl,
        "create",
        lambda: control,
    )
    monkeypatch.setattr(
        kronos_browser,
        "create_browser_server",
        lambda _app, port, restart_control, product_routes,
        provider_instrument_master_operation, intraday_discovery_control,
        intraday_historical_control, provider_login_navigation,
        mcx_v1_composition_factory: _Server(),
    )
    monkeypatch.setattr(
        kronos_browser,
        "_compose_housekeeping",
        lambda _server, _runtime: SimpleNamespace(
            production_activation=True,
            bind_maintenance_admission=lambda _admission: None,
        ),
    )
    monkeypatch.setattr(
        kronos_browser.webbrowser,
        "open_new_tab",
        lambda _url: (_ for _ in ()).throw(AssertionError),
    )
    assert kronos_browser.main(["--no-browser"]) == 0


def test_canonical_main_installs_real_mcx_owner_before_ready_without_acquisition(
    tmp_path, monkeypatch, *, _check_wo08=None,
):
    """Run main's actual server/factory path in the governed isolated home.

    The startup source gate is the module's explicit test fixture. READY and
    the serving loop are observed here; no production process is launched.
    """
    from kronos.application.swing_opportunities import SwingOpportunitiesApplication
    from kronos.application.swing_mcx_v1_composition import SwingMcxV1Composition
    from kronos.swing.v1.mtf_facts import MtfFactEvidenceStore
    from kronos.browser.server import KronosBrowserServer

    app = SwingOpportunitiesApplication(
        lambda: pytest.fail('canonical composition attempted Provider acquisition'),
        mtf_fact_evidence_store=MtfFactEvidenceStore(tmp_path / 'facts'))
    monkeypatch.setattr(kronos_browser, 'SwingOpportunitiesApplication', lambda *_args, **_kwargs: app)
    events = []

    def ready(_root, _revision):
        assert events == ['owners-installed']
        if _check_wo08 is not None:
            _check_wo08(_root)
        events.append('ready')

    original = kronos_browser.create_browser_server

    def composed(*args, **kwargs):
        server = original(*args, **kwargs)
        assert type(server.mcx_v1_composition) is SwingMcxV1Composition
        assert server.mcx_v1_control._maintenance_admission is server.maintenance_admission
        assert server.mcx_v1_control.native_review is server.native_review
        assert server.mcx_v1_control.workflow is None
        assert server.mcx_v1_control.worker_status()['pending'] == 0
        events.append('owners-installed')
        return server

    def serve(server, **_kwargs):
        assert events == ['owners-installed', 'ready']
        if _check_wo08 is not None:
            _check_wo08(server)
        assert server.mcx_v1_control._maintenance_admission is server.maintenance_admission
        events.append('serve')

    monkeypatch.setattr(kronos_browser, 'create_browser_server', composed)
    monkeypatch.setattr('kronos.browser.runtime_state.complete_startup', ready)
    monkeypatch.setattr(KronosBrowserServer, 'serve_forever', serve)
    assert kronos_browser.main(['--port', '0', '--no-browser']) == 0
    assert events == ['owners-installed', 'ready', 'serve']


@pytest.mark.parametrize("checkpoint_matches,failure_stage", (
    (True, None), (False, None), (True, "housekeeping"),
    (True, "ready"), (True, "workspace"),
))
def test_canonical_startup_restores_pre_mcx_continuity_without_rewriting_it(
    tmp_path, monkeypatch, checkpoint_matches, failure_stage,
):
    """Real constructors/checkpoint/READY; only launch authority and roots are fixtures."""
    from dataclasses import asdict
    from hashlib import sha256
    from kronos.browser.server import KronosBrowserServer
    from kronos.swing.v1.mtf_facts import SameRunMtfFactSnapshot
    from kronos.swing.v1 import opportunity_continuity as continuity
    from kronos.swing import run_publication as publication_module
    from tests.unit.swing.v1.test_opportunity_continuity import scenario
    from tests.unit.swing.test_run_publication import make_checkpoint, prepared

    snapshot, bindings = scenario.__wrapped__()
    original_json = continuity._json

    def predecessor_json(value):
        if type(value) is SameRunMtfFactSnapshot:
            value = asdict(value)
            for instrument in value["instruments"]:
                assert instrument.pop("mcx_request_lineage") is None
        return original_json(value)

    with monkeypatch.context() as predecessor:
        predecessor.setattr(continuity, "_json", predecessor_json)
        coordinator = publication_module.SwingRunPublication
        predecessor.setattr(publication_module, "SwingRunPublication",
                            lambda root, **kwargs: coordinator(
                                Path(root).parent / "run-publication-v1", **kwargs))
        publication, snapshot, bindings, _ = make_checkpoint(
            tmp_path / "historical", snapshot, bindings)
        token, values = prepared(publication, snapshot, bindings, 2)
        reference = publication.prepare(token, **values)
        assert publication.publish(token, reference,
                                   values["provenance"].successful_completed_at)
    before = {str(path): (path.read_bytes(), path.stat().st_mtime_ns,
                         path.stat().st_ctime_ns)
              for path in (tmp_path / "historical").rglob("*") if path.is_file()}
    for name, store in (
        ("MtfFactEvidenceStore", publication.mtf_store),
        ("NativeDiscoveryEvidenceStore", publication.native_store),
        ("RelativeContextEvidenceStore", publication.relative_store),
        ("LocalSwingRunProvenanceStore", publication.provenance_store),
    ):
        monkeypatch.setattr(kronos_browser, name,
                            lambda *_args, _store=store, **_kwargs: _store)
    digest = sha256(b"").hexdigest() if checkpoint_matches else "f" * 64
    checkpoint = DrainStartupContext("a" * 64, "EMPTY", 0, digest)
    monkeypatch.setattr(kronos_browser, "consume_startup_context",
                        lambda *_args, **_kwargs: checkpoint)
    # Restore the actual shared owners hidden by the fake-server unit fixture.
    monkeypatch.setattr("kronos.application.intraday_notifications.IntradayNotifications",
                        IntradayNotifications)
    monkeypatch.setattr("kronos.browser.runtime_state.complete_startup", complete_startup)
    monkeypatch.setattr(kronos_browser, "_build_provider",
                        lambda **_kwargs: pytest.fail("startup acquired Provider data"))
    servers, served = [], []
    create = kronos_browser.create_browser_server

    def capture(*args, **kwargs):
        server = create(*args, **kwargs)
        servers.append(server)
        return server

    def serve(server, **_kwargs):
        assert server.connection_governance.startup_state == "READY"
        assert server.connection_governance.maintenance_active is False
        assert server.provider_runtime.read_only_status()["capability_state"] == "ABSENT"
        assert server.mcx_v1_composition.control is server.mcx_v1_control
        assert server.mcx_v1_control.worker_status()["pending"] == 0
        assert server.maintenance_admission.snapshot()["owners"] == {}
        served.append(server)

    monkeypatch.setattr(kronos_browser, "create_browser_server", capture)
    monkeypatch.setattr(KronosBrowserServer, "serve_forever", serve)
    ended = []
    original_end = kronos_browser.SharedAuthenticatedProviderRuntime.end_kronos_session
    def end_session(runtime):
        ended.append(runtime)
        return original_end(runtime)
    monkeypatch.setattr(kronos_browser.SharedAuthenticatedProviderRuntime,
                        "end_kronos_session", end_session)
    def fail(*_args, **_kwargs):
        raise RuntimeError("isolated " + failure_stage + " startup failure")
    if failure_stage == "housekeeping":
        monkeypatch.setattr(kronos_browser, "_compose_housekeeping", fail)
    elif failure_stage == "ready":
        monkeypatch.setattr("kronos.browser.runtime_state.complete_startup", fail)
    elif failure_stage == "workspace":
        monkeypatch.setattr(kronos_browser.webbrowser, "open_new_tab", fail)
    args = ["--port", "0"] + ([] if failure_stage == "workspace" else ["--no-browser"])
    try:
        if checkpoint_matches and failure_stage is None:
            assert kronos_browser.main(args) == 0
            assert served == servers and len(served) == 1
        else:
            error = ValueError if failure_stage is None else RuntimeError
            message = ("WO13_NOTIFICATION_CHECKPOINT_MISMATCH" if failure_stage is None
                       else "isolated " + failure_stage + " startup failure")
            with pytest.raises(error, match=message):
                kronos_browser.main(args)
            assert not served
            # Failure after server construction must clean canonical owners;
            # the test's defensive finally must not hide a leaked listener.
            assert len(servers) == 1
            failed = servers[0]
            assert failed.socket.fileno() == -1
            assert failed.swing_research_control._worker_closed
            assert failed.application._SwingOpportunitiesApplication__research_capture is None
            assert all(owner._research_capture is None
                       for owner, _callback in failed._research_owner_bindings
                       if owner is not failed.application)
            assert failed.mcx_v1_control.worker_status()["state"] == "CLOSED"
            assert failed.maintenance_admission.snapshot()["owners"] == {}
        assert len(ended) == 1
    finally:
        for server in servers:
            server.server_close()
    after = {str(path): (path.read_bytes(), path.stat().st_mtime_ns,
                        path.stat().st_ctime_ns)
             for path in (tmp_path / "historical").rglob("*") if path.is_file()}
    assert after == before


def test_canonical_housekeeping_composes_enabled_actual_owned_stores(
    tmp_path,
) -> None:
    from kronos.swing.v1.review_evidence_store import ReviewEvidenceStore
    from tests.unit.application.test_intraday_research import _application

    review = ReviewEvidenceStore(tmp_path / "review")
    review.root.mkdir(parents=True)
    (review.root / "receipts").mkdir()
    pending = review.root / "receipts" / ".prepared-canonical"
    pending.write_bytes(b"disposable")
    research, _ = _application(tmp_path / "research")
    publication = research.update(operation_identity="PF10-CANONICAL-HOUSEKEEPING")
    stage = research.store.root / "staging" / __import__(
        "kronos.intraday.wo12_research_contract", fromlist=["digest"]
    ).digest("PF10-CANONICAL-HOUSEKEEPING")
    stage.mkdir(parents=True)
    shutil.copyfile(publication.workbook_path, stage / publication.workbook_path.name)
    server = SimpleNamespace(native_intake=SimpleNamespace(store=review))
    runtime = SimpleNamespace(research_application=research)

    queued = []
    clock = [0.0]
    canonical = kronos_browser._compose_housekeeping(
        server,
        runtime,
        clock=lambda: clock[0],
        background_runner=queued.append,
    )
    status = canonical.status_document()
    assert status["production_activation"] is True
    assert status["lifecycle_state"] == "IDLE"
    assert status["interval_seconds"] == 6 * 60 * 60
    assert canonical.trigger_periodic(now=(6 * 60 * 60) - 1) == "NOT_DUE"
    assert pending.exists() and stage.exists()
    assert canonical.trigger_periodic(now=6 * 60 * 60) == "SCHEDULED"
    assert canonical.trigger_periodic(now=6 * 60 * 60) == "PENDING"
    clock[0] = 6 * 60 * 60
    queued.pop()()
    assert not pending.exists() and not stage.exists()
    assert research.open_current("2026_08")[1] == publication.workbook_path.read_bytes()
    result = canonical.status_document()
    assert result["last_result"]["removed_files"] == 2
    assert result["next_due_monotonic"] == 2 * 6 * 60 * 60


def test_macos_launcher_is_minimal_double_click_app_without_credentials() -> None:
    root = Path(__file__).resolve().parents[3]
    executable = root / "tools/macos/KRONOS.app/Contents/MacOS/KRONOS"
    launcher_source = root / "tools/macos/kronos_launcher.c"
    plist = root / "tools/macos/KRONOS.app/Contents/Info.plist"
    brand_mark = root / "assets/images/brand/kronos-brand-mark.png"
    icon_png = root / "tools/macos/KRONOS.app/Contents/Resources/KRONOS.png"
    icon_icns = root / "tools/macos/KRONOS.app/Contents/Resources/KRONOS.icns"
    source = launcher_source.read_text(encoding="utf-8")
    assert executable.stat().st_mode & 0o111
    assert executable.read_bytes()[:4] in {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"}
    assert "discover_repository" in source
    assert "Documents/GitHub" in source
    assert "directory_exists(git_directory)" in source
    assert "matches == 1" in source
    assert ".rc02-publication-worktree" not in source
    assert ".venv/bin/python" in source
    assert "tools/kronos_browser.py" in source
    assert ".ready = backend_is_ready" in source
    assert "GET /status HTTP/1.0" in source
    assert "POST /control/shutdown HTTP/1.0" in source
    assert "request_graceful_shutdown" in source
    assert "wait_for_backend_stop" in source
    assert (
        "if (!bootstrap && !replacement && backend_is_reusable(control_path)) "
        "return open_workspace();"
    ) in source
    assert 'strcmp(mode, "GOVERNED_REPLACEMENT") == 0' in source
    assert 'getenv("KRONOS_REPLACEMENT_REVISION")' in source
    assert "show_existing_backend_unhealthy" in source
    assert "acquire_launcher_lock(repository)" in source
    assert "It was not reused" not in source
    assert "KRONOS restart blocked" in source
    assert "KRONOS is still starting" in source
    assert "http://127.0.0.1:8947/swing/opportunities" in source
    assert '"/usr/bin/osascript"' in source
    assert "set active tab index of browserWindow to tabNumber" in source
    assert "open location" in source
    assert 'Google Chrome' in source
    assert "setsid()" in source
    assert "Terminal" not in source
    assert "api_key" not in source.lower()
    assert "secret" not in source.lower()
    assert "com.project-kronos.browser-v1" in plist.read_text(encoding="utf-8")
    assert "<string>KRONOS</string>" in plist.read_text(encoding="utf-8")
    assert icon_png.read_bytes() == brand_mark.read_bytes()
    assert icon_icns.read_bytes().startswith(b"icns")


def test_wo08_canonical_main_binds_actual_collector_before_ready_and_serve(tmp_path, monkeypatch):
    from kronos.application.intraday_wo08_shadow import Wo08ShadowCollector
    from kronos.intraday.wo08_shadow_persistence import Wo08ShadowStore
    from kronos.application.intraday_reliance_bootstrap import DEFAULT_INTRADAY_EVIDENCE_ROOT

    runtimes, servers, bound, order = [], [], [], []
    from kronos.application.intraday_live_shadow import IntradayLiveShadowService
    dependency_init = IntradayLiveShadowService.__init__
    store_init = Wo08ShadowStore.__init__
    collector_init = Wo08ShadowCollector.__init__

    def dependencies(owner, *args, **kwargs):
        dependency_init(owner, *args, **kwargs)
        order.append('analysis-dependencies')

    def store_created(owner, *args, **kwargs):
        assert order == ['analysis-dependencies']
        store_init(owner, *args, **kwargs)
        order.append('store')

    def collector_created(owner, *args, **kwargs):
        assert order == ['analysis-dependencies', 'store']
        collector_init(owner, *args, **kwargs)
        order.append('collector')

    monkeypatch.setattr(IntradayLiveShadowService, '__init__', dependencies)
    monkeypatch.setattr(Wo08ShadowStore, '__init__', store_created)
    monkeypatch.setattr(Wo08ShadowCollector, '__init__', collector_created)
    monkeypatch.setattr(kronos_browser, '_build_provider',
                        lambda **_: pytest.fail('startup/GET called Provider builder'))
    original_runtime = kronos_browser.create_intraday_runtime
    original_server = kronos_browser.create_browser_server
    original_bind = Wo08ShadowCollector.bind_maintenance_admission

    def runtime(*args, **kwargs):
        # Observe the real canonical argument; do not inject a collector.
        composed = original_runtime(*args, **kwargs)
        assert type(composed.wo08_shadow) is Wo08ShadowCollector
        assert type(composed.wo08_shadow.store) is Wo08ShadowStore
        assert callable(kwargs['wo08_shadow_factory'])
        assert 'wo08_shadow' not in kwargs
        assert composed.discovery_v2_operation.wo08_shadow is composed.wo08_shadow
        runtimes.append(composed)
        return composed

    def server(*args, **kwargs):
        composed = original_server(*args, **kwargs)
        servers.append(composed)
        order.append('server')
        return composed

    def checked(collector, coordinator):
        assert len(runtimes) == len(servers) == 1
        assert collector is runtimes[0].wo08_shadow
        assert coordinator is servers[0].maintenance_admission
        assert collector.store.root == DEFAULT_INTRADAY_EVIDENCE_ROOT / 'wo08-research-only-v1'
        assert not collector.store.root.exists()
        assert collector._worker is None
        assert runtimes[0].provider_access._runtime.active_lease_count == 0
        original_bind(collector, coordinator)
        bound.append(coordinator)
        order.append('bound')

    monkeypatch.setattr(kronos_browser, 'create_intraday_runtime', runtime)
    monkeypatch.setattr(kronos_browser, 'create_browser_server', server)
    monkeypatch.setattr(Wo08ShadowCollector, 'bind_maintenance_admission', checked)
    checkpoints = []

    def check_before_ready_and_serve(server):
        collector = runtimes[0].wo08_shadow
        assert collector.maintenance_coordinator is server.maintenance_admission
        assert bound == [server.maintenance_admission]
        assert collector._worker is None and not collector.store.root.exists()
        assert collector.snapshot()['counts']['attempted'] == 0
        assert runtimes[0].provider_access._runtime.active_lease_count == 0
        order.append('ready' if not checkpoints else 'serve')
        if checkpoints:
            # Exercise real read-only handlers on a disposable allowed test socket.
            from http.client import HTTPConnection
            from threading import Thread
            before = collector.snapshot()
            for path in ('/status', '/intraday'):
                worker = Thread(target=server.handle_request)
                worker.start()
                connection = HTTPConnection(*server.server_address, timeout=3)
                try:
                    connection.request('GET', path)
                    response = connection.getresponse()
                    assert response.status == 200
                    assert response.read()
                finally:
                    connection.close()
                    worker.join(3)
                assert not worker.is_alive()
                assert collector.snapshot() == before
                assert not collector.store.root.exists() and collector._worker is None
        checkpoints.append(server)

    # Real composition, actual server and pre-READY/serve assertions; no injected collector.
    test_canonical_main_installs_real_mcx_owner_before_ready_without_acquisition(
        tmp_path, monkeypatch, _check_wo08=check_before_ready_and_serve,
    )
    assert checkpoints == [servers[0], servers[0]]
    assert order == ['analysis-dependencies', 'store', 'collector', 'server', 'bound', 'ready', 'serve']
    collector = runtimes[0].wo08_shadow
    assert bound == [servers[0].maintenance_admission]
    assert collector.maintenance_coordinator is bound[0]
    assert not collector.store.root.exists()
    assert collector.snapshot()['counts'] == dict(
        eligible=0, attempted=0, admitted=0, not_admitted=0,
        captured=0, failed=0, partial=0, excluded=0,
    )
    assert collector._worker is None and collector.snapshot()['closed'] is True


@pytest.mark.parametrize('failure', ['store', 'collector'])
def test_canonical_startup_isolates_unavailable_research_construction(tmp_path, monkeypatch, failure):
    from kronos.application.intraday_wo08_shadow import Wo08ShadowCollector, UnavailableWo08ShadowCollector
    from kronos.intraday.wo08_shadow_persistence import Wo08ShadowStore
    calls, observed = [], []

    def fail(*args, **kwargs):
        calls.append(True)
        raise OSError('research unavailable')

    monkeypatch.setattr(Wo08ShadowStore if failure == 'store' else Wo08ShadowCollector, '__init__', fail)
    original = kronos_browser.create_intraday_runtime
    def runtime(*args, **kwargs):
        composed = original(*args, **kwargs)
        assert type(composed.wo08_shadow) is UnavailableWo08ShadowCollector
        observed.append(composed.wo08_shadow)
        return composed
    monkeypatch.setattr(kronos_browser, 'create_intraday_runtime', runtime)
    monkeypatch.setattr(kronos_browser, '_build_provider',
                        lambda **_: pytest.fail('unavailable research acquired Provider'))

    def check(server):
        owner = observed[0]
        assert owner.maintenance_coordinator is server.maintenance_admission
        assert owner.snapshot()['availability'] == 'UNAVAILABLE'
        assert owner.snapshot()['unavailable_reason'] == 'WO08_CONSTRUCTION_UNAVAILABLE'
        assert owner.snapshot()['unavailable_error_type'] == 'OSError'
        assert owner.store is None and owner._worker is None
        assert server.maintenance_admission.snapshot()['owners'] == {}

    test_canonical_main_installs_real_mcx_owner_before_ready_without_acquisition(
        tmp_path, monkeypatch, _check_wo08=check,
    )
    assert len(calls) == len(observed) == 1
    assert observed[0].snapshot()['closed'] is True
