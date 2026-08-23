from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import inspect
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday import qualification_research
from kronos.intraday.qualification import (
    EvidenceReference,
    QualificationError,
    QualificationEvidenceSource,
    QualificationEvidenceSufficiency,
    QualificationObservationResult,
    create_narrow_cpr_hypothesis,
    create_population_diagnostics,
    create_qualification_corpus,
    create_qualification_corpus_session,
    create_qualification_observation,
)
from kronos.intraday.qualification_research import (
    COMPARISON_REPORT_IDENTITY,
    METHODOLOGY_RESEARCH_IDENTITY,
    METHODOLOGY_VARIANT_IDENTITY,
    OUTCOME_MEASUREMENT_IDENTITY,
    PART2_CONTRACT_VERSION,
    REAL_CORPUS_BINDING_IDENTITY,
    RESEARCH_RESULT_IDENTITY,
    DirectionContribution,
    EvidenceRole,
    HypothesisEvidence,
    HypothesisFamily,
    HypothesisResult,
    OutcomeDefinitionFamily,
    PopulationWarning,
    ResearchConclusion,
    ResearchDirection,
    ResearchDisposition,
    ResearchReason,
    ResearchStage,
    bind_real_corpus,
    compare_ablation,
    create_methodology_comparison_report,
    create_methodology_variant,
    create_outcome_measurement,
    create_outcome_measurement_definition,
    create_real_discovery_corpus_binding,
    create_research_hypothesis,
    create_session_variant_result,
    evaluate_methodology_variant,
    research_artifact_bytes,
    summarize_variant_population,
)
from kronos.intraday.qualification_research_persistence import (
    QualificationResearchStore,
)


IST = ZoneInfo("Asia/Kolkata")
BOUNDARY = datetime(2026, 8, 24, 12, 0, tzinfo=IST)
SYNTHETIC = QualificationEvidenceSource.SYNTHETIC_TEST_FIXTURE
REAL = QualificationEvidenceSource.REAL_GOVERNED_MARKET_EVIDENCE
CORPUS = "INTRADAY-QUALIFICATION-CORPUS-EXACT-001"


def _hypothesis(
    family: HypothesisFamily,
    *,
    role: EvidenceRole = EvidenceRole.MANDATORY,
    stage: ResearchStage = ResearchStage.COMPRESSION_CONTEXT,
    direction: DirectionContribution = DirectionContribution.NONE,
):  # type: ignore[no-untyped-def]
    return create_research_hypothesis(
        hypothesis_version="0.1.0",
        family=family,
        stage=stage,
        role=role,
        direction_contribution=direction,
        required_fact_families=(f"GOVERNED_{family.value}_FACTS",),
        provenance=("WO-06-PART-2-FIXTURE",),
    )


def _variant(
    hypotheses=None,  # type: ignore[no-untyped-def]
    *,
    support: tuple[tuple[ResearchStage, int], ...] = (),
):  # type: ignore[no-untyped-def]
    retained = hypotheses or (
        _hypothesis(HypothesisFamily.NARROW_CPR),
        _hypothesis(
            HypothesisFamily.HOURLY_REGIME,
            stage=ResearchStage.HIGHER_TIMEFRAME_REGIME,
            direction=DirectionContribution.LONG,
        ),
        _hypothesis(
            HypothesisFamily.FIFTEEN_MINUTE_STRUCTURE,
            stage=ResearchStage.DEVELOPING_STRUCTURE,
            direction=DirectionContribution.LONG,
        ),
    )
    return create_methodology_variant(
        variant_version="0.1.0",
        corpus_identity=CORPUS,
        hypotheses=tuple(retained),
        minimum_supporting_matches=support,
        outcome_definition_identity="OUTCOME-DEFINITION-PROPOSAL-V0",
        outcome_definition_version="0.1.0",
        population_diagnostic_version="0.1.0",
        provenance=("SYNTHETIC-RESEARCH-VARIANT",),
    )


