import copy
from dataclasses import replace
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

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
    Kr370V2SponsorPromotionPresentation,
    Kr370SponsorPromotionPresentation,
    present_v2_promotion,
    present_visual_v3_review,
)
from kronos.browser.views import (
    _swing_continuity_warning,
    _v2_card_summary,
    _v2_promotion_detail,
    _v2_state_class,
    _v2_state_label,
    render_native_analysis_details,
    render_opportunities,
)
from kronos.swing.v1.analytical_promotion_v2 import create_record
from kronos.swing.v1.analytical_promotion_v2 import (
    V2ConfirmationHorizonExplanation,
    V2CriterionExplanation,
    V2ReadinessExplanation,
)
from tests.unit.swing.v1.test_analytical_promotion_v2 import (
    source as v2_source, criteria as v2_criteria, nse as v2_nse,
    index as v2_index, mcx as v2_mcx,
)
from tests.unit.swing.v1.test_kr370_step31_handoff import _v2_completed
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


@pytest.mark.parametrize("state", (
    "NO_FOCUS", "NEAR_READY", "BUY_READY", "SELL_READY", "BUY_NOW", "SELL_NOW",
))
def test_v2_state_labels_are_distinct_from_disposition(state: str) -> None:
    record = create_record(source=v2_source(), criteria=v2_criteria(),
                           confirmation=v2_nse(), created_at=NOW)
    view = replace(present_v2_promotion(record), classification=state)
    assert _v2_state_label(view) == state.replace("_", " ")
    assert _v2_state_class(view) in {
        "kr370-state-now", "kr370-state-ready", "kr370-state-potential",
        "kr370-state-no-setup",
    }
    assert f'data-v2-state="{state}"' in _v2_promotion_detail(view)


def test_v2_nse_confirmation_and_dispositions_show_facts_without_hashes() -> None:
    for states, expected in (
        (("OUTPERFORMING", "OUTPERFORMING"), "ESTABLISHED"),
        (("EQUAL", "OUTPERFORMING"), "PENDING"),
        (("UNDERPERFORMING", "OUTPERFORMING"), "PENDING"),
        (("UNAVAILABLE", "OUTPERFORMING"), "UNAVAILABLE"),
    ):
        record = create_record(source=v2_source(), criteria=v2_criteria(),
                               confirmation=v2_nse(states=states), created_at=NOW)
        view = present_v2_promotion(record)
        html = _v2_promotion_detail(view)
        assert view.confirmation == expected
        assert "NIFTY CONFIRMATION" in html
        assert "1D ·" in html and "4H ·" in html
        assert "K1" in html and "K5" in html and "5/5" in html
        assert record.value["integrity_sha256"] not in html
        if expected != "ESTABLISHED":
            assert "CONFIRMATION PENDING" in html

    unavailable = create_record(source=v2_source(), criteria=v2_criteria(unavailable=1),
                                confirmation=v2_nse(), created_at=NOW)
    hard = create_record(source=v2_source(), criteria=v2_criteria(3),
                         confirmation=v2_nse(), created_at=NOW)
    for record, disposition in ((unavailable, "NOT_EVALUABLE"), (hard, "HARD_GATED")):
        view = present_v2_promotion(record)
        html = _v2_promotion_detail(view)
        assert view.classification is None
        assert view.disposition == disposition
        assert disposition.replace("_", " ") in html
        assert "NOT EVALUATED" in html and "Evaluation reasons" in html
        assert "BUY NOW" not in html and "BUY READY" not in html


