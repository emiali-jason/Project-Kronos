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
from kronos.application.swing_ux10 import Ux10NotificationSnapshot
from kronos.swing.v1.analytical_promotion import (
    Kr370AnalyticalClassification,
    Kr370AnalyticalPromotionRecord,
)
from kronos.swing.v1.analytical_promotion_v2 import V2PromotionRecord
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
    classification: Kr370AnalyticalClassification | str | None
    run_identity: str
    native_assessment_sha256: str
    contract_version: int = 1
    disposition: str | None = None
    confirmation: str | None = None


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
class IntradayDashboardSummary:
    now: int | None = None
    ready: int | None = None
    state: str = "CURRENT_AUTHORITY_UNAVAILABLE"
    current_readiness: tuple[str, ...] = ()
    watching_disposition: str = "DEFERRED_NOT_AUTHORITATIVE"
    opportunities: tuple[dict, ...] = ()


def project_intraday_dashboard(store, boundary=None, *, monitoring_projection=None) -> IntradayDashboardSummary:
    """Read exact WO09 authority under existing source/session owner checks.

    Counts are persisted readiness classifications, never assessed/browser rows.
    No handoff, watch, pointer, evaluation publication or acquisition is created.
    A closed/historical session contributes zero; missing/corrupt authority is
    unavailable, not an apparently successful empty operational population.
    """
    from contextlib import nullcontext
    from kronos.application.intraday_evidence_currentness import require_boundary
    from kronos.intraday.evidence_currentness import NewWorkNotEligible
    from kronos.intraday.wo09_readiness import CurrentnessState, ReadinessState
    if boundary is None:
        return IntradayDashboardSummary()
    try:
        owner = require_boundary(boundary)
        if owner.wo09 is not store or owner.wo08 is None or owner.native is None:
            raise ValueError("INTRADAY_DASHBOARD_OWNER_MISMATCH")
        before = store.restore_current()
        machine_preview = next((record for _, record in before if record.source_authority == 'WO08'), None)
        with (nullcontext() if machine_preview is None else owner._sources(machine_preview)):
            current = []
            opportunities = []
            now = ready = 0
            current_population = None
            for pointer, record in before:
                if record.source_authority != "WO08" or pointer.currentness is not CurrentnessState.CURRENT:
                    continue
                try:
                    # Compare retained owner identities; never run an evaluator on GET.
                    probable = owner.probables.load_current()
                    machine = owner.wo08.current_pointer()
                    if probable is None or machine is None:
                        raise ValueError('INTRADAY_DASHBOARD_SOURCE_UNAVAILABLE')
                    if (probable.run_identity != record.probables_run_identity
                            or machine['run_identity'] != probable.run_identity):
                        continue
                    if current_population is None:
                        current_population = ({a.identity:a for a in owner.wo08.current_run()},
                                              owner.probables.load_current_run())
                    assessments, run = current_population
                    assessment = assessments.get(record.wo08_identity)
                    if assessment is None:
                        continue
                    data = assessment.data
                    result = owner.probables.load_result(record.probable_result_identity)
                    if (run is None or result not in run.results
                            or run.integrity_identity != data['run_integrity']
                            or result.integrity_identity != data['probable_result_integrity']):
                        raise ValueError('INTRADAY_DASHBOARD_PROBABLE_BINDING_INVALID')
                    if (assessment.integrity != record.wo08_integrity
                            or data['probable_result_identity'] != record.probable_result_identity
                            or data['subject'] != record.canonical_subject_identity
                            or data['session_identity'] != record.session_identity):
                        raise ValueError("INTRADAY_DASHBOARD_BINDING_INVALID")
                    if data.get('native_decision_identity') is not None:
                        native = owner.native.load(data['native_decision_identity'])
                        if native.integrity != data['native_decision_integrity']:
                            raise ValueError('INTRADAY_DASHBOARD_NATIVE_BINDING_INVALID')
                        native_current = owner.native.bound_identity(data['semantic_evidence_identity'])
                        if native_current is None:
                            raise ValueError('INTRADAY_DASHBOARD_NATIVE_SOURCE_UNAVAILABLE')
                        if native_current != data['native_decision_identity']:
                            continue
                    if record.market_family == 'MCX':
                        # A retained unavailable/hard-gated assessment may truthfully
                        # have no contract. It cannot contribute READY/NOW, and no
                        # current-session assessment is claimed for that subject.
                        if (record.exact_mcx_contract_identity is None
                                and record.exact_mcx_roll_lineage is None
                                and record.readiness_state in {ReadinessState.HARD_GATE, ReadinessState.READINESS_UNAVAILABLE}):
                            continue
                        binding = owner.bindings.load_current(canonical_subject_id=record.canonical_subject_identity)
                        if binding is None:
                            raise ValueError('INTRADAY_DASHBOARD_MCX_SOURCE_UNAVAILABLE')
                        if (binding.binding_identity != record.exact_mcx_roll_lineage
                                or binding.active_binding.derivative_contract_id != record.exact_mcx_contract_identity):
                            continue
                    owner._session(record, "readiness")
                    if (store.load_pointer(record.canonical_subject_identity) != pointer
                            or probable != owner.probables.load_current()
                            or machine != owner.wo08.current_pointer()):
                        raise ValueError("INTRADAY_DASHBOARD_SOURCE_CHANGED")
                except NewWorkNotEligible as error:
                    if error.reason.value == "ELIGIBILITY_AUTHORITY_UNAVAILABLE":
                        raise
                    continue
                except ValueError as error:
                    if str(error) == "WO10_SESSION_NOT_OPEN":
                        continue
                    raise
                current.append(record.readiness_identity)
                if record.readiness_state in {ReadinessState.BUY_NOW, ReadinessState.SELL_NOW, ReadinessState.BUY_READY, ReadinessState.SELL_READY}:
                    from kronos.intraday.sponsor_presentation import security_name, waiting_for
                    opportunities.append(dict(security=security_name(record.canonical_subject_identity),
                        subject=record.canonical_subject_identity, direction=record.direction,
                        status='Now' if record.satisfied_count == 5 else 'Ready',
                        waiting=waiting_for(data['criteria']), contract=record.exact_mcx_contract_identity,
                        monitoring=None if monitoring_projection is None else monitoring_projection(record.readiness_identity)))
                now += record.readiness_state in {ReadinessState.BUY_NOW, ReadinessState.SELL_NOW}
                ready += record.readiness_state in {ReadinessState.BUY_READY, ReadinessState.SELL_READY}
            if before != store.restore_current():
                raise ValueError("INTRADAY_DASHBOARD_SOURCE_CHANGED")
            return IntradayDashboardSummary(now, ready, "CURRENT_SESSION_VERIFIED" if current else "NO_CURRENT_READINESS", tuple(current), opportunities=tuple(opportunities))
    except (ValueError, OSError):
        return IntradayDashboardSummary()


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
    intraday: IntradayDashboardSummary = IntradayDashboardSummary()

    @property
    def now_count(self) -> int:
        return sum(
            item.classification in {
                Kr370AnalyticalClassification.BUY_NOW,
                Kr370AnalyticalClassification.SELL_NOW,
                "BUY_NOW", "SELL_NOW",
            }
            for item in self.swing_opportunities
        )

    @property
    def ready_count(self) -> int:
        return sum(
            item.classification in {
                Kr370AnalyticalClassification.BUY_READY,
                Kr370AnalyticalClassification.SELL_READY,
                "BUY_READY", "SELL_READY",
            }
            for item in self.swing_opportunities
        )