def _evidence(
    hypothesis,  # type: ignore[no-untyped-def]
    result: HypothesisResult = HypothesisResult.MATCH,
    *,
    source: QualificationEvidenceSource = SYNTHETIC,
    available_at: datetime = BOUNDARY,
    outcome: bool = False,
):  # type: ignore[no-untyped-def]
    return HypothesisEvidence(
        hypothesis_identity=hypothesis.hypothesis_identity,
        result=result,
        evidence_identities=(f"FACT-{hypothesis.family.value}",),
        available_at=available_at,
        source=source,
        outcome_evidence=outcome,
    )


def _result(
    index: int = 0,
    *,
    variant=None,  # type: ignore[no-untyped-def]
    overrides=None,  # type: ignore[no-untyped-def]
    source: QualificationEvidenceSource = SYNTHETIC,
    session: str = "NSE:2026-08-24",
):  # type: ignore[no-untyped-def]
    selected = variant or _variant()
    changes = overrides or {}
    evidence = tuple(
        _evidence(item, changes.get(item.family, HypothesisResult.MATCH), source=source)
        for item in selected.hypotheses
    )
    return evaluate_methodology_variant(
        canonical_subject_identity=f"NSE-EQ-SUBJECT-{index:03d}",
        market_session_identity=session,
        observation_boundary=BOUNDARY,
        variant=selected,
        evidence=evidence,
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    )


def _session(count: int, *, variant=None, source=SYNTHETIC):  # type: ignore[no-untyped-def]
    selected = variant or _variant()
    results = tuple(_result(index, variant=selected, source=source) for index in range(count))
    if not results:
        # A factual population exists but the sole member fails at Stage 1;
        # this produces a zero-survivor session without inventing an empty run.
        results = (
            _result(
                999,
                variant=selected,
                overrides={HypothesisFamily.NARROW_CPR: HypothesisResult.NO_MATCH},
                source=source,
            ),
        )
    return create_session_variant_result(
        market_session_identity="NSE:2026-08-24",
        variant=selected,
        member_results=results,
        unavailable_member_identities=(
            "MCX-FUT-GOLDM",
            "MCX-FUT-SILVERM",
            "MCX-FUT-COPPER",
            "MCX-FUT-NATGAS",
            "MCX-FUT-CRUDE",
        ),
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    )


def test_part2_contract_identities_and_versions_are_explicit() -> None:
    assert METHODOLOGY_RESEARCH_IDENTITY.endswith("RESEARCH-V0")
    assert METHODOLOGY_VARIANT_IDENTITY.endswith("VARIANT-V0")
    assert RESEARCH_RESULT_IDENTITY.endswith("RESULT-V0")
    assert COMPARISON_REPORT_IDENTITY.endswith("REPORT-V0")
    assert OUTCOME_MEASUREMENT_IDENTITY.endswith("MEASUREMENT-V0")
    assert REAL_CORPUS_BINDING_IDENTITY.endswith("BINDING-V0")
    assert PART2_CONTRACT_VERSION == "0.1.0"


def test_methodology_and_variant_identities_are_deterministic() -> None:
    assert _variant() == _variant()
    assert _result() == _result()


def test_arbitrary_executable_expressions_are_prohibited() -> None:
    with pytest.raises(QualificationError):
        create_research_hypothesis(
            hypothesis_version="0.1.0",
            family=HypothesisFamily.DAILY_CONTEXT,
            stage=ResearchStage.HIGHER_TIMEFRAME_REGIME,
            role=EvidenceRole.MANDATORY,
            direction_contribution=DirectionContribution.NONE,
            required_fact_families=(lambda: True,),  # type: ignore[arg-type]
            provenance=("TEST",),
        )
    source = inspect.getsource(qualification_research)
    assert "eval(" not in source and "exec(" not in source


@pytest.mark.parametrize("role", tuple(EvidenceRole))
def test_all_governed_evidence_roles_are_representable(role: EvidenceRole) -> None:
    assert _hypothesis(HypothesisFamily.DAILY_CONTEXT, role=role).role is role


