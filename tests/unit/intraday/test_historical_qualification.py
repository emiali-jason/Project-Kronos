from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
import inspect
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday import historical_qualification
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_qualification import (
    HISTORICAL_CORPUS_ELIGIBILITY_IDENTITY,
    HISTORICAL_FACT_BUNDLE_IDENTITY,
    HISTORICAL_OUTCOME_IDENTITY,
    HISTORICAL_RECONSTRUCTION_IDENTITY,
    HISTORICAL_SUBJECT_SET_IDENTITY,
    WO06H_CONTRACT_VERSION,
    CorpusEligibilityState,
    HistoricalBindingAvailability,
    HistoricalEvidenceSource,
    HistoricalFactFamily,
    HistoricalQualificationError,
    HistoricalResearchPurpose,
    HistoricalSessionSelection,
    assess_historical_corpus_eligibility,
    create_historical_auxiliary_fact,
    create_historical_fact_bundle,
    create_historical_outcome_evidence,
    create_historical_reconstruction,
    create_historical_research_subject_set,
    create_historical_subject_binding,
    create_historical_timeframe_facts,
    historical_artifact_bytes,
    reconstruct_previous_session_facts,
    select_historical_session,
)
from kronos.intraday.historical_qualification_persistence import (
    HistoricalQualificationStore,
)
from kronos.intraday.qualification import (
    NARROW_CPR_CALCULATION_IDENTITY,
    QUALIFICATION_CONTRACT_IDENTITY,
)
from kronos.intraday.universe import (
    IntradayMarketFamily,
    IntradayUniverseError,
    IntradayUniverseFailure,
    load_intraday_universe_publication,
)
from kronos.market.schedule import (
    MarketDaySchedule,
    MarketWindow,
    TradingDayStatus,
)


IST = ZoneInfo("Asia/Kolkata")
TARGET_DATE = date(2026, 8, 17)
PREVIOUS_DATE = date(2026, 8, 14)
BOUNDARY = datetime(2026, 8, 17, 12, 0, tzinfo=IST)
PREVIOUS_CLOSE = datetime(2026, 8, 14, 15, 30, tzinfo=IST)


def _schedule(day: date) -> MarketDaySchedule:
    return MarketDaySchedule(
        exchange="NSE",
        trading_date=day,
        session_id=f"NSE:{day.isoformat()}",
        timezone="Asia/Kolkata",
        status=TradingDayStatus.TRADING,
        windows=(
            MarketWindow(
                datetime.combine(day, time(9, 15), IST),
                datetime.combine(day, time(15, 30), IST),
            ),
        ),
        source_identity="KRONOS-MARKET-CALENDAR-V1/FIXTURE",
        source_version="1",
    )


class _Calendar:
    def __init__(self) -> None:
        self.target = _schedule(TARGET_DATE)
        self.previous = _schedule(PREVIOUS_DATE)
        self.calls: list[tuple[str, date]] = []

    def schedule_for(self, exchange: str, trading_date: date):  # type: ignore[no-untyped-def]
        self.calls.append(("schedule", trading_date))
        return self.target if exchange == "NSE" and trading_date == TARGET_DATE else None

    def previous_trading_schedule(self, exchange: str, before_date: date):  # type: ignore[no-untyped-def]
        self.calls.append(("previous", before_date))
        return self.previous if exchange == "NSE" and before_date == TARGET_DATE else None


def _subject_set():  # type: ignore[no-untyped-def]
    return create_historical_research_subject_set(
        load_intraday_universe_publication()
    )


def _session(*, boundary: datetime = BOUNDARY):  # type: ignore[no-untyped-def]
    return select_historical_session(
        calendar=_Calendar(),
        exchange="NSE",
        target_trading_date=TARGET_DATE,
        observation_boundary_identity="WO-06H-GOVERNED-BOUNDARY-FIXTURE-V0",
        observation_boundary=boundary,
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    )


def _binding(label: str = "RELIANCE"):  # type: ignore[no-untyped-def]
    subject = _subject_set().lookup(label)
    return create_historical_subject_binding(
        subject=subject,
        historical_provider_fact_identity=f"EXACT-HISTORICAL-PROVIDER-FACT-{label}",
        provenance=("SYNTHETIC-EXACT-BINDING",),
    )


def _previous(session=None):  # type: ignore[no-untyped-def]
    selected = session or _session()
    return reconstruct_previous_session_facts(
        canonical_identity="RELIANCE",
        session=selected,
        previous_daily_candle_identity="GOVERNED-1D-RELIANCE-2026-08-14",
        completed_at=PREVIOUS_CLOSE,
        high=Decimal("1400"),
        low=Decimal("1370"),
        close=Decimal("1390"),
        source_integrity_identity="INTEGRITY-DAILY-RELIANCE-2026-08-14",
        provenance=("SYNTHETIC-GOVERNED-HISTORICAL-FACT",),
    )


