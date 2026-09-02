"""Governed Sponsor control and inert projection for Intraday WO-15."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from threading import RLock
import types
from typing import get_args, get_origin, get_type_hints

from kronos.application.intraday_wo15 import (
    IntradayWo15Application,
    IntradayWo15RestorationService,
    Wo15ApplicationError,
)
from kronos.intraday.wo15 import Wo15ContractError
from kronos.intraday.wo15_persistence import (
    Wo15OperationRequest,
    Wo15PersistenceError,
    Wo15Store,
)


WO15_CONTROL_ROUTE = "/control/intraday-wo15"
WO15_STATUS_ROUTE = "/control/intraday-wo15/status"
WO15_PRODUCT_ROUTE = "/intraday/wo15"
WO15_CONTROL_IDENTITY = "KRONOS-INTRADAY-WO15-SPONSOR-CONTROL-V1"
WO15_CONTROL_VERSION = "1.0.0"
MAX_WO15_REQUEST_BYTES = 262_144


class IntradayWo15OperationalControl:
    """Admit one exact immutable WO-15 request without analytical authority."""

    def __init__(
        self,
        application: IntradayWo15Application,
        restoration: IntradayWo15RestorationService,
    ) -> None:
        if (
            type(application) is not IntradayWo15Application
            or type(restoration) is not IntradayWo15RestorationService
        ):
            raise ValueError("WO15_OPERATIONAL_CONTROL_INVALID")
        self._application = application
        self._restoration_service = restoration
        self._state_lock = RLock()
        self._restoration = restoration.restore()
        self._active_request_identity: str | None = None
        self._last_operation: dict[str, object] | None = None
        self._sponsor_operations = 0
        self._timing_evaluations = 0

    @property
    def application(self) -> IntradayWo15Application:
        return self._application

    def status_document(self) -> dict[str, object]:
        """Project restored facts only; this method never evaluates timing."""

        with self._state_lock:
            restoration = self._restoration
            active = self._active_request_identity
            last = self._last_operation
            sponsor_operations = self._sponsor_operations
            timing_evaluations = self._timing_evaluations
        restored = restoration.restored
        latest_failure = restoration.latest_failure
        history, history_failure = _persisted_history_document(
            self._application.store
        )
        return {
            "control_identity": WO15_CONTROL_IDENTITY,
            "control_version": WO15_CONTROL_VERSION,
            "runtime_loaded": True,
            "restoration_state": restoration.state,
            "operation_state": "BUSY" if active is not None else "IDLE",
            "busy": active is not None,
            "active_request_identity": active,
            "current_timing": (
                None if restored is None else _timing_document(restored)
            ),
            "timing_history": history,
            "history_failure": history_failure,
            "last_operation": last,
            "latest_persisted_failure": (
                None if latest_failure is None else {
                    "invalid_identity": latest_failure.invalid_identity,
                    "request_identity": latest_failure.request_identity,
                    "stage": latest_failure.stage.value,
                    "reason": latest_failure.reason,
                    "failed_at": latest_failure.failed_at.isoformat(),
                }
            ),
            "failure_stage": restoration.failure_stage,
            "failure_reason": restoration.failure_reason,
            "provider_calls": 0,
            "wo13_operations": 0,
            "wo14_operations": 0,
            "upstream_operations": 0,
            "autonomous_operations": 0,
            "sponsor_operations": sponsor_operations,
            "timing_evaluations": timing_evaluations,
            "broker_operations": 0,
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

        with self._state_lock:
            if self._active_request_identity is not None:
                document = _failure_document(
                    payload, "CONCURRENCY", "WO15_OPERATION_BUSY", "BUSY"
                )
                self._record(document)
                return document
            self._active_request_identity = request.request_identity
            self._sponsor_operations += 1
        try:
            execution = self._application.execute(request)
            restoration = self._restoration_service.restore()
            if (
                restoration.state != "LOADED"
                or restoration.restored is None
                or restoration.restored.result != execution.timing_result
                or restoration.restored.pointer != execution.pointer
            ):
                raise Wo15ApplicationError("WO15_POST_EXECUTION_RESTORE_FAILED")
            with self._state_lock:
                self._restoration = restoration
                if not execution.replayed:
                    self._timing_evaluations += 1
            document = {
                "request_identity": request.request_identity,
                "outcome": "RETAINED" if execution.replayed else "COMPLETED",
                "idempotent": execution.replayed,
                "failure_stage": None,
                "failure_reason": None,
                "timing": _timing_document(restoration.restored),
            }
        except Exception as error:
            reason = _failure_code(error)
            restoration = self._restoration_service.restore()
            with self._state_lock:
                self._restoration = restoration
            document = _failure_document(
                payload,
                "CONCURRENCY" if reason == "WO15_OPERATION_BUSY" else "APPLICATION",
                reason,
                "BUSY" if reason == "WO15_OPERATION_BUSY" else "FAILED",
            )
        finally:
            with self._state_lock:
                self._active_request_identity = None
        self._record(document)
        return document

    def _record(self, document: dict[str, object]) -> None:
        with self._state_lock:
            self._last_operation = {
                key: document.get(key)
                for key in (
                    "request_identity", "outcome", "failure_stage", "failure_reason"
                )
            }


def operation_document(request: Wo15OperationRequest) -> dict[str, object]:
    if type(request) is not Wo15OperationRequest:
        raise ValueError("WO15_OPERATION_DOCUMENT_INVALID")
    return {"request": _wire(request)}


def _parse_operation(payload: object) -> Wo15OperationRequest:
    if type(payload) is not dict or set(payload) != {"request"}:
        raise ValueError("WO15_REQUEST_CONTRACT_INVALID")
    return _parse_value(payload["request"], Wo15OperationRequest)


def _parse_value(raw: object, expected: object) -> object:
    origin = get_origin(expected)
    args = get_args(expected)
    if origin in {types.UnionType, getattr(types, "UnionType", object)}:
        if raw is None and type(None) in args:
            return None
        for candidate in (item for item in args if item is not type(None)):
            try:
                return _parse_value(raw, candidate)
            except (TypeError, ValueError):
                continue
        raise ValueError("WO15_REQUEST_CONTRACT_INVALID")
    if origin is tuple:
        if type(raw) is not list:
            raise ValueError("WO15_REQUEST_CONTRACT_INVALID")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_parse_value(item, args[0]) for item in raw)
        if len(raw) != len(args):
            raise ValueError("WO15_REQUEST_CONTRACT_INVALID")
        return tuple(
            _parse_value(item, item_type)
            for item, item_type in zip(raw, args, strict=True)
        )
    if expected is datetime:
        if type(raw) is not str:
            raise ValueError("WO15_REQUEST_CONTRACT_INVALID")
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("WO15_REQUEST_CONTRACT_INVALID")
        return value
    if expected is date:
        if type(raw) is not str:
            raise ValueError("WO15_REQUEST_CONTRACT_INVALID")
        return date.fromisoformat(raw)
    if expected is Decimal:
        if type(raw) is not str:
            raise ValueError("WO15_REQUEST_CONTRACT_INVALID")
        return Decimal(raw)
    if isinstance(expected, type) and issubclass(expected, StrEnum):
        if type(raw) is not str:
            raise ValueError("WO15_REQUEST_CONTRACT_INVALID")
        return expected(raw)
    if expected in {str, int, bool}:
        if type(raw) is not expected:
            raise ValueError("WO15_REQUEST_CONTRACT_INVALID")
        return raw
    if isinstance(expected, type) and is_dataclass(expected):
        if type(raw) is not dict:
            raise ValueError("WO15_REQUEST_CONTRACT_INVALID")
        expected_fields = {item.name for item in fields(expected)}
        if set(raw) != expected_fields:
            raise ValueError("WO15_REQUEST_CONTRACT_INVALID")
        hints = get_type_hints(expected)
        return expected(**{
            item.name: _parse_value(raw[item.name], hints[item.name])
            for item in fields(expected)
        })
    raise TypeError("WO15_REQUEST_CONTRACT_INVALID")


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
    raise ValueError("WO15_OPERATION_DOCUMENT_INVALID")


def _timing_document(restored: object) -> dict[str, object]:
    result = restored.result
    admission = restored.admission
    session = restored.session
    pointer = restored.pointer
    return {
        "canonical_subject_identity": admission.canonical_subject_identity,
        "market_family": admission.market_family.value,
        "direction": admission.direction.value,
        "setup_family": admission.setup_family.value,
        "instrument_identity": admission.instrument_identity,
        "actual_contract_identity": admission.actual_contract_identity,
        "roll_lineage_identity": admission.roll_lineage_identity,
        "wo13_trade_plan_identity": admission.wo13_trade_plan_identity,
        "wo13_trade_plan_integrity": admission.wo13_trade_plan_integrity,
        "entry_reference": format(admission.entry_reference, "f"),
        "completed_five_minute_close": (
            None if restored.request.source_candle is None
            else format(restored.request.source_candle.close, "f")
        ),
        "session_identity": session.session_identity,
        "calendar_identity": session.calendar_identity,
        "calendar_version": session.calendar_version,
        "timing_result": _wire(result),
        "telemetry": None if restored.telemetry is None else _wire(restored.telemetry),
        "timing_handoff": (
            None if restored.timing_handoff is None else _wire(restored.timing_handoff)
        ),
        "operation": _wire(restored.operation),
        "current_pointer": _wire(pointer),
        "supersession": (
            None if restored.supersession is None else _wire(restored.supersession)
        ),
        "request_identity": restored.request.request_identity,
        "evidence_identity": restored.evidence.evidence_identity,
        "progression_identity": restored.progression.adapter_identity,
    }


def _persisted_history_document(
    store: Wo15Store,
) -> tuple[list[dict[str, object]], str | None]:
    """Load immutable WO-15 history without consulting or moving an alias."""

    try:
        events: list[tuple[datetime, str, dict[str, object]]] = []
        for path in (store.root / "results").glob("*.json"):
            result = store.load_result(path.stem)
            evaluation = result.cycle_evaluation
            events.append((
                result.observation_boundary,
                result.result_identity,
                {
                    "event": "TIMING_RESULT",
                    "boundary": result.observation_boundary.isoformat(),
                    "identity": result.result_identity,
                    "evidence_identity": result.evidence_identity,
                    "timing_cycle_id": result.timing_cycle_id,
                    "prior_state": result.prior_state.value,
                    "current_state": result.current_state.value,
                    "cause": result.cause.value,
                    "observation_identity": (
                        None if evaluation is None
                        else evaluation.observation.observation_identity
                    ),
                    "transition_identity": (
                        None if evaluation is None
                        else evaluation.transition.transition_identity
                    ),
                },
            ))
        for path in (store.root / "handoffs").glob("*.json"):
            handoff = store.load_handoff(path.stem)
            events.append((
                handoff.handoff_created_at,
                handoff.handoff_identity,
                {
                    "event": "TIMING_HANDOFF",
                    "boundary": handoff.handoff_created_at.isoformat(),
                    "identity": handoff.handoff_identity,
                    "evidence_identity": handoff.completed_five_minute_evidence_identity,
                    "timing_cycle_id": handoff.timing_cycle_id,
                    "prior_state": handoff.prior_state.value,
                    "current_state": handoff.current_state.value,
                    "cause": handoff.transition_cause,
                },
            ))
        for path in (store.root / "supersessions").glob("*.json"):
            lineage = store.load_supersession(path.stem)
            events.append((
                lineage.superseded_at,
                lineage.lineage_identity,
                {
                    "event": "SUPERSESSION",
                    "boundary": lineage.superseded_at.isoformat(),
                    "identity": lineage.lineage_identity,
                    "evidence_identity": lineage.successor_result_identity,
                    "timing_cycle_id": lineage.successor_cycle_identity,
                    "prior_state": None,
                    "current_state": None,
                    "cause": lineage.reason.value,
                },
            ))
        return [item[2] for item in sorted(events, key=lambda item: (item[0], item[1]))], None
    except (Wo15PersistenceError, Wo15ContractError, OSError, ValueError):
        return [], "WO15_HISTORY_RESTORATION_FAILED"


def _failure_document(
    payload: object, stage: str, reason: str, outcome: str,
) -> dict[str, object]:
    identity = None
    if type(payload) is dict and type(payload.get("request")) is dict:
        candidate = payload["request"].get("request_identity")
        identity = candidate if type(candidate) is str else None
    return {
        "request_identity": identity,
        "outcome": outcome,
        "idempotent": False,
        "failure_stage": stage,
        "failure_reason": reason,
        "timing": None,
    }


def _failure_code(error: Exception) -> str:
    if isinstance(error, (Wo15ApplicationError, Wo15ContractError)) and str(error):
        return str(error)
    if isinstance(error, Wo15PersistenceError):
        return "WO15_PERSISTENCE_UNAVAILABLE"
    if isinstance(error, (ValueError, TypeError)) and str(error).startswith("WO15_"):
        return str(error)
    return "WO15_OPERATION_FAILED"


__all__ = [
    "IntradayWo15OperationalControl", "MAX_WO15_REQUEST_BYTES",
    "WO15_CONTROL_IDENTITY", "WO15_CONTROL_ROUTE", "WO15_CONTROL_VERSION",
    "WO15_PRODUCT_ROUTE", "WO15_STATUS_ROUTE", "operation_document",
]