def test_mandatory_no_match_rejects_research_variant() -> None:
    result = _result(overrides={HypothesisFamily.NARROW_CPR: HypothesisResult.NO_MATCH})
    assert result.disposition is ResearchDisposition.QUALIFICATION_WOULD_FAIL
    assert ResearchReason.MANDATORY_NO_MATCH in result.reason_codes


def test_supporting_minimum_is_bounded_and_deterministic() -> None:
    support = _hypothesis(
        HypothesisFamily.NARROW_CPR,
        role=EvidenceRole.SUPPORTING,
    )
    variant = _variant((support,), support=((ResearchStage.COMPRESSION_CONTEXT, 1),))
    assert _result(variant=variant).research_qualified is True
    failed = _result(
        variant=variant,
        overrides={HypothesisFamily.NARROW_CPR: HypothesisResult.NO_MATCH},
    )
    assert failed.research_qualified is False
    assert ResearchReason.SUPPORT_INSUFFICIENT in failed.reason_codes


def test_veto_match_rejects_and_informational_result_does_not() -> None:
    veto = _hypothesis(HypothesisFamily.EXTENSION, role=EvidenceRole.VETO)
    info = _hypothesis(HypothesisFamily.PDH_PDL, role=EvidenceRole.INFORMATIONAL)
    variant = _variant((veto, info))
    result = _result(
        variant=variant,
        overrides={
            HypothesisFamily.EXTENSION: HypothesisResult.MATCH,
            HypothesisFamily.PDH_PDL: HypothesisResult.NO_MATCH,
        },
    )
    assert result.research_qualified is False
    assert ResearchReason.VETO_MATCH in result.reason_codes
    clear = _result(
        variant=variant,
        overrides={HypothesisFamily.EXTENSION: HypothesisResult.NO_MATCH},
    )
    assert clear.research_qualified is True
    assert ResearchReason.INFORMATION_RECORDED in clear.reason_codes


def test_narrow_cpr_can_be_mandatory_supporting_or_absent() -> None:
    mandatory = _variant((_hypothesis(HypothesisFamily.NARROW_CPR),))
    supporting_h = _hypothesis(HypothesisFamily.NARROW_CPR, role=EvidenceRole.SUPPORTING)
    supporting = _variant(
        (supporting_h,), support=((ResearchStage.COMPRESSION_CONTEXT, 1),)
    )
    absent = _variant((_hypothesis(HypothesisFamily.DAILY_CONTEXT),))
    assert any(item.family is HypothesisFamily.NARROW_CPR for item in mandatory.hypotheses)
    assert supporting.hypotheses[0].role is EvidenceRole.SUPPORTING
    assert all(item.family is not HypothesisFamily.NARROW_CPR for item in absent.hypotheses)


def test_narrow_cpr_is_capable_of_being_informational_non_useful() -> None:
    hypothesis = _hypothesis(HypothesisFamily.NARROW_CPR, role=EvidenceRole.INFORMATIONAL)
    result = _result(
        variant=_variant((hypothesis,)),
        overrides={HypothesisFamily.NARROW_CPR: HypothesisResult.NO_MATCH},
    )
    assert result.research_qualified is True
    assert result.direction is ResearchDirection.NON_DIRECTIONAL


@pytest.mark.parametrize(
    "direction, expected",
    (
        (DirectionContribution.LONG, ResearchDirection.LONG_HYPOTHESIS),
        (DirectionContribution.SHORT, ResearchDirection.SHORT_HYPOTHESIS),
        (DirectionContribution.NONE, ResearchDirection.NON_DIRECTIONAL),
    ),
)
def test_long_short_and_non_directional_hypotheses(
    direction: DirectionContribution, expected: ResearchDirection
) -> None:
    hypothesis = _hypothesis(
        HypothesisFamily.FIFTEEN_MINUTE_STRUCTURE,
        direction=direction,
    )
    assert _result(variant=_variant((hypothesis,))).direction is expected


