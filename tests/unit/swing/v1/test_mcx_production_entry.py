"""Exact MCX proof binds source bytes but never commissions production entry."""

from dataclasses import asdict, replace
from contextlib import contextmanager, nullcontext
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.application.swing_mcx_evidence import McxRetainedMasterMatch
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.swing.v1.mcx_contract_profile import (
    McxFamily, _digest as lineage_digest, mcx_unit_profile,
)
from kronos.swing.v1.mcx_contract_selection import (
    McxContractAdmissionFacts, McxSelectionRole, choose_mcx_contract,
    prepare_mcx_contract_offer,
)
from kronos.swing.v1.mcx_production_entry import (
    McxProductionEvidenceRejected, McxProductionReadSet,
    issue_mcx_exact_contract_proof, require_mcx_proof_current_at_commit,
)
from kronos.swing.v1.mcx_production_proof import (
    McxCutoffObservation, McxObservationOrigin,
    McxProviderConversionObservation, inspect_mcx_specification_pdf,
)
from kronos.swing.v1.mcx_quantity import McxQuantityProofOrigin, McxTypedQuantity
from kronos.swing.v1.mcx_step31_prepared_handoff import (
    _digest as handoff_digest, prepare_mcx_review_v2_step31_handoff,
)
from tests.unit.browser.test_swing_review_intake_binding import _inventory, native_intake
from tests.unit.swing.v1.test_mcx_step31_prepared_handoff import _current


IST = ZoneInfo("Asia/Kolkata")
CHOICE_AT = datetime(2026, 8, 14, 9, tzinfo=IST)
PREPARED_AT = datetime(2026, 8, 14, 23, 59, tzinfo=IST)
PROOF_AT = PREPARED_AT + timedelta(hours=1)
HASH = "a" * 64


def _file(root: Path, name: str, value: bytes) -> tuple[Path, str]:
    path = root / name
    path.write_bytes(value)
    return path, sha256(value).hexdigest()


