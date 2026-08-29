from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
from kronos.intraday.completed_evidence import (
    CompletedEvidenceError,
    EvidenceSessionRole,
    IntradayAnalysisPhase,
    build_completed_evidence_selection,
    phase_aware_historical_window,
    select_intraday_analysis_phase,
)
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import (
    SemanticDirection,
    create_governed_historical_candle_payload,
)
from kronos.intraday.nifty_relative_context import (
    NIFTY_CANONICAL_IDENTITY,
    NiftyApplicability,
    NiftyRelationship,
    NiftyRelativeState,
    build_nifty_relative_context,
    classify_relative_progression,
)
from kronos.intraday.opening_semantic import (
    OpeningRelationship,
    build_opening_semantic_evidence,
)
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import (
    PROBABLES_V2_METHODOLOGY_CHECKSUM,
    PROBABLES_V2_METHODOLOGY_IDENTITY,
    PROBABLES_V2_METHODOLOGY_VERSION,
    PROBABLES_V2_PUBLICATION_IDENTITY,
    PROBABLES_V2_SUCCESSOR_METHODOLOGY_CHECKSUM,
    PROBABLES_V2_SUCCESSOR_METHODOLOGY_VERSION,
    PROBABLES_V2_SUCCESSOR_PUBLICATION_IDENTITY,
    ProbableReasonV2,
    ProbablesUnavailableMemberV2,
    ProbablesV2Error,
    build_semantic_qualification_evidence_v2,
    create_discovery_probables_evidence_v2,
    create_probables_v2_methodology,
    evaluate_probables_v2_run,
)
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.qualification import (
    PreviousCompletedDailyCandle,
    create_narrow_cpr_fact,
)
from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus


IST = ZoneInfo("Asia/Kolkata")
CURRENT_DAY = date(2026, 8, 28)
PREVIOUS_DAY = date(2026, 8, 27)
OPEN = time(10, 0)
CLOSE = time(16, 30)
SOURCE_RUN = "INTRADAY-DISCOVERY-RUN-V2-FIXTURE"
PROVENANCE = ("KRONOS-WO-06E-IMPLEMENT-TEST",)


def _schedule(day: date, exchange: str = "NSE") -> MarketDaySchedule:
    return MarketDaySchedule(
        exchange=exchange,
        trading_date=day,
        session_id=f"{exchange}:{day.isoformat()}:NONSTANDARD",
        timezone="Asia/Kolkata",
        status=TradingDayStatus.TRADING,
        windows=(MarketWindow(
            opens_at=datetime.combine(day, OPEN, IST),
            closes_at=datetime.combine(day, CLOSE, IST),
        ),),
        source_identity="KRONOS-MARKET-CALENDAR-V1/TEST",
        source_version="1",
    )


def _candle(
    subject: str,
    schedule: MarketDaySchedule,
    timeframe: IntradayTimeframe,
    start: datetime,
    *,
    opening: str = "100",
    close: str = "101",
    observation_boundary: datetime,
):
    duration = {
        IntradayTimeframe.DAILY: timedelta(hours=6, minutes=30),
        IntradayTimeframe.ONE_HOUR: timedelta(hours=1),
        IntradayTimeframe.FIFTEEN_MINUTES: timedelta(minutes=15),
        IntradayTimeframe.FIVE_MINUTES: timedelta(minutes=5),
    }[timeframe]
    op = Decimal(opening)
    cl = Decimal(close)
    return create_governed_historical_candle_payload(
        canonical_subject_identity=subject,
        exchange=schedule.exchange,
        market_identity=schedule.exchange,
        market_session_identity=schedule.session_id,
        timeframe=timeframe,
        candle_start=start,
        candle_end=start + duration,
        open=op,
        high=max(op, cl) + Decimal("1"),
        low=min(op, cl) - Decimal("1"),
        close=cl,
        volume=100,
        observation_boundary=observation_boundary,
        provider_source_identity="DOMAIN-006:KITE:HISTORICAL",
        source_operation_identity="WO-06E-IMPLEMENT-TEST-OPERATION",
        provenance=PROVENANCE,
    )


