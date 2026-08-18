"""Intraday-owned runtime composition seam for the shared Browser process."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from kronos.application.intraday_reliance_bootstrap import (
    DEFAULT_INTRADAY_EVIDENCE_ROOT,
    RelianceIntradayBootstrap,
    RelianceIntradayRuntimeWorkstation,
)
from kronos.application.intraday_workstation import IntradayEvidenceWorkstation
from kronos.market.calendar import MarketCalendarPublisher
from kronos.provider.contracts.provider_authentication import ReadOnlyProviderOperation
from kronos.provider.runtime import (
    ReadOnlyProviderLease,
    SharedAuthenticatedProviderRuntime,
)


_INTRADAY_READ_OPERATIONS = frozenset({
    ReadOnlyProviderOperation.INSTRUMENTS,
    ReadOnlyProviderOperation.INSTRUMENT_ASSERTIONS,
    ReadOnlyProviderOperation.HISTORICAL_DATA,
})


class IntradayProviderRuntimeAccess:
    """Product-owned adapter requesting only Intraday factual read operations."""

    __slots__ = ("_runtime",)

    def __init__(self, runtime: SharedAuthenticatedProviderRuntime) -> None:
        if type(runtime) is not SharedAuthenticatedProviderRuntime:
            raise ValueError("INTRADAY_PROVIDER_RUNTIME_INVALID")
        self._runtime = runtime

    def acquire_historical_lease(self) -> ReadOnlyProviderLease:
        return self._runtime.acquire_lease(
            consumer_identity="INTRADAY",
            operations=_INTRADAY_READ_OPERATIONS,
        )


@dataclass(frozen=True, slots=True)
class IntradayRuntimeComposition:
    workstation: object
    provider_access: IntradayProviderRuntimeAccess


def create_intraday_runtime(
    provider_runtime: SharedAuthenticatedProviderRuntime,
    *,
    calendar_publisher: MarketCalendarPublisher | None = None,
    evidence_root: Path = DEFAULT_INTRADAY_EVIDENCE_ROOT,
    clock=lambda: datetime.now(timezone.utc),
) -> IntradayRuntimeComposition:
    """Compose Intraday without moving product policy into shared modules."""

    access = IntradayProviderRuntimeAccess(provider_runtime)
    return IntradayRuntimeComposition(
        workstation=RelianceIntradayRuntimeWorkstation(
            RelianceIntradayBootstrap(
                acquire_lease=access.acquire_historical_lease,
                calendar_publisher=calendar_publisher,
                evidence_root=evidence_root,
                clock=clock,
            )
        ),
        provider_access=access,
    )


def create_intraday_workstation() -> IntradayEvidenceWorkstation:
    """Preserve the published empty workstation until bootstrap is authorized."""

    return IntradayEvidenceWorkstation()


__all__ = [
    "IntradayProviderRuntimeAccess",
    "IntradayRuntimeComposition",
    "create_intraday_runtime",
    "create_intraday_workstation",
]
