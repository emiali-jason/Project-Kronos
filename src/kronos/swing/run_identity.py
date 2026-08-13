"""Immutable parent identity for one Swing market-analysis snapshot."""

from __future__ import annotations

import re


LEGACY_UNBOUND_SWING_RUN_ID = "LEGACY_UNBOUND"
_SWING_RUN_ID = re.compile(r"SWING-RUN-[0-9A-F]{32}\Z")


def is_swing_analysis_run_id(value: object) -> bool:
    """Return whether *value* is a bound, globally unique Swing run identity."""

    return isinstance(value, str) and _SWING_RUN_ID.fullmatch(value) is not None


def is_swing_run_binding(value: object) -> bool:
    """Accept a bound run or the explicit pre-fix legacy sentinel."""

    return value == LEGACY_UNBOUND_SWING_RUN_ID or is_swing_analysis_run_id(value)


__all__ = [
    "LEGACY_UNBOUND_SWING_RUN_ID",
    "is_swing_analysis_run_id",
    "is_swing_run_binding",
]
