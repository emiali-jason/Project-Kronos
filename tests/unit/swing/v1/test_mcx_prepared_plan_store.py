"""Durable MCX preparation remains outside Sponsor and entry authority."""

from dataclasses import replace
from decimal import Decimal

import pytest

from kronos.swing.v1.mcx_prepared_plan_store import (
    LocalMcxPreparedPlanStore, McxPreparedPlanEvidence,
    mcx_sponsor_admission_reasons,
)
from kronos.swing.v1.mcx_step31_construction import prepare_mcx_pending_construction
from kronos.swing.v1.mcx_step31_prepared_handoff import MCX_STEP31_COMMISSIONING
from tests.unit.browser.test_swing_review_intake_binding import _inventory, native_intake
from tests.unit.swing.v1.test_mcx_step31_construction import _fixture, _guard
from tests.unit.swing.v1.test_mcx_step31_prepared_handoff import FAMILIES, NOW


@pytest.mark.parametrize("native_intake", [f"{family}-LINEAGE" for family in FAMILIES], indirect=True)
def test_five_family_durable_preparation_is_non_actionable(native_intake, tmp_path):
    handoff, proof, geometry = _fixture(native_intake, tmp_path)
    pending = prepare_mcx_pending_construction(
        handoff, proof, geometry, lots=1, maximum_stop_risk=Decimal("1000000"),
        selected_current=lambda: handoff, commit_guard=_guard,
        guarded_recheck=lambda _: None,
    )
    record = McxPreparedPlanEvidence.create(pending, handoff)
    before = _inventory(tmp_path)
    store = LocalMcxPreparedPlanStore(tmp_path / "prepared-proposals")
    path = store.retain(record)
    assert store.retain(record) == path
    assert store.load(path) == record
    assert len(list(store.root.rglob("*.json"))) == 1
    assert path not in before
    assert record.authority == "NON_ACTIONABLE_PREPARATION_ONLY"
    assert record.commissioning_state == MCX_STEP31_COMMISSIONING
    assert MCX_STEP31_COMMISSIONING in mcx_sponsor_admission_reasons(
        record, pending, handoff, proof, observed_at=NOW,
    )
    assert not pending.entry_authority and not proof.permits_production_entry
    assert not list(tmp_path.rglob("*sponsor*.json"))
    assert not list(tmp_path.rglob("*trade-plan*.json"))


@pytest.mark.parametrize("native_intake", ["GOLDM-LINEAGE"], indirect=True)
def test_changed_sponsor_binding_and_corrupt_record_fail_closed(native_intake, tmp_path):
    handoff, proof, geometry = _fixture(native_intake, tmp_path)
    pending = prepare_mcx_pending_construction(
        handoff, proof, geometry, lots=1, maximum_stop_risk=Decimal("1000000"),
        selected_current=lambda: handoff, commit_guard=_guard,
        guarded_recheck=lambda _: None,
    )
    record = McxPreparedPlanEvidence.create(pending, handoff)
    store = LocalMcxPreparedPlanStore(tmp_path / "prepared-proposals")
    path = store.retain(record)
    changed = replace(pending, handoff_integrity_sha256="f" * 64)
    assert mcx_sponsor_admission_reasons(
        record, changed, handoff, proof, observed_at=NOW,
    ) == ("MCX_PREPARED_PLAN_CURRENT_BINDING_INVALID", MCX_STEP31_COMMISSIONING)
    assert mcx_sponsor_admission_reasons(
        record, pending, handoff, None, observed_at=NOW,
    ) == ("MCX_SPONSOR_ADMISSION_INPUT_INVALID", MCX_STEP31_COMMISSIONING)
    tampered = path.read_bytes().replace(b"GOLDM", b"COPPER")
    path.write_bytes(tampered)
    with pytest.raises(ValueError, match="INTEGRITY_INVALID"):
        store.load(path)
    with pytest.raises(ValueError, match="IMMUTABLE"):
        store.retain(record)
