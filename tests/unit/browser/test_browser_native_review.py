from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from zoneinfo import ZoneInfo
from urllib.parse import quote

from kronos.application.swing_native_review import (
    NativeReviewAnalysisOutcome,
    NativeReviewAnalysisState,
    NativeReviewWorkflow,
    project_native_analysis_details,
)
from kronos.application.swing_progression_watch import SwingProgressionWatchWorkflow
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.browser.server import create_browser_server
from kronos.browser.views import render_native_analysis_details, render_v1_review
from kronos.configuration.openai_chart_analyst import (
    ChartAnalystV2ActivationService,
    OpenAIChartAnalystCredentialService,
)
from kronos.swing.v1 import LocalTradingViewEvidenceStore
from kronos.swing.run_provenance import (
    LocalSwingRunProvenanceStore,
    SwingAnalysisRunProvenance,
)
from kronos.swing.v1.native_review import (
    McxReferenceEvidenceState,
    McxReferenceResult,
    McxReferenceStatus,
    NativeReviewEvidenceStore,
)
from kronos.swing.v1.mtf_facts import FactualTimeframe, MtfFactEvidenceStore
from kronos.swing.v1.native_discovery import (
    NativeDiscoveryEvidenceStore,
    NativeDiscoveryStatus,
    discover_native_mtf,
)
from kronos.swing.v1.models import V1Direction, V1Setup
from kronos.swing.v1.progression_watch import (
    ProgressionComparator,
    ProgressionRequirement,
    ProgressionRequirementState,
    ProgressionWatchStore,
)
from kronos.swing.v1.tradingview import ChartTimeframe
from kronos.swing.v1.visual_evidence_v2 import (
    VisualEvidenceV2ValidationDiagnostic,
    VisualEvidenceV2ValidationStage,
    VisualLevelAvailability,
    VisualObservationStatus,
    VisualTimeframe,
    VisualQuestionV2,
    VisualQuestionRouting,
    visual_question_routing,
)

from tests.unit.application.test_swing_opportunities import _Provider
from tests.unit.browser.test_browser_server import _request
from tests.unit.browser.test_browser_chart_analyst_credentials import (
    _CapabilityTester,
    _ProtectedBackend,
    _origin_headers,
)
from tests.unit.browser.test_browser_views import (
    _classified_run,
    _ready,
    _v1_probable,
)
from tests.unit.swing.v1.test_native_review import _evidence_run
from tests.unit.swing.v1.test_native_review_mcx_reference import _run_with_probables
from tests.unit.swing.v1.test_visual_evidence_v2 import _request as _visual_request
from tests.unit.swing.v1.test_visual_evidence_v2 import _response as _visual_response
from tests.unit.swing.v1.test_visual_evidence_v2 import _observation as _visual_observation
from tests.unit.swing.v1.test_native_review_chart_intake import _VisualV2Provider


def _population_run(
    base,
    *,
    run_identity: str,
    observed_at: datetime,
    probable_indices: frozenset[int],
    forming_index: int,
    unavailable_indices: frozenset[int],
):  # type: ignore[no-untyped-def]
    template = base.assessments[0]
    assessments = []
    for index, item in enumerate(base.assessments):
        common = {
            "run_identity": run_identity,
            "predecessor_result_sha256": None,
            "result_sha256": f"{index + 1:064x}",
        }
        if index in probable_indices:
            assessments.append(replace(
                item,
                **common,
                direction=template.direction,
                weekly_state=template.weekly_state,
                daily_state=template.daily_state,
                four_hour_state=template.four_hour_state,
                one_hour_state=template.one_hour_state,
                status=NativeDiscoveryStatus.PROBABLE,
                context_kind=template.context_kind,
                opportunity_identity=template.opportunity_identity,
                operative_anchor=template.operative_anchor,
                reason_codes=("ATOMIC_BINDING_TEST_PROBABLE",),
            ))
        elif index == forming_index:
            assessments.append(replace(
                item,
                **common,
                direction=template.direction,
                weekly_state=template.weekly_state,
                daily_state=template.daily_state,
                four_hour_state=template.four_hour_state,
                one_hour_state=template.one_hour_state,
                status=NativeDiscoveryStatus.FORMING_WATCH,
                context_kind=None,
                opportunity_identity=None,
                operative_anchor=None,
                reason_codes=("ATOMIC_BINDING_TEST_FORMING",),
            ))
        else:
            status = (
                NativeDiscoveryStatus.UNAVAILABLE
                if index in unavailable_indices
                else NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY
            )
            assessments.append(replace(
                item,
                **common,
                status=status,
                context_kind=None,
                opportunity_identity=None,
                operative_anchor=None,
                reason_codes=(f"ATOMIC_BINDING_TEST_{status.value}",),
            ))
    return replace(
        base,
        run_identity=run_identity,
        observed_at=observed_at,
        assessments=tuple(assessments),
        result_sha256=("c" if len(probable_indices) == 7 else "d") * 64,
    )


