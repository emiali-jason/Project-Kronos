"""Isolated actual-owner READY components under synthetic prevalidated trust.

The preparation/earlier protocol chain and Darwin observations are explicit
fixtures. No C entry carrier, operational approval or complete recovery is
established by these tests. Actual product constructors, native READY gate,
prospective ledger, private store, codecs and child evidence producer run here.
"""
from dataclasses import asdict, replace
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import time

import pytest

import kronos.common.failed_fenced_startup as startup_module
from kronos.common.failed_fenced_recovery import (
    RecoveryCodec, RecoveryStore, RecoveryBudget, EvidenceRegistry, ProspectiveLedger,
    PreparationContext, canonical_bytes, record_ref, PROTOCOL, VERSION, SCOPE_HASH, SCOPE_BYTES,
)
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.intraday.runtime_identity import StartupCapture, _PinnedLoader, canonical, digest, LauncherConfiguration
from tests.unit.intraday.test_runtime_identity import _seed
from tests.unit.common.test_failed_fenced_bootstrap_producer import captured


def test_ready_capture_accepts_later_pinned_imports(captured, monkeypatch):
    original, capture, module, _plan, pairs = captured
    name, raw = "kronos.synthetic_later", b"LATER = 11\n"
    sources = dict(capture._sources); sources[name] = ("/synthetic/later.py", raw, False)
    capture._sources = MappingProxyType(sources)
    complete = tuple(sorted((*pairs, (name, sha256(raw).hexdigest()))))
    later_startup = _seed(source_snapshot_digest=digest(complete), loaded_modules=pairs)
    capture._finished = later_startup
    loader = _PinnedLoader(capture, name, "/synthetic/later.py", raw)
    spec = importlib.util.spec_from_loader(name, loader)
    later = importlib.util.module_from_spec(spec); loader.exec_module(later)
    monkeypatch.setattr(startup_module, "_bootstrap_module_snapshot", lambda: ((pairs[0][0], module), (name, later)))
    assert later.LATER == 11 and original.loaded_modules == pairs
    assert startup_module._actual_ready_modules(later_startup, complete, SimpleNamespace(check=lambda: None)) == complete
    loader.payload = b"LATER = 99\n"
    with pytest.raises(startup_module.RecoveryStartupError):
        startup_module._actual_ready_modules(later_startup, complete, SimpleNamespace(check=lambda: None))


