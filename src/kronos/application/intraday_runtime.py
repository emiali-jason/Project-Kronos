"""Intraday-owned runtime composition seam for the shared Browser process."""

from __future__ import annotations

from kronos.application.intraday_workstation import IntradayEvidenceWorkstation


def create_intraday_workstation() -> IntradayEvidenceWorkstation:
    """Preserve the published empty workstation until bootstrap is authorized."""

    return IntradayEvidenceWorkstation()


__all__ = ["create_intraday_workstation"]
