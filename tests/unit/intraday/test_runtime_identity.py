from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone, timedelta
from hashlib import sha1
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from kronos.intraday.runtime_identity import (
    StartupCapture, LauncherConfiguration, LoadedCapability, _startup,
    canonical, create_runtime_manifest, runtime_document,
)

NOW = datetime(2026, 9, 7, 4, 0, tzinfo=timezone.utc)
MODULE = "kronos.wo05c_fixture"


@pytest.fixture
def captured(tmp_path):
    path = tmp_path / "src/kronos/wo05c_fixture.py"
    path.parent.mkdir(parents=True)
    path.write_text("VALUE = 'A'\ndef observed(): return VALUE\n")
    state = {"revision": "a" * 40, "dirty": False, "unavailable": False, "calls": [], "blob_override": None, "branch": "develop"}
    class FixtureCapture(StartupCapture):
        @staticmethod
        def _application_name(name):
            return name.startswith("kronos.wo05c_")
        def _git(self, *args):
            state["calls"].append(args)
            if state["unavailable"]: raise FileNotFoundError("OFFLINE-GIT-UNAVAILABLE")
            if args[0] == "rev-parse": return state["revision"].encode()
            if args[0] == "symbolic-ref":
                if state["branch"] is None: raise subprocess.CalledProcessError(1, "git")
                return state["branch"].encode()
            if args[0] == "status": return b" M src/kronos/wo05c_fixture.py" if state["dirty"] else b""
            payload = path.read_bytes()
            blob = state["blob_override"] or sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
            return ("100644 blob " + blob + "\tsrc/kronos/wo05c_fixture.py\0").encode()
    def factory(**kwargs):
        return FixtureCapture(tmp_path, clock=lambda:NOW, **kwargs)
    yield path, state, factory
    sys.modules.pop(MODULE, None)


def _load(capture):
    with capture:
        module = importlib.import_module(MODULE)
        evidence = capture.finish()
        assert capture.finish() is evidence
    return module, evidence


def _seed(**kwargs):
    values = dict(source_revision="a"*40, branch="develop", source_state="CLEAN_COMMIT",
        process_id=os.getpid(), startup_boundary_at=NOW, process_nonce="1"*32,
        python_runtime="cpython 3.13.0", source_snapshot_digest="f"*64,
        loaded_modules=(("kronos.application.intraday_discovery_operation", "d"*64),),
        load_verification="PINNED_STARTUP_IMPORTS")
    return _startup(**(values | kwargs))


def test_clean_startup_captures_exact_imported_source(captured):
    _,_,factory=captured
    module,evidence=_load(factory())
    assert module.observed()=="A"
    assert evidence.source_revision=="a"*40 and evidence.source_state=="CLEAN_COMMIT"
    assert evidence.load_verification=="PINNED_STARTUP_IMPORTS"
    assert evidence.loaded_modules[0][0]==MODULE


def test_checkout_advances_during_loading_but_import_uses_captured_A(captured):
    path,state,factory=captured
    capture=factory()
    path.write_text("VALUE = 'B'\ndef observed(): return VALUE\n")
    state["revision"]="b"*40
    module,evidence=_load(capture)
    assert module.observed()=="A" and evidence.source_revision=="a"*40
    assert evidence.source_state=="CLEAN_COMMIT"
    calls=list(state["calls"])
    manifest=create_runtime_manifest(evidence,LauncherConfiguration(8947,False),())
    assert runtime_document(manifest)["loaded_commit_revision"]=="a"*40
    assert state["calls"]==calls


def test_new_process_B_has_separate_identity_and_old_process_remains_A(captured):
    path,state,factory=captured
    module_a,a=_load(factory(process_id=101,nonce="1"*32))
    sys.modules.pop(MODULE)
    path.write_text("VALUE = 'B'\ndef observed(): return VALUE\n")
    state["revision"]="b"*40
    module_b,b=_load(factory(process_id=202,nonce="2"*32))
    assert module_a.observed()=="A" and module_b.observed()=="B"
    assert a.source_revision=="a"*40 and b.source_revision=="b"*40
    assert a.evidence_identity!=b.evidence_identity