def _readset(workflow, root: Path, family: McxFamily):
    profile = mcx_unit_profile(family)
    read = _current(workflow, root, promotion_at=PREPARED_AT)
    handoff = prepare_mcx_review_v2_step31_handoff(
        lambda: read, prepared_at=PREPARED_AT)
    bound = handoff.bound
    expiry = date.fromisoformat(bound.derivative_expiry)
    instrument = InstrumentRecord(
        "KITE", "MCX", "MCX-FUT", bound.derivative_symbol, family.value,
        "FUT", expiry, profile.tick_in_quotation_units, 1,
    )
    master_path, master_hash = _file(root, "master.json", b'{"fixture":"authenticated snapshot"}')
    master = McxRetainedMasterMatch(
        "ISOLATED-SNAPSHOT", "ISOLATED-RECORD", master_hash,
        CHOICE_AT - timedelta(hours=1), instrument, 123456,
        "ISOLATED-RECORD-INTEGRITY", CHOICE_AT - timedelta(hours=1),
        CHOICE_AT - timedelta(hours=1), None,
    )
    pdf_path, pdf_hash = _file(root, "specification.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n")
    spec = inspect_mcx_specification_pdf(
        pdf_path, family=family, source_url=profile.exchange_specification_url,
        expected_sha256=pdf_hash, effective_from=date(2026, 8, 1),
        effective_through=None, physical_quantity_per_lot=profile.trading_quantity,
        physical_unit=profile.trading_unit,
        quotation_base_quantity=profile.quotation_quantity,
        quotation_unit=profile.quotation_unit,
        tick_size=profile.tick_in_quotation_units,
        settlement=profile.settlement, origin=McxObservationOrigin.ISOLATED_FIXTURE,
    )
    selected_facts = McxContractAdmissionFacts(
        family, instrument, expiry, HASH, master.snapshot_identity,
        master.record_identity, PROOF_AT + timedelta(days=2),
        pdf_hash, profile.settlement,
        PROOF_AT + timedelta(days=2),
        PROOF_AT + timedelta(days=2) if profile.settlement.value == "PHYSICAL" else None,
        PROOF_AT + timedelta(days=2),
    )
    offer = prepare_mcx_contract_offer(
        bound.run_identity, family, (selected_facts,),
        observed_at=CHOICE_AT - timedelta(minutes=1),
    )
    selection = choose_mcx_contract(
        offer, McxSelectionRole.NEAR,
        sponsor_authorization_identity="ISOLATED-SPONSOR-CHOICE",
        recorded_at=CHOICE_AT,
    )
    original_lineage = read.facts.instrument(family.value).mcx_request_lineage
    lineage = replace(original_lineage,
        normalized_instrument_sha256=lineage_digest(asdict(instrument)))
    rebound = replace(bound,
        request_bound_lineage_sha256=lineage_digest(asdict(lineage)))
    unsigned = dict(contract_identity=handoff.contract_identity,
        authority=handoff.authority, commissioning_state=handoff.commissioning_state,
        bound=asdict(rebound), prepared_at=handoff.prepared_at)
    handoff = replace(handoff, bound=rebound,
        integrity_sha256=handoff_digest(unsigned))
    conversion_path, conversion_hash = _file(root, "conversion.json", b'{"fixture":"LOTS"}')
    conversion = McxProviderConversionObservation(
        master.snapshot_identity, master.record_identity,
        master.provider_instrument_token, instrument.trading_symbol,
        "LOTS", 1, conversion_hash, McxObservationOrigin.ISOLATED_FIXTURE,
    )
    quantity = McxTypedQuantity(
        2, profile.trading_quantity, profile.trading_unit,
        profile.quotation_quantity, profile.quotation_unit,
        profile.quotation_multiplier_per_lot, 2, "LOTS", conversion_hash,
        McxQuantityProofOrigin.ISOLATED_FIXTURE,
    )
    exchange_path, exchange_hash = _file(root, "exchange-cutoff.json", b'{"fixture":"exchange"}')
    broker_path, broker_hash = _file(root, "broker-cutoff.json", b'{"fixture":"broker"}')
    cutoff = McxCutoffObservation(
        instrument.trading_symbol, expiry,
        datetime(2026, 8, 28, 17, tzinfo=IST),
        datetime(2026, 8, 27, 15, tzinfo=IST),
        datetime(2026, 8, 27, 14, tzinfo=IST),
        datetime(2026, 8, 28, 16, tzinfo=IST),
        datetime(2026, 8, 27, 13, tzinfo=IST)
        if profile.settlement.value == "PHYSICAL" else None,
        exchange_hash, broker_hash, McxObservationOrigin.ISOLATED_FIXTURE,
    )
    return McxProductionReadSet(
        selection, handoff, lineage, master, master_path, spec, pdf_path,
        quantity, conversion, conversion_path, cutoff, exchange_path, broker_path,
    )


@pytest.mark.parametrize("family,native_intake", [
    (family, f"{family.value}-LINEAGE") for family in McxFamily
], indirect=["native_intake"])
def test_five_family_exact_units_and_source_proof_remain_non_actionable(family, native_intake, tmp_path):
    read = _readset(native_intake, tmp_path, family)
    before = _inventory(tmp_path)
    entry, stop = Decimal("100"), Decimal("95")
    proof = issue_mcx_exact_contract_proof(lambda: read, observed_at=PROOF_AT,
                                           entry=entry, stop=stop)
    assert proof.selected_contract == read.selection.trading_symbol
    assert proof.selection_sha256 == read.selection.integrity_sha256
    assert proof.handoff_sha256 == read.handoff.integrity_sha256
    assert proof.completed_one_hour_sha256 == read.lineage.completed_1h_sha256
    assert proof.provider_order_quantity == 2
    assert proof.physical_quantity == read.quantity.physical_quantity
    assert proof.gross_notional == read.quantity.notional(entry)
    assert proof.rupees_per_tick == read.specification.rupees_per_tick_per_lot * 2
    assert proof.gross_stop_risk == read.quantity.stop_risk(entry, stop)
    assert proof.fees is None and proof.margin is None
    assert not proof.permits_new_entry
    assert "MCX_NUMERIC_RISK_POLICY_UNAPPROVED" in proof.missing_authority
    with pytest.raises(McxProductionEvidenceRejected, match="NOT_COMMISSIONED"):
        require_mcx_proof_current_at_commit(
            proof, lambda: read, observed_at=PROOF_AT, entry=entry, stop=stop,
            commit_guard=nullcontext)
    assert _inventory(tmp_path) == before


