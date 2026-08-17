from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.contracts import create_intraday_run
from kronos.intraday.instrument import (
    InstrumentExecutionMetadata,
    IntradayInstrumentRegistry,
    adapt_instrument_reference,
)
from kronos.provider.contracts.instrument import InstrumentRecord


IST = ZoneInfo("Asia/Kolkata")


def _record(symbol: str = "RELIANCE") -> InstrumentRecord:
    return InstrumentRecord("KITE", "NSE", "NSE", symbol, symbol, "EQ", None)


def _metadata(token: int = 738561) -> InstrumentExecutionMetadata:
    return InstrumentExecutionMetadata(token, Decimal("0.05"), 1, 2)


def test_run_identity_is_unique_versioned_and_observation_bound() -> None:
    created = datetime(2026, 8, 17, 9, 0, tzinfo=IST)
    observed = datetime(2026, 8, 17, 9, 16, tzinfo=IST)
    first = create_intraday_run(created_at=created, observation_boundary=observed)
    second = create_intraday_run(created_at=created, observation_boundary=observed)

    assert first.run_id.startswith("INTRADAY-RUN-")
    assert first.run_id != second.run_id
    assert first.observation_boundary.observed_at == observed
    with pytest.raises(ValueError, match="INTRADAY_RUN_INVALID"):
        create_intraday_run(created_at=observed, observation_boundary=created)


def test_instrument_adapter_preserves_mapping_and_execution_facts() -> None:
    reference = adapt_instrument_reference(
        canonical_instrument_id="RELIANCE",
        provider_record=_record(),
        execution_metadata=_metadata(),
    )

    assert reference.canonical_instrument_id == "RELIANCE"
    assert reference.provider_symbol == "RELIANCE"
    assert reference.provider_instrument_token == 738561
    assert reference.tick_size == Decimal("0.05")
    assert reference.lot_size == 1
    assert reference.price_precision == 2
    assert "738561" not in repr(reference)
    assert adapt_instrument_reference(
        canonical_instrument_id="RELIANCE",
        provider_record=_record(),
        execution_metadata=_metadata(),
    ).mapping_identity == reference.mapping_identity


def test_instrument_metadata_and_unavailable_mapping_fail_closed() -> None:
    with pytest.raises(ValueError, match="INSTRUMENT_EXECUTION_METADATA_INVALID"):
        InstrumentExecutionMetadata(1, Decimal("0.05"), 0, 2)
    with pytest.raises(ValueError, match="INSTRUMENT_EXECUTION_METADATA_INVALID"):
        InstrumentExecutionMetadata(1, Decimal("0.005"), 1, 2)
    registry = IntradayInstrumentRegistry((
        adapt_instrument_reference(
            canonical_instrument_id="RELIANCE",
            provider_record=_record(),
            execution_metadata=_metadata(),
        ),
    ))
    with pytest.raises(ValueError, match="INTRADAY_INSTRUMENT_MAPPING_UNAVAILABLE"):
        registry.resolve("MISSING")


def test_registry_rejects_duplicate_conflicting_mappings() -> None:
    reference = adapt_instrument_reference(
        canonical_instrument_id="RELIANCE",
        provider_record=_record(),
        execution_metadata=_metadata(),
    )
    assert IntradayInstrumentRegistry((reference, reference)).references == (reference,)

    changed = adapt_instrument_reference(
        canonical_instrument_id="RELIANCE",
        provider_record=_record(),
        execution_metadata=InstrumentExecutionMetadata(738561, Decimal("0.05"), 2, 2),
    )
    with pytest.raises(ValueError, match="INTRADAY_INSTRUMENT_MAPPING_CONFLICT"):
        IntradayInstrumentRegistry((reference, changed))

    other = adapt_instrument_reference(
        canonical_instrument_id="OTHER",
        provider_record=_record("OTHER"),
        execution_metadata=_metadata(),
    )
    with pytest.raises(ValueError, match="INTRADAY_INSTRUMENT_MAPPING_CONFLICT"):
        IntradayInstrumentRegistry((reference, other))
