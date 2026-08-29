from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.mcx_continuous_research import (
    ContinuousResearchCandle,
    ContinuousSeriesQuality,
    ContinuousSubjectQualification,
    ContinuousSubjectSeries,
    MCX_CONTINUOUS_PRIOR_1H_POLICY,
    MCX_CONTINUOUS_REFERENCE_POLICY,
    MCX_CONTINUOUS_RESEARCH_AUTHORITY,
    MCX_CONTINUOUS_RESEARCH_IDENTITY,
    MCX_CONTINUOUS_RESEARCH_VERSION,
    McxContinuousResearchArtifact,
    McxContinuousResearchError,
    SubjectQualificationOutcome,
    _build_subject_series,
    _evaluate_frozen_v2,
    _identity,
    governed_native_continuous_capability,
    mcx_continuous_research_bytes,
    parse_mcx_continuous_research,
)
from kronos.intraday.mcx_continuous_research_persistence import (
    McxContinuousResearchStore,
)
from kronos.intraday.mcx_historical_research import McxHistoricalResearchState
from kronos.intraday.opening_semantic import OpeningRelationship
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import (
    PROBABLES_V2_METHODOLOGY_CHECKSUM,
    ProbableReasonV2,
)
from kronos.provider.adapters.kite.client import _KiteCandidateClientHandle


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def test_governed_provider_contract_exposes_no_native_continuous_timeframe() -> None:
    assert governed_native_continuous_capability() == {
        "1D": "NOT_SUPPORTED",
        "1H": "NOT_SUPPORTED",
        "15M": "NOT_SUPPORTED",
        "5M": "NOT_SUPPORTED",
    }
    source = inspect.getsource(_KiteCandidateClientHandle.historical_candles)
    assert "continuous=False" in source
    assert "oi=False" in source


def test_constructed_series_excludes_successor_candles_attributed_before_roll() -> None:
    old = SimpleNamespace(canonical_contract_identity="MCX-FUT-NATGAS-2026-08-26")
    new = SimpleNamespace(canonical_contract_identity="MCX-FUT-NATGAS-2026-09-25")
    sessions = (
        SimpleNamespace(
            analytical_subject="NATGAS",
            canonical_subject_identity="MCX-SUBJECT-NATGAS",
            trading_date=date(2026, 8, 26),
            binding=old,
            state=McxHistoricalResearchState.REJECTED,
            candles=(),
        ),
        SimpleNamespace(
            analytical_subject="NATGAS",
            canonical_subject_identity="MCX-SUBJECT-NATGAS",
            trading_date=date(2026, 8, 27),
            binding=new,
            state=McxHistoricalResearchState.COMPLETE,
            candles=(
                _source_candle(date(2026, 8, 26), new.canonical_contract_identity, 1),
                _source_candle(date(2026, 8, 27), new.canonical_contract_identity, 2),
            ),
        ),
    )
    corpus = SimpleNamespace(sessions=sessions)
    series = _build_subject_series(corpus, "NATGAS")

    assert _build_subject_series(corpus, "NATGAS") == series
    assert series.quality is ContinuousSeriesQuality.PARTIAL
    assert series.contract_attribution_exclusion_count == 1
    assert tuple(item.trading_date for item in series.candles) == (date(2026, 8, 27),)
    assert len(series.roll_boundaries) == 1
    assert series.roll_boundaries[0].old_contract_close is None
    assert series.roll_boundaries[0].reference_treatment == MCX_CONTINUOUS_REFERENCE_POLICY
    assert series.roll_boundaries[0].prior_one_hour_treatment == MCX_CONTINUOUS_PRIOR_1H_POLICY
    assert series.contract_splice_violation_count == 0


def test_frozen_opening_research_evaluation_has_no_benchmark_predicate() -> None:
    semantic = SimpleNamespace(narrow_cpr_qualified=True)
    opening = SimpleNamespace(
        fact=SimpleNamespace(
            opening_direction=SemanticDirection.LONG,
            prior_one_hour_relationship=OpeningRelationship.SUPPORTING,
            five_minute_relationship=OpeningRelationship.SUPPORTING,
        ),
        combined_relationship=OpeningRelationship.SUPPORTING,
    )
    state, direction, reasons = _evaluate_frozen_v2(
        phase=IntradayAnalysisPhase.OPENING,
        semantic=semantic,
        opening=opening,
    )
    assert state is ProbableState.LONG_PROBABLE
    assert direction is SemanticDirection.LONG
    assert reasons == (ProbableReasonV2.V2_CONDITIONS_SATISFIED,)


def test_artifact_is_byte_deterministic_explicitly_reloadable_and_tamper_safe(
    tmp_path: Path,
) -> None:
    artifact = _artifact()
    encoded = mcx_continuous_research_bytes(artifact)
    assert parse_mcx_continuous_research(encoded) == artifact

    store = McxContinuousResearchStore(tmp_path.resolve())
    path = store.retain(artifact)
    assert store.load(artifact_identity=artifact.artifact_identity) == artifact
    assert path.stat().st_mode & 0o777 == 0o600

    tampered = encoded.replace(b'"provider_request_count":0', b'"provider_request_count":1')
    with pytest.raises(McxContinuousResearchError):
        parse_mcx_continuous_research(tampered)


