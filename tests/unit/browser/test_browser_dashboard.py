from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Thread

from kronos.application.notifications import (
    ManagedNotification,
    NotificationProduct,
    NotificationState,
    NotificationWorkspaceSnapshot,
)
from kronos.application.swing_notifications import project_swing_notification_workspace
from kronos.application.swing_opportunities import (
    AnalysisState,
    ProviderConnectionState,
    SwingOpportunitiesApplication,
)
from kronos.application.swing_progression_watch import (
    SwingProgressionWatchSnapshot,
    SwingProgressionWatchWorkflow,
)
from kronos.application.swing_visual_v3 import SwingVisualV3ReviewCycle
from kronos.browser.dashboard import project_sponsor_dashboard
from kronos.browser.server import create_browser_server
from kronos.browser.views import render_dashboard
from kronos.swing.v1.analytical_promotion import (
    Kr370AnalyticalClassification,
    Kr370AnalyticalPromotionRecord,
    kr370_promotion_integrity_sha256,
)
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_discovery import Native1HState, NativeDiscoveryStatus
from kronos.swing.v1.native_readiness_v3 import NativeLayer2ReadinessV3Store
from kronos.swing.v1.native_review import NativeReviewEvidenceStore
from kronos.swing.v1.progression_watch import ProgressionWatchStore
from kronos.swing.v1.visual_evidence_v3 import LocalVisualEvidenceV3Store
from kronos.application.swing_native_review import NativeReviewWorkflow
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.browser.test_browser_server import _request
from tests.unit.swing.v1.test_kr370_step31_handoff import _completed
from tests.unit.swing.v1.test_native_review import _evidence_run


NOW = datetime(2026, 8, 21, 8, 0, tzinfo=UTC)
RUN = "SWING-RUN-0123456789ABCDEF0123456789ABCDEF"


def _bound_record(
    template: Kr370AnalyticalPromotionRecord,
    instrument: str,
    assessment_sha256: str,
    *,
    run_identity: str = RUN,
) -> Kr370AnalyticalPromotionRecord:
    payload = {field.name: getattr(template, field.name) for field in fields(template)}
    payload.update(
        run_identity=run_identity,
        canonical_instrument=instrument,
        native_assessment_sha256=assessment_sha256,
    )
    payload["integrity_sha256"] = kr370_promotion_integrity_sha256(payload)
    return Kr370AnalyticalPromotionRecord(**payload)


def _sources(tmp_path: Path, specs):  # type: ignore[no-untyped-def]
    _, base, probable = _evidence_run()
    assessments = []
    records = []
    for index, (scenario, expected) in enumerate(specs):
        source = base.assessments[index]
        digest = sha256(source.canonical_instrument.encode()).hexdigest()
        completed = _completed(tmp_path / str(index), **scenario)
        assert completed.promotion is not None
        assert completed.promotion.classification is expected
        assessment = replace(
            probable,
            canonical_instrument=source.canonical_instrument,
            direction=completed.promotion.direction,
            status=NativeDiscoveryStatus.PROBABLE,
            result_sha256=digest,
        )
        assessments.append(assessment)
        records.append(_bound_record(
            completed.promotion, source.canonical_instrument, digest,
        ))
    run = replace(
        base,
        assessments=tuple(assessments) + base.assessments[len(assessments):],
        result_sha256="d" * 64,
    )
    snapshot = replace(_ready(), swing_analysis_run_identity=run.run_identity)
    return snapshot, run, tuple(records)


def _notification(
    instrument: str,
    state: NotificationState,
    *,
    run_identity: str = RUN,
    offset: int = 0,
) -> ManagedNotification:
    observed = NOW + timedelta(minutes=offset)
    return ManagedNotification(
        f"WATCH-{instrument}-{offset}", NotificationProduct.SWING, instrument,
        "LONG", "ONE_HOUR_PROGRESSION", "1H close above governed level",
        "1H", "BAR_CLOSE_ABOVE", "1482.5", run_identity, NOW, state,
        observed if state is NotificationState.TRIGGERED else None,
        "REASSESSMENT REQUIRED" if state is NotificationState.TRIGGERED else "",
        "REASSESSMENT_REQUIRED", (), state is NotificationState.ACTIVE,
    )


