"""Browser control boundary for explicit WO-07F reconciliation."""

from __future__ import annotations

from kronos.application.intraday_visual_reconciliation_v2 import (
    IntradayVisualReconciliationV2Application,
)


class IntradayVisualReconciliationV2OperationalControl:
    def __init__(self, application: IntradayVisualReconciliationV2Application) -> None:
        if type(application) is not IntradayVisualReconciliationV2Application:
            raise ValueError("WO07F_CONTROL_INVALID")
        self._application = application

    def status_document(self) -> dict[str, object]:
        return self._application.status().document()

    def reconcile_all_ready(self) -> dict[str, object]:
        return self._application.reconcile_all_ready()


__all__ = ["IntradayVisualReconciliationV2OperationalControl"]
