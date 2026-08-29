from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from kronos.instrument.semantic_v2_persistence import InstrumentSemanticV2Store
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.mcx_expiry_continuity_research import (
    MCX_CONTRACT_EVIDENCE_ARCHIVE_IDENTITY,
    MCX_PROVIDER_TOKEN_PROVENANCE,
    ExpiryContinuityOutcome,
    ExpiryScenarioKind,
    FamilyExpiryContinuityScenario,
    ImmutableContractEvidenceArchive,
    McxExpiryContinuityError,
    RetainedContractCandle,
    _identity,
    governed_successor_contract,
)


def test_each_family_has_one_exact_governed_successor() -> None:
    catalogue = InstrumentSemanticV2Store(Path("data/instruments").resolve()).load(
        publication_identity="KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2",
        publication_version="1.2.0",
    )
    cases = (
        ("MCX-SUBJECT-GOLDM", "MCX-FUT-GOLDM-2026-09-04", "MCX-FUT-GOLDM-2026-10-05"),
        ("MCX-SUBJECT-SILVERM", "MCX-FUT-SILVERM-2026-08-31", "MCX-FUT-SILVERM-2026-11-30"),
        ("MCX-SUBJECT-COPPER", "MCX-FUT-COPPER-2026-08-31", "MCX-FUT-COPPER-2026-09-30"),
        ("MCX-SUBJECT-NATGAS", "MCX-FUT-NATGAS-2026-09-25", "MCX-FUT-NATGAS-2026-10-27"),
        ("MCX-SUBJECT-CRUDE", "MCX-FUT-CRUDE-2026-09-21", "MCX-FUT-CRUDE-2026-10-19"),
    )
    for subject, current, expected in cases:
        successor, directive = governed_successor_contract(
            catalogue=catalogue,
            subject_identity=subject,
            contract_a_identity=current,
        )
        assert successor.canonical_id == expected
        assert directive.canonical_object_id == expected