def test_conflicting_direction_is_not_tie_broken() -> None:
    long = _hypothesis(
        HypothesisFamily.HOURLY_REGIME,
        direction=DirectionContribution.LONG,
    )
    short = _hypothesis(
        HypothesisFamily.FIFTEEN_MINUTE_STRUCTURE,
        stage=ResearchStage.DEVELOPING_STRUCTURE,
        direction=DirectionContribution.SHORT,
    )
    result = _result(variant=_variant((long, short)))
    assert result.direction is ResearchDirection.DIRECTION_CONFLICTING
    assert result.research_qualified is True


def test_narrow_cpr_cannot_create_direction() -> None:
    with pytest.raises(QualificationError):
        _hypothesis(
            HypothesisFamily.NARROW_CPR,
            direction=DirectionContribution.LONG,
        )


def test_direction_can_be_unavailable_without_being_forced() -> None:
    hypothesis = _hypothesis(
        HypothesisFamily.HOURLY_REGIME,
        role=EvidenceRole.INFORMATIONAL,
        direction=DirectionContribution.LONG,
    )
    result = _result(
        variant=_variant((hypothesis,)),
        overrides={HypothesisFamily.HOURLY_REGIME: HypothesisResult.UNAVAILABLE},
    )
    assert result.direction is ResearchDirection.UNAVAILABLE


@pytest.mark.parametrize("family", tuple(HypothesisFamily))
def test_all_required_hypothesis_families_are_supported(
    family: HypothesisFamily,
) -> None:
    hypothesis = _hypothesis(family)
    assert hypothesis.family is family
    assert hypothesis.required_fact_families


def test_exact_hypothesis_set_is_bound() -> None:
    variant = _variant()
    with pytest.raises(QualificationError):
        evaluate_methodology_variant(
            canonical_subject_identity="NSE-EQ-RELIANCE",
            market_session_identity="NSE:2026-08-24",
            observation_boundary=BOUNDARY,
            variant=variant,
            evidence=tuple(_evidence(item) for item in variant.hypotheses[:-1]),
            provenance=("TEST",),
        )


def test_outcome_leakage_and_future_evidence_fail_closed() -> None:
    variant = _variant((_hypothesis(HypothesisFamily.DAILY_CONTEXT),))
    for evidence in (
        (_evidence(variant.hypotheses[0], outcome=True),),
        (_evidence(variant.hypotheses[0], available_at=BOUNDARY + timedelta(seconds=1)),),
    ):
        with pytest.raises(QualificationError):
            evaluate_methodology_variant(
                canonical_subject_identity="NSE-EQ-RELIANCE",
                market_session_identity="NSE:2026-08-24",
                observation_boundary=BOUNDARY,
                variant=variant,
                evidence=evidence,
                provenance=("TEST",),
            )


def test_stage_attrition_is_deterministic_and_reconciles() -> None:
    variant = _variant()
    session = create_session_variant_result(
        market_session_identity="NSE:2026-08-24",
        variant=variant,
        member_results=(
            _result(1, variant=variant),
            _result(
                2,
                variant=variant,
                overrides={HypothesisFamily.NARROW_CPR: HypothesisResult.NO_MATCH},
            ),
            _result(
                3,
                variant=variant,
                overrides={HypothesisFamily.HOURLY_REGIME: HypothesisResult.UNAVAILABLE},
            ),
        ),
        unavailable_member_identities=(),
        provenance=("TEST",),
    )
    compression = session.stage_diagnostics[1]
    hourly = session.stage_diagnostics[2]
    assert (compression.starting_count, compression.survivor_count) == (3, 2)
    assert (hourly.starting_count, hourly.survivor_count) == (2, 1)
    assert hourly.unavailable_count == 1
    assert hourly.cumulative_retention_percentage == Decimal(1) / Decimal(3) * 100


