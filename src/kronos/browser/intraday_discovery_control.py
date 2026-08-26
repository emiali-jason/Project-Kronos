"""Bounded loopback control projection for Intraday Discovery commissioning."""

from __future__ import annotations

from datetime import datetime
import re

from kronos.application.intraday_discovery import IntradayDiscoveryApplication
from kronos.application.intraday_discovery_operation import (
    DISCOVERY_PROBABLES_REFRESH_ORCHESTRATION_IDENTITY,
    DISCOVERY_PROBABLES_REFRESH_ORCHESTRATION_VERSION,
    DISCOVERY_OPERATION_SERVICE_IDENTITY,
    DISCOVERY_OPERATION_SERVICE_VERSION,
    DiscoveryOperationResult,
    IntradayDiscoveryOperationService,
    create_discovery_operation_request,
)
from kronos.intraday.probables_refresh import (
    DISCOVERY_PROBABLES_CONTRACT_VERSION,
    DISCOVERY_PROBABLES_MAPPING_IDENTITY,
)


INTRADAY_DISCOVERY_CONTROL_IDENTITY = (
    "KRONOS-INTRADAY-DISCOVERY-OPERATIONAL-CONTROL-V0"
)
INTRADAY_DISCOVERY_CONTROL_VERSION = "0.1.0"
DISCOVERY_OPERATIONAL_INVOCATION_SURFACE_UNAVAILABLE = (
    "DISCOVERY_OPERATIONAL_INVOCATION_SURFACE_UNAVAILABLE"
)
_REQUEST_IDENTITY = re.compile(r"[A-Z0-9][A-Z0-9._:-]{0,95}\Z")


class IntradayDiscoveryOperationalControl:
    """Project one exact Discovery service without owning HTTP transport."""

    __slots__ = ("_application", "_operation")

    def __init__(
        self,
        operation: IntradayDiscoveryOperationService,
        application: IntradayDiscoveryApplication,
    ) -> None:
        if (
            type(operation) is not IntradayDiscoveryOperationService
            or type(application) is not IntradayDiscoveryApplication
        ):
            raise ValueError("INTRADAY_DISCOVERY_CONTROL_INVALID")
        self._operation = operation
        self._application = application

    @property
    def operation_service(self) -> IntradayDiscoveryOperationService:
        """Return the composed service for local composition identity checks."""

        return self._operation

    def status_document(self) -> dict[str, object]:
        """Return current in-memory state without running Discovery or Provider."""

        snapshot = self._application.snapshot()
        probable = snapshot.probables
        diagnostics = (
            None if probable is None or probable.run is None else probable.run.diagnostics
        )
        last_result = self._operation.last_result
        return {
            "control_identity": INTRADAY_DISCOVERY_CONTROL_IDENTITY,
            "control_version": INTRADAY_DISCOVERY_CONTROL_VERSION,
            "service_identity": DISCOVERY_OPERATION_SERVICE_IDENTITY,
            "service_version": DISCOVERY_OPERATION_SERVICE_VERSION,
            "refresh_orchestration_identity": (
                DISCOVERY_PROBABLES_REFRESH_ORCHESTRATION_IDENTITY
            ),
            "refresh_orchestration_version": (
                DISCOVERY_PROBABLES_REFRESH_ORCHESTRATION_VERSION
            ),
            "probables_mapper_identity": DISCOVERY_PROBABLES_MAPPING_IDENTITY,
            "probables_mapper_version": DISCOVERY_PROBABLES_CONTRACT_VERSION,
            "service_available": True,
            "operation_available": self._operation.operation_available,
            "context_state": self._operation.actual_context_state,
            "active_operation_identity": self._operation.active_operation_identity,
            "last_result": (
                None if last_result is None else operation_result_document(last_result)
            ),
            "last_successful_run_identity": snapshot.last_successful_run_identity,
            "last_successful_analysis": _timestamp(snapshot.last_successful_analysis),
            "last_successful_probables_run_identity": (
                None if probable is None else probable.last_successful_run_identity
            ),
            "last_successful_probables_analysis": (
                None
                if probable is None
                else _timestamp(probable.last_successful_analysis)
            ),
            "probables_current_failure": (
                None if probable is None else probable.current_failure
            ),
            "long_probables": 0 if diagnostics is None else diagnostics.long_probables,
            "short_probables": 0 if diagnostics is None else diagnostics.short_probables,
            "total_probables": 0 if diagnostics is None else diagnostics.total_probables,
            "not_admitted": 0 if diagnostics is None else diagnostics.not_admitted_count,
            "unavailable": 0 if diagnostics is None else diagnostics.unavailable_count,
        }

    def execute_document(self, payload: object) -> dict[str, object]:
        """Validate the two-field control request and execute the composed service."""

        if type(payload) is not dict or set(payload) != {
            "request_identity",
            "observation_boundary",
        }:
            raise ValueError("INTRADAY_DISCOVERY_CONTROL_REQUEST_INVALID")
        request_identity = payload["request_identity"]
        observation_value = payload["observation_boundary"]
        if (
            type(request_identity) is not str
            or _REQUEST_IDENTITY.fullmatch(request_identity) is None
            or type(observation_value) is not str
            or len(observation_value) > 64
        ):
            raise ValueError("INTRADAY_DISCOVERY_CONTROL_REQUEST_INVALID")
        try:
            observation_boundary = datetime.fromisoformat(observation_value)
        except ValueError as error:
            raise ValueError("INTRADAY_DISCOVERY_CONTROL_REQUEST_INVALID") from error
        request = create_discovery_operation_request(
            observation_boundary=observation_boundary,
            request_identity=request_identity,
            requested_at=observation_boundary,
        )
        return operation_result_document(self._operation.execute(request))


def operation_result_document(result: DiscoveryOperationResult) -> dict[str, object]:
    """Serialize only the governed bounded result contract."""

    if type(result) is not DiscoveryOperationResult:
        raise ValueError("INTRADAY_DISCOVERY_CONTROL_RESULT_INVALID")
    return {
        "operation_identity": result.operation_identity,
        "state": result.state.value,
        "context_state": result.context_state,
        "stage": result.stage.value,
        "observation_boundary": result.observation_boundary.isoformat(),
        "universe_count": result.universe_count,
        "pre_evaluable_count": result.pre_evaluable_count,
        "prerequisite_unavailable_count": result.prerequisite_unavailable_count,
        "machine_fact_successes": result.machine_fact_successes,
        "machine_fact_failures": result.machine_fact_failures,
        "historical_request_count": result.historical_request_count,
        "run_identity": result.run_identity,
        "probables_run_identity": result.probables_run_identity,
        "probables_mapping_identity": result.probables_mapping_identity,
        "probables_invocation_count": result.probables_invocation_count,
        "probables_provider_request_count": result.probables_provider_request_count,
        "persistence_complete": result.persistence_complete,
        "snapshot_updated": result.snapshot_updated,
        "failure": None if result.failure is None else result.failure.value,
        "completed_at": result.completed_at.isoformat(),
    }


def _timestamp(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


__all__ = [
    "DISCOVERY_OPERATIONAL_INVOCATION_SURFACE_UNAVAILABLE",
    "INTRADAY_DISCOVERY_CONTROL_IDENTITY",
    "INTRADAY_DISCOVERY_CONTROL_VERSION",
    "IntradayDiscoveryOperationalControl",
    "operation_result_document",
]