def _narrow(subject: str, boundary: datetime, value: bool = True):
    high = Decimal("100" if value else "105")
    return create_narrow_cpr_fact(PreviousCompletedDailyCandle(
        canonical_subject_identity=subject,
        previous_session_identity=_schedule(PREVIOUS_DAY).session_id,
        observation_session_identity=_schedule(CURRENT_DAY).session_id,
        source_daily_candle_identity=f"GOVERNED-1D:{subject}:PREVIOUS",
        completed_at=datetime.combine(PREVIOUS_DAY, CLOSE, IST),
        observation_boundary=boundary,
        high=high,
        low=Decimal("90"),
        close=Decimal("95"),
        completed=True,
        source_integrity_identity=f"INTEGRITY-DAILY:{subject}:PREVIOUS",
        provenance=PROVENANCE,
    ))


def _opening_inputs(
    subject: str = "NSE-EQ-RELIANCE",
    *,
    subject_exchange: str = "NSE",
    nifty_close: str = "101",
    prior_supporting: bool = True,
    narrow_qualified: bool = True,
    methodology=None,
):
    current = _schedule(CURRENT_DAY, subject_exchange)
    previous = _schedule(PREVIOUS_DAY, subject_exchange)
    boundary = datetime.combine(CURRENT_DAY, time(10, 15), IST)
    prior_daily = (_candle(
        subject, previous, IntradayTimeframe.DAILY,
        datetime.combine(PREVIOUS_DAY, OPEN, IST),
        observation_boundary=boundary,
    ),)
    prior_values = (
        (("100", "101"), ("101", "102"))
        if prior_supporting
        else (("102", "101"), ("100", "99"))
    )
    prior_hours = tuple(
        _candle(
            subject, previous, IntradayTimeframe.ONE_HOUR,
            datetime.combine(PREVIOUS_DAY, start, IST),
            opening=prior_values[index][0],
            close=prior_values[index][1],
            observation_boundary=boundary,
        )
        for index, start in enumerate((time(14, 0), time(15, 0)))
    )
    opening = (_candle(
        subject, current, IntradayTimeframe.FIFTEEN_MINUTES,
        datetime.combine(CURRENT_DAY, OPEN, IST),
        opening="100", close="103", observation_boundary=boundary,
    ),)
    five = tuple(
        _candle(
            subject, current, IntradayTimeframe.FIVE_MINUTES,
            datetime.combine(CURRENT_DAY, time(10, index * 5), IST),
            opening=str(100 + index), close=str(101 + index),
            observation_boundary=boundary,
        )
        for index in range(3)
    )
    selection = build_completed_evidence_selection(
        canonical_subject_identity=subject,
        analysis_boundary=boundary,
        current_schedule=current,
        previous_schedule=previous,
        previous_daily=prior_daily,
        previous_one_hour=prior_hours,
        current_one_hour=(),
        current_fifteen_minute=opening,
        current_five_minute=five,
        provenance=PROVENANCE,
    )
    benchmark = _candle(
        NIFTY_CANONICAL_IDENTITY, current, IntradayTimeframe.FIFTEEN_MINUTES,
        datetime.combine(CURRENT_DAY, OPEN, IST),
        opening="100", close=nifty_close, observation_boundary=boundary,
    )
    nifty = build_nifty_relative_context(
        canonical_subject_identity=subject,
        subject_exchange=subject_exchange,
        opening_direction="LONG",
        analysis_boundary=boundary,
        subject_candle=opening[0],
        benchmark_candle=benchmark,
        subject_session_open=Decimal("100"),
        benchmark_session_open=Decimal("100"),
        provenance=PROVENANCE,
    )
    narrow = _narrow(subject, boundary, narrow_qualified)
    opening_semantic = build_opening_semantic_evidence(
        selection=selection,
        narrow_cpr_fact=narrow,
        nifty_relative_evidence=nifty,
        participation_state="AVAILABLE_SUPPORTING_NON_BLOCKING",
        provenance=PROVENANCE,
    )
    semantic = build_semantic_qualification_evidence_v2(
        selection=selection,
        narrow_cpr_fact=narrow,
        opening_semantic=opening_semantic,
        nifty_relative=nifty,
        reference_fact_identities=(("PDH_PDL", "FACT-PDH-PDL"),),
        participation_state="AVAILABLE_SUPPORTING_NON_BLOCKING",
        provenance=PROVENANCE,
    )
    mapping = create_discovery_probables_evidence_v2(
        universe_member_identity=f"INTRADAY-UNIVERSE-MEMBER:{subject}",
        source_discovery_run_identity=SOURCE_RUN,
        source_discovery_member_identity=f"INTRADAY-DISCOVERY-RESULT:{subject}",
        market_session_identity=current.session_id,
        completed_evidence=selection,
        semantic_evidence=semantic,
        opening_semantic=opening_semantic,
        nifty_relative=nifty,
        provenance=PROVENANCE,
        methodology=methodology,
    )
    return selection, nifty, opening_semantic, semantic, mapping