def test_hypothesis_population_effect_preserves_true_false_and_unavailable() -> None:
    variant = _variant()
    session = create_session_variant_result(
        market_session_identity="NSE:2026-08-24",
        variant=variant,
        member_results=(
            _result(1, variant=variant),
            _result(
                2,
                variant=variant,
                overrides={HypothesisFamily.NARROW_CPR: HypothesisResult.NO_MATCH},
            ),
            _result(
                3,
                variant=variant,
                overrides={HypothesisFamily.NARROW_CPR: HypothesisResult.UNAVAILABLE},
            ),
        ),
        unavailable_member_identities=("MCX-FUT-GOLDM",),
        provenance=("TEST",),
    )
    summary = summarize_variant_population(
        variant=variant,
        sessions=(session,),
        evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_UNAVAILABLE,
        provenance=("TEST",),
    )
    narrow = next(
        item
        for item in summary.hypothesis_population_effects
        if item.family is HypothesisFamily.NARROW_CPR
    )
    assert (narrow.match_count, narrow.non_match_count, narrow.unavailable_count) == (
        1,
        1,
        1,
    )
    assert narrow.match_percentage == Decimal(1) / Decimal(3) * 100
    assert narrow.final_qualified_match_count == 1
    assert summary.unavailable_member_count == 1


@pytest.mark.parametrize(
    "count, warning, zero, over10, over15, twenty",
    (
        (0, PopulationWarning.STARVATION_RISK, 1, 0, 0, 0),
        (7, PopulationWarning.NONE, 0, 0, 0, 0),
        (11, PopulationWarning.FLOODING_RISK, 0, 1, 0, 0),
        (16, PopulationWarning.FLOODING_RISK, 0, 1, 1, 0),
        (20, PopulationWarning.FLOODING_RISK, 0, 1, 1, 1),
    ),
)
def test_population_calibration_warning_buckets_do_not_truncate(
    count: int,
    warning: PopulationWarning,
    zero: int,
    over10: int,
    over15: int,
    twenty: int,
) -> None:
    variant = _variant()
    summary = summarize_variant_population(
        variant=variant,
        sessions=(_session(count, variant=variant),),
        evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_UNAVAILABLE,
        provenance=("TEST",),
    )
    assert summary.warning is warning
    assert (summary.zero_frequency, summary.over_ten_frequency) == (zero, over10)
    assert (summary.over_fifteen_frequency, summary.twenty_or_more_frequency) == (
        over15,
        twenty,
    )
    assert summary.maximum_survivors == count
    assert summary.conclusion is ResearchConclusion.INSUFFICIENT_EVIDENCE


def test_population_warning_never_alters_member_disposition() -> None:
    variant = _variant()
    session = _session(20, variant=variant)
    summary = summarize_variant_population(
        variant=variant,
        sessions=(session,),
        evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_UNAVAILABLE,
        provenance=("TEST",),
    )
    assert summary.warning is PopulationWarning.FLOODING_RISK
    assert all(item.research_qualified for item in session.member_results)


def test_no_fixed_quota_top_n_score_or_ranking_surface() -> None:
    source = inspect.getsource(qualification_research).lower()
    for banned in ("top_n", "rank_score", "confidence_score", "universal_score"):
        assert banned not in source
    assert "candidate_admitted" not in source
    assert "probable_long" not in source and "probable_short" not in source


