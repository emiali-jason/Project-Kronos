"""Factual MCX unit geometry and request-bound Swing candle lineage.

This is preparatory evidence, not MCX Step-31 or Sponsor authority.  The
normalized Swing historical response contains no Provider record identity;
therefore request binding alone can never certify a current derivative.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
import re

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.market_data import (
    HistoricalCandle,
    HistoricalCandleRequest,
    HistoricalInterval,
)
from kronos.swing.run_identity import is_swing_analysis_run_id


class McxFamily(StrEnum):
    GOLDM = "GOLDM"
    SILVERM = "SILVERM"
    COPPER = "COPPER"
    CRUDEOIL = "CRUDEOIL"
    NATURALGAS = "NATURALGAS"


MCX_SWING_FAMILIES = frozenset(family.value for family in McxFamily)
_MONTH_CODES = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)


class McxSettlement(StrEnum):
    PHYSICAL = "PHYSICAL"
    CASH = "CASH"


class McxEntryFactState(StrEnum):
    """A request lineage is not a verified Provider-master publication."""

    MASTER_AND_SPECIFICATION_UNVERIFIED = "MASTER_AND_SPECIFICATION_UNVERIFIED"


@dataclass(frozen=True, slots=True)
class McxUnitProfile:
    family: McxFamily
    trading_quantity: Decimal
    trading_unit: str
    quotation_quantity: Decimal
    quotation_unit: str
    tick_in_quotation_units: Decimal
    settlement: McxSettlement
    exchange_specification_url: str
    specification_series: str
    verified_specification_sha256: None = None
    provider_order_quantity_semantics: None = None
    approved_entry_blackout_identity: None = None

    def __post_init__(self) -> None:
        if (
            type(self.family) is not McxFamily
            or any(
                type(value) is not Decimal or not value.is_finite() or value <= 0
                for value in (
                    self.trading_quantity,
                    self.quotation_quantity,
                    self.tick_in_quotation_units,
                )
            )
            or self.trading_unit != self.quotation_unit
            or type(self.settlement) is not McxSettlement
            or not self.exchange_specification_url.startswith(
                "https://www.mcxindia.com/"
            )
            or not self.specification_series
            or self.verified_specification_sha256 is not None
            or self.provider_order_quantity_semantics is not None
            or self.approved_entry_blackout_identity is not None
        ):
            raise ValueError("MCX_UNIT_PROFILE_INVALID")

    @property
    def permits_new_entry(self) -> bool:
        return False

    @property
    def quotation_multiplier_per_lot(self) -> Decimal:
        return self.trading_quantity / self.quotation_quantity

    @property
    def rupees_per_tick_per_lot(self) -> Decimal:
        return self.tick_in_quotation_units * self.quotation_multiplier_per_lot

    def illustrative_price_exposure(
        self, *, entry: Decimal, stop: Decimal, lots: int
    ) -> tuple[Decimal, Decimal]:
        """Return quote-unit arithmetic, never admission or actual loss risk."""

        if (
            type(entry) is not Decimal
            or type(stop) is not Decimal
            or not entry.is_finite()
            or not stop.is_finite()
            or entry <= 0
            or stop <= 0
            or type(lots) is not int
            or lots <= 0
        ):
            raise ValueError("MCX_PRICE_EXPOSURE_INPUT_INVALID")
        quantity = Decimal(lots) * self.quotation_multiplier_per_lot
        return entry * quantity, abs(entry - stop) * quantity


_MCX_SPECIFICATIONS = {
    McxFamily.GOLDM: McxUnitProfile(
        McxFamily.GOLDM, Decimal("100"), "g", Decimal("10"), "g",
        Decimal("1"), McxSettlement.PHYSICAL,
        "https://www.mcxindia.com/docs/default-source/about-us/gold-mini-august-2026-contract-onwards8a79913a-e8de-4136-9f0b-25d31dc163c4.pdf",
        "GOLD-MINI-AUGUST-2026-ONWARDS",
    ),
    McxFamily.SILVERM: McxUnitProfile(
        McxFamily.SILVERM, Decimal("5"), "kg", Decimal("1"), "kg",
        Decimal("1"), McxSettlement.PHYSICAL,
        "https://www.mcxindia.com/docs/default-source/about-us/silver-mini-august-2026-contract-onwards.pdf",
        "SILVER-MINI-AUGUST-NOVEMBER-2026",
    ),
    McxFamily.COPPER: McxUnitProfile(
        McxFamily.COPPER, Decimal("2500"), "kg", Decimal("1"), "kg",
        Decimal("0.05"), McxSettlement.PHYSICAL,
        "https://www.mcxindia.com/docs/default-source/products/contract-specification/copper/copper-may-2026-contracts-onwards.pdf",
        "COPPER-MAY-2026-ONWARDS",
    ),
    McxFamily.CRUDEOIL: McxUnitProfile(
        McxFamily.CRUDEOIL, Decimal("100"), "barrel", Decimal("1"), "barrel",
        Decimal("1"), McxSettlement.CASH,
        "https://www.mcxindia.com/docs/default-source/products/contract-specification/crude-oil/crude-oil-january-2026-contract-onwards267be8c1-650a-4baa-aabd-ffcc9364c100.pdf",
        "CRUDE-OIL-JANUARY-2026-ONWARDS",
    ),
    McxFamily.NATURALGAS: McxUnitProfile(
        McxFamily.NATURALGAS, Decimal("1250"), "mmBtu", Decimal("1"), "mmBtu",
        Decimal("0.10"), McxSettlement.CASH,
        "https://www.mcxindia.com/docs/default-source/products/contract-specification/natural-gas/natural-gas-january-2026-contract-onwards2ff2141b-f6e4-4b6a-9f0e-59f260cecf9b.pdf",
        "NATURAL-GAS-JANUARY-2026-ONWARDS",
    ),
}


def mcx_unit_profile(family: McxFamily) -> McxUnitProfile:
    if type(family) is not McxFamily:
        raise ValueError("MCX_FAMILY_UNAVAILABLE")
    return _MCX_SPECIFICATIONS[family]


def mcx_contract_name_matches(
    family: McxFamily, instrument: InstrumentRecord,
) -> bool:
    """Exact Swing family/month identity; no fuzzy or alias matching."""

    if (
        type(family) is not McxFamily
        or type(instrument) is not InstrumentRecord
        or instrument.provider != "KITE"
        or instrument.exchange != "MCX"
        or instrument.segment != "MCX-FUT"
        or instrument.instrument_type != "FUT"
        or instrument.expiry is None
    ):
        return False
    match = re.fullmatch(
        re.escape(family.value) + r"(?P<year>\d{2})(?P<month>[A-Z]{3})FUT",
        instrument.trading_symbol,
    )
    return (
        match is not None
        and int(match.group("year")) == instrument.expiry.year % 100
        and match.group("month") == _MONTH_CODES[instrument.expiry.month - 1]
    )


def _digest(value: object) -> str:
    def normalize(item: object) -> object:
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, StrEnum):
            return item.value
        if isinstance(item, dict):
            return {key: normalize(part) for key, part in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalize(part) for part in item]
        return item

    return sha256(json.dumps(
        normalize(value), sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _valid_expiry(value: object) -> bool:
    if type(value) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class McxRequestBoundCandleLineage:
    """Exact normalized contract and source/read-set hashes for one Swing run.

    Provider historical candles do not echo a master record identity.  This
    artifact records what was requested and admitted, and explicitly withholds
    entry authority until a separately governed master/specification proof.
    """

    run_identity: str
    family: McxFamily
    provider: str
    exchange: str
    segment: str
    trading_symbol: str
    instrument_type: str
    expiry: str
    normalized_instrument_sha256: str
    daily_request_sha256: str
    hourly_request_sha256: str
    daily_source_sha256: str
    hourly_source_sha256: str
    retained_daily_sha256: str
    completed_1d_sha256: str
    completed_4h_sha256: str
    completed_1h_sha256: str
    completed_series_sha256: str
    completed_1d_boundary: datetime
    completed_4h_boundary: datetime
    completed_1h_boundary: datetime
    source_master_snapshot_identity: None = None
    source_master_record_identity: None = None
    effective_specification_sha256: None = None
    entry_fact_state: McxEntryFactState = (
        McxEntryFactState.MASTER_AND_SPECIFICATION_UNVERIFIED
    )

    def __post_init__(self) -> None:
        hashes = (
            self.normalized_instrument_sha256, self.daily_request_sha256,
            self.hourly_request_sha256, self.daily_source_sha256,
            self.hourly_source_sha256, self.retained_daily_sha256,
            self.completed_1d_sha256, self.completed_4h_sha256,
            self.completed_1h_sha256,
            self.completed_series_sha256,
        )
        if (
            not is_swing_analysis_run_id(self.run_identity)
            or type(self.family) is not McxFamily
            or self.provider != "KITE"
            or self.exchange != "MCX"
            or not self.segment
            or not re.fullmatch(r"[A-Z0-9]+", self.trading_symbol)
            or self.instrument_type != "FUT"
            or not _valid_expiry(self.expiry)
            or any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in hashes)
            or any(
                value.tzinfo is None or value.utcoffset() is None
                for value in (
                    self.completed_1d_boundary,
                    self.completed_4h_boundary,
                    self.completed_1h_boundary,
                )
            )
            or self.source_master_snapshot_identity is not None
            or self.source_master_record_identity is not None
            or self.effective_specification_sha256 is not None
            or self.entry_fact_state is not McxEntryFactState.MASTER_AND_SPECIFICATION_UNVERIFIED
        ):
            raise ValueError("MCX_CANDLE_LINEAGE_INVALID")

    @property
    def permits_new_entry(self) -> bool:
        return False


def capture_mcx_request_bound_lineage(
    *,
    run_identity: str,
    family: McxFamily,
    instrument: InstrumentRecord,
    daily_request: HistoricalCandleRequest,
    hourly_request: HistoricalCandleRequest,
    daily_source: tuple[HistoricalCandle, ...],
    hourly_source: tuple[HistoricalCandle, ...],
    retained_daily: tuple[HistoricalCandle, ...],
    completed_facts: tuple[object, object, object],
    completed_series: tuple[object, ...],
) -> McxRequestBoundCandleLineage:
    """Capture source/read-set identity after completed fact construction.

    `completed_facts` are the retained 1D, derived 4H and 1H facts.  No
    Provider master identity, effective specification or trading unit is
    inferred from the normalized historical request or Provider lot_size.
    """

    from kronos.swing.v1.mtf_facts import (
        CompletedTimeframeBar,
        CompletedTimeframeFact,
        FactualTimeframe,
    )

    if (
        type(family) is not McxFamily
        or type(instrument) is not InstrumentRecord
        or not mcx_contract_name_matches(family, instrument)
        or type(daily_request) is not HistoricalCandleRequest
        or daily_request.instrument != instrument
        or daily_request.interval is not HistoricalInterval.DAY
        or type(hourly_request) is not HistoricalCandleRequest
        or hourly_request.instrument != instrument
        or hourly_request.interval is not HistoricalInterval.SIXTY_MINUTE
        or any(
            type(series) is not tuple
            or not series
            or any(type(candle) is not HistoricalCandle for candle in series)
            for series in (daily_source, hourly_source, retained_daily)
        )
        or type(completed_facts) is not tuple
        or len(completed_facts) != 3
        or type(completed_series) is not tuple
        or any(type(bar) is not CompletedTimeframeBar for bar in completed_series)
        or tuple(
            fact.timeframe if type(fact) is CompletedTimeframeFact else None
            for fact in completed_facts
        ) != (
            FactualTimeframe.DAILY,
            FactualTimeframe.FOUR_HOUR,
            FactualTimeframe.ONE_HOUR,
        )
    ):
        raise ValueError("MCX_CANDLE_LINEAGE_SOURCE_INVALID")
    if any(
        not request.start <= candle.timestamp <= request.end
        for request, series in (
            (daily_request, daily_source),
            (hourly_request, hourly_source),
        )
        for candle in series
    ):
        raise ValueError("MCX_CANDLE_LINEAGE_WINDOW_MISMATCH")
    return McxRequestBoundCandleLineage(
        run_identity=run_identity,
        family=family,
        provider=instrument.provider,
        exchange=instrument.exchange,
        segment=instrument.segment,
        trading_symbol=instrument.trading_symbol,
        instrument_type=instrument.instrument_type,
        expiry=instrument.expiry.isoformat(),
        normalized_instrument_sha256=_digest(asdict(instrument)),
        daily_request_sha256=_digest(asdict(daily_request)),
        hourly_request_sha256=_digest(asdict(hourly_request)),
        daily_source_sha256=_digest([asdict(item) for item in daily_source]),
        hourly_source_sha256=_digest([asdict(item) for item in hourly_source]),
        retained_daily_sha256=_digest([asdict(item) for item in retained_daily]),
        completed_1d_sha256=_digest(asdict(completed_facts[0])),
        completed_4h_sha256=_digest(asdict(completed_facts[1])),
        completed_1h_sha256=_digest(asdict(completed_facts[2])),
        completed_series_sha256=_digest([
            asdict(bar) for bar in completed_series
            if bar.timeframe in (
                FactualTimeframe.DAILY,
                FactualTimeframe.FOUR_HOUR,
                FactualTimeframe.ONE_HOUR,
            )
        ]),
        completed_1d_boundary=completed_facts[0].observation_boundary,
        completed_4h_boundary=completed_facts[1].observation_boundary,
        completed_1h_boundary=completed_facts[2].observation_boundary,
    )


def mcx_lineage_matches_completed_facts(
    lineage: McxRequestBoundCandleLineage,
    *,
    run_identity: str,
    canonical_instrument: str,
    current_instrument: InstrumentRecord,
    completed_facts: tuple[object, object, object],
    completed_series: tuple[object, ...],
) -> bool:
    """Read-only final comparison; a missing or changed read-set is stale."""

    from kronos.swing.v1.mtf_facts import (
        CompletedTimeframeBar,
        CompletedTimeframeFact,
        FactualTimeframe,
    )

    if (
        type(lineage) is not McxRequestBoundCandleLineage
        or lineage.run_identity != run_identity
        or lineage.family.value != canonical_instrument
        or type(current_instrument) is not InstrumentRecord
        or _digest(asdict(current_instrument)) != lineage.normalized_instrument_sha256
        or current_instrument.trading_symbol != lineage.trading_symbol
        or current_instrument.expiry is None
        or current_instrument.expiry.isoformat() != lineage.expiry
        or type(completed_facts) is not tuple
        or tuple(
            fact.timeframe if type(fact) is CompletedTimeframeFact else None
            for fact in completed_facts
        ) != (
            FactualTimeframe.DAILY,
            FactualTimeframe.FOUR_HOUR,
            FactualTimeframe.ONE_HOUR,
        )
        or type(completed_series) is not tuple
        or any(type(bar) is not CompletedTimeframeBar for bar in completed_series)
    ):
        return False
    return (
        (lineage.completed_1d_sha256, lineage.completed_4h_sha256,
         lineage.completed_1h_sha256)
        == tuple(_digest(asdict(fact)) for fact in completed_facts)
        and lineage.completed_series_sha256 == _digest([
            asdict(bar) for bar in completed_series
            if bar.timeframe in (
                FactualTimeframe.DAILY,
                FactualTimeframe.FOUR_HOUR,
                FactualTimeframe.ONE_HOUR,
            )
        ])
    )


def mcx_lineage_from_dict(value: object) -> McxRequestBoundCandleLineage:
    if type(value) is not dict:
        raise ValueError("MCX_CANDLE_LINEAGE_INVALID")
    try:
        fields = dict(value)
        fields["family"] = McxFamily(fields["family"])
        for name in (
            "completed_1d_boundary", "completed_4h_boundary",
            "completed_1h_boundary",
        ):
            fields[name] = datetime.fromisoformat(fields[name])
        fields["entry_fact_state"] = McxEntryFactState(fields["entry_fact_state"])
        return McxRequestBoundCandleLineage(**fields)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("MCX_CANDLE_LINEAGE_INVALID") from error


__all__ = [
    "MCX_SWING_FAMILIES", "McxEntryFactState", "McxFamily",
    "McxRequestBoundCandleLineage",
    "McxSettlement", "McxUnitProfile", "capture_mcx_request_bound_lineage",
    "mcx_contract_name_matches", "mcx_lineage_from_dict",
    "mcx_lineage_matches_completed_facts",
    "mcx_unit_profile",
]
