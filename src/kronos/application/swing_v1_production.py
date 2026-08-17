"""Production-source composition for the authorized Swing V1 validation path.

The adapter binds already-authoritative evidence.  It does not requalify a
setup, infer market state, invent geometry, or create Risk policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

from kronos.application.swing_v1_review import (
    Step31EligibilityHandoff,
    Step31EligibleInstrument,
)
from kronos.instrument import CanonicalInstrumentContext, InstrumentContextStatus
from kronos.market import (
    MARKET_SCHEDULE_CONTRACT_ID,
    MARKET_SCHEDULE_CONTRACT_VERSION,
    MarketAvailability,
    MarketSchedule,
    MarketSessionWindow,
    ScheduleFreshness,
    ScheduleIntegrity,
)
from kronos.provider.contracts.market_data import HistoricalCandle
from kronos.swing.v1.chart_analyst_v2_layer2 import (
    ChartAnalystV2Layer2Record,
    ChartAnalystV2Layer2State,
)
from kronos.swing.v1.models import V1Layer1Assessment
from kronos.swing.v1.step32 import (
    BusinessJudgment,
    CandidateLifecycle,
    CandidateLifecycleState,
    LocalStep32Store,
    RiskApproval,
    RiskState,
    create_business_judgment,
    record_risk_result,
    start_candidate_lifecycle,
)
from kronos.swing.v1.trade_construction import (
    LocalTradeCandidateStore,
    MaterialBarrier,
    SwingV1TradeCandidate,
    TradeConstructionExecutionContext,
    TradeConstructionInput,
    TradeConstructionStatus,
    TradeViabilityStatus,
    construct_trade_candidate,
    domain_007_handoff,
)


RISK_POLICY_UNAVAILABLE_REASON = "APPROVED_RISK_POLICY_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class AuthoritativeTradeGeometryReferences:
    """Existing evidence coordinates; this contract performs no calculation."""

    pullback_structural_low: Decimal | None
    pullback_structural_high: Decimal | None
    prior_directional_swing_high: Decimal | None
    prior_directional_swing_low: Decimal | None
    original_range_high: Decimal | None
    original_range_low: Decimal | None
    source_evidence_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "pullback_structural_low",
            "pullback_structural_high",
            "prior_directional_swing_high",
            "prior_directional_swing_low",
            "original_range_high",
            "original_range_low",
        ):
            value = getattr(self, name)
            if value is not None:
                actual = value if type(value) is Decimal else Decimal(str(value))
                if not actual.is_finite() or actual <= 0:
                    raise ValueError("TRADE_GEOMETRY_REFERENCE_INVALID")
                object.__setattr__(self, name, actual)
        if not self.source_evidence_identities or len(set(self.source_evidence_identities)) != len(self.source_evidence_identities):
            raise ValueError("TRADE_GEOMETRY_REFERENCE_INVALID")


@dataclass(frozen=True, slots=True)
class ProductionTradeConstructionSource:
    handoff: Step31EligibilityHandoff
    eligibility: Step31EligibleInstrument
    layer1_assessment: V1Layer1Assessment
    layer2: ChartAnalystV2Layer2Record
    qualification_candle: HistoricalCandle
    active_chart_revision_identity: str
    instrument_context: CanonicalInstrumentContext
    market_schedule: MarketSchedule
    geometry: AuthoritativeTradeGeometryReferences


@dataclass(frozen=True, slots=True)
class ProductionLifecycleResult:
    candidate: SwingV1TradeCandidate
    business_judgment: BusinessJudgment | None
    risk: RiskApproval | None
    lifecycle: CandidateLifecycle | None

    @property
    def waiting_for_risk(self) -> bool:
        return (
            self.risk is not None
            and self.risk.state is RiskState.UNAVAILABLE
            and self.lifecycle is not None
            and self.lifecycle.state is CandidateLifecycleState.WAITING_FOR_RISK
        )


@dataclass(frozen=True, slots=True)
class ProductionSourceSnapshot:
    instrument_context: CanonicalInstrumentContext
    market_schedule: MarketSchedule


class LocalProductionSourceStore:
    """Immutable retention for restart hydration of DOMAIN-001/008 facts."""

    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute() or root in {Path("/"), Path("/private/tmp")}:
            raise ValueError("PRODUCTION_SOURCE_STORE_ROOT_INVALID")
        self._root = root

    def retain(
        self,
        instrument: CanonicalInstrumentContext,
        schedule: MarketSchedule,
    ) -> Path:
        snapshot = ProductionSourceSnapshot(instrument, schedule)
        payload = _source_payload(snapshot)
        encoded_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        envelope = {
            "payload": payload,
            "digest": sha256(encoded_payload.encode()).hexdigest(),
        }
        encoded = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        path = self._root / instrument.identity / f"{schedule.identity}.json"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.exists():
            if path.read_text(encoding="utf-8") != encoded:
                raise ValueError("PRODUCTION_SOURCE_IMMUTABLE_CONFLICT")
            return path
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(encoded, encoding="utf-8")
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return path

    def load(self, instrument_identity: str, schedule_identity: str) -> ProductionSourceSnapshot:
        path = self._root / instrument_identity / f"{schedule_identity}.json"
        envelope = json.loads(path.read_text(encoding="utf-8"))
        payload = envelope.get("payload")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if (
            not isinstance(payload, dict)
            or envelope.get("digest") != sha256(encoded.encode()).hexdigest()
        ):
            raise ValueError("PRODUCTION_SOURCE_STORED_INTEGRITY_INVALID")
        snapshot = _source_from_payload(payload)
        if (
            snapshot.instrument_context.identity != instrument_identity
            or snapshot.market_schedule.identity != schedule_identity
        ):
            raise ValueError("PRODUCTION_SOURCE_STORED_BINDING_INVALID")
        return snapshot


def compose_execution_context(
    instrument: CanonicalInstrumentContext,
    schedule: MarketSchedule,
) -> TradeConstructionExecutionContext | None:
    """Compose DOMAIN-001 + DOMAIN-008, failing closed on any missing fact."""

    if (
        type(instrument) is not CanonicalInstrumentContext
        or type(schedule) is not MarketSchedule
        or instrument.status is not InstrumentContextStatus.COMPLETE
        or instrument.exchange != schedule.exchange
        or schedule.market_availability is not MarketAvailability.OPEN
        or instrument.tick_size is None
        or instrument.price_precision is None
    ):
        return None
    return TradeConstructionExecutionContext(
        identity=f"{instrument.identity}|{schedule.identity}",
        canonical_instrument=instrument.canonical_instrument,
        product=instrument.product,
        tick_size=instrument.tick_size,
        price_precision=instrument.price_precision,
        session_calendar_identity="|".join((
            schedule.calendar_identity,
            schedule.calendar_version,
            schedule.session_identity,
        )),
        market_available=True,
    )


def build_trade_construction_input(
    source: ProductionTradeConstructionSource,
) -> TradeConstructionInput:
    """Bind the Step-30 handoff to existing Step-31 construction inputs."""

    if type(source) is not ProductionTradeConstructionSource:
        raise ValueError("PRODUCTION_TRADE_SOURCE_INVALID")
    assessment = source.layer1_assessment
    layer2_record = source.layer2.layer2_record
    expected_identity = "|".join((
        assessment.canonical_identity,
        assessment.setup.value,
        assessment.direction.value,
        assessment.observation_boundary.isoformat(),
    ))
    if (
        source.eligibility not in source.handoff.eligible_instruments
        or assessment.canonical_identity != source.eligibility.canonical_instrument
        or expected_identity not in source.eligibility.probable_assessment_identities
        or source.layer2.state is not ChartAnalystV2Layer2State.SHADOW_COMPLETE
        or layer2_record is None
        or layer2_record.readiness != source.layer2.readiness
        or source.qualification_candle.timestamp != source.eligibility.observation_boundary
        or source.active_chart_revision_identity != source.eligibility.source_image_sha256
    ):
        raise ValueError("PRODUCTION_TRADE_SOURCE_BINDING_INVALID")
    barriers = tuple(
        MaterialBarrier(
            f"{barrier.correlation_key}:{barrier.source_hashes[0]}",
            Decimal(str(barrier.price)),
        )
        for barrier in layer2_record.barriers
        if barrier.price is not None
    )
    geometry = source.geometry
    return TradeConstructionInput(
        handoff=source.handoff,
        eligibility=source.eligibility,
        layer1_assessment_identity=expected_identity,
        setup_family=assessment.setup,
        direction=assessment.direction,
        layer2_state_identity=source.layer2.state.value,
        readiness_identity=source.layer2.readiness.policy_identity,
        qualification_observation_boundary=source.eligibility.observation_boundary,
        active_chart_revision_identity=source.active_chart_revision_identity,
        qualification_high=Decimal(str(source.qualification_candle.high)),
        qualification_low=Decimal(str(source.qualification_candle.low)),
        pullback_structural_low=geometry.pullback_structural_low,
        pullback_structural_high=geometry.pullback_structural_high,
        prior_directional_swing_high=geometry.prior_directional_swing_high,
        prior_directional_swing_low=geometry.prior_directional_swing_low,
        original_range_high=geometry.original_range_high,
        original_range_low=geometry.original_range_low,
        clear_air_identity=layer2_record.clear_air.policy_identity,
        material_barriers=barriers,
        execution_context=compose_execution_context(
            source.instrument_context,
            source.market_schedule,
        ),
        source_evidence_identities=geometry.source_evidence_identities + (
            source.active_chart_revision_identity,
            source.instrument_context.identity,
            source.market_schedule.identity,
        ),
        market_data_boundary=source.eligibility.observation_boundary,
        qualification_candle_completed=True,
    )


def produce_waiting_for_risk_lifecycle(
    source: ProductionTradeConstructionSource,
    *,
    candidate_store: LocalTradeCandidateStore,
    step32_store: LocalStep32Store,
    source_store: LocalProductionSourceStore,
    clock: datetime,
) -> ProductionLifecycleResult:
    """Run the authorized path and stop at RISK_UNAVAILABLE."""

    item = build_trade_construction_input(source)
    source_store.retain(source.instrument_context, source.market_schedule)
    candidate = construct_trade_candidate(item, clock=clock)
    candidate_store.retain(candidate)
    if (
        candidate.construction_status is not TradeConstructionStatus.COMPLETE
        or candidate.viability_status is not TradeViabilityStatus.VIABLE
    ):
        return ProductionLifecycleResult(candidate, None, None, None)
    domain_007_handoff(candidate)
    judgment = create_business_judgment(
        candidate,
        validation_identity=source.layer2.readiness.policy_identity,
        clock=clock,
        canonical_instrument_echo=candidate.canonical_instrument,
        product_echo=candidate.product,
        setup_echo=candidate.setup_family,
        direction_echo=candidate.direction,
    )
    risk = record_risk_result(
        candidate,
        judgment,
        RiskState.UNAVAILABLE,
        reason=RISK_POLICY_UNAVAILABLE_REASON,
        clock=clock,
    )
    lifecycle = start_candidate_lifecycle(
        candidate,
        risk,
        monitoring_binding_id=f"MONITORING-DEFERRED-{candidate.candidate_id}",
        clock=clock,
    )
    for record in (judgment, risk, lifecycle):
        step32_store.retain(record)
    return ProductionLifecycleResult(candidate, judgment, risk, lifecycle)


def _source_payload(snapshot: ProductionSourceSnapshot) -> dict[str, object]:
    instrument = snapshot.instrument_context
    schedule = snapshot.market_schedule
    return {
        "instrument": {
            "identity": instrument.identity,
            "canonical_instrument": instrument.canonical_instrument,
            "product": instrument.product,
            "provider": instrument.provider,
            "provider_trading_symbol": instrument.provider_trading_symbol,
            "exchange": instrument.exchange,
            "segment": instrument.segment,
            "instrument_type": instrument.instrument_type,
            "tick_size": str(instrument.tick_size) if instrument.tick_size is not None else None,
            "lot_size": instrument.lot_size,
            "price_precision": instrument.price_precision,
            "status": instrument.status.value,
            "provenance": list(instrument.provenance),
        },
        "schedule": {
            "identity": schedule.identity,
            "market_identity": schedule.market_identity,
            "exchange": schedule.exchange,
            "trading_date": schedule.trading_date.isoformat(),
            "calendar_identity": schedule.calendar_identity,
            "calendar_version": schedule.calendar_version,
            "session_identity": schedule.session_identity,
            "session_type": schedule.session_type,
            "session_open": schedule.session_open.isoformat() if schedule.session_open else None,
            "session_close": schedule.session_close.isoformat() if schedule.session_close else None,
            **(
                {
                    "windows": [
                        {
                            "identity": item.identity,
                            "order": item.order,
                            "open": item.window_open.isoformat(),
                            "close": item.window_close.isoformat(),
                        }
                        for item in schedule.windows
                    ]
                }
                if len(schedule.windows) > 1
                else {}
            ),
            "timezone": schedule.timezone,
            "market_availability": schedule.market_availability.value,
            "as_of": schedule.as_of.isoformat(),
            "source_identity": schedule.source_identity,
            "source_boundary": schedule.source_boundary.isoformat(),
            "freshness_status": schedule.freshness_status.value,
            "integrity_status": schedule.integrity_status.value,
            "provenance": list(schedule.provenance),
        },
    }


def _source_from_payload(payload: dict[str, object]) -> ProductionSourceSnapshot:
    try:
        instrument = payload["instrument"]
        schedule = payload["schedule"]
        if not isinstance(instrument, dict) or not isinstance(schedule, dict):
            raise TypeError
        windows_payload = schedule.get("windows", ())
        if not isinstance(windows_payload, (list, tuple)):
            raise TypeError
        schedule_windows = tuple(
            MarketSessionWindow(
                item["identity"],
                item["order"],
                datetime.fromisoformat(item["open"]),
                datetime.fromisoformat(item["close"]),
            )
            for item in windows_payload
        )
        if (
            not schedule_windows
            and schedule.get("session_open")
            and schedule.get("session_close")
        ):
            schedule_windows = (
                MarketSessionWindow(
                    f"{schedule['session_identity']}:WINDOW:1",
                    1,
                    datetime.fromisoformat(schedule["session_open"]),
                    datetime.fromisoformat(schedule["session_close"]),
                ),
            )
        instrument_context = CanonicalInstrumentContext(
            identity=instrument["identity"],
            canonical_instrument=instrument["canonical_instrument"],
            product=instrument["product"],
            provider=instrument["provider"],
            provider_trading_symbol=instrument["provider_trading_symbol"],
            exchange=instrument["exchange"],
            segment=instrument["segment"],
            instrument_type=instrument["instrument_type"],
            tick_size=(Decimal(instrument["tick_size"]) if instrument["tick_size"] is not None else None),
            lot_size=instrument["lot_size"],
            price_precision=instrument["price_precision"],
            status=InstrumentContextStatus(instrument["status"]),
            provenance=tuple(instrument["provenance"]),
        )
        market_schedule = MarketSchedule(
            MARKET_SCHEDULE_CONTRACT_ID,
            MARKET_SCHEDULE_CONTRACT_VERSION,
            schedule["identity"],
            schedule["market_identity"],
            schedule["exchange"],
            date.fromisoformat(schedule["trading_date"]),
            schedule["calendar_identity"],
            schedule["calendar_version"],
            schedule["session_identity"],
            schedule["session_type"],
            datetime.fromisoformat(schedule["session_open"]) if schedule["session_open"] else None,
            datetime.fromisoformat(schedule["session_close"]) if schedule["session_close"] else None,
            schedule["timezone"],
            MarketAvailability(schedule["market_availability"]),
            datetime.fromisoformat(schedule["as_of"]),
            schedule["source_identity"],
            datetime.fromisoformat(schedule["source_boundary"]),
            ScheduleFreshness(schedule["freshness_status"]),
            ScheduleIntegrity(schedule["integrity_status"]),
            tuple(schedule["provenance"]),
            schedule_windows,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("PRODUCTION_SOURCE_STORED_INVALID") from error
    return ProductionSourceSnapshot(instrument_context, market_schedule)


__all__ = [
    "AuthoritativeTradeGeometryReferences",
    "ProductionLifecycleResult",
    "LocalProductionSourceStore",
    "ProductionSourceSnapshot",
    "ProductionTradeConstructionSource",
    "RISK_POLICY_UNAVAILABLE_REASON",
    "build_trade_construction_input",
    "compose_execution_context",
    "produce_waiting_for_risk_lifecycle",
]