@pytest.fixture
def ready_case(tmp_path, monkeypatch):
    from kronos.application.failed_fenced_owners import ProspectiveComposition, FINITE_OWNERS
    from kronos.application.intraday_runtime import create_intraday_runtime
    from kronos.application.intraday_live_shadow import IntradayLiveShadowService
    from kronos.intraday.live_shadow_persistence import ShadowStore
    from kronos.browser.server import create_browser_server
    from kronos.browser.restart_control import BrowserBackendRestartControl
    from kronos.browser.intraday_probables_v2_control import IntradayProbablesV2OperationalControl
    from kronos.browser.intraday_routes import IntradayBrowserRoutes
    from kronos.browser.product_routes import ProductBrowserRoutes
    from kronos.browser.runtime_state import complete_startup
    from tests.unit.application.test_sph_maintenance import composed
    from tests.unit.browser.test_intraday_wo17_control import _control

    origin = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    dummy = {"authority": "CA", "contract": "synthetic-only", "identity": "fixture", "hash": "d" * 64, "bytes": "1"}
    clock = {"type": "CLOCK_MONOTONIC", "boot_id": "synthetic-boot", "qualification": dummy}
    old_codec = RecoveryCodec(b"KRONOS_BROWSER_BACKEND_CONTROL_V1\n987654\n" + b"b" * 64 + b"\n", clock)
    child_codec = RecoveryCodec(("KRONOS_BROWSER_BACKEND_CONTROL_V1\n" + str(os.getpid()) + "\n" + "c" * 64 + "\n").encode(), clock)
    estate = tmp_path / "estate"; estate.mkdir(mode=0o700); store = RecoveryStore(estate)
    guard_scope = {"schema": "KRONOS_FAILED_FENCED_GUARD_SCOPE_V1", "version": "1.0.0", "service": "fixture", "installation": "fixture", "policy": "MANDATORY"}
    store.provision(guard_scope, sha256(canonical_bytes(guard_scope)).hexdigest())
    raw_scope = (Path(__file__).resolve().parents[5] / "contract-successor-r3" / "SUPPORTED-OWNER-AND-OBLIGATION-SCOPE.md").read_bytes()
    scope_blob = store.write_blob("FAILED_FENCED_INITIAL_OWNER_SCOPE_V1", raw_scope)
    assert scope_blob["hash"] == SCOPE_HASH and scope_blob["bytes"] == SCOPE_BYTES
    scope = dict(scope_blob, authority="CA", contract=PROTOCOL + ":" + VERSION)
    modules = tuple((name,"e"*64) for name in sorted({module for _,module in startup_module._RECOVERY_OPERATION_MODULES}))
    source_inventory = store.write_blob("source-inventory", canonical(modules))
    native_startup = _seed(source_revision="d" * 40, source_snapshot_digest=digest(modules), loaded_modules=modules)
    process = {"pid": str(os.getpid()), "kernel_birth": {"seconds": "1", "microseconds": "2"}, "runtime": sha256(native_startup.evidence_identity.encode()).hexdigest()}
    parent = {"pid": str(os.getppid()), "kernel_birth": {"seconds": "3", "microseconds": "4"}, "runtime": "synthetic-canonical-parent"}
    admission = MaintenanceAdmissionCoordinator()
    ledger = ProspectiveLedger.capture(admission, child_codec, store, process, scope)
    ledger.native_startup, ledger.native_process = native_startup, process
    composition = ProspectiveComposition(ledger, source_inventory, scope)
    ledger.native_composition = composition
    ticket = admission.admit("SPONSOR_RESTORATION"); ledger._canonical_startup_ticket = ticket
    with ledger.activate(), ticket.activate():
        g, shared, app, provider, calls = composed(tmp_path / "app")
        g.process = replace(g.process, runtime_identity=process["runtime"], startup_at=native_startup.startup_boundary_at.isoformat())
        g.maintenance_identity = sha256(("f" * 64).encode("ascii")).hexdigest()
        control = BrowserBackendRestartControl.create(tmp_path / "runtime" / "control", token="c" * 64)
        shadow = IntradayLiveShadowService(store=ShadowStore(tmp_path / "shadow"), clock=g.clock)
        intraday = create_intraday_runtime(shared, evidence_root=tmp_path / "intraday", startup_evidence=native_startup, wo08_shadow=shadow, clock=g.clock)
        v2 = IntradayProbablesV2OperationalControl(intraday.discovery_v2_operation, intraday.probables_v2_application,
            intraday.refresh_v2_provenance_store, startup_evidence=native_startup, launcher_configuration=LauncherConfiguration(0, False), clock=g.clock)
        wo17, _store, _request = _control(tmp_path / "wo17")
        wo17._monitoring = intraday.wo17_monitoring
        routes = ProductBrowserRoutes((IntradayBrowserRoutes(intraday.workstation, probables_v2_control=v2, wo17_control=wo17),))
        server = create_browser_server(app, port=0, restart_control=control, product_routes=routes)
        server.provider_runtime, server.intraday_lifecycle = shared, intraday.lifecycle_application
        server.intraday_wo17_monitoring = intraday.wo17_monitoring
        ledger.bind_runtime_manifest(v2._runtime_manifest)
        # Explicit hypothetical fixture configuration. This is not a runtime
        # absence census and confers no approved finite-profile authority.
        for owner in sorted(FINITE_OWNERS - set(composition._slots)):
            composition.declare(owner, "synthetic-absent-" + owner, "NOT_INSTALLED")
        runtime = startup_module.ProspectiveRuntimeStartup(ledger, composition, control)
        runtime.complete_construction(server)
        complete_startup(server, shadow, swing_outcomes=server.startup_restoration_outcomes(), wo11=intraday.lifecycle_application, wo17=wo17.status_document())
    ticket.release()
    assert g.startup_state == "READY"
    artifacts = store.write_blob("synthetic-artifact", b"synthetic independently approved artifact boundary")
    operations = startup_module.recovery_operation_manifest(modules)
    operation_manifest = store.write_blob("qualified-operation-manifest", canonical_bytes(operations))
    analytical_manifest = store.write_blob("qualified-native-runtime-declaration", canonical(asdict(ledger.native_runtime_manifest)))
    tail = store.write_blob("qualified-tail-callgraph", b"synthetic preapproved tail qualification")
    target = {"identity": "target", "approval": "synthetic-artifact-approval", "service": "fixture", "revision": native_startup.source_revision,
        "source_inventory": source_inventory, "capability_manifest": analytical_manifest, "configuration": artifacts, "package": artifacts,
        "interface": artifacts, "scope": scope_blob, "restoration_plan": artifacts, "bootstrap_plan": artifacts}
    registry = object.__new__(EvidenceRegistry); registry.codec, registry.store = old_codec, store
    registry._validated_sources = {}; registry._visiting = set()
    prep = object.__new__(PreparationContext)
    prep.record = {"mode": "RECOVERY", "installation": "fixture", "lineage": {"predecessor": dict(process, pid="987654"), "generation": "a" * 64}, "controller": parent}
    bindings = {"source_inventory": source_inventory, "callgraph": tail}
    prep.rows = {"ca-tail": {"authority": "CA", "purpose": "TAIL", "bindings": bindings}, "pcp-tail": {"authority": "PCP", "purpose": "TAIL", "bindings": bindings}}
    registry.preparation = prep
    plan = {"owners": [{"owner": owner, "contract": "synthetic-restoration-" + owner, "validator": artifacts, "applicability": artifacts}
        for owner in ("LOCAL_ANALYSIS", "MCX", "NATIVE", "RESEARCH", "SWING_ANALYSIS", "TRADE_WINDOW", "WO08", "WO11", "WO17")]}
    # Only preexisting authority decisions are substituted. Native source,
    # restoration, absence and new same-process witness validation remain real.
    def verify(evidence, kind, subject=None, context=None):
        if kind == "TARGET_ARTIFACT": return {"payload": target}
        if kind == "RESTORATION_PLAN": return {"payload": plan}
        proof = old_codec.decode_proof(store.read_blob(evidence), kind)
        assert proof["role"] == "SUCCESSOR" and proof["issuer"] == process
        if kind == "SOURCE": registry._native_source(proof["payload"])
        elif kind == "CAPABILITY": registry._successor_runtime.verify_capability_witness(proof["payload"])
        else: startup_module.validate_external_native_proof(proof, registry, context or {})
        return proof
    registry.verify = verify
    budget = RecoveryBudget(clock, origin, origin + 15_000_000_000)
    slot, nonce = "a" * 64, "b" * 64
    ref = lambda kind: {"kind": kind, "hash": "f" * 64}
    target_evidence = dict(artifacts, authority="LAUNCHER", contract="synthetic-target")
    checkpoint = {"state": "EMPTY", "pending": "0", "digest": sha256(b"").hexdigest(), "evidence": dummy}
    chain = {kind + "_RAW": canonical_bytes({"kind": kind}) for kind in ("ORIGINAL", "TERMINAL", "GUARD", "CLAIM", "CLAIM_ACCEPTED", "SEAL", "OWNER_PROOF", "CERTIFICATE", "PREPARED_COMMIT", "ACK", "OBSERVATION", "EXIT_PROOF", "CHILD_INTENT")}
    for kind in ("OWNER_PROOF", "CERTIFICATE", "PREPARED_COMMIT", "ACK", "OBSERVATION"):
        chain[kind] = {"issued_ns": str(origin)}
    intent = {"slot": slot, "transaction": "f" * 64, "child_nonce": nonce, "successor_source": target_evidence, "successor_capability": target_evidence,
        "execution_owner": "synthetic-launcher", "bootstrap_owner": "synthetic-bootstrap"}
    chain["CHILD_INTENT"] = {"payload": intent}; chain["CLAIM"] = {"payload": {"guard": ref("GUARD")}}
    started = {"slot": slot, "transaction": "f" * 64, "intent": record_ref(chain["CHILD_INTENT_RAW"]), "child_identity": ref("CHILD_IDENTITY"), "child": process, "child_nonce": nonce,
        "fork_enter_ns": str(origin), "fork_return_ns": str(origin + 1), "ready_deadline_ns": str(origin + 120_000_000_000), "parent": parent, "kernel_parent": dummy}
    started_raw = old_codec.encode("CHILD_STARTED", started, "LAUNCHER", origin + 1)
    chain["CHILD_STARTED_RAW"], chain["CHILD_STARTED"] = started_raw, old_codec.decode(started_raw)
    grant = {"slot": slot, "transaction": "f" * 64, "claim": ref("CLAIM"), "intent": record_ref(chain["CHILD_INTENT_RAW"]), "child_started": record_ref(started_raw), "parent": parent,
        "controller_capability": dummy, "child": process, "child_nonce": nonce, "child_started_durable_ns": str(origin + 2), "identity_verified_ns": str(origin + 3), "gate_ns": str(origin + 4),
        "stop_deadline_ns": str(origin + 15_000_000_000), "ready_deadline_ns": str(origin + 120_000_000_000), "decision": "GRANT_ONCE"}
    grant_raw = old_codec.encode("COMPOSITION_AUTHORITY", grant, "LAUNCHER", origin + 4)
    session = object.__new__(startup_module.BootstrapSession)
    session.codec, session.store, session.registry, session.budget, session.chain = old_codec, store, registry, budget, chain
    session.native = startup_module.NativeBootstrap(native_startup, process, modules); session.parent = parent
    session._pid, session._consumed, session._record_ref = os.getpid(), False, record_ref
    session.latch = startup_module.CompositionLatch(grant_raw, old_codec.decode(grant_raw), origin + 5, origin + 6)
    store.reserve(slot, "claim", chain["CLAIM_RAW"])
    store.reserve(slot, "child-intent", chain["CHILD_INTENT_RAW"])
    session.consume(bootstrap_evidence=dummy, checkpoint=checkpoint, restoration_scope=dummy)
    monkeypatch.setattr(startup_module, "_actual_ready_modules", lambda startup, inventory, budget: modules)
    def observed(pid, budget):
        native = process if pid == os.getpid() else parent
        return dict(native, parent_pid=parent["pid"] if pid == os.getpid() else "1")
    monkeypatch.setattr(startup_module, "_bootstrap_process_observation", observed)
    monkeypatch.setattr("tools.runtime_source_gate.canonical_parent", lambda **kwargs: None)
    case = SimpleNamespace(session=session, runtime=runtime, server=server, provider=provider, calls=calls, target=target, registry=registry, modules=modules, tmp=tmp_path, operation_manifest=operation_manifest)
    yield case
    server.server_close()