def _run(mapping):
    return evaluate_probables_v2_run(
        source_discovery_run_identity=SOURCE_RUN,
        universe_identity="KRONOS-INTRADAY-NATIVE-UNIVERSE-V1",
        universe_version="1.0.0",
        reconciliation_identity="KRONOS-INTRADAY-RECONCILIATION-V1",
        reconciliation_version="1.0.0",
        market_session_identity=mapping.market_session_identity,
        analysis_boundary=mapping.analysis_boundary,
        member_evidence=(mapping,),
        unavailable_members=(),
        provenance=PROVENANCE,
        methodology=(
            create_probables_v2_methodology(legacy=True)
            if mapping.methodology_version == PROBABLES_V2_METHODOLOGY_VERSION
            else None
        ),
    )


def _later_mapping(
    completed_fifteen: int,
    completed_hours: int,
    *,
    boundary: datetime,
):
    subject = "NSE-EQ-RELIANCE"
    current = _schedule(CURRENT_DAY)
    previous = _schedule(PREVIOUS_DAY)
    prior_daily = (_candle(
        subject, previous, IntradayTimeframe.DAILY,
        datetime.combine(PREVIOUS_DAY, OPEN, IST),
        observation_boundary=boundary,
    ),)
    prior_hours = tuple(
        _candle(
            subject, previous, IntradayTimeframe.ONE_HOUR,
            datetime.combine(PREVIOUS_DAY, start, IST),
            opening=str(100 + index), close=str(101 + index),
            observation_boundary=boundary,
        )
        for index, start in enumerate((time(14, 0), time(15, 0)))
    )
    current_hours = tuple(
        _candle(
            subject, current, IntradayTimeframe.ONE_HOUR,
            datetime.combine(CURRENT_DAY, time(10 + index, 0), IST),
            opening=str(102 + index * 2), close=str(104 + index * 2),
            observation_boundary=boundary,
        )
        for index in range(completed_hours)
    )
    fifteen = tuple(
        _candle(
            subject, current, IntradayTimeframe.FIFTEEN_MINUTES,
            datetime.combine(CURRENT_DAY, OPEN, IST) + timedelta(minutes=15 * index),
            opening=str(100 + index), close=str(102 + index),
            observation_boundary=boundary,
        )
        for index in range(completed_fifteen)
    )
    five = tuple(
        _candle(
            subject, current, IntradayTimeframe.FIVE_MINUTES,
            datetime.combine(CURRENT_DAY, OPEN, IST) + timedelta(minutes=5 * index),
            opening=str(100 + index), close=str(101 + index),
            observation_boundary=boundary,
        )
        for index in range(completed_fifteen * 3)
    )
    selection = build_completed_evidence_selection(
        canonical_subject_identity=subject,
        analysis_boundary=boundary,
        current_schedule=current,
        previous_schedule=previous,
        previous_daily=prior_daily,
        previous_one_hour=prior_hours,
        current_one_hour=current_hours,
        current_fifteen_minute=fifteen,
        current_five_minute=five,
        provenance=PROVENANCE,
    )
    narrow = _narrow(subject, boundary)
    semantic = build_semantic_qualification_evidence_v2(
        selection=selection,
        narrow_cpr_fact=narrow,
        participation_state="AVAILABLE_SUPPORTING_NON_BLOCKING",
        provenance=PROVENANCE,
    )
    return create_discovery_probables_evidence_v2(
        universe_member_identity=f"INTRADAY-UNIVERSE-MEMBER:{subject}",
        source_discovery_run_identity=SOURCE_RUN,
        source_discovery_member_identity=f"INTRADAY-DISCOVERY-RESULT:{subject}",
        market_session_identity=current.session_id,
        completed_evidence=selection,
        semantic_evidence=semantic,
        opening_semantic=None,
        nifty_relative=None,
        provenance=PROVENANCE,
    )