@pytest.mark.parametrize(
    ("instrument", "pattern", "states", "extension_atr", "expected"),
    (
        ("ADANIENT", "YYYYN", ("UNDERPERFORMING", "UNDERPERFORMING"), 5.9298, "SELL_READY"),
        ("ADANIGREEN", "YYYYN", ("UNDERPERFORMING", "OUTPERFORMING"), 2.6968, "SELL_READY"),
        ("AXISBANK", "NYNNN", ("UNDERPERFORMING", "UNDERPERFORMING"), 5.3867, None),
        ("INFY", "NYNYY", ("OUTPERFORMING", "UNDERPERFORMING"), 0.7826, "NEAR_READY"),
        ("RELIANCE", "YYYYN", ("UNDERPERFORMING", "UNDERPERFORMING"), 5.5478, "SELL_READY"),
        ("RVNL", "YNYYN", ("UNDERPERFORMING", "UNDERPERFORMING"), 5.0523, "NEAR_READY"),
        ("TMPV", "YYYYN", ("UNDERPERFORMING", "UNDERPERFORMING"), 3.1175, "SELL_READY"),
        ("UPL", "YYYYN", ("OUTPERFORMING", "OUTPERFORMING"), 4.6163, "SELL_READY"),
    ),
)
def test_current_eight_patterns_show_evaluator_values_without_changing_outcome(
    instrument, pattern, states, extension_atr, expected,
) -> None:
    from kronos.swing.v1.analytical_promotion_v2 import create_record
    from kronos.swing.v1.analytical_promotion import (
        Kr370CriterionIdentity, Kr370CriterionResult,
    )
    from kronos.validation.kr370 import Kr370CriterionState

    reasons_y = (
        "NATIVE_1H_DIRECTIONALLY_PROGRESSING",
        "COMPLETED_1H_CLOSE_ACCEPTED_BEYOND_CPR",
        "E01_PATH_CLEAR", "CLEAN_DIRECTIONAL", "E03_NOT_MATERIALLY_EXTENDED",
    )
    reasons_n = (
        "NATIVE_1H_STALLING", "COMPLETED_1H_CLOSE_NOT_ACCEPTED_BEYOND_CPR",
        "E01_IMMEDIATE_PATH_BLOCKED", "MESSY_CHOPPY", "E03_MATERIALLY_EXTENDED",
    )
    criterion_values = tuple(
        Kr370CriterionResult(identity,
            Kr370CriterionState.SATISFIED if state == "Y" else Kr370CriterionState.UNSATISFIED,
            reasons_y[index] if state == "Y" else reasons_n[index], ("a" * 64,))
        for index, (identity, state) in enumerate(zip(Kr370CriterionIdentity, pattern, strict=True))
    )
    source = v2_source(direction="SHORT", instrument=instrument)
    confirmation = v2_nse(direction="SHORT", states=states)
    confirmation["nse_binding"]["payload"]["canonical_instrument"] = instrument
    confirmation["state"], confirmation["reason_codes"] = __import__(
        "kronos.swing.v1.analytical_promotion_v2", fromlist=["_validate_nse"]
    )._validate_nse(confirmation["nse_binding"], source)
    record = create_record(source=source, criteria=criterion_values,
                           confirmation=confirmation, created_at=NOW)
    explanations = []
    for index, item in enumerate(criterion_values):
        observed, required, metrics = item.reason, "governed condition", ()
        if index == 1:
            observed = "completed close 206"
            required = "completed 1H close < BC 204.72"
            metrics = (
                ("Completed close", 206.0, "PRICE"),
                ("CPR threshold", 204.72, "PRICE"),
                ("Gap to condition", 1.28, "PRICE"),
            )
        elif index == 4:
            observed = f"{extension_atr:g} ATR14 structural extension"
            required = "completed 1H structural extension <= 2 ATR14"
            metrics = (
                ("Structural extension", extension_atr, "ATR14"),
                ("Excess over limit", max(0.0, extension_atr - 2.0), "ATR14"),
            )
        explanations.append(V2CriterionExplanation(
            item.identity.value, item.state.value, item.reason, observed, required,
            metrics, "1H", NOW, "next governed completed 1H observation",
        ))
    contexts = tuple(
        "SUPPORTIVE_CONTEXT" if state == "UNDERPERFORMING" else "CONTRADICTORY_CONTEXT"
        for state in states
    )
    horizons = tuple(
        V2ConfirmationHorizonExplanation(
            timeframe, context, -1.0 if state == "UNDERPERFORMING" else 1.0,
            0.0, -1.0 if state == "UNDERPERFORMING" else 1.0,
            "stock return − Nifty return < 0%",
            0.0 if state == "UNDERPERFORMING" else 1.0,
            NOW, f"next completed {timeframe} relative-context observation",
        )
        for timeframe, state, context in zip(("1D", "4H"), states, contexts, strict=True)
    )
    explanation = V2ReadinessExplanation(
        source["native_run_identity"], instrument, source["native_assessment_sha256"],
        record.value["promotion_state"], record.value["evaluation_disposition"],
        tuple(explanations), record.value["confirmation"]["state"], horizons,
    )
    before = record.payload
    view = present_v2_promotion(record, explanation=explanation)
    html = _v2_promotion_detail(view)
    card = _v2_card_summary(view)

    with pytest.raises(ValueError, match="KR370_V2_EXPLANATION_BINDING_INVALID"):
        present_v2_promotion(
            record,
            explanation=replace(
                explanation,
                run_identity="SWING-RUN-" + "F" * 32,
            ),
        )

    assert record.payload == before
    assert view.classification == expected
    assert "WHAT MUST CHANGE" not in html and "WHAT MUST CHANGE" not in card
    assert "v2-readiness-lines" in card
    assert "K5_NON_EXTENSION" not in card
    assert NOW.isoformat() not in card
    assert f"{extension_atr:g} ATR14" in html
    assert "Next valid check" in html
    assert "Numeric threshold unavailable by policy" in html
    if instrument == "ADANIENT":
        assert ("1H structural extension must be ≤2.00 ATR. Current 5.93 ATR — "
                "3.93 ATR over.") in card
    if instrument == "RVNL":
        assert ("Need a completed 1H close below ₹204.72. Last close ₹206.00 — "
                "₹1.28 above.") in card
    if record.value["confirmation"]["state"] == "WITHHELD":
        assert "CONTRADICTORY CONTEXT" in html and "Numeric gap 1%" in html
        assert "v2-confirmation-line" in card
        assert "confirmation is contradictory context" in card
    else:
        assert "CONFIRMATION ESTABLISHED" in html


