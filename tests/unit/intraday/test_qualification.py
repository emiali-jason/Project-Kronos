from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
import inspect
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday import qualification
from kronos.intraday.qualification import (
    FACTUAL_OUTCOME_CONTRACT_IDENTITY,
    NARROW_CPR_CALCULATION_IDENTITY,
    NARROW_CPR_FACT_IDENTITY,
    PART1_CONTRACT_VERSION,
    POPULATION_DIAGNOSTICS_IDENTITY,
    QUALIFICATION_CONTRACT_IDENTITY,
    QUALIFICATION_CORPUS_IDENTITY,
    QUALIFICATION_HYPOTHESIS_IDENTITY,
    QUALIFICATION_OBSERVATION_IDENTITY,
    QUALIFICATION_REPORT_IDENTITY,
    EvidenceReference,
    OutcomeDefinitionStatus,
    PreviousCompletedDailyCandle,
    QualificationCorpusSession,
    QualificationError,
    QualificationEvidenceSource,
    QualificationEvidenceSufficiency,
    QualificationFailure,
    QualificationHypothesisStatus,
    QualificationObservationResult,
    create_factual_outcome_definition,
    create_factual_outcome_record,
    create_narrow_cpr_fact,
    create_narrow_cpr_hypothesis,
    create_population_diagnostics,
    create_qualification_corpus,
    create_qualification_corpus_session,
    create_qualification_hypothesis,
    create_qualification_observation,
    create_qualification_report,
    qualification_artifact_bytes,
    qualification_artifact_from_bytes,
)
from kronos.intraday.qualification_persistence import QualificationStore


IST = ZoneInfo("Asia/Kolkata")
OBSERVED = datetime(2026, 8, 24, 9, 15, tzinfo=IST)
COMPLETED = datetime(2026, 8, 21, 15, 30, tzinfo=IST)
SYNTHETIC = QualificationEvidenceSource.SYNTHETIC_TEST_FIXTURE


def _candle(
    *,
    high: object = Decimal("101"),
    low: object = Decimal("98.41"),
    close: object = Decimal("100"),
    completed: bool = True,
    previous_session: str = "NSE:2026-08-21",
    observation_session: str = "NSE:2026-08-24",
    integrity: str = "INTEGRITY-DAILY-CANDLE-001",
) -> PreviousCompletedDailyCandle:
    return PreviousCompletedDailyCandle(
        canonical_subject_identity="NSE-EQ-RELIANCE",
        previous_session_identity=previous_session,
        observation_session_identity=observation_session,
        source_daily_candle_identity="GOVERNED-1D-CANDLE-RELIANCE-2026-08-21",
        completed_at=COMPLETED,
        observation_boundary=OBSERVED,
        high=high,  # type: ignore[arg-type]
        low=low,  # type: ignore[arg-type]
        close=close,  # type: ignore[arg-type]
        completed=completed,
        source_integrity_identity=integrity,
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    )


def _hypothesis():  # type: ignore[no-untyped-def]
    return create_narrow_cpr_hypothesis(
        effective_from=OBSERVED,
        effective_through=datetime(9999, 12, 31, tzinfo=IST),
    )


def _observation(
    index: int,
    result: QualificationObservationResult,
    *,
    source: QualificationEvidenceSource = SYNTHETIC,
    session: str = "NSE:2026-08-24",
    subject: str | None = None,
):  # type: ignore[no-untyped-def]
    hypothesis = _hypothesis()
    evidence = EvidenceReference(
        evidence_identity=f"EVIDENCE-{index}",
        available_at=OBSERVED,
        source=source,
        provenance=("FIXTURE",),
    )
    return create_qualification_observation(
        canonical_subject_identity=subject or f"SUBJECT-{index}",
        market_session_identity=session,
        observation_boundary=OBSERVED,
        hypothesis=hypothesis,
        evidence=(evidence,),
        result=result,
        result_fact_identity=(
            f"NARROW-CPR-FACT-{index}"
            if result in {
                QualificationObservationResult.HYPOTHESIS_TRUE,
                QualificationObservationResult.HYPOTHESIS_FALSE,
            }
            else None
        ),
        evidence_source=source,
        provenance=("FIXTURE",),
    )


