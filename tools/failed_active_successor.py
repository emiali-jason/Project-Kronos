"""Read-only exact successor verification for the authorized recovery launcher.

No Browser construction, remote calls, restoration, enrollment or mutations.
The launcher supplies documents read from its child and an already hash-bound
approved relation. This check confers no authority on an arbitrary relation.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _json(raw):
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def read_private(path, *, private=False):
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("unsafe path")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or private and info.st_mode & 0o077 or not 0 < info.st_size <= 262144):
            raise ValueError("unsafe record")
        raw = source.read(262145)
    if len(raw) != info.st_size:
        raise ValueError("record changed")
    return raw


def verify_documents(documents, relation, *, pid, revision, generation, capability):
    from kronos.intraday.live_shadow_epochs import capabilities, validate
    from kronos.intraday.live_shadow_transition import capability_identity
    validate(relation)
    if relation["kind"] != "successor_compatibility":
        raise ValueError("wrong relation")
    body = relation["body"]
    runtime, status, intraday = documents
    maintenance = {"protocol": "KRONOS_MAINTENANCE_HANDOFF_V1", "state": "INACTIVE",
        "active": False, "generation": generation, "startup": "READY", "failure": None}
    if (runtime["schema"] != "KRONOS-RUNTIME-STATE/1.0.0"
            or runtime["process"] != {"pid": pid, "revision": revision, "source_state": "CLEAN_COMMIT"}
            or runtime["maintenance"] != maintenance or status["maintenance"] != maintenance
            or status["service"] != "KRONOS_BROWSER_V1" or status["runtime_ready"] is not True
            or status["provider"] != "DISCONNECTED"
            or runtime["rest_authentication"] != "DISCONNECTED"
            or runtime["rest_capability"] != "ABSENT" or runtime["connection_attempt"] is not None
            or intraday["active_operation_identity"] is not None or intraday["current_failure"] is not None):
        raise ValueError("successor binding")
    provider = runtime["provider_runtime"]
    if (provider["capability_state"] != "ABSENT" or provider["cleanup_state"] != "COMPLETE"
            or any(type(provider[name]) is not int or provider[name] != 0 for name in
                   ("owned_work_count", "retained_lease_count", "unresolved_cleanup_count"))):
        raise ValueError("provider authority")
    shadow = intraday["live_shadow"]
    if (shadow["runtime_accepted"] is not True or shadow["enabled"] is not True
            or shadow["acceptance_disposition"] != "EXISTING_ACCEPTANCE_RESTORED"
            or shadow["acceptance_identity"] != body["acceptance"]
            or shadow["current_epoch"] != body["epoch"]
            or shadow["window"] != {"identity": body["window"], "start": body["start"], "end": body["end"]}
            or any(shadow[name] is not None for name in ("failure", "epoch_failure", "publication_hook_failure"))):
        raise ValueError("restoration binding")
    proof = shadow["runtime_proof"]
    mapped = capabilities(proof)
    if (type(proof["pid"]) is not int or proof["pid"] != pid or proof["revision"] != revision
            or proof["source_state"] != "CLEAN_COMMIT"
            or capability_identity(proof) != capability or body["target_aggregate"] != capability
            or proof["configuration"] != body["configuration"]
            or [asdict(mapped[name]) for name in sorted(mapped)] != body["target_capabilities"]
            or any(row["disposition"] != "APPROVED" for row in body["owner_approvals"])):
        raise ValueError("capability binding")


def main(argv=None):
    parser = argparse.ArgumentParser()
    for name in ("relation", "relation-sha256", "capability", "revision", "generation", "maintenance-root", "evidence-root"):
        parser.add_argument("--" + name, required=True)
    for name in ("pid", "parent-pid", "valid-from-us", "valid-until-us"):
        parser.add_argument("--" + name, required=True, type=int)
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(196609)
        if len(raw) > 196608:
            raise ValueError("documents too large")
        relation_raw = read_private(args.relation)
        if hashlib.sha256(relation_raw).hexdigest() != args.relation_sha256:
            raise ValueError("relation changed")
        relation = _json(relation_raw)
        documents = _json(raw)
        verify_documents(documents, relation, pid=args.pid, revision=args.revision,
            generation=args.generation, capability=args.capability)
        claim = _json(read_private(Path(args.maintenance_root) / (args.generation + ".consumed.json"), private=True))
        if (set(claim) != {"schema", "generation", "parent_pid", "process_id", "runtime_identity", "accepted_at"}
                or claim["schema"] != "KRONOS_MAINTENANCE_CONSUMPTION_V2"
                or claim["generation"] != args.generation or claim["process_id"] != args.pid
                or claim["parent_pid"] != args.parent_pid
                or not re.fullmatch(r"[a-f0-9]{64}", claim["runtime_identity"])):
            raise ValueError("handoff consumption")
        receipt = _json(read_private(Path(args.evidence_root) / "shared/provider-connection-v1/maintenance" /
            (claim["runtime_identity"] + "-startup.json"), private=True))
        if (set(receipt) != {"schema", "runtime_identity", "maintenance_identity", "at", "trigger"}
                or receipt["schema"] != "RUNTIME_STARTUP_MAINTENANCE_EXIT_V1"
                or receipt["runtime_identity"] != claim["runtime_identity"]
                or receipt["maintenance_identity"] != args.generation
                or receipt["trigger"] != "VERIFIED_CANONICAL_STARTUP"):
            raise ValueError("startup receipt")
        now = datetime.now(timezone.utc)
        delta = now - datetime(1970, 1, 1, tzinfo=timezone.utc)
        now_us = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
        body = relation["body"]
        if not (args.valid_from_us <= now_us < args.valid_until_us
                and datetime.fromisoformat(body["start"]) <= now < datetime.fromisoformat(body["end"])
                and datetime.fromisoformat(documents[2]["live_shadow"]["runtime_proof"]["startup"])
                <= datetime.fromisoformat(claim["accepted_at"])
                <= datetime.fromisoformat(receipt["at"]) <= now):
            raise ValueError("expired")
    except Exception:
        print("KRONOS_RECOVERY_SUCCESSOR_V1 INVALID")
        return 2
    print("KRONOS_RECOVERY_SUCCESSOR_V1 VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
