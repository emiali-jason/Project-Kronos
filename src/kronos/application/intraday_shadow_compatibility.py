"""Maintenance-only restoration of one already-governed compatible WO-06H epoch."""

from hashlib import sha256
import os
import re

from kronos.application.intraday_shadow_epochs import restore_epoch
from kronos.intraday.live_shadow import ShadowError
from kronos.intraday.live_shadow_epoch_capability import CAPABILITY_IDENTITY
from kronos.intraday.live_shadow_epochs import capabilities
from kronos.intraday.live_shadow_transition import capability_identity, validate_equivalence
from kronos.intraday.population_measurement import canonical, identity


POLICY = "KRONOS-WO06H-SAME-EPOCH-COMPATIBILITY-RESTORATION/1.0.0"
ROUTE = "/control/intraday-live-shadow/compatibility-restoration/v1"
ACTION = "RESTORE_SAME_EPOCH_COMPATIBILITY"
FIELDS = {
    "policy",
    "action",
    "epoch_identity",
    "acceptance_identity",
    "window_identity",
    "current_runtime_proof",
    "current_capability_proof",
    "compatibility_identity",
    "sponsor_authorization",
    "request_identity",
    "integrity",
}
IDENTITIES = {
    "epoch_identity": re.compile(r"WO06H-EPOCH-[a-f0-9]{64}\Z"),
    "acceptance_identity": re.compile(r"WO06H-ACCEPTANCE-[a-f0-9]{64}\Z"),
    "window_identity": re.compile(r"WO06H-WINDOW-[a-f0-9]{64}\Z"),
    "current_capability_proof": re.compile(r"WO06H-CAPABILITY-[a-f0-9]{64}\Z"),
    "compatibility_identity": re.compile(r"WO06H-COMPATIBILITY-[a-f0-9]{64}\Z"),
}


def restoration_request(
    *,
    epoch_identity,
    acceptance_identity,
    window_identity,
    current_runtime_proof,
    compatibility_identity,
    sponsor_authorization,
):
    """Build the exact content-addressed request accepted by the restoration surface."""
    core = {
        "policy": POLICY,
        "action": ACTION,
        "epoch_identity": epoch_identity,
        "acceptance_identity": acceptance_identity,
        "window_identity": window_identity,
        "current_runtime_proof": current_runtime_proof,
        "current_capability_proof": capability_identity(current_runtime_proof),
        "compatibility_identity": compatibility_identity,
        "sponsor_authorization": sponsor_authorization,
    }
    core["request_identity"] = identity("WO06H-RESTORATION-", core)
    core["integrity"] = sha256(canonical(core)).hexdigest()
    return core


def _validate_request(payload):
    if (
        type(payload) is not dict
        or set(payload) != FIELDS
        or payload["policy"] != POLICY
        or payload["action"] != ACTION
        or type(payload["current_runtime_proof"]) is not dict
        or type(payload["sponsor_authorization"]) is not str
        or not payload["sponsor_authorization"].strip()
        or any(
            type(payload[name]) is not str or pattern.fullmatch(payload[name]) is None
            for name, pattern in IDENTITIES.items()
        )
        or type(payload["request_identity"]) is not str
        or re.fullmatch(r"WO06H-RESTORATION-[a-f0-9]{64}", payload["request_identity"]) is None
        or type(payload["integrity"]) is not str
        or re.fullmatch(r"[a-f0-9]{64}", payload["integrity"]) is None
    ):
        raise ShadowError("SHADOW_COMPATIBILITY_RESTORATION_REQUEST_INVALID")
    supplied = dict(payload)
    integrity = supplied.pop("integrity")
    request_identity = supplied.pop("request_identity")
    if (
        request_identity != identity("WO06H-RESTORATION-", supplied)
        or integrity != sha256(canonical(dict(supplied, request_identity=request_identity))).hexdigest()
    ):
        raise ShadowError("SHADOW_COMPATIBILITY_RESTORATION_REQUEST_INTEGRITY_INVALID")
    return payload


def restore_compatible_epoch(service, payload, *, maintenance, idle):
    """Restore the current existing epoch through one exact compatibility record."""
    _validate_request(payload)
    if maintenance is not True or idle is not True:
        raise ShadowError("SHADOW_COMPATIBILITY_RESTORATION_MAINTENANCE_OR_QUIESCENCE_REQUIRED")
    with service._lock, service._epochs.transaction():
        store = service._epochs
        current = service._runtime_proof()
        declared = capabilities(current)
        if (
            current != payload["current_runtime_proof"]
            or current["pid"] != os.getpid()
            or current["source_state"] != "CLEAN_COMMIT"
            or capability_identity(current) != payload["current_capability_proof"]
            or CAPABILITY_IDENTITY not in declared
            or declared[CAPABILITY_IDENTITY].version != "1.2.0"
        ):
            raise ShadowError("SHADOW_COMPATIBILITY_RESTORATION_RUNTIME_INVALID")

        pointer = store.pointer()
        chain = store.chain()
        if (
            pointer is None
            or not chain
            or pointer["body"]["epoch"] != payload["epoch_identity"]
            or chain[0]["identity"] != payload["epoch_identity"]
        ):
            raise ShadowError("SHADOW_COMPATIBILITY_RESTORATION_CURRENT_EPOCH_INVALID")
        epoch = chain[0]
        window, acceptance = store.bound(epoch)
        if (
            epoch["body"]["acceptance"] != payload["acceptance_identity"]
            or acceptance.key != payload["acceptance_identity"]
            or epoch["body"]["window"] != payload["window_identity"]
            or window.key != payload["window_identity"]
        ):
            raise ShadowError("SHADOW_COMPATIBILITY_RESTORATION_BOUND_AUTHORITY_INVALID")

        try:
            record = store.load(payload["compatibility_identity"])
            diagnosis = store.load(record["body"]["diagnosis"])
        except (KeyError, ShadowError) as error:
            raise ShadowError("SHADOW_COMPATIBILITY_RESTORATION_RECORD_MISSING") from error
        if record["body"]["sponsor_authorization"] != payload["sponsor_authorization"]:
            raise ShadowError("SHADOW_COMPATIBILITY_RESTORATION_SPONSOR_AUTHORITY_INVALID")
        validate_equivalence(record, epoch, current, diagnosis)
        if store.equivalence(epoch, current) is not True:
            raise ShadowError("SHADOW_COMPATIBILITY_RESTORATION_NOT_ESTABLISHED")

        already_restored = (
            service._restored_acceptance == acceptance.key
            and service._accepted == current["manifest"]
            and service._window is not None
            and service._window.key == window.key
        )
        restore_epoch(service)
        status = service.status()
        if (
            not status["runtime_accepted"]
            or status["acceptance_disposition"] != "EXISTING_ACCEPTANCE_RESTORED"
            or status["acceptance_identity"] != acceptance.key
            or status["current_epoch"] != epoch["identity"]
            or status["window"]["identity"] != window.key
        ):
            raise ShadowError("SHADOW_COMPATIBILITY_RESTORATION_RESULT_INVALID")
        return {
            "outcome": "ALREADY_RESTORED" if already_restored else "RESTORED",
            "epoch": epoch["identity"],
            "acceptance": acceptance.key,
            "window": window.key,
            "compatibility": record["identity"],
            "request": payload["request_identity"],
            "status": status,
        }


__all__ = [
    "ACTION",
    "POLICY",
    "ROUTE",
    "restoration_request",
    "restore_compatible_epoch",
]