@pytest.mark.parametrize("native_intake", ["COPPER-LINEAGE"], indirect=True)
def test_each_changed_binding_or_source_rejects_without_durable_effect(native_intake, tmp_path):
    read = _readset(native_intake, tmp_path, McxFamily.COPPER)
    before = _inventory(tmp_path)
    kwargs = dict(observed_at=PROOF_AT, entry=Decimal("100"), stop=Decimal("95"))
    original = issue_mcx_exact_contract_proof(lambda: read, **kwargs)
    cases = (
        replace(read, selection=None),
        replace(read, master=replace(read.master, provider_instrument_token=999)),
        replace(read, specification=replace(read.specification, effective_from=date(2026, 9, 1))),
        replace(read, conversion=replace(read.conversion, provider_quantity_per_lot=5)),
        replace(read, cutoff=replace(read.cutoff, trading_symbol="OTHER26AUGFUT")),
        replace(read, lineage=replace(read.lineage, completed_1h_sha256=HASH)),
        replace(read, handoff=None),
    )
    for changed in cases:
        with pytest.raises((McxProductionEvidenceRejected, ValueError)):
            issue_mcx_exact_contract_proof(lambda changed=changed: changed, **kwargs)
    calls = iter((read, replace(read, master=replace(read.master, record_identity="OTHER"))))
    with pytest.raises(McxProductionEvidenceRejected):
        issue_mcx_exact_contract_proof(lambda: next(calls), **kwargs)
    guard_active = []

    @contextmanager
    def commit_guard():
        guard_active.append(True)
        try:
            yield
        finally:
            guard_active.pop()

    def changed_current():
        assert guard_active
        return replace(read, cutoff=replace(
            read.cutoff, broker_entry_until=read.cutoff.broker_entry_until - timedelta(minutes=1)))

    with pytest.raises(McxProductionEvidenceRejected, match="STALE_AT_COMMIT"):
        require_mcx_proof_current_at_commit(
            original, changed_current, commit_guard=commit_guard, **kwargs)
    assert not guard_active
    read.conversion_file.write_bytes(b'{"fixture":"changed"}')
    with pytest.raises(McxProductionEvidenceRejected, match="SOURCE_CHANGED"):
        issue_mcx_exact_contract_proof(lambda: read, **kwargs)
    assert _inventory(tmp_path) != before  # only the deliberate fixture mutation


@pytest.mark.parametrize("native_intake", ["COPPER-LINEAGE"], indirect=True)
def test_closed_entry_cutoff_and_wrong_tick_reject(native_intake, tmp_path):
    read = _readset(native_intake, tmp_path, McxFamily.COPPER)
    with pytest.raises(McxProductionEvidenceRejected, match="PRICE_TICK"):
        issue_mcx_exact_contract_proof(lambda: read, observed_at=PROOF_AT,
                                       entry=Decimal("100.01"), stop=Decimal("95"))
    proof = issue_mcx_exact_contract_proof(
        lambda: read, observed_at=read.cutoff.broker_entry_until,
        entry=Decimal("100"), stop=Decimal("95"))
    assert "MCX_BROKER_ENTRY_CLOSED" in proof.missing_authority
    assert not proof.permits_new_entry
