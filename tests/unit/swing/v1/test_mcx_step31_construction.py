"""Non-actionable five-family MCX construction and lifecycle fences."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from kronos.swing.v1.mcx_contract_profile import McxFamily, mcx_unit_profile
from kronos.swing.v1.mcx_step31_construction import (
    McxConstructionRejected, McxContractProofPrerequisites,
    McxOneHourGeometry, McxProofOrigin, McxQuantitySemantics,
    calculate_mcx_monetary_risk, check_mcx_pending_entry,
    existing_mcx_position_monitoring_and_exit_preserved,
    prepare_mcx_pending_construction, prepare_mcx_pending_from_owner,
    select_owner_current_mcx_handoff,
)
from kronos.swing.v1.mcx_step31_prepared_handoff import (
    MCX_STEP31_COMMISSIONING, prepare_mcx_review_v2_step31_handoff,
)
from tests.unit.browser.test_swing_review_intake_binding import _inventory, native_intake
from tests.unit.swing.v1.test_mcx_step31_prepared_handoff import FAMILIES, _current, NOW
from tests.unit.application.test_swing_mtf_facts import _instrument


def _fixture(native_intake, root):
    read = _current(native_intake, root)
    handoff = prepare_mcx_review_v2_step31_handoff(lambda: read, prepared_at=NOW)
    bound = handoff.bound
    proof = McxContractProofPrerequisites(
        family=bound.family, trading_symbol=bound.derivative_symbol,
        expiry=bound.derivative_expiry, origin=McxProofOrigin.ISOLATED_FIXTURE,
        provider_snapshot_identity="fixture-snapshot",
        provider_record_identity="fixture-record",
        normalized_instrument_sha256="a" * 64,
        effective_specification_sha256="b" * 64,
        quantity_semantics=McxQuantitySemantics.LOTS,
        expiry_session_identity="fixture-domain008",
        expiry_eligibility_boundary=NOW + timedelta(days=1),
        entry_blackout_policy_identity="fixture-blackout",
        energy_execution_decision_identity=(
            "fixture-energy-only" if bound.family in {McxFamily.CRUDEOIL, McxFamily.NATURALGAS}
            else None
        ),
    )
    geometry = McxOneHourGeometry(
        entry=Decimal("100"), stop=Decimal("95"), target=Decimal("110"),
        completed_one_hour_sha256=bound.completed_one_hour_sha256,
        completed_one_hour_boundary=bound.completed_one_hour_boundary,
    )
    return handoff, proof, geometry


@contextmanager
def _guard():
    yield


@pytest.mark.parametrize("native_intake", [f"{family}-LINEAGE" for family in FAMILIES], indirect=True)
def test_five_family_exact_quote_unit_risk_is_non_actionable(native_intake, tmp_path):
    handoff, proof, geometry = _fixture(native_intake, tmp_path)
    before = _inventory(tmp_path)
    pending = prepare_mcx_pending_construction(
        handoff, proof, geometry, lots=2, maximum_stop_risk=Decimal("1000000"),
        selected_current=lambda: handoff, commit_guard=_guard,
        guarded_recheck=lambda expected: None,
    )
    profile = mcx_unit_profile(proof.family)
    multiplier = profile.quotation_multiplier_per_lot
    assert pending.risk.notional == Decimal("200") * multiplier
    assert pending.risk.stop_risk == Decimal("10") * multiplier
    assert pending.risk.tick_value_per_lot == profile.tick_in_quotation_units * multiplier
    assert pending.risk.provider_order_quantity is None
    assert pending.commissioning_state == MCX_STEP31_COMMISSIONING
    assert not pending.entry_authority and not proof.permits_production_entry
    assert check_mcx_pending_entry(pending, handoff, proof, observed_at=NOW) == (
        MCX_STEP31_COMMISSIONING,
    )
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize("native_intake", ["GOLDM-LINEAGE"], indirect=True)
def test_selected_current_and_final_commit_fence_reject_changed_sources(native_intake, tmp_path):
    handoff, proof, geometry = _fixture(native_intake, tmp_path)
    before = _inventory(tmp_path)
    calls = []
    with pytest.raises(McxConstructionRejected, match="CURRENT_SELECTION_CHANGED"):
        prepare_mcx_pending_construction(
            handoff, proof, geometry, lots=1, maximum_stop_risk=Decimal("1000"),
            selected_current=lambda: None, commit_guard=_guard,
            guarded_recheck=lambda _: calls.append("commit"),
        )
    assert calls == []
    for changed in ("run", "pointer", "receipt", "promotion", "confirmation"):
        def recheck(_):
            calls.append(changed)
            raise ValueError("changed exact byte: " + changed)
        with pytest.raises(McxConstructionRejected, match="COMMIT_FENCE_CHANGED"):
            prepare_mcx_pending_construction(
                handoff, proof, geometry, lots=1, maximum_stop_risk=Decimal("1000"),
                selected_current=lambda: handoff, commit_guard=_guard,
                guarded_recheck=recheck,
            )
    assert calls == ["run", "pointer", "receipt", "promotion", "confirmation"]
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize("native_intake", ["COPPER-LINEAGE"], indirect=True)
def test_geometry_quantity_and_monetary_risk_fail_closed(native_intake, tmp_path):
    handoff, _, geometry = _fixture(native_intake, tmp_path)
    invalid = (
        replace(geometry, completed_one_hour_sha256="f" * 64),
        replace(geometry, stop=Decimal("101")),
        replace(geometry, target=Decimal("99")),
        replace(geometry, entry=Decimal("100.01")),
    )
    for candidate in invalid:
        with pytest.raises(McxConstructionRejected, match="GEOMETRY_INVALID"):
            calculate_mcx_monetary_risk(
                handoff, candidate, lots=1,
                maximum_stop_risk=Decimal("1000000"),
            )
    for lots in (0, -1, True, 1.5):
        with pytest.raises(McxConstructionRejected, match="GEOMETRY_INVALID"):
            calculate_mcx_monetary_risk(
                handoff, geometry, lots=lots,
                maximum_stop_risk=Decimal("1000000"),
            )
    with pytest.raises(McxConstructionRejected, match="MONETARY_RISK_EXCEEDED"):
        calculate_mcx_monetary_risk(
            handoff, geometry, lots=1, maximum_stop_risk=Decimal("100"),
        )


@pytest.mark.parametrize("native_intake", ["CRUDEOIL-LINEAGE"], indirect=True)
def test_missing_proof_expiry_and_roll_block_entry_but_not_historical_exit(native_intake, tmp_path):
    handoff, proof, geometry = _fixture(native_intake, tmp_path)
    pending = prepare_mcx_pending_construction(
        handoff, proof, geometry, lots=1, maximum_stop_risk=Decimal("1000000"),
        selected_current=lambda: handoff, commit_guard=_guard,
        guarded_recheck=lambda _: None,
    )
    missing = McxContractProofPrerequisites(
        family=proof.family, trading_symbol=proof.trading_symbol, expiry=proof.expiry,
    )
    reasons = check_mcx_pending_entry(pending, handoff, missing, observed_at=NOW)
    assert "PROVIDER_SNAPSHOT_IDENTITY_UNAVAILABLE" in reasons
    assert "EFFECTIVE_SPECIFICATION_SHA256_UNAVAILABLE" in reasons
    assert "PROVIDER_QUANTITY_SEMANTICS_UNAVAILABLE" in reasons
    assert "ENERGY_EXECUTION_DECISION_UNAVAILABLE" in reasons
    assert "MCX_PENDING_EXPIRY_ELIGIBILITY_UNAVAILABLE_OR_EXPIRED" in reasons
    assert "MCX_PENDING_EXPIRY_ELIGIBILITY_UNAVAILABLE_OR_EXPIRED" in check_mcx_pending_entry(
        pending, handoff, proof, observed_at=proof.expiry_eligibility_boundary,
    )
    rolled = replace(proof, trading_symbol="CRUDEOIL27JANFUT", expiry="2027-01-19")
    assert "MCX_PENDING_CONTRACT_ROLLED_OR_CHANGED" in check_mcx_pending_entry(
        pending, handoff, rolled, observed_at=NOW,
    )
    assert existing_mcx_position_monitoring_and_exit_preserved(
        historical_contract_symbol=pending.trading_symbol,
        historical_expiry=pending.expiry,
        current_contract_symbol=rolled.trading_symbol,
    )


@pytest.mark.parametrize("native_intake", ["GOLDM-LINEAGE"], indirect=True)
def test_owner_current_selection_and_wo05_wo07_byte_fence(native_intake, tmp_path):
    read = _current(native_intake, tmp_path)
    native_intake._v2_store.retain(
        read.promotion, current=native_intake._v2_current,
    )
    native_intake._v2_promotions[(read.run_identity, "GOLDM")] = read.promotion
    selection = select_owner_current_mcx_handoff(
        native_intake, McxFamily.GOLDM, _instrument("GOLDM", "MCX"),
        prepared_at=NOW,
    )
    assert selection.prepared.bound.receipt_identity == read.receipt.receipt_id
    assert selection.prepared.bound.promotion_identity == read.promotion.identity
    assert selection.fence.entries
    assert native_intake.prepare_page_state()
    with native_intake.page_response() as response:
        shared = select_owner_current_mcx_handoff(
            native_intake, McxFamily.GOLDM, _instrument("GOLDM", "MCX"),
            prepared_at=NOW, _response=response)
        assert shared.prepared == selection.prepared
        assert shared.fence.entries
        from types import SimpleNamespace
        with pytest.raises(ValueError):
            select_owner_current_mcx_handoff(
                native_intake, McxFamily.GOLDM, _instrument("GOLDM", "MCX"),
                prepared_at=NOW, _response=SimpleNamespace(active=True, owner=object()))
    with pytest.raises(ValueError):
        select_owner_current_mcx_handoff(
            native_intake, McxFamily.GOLDM, _instrument("GOLDM", "MCX"),
            prepared_at=NOW, _response=response)
    selected_paths = {str(path) for path, _ in selection.fence.entries}
    assert any(path.endswith("current-mcx-request.json") for path in selected_paths)
    assert any("acceptance-current/" in path for path in selected_paths)
    assert any("chart-selections/" in path for path in selected_paths)
    assert any(path.endswith("/" + read.promotion.value["input_sha256"] + ".json")
               for path in selected_paths)
    with selection.final_fence():
        pass
    owner_pending = prepare_mcx_pending_from_owner(
        native_intake, McxFamily.GOLDM, _instrument("GOLDM", "MCX"),
        McxContractProofPrerequisites(
            family=McxFamily.GOLDM,
            trading_symbol=selection.prepared.bound.derivative_symbol,
            expiry=selection.prepared.bound.derivative_expiry,
        ),
        McxOneHourGeometry(
            entry=Decimal("100"), stop=Decimal("95"), target=Decimal("110"),
            completed_one_hour_sha256=selection.prepared.bound.completed_one_hour_sha256,
            completed_one_hour_boundary=selection.prepared.bound.completed_one_hour_boundary,
        ),
        prepared_at=NOW, lots=1, maximum_stop_risk=Decimal("1000"),
    )
    assert not owner_pending.entry_authority
    current_pointer = native_intake.store.root / "current-mcx-request.json"
    current_pointer.write_bytes(b"changed isolated test pointer")
    with pytest.raises(ValueError):
        with selection.final_fence():
            pytest.fail("stale pointer entered prospective commit scope")
