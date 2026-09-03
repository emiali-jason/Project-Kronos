"""Exact Sponsor control and inert status projection for Intraday WO-17."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from threading import RLock
import types
from typing import get_args, get_origin, get_type_hints

from kronos.application.intraday_wo17 import (
    IntradayWo17Application,
    IntradayWo17RestorationService,
    Wo17ApplicationError,
    Wo17BusyOutcome,
    Wo17OperationRequest,
)
from kronos.intraday.wo17 import (
    WO17_POLICY_CHECKSUM,
    WO17_POLICY_IDENTITY,
    WO17_POLICY_VERSION,
    Wo17ContractError,
)
from kronos.intraday.wo17_persistence import (
    RestoredWo17State,
    Wo17PersistenceError,
    Wo17RestorationState,
)
from kronos.intraday.wo16_persistence import Wo16Store


WO17_CONTROL_ROUTE = "/control/intraday-wo17"
WO17_STATUS_ROUTE = "/control/intraday-wo17/status"
WO17_PRODUCT_ROUTE = "/intraday/wo17"
WO17_CONTROL_IDENTITY = "KRONOS-INTRADAY-WO17-LIFECYCLE-CONTROL-V1"
WO17_CONTROL_VERSION = "1.0.0"
MAX_WO17_REQUEST_BYTES = 524_288


class _Wo17ControlError(ValueError):
    pass


class IntradayWo17OperationalControl:
    """Admit exact WO-17 graphs bound to the current WO-16 pointer."""

    def __init__(
        self,
        application: IntradayWo17Application,
        restoration: IntradayWo17RestorationService,
        *,
        wo16_store: Wo16Store,
        monitoring: object | None = None,
    ) -> None:
        if (
            type(application) is not IntradayWo17Application
            or type(restoration) is not IntradayWo17RestorationService
            or type(wo16_store) is not Wo16Store
        ):
            raise ValueError("WO17_OPERATIONAL_CONTROL_INVALID")
        self._application = application
        self._restoration_service = restoration
        self._wo16_store = wo16_store
        self._monitoring = monitoring
        self._lock = RLock()
        self._restoration = restoration.restore()
        self._active_request_identity: str | None = None
        self._last_operation: dict[str, object] | None = None
        self._sponsor_operations = 0
        self._positions_created = 0
        self._positions_closed = 0

    @property
    def application(self) -> IntradayWo17Application:
        return self._application

    def status_document(self) -> dict[str, object]:
        latest_restoration = self._restoration_service.restore()
        with self._lock:
            self._restoration = latest_restoration
            restoration = latest_restoration
            active = self._active_request_identity
            last = self._last_operation
            sponsor_operations = self._sponsor_operations
            positions_created = self._positions_created
            positions_closed = self._positions_closed
        currents = [_state_document(item) for item in restoration.restored]
        history = [
            _history_document(pointer)
            for item in restoration.restored
            for pointer in item.history
        ]
        failures = [_failure_projection(item) for item in restoration.latest_failures]
        monitoring = (
            self._monitoring.status_document()
            if callable(getattr(self._monitoring, "status_document", None))
            else {
                "state": "NOT_APPLICABLE",
                "bindings": [],
                "provider_calls": 0,
                "order_updates_ignored": 0,
                "autonomous_operations": 0,
            }
        )
        event_count = sum(
            0 if item.closure is None else len(item.closure.events)
            for item in restoration.restored
        )
        return {
            "control_identity": WO17_CONTROL_IDENTITY,
            "control_version": WO17_CONTROL_VERSION,
            "runtime_loaded": True,
            "restoration_state": restoration.state.value,
            "operation_state": "BUSY" if active is not None else "IDLE",
            "busy": active is not None,
            "active_request_identity": active,
            "current_positions": currents,
            "position_history": history,
            "immutable_event_count": event_count,
            "last_operation": last,
            "latest_persisted_failures": failures,
            "failure_stage": restoration.failure_stage,
            "failure_reason": restoration.failure_reason,
            "monitoring": monitoring,
            "policy_identity": WO17_POLICY_IDENTITY,
            "policy_version": WO17_POLICY_VERSION,
            "policy_checksum": WO17_POLICY_CHECKSUM,
            "provider_analytical_calls": 0,
            "sponsor_operations": sponsor_operations,
            "autonomous_operations": monitoring.get("autonomous_operations", 0),
            "broker_operations": 0,
            "notification_deliveries": 0,
            "positions_created": positions_created,
            "positions_closed": positions_closed,
            "persistence_writes_from_get": 0,
        }

    def execute_document(self, payload: object) -> dict[str, object]:
        try:
            request = _parse_operation(payload)
        except Exception as error:
            document = _failure_document(
                payload, "REQUEST_VALIDATION", _failure_code(error), "REJECTED"
            )
            self._record(document)
            return document
        with self._lock:
            if self._active_request_identity is not None:
                document = _failure_document(
                    payload, "CONCURRENCY", "WO17_OPERATION_BUSY", "BUSY"
                )
                self._record(document)
                return document
            self._active_request_identity = request.request_identity
            self._sponsor_operations += 1
        try:
            self._validate_current_upstream(request)
            previous = self._application.store.restore_current(
                request.canonical_subject_identity
            )
            execution = self._application.execute(request)
            if type(execution) is Wo17BusyOutcome:
                document = _failure_document(
                    payload, "CONCURRENCY", "WO17_OPERATION_BUSY", "BUSY"
                )
            else:
                restoration = self._restoration_service.restore()
                restored = next(
                    (
                        item
                        for item in restoration.restored
                        if item.pointer.canonical_subject_identity
                        == request.canonical_subject_identity
                    ),
                    None,
                )
                if (
                    restoration.state is not Wo17RestorationState.LOADED
                    or restored is None
                    or restored.pointer != execution.pointer
                    or restored.request != request
                ):
                    raise Wo17ApplicationError("WO17_POST_EXECUTION_RESTORE_FAILED")
                with self._lock:
                    self._restoration = restoration
                    if not execution.replayed:
                        if (
                            previous is None
                            or previous.position.position_evidence is None
                        ) and request.position.position_evidence is not None:
                            self._positions_created += 1
                        if (
                            (previous is None or previous.pointer.closure_identity is None)
                            and execution.pointer.closure_identity is not None
                        ):
                            self._positions_closed += 1
                document = {
                    "request_identity": request.request_identity,
                    "outcome": "RETAINED" if execution.replayed else "COMPLETED",
                    "idempotent": execution.replayed,
                    "failure_stage": None,
                    "failure_reason": None,
                    "position": _state_document(restored),
                }
        except Exception as error:
            reason = _failure_code(error)
            restoration = self._restoration_service.restore()
            with self._lock:
                self._restoration = restoration
            document = _failure_document(
                payload,
                "CONCURRENCY" if reason == "WO17_OPERATION_BUSY" else "APPLICATION",
                reason,
                "BUSY" if reason == "WO17_OPERATION_BUSY" else "FAILED",
            )
        finally:
            with self._lock:
                self._active_request_identity = None
        self._record(document)
        return document

    def _validate_current_upstream(self, request: Wo17OperationRequest) -> None:
        lineage = request.snapshot.lineage
        current = self._wo16_store.load_current(lineage.canonical_subject_identity)
        if current is None:
            raise _Wo17ControlError("WO16_CURRENT_DECISION_UNAVAILABLE")
        if (
            current.pointer_identity != lineage.current_wo16_pointer_identity
            or current.pointer_integrity != lineage.current_wo16_pointer_integrity
            or current.snapshot_identity != lineage.wo16_snapshot_identity
            or current.snapshot_integrity != lineage.wo16_snapshot_integrity
            or current.decision_identity != lineage.wo16_decision_identity
            or current.decision_integrity != lineage.wo16_decision_integrity
            or current.admission_identity != lineage.wo16_admission_identity
            or current.admission_integrity != lineage.wo16_admission_integrity
        ):
            raise _Wo17ControlError("WO16_NOT_CURRENT")

    def _record(self, document: dict[str, object]) -> None:
        with self._lock:
            self._last_operation = {
                key: document.get(key)
                for key in (
                    "request_identity",
                    "outcome",
                    "failure_stage",
                    "failure_reason",
                )
            }


def operation_document(request: Wo17OperationRequest) -> dict[str, object]:
    if type(request) is not Wo17OperationRequest:
        raise ValueError("WO17_OPERATION_DOCUMENT_INVALID")
    return {"request": _wire(request)}


def _parse_operation(payload: object) -> Wo17OperationRequest:
    if type(payload) is not dict or set(payload) != {"request"}:
        raise ValueError("WO17_REQUEST_CONTRACT_INVALID")
    result = _parse_value(payload["request"], Wo17OperationRequest)
    if type(result) is not Wo17OperationRequest:
        raise ValueError("WO17_REQUEST_CONTRACT_INVALID")
    return result


def _parse_value(raw: object, expected: object) -> object:
    origin = get_origin(expected)
    args = get_args(expected)
    if raw is None and (expected is type(None) or expected is None):
        return None
    if origin in {types.UnionType, getattr(types, "UnionType", object)}:
        if raw is None and type(None) in args:
            return None
        for candidate in (item for item in args if item is not type(None)):
            try:
                return _parse_value(raw, candidate)
            except (TypeError, ValueError):
                continue
        raise ValueError("WO17_REQUEST_CONTRACT_INVALID")
    if origin is tuple:
        if type(raw) is not list:
            raise ValueError("WO17_REQUEST_CONTRACT_INVALID")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_parse_value(item, args[0]) for item in raw)
        if len(raw) != len(args):
            raise ValueError("WO17_REQUEST_CONTRACT_INVALID")
        return tuple(
            _parse_value(item, item_type)
            for item, item_type in zip(raw, args, strict=True)
        )
    if expected is datetime:
        if type(raw) is not str:
            raise ValueError("WO17_REQUEST_CONTRACT_INVALID")
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("WO17_REQUEST_CONTRACT_INVALID")
        return value
    if expected is date:
        if type(raw) is not str:
            raise ValueError("WO17_REQUEST_CONTRACT_INVALID")
        return date.fromisoformat(raw)
    if expected is timedelta:
        if type(raw) is not str:
            raise ValueError("WO17_REQUEST_CONTRACT_INVALID")
        return timedelta(seconds=Decimal(raw))
    if expected is Decimal:
        if type(raw) is not str:
            raise ValueError("WO17_REQUEST_CONTRACT_INVALID")
        return Decimal(raw)
    if isinstance(expected, type) and issubclass(expected, StrEnum):
        if type(raw) is not str:
            raise ValueError("WO17_REQUEST_CONTRACT_INVALID")
        return expected(raw)
    if expected in {str, int, bool}:
        if type(raw) is not expected:
            raise ValueError("WO17_REQUEST_CONTRACT_INVALID")
        return raw
    if isinstance(expected, type) and is_dataclass(expected):
        if type(raw) is not dict:
            raise ValueError("WO17_REQUEST_CONTRACT_INVALID")
        expected_fields = {item.name for item in fields(expected)}
        if set(raw) != expected_fields:
            raise ValueError("WO17_REQUEST_CONTRACT_INVALID")
        hints = get_type_hints(expected)
        return expected(
            **{
                item.name: _parse_value(raw[item.name], hints[item.name])
                for item in fields(expected)
            }
        )
    raise TypeError("WO17_REQUEST_CONTRACT_INVALID")


def _wire(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _wire(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return format(Decimal(str(value.total_seconds())), "f")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, tuple):
        return [_wire(item) for item in value]
    if value is None or type(value) in {str, int, bool}:
        return value
    raise ValueError("WO17_OPERATION_DOCUMENT_INVALID")


def _state_document(restored: RestoredWo17State) -> dict[str, object]:
    request = restored.request
    lineage = restored.snapshot.lineage
    position = request.position
    evidence = position.position_evidence
    lifecycle = request.lifecycle
    closure = request.closure
    return {
        "canonical_subject_identity": lineage.canonical_subject_identity,
        "market_family": lineage.market_family.value,
        "instrument_identity": lineage.instrument_identity,
        "actual_contract_identity": lineage.actual_contract_identity,
        "contract_expiry": None if lineage.contract_expiry is None else lineage.contract_expiry.isoformat(),
        "roll_lineage_identity": lineage.roll_lineage_identity,
        "trading_date": lineage.trading_date.isoformat(),
        "session_identity": lineage.session_identity,
        "trade_plan": {
            "trade_plan_identity": lineage.wo13_trade_plan_identity,
            "trade_plan_integrity": lineage.wo13_trade_plan_integrity,
            "direction": lineage.direction.value,
            "setup_family": lineage.setup_family.value,
            "entry_reference": format(lineage.entry_reference, "f"),
            "entry_condition": lineage.entry_condition,
            "stop": format(lineage.stop, "f"),
            "thesis_invalidation_reference": format(
                lineage.thesis_invalidation_reference, "f"
            ),
            "thesis_invalidation_event": lineage.thesis_invalidation_event,
            "canonical_target": format(lineage.canonical_target, "f"),
            "model_rr": format(lineage.model_rr, "f"),
        },
        "risk_observation": {
            "observation_identity": lineage.wo14_observation_identity,
            "observation_integrity": lineage.wo14_observation_integrity,
            "state": lineage.risk_observation_state.value,
            "authority": "ADVISORY_RISK_OBSERVATION_ONLY",
        },
        "timing_handoff": {
            "handoff_identity": lineage.wo15_handoff_identity,
            "handoff_integrity": lineage.wo15_handoff_integrity,
            "current_state": lineage.timing_state.value,
            "evidence_boundary": lineage.timing_evidence_boundary.isoformat(),
        },
        "sponsor_decision": {
            "decision_identity": lineage.wo16_decision_identity,
            "decision_integrity": lineage.wo16_decision_integrity,
            "choice": lineage.sponsor_decision.value,
        },
        "lifecycle_admission": {
            "admission_identity": lineage.wo16_admission_identity,
            "admission_integrity": lineage.wo16_admission_integrity,
            "disposition": lineage.lifecycle_admission.value,
        },
        "position_state": position.state.value,
        "position_evidence_role": None if evidence is None else evidence.evidence_role,
        "entry_evidence": None if evidence is None else _wire(evidence),
        "live_entry_attestation": None if position.live_attestation is None else _wire(position.live_attestation),
        "monitoring_availability": "NOT_APPLICABLE" if lifecycle is None else lifecycle.monitoring_availability.value,
        "lifecycle_observations": [] if lifecycle is None else _wire(lifecycle.observations),
        "lifecycle_assessments": [] if lifecycle is None else _wire(lifecycle.assessments),
        "session_end_fact": None if lifecycle is None or lifecycle.session_end_fact is None else _wire(lifecycle.session_end_fact),
        "live_exit_attestation": None if request.live_exit_attestation is None else _wire(request.live_exit_attestation),
        "closure": None if closure is None or closure.closure is None else _wire(closure.closure),
        "events": [] if closure is None else _wire(closure.events),
        "current_pointer": _wire(restored.pointer),
        "operation": _wire(restored.operation),
        "successor": None if restored.successor is None else _wire(restored.successor),
        "fill": "UNAVAILABLE",
        "quantity": "UNAVAILABLE",
        "fees": "UNAVAILABLE",
        "monetary_pnl": "UNAVAILABLE",
        "realised_r": "UNAVAILABLE",
        "broker_order": "NONE",
    }


def _history_document(pointer: object) -> dict[str, object]:
    return {
        "canonical_subject_identity": pointer.canonical_subject_identity,
        "position_state": pointer.position_state.value,
        "monitoring_availability": pointer.monitoring_availability,
        "closure_state": None if pointer.closure_state is None else pointer.closure_state.value,
        "published_at": pointer.published_at.isoformat(),
        "pointer_identity": pointer.pointer_identity,
        "predecessor_pointer_identity": pointer.predecessor_pointer_identity,
    }


def _failure_projection(value: object) -> dict[str, object]:
    return {
        "invalid_identity": value.invalid_identity,
        "request_identity": value.request_identity,
        "canonical_subject_identity": value.canonical_subject_identity,
        "stage": value.stage.value,
        "reason": value.reason,
        "failed_at": value.failed_at.isoformat(),
    }


def _failure_document(payload: object, stage: str, reason: str, outcome: str) -> dict[str, object]:
    identity = None
    if type(payload) is dict and type(payload.get("request")) is dict:
        value = payload["request"].get("request_identity")
        identity = value if type(value) is str else None
    return {
        "request_identity": identity,
        "outcome": outcome,
        "idempotent": False,
        "failure_stage": stage,
        "failure_reason": reason,
        "position": None,
    }


def _failure_code(error: Exception) -> str:
    value = error.args[0] if error.args else None
    if (
        type(value) is str
        and len(value) <= 128
        and all(character.isupper() or character.isdigit() or character == "_" for character in value)
    ):
        return value
    if isinstance(error, Wo17PersistenceError):
        return "WO17_PERSISTENCE_UNAVAILABLE"
    if isinstance(error, (Wo17ApplicationError, Wo17ContractError)):
        return "WO17_APPLICATION_FAILURE"
    return "WO17_OPERATION_FAILED"


__all__ = [
    "IntradayWo17OperationalControl",
    "MAX_WO17_REQUEST_BYTES",
    "WO17_CONTROL_IDENTITY",
    "WO17_CONTROL_ROUTE",
    "WO17_CONTROL_VERSION",
    "WO17_PRODUCT_ROUTE",
    "WO17_STATUS_ROUTE",
    "operation_document",
]