def _timeframe_facts(
    *, late: IntradayTimeframe | None = None, completed: bool = True
):
    availability = {
        IntradayTimeframe.DAILY: PREVIOUS_CLOSE,
        IntradayTimeframe.ONE_HOUR: datetime(2026, 8, 17, 11, 15, tzinfo=IST),
        IntradayTimeframe.FIFTEEN_MINUTES: datetime(2026, 8, 17, 11, 45, tzinfo=IST),
        IntradayTimeframe.FIVE_MINUTES: datetime(2026, 8, 17, 11, 55, tzinfo=IST),
    }
    result = []
    for timeframe in IntradayTimeframe:
        available_at = availability[timeframe]
        if timeframe is late:
            available_at = BOUNDARY.replace(hour=12, minute=5)
        result.append(
            create_historical_timeframe_facts(
                timeframe=timeframe,
                completed_candle_identities=(f"COMPLETED-{timeframe.value}-FACT-001",),
                source_identities=(f"PROVIDER-HISTORICAL-{timeframe.value}-001",),
                available_at=available_at,
                completed=completed,
                provenance=("SYNTHETIC-GOVERNED-HISTORICAL-FACT",),
            )
        )
    return tuple(result)


def _bundle(*, facts=None):  # type: ignore[no-untyped-def]
    session = _session()
    previous = _previous(session)
    auxiliary = tuple(
        create_historical_auxiliary_fact(
            family=family,
            source_identities=(f"SOURCE-{family.value}",),
            available_at=BOUNDARY,
            provenance=("SYNTHETIC-GOVERNED-HISTORICAL-FACT",),
        )
        for family in (
            HistoricalFactFamily.PREVIOUS_SESSION_HLC_PDH_PDL,
            HistoricalFactFamily.CLASSIC_PIVOTS_CPR,
            HistoricalFactFamily.NARROW_CPR,
            HistoricalFactFamily.STRUCTURAL_FACTS,
            HistoricalFactFamily.VOLUME_FACTS,
            HistoricalFactFamily.DISTANCE_PATH_FACTS,
        )
    )
    return create_historical_fact_bundle(
        binding=_binding(),
        session=session,
        timeframe_facts=facts or _timeframe_facts(),
        previous_session_facts=previous,
        auxiliary_facts=auxiliary,
        historical_source_identities=(
            "KITE-HISTORICAL-READ-FIXTURE",
            "KRONOS-MARKET-CALENDAR-V1/FIXTURE",
        ),
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    )


def _reconstruction():  # type: ignore[no-untyped-def]
    return create_historical_reconstruction(
        subject_set=_subject_set(),
        reconciliation_identity="KRONOS-INTRADAY-CANONICAL-RUNTIME-RECONCILIATION-V1",
        reconciliation_version="1.0.0",
        session=_session(),
        fact_bundles=(_bundle(),),
        hypothesis_versions=((NARROW_CPR_CALCULATION_IDENTITY, "0.1.0"),),
        provenance=("SYNTHETIC-TEST-FIXTURE",),
    )


def test_contract_identities_are_explicit_and_separate_from_production() -> None:
    assert HISTORICAL_RECONSTRUCTION_IDENTITY.endswith("RECONSTRUCTION-V0")
    assert HISTORICAL_FACT_BUNDLE_IDENTITY.endswith("FACT-BUNDLE-V0")
    assert HISTORICAL_SUBJECT_SET_IDENTITY.endswith("SUBJECT-SET-V0")
    assert HISTORICAL_CORPUS_ELIGIBILITY_IDENTITY.endswith("ELIGIBILITY-V0")
    assert HISTORICAL_OUTCOME_IDENTITY.endswith("OUTCOME-V0")
    assert WO06H_CONTRACT_VERSION == "0.1.0"
    assert "NATIVE-DISCOVERY-RUNTIME" not in HISTORICAL_RECONSTRUCTION_IDENTITY


def test_production_pre_valid_from_remains_publication_stale() -> None:
    universe = load_intraday_universe_publication()
    before = universe.valid_from.replace(day=universe.valid_from.day - 1)
    with pytest.raises(IntradayUniverseError) as caught:
        universe.require_current(before)
    assert caught.value.failure is IntradayUniverseFailure.PUBLICATION_STALE