def test_frozen_methodology_and_completion_driven_phase_family() -> None:
    methodology = create_probables_v2_methodology()
    assert methodology.methodology_identity == PROBABLES_V2_METHODOLOGY_IDENTITY
    assert methodology.methodology_version == PROBABLES_V2_SUCCESSOR_METHODOLOGY_VERSION
    assert methodology.publication_identity == PROBABLES_V2_SUCCESSOR_PUBLICATION_IDENTITY
    assert methodology.payload_checksum == PROBABLES_V2_SUCCESSOR_METHODOLOGY_CHECKSUM
    legacy = create_probables_v2_methodology(legacy=True)
    assert legacy.methodology_version == PROBABLES_V2_METHODOLOGY_VERSION
    assert legacy.publication_identity == PROBABLES_V2_PUBLICATION_IDENTITY
    assert legacy.payload_checksum == PROBABLES_V2_METHODOLOGY_CHECKSUM
    assert select_intraday_analysis_phase(current_completed_15m_count=0, current_completed_1h_count=0) is None
    assert select_intraday_analysis_phase(current_completed_15m_count=1, current_completed_1h_count=0) is IntradayAnalysisPhase.OPENING
    assert select_intraday_analysis_phase(current_completed_15m_count=2, current_completed_1h_count=0) is IntradayAnalysisPhase.STRUCTURE
    assert select_intraday_analysis_phase(current_completed_15m_count=4, current_completed_1h_count=1) is IntradayAnalysisPhase.FIRST_CURRENT_SESSION_1H
    assert select_intraday_analysis_phase(current_completed_15m_count=8, current_completed_1h_count=2) is IntradayAnalysisPhase.CURRENT_SESSION_ESTABLISHED


def test_opening_selection_uses_nonstandard_schedule_and_prior_session() -> None:
    selection, _, _, _, _ = _opening_inputs()
    assert selection.phase is IntradayAnalysisPhase.OPENING
    assert selection.current_market_session_identity.endswith(":NONSTANDARD")
    assert len(selection.candles(IntradayTimeframe.ONE_HOUR, EvidenceSessionRole.PRIOR_SESSION_1H_CONTEXT)) == 2
    assert len(selection.candles(IntradayTimeframe.FIVE_MINUTES, EvidenceSessionRole.CURRENT_SESSION_5M)) == 3
    start, end = phase_aware_historical_window(
        current_schedule=_schedule(CURRENT_DAY),
        previous_schedule=_schedule(PREVIOUS_DAY),
        observation_boundary=selection.analysis_boundary,
    )
    assert start == datetime.combine(PREVIOUS_DAY, OPEN, IST)
    assert end == selection.analysis_boundary


def test_opening_semantics_nifty_arithmetic_and_admission() -> None:
    selection, nifty, opening, semantic, mapping = _opening_inputs()
    assert nifty.fact.subject_return_pct == Decimal("3.00")
    assert nifty.fact.benchmark_return_pct == Decimal("1.00")
    assert nifty.fact.relative_return_pct == Decimal("2.00")
    assert nifty.fact.state is NiftyRelativeState.OUTPERFORMING
    assert nifty.relationship is NiftyRelationship.SUPPORTING
    assert opening.fact.opening_direction is SemanticDirection.LONG
    assert opening.fact.five_minute_progression is SemanticDirection.LONG
    assert opening.combined_relationship is OpeningRelationship.SUPPORTING
    assert semantic.completed_evidence_selection_identity == selection.selection_identity
    run = _run(mapping)
    assert run.results[0].state is ProbableState.LONG_PROBABLE
    assert run.results[0].direction is SemanticDirection.LONG
    assert run.results[0].reasons == (ProbableReasonV2.V2_CONDITIONS_SATISFIED,)


def test_conflicting_nifty_blocks_without_flipping_direction() -> None:
    *_, mapping = _opening_inputs(nifty_close="105")
    run = _run(mapping)
    assert run.results[0].state is ProbableState.NOT_ADMITTED
    assert run.results[0].direction is SemanticDirection.LONG
    assert run.results[0].reasons == (ProbableReasonV2.NIFTY_CONTEXT_CONFLICTING_NO_DIRECTION_FLIP,)


def test_prior_hour_conflict_blocks_without_flipping_direction() -> None:
    *_, mapping = _opening_inputs(prior_supporting=False)
    result = _run(mapping).results[0]
    assert result.state is ProbableState.NOT_ADMITTED
    assert result.direction is SemanticDirection.LONG
    assert result.reasons == (
        ProbableReasonV2.PRIOR_1H_CONFLICTING_NO_DIRECTION_FLIP,
    )


