from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.application.intraday_probables import IntradayProbablesApplication
from kronos.intraday.historical_semantic import (
    SEMANTIC_QUALIFICATION_EVIDENCE_IDENTITY,
    WO06S_CONTRACT_VERSION,
    SemanticAvailability,
    SemanticDirection,
    SemanticFactFamily,
    SemanticQualificationEvidence,
    _identity,
    create_semantic_qualification_fact,
)
from kronos.intraday.probables import (
    FactualSourceKind,
    PopulationBucket,
    ProbableReason,
    ProbableState,
    ProbablesError,
    ProbablesFailure,
    ProbablesMemberEvidence,
    ProbablesStage,
    ProbablesUnavailableMember,
    create_v0_probables_methodology,
    evaluate_probables_run,
    probables_artifact_bytes,
)
from kronos.intraday.probables_persistence import ProbablesStore
from kronos.intraday.qualification import (
    PreviousCompletedDailyCandle,
    create_narrow_cpr_fact,
)
from tests.unit.intraday.test_historical_semantic import BOUNDARY, _semantic


IST = ZoneInfo("Asia/Kolkata")
SOURCE_RUN = "INTRADAY-DISCOVERY-RUN-PART3-FIXTURE"
SESSION = "NSE:2026-08-17"


def _narrow(subject: str, boundary: datetime, *, value: bool = True):  # type: ignore[no-untyped-def]
    high, low, close = (
        ("100", "90", "95") if value else ("105", "90", "95")
    )
    from decimal import Decimal

    return create_narrow_cpr_fact(PreviousCompletedDailyCandle(
        canonical_subject_identity=subject,
        previous_session_identity="NSE:2026-08-14",
        observation_session_identity=SESSION,
        source_daily_candle_identity=f"GOVERNED-1D:{subject}:2026-08-14",
        completed_at=datetime(2026, 8, 14, 15, 30, tzinfo=IST),
        observation_boundary=boundary,
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        completed=True,
        source_integrity_identity=f"INTEGRITY-DAILY:{subject}:2026-08-14",
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    ))


def _semantic_for(
    subject: str,
    *,
    boundary: datetime = BOUNDARY,
    hourly: SemanticDirection = SemanticDirection.LONG,
    fifteen: SemanticDirection = SemanticDirection.LONG,
    coherence: SemanticDirection | None = None,
    unavailable: frozenset[SemanticFactFamily] = frozenset(),
    information_suffix: str = "A",
):  # type: ignore[no-untyped-def]
    template = _semantic(
        hourly="SHORT" if hourly is SemanticDirection.SHORT else "LONG",
        fifteen="SHORT" if fifteen is SemanticDirection.SHORT else "LONG",
    )
    requested = {
        SemanticFactFamily.HOURLY_REGIME: hourly,
        SemanticFactFamily.FIFTEEN_MINUTE_STRUCTURE: fifteen,
        SemanticFactFamily.DIRECTIONAL_COHERENCE: (
            coherence
            if coherence is not None
            else hourly
            if hourly is fifteen and hourly in (SemanticDirection.LONG, SemanticDirection.SHORT)
            else SemanticDirection.CONFLICTING
        ),
    }
    facts = []
    for original in template.facts:
        direction = requested.get(original.family, original.direction)
        availability = SemanticAvailability.AVAILABLE
        if original.family in unavailable:
            availability = SemanticAvailability.UNAVAILABLE
            direction = SemanticDirection.UNAVAILABLE
        attributes = original.attributes
        if original.family is SemanticFactFamily.DAILY_CONTEXT:
            attributes = (*attributes, ("fixture_information", information_suffix))
        facts.append(create_semantic_qualification_fact(
            family=original.family,
            canonical_subject_identity=subject,
            market_session_identity=SESSION,
            timeframe=original.timeframe,
            availability=availability,
            direction=direction,
            attributes=attributes,
            values=original.values,
            source_evidence_identities=tuple(
                f"{identity}:{subject}" for identity in original.source_evidence_identities
            ),
            available_at=min(original.available_at, boundary),
            observation_boundary=boundary,
            policy_identity=original.policy_identity,
            source_operation_identity="PART3-FIXTURE-OPERATION",
            provenance=("SYNTHETIC-TEST-FIXTURE",),
        ))
    values = {
        "canonical_subject_identity": subject,
        "market_session_identity": SESSION,
        "observation_boundary": boundary,
        "source_bundle_identity": f"PART3-FIXTURE-BUNDLE:{subject}:{boundary.isoformat()}",
        "source_operation_identity": "PART3-FIXTURE-OPERATION",
        "candle_payload_identities": tuple(
            f"PART3-CANDLE:{subject}:{index}:{boundary.isoformat()}" for index in range(7)
        ),
        "facts": tuple(facts),
        "provenance": ("SYNTHETIC-TEST-FIXTURE",),
        "schema_identity": SEMANTIC_QUALIFICATION_EVIDENCE_IDENTITY,
        "schema_version": WO06S_CONTRACT_VERSION,
    }
    return SemanticQualificationEvidence(
        evidence_identity=_identity("INTRADAY-SEMANTIC-EVIDENCE-", values),
        integrity_identity=_identity("INTEGRITY-SEMANTIC-EVIDENCE-", values),
        **values,
    )


