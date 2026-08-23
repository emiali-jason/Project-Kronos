"""Bounded loopback control for the composed Intraday historical operation."""

from __future__ import annotations

from datetime import date, datetime
import re

from kronos.application.intraday_historical_operation import (
    IntradayHistoricalQualificationHarness,
    IntradayHistoricalQualificationOperationService,
)
from kronos.intraday.historical_operation import (
    COMPLETED_SESSION_EOD_BOUNDARY_IDENTITY,
    COMPLETED_SESSION_EOD_BOUNDARY_VERSION,
    HISTORICAL_OPERATION_IDENTITY,
    HISTORICAL_OPERATION_TIMEFRAMES,
    HISTORICAL_OPERATION_VERSION,
    REQUIRED_HISTORICAL_FACT_FAMILIES,
    HistoricalOperationError,
    HistoricalOperationSessionRequest,
    HistoricalQualificationOperationResult,
    create_historical_operation_request,
)


INTRADAY_HISTORICAL_CONTROL_IDENTITY = (
    "KRONOS-INTRADAY-HISTORICAL-QUALIFICATION-OPERATIONAL-CONTROL-V0"
)
INTRADAY_HISTORICAL_CONTROL_VERSION = "0.1.0"
HISTORICAL_OPERATION_IN_PROCESS_INVOCATION_UNAVAILABLE = (
    "HISTORICAL_OPERATION_IN_PROCESS_INVOCATION_UNAVAILABLE"
)
_REQUEST_IDENTITY = re.compile(r"[A-Z0-9][A-Z0-9._:-]{0,95}\Z")


class IntradayHistoricalQualificationOperationalControl:
    """Wrap one exact in-process historical invocation without owning policy."""

    __slots__ = ("_invocation", "_operation")

    def __init__(self, invocation: IntradayHistoricalQualificationHarness) -> None:
        if type(invocation) is not IntradayHistoricalQualificationHarness:
            raise ValueError("INTRADAY_HISTORICAL_CONTROL_INVALID")
        operation = invocation.operation_service
        if type(operation) is not IntradayHistoricalQualificationOperationService:
            raise ValueError("INTRADAY_HISTORICAL_CONTROL_INVALID")
        self._invocation = invocation
        self._operation = operation

    @property
    def historical_invocation(self) -> IntradayHistoricalQualificationHarness:
        return self._invocation

    @property
    def operation_service(self) -> IntradayHistoricalQualificationOperationService:
        return self._operation

    def status_document(self) -> dict[str, object]:
        """Project sanitized state without invoking historical or Provider work."""

        last_result = self._operation.last_result
        return {
            "control_identity": INTRADAY_HISTORICAL_CONTROL_IDENTITY,
            "control_version": INTRADAY_HISTORICAL_CONTROL_VERSION,
            "service_identity": HISTORICAL_OPERATION_IDENTITY,
            "service_version": HISTORICAL_OPERATION_VERSION,
            "service_available": True,
            "operation_available": self._operation.operation_available,
            "context_state": self._operation.actual_context_state,
            "active_operation_identity": self._operation.active_operation_identity,
            "last_result": (
                None
                if last_result is None
                else historical_operation_result_document(last_result)
            ),
        }

    def execute_document(self, payload: object) -> dict[str, object]:
        """Construct one governed request and call the existing typed harness."""

        if type(payload) is not dict or set(payload) != {
            "request_identity",
            "sessions",
            "maximum_provider_requests",
            "requested_at",
        }:
            raise ValueError("INTRADAY_HISTORICAL_CONTROL_REQUEST_INVALID")
        request_label = payload["request_identity"]
        session_values = payload["sessions"]
        maximum = payload["maximum_provider_requests"]
        requested_at_value = payload["requested_at"]
        if (
            type(request_label) is not str
            or _REQUEST_IDENTITY.fullmatch(request_label) is None
            or type(session_values) is not list
            or not session_values
            or type(maximum) is not int
            or type(requested_at_value) is not str
            or len(requested_at_value) > 64
        ):
            raise ValueError("INTRADAY_HISTORICAL_CONTROL_REQUEST_INVALID")
        try:
            sessions = tuple(_session(value) for value in session_values)
            requested_at = datetime.fromisoformat(requested_at_value)
            if requested_at.tzinfo is None or requested_at.utcoffset() is None:
                raise ValueError
            universe = self._operation.universe_publication
            request = create_historical_operation_request(
                universe_identity=universe.publication_identity,
                universe_version=universe.publication_version,
                universe_integrity_identity=universe.integrity_identity,
                sessions=sessions,
                boundary_family_identity=COMPLETED_SESSION_EOD_BOUNDARY_IDENTITY,
                boundary_family_version=COMPLETED_SESSION_EOD_BOUNDARY_VERSION,
                timeframes=HISTORICAL_OPERATION_TIMEFRAMES,
                maximum_provider_requests=maximum,
                requested_factual_families=REQUIRED_HISTORICAL_FACT_FAMILIES,
                requested_outcome_families=(),
                requested_at=requested_at,
                provenance=(
                    request_label,
                    INTRADAY_HISTORICAL_CONTROL_IDENTITY,
                    INTRADAY_HISTORICAL_CONTROL_VERSION,
                ),
            )
        except (ValueError, HistoricalOperationError) as error:
            raise ValueError(
                "INTRADAY_HISTORICAL_CONTROL_REQUEST_INVALID"
            ) from error
        return historical_operation_result_document(
            self._invocation.execute(request),
            request_identity=request.request_identity,
        )


