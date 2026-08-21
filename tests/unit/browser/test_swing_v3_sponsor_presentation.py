import copy
from dataclasses import replace
from pathlib import Path
from threading import Thread

import pytest

from kronos.application.swing_native_review import (
    NativeAnalysisDetailsProjection,
    NativeReviewWorkflow,
)
from kronos.application.swing_opportunities import SwingOpportunitiesApplication
from kronos.application.swing_notifications import project_swing_notification_workspace
from kronos.application.swing_progression_watch import SwingProgressionWatchWorkflow
from kronos.application.swing_v1_review import SwingV1ReviewWorkflow
from kronos.application.swing_visual_v3 import (
    CompletedVisualV3Review,
    SwingVisualV3ReviewCycle,
)
from kronos.browser.server import create_browser_server
from kronos.browser.swing_v3_presentation import (
    Kr370SponsorPromotionPresentation,
    present_visual_v3_review,
)
from kronos.browser.views import render_native_analysis_details, render_opportunities
from kronos.swing.v1.mtf_facts import FactualTimeframe
from kronos.swing.v1.native_readiness import (
    ConditionEvidence,
    DeterministicRetestEvidence,
    LevelAvailability,
    NativeConditionInputs,
    NextConditionEvidence,
)
from kronos.swing.v1.native_readiness_v3 import create_native_readiness_record_v3
from kronos.swing.v1.native_readiness_v3 import NativeLayer2ReadinessV3Store
from kronos.swing.v1.native_review import (
    NativeLayer2EvidenceState,
    NativeReviewEvidenceStore,
    build_native_review_requirements,
)
from kronos.swing.v1.progression_watch import (
    GovernedCompletedBar,
    ProgressionRequirementState,
    ProgressionWatchState,
    ProgressionWatchStore,
    derive_v3_progression_requirements,
)
from kronos.swing.v1.reference_facts import (
    SwingReferenceAvailability,
    SwingReferenceUnavailableReason,
    machine_fact_integrity_sha256,
)
from kronos.swing.v1.visual_evidence_v2 import VisualObservationStatus, VisualTimeframe
from kronos.swing.v1.visual_evidence_v3 import (
    LocalVisualEvidenceV3Store,
    VisualClusteringState,
    VisualQuestionV3,
)
from kronos.swing.v1.evidence_store import LocalTradingViewEvidenceStore
from tests.unit.application.test_swing_opportunities import _Provider, _ready
from tests.unit.browser.test_browser_server import _request as _browser_request
from tests.unit.browser.test_browser_native_review import _v2_review_pack
from tests.unit.swing.v1.test_native_review import _evidence_run, _layer2
from tests.unit.swing.v1.test_visual_evidence_v3 import (
    NOW,
    _response,
    _request,
    _visual_for,
)