def test_review_renders_minimum_native_identity_and_preserves_header(tmp_path: Path) -> None:
    facts, run, probable = _evidence_run()
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    prepared = native.prepare(run, facts)
    legacy = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path / "legacy")
    ).snapshot()
    snapshot = _ready()

    html = render_v1_review(snapshot, legacy, prepared)

    assert "LAST SUCCESSFUL ANALYSIS" in html
    assert "ANALYSIS BOUNDARY" not in html
    assert probable.canonical_instrument in html
    assert probable.direction.value in html
    assert probable.opportunity_identity.value.replace("_", " ") in html
    assert probable.weekly_state.value in html
    assert probable.daily_state.value.replace("_", " ") in html
    assert probable.four_hour_state.value.replace("_", " ") in html
    assert probable.one_hour_state.value in html
    assert f"{probable.operative_anchor.price:g}" in html
    assert run.run_identity in html
    normal_card = html.split("<details class=\"native-diagnostics\">", 1)[0]
    assert run.run_identity not in normal_card
    assert "ANALYSIS DETAILS / DIAGNOSTICS" in html
    assert "NOT ANALYZED" in html
    assert f'native-direction-badge direction-{probable.direction.value.lower()}' in html
    assert "REFRESH REVIEW" in html
    assert "CREATE ALL REVIEW PDF" in html
    assert "ANALYZE ALL" not in html
    assert "ANALYZE NATIVE REVIEW" not in html
    assert "CHART REQUIRED" in html
    assert "TRADINGVIEW CHARTS" in html
    assert "TRADINGVIEW 4-CHART IMAGE · MISSING" in html
    assert "Required panels: 1W · 1D · 4H · 1H" in html
    assert html.count("Paste composite native chart") == 1
    assert "/swing/v1/native-chart?" in html
    assert "V1Layer1Assessment" not in html


def test_sponsor_failure_stays_concise_and_safe_cause_is_diagnostics_only(
    tmp_path: Path,
) -> None:
    facts, run, probable = _evidence_run()
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    prepared = native.prepare(run, facts)
    diagnostic = VisualEvidenceV2ValidationDiagnostic(
        native_run_identity=run.run_identity,
        canonical_instrument=probable.canonical_instrument,
        timeframe=VisualTimeframe.DAILY,
        chart_revision_sha256="a" * 64,
        model_identity="gpt-5.6-sol",
        attempt=1,
        api_request_completed=True,
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        response_status="completed",
        validation_stage=VisualEvidenceV2ValidationStage.FROZEN_DOMAIN_INVARIANT,
        validation_error_code="V2_LEVEL_AVAILABILITY_INCONSISTENT",
        structural_path="observations[6]",
        expected_constraint="AVAILABLE requires exactly one valid point or bounded zone",
        received_shape="enum=AVAILABLE + price=null + zone=null",
        retry_disposition="FAILED_FINAL",
        recorded_at=datetime(2026, 8, 16, 12, 0, tzinfo=UTC),
    )
    prepared = replace(
        prepared,
        analysis_outcomes=(NativeReviewAnalysisOutcome(
            probable.canonical_instrument,
            NativeReviewAnalysisState.ANALYSIS_FAILED,
            "FAILED",
            "SCHEMA VALIDATION FAILED",
        ),),
        visual_v2_diagnostics=(diagnostic,),
    )
    legacy = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path / "legacy")
    ).snapshot()

    html = render_v1_review(_ready(), legacy, prepared)
    normal_card, diagnostics = html.split(
        '<details class="native-diagnostics">', 1
    )

    assert "SCHEMA VALIDATION FAILED" not in normal_card
    assert "SCHEMA VALIDATION FAILED" in diagnostics
    assert "V2_LEVEL_AVAILABILITY_INCONSISTENT" not in normal_card
    assert "V2_LEVEL_AVAILABILITY_INCONSISTENT" in diagnostics
    assert "observations[6]" in diagnostics