def historical_operation_result_document(
    result: HistoricalQualificationOperationResult,
    *,
    request_identity: str | None = None,
) -> dict[str, object]:
    """Serialize bounded accounting and identities, never Provider payloads."""

    if type(result) is not HistoricalQualificationOperationResult:
        raise ValueError("INTRADAY_HISTORICAL_CONTROL_RESULT_INVALID")
    document: dict[str, object] = {
        "operation_identity": result.operation_identity,
        "state": result.state.value,
        "stage": result.stage.value,
        "context_state": result.context_state,
        "request_plan_identity": result.request_plan_identity,
        "subject_set_count": result.subject_set_count,
        "historically_resolvable_count": result.historically_resolvable_count,
        "prerequisite_unavailable_count": result.prerequisite_unavailable_count,
        "sessions_requested": result.sessions_requested,
        "sessions_valid": result.sessions_valid,
        "sessions_unavailable": result.sessions_unavailable,
        "subject_session_observations_planned": (
            result.subject_session_observations_planned
        ),
        "successful_reconstructions": result.successful_reconstructions,
        "factual_failures": result.factual_failures,
        "prerequisite_unavailable_observations": (
            result.prerequisite_unavailable_observations
        ),
        "narrow_cpr_true_count": result.narrow_cpr_true_count,
        "narrow_cpr_false_count": result.narrow_cpr_false_count,
        "narrow_cpr_unavailable_count": result.narrow_cpr_unavailable_count,
        "provider_request_ceiling": result.provider_request_ceiling,
        "provider_request_count": result.provider_request_count,
        "reconstruction_count": len(result.reconstruction_identities),
        "bundle_count": len(result.bundle_identities),
        "session_accounting": [
            {
                "session_identity": item.session_identity,
                "subject_set_count": item.subject_set_count,
                "historically_evaluable_count": item.historically_evaluable_count,
                "prerequisite_unavailable_count": (
                    item.prerequisite_unavailable_count
                ),
                "factual_success_count": item.factual_success_count,
                "factual_failure_count": item.factual_failure_count,
                "narrow_cpr_true_count": item.narrow_cpr_true_count,
                "narrow_cpr_false_count": item.narrow_cpr_false_count,
                "narrow_cpr_unavailable_count": item.narrow_cpr_unavailable_count,
            }
            for item in result.session_accounting
        ],
        "observation_failure_counts": [
            {"failure": name, "count": count}
            for name, count in result.observation_failure_counts
        ],
        "persistence_complete": result.persistence_complete,
        "reload_verified": result.reload_verified,
        "corpus_binding_performed": result.corpus_binding_performed,
        "production_state_mutated": result.production_state_mutated,
        "failure": None if result.failure is None else result.failure.value,
        "completed_at": result.completed_at.isoformat(),
    }
    if request_identity is not None:
        document["request_identity"] = request_identity
    return document


def _session(value: object) -> HistoricalOperationSessionRequest:
    if type(value) is not dict or set(value) != {
        "trading_date",
        "session_identity",
    }:
        raise ValueError("INTRADAY_HISTORICAL_CONTROL_REQUEST_INVALID")
    trading_date = value["trading_date"]
    session_identity = value["session_identity"]
    if (
        type(trading_date) is not str
        or len(trading_date) != 10
        or type(session_identity) is not str
        or not session_identity
        or session_identity != session_identity.strip()
    ):
        raise ValueError("INTRADAY_HISTORICAL_CONTROL_REQUEST_INVALID")
    return HistoricalOperationSessionRequest(
        trading_date=date.fromisoformat(trading_date),
        session_identity=session_identity,
    )


__all__ = [
    "HISTORICAL_OPERATION_IN_PROCESS_INVOCATION_UNAVAILABLE",
    "INTRADAY_HISTORICAL_CONTROL_IDENTITY",
    "INTRADAY_HISTORICAL_CONTROL_VERSION",
    "IntradayHistoricalQualificationOperationalControl",
    "historical_operation_result_document",
]
