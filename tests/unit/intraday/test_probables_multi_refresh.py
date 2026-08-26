from __future__ import annotations

from dataclasses import fields, replace
from datetime import timedelta
from hashlib import sha256
import inspect
from pathlib import Path

import pytest

from kronos.application.intraday_discovery_operation import (
    IntradayDiscoveryOperationService,
)
from kronos.application.intraday_probables import (
    IntradayProbablesApplication,
    IntradayProbablesSnapshot,
)
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import (
    SemanticDirection,
    SemanticFactFamily,
    SemanticQualificationEvidence,
    SemanticEvidenceError,
    _identity,
    create_semantic_qualification_fact,
    derive_semantic_qualification_evidence,
)
from kronos.intraday.probables import (
    FactualSourceKind,
    PopulationBucket,
    ProbableMemberResult,
    ProbableReason,
    ProbableState,
    ProbablesError,
    ProbablesFailure,
    ProbablesRun,
    probables_artifact_bytes,
)
from kronos.intraday.probables_persistence import ProbablesStore
from tests.unit.intraday.test_historical_semantic import (
    BOUNDARY,
    _candle,
    _payloads,
    _previous,
)
from tests.unit.intraday.test_probables import (
    SESSION,
    SOURCE_RUN,
    _member,
    _run,
    _unavailable,
)


def _refresh(
    application: IntradayProbablesApplication,
    members,
    unavailable=(),
    *,
    boundary=BOUNDARY,
):  # type: ignore[no-untyped-def]
    return application.refresh_analysis(
        source_kind=FactualSourceKind.NATIVE_DISCOVERY,
        source_run_identity=SOURCE_RUN,
        universe_identity="KRONOS-INTRADAY-NATIVE-UNIVERSE-V1",
        universe_version="1.0.0",
        reconciliation_identity=(
            "KRONOS-INTRADAY-CANONICAL-RUNTIME-RECONCILIATION-V1"
        ),
        reconciliation_version="1.0.0",
        market_session_identity=SESSION,
        observation_boundary=boundary,
        member_evidence=members,
        unavailable_members=unavailable,
        provenance=("SYNTHETIC-WO-06V-TEST-FIXTURE", "NO-TRADING-AUTHORITY"),
    )


def test_four_same_session_refreshes_are_immutable_and_restart_reconstructable(
    tmp_path: Path,
) -> None:
    store = ProbablesStore(tmp_path)
    application = IntradayProbablesApplication(store=store)
    boundaries = tuple(
        BOUNDARY - timedelta(minutes=value) for value in (180, 120, 60, 0)
    )
    members = (
        _member(
            boundary=boundaries[0],
            fifteen=SemanticDirection.NON_DIRECTIONAL,
        ),
        _member(boundary=boundaries[1]),
        _member(
            boundary=boundaries[2],
            hourly=SemanticDirection.SHORT,
            fifteen=SemanticDirection.SHORT,
        ),
        _member(
            boundary=boundaries[3],
            hourly=SemanticDirection.LONG,
            fifteen=SemanticDirection.SHORT,
        ),
    )
    stable_narrow = members[0].narrow_cpr_fact
    members = tuple(replace(item, narrow_cpr_fact=stable_narrow) for item in members)

    runs = tuple(
        _refresh(application, (member,), boundary=boundary)
        for member, boundary in zip(members, boundaries, strict=True)
    )

    assert tuple(run.results[0].state for run in runs) == (
        ProbableState.NOT_ADMITTED,
        ProbableState.LONG_PROBABLE,
        ProbableState.SHORT_PROBABLE,
        ProbableState.NOT_ADMITTED,
    )
    assert runs[0].results[0].reasons == (
        ProbableReason.FIFTEEN_MINUTE_NON_DIRECTIONAL,
    )
    assert runs[3].results[0].reasons == (ProbableReason.DIRECTION_CONFLICTING,)
    assert len({run.run_identity for run in runs}) == 4
    assert len({run.results[0].result_identity for run in runs}) == 4
    assert all(
        run.results[0].lineage.narrow_cpr_fact_identity
        == runs[0].results[0].lineage.narrow_cpr_fact_identity
        for run in runs
    )
    assert stable_narrow is not None
    assert all(
        item.narrow_cpr_fact is not None
        and (
            item.narrow_cpr_fact.previous_daily_high,
            item.narrow_cpr_fact.previous_daily_low,
            item.narrow_cpr_fact.previous_daily_close,
        )
        == (
            stable_narrow.previous_daily_high,
            stable_narrow.previous_daily_low,
            stable_narrow.previous_daily_close,
        )
        for item in members
    )
    for family in (
        SemanticFactFamily.PDH_PDL_RELATIONSHIP,
        SemanticFactFamily.CPR_LOCATION,
        SemanticFactFamily.CLASSIC_PIVOT_RELATIONSHIPS,
    ):
        stable_levels = tuple(
            (name, value)
            for name, value in members[0].fact_map[family].values
            if name != "current_close"
        )
        assert all(
            tuple(
                (name, value)
                for name, value in item.fact_map[family].values
                if name != "current_close"
            )
            == stable_levels
            for item in members
        )
    assert all(store.load_run(run_identity=run.run_identity) == run for run in runs)

    restarted = IntradayProbablesApplication(
        store=store,
        last_successful_run_identity=runs[-1].run_identity,
    )
    assert restarted.snapshot().run == runs[-1]
    assert store.load_run(run_identity=runs[0].run_identity) == runs[0]