def test_actual_owner_ready_produces_only_s_graph_and_unsigned_receipt(ready_case):
    case = ready_case
    witness = startup_module.SuccessorReadyEvidence(case.session, case.runtime, case.server)
    before = {str(path): path.read_bytes() for path in case.tmp.rglob("*") if path.is_file() and "estate" not in path.parts}
    receipt = witness.publish()
    assert receipt["runtime"] == case.session.native.process
    assert set(receipt) == {"slot", "transaction", "guard", "intent", "child_started", "consumption", "startup", "runtime", "ready_ns", "restoration", "source", "capability", "provider_absence", "transport_absence", "execution_owner"}
    for field, kind in (("source", "SOURCE"), ("capability", "CAPABILITY"), ("restoration", "RESTORATION"), ("provider_absence", "ABSENCE"), ("transport_absence", "ABSENCE")):
        actual = case.session.codec.decode_proof(case.session.store.read_blob(receipt[field]), kind)
        assert actual["role"] == "SUCCESSOR" and actual["issuer"] == case.session.native.process
    assert case.provider.begin_count == 0 and case.calls == []
    assert before == {str(path): path.read_bytes() for path in case.tmp.rglob("*") if path.is_file() and "estate" not in path.parts}
    assert not list((case.session.store.root / "records").glob("READY_RECEIPT-*"))
    with pytest.raises(startup_module.RecoveryStartupError, match="ATTEMPT_SPENT"):
        witness.publish()