def _completed(
    *,
    q9: VisualClusteringState = VisualClusteringState.CLUSTERED,
    missing_question: VisualQuestionV3 | None = None,
    unavailable_reason: SwingReferenceUnavailableReason | None = None,
    next_price: float | None = None,
):  # type: ignore[no-untyped-def]
    facts, run, probable = _evidence_run()
    requirement = build_native_review_requirements(run, facts)[0]
    if unavailable_reason is not None:
        instrument = facts.instrument(requirement.canonical_instrument)
        unavailable = copy.deepcopy(instrument.reference_facts[0])
        for field in (
            "reference_open", "reference_high", "reference_low", "reference_close",
            "cp", "bc", "tc",
        ):
            object.__setattr__(unavailable, field, None)
        object.__setattr__(
            unavailable, "availability", SwingReferenceAvailability.UNAVAILABLE
        )
        object.__setattr__(unavailable, "unavailable_reason", unavailable_reason)
        object.__setattr__(
            unavailable, "integrity_sha256", machine_fact_integrity_sha256(unavailable)
        )
        changed_instrument = replace(
            instrument,
            reference_facts=(unavailable, *instrument.reference_facts[1:]),
        )
        facts = replace(
            facts,
            instruments=tuple(
                changed_instrument if item is instrument else item
                for item in facts.instruments
            ),
        )
    visual = tuple(
        _response(_request(timeframe), q9=q9)
        for timeframe in VisualTimeframe
    ) if unavailable_reason is None else _visual_for(facts, requirement)
    if missing_question is not None:
        changed_response = visual[0]
        observations = list(changed_response.observations)
        index = next(
            index for index, item in enumerate(observations)
            if item.question_id is missing_question
        )
        observations[index] = replace(
            observations[index],
            observation_status=VisualObservationStatus.UNAVAILABLE,
            ambiguity_reason="VISIBLE CHART DOES NOT ESTABLISH THIS FACT",
        )
        visual = (replace(changed_response, observations=tuple(observations)), *visual[1:])
    inputs = NativeConditionInputs()
    if next_price is not None:
        reference = ConditionEvidence(
            "RETEST_REFERENCE",
            (probable.result_sha256,),
            FactualTimeframe.ONE_HOUR,
            "GOVERNED_STRUCTURE",
            LevelAvailability.AVAILABLE,
            float(next_price),
            None,
            None,
            NOW,
            "RETEST_DEVELOPING",
            ("CONTROLLED_V3_SPONSOR_FIXTURE",),
        )
        inputs = NativeConditionInputs(
            retest=DeterministicRetestEvidence(
                reference, True, True, False, False, False
            ),
            next_condition=NextConditionEvidence(
                FactualTimeframe.ONE_HOUR,
                "ONE_HOUR_PROGRESSION",
                "COMPLETED_ONE_HOUR_CLOSE_ABOVE",
                "GOVERNED_STRUCTURE",
                LevelAvailability.AVAILABLE,
                float(next_price),
                None,
                None,
                (probable.result_sha256,),
                NOW,
            ),
        )
    record = create_native_readiness_record_v3(
        requirement,
        _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS),
        facts,
        visual,
        created_at=NOW,
        inputs=inputs,
    )
    completed = CompletedVisualV3Review(requirement, facts, visual, record)
    details = NativeAnalysisDetailsProjection(
        probable, requirement, (), None, None, (), None
    )
    return completed, details, run


def _requirements(completed: CompletedVisualV3Review):  # type: ignore[no-untyped-def]
    return derive_v3_progression_requirements(
        requirement=completed.requirement,
        machine_facts=completed.mtf_snapshot.instrument(
            completed.requirement.canonical_instrument
        ).reference_facts,
        visual=completed.responses,
        readiness=completed.readiness,
        provenance=("CONTROLLED_V3_SPONSOR_FIXTURE",),
    )


def _sponsor_promotion(
    classification: str,
    *,
    direction: str = "LONG",
    missing: tuple[str, ...] = (),
    hard_gate: str | None = None,
    unavailable: str | None = None,
    condition: str | None = None,
    watchability: str = "Not Applicable",
) -> Kr370SponsorPromotionPresentation:
    return Kr370SponsorPromotionPresentation(
        classification=classification,
        direction=direction,
        score=f"{5 - len(missing)}/5",
        criteria=tuple(
            (name, "UNSATISFIED" if name in missing else "SATISFIED", "CONTROLLED")
            for name in (
                "K1 1H DIRECTIONAL PROGRESSION",
                "K2 1H CPR ACCEPTANCE",
                "K3 IMMEDIATE PATH CLEARANCE",
                "K4 SETUP QUALITY",
                "K5 NON EXTENSION",
            )
        ),
        missing_criteria=missing,
        hard_gate_reason=hard_gate,
        not_evaluable_reason=unavailable,
        next_promotion_condition=condition,
        watchability=watchability,
        all_criteria_satisfied=classification in {"BUY NOW", "SELL NOW"},
        integrity_sha256="a" * 64,
    )


def _opportunity_with_promotion(
    promotion: Kr370SponsorPromotionPresentation,
) -> str:
    completed, _, run = _completed()
    presentation = replace(
        present_visual_v3_review(completed),
        sponsor_status=promotion.classification,
        kr370=promotion,
    )
    return render_opportunities(_ready(), run, visual_v3=(presentation,))


@pytest.mark.parametrize("timeframe", ("1W", "1D", "4H", "1H"))
def test_machine_cpr_and_reference_levels_are_presented_for_each_timeframe(
    timeframe: str,
) -> None:
    presentation = present_visual_v3_review(_completed()[0]).machine_for(timeframe)
    assert all((presentation.bc, presentation.cp, presentation.tc))
    assert all((presentation.reference_high, presentation.reference_low))
    assert all(value.startswith("₹") for value in (
        presentation.bc, presentation.cp, presentation.tc,
        presentation.reference_high, presentation.reference_low,
    ))