def test_same_boundary_same_evidence_has_same_complete_canonical_document(
    tmp_path: Path,
) -> None:
    application = IntradayProbablesApplication(store=ProbablesStore(tmp_path))
    first = _refresh(application, (_member(),))
    replay = _refresh(application, (_member(),))

    assert first.run_identity == replay.run_identity
    assert first.results == replay.results
    assert first.diagnostics == replay.diagnostics
    assert probables_artifact_bytes(first) == probables_artifact_bytes(replay)


@pytest.mark.parametrize(
    ("timeframe", "payload_index", "start"),
    (
        (IntradayTimeframe.FIVE_MINUTES, 6, BOUNDARY - timedelta(minutes=5)),
        (IntradayTimeframe.FIFTEEN_MINUTES, 4, BOUNDARY - timedelta(minutes=15)),
        (IntradayTimeframe.ONE_HOUR, 2, BOUNDARY - timedelta(hours=1)),
    ),
)
def test_incomplete_candle_is_excluded_then_eligible_only_at_next_boundary(
    timeframe: IntradayTimeframe,
    payload_index: int,
    start,
) -> None:  # type: ignore[no-untyped-def]
    candidate = _candle(
        timeframe=timeframe,
        start=start,
        high="104",
        low="100",
        close="103",
        volume=250,
    )
    early_boundary = BOUNDARY - timedelta(microseconds=1)
    with pytest.raises(SemanticEvidenceError, match="CANDLE_PAYLOAD_INVALID"):
        replace(candidate, observation_boundary=early_boundary)

    payloads = list(_payloads())
    payloads[payload_index] = candidate
    semantic = derive_semantic_qualification_evidence(
        candle_payloads=tuple(payloads),
        previous_session_facts=_previous(),
        source_bundle_identity=f"INTRADAY-HISTORICAL-FACT-BUNDLE-WO06V-{timeframe.value}",
        source_operation_identity=candidate.source_operation_identity,
        provenance=("SYNTHETIC-WO-06V-TEST-FIXTURE",),
    )
    later_member = replace(_member(), semantic_evidence=semantic)
    later_run = _run((later_member,))

    assert candidate.candle_identity in semantic.candle_payload_identities
    assert candidate.available_at == BOUNDARY
    assert later_run.results[0].state is ProbableState.LONG_PROBABLE


def test_probable_entry_exit_and_direction_flip_never_rewrite_prior_results() -> None:
    boundary_a = BOUNDARY - timedelta(minutes=30)
    boundary_b = BOUNDARY - timedelta(minutes=15)
    boundary_c = BOUNDARY
    run_a = _run((_member(boundary=boundary_a, narrow=False),), boundary=boundary_a)
    run_b = _run((_member(boundary=boundary_b),), boundary=boundary_b)
    run_c = _run(
        (_member(
            boundary=boundary_c,
            hourly=SemanticDirection.SHORT,
            fifteen=SemanticDirection.SHORT,
        ),),
        boundary=boundary_c,
    )

    assert run_a.results[0].state is ProbableState.NOT_ADMITTED
    assert run_b.results[0].state is ProbableState.LONG_PROBABLE
    assert run_c.results[0].state is ProbableState.SHORT_PROBABLE
    assert len({run_a.run_identity, run_b.run_identity, run_c.run_identity}) == 3
    assert run_a.results[0].state is ProbableState.NOT_ADMITTED
    assert run_b.results[0].state is ProbableState.LONG_PROBABLE