@pytest.mark.parametrize("fault", ["attempt_only", "maintenance", "admission", "source", "runtime_manifest", "live_owner", "parent", "late", "startup_record", "inventory", "provider", "transport", "governance_runtime", "generation"])
def test_actual_ready_denies_incomplete_stale_or_changed_native_evidence(ready_case, monkeypatch, fault):
    case = ready_case
    if fault == "attempt_only": del case.session.consumption_raw
    elif fault == "maintenance": case.server.connection_governance.maintenance_active = True
    elif fault == "admission": case.runtime.ledger.coordinator._state = "FENCED"
    elif fault == "source": case.runtime.ledger.native_startup = replace(case.runtime.ledger.native_startup)
    elif fault == "runtime_manifest": case.runtime.ledger.native_runtime_manifest = replace(case.runtime.ledger.native_runtime_manifest)
    elif fault == "live_owner": case.runtime.ledger.coordinator.admit("WO11")
    elif fault == "parent": case.session.parent = dict(case.session.parent, kernel_birth={"seconds": "9", "microseconds": "9"})
    elif fault == "late": case.session.ready_budget.ready_deadline_ns = time.clock_gettime_ns(time.CLOCK_MONOTONIC) - 1
    elif fault == "startup_record": next((case.server.connection_governance.store.root / "maintenance").glob("*-startup.json")).unlink()
    elif fault == "inventory": case.runtime.ledger._inventory_payload["instances"] = []
    elif fault == "provider": case.server.provider_runtime._SharedAuthenticatedProviderRuntime__cleanup_in_progress = 1
    elif fault == "transport": case.server.swing_monitoring_hub._retired_session = object()
    elif fault == "governance_runtime": case.server.connection_governance.process = replace(case.server.connection_governance.process, runtime_identity="9" * 64)
    elif fault == "generation": case.server.connection_governance.maintenance_identity = "9" * 64
    try:
        with pytest.raises((ValueError, OSError)):
            startup_module.SuccessorReadyEvidence(case.session, case.runtime, case.server)
    finally:
        if fault == "provider": case.server.provider_runtime._SharedAuthenticatedProviderRuntime__cleanup_in_progress = 0
        if fault == "transport": case.server.swing_monitoring_hub._retired_session = None
        if fault == "live_owner":
            for ticket in tuple(case.runtime.ledger.coordinator._tickets.values()): ticket.release()
        case.runtime.ledger.coordinator._state = "OPEN"