def _diagnostics(matches: int, *, total: int | None = None):  # type: ignore[no-untyped-def]
    population = matches if total is None else total
    observations = tuple(
        _observation(
            index,
            (
                QualificationObservationResult.HYPOTHESIS_TRUE
                if index < matches
                else QualificationObservationResult.HYPOTHESIS_FALSE
            ),
        )
        for index in range(population)
    )
    return create_population_diagnostics(
        market_session_identity="NSE:2026-08-24",
        hypothesis_identity=_hypothesis().hypothesis_identity,
        observations=observations,
    )


def _corpus(observations):  # type: ignore[no-untyped-def]
    hypothesis = _hypothesis()
    diagnostics = create_population_diagnostics(
        market_session_identity="NSE:2026-08-24",
        hypothesis_identity=hypothesis.hypothesis_identity,
        observations=observations,
    )
    session = create_qualification_corpus_session(
        market_session_identity="NSE:2026-08-24",
        observation_boundary=OBSERVED,
        universe_publication_identity="UNIVERSE-V1/1.0.0",
        reconciliation_publication_identity="RECONCILIATION-V1/1.0.0",
        discovery_run_identity=None,
        factual_evidence_identities=tuple(
            item.evidence[0].evidence_identity for item in observations
        ),
        hypothesis_identities=(hypothesis.hypothesis_identity,),
        outcome_evidence_window_identity=None,
        population_diagnostics_identity=diagnostics.diagnostics_identity,
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    )
    corpus = create_qualification_corpus(
        corpus_version="0.1.0",
        sessions=(session,),
        observations=observations,
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    )
    return corpus, hypothesis, diagnostics


def test_governed_contract_identities_are_explicit_and_versioned() -> None:
    assert QUALIFICATION_CONTRACT_IDENTITY.endswith("QUALIFICATION-V0")
    assert QUALIFICATION_HYPOTHESIS_IDENTITY.endswith("HYPOTHESIS-V0")
    assert QUALIFICATION_CORPUS_IDENTITY.endswith("CORPUS-V0")
    assert QUALIFICATION_OBSERVATION_IDENTITY.endswith("OBSERVATION-V0")
    assert POPULATION_DIAGNOSTICS_IDENTITY.endswith("DIAGNOSTICS-V0")
    assert QUALIFICATION_REPORT_IDENTITY.endswith("REPORT-V0")
    assert FACTUAL_OUTCOME_CONTRACT_IDENTITY.endswith("FACTUAL-OUTCOME-V0")
    assert NARROW_CPR_FACT_IDENTITY.endswith("NARROW-CPR-KGS-V0")
    assert PART1_CONTRACT_VERSION == "0.1.0"


def test_narrow_cpr_exact_formula_ordering_and_equivalence() -> None:
    fact = create_narrow_cpr_fact(_candle())
    expected_p = (Decimal("101") + Decimal("98.41") + Decimal("100")) / 3
    expected_bc = (Decimal("101") + Decimal("98.41")) / 2
    expected_tc = 2 * expected_p - expected_bc

    assert fact.pivot == expected_p
    assert fact.bc_raw == expected_bc
    assert fact.tc_raw == expected_tc
    assert fact.cpr_bottom == min(expected_bc, expected_tc)
    assert fact.cpr_top == max(expected_bc, expected_tc)
    assert fact.cpr_half_width == abs(expected_p - expected_bc)
    assert fact.cpr_half_width_pct == fact.cpr_half_width / Decimal("100") * 100
    assert fact.cpr_total_width == fact.cpr_top - fact.cpr_bottom
    assert fact.cpr_total_width_pct == fact.cpr_total_width / Decimal("100") * 100
    exact = create_narrow_cpr_fact(
        _candle(high=Decimal("102"), low=Decimal("99"), close=Decimal("99"))
    )
    assert exact.cpr_total_width == 2 * exact.cpr_half_width
    assert exact.cpr_total_width_pct == 2 * exact.cpr_half_width_pct