def _member(
    subject: str = "RELIANCE",
    *,
    boundary: datetime = BOUNDARY,
    narrow: bool | None = True,
    hourly: SemanticDirection = SemanticDirection.LONG,
    fifteen: SemanticDirection = SemanticDirection.LONG,
    coherence: SemanticDirection | None = None,
    unavailable: frozenset[SemanticFactFamily] = frozenset(),
    information_suffix: str = "A",
) -> ProbablesMemberEvidence:
    return ProbablesMemberEvidence(
        universe_member_identity=f"INTRADAY-UNIVERSE-MEMBER:{subject}",
        canonical_subject_identity=subject,
        market_session_identity=SESSION,
        observation_boundary=boundary,
        source_kind=FactualSourceKind.NATIVE_DISCOVERY,
        source_run_identity=SOURCE_RUN,
        source_member_identity=f"INTRADAY-DISCOVERY-RESULT:{subject}:{boundary.isoformat()}",
        narrow_cpr_fact=None if narrow is None else _narrow(subject, boundary, value=narrow),
        semantic_evidence=_semantic_for(
            subject,
            boundary=boundary,
            hourly=hourly,
            fifteen=fifteen,
            coherence=coherence,
            unavailable=unavailable,
            information_suffix=information_suffix,
        ),
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    )


def _unavailable(subject: str, *, boundary: datetime = BOUNDARY) -> ProbablesUnavailableMember:
    return ProbablesUnavailableMember(
        universe_member_identity=f"INTRADAY-UNIVERSE-MEMBER:{subject}",
        canonical_subject_identity=subject,
        market_session_identity=SESSION,
        observation_boundary=boundary,
        reason=ProbableReason.PREREQUISITE_UNAVAILABLE,
        source_identity=f"INTRADAY-RECONCILIATION:{subject}",
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    )


def _run(
    members: tuple[ProbablesMemberEvidence, ...],
    unavailable: tuple[ProbablesUnavailableMember, ...] = (),
    *,
    boundary: datetime = BOUNDARY,
):  # type: ignore[no-untyped-def]
    return evaluate_probables_run(
        methodology=create_v0_probables_methodology(),
        source_kind=FactualSourceKind.NATIVE_DISCOVERY,
        source_run_identity=SOURCE_RUN,
        universe_identity="KRONOS-INTRADAY-NATIVE-UNIVERSE-V1",
        universe_version="1.0.0",
        reconciliation_identity="KRONOS-INTRADAY-CANONICAL-RUNTIME-RECONCILIATION-V1",
        reconciliation_version="1.0.0",
        market_session_identity=SESSION,
        observation_boundary=boundary,
        member_evidence=members,
        unavailable_members=unavailable,
        provenance=("SYNTHETIC-TEST-FIXTURE", "NO-TRADING-AUTHORITY"),
    )