@pytest.mark.parametrize(
    "family",
    (
        SemanticFactFamily.DAILY_CONTEXT,
        SemanticFactFamily.FIVE_MINUTE_PROGRESSION,
        SemanticFactFamily.PDH_PDL_RELATIONSHIP,
        SemanticFactFamily.CPR_LOCATION,
        SemanticFactFamily.CLASSIC_PIVOT_RELATIONSHIPS,
    ),
)
def test_each_informational_family_can_change_without_admission_authority(
    family: SemanticFactFamily,
) -> None:
    baseline_member = _member()
    semantic = baseline_member.semantic_evidence
    changed_facts = []
    for fact in semantic.facts:
        if fact.family is family:
            fact = create_semantic_qualification_fact(
                family=fact.family,
                canonical_subject_identity=fact.canonical_subject_identity,
                market_session_identity=fact.market_session_identity,
                timeframe=fact.timeframe,
                availability=fact.availability,
                direction=fact.direction,
                attributes=(*fact.attributes, ("wo06v_mutation", family.value)),
                values=fact.values,
                source_evidence_identities=fact.source_evidence_identities,
                available_at=fact.available_at,
                observation_boundary=fact.observation_boundary,
                policy_identity=fact.policy_identity,
                source_operation_identity=fact.source_operation_identity,
                provenance=fact.provenance,
            )
        changed_facts.append(fact)
    values = {
        "canonical_subject_identity": semantic.canonical_subject_identity,
        "market_session_identity": semantic.market_session_identity,
        "observation_boundary": semantic.observation_boundary,
        "source_bundle_identity": f"{semantic.source_bundle_identity}:{family.value}",
        "source_operation_identity": semantic.source_operation_identity,
        "candle_payload_identities": semantic.candle_payload_identities,
        "facts": tuple(changed_facts),
        "provenance": semantic.provenance,
        "schema_identity": semantic.schema_identity,
        "schema_version": semantic.schema_version,
    }
    changed_semantic = SemanticQualificationEvidence(
        evidence_identity=_identity("INTRADAY-SEMANTIC-EVIDENCE-", values),
        integrity_identity=_identity("INTEGRITY-SEMANTIC-EVIDENCE-", values),
        **values,
    )
    baseline = _run((baseline_member,)).results[0]
    changed = _run((replace(baseline_member, semantic_evidence=changed_semantic),)).results[0]

    assert baseline.state is changed.state is ProbableState.LONG_PROBABLE
    assert baseline.direction is changed.direction
    assert baseline.result_identity != changed.result_identity


def test_member_failures_and_five_mcx_unavailable_do_not_abort_nse_population() -> None:
    nse = (_member("RELIANCE"), _member("SBIN"), _member("INFY", narrow=False))
    failed = (_unavailable("TCS"), _unavailable("HDFCBANK"))
    mcx = tuple(
        _unavailable(subject)
        for subject in ("GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE")
    )
    run = _run(nse, (*failed, *mcx))

    assert run.diagnostics.starting_population == 10
    assert run.diagnostics.evaluable_count == 3
    assert run.diagnostics.unavailable_count == 7
    assert run.diagnostics.long_probables == 2
    assert run.diagnostics.not_admitted_count == 1
    assert all(
        result.state is ProbableState.UNAVAILABLE
        for result in run.results
        if result.canonical_subject_identity
        in {"GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE"}
    )


def test_run_level_integrity_failure_preserves_last_success_and_records_failure(
    tmp_path: Path,
) -> None:
    store = ProbablesStore(tmp_path)
    application = IntradayProbablesApplication(store=store)
    successful = _refresh(application, (_member(),))
    successful_timestamp = application.snapshot().last_successful_analysis

    with pytest.raises(ProbablesError, match=ProbablesFailure.INPUT_INVALID.value):
        _refresh(application, (_member(), _member()))

    snapshot = application.snapshot()
    assert snapshot.last_successful_run_identity == successful.run_identity
    assert snapshot.last_successful_analysis == successful_timestamp
    assert snapshot.run == successful
    assert snapshot.current_failure == ProbablesFailure.INPUT_INVALID.value
    assert tuple((tmp_path / "probables-v1" / "runs").glob("*.json")) == (
        store.run_path(successful.run_identity),
    )