@pytest.mark.parametrize(
    ("low", "expected"),
    (("98.41", True), ("98.4", False), ("98.39", False)),
)
def test_narrow_cpr_strict_point_one_percent_boundary(
    low: str, expected: bool
) -> None:
    fact = create_narrow_cpr_fact(_candle(low=Decimal(low)))
    assert fact.narrow_cpr_kgs_v0 is expected
    if low == "98.4":
        assert fact.cpr_half_width_pct == Decimal("0.100")


@pytest.mark.parametrize(
    ("high", "low", "close", "relation"),
    (
        ("101", "98.41", "100", "above"),
        ("101", "99", "99", "below"),
        ("101", "99", "100", "equal"),
    ),
)
def test_tc_raw_may_be_above_below_or_equal_bc_raw(
    high: str, low: str, close: str, relation: str
) -> None:
    fact = create_narrow_cpr_fact(
        _candle(high=Decimal(high), low=Decimal(low), close=Decimal(close))
    )
    comparison = (
        "above" if fact.tc_raw > fact.bc_raw
        else "below" if fact.tc_raw < fact.bc_raw
        else "equal"
    )
    assert comparison == relation
    assert fact.cpr_bottom == min(fact.bc_raw, fact.tc_raw)
    assert fact.cpr_top == max(fact.bc_raw, fact.tc_raw)


@pytest.mark.parametrize(
    "changes",
    (
        {"high": None},
        {"low": None},
        {"close": None},
        {"high": Decimal("NaN")},
        {"low": Decimal("Infinity")},
        {"close": Decimal("0")},
        {"close": Decimal("-1")},
        {"completed": False},
        {"previous_session": "NSE:2026-08-24"},
        {"integrity": "INVALID"},
    ),
)
def test_narrow_cpr_invalid_or_incomplete_inputs_fail_closed(changes) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(QualificationError):
        _candle(**changes)


def test_narrow_cpr_identity_is_deterministic_and_reconstructable() -> None:
    first = create_narrow_cpr_fact(_candle())
    second = create_narrow_cpr_fact(_candle())
    restored = qualification_artifact_from_bytes(qualification_artifact_bytes(first))
    assert first == second == restored
    assert first.schema_identity == NARROW_CPR_FACT_IDENTITY
    assert first.schema_version == PART1_CONTRACT_VERSION


def test_tampered_narrow_cpr_integrity_is_rejected() -> None:
    fact = create_narrow_cpr_fact(_candle())
    document = json.loads(qualification_artifact_bytes(fact))
    document["artifact"]["cpr_half_width_pct"] = "99"
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(QualificationError) as caught:
        qualification_artifact_from_bytes(encoded)
    assert caught.value.failure is QualificationFailure.INTEGRITY_INVALID


def test_narrow_cpr_has_no_external_or_candidate_authority() -> None:
    source = inspect.getsource(qualification)
    assert "chartink" not in source.lower()
    assert "tradingview" not in source.lower()
    assert "chart_analyst" not in source.lower()
    assert "CandidateState" not in source
    assert "CANDIDATE_ADMITTED" not in source
    assert "BUY" not in source and "SELL" not in source


def test_hypothesis_identity_status_and_executable_configuration_boundary() -> None:
    first = _hypothesis()
    second = _hypothesis()
    assert first == second
    assert first.calculation_identity == NARROW_CPR_CALCULATION_IDENTITY
    assert first.status is QualificationHypothesisStatus.QUALIFYING
    assert first.evidence_sufficiency is QualificationEvidenceSufficiency.EVIDENCE_UNAVAILABLE
    assert first.real_evidence_count == 0
    with pytest.raises(QualificationError):
        create_qualification_hypothesis(
            hypothesis_version="0.1.0",
            name="unsafe",
            family="unsafe",
            required_evidence_families=(lambda: True,),  # type: ignore[arg-type]
            calculation_identity="unsafe",
            status=QualificationHypothesisStatus.QUALIFYING,
            evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_UNAVAILABLE,
            effective_from=OBSERVED,
            effective_through=OBSERVED,
            provenance=("TEST",),
        )