@pytest.mark.parametrize(
    ("timeframe", "period"),
    (("1W", "Previous Month"), ("1D", "Previous Month"),
     ("4H", "Previous Month"), ("1H", "Previous Week")),
)
def test_governed_reference_period_is_plain_english(
    timeframe: str, period: str
) -> None:
    assert present_visual_v3_review(_completed()[0]).machine_for(
        timeframe
    ).reference_period == period


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        (VisualClusteringState.CLUSTERED, "visibly cluster"),
        (VisualClusteringState.NOT_CLUSTERED, "No meaningful visual clustering"),
        (VisualClusteringState.PARTIAL_COMPONENT_IDENTITY, "does not reliably identify every"),
        (VisualClusteringState.NOT_OBSERVABLE, "does not reliably establish whether"),
    ),
)
def test_q9_is_component_based_and_never_creates_a_zone(
    state: VisualClusteringState, expected: str
) -> None:
    value = present_visual_v3_review(_completed(q9=state)[0]).visual_for("1W")
    assert expected in value.clustering_observation
    assert not hasattr(value, "zone_low")
    assert not hasattr(value, "zone_high")


@pytest.mark.parametrize("reason", tuple(SwingReferenceUnavailableReason))
def test_unavailable_machine_fact_has_bounded_plain_explanation(
    reason: SwingReferenceUnavailableReason,
) -> None:
    presentation = present_visual_v3_review(
        _completed(unavailable_reason=reason)[0]
    )
    fact = presentation.machine_for("1W")
    assert fact.availability == "UNAVAILABLE"
    assert fact.unavailable_explanation
    assert (fact.bc, fact.cp, fact.tc, fact.reference_high, fact.reference_low) == (
        None, None, None, None, None
    )
    assert presentation.sponsor_status == "REFERENCE DATA NOT AVAILABLE"


@pytest.mark.parametrize(
    ("question", "fragment"),
    (
        (VisualQuestionV3.CPR_VISUAL_RELATIONSHIP, "does not reliably show whether price"),
        (VisualQuestionV3.GOVERNED_REFERENCE_VISUAL_CONTEXT, "does not reliably establish price interaction"),
        (VisualQuestionV3.VISUAL_COMPONENT_CLUSTERING, "does not reliably establish whether nearby structures"),
    ),
)
def test_missing_visual_evidence_is_explained_without_fake_watch(
    question: VisualQuestionV3, fragment: str
) -> None:
    completed = _completed(missing_question=question)[0]
    presentation = present_visual_v3_review(completed).visual_for("1W")
    assert fragment in " ".join((
        presentation.cpr_observation,
        presentation.reference_observation,
        presentation.clustering_observation,
    ))
    matching = tuple(
        item for item in _requirements(completed)
        if question.value in item.condition_identity
    )
    assert matching
    assert any(item.state is ProgressionRequirementState.EVIDENCE_REQUIRED for item in matching)
    assert all(
        item.comparator is None and item.price is None
        for item in matching
        if item.state is ProgressionRequirementState.EVIDENCE_REQUIRED
    )


def test_exact_governed_next_condition_is_the_only_watchable_v3_requirement() -> None:
    completed = _completed(next_price=1482.5)[0]
    requirements = _requirements(completed)
    watchable = tuple(
        item for item in requirements
        if item.state is ProgressionRequirementState.WATCH_AVAILABLE
    )
    assert len(watchable) == 1
    assert watchable[0].condition_identity == "ONE_HOUR_PROGRESSION"
    assert watchable[0].price == 1482.5
    assert watchable[0].timeframe is FactualTimeframe.ONE_HOUR
    assert all(
        item.state is not ProgressionRequirementState.WATCH_AVAILABLE
        for item in requirements
        if "REFERENCE_FACT" in item.condition_identity
        or "VISUAL" in item.condition_identity
    )


@pytest.mark.parametrize("price", (96.66666666666667, 1482.5))
def test_instrument_specific_authoritative_prices_render_without_float_noise(
    price: float,
) -> None:
    completed, details, _ = _completed(next_price=price)
    workflow = SwingProgressionWatchWorkflow()
    snapshot = workflow.synchronize(
        completed.readiness.run_identity, _requirements(completed)
    )
    rendered = render_native_analysis_details(
        _ready(), details, snapshot, present_visual_v3_review(completed)
    )
    expected = "₹96.6667" if price < 100 else "₹1,482.5"
    assert expected in rendered


def test_same_governed_condition_produces_no_artificial_instrument_difference() -> None:
    first = _requirements(_completed(next_price=101.25)[0])[-1]
    second = _requirements(_completed(next_price=101.25)[0])[-1]
    assert first.summary == second.summary
    assert first.price == second.price
    assert first.requirement_id == second.requirement_id


