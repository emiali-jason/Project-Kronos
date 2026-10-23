"""Fixed WO06H compatibility adapter; no caller context supplies native truth.

The qualified target manifest is a retained declaration snapshot. Its process
identity never asserts that an unborn successor has loaded anything. Later
SOURCE evidence independently proves the actual child, then compares the
complete declarations/configuration/source with that unchanged target.
"""
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json

from kronos.intraday.evidence_paths import DEFAULT_INTRADAY_EVIDENCE_ROOT
from kronos.intraday.runtime_identity import (
    StartupEvidence, RuntimeManifest, LoadedCapability, LauncherConfiguration, canonical,
)


def _deny(condition, reason):
    if not condition:
        from .failed_fenced_startup import RecoveryStartupError
        raise RecoveryStartupError("RECOVERY_NATIVE_COMPATIBILITY_" + reason)


def read_native_runtime_manifest(raw):
    """Reconstruct the unchanged native identity, including canonical bytes."""
    try:
        data = json.loads(raw)
        startup = dict(data["startup"])
        startup["startup_boundary_at"] = datetime.fromisoformat(startup["startup_boundary_at"])
        startup["loaded_modules"] = tuple(tuple(row) for row in startup["loaded_modules"])
        data["startup"] = StartupEvidence(**startup)
        data["capabilities"] = tuple(LoadedCapability(**row) for row in data["capabilities"])
        manifest = RuntimeManifest(**data)
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        from .failed_fenced_startup import RecoveryStartupError
        raise RecoveryStartupError("RECOVERY_NATIVE_COMPATIBILITY_NATIVE_MANIFEST") from error
    _deny(canonical(asdict(manifest)) == raw, "NATIVE_MANIFEST_ENCODING")
    _deny(manifest.startup.source_state == "CLEAN_COMMIT"
        and manifest.startup.load_verification == "PINNED_STARTUP_IMPORTS", "NATIVE_SOURCE")
    return manifest


def native_wo06h_proof(manifest):
    """Existing native proof projection; no substituted PID or manifest ID."""
    from kronos.intraday.live_shadow_acceptance import validate_acceptance_proof
    _deny(type(manifest) is RuntimeManifest, "NATIVE_MANIFEST")
    result = dict(manifest=manifest.manifest_identity, pid=manifest.startup.process_id,
        revision=manifest.startup.source_revision, source_state=manifest.startup.source_state,
        startup=manifest.startup.startup_boundary_at.isoformat(),
        configuration=manifest.configuration_identity,
        capabilities=[asdict(row) for row in manifest.capabilities])
    validate_acceptance_proof(result, manifest.manifest_identity)
    return result


def validate_qualified_target_manifest(raw, target, inventory_raw):
    """Bind the existing native declaration snapshot to its approved target."""
    from .failed_fenced_startup import validate_source_inventory_blob
    manifest = read_native_runtime_manifest(raw)
    modules = dict(validate_source_inventory_blob(inventory_raw))
    _deny(manifest.startup.source_revision == target["revision"]
        and manifest.startup.source_snapshot_digest == sha256(inventory_raw).hexdigest()
        and all(modules.get(name) == digest for name, digest in manifest.startup.loaded_modules),
        "TARGET_SOURCE")
    native_wo06h_proof(manifest)
    return manifest


def verify_target_runtime_manifest(actual, declaration_raw, target, inventory_raw):
    """Compare actual child declarations; target PID/time are never copied."""
    declared = validate_qualified_target_manifest(declaration_raw, target, inventory_raw)
    _deny(type(actual) is RuntimeManifest, "ACTUAL_MANIFEST")
    native_wo06h_proof(actual)
    _deny(actual.startup.source_revision == declared.startup.source_revision
        and actual.startup.source_snapshot_digest == declared.startup.source_snapshot_digest
        and actual.configuration_identity == declared.configuration_identity
        and actual.capabilities == declared.capabilities, "TARGET_CHANGED")
    return declared


def _utc_now():
    return datetime.now(timezone.utc)