def test_synthetic_evidence_cannot_approve_methodology_or_report_readiness() -> None:
    base = _hypothesis()
    with pytest.raises(QualificationError):
        replace(
            base,
            status=QualificationHypothesisStatus.APPROVED_FOR_METHODOLOGY,
        )
    corpus, hypothesis, diagnostics = _corpus(
        (_observation(1, QualificationObservationResult.HYPOTHESIS_TRUE),)
    )
    with pytest.raises(QualificationError) as caught:
        create_qualification_report(
            report_version="0.1.0",
            corpus=corpus,
            hypotheses=(hypothesis,),
            diagnostics=(diagnostics,),
            evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_READY_FOR_REVIEW,
            unresolved_methodology_questions=("MARKET_USEFULNESS",),
            provenance=("TEST",),
        )
    assert caught.value.failure is QualificationFailure.EVIDENCE_AUTHORITY


def test_real_and_synthetic_evidence_are_distinct_and_lookahead_fails() -> None:
    synthetic = _observation(1, QualificationObservationResult.HYPOTHESIS_TRUE)
    real = _observation(
        2,
        QualificationObservationResult.HYPOTHESIS_FALSE,
        source=QualificationEvidenceSource.REAL_GOVERNED_MARKET_EVIDENCE,
    )
    assert synthetic.evidence_source is SYNTHETIC
    assert real.evidence_source is QualificationEvidenceSource.REAL_GOVERNED_MARKET_EVIDENCE
    leaking = EvidenceReference(
        evidence_identity="FUTURE-EVIDENCE",
        available_at=OBSERVED + timedelta(minutes=1),
        source=SYNTHETIC,
        provenance=("TEST",),
    )
    with pytest.raises(QualificationError) as caught:
        create_qualification_observation(
            canonical_subject_identity="SUBJECT",
            market_session_identity="SESSION",
            observation_boundary=OBSERVED,
            hypothesis=_hypothesis(),
            evidence=(leaking,),
            result=QualificationObservationResult.HYPOTHESIS_TRUE,
            result_fact_identity="FACT",
            evidence_source=SYNTHETIC,
            provenance=("TEST",),
        )
    assert caught.value.failure is QualificationFailure.LOOK_AHEAD


def test_observation_identity_is_deterministic_and_unavailable_is_preserved() -> None:
    first = _observation(1, QualificationObservationResult.UNAVAILABLE)
    second = _observation(1, QualificationObservationResult.UNAVAILABLE)
    assert first == second
    assert first.result is QualificationObservationResult.UNAVAILABLE
    assert first.result_fact_identity is None


def test_factual_outcome_definition_is_versioned_and_not_a_trade() -> None:
    pending = create_factual_outcome_definition(
        definition_version="0.1.0",
        family="SESSION_EXPANSION",
        measure_names=("maximum_upward_excursion", "maximum_downward_excursion"),
        status=OutcomeDefinitionStatus.OUTCOME_DEFINITION_PENDING,
        provenance=("WO-06-PART-1",),
    )
    with pytest.raises(QualificationError) as caught:
        create_factual_outcome_record(
            definition=pending,
            canonical_subject_identity="SUBJECT",
            source_observation_identity="OBSERVATION",
            observation_boundary=OBSERVED,
            measured_at=OBSERVED + timedelta(hours=6),
            measures=(("maximum_upward_excursion", Decimal("1")), ("maximum_downward_excursion", Decimal("2"))),
            provenance=("TEST",),
        )
    assert caught.value.failure is QualificationFailure.OUTCOME_DEFINITION_PENDING
    with pytest.raises(QualificationError):
        create_factual_outcome_definition(
            definition_version="0.1.0",
            family="INVALID-TRADE",
            measure_names=("pnl",),
            status=OutcomeDefinitionStatus.DEFINITION_APPROVED,
            provenance=("TEST",),
        )


