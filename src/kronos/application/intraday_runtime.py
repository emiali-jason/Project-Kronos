"""Intraday-owned runtime composition seam for the shared Browser process."""

from __future__ import annotations

from dataclasses import dataclass

from kronos.application.intraday_workstation import IntradayEvidenceWorkstation
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
    workstation: IntradayEvidenceWorkstation
    provider_access: IntradayProviderRuntimeAccess


def create_intraday_runtime(
    provider_runtime: SharedAuthenticatedProviderRuntime,
) -> IntradayRuntimeComposition:
    """Compose Intraday without moving product policy into shared modules."""

    return IntradayRuntimeComposition(
        workstation=create_intraday_workstation(),
        provider_access=IntradayProviderRuntimeAccess(provider_runtime),
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