def test_ablation_and_variant_comparison_are_deterministic() -> None:
    narrow = _hypothesis(HypothesisFamily.NARROW_CPR)
    context = _hypothesis(HypothesisFamily.HOURLY_REGIME)
    base = _variant((narrow, context))
    ablated = _variant((context,))
    base_summary = summarize_variant_population(
        variant=base,
        sessions=(_session(2, variant=base),),
        evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_UNAVAILABLE,
        provenance=("TEST",),
    )
    ablated_summary = summarize_variant_population(
        variant=ablated,
        sessions=(_session(3, variant=ablated),),
        evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_UNAVAILABLE,
        provenance=("TEST",),
    )
    comparison = compare_ablation(
        base_variant=base,
        ablated_variant=ablated,
        base_summary=base_summary,
        ablated_summary=ablated_summary,
        provenance=("TEST",),
    )
    report = create_methodology_comparison_report(
        report_version="0.1.0",
        corpus_identity=CORPUS,
        variant_summaries=(base_summary, ablated_summary),
        ablation_comparisons=(comparison,),
        evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_UNAVAILABLE,
        market_condition_coverage=("SYNTHETIC_FIXTURE_ONLY",),
        missing_evidence=("POST_ACTIVATION_REAL_DISCOVERY_CORPUS",),
        conclusion=ResearchConclusion.INSUFFICIENT_EVIDENCE,
        provenance=("TEST",),
    )
    assert comparison == compare_ablation(
        base_variant=base,
        ablated_variant=ablated,
        base_summary=base_summary,
        ablated_summary=ablated_summary,
        provenance=("TEST",),
    )
    assert report.variant_summaries == (base_summary, ablated_summary)
    assert not hasattr(report, "score") and not hasattr(report, "ranking")


def test_synthetic_evidence_cannot_approve_methodology() -> None:
    variant = _variant()
    summary = summarize_variant_population(
        variant=variant,
        sessions=(_session(2, variant=variant),),
        evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_READY_FOR_REVIEW,
        provenance=("TEST",),
        outcome_metrics=(("maximum_upward_excursion", Decimal("1.5")),),
    )
    assert summary.conclusion is ResearchConclusion.INSUFFICIENT_EVIDENCE
    with pytest.raises(QualificationError):
        create_methodology_comparison_report(
            report_version="0.1.0",
            corpus_identity=CORPUS,
            variant_summaries=(summary,),
            ablation_comparisons=(),
            evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_READY_FOR_REVIEW,
            market_condition_coverage=("SYNTHETIC_FIXTURE_ONLY",),
            missing_evidence=("REAL_EVIDENCE",),
            conclusion=ResearchConclusion.READY_FOR_METHODOLOGY_FREEZE_REVIEW,
            provenance=("TEST",),
        )


def test_real_and_synthetic_observations_are_counted_separately() -> None:
    variant = _variant()
    synthetic = _session(2, variant=variant, source=SYNTHETIC)
    real = create_session_variant_result(
        market_session_identity="NSE:2026-08-25",
        variant=variant,
        member_results=tuple(
            _result(
                index,
                variant=variant,
                source=REAL,
                session="NSE:2026-08-25",
            )
            for index in range(3)
        ),
        unavailable_member_identities=(),
        provenance=("REAL-FIXTURE",),
    )
    assert synthetic.member_results[0].evidence_source is SYNTHETIC
    assert real.member_results[0].evidence_source is REAL
    summary = summarize_variant_population(
        variant=variant,
        sessions=(synthetic, real),
        evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_ACCUMULATING,
        provenance=("TEST",),
    )
    assert (summary.real_observation_count, summary.synthetic_observation_count) == (3, 2)


def test_outcome_definition_and_later_measurements_are_factual_only() -> None:
    expansion = create_outcome_measurement_definition(
        definition_version="0.1.0",
        family=OutcomeDefinitionFamily.EXPANSION,
        measure_names=("subsequent_range_expansion", "time_to_expansion_seconds"),
        normalization_options=("PREVIOUS_SESSION_RANGE", "PRE_OBSERVATION_MOVE_RANGE"),
        provenance=("WO-06-PART-2",),
    )
    directional = create_outcome_measurement_definition(
        definition_version="0.1.0",
        family=OutcomeDefinitionFamily.DIRECTIONAL,
        measure_names=(
            "maximum_upward_excursion",
            "maximum_downward_excursion",
            "net_directional_displacement",
        ),
        normalization_options=("ABSOLUTE_PRICE_DISTANCE", "PREVIOUS_SESSION_RANGE"),
        provenance=("WO-06-PART-2",),
    )
    measurement = create_outcome_measurement(
        definition=directional,
        source_result=_result(),
        measured_at=BOUNDARY + timedelta(hours=3),
        measures=(
            ("maximum_upward_excursion", Decimal("2.5")),
            ("maximum_downward_excursion", Decimal("0.8")),
            ("net_directional_displacement", Decimal("1.7")),
        ),
        provenance=("SYNTHETIC-OUTCOME",),
    )
    assert expansion.threshold is None and directional.threshold is None
    assert measurement.measured_at > measurement.observation_boundary
    assert all("pnl" not in name.lower() for name, _ in measurement.measures)


