"""Provider-neutral schema for the Swing V1 visible Pine evidence panel.

The module defines panel identity, fixed row topology and known-truth fixture
shape only. It performs no image extraction, OpenAI call, market analysis,
Readiness calculation or reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


VISIBLE_PINE_PANEL_CONTRACT_ID = "KRONOS-SWING-V1-PINE-VISIBLE-EVIDENCE-V1"
VISIBLE_PINE_PANEL_VERSION = "1.0"
VISIBLE_PINE_PANEL_PUBLISHER_ROLE = "CANDIDATE"

VISIBLE_PINE_PANEL_ROW_ORDER = (
    "SECTION A",
    "PANEL_SCHEMA",
    "PANEL_VERSION",
    "PRODUCT",
    "PINE_IDENTITY",
    "PINE_VERSION",
    "PINE_BUILD",
    "PUBLISHER_ROLE",
    "CANONICAL_INSTR",
    "TIMEFRAME",
    "OBS_BOUNDARY",
    "BOUNDARY_STATE",
    "STRUCTURE",
    "VISIBLE_SWINGS",
    "STRUCTURE_BREAK",
    "RANGE",
    "BREAK",
    "SMA20",
    "SMA50",
    "SMA200",
    "CANDLE",
    "VOLUME",
    "REFERENCE_LEVELS",
    "BARRIERS",
    "SECTION B",
    "TREND",
    "QUALITY",
    "ACCEPTANCE",
    "MOMENTUM",
    "OPPORTUNITY",
    "CONFIDENCE",
    "DECISION",
    "NEED",
    "STATUS",
    "PRODUCT_CONTEXT_1",
    "PRODUCT_CONTEXT_2",
    "PRODUCT_CONTEXT_3",
)

VISIBLE_PINE_PANEL_DOMAIN_ROWS = (
    "CANONICAL_INSTR",
    "TIMEFRAME",
    "STRUCTURE",
    "VISIBLE_SWINGS",
    "RANGE",
    "BREAK",
    "SMA20",
    "SMA50",
    "SMA200",
    "CANDLE",
    "VOLUME",
    "REFERENCE_LEVELS",
    "BARRIERS",
    "STATUS",
)

VISIBLE_PINE_MISSING_TOKENS = ("UNAVAILABLE", "NOT_APPLICABLE", "UNKNOWN")


class VisiblePinePanelProduct(StrEnum):
    MCX = "MCX"
    NSE = "NSE"


class VisiblePineBoundaryState(StrEnum):
    COMPLETED = "COMPLETED"
    DEVELOPING = "DEVELOPING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class VisiblePinePanelRow:
    label: str
    value: str

    def __post_init__(self) -> None:
        if not self.label.strip() or not self.value.strip():
            raise ValueError("VISIBLE_PINE_PANEL_ROW_INVALID")


@dataclass(frozen=True, slots=True)
class VisiblePineKnownTruthFixture:
    fixture_id: str
    product: VisiblePinePanelProduct
    canonical_instrument: str
    timeframe: str
    boundary_state: VisiblePineBoundaryState
    publisher_role: str
    rows: tuple[VisiblePinePanelRow, ...]
    pine_owned_domains: tuple[str, ...]
    product_extension: tuple[str, ...]

    def __post_init__(self) -> None:
        normalized_labels = tuple(
            "PRODUCT_CONTEXT_" + row.label.rsplit("_", 1)[-1]
            if row.label.startswith(("MCX_CONTEXT_", "NSE_CONTEXT_"))
            else row.label
            for row in self.rows
        )
        if (
            not self.fixture_id.strip()
            or not self.canonical_instrument.strip()
            or not self.timeframe.strip()
            or self.publisher_role != VISIBLE_PINE_PANEL_PUBLISHER_ROLE
            or normalized_labels != VISIBLE_PINE_PANEL_ROW_ORDER
            or self.pine_owned_domains != VISIBLE_PINE_PANEL_DOMAIN_ROWS
            or len(self.product_extension) != 3
        ):
            raise ValueError("VISIBLE_PINE_KNOWN_TRUTH_FIXTURE_INVALID")


__all__ = [
    "VISIBLE_PINE_MISSING_TOKENS",
    "VISIBLE_PINE_PANEL_CONTRACT_ID",
    "VISIBLE_PINE_PANEL_DOMAIN_ROWS",
    "VISIBLE_PINE_PANEL_PUBLISHER_ROLE",
    "VISIBLE_PINE_PANEL_ROW_ORDER",
    "VISIBLE_PINE_PANEL_VERSION",
    "VisiblePineBoundaryState",
    "VisiblePineKnownTruthFixture",
    "VisiblePinePanelProduct",
    "VisiblePinePanelRow",
]