def test_continuity_hold_is_a_separate_plain_language_warning() -> None:
    warning = _swing_continuity_warning(SimpleNamespace(
        reason="UNRESOLVED_CONTINUITY_BREAK",
        qualification=None,
        disposition=SimpleNamespace(value="MANUAL_REVIEW_REQUIRED"),
    ))
    assert warning == (
        '<p class="swing-card-warning">Manual review required — '
        'unresolved continuity break</p>'
    )


def test_v2_index_and_mcx_reference_are_separate_from_nifty() -> None:
    index_record = create_record(source=v2_source(asset_class="NSE_INDEX", instrument="NIFTY"),
                                 criteria=v2_criteria(), confirmation=v2_index(), created_at=NOW)
    index_html = _v2_promotion_detail(present_v2_promotion(index_record))
    assert "NIFTY CONFIRMATION — NOT REQUIRED BY ASSET CLASS" in index_html
    assert "SUPPORTIVE" not in index_html

    mcx_record = create_record(source=v2_source(market="MCX"), criteria=v2_criteria(),
                               confirmation=v2_mcx(limits=("DIFFERENT_SESSIONS",)),
                               created_at=NOW)
    mcx_html = _v2_promotion_detail(present_v2_promotion(mcx_record))
    for label in ("REGISTERED GLOBAL REFERENCE", "COMEX Gold", "M1 mapping / coverage",
                  "M2 structural agreement", "M3 divergence", "DIFFERENT SESSIONS",
                  "CONFIRMATION ESTABLISHED", "DOWNSTREAM — MCX STEP-31 NOT COMMISSIONED"):
        assert label in mcx_html
    assert "NIFTY CONFIRMATION" not in mcx_html
    assert mcx_record.value["integrity_sha256"] not in mcx_html


def test_v2_completed_visual_presentation_does_not_relabel_v1(tmp_path: Path) -> None:
    completed = _v2_completed(tmp_path)
    presented = present_visual_v3_review(completed)
    assert presented.kr370 is None and presented.kr370_v2 is not None
    assert presented.sponsor_status == "BUY NOW"
    assert "KR-370 V2" in _v2_promotion_detail(presented.kr370_v2)
    historical = present_visual_v3_review(replace(completed, promotion_v2=None))
    assert historical.kr370 is not None and historical.kr370_v2 is None


def test_current_v2_opportunity_and_detail_are_sponsor_safe(tmp_path: Path) -> None:
    completed = _v2_completed(tmp_path)
    assert completed.promotion_v2 is not None
    _, run, probable = _evidence_run()
    presented = present_visual_v3_review(completed)
    opportunities = render_opportunities(
        _ready(), run, visual_v3=(presented,), promotions_v2=(completed.promotion_v2,))
    details = NativeAnalysisDetailsProjection(
        probable, completed.requirement, (), None, None, (), None)
    detailed = render_native_analysis_details(
        _ready(), details, visual_v3=presented, promotion_v2=completed.promotion_v2)
    for html in (opportunities, detailed):
        assert "KR-370 V2" in html and "BUY NOW" in html
        assert "NIFTY CONFIRMATION" in html and "1D ·" in html and "4H ·" in html
        assert "K1" in html and "K5" in html
        assert completed.promotion_v2.value["integrity_sha256"] not in html
    assert "G. TECHNICAL EVIDENCE" not in detailed
    assert "SUPPORTING CONTEXT ONLY · NON-VETO" not in detailed
    assert "@media(max-width:760px){.v2-promotion-grid,.v2-criterion-list" in detailed


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
    assert "REFRESH ANALYSIS AFTER NEXT COMPLETED 1H" in unavailable
    assert "NO AUTOMATED ALERT AVAILABLE" not in unavailable


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
