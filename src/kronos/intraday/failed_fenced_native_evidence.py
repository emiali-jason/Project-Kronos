"""Pure native retained-evidence codecs for the fixed R3 owner contracts.

These are the unchanged owner validators, separated from application lifecycle
imports. They do not construct owners, hydrate peers, acquire data or issue
recovery authority. Application producers re-export this same implementation.
"""
from __future__ import annotations
from dataclasses import asdict
from hashlib import sha256
import json
from kronos.intraday.wo09_readiness import artifact_bytes
from kronos.intraday.wo10_futures_contract import Record, encoded
from kronos.intraday.wo11_lifecycle_contract import LifecycleRecord

CLOSED_NATIVE_CONTRACTS = frozenset({
    ("WO09", "KRONOS-INTRADAY-WO-09-READINESS-RECORD-V1"),
    ("WO09", "KRONOS-INTRADAY-WO-09-MACHINE-READINESS-RECORD-V2"),
    ("WO09", "KRONOS-INTRADAY-WO09-EXPERIMENTAL-PAPER-READINESS-V1"),
    ("WO09", "KRONOS-INTRADAY-WO-09-CURRENT-POINTER-V1"),
    ("WO10", "WO10_SPONSOR_COMPARISON_V1"),
    ("WO10", "WO10_CONSTRUCTION_UNAVAILABLE_V1"),
    ("WO10", "WO10_SPONSOR_SELECTION_V1"),
    ("WO11", "WO11_TRACK_V1"),
    ("WO11", "WO11_ACTION_V1"),
    ("WO13", "KRONOS-INTRADAY-WO13-SOURCE-REFERENCE-V1"),
})


RELATIONS = {
    ("WO09", "READINESS"): ("WO09_READINESS_EFFECT", "WO09_READINESS_REFERENCE"),
    ("WO09", "CURRENTNESS"): ("WO09_CURRENTNESS_EFFECT", "WO09_CURRENTNESS_REFERENCE"),
    ("WO10", "COMPARISON"): ("WO10_COMPARISON_EFFECT", "WO10_COMPARISON_REFERENCE"),
    ("WO10", "UNAVAILABLE"): ("WO10_UNAVAILABLE_EFFECT", "WO10_UNAVAILABLE_REFERENCE"),
    ("WO11", "TRACK"): ("WO11_PUBLICATION", "WO11_TRACK_REFERENCE"),
}


def _require(value, code="FAILED_FENCED_NATIVE_OWNER_UNPROVEN"):
    if not value:
        raise ValueError(code)


def source_identity(value):
    _require(type(value) is str and value)
    return {"encoding": "UTF-8", "bytes": value.encode("utf-8").hex()}


def native_bytes(value):
    if isinstance(value, (Record, LifecycleRecord)):
        value.__post_init__()
        return encoded(asdict(value)) + b"\n"
    value.__post_init__()
    return artifact_bytes(value)


def native_contract(value):
    return getattr(value, "schema", None) or value.schema_identity


def native_identity(value):
    if isinstance(value, (Record, LifecycleRecord)):
        return value.identity
    # CURRENTNESS source identities are the exact original subject bytes; its
    # pointer integrity and whole transition are bound separately in the Effect.
    return getattr(value, "readiness_identity", None)


def verify_native_evidence(evidence, raw, context):
    """Fixed source-owned decoding, never caller-selected validator dispatch."""
    owner, contract = evidence["authority"], evidence["contract"]
    _require((owner, contract) in CLOSED_NATIVE_CONTRACTS)
    _require(type(raw) is bytes and sha256(raw).hexdigest() == evidence["hash"]
             and str(len(raw)) == evidence["bytes"])
    data = json.loads(raw)
    if owner == "WO13":
        from datetime import datetime
        _require(set(data) == {"kind", "identity", "received_at"}
            and data["kind"] in {"READINESS", "CURRENTNESS", "COMPARISON", "UNAVAILABLE", "TRACK"}
            and type(data["identity"]) is str and 0 < len(data["identity"]) <= 200)
        at = datetime.fromisoformat(data["received_at"])
        _require(at.tzinfo is not None and at.utcoffset() is not None
            and json.dumps(data, sort_keys=True).encode() == raw
            and context.get("reference_kind") == data["kind"])
        identity, value = data["identity"], data
    elif owner == "WO09":
        from kronos.intraday.wo09_persistence import _readiness, _pointer
        value = _pointer(data) if contract.endswith("CURRENT-POINTER-V1") else _readiness(data)
        _require(artifact_bytes(value) == raw and value.schema_identity == contract)
        identity = (value.canonical_subject_identity if contract.endswith("CURRENT-POINTER-V1")
                    else value.readiness_identity)
    else:
        value = (Record if owner == "WO10" else LifecycleRecord)(**data)
        _require(native_bytes(value) == raw and value.schema == contract)
        identity = value.identity
    expected_identity = context.get("source_identity")
    if isinstance(expected_identity, dict):
        expected_identity = _source_text(expected_identity)
    _require(type(context) is dict and (context.get("owner") == owner or
             context.get("owner") == "WO13" and owner in {"WO09", "WO10", "WO11"})
             and expected_identity == identity
             and context.get("owner_instance")
             and context.get("operation") and context.get("ticket"))
    # The codec/registry verifies actual ticket/instance/inventory continuity;
    # native identity remains exactly the original source bytes, not the Id.
    return {"owner": owner, "contract": contract, "source_identity": identity,
            "value": value}