def test_active_legacy_review_does_not_hide_native_prepare_control(
    tmp_path: Path,
) -> None:
    legacy = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path / "legacy")
    )
    legacy.publish_layer1(
        _classified_run({("NAUKRI", V1Setup.PULLBACK_CONTINUATION)})
    )
    native = NativeReviewWorkflow(
        NativeReviewEvidenceStore(tmp_path / "native"),
        chart_store=LocalTradingViewEvidenceStore(tmp_path / "shared"),
    )

    html = render_v1_review(
        replace(
            _ready(),
            swing_analysis_run_identity=(
                "SWING-RUN-0123456789ABCDEF0123456789ABCDEF"
            ),
        ),
        legacy.snapshot(),
        native.snapshot(),
    )

    assert "REFRESH REVIEW" in html
    assert "NAUKRI" in html


def test_native_direction_badges_are_green_for_long_and_red_for_short(
    tmp_path: Path,
) -> None:
    facts, run, _ = _evidence_run()
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    prepared = native.prepare(run, facts)
    long_html = render_v1_review(
        _ready(),
        SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ).snapshot(),
        prepared,
    )
    assert "native-direction-badge direction-long" in long_html

    requirement = prepared.requirements[0]
    short_requirement = replace(
        requirement,
        thesis=replace(requirement.thesis, direction=V1Direction.SHORT),
    )
    short_snapshot = replace(
        prepared,
        requirements=(short_requirement,),
        chart_packages=(),
    )
    short_html = render_v1_review(
        _ready(),
        SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy-short")
        ).snapshot(),
        short_snapshot,
    )
    assert "native-direction-badge direction-short" in short_html


