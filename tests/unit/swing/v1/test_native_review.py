from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest

from kronos.application.swing_native_review import (
    NativeReviewRunState,
    NativeReviewWorkflow,
)
from kronos.swing.v1.layer2 import ReadinessState
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.mtf_facts import FactualTimeframe
from kronos.swing.v1.native_discovery import (
    Native1DState,
    Native1HState,
    Native1WState,
    Native4HState,
    NativeAnchor,
    NativeAnchorType,
    NativeContextKind,
    NativeDiscoveryStatus,
    NativeOpportunityIdentity,
    discover_native_mtf,
)
from kronos.swing.v1.native_review import (
    NativeIndependentLayer2Evidence,
    NativeLayer2EvidenceState,
    NativeReviewEvidenceStore,
    build_native_review_requirements,
    reconcile_native_layer2,
)
from tests.unit.application.test_swing_mtf_facts import _build as _mtf_build


@lru_cache(maxsize=1)
def _evidence_run():  # type: ignore[no-untyped-def]
    facts, _ = _mtf_build()
    base = discover_native_mtf(facts)
    source = base.assessments[0]
    boundary = facts.instrument(source.canonical_instrument).fact(
        FactualTimeframe.FOUR_HOUR
    ).observation_boundary
    probable = replace(
        source,
        direction=V1Direction.LONG,
        weekly_state=Native1WState.SUPPORTIVE,
        daily_state=Native1DState.BULLISH_SWING_REGIME,
        four_hour_state=Native4HState.STRUCTURAL_HOLD,
        one_hour_state=Native1HState.NEUTRAL,
        status=NativeDiscoveryStatus.PROBABLE,
        context_kind=NativeContextKind.ESTABLISHED_TREND,
        opportunity_identity=NativeOpportunityIdentity.ESTABLISHED_TREND_STRUCTURAL_HOLD,
        operative_anchor=NativeAnchor(
            NativeAnchorType.FOUR_HOUR_RADIUS_2_STRUCTURE,
            100.0,
            boundary,
        ),
        reason_codes=("NATIVE_TEST_PROBABLE",),
        daily_control_probable_identities=(),
        result_sha256="a" * 64,
    )
    run = replace(
        base,
        assessments=(probable, *base.assessments[1:]),
        result_sha256="b" * 64,
    )
    return facts, run, probable


def _layer2(requirement, state: NativeLayer2EvidenceState):  # type: ignore[no-untyped-def]
    return NativeIndependentLayer2Evidence(
        requirement.native_run_identity,
        requirement.canonical_instrument,
        tuple((timeframe, state) for timeframe in FactualTimeframe),
        state,
        ("SPONSOR_CHART_EVIDENCE",),
    )


def test_only_probable_enters_review_without_daily_control_or_legacy_assessment() -> None:
    facts, run, probable = _evidence_run()
    requirements = build_native_review_requirements(run, facts)

    assert len(requirements) == 1
    thesis = requirements[0].thesis
    assert thesis.native_run_identity == run.run_identity
    assert thesis.native_assessment_sha256 == probable.result_sha256
    assert thesis.direction is probable.direction
    assert thesis.opportunity_identity is probable.opportunity_identity
    assert thesis.weekly_state is probable.weekly_state
    assert thesis.daily_state is probable.daily_state
    assert thesis.four_hour_state is probable.four_hour_state
    assert thesis.one_hour_state is probable.one_hour_state
    assert thesis.operative_anchor_price == probable.operative_anchor.price
    assert probable.daily_control_probable_identities == ()
    assert not hasattr(requirements[0], "probable_setups")
    assert len(thesis.timeframe_facts) == 4
    assert all(type(item.pivots) is tuple for item in thesis.timeframe_facts)