def test_approved_factual_outcome_occurs_only_after_observation() -> None:
    definition = create_factual_outcome_definition(
        definition_version="0.1.0",
        family="SESSION_RANGE",
        measure_names=("subsequent_range",),
        status=OutcomeDefinitionStatus.DEFINITION_APPROVED,
        provenance=("TEST",),
    )
    outcome = create_factual_outcome_record(
        definition=definition,
        canonical_subject_identity="SUBJECT",
        source_observation_identity="OBSERVATION",
        observation_boundary=OBSERVED,
        measured_at=OBSERVED + timedelta(hours=6),
        measures=(("subsequent_range", Decimal("4.5")),),
        provenance=("TEST",),
    )
    assert outcome.measured_at > outcome.observation_boundary
    assert qualification_artifact_from_bytes(qualification_artifact_bytes(outcome)) == outcome


def test_population_arithmetic_distinguishes_matches_unavailable_and_failures() -> None:
    observations = (
        _observation(1, QualificationObservationResult.HYPOTHESIS_TRUE),
        _observation(2, QualificationObservationResult.HYPOTHESIS_FALSE),
        _observation(3, QualificationObservationResult.UNAVAILABLE),
        _observation(4, QualificationObservationResult.FACTUAL_FAILURE),
    )
    result = create_population_diagnostics(
        market_session_identity="NSE:2026-08-24",
        hypothesis_identity=_hypothesis().hypothesis_identity,
        observations=observations,
    )
    assert result.factual_universe_count == 4
    assert result.hypothesis_match_count == 1
    assert result.hypothesis_non_match_count == 1
    assert result.unavailable_count == 1
    assert result.factual_failure_count == 1
    assert result.retention_percentage == Decimal("25")
    assert result.final_probables_count is None


@pytest.mark.parametrize(
    ("matches", "zero", "over_ten", "over_fifteen", "twenty"),
    (
        (0, True, False, False, False),
        (5, False, False, False, False),
        (12, False, True, False, False),
        (16, False, True, True, False),
        (20, False, True, True, True),
    ),
)
def test_population_extremes_are_diagnostics_without_truncation(
    matches: int,
    zero: bool,
    over_ten: bool,
    over_fifteen: bool,
    twenty: bool,
) -> None:
    result = _diagnostics(matches)
    assert result.hypothesis_match_count == matches
    assert result.zero_match_session is zero
    assert result.over_ten_session is over_ten
    assert result.over_fifteen_session is over_fifteen
    assert result.twenty_or_more_session is twenty
    assert result.final_probables_count is None


def test_no_fixed_population_quota_score_ranking_or_top_n_exists() -> None:
    source = inspect.getsource(qualification)
    for prohibited in (
        "MIN_PROBABLES",
        "MAX_PROBABLES",
        "top_n",
        "candidate_score",
        "candidate_ranking",
    ):
        assert prohibited not in source


def test_current_five_unavailable_members_cannot_become_fixture_probables() -> None:
    labels = ("GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE")
    observations = tuple(
        _observation(
            index,
            QualificationObservationResult.UNAVAILABLE,
            subject=label,
        )
        for index, label in enumerate(labels)
    )
    assert all(item.result is QualificationObservationResult.UNAVAILABLE for item in observations)
    assert all(item.result_fact_identity is None for item in observations)


def test_corpus_is_multi_subject_identity_bound_and_deterministic() -> None:
    observations = (
        _observation(1, QualificationObservationResult.HYPOTHESIS_TRUE),
        _observation(2, QualificationObservationResult.HYPOTHESIS_FALSE),
    )
    first, _, _ = _corpus(observations)
    second, _, _ = _corpus(observations)
    assert first == second
    assert first.schema_identity == QUALIFICATION_CORPUS_IDENTITY
    assert len(first.observations) == 2
    assert first.sessions[0].discovery_run_identity is None


