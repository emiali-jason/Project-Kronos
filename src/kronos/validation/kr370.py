"""Product-neutral KR-370 analytical-promotion contract primitives."""

from __future__ import annotations

from enum import StrEnum
from typing import Sequence


KR370_PROMOTION_CONTRACT_ID = "KRONOS-KR-370-ANALYTICAL-PROMOTION-V1"
KR370_PROMOTION_CONTRACT_VERSION = "1"
KR370_PROMOTION_AUTHORITY = "ANALYTICAL_PROMOTION_ONLY"
KR370_OWNER_IDENTITY = "KR-370"
KR370_STATE_FAMILY_IDENTITY = "KR370_ANALYTICAL_PROMOTION"


class Kr370CriterionState(StrEnum):
    SATISFIED = "SATISFIED"
    UNSATISFIED = "UNSATISFIED"
    UNAVAILABLE = "UNAVAILABLE"


class Kr370AnalyticalClassification(StrEnum):
    BUY_NOW = "BUY_NOW"
    SELL_NOW = "SELL_NOW"
    BUY_READY = "BUY_READY"
    SELL_READY = "SELL_READY"
    POTENTIAL_BUY_SETUP = "POTENTIAL_BUY_SETUP"
    POTENTIAL_SELL_SETUP = "POTENTIAL_SELL_SETUP"
    NO_SETUP = "NO_SETUP"


def classify_five_criteria(
    direction: str,
    states: Sequence[Kr370CriterionState],
) -> tuple[Kr370AnalyticalClassification, int, int]:
    """Apply the common unweighted five-criterion maturity mapping."""

    retained = tuple(states)
    if (
        direction not in {"LONG", "SHORT"}
        or len(retained) != 5
        or any(type(item) is not Kr370CriterionState for item in retained)
        or any(item is Kr370CriterionState.UNAVAILABLE for item in retained)
    ):
        raise ValueError("KR370_CLASSIFICATION_INPUT_INVALID")
    satisfied = sum(item is Kr370CriterionState.SATISFIED for item in retained)
    unsatisfied = 5 - satisfied
    if satisfied == 5:
        state = (
            Kr370AnalyticalClassification.BUY_NOW
            if direction == "LONG"
            else Kr370AnalyticalClassification.SELL_NOW
        )
    elif satisfied == 4:
        state = (
            Kr370AnalyticalClassification.BUY_READY
            if direction == "LONG"
            else Kr370AnalyticalClassification.SELL_READY
        )
    elif satisfied in {2, 3}:
        state = (
            Kr370AnalyticalClassification.POTENTIAL_BUY_SETUP
            if direction == "LONG"
            else Kr370AnalyticalClassification.POTENTIAL_SELL_SETUP
        )
    else:
        state = Kr370AnalyticalClassification.NO_SETUP
    return state, satisfied, unsatisfied


__all__ = [
    "KR370_OWNER_IDENTITY",
    "KR370_PROMOTION_AUTHORITY",
    "KR370_PROMOTION_CONTRACT_ID",
    "KR370_PROMOTION_CONTRACT_VERSION",
    "KR370_STATE_FAMILY_IDENTITY",
    "Kr370AnalyticalClassification",
    "Kr370CriterionState",
    "classify_five_criteria",
]