def test_browser_prepares_native_review_from_same_application_run(tmp_path: Path) -> None:
    facts, run, probable = _evidence_run()
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    legacy = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path / "legacy")
    )
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    server = create_browser_server(
        application,
        port=0,
        v1_review=legacy,
        native_review=native,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, headers, _ = _request(
            server,
            "POST",
            "/swing/v1/native-review",
            headers={
                "Host": f"127.0.0.1:{server.server_port}",
                "Origin": f"http://127.0.0.1:{server.server_port}",
                "Referer": f"http://127.0.0.1:{server.server_port}/swing/v1-review",
                "Content-Length": "0",
            },
        )
        assert status == 303
        assert headers["Location"] == "/swing/v1-review"

        status, _, body = _request(server, "GET", "/swing/v1-review")
        assert status == 200
        assert probable.canonical_instrument in body
        assert run.run_identity in body
        assert "NOT ANALYZED" in body
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_opportunities_uses_native_population_and_keeps_layer1_separate(
    tmp_path: Path,
) -> None:
    facts, run, probable = _evidence_run()
    application = SwingOpportunitiesApplication(
        _Provider,
        initial_snapshot=replace(
            _ready(),
            swing_analysis_run_identity=run.run_identity,
            v1_probables=(_v1_probable("BDL"), _v1_probable("ALKEM")),
        ),
    )
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    native.prepare(run, facts)
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=native,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = _request(server, "GET", "/swing/opportunities")
        assert status == 200
        assert "Current successful KRONOS Native Discovery opportunities" in body
        assert probable.canonical_instrument in body
        assert probable.opportunity_identity.value.replace("_", " ") in body
        assert "FORMING / WATCH" in body
        assert "NO CURRENT OPPORTUNITY" in body
        assert "UNAVAILABLE" in body
        assert "Open Native Review" in body
        assert "/swing/v1-review" in body
        assert 'class="opportunity native-opportunity"' in body
        assert 'class="native-opportunity-actions"' in body
        assert ".native-opportunity .opp-identity h3{font-size:18px" in body
        assert ".native-opportunity-actions .button" in body
        assert "min-height:27px" in body
        assert "white-space:nowrap" in body
        assert "1W SUPPORTIVE" in body
        assert "1D BULLISH SWING REGIME" in body
        assert "4H STRUCTURAL HOLD" in body
        assert "1H NEUTRAL" in body
        assert "BDL" not in body
        assert "ALKEM" not in body
        assert "Current immutable Swing V1 Layer-1 Probables" not in body
        assert "V1 Layer-1 probable policy" not in body
        assert "direction-long" in body

        status, _, history = _request(server, "GET", "/swing/layer1-history")
        assert status == 200
        assert "Historical Swing V1 Layer-1 validation evidence" in history
        assert "BDL" in history
        assert "ALKEM" in history
        assert probable.canonical_instrument not in history
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_analysis_details_route_binds_exact_current_run_and_instrument(
    tmp_path: Path,
) -> None:
    facts, run, probable = _evidence_run()
    application = SwingOpportunitiesApplication(
        _Provider,
        initial_snapshot=replace(_ready(), swing_analysis_run_identity=run.run_identity),
    )
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    native.prepare(run, facts)
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=native,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        application_before = application.snapshot()
        native_before = native.snapshot()
        status, _, opportunities = _request(server, "GET", "/swing/opportunities")
        route = (
            f"/swing/analysis-details/{run.run_identity}/"
            f"{quote(probable.canonical_instrument, safe='')}"
        )
        assert status == 200
        assert f'href="{route}"' in opportunities
        assert "View Analysis Details" in opportunities
        assert "Requirements to progress" in opportunities

        status, _, body = _request(server, "GET", route)
        assert status == 200
        assert f"{probable.canonical_instrument} Analysis Details" in body
        assert (
            '<details class="analysis-section"><summary>'
            'A. WHAT KITE / NATIVE DISCOVERY SAYS</summary>' in body
        )
        assert (
            '<details class="analysis-section"><summary>'
            'B. WHAT THE TRADINGVIEW CHART / CHART ANALYST SAYS</summary>' in body
        )
        assert (
            '<section class="analysis-section"><h2>'
            'C. WHAT KRONOS RECONCILED</h2>' in body
        )
        assert '<section class="analysis-section"><h2>D. CURRENT DECISION</h2>' in body
        assert '<section class="analysis-section"><h2>E. REQUIREMENTS TO PROGRESS</h2>' in body
        assert '<section class="analysis-section analysis-next"><h2>F. WHAT HAPPENS NEXT</h2>' in body
        assert '<details class="analysis-section"><summary>G. TECHNICAL EVIDENCE</summary>' in body
        assert '<details open class="analysis-section"><summary>A.' not in body
        assert '<details open class="analysis-section"><summary>B.' not in body
        assert '<details open class="analysis-section"><summary>G.' not in body
        assert probable.direction.value in body
        assert probable.weekly_state.value in body
        assert probable.daily_state.value.replace("_", " ") in body
        assert probable.four_hour_state.value.replace("_", " ") in body
        assert probable.one_hour_state.value in body
        assert "NATIVE TEST PROBABLE" in body
        assert "Governed Visual V2 evidence is not yet available" in body
        assert "REVIEW REQUIRED" in body
        assert "REQUIREMENTS TO PROGRESS" in body
        assert "Native thesis intact" in body
        assert "EVIDENCE REQUIRED" in body
        assert "Activate Watch" not in body
        assert "does not authorize a trade" in body
        assert application.snapshot() == application_before
        assert native.snapshot() == native_before

        form = "requirement_id=" + "f" * 64
        foreign_status, _, _ = _request(
            server, "POST", "/swing/progression-watch/activate",
            body=form.encode(),
            headers={
                "Host": f"127.0.0.1:{server.server_port}",
                "Origin": "http://127.0.0.1:9999",
                "Referer": "http://127.0.0.1:9999/swing/opportunities",
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(form)),
            },
        )
        assert foreign_status == 403
        assert "TECHNICAL EVIDENCE" in body
        assert '<details class="analysis-section">' in body
        assert run.run_identity in body

        wrong_run = "SWING-RUN-" + "F" * 32
        assert _request(server, "GET", route.replace(run.run_identity, wrong_run))[0] == 404
        assert _request(server, "GET", route.rsplit("/", 1)[0] + "/UNKNOWN")[0] == 404
        swing_status, swing_headers, _ = _request(server, "GET", "/swing")
        assert swing_status == 303
        assert swing_headers["Location"] == "/swing/opportunities"
        assert _request(server, "GET", "/notifications")[0] == 200
        assert _request(server, "GET", "/intraday")[0] == 200
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_analysis_details_exposes_only_governed_watch_activation(tmp_path: Path) -> None:
    facts, run, probable = _evidence_run()
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    review = native.prepare(run, facts)
    details = project_native_analysis_details(
        run, review, run.run_identity, probable.canonical_instrument
    )
    assert details is not None
    requirement = ProgressionRequirement(
        "a" * 64, "SWING", probable.canonical_instrument,
        probable.direction, run.run_identity, probable.result_sha256,
        "WAIT_PULLBACK_DEVELOPING", "ONE_HOUR_PROGRESSION",
        "1H close above 1482.5", ProgressionRequirementState.WATCH_AVAILABLE,
        FactualTimeframe.ONE_HOUR, ProgressionComparator.BAR_CLOSE_ABOVE,
        1482.5, None, None, (probable.result_sha256,), run.observed_at,
        ("CONTROLLED_TEST_EVIDENCE",),
    )
    workflow = SwingProgressionWatchWorkflow(
        ProgressionWatchStore(tmp_path / "watches")
    )
    progression = workflow.synchronize(run.run_identity, (requirement,))

    body = render_native_analysis_details(_ready(), details, progression)

    assert "WATCH AVAILABLE" in body
    assert "Activate Watch" in body
    assert 'name="requirement_id"' in body
    assert "Bar close crosses above 1482.5" in body
    assert "KRONOS progression watch" in body
    assert "BUY ABOVE" not in body
    assert "ENTRY ABOVE" not in body


