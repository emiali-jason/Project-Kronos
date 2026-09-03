from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict, replace
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

from kronos.intraday.wo17 import (
    WO17_AUTHORITY,
    WO17_CONTRACT_VERSION,
    WO17_POLICY_CHECKSUM,
    WO17_POLICY_IDENTITY,
    WO17_POLICY_VERSION,
    WO17_PRODUCT_IDENTITY,
    Wo17ContractError,
    Wo17PolicyBinding,
    canonical_document_bytes,
    wo17_policy_from_dict,
)


def test_policy_identity_version_checksum_and_cardinality_are_exact() -> None:
    policy = Wo17PolicyBinding()
    assert (
        policy.product_identity,
        policy.policy_identity,
        policy.policy_version,
        policy.policy_checksum,
        policy.authority,
    ) == (
        WO17_PRODUCT_IDENTITY,
        WO17_POLICY_IDENTITY,
        WO17_POLICY_VERSION,
        WO17_POLICY_CHECKSUM,
        WO17_AUTHORITY,
    )
    assert policy.maximum_non_closed_positions_per_subject == 1
    assert policy.prior_session_non_closed_position_blocks_activation
    assert policy.successor_wo16_evidence_may_coexist
    assert policy.automatic_mcx_roll_migration == "PROHIBITED"


def test_slice1_policy_has_no_operational_authority() -> None:
    policy = Wo17PolicyBinding()
    assert not any(
        value
        for name, value in asdict(policy).items()
        if name.endswith("_authority")
    )


def test_governed_policy_payload_checksum_matches_constant() -> None:
    path = (
        Path(__file__).resolve().parents[3]
        / "docs/architecture/products/intraday"
        / "KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-"
        "MONITORING-POLICY-V1.json"
    )
    assert sha256(path.read_bytes()).hexdigest() == WO17_POLICY_CHECKSUM


def test_policy_is_immutable_and_rejects_changed_governance() -> None:
    policy = Wo17PolicyBinding()
    with pytest.raises(FrozenInstanceError):
        policy.policy_version = "2.0.0"
    with pytest.raises(Wo17ContractError, match="WO17_POLICY_BINDING_INVALID"):
        replace(policy, maximum_non_closed_positions_per_subject=2)


def test_canonical_json_preserves_exact_decimals_and_aware_timestamps() -> None:
    timestamp = datetime.fromisoformat("2026-09-03T10:15:30+05:30")
    value = {"price": Decimal("101.2500"), "observed_at": timestamp}
    encoded = canonical_document_bytes(value)
    assert encoded == (
        b'{"observed_at":"2026-09-03T10:15:30+05:30","price":"101.2500"}'
    )
    assert encoded == canonical_document_bytes(value)


@pytest.mark.parametrize(
    ("value", "reason"),
    (
        ({"price": 101.25}, "WO17_FLOAT_PROHIBITED"),
        ({"price": Decimal("NaN")}, "WO17_DECIMAL_INVALID"),
        (
            {"observed_at": datetime(2026, 9, 3, 10, 15)},
            "WO17_TIMESTAMP_TIMEZONE_REQUIRED",
        ),
    ),
)
# type annotations are intentionally omitted for compact parametrized fixtures.
def test_invalid_numeric_or_time_representation_fails_closed(
    value, reason
) -> None:
    with pytest.raises(Wo17ContractError, match=reason):
        canonical_document_bytes(value)


def test_unknown_missing_and_extra_policy_fields_are_rejected() -> None:
    values = asdict(Wo17PolicyBinding())
    values.pop("policy_identity")
    with pytest.raises(Wo17ContractError, match="WO17_CONTRACT_FIELDS_INVALID"):
        wo17_policy_from_dict(values)
    values = asdict(Wo17PolicyBinding())
    values["unknown_authority"] = False
    with pytest.raises(Wo17ContractError, match="WO17_CONTRACT_FIELDS_INVALID"):
        wo17_policy_from_dict(values)


def test_contract_version_is_frozen() -> None:
    assert WO17_CONTRACT_VERSION == "1.0.0"