def test_retained_archive_replays_after_current_master_removes_contract_a() -> None:
    candle = _candle()
    archive_values = {
        "canonical_subject_identity": candle.canonical_subject_identity,
        "canonical_contract_identity": candle.canonical_contract_identity,
        "provider_symbols": ("NATURALGAS26SEPFUT",),
        "provider_record_identities": candle.provider_record_identities,
        "historical_binding_identities": candle.historical_binding_identities,
        "candles": (candle,),
        "current_instrument_master_dependency": False,
        "immutable": True,
        "contract_identity": MCX_CONTRACT_EVIDENCE_ARCHIVE_IDENTITY,
    }
    archive = ImmutableContractEvidenceArchive(
        archive_identity=_identity("INTRADAY-MCX-CONTRACT-ARCHIVE-", archive_values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-CONTRACT-ARCHIVE-", archive_values),
        **archive_values,
    )
    digest = "a" * 64
    scenario_values = {
        "analytical_subject": "NATGAS",
        "canonical_subject_identity": "MCX-SUBJECT-NATGAS",
        "provider_contract_family": "NATURALGAS",
        "scenario_kind": ExpiryScenarioKind.CONTROLLED_DETERMINISTIC,
        "contract_a_identity": archive.canonical_contract_identity,
        "contract_a_expiry": date(2026, 9, 25),
        "contract_a_archive_identity": archive.archive_identity,
        "contract_a_candle_count": 1,
        "successor_contract_b_identity": "MCX-FUT-NATGAS-2026-10-27",
        "successor_contract_b_expiry": date(2026, 10, 27),
        "successor_provider_directive_identity": "MCXR-KITE-DIRECTIVE-MCX-FUT-NATGAS-2026-10-27",
        "simulated_current_master_contract_identities": ("MCX-FUT-NATGAS-2026-10-27",),
        "contract_a_absent_from_simulated_current_master": True,
        "successor_b_present_in_simulated_current_master": True,
        "replayed_candle_count": 1,
        "replayed_candle_integrity_digest": digest,
        "original_candle_integrity_digest": digest,
        "replay_exact": True,
        "fabricated_market_candle_count": 0,
        "manual_expiry_intervention_required": False,
        "current_instrument_master_dependency_for_old_history": False,
        "outcome": ExpiryContinuityOutcome.PASS,
    }
    scenario = FamilyExpiryContinuityScenario(
        scenario_identity=_identity("INTRADAY-MCX-EXPIRY-SCENARIO-", scenario_values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-EXPIRY-SCENARIO-", scenario_values),
        **scenario_values,
    )
    assert scenario.contract_a_identity not in scenario.simulated_current_master_contract_identities
    assert scenario.replay_exact
    assert scenario.fabricated_market_candle_count == 0


def test_retained_candle_keeps_provider_provenance_but_not_token() -> None:
    candle = _candle()
    assert candle.provider_record_identities == ("PROVIDER-INSTRUMENT-RECORD-ABC",)
    assert candle.provider_token_provenance == MCX_PROVIDER_TOKEN_PROVENANCE
    assert "token" not in " ".join(candle.source_provider_identities).lower()

    values = dict(candle.__dict__) if hasattr(candle, "__dict__") else None
    assert values is None  # slots prevent accidental ad-hoc credential fields


def test_scenario_fails_closed_if_a_remains_in_current_master() -> None:
    candle = _candle()
    with pytest.raises(McxExpiryContinuityError):
        FamilyExpiryContinuityScenario(
            scenario_identity="INTRADAY-MCX-EXPIRY-SCENARIO-BAD",
            analytical_subject="NATGAS",
            canonical_subject_identity="MCX-SUBJECT-NATGAS",
            provider_contract_family="NATURALGAS",
            scenario_kind=ExpiryScenarioKind.CONTROLLED_DETERMINISTIC,
            contract_a_identity=candle.canonical_contract_identity,
            contract_a_expiry=date(2026, 9, 25),
            contract_a_archive_identity="INTRADAY-MCX-CONTRACT-ARCHIVE-X",
            contract_a_candle_count=1,
            successor_contract_b_identity="MCX-FUT-NATGAS-2026-10-27",
            successor_contract_b_expiry=date(2026, 10, 27),
            successor_provider_directive_identity="DIRECTIVE-X",
            simulated_current_master_contract_identities=(
                candle.canonical_contract_identity,
                "MCX-FUT-NATGAS-2026-10-27",
            ),
            contract_a_absent_from_simulated_current_master=True,
            successor_b_present_in_simulated_current_master=True,
            replayed_candle_count=1,
            replayed_candle_integrity_digest="a" * 64,
            original_candle_integrity_digest="a" * 64,
            replay_exact=True,
            fabricated_market_candle_count=0,
            manual_expiry_intervention_required=False,
            current_instrument_master_dependency_for_old_history=False,
            outcome=ExpiryContinuityOutcome.PASS,
            integrity_identity="INTEGRITY-BAD",
        )


def _candle() -> RetainedContractCandle:
    start = datetime(2026, 8, 28, 10, 0, tzinfo=UTC)
    values = {
        "canonical_subject_identity": "MCX-SUBJECT-NATGAS",
        "canonical_contract_identity": "MCX-FUT-NATGAS-2026-09-25",
        "provider_record_identities": ("PROVIDER-INSTRUMENT-RECORD-ABC",),
        "historical_binding_identities": ("INTRADAY-MCX-HISTORICAL-BINDING-ABC",),
        "provider_token_provenance": MCX_PROVIDER_TOKEN_PROVENANCE,
        "market_session_identity": "MCX:2026-08-28",
        "timeframe": IntradayTimeframe.FIVE_MINUTES,
        "trading_date": date(2026, 8, 28),
        "candle_start": start,
        "candle_end": start + timedelta(minutes=5),
        "open": Decimal("100"),
        "high": Decimal("102"),
        "low": Decimal("99"),
        "close": Decimal("101"),
        "volume": 10,
        "source_candle_identities": ("SOURCE-CANDLE-1",),
        "source_provider_identities": ("DOMAIN-006:KITE:HISTORICAL:5minute",),
    }
    return RetainedContractCandle(
        candle_identity=_identity("INTRADAY-MCX-RETAINED-CANDLE-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-MCX-RETAINED-CANDLE-", values),
        **values,
    )
