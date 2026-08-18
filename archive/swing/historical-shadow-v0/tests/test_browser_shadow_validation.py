from datetime import UTC, datetime

from kronos.application.swing_opportunities import (
    AnalysisState,
    BrowserWorkspaceSnapshot,
    ProviderConnectionState,
)
from kronos.browser.views import render_shadow_validation
from kronos.swing.v1.models import StructuralState, V1Direction, V1Setup
from kronos.swing.v1.shadow_mtf import (
    DailyControlEvidence,
    DailyControlProbableIdentity,
    ShadowTimeframe,
    TimeframeStructuralEvidence,
    reconcile_shadow_candidate,
)


NOW = datetime(2026, 8, 14, tzinfo=UTC)


def _ready() -> BrowserWorkspaceSnapshot:
    return BrowserWorkspaceSnapshot(
        ProviderConnectionState.CONNECTED,
        AnalysisState.READY,
        98,
    )


def _assessment():
    def timeframe(identity, state, *, setup=None, direction=V1Direction.NONE, remainder=False):
        return TimeframeStructuralEvidence(
            identity,
            NOW,
            state,
            setup,
            direction,
            "WAIT_FOR_COMPLETED_STRUCTURE_ACCEPTANCE",
            ("SWING_HIGH:128.5",),
            "AVAILABLE",
            True,
            remainder,
        )
    return reconcile_shadow_candidate(
        run_identity="RUN-001",
        provider_source_identity="KITE-SNAPSHOT",
        canonical_instrument="RELIANCE",
        control=DailyControlEvidence(
            False, None, V1Direction.NONE, "DAILY_CONTROL_NOT_CANDIDATE", NOW
        ),
        weekly=timeframe(ShadowTimeframe.WEEKLY, StructuralState.BULLISH_HH_HL),
        daily=timeframe(ShadowTimeframe.DAILY, StructuralState.BULLISH_HH_HL),
        four_hour=timeframe(
            ShadowTimeframe.FOUR_HOUR,
            StructuralState.BULLISH_HH_HL,
            setup=V1Setup.PULLBACK_CONTINUATION,
            direction=V1Direction.LONG,
            remainder=True,
        ),
        one_hour=timeframe(ShadowTimeframe.ONE_HOUR, StructuralState.BULLISH_HH_HL),
        remainder_material_to_change=True,
    )


def test_control_shadow_view_is_compact_expanded_and_explicitly_non_authoritative() -> None:
    rendered = render_shadow_validation(_ready(), (_assessment(),))
    for text in (
        "VALIDATION EXPERIMENT",
        "SHADOW — NO TRADING AUTHORITY",
        "DAILY CONTROL",
        "MTF SHADOW",
        "View Analysis",
        "WHAT AM I WAITING FOR?",
        "CHART-HEALTH EVENT",
        "READINESS REQUIRES SEPARATE REASSESSMENT",
        "Sponsor independent observation",
        "IMPULSE / PULLBACK",
        "KEY LEVELS",
        "PARTICIPATION",
        "MATURITY / CHASE",
        "CONTRADICTIONS",
        "LEVEL UNAVAILABLE",
    ):
        assert text in rendered


def test_view_shows_all_timeframes_and_remainder_dependency_tag() -> None:
    rendered = render_shadow_validation(_ready(), (_assessment(),))
    assert "1W" in rendered
    assert "1D" in rendered
    assert "4H" in rendered
    assert "1H" in rendered
    assert "COMPLETED 4H SESSION-REMAINDER BUCKET" in rendered
    assert "CURRENT DAILY LAYER-1" not in rendered


def test_view_preserves_all_daily_control_probable_identities() -> None:
    assessment = _assessment()
    control = DailyControlEvidence(
        True,
        None,
        V1Direction.NONE,
        "UNCHANGED_DAILY_LAYER1_MULTIPLE_PROBABLES",
        NOW,
        (
            DailyControlProbableIdentity(
                V1Setup.PULLBACK_CONTINUATION,
                V1Direction.LONG,
            ),
            DailyControlProbableIdentity(
                V1Setup.CONSOLIDATION_BREAKOUT,
                V1Direction.LONG,
            ),
        ),
    )
    rendered = render_shadow_validation(
        _ready(),
        (
            type(assessment)(
                assessment.run_identity,
                assessment.provider_source_identity,
                assessment.canonical_instrument,
                control,
                assessment.weekly,
                assessment.daily,
                assessment.four_hour,
                assessment.one_hour,
                assessment.state,
                assessment.setup,
                assessment.direction,
                assessment.primary_reason,
                assessment.contradictions,
                assessment.session_remainder_dependent_change,
            ),
        ),
    )
    assert "Control YES" in rendered
    assert "PULLBACK_CONTINUATION LONG" in rendered
    assert "CONSOLIDATION_BREAKOUT LONG" in rendered
