"""Sponsor and developer entry point for the local KRONOS Browser V1."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
import webbrowser
import os
from hashlib import sha256

from pathlib import Path
# Bootstrap is entry-local, as StartupCapture cannot retroactively certify a
# normally preloaded application module. Execute only this exact custody source;
# compare it to the retained snapshot before any application import/effect.
# State exists before adoption/capture/imports. Missing state is never authority.
_ADMISSION = None
_ADMISSION_PAYLOAD = None
_admission_bootstrap = None
_pinned_release_admission = None
_CUSTODY_ADOPTED = False
_ENTRY_PHASE = "ADOPTION"
_NATIVE_STARTUP_FACTS = None


def _failure_attribute(value, name, default=None):
    try:return getattr(value, name, default)
    except BaseException:return default


def _fallback_failure_report(phase, deadline):
    # Entry-local standard-library fallback for an incomplete bootstrap module.
    # O_NONBLOCK is one-way for the shared startup stream; never restore flags.
    import fcntl
    import json
    try:
        raw = (json.dumps({"schema": "KRONOS_VALIDATION_OUTCOME_V1",
            "phase": phase, "clock": "CLOCK_MONOTONIC", "deadline_ns": deadline,
            "direct_child": None, "observed_result": "STARTUP_FAILURE",
            "cleanup": "CLEANUP_UNRESOLVED"}, separators=(",", ":")) + "\n").encode()
        flags = fcntl.fcntl(2, fcntl.F_GETFL)
        fcntl.fcntl(2, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        return os.write(2, raw) == len(raw)
    except BaseException:
        return False


def _retain_early_failure(custody, modules):
    # No adoption, reopening, retry or product cleanup is attempted here. Keep
    # the process/reference alive even when optional module state is incomplete.
    import time
    while True:
        try:
            for module in modules:
                children = _failure_attribute(module, "_OWNED_VALIDATION_HELPERS", {})
                if isinstance(children, dict):
                    for child in tuple(children.values()):
                        try:child.poll()
                        except BaseException:pass
            time.sleep(.1)
        except BaseException:
            continue


def _handle_canonical_failure():
    custody = globals().get("_ADMISSION")
    modules = tuple(module for module in (globals().get("_admission_bootstrap"),
        globals().get("_pinned_release_admission")) if module is not None)
    complete = (_failure_attribute(custody, "cleanup_complete", False) is True
                and _failure_attribute(custody, "released", False) is True
                and globals().get("_CUSTODY_ADOPTED") is True)
    def unresolved_modules():
        if not modules:return True
        for module in modules:
            reader = _failure_attribute(module, "validation_unresolved")
            if not callable(reader):return True
            try:
                if reader() is not False:return True
            except BaseException:return True
        return False
    unresolved = unresolved_modules()
    stage = globals().get("_ENTRY_PHASE")
    if stage not in {"ADOPTION", "PRE_CAPTURE", "CAPTURE", "PINNED_IMPORTS", "MAIN"}:
        stage = "UNKNOWN"
    phase = "CANONICAL_" + stage
    deadline = _failure_attribute(_failure_attribute(custody, "budget"), "deadline_ns", 0)
    if type(deadline) is not int or deadline < 0:deadline = 0
    reported = False
    for module in modules:
        reporter = _failure_attribute(module, "report_validation")
        if callable(reporter):
            try:
                reporter(phase, deadline, None, "STARTUP_FAILURE",
                         "COMPLETED_CLEANUP" if complete and not unresolved else "CLEANUP_UNRESOLVED")
                reported = True
                break
            except BaseException:
                unresolved = True
    if not reported:
        _fallback_failure_report(phase, deadline)
        unresolved = True
    unresolved = unresolved or unresolved_modules()
    if ((custody is not None or globals().get("_CUSTODY_ADOPTED") is True)
            and _failure_attribute(custody, "released", False) is not True):
        # A validly adopted reference cannot be dropped because capture/imports
        # failed before main. A partial retainer is not allowed to escape either.
        for module in modules:
            retainer = _failure_attribute(module, "retain_failure_custody")
            if callable(retainer):
                try:retainer(custody, modules)
                except BaseException:pass
                break
        _retain_early_failure(custody, modules)
    return 78 if complete and not unresolved else 79


# One boundary covers adoption, pre-capture validation, capture/pinned imports,
# definitions and canonical main execution. Normal SystemExit is outside it.
try:
    if __name__ == "__main__":
        import sys
        import types
        os.set_inheritable(197, False)
        _admission_path = Path(__file__).resolve().parents[1] / "src/kronos/common/release_admission.py"
        _ADMISSION_PAYLOAD = _admission_path.read_bytes()
        _admission_bootstrap = types.ModuleType("_kronos_admission_bootstrap")
        sys.modules[_admission_bootstrap.__name__] = _admission_bootstrap
        exec(compile(_ADMISSION_PAYLOAD, str(_admission_path), "exec"), _admission_bootstrap.__dict__)
        _ADMISSION = _admission_bootstrap.adopt_from_launcher()
        _CUSTODY_ADOPTED = True
        _ENTRY_PHASE = "PRE_CAPTURE"


    def _check_admission():
        if _ADMISSION is not None:
            _ADMISSION.check()


    def _reconcile_admission_module_identity():
        """Make the pinned consumer observe the one adopted custody class.

        The launcher executes the admission source once before capture and
        StartupCapture later imports the same pinned bytes as the normal
        package module.  Those two module objects must not create two custody
        type identities.  We verify byte equality before aliasing only the
        shared contract classes; no second lock or custody object is made.
        """
        if _admission_bootstrap is None or _pinned_release_admission is None:
            raise ValueError("RESTORATION_ADMISSION_MODULE_UNAVAILABLE")
        if _ADMISSION_PAYLOAD != Path(
                _pinned_release_admission.__file__).read_bytes():
            raise ValueError("RESTORATION_ADMISSION_SOURCE_MISMATCH")
        if (_admission_bootstrap.PERSISTENT_ANCHOR_BINDING != _pinned_release_admission.PERSISTENT_ANCHOR_BINDING):
            raise ValueError('PERSISTENT_ADMISSION_POLICY_MISMATCH')
        for name in ("AdmissionCustody", "ValidationBudget"):
            bootstrap_type = getattr(_admission_bootstrap, name, None)
            pinned_type = getattr(_pinned_release_admission, name, None)
            if bootstrap_type is None or pinned_type is None:
                raise ValueError("RESTORATION_ADMISSION_TYPE_UNAVAILABLE")
            if pinned_type is not bootstrap_type:
                setattr(_pinned_release_admission, name, bootstrap_type)


    from kronos.intraday.runtime_identity import StartupCapture, LauncherConfiguration


    class _EntryStartupCapture(StartupCapture):
        def _git(self, *args):
            _check_admission()
            return _admission_bootstrap.validation_output(["git", *args], cwd=self._root,
                budget=_ADMISSION.budget, ceiling=10, phase="STARTUP_CAPTURE")


    _Capture = _EntryStartupCapture if _ADMISSION is not None else StartupCapture

    _check_admission()

    # Capture before application imports. Never replace this with a later HEAD lookup.
    _ENTRY_PHASE = "CAPTURE"
    with _Capture(Path(__file__).resolve().parents[1], keep_sources_pinned=True) as _startup_capture:
        if _ADMISSION_PAYLOAD is not None:
            _pinned_admission = _startup_capture._sources.get("kronos.common.release_admission")
            if (_pinned_admission is None or _pinned_admission[1] != _ADMISSION_PAYLOAD):
                raise ValueError("INSTALLATION_ADMISSION_SOURCE_NOT_PINNED")
        _ENTRY_PHASE = "PINNED_IMPORTS"
        from kronos.common import release_admission as _pinned_release_admission
        from kronos.application.provider_instrument_master_operation import (
            ProviderInstrumentMasterOperationalComposition,
        )
        from kronos.application.housekeeping import (
            BoundedHousekeeping,
            intraday_research_staging_scope,
            review_preparation_scope,
        )
        from kronos.application.mcx_official_check import McxOfficialCheckEngine, OfficialHttpsTransport
        from kronos.application.swing_opportunities import SwingOpportunitiesApplication
        from kronos.application.swing_analysis_process import SwingAnalysisProcessOwner
        from kronos.application.intraday_runtime import create_intraday_runtime
        from kronos.application.intraday_reliance_bootstrap import DEFAULT_INTRADAY_EVIDENCE_ROOT
        from kronos.application.intraday_wo08_shadow import compose_wo08_shadow
        from kronos.application.intraday_statistics import IntradayStatisticsApplication
        from kronos.browser.server import (create_browser_server, _StartupCleanup,
            _startup_work_stopped, _startup_application_closed, _startup_provider_closed,
            _startup_notifications_closed)
        from kronos.browser.intraday_discovery_control import (
            IntradayDiscoveryOperationalControl,
        )
        from kronos.browser.intraday_probables_v2_control import (
            IntradayProbablesV2OperationalControl,
        )
        from kronos.browser.intraday_review_v2_control import (
            IntradayReviewV2OperationalControl,
        )
        from kronos.browser.intraday_visual_reconciliation_v2_control import (
            IntradayVisualReconciliationV2OperationalControl,
        )
        from kronos.browser.intraday_wo10_control import (
            IntradayWo10OperationalControl,
        )
        from kronos.browser.intraday_wo09_control import IntradayWo09Projection
        from kronos.browser.intraday_futures_control import IntradayFuturesControl, domain008_session
        from kronos.browser.intraday_wo11_control import (
            IntradayWo11OperationalControl,
        )
        from kronos.browser.intraday_wo12_v2_control import (
            IntradayWo12V2OperationalControl,
        )
        from kronos.browser.intraday_wo13_control import IntradayWo13OperationalControl
        from kronos.browser.intraday_wo14_control import IntradayWo14OperationalControl
        from kronos.browser.intraday_wo15_control import IntradayWo15OperationalControl
        from kronos.browser.intraday_wo16_control import IntradayWo16OperationalControl
        from kronos.browser.intraday_wo17_control import IntradayWo17OperationalControl
        from kronos.browser.intraday_operational_readiness import (
            IntradayOperationalReadinessProjection,
        )
        from kronos.browser.intraday_routes import IntradayBrowserRoutes
        from kronos.browser.product_routes import ProductBrowserRoutes
        from kronos.browser.theta_composition import compose_theta_browser_routes
        from kronos.theta.composition import compose_theta_sponsor_workflow
        from kronos.browser.intraday_historical_control import (
            IntradayHistoricalQualificationOperationalControl,
        )
        from kronos.browser.restart_control import BrowserBackendRestartControl, DEFAULT_BACKEND_CONTROL_PATH
        from kronos.common.connection_governance import ConnectionProcess, ConnectionAuditStore, ConnectionGovernance
        from kronos.common.legacy_bootstrap import consume_startup_context
        from kronos.common.maintenance import DrainStartupContext
        from kronos.market.calendar import MarketCalendarPublisher
        from kronos.application.swing_mcx_v1_composition import install_canonical_mcx_v1
        from kronos.intraday.universe import load_intraday_universe_publication
        from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
        from kronos.provider.adapters.kite.navigation import KiteBrowserRedirectNavigator
        from kronos.provider.instrument_master_persistence import (
            DEFAULT_PROVIDER_INSTRUMENT_SNAPSHOT_ROOT,
            ProviderInstrumentSnapshotStore,
        )
        from kronos.provider.runtime import SharedAuthenticatedProviderRuntime
        from kronos.swing.run_provenance import LocalSwingRunProvenanceStore
        from kronos.swing.v1.mtf_facts import (
            DEFAULT_MTF_FACT_EVIDENCE_ROOT,
            MtfFactEvidenceStore,
        )
        from kronos.swing.v1.native_discovery import (
            DEFAULT_NATIVE_DISCOVERY_EVIDENCE_ROOT,
            NativeDiscoveryEvidenceStore,
        )
        from kronos.swing.v1.relative_context import (
            DEFAULT_RELATIVE_CONTEXT_EVIDENCE_ROOT,
            RelativeContextEvidenceStore,
        )
        from tools.provider_pilots.provider_foundation_v2_historical_proof import (
            _build_provider,
        )
        _STARTUP_EVIDENCE = _startup_capture.finish()
    # Restoration uses this original capture's immutable byte roster after
    # bootstrap. Keep the same object that owns the pinned-import snapshot.
    _check_admission()


    CANONICAL_HOUSEKEEPING_ACTIVATION = True


    def _compose_housekeeping(
        server,
        intraday_runtime,
        *,
        production_activation: bool = CANONICAL_HOUSEKEEPING_ACTIVATION,
        **testing,
    ):
        intake = getattr(server, "native_intake", None)
        store = None if intake is None else getattr(intake, "store", None)
        research = getattr(intraday_runtime, "research_application", None)
        if store is None or research is None:
            raise ValueError("CANONICAL_HOUSEKEEPING_OWNER_UNAVAILABLE")
        return BoundedHousekeeping(
            (
                review_preparation_scope(store),
                intraday_research_staging_scope(research),
            ),
            production_activation=production_activation,
            **testing,
        )


    def _validation_cleanup_unresolved():
        return any(getattr(globals().get(name), "validation_unresolved", lambda: False)()
                   for name in ("_admission_bootstrap", "_pinned_release_admission"))


    def _release_startup_output():
        if _ADMISSION_PAYLOAD is not None:
            log_sink = os.open(os.devnull, os.O_WRONLY | os.O_CLOEXEC)
            try:os.dup2(log_sink, 2)
            finally:os.close(log_sink)


    def _activate_canonical_notifications(server):
        """Release actual adopted custody, then activate the existing owner.

        A returned startup function, receipt or caller boolean is not authority.
        Only the canonical bootstrap's exact adopted custody class can execute
        its existing READY/receipt validation and successful close-only release.
        """
        import errno
        from kronos.application.intraday_notifications import IntradayNotifications
        from kronos.application.swing_refresh_reminder import SwingK5RefreshReminderWorkflow
        from kronos.application.swing_ux10 import SwingUx10NotificationService
        custody = _ADMISSION
        custody_type = getattr(_admission_bootstrap, "AdmissionCustody", None)
        notifications = server.intraday_notifications
        ux10 = getattr(server, "ux10_notifications", None)
        reminders = getattr(server, "refresh_reminders", None)
        if (custody is None or type(custody) is not custody_type
                or custody.released or custody.cleanup_started or custody.cleanup_complete
                or type(notifications) is not IntradayNotifications
                or not notifications._deferred_replay
                or type(ux10) is not SwingUx10NotificationService
                or not ux10.delivery_deferred
                or type(reminders) is not SwingK5RefreshReminderWorkflow
                or not reminders._deferred_execution
                or reminders._active or reminders._closed or reminders._failed):
            raise ValueError("WO13_CANONICAL_REPLAY_CUSTODY_UNAVAILABLE")
        facts = _NATIVE_STARTUP_FACTS
        if facts is not None: facts.boundary('ready-release', outcome='intent')
        custody_type.release_ready(custody, server)
        if facts is not None: facts.boundary('ready-release', outcome='returned')
        if (_ADMISSION is not custody or custody.released is not True
                or custody.cleanup_started or custody.cleanup_complete):
            raise ValueError("WO13_CANONICAL_REPLAY_CUSTODY_UNAVAILABLE")
        try:
            os.fstat(custody.descriptor)
        except OSError as error:
            if error.errno != errno.EBADF:
                raise
        else:
            raise ValueError("WO13_CANONICAL_REPLAY_CUSTODY_STILL_OPEN")
        if facts is not None: facts.boundary('ux10', outcome='intent')
        ux10.activate_delivery()
        if facts is not None: facts.boundary('ux10', outcome='returned')
        if facts is not None: facts.boundary('wo13', outcome='intent')
        notifications._activate_replay()
        if facts is not None: facts.boundary('wo13', outcome='returned')
        if facts is not None: facts.boundary('k5', outcome='intent')
        reminders._activate_execution()
        if facts is not None: facts.boundary('k5', outcome='returned')
        checker = getattr(server, 'mcx_official_check', None)
        if checker is not None:
            checker.activate_from_canonical(server, custody)
            checker.trigger_scheduled()


    def _compose_mcx_official_check(server):
        from kronos.theta.operational import reviewed_owner
        return McxOfficialCheckEngine(
            Path.home() / 'Library/Application Support/KRONOS/evidence/shared/mcx-official-check-v1',
            transport=OfficialHttpsTransport(), authority_provider=reviewed_owner)


    def _parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description="Launch local KRONOS Browser V1")
        parser.add_argument("--port", type=int, default=8947)
        parser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
        return parser


    _LAST_STARTUP_CLEANUP = None

    def main(argv: Sequence[str] | None = None) -> int:
        global _LAST_STARTUP_CLEANUP
        cleanup = _StartupCleanup()
        _LAST_STARTUP_CLEANUP = cleanup
        try:
            return _run_main(argv, cleanup)
        except BaseException as error:
            cleanup.original_failure = error
            raise
        finally:
            pending = (_ADMISSION is not None
                and _failure_attribute(_ADMISSION, "released", False) is not True)
            custody_cleanup_available = True
            if pending:
                begin = _failure_attribute(_ADMISSION, "begin_failure_cleanup")
                if callable(begin):
                    try:
                        begin()
                    except BaseException as error:
                        cleanup.errors.append(("admission", error))
                        custody_cleanup_available = False
                else:
                    custody_cleanup_available = False
            # The original startup budget also bounds observation of an entered
            # K5 callback. No new budget, repeated close or forced unlock.
            deadline = (_ADMISSION.budget.deadline_ns / 1_000_000_000
                        if _ADMISSION is not None and
                        (pending or cleanup.original_failure is not None) else None)
            stop_context = getattr(cleanup.server,'_ordinary_stop_context',None)
            if stop_context is not None:
                stop_deadline=stop_context[1].budget.deadline_ns/1_000_000_000
                deadline=stop_deadline if deadline is None else min(deadline,stop_deadline)
            complete = cleanup.cleanup(deadline=deadline) and custody_cleanup_available
            server = cleanup.server
            if complete and server is not None:
                server._domain_closed = True
            # Fully composed startup ALWAYS retains the existing stronger proof.
            proof = (server._maintenance_final_owner_proof()
                     if server is not None and server._startup_fully_composed else complete)
            if stop_context is not None:
                try:
                    if not complete or not proof or _validation_cleanup_unresolved():
                        raise RuntimeError('ORDINARY_STOP_CLEANUP_UNRESOLVED')
                    from kronos.common.legacy_bootstrap import publish_ordinary_stop_owners
                    publish_ordinary_stop_owners(server,stop_context)
                except BaseException as error:
                    cleanup.errors.append(('ordinary-stop',error));complete=False
                    if cleanup.original_failure is None:raise
                    cleanup.original_failure.add_note('Ordinary stop evidence unresolved: '+type(error).__name__)
            facts = _NATIVE_STARTUP_FACTS
            if facts is not None and not facts.startup_success_published:
                try:
                    facts.cleanup_observed(cleanup, complete=complete, final_owner_proof=proof,
                        helpers_unresolved=_validation_cleanup_unresolved())
                except BaseException as error:
                    cleanup.errors.append(('native-facts', error))
                    complete = False  # Missing durable facts cannot acknowledge cleanup.
            if pending:
                if (complete and proof and not _validation_cleanup_unresolved()
                        and callable(_failure_attribute(_ADMISSION, "completed_failure_cleanup"))):
                    _ADMISSION.completed_failure_cleanup()
                    if facts is not None:
                        try: facts.cleanup_acknowledged()
                        except BaseException as error:
                            cleanup.errors.append(('native-cleanup-ack', error))
                            if cleanup.original_failure is None: raise
                elif cleanup.original_failure is None:
                    raise RuntimeError("INSTALLATION_ADMISSION_CLEANUP_UNRESOLVED")
            if not complete and cleanup.original_failure is None:
                raise RuntimeError("STARTUP_RESOURCE_CLEANUP_UNRESOLVED")
            if cleanup.original_failure is not None:
                for name, error in cleanup.errors:
                    cleanup.original_failure.add_note("Cleanup unresolved: " + name + ":" + type(error).__name__)

    def _run_main(argv, cleanup):
        global _NATIVE_STARTUP_FACTS
        _check_admission()
        args = _parser().parse_args(argv)
        from tools.runtime_source_gate import qualify_startup
        qualify_startup(Path(__file__).resolve().parents[1], _STARTUP_EVIDENCE)
        _check_admission()
        process_identity = sha256(_STARTUP_EVIDENCE.evidence_identity.encode()).hexdigest()
        if _CUSTODY_ADOPTED:
            _reconcile_admission_module_identity()
            from kronos.common.legacy_bootstrap import NativeStartupFacts
            _NATIVE_STARTUP_FACTS = NativeStartupFacts(os.environ, custody=_ADMISSION,
                evidence=_STARTUP_EVIDENCE, capture=_startup_capture)
        restoration_child = None
        restoration_observation = None
        restoration_attempt = None
        restoration_mode = (os.environ.get("KRONOS_LAUNCH_MODE") ==
                            "FAILED_SUCCESSOR_RESTORATION")
        if restoration_mode:
            _reconcile_admission_module_identity()
            from kronos.common.legacy_bootstrap import capture_restoration_child
            repository = Path(__file__).resolve().parents[1]
            captured_sources = tuple(sorted(
                (name, Path(item[0]).relative_to(repository).as_posix(),
                 sha256(item[1]).hexdigest())
                for name, item in _startup_capture._sources.items()))
            restoration_observation = capture_restoration_child(
                os.environ,
                custody=_ADMISSION,
                process_id=os.getpid(),
                parent_pid=os.getppid(),
                runtime_identity=process_identity,
                loaded_revision=_STARTUP_EVIDENCE.source_revision,
                pinned_capture_sha256=_STARTUP_EVIDENCE.source_snapshot_digest,
                repository=repository,
                captured_sources=captured_sources,
                loaded_modules=_STARTUP_EVIDENCE.loaded_modules,
                load_verification=_STARTUP_EVIDENCE.load_verification,
            )
            restoration_child = restoration_observation.child
        maintenance = consume_startup_context(DEFAULT_BACKEND_CONTROL_PATH.parent, os.environ,
            revision=_STARTUP_EVIDENCE.source_revision, source_state=_STARTUP_EVIDENCE.source_state,
            repository=Path(__file__).resolve().parents[1],
            runtime_identity=process_identity, now=datetime.now(UTC),
            **({"custody": _ADMISSION,
                "restoration_observation": restoration_observation,
                "restoration_retain": True}
               if restoration_mode else {}))
        if restoration_mode:
            from kronos.common.legacy_bootstrap import RestorationAttempt
            if type(maintenance) is not RestorationAttempt:
                raise ValueError("RESTORATION_ACCEPTED_ATTEMPT_MISSING")
            restoration_attempt = maintenance
            maintenance = restoration_attempt.context
        if _NATIVE_STARTUP_FACTS is not None:
            _NATIVE_STARTUP_FACTS.consumed(maintenance, DEFAULT_BACKEND_CONTROL_PATH.parent / 'maintenance')
        from kronos.common.failed_successor_restore import RestorationStartupContext
        if isinstance(maintenance, RestorationStartupContext):
            maintenance_identity = maintenance.maintenance_identity
            expected_notification_checkpoint = maintenance.notification_checkpoint()
        else:
            maintenance_identity = (maintenance.generation if isinstance(
                maintenance, DrainStartupContext) else maintenance)
            expected_notification_checkpoint = (maintenance.notification_checkpoint()
                if isinstance(maintenance, DrainStartupContext) else None)
        _check_admission()
        governance = ConnectionGovernance(ConnectionProcess(
            _STARTUP_EVIDENCE.process_id, _STARTUP_EVIDENCE.startup_boundary_at.isoformat(),
            process_identity, _STARTUP_EVIDENCE.source_revision, _STARTUP_EVIDENCE.source_state),
            ConnectionAuditStore(Path.home() / "Library/Application Support/KRONOS/evidence/shared/provider-connection-v1"),
            maintenance_identity=maintenance_identity or process_identity)
        mtf_fact_store = MtfFactEvidenceStore(DEFAULT_MTF_FACT_EVIDENCE_ROOT)
        native_discovery_store = NativeDiscoveryEvidenceStore(
            DEFAULT_NATIVE_DISCOVERY_EVIDENCE_ROOT
        )
        relative_context_store = RelativeContextEvidenceStore(
            DEFAULT_RELATIVE_CONTEXT_EVIDENCE_ROOT
        )
        provider_login_navigation = KiteBrowserRedirectNavigator()
        callback_return_url = f"http://127.0.0.1:{args.port}/swing/opportunities"
        shared_provider_runtime = cleanup.construct("provider", lambda: (SharedAuthenticatedProviderRuntime(
            lambda: _build_provider(
                navigator=provider_login_navigation,
                callback_return_url=callback_return_url,
            ),
            provider_identity="KITE",
            connection_governance=governance,
        )), "end_kronos_session", _startup_provider_closed)
        swing_provider_factory = lambda: shared_provider_runtime.compatibility_facade(
            consumer_identity="SWING",
            operations=frozenset({
                ReadOnlyProviderOperation.INSTRUMENTS,
                ReadOnlyProviderOperation.INSTRUMENT_ASSERTIONS,
                ReadOnlyProviderOperation.HISTORICAL_DATA,
                ReadOnlyProviderOperation.QUOTE,
                ReadOnlyProviderOperation.LTP,
                ReadOnlyProviderOperation.OHLC,
                ReadOnlyProviderOperation.MONITORING,
            }),
        )
        _check_admission()
        intraday_runtime = cleanup.returned_intraday_composition(lambda: (create_intraday_runtime(
            shared_provider_runtime, startup_evidence=_STARTUP_EVIDENCE,
            # Construction is inert; only future completed Analysis can admit work.
            wo08_shadow_factory=lambda: compose_wo08_shadow(DEFAULT_INTRADAY_EVIDENCE_ROOT),
        )))
        cleanup.own("lifecycle", intraday_runtime.lifecycle_application, "shutdown", _startup_work_stopped)
        cleanup.own("experimental", intraday_runtime.wo09_application.experimental_watches, "shutdown",
            lambda o: o._queue_closed and not o._queue and not o.registrations
                and (o._worker_thread is None or not o._worker_thread.is_alive()))
        cleanup.own("wo17", intraday_runtime.wo17_monitoring, "shutdown", _startup_work_stopped)
        shadow = intraday_runtime.wo08_shadow
        if shadow is not None:
            cleanup.own("wo08_shadow", shadow, "close", lambda o: o.snapshot()["closed"])
        else:
            cleanup.absent_returned_shadow(intraday_runtime)
        intraday_discovery_control = IntradayDiscoveryOperationalControl(
            intraday_runtime.discovery_operation,
            intraday_runtime.discovery_application,
        )
        intraday_probables_v2_control = IntradayProbablesV2OperationalControl(
            intraday_runtime.discovery_v2_operation,
            intraday_runtime.probables_v2_application,
            intraday_runtime.refresh_v2_provenance_store,
            startup_evidence=intraday_runtime.startup_evidence,
            launcher_configuration=LauncherConfiguration(args.port, not args.no_browser),
        )
        intraday_review_v2_control = IntradayReviewV2OperationalControl(
            intraday_runtime.review_v2_application,
            intraday_runtime.review_v2_operation_store,
        )
        intraday_visual_reconciliation_v2_control = (
            IntradayVisualReconciliationV2OperationalControl(
                intraday_runtime.visual_reconciliation_v2_application
            )
        )
        intraday_wo10_control = IntradayWo10OperationalControl(
            intraday_runtime.wo10_runtime,
            intraday_runtime.probables_v2_store,
            intraday_runtime.wo10_policy_registry,
        )
        from kronos.browser.dashboard import project_intraday_dashboard
        def intraday_dashboard_summary():
            return project_intraday_dashboard(intraday_runtime.wo09_store,
                intraday_runtime.wo09_application.eligibility,
                monitoring_projection=intraday_runtime.wo09_application.experimental_watches.monitoring_projection)
        intraday_wo09_projection = IntradayWo09Projection(intraday_runtime.wo09_store,
            machine_successor=True, operational_summary=intraday_dashboard_summary,
            monitoring_projection=intraday_runtime.wo09_application.experimental_watches.monitoring_projection)
        def futures_guard():
            governance.require_operations()
            return True
        intraday_runtime.futures_application.operational_guard = futures_guard
        def futures_session(subject, now):
            app = intraday_runtime.futures_application
            current = app.store.current(subject)
            contract = None if current is None else app.store.load(current.data["expression_identity"]).data["future"]
            return domain008_session(MarketCalendarPublisher(), subject, now, contract=contract)
        from kronos.browser.intraday_lifecycle_control import IntradayLifecycleControl
        lifecycle_control = IntradayLifecycleControl(intraday_runtime.lifecycle_application)
        intraday_futures_control = IntradayFuturesControl(intraday_runtime.futures_application, futures_session, lifecycle_control)

        intraday_wo11_control = IntradayWo11OperationalControl(
            intraday_runtime.wo11_runtime,
        )
        from kronos.browser.intraday_research import IntradayResearchControl
        intraday_research_control = IntradayResearchControl(
            intraday_runtime.research_application
        )
        intraday_wo12_v2_control = IntradayWo12V2OperationalControl(
            intraday_runtime.wo12_v2_runtime,
        )
        intraday_wo13_control = IntradayWo13OperationalControl(
            intraday_runtime.wo13_application,
            intraday_runtime.wo13_restoration,
            intraday_runtime.wo12_v2_store,
        )
        intraday_wo14_control = IntradayWo14OperationalControl(
            intraday_runtime.wo14_application,
            intraday_runtime.wo14_restoration,
        )
        intraday_wo15_control = IntradayWo15OperationalControl(
            intraday_runtime.wo15_application,
            intraday_runtime.wo15_restoration,
        )
        intraday_wo16_control = IntradayWo16OperationalControl(
            intraday_runtime.wo16_application,
            intraday_runtime.wo16_restoration,
            wo13_store=intraday_runtime.wo13_store,
            wo14_store=intraday_runtime.wo14_store,
            wo15_store=intraday_runtime.wo15_store,
        )
        intraday_wo17_control = IntradayWo17OperationalControl(
            intraday_runtime.wo17_application,
            intraday_runtime.wo17_restoration,
            wo16_store=intraday_runtime.wo16_store,
            monitoring=intraday_runtime.wo17_monitoring,
        )
        intraday_operational_readiness = IntradayOperationalReadinessProjection(
            intraday_runtime.wo_b_runtime
        )
        from kronos.browser.intraday_wo08 import IntradayWo08Projection, IntradayVisualHistory
        intraday_wo08_projection = IntradayWo08Projection(
            intraday_runtime.wo08_store, intraday_runtime.probables_v2_store)
        from kronos.application.intraday_machine_history import IntradayMachineHistory
        intraday_machine_history = IntradayMachineHistory(
            assessments=intraday_runtime.wo08_store,
            probables=intraday_runtime.probables_v2_store,
            readiness=intraday_runtime.wo09_store,
            recent_attempts=intraday_probables_v2_control.analysis_history_document,
        )
        intraday_visual_history = IntradayVisualHistory(
            intraday_runtime.review_v2_store, intraday_runtime.mcx_paired_review_store,
            intraday_runtime.visual_reconciliation_v2_store)
        intraday_statistics = IntradayStatisticsApplication(
            current_probables=intraday_runtime.probables_v2_store.load_current_run,
            current_review=intraday_runtime.review_v2_application.historical_snapshot,
            machine_assessment=intraday_wo08_projection.status_document,
            operational_readiness=intraday_runtime.wo_b_runtime.status_document,
        )
        product_routes = ProductBrowserRoutes((IntradayBrowserRoutes(
            intraday_runtime.discovery_v2_application,
            probables_v2_control=intraday_probables_v2_control,
            wo08_projection=intraday_wo08_projection,
            visual_history=intraday_visual_history,
            machine_history=intraday_machine_history,
            review_v2_control=intraday_review_v2_control,
            visual_reconciliation_v2_control=intraday_visual_reconciliation_v2_control,
            wo09_projection=intraday_wo09_projection,
            futures_control=intraday_futures_control,
            lifecycle_control=lifecycle_control,
            prospective_programme_v2=True,
            wo10_control=intraday_wo10_control,
            wo11_control=intraday_wo11_control,
            research_control=intraday_research_control,
            wo12_v2_control=intraday_wo12_v2_control,
            wo13_control=intraday_wo13_control,
            wo14_control=intraday_wo14_control,
            wo15_control=intraday_wo15_control,
            wo16_control=intraday_wo16_control,
            wo17_control=intraday_wo17_control,
            operational_readiness=intraday_operational_readiness,
            statistics=intraday_statistics,
            review_workstation=intraday_runtime.discovery_application,
        ),))
        # PLC-01 source candidate only. Preserve exact current Intraday owner/control
        # instances and add Theta's offline manual workflow; never adopt trial state.
        product_routes = compose_theta_browser_routes(product_routes,
            factory=compose_theta_sponsor_workflow)
        intraday_historical_control = (
            IntradayHistoricalQualificationOperationalControl(
                intraday_runtime.historical_invocation
            )
        )
        provider_instrument_master_operation = (
            ProviderInstrumentMasterOperationalComposition(
                shared_provider_runtime,
                store=ProviderInstrumentSnapshotStore(
                    DEFAULT_PROVIDER_INSTRUMENT_SNAPSHOT_ROOT
                ),
                universe=load_intraday_universe_publication(),
                clock=lambda: datetime.now(UTC),
            )
        )
        _check_admission()
        run_provenance_store = LocalSwingRunProvenanceStore()
        application = cleanup.construct("application", lambda: (SwingOpportunitiesApplication(
            swing_provider_factory,
            connection_governance=governance,
            run_provenance_store=run_provenance_store,
            market_calendar_publisher=MarketCalendarPublisher(),
            mtf_fact_evidence_store=mtf_fact_store,
            native_discovery_evidence_store=native_discovery_store,
            relative_context_evidence_store=relative_context_store,
            analysis_process_owner=SwingAnalysisProcessOwner(),
        )), "close", _startup_application_closed)
        _check_admission()
        restart_control = cleanup.construct("control", lambda: (BrowserBackendRestartControl.create()), "remove", lambda o: not o.path.exists())
        _check_admission()
        cleanup.begin("server")
        server = create_browser_server(
            application,
            port=args.port,
            restart_control=restart_control,
            product_routes=product_routes,
            intraday_dashboard_summary=intraday_dashboard_summary,
            provider_instrument_master_operation=(
                provider_instrument_master_operation
            ),
            intraday_discovery_control=intraday_discovery_control,
            intraday_historical_control=intraday_historical_control,
            provider_login_navigation=provider_login_navigation,
            mcx_v1_composition_factory=lambda owner: install_canonical_mcx_v1(
                owner, master=ProviderInstrumentSnapshotStore(
                    DEFAULT_PROVIDER_INSTRUMENT_SNAPSHOT_ROOT),
                calendar=MarketCalendarPublisher()),
            _startup_cleanup=cleanup,
            _defer_k5_execution=True,
            _defer_ux10_delivery=True,
        )
        _check_admission()
        # The canonical collector borrows this exact coordinator before READY/serve.
        # Direct runtime compositions remain default-absent; no second coordinator.
        wo08_shadow = getattr(intraday_runtime, "wo08_shadow", None)
        if wo08_shadow is not None:
            wo08_shadow.bind_maintenance_admission(server.maintenance_admission)
        server.housekeeping = cleanup.construct("housekeeping",
            lambda: _compose_housekeeping(server, intraday_runtime), "shutdown",
            lambda o: o.status_document()["lifecycle_state"] == "STOPPED"
                and not o.status_document()["owned_workers"] and not o.status_document()["pass_active"])
        server.housekeeping.bind_maintenance_admission(server.maintenance_admission)
        server.mcx_official_check = cleanup.construct('official_check',
            lambda: _compose_mcx_official_check(server), 'close', lambda owner: owner.cleanup_complete())
        server.mcx_official_check.bind_maintenance_admission(server.maintenance_admission)
        if _ADMISSION is not None:
            server.mcx_official_check.bind_canonical_custody(_ADMISSION)
        server.provider_runtime = shared_provider_runtime
        server.intraday_wo09_notification_sources = (
            intraday_runtime.wo09_store.load_notifications
        )
        intraday_runtime.lifecycle_application.bind_monitoring(server.swing_monitoring_hub, application.authenticated_read_only_capability)
        intraday_runtime.lifecycle_application.bind_maintenance_admission(
            server.maintenance_admission
        )
        server.intraday_lifecycle = intraday_runtime.lifecycle_application
        intraday_runtime.wo09_application.experimental_watches.bind_monitoring(
            server.swing_monitoring_hub, application.authenticated_read_only_capability,
            server.maintenance_admission)
        server.intraday_experimental_watches = intraday_runtime.wo09_application.experimental_watches

        intraday_runtime.wo17_monitoring.bind_maintenance_admission(
            server.maintenance_admission
        )
        server.intraday_wo17_monitoring = intraday_runtime.wo17_monitoring
        server.intraday_journal = intraday_runtime.journal_application
        from kronos.application.intraday_notifications import IntradayNotifications
        server.intraday_notifications = cleanup.construct("notifications", lambda: (IntradayNotifications(
            centre=server.notification_centre, research=intraday_runtime.research_application,
            wo09=intraday_runtime.wo09_store, futures=intraday_runtime.futures_application.store,
            lifecycle=intraday_runtime.lifecycle_application.store, telegram=server.telegram,
            expected_checkpoint=expected_notification_checkpoint, defer_replay=True,
            monitoring_projection=server.intraday_experimental_watches.monitoring_projection)), "close", _startup_notifications_closed)
        server.intraday_notifications.bind_maintenance_admission(
            server.maintenance_admission
        )
        server.intraday_notifications.bind(intraday_runtime.probables_v2_store)
        intraday_runtime.journal_application.bind()
        from kronos.application.intraday_books import IntradayBooks
        server.intraday_books = IntradayBooks(
            research=intraday_runtime.journal_application.research,
            futures=intraday_runtime.journal_application.futures,
            lifecycle=intraday_runtime.lifecycle_application,
        )
        server.intraday_books.bind()
        server.intraday_research_application = intraday_runtime.research_application
        intraday_runtime.wo17_monitoring.set_shared_monitoring_hub(
            server.swing_monitoring_hub
        )
        intraday_runtime.wo17_monitoring.set_monitoring_capability_supplier(
            application.authenticated_read_only_capability
        )
        server._startup_fully_composed = True
        if _NATIVE_STARTUP_FACTS is not None:
            # Keep the exact returned owners. No owner is reconstructed after
            # failure; the native journal lives outside this product root.
            _NATIVE_STARTUP_FACTS.composition_returned(server, intraday_runtime,
                intraday_wo17_control.status_document, product_routes,
                (Path.home() / 'Library/Application Support/KRONOS/evidence',
                 mtf_fact_store._root, native_discovery_store._root, relative_context_store._root,
                 run_provenance_store.root, run_provenance_store.root.parent / 'run-publication-v1'))
            server._ordinary_composition = _NATIVE_STARTUP_FACTS.composed
        _check_admission()
        if isinstance(maintenance, RestorationStartupContext):
            from kronos.common.legacy_bootstrap import revalidate_restoration_context
            restoration_attempt = revalidate_restoration_context(
                os.environ,
                context=maintenance,
                custody=_ADMISSION,
                child=restoration_child,
                repository=Path(__file__).resolve().parents[1],
                now=datetime.now(UTC),
                attempt=restoration_attempt,
            )
        from kronos.browser.runtime_state import complete_startup
        facts = _NATIVE_STARTUP_FACTS
        if facts is not None: facts.completion_intent()
        completed = False
        try:
            complete_startup(
                server, intraday_runtime.discovery_v2_operation.live_shadow,
                swing_outcomes=server.startup_restoration_outcomes(),
                wo11=intraday_runtime.lifecycle_application,
                wo17=intraday_wo17_control.status_document(),
            )
            completed = True
        finally:
            if facts is not None: facts.completion_outcome(server, returned=completed)
        if isinstance(maintenance, RestorationStartupContext):
            # Completion may create genuine READY/receipt and reconciliation
            # evidence. A later denial preserves it and enters ordinary failure
            # cleanup; it never permits successful release or owner activation.
            restoration_attempt = revalidate_restoration_context(
                os.environ, context=maintenance, custody=_ADMISSION,
                child=restoration_child,
                repository=Path(__file__).resolve().parents[1],
                now=datetime.now(UTC), attempt=restoration_attempt,
            )
            # Keep the original selected facts through the last read-only check.
            for name in (
                "KRONOS_LAUNCH_MODE",
                "KRONOS_RESTORATION_ORIGINAL_ATTEMPT_ID",
                "KRONOS_RESTORATION_PERMIT_PATH",
                "KRONOS_RESTORATION_PERMIT_BYTES",
                "KRONOS_RESTORATION_PERMIT_SHA256",
                "KRONOS_RESTORATION_PERMIT_ID",
                "KRONOS_RESTORATION_RESERVATION_PATH",
                "KRONOS_RESTORATION_RESERVATION_BYTES",
                "KRONOS_RESTORATION_RESERVATION_SHA256",
                "KRONOS_RESTORATION_RESERVATION_ID",
                "KRONOS_RESTORATION_PARENT_KERNEL_BIRTH",
                "KRONOS_RESTORATION_CHILD_KERNEL_BIRTH",
                "KRONOS_RESTORATION_SOURCE_MANIFEST_PATH",
                "KRONOS_RESTORATION_ARTIFACT_MANIFEST_PATH",
            ):
                os.environ.pop(name, None)
        if _ADMISSION is not None:
            _activate_canonical_notifications(server)
            if facts is not None: facts.startup_success(server)
            # Relinquish the controlled-attempt pipe at the READY boundary;
            # the lifetime service retains its prior devnull logging behavior.
            _release_startup_output()
        url = f"http://127.0.0.1:{server.server_port}/swing/opportunities"
        if not args.no_browser:
            webbrowser.open_new_tab(url)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        return 0


    def _canonical_entry():
        global _ENTRY_PHASE
        _ENTRY_PHASE = "MAIN"
        try:
            return main()
        except BaseException:
            return _handle_canonical_failure()

    if __name__ == "__main__":
        _CANONICAL_EXIT = _canonical_entry()
except BaseException:
    if __name__ != "__main__":
        raise  # Preserve the existing library-import exception semantics.
    _CANONICAL_EXIT = _handle_canonical_failure()

if __name__ == "__main__":
    raise SystemExit(_CANONICAL_EXIT)
