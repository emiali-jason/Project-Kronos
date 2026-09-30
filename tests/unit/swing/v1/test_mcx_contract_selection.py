"""Sponsor expiry choice precedes contract-bound Swing evidence acquisition."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.application import swing_opportunities as app
from kronos.swing.universe import SwingUniverseAssetClass
from kronos.swing.v1.mcx_contract_profile import McxFamily, McxSettlement
from kronos.swing.v1.mcx_contract_selection import (
    LocalMcxSponsorSelectionStore, McxContractAdmissionFacts,
    McxSelectionRole, acquire_selected_mcx_evidence, choose_mcx_contract,
    prepare_mcx_contract_offer, require_mcx_choice_matches_handoff,
    selected_mcx_instrument_before_acquisition, V1_ADVISORY_SELECTION,
)
from tests.unit.browser.test_swing_review_intake_binding import native_intake
from tests.unit.swing.v1.test_mcx_step31_construction import _fixture as handoff_fixture


RUN = "SWING-RUN-00000000000000000000000000000001"
NOW = datetime(2026, 9, 28, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
FAMILIES = tuple(McxFamily)
PHYSICAL = {McxFamily.GOLDM, McxFamily.SILVERM, McxFamily.COPPER}


@pytest.mark.parametrize("family", FAMILIES)
def test_v1_shows_two_nearest_unexpired_authentic_listings_without_invented_gates(family, tmp_path):
    expired = _fact(family, date(2026, 9, 27))
    near = replace(_fact(family, date(2026, 10, 8)),
                   verified_expiry=None, expiry_proof_sha256=None,
                   master_valid_until=None, effective_specification_sha256=None,
                   settlement=None, broker_entry_until=None, delivery_start=None,
                   entry_until=None)
    second = replace(_fact(family, date(2026, 11, 8)),
                     verified_expiry=None, expiry_proof_sha256=None,
                     master_valid_until=None, effective_specification_sha256=None,
                     settlement=None, broker_entry_until=None, delivery_start=None,
                     entry_until=None)
    third = _fact(family, date(2026, 12, 8))
    offer = prepare_mcx_contract_offer(
        RUN, family, (third, second, expired, near), observed_at=NOW,
        selection_policy=V1_ADVISORY_SELECTION,
    )
    assert (offer.near, offer.next_eligible) == (near, second)
    assert offer.selectable() == (McxSelectionRole.NEAR, McxSelectionRole.NEXT_ELIGIBLE)
    assert offer.days_to_verified_expiry == 10
    choice = choose_mcx_contract(offer, McxSelectionRole.NEXT_ELIGIBLE,
                                 sponsor_authorization_identity="SPONSOR-V1-CHOICE",
                                 recorded_at=NOW + timedelta(seconds=1))
    store = LocalMcxSponsorSelectionStore(tmp_path / "selection")
    store.retain(choice)
    acquired = acquire_selected_mcx_evidence(
        store, offer, (near.instrument, second.instrument, third.instrument),
        acquired_at=NOW + timedelta(seconds=2),
        acquire=lambda exact: exact,
    )
    assert acquired == second.instrument
    assert store.load(RUN, family) == choice


def test_v1_shows_but_cannot_choose_known_closed_second_contract():
    near = _fact(McxFamily.COPPER, date(2026, 10, 8))
    closed = replace(_fact(McxFamily.COPPER, date(2026, 11, 8)),
                     entry_until=NOW - timedelta(seconds=1))
    later = _fact(McxFamily.COPPER, date(2026, 12, 8))
    offer = prepare_mcx_contract_offer(RUN, McxFamily.COPPER,
        (near, closed, later), observed_at=NOW,
        selection_policy=V1_ADVISORY_SELECTION)
    assert offer.next_eligible == closed
    assert offer.selectable() == (McxSelectionRole.NEAR,)
    with pytest.raises(ValueError, match="CHOICE_REJECTED"):
        choose_mcx_contract(offer, McxSelectionRole.NEXT_ELIGIBLE,
            sponsor_authorization_identity="SPONSOR-V1-CHOICE", recorded_at=NOW)


def _fact(family, expiry, *, entry=True, broker=True, delivery=True,
          master=True, spec=True):
    instrument = InstrumentRecord(
        "KITE", "MCX", "MCX-FUT",
        f"{family.value}{expiry.year % 100:02d}{expiry.strftime('%b').upper()}FUT",
        family.value, "FUT", expiry, Decimal("1"), 1,
    )
    physical = family in PHYSICAL
    return McxContractAdmissionFacts(
        family, instrument, expiry, "a" * 64, "fixture-authenticated-master",
        "fixture-record-" + instrument.trading_symbol,
        NOW + timedelta(days=5) if master else NOW - timedelta(seconds=1),
        "b" * 64 if spec else None,
        McxSettlement.PHYSICAL if physical else McxSettlement.CASH,
        NOW + timedelta(days=5) if entry else NOW - timedelta(seconds=1),
        (NOW + timedelta(days=5) if delivery else None) if physical else None,
        NOW + timedelta(days=5) if broker else None,
    )


@pytest.mark.parametrize("family", FAMILIES)
def test_ten_day_offer_records_next_before_own_candle_acquisition(family, tmp_path):
    near = _fact(family, date(2026, 10, 8))
    next_contract = _fact(family, date(2026, 11, 8))
    offer = prepare_mcx_contract_offer(RUN, family, (near, next_contract), observed_at=NOW)
    assert offer.days_to_verified_expiry == 10
    assert offer.selectable() == (McxSelectionRole.NEAR, McxSelectionRole.NEXT_ELIGIBLE)
    selection = choose_mcx_contract(
        offer, McxSelectionRole.NEXT_ELIGIBLE,
        sponsor_authorization_identity="ISOLATED-SPONSOR-AUTH",
        recorded_at=NOW + timedelta(seconds=1),
    )
    store = LocalMcxSponsorSelectionStore(tmp_path / "selection")
    path = store.retain(selection)
    assert store.retain(selection) == path
    assert store.load(RUN, family) == selection
    events = []

    def acquire(instrument):
        assert path.exists() and store.load(RUN, family) == selection
        events.append(instrument.trading_symbol)
        return (instrument.trading_symbol, instrument.expiry)

    result = acquire_selected_mcx_evidence(
        store, offer, (near.instrument, next_contract.instrument),
        acquired_at=NOW + timedelta(seconds=2), acquire=acquire,
    )
    assert result == (next_contract.instrument.trading_symbol, next_contract.instrument.expiry)
    assert events == [next_contract.instrument.trading_symbol]
    assert not list(tmp_path.rglob("*trade-plan*.json"))
    assert not list(tmp_path.rglob("*sponsor-decision*.json"))


def test_threshold_and_first_eligible_later_expiry(tmp_path):
    far_near = _fact(McxFamily.GOLDM, date(2026, 10, 9))
    november = _fact(McxFamily.GOLDM, date(2026, 11, 8))
    offer = prepare_mcx_contract_offer(RUN, McxFamily.GOLDM,
                                       (far_near, november), observed_at=NOW)
    assert offer.days_to_verified_expiry == 11
    assert offer.next_eligible is None
    with pytest.raises(ValueError, match="CHOICE_REJECTED"):
        choose_mcx_contract(offer, McxSelectionRole.NEXT_ELIGIBLE,
                            sponsor_authorization_identity="ISOLATED-SPONSOR-AUTH",
                            recorded_at=NOW)
    near = _fact(McxFamily.GOLDM, date(2026, 10, 8), delivery=False)
    first_later = _fact(McxFamily.GOLDM, date(2026, 11, 8), broker=False)
    second_later = _fact(McxFamily.GOLDM, date(2026, 12, 8))
    offer = prepare_mcx_contract_offer(RUN, McxFamily.GOLDM,
                                       (near, first_later, second_later), observed_at=NOW)
    assert offer.selectable() == (McxSelectionRole.NEXT_ELIGIBLE,)
    assert offer.next_eligible == second_later
    with pytest.raises(ValueError, match="CHOICE_REJECTED"):
        choose_mcx_contract(offer, McxSelectionRole.NEAR,
                            sponsor_authorization_identity="ISOLATED-SPONSOR-AUTH",
                            recorded_at=NOW)


@pytest.mark.parametrize("blocked", ("entry", "broker", "delivery", "master", "spec"))
def test_near_gates_block_choice_without_disabling_later_valid_contract(blocked):
    near = _fact(McxFamily.COPPER, date(2026, 10, 8), **{blocked: False})
    later = _fact(McxFamily.COPPER, date(2026, 11, 8))
    offer = prepare_mcx_contract_offer(RUN, McxFamily.COPPER, (near, later), observed_at=NOW)
    assert McxSelectionRole.NEAR not in offer.selectable()
    assert McxSelectionRole.NEXT_ELIGIBLE in offer.selectable()


def test_ambiguous_or_unverified_expiry_rejects_offer():
    near = _fact(McxFamily.CRUDEOIL, date(2026, 10, 8))
    with pytest.raises(ValueError, match="AMBIGUOUS"):
        prepare_mcx_contract_offer(RUN, McxFamily.CRUDEOIL, (near, near), observed_at=NOW)
    with pytest.raises(ValueError, match="UNVERIFIED"):
        prepare_mcx_contract_offer(RUN, McxFamily.CRUDEOIL,
                                   (replace(near, expiry_proof_sha256=None),), observed_at=NOW)


def test_selection_is_one_per_run_and_fails_closed_before_any_new_evidence(tmp_path):
    near = _fact(McxFamily.SILVERM, date(2026, 10, 8))
    later = _fact(McxFamily.SILVERM, date(2026, 11, 8))
    offer = prepare_mcx_contract_offer(RUN, McxFamily.SILVERM, (near, later), observed_at=NOW)
    store = LocalMcxSponsorSelectionStore(tmp_path / "selection")
    selected = choose_mcx_contract(offer, McxSelectionRole.NEAR,
                                   sponsor_authorization_identity="ISOLATED-SPONSOR-AUTH",
                                   recorded_at=NOW + timedelta(seconds=1))
    store.retain(selected)
    changed = choose_mcx_contract(offer, McxSelectionRole.NEXT_ELIGIBLE,
                                  sponsor_authorization_identity="ISOLATED-SPONSOR-AUTH",
                                  recorded_at=NOW + timedelta(seconds=1))
    with pytest.raises(ValueError, match="IMMUTABLE"):
        store.retain(changed)
    calls = []
    with pytest.raises(ValueError, match="MASTER_CHANGED"):
        acquire_selected_mcx_evidence(
            store, offer, (later.instrument,), acquired_at=NOW + timedelta(seconds=2),
            acquire=lambda instrument: calls.append(instrument),
        )
    assert calls == []
    with pytest.raises(ValueError, match="INELIGIBLE"):
        selected_mcx_instrument_before_acquisition(
            store, offer, (near.instrument, later.instrument),
            acquired_at=NOW + timedelta(days=6),
        )
    assert store.load(RUN, McxFamily.SILVERM) == selected


def test_new_run_choice_does_not_roll_or_rewrite_old_contract(tmp_path):
    family = McxFamily.NATURALGAS
    near = _fact(family, date(2026, 10, 8))
    later = _fact(family, date(2026, 11, 8))
    store = LocalMcxSponsorSelectionStore(tmp_path / "selection")
    original_offer = prepare_mcx_contract_offer(
        RUN, family, (near, later), observed_at=NOW,
    )
    original = choose_mcx_contract(
        original_offer, McxSelectionRole.NEAR,
        sponsor_authorization_identity="ISOLATED-SPONSOR-AUTH",
        recorded_at=NOW + timedelta(seconds=1),
    )
    original_path = store.retain(original)
    original_bytes = original_path.read_bytes()
    successor_run = "SWING-RUN-00000000000000000000000000000002"
    next_offer = prepare_mcx_contract_offer(
        successor_run, family, (near, later), observed_at=NOW,
    )
    successor = choose_mcx_contract(
        next_offer, McxSelectionRole.NEXT_ELIGIBLE,
        sponsor_authorization_identity="ISOLATED-SPONSOR-AUTH",
        recorded_at=NOW + timedelta(seconds=1),
    )
    store.retain(successor)
    assert store.load(RUN, family) == original
    assert original_path.read_bytes() == original_bytes
    assert store.load(successor_run, family) == successor
    assert original.trading_symbol != successor.trading_symbol


@pytest.mark.parametrize("native_intake", ["GOLDM-LINEAGE"], indirect=True)
def test_different_expiry_cannot_reuse_old_review_v2_handoff(native_intake, tmp_path):
    handoff, _, _ = handoff_fixture(native_intake, tmp_path)
    bound = handoff.bound
    assert bound.family is McxFamily.GOLDM
    expiry = date.fromisoformat(bound.derivative_expiry)
    near = _fact(McxFamily.GOLDM, expiry)
    later = _fact(McxFamily.GOLDM, date(expiry.year, expiry.month + 1, expiry.day))
    observed = datetime(expiry.year, expiry.month, expiry.day, 10, tzinfo=ZoneInfo("Asia/Kolkata"))
    # The fixture's retained Review/V2 is for near; a newly selected expiry
    # cannot inherit its chart, Answer, promotion or risk calculation.
    near = replace(near, master_valid_until=observed + timedelta(days=1),
                   entry_until=observed + timedelta(days=1),
                   delivery_start=observed + timedelta(days=1),
                   broker_entry_until=observed + timedelta(days=1))
    later = replace(later, master_valid_until=observed + timedelta(days=1),
                    entry_until=observed + timedelta(days=1),
                    delivery_start=observed + timedelta(days=1),
                    broker_entry_until=observed + timedelta(days=1))
    offer = prepare_mcx_contract_offer(bound.run_identity, McxFamily.GOLDM,
                                       (near, later), observed_at=observed)
    selection = choose_mcx_contract(offer, McxSelectionRole.NEXT_ELIGIBLE,
                                    sponsor_authorization_identity="ISOLATED-SPONSOR-AUTH",
                                    recorded_at=observed + timedelta(seconds=1))
    with pytest.raises(ValueError, match="REVIEW_V2_CONTRACT_MISMATCH"):
        require_mcx_choice_matches_handoff(selection, handoff)


def test_swing_daily_builder_uses_five_durable_choices_before_mcx_candles(
    monkeypatch, tmp_path,
):
    master = []
    choices = {}
    events = []
    for family in FAMILIES:
        near = _fact(family, date(2026, 10, 8))
        later = _fact(family, date(2026, 11, 8))
        offer = prepare_mcx_contract_offer(RUN, family, (near, later), observed_at=NOW)
        store = LocalMcxSponsorSelectionStore(tmp_path / family.value)
        store.retain(choose_mcx_contract(
            offer, McxSelectionRole.NEXT_ELIGIBLE,
            sponsor_authorization_identity="ISOLATED-SPONSOR-AUTH",
            recorded_at=NOW + timedelta(seconds=1),
        ))
        choices[family] = (offer, store)
        master.extend((near.instrument, later.instrument))

    class Instruments:
        def __init__(self, _capability):
            pass

        def retrieve(self, exchange):
            return tuple(master) if exchange == "MCX" else ()

        def resolve_from_records(self, _master, _request):
            events.append("NSE_SHARED_RESOLVER")
            return "NSE_UNCHANGED"

    class MarketData:
        def __init__(self, _capability):
            pass

    def daily(_universe, *, resolve_instrument, **_kwargs):
        member = SimpleNamespace(asset_class=SwingUniverseAssetClass.NSE_EQUITY,
                                 canonical_identity="RELIANCE")
        assert resolve_instrument(member) == "NSE_UNCHANGED"
        for family in FAMILIES:
            member = SimpleNamespace(asset_class=SwingUniverseAssetClass.MCX_COMMODITY,
                                     canonical_identity=family.value)
            selected = resolve_instrument(member)
            assert selected.expiry == date(2026, 11, 8)
            assert choices[family][1].load(RUN, family).trading_symbol == selected.trading_symbol
            events.append(family.value)
        raise RuntimeError("STOP_AFTER_PRE_ACQUISITION_PROOF")

    monkeypatch.setattr(app, "KiteInstrumentProvider", Instruments)
    monkeypatch.setattr(app, "KiteMarketDataProvider", MarketData)
    monkeypatch.setattr(app, "build_swing_daily_dataset", daily)
    with pytest.raises(RuntimeError, match="STOP_AFTER_PRE_ACQUISITION_PROOF"):
        app.build_completed_swing_analysis(
            SimpleNamespace(active=True), analysis_run_identity="ANALYSIS-000001",
            swing_analysis_run_identity=RUN, now=NOW + timedelta(seconds=2),
            pace=lambda: None, mcx_contract_choices=choices,
        )
    assert events == ["NSE_SHARED_RESOLVER", *(family.value for family in FAMILIES)]


def test_swing_daily_builder_rejects_missing_choice_before_any_candle(
    monkeypatch, tmp_path,
):
    master = []
    choices = {}
    for family in FAMILIES:
        near = _fact(family, date(2026, 10, 8))
        later = _fact(family, date(2026, 11, 8))
        offer = prepare_mcx_contract_offer(RUN, family, (near, later), observed_at=NOW)
        store = LocalMcxSponsorSelectionStore(tmp_path / family.value)
        if family is not McxFamily.SILVERM:
            store.retain(choose_mcx_contract(
                offer, McxSelectionRole.NEAR,
                sponsor_authorization_identity="ISOLATED-SPONSOR-AUTH",
                recorded_at=NOW + timedelta(seconds=1),
            ))
        choices[family] = (offer, store)
        master.extend((near.instrument, later.instrument))
    calls = []

    class Instruments:
        def __init__(self, _capability):
            pass

        def retrieve(self, exchange):
            return tuple(master) if exchange == "MCX" else ()

    class MarketData:
        def __init__(self, _capability):
            pass

    monkeypatch.setattr(app, "KiteInstrumentProvider", Instruments)
    monkeypatch.setattr(app, "KiteMarketDataProvider", MarketData)
    monkeypatch.setattr(app, "build_swing_daily_dataset", lambda *_a, **_k: calls.append("daily"))
    with pytest.raises(ValueError, match="MCX_SPONSOR_SELECTION_INTEGRITY_INVALID"):
        app.build_completed_swing_analysis(
            SimpleNamespace(active=True), analysis_run_identity="ANALYSIS-000001",
            swing_analysis_run_identity=RUN, now=NOW + timedelta(seconds=2),
            pace=lambda: None, mcx_contract_choices=choices,
        )
    assert calls == []
