from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from kronos.instrument.runtime import (
    ExecutionContextAvailability,
    InstrumentFreshness,
    ProviderBindingStatus,
    create_canonical_instrument,
    create_provider_assertion,
    create_provider_binding_directive,
    price_precision_for_tick,
    publish_runtime_instruments,
)


IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 8, 17, 9, 0, tzinfo=IST)


def _canonical(
    identity: str = "NIFTY",
    *,
    tick: Decimal | None = Decimal("0.05"),
    lot: int | None = 1,
    valid_through: datetime | None = None,
):  # type: ignore[no-untyped-def]
    return create_canonical_instrument(
        canonical_instrument_id=identity,
        exchange="NSE",
        segment="INDICES",
        instrument_type="EQ",
        canonical_tick_size=tick,
        canonical_lot_size=lot,
        canonical_source_identity="GOVERNED-CANONICAL-UNIVERSE-V1",
        source_boundary=NOW - timedelta(days=1),
        valid_through=valid_through or NOW + timedelta(days=1),
    )


def _assertion(
    symbol: str = "NIFTY 50",
    token: int = 256265,
    *,
    valid_through: datetime | None = None,
):  # type: ignore[no-untyped-def]
    return create_provider_assertion(
        provider="KITE",
        provider_symbol=symbol,
        provider_instrument_token=token,
        exchange="NSE",
        segment="INDICES",
        instrument_type="EQ",
        asserted_tick_size=Decimal("0.05"),
        asserted_lot_size=1,
        binding_source_identity="KITE-INSTRUMENT-MASTER-20260817",
        source_boundary=NOW - timedelta(hours=1),
        valid_through=valid_through or NOW + timedelta(days=1),
    )


def _directive(identity: str = "NIFTY", symbol: str = "NIFTY 50"):  # type: ignore[no-untyped-def]
    return create_provider_binding_directive(
        canonical_instrument_id=identity,
        provider="KITE",
        provider_symbol=symbol,
        directive_source_identity="GOVERNED-PROVIDER-BINDINGS-V1",
    )


@pytest.mark.parametrize(
    ("tick", "precision"),
    [
        (Decimal("1"), 0),
        (Decimal("0.5"), 1),
        (Decimal("0.05"), 2),
        (Decimal("0.0025"), 4),
        (None, None),
    ],
)
def test_price_precision_is_minimum_exact_decimal_precision(
    tick: Decimal | None,
    precision: int | None,
) -> None:
    assert price_precision_for_tick(tick) == precision


def test_publisher_separates_canonical_meaning_and_typed_provider_binding() -> None:
    registry = publish_runtime_instruments(
        canonical_instruments=(_canonical(),),
        provider_assertions=(_assertion(),),
        binding_directives=(_directive(),),
        observed_at=NOW,
    )
    published = registry.require_consumable("NIFTY")

    assert published.canonical.canonical_instrument_id == "NIFTY"
    assert published.canonical.canonical_tick_size == Decimal("0.05")
    assert published.canonical.canonical_price_precision == 2
    assert published.binding_status is ProviderBindingStatus.BOUND
    assert published.provider_binding is not None
    assert published.provider_binding.provider_symbol == "NIFTY 50"
    assert published.provider_binding.provider_instrument_token == 256265
    assert "256265" not in published.canonical.integrity_identity
    assert published.execution_context is ExecutionContextAvailability.COMPLETE


def test_missing_tick_or_binding_publishes_incomplete_not_invented_facts() -> None:
    missing_tick = publish_runtime_instruments(
        canonical_instruments=(_canonical(tick=None),),
        provider_assertions=(),
        binding_directives=(),
        observed_at=NOW,
    ).lookup("NIFTY")
    missing_binding = publish_runtime_instruments(
        canonical_instruments=(_canonical(),),
        provider_assertions=(),
        binding_directives=(),
        observed_at=NOW,
    ).lookup("NIFTY")

    assert missing_tick.canonical.canonical_price_precision is None
    assert missing_tick.execution_context is ExecutionContextAvailability.INCOMPLETE
    assert missing_binding.binding_status is ProviderBindingStatus.UNAVAILABLE
    with pytest.raises(ValueError, match="RUNTIME_INSTRUMENT_INCOMPLETE"):
        publish_runtime_instruments(
            canonical_instruments=(_canonical(),),
            provider_assertions=(),
            binding_directives=(),
            observed_at=NOW,
        ).require_consumable("NIFTY")


