"""Canonical Swing Phase 1 analytical-universe membership."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import re


_EQUITY_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "nse"
    / "KRONOS_NSE_RELATIONSHIPS.csv"
)
_CANONICAL_IDENTITY = re.compile(r"[A-Z0-9_&-]+(?: [A-Z0-9_&-]+)*\Z")
_EXPECTED_EQUITY_COUNT = 91


class SwingUniverseAssetClass(StrEnum):
    """The three bounded asset classes in the Phase 1 universe."""

    NSE_EQUITY = "NSE_EQUITY"
    NSE_INDEX = "NSE_INDEX"
    MCX_COMMODITY = "MCX_COMMODITY"


class SwingUniverseFailure(StrEnum):
    """Sanitized fail-closed universe construction failures."""

    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    MALFORMED_SOURCE = "MALFORMED_SOURCE"
    EQUITY_COUNT_MISMATCH = "EQUITY_COUNT_MISMATCH"
    DUPLICATE_IDENTITY = "DUPLICATE_IDENTITY"
    REQUIRED_IDENTITY_MISSING = "REQUIRED_IDENTITY_MISSING"


class SwingUniverseError(RuntimeError):
    """Universe failure retaining no malformed source contents."""

    def __init__(self, failure: SwingUniverseFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class SwingUniverseMember:
    """One immutable Swing-owned analytical identity."""

    canonical_identity: str
    asset_class: SwingUniverseAssetClass

    def __post_init__(self) -> None:
        if (
            type(self.canonical_identity) is not str
            or _CANONICAL_IDENTITY.fullmatch(self.canonical_identity) is None
            or type(self.asset_class) is not SwingUniverseAssetClass
        ):
            raise ValueError("SWING_UNIVERSE_MEMBER_INVALID")


_INDICES = (
    SwingUniverseMember("NIFTY", SwingUniverseAssetClass.NSE_INDEX),
    SwingUniverseMember("BANK NIFTY", SwingUniverseAssetClass.NSE_INDEX),
)
_COMMODITIES = tuple(
    SwingUniverseMember(symbol, SwingUniverseAssetClass.MCX_COMMODITY)
    for symbol in ("GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS")
)
_REQUIRED_IDENTITIES = frozenset(
    member.canonical_identity for member in _INDICES + _COMMODITIES
)


def load_swing_phase1_universe(
    equity_source: Path = _EQUITY_SOURCE,
) -> tuple[SwingUniverseMember, ...]:
    """Load and validate the exact deterministic 98-member universe."""

    equities = _load_equities(equity_source)
    universe = equities + _INDICES + _COMMODITIES
    identities = tuple(member.canonical_identity for member in universe)
    if len(set(identities)) != len(identities):
        raise SwingUniverseError(SwingUniverseFailure.DUPLICATE_IDENTITY)
    if not _REQUIRED_IDENTITIES.issubset(identities):
        raise SwingUniverseError(SwingUniverseFailure.REQUIRED_IDENTITY_MISSING)
    if len(universe) != 98:
        raise SwingUniverseError(SwingUniverseFailure.MALFORMED_SOURCE)
    return universe


def _load_equities(source_path: Path) -> tuple[SwingUniverseMember, ...]:
    if not isinstance(source_path, Path):
        raise SwingUniverseError(SwingUniverseFailure.MALFORMED_SOURCE)
    try:
        with source_path.open(newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source, strict=True)
            if reader.fieldnames is None or "symbol" not in reader.fieldnames:
                raise SwingUniverseError(SwingUniverseFailure.MALFORMED_SOURCE)
            rows = tuple(reader)
    except SwingUniverseError:
        raise
    except (OSError, UnicodeError):
        raise SwingUniverseError(SwingUniverseFailure.SOURCE_UNAVAILABLE) from None
    except csv.Error:
        raise SwingUniverseError(SwingUniverseFailure.MALFORMED_SOURCE) from None

    symbols = tuple(row.get("symbol") for row in rows)
    if any(
        None in row
        or type(symbol) is not str
        or _CANONICAL_IDENTITY.fullmatch(symbol) is None
        for row, symbol in zip(rows, symbols)
    ):
        raise SwingUniverseError(SwingUniverseFailure.MALFORMED_SOURCE)
    if len(symbols) != _EXPECTED_EQUITY_COUNT:
        raise SwingUniverseError(SwingUniverseFailure.EQUITY_COUNT_MISMATCH)
    if len(set(symbols)) != len(symbols):
        raise SwingUniverseError(SwingUniverseFailure.DUPLICATE_IDENTITY)
    return tuple(
        SwingUniverseMember(symbol, SwingUniverseAssetClass.NSE_EQUITY)
        for symbol in symbols
    )


SWING_PHASE1_UNIVERSE = load_swing_phase1_universe()


def enabled_swing_phase1_universe() -> tuple[SwingUniverseMember, ...]:
    """Return the immutable canonical Phase 1 analytical universe."""

    return SWING_PHASE1_UNIVERSE


__all__ = [
    "SWING_PHASE1_UNIVERSE",
    "SwingUniverseAssetClass",
    "SwingUniverseError",
    "SwingUniverseFailure",
    "SwingUniverseMember",
    "enabled_swing_phase1_universe",
    "load_swing_phase1_universe",
]
