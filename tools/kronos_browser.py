"""Sponsor and developer entry point for the local KRONOS Browser V1."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
import webbrowser
import os
import time
_CANONICAL_ENTRY_ORIGIN_NS = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
from hashlib import sha256

from pathlib import Path
from kronos.intraday.runtime_identity import StartupCapture, LauncherConfiguration

# This deny-only parser is intentionally stdlib-only and precedes native source
# capture. It authenticates inherited immutable bounds, never installation,
# human authority, actual source, capability, composition or restoration.
class _InheritedRecoveryBudget:
    def __init__(self, clock, origin, stop, claim_hash, intent_hash):
        import time
        self.clock, self.origin_ns, self.stop_deadline_ns = clock, origin, stop
        self.claim_hash, self.intent_hash = claim_hash, intent_hash
        self._last = origin
        self._failed = False
        self.check()

    def now_ns(self):
        import time
        now = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        if now < self._last:
            self._failed = True
        self._last = max(now, self._last)
        if self._failed:
            raise ValueError("FAILED_FENCED_INHERITED_CLOCK_REJECTED")
        return now

    def check(self, deadline_ns=None):
        deadline = self.stop_deadline_ns if deadline_ns is None else min(self.stop_deadline_ns, deadline_ns)
        if self.now_ns() >= deadline:
            self._failed = True
            raise ValueError("FAILED_FENCED_INHERITED_DEADLINE_EXPIRED")

    def remaining_seconds(self, deadline_ns=None):
        self.check(deadline_ns)
        deadline = self.stop_deadline_ns if deadline_ns is None else min(self.stop_deadline_ns, deadline_ns)
        return (deadline - self.now_ns()) / 1e9


def _inherited_recovery_budget(environment, *, estate=None, _pipe_descriptor=3):
    import fcntl
    import hmac
    import json
    import re
    import stat
    prefix = "KRONOS_FAILED_FENCED_RECOVERY_"
    keys = {prefix + suffix for suffix in ("VERSION", "SLOT", "CHILD_NONCE")}
    present = {key for key in environment if key.startswith(prefix)}
    if not present:
        return None
    if (present != keys or environment[prefix + "VERSION"] != "1.0.0"
            or any(re.fullmatch(r"[0-9a-f]{64}", environment[prefix + name]) is None for name in ("SLOT", "CHILD_NONCE"))
            or any(key.startswith(("KRONOS_MAINTENANCE_", "KRONOS_LEGACY_BOOTSTRAP_")) or key == "KRONOS_LAUNCH_MODE" for key in environment)):
        raise ValueError("FAILED_FENCED_INHERITED_SELECTORS_REJECTED")
    # Before any helper, ensure the inherited private pipe cannot leak through
    # a later source/signature/Git exec. It confers no authority until consumed.
    if not stat.S_ISFIFO(os.fstat(_pipe_descriptor).st_mode):
        raise ValueError("FAILED_FENCED_INHERITED_PIPE_REQUIRED")
    fcntl.fcntl(_pipe_descriptor, fcntl.F_SETFD, fcntl.fcntl(_pipe_descriptor, fcntl.F_GETFD) | fcntl.FD_CLOEXEC)
    if estate is None:
        # Keep this pre-capture parser stdlib-only. The native account lookup
        # matches C and tools.runtime_source_gate.fixed_native_estate exactly.
        import pwd
        if os.getuid()!=os.geteuid():raise ValueError('RECOVERY_NATIVE_ACCOUNT_CHANGED')
        home=Path(pwd.getpwuid(os.geteuid()).pw_dir)
        if not home.is_absolute() or '..' in home.parts:raise ValueError('RECOVERY_NATIVE_ACCOUNT_HOME_INVALID')
        estate=home/'Library/Application Support/KRONOS/runtime'
    root = Path(estate) / "recovery-v1"
    # estate is an internal isolated-facility argument; production has no CLI
    # or environment override. Full independent prepared identity follows.
    def read(parts, name, cap):
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        fd = os.open("/", flags | os.O_DIRECTORY)
        try:
            for component in root.parts[1:] + tuple(parts):
                child = os.open(component, flags | os.O_DIRECTORY, dir_fd=fd)
                os.close(fd)
                fd = child
                info = os.fstat(fd)
                # Canonical ancestors retain their existing modes. The estate
                # and every recovery descendant must be private owned dirs.
                if component == "recovery-v1" or component in parts:
                    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                        raise ValueError("FAILED_FENCED_INHERITED_PRIVATE_DIRECTORY")
            item = os.open(name, flags, dir_fd=fd)
            try:
                before = os.fstat(item)
                if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1:
                    raise ValueError("FAILED_FENCED_INHERITED_PRIVATE_FILE")
                raw = os.read(item, cap + 1)
                after = os.fstat(item)
                if len(raw) > cap or any(getattr(before, key) != getattr(after, key) for key in ("st_dev", "st_ino", "st_mode", "st_uid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")):
                    raise ValueError("FAILED_FENCED_INHERITED_FILE_CHANGED")
                return raw
            finally:
                os.close(item)
        finally:
            os.close(fd)
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError("FAILED_FENCED_INHERITED_DUPLICATE_FIELD")
            result[key] = value
        return result
    def number(_):
        raise ValueError("FAILED_FENCED_INHERITED_NUMBER_REJECTED")
    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("ascii")
    def decode(raw):
        value = json.loads(raw.decode("ascii"), object_pairs_hook=pairs, parse_int=number, parse_float=number, parse_constant=number)
        if canonical(value) != raw:
            raise ValueError("FAILED_FENCED_INHERITED_NONCANONICAL")
        return value
    slot = environment[prefix + "SLOT"]
    claim_raw = read(("slots", slot), "claim", 1 << 20)
    claim = decode(claim_raw)
    key_id = claim.get("key_id")
    if type(key_id) is not str or re.fullmatch(r"[0-9a-f]{64}", key_id) is None:
        raise ValueError("FAILED_FENCED_INHERITED_KEY_REJECTED")
    control = read(("custody",), key_id + ".control", 255)
    if (sha256(control).hexdigest() != key_id or re.fullmatch(rb"KRONOS_BROWSER_BACKEND_CONTROL_V1\n[1-9][0-9]*\n[0-9a-f]{64}\n", control) is None):
        raise ValueError("FAILED_FENCED_INHERITED_CUSTODY_REJECTED")
    key = bytes.fromhex(control.splitlines()[2].decode("ascii"))
    def authenticated(value, kind):
        fields = {"protocol", "version", "kind", "role", "key_id", "clock", "issued_ns", "payload", "mac"}
        if (type(value) is not dict or set(value) != fields or value["protocol"] != "KRONOS-FAILED-FENCED-RECOVERY-V1" or value["version"] != "1.0.0"
                or value["kind"] != kind or value["role"] != "LAUNCHER" or value["key_id"] != key_id):
            raise ValueError("FAILED_FENCED_INHERITED_RECORD_REJECTED")
        derived = hmac.digest(key, ("KRONOS-FAILED-FENCED-RECOVERY-V1/1.0.0/key/LAUNCHER/" + key_id).encode("ascii"), "sha256")
        signed = {k: v for k, v in value.items() if k != "mac"}
        actual = hmac.new(derived, b"KRONOS-FAILED-FENCED-RECOVERY-V1/1.0.0/record\n" + canonical(signed), "sha256").hexdigest()
        if type(value["mac"]) is not str or not hmac.compare_digest(actual, value["mac"]):
            raise ValueError("FAILED_FENCED_INHERITED_MAC_REJECTED")
    authenticated(claim, "CLAIM")
    payload = claim["payload"]
    expected = {"slot", "guard", "transaction", "binding", "authorization", "scope_approvals", "control_challenge", "launcher", "launcher_capability", "endpoint", "limits", "successor_source", "successor_capability", "installed_package", "rollback_package", "compatibility"}
    if type(payload) is not dict or set(payload) != expected or payload["slot"] != slot:
        raise ValueError("FAILED_FENCED_INHERITED_CLAIM_REJECTED")
    limits = payload["limits"]
    if type(limits) is not dict or set(limits) != {"clock", "origin_ns", "stop_deadline_ns"} or limits["clock"] != claim["clock"]:
        raise ValueError("FAILED_FENCED_INHERITED_LIMITS_REJECTED")
    clock = claim["clock"]
    if type(clock) is not dict or set(clock) != {"type", "boot_id", "qualification"} or clock["type"] != "CLOCK_MONOTONIC":
        raise ValueError("FAILED_FENCED_INHERITED_CLOCK_REJECTED")
    for value in (limits["origin_ns"], limits["stop_deadline_ns"], claim["issued_ns"]):
        if type(value) is not str or re.fullmatch(r"0|[1-9][0-9]{0,19}", value) is None or int(value) >= 1 << 64:
            raise ValueError("FAILED_FENCED_INHERITED_LIMITS_REJECTED")
    origin, stop = int(limits["origin_ns"]), int(limits["stop_deadline_ns"])
    if stop != origin + 15_000_000_000 or not origin <= int(claim["issued_ns"]) < stop:
        raise ValueError("FAILED_FENCED_INHERITED_BUDGET_EXTENSION")
    intent_raw = read(("slots", slot), "child-intent", 1 << 20)
    intent = decode(intent_raw)
    authenticated(intent, "CHILD_INTENT")
    if (intent["clock"] != clock or intent["payload"]["slot"] != slot
            or intent["payload"]["child_nonce"] != environment[prefix + "CHILD_NONCE"]
            or intent["payload"]["claim"] != {"kind": "CLAIM", "hash": sha256(claim_raw).hexdigest()}
            or intent["payload"]["limits"] != limits):
        raise ValueError("FAILED_FENCED_INHERITED_INTENT_REJECTED")
    return _InheritedRecoveryBudget(clock, origin, stop, sha256(claim_raw).hexdigest(), sha256(intent_raw).hexdigest())


_RECOVERY_EARLY_BUDGET = _inherited_recovery_budget(os.environ)

# Capture before application imports. Never replace this with a later HEAD lookup.
with StartupCapture(Path(__file__).resolve().parents[1], keep_sources_pinned=True,
                    recovery_budget=_RECOVERY_EARLY_BUDGET) as _startup_capture:
    from kronos.application.provider_instrument_master_operation import (
        ProviderInstrumentMasterOperationalComposition,
    )
    from kronos.application.housekeeping import (
        BoundedHousekeeping,
        intraday_research_staging_scope,
        review_preparation_scope,
    )
    from kronos.application.swing_opportunities import SwingOpportunitiesApplication
    from kronos.application.swing_analysis_process import SwingAnalysisProcessOwner
    from kronos.application.intraday_runtime import create_intraday_runtime
    from kronos.application.intraday_reliance_bootstrap import DEFAULT_INTRADAY_EVIDENCE_ROOT
    from kronos.application.intraday_wo08_shadow import compose_wo08_shadow
    from kronos.application.intraday_statistics import IntradayStatisticsApplication
    from kronos.browser.server import create_browser_server
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
del _startup_capture


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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch local KRONOS Browser V1")
    parser.add_argument("--port", type=int, default=8947)
    parser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None, *, prepared_runtime=None, recovery_child=None) -> int:
    # These are source-owned typed injection points for canonical approved
    # installation/controller preparation. No CLI/env/HTTP deserialization can
    # select an authority, ledger, callable or alternative estate.
    from kronos.common.failed_fenced_startup import (
        PreparedChildStartup, PreparedRuntimeFactory, ProspectiveRuntimeStartup, RecoveryStartupError,
    )
    if _RECOVERY_EARLY_BUDGET is not None and recovery_child is None:
        from kronos.common.failed_fenced_startup import load_child_preparation, prepare_child_startup
        authority, canonical_factory = load_child_preparation(
            _STARTUP_EVIDENCE, os.environ, _RECOVERY_EARLY_BUDGET)
        recovery_child = prepare_child_startup(authority, _STARTUP_EVIDENCE, os.environ)
        if prepared_runtime is not None:
            raise RecoveryStartupError("RECOVERY_CHILD_RUNTIME_FACTORY_SUBSTITUTION")
        prepared_runtime = canonical_factory
    if _RECOVERY_EARLY_BUDGET is not None and type(recovery_child) is not PreparedChildStartup:
        raise RecoveryStartupError("RECOVERY_CANONICAL_CHILD_PREPARATION_REQUIRED")
    if recovery_child is not None and (type(recovery_child) is not PreparedChildStartup or _RECOVERY_EARLY_BUDGET is None):
        raise RecoveryStartupError("RECOVERY_CHILD_CONTEXT_REJECTED")
    if prepared_runtime is None:
        # This source is the capable composition. Neither a redirected HOME nor
        # an absent namespace classifies it as historical LEGACY_UNENROLLED.
        # The fixed native-account estate and affirmative static approvals are
        # independently checked before any product construction. Ordinary V1/V2
        # composition below remains unchanged after this admission boundary.
        from kronos.common.failed_fenced_startup import load_capture_installation
        try:
            prepared_runtime = load_capture_installation(_STARTUP_EVIDENCE,
                origin_ns=_CANONICAL_ENTRY_ORIGIN_NS)
        except (OSError, ValueError) as exc:
            raise RecoveryStartupError("RECOVERY_GUARD_PREPARATION_REQUIRED") from exc
    if type(prepared_runtime) is PreparedRuntimeFactory:
        return _main(argv, prepared_runtime=prepared_runtime, recovery_child=recovery_child)
    if type(prepared_runtime) is not ProspectiveRuntimeStartup or recovery_child is not None:
        raise RecoveryStartupError("RECOVERY_PROSPECTIVE_RUNTIME_REQUIRED")
    with prepared_runtime.activate(_STARTUP_EVIDENCE):
        return _main(argv, prepared_runtime=prepared_runtime, recovery_child=recovery_child)


def _main(argv: Sequence[str] | None = None, *, prepared_runtime=None, recovery_child=None) -> int:
    args = _parser().parse_args(argv)
    from tools.runtime_source_gate import qualify_startup
    if _RECOVERY_EARLY_BUDGET is None:
        qualify_startup(Path(__file__).resolve().parents[1], _STARTUP_EVIDENCE)
    else:
        qualify_startup(Path(__file__).resolve().parents[1], _STARTUP_EVIDENCE,
                        budget=_RECOVERY_EARLY_BUDGET)
    process_identity = sha256(_STARTUP_EVIDENCE.evidence_identity.encode()).hexdigest()
    child_session = None
    if recovery_child is not None:
        child_session, startup_context = recovery_child.enter(os.environ, _STARTUP_EVIDENCE,
                                                              _RECOVERY_EARLY_BUDGET)
        # R3 never produces or consumes an ordinary V1/V2 maintenance handoff.
        maintenance = None
        # Existing connection-governance audit identity is a SHA-256 value;
        # R3 transaction remains its exact governed Id in immutable records.
        maintenance_identity = sha256(startup_context["payload"]["transaction"].encode("ascii")).hexdigest()
        checkpoint = recovery_child.checkpoint
        expected_notification_checkpoint = {"state": checkpoint["state"],
            "pending_count": int(checkpoint["pending"]), "sha256": checkpoint["digest"]}
        child_session.ready_budget.check()
    else:
        maintenance = consume_startup_context(DEFAULT_BACKEND_CONTROL_PATH.parent, os.environ,
            revision=_STARTUP_EVIDENCE.source_revision, source_state=_STARTUP_EVIDENCE.source_state,
            repository=Path(__file__).resolve().parents[1],
            runtime_identity=process_identity, now=datetime.now(UTC))
        maintenance_identity = (maintenance.generation if isinstance(
            maintenance, DrainStartupContext) else maintenance)
        expected_notification_checkpoint = (maintenance.notification_checkpoint()
            if isinstance(maintenance, DrainStartupContext) else None)
    from kronos.common.failed_fenced_startup import PreparedRuntimeFactory
    if type(prepared_runtime) is PreparedRuntimeFactory:
        prepared_runtime = prepared_runtime.construct(_STARTUP_EVIDENCE, child_session)
        with prepared_runtime.activate(_STARTUP_EVIDENCE):
            return _compose_application(args, process_identity, maintenance_identity,
                                        expected_notification_checkpoint, prepared_runtime, child_session)
    return _compose_application(args, process_identity, maintenance_identity,
                                expected_notification_checkpoint, prepared_runtime, child_session)


def _compose_application(args, process_identity, maintenance_identity,
                         expected_notification_checkpoint, prepared_runtime, child_session):
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
    shared_provider_runtime = SharedAuthenticatedProviderRuntime(
        lambda: _build_provider(
            navigator=provider_login_navigation,
            callback_return_url=callback_return_url,
        ),
        provider_identity="KITE",
        connection_governance=governance,
    )
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
    intraday_runtime = create_intraday_runtime(
        shared_provider_runtime, startup_evidence=_STARTUP_EVIDENCE,
        # Construction is inert; only future completed Analysis can admit work.
        wo08_shadow_factory=lambda: compose_wo08_shadow(DEFAULT_INTRADAY_EVIDENCE_ROOT),
    )
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
    if prepared_runtime is not None:
        # Retain the actual native constructor result, not JSON copied from a
        # source proof or status response. Source validation uses this witness.
        prepared_runtime.ledger.bind_runtime_manifest(intraday_probables_v2_control._runtime_manifest)
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
    application = SwingOpportunitiesApplication(
        swing_provider_factory,
        connection_governance=governance,
        run_provenance_store=LocalSwingRunProvenanceStore(),
        market_calendar_publisher=MarketCalendarPublisher(),
        mtf_fact_evidence_store=mtf_fact_store,
        native_discovery_evidence_store=native_discovery_store,
        relative_context_evidence_store=relative_context_store,
        analysis_process_owner=SwingAnalysisProcessOwner(),
    )
    restart_control = (BrowserBackendRestartControl.create() if prepared_runtime is None
                       else prepared_runtime.restart_control)
    server = None
    try:
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
        )
        # The canonical collector borrows this exact coordinator before READY/serve.
        # Direct runtime compositions remain default-absent; no second coordinator.
        wo08_shadow = getattr(intraday_runtime, "wo08_shadow", None)
        if wo08_shadow is not None:
            wo08_shadow.bind_maintenance_admission(server.maintenance_admission)
        server.housekeeping = _compose_housekeeping(server, intraday_runtime)
        server.housekeeping.bind_maintenance_admission(server.maintenance_admission)
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
        server.intraday_notifications = IntradayNotifications(
            centre=server.notification_centre, research=intraday_runtime.research_application,
            wo09=intraday_runtime.wo09_store, futures=intraday_runtime.futures_application.store,
            lifecycle=intraday_runtime.lifecycle_application.store, telegram=server.telegram,
            expected_checkpoint=expected_notification_checkpoint,
            monitoring_projection=server.intraday_experimental_watches.monitoring_projection)
        server.intraday_notifications.bind_maintenance_admission(
            server.maintenance_admission
        )
        if prepared_runtime is None:
            server.intraday_notifications.bind(intraday_runtime.probables_v2_store)
        else:
            server.intraday_notifications.bind(intraday_runtime.probables_v2_store,
                defer_start=True)
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
        if prepared_runtime is not None:
            if child_session is not None:
                server._failed_fenced_child_session = child_session
            from kronos.application.failed_fenced_owners import enroll_canonical_sources
            enroll_canonical_sources(prepared_runtime.composition,
                wo09=intraday_runtime.wo09_store, futures=intraday_runtime.futures_application.store,
                lifecycle=intraday_runtime.lifecycle_application.store,
                notifications=server.intraday_notifications, journal=server.intraday_journal,
                books=server.intraday_books, caller=server.intraday_lifecycle)
            prepared_runtime.complete_construction(server)
            server.intraday_notifications.start_pending()
        if child_session is not None:
            child_session.ready_budget.check()
        from kronos.browser.runtime_state import complete_startup
        complete_startup(
            server, intraday_runtime.discovery_v2_operation.live_shadow,
            swing_outcomes=server.startup_restoration_outcomes(),
            wo11=intraday_runtime.lifecycle_application,
            wo17=intraday_wo17_control.status_document(),
        )
        if child_session is not None:
            child_session.ready_budget.check()
        if prepared_runtime is not None:
            startup_ticket = getattr(prepared_runtime.ledger, "_canonical_startup_ticket", None)
            if startup_ticket is not None:
                startup_ticket.release()
        if child_session is not None:
            from kronos.common.failed_fenced_startup import SuccessorReadyEvidence
            # The actual child publishes S evidence only. The canonical native
            # parent independently validates it and alone issues L READY_RECEIPT.
            ready = SuccessorReadyEvidence(child_session, prepared_runtime, server)
            server._failed_fenced_ready_payload = ready.publish()
            server._failed_fenced_ready_evidence = ready
        url = f"http://127.0.0.1:{server.server_port}/swing/opportunities"
        if not args.no_browser:
            webbrowser.open_new_tab(url)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
    finally:
        # The installed owners and socket also belong to failed composition,
        # checkpoint verification, READY and workspace-open paths.
        try:
            if server is not None:
                server.server_close()
            else:
                restart_control.remove()
        finally:
            # The reviewed R3 tail has already completed every cleanup and
            # released its final publisher before ACK. No domain finalizer,
            # Provider audit, WO08 callback or ordinary handoff may run again.
            write_free = server is not None and getattr(server, "_failed_fenced_write_free", False)
            if not write_free:
                wo08_shadow = getattr(intraday_runtime, "wo08_shadow", None)
                if wo08_shadow is not None:
                    wo08_shadow.close()
                shared_provider_runtime.end_kronos_session()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