@pytest.mark.parametrize(
    "status",
    (
        NativeDiscoveryStatus.FORMING_WATCH,
        NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY,
        NativeDiscoveryStatus.UNAVAILABLE,
    ),
)
def test_non_probable_states_cannot_enter_review(status: NativeDiscoveryStatus) -> None:
    facts, run, probable = _evidence_run()
    blocked = replace(
        probable,
        status=status,
        opportunity_identity=None,
        context_kind=None,
        operative_anchor=None,
    )
    changed = replace(run, assessments=(blocked, *run.assessments[1:]))
    assert build_native_review_requirements(changed, facts) == ()


def test_weekly_opposing_probable_fails_closed() -> None:
    facts, run, probable = _evidence_run()
    opposing = replace(probable, weekly_state=Native1WState.OPPOSING)
    changed = replace(run, assessments=(opposing, *run.assessments[1:]))
    with pytest.raises(ValueError, match="OPPOSING"):
        build_native_review_requirements(changed, facts)


@pytest.mark.parametrize(
    "state",
    tuple(NativeLayer2EvidenceState),
)
def test_layer2_preserves_native_thesis_and_never_auto_readies(
    state: NativeLayer2EvidenceState,
) -> None:
    facts, run, probable = _evidence_run()
    requirement = build_native_review_requirements(run, facts)[0]
    record = reconcile_native_layer2(requirement, _layer2(requirement, state))

    assert record.reconciliation is state
    assert record.requirement.thesis.native_assessment_sha256 == probable.result_sha256
    assert record.native_thesis_unchanged
    assert record.readiness.state is ReadinessState.CONTEXT_INCOMPLETE
    assert record.readiness.probable_assessment_identities == (probable.result_sha256,)


def test_pine_contradiction_is_retained_without_rewriting_discovery() -> None:
    facts, run, probable = _evidence_run()
    requirement = build_native_review_requirements(run, facts)[0]
    evidence = NativeIndependentLayer2Evidence(
        run.run_identity,
        probable.canonical_instrument,
        tuple(
            (timeframe, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS)
            for timeframe in FactualTimeframe
        ),
        NativeLayer2EvidenceState.CONTRADICTS_NATIVE_THESIS,
        ("PINE_LAYER2_EVIDENCE",),
    )
    record = reconcile_native_layer2(requirement, evidence)

    assert record.reconciliation is NativeLayer2EvidenceState.CONTRADICTS_NATIVE_THESIS
    assert record.contradictions == ("PINE_CONTRADICTS_NATIVE_THESIS",)
    assert record.requirement.thesis.opportunity_identity is probable.opportunity_identity


def test_restart_requires_exact_same_run_and_source_evidence(tmp_path: Path) -> None:
    facts, run, _ = _evidence_run()
    workflow = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path))
    prepared = workflow.prepare(run, facts)
    assert prepared.state is NativeReviewRunState.REVIEW_REQUIRED

    restored = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path)).restore(
        run, facts
    )
    assert restored.requirements == prepared.requirements

    wrong_facts = replace(
        facts,
        run_identity="SWING-RUN-" + "C" * 32,
        instruments=tuple(
            replace(item, reference_facts=()) for item in facts.instruments
        ),
    )
    with pytest.raises(ValueError, match="SAME_RUN"):
        NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path)).restore(
            run, wrong_facts
        )

    missing = NativeReviewEvidenceStore(tmp_path / "orphan")
    with pytest.raises(ValueError, match="UNAVAILABLE"):
        NativeReviewWorkflow(missing).restore(run, facts)


def test_workflow_rejects_changed_active_run_and_changed_layer2(tmp_path: Path) -> None:
    facts, run, _ = _evidence_run()
    workflow = NativeReviewWorkflow(NativeReviewEvidenceStore(tmp_path))
    prepared = workflow.prepare(run, facts)
    requirement = prepared.requirements[0]
    workflow.ingest_layer2(
        _layer2(requirement, NativeLayer2EvidenceState.SUPPORTS_NATIVE_THESIS)
    )
    with pytest.raises(ValueError, match="IMMUTABLE"):
        workflow.ingest_layer2(
            _layer2(requirement, NativeLayer2EvidenceState.MIXED)
        )
