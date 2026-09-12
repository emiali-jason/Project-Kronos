"""Dedicated same-epoch restoration tests use isolated stores only."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from kronos.application.intraday_shadow_compatibility import (
    ACTION,
    POLICY,
    restoration_request,
    restore_compatible_epoch,
)
from kronos.intraday.live_shadow import ShadowError
from kronos.intraday.live_shadow_epoch_capability import CAPABILITY_IDENTITY
from tests.unit.intraday.test_live_shadow_epoch_deterministic_digest import (
    corrected_restart,
    production_case,
    retain_equivalence,
)
from tests.unit.intraday.test_live_shadow_epochs import inventory, perform


def request_for(service, record):
    epoch = service._epochs.chain()[0]
    return restoration_request(
        epoch_identity=epoch["identity"],
        acceptance_identity=epoch["body"]["acceptance"],
        window_identity=epoch["body"]["window"],
        current_runtime_proof=service._runtime_proof(),
        compatibility_identity=record["identity"],
        sponsor_authorization=record["body"]["sponsor_authorization"],
    )


def restore(service, record, **conditions):
    return restore_compatible_epoch(
        service,
        request_for(service, record),
        maintenance=conditions.get("maintenance", True),
        idle=conditions.get("idle", True),
    )


def test_compatibility_restores_existing_authority_without_creating_records(production_case):
    record = retain_equivalence(production_case)
    epoch = production_case._epochs.chain()[0]
    before = inventory(production_case._epochs.raw.root)
    result = restore(production_case, record)
    after = inventory(production_case._epochs.raw.root)
    status = result["status"]
    assert result["outcome"] == "RESTORED"
    assert result["epoch"] == epoch["identity"]
    assert result["acceptance"] == epoch["body"]["acceptance"]
    assert result["window"] == epoch["body"]["window"]
    assert before == after
    assert status["enabled"] and status["acceptance_disposition"] == "EXISTING_ACCEPTANCE_RESTORED"
    assert status["counts"]["cohort_a"] == status["counts"]["cohort_b"] == status["counts"]["eod_available"] == 0
    assert status["all_epoch_counts"] == {"cohort_a": 34, "cohort_b": 66, "eod_available": 0}


def test_duplicate_restoration_is_idempotent(production_case):
    record = retain_equivalence(production_case)
    restore(production_case, record)
    before = inventory(production_case._epochs.raw.root)
    assert restore(production_case, record)["outcome"] == "ALREADY_RESTORED"
    assert inventory(production_case._epochs.raw.root) == before


@pytest.mark.parametrize("condition", [{"maintenance": False}, {"idle": False}])
def test_maintenance_and_quiescence_are_server_owned_gates(production_case, condition):
    record = retain_equivalence(production_case)
    with pytest.raises(ShadowError, match="MAINTENANCE_OR_QUIESCENCE"):
        restore(production_case, record, **condition)
    assert not production_case.status()["enabled"]


@pytest.mark.parametrize("field", ["epoch_identity", "acceptance_identity", "window_identity"])
def test_wrong_existing_authority_fails_closed(production_case, field):
    record = retain_equivalence(production_case)
    payload = request_for(production_case, record)
    payload[field] = payload[field].rsplit("-", 1)[0] + "-" + "f" * 64
    supplied = {key: value for key, value in payload.items() if key not in {"request_identity", "integrity"}}
    payload = restoration_request(**{
        "epoch_identity": supplied["epoch_identity"],
        "acceptance_identity": supplied["acceptance_identity"],
        "window_identity": supplied["window_identity"],
        "current_runtime_proof": supplied["current_runtime_proof"],
        "compatibility_identity": supplied["compatibility_identity"],
        "sponsor_authorization": supplied["sponsor_authorization"],
    })
    with pytest.raises(ShadowError):
        restore_compatible_epoch(production_case, payload, maintenance=True, idle=True)


def test_missing_or_wrong_compatibility_record_fails_closed(production_case):
    record = retain_equivalence(production_case)
    payload = request_for(production_case, record)
    payload = restoration_request(
        epoch_identity=payload["epoch_identity"], acceptance_identity=payload["acceptance_identity"],
        window_identity=payload["window_identity"], current_runtime_proof=payload["current_runtime_proof"],
        compatibility_identity="WO06H-COMPATIBILITY-" + "f" * 64,
        sponsor_authorization=payload["sponsor_authorization"],
    )
    with pytest.raises(ShadowError, match="RECORD_MISSING"):
        restore_compatible_epoch(production_case, payload, maintenance=True, idle=True)


@pytest.mark.parametrize("fault", ["historical", "corrected", "diagnosis", "sponsor", "evidence"])
def test_invalid_compatibility_binding_fails_closed(production_case, fault):
    record = retain_equivalence(production_case, fault=fault)
    payload = request_for(production_case, record)
    with pytest.raises(ShadowError):
        restore_compatible_epoch(production_case, payload, maintenance=True, idle=True)


@pytest.mark.parametrize("mutation", ["WO_06H_LIVE_SHADOW", "INTRADAY_DISCOVERY_OPERATION"])
def test_calculation_or_other_capability_drift_rejects(tmp_path, production_case, mutation):
    record = retain_equivalence(production_case)
    changed = corrected_restart(tmp_path, production_case, mutation=mutation)
    payload = restoration_request(
        epoch_identity=production_case._epochs.chain()[0]["identity"],
        acceptance_identity=production_case._epochs.chain()[0]["body"]["acceptance"],
        window_identity=production_case._epochs.chain()[0]["body"]["window"],
        current_runtime_proof=changed._runtime_proof(), compatibility_identity=record["identity"],
        sponsor_authorization=record["body"]["sponsor_authorization"],
    )
    with pytest.raises(ShadowError):
        restore_compatible_epoch(changed, payload, maintenance=True, idle=True)


def test_semantic_drift_without_record_and_dirty_runtime_reject(production_case):
    record = retain_equivalence(production_case)
    missing = request_for(production_case, record)
    missing["compatibility_identity"] = "WO06H-COMPATIBILITY-" + "0" * 64
    with pytest.raises(ShadowError):
        restore_compatible_epoch(production_case, missing, maintenance=True, idle=True)
    object.__setattr__(production_case._manifest.startup, "source_state", "DIRTY_WORKTREE")
    dirty_record = deepcopy(record)
    with pytest.raises(ShadowError):
        restore(production_case, dirty_record)


def test_request_rejects_creation_fields_tampering_and_self_asserted_authority(production_case):
    record = retain_equivalence(production_case)
    payload = request_for(production_case, record)
    assert payload["policy"] == POLICY and payload["action"] == ACTION
    for mutation in (
        dict(payload, new_epoch=True),
        dict(payload, research_window={}),
        dict(payload, acceptance={}),
        dict(payload, integrity="0" * 64),
        dict(payload, sponsor_authorization="CALLER-SELF-ASSERTED"),
    ):
        with pytest.raises(ShadowError):
            restore_compatible_epoch(production_case, mutation, maintenance=True, idle=True)


def test_exact_restoration_and_successor_commissioning_remain_separate(production_case):
    record = retain_equivalence(production_case)
    original_epoch = production_case._epochs.chain()[0]["identity"]
    transition = production_case._epochs.pointer()
    old = production_case._epochs.load(transition["body"]["authorization"])
    old_authorization = {
        "action": "COMMISSION_SUCCESSOR_EPOCH",
        "request_identity": old["body"]["request"],
        "authorization_identity": old["identity"],
    }
    with pytest.raises(ShadowError):
        perform(production_case, old_authorization)
    assert restore(production_case, record)["epoch"] == original_epoch


def test_documented_current_production_case_matches_qualified_shape():
    fixture = json.loads((Path(__file__).parents[2] / "fixtures" / "intraday" /
        "wo06h_same_epoch_compatibility_production.json").read_text())
    assert fixture == {
        "acceptance": "WO06H-ACCEPTANCE-705befed9c2ff4d8d3a53aa94b4b9d8b9c5d67b99f6a0093d22ed4335cd71259",
        "compatibility": "WO06H-COMPATIBILITY-026b07704ccaed7d3d81c95b4d5965cefe68cb52996ab3628ed6f6a181fe0e03",
        "compatibility_projection": "COMPATIBLE",
        "current_counts": {"cohort_a": 0, "cohort_b": 0, "eod_available": 0},
        "epoch": "WO06H-EPOCH-4bc5e40a837f8ba26ea8ed91245148c4e45a6d24178d90ba187822586b16dcc3",
        "historical_counts": {"cohort_a": 34, "cohort_b": 66, "eod_available": 0},
        "maintenance": "ACTIVE", "provider": "DISCONNECTED",
        "revision": "507e643b68e7b5ebe7a597f5e278c40c5cc03f20",
        "window": "WO06H-WINDOW-ed7a53dfdc22e1f95440c7778b381a9a2d7ad69d10b892a5857c29576f1e094c",
    }