def test_historical_research_before_valid_from_is_representable() -> None:
    universe = load_intraday_universe_publication()
    reconstruction = _reconstruction()
    assert reconstruction.observation_boundary < universe.valid_from
    assert reconstruction.purpose is HistoricalResearchPurpose.QUALIFICATION_RESEARCH
    assert reconstruction.research_only is True


def test_research_does_not_mutate_or_backdate_universe_validity() -> None:
    universe = load_intraday_universe_publication()
    before = universe.valid_from
    _reconstruction()
    after = load_intraday_universe_publication().valid_from
    assert before == after


def test_research_authority_flags_are_all_fail_closed() -> None:
    value = _reconstruction()
    assert value.research_only
    assert value.not_production_discovery
    assert value.not_probable
    assert value.not_promotion
    assert value.not_execution
    for forbidden in (
        "production_candidate",
        "probable",
        "promotion",
        "risk",
        "entry_timing",
        "execution_eligibility",
        "broker_state",
        "notification_source_authority",
    ):
        assert not hasattr(value, forbidden)


def test_current_membership_is_research_subject_set_not_historical_claim() -> None:
    subject_set = _subject_set()
    assert len(subject_set.subjects) == 98
    assert subject_set.current_membership_used_for_research is True
    assert subject_set.historical_operational_membership_claim is False
    assert subject_set.provider_presence_creates_membership is False
    assert all(item.sponsor_label != "KITEONLY" for item in subject_set.subjects)


def test_subject_set_identity_is_deterministic_and_current_publication_bound() -> None:
    first = _subject_set()
    second = _subject_set()
    universe = load_intraday_universe_publication()
    assert first == second
    assert first.current_universe_identity == universe.publication_identity
    assert first.current_universe_version == universe.publication_version
    assert first.current_universe_integrity_identity == universe.integrity_identity


def test_explicit_session_and_domain008_previous_schedule_are_required() -> None:
    calendar = _Calendar()
    selected = select_historical_session(
        calendar=calendar,
        exchange="NSE",
        target_trading_date=TARGET_DATE,
        observation_boundary_identity="EXPLICIT-BOUNDARY-001",
        observation_boundary=BOUNDARY,
        provenance=("TEST",),
    )
    assert selected.target_session_identity == "NSE:2026-08-17"
    assert selected.previous_session_identity == "NSE:2026-08-14"
    assert selected.previous_trading_date == PREVIOUS_DATE
    assert ("previous", TARGET_DATE) in calendar.calls


@pytest.mark.parametrize("alias", ("LATEST", "NEWEST", "CURRENT", ""))
def test_latest_or_implicit_session_boundary_is_prohibited(alias: str) -> None:
    with pytest.raises(HistoricalQualificationError):
        select_historical_session(
            calendar=_Calendar(),
            exchange="NSE",
            target_trading_date=TARGET_DATE,
            observation_boundary_identity=alias,
            observation_boundary=BOUNDARY,
            provenance=("TEST",),
        )


def test_observation_boundary_is_identity_bound_and_multi_boundary_capable() -> None:
    first = _session()
    second_boundary = BOUNDARY.replace(hour=13)
    second = _session(boundary=second_boundary)
    assert first.observation_boundary == BOUNDARY
    assert second.observation_boundary == second_boundary
    assert first.selection_identity != second.selection_identity


@pytest.mark.parametrize("timeframe", tuple(IntradayTimeframe))
def test_all_four_completed_historical_timeframes_are_supported(
    timeframe: IntradayTimeframe,
) -> None:
    facts = next(item for item in _timeframe_facts() if item.timeframe is timeframe)
    assert facts.completed is True
    assert facts.available_at <= BOUNDARY
    assert facts.completed_candle_identities


def test_incomplete_historical_candle_is_rejected() -> None:
    with pytest.raises(HistoricalQualificationError):
        create_historical_timeframe_facts(
            timeframe=IntradayTimeframe.FIVE_MINUTES,
            completed_candle_identities=("INCOMPLETE-CANDLE",),
            source_identities=("PROVIDER-SOURCE",),
            available_at=BOUNDARY,
            completed=False,
            provenance=("TEST",),
        )


@pytest.mark.parametrize("timeframe", tuple(IntradayTimeframe))
def test_fact_known_today_but_unavailable_at_boundary_is_rejected(
    timeframe: IntradayTimeframe,
) -> None:
    with pytest.raises(HistoricalQualificationError):
        _bundle(facts=_timeframe_facts(late=timeframe))