def _canonical_epoch_store():
    # Canonical source-owned estate, not a path from an HTTP/env/context value.
    from kronos.intraday.live_shadow_epochs import EpochStore
    from kronos.intraday.live_shadow_persistence import ShadowStore
    return EpochStore(ShadowStore(DEFAULT_INTRADAY_EVIDENCE_ROOT))


def _retained_direct_relation(epochs,epoch,current,registry,budget):
    """Same exact non-transitive selector as EpochStore.successor_equivalence."""
    import os,re
    from kronos.intraday.live_shadow_transition import capability_identity,validate_successor_relation
    now=_utc_now()
    _deny(epochs.successor_equivalence(epoch,current,now),"RELATION_REQUIRED")
    source=capability_identity(epoch["body"]["proof"]);target=capability_identity(current)
    descriptor=epochs._directory()
    _deny(descriptor is not None,"RELATION_REQUIRED")
    try:names=sorted(name for name in os.listdir(descriptor)
        if re.fullmatch(r"WO06H-SUCCESSOR_COMPATIBILITY-[a-f0-9]{64}\.json",name))
    finally:os.close(descriptor)
    matches=[]
    for name in names:
        budget.check();record=epochs.load(name[:-5]);body=record["body"]
        if (body["epoch"],body["source_aggregate"],body["target_aggregate"])==(epoch["identity"],source,target):matches.append(record)
    _deny(len(matches)==1,"RELATION_REQUIRED")
    record=matches[0];validate_successor_relation(record,epoch,current,_utc_now())
    from .failed_fenced_recovery import blob_ref
    raw=canonical(record);reference=blob_ref(record["identity"],raw)
    _deny(registry.store.read_blob(reference)==raw,"RELATION_NOT_RETAINED")
    budget.check()
    return reference


def capture_native_compatibility_payload(registry, predecessor, successor, *, budget, relation=None):
    """Unsigned factual proposal in the already counted ORIGINAL preflight.

    The private native C exchange remains the only L issuer. This function
    cannot publish, acquire an operational permission, select a caller epoch or
    replace the native acceptance/window. Its referenced original factual bytes
    must already be present in the independently prepared immutable estate.
    A later recovery operation still binds its exact current-C proof identity.
    """
    from .failed_fenced_recovery import EvidenceRegistry, RecoveryBudget, blob_ref, canonical_bytes
    from kronos.intraday.live_shadow_epochs import compatible
    _deny(type(registry) is EvidenceRegistry and type(budget) is RecoveryBudget
        and registry.preparation.record["mode"] == "ORIGINAL"
        and registry.codec.clock == budget.clock, "CAPTURE_CONTEXT")
    budget.check()
    source=registry.verify_blob(predecessor,"SOURCE",context={"mode":"ORIGINAL"})["payload"]
    _deny(source["process"]==registry.preparation.record["lineage"]["predecessor"],"PREDECESSOR")
    target=registry.verify_blob(successor,"TARGET_ARTIFACT",context={"mode":"ORIGINAL"})["payload"]
    before=read_native_runtime_manifest(registry.store.read_blob(source["runtime_manifest"]))
    after=validate_qualified_target_manifest(registry.store.read_blob(target["capability_manifest"]),
        target,registry.store.read_blob(target["source_inventory"]))
    epochs=_canonical_epoch_store();chain=epochs.chain()
    _deny(bool(chain),"EPOCH_MISSING")
    epoch=chain[0];window,acceptance=epochs.bound(epoch)
    window_ref=blob_ref("native-compatibility-window",window.payload)
    _deny(registry.store.read_blob(window_ref)==window.payload,"WINDOW_NOT_RETAINED")
    if compatible(native_wo06h_proof(before),native_wo06h_proof(after)):
        _deny(relation is None,"RELATION_UNEXPECTED")
        mode="EXACT"
    else:
        _deny(relation is not None,"RELATION_REQUIRED")
        mode="DIRECT_APPROVED"
    verified=budget.check()
    payload=dict(identity="native-compatibility-"+sha256(canonical_bytes(dict(
        predecessor=predecessor,successor=successor,epoch=epoch["identity"]))).hexdigest(),
        predecessor=predecessor,successor=successor,configuration=target["configuration"],
        epoch=epoch["identity"],acceptance=acceptance.key,window=window_ref,
        mode=mode,relation=relation,verified_ns=str(verified))
    # Reuse the same fixed native validator as every later consumption. The
    # synthetic unsigned envelope is never encoded, retained or authenticated.
    proposal=dict(kind="COMPATIBILITY",role="LAUNCHER",issuer=registry.preparation.record["controller"],
        payload=payload,issued_ns=str(verified))
    validate_compatibility_evidence(proposal,registry,{"mode":"ORIGINAL"})
    _deny(epochs.chain()[0]==epoch,"EPOCH_CHANGED")
    budget.check()
    return payload