class _Ux01VisualProvider(_VisualV2Provider):
    def analyze(self, request):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        replacements = {
            question: _visual_observation(
                request,
                question,
                status=VisualObservationStatus.OBSERVED,
                observation="VISIBLE FACT",
            )
            for question, routing in visual_question_routing(request.timeframe)
            if routing is VisualQuestionRouting.YES
        }
        replacements[VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP] = (
            _visual_observation(
                request,
                VisualQuestionV2.VISUAL_SUPPORT_RESISTANCE_GAP,
                status=VisualObservationStatus.OBSERVED,
                observation="NONE",
                level=VisualLevelAvailability.NOT_APPLICABLE,
            )
        )
        for question in (
            VisualQuestionV2.CPR_CONTEXT,
            VisualQuestionV2.VISUAL_CONFLUENCE,
        ):
            if dict(request.routing)[question] is VisualQuestionRouting.YES:
                replacements[question] = _visual_observation(
                    request,
                    question,
                    status=VisualObservationStatus.PARTIAL,
                    observation="CHART LEVEL PARTIALLY VISIBLE",
                    level=VisualLevelAvailability.LEVEL_UNAVAILABLE,
                )
        if request.timeframe is VisualTimeframe.ONE_HOUR:
            replacements[VisualQuestionV2.PDH_PDL_REFERENCE_CONTEXT] = (
                _visual_observation(
                    request,
                    VisualQuestionV2.PDH_PDL_REFERENCE_CONTEXT,
                    status=VisualObservationStatus.PARTIAL,
                    observation="PDH PDL PARTIALLY VISIBLE",
                    level=VisualLevelAvailability.LEVEL_UNAVAILABLE,
                )
            )
        return _visual_response(request, replacements)