def test_current_exact_kr370_now_and_ready_states_are_the_only_swing_summary(
    tmp_path: Path,
) -> None:
    snapshot, run, records = _sources(tmp_path, (
        ({}, Kr370AnalyticalClassification.BUY_NOW),
        ({"direction": V1Direction.SHORT}, Kr370AnalyticalClassification.SELL_NOW),
        ({"extended": True}, Kr370AnalyticalClassification.BUY_READY),
        ({"direction": V1Direction.SHORT, "extended": True},
         Kr370AnalyticalClassification.SELL_READY),
        ({"cpr_accepted": False, "path_clear": False},
         Kr370AnalyticalClassification.POTENTIAL_BUY_SETUP),
        ({"progression": Native1HState.NEUTRAL, "cpr_accepted": False,
          "path_clear": False, "extended": True},
         Kr370AnalyticalClassification.NO_SETUP),
        ({"path_clear": None}, Kr370AnalyticalClassification.NO_SETUP),
    ))
    projection = project_sponsor_dashboard(
        snapshot, run, records, NotificationWorkspaceSnapshot(()),
    )
    html = render_dashboard(snapshot, projection)

    assert projection.now_count == 2
    assert projection.ready_count == 2
    assert tuple(item.classification for item in projection.swing_opportunities) == (
        Kr370AnalyticalClassification.BUY_NOW,
        Kr370AnalyticalClassification.SELL_NOW,
        Kr370AnalyticalClassification.BUY_READY,
        Kr370AnalyticalClassification.SELL_READY,
    )
    for state in ("BUY NOW", "SELL NOW", "BUY READY", "SELL READY"):
        assert state in html
    for record in records[:4]:
        assert record.canonical_instrument in html
        assert (
            f'/swing/analysis-details/{RUN}/{record.canonical_instrument}' in html
        )
    for record in records[4:]:
        assert record.canonical_instrument not in html
    for forbidden in (
        "POTENTIAL BUY SETUP", "POTENTIAL SELL SETUP", "NOT EVALUABLE",
        "K1", "K2", "ENTRY", "STOP", "TARGET", "R:R",
    ):
        assert forbidden not in html


def test_stale_or_wrong_assessment_promotions_fail_closed(tmp_path: Path) -> None:
    snapshot, run, records = _sources(tmp_path, (
        ({}, Kr370AnalyticalClassification.BUY_NOW),
    ))
    stale = _bound_record(
        records[0], records[0].canonical_instrument,
        records[0].native_assessment_sha256,
        run_identity="SWING-RUN-" + "F" * 32,
    )
    wrong_assessment = _bound_record(
        records[0], records[0].canonical_instrument, "f" * 64,
    )

    projection = project_sponsor_dashboard(
        snapshot, run, (stale, wrong_assessment), NotificationWorkspaceSnapshot(()),
    )
    assert projection.swing_summary_available is False
    assert projection.swing_opportunities == ()
    assert "CURRENT SWING RESULTS UNAVAILABLE" in render_dashboard(snapshot, projection)


def test_current_non_actionable_records_and_missing_records_have_distinct_empty_states(
    tmp_path: Path,
) -> None:
    snapshot, run, records = _sources(tmp_path, (
        ({"cpr_accepted": False, "path_clear": False},
         Kr370AnalyticalClassification.POTENTIAL_BUY_SETUP),
    ))
    bounded = project_sponsor_dashboard(
        snapshot, run, records, NotificationWorkspaceSnapshot(()),
    )
    unavailable = project_sponsor_dashboard(
        snapshot, run, (), NotificationWorkspaceSnapshot(()),
    )

    assert bounded.swing_summary_available is True
    assert bounded.swing_opportunities == ()
    assert "NO BUY/SELL NOW OR READY OPPORTUNITIES" in render_dashboard(
        snapshot, bounded,
    )
    assert unavailable.swing_summary_available is False
    assert "CURRENT SWING RESULTS UNAVAILABLE" in render_dashboard(
        snapshot, unavailable,
    )


def test_alert_preview_uses_only_current_active_authoritative_records_and_is_bounded(
    tmp_path: Path,
) -> None:
    snapshot, run, records = _sources(tmp_path, (
        ({}, Kr370AnalyticalClassification.BUY_NOW),
    ))
    old_run = "SWING-RUN-" + "E" * 32
    workspace = NotificationWorkspaceSnapshot((
        _notification("RELIANCE", NotificationState.ACTIVE),
        _notification("CANBK", NotificationState.TRIGGERED, offset=1),
        _notification("CDSL", NotificationState.ACTIVE, offset=2),
        _notification("SAIL", NotificationState.ACTIVE, offset=3),
        _notification("RVNL", NotificationState.INACTIVE, offset=4),
        _notification("OLD", NotificationState.TRIGGERED,
                      run_identity=old_run, offset=5),
    ))
    projection = project_sponsor_dashboard(snapshot, run, records, workspace)
    html = render_dashboard(snapshot, projection)

    assert tuple(item.instrument for item in projection.active_alerts) == (
        "RELIANCE", "CANBK", "CDSL",
    )
    assert "SAIL" not in html and "RVNL" not in html and "OLD" not in html
    assert 'href="/notifications"' in html
    empty = project_sponsor_dashboard(
        snapshot, run, records, NotificationWorkspaceSnapshot(()),
    )
    assert "NO ACTIVE ALERTS" in render_dashboard(snapshot, empty)