def test_narrow_cpr_failure_preserves_factual_opening_direction() -> None:
    *_, mapping = _opening_inputs(narrow_qualified=False)
    result = _run(mapping).results[0]
    assert result.state is ProbableState.NOT_ADMITTED
    assert result.direction is SemanticDirection.LONG
    assert result.reasons == (ProbableReasonV2.NARROW_CPR_NOT_SATISFIED,)


@pytest.mark.parametrize(
    ("fifteen", "hours", "boundary", "expected"),
    (
        (2, 0, datetime(2026, 8, 28, 10, 30, tzinfo=IST), IntradayAnalysisPhase.STRUCTURE),
        (4, 1, datetime(2026, 8, 28, 11, 0, tzinfo=IST), IntradayAnalysisPhase.FIRST_CURRENT_SESSION_1H),
        (8, 2, datetime(2026, 8, 28, 12, 0, tzinfo=IST), IntradayAnalysisPhase.CURRENT_SESSION_ESTABLISHED),
    ),
)
def test_later_phase_transition_and_admission(fifteen, hours, boundary, expected) -> None:
    mapping = _later_mapping(fifteen, hours, boundary=boundary)
    assert mapping.phase is expected
    assert mapping.nifty_relative is None
    assert mapping.semantic_evidence.nifty_relative_evidence_identity is None
    run = _run(mapping)
    assert run.results[0].state is ProbableState.LONG_PROBABLE
    assert run.results[0].direction is SemanticDirection.LONG


def test_multi_boundary_assessments_have_independent_immutable_identities(tmp_path: Path) -> None:
    *_, opening = _opening_inputs()
    structure = _later_mapping(2, 0, boundary=datetime(2026, 8, 28, 10, 30, tzinfo=IST))
    first_hour = _later_mapping(4, 1, boundary=datetime(2026, 8, 28, 11, 0, tzinfo=IST))
    established = _later_mapping(8, 2, boundary=datetime(2026, 8, 28, 12, 0, tzinfo=IST))
    mappings = (opening, structure, first_hour, established)
    identities = set()
    store = ProbablesV2Store(tmp_path.resolve())
    for mapping in mappings:
        run = _run(mapping)
        store.retain_complete(run=run, mappings=(mapping,))
        identities.add(run.run_identity)
    assert len(identities) == 4
    for identity in identities:
        assert store.load_run(identity).run_identity == identity


def test_historical_v2_2_0_run_reloads_under_original_publication(tmp_path: Path) -> None:
    legacy = create_probables_v2_methodology(legacy=True)
    *_, mapping = _opening_inputs(methodology=legacy)
    run = _run(mapping)
    store = ProbablesV2Store(tmp_path.resolve())
    store.retain_complete(run=run, mappings=(mapping,))
    restored = store.load_run(run.run_identity)
    assert restored.methodology == legacy
    assert restored.methodology.methodology_version == "2.0.0"
    assert restored.methodology.payload_checksum == PROBABLES_V2_METHODOLOGY_CHECKSUM
    application = IntradayProbablesV2Application(store=store)
    assert application.snapshot().run == run


def test_nifty_not_applicable_unavailable_and_progression_contracts() -> None:
    selection, _, _, _, _ = _opening_inputs()
    mcx = build_nifty_relative_context(
        canonical_subject_identity="MCX-FAMILY-GOLDM",
        subject_exchange="MCX",
        opening_direction="LONG",
        analysis_boundary=selection.analysis_boundary,
        subject_candle=None,
        benchmark_candle=None,
        subject_session_open=None,
        benchmark_session_open=None,
        provenance=PROVENANCE,
    )
    assert mcx.fact.applicability is NiftyApplicability.NOT_APPLICABLE
    assert mcx.relationship is NiftyRelationship.NOT_APPLICABLE
    unavailable = build_nifty_relative_context(
        canonical_subject_identity="NSE-EQ-RELIANCE",
        subject_exchange="NSE",
        opening_direction="LONG",
        analysis_boundary=selection.analysis_boundary,
        subject_candle=None,
        benchmark_candle=None,
        subject_session_open=None,
        benchmark_session_open=None,
        provenance=PROVENANCE,
    )
    assert unavailable.relationship is NiftyRelationship.UNAVAILABLE
    assert classify_relative_progression((Decimal("1"), Decimal("2"), Decimal("3"))).value == "IMPROVING"
    assert classify_relative_progression((Decimal("3"), Decimal("2"), Decimal("1"))).value == "DETERIORATING"
    assert classify_relative_progression((Decimal("1"), Decimal("1"), Decimal("1"))).value == "FLAT"