def capture_native_compatibility_facts(registry, predecessor, artifact_approval, restoration_plan, *, budget, relation=None):
    """First-generation native facts, before a recovery C or its proof exists.

    ARTIFACT and RESTORATION_PLAN retain their existing independent authorities.
    The returned target is only their factual declaration; the compatibility
    fields intentionally lack the future successor wrapper. The original C
    retains these unsigned bytes through its fixed FACT exchange. Recovery C
    later issues its own TARGET, fills that exact successor Blob, and only the
    subsequent Sponsor operation can authorize a recovery of that identity.
    """
    from .failed_fenced_recovery import EvidenceRegistry, RecoveryBudget, blob_ref, canonical_bytes
    from kronos.intraday.live_shadow_epochs import compatible
    _deny(type(registry) is EvidenceRegistry and type(budget) is RecoveryBudget
        and registry.preparation.record["mode"]=="ORIGINAL"
        and registry.codec.clock==budget.clock,"CAPTURE_CONTEXT")
    budget.check()
    row=registry.preparation.approval(artifact_approval,purpose="ARTIFACT",authority="CA")
    binding=row["bindings"]
    plan=registry.verify_blob(restoration_plan,"RESTORATION_PLAN")["payload"]
    _deny(plan["approval"]==artifact_approval and all(plan[field]==binding[field]
        for field in ("revision","source_inventory","configuration"))
        and plan["service"]==registry.preparation.record["service"]
        and binding["bootstrap_plan"] is not None,"TARGET_SOURCE")
    target=dict(identity="native-target-"+binding["source_inventory"]["hash"],approval=artifact_approval,
        service=plan["service"],**{field:binding[field] for field in
            ("revision","source_inventory","capability_manifest","configuration","package","bootstrap_plan")},
        interface=registry.preparation.catalogue["interface"],scope=registry.preparation.catalogue["scope"],
        restoration_plan=restoration_plan)
    source=registry.verify_blob(predecessor,"SOURCE",context={"mode":"ORIGINAL"})["payload"]
    _deny(source["process"]==registry.preparation.record["lineage"]["predecessor"],"PREDECESSOR")
    before=read_native_runtime_manifest(registry.store.read_blob(source["runtime_manifest"]))
    after=validate_qualified_target_manifest(registry.store.read_blob(target["capability_manifest"]),
        target,registry.store.read_blob(target["source_inventory"]))
    epochs=_canonical_epoch_store();chain=epochs.chain()
    _deny(bool(chain),"EPOCH_MISSING")
    epoch=chain[0];window,acceptance=epochs.bound(epoch)
    window_ref=blob_ref("native-compatibility-window",window.payload)
    _deny(registry.store.read_blob(window_ref)==window.payload,"WINDOW_NOT_RETAINED")
    exact=compatible(native_wo06h_proof(before),native_wo06h_proof(after))
    if not exact and relation is None:
        relation=_retained_direct_relation(epochs,epoch,native_wo06h_proof(after),registry,budget)
    _deny(relation is None if exact else relation is not None,"RELATION_UNEXPECTED" if exact else "RELATION_REQUIRED")
    fields=dict(identity="native-compatibility-"+sha256(canonical_bytes(dict(
        predecessor=predecessor,target=target,epoch=epoch["identity"]))).hexdigest(),
        predecessor=predecessor,configuration=target["configuration"],epoch=epoch["identity"],
        acceptance=acceptance.key,window=window_ref,mode="EXACT" if exact else "DIRECT_APPROVED",
        relation=relation,verified_ns=str(budget.check()))
    _validate_native_window(fields,before,after,registry)
    _deny(epochs.chain()[0]==epoch,"EPOCH_CHANGED")
    budget.check()
    return target,fields