def test_zero_and_twenty_plus_populations_have_exact_unrelaxed_accounting() -> None:
    zero = _run(tuple(_member(f"ZERO-{index}", narrow=False) for index in range(6)))
    long_members = tuple(_member(f"LONG-{index:02d}") for index in range(10))
    short_members = tuple(
        _member(
            f"SHORT-{index:02d}",
            hourly=SemanticDirection.SHORT,
            fifteen=SemanticDirection.SHORT,
        )
        for index in range(11)
    )
    rejected = tuple(_member(f"REJECTED-{index}", narrow=False) for index in range(2))
    conflicts = tuple(
        _member(
            f"CONFLICT-{index}",
            hourly=SemanticDirection.LONG,
            fifteen=SemanticDirection.SHORT,
        )
        for index in range(2)
    )
    unavailable = tuple(_unavailable(f"FAILED-{index}") for index in range(3))
    flood = _run((*long_members, *short_members, *rejected, *conflicts), unavailable)

    assert zero.diagnostics.total_probables == 0
    assert zero.diagnostics.population_bucket is PopulationBucket.ZERO
    assert zero.diagnostics.not_admitted_count == 6
    assert flood.diagnostics.starting_population == 28
    assert flood.diagnostics.evaluable_count == 25
    assert flood.diagnostics.unavailable_count == 3
    assert flood.diagnostics.long_probables == 10
    assert flood.diagnostics.short_probables == 11
    assert flood.diagnostics.total_probables == 21
    assert flood.diagnostics.not_admitted_count == 4
    assert flood.diagnostics.conflicting_count == 2
    assert flood.diagnostics.retention == "21/28"
    assert flood.diagnostics.attrition == "7/28"
    assert flood.diagnostics.population_bucket is PopulationBucket.TWENTY_PLUS
    assert len(flood.results) == 28


def test_governed_boundary_not_wall_clock_controls_identity_and_look_ahead() -> None:
    first = _run((_member(),))
    wall_clock_observation = BOUNDARY + timedelta(days=3650)
    replay = _run((_member(),))
    assert wall_clock_observation > first.observation_boundary
    assert probables_artifact_bytes(first) == probables_artifact_bytes(replay)

    with pytest.raises(ProbablesError, match=ProbablesFailure.LOOK_AHEAD.value):
        replace(
            _member(boundary=BOUNDARY + timedelta(minutes=5)),
            observation_boundary=BOUNDARY,
        )


def test_probables_contract_has_no_downstream_trade_or_risk_mutation_surface() -> None:
    prohibited = {
        "trade_construction",
        "entry_timing",
        "sponsor_decision",
        "position",
        "lifecycle",
        "paper_eligibility",
        "live_eligibility",
    }
    exposed = {
        field.name
        for contract in (ProbableMemberResult, ProbablesRun, IntradayProbablesSnapshot)
        for field in fields(contract)
    }
    assert prohibited.isdisjoint(exposed)
    assert _run((_member(),)).results[0].execution_eligibility == "NOT_ESTABLISHED"


def test_published_refresh_control_invokes_bounded_probables_composition() -> None:
    source = inspect.getsource(IntradayDiscoveryOperationService.execute)
    assert "map_discovery_execution_to_probables" in source
    assert "refresh_analysis" in source
    assert "historical_candles" not in inspect.getsource(
        IntradayProbablesApplication.refresh_analysis
    )


def test_commissioned_methodology_document_checksum_is_frozen() -> None:
    document = Path(
        "docs/architecture/products/intraday/"
        "KRONOS-INTRADAY-WO-06-PART-3-V0-PROBABLES-METHODOLOGY.md"
    )
    assert sha256(document.read_bytes()).hexdigest() == (
        "54807349d01da1d07cc9f7c7d6c323803e174d9822d4c92c6a19bef717f51fbd"
    )