@pytest.mark.parametrize("family", ("GOLDM", "SILVERM", "COPPER", "CRUDE"))
def test_mcx_commissioned_subject_is_evaluated_and_retains_exact_lineage(
    tmp_path: Path, family: str,
) -> None:
    *_, mapping = _opening_inputs(
        subject=f"MCX-SUBJECT-{family}",
        subject_exchange="MCX",
    )

    run = _run(mapping)
    result = run.results[0]

    assert result.state is ProbableState.LONG_PROBABLE
    assert result.reasons == (ProbableReasonV2.V2_CONDITIONS_SATISFIED,)
    assert result.source_mapping_identity == mapping.mapping_identity
    assert result.nifty_applicability is NiftyApplicability.NOT_APPLICABLE
    assert result.nifty_relationship is NiftyRelationship.NOT_APPLICABLE
    assert result.direction is SemanticDirection.LONG
    assert any(item == "MCX_COMMISSIONING_STATE:COMMISSIONED" for item in result.provenance)

    store = ProbablesV2Store(tmp_path.resolve())
    store.retain_complete(run=run, mappings=(mapping,))
    assert store.load_current_run() == run
    assert store.load_mapping(mapping.mapping_identity) == mapping


def test_mcx_natgas_remains_held_and_unavailable() -> None:
    *_, mapping = _opening_inputs(
        subject="MCX-SUBJECT-NATGAS",
        subject_exchange="MCX",
    )
    result = _run(mapping).results[0]
    assert result.state is ProbableState.UNAVAILABLE
    assert result.reasons == (
        ProbableReasonV2.MCX_V2_EMPIRICAL_COMMISSIONING_REQUIRED,
    )
    assert result.nifty_applicability is NiftyApplicability.NOT_APPLICABLE
    assert result.nifty_relationship is NiftyRelationship.NOT_APPLICABLE


def test_unknown_mcx_subject_fails_closed() -> None:
    *_, mapping = _opening_inputs(
        subject="MCX-SUBJECT-UNKNOWN",
        subject_exchange="MCX",
    )
    with pytest.raises(ValueError, match="MCX_SUBJECT_COMMISSIONING_UNKNOWN"):
        _run(mapping)


def test_pre_mapping_unavailable_retains_no_mapping_lineage(tmp_path: Path) -> None:
    boundary = datetime.combine(CURRENT_DAY, time(10, 15), IST)
    unavailable = ProbablesUnavailableMemberV2(
        universe_member_identity="INTRADAY-UNIVERSE-MEMBER:NSE-EQ-UNAVAILABLE",
        canonical_subject_identity="NSE-EQ-UNAVAILABLE",
        market_session_identity=_schedule(CURRENT_DAY).session_id,
        analysis_boundary=boundary,
        reason=ProbableReasonV2.MANDATORY_EVIDENCE_UNAVAILABLE,
        source_identity=SOURCE_RUN,
        provenance=PROVENANCE,
    )
    run = evaluate_probables_v2_run(
        source_discovery_run_identity=SOURCE_RUN,
        universe_identity="KRONOS-INTRADAY-NATIVE-UNIVERSE-V1",
        universe_version="1.0.0",
        reconciliation_identity="KRONOS-INTRADAY-RECONCILIATION-V1",
        reconciliation_version="1.0.0",
        market_session_identity=_schedule(CURRENT_DAY).session_id,
        analysis_boundary=boundary,
        member_evidence=(),
        unavailable_members=(unavailable,),
        provenance=PROVENANCE,
    )
    result = run.results[0]

    assert result.state is ProbableState.UNAVAILABLE
    assert result.source_mapping_identity is None
    assert result.completed_evidence_selection_identity is None
    assert result.semantic_evidence_identity is None

    store = ProbablesV2Store(tmp_path.resolve())
    store.retain_complete(run=run, mappings=())
    assert store.load_current_run() == run


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("canonical_subject_identity", "MCX-SUBJECT-WRONG"),
        ("source_discovery_run_identity", "INTRADAY-DISCOVERY-RUN-WRONG"),
        ("source_discovery_member_identity", "INTRADAY-DISCOVERY-RESULT-WRONG"),
        ("analysis_boundary", datetime(2026, 8, 28, 10, 16, tzinfo=IST)),
        ("methodology_identity", "KRONOS-INTRADAY-PROBABLES-METHODOLOGY-WRONG"),
        ("mapping_identity", "INTRADAY-DISCOVERY-PROBABLES-V2-MAPPING-TAMPERED"),
        ("integrity_identity", "INTEGRITY-INTRADAY-DISCOVERY-PROBABLES-V2-MAPPING-TAMPERED"),
    ),
)
def test_mapped_unavailable_rejects_wrong_or_tampered_mapping(
    field: str,
    value: object,
) -> None:
    *_, mapping = _opening_inputs(
        subject="MCX-SUBJECT-GOLDM",
        subject_exchange="MCX",
    )

    with pytest.raises(ProbablesV2Error, match="MAPPING_INVALID"):
        replace(mapping, **{field: value})