def test_ready_operation_bytes_and_owner_approvals_are_not_names_only(ready_case):
    case = ready_case
    witness = startup_module.SuccessorReadyEvidence(case.session, case.runtime, case.server)
    case.registry.preparation.rows.pop("pcp-tail")
    with pytest.raises(startup_module.RecoveryStartupError, match="TAIL_APPROVAL_UNAVAILABLE"):
        witness.publish()
    assert case.provider.begin_count == 0 and case.calls == []


def test_same_process_restoration_proof_without_actual_witness_is_denied(ready_case):
    case = ready_case
    with pytest.raises(startup_module.RecoveryStartupError, match="NATIVE_WITNESS_REQUIRED"):
        startup_module.validate_external_native_proof({"kind": "RESTORATION", "role": "SUCCESSOR", "payload": {"process": case.session.native.process}}, case.registry, {})


@pytest.mark.parametrize("fault", ["unloaded", "digest", "duplicate", "unknown_field"])
def test_qualified_manifest_cannot_replace_actual_executing_bytes(ready_case, fault, monkeypatch):
    case = ready_case
    witness = startup_module.SuccessorReadyEvidence(case.session, case.runtime, case.server)
    rows = json.loads(case.session.store.read_blob(case.operation_manifest))
    if fault == "unloaded": rows[0]["module"] = "kronos.not_loaded"
    elif fault == "digest": rows[0]["digest"] = "f" * 64
    elif fault == "duplicate": rows.append(dict(rows[0]))
    else: rows[0]["approved"] = "YES"
    # Mutate only this explicit synthetic source-catalogue boundary. The
    # analytical native declaration remains a separate, unchanged artifact.
    monkeypatch.setattr(startup_module,"recovery_operation_manifest",lambda inventory:rows)
    with pytest.raises(startup_module.RecoveryStartupError, match="OPERATION_"):
        witness.publish()
    assert case.provider.begin_count == 0 and case.calls == []


def test_consumption_attempt_without_complete_durability_has_no_completion_witness(ready_case, tmp_path, monkeypatch):
    from tests.unit.common.test_failed_fenced_recovery import private_store
    case = ready_case
    root = tmp_path / "interrupted"; root.mkdir()
    store = private_store(root)
    session = object.__new__(startup_module.BootstrapSession)
    for name in ("codec", "registry", "budget", "chain", "native", "parent", "_pid", "_record_ref"):
        setattr(session, name, getattr(case.session, name))
    session.store, session._consumed = store, False
    old = case.session.latch
    session.latch = startup_module.CompositionLatch(old.raw, old.record, old.received_ns, old.verified_ns)
    intent = session.chain["CHILD_INTENT"]["payload"]
    store.reserve(intent["slot"], "claim", session.chain["CLAIM_RAW"])
    monkeypatch.setattr(store, "publish", lambda raw: (_ for _ in ()).throw(OSError("SYNTHETIC_STARTUP_DURABILITY_FAILURE")))
    original = case.session.codec.decode(case.session.startup_context_raw, "STARTUP_CONTEXT")["payload"]
    with pytest.raises(OSError, match="DURABILITY_FAILURE"):
        session.consume(bootstrap_evidence=original["restoration_scope"], checkpoint=original["checkpoint"], restoration_scope=original["restoration_scope"])
    assert session._consumed and not session.latch._spent
    assert not hasattr(session, "consumption_raw") and not hasattr(session, "startup_context_raw")
    with pytest.raises(startup_module.RecoveryStartupError, match="CONSUMPTION_REJECTED"):
        session.consume(bootstrap_evidence=original["restoration_scope"], checkpoint=original["checkpoint"], restoration_scope=original["restoration_scope"])