def _source_candle(
    trading_date: date,
    contract: str,
    ordinal: int,
) -> SimpleNamespace:
    start = datetime.combine(trading_date, datetime.min.time(), tzinfo=UTC) + timedelta(hours=ordinal)
    return SimpleNamespace(
        canonical_subject_identity="MCX-SUBJECT-NATGAS",
        canonical_contract_identity=contract,
        timeframe=IntradayTimeframe.FIVE_MINUTES,
        trading_date=trading_date,
        candle_start=start,
        candle_end=start + timedelta(minutes=5),
        session_identity=f"MCX:{trading_date.isoformat()}",
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal("101"),
        volume=10,
        candle_identity=f"SOURCE-{trading_date.isoformat()}-{ordinal}",
        source_identity="DOMAIN-006:KITE:HISTORICAL:5minute",
    )


def _artifact() -> McxContinuousResearchArtifact:
    start = NOW
    candle_values = {
        "canonical_subject_identity": "MCX-SUBJECT-GOLDM",
        "canonical_contract_identity": "MCX-FUT-GOLDM-2026-09-04",
        "timeframe": IntradayTimeframe.FIVE_MINUTES,
        "trading_date": date(2026, 8, 28),
        "market_session_identity": "MCX:2026-08-28",
        "candle_start": start,
        "candle_end": start + timedelta(minutes=5),
        "open": Decimal("100"),
        "high": Decimal("102"),
        "low": Decimal("99"),
        "close": Decimal("101"),
        "volume": 10,
        "source_candle_identities": ("SOURCE-CANDLE-1",),
        "source_provider_identity": "DOMAIN-006:KITE:HISTORICAL:5minute",
    }
    candle = ContinuousResearchCandle(
        candle_identity=_identity("INTRADAY-MCX-CONTINUOUS-CANDLE-", candle_values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-MCX-CONTINUOUS-CANDLE-", candle_values
        ),
        **candle_values,
    )
    series_values = {
        "analytical_subject": "GOLDM",
        "canonical_subject_identity": "MCX-SUBJECT-GOLDM",
        "governed_contract_identities": ("MCX-FUT-GOLDM-2026-09-04",),
        "represented_contract_identities": ("MCX-FUT-GOLDM-2026-09-04",),
        "candles": (candle,),
        "roll_boundaries": (),
        "missing_trading_dates": (),
        "contract_attribution_exclusion_count": 0,
        "source_duplicate_observation_count": 0,
        "duplicate_count": 0,
        "overlap_count": 0,
        "contract_splice_violation_count": 0,
        "quality": ContinuousSeriesQuality.COMPLETE,
        "limitations": (
            "NON_BACK_ADJUSTED",
            MCX_CONTINUOUS_REFERENCE_POLICY,
            MCX_CONTINUOUS_PRIOR_1H_POLICY,
        ),
    }
    series = ContinuousSubjectSeries(
        series_identity=_identity("INTRADAY-MCX-CONTINUOUS-SERIES-", series_values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-MCX-CONTINUOUS-SERIES-", series_values
        ),
        **series_values,
    )
    qualification_values = {
        "analytical_subject": "GOLDM",
        "canonical_subject_identity": "MCX-SUBJECT-GOLDM",
        "complete_session_count": 5,
        "phase_assessment_count": 20,
        "result_accounting": (("NOT_ADMITTED", 20),),
        "conflict_assessment_count": 0,
        "state_transition_count": 0,
        "outcome": SubjectQualificationOutcome.PASS,
        "commissioning_recommended": True,
        "reasons": ("FIVE_COMPLETE_SESSIONS_AND_FOUR_PHASE_REPLAY_PASS",),
    }
    qualification = ContinuousSubjectQualification(
        qualification_identity=_identity(
            "INTRADAY-MCX-CONTINUOUS-QUALIFICATION-", qualification_values
        ),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-MCX-CONTINUOUS-QUALIFICATION-", qualification_values
        ),
        **qualification_values,
    )
    values = {
        "created_at": NOW,
        "source_corpus_identity": "SOURCE-CORPUS",
        "source_corpus_integrity_identity": "SOURCE-CORPUS-INTEGRITY",
        "native_provider_capability": (
            ("1D", "NOT_SUPPORTED"),
            ("1H", "NOT_SUPPORTED"),
            ("15M", "NOT_SUPPORTED"),
            ("5M", "NOT_SUPPORTED"),
        ),
        "construction_method": "KRONOS_CONSTRUCTED_EXACT_CONTRACT_SEGMENTS",
        "back_adjustment_policy": "NON_BACK_ADJUSTED",
        "roll_gap_policy": "CONTRACT_ROLL_BOUNDARY_NOT_MARKET_GAP",
        "reference_policy": MCX_CONTINUOUS_REFERENCE_POLICY,
        "prior_one_hour_policy": MCX_CONTINUOUS_PRIOR_1H_POLICY,
        "benchmark_applicability": "NOT_APPLICABLE",
        "series": (series,),
        "assessments": (),
        "qualifications": (qualification,),
        "provider_request_count": 0,
        "authority": MCX_CONTINUOUS_RESEARCH_AUTHORITY,
        "limitations": (
            "Provider-native continuous history is not exposed by the governed KRONOS request contract.",
        ),
        "contract_identity": MCX_CONTINUOUS_RESEARCH_IDENTITY,
        "contract_version": MCX_CONTINUOUS_RESEARCH_VERSION,
    }
    return McxContinuousResearchArtifact(
        artifact_identity=_identity("INTRADAY-MCX-CONTINUOUS-RESEARCH-", values),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-MCX-CONTINUOUS-RESEARCH-", values
        ),
        **values,
    )
