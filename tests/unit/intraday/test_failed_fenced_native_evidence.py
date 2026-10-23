"""Pure retained-evidence validation; synthetic fixtures confer no authority."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from kronos.intraday.failed_fenced_native_evidence import (
    native_bytes, source_identity, verify_native_evidence,
    verify_native_peer_registration, verify_native_peer_fulfillment,
)


ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("owner_module,owner_name,pure_module,pure_name", [
    ("kronos.application.intraday_live_shadow", "IntradayLiveShadowService._validate_acceptance_proof",
     "kronos.intraday.live_shadow_acceptance", "validate_acceptance_proof"),
    ("kronos.application.intraday_shadow_history", "validate_historical_relation",
     "kronos.intraday.live_shadow_history_checks", "validate_historical_relation"),
    ("kronos.application.intraday_shadow_history", "historical_compatible",
     "kronos.intraday.live_shadow_history_checks", "historical_compatible"),
])
def test_pure_native_checks_match_unchanged_application_predicates(
        owner_module, owner_name, pure_module, pure_name):
    import ast
    import importlib
    import inspect
    import textwrap

    def predicate(module_name, qualified_name):
        value = importlib.import_module(module_name)
        for part in qualified_name.split("."):
            value = getattr(value, part)
        node = ast.parse(textwrap.dedent(inspect.getsource(value))).body[0]
        node.name = "same_predicate"
        node.decorator_list = []
        if isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
            node.body = node.body[1:]
        return ast.dump(node, include_attributes=False)

    assert predicate(owner_module, owner_name) == predicate(pure_module, pure_name)
    if pure_name == "validate_acceptance_proof":
        assert importlib.import_module(owner_module).REQUIRED == importlib.import_module(pure_module).REQUIRED


class RetainedBytes:
    """Read-only test blob transport, not an owner approval or registry."""
    def __init__(self):
        self.values = {}

    def retain(self, raw):
        ref = {"identity": "synthetic-retained-" + sha256(raw).hexdigest(),
               "hash": sha256(raw).hexdigest(), "bytes": str(len(raw))}
        self.values[ref["hash"]] = raw
        return ref

    def read_blob(self, ref):
        raw = self.values[ref["hash"]]
        assert sha256(raw).hexdigest() == ref["hash"] and len(raw) == int(ref["bytes"])
        return raw


def actual_peer_output(tmp_path, peer):
    from tests.unit.intraday.test_wo14_journal import build
    from kronos.application.intraday_books import IntradayBooks
    from kronos.intraday.wo11_lifecycle_contract import record
    journal, futures, lifecycle, _, _, current = build(tmp_path)
    # The existing Journal projection fixture uses lightweight Facts. Retain
    # its same governed payload in the real immutable lifecycle codec before
    # exercising a recovery validator that correctly requires that codec.
    data = deepcopy(current.data)
    data["terminal_status"] = "CLOSED"
    data["exit"]["reason"] = data["exit_reason"]
    current = record("WO11_TRACK_V1", **data)
    lifecycle.store.values[current.identity] = current
    owner = journal if peer == "JOURNAL" else IntradayBooks(
        research=journal.research, futures=futures, lifecycle=lifecycle)
    output, = owner.consume_source("TRACK", current.identity)
    native = RetainedBytes()
    registration = {"producer": "WO11", "source_kind": "TRACK", "predicate": "REQUIRED",
        "source_identity": source_identity(current.identity),
        "source_input": native.retain(native_bytes(current)), "previous_source": None, "peer": peer}
    retained = dict(output, identity=source_identity(output["identity"]),
        bytes=native.retain(output["bytes"]),
        pointer=None if output["pointer"] is None else native.retain(output["pointer"]))
    fulfillment = {"outcome": "COMPLETED", "failure": False, "invoked_ns": "10",
        "returned_ns": "11", "recorded_ns": "12", "outputs": [retained]}
    return native, registration, fulfillment


def test_application_reexports_exact_pure_implementations_and_journal_constant():
    from kronos.application import failed_fenced_owners as application
    from kronos.intraday import failed_fenced_native_evidence as pure
    from kronos.application import intraday_books as books
    from kronos.intraday import books_factual_contract as facts
    from kronos.application.intraday_journal import IntradaySourceAdapter
    from kronos.intraday.wo14_journal_contract import JOURNAL_SOURCE_KINDS
    for name in ("CLOSED_NATIVE_CONTRACTS", "RELATIONS", "_require", "source_identity",
            "native_bytes", "native_contract", "native_identity", "verify_native_evidence",
            "_source_text", "_decode_native", "verify_native_peer_registration",
            "verify_native_peer_fulfillment", "verify_native_owner_result"):
        assert getattr(application, name) is getattr(pure, name)
    assert books.FactualRow is facts.FactualRow and books.factual_row is facts.factual_row
    assert IntradaySourceAdapter.SOURCE_KINDS is JOURNAL_SOURCE_KINDS
    assert JOURNAL_SOURCE_KINDS == frozenset({"SELECTION", "ACTION", "TRACK"})


@pytest.mark.parametrize("peer", ["JOURNAL", "BOOKS"])
def test_actual_retained_native_peer_output_in_fresh_application_blocked_interpreter(tmp_path, peer):
    native, registration, fulfillment = actual_peer_output(tmp_path, peer)
    payload = {"registration": registration, "fulfillment": fulfillment,
               "blobs": {key: raw.hex() for key, raw in native.values.items()}}
    script = r'''
import sys, importlib.abc, json, hashlib
class DenyApplicationAndPdf(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "kronos.application" or fullname.startswith("kronos.application.") or fullname == "pypdf" or fullname.startswith("pypdf."):
            raise AssertionError("NATIVE_HELPER_APPLICATION_IMPORT_FORBIDDEN:" + fullname)
sys.meta_path.insert(0, DenyApplicationAndPdf())
sys.path.insert(0, sys.argv[1])
from kronos.intraday.failed_fenced_native_evidence import verify_native_peer_registration, verify_native_peer_fulfillment
data=json.loads(sys.stdin.read())
class ReadOnly:
    def read_blob(self, ref):
        raw=bytes.fromhex(data["blobs"][ref["hash"]])
        assert hashlib.sha256(raw).hexdigest()==ref["hash"] and len(raw)==int(ref["bytes"])
        return raw
class Registry:
    store=ReadOnly()
verify_native_peer_registration(data["registration"], Registry())
verify_native_peer_fulfillment(data["registration"], data["fulfillment"], Registry())
assert not any(name=="kronos.application" or name.startswith("kronos.application.") or name=="pypdf" or name.startswith("pypdf.") for name in sys.modules)
print("ACTUAL_NATIVE_RETAINED_PEER_VALIDATED_WITHOUT_APPLICATION_OR_PDF")
'''
    result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(ROOT / "src")],
        input=json.dumps(payload).encode(), capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == b"ACTUAL_NATIVE_RETAINED_PEER_VALIDATED_WITHOUT_APPLICATION_OR_PDF\n"


@pytest.mark.parametrize("peer", ["JOURNAL", "BOOKS"])
@pytest.mark.parametrize("tamper", ["source_identity", "output_identity", "output_bytes", "predicate"])
def test_rehashed_or_rebound_native_peer_output_still_rejected(tmp_path, peer, tamper):
    native, registration, fulfillment = actual_peer_output(tmp_path, peer)
    registry = SimpleNamespace(store=native)
    verify_native_peer_registration(registration, registry)
    verify_native_peer_fulfillment(registration, fulfillment, registry)
    bad_registration, bad_output = deepcopy(registration), deepcopy(fulfillment)
    if tamper == "source_identity":
        bad_registration["source_identity"] = source_identity("SYNTHETIC-OTHER-SOURCE")
    elif tamper == "output_identity":
        bad_output["outputs"][0]["identity"] = source_identity("SYNTHETIC-OTHER-OUTPUT")
    elif tamper == "output_bytes":
        raw = native.read_blob(bad_output["outputs"][0]["bytes"])
        decoded = json.loads(raw)
        if peer == "JOURNAL":
            decoded["revision_identity"] = "SYNTHETIC-REHASHED-OTHER-REVISION"
        else:
            decoded["opportunity_identity"] = "SYNTHETIC-REHASHED-OTHER-ORIGIN"
        bad_output["outputs"][0]["bytes"] = native.retain(json.dumps(decoded, sort_keys=True).encode())
    else:
        bad_registration["predicate"] = "BOOKS_NO_SOURCE_EDGE"
    with pytest.raises((ValueError, KeyError, TypeError)):
        verify_native_peer_registration(bad_registration, registry)
        verify_native_peer_fulfillment(bad_registration, bad_output, registry)


def test_native_wo11_input_codec_keeps_exact_source_identity_binding(tmp_path):
    native, registration, _ = actual_peer_output(tmp_path, "JOURNAL")
    source = registration["source_input"]
    raw = native.read_blob(source)
    evidence = {**source, "authority": "WO11", "contract": "WO11_TRACK_V1"}
    context = {"owner": "WO11", "owner_instance": "synthetic-real-codec-instance",
               "source_identity": registration["source_identity"],
               "operation": "synthetic-original", "ticket": "synthetic-ticket"}
    assert verify_native_evidence(evidence, raw, context)["source_identity"] == \
        bytes.fromhex(registration["source_identity"]["bytes"]).decode()
    with pytest.raises(ValueError):
        verify_native_evidence(evidence, raw, {**context, "source_identity": "SYNTHETIC-OTHER"})


@pytest.mark.parametrize("kind", ["READINESS", "CURRENTNESS"])
def test_actual_wo09_codec_in_fresh_application_blocked_interpreter(kind):
    from tests.unit.intraday.test_wo09_readiness import evaluated, NOW
    from kronos.intraday.wo09_persistence import create_pointer
    from kronos.intraday.wo09_readiness import CurrentnessState
    assessment, _ = evaluated()
    value = assessment if kind == "READINESS" else create_pointer(
        assessment, currentness=CurrentnessState.CURRENT, superseded=None, updated_at=NOW)
    raw = native_bytes(value)
    identity = value.readiness_identity if kind == "READINESS" else value.canonical_subject_identity
    evidence = {"authority": "WO09", "contract": value.schema_identity,
        "identity": "synthetic-retained-" + sha256(raw).hexdigest(),
        "hash": sha256(raw).hexdigest(), "bytes": str(len(raw))}
    context = {"owner": "WO09", "owner_instance": "synthetic-actual-codec-instance",
        "source_identity": source_identity(identity), "operation": "synthetic-original",
        "ticket": "synthetic-issued-at-test-boundary"}
    payload = {"evidence": evidence, "context": context, "raw": raw.hex()}
    script = r'''
import sys, importlib.abc, json
class DenyApplicationAndPdf(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "kronos.application" or fullname.startswith("kronos.application.") or fullname == "pypdf" or fullname.startswith("pypdf."):
            raise AssertionError("NATIVE_HELPER_APPLICATION_IMPORT_FORBIDDEN:" + fullname)
sys.meta_path.insert(0, DenyApplicationAndPdf())
sys.path.insert(0, sys.argv[1])
from kronos.intraday.failed_fenced_native_evidence import verify_native_evidence, _decode_native
data=json.loads(sys.stdin.read())
raw=bytes.fromhex(data["raw"])
result=verify_native_evidence(data["evidence"], raw, data["context"])
assert result["source_identity"] == bytes.fromhex(data["context"]["source_identity"]["bytes"]).decode()
assert _decode_native("WO09", raw) == result["value"]
try:
    verify_native_evidence(data["evidence"], raw, dict(data["context"], source_identity="SYNTHETIC-OTHER"))
except ValueError:
    pass
else:
    raise AssertionError("REBOUND_NATIVE_IDENTITY_ACCEPTED")
assert not any(name=="kronos.application" or name.startswith("kronos.application.") or name=="pypdf" or name.startswith("pypdf.") for name in sys.modules)
print("ACTUAL_WO09_CODEC_VALIDATED_WITHOUT_APPLICATION_OR_PDF")
'''
    result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(ROOT / "src")],
        input=json.dumps(payload).encode(), capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == b"ACTUAL_WO09_CODEC_VALIDATED_WITHOUT_APPLICATION_OR_PDF\n"
