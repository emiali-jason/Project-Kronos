"""Authenticated synthetic receipt graphs; no operational/owner authority.

Every record uses the actual closed schema and actual RecoveryCodec MAC domain.
Opaque external Evidence represents a separately prevalidated test boundary;
these tests exercise the real cross-record receipt validator without replacing
it, and do not claim a native C launch or independent authority qualification.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from kronos.common import failed_fenced_schema as schema
from kronos.common.failed_fenced_recovery import record_ref
from kronos.common.failed_fenced_startup import _validate_child_receipts
from tests.unit.common.test_failed_fenced_recovery import codec, PROCESS, CLOCK, evidence

SECOND=1_000_000_000
ORIGIN=SECOND; STOP=16*SECOND; FORK=9*SECOND; READY=FORK+120*SECOND
PARENT=dict(PROCESS,runtime="synthetic-parent")
CHILD=dict(PROCESS,pid=str(int(PROCESS["pid"])+1),runtime="synthetic-child")
CHECKPOINT=dict(state="EMPTY",pending="0",digest="c"*64,evidence=evidence("checkpoint"))
LIMITS=dict(clock=CLOCK,origin_ns=str(ORIGIN),stop_deadline_ns=str(STOP))


def _example(node):
    kind,rule=node
    if kind=="object":return {name:_example(value) for name,value in rule.items()}
    if kind=="array":return []
    if kind=="nullable":return None
    if kind=="union":return _example(rule[0])
    if kind=="tuple":return [_example(value) for value in rule]
    if kind=="literal":return rule
    if rule=="Process":return deepcopy(PROCESS)
    if rule=="Clock":return deepcopy(CLOCK)
    if rule=="Evidence":return evidence()
    if rule=="Endpoint":return dict(host="127.0.0.1",port="12345",configuration=evidence("endpoint"))
    if rule=="Checkpoint":return deepcopy(CHECKPOINT)
    if rule=="Limits":return deepcopy(LIMITS)
    if rule=="Ref":return dict(kind="CUSTODY",hash="0"*64)
    if rule in schema.TYPE_SCHEMAS:return _example(schema._parse(schema.TYPE_SCHEMAS[rule]))
    if rule in schema.SCALAR_ENUMS:return sorted(schema.SCALAR_ENUMS[rule])[0]
    return {"Id":"synthetic","Hash":"a"*64,"Revision":"a"*40,"U64":"1","Ns":"1","Count":"0","Bool":True,"HexBytes":"00"}[rule]


def graph(changes=None):
    """Create actual schema-valid MAC records with explicit event relationships."""
    changes={} if changes is None else changes
    chain={}; encoder=codec()
    def emit(kind,issued=5*SECOND,**fields):
        payload=_example(schema._parse(schema.RECORD_SCHEMAS[kind]));payload.update(fields)
        patch=deepcopy(changes.get(kind,{})); issued=patch.pop("__issued_ns__",issued); payload.update(patch)
        if kind=="ACK":payload["ack_ns"]=str(issued)
        if kind=="COMPOSITION_AUTHORITY":issued=int(payload["gate_ns"])
        raw=encoder.encode(kind,payload,schema.RECORD_ROLES[kind][0],issued)
        chain[kind]=encoder.decode(raw,kind);chain[kind+"_RAW"]=raw
        return record_ref(raw)
    original=emit("ORIGINAL"); terminal=emit("TERMINAL",original=original)
    guard=emit("GUARD")
    claim=emit("CLAIM",guard=guard,launcher=PARENT,limits=LIMITS)
    accepted=emit("CLAIM_ACCEPTED",claim=claim)
    seal=emit("SEAL",claim=claim,accepted=accepted,product_owners="0",accepted_owners="0",commit_owners="1",checkpoint=CHECKPOINT)
    owner=emit("OWNER_PROOF",claim=claim,seal=seal,product_owners="0",accepted_owners="0",commit_owners="1",checkpoint=CHECKPOINT)
    certificate=emit("CERTIFICATE",claim=claim,accepted=accepted,seal=seal,owner_proof=owner)
    prepared=emit("PREPARED_COMMIT",seal=seal,owner_proof=owner,certificate=certificate,product_owners="0",accepted_owners="0",commit_owners="1")
    ack=emit("ACK",claim=claim,seal=seal,owner_proof=owner,certificate=certificate,prepared=prepared,
        publication_complete_ns=str(2*SECOND),released_ns=str(3*SECOND),ack_ns=str(4*SECOND),
        work_deadline_ns=str(11*SECOND),stop_deadline_ns=str(STOP),recovery_owners="0")
    observation=emit("OBSERVATION",6*SECOND,claim=claim,ack=ack,ack_bytes=chain["ACK_RAW"].hex(),launcher=PARENT,
        received_ns=str(5*SECOND),verified_ns=str(6*SECOND),limits=LIMITS)
    exited=emit("EXIT_PROOF",7*SECOND,observation=observation,limits=LIMITS)
    intent=emit("CHILD_INTENT",8*SECOND,claim=claim,observation=observation,exit_proof=exited,
        child_nonce="b"*64,checkpoint=CHECKPOINT,limits=LIMITS,execution_owner="launcher-owner",bootstrap_owner="bootstrap-owner")
    identity=emit("CHILD_IDENTITY",10*SECOND,intent=intent,child=CHILD,parent=PARENT,
        child_nonce=chain["CHILD_INTENT"]["payload"]["child_nonce"],bootstrap=evidence("actual-bootstrap"),observed_ns=str(10*SECOND))
    started=emit("CHILD_STARTED",11*SECOND,intent=intent,child_identity=identity,child=CHILD,parent=PARENT,
        child_nonce=chain["CHILD_INTENT"]["payload"]["child_nonce"],fork_enter_ns=str(FORK),
        fork_return_ns=str(FORK+SECOND//2),ready_deadline_ns=str(READY))
    grant=emit("COMPOSITION_AUTHORITY",12*SECOND,claim=claim,intent=intent,child_started=started,
        parent=PARENT,controller_capability=chain["CLAIM"]["payload"]["launcher_capability"],child=CHILD,
        child_nonce=chain["CHILD_INTENT"]["payload"]["child_nonce"],child_started_durable_ns=str(11*SECOND+SECOND//5),
        identity_verified_ns=str(11*SECOND+SECOND//10),gate_ns=str(12*SECOND),stop_deadline_ns=str(STOP),ready_deadline_ns=str(READY))
    consumed=emit("CONSUMPTION",50*SECOND,guard=guard,claim=claim,accepted=accepted,seal=seal,owner_proof=owner,
        certificate=certificate,prepared=prepared,ack=ack,observation=observation,exit_proof=exited,intent=intent,
        child_started=started,composition_authority=grant,authority_bytes=chain["COMPOSITION_AUTHORITY_RAW"].hex(),
        authority_received_ns=str(13*SECOND),authority_verified_ns=str(14*SECOND),consumer=CHILD,
        child_nonce=chain["CHILD_INTENT"]["payload"]["child_nonce"],checkpoint=CHECKPOINT,consumed_ns=str(50*SECOND),
        ready_deadline_ns=str(READY),source=chain["CHILD_IDENTITY"]["payload"]["bootstrap"],
        capability=chain["CHILD_IDENTITY"]["payload"]["bootstrap"],execution_owner="bootstrap-owner")
    startup=emit("STARTUP_CONTEXT",51*SECOND,original=original,terminal=terminal,consumption=consumed,
        child_started=started,runtime=CHILD,checkpoint=CHECKPOINT,ready_deadline_ns=str(READY))
    emit("READY_RECEIPT",READY-SECOND//2,guard=guard,intent=intent,child_started=started,consumption=consumed,
        startup=startup,runtime=CHILD,ready_ns=str(READY-SECOND),execution_owner="launcher-owner")
    return chain


def validate(chain,*,historical=False,now=READY-1):
    return _validate_child_receipts(chain,historical=historical,
        budget=None if historical else SimpleNamespace(now_ns=lambda:now))


def test_exact_records_allow_ready_after_45_seconds_but_before_fork_plus120():
    chain=graph()
    assert validate(chain)==50*SECOND
    assert int(chain["READY_RECEIPT"]["payload"]["ready_ns"])-int(chain["OWNER_PROOF"]["issued_ns"])>45*SECOND
    assert chain["COMPOSITION_AUTHORITY"]["payload"]["gate_ns"]<chain["CLAIM"]["payload"]["limits"]["stop_deadline_ns"]


@pytest.mark.parametrize("kind,patch",[
    ("CHILD_IDENTITY",dict(child_nonce="f"*64)),
    ("CHILD_IDENTITY",dict(child=dict(CHILD,runtime="foreign-child"))),
    ("CHILD_IDENTITY",dict(parent=dict(PARENT,runtime="foreign-parent"))),
    ("CHILD_STARTED",dict(child_nonce="f"*64)),
    ("CHILD_STARTED",dict(parent=dict(PARENT,runtime="foreign-parent"))),
    ("CHILD_STARTED",dict(fork_return_ns=str(STOP))),
    ("COMPOSITION_AUTHORITY",dict(child_nonce="f"*64)),
    ("COMPOSITION_AUTHORITY",dict(child=dict(CHILD,runtime="foreign-child"))),
    ("COMPOSITION_AUTHORITY",dict(controller_capability=evidence("foreign-capability"))),
    ("COMPOSITION_AUTHORITY",dict(gate_ns=str(STOP),stop_deadline_ns=str(STOP+SECOND))),
    ("COMPOSITION_AUTHORITY",dict(identity_verified_ns=str(8*SECOND))),
    ("CONSUMPTION",dict(authority_bytes="00")),
    ("CONSUMPTION",dict(consumer=dict(CHILD,runtime="foreign-child"))),
    ("CONSUMPTION",dict(child_nonce="f"*64)),
    ("CONSUMPTION",dict(source=evidence("foreign-source"))),
    ("CONSUMPTION",dict(capability=evidence("foreign-capability"))),
    ("CONSUMPTION",dict(checkpoint=dict(CHECKPOINT,digest="f"*64))),
    ("CONSUMPTION",dict(execution_owner="foreign-owner")),
    ("CONSUMPTION",dict(authority_received_ns=str(11*SECOND))),
    ("CONSUMPTION",dict(authority_verified_ns=str(STOP))),
    ("CONSUMPTION",dict(consumed_ns=str(13*SECOND))),
    ("CONSUMPTION",dict(consumed_ns=str(READY))),
    ("STARTUP_CONTEXT",dict(runtime=dict(CHILD,runtime="foreign-child"))),
    ("STARTUP_CONTEXT",dict(checkpoint=dict(CHECKPOINT,digest="f"*64))),
    ("STARTUP_CONTEXT",dict(__issued_ns__=49*SECOND)),
    ("READY_RECEIPT",dict(runtime=dict(CHILD,runtime="foreign-child"))),
    ("READY_RECEIPT",dict(execution_owner="foreign-owner")),
    ("READY_RECEIPT",dict(ready_ns=str(50*SECOND))),
    ("READY_RECEIPT",dict(ready_ns=str(READY))),
    ("READY_RECEIPT",dict(__issued_ns__=READY)),
])
def test_authenticated_but_inconsistent_receipts_are_rejected(kind,patch):
    with pytest.raises(ValueError,match="RECOVERY_"): validate(graph({kind:patch}))


@pytest.mark.parametrize("field,kind",[
    ("guard","GUARD"),("claim","CLAIM"),("accepted","CLAIM_ACCEPTED"),("seal","SEAL"),
    ("owner_proof","OWNER_PROOF"),("certificate","CERTIFICATE"),("prepared","PREPARED_COMMIT"),
    ("ack","ACK"),("observation","OBSERVATION"),("exit_proof","EXIT_PROOF"),("intent","CHILD_INTENT"),
    ("child_started","CHILD_STARTED"),("composition_authority","COMPOSITION_AUTHORITY"),
])
def test_each_consumption_reference_must_match_exact_authenticated_record(field,kind):
    with pytest.raises(ValueError,match="RECOVERY_"): validate(graph({"CONSUMPTION":{field:dict(kind=kind,hash="f"*64)}}))


@pytest.mark.parametrize("kind",["OWNER_PROOF","CERTIFICATE","PREPARED_COMMIT","ACK","OBSERVATION"])
def test_freshness_is_checked_at_actual_consumption_including_historical_replay(kind):
    # Exactly45 seconds is accepted; +1ns is not, independently for each proof.
    chain=graph({kind:{"__issued_ns__":5*SECOND-1}})
    with pytest.raises(ValueError,match="CONSUMPTION_PROOF_EXPIRED"): validate(chain)
    with pytest.raises(ValueError,match="CONSUMPTION_PROOF_EXPIRED"): validate(chain,historical=True)


def test_resolved_history_checks_original_times_without_current_clock_authority():
    assert validate(graph(),historical=True)==50*SECOND
    with pytest.raises(ValueError,match="READY_OBSERVATION_DEADLINE"):
        validate(graph(),now=READY)


@pytest.mark.parametrize("missing,code",[("CHILD_STARTED","CHILD_STARTED_REQUIRED"),
    ("COMPOSITION_AUTHORITY","LIVE_AUTHORITY_REQUIRED"),("CONSUMPTION","CONSUMPTION_REQUIRED")])
def test_later_receipts_never_replace_missing_live_gate(missing,code):
    chain=graph();chain.pop(missing);chain.pop(missing+"_RAW")
    with pytest.raises(ValueError,match=code):validate(chain)


def test_started_child_without_later_grant_is_not_consumed_or_ready():
    chain=graph()
    for kind in ("COMPOSITION_AUTHORITY","CONSUMPTION","STARTUP_CONTEXT","READY_RECEIPT"):
        chain.pop(kind);chain.pop(kind+"_RAW")
    assert validate(chain) is None


# Existing native Browser tuple rules, now also usable by the keyless helper.
_RESTORATION_OUTCOMES = tuple((owner, "SUCCESS") for owner in
    ("LEGACY_MTF", "LEGACY_NATIVE", "NATIVE_REVIEW", "V3_RECORDS", "V3_RESTORE", "TRADE_WINDOW"))


@pytest.mark.parametrize("change", [None, "LEGACY_MTF", "LEGACY_NATIVE", "NATIVE_REVIEW", "V3_RESTORE", "review-unestablished"])
def test_pure_restoration_keeps_native_accepted_outcomes(change):
    from kronos.common.runtime_restoration import _swing_restoration_failure
    outcomes = _RESTORATION_OUTCOMES
    if change:
        owner = "NATIVE_REVIEW" if change == "review-unestablished" else change
        value = "APPLICABILITY_NOT_ESTABLISHED" if change == "review-unestablished" else "NOT_APPLICABLE"
        outcomes = tuple((key, value if key == owner else state) for key, state in outcomes)
    assert _swing_restoration_failure(outcomes) is False


@pytest.mark.parametrize("fault", ["none", "list", "row-list", "short", "duplicate", "unknown", "failed", "required-records", "required-window", "unestablished-wrong-owner"])
def test_pure_restoration_keeps_native_rejected_outcomes(fault):
    from kronos.common.runtime_restoration import _swing_restoration_failure
    outcomes = _RESTORATION_OUTCOMES
    if fault == "none": outcomes = None
    elif fault == "list": outcomes = list(outcomes)
    elif fault == "row-list": outcomes = (list(outcomes[0]),) + outcomes[1:]
    elif fault == "short": outcomes = outcomes[:-1]
    elif fault == "duplicate": outcomes = (outcomes[1],) + outcomes[1:]
    elif fault == "unknown": outcomes = (("UNKNOWN", "SUCCESS"),) + outcomes[1:]
    elif fault == "failed": outcomes = ((outcomes[0][0], "FAILED"),) + outcomes[1:]
    else:
        owner = {"required-records": "V3_RECORDS", "required-window": "TRADE_WINDOW", "unestablished-wrong-owner": "LEGACY_MTF"}[fault]
        value = "APPLICABILITY_NOT_ESTABLISHED" if fault == "unestablished-wrong-owner" else "NOT_APPLICABLE"
        outcomes = tuple((key, value if key == owner else state) for key, state in outcomes)
    assert _swing_restoration_failure(outcomes) is True


def test_pure_restoration_body_matches_retained_native_ast_and_browser_reexports():
    import ast
    from pathlib import Path
    import kronos.common.runtime_restoration as pure
    from kronos.browser.runtime_state import _swing_restoration_failure as native
    assert native is pure._swing_restoration_failure
    node = next(item for item in ast.parse(Path(pure.__file__).read_text()).body
        if isinstance(item, ast.FunctionDef) and item.name == "_swing_restoration_failure")
    # Exact original source captured before extraction. Parse both with this
    # interpreter: Python-version AST dump formatting is not a semantic change.
    original_source = 'def _swing_restoration_failure(outcomes):\n    required = {"LEGACY_MTF", "LEGACY_NATIVE", "NATIVE_REVIEW", "V3_RECORDS",\n                "V3_RESTORE", "TRADE_WINDOW"}\n    if (type(outcomes) is not tuple or len(outcomes) != len(required)\n            or any(type(row) is not tuple or len(row) != 2 for row in outcomes)):\n        return True\n    result = dict(outcomes)\n    return (set(result) != required\n            or any(value not in ({"SUCCESS", "NOT_APPLICABLE", "APPLICABILITY_NOT_ESTABLISHED"}\n                                 if key == "NATIVE_REVIEW" else {"SUCCESS", "NOT_APPLICABLE"})\n                   for key, value in result.items())\n            or result["V3_RECORDS"] != "SUCCESS"\n            or result["TRADE_WINDOW"] != "SUCCESS")'
    original_node = ast.parse(original_source).body[0]
    assert ast.dump(node, include_attributes=False) == ast.dump(original_node, include_attributes=False)


def test_pure_restoration_imports_in_isolated_helper_without_product_packages():
    from pathlib import Path
    import subprocess
    import sys
    source = Path(__file__).resolve().parents[3] / "src"
    script = """import sys, importlib.abc
sys.path.insert(0, sys.argv[1])
class DenyProduct(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'pypdf' or fullname.startswith(('pypdf.', 'kronos.application', 'kronos.browser')):
            raise AssertionError('helper imported product package: ' + fullname)
sys.meta_path.insert(0, DenyProduct())
from kronos.common.runtime_restoration import _swing_restoration_failure
assert _swing_restoration_failure(None) is True
assert not any(name.startswith(('kronos.application', 'kronos.browser', 'pypdf')) for name in sys.modules)
"""
    result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", script, str(source)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