def test_stale_canonical_or_provider_binding_fails_consumption_closed() -> None:
    stale_assertion = _assertion(valid_through=NOW - timedelta(minutes=1))
    stale_binding = publish_runtime_instruments(
        canonical_instruments=(_canonical(),),
        provider_assertions=(stale_assertion,),
        binding_directives=(_directive(),),
        observed_at=NOW,
    ).lookup("NIFTY")
    stale_canonical = publish_runtime_instruments(
        canonical_instruments=(
            _canonical(valid_through=NOW - timedelta(minutes=1)),
        ),
        provider_assertions=(),
        binding_directives=(),
        observed_at=NOW,
    ).lookup("NIFTY")

    assert stale_binding.binding_status is ProviderBindingStatus.STALE
    assert stale_binding.provider_binding is not None
    assert stale_binding.execution_context is ExecutionContextAvailability.INCOMPLETE
    assert stale_canonical.canonical_freshness is InstrumentFreshness.STALE


def test_invalid_tick_lot_and_integrity_are_rejected() -> None:
    with pytest.raises(ValueError, match="CANONICAL_TICK_SIZE_INVALID"):
        _canonical(tick=Decimal("-0.05"))
    with pytest.raises(ValueError, match="CANONICAL_INSTRUMENT_INVALID"):
        _canonical(lot=0)
    with pytest.raises(ValueError, match="CANONICAL_INSTRUMENT_INVALID"):
        replace(_canonical(), integrity_identity="CANONICAL-INSTRUMENT-tampered")


def test_duplicates_conflicts_and_provider_token_reuse_are_rejected() -> None:
    canonical = _canonical()
    with pytest.raises(ValueError, match="CANONICAL_INSTRUMENT_DUPLICATE"):
        publish_runtime_instruments(
            canonical_instruments=(canonical, canonical),
            provider_assertions=(),
            binding_directives=(),
            observed_at=NOW,
        )
    with pytest.raises(ValueError, match="PROVIDER_ASSERTION_DUPLICATE"):
        publish_runtime_instruments(
            canonical_instruments=(canonical,),
            provider_assertions=(_assertion(), _assertion()),
            binding_directives=(),
            observed_at=NOW,
        )
    with pytest.raises(ValueError, match="PROVIDER_TOKEN_CONFLICT"):
        publish_runtime_instruments(
            canonical_instruments=(canonical,),
            provider_assertions=(_assertion(), _assertion("OTHER", 256265)),
            binding_directives=(),
            observed_at=NOW,
        )
    with pytest.raises(ValueError, match="PROVIDER_BINDING_CONFLICT"):
        publish_runtime_instruments(
            canonical_instruments=(canonical, _canonical("BANK NIFTY")),
            provider_assertions=(_assertion(),),
            binding_directives=(_directive(), _directive("BANK NIFTY")),
            observed_at=NOW,
        )


def test_provider_assertion_mismatch_does_not_become_canonical_truth() -> None:
    assertion = create_provider_assertion(
        provider="KITE",
        provider_symbol="NIFTY 50",
        provider_instrument_token=256265,
        exchange="NSE",
        segment="NSE",
        instrument_type="EQ",
        asserted_tick_size=Decimal("0.05"),
        asserted_lot_size=1,
        binding_source_identity="KITE-INSTRUMENT-MASTER-20260817",
        source_boundary=NOW - timedelta(hours=1),
        valid_through=NOW + timedelta(days=1),
    )
    published = publish_runtime_instruments(
        canonical_instruments=(_canonical(),),
        provider_assertions=(assertion,),
        binding_directives=(_directive(),),
        observed_at=NOW,
    ).lookup("NIFTY")

    assert published.binding_status is ProviderBindingStatus.UNAVAILABLE
    assert published.provider_binding is None
    assert published.execution_context is ExecutionContextAvailability.INCOMPLETE
