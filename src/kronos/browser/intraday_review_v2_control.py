"""Explicit same-process Browser control for Phase-A Intraday Review V2."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import re
from threading import Lock
from typing import Callable

from kronos.application.intraday_review_v2 import IntradayReviewV2Application
from kronos.intraday.review import ReviewError
from kronos.intraday.review_v2_operation import (
    REVIEW_V2_CREATE_REQUEST_IDENTITY,
    REVIEW_V2_CREATE_REQUEST_VERSION,
    REVIEW_V2_CREATE_ROUTE,
    ReviewV2CreateRequest,
    ReviewV2OperationOutcome,
    ReviewV2OperationSource,
    create_review_v2_provenance,
    create_review_v2_request,
)
from kronos.intraday.review_v2_operation_persistence import (
    ReviewV2OperationProvenanceStore,
)


INTRADAY_REVIEW_V2_CONTROL_IDENTITY = (
    "KRONOS-INTRADAY-REVIEW-V2-OPERATIONAL-CONTROL"
)
INTRADAY_REVIEW_V2_CONTROL_VERSION = "1.1.0"
REVIEW_V2_STATUS_ROUTE = "/control/intraday-review/v2/status"
MAX_REVIEW_V2_REQUEST_BYTES = 8192
_REQUEST_IDENTITY = re.compile(r"[A-Z0-9][A-Z0-9._:-]{0,95}\Z")
_REQUEST_FIELDS = {
    "request_identity",
    "probables_run_identity",
    "expected_methodology_identity",
    "expected_methodology_version",
    "expected_methodology_publication_identity",
    "expected_methodology_checksum",
    "requested_at",
    "source",
    "contract_identity",
    "contract_version",
}


class IntradayReviewV2OperationalControl:
    """Validate, serialize, invoke, and audit one exact V2 Review request."""

    def __init__(
        self,
        application: IntradayReviewV2Application,
        provenance_store: ReviewV2OperationProvenanceStore,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        process_identity: Callable[[], str] = lambda: f"KRONOS-BACKEND-PID-{os.getpid()}",
    ) -> None:
        if (
            type(application) is not IntradayReviewV2Application
            or type(provenance_store) is not ReviewV2OperationProvenanceStore
            or not callable(clock)
            or not callable(process_identity)
        ):
            raise ValueError("INTRADAY_REVIEW_V2_CONTROL_INVALID")
        self._application = application
        self._store = provenance_store
        self._clock = clock
        self._process_identity = process_identity
        self._operation_lock = Lock()
        self._state_lock = Lock()
        self._active_operation_identity: str | None = None

    @property
    def application(self) -> IntradayReviewV2Application:
        return self._application

    def status_document(self) -> dict[str, object]:
        with self._state_lock:
            active = self._active_operation_identity
        latest = self._store.latest()
        snapshot = self._application.snapshot()
        try:
            currentness = self._application.currentness()
            currentness_failure = None
        except ReviewError as error:
            currentness = None
            currentness_failure = error.failure.value
        state = (
            "RUNNING"
            if active is not None
            else "NOT_YET_RUN"
            if latest is None
            else "COMPLETE"
            if latest.outcome is ReviewV2OperationOutcome.COMPLETE
            else "LAST_FAILURE"
        )
        return {
            "control_identity": INTRADAY_REVIEW_V2_CONTROL_IDENTITY,
            "control_version": INTRADAY_REVIEW_V2_CONTROL_VERSION,
            "route_identity": REVIEW_V2_CREATE_ROUTE,
            "request_contract_identity": REVIEW_V2_CREATE_REQUEST_IDENTITY,
            "request_contract_version": REVIEW_V2_CREATE_REQUEST_VERSION,
            "state": state,
            "active_operation_identity": active,
            "source_probables_run_identity": snapshot.probables_run_identity,
            "cycle_count": len(snapshot.candidates),
            "cycle_identities": [item.cycle_identity for item in snapshot.candidates],
            "chart_required_count": sum(
                item.chart_state == "CHART_REQUIRED" for item in snapshot.candidates
            ),
            "currentness_state": (
                "INTEGRITY_INVALID" if currentness is None else currentness.state
            ),
            "currentness_failure": currentness_failure,
            "current_probables_run_identity": (
                None if currentness is None
                else currentness.current_probables_run_identity
            ),
            "current_probables_pointer_integrity": (
                None if currentness is None
                else currentness.current_probables_pointer_integrity
            ),
            "current_probables_publication_identity": (
                None if currentness is None
                else currentness.current_probables_publication_identity
            ),
            "current_probables_analysis_boundary": (
                None
                if currentness is None
                or currentness.current_probables_analysis_boundary is None
                else currentness.current_probables_analysis_boundary.isoformat()
            ),
            "current_probables_candidate_population_identity": (
                None if currentness is None
                else currentness.current_probables_candidate_population_identity
            ),
            "current_probables_candidate_count": (
                0 if currentness is None
                else currentness.current_probables_candidate_count
            ),
            "current_review_probables_run_identity": (
                None if currentness is None
                else currentness.current_review_probables_run_identity
            ),
            "current_review_analysis_boundary": (
                None
                if currentness is None
                or currentness.current_review_analysis_boundary is None
                else currentness.current_review_analysis_boundary.isoformat()
            ),
            "current_review_candidate_count": (
                0 if currentness is None
                else currentness.current_review_candidate_count
            ),
            "is_review_current": (
                False if currentness is None else currentness.is_review_current
            ),
            "last_operation": None if latest is None else _record_document(latest, False),
        }

    def execute_document(self, payload: object) -> dict[str, object]:
        received = self._clock()
        try:
            request = _parse_request(payload)
        except ValueError as error:
            record = self._rejection(payload, received, "REQUEST_VALIDATION", str(error))
            self._store.retain(record, primary=False)
            return _record_document(record, False)

        existing = self._store.load_for_request(request.request_identity)
        if existing is not None:
            if existing.request_integrity_identity == request.integrity_identity:
                return _record_document(existing, True, "REQUEST_REPLAY")
            record = self._record(
                request=request,
                received_at=received,
                started_at=None,
                completed_at=received,
                outcome=ReviewV2OperationOutcome.REJECTED,
                failure_stage="IDEMPOTENCY",
                failure_reason="INTRADAY_REVIEW_V2_REQUEST_IDENTITY_CONFLICT",
            )
            self._store.retain(record, primary=False)
            return _record_document(record, False)

        if not self._operation_lock.acquire(blocking=False):
            record = self._record(
                request=request,
                received_at=received,
                started_at=None,
                completed_at=received,
                outcome=ReviewV2OperationOutcome.REJECTED,
                failure_stage="CONCURRENCY",
                failure_reason="INTRADAY_REVIEW_V2_OPERATION_CONFLICT",
            )
            self._store.retain(record, primary=False)
            return _record_document(record, False)

        with self._state_lock:
            self._active_operation_identity = request.request_identity
        started = self._clock()
        try:
            result = self._application.currentize_eligible_cycles_for_run_identity(
                probables_run_identity=request.probables_run_identity,
                methodology_identity=request.expected_methodology_identity,
                methodology_version=request.expected_methodology_version,
                methodology_publication_identity=(
                    request.expected_methodology_publication_identity
                ),
                methodology_checksum=request.expected_methodology_checksum,
            )
            record = self._record(
                request=request,
                received_at=received,
                started_at=started,
                completed_at=self._clock(),
                outcome=ReviewV2OperationOutcome.COMPLETE,
                cycle_identities=tuple(
                    cycle.cycle_identity for cycle in result.cycles
                ),
            )
            self._store.retain(record)
            return _record_document(
                record,
                result.retained,
                "ALREADY_CURRENT" if result.retained else "CURRENTIZED",
            )
        except ReviewError as error:
            stage = {
                "INTRADAY_REVIEW_NOT_CURRENT": "PROBABLES_CURRENTNESS",
                "INTRADAY_REVIEW_ARTIFACT_UNAVAILABLE": "PROBABLES_RELOAD",
                "INTRADAY_REVIEW_INTEGRITY_INVALID": "PROBABLES_RELOAD",
                "INTRADAY_REVIEW_NOT_ELIGIBLE": "REVIEW_INTAKE_CONSTRUCTION",
                "INTRADAY_REVIEW_PERSISTENCE_CONFLICT": "PERSISTENCE",
            }.get(error.failure.value, "REVIEW_INTAKE_CONSTRUCTION")
            record = self._record(
                request=request,
                received_at=received,
                started_at=started,
                completed_at=self._clock(),
                outcome=ReviewV2OperationOutcome.FAILED,
                failure_stage=stage,
                failure_reason=error.failure.value,
            )
            self._store.retain(record)
            return _record_document(record, False)
        except (OSError, ValueError):
            record = self._record(
                request=request,
                received_at=received,
                started_at=started,
                completed_at=self._clock(),
                outcome=ReviewV2OperationOutcome.FAILED,
                failure_stage="PERSISTENCE",
                failure_reason="INTRADAY_REVIEW_V2_PERSISTENCE_FAILED",
            )
            self._store.retain(record)
            return _record_document(record, False)
        finally:
            with self._state_lock:
                self._active_operation_identity = None
            self._operation_lock.release()

    def _rejection(
        self,
        payload: object,
        received: datetime,
        stage: str,
        reason: str,
    ):
        digest = sha256(_safe_payload(payload)).hexdigest().upper()
        request_identity = f"REJECTED-V2-REVIEW-REQUEST-{digest}"
        if type(payload) is dict and _valid_request_identity(payload.get("request_identity")):
            request_identity = payload["request_identity"]
        return create_review_v2_provenance(
            request_identity=request_identity,
            request_integrity_identity=f"REJECTED-V2-REVIEW-CONTENT-{digest}",
            route_identity=REVIEW_V2_CREATE_ROUTE,
            source=ReviewV2OperationSource.SPONSOR_BROWSER_CONTROL,
            backend_process_identity=self._process_identity(),
            received_at=received,
            operation_started_at=None,
            operation_completed_at=received,
            probables_run_identity=None,
            methodology_identity=None,
            methodology_version=None,
            methodology_publication_identity=None,
            methodology_checksum=None,
            cycle_identities=(),
            outcome=ReviewV2OperationOutcome.REJECTED,
            failure_stage=stage,
            failure_reason=reason,
        )

    def _record(
        self,
        *,
        request: ReviewV2CreateRequest,
        received_at: datetime,
        started_at: datetime | None,
        completed_at: datetime,
        outcome: ReviewV2OperationOutcome,
        cycle_identities: tuple[str, ...] = (),
        failure_stage: str | None = None,
        failure_reason: str | None = None,
    ):
        return create_review_v2_provenance(
            request_identity=request.request_identity,
            request_integrity_identity=request.integrity_identity,
            route_identity=REVIEW_V2_CREATE_ROUTE,
            source=request.source,
            backend_process_identity=self._process_identity(),
            received_at=received_at,
            operation_started_at=started_at,
            operation_completed_at=completed_at,
            probables_run_identity=request.probables_run_identity,
            methodology_identity=request.expected_methodology_identity,
            methodology_version=request.expected_methodology_version,
            methodology_publication_identity=request.expected_methodology_publication_identity,
            methodology_checksum=request.expected_methodology_checksum,
            cycle_identities=cycle_identities,
            outcome=outcome,
            failure_stage=failure_stage,
            failure_reason=failure_reason,
        )


def _parse_request(payload: object) -> ReviewV2CreateRequest:
    if type(payload) is not dict or set(payload) != _REQUEST_FIELDS:
        raise ValueError("INTRADAY_REVIEW_V2_REQUEST_CONTRACT_INVALID")
    if (
        payload["source"] != ReviewV2OperationSource.SPONSOR_BROWSER_CONTROL.value
        or payload["contract_identity"] != REVIEW_V2_CREATE_REQUEST_IDENTITY
        or payload["contract_version"] != REVIEW_V2_CREATE_REQUEST_VERSION
        or not _valid_request_identity(payload["request_identity"])
    ):
        raise ValueError("INTRADAY_REVIEW_V2_REQUEST_CONTRACT_INVALID")
    try:
        requested_at = datetime.fromisoformat(payload["requested_at"])
    except (TypeError, ValueError) as error:
        raise ValueError("INTRADAY_REVIEW_V2_REQUEST_TIMESTAMP_INVALID") from error
    try:
        return create_review_v2_request(
            request_identity=payload["request_identity"],
            probables_run_identity=payload["probables_run_identity"],
            expected_methodology_identity=payload["expected_methodology_identity"],
            expected_methodology_version=payload["expected_methodology_version"],
            expected_methodology_publication_identity=(
                payload["expected_methodology_publication_identity"]
            ),
            expected_methodology_checksum=payload["expected_methodology_checksum"],
            requested_at=requested_at,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("INTRADAY_REVIEW_V2_REQUEST_CONTRACT_INVALID") from error


def _record_document(
    record,
    idempotent: bool,
    currentization_state: str | None = None,
) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "provenance_identity": record.provenance_identity,
        "request_identity": record.request_identity,
        "source": record.source.value,
        "probables_run_identity": record.probables_run_identity,
        "methodology_identity": record.methodology_identity,
        "methodology_version": record.methodology_version,
        "methodology_publication_identity": record.methodology_publication_identity,
        "methodology_checksum": record.methodology_checksum,
        "cycle_count": len(record.cycle_identities),
        "cycle_identities": list(record.cycle_identities),
        "chart_required_count": len(record.cycle_identities),
        "review_pack_count": 0,
        "question_pack_count": 0,
        "outcome": record.outcome.value,
        "failure_stage": record.failure_stage,
        "failure_reason": record.failure_reason,
        "idempotent": idempotent,
        "currentization_state": currentization_state,
        "completed_at": record.operation_completed_at.isoformat(),
    }


def _valid_request_identity(value: object) -> bool:
    return type(value) is str and _REQUEST_IDENTITY.fullmatch(value) is not None


def _safe_payload(payload: object) -> bytes:
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    except (TypeError, ValueError):
        return type(payload).__name__.encode()


__all__ = [
    "INTRADAY_REVIEW_V2_CONTROL_IDENTITY",
    "INTRADAY_REVIEW_V2_CONTROL_VERSION",
    "MAX_REVIEW_V2_REQUEST_BYTES",
    "REVIEW_V2_STATUS_ROUTE",
    "IntradayReviewV2OperationalControl",
]