@pytest.mark.parametrize(
    ("member", "state", "reason", "direction"),
    (
        (_member(), ProbableState.LONG_PROBABLE, ProbableReason.V0_CONDITIONS_SATISFIED, SemanticDirection.LONG),
        (_member(hourly=SemanticDirection.SHORT, fifteen=SemanticDirection.SHORT), ProbableState.SHORT_PROBABLE, ProbableReason.V0_CONDITIONS_SATISFIED, SemanticDirection.SHORT),
        (_member(narrow=False), ProbableState.NOT_ADMITTED, ProbableReason.NARROW_CPR_NOT_SATISFIED, None),
        (_member(narrow=None), ProbableState.UNAVAILABLE, ProbableReason.NARROW_CPR_UNAVAILABLE, None),
        (_member(hourly=SemanticDirection.NON_DIRECTIONAL), ProbableState.NOT_ADMITTED, ProbableReason.ONE_HOUR_NON_DIRECTIONAL, None),
        (_member(fifteen=SemanticDirection.NON_DIRECTIONAL), ProbableState.NOT_ADMITTED, ProbableReason.FIFTEEN_MINUTE_NON_DIRECTIONAL, None),
        (_member(hourly=SemanticDirection.LONG, fifteen=SemanticDirection.SHORT), ProbableState.NOT_ADMITTED, ProbableReason.DIRECTION_CONFLICTING, None),
        (_member(hourly=SemanticDirection.SHORT, fifteen=SemanticDirection.LONG), ProbableState.NOT_ADMITTED, ProbableReason.DIRECTION_CONFLICTING, None),
        (_member(unavailable=frozenset({SemanticFactFamily.HOURLY_REGIME})), ProbableState.UNAVAILABLE, ProbableReason.ONE_HOUR_FACT_UNAVAILABLE, None),
        (_member(unavailable=frozenset({SemanticFactFamily.FIFTEEN_MINUTE_STRUCTURE})), ProbableState.UNAVAILABLE, ProbableReason.FIFTEEN_MINUTE_FACT_UNAVAILABLE, None),
    ),
)
def test_adversarial_methodology_states(member, state, reason, direction) -> None:  # type: ignore[no-untyped-def]
    result = _run((member,)).results[0]
    assert result.state is state
    assert result.reasons == (reason,)
    assert result.direction is direction


def test_participation_is_nonblocking_and_information_does_not_change_admission() -> None:
    unavailable = _run((_member(
        unavailable=frozenset({SemanticFactFamily.VOLUME_PARTICIPATION})
    ),)).results[0]
    changed = _run((_member(information_suffix="B"),)).results[0]
    baseline = _run((_member(information_suffix="A"),)).results[0]

    assert unavailable.state is ProbableState.LONG_PROBABLE
    assert unavailable.participation_state == "UNAVAILABLE"
    assert changed.state is baseline.state is ProbableState.LONG_PROBABLE
    assert changed.lineage.informational_fact_identities != baseline.lineage.informational_fact_identities
    assert changed.result_identity != baseline.result_identity


def test_member_failure_and_mcx_unavailability_are_isolated() -> None:
    run = _run((_member("RELIANCE"),), (_unavailable("GOLDM"), _unavailable("CRUDE")))
    assert run.diagnostics.starting_population == 3
    assert run.diagnostics.long_probables == 1
    assert run.diagnostics.unavailable_count == 2
    assert run.results[0].canonical_subject_identity == "CRUDE"
    assert all(
        item.state is ProbableState.UNAVAILABLE
        for item in run.results
        if item.canonical_subject_identity in {"GOLDM", "CRUDE"}
    )


@pytest.mark.parametrize(
    ("count", "bucket"),
    (
        (0, PopulationBucket.ZERO),
        (1, PopulationBucket.ONE_TO_FIVE),
        (6, PopulationBucket.SIX_TO_TEN),
        (11, PopulationBucket.ELEVEN_TO_FIFTEEN),
        (16, PopulationBucket.SIXTEEN_TO_NINETEEN),
        (20, PopulationBucket.TWENTY_PLUS),
    ),
)
def test_population_buckets_are_diagnostic_only(count: int, bucket: PopulationBucket) -> None:
    population = tuple(_member(f"MEMBER-{index:02d}") for index in range(max(count, 1)))
    if count == 0:
        population = tuple(
            _member(f"MEMBER-{index:02d}", narrow=False) for index in range(3)
        )
    run = _run(population)
    assert run.diagnostics.total_probables == count
    assert run.diagnostics.population_bucket is bucket
    assert len(run.results) == len(population)


def test_same_boundary_is_deterministic_and_new_boundary_creates_new_immutable_run() -> None:
    run_a = _run((_member(),))
    replay = _run((_member(),))
    boundary_b = BOUNDARY + timedelta(minutes=5)
    run_b = _run((_member(boundary=boundary_b),), boundary=boundary_b)

    assert probables_artifact_bytes(run_a) == probables_artifact_bytes(replay)
    assert run_a.run_identity == replay.run_identity
    assert run_b.run_identity != run_a.run_identity
    assert run_a.observation_boundary == BOUNDARY
    assert run_b.observation_boundary == boundary_b


def test_future_or_incomplete_facts_fail_closed() -> None:
    semantic = _semantic_for("RELIANCE", boundary=BOUNDARY + timedelta(minutes=5))
    with pytest.raises(ProbablesError, match=ProbablesFailure.LOOK_AHEAD.value):
        ProbablesMemberEvidence(
            universe_member_identity="INTRADAY-UNIVERSE-MEMBER:RELIANCE",
            canonical_subject_identity="RELIANCE",
            market_session_identity=SESSION,
            observation_boundary=BOUNDARY,
            source_kind=FactualSourceKind.NATIVE_DISCOVERY,
            source_run_identity=SOURCE_RUN,
            source_member_identity="INTRADAY-DISCOVERY-RESULT:RELIANCE",
            narrow_cpr_fact=_narrow("RELIANCE", BOUNDARY),
            semantic_evidence=semantic,
            provenance=("SYNTHETIC-TEST-FIXTURE",),
        )