def test_report_aggregates_population_without_claiming_market_efficacy() -> None:
    observations = tuple(
        _observation(
            index,
            QualificationObservationResult.HYPOTHESIS_TRUE if index < 5 else QualificationObservationResult.HYPOTHESIS_FALSE,
        )
        for index in range(8)
    )
    corpus, hypothesis, diagnostics = _corpus(observations)
    report = create_qualification_report(
        report_version="0.1.0",
        corpus=corpus,
        hypotheses=(hypothesis,),
        diagnostics=(diagnostics,),
        evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_UNAVAILABLE,
        unresolved_methodology_questions=("DIRECTION", "OUTCOME_DEFINITION"),
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    )
    assert report.session_count == 1
    assert report.observation_count == 8
    assert report.real_evidence_count == 0
    assert report.synthetic_fixture_count == 8
    assert report.hypothesis_true_count == 5
    assert report.hypothesis_false_count == 3
    assert report.mean_match_population == report.median_match_population == Decimal(5)
    assert report.stage_survivor_totals == ()
    assert report.conclusion == "MARKET_USEFULNESS_NOT_ESTABLISHED"
    assert not report.outcome_available


def test_multi_session_report_aggregates_distribution_and_stage_attrition() -> None:
    hypothesis = _hypothesis()
    first_observations = tuple(
        _observation(
            index,
            QualificationObservationResult.HYPOTHESIS_TRUE if index < 2 else QualificationObservationResult.HYPOTHESIS_FALSE,
            session="SESSION-1",
        )
        for index in range(4)
    )
    second_observations = tuple(
        _observation(
            index + 10,
            QualificationObservationResult.HYPOTHESIS_TRUE if index < 3 else QualificationObservationResult.HYPOTHESIS_FALSE,
            session="SESSION-2",
        )
        for index in range(5)
    )
    first_diagnostics = create_population_diagnostics(
        market_session_identity="SESSION-1",
        hypothesis_identity=hypothesis.hypothesis_identity,
        observations=first_observations,
        stage_survivor_counts=(("NARROW_CPR", 2),),
    )
    second_diagnostics = create_population_diagnostics(
        market_session_identity="SESSION-2",
        hypothesis_identity=hypothesis.hypothesis_identity,
        observations=second_observations,
        stage_survivor_counts=(("NARROW_CPR", 3),),
    )
    sessions = tuple(
        create_qualification_corpus_session(
            market_session_identity=session,
            observation_boundary=OBSERVED,
            universe_publication_identity="UNIVERSE",
            reconciliation_publication_identity="RECONCILIATION",
            discovery_run_identity=None,
            factual_evidence_identities=tuple(
                item.evidence[0].evidence_identity for item in observations
            ),
            hypothesis_identities=(hypothesis.hypothesis_identity,),
            outcome_evidence_window_identity=None,
            population_diagnostics_identity=diagnostics.diagnostics_identity,
            provenance=("FIXTURE",),
        )
        for session, observations, diagnostics in (
            ("SESSION-1", first_observations, first_diagnostics),
            ("SESSION-2", second_observations, second_diagnostics),
        )
    )
    corpus = create_qualification_corpus(
        corpus_version="0.1.0",
        sessions=sessions,
        observations=first_observations + second_observations,
        provenance=("FIXTURE",),
    )
    report = create_qualification_report(
        report_version="0.1.0",
        corpus=corpus,
        hypotheses=(hypothesis,),
        diagnostics=(first_diagnostics, second_diagnostics),
        evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_ACCUMULATING,
        unresolved_methodology_questions=("MARKET_USEFULNESS",),
        provenance=("FIXTURE",),
    )
    assert report.session_count == 2
    assert report.observation_count == 9
    assert report.mean_match_population == Decimal("2.5")
    assert report.median_match_population == Decimal("2.5")
    assert report.minimum_match_population == 2
    assert report.maximum_match_population == 3
    assert report.match_population_distribution == ((2, 1), (3, 1))
    assert report.stage_survivor_totals == (("NARROW_CPR", 5),)