def test_previous_session_narrow_cpr_uses_unchanged_part1_formula() -> None:
    previous = _previous()
    expected_p = (Decimal("1400") + Decimal("1370") + Decimal("1390")) / 3
    expected_bc = (Decimal("1400") + Decimal("1370")) / 2
    assert previous.narrow_cpr.pivot == expected_p
    assert previous.narrow_cpr.bc_raw == expected_bc
    assert previous.narrow_cpr.tc_raw == 2 * expected_p - expected_bc
    assert previous.narrow_cpr.narrow_cpr_kgs_v0 is False


def test_later_previous_daily_fact_fails_no_lookahead() -> None:
    with pytest.raises(HistoricalQualificationError):
        reconstruct_previous_session_facts(
            canonical_identity="RELIANCE",
            session=_session(),
            previous_daily_candle_identity="LATE-DAILY",
            completed_at=BOUNDARY.replace(hour=13),
            high=Decimal("1400"),
            low=Decimal("1370"),
            close=Decimal("1390"),
            source_integrity_identity="INTEGRITY-LATE-DAILY",
            provenance=("TEST",),
        )


def test_fact_bundle_binds_sources_session_boundary_and_canonical_identity() -> None:
    bundle = _bundle()
    assert bundle.canonical_identity == "RELIANCE"
    assert bundle.target_session_identity == "NSE:2026-08-17"
    assert bundle.observation_boundary == BOUNDARY
    assert bundle.historical_source_identities
    assert bundle.evidence_source is HistoricalEvidenceSource.HISTORICAL_QUALIFICATION_RECONSTRUCTION


def test_reconstruction_identity_is_deterministic_and_contract_bound() -> None:
    first = _reconstruction()
    second = _reconstruction()
    assert first == second
    assert first.qualification_contract_identity == QUALIFICATION_CONTRACT_IDENTITY
    assert first.hypothesis_versions == ((NARROW_CPR_CALCULATION_IDENTITY, "0.1.0"),)
    assert first.fact_bundle_identities == (_bundle().bundle_identity,)
    assert not hasattr(first, "production_discovery_run_identity")


def test_evidence_source_classes_are_distinct() -> None:
    assert len(set(HistoricalEvidenceSource)) == 3
    historical = HistoricalEvidenceSource.HISTORICAL_QUALIFICATION_RECONSTRUCTION
    assert (
        HistoricalEvidenceSource.PRODUCTION_POST_ACTIVATION_DISCOVERY_EVIDENCE
        is not historical
    )
    assert HistoricalEvidenceSource.SYNTHETIC_TEST_FIXTURE is not historical


def test_outcome_evidence_is_later_and_stored_separately() -> None:
    reconstruction = _reconstruction()
    outcome = create_historical_outcome_evidence(
        reconstruction=reconstruction,
        source_bundle_identity=reconstruction.fact_bundle_identities[0],
        available_at=BOUNDARY.replace(hour=15),
        factual_measure_identities=("MAX-UP-EXCURSION-001", "MAX-DOWN-EXCURSION-001"),
        provenance=("TEST",),
    )
    assert outcome.available_at > reconstruction.observation_boundary
    assert not hasattr(_bundle(), "outcome_identity")


def test_outcome_at_or_before_boundary_is_rejected() -> None:
    with pytest.raises(HistoricalQualificationError):
        create_historical_outcome_evidence(
            reconstruction=_reconstruction(),
            source_bundle_identity=_bundle().bundle_identity,
            available_at=BOUNDARY,
            factual_measure_identities=("OUTCOME-001",),
            provenance=("TEST",),
        )


def test_exact_identity_corpus_eligibility_requires_separate_binding() -> None:
    eligibility = assess_historical_corpus_eligibility(_reconstruction())
    assert eligibility.state is CorpusEligibilityState.ELIGIBLE_FOR_EXPLICIT_BINDING_REVIEW
    assert eligibility.explicit_binding_required is True
    assert eligibility.automatic_append is False
    assert eligibility.reconstruction_identity == _reconstruction().reconstruction_identity


@pytest.mark.parametrize("label", ("GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE"))
def test_current_mcx_member_without_historical_canonical_binding_fails_closed(
    label: str,
) -> None:
    subject = _subject_set().lookup(label)
    binding = create_historical_subject_binding(
        subject=subject,
        historical_provider_fact_identity=f"CURRENT-PROVIDER-FACT-{label}",
        historical_derivative_contract_identity=None,
        provenance=("TEST",),
    )
    assert subject.market_family is IntradayMarketFamily.MCX
    assert subject.canonical_identity is None
    assert binding.availability is HistoricalBindingAvailability.HISTORICAL_CANONICAL_BINDING_UNAVAILABLE
    assert binding.historical_derivative_contract_identity is None


