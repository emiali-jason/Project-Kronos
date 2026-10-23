"""Native compatibility components, with explicit synthetic outer proof trust.

Actual native epoch/window/acceptance files, RuntimeManifest identities and WO06H
validators run against disposable stores. The test registry substitutes only
the independently prevalidated outer SOURCE/TARGET/catalogue/MAC edge; it does
not establish production approval, launcher trust or a full native recovery.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import timedelta
from hashlib import sha256
from types import SimpleNamespace
import json

import pytest

from kronos.common import failed_fenced_compatibility as compatibility
from kronos.common.failed_fenced_recovery import RecoveryStore, canonical_bytes, blob_ref
from kronos.common.failed_fenced_startup import RecoveryStartupError, validate_external_native_proof
from kronos.intraday.runtime_identity import create_runtime_manifest, canonical, LauncherConfiguration, _startup
from kronos.intraday.live_shadow import instant
from kronos.intraday.live_shadow_epochs import document
from tests.unit.intraday.test_runtime_identity import _seed
from tests.unit.intraday.test_live_shadow import service, NOW
from tests.unit.intraday.test_live_shadow_epochs import inventory
from tests.unit.intraday.test_live_shadow_successor_compatibility import relation


def native_startup(previous, **changes):
    values=asdict(previous); values.pop("evidence_identity"); values.pop("contract_version")
    return _startup(**(values | changes))


@pytest.fixture
def native_case(tmp_path, monkeypatch):
    shadow, _, original = service(tmp_path / "native")
    monkeypatch.setattr(compatibility, "DEFAULT_INTRADAY_EVIDENCE_ROOT", tmp_path / "native")
    monkeypatch.setattr(compatibility, "_utc_now", lambda: NOW + timedelta(minutes=1))
    estate = tmp_path / "estate"; estate.mkdir(mode=0o700)
    store = RecoveryStore(estate)
    scope = dict(schema="KRONOS_FAILED_FENCED_GUARD_SCOPE_V1", version="1.0.0",
        service="synthetic-service", installation="synthetic-install", policy="MANDATORY")
    store.provision(scope, sha256(canonical_bytes(scope)).hexdigest())
    retained={}
    def put(identity, raw):
        digest=sha256(raw).hexdigest()
        if digest not in retained:
            store.write_blob(identity,raw); retained[digest]=raw
        else:
            assert retained[digest]==raw
        return blob_ref(identity,raw)
    modules = (("kronos.synthetic_compatibility", "e" * 64),)
    native_inventory = put("qualified-source-inventory", canonical(modules))
    configuration = LauncherConfiguration(8947, False)
    start = _seed(startup_boundary_at=NOW, loaded_modules=modules,
        source_snapshot_digest=native_inventory["hash"])
    before = create_runtime_manifest(start, configuration, original.capabilities)
    target_manifest = create_runtime_manifest(native_startup(start, process_nonce="2" * 32,
        process_id=start.process_id + 1), configuration, original.capabilities)
    process = dict(pid=str(start.process_id), kernel_birth=dict(seconds="1", microseconds="2"), runtime="synthetic-original")
    issuer = dict(pid="998877", kernel_birth=dict(seconds="3", microseconds="4"), runtime="synthetic-launcher")
    proofs = {}
    def retain(kind, payload, role="LAUNCHER"):
        raw = canonical_bytes(dict(kind=kind, payload=payload, role=role))
        ref = put("fixture-" + kind.lower(), raw)
        proofs[ref["hash"]] = dict(kind=kind, payload=payload, role=role)
        return ref
    source = retain("SOURCE", dict(process=process, runtime_manifest=put("predecessor-manifest", canonical(asdict(before))), source_inventory=native_inventory), "PREDECESSOR")
    target = dict(revision=start.source_revision, source_inventory=native_inventory,
        capability_manifest=put("qualified-native-manifest", canonical(asdict(target_manifest))),
        configuration=put("native-configuration", canonical(asdict(configuration))))
    target_ref = retain("TARGET_ARTIFACT", target)
    epoch = shadow._epochs.chain()[0]; window, acceptance = shadow._epochs.bound(epoch)
    payload = dict(identity="synthetic-compatibility", predecessor=source, successor=target_ref,
        configuration=target["configuration"], epoch=epoch["identity"], acceptance=acceptance.key,
        window=put("native-window", window.payload), mode="EXACT", relation=None, verified_ns="1")
    proof = dict(kind="COMPATIBILITY", payload=payload, role="LAUNCHER", issuer=issuer, issued_ns="2")
    lineage = dict(predecessor=process, generation="a" * 64)
    record = dict(service="synthetic-service", lineage=lineage)
    row = dict(purpose="RECOVERY_OPERATION", authority="SPONSOR", bindings=dict(service=record["service"], lineage=lineage,
        predecessor_source=source, target=target_ref,
        compatibility=put(payload["identity"], canonical_bytes(proof))))
    class SyntheticPrevalidatedRegistry:
        def __init__(self):
            self.store=store; self.preparation=SimpleNamespace(record=record, rows={"exact-operation":row})
            self.codec=SimpleNamespace(decode_proof=lambda raw:json.loads(raw))
        def verify_blob(self, ref, kind, **_bound_subject):
            value=proofs[ref["hash"]]
            assert store.read_blob(ref) == canonical_bytes(value)
            assert value["kind"] == kind
            return value
    registry = SyntheticPrevalidatedRegistry()
    def rebind():
        fresh_target=retain("TARGET_ARTIFACT", target)
        row["bindings"]["target"] = fresh_target
        if proof["role"] == "LAUNCHER": payload["successor"] = fresh_target
        row["bindings"]["compatibility"] = put(payload["identity"], canonical_bytes(proof))
    return SimpleNamespace(shadow=shadow,store=store,proofs=proofs,registry=registry,
        proof=proof,payload=payload,row=row,target=target,target_ref=target_ref,
        before=before,target_manifest=target_manifest,modules=modules,retain=retain,rebind=rebind,put=put)


def test_exact_native_eligibility_uses_retained_records_not_context(native_case):
    c = native_case; before = inventory(c.shadow._epochs.raw.root)
    bogus = dict(wo06h_epoch={"fabricated":True}, wo06h_predecessor={}, wo06h_successor={}, wo06h_verified_at=NOW-timedelta(days=500))
    assert validate_external_native_proof(c.proof,c.registry,bogus) == c.shadow._epochs.chain()[0]
    assert inventory(c.shadow._epochs.raw.root) == before


@pytest.mark.parametrize("fault", ["epoch","acceptance","window","configuration","target_rows","target_source","predecessor_source"])
def test_native_binding_or_operation_manifest_substitution_is_rejected(native_case, fault):
    c=native_case
    if fault in {"epoch","acceptance"}: c.payload[fault]="wrong-"+fault
    elif fault=="window": c.payload["window"]=c.store.write_blob("different-window", b"{}")
    elif fault=="configuration": c.payload["configuration"]=c.store.write_blob("different-config",canonical(asdict(LauncherConfiguration(8933,False))))
    elif fault=="target_rows": c.target["capability_manifest"]=c.store.write_blob("recovery-operations",canonical_bytes([dict(operation="journal",module="kronos.synthetic_compatibility",digest="e"*64,contract="R3")]))
    elif fault=="target_source": c.target["revision"]="f"*40
    elif fault=="predecessor_source": c.payload["predecessor"]=c.retain("SOURCE",dict(process=dict(pid="5555",kernel_birth=dict(seconds="1",microseconds="2"),runtime="foreign"),runtime_manifest=c.put("foreign-manifest",canonical(asdict(c.before))),source_inventory=c.target["source_inventory"]),"PREDECESSOR")
    c.rebind(); before=inventory(c.shadow._epochs.raw.root)
    with pytest.raises(ValueError): validate_external_native_proof(c.proof,c.registry,{"wo06h_epoch":c.shadow._epochs.chain()[0]})
    assert inventory(c.shadow._epochs.raw.root)==before


def test_prefork_native_fact_requires_no_future_operational_approval(native_case):
    c=native_case; c.registry.preparation.rows={}
    # The outer test boundary independently prevalidates the CA target artifact.
    # No operation, CLAIM or process transition is executed or authorized here.
    assert validate_external_native_proof(c.proof,c.registry,{})==c.shadow._epochs.chain()[0]


def test_original_counted_capture_returns_only_native_unsigned_facts(native_case):
    from kronos.common.failed_fenced_recovery import EvidenceRegistry,RecoveryBudget
    from tests.unit.common.test_failed_fenced_recovery import CLOCK
    import time
    c=native_case
    # The exact fixed Registry type is retained; only the same documented outer
    # prevalidated SOURCE/CA TARGET/MAC boundary is substituted in this unit.
    registry=object.__new__(EvidenceRegistry)
    registry.store=c.registry.store;registry.preparation=c.registry.preparation
    registry.preparation.record.update(mode="ORIGINAL",controller=c.proof["issuer"])
    registry.preparation.rows={}
    registry.codec=SimpleNamespace(clock=CLOCK)
    registry.verify_blob=c.registry.verify_blob
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    budget=RecoveryBudget(CLOCK,now,now+15_000_000_000)
    before={str(path.relative_to(c.store.root)):path.read_bytes() for path in c.store.root.rglob("*") if path.is_file()}
    payload=compatibility.capture_native_compatibility_payload(registry,c.payload["predecessor"],c.payload["successor"],budget=budget)
    assert set(payload)==set(c.payload) and payload["mode"]=="EXACT"
    assert payload["epoch"]==c.payload["epoch"] and payload["acceptance"]==c.payload["acceptance"]
    assert payload["window"]["hash"]==c.payload["window"]["hash"]
    assert now<=int(payload["verified_ns"])<=budget.check()
    assert not {"mac","issuer","approval","authorization","transaction","slot"}.intersection(payload)
    assert {str(path.relative_to(c.store.root)):path.read_bytes() for path in c.store.root.rglob("*") if path.is_file()}==before
    registry.preparation.record["mode"]="RECOVERY"
    with pytest.raises(RecoveryStartupError,match="CAPTURE_CONTEXT"):
        compatibility.capture_native_compatibility_payload(registry,c.payload["predecessor"],c.payload["successor"],budget=budget)


def test_first_generation_facts_do_not_require_or_create_future_target_wrapper(native_case):
    from kronos.common.failed_fenced_recovery import EvidenceRegistry,RecoveryBudget
    from tests.unit.common.test_failed_fenced_recovery import CLOCK
    import time
    c=native_case;registry=object.__new__(EvidenceRegistry)
    registry.store=c.store;registry.codec=SimpleNamespace(clock=CLOCK)
    artifact="synthetic-prevalidated-artifact"
    body=dict(c.target,package=c.put("fixture-package",b"synthetic independently approved package"),
        bootstrap_plan=c.put("fixture-bootstrap",b"synthetic independently approved plan"))
    declaration=dict(identity="fixture-restoration",approval=artifact,service="synthetic-service",
        **{field:body[field] for field in ("revision","source_inventory","configuration")})
    restore=c.retain("RESTORATION_PLAN",declaration)
    row=dict(identity=artifact,authority="CA",purpose="ARTIFACT",bindings=body)
    registry.preparation=SimpleNamespace(record=dict(c.registry.preparation.record,mode="ORIGINAL",controller=c.proof["issuer"]),
        catalogue=dict(interface=c.put("fixture-interface",b"synthetic prevalidated interface"),
            scope=c.put("fixture-scope",b"synthetic prevalidated scope")),
        approval=lambda identity,**expected:row if identity==artifact and expected==dict(purpose="ARTIFACT",authority="CA") else pytest.fail("Wrong approved artifact"))
    registry.verify_blob=c.registry.verify_blob
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC);budget=RecoveryBudget(CLOCK,now,now+15_000_000_000)
    before={str(path.relative_to(c.store.root)):path.read_bytes() for path in c.store.root.rglob("*") if path.is_file()}
    target,fields=compatibility.capture_native_compatibility_facts(registry,c.payload["predecessor"],artifact,restore,budget=budget)
    assert target["approval"]==artifact and target["restoration_plan"]==restore
    assert all(target[key]==value for key,value in body.items())
    assert set(fields)==set(c.payload)-{"successor"}
    assert fields["epoch"]==c.payload["epoch"] and fields["window"]["hash"]==c.payload["window"]["hash"]
    assert not {"mac","issuer","authorization","transaction","slot","successor"}.intersection(fields)
    assert {str(path.relative_to(c.store.root)):path.read_bytes() for path in c.store.root.rglob("*") if path.is_file()}==before
    declaration["configuration"]=c.put("changed-config",b"changed")
    with pytest.raises((ValueError,AssertionError)):
        compatibility.capture_native_compatibility_facts(registry,c.payload["predecessor"],artifact,restore,budget=budget)


@pytest.mark.parametrize("fault",[None,"missing_recovery_blob","pending","ambiguous"])
def test_automatic_direct_relation_selects_only_one_actual_retained_native_match(native_case,fault):
    from kronos.common.failed_fenced_recovery import RecoveryBudget
    from tests.unit.common.test_failed_fenced_recovery import CLOCK
    from kronos.intraday.live_shadow_epochs import document
    import time
    c=native_case
    caps=tuple(replace(value,implementation_digest="b"*64) if value.identity=="INTRADAY_DISCOVERY_OPERATION" else value
        for value in c.target_manifest.capabilities)
    after=create_runtime_manifest(c.target_manifest.startup,LauncherConfiguration(8947,False),caps)
    c.shadow._manifest=after
    native=relation(c.shadow,approved=fault!="pending");c.shadow._epochs.retain(native)
    if fault!="missing_recovery_blob":c.put(native["identity"],canonical(native))
    if fault=="ambiguous":
        body=deepcopy(native["body"]);body["evidence_package"]["identity"]="SECOND-SYNTHETIC-QUALIFICATION"
        other=document("successor_compatibility",body);c.shadow._epochs.retain(other)
        c.put(other["identity"],canonical(other))
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC);budget=RecoveryBudget(CLOCK,now,now+15_000_000_000)
    before=inventory(c.shadow._epochs.raw.root)
    if fault is None:
        actual=compatibility._retained_direct_relation(c.shadow._epochs,c.shadow._epochs.chain()[0],
            compatibility.native_wo06h_proof(after),c.registry,budget)
        assert actual==dict(identity=native["identity"],hash=sha256(canonical(native)).hexdigest(),bytes=str(len(canonical(native))))
    else:
        with pytest.raises(ValueError):
            compatibility._retained_direct_relation(c.shadow._epochs,c.shadow._epochs.chain()[0],
                compatibility.native_wo06h_proof(after),c.registry,budget)
    assert inventory(c.shadow._epochs.raw.root)==before


@pytest.mark.parametrize("when", ["before","end","after"])
def test_native_original_window_is_end_exclusive_without_context_restamping(native_case,monkeypatch,when):
    c=native_case; body=c.shadow._epochs.chain()[0]["body"]
    now=instant(body["start"])-timedelta(microseconds=1) if when=="before" else instant(body["end"])+(timedelta(microseconds=1) if when=="after" else timedelta())
    monkeypatch.setattr(compatibility,"_utc_now",lambda:now)
    before=inventory(c.shadow._epochs.raw.root)
    with pytest.raises(RecoveryStartupError,match="WINDOW_NOT_ACTIVE"):
        validate_external_native_proof(c.proof,c.registry,{"wo06h_verified_at":NOW})
    assert inventory(c.shadow._epochs.raw.root)==before


def test_static_target_and_actual_child_are_distinct_native_identities(native_case):
    c=native_case
    actual=create_runtime_manifest(native_startup(c.target_manifest.startup,process_id=c.before.startup.process_id+2,process_nonce="3"*32),
        LauncherConfiguration(8947,False), c.target_manifest.capabilities)
    declared=compatibility.verify_target_runtime_manifest(actual,c.store.read_blob(c.target["capability_manifest"]),c.target,c.store.read_blob(c.target["source_inventory"]))
    assert declared is not actual and declared.manifest_identity!=actual.manifest_identity
    assert actual.startup.process_id!=declared.startup.process_id


@pytest.mark.parametrize("kind", ["SOURCE", "CAPABILITY"])
@pytest.mark.parametrize("fault", [None,"process","inventory","capability","future_startup","missing_operation"])
def test_postfork_derives_actual_child_and_rejects_target_substitution(native_case,kind,fault):
    c=native_case
    original=c.row["bindings"]["compatibility"]
    c.proofs[original["hash"]]=deepcopy(c.proof)
    caps=c.target_manifest.capabilities
    if fault=="capability":caps=(replace(caps[0],implementation_digest="0"*64),*caps[1:])
    actual=create_runtime_manifest(native_startup(c.target_manifest.startup,
        process_id=c.before.startup.process_id+2,process_nonce="3"*32,
        startup_boundary_at=NOW+timedelta(days=500) if fault=="future_startup" else NOW+timedelta(seconds=30)),
        LauncherConfiguration(8947,False),caps)
    process=dict(pid=str(actual.startup.process_id),kernel_birth=dict(seconds="5",microseconds="6"),runtime="synthetic-child")
    source=c.retain("SOURCE",dict(process=process,
        runtime_manifest=c.put("actual-child-manifest",canonical(asdict(actual))),
        source_inventory=c.put("foreign-source",canonical((("kronos.foreign","b"*64),))) if fault=="inventory" else c.target["source_inventory"]),"SUCCESSOR")
    successor=c.retain("CAPABILITY",dict(source=source),"SUCCESSOR") if kind=="CAPABILITY" else source
    c.proof.update(role="SUCCESSOR",issuer=dict(process,pid="12345") if fault=="process" else process)
    c.payload["successor"]=successor
    if fault=="missing_operation":c.registry.preparation.rows={}
    before=inventory(c.shadow._epochs.raw.root)
    if fault is None:
        assert validate_external_native_proof(c.proof,c.registry,{})==c.shadow._epochs.chain()[0]
        assert actual.startup.process_id!=c.target_manifest.startup.process_id
    else:
        with pytest.raises(ValueError):validate_external_native_proof(c.proof,c.registry,{})
    assert inventory(c.shadow._epochs.raw.root)==before


def historical_marker(c):
    """Actual closed reader marker over MAC records; outer owner trust is synthetic."""
    from kronos.common import failed_fenced_startup as startup
    from kronos.common import failed_fenced_schema as schema
    from tests.unit.common.test_failed_fenced_recovery import codec, evidence, PROCESS
    from tests.unit.common.test_failed_fenced_child_receipts import graph, _example, CHILD, CHECKPOINT, READY
    from kronos.common.failed_fenced_recovery import record_ref
    encoder=codec(); c.registry.codec=encoder
    compraw=encoder.encode_proof("COMPATIBILITY",c.payload,c.proof["issuer"],"LAUNCHER",2)
    c.proof=encoder.decode_proof(compraw,"COMPATIBILITY")
    comp=dict(authority="LAUNCHER",contract="synthetic-prevalidated",**c.put(c.payload["identity"],compraw))
    def external(proof_kind,role="SUCCESSOR",**fields):
        payload=_example(schema._parse(schema.PROOF_SCHEMAS[proof_kind]));payload.update(fields)
        payload["identity"]="synthetic-"+proof_kind.lower()+"-"+role.lower()
        process=CHILD if role=="SUCCESSOR" else PROCESS
        if "process" in payload:payload["process"]=process
        raw=encoder.encode_proof(proof_kind,payload,process,role,10)
        return dict(authority=role,contract="synthetic-prevalidated",**c.put(payload["identity"],raw))
    before=external("SOURCE","PREDECESSOR"); beforecap=external("CAPABILITY","PREDECESSOR")
    after=external("SOURCE");aftercap=external("CAPABILITY");bootstrap=external("BOOTSTRAP_IDENTITY")
    # Explicit existing absence fields; no native status or approval is inferred.
    provider=external("ABSENCE",kind="PROVIDER",active="0",retained_leases="0",callbacks="0",unresolved_cleanup="0")
    transport=external("ABSENCE",kind="MARKET_TRANSPORT",active="0",retained_leases="0",callbacks="0",unresolved_cleanup="0")
    checkpoint=external("OWNER_RESULT","PREDECESSOR",owner="WO13",purpose="CHECKPOINT",
        action="CERTIFY_CHECKPOINT",result="COMPLETE",reason="CHECKPOINT_COMPLETE",
        notification_failure=False,durability_unproven=False,owned_workers="0",queued_items="0",callbacks="0",durable_writes="0")
    termination=external("EXECUTOR_TERMINATION","PREDECESSOR",owned_workers="0",pending_callbacks="0",pending_publications="0")
    executor_payload=_example(schema._parse(schema.RECORD_SCHEMAS["EXECUTOR"]))
    executor_payload.update(state="TERMINATED",original_controller=evidence(),no_child_start=evidence(),no_consumption=evidence(),completion=termination)
    executorraw=encoder.encode("EXECUTOR",executor_payload,"PREDECESSOR",10)
    c.store.publish(executorraw)
    binding=_example(schema._parse(schema.TYPE_SCHEMAS["OriginalBinding"]));binding["executor"]=record_ref(executorraw)
    chain=graph({"ORIGINAL":dict(source=before,capability=beforecap),
        "CLAIM":dict(compatibility=comp,binding=binding),
        "CHILD_IDENTITY":dict(bootstrap=bootstrap),
        "SEAL":dict(checkpoint=dict(CHECKPOINT,evidence=checkpoint)),
        "READY_RECEIPT":dict(source=after,capability=aftercap,provider_absence=provider,transport_absence=transport)})
    restoration=external("RESTORATION",startup_context=record_ref(chain["STARTUP_CONTEXT_RAW"]),result="READY")
    payload=dict(chain["READY_RECEIPT"]["payload"],restoration=restoration)
    readyraw=encoder.encode("READY_RECEIPT",payload,"LAUNCHER",READY-500_000_000)
    chain["READY_RECEIPT"],chain["READY_RECEIPT_RAW"]=encoder.decode(readyraw),readyraw
    c.store.publish(readyraw)
    return startup._HistoricalRecoveryValidation(encoder,c.store,readyraw,chain,_reader=startup._HISTORICAL_GRAPH_READER)


@pytest.mark.parametrize("current_epoch_changed",[False,True])
def test_exact_resolved_history_does_not_regrant_or_require_todays_epoch(native_case,monkeypatch,current_epoch_changed):
    c=native_case; marker=historical_marker(c)
    original=c.shadow._epochs.chain()[0]
    if current_epoch_changed:
        from tests.unit.intraday.test_live_shadow_epochs import restart,authorize,perform
        successor=restart(c.shadow._epochs.raw.root.parent,c.shadow)
        perform(successor,authorize(successor))
        assert successor._epochs.chain()[0]["identity"]!=original["identity"]
    monkeypatch.setattr(compatibility,"_utc_now",lambda:instant(original["body"]["end"])+timedelta(days=100))
    before=inventory(c.shadow._epochs.raw.root)
    assert validate_external_native_proof(c.proof,c.registry,{"historical_validation":marker})==original
    assert inventory(c.shadow._epochs.raw.root)==before
    with pytest.raises(RecoveryStartupError,match="WINDOW_NOT_ACTIVE|EPOCH_BINDING"):
        validate_external_native_proof(c.proof,c.registry,{"historical":True})


def test_caller_boolean_or_duck_marker_cannot_supply_historical_authority(native_case,monkeypatch):
    c=native_case
    monkeypatch.setattr(compatibility,"_utc_now",lambda:NOW+timedelta(days=100))
    with pytest.raises(RecoveryStartupError,match="WINDOW_NOT_ACTIVE"):
        validate_external_native_proof(c.proof,c.registry,{"historical":True})
    with pytest.raises(RecoveryStartupError,match="HISTORICAL_CONTEXT"):
        validate_external_native_proof(c.proof,c.registry,{"historical_validation":SimpleNamespace(permits=lambda *args:True)})


@pytest.mark.parametrize("fault", ["capability","configuration","revision","inventory"])
def test_actual_child_cannot_substitute_target_declarations(native_case,fault):
    c=native_case; m=c.target_manifest; caps=m.capabilities
    if fault=="capability":caps=(replace(caps[0],implementation_digest="0"*64),*caps[1:])
    startup=native_startup(m.startup,source_revision="f"*40) if fault=="revision" else native_startup(m.startup,source_snapshot_digest="0"*64) if fault=="inventory" else m.startup
    actual=create_runtime_manifest(startup,LauncherConfiguration(8933 if fault=="configuration" else 8947,False),caps)
    with pytest.raises(ValueError): compatibility.verify_target_runtime_manifest(actual,c.store.read_blob(c.target["capability_manifest"]),c.target,c.store.read_blob(c.target["source_inventory"]))


@pytest.mark.parametrize("fault", [None,"pending","not_retained","reverse","calculation"])
def test_direct_approved_uses_exact_native_relation_and_preserves_history(native_case,fault):
    c=native_case
    caps=tuple(replace(v,implementation_digest="b"*64) if v.identity=="INTRADAY_DISCOVERY_OPERATION" or (fault=="calculation" and v.identity=="WO_06H_LIVE_SHADOW") else v for v in c.target_manifest.capabilities)
    target_manifest=create_runtime_manifest(c.target_manifest.startup,LauncherConfiguration(8947,False),caps)
    c.shadow._manifest=target_manifest
    record=relation(c.shadow,approved=fault!="pending")
    if fault=="reverse":
        body=deepcopy(record["body"]);body["direction"]="TARGET_TO_SOURCE";record=document("successor_compatibility",body)
    if fault!="not_retained":c.shadow._epochs.retain(record)
    c.target["capability_manifest"]=c.store.write_blob("qualified-target-native",canonical(asdict(target_manifest)))
    c.payload.update(mode="DIRECT_APPROVED",relation=c.store.write_blob(record["identity"],canonical(record)))
    c.rebind(); before=inventory(c.shadow._epochs.raw.root)
    if fault is None:
        assert validate_external_native_proof(c.proof,c.registry,{})==c.shadow._epochs.chain()[0]
    else:
        with pytest.raises(ValueError):validate_external_native_proof(c.proof,c.registry,{})
    assert inventory(c.shadow._epochs.raw.root)==before


def test_historical_native_checks_preserve_exact_owner_function_asts():
    import ast
    from pathlib import Path
    from kronos.intraday import live_shadow_history_checks as pure
    from kronos.application import intraday_shadow_history as application
    nodes={node.name:node for node in ast.parse(Path(pure.__file__).read_text()).body if isinstance(node,ast.FunctionDef)}
    # These exact pre-extraction native bodies are immutable expected inputs;
    # same-interpreter parsing avoids version-dependent ast.dump formatting.
    originals={'validate_historical_relation': 'def validate_historical_relation(record, epoch, current, now):\n    """Require all existing exact relation checks at actual post-expiry time.\n\n    The frozen operational validator checks approvals *after* its window gate.\n    Check those independently first, then accept only that specific time denial.\n    This never supplies a fabricated in-window time or grants active authority.\n    """\n    validate(record); validate(epoch)\n    _validate_successor_body(record[\'body\'])\n    if any(row[\'disposition\'] != \'APPROVED\' for row in record[\'body\'][\'owner_approvals\']):\n        raise ShadowError(\'SHADOW_SUCCESSOR_COMPATIBILITY_NOT_APPROVED\')\n    if now < instant(epoch[\'body\'][\'end\']):\n        raise ShadowError(\'SHADOW_HISTORICAL_WINDOW_NOT_EXPIRED\')\n    try:\n        validate_successor_relation(record, epoch, current, now)\n    except ShadowError as error:\n        if str(error) != \'SHADOW_RESTORATION_WINDOW_NOT_ACTIVE\':\n            raise\n        return True\n    raise ShadowError(\'SHADOW_HISTORICAL_WINDOW_INVALID\')', 'historical_compatible': "def historical_compatible(store, epoch, current, now):\n    if compatible(epoch['body']['proof'], current) or store.equivalence(epoch, current):\n        return True\n    source, target = capability_identity(epoch['body']['proof']), capability_identity(current)\n    fd = store._directory()\n    if fd is None:\n        return False\n    try:\n        names = sorted(name for name in os.listdir(fd)\n            if re.fullmatch(r'WO06H-SUCCESSOR_COMPATIBILITY-[a-f0-9]{64}\\.json', name))\n    finally:\n        os.close(fd)\n    matches = []\n    for name in names:\n        value = store.load(name[:-5]); body = value['body']\n        if (body['epoch'], body['source_aggregate'], body['target_aggregate']) == (\n                epoch['identity'], source, target):\n            matches.append(value)\n    if not matches:\n        return False\n    if len(matches) != 1:\n        raise ShadowError('SHADOW_SUCCESSOR_COMPATIBILITY_AMBIGUOUS')\n    return validate_historical_relation(matches[0], epoch, current, now)"}
    for name,source in originals.items():
        import inspect, textwrap
        owner=ast.parse(textwrap.dedent(inspect.getsource(getattr(application,name)))).body[0]
        original=ast.parse(source).body[0]
        assert ast.dump(owner,include_attributes=False)==ast.dump(original,include_attributes=False)
        assert ast.dump(nodes[name],include_attributes=False)==ast.dump(original,include_attributes=False)


@pytest.mark.parametrize("mode,fault", [("EXACT",None),("DIRECT_APPROVED",None),("DIRECT_APPROVED","pending"),("DIRECT_APPROVED","missing")])
def test_expired_native_guard_compatibility_path_has_no_product_imports(native_case,monkeypatch,tmp_path,mode,fault):
    """Real native epoch/relation files and authenticated reader marker.

    Outer reviewed SOURCE/TARGET evidence is the existing explicit synthetic
    boundary; fresh -I/-S child additionally runs the native expired branch
    with only the unchanged native acceptance-validator module allowed;
    Swing/other application, Browser and PDF imports remain prohibited.
    """
    from pathlib import Path
    import subprocess,sys
    c=native_case;target_manifest=c.target_manifest
    if mode=="DIRECT_APPROVED":
        caps=tuple(replace(value,implementation_digest="b"*64) if value.identity=="INTRADAY_DISCOVERY_OPERATION" else value for value in target_manifest.capabilities)
        target_manifest=create_runtime_manifest(target_manifest.startup,LauncherConfiguration(8947,False),caps)
        c.shadow._manifest=target_manifest
        retained=relation(c.shadow,approved=fault!="pending")
        if fault!="missing":c.shadow._epochs.retain(retained)
        c.target["capability_manifest"]=c.put("historical-qualified-target",canonical(asdict(target_manifest)))
        c.payload.update(mode=mode,relation=c.put(retained["identity"],canonical(retained)))
        c.rebind()
    epoch=c.shadow._epochs.chain()[0];now=instant(epoch["body"]["end"])+timedelta(days=100)
    monkeypatch.setattr(compatibility,"_utc_now",lambda:now)
    marker=historical_marker(c)
    before=inventory(c.shadow._epochs.raw.root)
    estate_before={str(path):path.read_bytes() for path in c.store.root.rglob("*") if path.is_file()}
    if fault is None:
        assert validate_external_native_proof(c.proof,c.registry,{"historical_validation":marker})==epoch
    else:
        with pytest.raises(ValueError):validate_external_native_proof(c.proof,c.registry,{"historical_validation":marker})
    data=dict(before=asdict(c.before),after=asdict(target_manifest),payload=c.payload,
        root=str(c.shadow._epochs.raw.root.parent),estate=str(c.store.estate),now=now.isoformat(),fault=fault)
    inputs=tmp_path/"historical-reader-input.json";inputs.write_bytes(canonical(data))
    script="""import sys, importlib.abc, json
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace
sys.path.insert(0,sys.argv[1])
class DenyProduct(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (fullname=='pypdf' or fullname.startswith(('pypdf.','kronos.browser'))
                or fullname.startswith('kronos.application') and fullname not in {'kronos.application','kronos.application.intraday_live_shadow'}):
            raise AssertionError('historical helper imported product package: '+fullname)
sys.meta_path.insert(0,DenyProduct())
from kronos.common import failed_fenced_compatibility as compatibility
from kronos.common.failed_fenced_recovery import RecoveryStore
from kronos.intraday.runtime_identity import canonical
value=json.loads(Path(sys.argv[2]).read_text())
compatibility.DEFAULT_INTRADAY_EVIDENCE_ROOT=Path(value['root'])
compatibility._utc_now=lambda:datetime.fromisoformat(value['now'])
before=compatibility.read_native_runtime_manifest(canonical(value['before']))
after=compatibility.read_native_runtime_manifest(canonical(value['after']))
registry=SimpleNamespace(store=RecoveryStore(Path(value['estate'])))
try:
    result=compatibility._validate_native_window(value['payload'],before,after,registry,historical=True)
except ValueError:
    if value['fault'] is None:raise
else:
    assert value['fault'] is None and result['identity']==value['payload']['epoch']
assert not any(name.startswith(('kronos.browser','pypdf')) or name.startswith('kronos.application') and name not in {'kronos.application','kronos.application.intraday_live_shadow'} for name in sys.modules)
assert 'kronos.application.intraday_live_shadow' in sys.modules
"""
    source=Path(__file__).resolve().parents[3]/"src"
    result=subprocess.run([sys.executable,"-I","-S","-B","-c",script,str(source),str(inputs)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stdout+result.stderr
    assert inventory(c.shadow._epochs.raw.root)==before
    assert {str(path):path.read_bytes() for path in c.store.root.rglob("*") if path.is_file()}==estate_before