def test_wrong_or_early_outcome_measurement_fails_closed() -> None:
    definition = create_outcome_measurement_definition(
        definition_version="0.1.0",
        family=OutcomeDefinitionFamily.DIRECTIONAL,
        measure_names=("maximum_upward_excursion",),
        normalization_options=("ABSOLUTE_PRICE_DISTANCE",),
        provenance=("TEST",),
    )
    with pytest.raises(QualificationError):
        create_outcome_measurement(
            definition=definition,
            source_result=_result(),
            measured_at=BOUNDARY,
            measures=(("maximum_upward_excursion", Decimal("1")),),
            provenance=("TEST",),
        )


def test_later_outcome_definition_does_not_mutate_historical_measurement() -> None:
    first = create_outcome_measurement_definition(
        definition_version="0.1.0",
        family=OutcomeDefinitionFamily.EXPANSION,
        measure_names=("subsequent_range_expansion",),
        normalization_options=("PREVIOUS_SESSION_RANGE",),
        provenance=("TEST",),
    )
    measurement = create_outcome_measurement(
        definition=first,
        source_result=_result(),
        measured_at=BOUNDARY + timedelta(hours=1),
        measures=(("subsequent_range_expansion", Decimal("1.2")),),
        provenance=("TEST",),
    )
    second = create_outcome_measurement_definition(
        definition_version="0.2.0",
        family=OutcomeDefinitionFamily.EXPANSION,
        measure_names=("subsequent_range_expansion",),
        normalization_options=("PRE_OBSERVATION_MOVE_RANGE",),
        provenance=("TEST",),
    )
    assert measurement.definition_identity == first.definition_identity
    assert measurement.definition_identity != second.definition_identity


def _real_part1_corpus():  # type: ignore[no-untyped-def]
    hypothesis = create_narrow_cpr_hypothesis(
        effective_from=BOUNDARY,
        effective_through=datetime(9999, 12, 31, tzinfo=IST),
    )
    evidence = EvidenceReference(
        evidence_identity="MACHINE-FACT-BUNDLE-001",
        available_at=BOUNDARY,
        source=REAL,
        provenance=("REAL-GOVERNED-FIXTURE",),
    )
    observation = create_qualification_observation(
        canonical_subject_identity="NSE-EQ-RELIANCE",
        market_session_identity="NSE:2026-08-24",
        observation_boundary=BOUNDARY,
        hypothesis=hypothesis,
        evidence=(evidence,),
        result=QualificationObservationResult.HYPOTHESIS_TRUE,
        result_fact_identity="NARROW-CPR-FACT-001",
        evidence_source=REAL,
        provenance=("REAL-GOVERNED-FIXTURE",),
    )
    diagnostics = create_population_diagnostics(
        market_session_identity="NSE:2026-08-24",
        hypothesis_identity=hypothesis.hypothesis_identity,
        observations=(observation,),
    )
    session = create_qualification_corpus_session(
        market_session_identity="NSE:2026-08-24",
        observation_boundary=BOUNDARY,
        universe_publication_identity="UNIVERSE-1.0.0-EXACT",
        reconciliation_publication_identity="RECONCILIATION-1.0.0-EXACT",
        discovery_run_identity="DISCOVERY-RUN-EXACT-001",
        factual_evidence_identities=("MACHINE-FACT-BUNDLE-001",),
        hypothesis_identities=(hypothesis.hypothesis_identity,),
        outcome_evidence_window_identity=None,
        population_diagnostics_identity=diagnostics.diagnostics_identity,
        provenance=("REAL-GOVERNED-FIXTURE",),
    )
    return create_qualification_corpus(
        corpus_version="0.1.0",
        sessions=(session,),
        observations=(observation,),
        provenance=("REAL-GOVERNED-FIXTURE",),
    )


