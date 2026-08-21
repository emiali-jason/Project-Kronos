"""Read-only Sponsor Dashboard projection over authoritative KRONOS records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from kronos.application.notifications import (
    NotificationState,
    NotificationWorkspaceSnapshot,
)
from kronos.application.swing_opportunities import (
    AnalysisState,
    BrowserWorkspaceSnapshot,
    ProviderConnectionState,
)
from kronos.swing.v1.analytical_promotion import (
    Kr370AnalyticalClassification,
    Kr370AnalyticalPromotionRecord,
)
from kronos.swing.v1.native_discovery import (
    NativeDiscoveryRun,
    NativeDiscoveryStatus,
)


_DASHBOARD_SWING_STATES = {
    Kr370AnalyticalClassification.BUY_NOW,
    Kr370AnalyticalClassification.SELL_NOW,
    Kr370AnalyticalClassification.BUY_READY,
    Kr370AnalyticalClassification.SELL_READY,
}


@dataclass(frozen=True, slots=True)
class DashboardSwingOpportunity:
    instrument: str
    classification: Kr370AnalyticalClassification
    run_identity: str
    native_assessment_sha256: str


@dataclass(frozen=True, slots=True)
class DashboardAlert:
    instrument: str
    strategy: str
    condition: str
    state: NotificationState
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class DashboardIssue:
    identity: str
    summary: str


@dataclass(frozen=True, slots=True)
class SponsorDashboardProjection:
    current_run_identity: str | None
    swing_summary_available: bool
    swing_opportunities: tuple[DashboardSwingOpportunity, ...]
    active_alerts: tuple[DashboardAlert, ...]
    issues: tuple[DashboardIssue, ...]
    system_status: str
    data_status: str
    analysis_status: str
    last_successful_analysis: datetime | None

    @property
    def now_count(self) -> int:
        return sum(
            item.classification in {
                Kr370AnalyticalClassification.BUY_NOW,
                Kr370AnalyticalClassification.SELL_NOW,
            }
            for item in self.swing_opportunities
        )

    @property
    def ready_count(self) -> int:
        return sum(
            item.classification in {
                Kr370AnalyticalClassification.BUY_READY,
                Kr370AnalyticalClassification.SELL_READY,
            }
            for item in self.swing_opportunities
        )


def project_sponsor_dashboard(
    snapshot: BrowserWorkspaceSnapshot,
    discovery: NativeDiscoveryRun | None,
    promotions: tuple[Kr370AnalyticalPromotionRecord, ...],
    notifications: NotificationWorkspaceSnapshot,
) -> SponsorDashboardProjection:
    """Project current facts without evaluating or mutating any source authority."""

    if (
        type(snapshot) is not BrowserWorkspaceSnapshot
        or (discovery is not None and type(discovery) is not NativeDiscoveryRun)
        or type(promotions) is not tuple
        or any(type(item) is not Kr370AnalyticalPromotionRecord for item in promotions)
        or type(notifications) is not NotificationWorkspaceSnapshot
    ):
        raise TypeError("SPONSOR_DASHBOARD_SOURCE_INVALID")

    current = discovery
    if (
        current is None
        or current.run_identity != snapshot.swing_analysis_run_identity
        or snapshot.completed_at is None
    ):
        current = None

    current_records: tuple[Kr370AnalyticalPromotionRecord, ...] = ()
    if current is not None:
        assessments = {
            (item.canonical_instrument, item.result_sha256)
            for item in current.assessments
            if item.status is NativeDiscoveryStatus.PROBABLE
        }
        candidates = tuple(
            item for item in promotions
            if item.run_identity == current.run_identity
            and (item.canonical_instrument, item.native_assessment_sha256)
            in assessments
        )
        identities = tuple(item.canonical_instrument for item in candidates)
        if len(set(identities)) == len(identities):
            current_records = candidates

    classification_order = {
        Kr370AnalyticalClassification.BUY_NOW: 0,
        Kr370AnalyticalClassification.SELL_NOW: 1,
        Kr370AnalyticalClassification.BUY_READY: 2,
        Kr370AnalyticalClassification.SELL_READY: 3,
    }
    swing = tuple(
        DashboardSwingOpportunity(
            item.canonical_instrument,
            item.classification,
            item.run_identity,
            item.native_assessment_sha256,
        )
        for item in sorted(
            (item for item in current_records if item.classification in _DASHBOARD_SWING_STATES),
            key=lambda item: (
                classification_order[item.classification],
                item.canonical_instrument,
            ),
        )
    )

    alerts = ()
    if current is not None:
        alerts = tuple(
            DashboardAlert(
                item.instrument,
                item.product.value,
                item.condition_summary,
                item.state,
                item.triggered_at or item.activated_at,
            )
            for item in notifications.records
            if item.source_run_identity == current.run_identity
            and item.state in {NotificationState.ACTIVE, NotificationState.TRIGGERED}
        )[:3]

    issues: list[DashboardIssue] = []
    if snapshot.provider_state is ProviderConnectionState.DISCONNECTED:
        issues.append(DashboardIssue("KITE_DISCONNECTED", "Kite is disconnected."))
    elif snapshot.provider_state is ProviderConnectionState.CONNECTING:
        issues.append(DashboardIssue("KITE_CONNECTING", "Kite connection is in progress."))
    elif snapshot.provider_state is ProviderConnectionState.ERROR:
        issues.append(DashboardIssue("KITE_CONNECTION_ERROR", "Kite connection failed."))
    if snapshot.analysis_state is AnalysisState.ERROR or snapshot.analysis_failure:
        issues.append(DashboardIssue("SWING_ANALYSIS_FAILURE", "Swing analysis failed."))
    if current is None:
        issues.append(DashboardIssue(
            "CURRENT_NATIVE_DATA_UNAVAILABLE",
            "Current Native Swing results are unavailable.",
        ))

    return SponsorDashboardProjection(
        current_run_identity=None if current is None else current.run_identity,
        swing_summary_available=bool(current_records),
        swing_opportunities=swing,
        active_alerts=alerts,
        issues=tuple(issues),
        system_status="BROWSER AVAILABLE",
        data_status=(
            "CURRENT NATIVE RUN AVAILABLE"
            if current is not None else "CURRENT NATIVE RUN UNAVAILABLE"
        ),
        analysis_status=snapshot.analysis_state.value,
        last_successful_analysis=snapshot.completed_at,
    )


__all__ = [
    "DashboardAlert",
    "DashboardIssue",
    "DashboardSwingOpportunity",
    "SponsorDashboardProjection",
    "project_sponsor_dashboard",
]
