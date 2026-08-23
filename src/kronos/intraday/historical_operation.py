"""WO-06HA governed contracts for bounded historical research operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Iterable

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_qualification import (
    HISTORICAL_RECONSTRUCTION_IDENTITY,
    WO06H_CONTRACT_VERSION,
    HistoricalBindingAvailability,
    HistoricalCalendarSource,
    HistoricalFactualFailureEvidence,
    HistoricalFactFamily,
    HistoricalResearchSubjectSet,
    HistoricalResearchSubject,
    HistoricalSessionSelection,
    HistoricalSubjectBinding,
    create_historical_subject_binding,
    select_historical_session,
)
from kronos.intraday.reconciliation import (
    Availability,
    ReconciliationMember,
    ReconciliationPublication,
)
from kronos.market.schedule import MarketDaySchedule, TradingDayStatus


HISTORICAL_OPERATION_IDENTITY = (
    "KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-OPERATION-V0"
)
HISTORICAL_OPERATION_VERSION = "0.1.0"
HISTORICAL_OPERATION_REQUEST_IDENTITY = (
    "KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-OPERATION-REQUEST-V0"
)
COMPLETED_SESSION_EOD_BOUNDARY_IDENTITY = (
    "KRONOS-INTRADAY-COMPLETED-SESSION-EOD-RESEARCH-V0"
)
COMPLETED_SESSION_EOD_BOUNDARY_VERSION = "0.1.0"
PROVIDER_REQUEST_LIMIT_CEILING = 10_000

HISTORICAL_OPERATION_TIMEFRAMES = (
    IntradayTimeframe.DAILY,
    IntradayTimeframe.ONE_HOUR,
    IntradayTimeframe.FIFTEEN_MINUTES,
    IntradayTimeframe.FIVE_MINUTES,
)
REQUIRED_HISTORICAL_FACT_FAMILIES = (
    HistoricalFactFamily.COMPLETED_OHLCV,
    HistoricalFactFamily.PREVIOUS_SESSION_HLC_PDH_PDL,
    HistoricalFactFamily.CLASSIC_PIVOTS_CPR,
    HistoricalFactFamily.NARROW_CPR,
)


class HistoricalOperationState(StrEnum):
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CONFLICT = "CONFLICT"


class HistoricalOperationStage(StrEnum):
    CONTEXT_VERIFICATION = "CONTEXT_VERIFICATION"
    REQUEST_VALIDATION = "REQUEST_VALIDATION"
    SUBJECT_SET_RESOLUTION = "SUBJECT_SET_RESOLUTION"
    SESSION_RESOLUTION = "SESSION_RESOLUTION"
    REQUEST_PLANNING = "REQUEST_PLANNING"
    LEASE_ACQUISITION = "LEASE_ACQUISITION"
    HISTORICAL_FACT_ACQUISITION = "HISTORICAL_FACT_ACQUISITION"
    RECONSTRUCTION = "RECONSTRUCTION"
    PERSISTENCE = "PERSISTENCE"
    RELOAD_VERIFICATION = "RELOAD_VERIFICATION"
    COMPLETE = "COMPLETE"


class HistoricalOperationFailure(StrEnum):
    CONTEXT_UNAVAILABLE = "CONTEXT_UNAVAILABLE"
    CONTEXT_EXPIRED = "CONTEXT_EXPIRED"
    REQUEST_INVALID = "REQUEST_INVALID"
    REQUEST_BOUND_EXCEEDED = "REQUEST_BOUND_EXCEEDED"
    UNIVERSE_UNAVAILABLE = "UNIVERSE_UNAVAILABLE"
    SESSION_UNAVAILABLE = "SESSION_UNAVAILABLE"
    HISTORICAL_CANONICAL_BINDING_UNAVAILABLE = (
        "HISTORICAL_CANONICAL_BINDING_UNAVAILABLE"
    )
    HISTORICAL_PREREQUISITE_UNAVAILABLE = (
        "HISTORICAL_PREREQUISITE_UNAVAILABLE"
    )
    PROVIDER_ACQUISITION_FAILED = "PROVIDER_ACQUISITION_FAILED"
    MANDATORY_TIMEFRAME_UNAVAILABLE = "MANDATORY_TIMEFRAME_UNAVAILABLE"
    INCOMPLETE_CANDLE_NOT_AUTHORIZED = "INCOMPLETE_CANDLE_NOT_AUTHORIZED"
    QUALIFICATION_LOOK_AHEAD_REJECTED = (
        "QUALIFICATION_LOOK_AHEAD_REJECTED"
    )
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"
    RELOAD_FAILED = "RELOAD_FAILED"
    INTEGRITY_INVALID = "INTEGRITY_INVALID"
    OPERATION_CONFLICT = "OPERATION_CONFLICT"


class HistoricalOperationError(RuntimeError):
    def __init__(
        self,
        failure: HistoricalOperationFailure,
        *,
        evidence: HistoricalFactualFailureEvidence | None = None,
    ) -> None:
        self.failure = failure
        self.evidence = evidence
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class HistoricalOperationSessionRequest:
    trading_date: date
    session_identity: str

    def __post_init__(self) -> None:
        if (
            type(self.trading_date) is not date
            or not _text(self.session_identity)
            or self.session_identity.upper() in {"LATEST", "NEWEST", "CURRENT"}
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.REQUEST_INVALID
            )


@dataclass(frozen=True, slots=True)
class HistoricalQualificationOperationRequest:
    request_identity: str
    operation_identity: str
    universe_identity: str
    universe_version: str
    universe_integrity_identity: str
    sessions: tuple[HistoricalOperationSessionRequest, ...]
    boundary_family_identity: str
    boundary_family_version: str
    timeframes: tuple[IntradayTimeframe, ...]
    maximum_provider_requests: int
    requested_factual_families: tuple[HistoricalFactFamily, ...]
    requested_outcome_families: tuple[str, ...]
    requested_at: datetime
    provenance: tuple[str, ...]
    integrity_identity: str
    reconstruction_contract_identity: str = HISTORICAL_RECONSTRUCTION_IDENTITY
    reconstruction_contract_version: str = WO06H_CONTRACT_VERSION
    schema_identity: str = HISTORICAL_OPERATION_REQUEST_IDENTITY
    schema_version: str = HISTORICAL_OPERATION_VERSION

    def __post_init__(self) -> None:
        core = _request_core(self)
        session_dates = tuple(item.trading_date for item in self.sessions)
        session_ids = tuple(item.session_identity for item in self.sessions)
        if (
            not self.request_identity.startswith("INTRADAY-HISTORICAL-REQUEST-")
            or not self.operation_identity.startswith(
                "INTRADAY-HISTORICAL-QUALIFICATION-OPERATION-"
            )
            or not _texts(
                (
                    self.universe_identity,
                    self.universe_version,
                    self.universe_integrity_identity,
                    self.boundary_family_identity,
                    self.boundary_family_version,
                )
            )
            or not self.sessions
            or any(
                type(item) is not HistoricalOperationSessionRequest
                for item in self.sessions
            )
            or tuple(sorted(session_dates)) != session_dates
            or len(set(session_dates)) != len(session_dates)
            or len(set(session_ids)) != len(session_ids)
            or not self.timeframes
            or any(type(item) is not IntradayTimeframe for item in self.timeframes)
            or len(set(self.timeframes)) != len(self.timeframes)
            or type(self.maximum_provider_requests) is not int
            or not 1 <= self.maximum_provider_requests <= PROVIDER_REQUEST_LIMIT_CEILING
            or not self.requested_factual_families
            or any(
                type(item) is not HistoricalFactFamily
                for item in self.requested_factual_families
            )
            or len(set(self.requested_factual_families))
            != len(self.requested_factual_families)
            or not _texts(self.requested_outcome_families, allow_empty=True)
            or not _aware(self.requested_at)
            or not _texts(self.provenance)
            or self.reconstruction_contract_identity
            != HISTORICAL_RECONSTRUCTION_IDENTITY
            or self.reconstruction_contract_version != WO06H_CONTRACT_VERSION
            or self.schema_identity != HISTORICAL_OPERATION_REQUEST_IDENTITY
            or self.schema_version != HISTORICAL_OPERATION_VERSION
            or self.request_identity != _identity("INTRADAY-HISTORICAL-REQUEST-", core)
            or self.operation_identity
            != _identity(
                "INTRADAY-HISTORICAL-QUALIFICATION-OPERATION-", core
            )
            or self.integrity_identity
            != _identity("INTEGRITY-HISTORICAL-OPERATION-REQUEST-", core)
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.REQUEST_INVALID
            )


def create_historical_operation_request(
    *,
    universe_identity: str,
    universe_version: str,
    universe_integrity_identity: str,
    sessions: tuple[HistoricalOperationSessionRequest, ...],
    boundary_family_identity: str,
    boundary_family_version: str,
    timeframes: tuple[IntradayTimeframe, ...],
    maximum_provider_requests: int,
    requested_factual_families: tuple[HistoricalFactFamily, ...],
    requested_outcome_families: tuple[str, ...],
    requested_at: datetime,
    provenance: tuple[str, ...],
) -> HistoricalQualificationOperationRequest:
    ordered_sessions = tuple(sorted(sessions, key=lambda item: item.trading_date))
    values = {
        "universe_identity": universe_identity,
        "universe_version": universe_version,
        "universe_integrity_identity": universe_integrity_identity,
        "sessions": ordered_sessions,
        "boundary_family_identity": boundary_family_identity,
        "boundary_family_version": boundary_family_version,
        "timeframes": timeframes,
        "maximum_provider_requests": maximum_provider_requests,
        "requested_factual_families": requested_factual_families,
        "requested_outcome_families": requested_outcome_families,
        "requested_at": requested_at,
        "provenance": provenance,
        "reconstruction_contract_identity": HISTORICAL_RECONSTRUCTION_IDENTITY,
        "reconstruction_contract_version": WO06H_CONTRACT_VERSION,
        "schema_identity": HISTORICAL_OPERATION_REQUEST_IDENTITY,
        "schema_version": HISTORICAL_OPERATION_VERSION,
    }
    core = _normalize(values)
    return HistoricalQualificationOperationRequest(
        request_identity=_identity("INTRADAY-HISTORICAL-REQUEST-", core),
        operation_identity=_identity(
            "INTRADAY-HISTORICAL-QUALIFICATION-OPERATION-", core
        ),
        integrity_identity=_identity(
            "INTEGRITY-HISTORICAL-OPERATION-REQUEST-", core
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class HistoricalOperationalSubject:
    universe_member_identity: str
    sponsor_label: str
    exchange: str
    provider_symbol: str | None
    reconciliation_member_identity: str
    binding: HistoricalSubjectBinding

    def __post_init__(self) -> None:
        if (
            not _texts(
                (
                    self.universe_member_identity,
                    self.sponsor_label,
                    self.exchange,
                    self.reconciliation_member_identity,
                )
            )
            or self.provider_symbol is not None and not _text(self.provider_symbol)
            or type(self.binding) is not HistoricalSubjectBinding
            or self.binding.universe_member_identity
            != self.universe_member_identity
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.INTEGRITY_INVALID
            )


def resolve_historical_operational_subjects(
    *,
    subject_set: HistoricalResearchSubjectSet,
    reconciliation: ReconciliationPublication,
) -> tuple[HistoricalOperationalSubject, ...]:
    if (
        type(subject_set) is not HistoricalResearchSubjectSet
        or type(reconciliation) is not ReconciliationPublication
        or reconciliation.universe_identity != subject_set.current_universe_identity
        or reconciliation.universe_version != subject_set.current_universe_version
        or reconciliation.universe_integrity_identity
        != subject_set.current_universe_integrity_identity
    ):
        raise HistoricalOperationError(
            HistoricalOperationFailure.UNIVERSE_UNAVAILABLE
        )
    members = {item.sponsor_label: item for item in reconciliation.members}
    resolved: list[HistoricalOperationalSubject] = []
    for subject in subject_set.subjects:
        member = members.get(subject.sponsor_label)
        if (
            type(member) is not ReconciliationMember
            or member.universe_member_identity != subject.universe_member_identity
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.UNIVERSE_UNAVAILABLE
            )
        provider_fact_identity = (
            member.provider_record_identities[0]
            if member.dimensions.canonical_identity is Availability.AVAILABLE
            and member.dimensions.machine_fact_consumability is Availability.AVAILABLE
            and member.provider_symbol is not None
            and len(member.provider_record_identities) == 1
            else None
        )
        reconciled_subject = HistoricalResearchSubject(
            universe_member_identity=subject.universe_member_identity,
            sponsor_label=subject.sponsor_label,
            canonical_identity=(
                member.canonical_identity
                if member.dimensions.canonical_identity is Availability.AVAILABLE
                else None
            ),
            market_family=subject.market_family,
            universe_member_source_identity=subject.universe_member_source_identity,
        )
        binding = create_historical_subject_binding(
            subject=reconciled_subject,
            historical_provider_fact_identity=provider_fact_identity,
            historical_derivative_contract_identity=None,
            provenance=(
                HISTORICAL_OPERATION_IDENTITY,
                reconciliation.integrity_identity,
                member.reconciliation_member_identity,
            ),
        )
        resolved.append(
            HistoricalOperationalSubject(
                universe_member_identity=subject.universe_member_identity,
                sponsor_label=subject.sponsor_label,
                exchange=member.exchange,
                provider_symbol=member.provider_symbol,
                reconciliation_member_identity=member.reconciliation_member_identity,
                binding=binding,
            )
        )
    return tuple(resolved)


@dataclass(frozen=True, slots=True)
class HistoricalEodSession:
    request: HistoricalOperationSessionRequest
    target_schedule: MarketDaySchedule
    previous_schedule: MarketDaySchedule
    selection: HistoricalSessionSelection
    boundary_identity: str

    def __post_init__(self) -> None:
        if (
            type(self.request) is not HistoricalOperationSessionRequest
            or type(self.target_schedule) is not MarketDaySchedule
            or type(self.previous_schedule) is not MarketDaySchedule
            or type(self.selection) is not HistoricalSessionSelection
            or not _text(self.boundary_identity)
            or self.request.trading_date != self.target_schedule.trading_date
            or self.selection.target_session_identity
            != self.target_schedule.session_id
            or self.selection.previous_session_identity
            != self.previous_schedule.session_id
            or self.selection.observation_boundary
            != self.target_schedule.windows[-1].closes_at
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.SESSION_UNAVAILABLE
            )


def resolve_historical_eod_sessions(
    *,
    calendar: HistoricalCalendarSource,
    requested: tuple[HistoricalOperationSessionRequest, ...],
    exchange: str,
    provenance: tuple[str, ...],
    require_requested_session_identity: bool = True,
) -> tuple[HistoricalEodSession, ...]:
    if (
        not requested
        or not _text(exchange)
        or not _texts(provenance)
        or type(require_requested_session_identity) is not bool
    ):
        raise HistoricalOperationError(HistoricalOperationFailure.REQUEST_INVALID)
    resolved: list[HistoricalEodSession] = []
    for item in requested:
        target = calendar.schedule_for(exchange, item.trading_date)
        previous = calendar.previous_trading_schedule(exchange, item.trading_date)
        if (
            type(target) is not MarketDaySchedule
            or type(previous) is not MarketDaySchedule
            or target.status is not TradingDayStatus.TRADING
            or previous.status is not TradingDayStatus.TRADING
            or require_requested_session_identity
            and target.session_id != item.session_identity
            or not target.windows
            or not previous.windows
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.SESSION_UNAVAILABLE
            )
        boundary = target.windows[-1].closes_at
        boundary_identity = _identity(
            "INTRADAY-COMPLETED-SESSION-EOD-BOUNDARY-",
            {
                "family": COMPLETED_SESSION_EOD_BOUNDARY_IDENTITY,
                "version": COMPLETED_SESSION_EOD_BOUNDARY_VERSION,
                "session": target.session_id,
                "boundary": boundary,
                "source": target.source_identity,
                "source_version": target.source_version,
            },
        )
        selection = select_historical_session(
            calendar=calendar,
            exchange=exchange,
            target_trading_date=item.trading_date,
            observation_boundary_identity=boundary_identity,
            observation_boundary=boundary,
            provenance=provenance,
        )
        resolved.append(
            HistoricalEodSession(
                request=item,
                target_schedule=target,
                previous_schedule=previous,
                selection=selection,
                boundary_identity=boundary_identity,
            )
        )
    return tuple(resolved)


@dataclass(frozen=True, slots=True)
class HistoricalProviderRequestPlan:
    plan_identity: str
    operation_identity: str
    subject_set_count: int
    eligible_subject_count: int
    unavailable_subject_count: int
    session_count: int
    timeframe_count: int
    subject_session_observations: int
    instrument_record_request_count: int
    historical_request_count: int
    total_provider_request_count: int
    sequential: bool
    automatic_retry: bool
    integrity_identity: str

    def __post_init__(self) -> None:
        core = _plan_core(self)
        counts = (
            self.subject_set_count,
            self.eligible_subject_count,
            self.unavailable_subject_count,
            self.session_count,
            self.timeframe_count,
            self.subject_session_observations,
            self.instrument_record_request_count,
            self.historical_request_count,
            self.total_provider_request_count,
        )
        if (
            not self.plan_identity.startswith("INTRADAY-HISTORICAL-REQUEST-PLAN-")
            or not _text(self.operation_identity)
            or any(type(value) is not int or value < 0 for value in counts)
            or self.subject_set_count
            != self.eligible_subject_count + self.unavailable_subject_count
            or self.subject_session_observations
            != self.subject_set_count * self.session_count
            or self.historical_request_count
            != self.eligible_subject_count
            * self.session_count
            * self.timeframe_count
            or self.total_provider_request_count
            != self.historical_request_count
            + self.instrument_record_request_count
            or not self.sequential
            or self.automatic_retry
            or self.plan_identity
            != _identity("INTRADAY-HISTORICAL-REQUEST-PLAN-", core)
            or self.integrity_identity
            != _identity("INTEGRITY-HISTORICAL-REQUEST-PLAN-", core)
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.INTEGRITY_INVALID
            )


def create_historical_request_plan(
    *,
    request: HistoricalQualificationOperationRequest,
    subjects: tuple[HistoricalOperationalSubject, ...],
    sessions: tuple[HistoricalEodSession, ...],
) -> HistoricalProviderRequestPlan:
    if (
        type(request) is not HistoricalQualificationOperationRequest
        or not subjects
        or any(type(item) is not HistoricalOperationalSubject for item in subjects)
        or not sessions
        or any(type(item) is not HistoricalEodSession for item in sessions)
    ):
        raise HistoricalOperationError(HistoricalOperationFailure.REQUEST_INVALID)
    eligible = tuple(
        item
        for item in subjects
        if item.binding.availability is HistoricalBindingAvailability.AVAILABLE
    )
    exchanges = {item.exchange for item in eligible}
    values = {
        "operation_identity": request.operation_identity,
        "subject_set_count": len(subjects),
        "eligible_subject_count": len(eligible),
        "unavailable_subject_count": len(subjects) - len(eligible),
        "session_count": len(sessions),
        "timeframe_count": len(request.timeframes),
        "subject_session_observations": len(subjects) * len(sessions),
        "instrument_record_request_count": len(exchanges),
        "historical_request_count": (
            len(eligible) * len(sessions) * len(request.timeframes)
        ),
        "total_provider_request_count": (
            len(eligible) * len(sessions) * len(request.timeframes)
            + len(exchanges)
        ),
        "sequential": True,
        "automatic_retry": False,
    }
    core = _normalize(values)
    return HistoricalProviderRequestPlan(
        plan_identity=_identity("INTRADAY-HISTORICAL-REQUEST-PLAN-", core),
        integrity_identity=_identity(
            "INTEGRITY-HISTORICAL-REQUEST-PLAN-", core
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class HistoricalSessionOperationAccounting:
    session_identity: str
    subject_set_count: int
    historically_evaluable_count: int
    prerequisite_unavailable_count: int
    factual_success_count: int
    factual_failure_count: int
    narrow_cpr_true_count: int
    narrow_cpr_false_count: int
    narrow_cpr_unavailable_count: int

    def __post_init__(self) -> None:
        counts = tuple(
            getattr(self, name)
            for name in HistoricalSessionOperationAccounting.__dataclass_fields__
            if name != "session_identity"
        )
        if (
            not _text(self.session_identity)
            or any(type(value) is not int or value < 0 for value in counts)
            or self.subject_set_count
            != self.historically_evaluable_count
            + self.prerequisite_unavailable_count
            or self.historically_evaluable_count
            != self.factual_success_count + self.factual_failure_count
            or self.subject_set_count
            != self.narrow_cpr_true_count
            + self.narrow_cpr_false_count
            + self.narrow_cpr_unavailable_count
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.INTEGRITY_INVALID
            )


@dataclass(frozen=True, slots=True)
class HistoricalQualificationOperationResult:
    operation_identity: str
    state: HistoricalOperationState
    stage: HistoricalOperationStage
    context_state: str
    request_plan_identity: str | None
    subject_set_count: int
    historically_resolvable_count: int
    prerequisite_unavailable_count: int
    sessions_requested: int
    sessions_valid: int
    sessions_unavailable: int
    subject_session_observations_planned: int
    successful_reconstructions: int
    factual_failures: int
    prerequisite_unavailable_observations: int
    narrow_cpr_true_count: int
    narrow_cpr_false_count: int
    narrow_cpr_unavailable_count: int
    provider_request_ceiling: int
    provider_request_count: int
    reconstruction_identities: tuple[str, ...]
    bundle_identities: tuple[str, ...]
    failure_evidence_identities: tuple[str, ...]
    session_accounting: tuple[HistoricalSessionOperationAccounting, ...]
    observation_failure_counts: tuple[tuple[str, int], ...]
    persistence_complete: bool
    reload_verified: bool
    corpus_binding_performed: bool
    production_state_mutated: bool
    failure: HistoricalOperationFailure | None
    completed_at: datetime

    def __post_init__(self) -> None:
        counts = (
            self.subject_set_count,
            self.historically_resolvable_count,
            self.prerequisite_unavailable_count,
            self.sessions_requested,
            self.sessions_valid,
            self.sessions_unavailable,
            self.subject_session_observations_planned,
            self.successful_reconstructions,
            self.factual_failures,
            self.prerequisite_unavailable_observations,
            self.narrow_cpr_true_count,
            self.narrow_cpr_false_count,
            self.narrow_cpr_unavailable_count,
            self.provider_request_ceiling,
            self.provider_request_count,
        )
        if (
            not _text(self.operation_identity)
            or type(self.state) is not HistoricalOperationState
            or type(self.stage) is not HistoricalOperationStage
            or not _text(self.context_state)
            or self.request_plan_identity is not None
            and not _text(self.request_plan_identity)
            or any(type(value) is not int or value < 0 for value in counts)
            or not _texts(self.reconstruction_identities, allow_empty=True)
            or not _texts(self.bundle_identities, allow_empty=True)
            or not _texts(self.failure_evidence_identities, allow_empty=True)
            or any(
                type(item) is not HistoricalSessionOperationAccounting
                for item in self.session_accounting
            )
            or any(
                type(item) is not tuple
                or len(item) != 2
                or not _text(item[0])
                or type(item[1]) is not int
                or item[1] < 1
                for item in self.observation_failure_counts
            )
            or tuple(sorted(self.observation_failure_counts))
            != self.observation_failure_counts
            or type(self.persistence_complete) is not bool
            or type(self.reload_verified) is not bool
            or self.corpus_binding_performed
            or self.production_state_mutated
            or self.failure is not None
            and type(self.failure) is not HistoricalOperationFailure
            or not _aware(self.completed_at)
        ):
            raise HistoricalOperationError(
                HistoricalOperationFailure.INTEGRITY_INVALID
            )


def _request_core(value: HistoricalQualificationOperationRequest) -> object:
    fields = asdict(value)
    for name in ("request_identity", "operation_identity", "integrity_identity"):
        fields.pop(name)
    return _normalize(fields)


def _plan_core(value: HistoricalProviderRequestPlan) -> object:
    fields = asdict(value)
    fields.pop("plan_identity")
    fields.pop("integrity_identity")
    return _normalize(fields)


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(value)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _normalize(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return _normalize(asdict(value))
    return value


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: Iterable[object], *, allow_empty: bool = False) -> bool:
    retained = tuple(values)
    return (allow_empty or bool(retained)) and all(_text(value) for value in retained)


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "COMPLETED_SESSION_EOD_BOUNDARY_IDENTITY",
    "COMPLETED_SESSION_EOD_BOUNDARY_VERSION",
    "HISTORICAL_OPERATION_IDENTITY",
    "HISTORICAL_OPERATION_REQUEST_IDENTITY",
    "HISTORICAL_OPERATION_TIMEFRAMES",
    "HISTORICAL_OPERATION_VERSION",
    "PROVIDER_REQUEST_LIMIT_CEILING",
    "REQUIRED_HISTORICAL_FACT_FAMILIES",
    "HistoricalEodSession",
    "HistoricalOperationError",
    "HistoricalOperationFailure",
    "HistoricalOperationSessionRequest",
    "HistoricalOperationStage",
    "HistoricalOperationState",
    "HistoricalOperationalSubject",
    "HistoricalProviderRequestPlan",
    "HistoricalQualificationOperationRequest",
    "HistoricalQualificationOperationResult",
    "HistoricalSessionOperationAccounting",
    "create_historical_operation_request",
    "create_historical_request_plan",
    "resolve_historical_eod_sessions",
    "resolve_historical_operational_subjects",
]