def test_watch_activation_notification_and_trigger_reuse_ux08(tmp_path: Path) -> None:
    completed = _completed(next_price=1482.5)[0]
    workflow = SwingProgressionWatchWorkflow(
        ProgressionWatchStore(tmp_path), clock=lambda: NOW
    )
    snapshot = workflow.synchronize(
        completed.readiness.run_identity, _requirements(completed)
    )
    watchable = next(
        item for item in snapshot.requirements
        if item.state is ProgressionRequirementState.WATCH_AVAILABLE
    )

    # Bounded fixture bypasses Provider resolution/monitoring; UX-08 identity and
    # persistence are exercised by the domain activation below.
    from kronos.swing.v1.progression_watch import activate_watch, observe_completed_bar

    watch = activate_watch(watchable, activated_at=NOW)
    assert watch.state is ProgressionWatchState.ACTIVE
    projected = replace(snapshot, watches=(watch,))
    notifications = project_swing_notification_workspace(projected)
    assert notifications.records[0].source_identity == watch.watch_id
    triggered = observe_completed_bar(watch, GovernedCompletedBar(
        watchable.canonical_instrument,
        FactualTimeframe.ONE_HOUR,
        1500.0,
        NOW.replace(hour=13),
        "KITE_NORMALIZED_HISTORICAL",
        "KRONOS-MARKET-CALENDAR-V1-NSE",
        "2026.1.2",
        "NSE-CM-REGULAR",
        ("CONTROLLED_V3_TRIGGER",),
    ))
    assert triggered.state is ProgressionWatchState.TRIGGERED
    assert triggered.consequence == "REASSESSMENT_REQUIRED"
    assert completed.readiness.readiness.value != "REASSESSMENT_REQUIRED"
    assert not hasattr(triggered, "trade_plan")
    assert not hasattr(triggered, "sponsor_decision")
    assert not hasattr(triggered, "order")


@pytest.mark.parametrize(
    "expected",
    (
        "KRONOS NUMERICAL FACTS",
        "CHART OBSERVATION",
        "Previous Week",
        "Reference High",
        "Reference Low",
        "Nearby technical structures",
        "CURRENT DECISION",
        "WHAT KRONOS IS WAITING FOR",
    ),
)
def test_analysis_details_explains_v3_evidence(expected: str) -> None:
    completed, details, _ = _completed(next_price=1482.5)
    workflow = SwingProgressionWatchWorkflow()
    progression = workflow.synchronize(
        completed.readiness.run_identity, _requirements(completed)
    )
    rendered = render_native_analysis_details(
        _ready(), details, progression, present_visual_v3_review(completed)
    )
    assert expected in rendered


@pytest.mark.parametrize(
    "forbidden",
    ("1H PDH/PDL", "Confluence Zone", "zone upper", "zone lower", "cluster score"),
)
def test_v3_analysis_details_does_not_reintroduce_legacy_or_invented_terms(
    forbidden: str,
) -> None:
    completed, details, _ = _completed()
    rendered = render_native_analysis_details(
        _ready(), details, None, present_visual_v3_review(completed)
    )
    assert forbidden not in rendered


@pytest.mark.parametrize(
    ("title", "open_by_default"),
    (("A. WHAT KITE", False), ("B. WHAT THE TRADINGVIEW", False),
     ("C. WHAT KRONOS", True), ("D. CURRENT DECISION", True),
     ("E. REQUIREMENTS TO PROGRESS", True), ("F. WHAT HAPPENS NEXT", True),
     ("G. TECHNICAL EVIDENCE", False)),
)
def test_ux01r_disclosure_defaults_are_preserved(
    title: str, open_by_default: bool
) -> None:
    completed, details, _ = _completed()
    rendered = render_native_analysis_details(
        _ready(), details, None, present_visual_v3_review(completed)
    )
    if open_by_default:
        assert f"<h2>{title}" in rendered
    else:
        assert f"<summary>{title}" in rendered


def test_opportunity_card_stays_compact_and_uses_v3_status() -> None:
    completed, _, run = _completed(next_price=1482.5)
    workflow = SwingProgressionWatchWorkflow()
    progression = workflow.synchronize(
        completed.readiness.run_identity, _requirements(completed)
    )
    rendered = render_opportunities(
        _ready(), run, None, progression,
        (present_visual_v3_review(completed),),
    )
    assert "Chart / reference status" in rendered
    assert "Requirements to progress" in rendered
    assert "watchable" in rendered
    probable_card = rendered.split('<article class="opportunity native-opportunity">', 1)[1]
    probable_card = probable_card.split("</article>", 1)[0]
    assert "Reference High" not in probable_card
    assert "BC ₹" not in probable_card