def test_lineage_is_complete_and_contains_no_provider_token_or_trade_authority() -> None:
    result = _run((_member(),)).results[0]
    encoded = probables_artifact_bytes(_run((_member(),))).lower()
    assert result.state is ProbableState.LONG_PROBABLE
    assert result.completed_stages == tuple(ProbablesStage)
    assert result.lineage.narrow_cpr_fact_identity
    assert result.lineage.one_hour_fact_identity
    assert result.lineage.fifteen_minute_fact_identity
    assert result.lineage.coherence_fact_identity
    assert result.lineage.participation_fact_identity
    assert len(result.lineage.informational_fact_identities) == 5
    assert b"instrument_token" not in encoded
    assert b"access_token" not in encoded
    assert b"place_order" not in encoded
    assert b"paper" not in encoded
    assert b"live" not in encoded


def test_persistence_explicit_reload_idempotency_restart_and_conflict(tmp_path: Path) -> None:
    store = ProbablesStore(tmp_path)
    methodology = create_v0_probables_methodology()
    run_a = _run((_member(),))
    run_b = _run(
        (_member(boundary=BOUNDARY + timedelta(minutes=5)),),
        boundary=BOUNDARY + timedelta(minutes=5),
    )
    store.retain_methodology(methodology)
    path_a = store.retain_run(run_a)
    path_b = store.retain_run(run_b)
    assert store.retain_run(run_a) == path_a
    assert store.load_methodology(publication_identity=methodology.publication_identity) == methodology
    assert store.load_run(run_identity=run_a.run_identity) == run_a
    assert store.load_run(run_identity=run_b.run_identity) == run_b
    assert store.load_result(result_identity=run_a.results[0].result_identity) == run_a.results[0]
    assert store.load_diagnostics(
        diagnostics_identity=run_a.diagnostics.diagnostics_identity
    ) == run_a.diagnostics
    assert path_a != path_b and path_a.exists() and path_b.exists()
    path_a.write_bytes(path_a.read_bytes().replace(b"RELIANCE", b"TAMPERED"))
    with pytest.raises(ProbablesError, match=ProbablesFailure.INTEGRITY_INVALID.value):
        store.load_run(run_identity=run_a.run_identity)


def test_failed_later_refresh_preserves_last_successful(tmp_path: Path) -> None:
    app = IntradayProbablesApplication(store=ProbablesStore(tmp_path))
    member = _member()
    successful = app.refresh_analysis(
        source_kind=FactualSourceKind.NATIVE_DISCOVERY,
        source_run_identity=SOURCE_RUN,
        universe_identity="KRONOS-INTRADAY-NATIVE-UNIVERSE-V1",
        universe_version="1.0.0",
        reconciliation_identity="KRONOS-INTRADAY-CANONICAL-RUNTIME-RECONCILIATION-V1",
        reconciliation_version="1.0.0",
        market_session_identity=SESSION,
        observation_boundary=BOUNDARY,
        member_evidence=(member,),
        unavailable_members=(),
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    )
    app.record_failure("LATER_REFRESH_FACTUAL_FAILURE")
    snapshot = app.snapshot()
    assert snapshot.last_successful_run_identity == successful.run_identity
    assert snapshot.results == successful.results
    assert snapshot.current_failure == "LATER_REFRESH_FACTUAL_FAILURE"


def test_previous_session_fact_is_stable_across_same_session_refreshes() -> None:
    boundary_b = BOUNDARY + timedelta(minutes=5)
    first = _member()
    second = replace(
        _member(boundary=boundary_b),
        narrow_cpr_fact=first.narrow_cpr_fact,
    )
    assert first.narrow_cpr_fact is not None and second.narrow_cpr_fact is not None
    assert first.narrow_cpr_fact.fact_identity == second.narrow_cpr_fact.fact_identity
    assert first.narrow_cpr_fact.previous_session_identity == second.narrow_cpr_fact.previous_session_identity
    assert first.narrow_cpr_fact.previous_daily_high == second.narrow_cpr_fact.previous_daily_high
    assert first.narrow_cpr_fact.previous_daily_low == second.narrow_cpr_fact.previous_daily_low
    assert first.narrow_cpr_fact.previous_daily_close == second.narrow_cpr_fact.previous_daily_close