def test_analysis_details_projects_visual_layer2_readiness_without_new_authority(
    tmp_path: Path,
) -> None:
    facts, run, probable = _evidence_run()
    application = SwingOpportunitiesApplication(
        _Provider,
        initial_snapshot=replace(_ready(), swing_analysis_run_identity=run.run_identity),
    )
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    provider = _Ux01VisualProvider()
    native = NativeReviewWorkflow(
        NativeReviewEvidenceStore(tmp_path / "native"),
        chart_store=LocalTradingViewEvidenceStore(tmp_path / "charts"),
        visual_v2_provider=provider,
    )
    native.prepare(run, facts)
    native.upload_chart(
        instrument=probable.canonical_instrument,
        content_type="image/png",
        original_bytes=b"\x89PNG\r\n\x1a\nux01-composite",
    )
    native.analyze(probable.canonical_instrument)
    assert len(provider.requests) == 4
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=native,
    )
    before = native.snapshot()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, opportunities = _request(server, "GET", "/swing/opportunities")
        assert status == 200
        assert "CHART LEVELS NOT CONFIRMED" in opportunities
        assert "CPR · 1H PDH/PDL · Confluence Zone" in opportunities

        status, _, review_body = _request(server, "GET", "/swing/v1-review")
        assert status == 200
        assert "CHART LEVELS NOT CONFIRMED" in review_body
        assert "CPR · 1H PDH/PDL · Confluence Zone" in review_body
        assert "CONTEXT_INCOMPLETE" in review_body

        route = (
            f"/swing/analysis-details/{run.run_identity}/"
            f"{quote(probable.canonical_instrument, safe='')}"
        )
        status, _, body = _request(server, "GET", route)
        assert status == 200
        assert "WHAT THE TRADINGVIEW CHART / CHART ANALYST SAYS" in body
        assert "PARTIAL" in body
        assert "CHART LEVEL PARTIALLY VISIBLE" in body
        assert "LEVEL_UNAVAILABLE" in body
        assert ">NONE<" in body
        assert "NOT_VISIBLE" in body
        assert "NOT_APPLICABLE" in body
        assert "WHAT KRONOS RECONCILED" in body
        assert "PERSISTED READINESS CONDITIONS" in body
        assert before.readiness_records[0].conditions.thesis_intact.value.replace("_", " ") in body
        assert "CURRENT DECISION" in body
        assert before.readiness_records[0].primary_reason.replace("_", " ") in body
        assert "WHAT HAPPENS NEXT" in body
        assert "CHART LEVELS NOT CONFIRMED" in body
        assert "Missing evidence" in body
        assert "CPR" in body
        assert "1H PDH/PDL" in body
        assert "Confluence Zone" in body
        assert "CPR must be established" in body
        assert "1H PDH/PDL must be established" in body
        assert "Confluence Zone must be established" in body
        assert body.count("EVIDENCE REQUIRED") >= 3
        assert "Activate Watch" not in body
        assert "Internal readiness" in body
        assert "CONTEXT_INCOMPLETE" in body
        assert "Q2 CPR CONTEXT" in body
        assert "Chart revisions" in body
        assert "Evidence hashes" in body
        assert "Readiness policy" in body
        assert native.snapshot() == before
        assert len(provider.requests) == 4
        assert "place_order" not in body
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_opportunities_atomically_binds_header_population_and_cards_to_current_run(
    tmp_path: Path,
) -> None:
    facts, base, _ = _evidence_run()
    old_run = _population_run(
        base,
        run_identity=base.run_identity,
        observed_at=base.observed_at,
        probable_indices=frozenset(range(7)),
        forming_index=80,
        unavailable_indices=frozenset(range(81, 98)),
    )
    new_run_identity = "SWING-RUN-4A7E577DC8004D99AE913B7EEEC511C9"
    new_observed_at = base.observed_at + timedelta(minutes=10)
    new_run = _population_run(
        base,
        run_identity=new_run_identity,
        observed_at=new_observed_at,
        probable_indices=frozenset(range(6, 18)),
        forming_index=79,
        unavailable_indices=frozenset(range(80, 98)),
    )
    snapshot = replace(
        _ready(),
        swing_analysis_run_identity=new_run_identity,
        run_created_at=new_observed_at - timedelta(minutes=2),
        completed_at=new_observed_at,
    )
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=snapshot)
    application.restore_native_discovery_run(new_run)
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    native.prepare(old_run, facts)
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=native,
    )
    # Reproduce the diagnosed defect: Review internals remain bound to the old run.
    server.native_review_run = old_run
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    old_only = old_run.assessments[0].canonical_instrument
    new_only = new_run.assessments[17].canonical_instrument
    try:
        status, _, body = _request(server, "GET", "/swing/opportunities")

        assert status == 200
        assert "<span>PROBABLE</span><strong>12</strong>" in body
        assert "<span>FORMING / WATCH</span><strong>1</strong>" in body
        assert "<span>NO CURRENT OPPORTUNITY</span><strong>67</strong>" in body
        assert "<span>UNAVAILABLE</span><strong>18</strong>" in body
        assert new_only in body
        assert old_only not in body
        assert "REVIEW REQUIRED" in body
        assert "REVIEW NOT PREPARED" not in body
        assert (
            new_observed_at.astimezone(ZoneInfo("Asia/Kolkata"))
            .strftime("%d %b %Y %H:%M")
            .upper()
            in body
        )
        assert server.native_review_run is old_run
        assert application.opportunities_projection() == (snapshot, new_run)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_opportunities_restores_latest_successful_native_population_after_restart(
    tmp_path: Path,
) -> None:
    facts, _, _ = _evidence_run()
    run = discover_native_mtf(facts)
    mtf_store = MtfFactEvidenceStore(tmp_path / "mtf")
    native_store = NativeDiscoveryEvidenceStore(tmp_path / "discovery")
    provenance_store = LocalSwingRunProvenanceStore(tmp_path / "provenance")
    mtf_store.retain(facts)
    native_store.retain(run)
    provenance_store.retain(SwingAnalysisRunProvenance(
        run_id=run.run_identity,
        run_created_at=run.observed_at,
        analysis_boundary=run.observed_at,
        market_data_snapshot_identity=(
            "SWING-MARKET-DATA-SNAPSHOT-" + "a" * 64
        ),
        successful_completed_at=run.observed_at,
    ))
    restarted = SwingOpportunitiesApplication(
        _Provider,
        initial_snapshot=replace(
            _ready(),
            v1_probables=(_v1_probable("BDL"),),
        ),
        mtf_fact_evidence_store=mtf_store,
        native_discovery_evidence_store=native_store,
        run_provenance_store=provenance_store,
    )
    server = create_browser_server(
        restarted,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=NativeReviewWorkflow(
            NativeReviewEvidenceStore(tmp_path / "native")
        ),
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = _request(server, "GET", "/swing/opportunities")
        assert status == 200
        assert "Native Discovery unavailable" not in body
        assert (
            f'<span>PROBABLE</span><strong>{sum(item.status is NativeDiscoveryStatus.PROBABLE for item in run.assessments)}</strong>'
            in body
        )
        assert "BDL" not in body
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_browser_native_upload_route_uses_native_slot_binding(tmp_path: Path) -> None:
    facts, run, probable = _evidence_run()
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    shared = LocalTradingViewEvidenceStore(tmp_path / "shared")
    legacy = SwingV1ReviewWorkflow(shared)
    native = NativeReviewWorkflow(
        NativeReviewEvidenceStore(tmp_path / "native"),
        chart_store=shared,
    )
    native.prepare(run, facts)
    server = create_browser_server(
        application, port=0, v1_review=legacy, native_review=native
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    authority = f"127.0.0.1:{server.server_port}"
    headers = {
        "Host": authority,
        "Origin": f"http://{authority}",
        "Referer": f"http://{authority}/swing/v1-review",
        "Content-Type": "image/png",
    }
    image = b"\x89PNG\r\n\x1a\nnative"
    try:
        status, _, _ = _request(
            server,
            "POST",
            (
                "/swing/v1/native-chart?instrument="
                f"{probable.canonical_instrument}&subject=native"
            ),
            headers={**headers, "Content-Length": str(len(image))},
            body=image,
        )
        assert status == 303
        package = native.snapshot().chart_packages[0]
        assert package.active_revisions[0].timeframe is ChartTimeframe.COMPOSITE
        assert package.binding.native_assessment_sha256 == probable.result_sha256

        status, _, _ = _request(
            server,
            "POST",
            "/swing/v1/native-chart?instrument=WRONG&subject=native",
            headers={**headers, "Content-Length": str(len(image))},
            body=image,
        )
        assert status == 400
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_browser_analyze_all_uses_governed_native_pipeline_and_persists_readiness(
    tmp_path: Path,
) -> None:
    facts, run, probable = _evidence_run()
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    store = NativeReviewEvidenceStore(tmp_path / "native")
    charts = LocalTradingViewEvidenceStore(tmp_path / "charts")
    provider = _VisualV2Provider()
    native = NativeReviewWorkflow(
        store,
        chart_store=charts,
        visual_v2_provider=provider,
    )
    native.prepare(run, facts)
    native.upload_chart(
        instrument=probable.canonical_instrument,
        content_type="image/png",
        original_bytes=b"\x89PNG\r\n\x1a\nbrowser-composite",
    )
    backend = _ProtectedBackend()
    backend.stored = True
    credentials = OpenAIChartAnalystCredentialService(
        provisioner=backend,
        presence_probe=backend,
        capability_tester=_CapabilityTester(),
    )
    activation = ChartAnalystV2ActivationService(tmp_path / "activation.json")
    activation.set_enabled(True)
    server = create_browser_server(
        application,
        port=0,
        native_review=native,
        chart_analyst_credentials=credentials,
        chart_analyst_activation=activation,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, headers, _ = _request(
            server,
            "POST",
            "/swing/v1/native-analyze-all",
            headers=_origin_headers(server),
        )
        assert status == 303
        assert headers["Location"] == "/swing/v1-review"
        assert len(provider.requests) == 4
        status, _, body = _request(server, "GET", "/swing/v1-review")
        assert status == 200
        assert "READY FOR REVIEW" in body
        assert "WHY THIS TRADE?" in body
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    restored = NativeReviewWorkflow(
        store,
        chart_store=charts,
        visual_v2_provider=provider,
    )
    snapshot = restored.restore(run, facts)
    assert len(snapshot.readiness_records) == 1
    assert snapshot.readiness_records[0].canonical_instrument == (
        probable.canonical_instrument
    )


def test_browser_individual_analyze_invokes_only_bound_native_candidate(
    tmp_path: Path,
) -> None:
    facts, run, probable = _evidence_run()
    application = SwingOpportunitiesApplication(_Provider, initial_snapshot=_ready())
    application.restore_mtf_fact_snapshot(facts)
    application.restore_native_discovery_run(run)
    provider = _VisualV2Provider()
    native = NativeReviewWorkflow(
        NativeReviewEvidenceStore(tmp_path / "native"),
        chart_store=LocalTradingViewEvidenceStore(tmp_path / "charts"),
        visual_v2_provider=provider,
    )
    native.prepare(run, facts)
    native.upload_chart(
        instrument=probable.canonical_instrument,
        content_type="image/png",
        original_bytes=b"\x89PNG\r\n\x1a\nindividual-composite",
    )
    backend = _ProtectedBackend()
    backend.stored = True
    credentials = OpenAIChartAnalystCredentialService(
        provisioner=backend,
        presence_probe=backend,
        capability_tester=_CapabilityTester(),
    )
    activation = ChartAnalystV2ActivationService(tmp_path / "activation.json")
    activation.set_enabled(True)
    server = create_browser_server(
        application,
        port=0,
        native_review=native,
        chart_analyst_credentials=credentials,
        chart_analyst_activation=activation,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, headers, _ = _request(
            server,
            "POST",
            f"/swing/v1/native-analyze?instrument={probable.canonical_instrument}",
            headers=_origin_headers(server),
        )
        assert status == 303
        assert headers["Location"] == "/swing/v1-review"
        assert len(provider.requests) == 4
        assert {
            request.requirement.canonical_instrument
            for request in provider.requests
        } == {probable.canonical_instrument}
        assert len(native.snapshot().readiness_records) == 1
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_review_shows_compact_mcx_reference_requirement_and_status(tmp_path: Path) -> None:
    facts, run = _run_with_probables("GOLDM")
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    prepared = native.prepare(run, facts)
    legacy = SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path / "legacy")).snapshot()

    html = render_v1_review(_ready(), legacy, prepared)

    assert "GOLDM" in html
    assert "COMEX · COMEX:GC1!" in html
    assert "Reference status</span><strong>REQUIRED" in html
    assert "Reference evidence</span><strong>UNAVAILABLE" in html
    assert "SAME RUN REQUIREMENT" in html


def test_goldm_review_uses_one_shared_composite_upload_control(tmp_path: Path) -> None:
    facts, run = _run_with_probables("GOLDM")
    native = NativeReviewWorkflow(
        NativeReviewEvidenceStore(tmp_path / "native"),
        chart_store=LocalTradingViewEvidenceStore(tmp_path / "charts"),
    )
    native.prepare(run, facts)
    native.upload_chart(
        instrument="GOLDM",
        content_type="image/png",
        original_bytes=b"\x89PNG\r\n\x1a\ngoldm-shared-composite",
    )
    legacy = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path / "legacy")
    ).snapshot()

    html = render_v1_review(_ready(), legacy, native.snapshot())

    assert html.count("GOLDM TRADINGVIEW COMPOSITE") == 1
    assert html.count("subject=native") >= 1
    assert "subject=reference" not in html
    assert "COMEX 1D · COMEX 4H · COMEX 1H · MCX GOLDM 1H" in html