def _selected_target(proof, registry, historical_marker=None):
    """Use the exact current pinned recovery-operation row, without a new grant."""
    payload, preparation = proof["payload"], registry.preparation
    if proof["role"] == "LAUNCHER":
        # This is an inert native fact needed to prepare the later exact
        # RECOVERY_OPERATION approval. Requiring that approval here would make
        # the fact depend on its own future hash. TARGET still requires its
        # separate preexisting CA ARTIFACT approval and fixed L issuer.
        target = registry.verify_blob(payload["successor"], "TARGET_ARTIFACT")["payload"]
        _deny(target["configuration"] == payload["configuration"], "CONFIGURATION_BINDING")
        return target
    selected = []
    for row in preparation.rows.values():
        if row["purpose"] != "RECOVERY_OPERATION" or row["authority"] != "SPONSOR":
            continue
        binding = row["bindings"]
        if (binding["service"] != preparation.record["service"]
                or binding["lineage"] != preparation.record["lineage"]
                or binding["predecessor_source"] != payload["predecessor"]):
            continue
        previous = registry.verify_blob(binding["compatibility"], "COMPATIBILITY",
            context={"historical_validation": historical_marker} if historical_marker is not None else None)["payload"]
        if any(previous[key] != payload[key] for key in
               ("predecessor", "configuration", "epoch", "acceptance", "window", "mode", "relation")):
            continue
        selected.append(binding["target"])
    _deny(len(selected) == 1, "TARGET_SELECTION")
    target = registry.verify_blob(selected[0], "TARGET_ARTIFACT")["payload"]
    _deny(target["configuration"] == payload["configuration"], "CONFIGURATION_BINDING")
    return target


def validate_compatibility_evidence(proof, registry, context=None):
    """Read current native epoch/window; unchanged validators decide eligibility."""
    from kronos.intraday.live_shadow import instant
    from kronos.intraday.live_shadow_epochs import compatible
    from kronos.intraday.live_shadow_transition import validate_successor_relation
    from .failed_fenced_startup import _HistoricalRecoveryValidation
    marker = context.get("historical_validation") if type(context) is dict else None
    historical = type(marker) is _HistoricalRecoveryValidation and marker.permits(proof, registry)
    _deny(marker is None or historical, "HISTORICAL_CONTEXT")
    payload = proof["payload"]
    _deny(proof["role"] in {"LAUNCHER", "SUCCESSOR"}, "ROLE")
    _deny(int(payload["verified_ns"]) <= int(proof["issued_ns"]), "TIME_ORDER")
    source = registry.verify_blob(payload["predecessor"], "SOURCE", context={"mode": "ORIGINAL"})["payload"]
    _deny(source["process"] == registry.preparation.record["lineage"]["predecessor"], "PREDECESSOR")
    before = read_native_runtime_manifest(registry.store.read_blob(source["runtime_manifest"]))
    target = _selected_target(proof, registry, marker if historical else None)
    inventory_raw = registry.store.read_blob(target["source_inventory"])
    declaration_raw = registry.store.read_blob(target["capability_manifest"])
    declared = validate_qualified_target_manifest(declaration_raw, target, inventory_raw)
    if proof["role"] == "LAUNCHER":
        after = declared  # Static target eligibility, never loaded-child evidence.
    else:
        actual = registry.codec.decode_proof(registry.store.read_blob(payload["successor"]))
        _deny(actual["kind"] in {"SOURCE", "CAPABILITY"} and actual["role"] == "SUCCESSOR", "SUCCESSOR_KIND")
        current = registry.verify_blob(payload["successor"], actual["kind"], subject=proof["issuer"])["payload"]
        if actual["kind"] == "CAPABILITY":
            current = registry.verify_blob(current["source"], "SOURCE", subject=proof["issuer"])["payload"]
        _deny(current["process"] == proof["issuer"] and current["source_inventory"] == target["source_inventory"], "SUCCESSOR_BINDING")
        after = read_native_runtime_manifest(registry.store.read_blob(current["runtime_manifest"]))
        verify_target_runtime_manifest(after, declaration_raw, target, inventory_raw)
    return _validate_native_window(payload,before,after,registry,historical=historical)