def _source_text(value):
    _require(type(value) is dict and value.get("encoding") == "UTF-8")
    raw = bytes.fromhex(value["bytes"])
    text = raw.decode("utf-8")
    _require(raw == text.encode("utf-8"))
    return text


def _decode_native(owner, raw):
    data = json.loads(raw)
    if owner == "WO09":
        from kronos.intraday.wo09_persistence import _readiness, _pointer, POINTER_SCHEMA
        value = _pointer(data) if data.get("schema_identity") == POINTER_SCHEMA else _readiness(data)
        _require(artifact_bytes(value) == raw)
    else:
        _require(owner in {"WO10", "WO11"})
        value = (Record if owner == "WO10" else LifecycleRecord)(**data)
        _require(native_bytes(value) == raw)
    return value


def verify_native_peer_registration(payload, registry):
    """Recompute only the finite predicate captured before the original effect."""
    owner, kind, predicate = payload["producer"], payload["source_kind"], payload["predicate"]
    value = _decode_native(owner, registry.store.read_blob(payload["source_input"]))
    identity = _source_text(payload["source_identity"])
    expected_schemas = {("WO10", "SELECTION"): "WO10_SPONSOR_SELECTION_V1",
        ("WO10", "COMPARISON"): "WO10_SPONSOR_COMPARISON_V1",
        ("WO10", "UNAVAILABLE"): "WO10_CONSTRUCTION_UNAVAILABLE_V1",
        ("WO11", "ACTION"): "WO11_ACTION_V1", ("WO11", "TRACK"): "WO11_TRACK_V1"}
    _require(expected_schemas.get((owner, kind)) == value.schema and value.identity == identity)
    peer = payload["peer"]
    if predicate == "OWNER_SLOT_NOT_INSTALLED":
        return
    if predicate == "JOURNAL_UNSUPPORTED_KIND":
        from kronos.intraday.wo14_journal_contract import JOURNAL_SOURCE_KINDS
        _require(peer == "JOURNAL" and kind in {"COMPARISON", "UNAVAILABLE"}
                 and kind not in JOURNAL_SOURCE_KINDS)
    elif predicate == "BOOKS_NO_SOURCE_EDGE":
        _require(peer == "BOOKS" and kind in {"COMPARISON", "UNAVAILABLE"})
    elif predicate == "JOURNAL_TRACK_UNCHANGED":
        _require(peer == "JOURNAL" and kind == "TRACK" and payload["previous_source"] is not None)
        previous = _decode_native("WO11", registry.store.read_blob(payload["previous_source"]))
        _require(previous.schema == "WO11_TRACK_V1" and value.data["predecessor"] == previous.identity
            and all(previous.data[key] == value.data[key]
                    for key in ("state", "entry", "exit", "monitoring")))
    elif predicate == "SELECTION_NO_OUTPUT":
        _require(kind == "SELECTION" and value.data["choice"] != "NONE")
    elif predicate == "ACTION_NO_OUTPUT":
        _require(kind == "ACTION" and value.data["action"] != "DO_NOTHING")
    else:
        _require(predicate == "REQUIRED" and kind in {"SELECTION", "ACTION", "TRACK"})
        _require(not (kind == "SELECTION" and value.data["choice"] != "NONE")
            and not (kind == "ACTION" and value.data["action"] != "DO_NOTHING"))