@pytest.mark.parametrize(
    ("classification", "direction", "css_class"),
    (
        ("BUY NOW", "LONG", "kr370-state-now"),
        ("SELL NOW", "SHORT", "kr370-state-now"),
        ("BUY READY — 1 CRITERION REMAINING", "LONG", "kr370-state-ready"),
        ("SELL READY — 1 CRITERION REMAINING", "SHORT", "kr370-state-ready"),
        ("POTENTIAL BUY SETUP — 2 CRITERIA REMAINING", "LONG", "kr370-state-potential"),
        ("POTENTIAL SELL SETUP — 3 CRITERIA REMAINING", "SHORT", "kr370-state-potential"),
        ("NO SETUP", "LONG", "kr370-state-no-setup"),
    ),
)
def test_kr370_classification_has_exact_sponsor_colour_family(
    classification: str, direction: str, css_class: str
) -> None:
    missing = (
        () if classification in {"BUY NOW", "SELL NOW", "NO SETUP"}
        else ("K1 1H DIRECTIONAL PROGRESSION",)
        if "READY" in classification
        else (
            "K1 1H DIRECTIONAL PROGRESSION",
            "K3 IMMEDIATE PATH CLEARANCE",
        )
    )
    rendered = _opportunity_with_promotion(_sponsor_promotion(
        classification,
        direction=direction,
        missing=missing,
        hard_gate="V3 1 1H Messy Choppy" if classification == "NO SETUP" else None,
    ))

    label = classification.partition(" — ")[0]
    assert f'class="kr370-state {css_class}">{label}</span>' in rendered
    assert "kr370-state-now{color:#d8ffea" in rendered
    assert "kr370-state-ready{color:#77e6a9" in rendered
    assert "kr370-state-potential{color:#ffd57a" in rendered
    assert "kr370-state-no-setup{color:#ff9a9f" in rendered
    assert 'class="direction direction-long"' in rendered


def test_not_evaluable_is_neutral_and_distinct_from_evaluated_no_setup() -> None:
    rendered = _opportunity_with_promotion(_sponsor_promotion(
        "NO SETUP",
        unavailable="Mandatory K5 Non Extension Evidence Unavailable",
    ))

    assert 'class="kr370-state kr370-state-unavailable">NOT EVALUABLE</span>' in rendered
    assert "Required evidence is unavailable" in rendered
    assert "kr370-state-no-setup\">NO SETUP" not in rendered


def test_potential_card_uses_plain_criterion_names_without_k_score() -> None:
    rendered = _opportunity_with_promotion(_sponsor_promotion(
        "POTENTIAL BUY SETUP — 3 CRITERIA REMAINING",
        missing=(
            "K1 1H DIRECTIONAL PROGRESSION",
            "K3 IMMEDIATE PATH CLEARANCE",
            "K5 NON EXTENSION",
        ),
    ))

    assert "3 CRITERIA REMAINING" in rendered
    assert "Missing: 1H Progression · Path Clearance · Extension" in rendered
    assert "K score" not in rendered
    assert "3/5" not in rendered
    assert "K1 1H" not in rendered
    assert "K3 IMMEDIATE" not in rendered
    assert "K5 NON" not in rendered


def test_ready_card_preserves_exact_condition_or_no_alert_without_fake_watch() -> None:
    condition = "Completed 1H close above ₹1,482.5"
    watchable = _opportunity_with_promotion(_sponsor_promotion(
        "BUY READY — 1 CRITERION REMAINING",
        missing=("K2 1H CPR ACCEPTANCE",),
        condition=condition,
        watchability="Watch Available",
    ))
    unavailable = _opportunity_with_promotion(_sponsor_promotion(
        "SELL READY — 1 CRITERION REMAINING",
        direction="SHORT",
        missing=("K5 NON EXTENSION",),
        watchability="No Automated Alert Available",
    ))

    assert "1 CRITERION REMAINING" in watchable
    assert "Waiting for: 1H CPR Clearance" in watchable
    assert condition in watchable
    assert "NO AUTOMATED ALERT AVAILABLE" not in watchable
    assert "Waiting for: Extension" in unavailable
    assert "NO AUTOMATED ALERT AVAILABLE" in unavailable