def _validate_native_window(payload,before,after,registry,*,historical=False):
    """The existing source-owned native checks shared by capture and consumption."""
    from kronos.intraday.live_shadow import instant
    from kronos.intraday.live_shadow_epochs import compatible
    from kronos.intraday.live_shadow_transition import validate_successor_relation
    configuration_raw = registry.store.read_blob(payload["configuration"])
    try:
        configuration = LauncherConfiguration(**json.loads(configuration_raw))
    except (ValueError, TypeError, KeyError) as error:
        from .failed_fenced_startup import RecoveryStartupError
        raise RecoveryStartupError("RECOVERY_NATIVE_COMPATIBILITY_CONFIGURATION") from error
    _deny(canonical(asdict(configuration)) == configuration_raw
        and before.configuration_identity == after.configuration_identity == configuration.identity,
        "CONFIGURATION")
    epochs = _canonical_epoch_store()
    if historical:
        from kronos.intraday.live_shadow import ShadowError
        try:
            epoch = epochs.load(payload["epoch"])
        except ShadowError as error:
            if str(error) != "SHADOW_EPOCH_RECORD_MISSING":
                raise
            epoch = epochs.legacy()
            _deny(epoch is not None and epoch["identity"] == payload["epoch"], "EPOCH_MISSING")
    else:
        chain = epochs.chain()
        _deny(bool(chain), "EPOCH_MISSING")
        epoch = chain[0]
    window, acceptance = epochs.bound(epoch)
    _deny(payload["epoch"] == epoch["identity"]
        and payload["acceptance"] == acceptance.key == epoch["body"]["acceptance"]
        and window.key == epoch["body"]["window"]
        and registry.store.read_blob(payload["window"]) == window.payload, "EPOCH_BINDING")
    now = _utc_now()
    if not historical:
        _deny(instant(epoch["body"]["start"]) <= now < instant(epoch["body"]["end"]), "WINDOW_NOT_ACTIVE")
    old, new = native_wo06h_proof(before), native_wo06h_proof(after)
    if historical and now >= instant(epoch["body"]["end"]):
        from kronos.intraday.live_shadow_history_checks import historical_compatible
        _deny(historical_compatible(epochs, epoch, old, now), "PREDECESSOR_NOT_ACCEPTED")
    else:
        _deny(instant(old["startup"]) <= now and instant(new["startup"]) <= now, "STARTUP_TIME")
        _deny(epochs.restoration_compatible(epoch, old, now), "PREDECESSOR_NOT_ACCEPTED")
    if payload["mode"] == "EXACT":
        _deny(payload["relation"] is None and compatible(old, new), "REJECTED")
    else:
        _deny(payload["mode"] == "DIRECT_APPROVED" and payload["relation"] is not None, "RELATION_REQUIRED")
        raw = registry.store.read_blob(payload["relation"])
        relation = json.loads(raw)
        _deny(canonical(relation) == raw and epochs.load(relation["identity"]) == relation,
              "RELATION_NOT_RETAINED")
        if historical and now >= instant(epoch["body"]["end"]):
            from kronos.intraday.live_shadow_history_checks import historical_compatible, validate_historical_relation
            _deny(historical_compatible(epochs, epoch, new, now), "RELATION_REJECTED")
            validate_historical_relation(relation, epoch, new, now)
        else:
            _deny(epochs.successor_equivalence(epoch, new, now), "RELATION_REJECTED")
            validate_successor_relation(relation, epoch, new, now)
    # No epoch advance or end-boundary crossing may be hidden by a prior read.
    latest_window, latest_acceptance = epochs.bound(epoch)
    _deny((historical or epochs.chain()[0] == epoch) and latest_window.payload == window.payload
        and latest_acceptance.payload == acceptance.payload, "EPOCH_CHANGED")
    if not historical:
        _deny(instant(epoch["body"]["start"]) <= _utc_now() < instant(epoch["body"]["end"]),
              "WINDOW_NOT_ACTIVE")
    return epoch