def test_system_issues_are_factual_and_have_a_bounded_empty_state(tmp_path: Path) -> None:
    snapshot, run, records = _sources(tmp_path, (
        ({}, Kr370AnalyticalClassification.BUY_NOW),
    ))
    healthy = project_sponsor_dashboard(
        snapshot, run, records, NotificationWorkspaceSnapshot(()),
    )
    failed_snapshot = replace(
        snapshot,
        provider_state=ProviderConnectionState.DISCONNECTED,
        analysis_state=AnalysisState.ERROR,
        analysis_failure="SWING_ANALYSIS_FAILED",
    )
    failed = project_sponsor_dashboard(
        failed_snapshot, run, records, NotificationWorkspaceSnapshot(()),
    )

    assert healthy.issues == ()
    assert "NO CURRENT SYSTEM / DATA ISSUES" in render_dashboard(snapshot, healthy)
    assert tuple(item.identity for item in failed.issues) == (
        "KITE_DISCONNECTED", "SWING_ANALYSIS_FAILURE",
    )
    failed_html = render_dashboard(failed_snapshot, failed)
    assert "Kite is disconnected." in failed_html
    assert "Swing analysis failed." in failed_html
    assert "HIGH" not in failed_html and "MEDIUM" not in failed_html


def test_strategy_colours_and_responsive_grid_are_presentation_only(tmp_path: Path) -> None:
    snapshot, run, records = _sources(tmp_path, (
        ({}, Kr370AnalyticalClassification.BUY_NOW),
    ))
    html = render_dashboard(
        snapshot,
        project_sponsor_dashboard(
            snapshot, run, records, NotificationWorkspaceSnapshot(()),
        ),
    )

    assert ".strategy-card.swing{--strategy-line:#256da4" in html
    assert ".strategy-card.intraday{--strategy-line:#24714a" in html
    assert ".strategy-card.theta{--strategy-line:#60458a" in html
    assert ".strategy-card.fundamental{--strategy-line:#786020" in html
    assert ".strategy-grid{display:grid;grid-template-columns:repeat(4" in html
    assert ".strategy-grid{grid-template-columns:repeat(2" in html
    assert ".status-grid,.strategy-grid{grid-template-columns:1fr}" in html


def test_dashboard_route_restores_current_sources_and_is_read_only(
    tmp_path: Path,
) -> None:
    completed = _completed(tmp_path)
    assert completed.promotion is not None
    facts, run, _ = _evidence_run()
    application = SwingOpportunitiesApplication(
        _Provider,
        initial_snapshot=replace(_ready(), swing_analysis_run_identity=run.run_identity),
    )
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    cycle = SwingVisualV3ReviewCycle(
        LocalVisualEvidenceV3Store(tmp_path / "visual-v3"),
        NativeLayer2ReadinessV3Store(tmp_path / "readiness-v3"),
    )
    cycle.restore_completed(completed)
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=NativeReviewWorkflow(
            NativeReviewEvidenceStore(tmp_path / "native")
        ),
        progression_watches=SwingProgressionWatchWorkflow(
            ProgressionWatchStore(tmp_path / "watches")
        ),
        visual_v3=cycle,
    )
    before = application.opportunities_projection()
    completed_before = cycle.completed_snapshot()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, html = _request(server, "GET", "/dashboard")
        assert status == 200
        assert "Strategy Command Centre" in html
        assert "BUY NOW" in html
        assert completed.requirement.canonical_instrument in html
        assert "SUMMARY NOT YET ACTIVATED" in html
        assert 'href="/intraday"' in html
        assert 'href="/theta-earners"' in html
        assert "FUNDAMENTAL" in html and "RESERVED" in html
        assert "Dashboard workspace is reserved" not in html
        assert "/step31" not in html
        assert "SEND TELEGRAM" not in html
        assert "PLACE ORDER" not in html
        assert application.opportunities_projection() == before
        assert cycle.completed_snapshot() == completed_before
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert project_swing_notification_workspace(
        SwingProgressionWatchSnapshot(run.run_identity, (), ())
    ).records == ()
