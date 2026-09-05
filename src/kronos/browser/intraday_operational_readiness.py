"""GET-only Browser projection for WO-B operational-readiness review."""

from __future__ import annotations

from kronos.application.intraday_operational_readiness import (
    IntradayOperationalReadinessRuntimeService,
)


WO_B_PRODUCT_ROUTE = "/intraday/operational-review"


class IntradayOperationalReadinessProjection:
    """Expose the runtime service without adding an operational POST seam."""

    __slots__ = ("_runtime",)

    def __init__(self, runtime: IntradayOperationalReadinessRuntimeService) -> None:
        if type(runtime) is not IntradayOperationalReadinessRuntimeService:
            raise ValueError("WO_B_BROWSER_PROJECTION_INVALID")
        self._runtime = runtime

    def status_document(self) -> dict[str, object]:
        return self._runtime.status_document()


__all__ = ["IntradayOperationalReadinessProjection", "WO_B_PRODUCT_ROUTE"]