def test_real_corpus_binding_requires_exact_governed_identities() -> None:
    binding = create_real_discovery_corpus_binding(
        discovery_run_identity="DISCOVERY-RUN-EXACT-001",
        universe_publication_identity="UNIVERSE-1.0.0-EXACT",
        reconciliation_publication_identity="RECONCILIATION-1.0.0-EXACT",
        observation_boundary=BOUNDARY,
        machine_fact_bundle_identities=("MACHINE-FACT-BUNDLE-001",),
        provenance=("TEST",),
    )
    assert bind_real_corpus(_real_part1_corpus(), binding)
    changed = create_real_discovery_corpus_binding(
        discovery_run_identity="DISCOVERY-RUN-EXACT-002",
        universe_publication_identity="UNIVERSE-1.0.0-EXACT",
        reconciliation_publication_identity="RECONCILIATION-1.0.0-EXACT",
        observation_boundary=BOUNDARY,
        machine_fact_bundle_identities=("MACHINE-FACT-BUNDLE-001",),
        provenance=("TEST",),
    )
    with pytest.raises(QualificationError):
        bind_real_corpus(_real_part1_corpus(), changed)


@pytest.mark.parametrize("alias", ("LATEST", "NEWEST", "CURRENT"))
def test_no_latest_run_or_publication_binding(alias: str) -> None:
    with pytest.raises(QualificationError):
        create_real_discovery_corpus_binding(
            discovery_run_identity=alias,
            universe_publication_identity="UNIVERSE-EXACT",
            reconciliation_publication_identity="RECONCILIATION-EXACT",
            observation_boundary=BOUNDARY,
            machine_fact_bundle_identities=("FACT-BUNDLE-EXACT",),
            provenance=("TEST",),
        )


def test_current_five_mcx_members_remain_unavailable_and_not_removed() -> None:
    session = _session(3)
    assert session.unavailable_member_identities == (
        "MCX-FUT-GOLDM",
        "MCX-FUT-SILVERM",
        "MCX-FUT-COPPER",
        "MCX-FUT-NATGAS",
        "MCX-FUT-CRUDE",
    )
    assert session.factual_population_count == 3


def test_research_persistence_is_explicit_idempotent_and_tamper_safe(
    tmp_path: Path,
) -> None:
    store = QualificationResearchStore(tmp_path)
    variant = _variant()
    path = store.retain(variant)
    assert store.retain(variant) == path
    document = store.load_document(
        artifact_type="MethodologyVariant",
        artifact_identity=variant.variant_identity,
    )
    assert document["artifact_identity"] == variant.variant_identity
    tampered = json.loads(path.read_bytes())
    tampered["artifact"]["variant_version"] = "9.9.9"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(QualificationError):
        store.load_document(
            artifact_type="MethodologyVariant",
            artifact_identity=variant.variant_identity,
        )


@pytest.mark.parametrize(
    "value",
    (
        lambda: _variant(),
        lambda: _result(),
        lambda: _session(2),
        lambda: create_outcome_measurement_definition(
            definition_version="0.1.0",
            family=OutcomeDefinitionFamily.EXPANSION,
            measure_names=("subsequent_range_expansion",),
            normalization_options=("PREVIOUS_SESSION_RANGE",),
            provenance=("TEST",),
        ),
    ),
)
def test_research_artifacts_have_deterministic_canonical_json(value) -> None:  # type: ignore[no-untyped-def]
    artifact = value()
    assert research_artifact_bytes(artifact) == research_artifact_bytes(artifact)


def test_framework_has_no_fixed_98_or_93_capacity() -> None:
    source = inspect.getsource(qualification_research)
    assert "range(98)" not in source and "range(93)" not in source
    assert "MAX_CANDIDATES" not in source and "FIXED_CAPACITY" not in source