@pytest.mark.parametrize(
    "artifact_name",
    (
        "NarrowCprFact",
        "QualificationHypothesis",
        "QualificationObservation",
        "PopulationDiagnostics",
        "QualificationCorpus",
        "QualificationReport",
        "FactualOutcomeDefinition",
        "FactualOutcomeRecord",
    ),
)
def test_qualification_store_is_explicit_idempotent_and_restart_safe(
    tmp_path: Path, artifact_name: str
) -> None:
    fact = create_narrow_cpr_fact(_candle())
    observation = _observation(1, QualificationObservationResult.HYPOTHESIS_TRUE)
    corpus, hypothesis, diagnostics = _corpus((observation,))
    report = create_qualification_report(
        report_version="0.1.0",
        corpus=corpus,
        hypotheses=(hypothesis,),
        diagnostics=(diagnostics,),
        evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_UNAVAILABLE,
        unresolved_methodology_questions=("MARKET_USEFULNESS",),
        provenance=("TEST",),
    )
    outcome_definition = create_factual_outcome_definition(
        definition_version="0.1.0",
        family="SESSION_RANGE",
        measure_names=("subsequent_range",),
        status=OutcomeDefinitionStatus.DEFINITION_APPROVED,
        provenance=("TEST",),
    )
    outcome = create_factual_outcome_record(
        definition=outcome_definition,
        canonical_subject_identity="SUBJECT",
        source_observation_identity=observation.observation_identity,
        observation_boundary=OBSERVED,
        measured_at=OBSERVED + timedelta(hours=6),
        measures=(("subsequent_range", Decimal("5")),),
        provenance=("TEST",),
    )
    artifacts = {
        "NarrowCprFact": (fact, fact.fact_identity),
        "QualificationHypothesis": (hypothesis, hypothesis.hypothesis_identity),
        "QualificationObservation": (observation, observation.observation_identity),
        "PopulationDiagnostics": (diagnostics, diagnostics.diagnostics_identity),
        "QualificationCorpus": (corpus, corpus.corpus_identity),
        "QualificationReport": (report, report.report_identity),
        "FactualOutcomeDefinition": (
            outcome_definition,
            outcome_definition.definition_identity,
        ),
        "FactualOutcomeRecord": (outcome, outcome.outcome_identity),
    }
    value, identity = artifacts[artifact_name]
    store = QualificationStore(tmp_path.resolve())
    first_path = store.retain(value)
    second_path = store.retain(value)
    restarted = QualificationStore(tmp_path.resolve())
    assert first_path == second_path
    assert restarted.load(artifact_type=artifact_name, artifact_identity=identity) == value
    assert not hasattr(restarted, "load_latest")


def test_persistence_conflict_and_tamper_fail_closed(tmp_path: Path) -> None:
    fact = create_narrow_cpr_fact(_candle())
    store = QualificationStore(tmp_path.resolve())
    path = store.retain(fact)
    path.write_text("{}\n")
    with pytest.raises(QualificationError) as conflict:
        store.retain(fact)
    assert conflict.value.failure is QualificationFailure.PERSISTENCE_CONFLICT
    with pytest.raises(QualificationError):
        store.load(artifact_type="NarrowCprFact", artifact_identity=fact.fact_identity)


def test_successor_hypothesis_does_not_mutate_historical_record(tmp_path: Path) -> None:
    first = _hypothesis()
    successor = create_qualification_hypothesis(
        hypothesis_version="0.2.0",
        name=first.name,
        family=first.family,
        required_evidence_families=first.required_evidence_families,
        calculation_identity="NARROW_CPR_SUCCESSOR_RESEARCH_ONLY",
        status=QualificationHypothesisStatus.UNCOMMISSIONED,
        evidence_sufficiency=QualificationEvidenceSufficiency.EVIDENCE_UNAVAILABLE,
        effective_from=OBSERVED + timedelta(days=1),
        effective_through=datetime(9999, 12, 31, tzinfo=IST),
        provenance=("SUCCESSOR-TEST",),
    )
    store = QualificationStore(tmp_path.resolve())
    first_path = store.retain(first)
    first_bytes = first_path.read_bytes()
    successor_path = store.retain(successor)
    assert first_path != successor_path
    assert first_path.read_bytes() == first_bytes
    assert store.load(artifact_type="QualificationHypothesis", artifact_identity=first.hypothesis_identity) == first


def test_framework_has_no_fixed_current_universe_capacity_literals() -> None:
    source = inspect.getsource(qualification)
    for literal in ("98", "93", "91"):
        assert literal not in source