def test_goldm_review_presents_received_reference_without_second_upload(
    tmp_path: Path,
) -> None:
    facts, run = _run_with_probables("GOLDM")
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    prepared = native.prepare(run, facts)
    reference = prepared.requirements[0].mcx_reference
    assert reference is not None
    native.ingest_reference(McxReferenceResult(
        reference,
        McxReferenceStatus.RECEIVED,
        McxReferenceEvidenceState.UNAVAILABLE,
        "a" * 64,
        "b" * 64,
        tuple(
            (timeframe, datetime(2026, 8, 17, 8, 30, tzinfo=UTC))
            for timeframe in ("1D", "4H", "1H")
        ),
        ("SPONSOR_MEDIATED_PDF",),
        "SAME_RUN_REFERENCE_BOUND",
        "REFERENCE_VISUAL_EVIDENCE_RECEIVED_RECONCILIATION_PENDING",
    ))
    legacy = SwingV1ReviewWorkflow(
        LocalTradingViewEvidenceStore(tmp_path / "legacy")
    ).snapshot()

    html = render_v1_review(_ready(), legacy, native.snapshot())

    assert "Reference status</span><strong>RECEIVED" in html
    assert "Reference evidence</span><strong>RECEIVED" in html
    assert "Reference consequence</span><strong>UNAVAILABLE" in html
    assert "Binding</span><strong>SAME_RUN_REFERENCE_BOUND" in html
    assert "subject=reference" not in html


def test_review_shows_minimum_visual_v2_diagnostics(tmp_path: Path) -> None:
    facts, run, _ = _evidence_run()
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    native.prepare(run, facts)
    request = _visual_request()
    response = _visual_response(request)
    unreadable = replace(
        response.observations[1],
        observation_status=VisualObservationStatus.OBSERVED,
        observation="CPR VISIBLE; VALUE UNREADABLE",
        level_availability=VisualLevelAvailability.LEVEL_UNAVAILABLE,
    )
    response = replace(
        response,
        observations=(response.observations[0], unreadable, *response.observations[2:]),
    )
    native.ingest_visual_v2(request, response)
    legacy = SwingV1ReviewWorkflow(LocalTradingViewEvidenceStore(tmp_path / "legacy")).snapshot()

    html = render_v1_review(_ready(), legacy, native.snapshot())

    assert "SWING-V1-VISUAL-QUESTION-SET-V2" in html
    assert "ANALYZED · 10 OBS · 1 LEVEL UNAVAILABLE" in html
    assert "Chart revision" in html
    assert request.chart_revision_sha256 in html
    assert "Evidence integrity" in html
    assert response.evidence_sha256 in html