def project_sponsor_dashboard(
    snapshot: BrowserWorkspaceSnapshot,
    discovery: NativeDiscoveryRun | None,
    promotions: tuple[Kr370AnalyticalPromotionRecord, ...],
    notifications: NotificationWorkspaceSnapshot,
    ux10: Ux10NotificationSnapshot | None = None,
    *,
    promotions_v2: tuple[V2PromotionRecord, ...] = (),
    intraday: IntradayDashboardSummary = IntradayDashboardSummary(),
) -> SponsorDashboardProjection:
    """Project current facts without evaluating or mutating any source authority."""

    if (
        type(snapshot) is not BrowserWorkspaceSnapshot
        or type(intraday) is not IntradayDashboardSummary
        or (discovery is not None and type(discovery) is not NativeDiscoveryRun)
        or type(promotions) is not tuple
        or any(type(item) is not Kr370AnalyticalPromotionRecord for item in promotions)
        or type(promotions_v2) is not tuple
        or any(type(item) is not V2PromotionRecord for item in promotions_v2)
        or type(notifications) is not NotificationWorkspaceSnapshot
        or (ux10 is not None and type(ux10) is not Ux10NotificationSnapshot)
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
    current_v2: tuple[V2PromotionRecord, ...] = ()
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
        selected = tuple(item for item in promotions_v2
                         if item.value["source"]["native_run_identity"] == current.run_identity
                         and (item.value["source"]["canonical_instrument"],
                              item.value["source"]["native_assessment_sha256"]) in assessments)
        selected_ids = tuple(item.value["source"]["canonical_instrument"] for item in selected)
        if len(set(selected_ids)) != len(selected_ids):
            raise ValueError("SPONSOR_DASHBOARD_V2_AMBIGUOUS")
        if set(identities) & set(selected_ids):
            raise ValueError("SPONSOR_DASHBOARD_VERSION_MIXED")
        current_v2 = selected

    classification_order = {
        Kr370AnalyticalClassification.BUY_NOW: 0,
        Kr370AnalyticalClassification.SELL_NOW: 1,
        Kr370AnalyticalClassification.BUY_READY: 2,
        Kr370AnalyticalClassification.SELL_READY: 3,
    }
    swing_v1 = tuple(
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
    v2_order = {state: offset for offset, state in enumerate(
        ("BUY_NOW", "SELL_NOW", "BUY_READY", "SELL_READY", "NEAR_READY", "NO_FOCUS"))}
    swing_v2 = tuple(DashboardSwingOpportunity(
        item.value["source"]["canonical_instrument"], item.value["promotion_state"],
        item.value["source"]["native_run_identity"],
        item.value["source"]["native_assessment_sha256"],
        contract_version=2,
        disposition=item.value["evaluation_disposition"],
        confirmation=item.value["confirmation"]["state"],
    ) for item in sorted(current_v2, key=lambda item: (
        v2_order.get(item.value["promotion_state"], 99),
        item.value["source"]["canonical_instrument"])))
    swing = swing_v1 + swing_v2

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
    if ux10 is not None:
        issues.extend(
            DashboardIssue(item.notification_type.value, item.summary)
            for item in ux10.active_incidents
        )

    return SponsorDashboardProjection(
        current_run_identity=None if current is None else current.run_identity,
        swing_summary_available=bool(current_records or current_v2),
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
        intraday=intraday,
    )


__all__ = [
    "DashboardAlert",
    "DashboardIssue",
    "DashboardSwingOpportunity",
    "SponsorDashboardProjection",
    "project_sponsor_dashboard",
]