@pytest.mark.parametrize("label", ("GOLDM", "SILVERM", "COPPER", "NATGAS", "CRUDE"))
def test_mcx_historical_contract_is_never_guessed_after_canonical_binding(
    label: str,
) -> None:
    current = _subject_set().lookup(label)
    subject = type(current)(
        universe_member_identity=current.universe_member_identity,
        sponsor_label=current.sponsor_label,
        canonical_identity=f"HISTORICAL-CANONICAL-{label}",
        market_family=current.market_family,
        universe_member_source_identity=current.universe_member_source_identity,
    )
    binding = create_historical_subject_binding(
        subject=subject,
        historical_provider_fact_identity=f"HISTORICAL-PROVIDER-FACT-{label}",
        historical_derivative_contract_identity=None,
        provenance=("TEST",),
    )
    assert binding.availability is HistoricalBindingAvailability.HISTORICAL_PREREQUISITE_UNAVAILABLE
    assert binding.historical_derivative_contract_identity is None


def test_natural_gas_fuzzy_alias_is_not_accepted() -> None:
    with pytest.raises(HistoricalQualificationError):
        _subject_set().lookup("NATURALGAS")


def test_missing_canonical_identity_remains_unavailable() -> None:
    subject = _subject_set().lookup("RELIANCE")
    unavailable = type(subject)(
        universe_member_identity=subject.universe_member_identity,
        sponsor_label=subject.sponsor_label,
        canonical_identity=None,
        market_family=subject.market_family,
        universe_member_source_identity=subject.universe_member_source_identity,
    )
    binding = create_historical_subject_binding(
        subject=unavailable,
        historical_provider_fact_identity=None,
        provenance=("TEST",),
    )
    assert binding.availability is HistoricalBindingAvailability.HISTORICAL_CANONICAL_BINDING_UNAVAILABLE


def test_persistence_is_explicit_idempotent_and_tamper_safe(tmp_path: Path) -> None:
    store = HistoricalQualificationStore(tmp_path)
    reconstruction = _reconstruction()
    outcome = create_historical_outcome_evidence(
        reconstruction=reconstruction,
        source_bundle_identity=reconstruction.fact_bundle_identities[0],
        available_at=BOUNDARY.replace(hour=15),
        factual_measure_identities=("OUTCOME-ROUND-TRIP",),
        provenance=("TEST",),
    )
    artifacts = (
        (_subject_set(), "subject_set_identity"),
        (_binding(), "binding_identity"),
        (_session(), "selection_identity"),
        (_previous(), "facts_identity"),
        (_timeframe_facts()[0], "fact_set_identity"),
        (_bundle(), "bundle_identity"),
        (reconstruction, "reconstruction_identity"),
        (outcome, "outcome_identity"),
        (assess_historical_corpus_eligibility(reconstruction), "eligibility_identity"),
    )
    for value, identity_name in artifacts:
        identity = getattr(value, identity_name)
        retained = store.retain(value)
        assert store.retain(value) == retained
        assert store.load(
            artifact_type=type(value).__name__,
            artifact_identity=identity,
        ) == value

    path = store.retain(reconstruction)
    assert store.retain(reconstruction) == path
    loaded = store.load_document(
        artifact_type="HistoricalQualificationReconstruction",
        artifact_identity=reconstruction.reconstruction_identity,
    )
    assert loaded["artifact_identity"] == reconstruction.reconstruction_identity
    tampered = json.loads(path.read_bytes())
    tampered["artifact"]["research_only"] = False
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(HistoricalQualificationError):
        store.load_document(
            artifact_type="HistoricalQualificationReconstruction",
            artifact_identity=reconstruction.reconstruction_identity,
        )


def test_artifacts_are_canonical_and_have_no_latest_lookup() -> None:
    value = _reconstruction()
    assert historical_artifact_bytes(value) == historical_artifact_bytes(value)
    assert not hasattr(HistoricalQualificationStore, "load_latest")
    assert not hasattr(HistoricalQualificationStore, "latest")


def test_framework_is_collection_driven_and_has_no_fixed_capacity() -> None:
    source = inspect.getsource(historical_qualification)
    assert "range(98)" not in source and "range(93)" not in source
    assert "MAX_REQUEST_COUNT =" not in source
    assert "allow_stale_universe" not in source
    assert "ignore_valid_from" not in source
    assert "force_historical_discovery" not in source
    assert "backdated_production" not in source


def test_no_external_numerical_or_broker_authority_is_imported() -> None:
    source = inspect.getsource(historical_qualification).lower()
    assert "chartink" not in source
    assert "tradingview" not in source
    assert "openai" not in source
    assert "place_order" not in source
    assert "modify_order" not in source
    assert "cancel_order" not in source