def verify_native_peer_fulfillment(registration, fulfillment, registry):
    """Validate retained native outputs; never invoke/hydrate either peer."""
    if fulfillment["outcome"] == "FAILED":
        _require(fulfillment["failure"] and not fulfillment["outputs"]
            and fulfillment["invoked_ns"] is not None and fulfillment["returned_ns"] is not None
            and int(fulfillment["invoked_ns"]) <= int(fulfillment["returned_ns"]) <= int(fulfillment["recorded_ns"]))
        return
    _require(not fulfillment["failure"])
    predicate = registration["predicate"]
    if predicate in {"OWNER_SLOT_NOT_INSTALLED", "JOURNAL_TRACK_UNCHANGED",
                     "JOURNAL_UNSUPPORTED_KIND", "BOOKS_NO_SOURCE_EDGE"}:
        _require(fulfillment["outcome"] == "NOT_REQUIRED" and not fulfillment["outputs"]
                 and fulfillment["invoked_ns"] is None and fulfillment["returned_ns"] is None)
        return
    _require(fulfillment["outcome"] == "COMPLETED"
        and int(fulfillment["invoked_ns"]) <= int(fulfillment["returned_ns"])
        <= int(fulfillment["recorded_ns"]))
    if predicate in {"SELECTION_NO_OUTPUT", "ACTION_NO_OUTPUT"}:
        _require(not fulfillment["outputs"])
        return
    _require(predicate == "REQUIRED" and len(fulfillment["outputs"]) == 1)
    output = fulfillment["outputs"][0]
    source = _source_text(registration["source_identity"])
    raw = registry.store.read_blob(output["bytes"])
    if registration["peer"] == "JOURNAL":
        from kronos.intraday.wo14_journal_contract import JournalRevision
        item = JournalRevision(**json.loads(raw))
        item.__post_init__()
        _require(output["adapter"] == "JOURNAL_REVISION_V1"
            and _source_text(output["identity"]) == item.revision_identity
            and source in item.data["source_identities"]
            and output["pointer"] is not None)
        pointer = registry.store.read_blob(output["pointer"])
        expected = {"journal_identity": item.journal_identity,
                    "revision_identity": item.revision_identity}
        _require(pointer == json.dumps(expected, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    else:
        from kronos.intraday.books_factual_contract import FactualRow, factual_row
        _require(output["adapter"] == "BOOKS_FACTUAL_ROW_V1" and output["pointer"] is None)
        row = FactualRow(_source_text(output["identity"]), raw.decode("utf-8"))
        _require(factual_row(**row.data) == row and source in row.data["source_identities"])
        if registration["source_kind"] == "TRACK":
            _require(row.data["observation"]["source_lifecycle_identity"] == source)


def verify_native_owner_result(payload, registry, context):
    """Closed native action checking in addition to core instance/ticket proof."""
    if payload["result"] != "COMPLETE":
        _require(payload["result"] == "FAILED" and payload["reason"] == "UNPROVEN"
                 and not payload["peer_fulfillment"])
        return  # A negative original record confers no recovery authority.
    _require(not payload["notification_failure"] and not payload["durability_unproven"])
    _require(all(payload[field] == "0" for field in
        ("owned_workers", "queued_items", "callbacks", "durable_writes")))
    if payload["purpose"] == "EFFECT":
        inverse = {pair[0]: (owner, kind) for (owner, kind), pair in RELATIONS.items()}
        _require(payload["action"] in inverse and inverse[payload["action"]][0] == payload["owner"]
            and len(payload["targets"]) == 1 and len(payload["after"]) == 1)
        raw = registry.store.read_blob(payload["targets"][0])
        _decode_native(payload["owner"], raw)
        _require(payload["after"] == payload["targets"])
        # Exact effect/input/listener relationships are additionally checked by
        # the common OBLIGATION validator against the actual retained chain.
    elif payload["purpose"] == "REFERENCE":
        allowed = {pair[1] for pair in RELATIONS.values()}
        _require(payload["owner"] == "WO13" and payload["action"] in allowed
            and len(payload["after"]) == 1)
        data = json.loads(registry.store.read_blob(payload["after"][0]))
        relation_kind = {pair[1]: kind for (_, kind), pair in RELATIONS.items()}
        _require(data["kind"] == relation_kind[payload["action"]]
            and set(data) == {"kind", "identity", "received_at"})
    elif payload["purpose"] in {"RECONCILIATION", "CHECKPOINT"}:
        # These are whole-set claims. A fixed source-owned certificate supplied
        # by the common reconciliation engine is mandatory; mere EMPTY or a
        # hand-authored true flag cannot establish absence of missed effects.
        certificate = context.get("reconciliation")
        _require(type(certificate) is dict and certificate.get("owner") == "WO13"
            and certificate.get("operation") == payload["operation"]
            and certificate.get("result_hash") == sha256(json.dumps(payload,
                sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            and certificate.get("accepted_heads") == context.get("accepted_heads")
            and certificate.get("references") == context.get("references"))
    else:
        raise ValueError("FAILED_FENCED_NATIVE_OWNER_UNSUPPORTED_RESULT")