@pytest.mark.parametrize("classification", ("BUY NOW", "SELL NOW"))
def test_now_card_suppresses_zero_diagnostics_and_score(classification: str) -> None:
    rendered = _opportunity_with_promotion(_sponsor_promotion(classification))

    assert "ALL PROMOTION CRITERIA SATISFIED" in rendered
    assert "5/5" not in rendered
    assert "0 OUTSTANDING" not in rendered
    assert "0 WATCHABLE" not in rendered


def test_no_setup_uses_bounded_plain_reason_while_details_retain_enum() -> None:
    completed, details, _ = _completed()
    promotion = _sponsor_promotion(
        "NO SETUP", hard_gate="V3 1 1H Messy Choppy"
    )
    compact = _opportunity_with_promotion(promotion)
    presentation = replace(
        present_visual_v3_review(completed),
        sponsor_status=promotion.classification,
        kr370=promotion,
    )
    detailed = render_native_analysis_details(
        _ready(), details, None, presentation
    )

    assert "Messy/choppy 1H price action" in compact
    assert "V3 1 1H Messy Choppy" not in compact
    assert "V3 1 1H Messy Choppy" in detailed
    assert 'class="analysis-decision kr370-state kr370-state-no-setup">NO SETUP' in detailed


def test_version_mismatch_fails_closed_instead_of_falling_back() -> None:
    completed = _completed()[0]
    damaged = copy.deepcopy(completed)
    object.__setattr__(damaged.readiness, "question_set_version", "2.0")
    with pytest.raises(ValueError, match="VERSION_MISMATCH"):
        present_visual_v3_review(damaged)


def test_browser_routes_select_exact_v3_cycle_and_keep_notifications_healthy(
    tmp_path: Path,
) -> None:
    completed, _, run = _completed(next_price=1482.5)
    application = SwingOpportunitiesApplication(
        _Provider,
        initial_snapshot=replace(
            _ready(), swing_analysis_run_identity=run.run_identity
        ),
    )
    application.restore_mtf_fact_snapshot(completed.mtf_snapshot)
    application.restore_native_discovery_run(run)
    native = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path / "native"))
    native.prepare(run, completed.mtf_snapshot)
    probable = next(
        item for item in run.assessments
        if item.canonical_instrument == completed.requirement.canonical_instrument
    )
    native._review_pack = _v2_review_pack(  # type: ignore[attr-defined]
        probable,
        run_identity="SWING-RUN-" + "F" * 32,
    )
    native._review_pack_scope = "ALL_ELIGIBLE"  # type: ignore[attr-defined]
    assert native.snapshot().review_pack_superseded is True
    cycle = SwingVisualV3ReviewCycle(
        LocalVisualEvidenceV3Store((tmp_path / "visual-v3").resolve()),
        NativeLayer2ReadinessV3Store((tmp_path / "readiness-v3").resolve()),
    )
    cycle.restore_completed(completed)
    server = create_browser_server(
        application,
        port=0,
        v1_review=SwingV1ReviewWorkflow(
            LocalTradingViewEvidenceStore(tmp_path / "legacy")
        ),
        native_review=native,
        progression_watches=SwingProgressionWatchWorkflow(
            ProgressionWatchStore(tmp_path / "watches")
        ),
        visual_v3=cycle,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, opportunities = _browser_request(
            server, "GET", "/swing/opportunities"
        )
        assert status == 200
        assert "Chart / reference status" in opportunities
        path = (
            f"/swing/analysis-details/{run.run_identity}/"
            f"{completed.requirement.canonical_instrument}"
        )
        status, _, details = _browser_request(server, "GET", path)
        assert status == 200
        assert "SWING-V1-VISUAL-QUESTION-SET-V3" in details
        assert '<details class="analysis-section"><summary>A.' in details
        assert '<details class="analysis-section"><summary>B.' in details
        assert '<section class="analysis-section"><h2>C.' in details
        assert '<section class="analysis-section"><h2>D.' in details
        assert '<section class="analysis-section"><h2>E.' in details
        assert '<section class="analysis-section analysis-next"><h2>F.' in details
        assert '<details class="analysis-section"><summary>G.' in details
        assert '<details open class="analysis-section"><summary>A.' not in details
        assert '<details open class="analysis-section"><summary>B.' not in details
        assert '<details open class="analysis-section"><summary>G.' not in details
        assert _browser_request(server, "GET", "/notifications")[0] == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