def test_dirty_source_retains_base_but_never_claims_exact_clean_commit(captured):
    _,state,factory=captured; state["dirty"]=True
    _,evidence=_load(factory())
    document=runtime_document(create_runtime_manifest(evidence,None,()))
    assert evidence.source_state=="DIRTY_WORKTREE" and evidence.source_revision=="a"*40
    assert document["loaded_commit_revision"] is None


def test_byte_comparison_catches_dirty_source_despite_clean_git_status(captured):
    _,state,factory=captured; state["blob_override"]="0"*40
    _,evidence=_load(factory())
    assert evidence.source_state=="DIRTY_WORKTREE"


def test_git_unavailable_does_not_block_existing_application_loading(captured):
    _,state,factory=captured; state["unavailable"]=True
    module,evidence=_load(factory())
    assert module.observed()=="A"
    assert evidence.source_revision is None and evidence.source_state=="REVISION_UNAVAILABLE"


def test_preimported_application_code_is_not_retroactively_certified(captured):
    _,_,factory=captured
    _load(factory())
    _,evidence=_load(factory())
    assert evidence.source_state=="REVISION_UNAVAILABLE" and evidence.load_verification=="NOT_PROVEN"


def test_import_finder_is_removed_even_when_startup_raises(captured):
    _,_,factory=captured; capture=factory(); before=tuple(sys.meta_path)
    with pytest.raises(RuntimeError):
        with capture: raise RuntimeError("ISOLATED")
    assert tuple(sys.meta_path)==before


def test_reusing_startup_capture_rejects(captured):
    _,_,factory=captured; capture=factory(); _load(capture)
    with pytest.raises(ValueError):
        with capture: pass


@pytest.mark.parametrize("difference", [dict(process_id=999),dict(process_nonce="2"*32),dict(startup_boundary_at=NOW+timedelta(seconds=1))])
def test_pid_nonce_and_start_time_distinguish_process_instances(difference):
    assert _seed().evidence_identity!=_seed(**difference).evidence_identity


def test_configuration_digest_distinguishes_only_allowlisted_launcher_settings():
    seed=_seed()
    a=create_runtime_manifest(seed,LauncherConfiguration(8947,True),())
    b=create_runtime_manifest(seed,LauncherConfiguration(8948,True),())
    assert a.manifest_identity!=b.manifest_identity
    assert a.configuration_identity!=b.configuration_identity
    with pytest.raises(ValueError): create_runtime_manifest(seed,{"api_secret":"DO-NOT-EXPORT"},())


def test_manifest_is_immutable_and_returned_status_is_a_copy():
    manifest=create_runtime_manifest(_seed(),None,())
    with pytest.raises(FrozenInstanceError): manifest.product="SWING"
    doc=runtime_document(manifest); doc["startup"]["source_revision"]="b"*40
    assert runtime_document(manifest)["loaded_commit_revision"]=="a"*40


def test_integrity_rejects_tampered_source_and_runtime():
    seed=_seed(); manifest=create_runtime_manifest(seed,None,())
    with pytest.raises(ValueError): replace(seed,source_revision="b"*40)
    with pytest.raises(ValueError): replace(manifest,configuration_identity="INTRADAY-LAUNCHER-CONFIG-"+"b"*64)


@pytest.mark.parametrize("invalid", [dict(process_id=0),dict(process_id=True),dict(startup_boundary_at=NOW.replace(tzinfo=None)),dict(source_state="EXACT"),dict(source_revision="secret"),dict(process_nonce="bad")])
def test_invalid_startup_metadata_rejects(invalid):
    with pytest.raises(ValueError): _seed(**invalid)


def test_missing_historical_identity_is_not_fabricated_from_checkout():
    assert runtime_document(None)["availability"]=="NOT_RETAINED"
    assert runtime_document(None)["loaded_commit_revision"] is None


