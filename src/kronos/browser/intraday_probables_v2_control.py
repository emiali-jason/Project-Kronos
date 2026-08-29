"""Explicit version-bound Browser control for Intraday Probables V2 Refresh."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import re
from typing import Callable

from kronos.application.intraday_discovery_operation import (
    DiscoveryOperationResult,
    DiscoveryOperationState,
    IntradayDiscoveryOperationService,
    create_discovery_operation_request,
)
from kronos.application.intraday_probables_v2 import IntradayProbablesV2Application
from kronos.intraday.probables_v2 import (
    PROBABLES_V2_METHODOLOGY_IDENTITY,
    PROBABLES_V2_SUCCESSOR_METHODOLOGY_CHECKSUM as PROBABLES_V2_METHODOLOGY_CHECKSUM,
    PROBABLES_V2_SUCCESSOR_METHODOLOGY_VERSION as PROBABLES_V2_METHODOLOGY_VERSION,
    PROBABLES_V2_SUCCESSOR_PUBLICATION_IDENTITY as PROBABLES_V2_PUBLICATION_IDENTITY,
)
from kronos.intraday.refresh_v2 import (
    REFRESH_V2_OPERATION_TYPE,
    REFRESH_V2_REQUEST_IDENTITY,
    REFRESH_V2_REQUEST_VERSION,
    REFRESH_V2_ROUTE,
    RefreshV2Outcome,
    RefreshV2ProvenanceRecord,
    RefreshV2SourceClass,
    create_refresh_v2_provenance,
    create_refresh_v2_request,
)
from kronos.intraday.refresh_v2_persistence import RefreshV2ProvenanceStore


INTRADAY_PROBABLES_V2_CONTROL_IDENTITY = (
    "KRONOS-INTRADAY-PROBABLES-V2-OPERATIONAL-CONTROL"
)
INTRADAY_PROBABLES_V2_CONTROL_VERSION = "1.0.0"
_REQUEST_IDENTITY = re.compile(r"[A-Z0-9][A-Z0-9._:-]{0,95}\Z")
_REQUEST_FIELDS = {
    "request_identity",
    "observation_boundary",
    "request_created_at",
    "source_class",
    "contract_identity",
    "contract_version",
    "methodology_identity",
    "methodology_version",
    "methodology_publication_identity",
    "methodology_checksum",
    "operation_type",
}


class IntradayProbablesV2OperationalControl:
    """Validate, deduplicate, invoke, and audit exactly one V2 request."""

    def __init__(
        self,
        operation: IntradayDiscoveryOperationService,
        probables: IntradayProbablesV2Application,
        provenance_store: RefreshV2ProvenanceStore,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        process_identity: Callable[[], str] = lambda: f"KRONOS-BACKEND-PID-{os.getpid()}",
    ) -> None:
        if (
            type(operation) is not IntradayDiscoveryOperationService
            or type(probables) is not IntradayProbablesV2Application
            or type(provenance_store) is not RefreshV2ProvenanceStore
            or not callable(clock)
            or not callable(process_identity)
        ):
            raise ValueError("INTRADAY_PROBABLES_V2_CONTROL_INVALID")
        self._operation = operation
        self._probables = probables
        self._store = provenance_store
        self._clock = clock
        self._process_identity = process_identity

    @property
    def operation_service(self) -> IntradayDiscoveryOperationService:
        return self._operation

    def status_document(self) -> dict[str, object]:
        snapshot = self._probables.snapshot()
        last = self._operation.last_result
        latest_provenance = self._store.latest()
        latest_failure = (
            None
            if latest_provenance is None
            or latest_provenance.outcome is RefreshV2Outcome.SUCCESS
            else latest_provenance.failure
        )
        return {
            "control_identity": INTRADAY_PROBABLES_V2_CONTROL_IDENTITY,
            "control_version": INTRADAY_PROBABLES_V2_CONTROL_VERSION,
            "route_identity": REFRESH_V2_ROUTE,
            "methodology_identity": PROBABLES_V2_METHODOLOGY_IDENTITY,
            "methodology_version": PROBABLES_V2_METHODOLOGY_VERSION,
            "methodology_publication_identity": PROBABLES_V2_PUBLICATION_IDENTITY,
            "methodology_checksum": PROBABLES_V2_METHODOLOGY_CHECKSUM,
            "operation_available": self._operation.operation_available,
            "context_state": self._operation.actual_context_state,
            "active_operation_identity": self._operation.active_operation_identity,
            "state": (
                "RUNNING"
                if self._operation.active_operation_identity is not None
                else "LAST_FAILURE"
                if snapshot.current_failure is not None or latest_failure is not None
                else "LAST_SUCCESSFUL_ANALYSIS"
                if snapshot.run is not None
                else "NOT_YET_RUN"
            ),
            "last_result": None if last is None else _operation_document(last),
            "last_successful_discovery_identity": snapshot.last_successful_discovery_run_identity,
            "last_successful_probables_identity": snapshot.last_successful_run_identity,
            "last_successful_analysis": (
                None if snapshot.last_successful_analysis is None
                else snapshot.last_successful_analysis.isoformat()
            ),
            "current_failure": snapshot.current_failure or latest_failure,
            "failure_detail": (
                None
                if snapshot.failure_detail is None
                else _failure_detail_document(snapshot.failure_detail)
            ),
        }

    def execute_document(self, payload: object) -> dict[str, object]:
        received = self._clock()
        try:
            request = _parse_request(payload)
        except ValueError as error:
            record = self._rejection(payload, received, str(error))
            self._store.retain(record, primary=False)
            return _record_document(record, idempotent=False)
        existing = self._store.load_for_request(request.request_identity)
        if existing is not None:
            if existing.request_integrity_identity == request.integrity_identity:
                return _record_document(existing, idempotent=True)
            record = self._record(
                request_identity=request.request_identity,
                request_integrity_identity=request.integrity_identity,
                observation_boundary=request.observation_boundary,
                received_at=received,
                operation_started_at=None,
                operation_completed_at=received,
                outcome=RefreshV2Outcome.REJECTED,
                failure="INTRADAY_PROBABLES_V2_REQUEST_IDENTITY_CONFLICT",
            )
            self._store.retain(record, primary=False)
            return _record_document(record, idempotent=False)
        started = self._clock()
        operation_request = create_discovery_operation_request(
            observation_boundary=request.observation_boundary,
            request_identity=request.request_identity,
            requested_at=request.request_created_at,
        )
        result = self._operation.execute(operation_request)
        completed = self._clock()
        success = result.state is DiscoveryOperationState.COMPLETE
        outcome = (
            RefreshV2Outcome.SUCCESS
            if success
            else RefreshV2Outcome.REJECTED
            if result.state is DiscoveryOperationState.CONFLICT
            else RefreshV2Outcome.FAILED
        )
        record = self._record(
            request_identity=request.request_identity,
            request_integrity_identity=request.integrity_identity,
            observation_boundary=request.observation_boundary,
            received_at=received,
            operation_started_at=started,
            operation_completed_at=completed,
            outcome=outcome,
            failure=None if result.failure is None else result.failure.value,
            resulting_refresh_identity=(
                None if not success else _refresh_identity(request.integrity_identity, result)
            ),
            resulting_discovery_identity=result.run_identity,
            resulting_probables_identity=result.probables_run_identity,
            replay_envelope_identity=result.replay_envelope_identity,
            failure_detail_identity=result.failure_detail_identity,
        )
        self._store.retain(record)
        return _record_document(record, idempotent=False)

    def _rejection(
        self, payload: object, received: datetime, failure: str
    ) -> RefreshV2ProvenanceRecord:
        digest = sha256(_safe_payload(payload)).hexdigest().upper()
        request_identity = f"REJECTED-V2-REQUEST-{digest}"
        if type(payload) is dict and _valid_request_identity(payload.get("request_identity")):
            request_identity = payload["request_identity"]
        return self._record(
            request_identity=request_identity,
            request_integrity_identity=f"REJECTED-V2-CONTENT-{digest}",
            observation_boundary=None,
            received_at=received,
            operation_started_at=None,
            operation_completed_at=received,
            outcome=RefreshV2Outcome.REJECTED,
            failure=failure,
        )

    def _record(
        self,
        *,
        request_identity: str,
        request_integrity_identity: str,
        observation_boundary: datetime | None,
        received_at: datetime,
        operation_started_at: datetime | None,
        operation_completed_at: datetime,
        outcome: RefreshV2Outcome,
        failure: str | None,
        resulting_refresh_identity: str | None = None,
        resulting_discovery_identity: str | None = None,
        resulting_probables_identity: str | None = None,
        replay_envelope_identity: str | None = None,
        failure_detail_identity: str | None = None,
    ) -> RefreshV2ProvenanceRecord:
        return create_refresh_v2_provenance(
            request_identity=request_identity,
            request_integrity_identity=request_integrity_identity,
            route_identity=REFRESH_V2_ROUTE,
            methodology_identity=PROBABLES_V2_METHODOLOGY_IDENTITY,
            methodology_version=PROBABLES_V2_METHODOLOGY_VERSION,
            methodology_publication_identity=PROBABLES_V2_PUBLICATION_IDENTITY,
            methodology_checksum=PROBABLES_V2_METHODOLOGY_CHECKSUM,
            observation_boundary=observation_boundary,
            received_at=received_at,
            operation_started_at=operation_started_at,
            operation_completed_at=operation_completed_at,
            resulting_refresh_identity=resulting_refresh_identity,
            resulting_discovery_identity=resulting_discovery_identity,
            resulting_probables_identity=resulting_probables_identity,
            replay_envelope_identity=replay_envelope_identity,
            failure_detail_identity=failure_detail_identity,
            outcome=outcome,
            failure=failure,
            source_class=RefreshV2SourceClass.SPONSOR_BROWSER_CONTROL,
            backend_process_identity=self._process_identity(),
            remote_address_class="LOOPBACK_ADMITTED",
            origin_validation="PASSED_BY_SHARED_BROWSER_ADMISSION",
            host_validation="PASSED_BY_SHARED_BROWSER_ADMISSION",
        )


def _parse_request(payload: object):  # type: ignore[no-untyped-def]
    if type(payload) is not dict or set(payload) != _REQUEST_FIELDS:
        raise ValueError("INTRADAY_PROBABLES_V2_REQUEST_CONTRACT_INVALID")
    expected = {
        "source_class": RefreshV2SourceClass.SPONSOR_BROWSER_CONTROL.value,
        "contract_identity": REFRESH_V2_REQUEST_IDENTITY,
        "contract_version": REFRESH_V2_REQUEST_VERSION,
        "methodology_identity": PROBABLES_V2_METHODOLOGY_IDENTITY,
        "methodology_version": PROBABLES_V2_METHODOLOGY_VERSION,
        "methodology_publication_identity": PROBABLES_V2_PUBLICATION_IDENTITY,
        "methodology_checksum": PROBABLES_V2_METHODOLOGY_CHECKSUM,
        "operation_type": REFRESH_V2_OPERATION_TYPE,
    }
    if any(payload[name] != value for name, value in expected.items()):
        raise ValueError("INTRADAY_PROBABLES_V2_METHODOLOGY_BINDING_INVALID")
    if not _valid_request_identity(payload["request_identity"]):
        raise ValueError("INTRADAY_PROBABLES_V2_REQUEST_IDENTITY_INVALID")
    try:
        observation = datetime.fromisoformat(payload["observation_boundary"])
        created = datetime.fromisoformat(payload["request_created_at"])
    except (TypeError, ValueError) as error:
        raise ValueError("INTRADAY_PROBABLES_V2_REQUEST_BOUNDARY_INVALID") from error
    return create_refresh_v2_request(
        request_identity=payload["request_identity"],
        observation_boundary=observation,
        request_created_at=created,
    )


def _record_document(
    record: RefreshV2ProvenanceRecord, *, idempotent: bool
) -> dict[str, object]:
    return {
        "provenance_identity": record.provenance_identity,
        "request_identity": record.request_identity,
        "route_identity": record.route_identity,
        "outcome": record.outcome.value,
        "failure": record.failure,
        "resulting_refresh_identity": record.resulting_refresh_identity,
        "resulting_discovery_identity": record.resulting_discovery_identity,
        "resulting_probables_identity": record.resulting_probables_identity,
        "replay_envelope_identity": record.replay_envelope_identity,
        "failure_detail_identity": record.failure_detail_identity,
        "operation_completed_at": record.operation_completed_at.isoformat(),
        "idempotent": idempotent,
    }


def _operation_document(result: DiscoveryOperationResult) -> dict[str, object]:
    return {
        "operation_identity": result.operation_identity,
        "state": result.state.value,
        "stage": result.stage.value,
        "failure": None if result.failure is None else result.failure.value,
        "run_identity": result.run_identity,
        "probables_run_identity": result.probables_run_identity,
        "replay_envelope_identity": result.replay_envelope_identity,
        "failure_detail_identity": result.failure_detail_identity,
    }


def _failure_detail_document(detail) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "failure_identity": detail.failure_identity,
        "stage": detail.operation_stage,
        "reason": detail.typed_reason_code,
        "affected": detail.affected_canonical_subject_identity,
    }


def _refresh_identity(request_integrity: str, result: DiscoveryOperationResult) -> str:
    payload = json.dumps({
        "request_integrity": request_integrity,
        "discovery": result.run_identity,
        "probables": result.probables_run_identity,
    }, sort_keys=True, separators=(",", ":")).encode()
    return "INTRADAY-PROBABLES-V2-REFRESH-" + sha256(payload).hexdigest().upper()


def _valid_request_identity(value: object) -> bool:
    return type(value) is str and _REQUEST_IDENTITY.fullmatch(value) is not None


def _safe_payload(payload: object) -> bytes:
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    except (TypeError, ValueError):
        return repr(type(payload).__name__).encode()


__all__ = [
    "INTRADAY_PROBABLES_V2_CONTROL_IDENTITY",
    "INTRADAY_PROBABLES_V2_CONTROL_VERSION",
    "IntradayProbablesV2OperationalControl",
]
