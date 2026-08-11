from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

import kronos.swing.universe as universe_module
from kronos.swing.universe import (
    SWING_PHASE1_UNIVERSE,
    SwingUniverseAssetClass,
    SwingUniverseError,
    SwingUniverseFailure,
    enabled_swing_phase1_universe,
    load_swing_phase1_universe,
)


REQUIRED = {
    "NIFTY",
    "BANK NIFTY",
    "GOLDM",
    "SILVERM",
    "COPPER",
    "CRUDEOIL",
    "NATURALGAS",
}


def test_canonical_universe_has_exact_approved_composition() -> None:
    universe = enabled_swing_phase1_universe()

    assert universe is SWING_PHASE1_UNIVERSE
    assert len(universe) == 98
    assert sum(
        member.asset_class is SwingUniverseAssetClass.NSE_EQUITY
        for member in universe
    ) == 91
    assert sum(
        member.asset_class is SwingUniverseAssetClass.NSE_INDEX
        for member in universe
    ) == 2
    assert sum(
        member.asset_class is SwingUniverseAssetClass.MCX_COMMODITY
        for member in universe
    ) == 5
    identities = tuple(member.canonical_identity for member in universe)
    assert len(set(identities)) == 98
    assert REQUIRED.issubset(identities)


def test_universe_order_is_source_order_then_indices_then_commodities() -> None:
    identities = tuple(
        member.canonical_identity for member in enabled_swing_phase1_universe()
    )

    assert identities[:3] == ("IOC", "HINDPETRO", "BPCL")
    assert identities[88:91] == ("HINDALCO", "IDEA", "VBL")
    assert identities[91:] == (
        "NIFTY",
        "BANK NIFTY",
        "GOLDM",
        "SILVERM",
        "COPPER",
        "CRUDEOIL",
        "NATURALGAS",
    )
    assert load_swing_phase1_universe() == enabled_swing_phase1_universe()


def test_universe_is_immutable_and_contains_no_provider_material() -> None:
    universe = enabled_swing_phase1_universe()
    member_fields = {field.name for field in fields(type(universe[0]))}

    assert type(universe) is tuple
    assert member_fields == {"canonical_identity", "asset_class"}
    assert not member_fields.intersection(
        {"instrument_token", "provider_token", "raw_record", "kite_client"}
    )
    with pytest.raises(FrozenInstanceError):
        universe[0].canonical_identity = "MUTATED"  # type: ignore[misc]


def test_commodity_identities_do_not_freeze_expiring_contracts() -> None:
    commodities = tuple(
        member.canonical_identity
        for member in enabled_swing_phase1_universe()
        if member.asset_class is SwingUniverseAssetClass.MCX_COMMODITY
    )

    assert commodities == (
        "GOLDM",
        "SILVERM",
        "COPPER",
        "CRUDEOIL",
        "NATURALGAS",
    )
    assert all(not any(character.isdigit() for character in item) for item in commodities)
    assert all(not item.endswith("FUT") for item in commodities)


def test_duplicate_equity_source_fails_closed(tmp_path: Path) -> None:
    rows = [f"SYMBOL{index}" for index in range(90)] + ["SYMBOL0"]
    source = tmp_path / "equities.csv"
    source.write_text("symbol\n" + "\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(SwingUniverseError) as captured:
        load_swing_phase1_universe(source)

    assert captured.value.failure is SwingUniverseFailure.DUPLICATE_IDENTITY


@pytest.mark.parametrize(
    ("content", "failure"),
    [
        ("Symbol\nRELIANCE\n", SwingUniverseFailure.MALFORMED_SOURCE),
        ("symbol\ninvalid symbol\n", SwingUniverseFailure.MALFORMED_SOURCE),
        (
            "symbol\n" + "\n".join(f"SYMBOL{index}" for index in range(90)) + "\n",
            SwingUniverseFailure.EQUITY_COUNT_MISMATCH,
        ),
    ],
)
def test_malformed_or_incomplete_equity_source_fails_closed(
    tmp_path: Path,
    content: str,
    failure: SwingUniverseFailure,
) -> None:
    source = tmp_path / "equities.csv"
    source.write_text(content, encoding="utf-8")

    with pytest.raises(SwingUniverseError) as captured:
        load_swing_phase1_universe(source)

    assert captured.value.failure is failure


def test_missing_required_fixed_identity_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(universe_module, "_INDICES", universe_module._INDICES[:1])

    with pytest.raises(SwingUniverseError) as captured:
        load_swing_phase1_universe()

    assert captured.value.failure is SwingUniverseFailure.REQUIRED_IDENTITY_MISSING