def test_runtime_identity_does_not_claim_market_freshness_or_acceptance():
    document=runtime_document(create_runtime_manifest(_seed(),None,()))
    assert document["runtime_accepted"]=="NOT_PROVEN"
    assert document["market_data_freshness"]=="NOT_ASSESSED_BY_RUNTIME_IDENTITY"
    assert document["os_process_birth_time"]=="NOT_RETAINED"


def test_environment_credentials_never_appear_in_manifest(monkeypatch):
    monkeypatch.setenv("KRONOS_KITE_API_SECRET","WO05C-SENTINEL-SECRET")
    monkeypatch.setenv("OPENAI_API_KEY","WO05C-SENTINEL-TOKEN")
    payload=canonical(runtime_document(create_runtime_manifest(_seed(),LauncherConfiguration(8947,False),())))
    assert b"SENTINEL" not in payload and b"API_KEY" not in payload
    assert b"/Users/" not in payload and b"environment" not in payload


def test_actual_launcher_captures_before_application_imports_in_fresh_process():
    root=Path(__file__).resolve().parents[3]
    script="from tools import kronos_browser; import json; s=kronos_browser._STARTUP_EVIDENCE; print(json.dumps({'verification':s.load_verification,'state':s.source_state,'modules':len(s.loaded_modules)}))"
    env=dict(os.environ,PYTHONPATH=str(root/'src')+':'+str(root),PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.check_output([sys.executable,'-B','-c',script],cwd=root,env=env,text=True)
    value=json.loads(result)
    assert value["verification"]=="PINNED_STARTUP_IMPORTS" and value["modules"]>100
    assert value["state"] in {"DIRTY_WORKTREE","CLEAN_COMMIT"}


def test_actual_composition_and_status_declare_loaded_capabilities(tmp_path):
    from tests.unit.intraday.test_operation_accounting import _operation
    from kronos.browser.intraday_probables_v2_control import IntradayProbablesV2OperationalControl
    from kronos.browser.intraday_routes import IntradayBrowserRoutes
    from kronos.browser.product_routes import BrowserGetRequest
    _,c,_,events=_operation(tmp_path,authenticated=False)
    control=IntradayProbablesV2OperationalControl(c.discovery_v2_operation,c.probables_v2_application,
        c.refresh_v2_provenance_store,startup_evidence=_seed(),launcher_configuration=LauncherConfiguration(8947,False))
    identity=control.status_document()["runtime_identity"]
    assert {x["identity"] for x in identity["capabilities"]}=={
        "INTRADAY_DISCOVERY_OPERATION","WO_05A_TRUSTED_TIME_ADMISSION","WO_05B_OPERATION_ACCOUNTING","INTRADAY_V2_OPERATIONAL_CONTROL"}
    routes=IntradayBrowserRoutes(c.discovery_v2_application,probables_v2_control=control)
    response=routes.handle_get(BrowserGetRequest('/control/intraday-discovery/v2/status', {}), lambda:None)
    assert json.loads(response.body)["runtime_identity"]==identity
    assert events==[] and not list(tmp_path.rglob('*runtime-manifest*'))


def test_uncomposed_capabilities_are_not_declared():
    from kronos.application.intraday_runtime_identity import compose_runtime_manifest
    manifest=compose_runtime_manifest(_seed(),None,None,None)
    assert manifest.capabilities==()


def test_foreign_process_evidence_cannot_label_current_composition():
    from kronos.application.intraday_runtime_identity import compose_runtime_manifest
    assert compose_runtime_manifest(_seed(process_id=os.getpid()+100000),None,None,None) is None


def test_missing_guard_is_not_reported_as_loaded(tmp_path,monkeypatch):
    from tests.unit.intraday.test_operation_accounting import _operation
    from kronos.application import intraday_discovery_operation as module
    from kronos.application.intraday_runtime_identity import compose_runtime_manifest
    _,c,_,_=_operation(tmp_path,authenticated=False)
    monkeypatch.setattr(module,"admit_analysis_time",None)
    manifest=compose_runtime_manifest(_seed(),None,c.discovery_v2_operation,None)
    assert "WO_05A_TRUSTED_TIME_ADMISSION" not in {x.identity for x in manifest.capabilities}


def test_status_never_relabels_inherited_parent_manifest_as_child_process(monkeypatch):
    manifest=create_runtime_manifest(_seed(),None,())
    monkeypatch.setattr(os,"getpid",lambda:manifest.startup.process_id+1)
    result=runtime_document(manifest)
    assert result["availability"]=="NOT_RETAINED"
    assert result["loaded_commit_revision"] is None
    assert result["reason"]=="PROCESS_INSTANCE_MISMATCH"


def test_detached_source_state_is_explicit():
    result=runtime_document(create_runtime_manifest(_seed(branch=None),None,()))
    assert result["startup_checkout_mode"]=="DETACHED"


def test_same_configuration_is_deterministic_and_unknown_config_stays_unknown():
    seed=_seed()
    one=create_runtime_manifest(seed,LauncherConfiguration(8947,False),())
    two=create_runtime_manifest(seed,LauncherConfiguration(8947,False),())
    assert canonical(runtime_document(one))==canonical(runtime_document(two))
    assert create_runtime_manifest(seed,None,()).configuration_identity is None


def test_missing_accounting_implementation_is_not_declared(tmp_path,monkeypatch):
    from tests.unit.intraday.test_operation_accounting import _operation
    from kronos.application import intraday_discovery_operation as module
    from kronos.application.intraday_runtime_identity import compose_runtime_manifest
    _,c,_,_=_operation(tmp_path,authenticated=False)
    monkeypatch.setattr(module,"ProviderRequestCounter",None)
    manifest=compose_runtime_manifest(_seed(),None,c.discovery_v2_operation,None)
    assert "WO_05B_OPERATION_ACCOUNTING" not in {x.identity for x in manifest.capabilities}


def test_duplicate_capabilities_reject():
    capability=LoadedCapability("TEST_CAPABILITY","1.0.0","f"*64)
    with pytest.raises(ValueError): create_runtime_manifest(_seed(),None,(capability,capability))


def test_pinned_source_ignores_stale_bytecode(captured):
    import py_compile
    path,_,factory=captured
    path.write_text("VALUE = 'B'\n")
    py_compile.compile(str(path),doraise=True)
    path.write_text("VALUE = 'A'\n")
    capture=factory()
    module,evidence=_load(capture)
    assert module.VALUE=="A" and evidence.source_state=="CLEAN_COMMIT"


def test_later_local_imports_use_same_frozen_snapshot(captured):
    path,state,factory=captured
    later=path.with_name("wo05c_later.py")
    later.write_text("VALUE='A'\n")
    capture=factory(keep_sources_pinned=True)
    try:
        _,evidence=_load(capture)
        later.write_text("VALUE='B'\n")
        state["revision"]="b"*40
        module=importlib.import_module("kronos.wo05c_later")
        assert module.VALUE=="A"
        assert capture.finish() is evidence and evidence.source_revision=="a"*40
        assert "kronos.wo05c_later" not in dict(evidence.loaded_modules)
    finally:
        if capture in sys.meta_path: sys.meta_path.remove(capture)
        sys.modules.pop("kronos.wo05c_later",None)


def test_unrepresentable_branch_is_not_mislabeled_detached(captured):
    _,state,factory=captured;state["branch"]="feature/@branch"
    _,evidence=_load(factory())
    assert evidence.source_revision=="a"*40
    assert evidence.branch is None and evidence.checkout_mode=="UNAVAILABLE"
    assert runtime_document(create_runtime_manifest(evidence,None,()))["startup_checkout_mode"]=="UNAVAILABLE"


def test_actual_detached_probe_is_distinct_from_unavailable_branch(captured):
    _,state,factory=captured;state["branch"]=None
    _,evidence=_load(factory())
    assert evidence.source_revision=="a"*40 and evidence.checkout_mode=="DETACHED"