def test_wrong_or_forming_evidence_fails_closed() -> None:
    selection, _, _, _, _ = _opening_inputs()
    candle = selection.selected_candles[0].candle
    with pytest.raises(ValueError):
        replace(candle, completion_state="FORMING")
    with pytest.raises(CompletedEvidenceError):
        build_completed_evidence_selection(
            canonical_subject_identity="NSE-EQ-WRONG",
            analysis_boundary=selection.analysis_boundary,
            current_schedule=_schedule(CURRENT_DAY),
            previous_schedule=_schedule(PREVIOUS_DAY),
            previous_daily=(candle,),
            previous_one_hour=(),
            current_one_hour=(),
            current_fifteen_minute=(),
            current_five_minute=(),
            provenance=PROVENANCE,
        )


def test_v2_persistence_restart_and_tamper_fail_closed(tmp_path: Path) -> None:
    *_, mapping = _opening_inputs()
    store = ProbablesV2Store(tmp_path.resolve())
    application = IntradayProbablesV2Application(store=store)
    run = application.refresh_analysis(
        source_discovery_run_identity=SOURCE_RUN,
        universe_identity="KRONOS-INTRADAY-NATIVE-UNIVERSE-V1",
        universe_version="1.0.0",
        reconciliation_identity="KRONOS-INTRADAY-RECONCILIATION-V1",
        reconciliation_version="1.0.0",
        market_session_identity=_schedule(CURRENT_DAY).session_id,
        analysis_boundary=mapping.analysis_boundary,
        member_evidence=(mapping,),
        unavailable_members=(),
        provenance=PROVENANCE,
    )
    restarted = IntradayProbablesV2Application(store=ProbablesV2Store(tmp_path.resolve()))
    assert restarted.snapshot().run == run
    store.retain_complete(run=run, mappings=(mapping,))
    path = store.root / "probables-v2" / "runs" / f"{run.run_identity}.json"
    path.write_bytes(path.read_bytes().replace(b"LONG_PROBABLE", b"SHORT_PROBABLE"))
    with pytest.raises(Exception, match="INTEGRITY|INVALID"):
        ProbablesV2Store(tmp_path.resolve()).load_current_run()


def test_v2_restart_fails_closed_when_bound_selection_is_missing(
    tmp_path: Path,
) -> None:
    *_, mapping = _opening_inputs()
    store = ProbablesV2Store(tmp_path.resolve())
    run = _run(mapping)
    store.retain_complete(run=run, mappings=(mapping,))
    selection_path = (
        store.root
        / "completed-evidence-v1"
        / "selections"
        / f"{mapping.completed_evidence.selection_identity}.json"
    )
    selection_path.unlink()
    with pytest.raises(Exception, match="UNAVAILABLE"):
        IntradayProbablesV2Application(store=ProbablesV2Store(tmp_path.resolve()))


def test_v1_store_namespace_is_untouched(tmp_path: Path) -> None:
    *_, mapping = _opening_inputs()
    store = ProbablesV2Store(tmp_path.resolve())
    store.retain_complete(run=_run(mapping), mappings=(mapping,))
    assert (tmp_path / "probables-v2").is_dir()
    assert not (tmp_path / "probables-v1").exists()
