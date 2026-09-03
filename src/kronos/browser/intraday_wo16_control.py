"""Governed exact-request control and inert projection for Intraday WO-16."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from threading import RLock
import types
from typing import get_args, get_origin, get_type_hints
from zoneinfo import ZoneInfo

from kronos.application.intraday_wo16 import (
    IntradayWo16PersistenceApplication,
    IntradayWo16RestorationService,
    Wo16ApplicationError,
    Wo16BusyOutcome,
    Wo16OperationRequest,
)
from kronos.intraday.wo13_persistence import Wo13Store
from kronos.intraday.wo14_persistence import Wo14Store
from kronos.intraday.wo15_persistence import CurrentWo15Pointer, Wo15Store
from kronos.intraday.wo16 import (
    WO16_POLICY_CHECKSUM,
    WO16_POLICY_IDENTITY,
    WO16_POLICY_VERSION,
    Wo16ContractError,
    Wo16SponsorDecision,
)
from kronos.intraday.wo16_adapters import Wo16CurrentWo15Pointer
from kronos.intraday.wo16_persistence import (
    RestoredWo16State,
    Wo16PersistenceError,
    Wo16RestorationState,
)
from kronos.market.schedule import MarketDaySchedule, MarketWindow


WO16_CONTROL_ROUTE = "/control/intraday-wo16"
WO16_STATUS_ROUTE = "/control/intraday-wo16/status"
WO16_PRODUCT_ROUTE = "/intraday/wo16"
WO16_CONTROL_IDENTITY = "KRONOS-INTRADAY-WO16-SPONSOR-CONTROL-V1"
WO16_CONTROL_VERSION = "1.0.0"
MAX_WO16_REQUEST_BYTES = 262_144


class _Wo16ControlError(ValueError):
    pass


class IntradayWo16OperationalControl:
    """Admit only an exact current immutable WO-16 Sponsor request."""

    def __init__(
        self,
        application: IntradayWo16PersistenceApplication,
        restoration: IntradayWo16RestorationService,
        *,
        wo13_store: Wo13Store,
        wo14_store: Wo14Store,
        wo15_store: Wo15Store,
    ) -> None:
        if (
            type(application) is not IntradayWo16PersistenceApplication
            or type(restoration) is not IntradayWo16RestorationService
            or type(wo13_store) is not Wo13Store
            or type(wo14_store) is not Wo14Store
            or type(wo15_store) is not Wo15Store
        ):
            raise ValueError("WO16_OPERATIONAL_CONTROL_INVALID")
        self._application = application
        self._restoration_service = restoration
        self._wo13_store = wo13_store
        self._wo14_store = wo14_store
        self._wo15_store = wo15_store
        self._state_lock = RLock()
        self._restoration = restoration.restore()
        self._active_request_identity: str | None = None
        self._last_operation: dict[str, object] | None = None
        self._sponsor_operations = 0
        self._decision_operations = 0

    @property
    def application(self) -> IntradayWo16PersistenceApplication:
        return self._application

    def status_document(self) -> dict[str, object]:
        """Return restored persisted facts without evaluating any upstream work."""

        with self._state_lock:
            restoration = self._restoration
            active = self._active_request_identity
            last = self._last_operation
            sponsor_operations = self._sponsor_operations
            decision_operations = self._decision_operations
        currents = [_state_document(item) for item in restoration.restored]
        history = [
            _history_document(
                item, restored.pointer.canonical_subject_identity
            )
            for restored in restoration.restored
            for item in restored.history
        ]
        failures = [_failure_projection(item) for item in restoration.latest_failures]
        return {
            "control_identity": WO16_CONTROL_IDENTITY,
            "control_version": WO16_CONTROL_VERSION,
            "runtime_loaded": True,
            "restoration_state": restoration.state.value,
            "operation_state": "BUSY" if active is not None else "IDLE",
            "busy": active is not None,
            "active_request_identity": active,
            "current_decisions": currents,
            "decision_history": history,
            "last_operation": last,
            "latest_persisted_failures": failures,
            "failure_stage": restoration.failure_stage,
            "failure_reason": restoration.failure_reason,
            "decision_vocabulary": [item.value for item in Wo16SponsorDecision],
            # No fresh DOMAIN-008 fact is acquired by GET. The exact JSON POST
            # remains the only admission seam, so the page fails closed here.
            "decision_controls_available": False,
            "policy_identity": WO16_POLICY_IDENTITY,
            "policy_version": WO16_POLICY_VERSION,
            "policy_checksum": WO16_POLICY_CHECKSUM,
            "provider_calls": 0,
            "wo13_operations": 0,
            "wo14_operations": 0,
            "wo15_operations": 0,
            "upstream_operations": 0,
            "autonomous_operations": 0,
            "sponsor_operations": sponsor_operations,
            "decision_operations": decision_operations,
            "persistence_writes_from_get": 0,
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
                    payload, "CONCURRENCY", "WO16_OPERATION_BUSY", "BUSY"
                )
                self._record(document)
                return document
            self._active_request_identity = request.request_identity
            self._sponsor_operations += 1
        try:
            self._validate_current_upstream(request)
            execution = self._application.execute(request)
            if type(execution) is Wo16BusyOutcome:
                document = _failure_document(
                    payload, "CONCURRENCY", execution.reason, "BUSY"
                )
            else:
                restoration = self._restoration_service.restore()
                subject = request.wo13_trade_plan.canonical_subject_identity
                restored = next(
                    (
                        item
                        for item in restoration.restored
                        if item.pointer.canonical_subject_identity == subject
                    ),
                    None,
                )
                if (
                    restoration.state is not Wo16RestorationState.LOADED
                    or restored is None
                    or restored.pointer != execution.pointer
                    or restored.decision != execution.execution.decision
                    or restored.admission != execution.execution.admission
                ):
                    raise Wo16ApplicationError(
                        "WO16_POST_EXECUTION_RESTORE_FAILED"
                    )
                with self._state_lock:
                    self._restoration = restoration
                    if not execution.replayed:
                        self._decision_operations += 1
                document = {
                    "request_identity": request.request_identity,
                    "outcome": "RETAINED" if execution.replayed else "COMPLETED",
                    "idempotent": execution.replayed,
                    "failure_stage": None,
                    "failure_reason": None,
                    "decision": _state_document(restored),
                }
        except Exception as error:
            reason = _failure_code(error)
            restoration = self._restoration_service.restore()
            with self._state_lock:
                self._restoration = restoration
            document = _failure_document(
                payload,
                "CONCURRENCY" if reason == "WO16_OPERATION_BUSY" else "APPLICATION",
                reason,
                "BUSY" if reason == "WO16_OPERATION_BUSY" else "FAILED",
            )
        finally:
            with self._state_lock:
                self._active_request_identity = None
        self._record(document)
        return document

    def _validate_current_upstream(self, request: Wo16OperationRequest) -> None:
        if self._wo13_store.load_current() != request.current_wo13_pointer:
            raise _Wo16ControlError("WO13_NOT_CURRENT")
        if self._wo14_store.load_current() != request.current_wo14_pointer:
            raise _Wo16ControlError("WO14_NOT_CURRENT")
        if self._wo15_store.load_current() != request.current_wo15_pointer:
            raise _Wo16ControlError("WO15_NOT_CURRENT")

    def _record(self, document: dict[str, object]) -> None:
        with self._state_lock:
            self._last_operation = {
                key: document.get(key)
                for key in (
                    "request_identity",
                    "outcome",
                    "failure_stage",
                    "failure_reason",
                )
            }


def operation_document(request: Wo16OperationRequest) -> dict[str, object]:
    if type(request) is not Wo16OperationRequest:
        raise ValueError("WO16_OPERATION_DOCUMENT_INVALID")
    return {"request": _wire(request)}


def _parse_operation(payload: object) -> Wo16OperationRequest:
    if type(payload) is not dict or set(payload) != {"request"}:
        raise ValueError("WO16_REQUEST_CONTRACT_INVALID")
    value = _parse_value(payload["request"], Wo16OperationRequest)
    if type(value) is not Wo16OperationRequest:
        raise ValueError("WO16_REQUEST_CONTRACT_INVALID")
    return value


def _parse_value(raw: object, expected: object) -> object:
    if expected is Wo16CurrentWo15Pointer:
        expected = CurrentWo15Pointer
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
        raise ValueError("WO16_REQUEST_CONTRACT_INVALID")
    if origin is tuple:
        if type(raw) is not list:
            raise ValueError("WO16_REQUEST_CONTRACT_INVALID")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_parse_value(item, args[0]) for item in raw)
        if len(raw) != len(args):
            raise ValueError("WO16_REQUEST_CONTRACT_INVALID")
        return tuple(
            _parse_value(item, item_type)
            for item, item_type in zip(raw, args, strict=True)
        )
    if expected is datetime:
        if type(raw) is not str:
            raise ValueError("WO16_REQUEST_CONTRACT_INVALID")
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("WO16_REQUEST_CONTRACT_INVALID")
        return value
    if expected is date:
        if type(raw) is not str:
            raise ValueError("WO16_REQUEST_CONTRACT_INVALID")
        return date.fromisoformat(raw)
    if expected is timedelta:
        if type(raw) is not str:
            raise ValueError("WO16_REQUEST_CONTRACT_INVALID")
        return timedelta(seconds=Decimal(raw))
    if expected is Decimal:
        if type(raw) is not str:
            raise ValueError("WO16_REQUEST_CONTRACT_INVALID")
        return Decimal(raw)
    if isinstance(expected, type) and issubclass(expected, StrEnum):
        if type(raw) is not str:
            raise ValueError("WO16_REQUEST_CONTRACT_INVALID")
        return expected(raw)
    if expected in {str, int, bool}:
        if type(raw) is not expected:
            raise ValueError("WO16_REQUEST_CONTRACT_INVALID")
        return raw
    if isinstance(expected, type) and is_dataclass(expected):
        if type(raw) is not dict:
            raise ValueError("WO16_REQUEST_CONTRACT_INVALID")
        expected_fields = {item.name for item in fields(expected)}
        if set(raw) != expected_fields:
            raise ValueError("WO16_REQUEST_CONTRACT_INVALID")
        hints = get_type_hints(expected)
        values = {
            item.name: _parse_value(raw[item.name], hints[item.name])
            for item in fields(expected)
        }
        if expected is MarketDaySchedule:
            zone = ZoneInfo(values["timezone"])
            values["windows"] = tuple(
                MarketWindow(
                    item.opens_at.astimezone(zone),
                    item.closes_at.astimezone(zone),
                )
                for item in values["windows"]
            )
        return expected(**values)
    raise TypeError("WO16_REQUEST_CONTRACT_INVALID")


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
    raise ValueError("WO16_OPERATION_DOCUMENT_INVALID")


def _state_document(restored: RestoredWo16State) -> dict[str, object]:
    lineage = restored.snapshot.upstream_lineage
    return {
        "canonical_subject_identity": restored.pointer.canonical_subject_identity,
        "market_family": restored.pointer.market_family.value,
        "instrument_identity": restored.pointer.instrument_identity,
        "actual_contract_identity": restored.pointer.actual_contract_identity,
        "contract_expiry": (
            None
            if restored.pointer.contract_expiry is None
            else restored.pointer.contract_expiry.isoformat()
        ),
        "roll_lineage_identity": restored.pointer.roll_lineage_identity,
        "trading_date": restored.pointer.trading_date.isoformat(),
        "session_identity": restored.pointer.session_identity,
        "calendar_identity": restored.pointer.calendar_identity,
        "calendar_version": restored.pointer.calendar_version,
        "trade_plan": _wire(lineage.trade_plan),
        "risk_observation": _wire(lineage.risk_observation),
        "timing_handoff": _wire(lineage.timing_handoff),
        "session": _wire(lineage.session),
        "sponsor_decision": _wire(restored.decision),
        "lifecycle_admission": _wire(restored.admission),
        "current_pointer": _wire(restored.pointer),
        "operation": _wire(restored.operation),
        "successor": None if restored.successor is None else _wire(restored.successor),
        "actual_fill": "UNAVAILABLE",
        "quantity": "UNAVAILABLE",
        "pnl": "UNAVAILABLE",
        "realised_r": "UNAVAILABLE",
        "broker_order": "NONE",
        "position_created": False,
    }


def _history_document(
    value: object, canonical_subject_identity: str
) -> dict[str, object]:
    return {
        "canonical_subject_identity": canonical_subject_identity,
        "decision_identity": value.decision_identity,
        "choice": value.choice.value,
        "decision_timestamp": value.decision_timestamp.isoformat(),
        "timing_handoff_identity": value.timing_handoff_identity,
        "predecessor_decision_identity": value.predecessor_decision_identity,
        "supersession_lineage_identity": value.supersession_lineage_identity,
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


def _failure_document(
    payload: object, stage: str, reason: str, outcome: str
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
        "decision": None,
    }


def _failure_code(error: Exception) -> str:
    value = error.args[0] if error.args else None
    if (
        type(value) is str
        and len(value) <= 128
        and all(
            character.isupper()
            or character.isdigit()
            or character == "_"
            for character in value
        )
    ):
        return value
    if isinstance(error, Wo16PersistenceError):
        return "WO16_PERSISTENCE_UNAVAILABLE"
    if isinstance(error, (Wo16ApplicationError, Wo16ContractError)):
        return "WO16_APPLICATION_FAILURE"
    return "WO16_OPERATION_FAILED"


__all__ = [
    "IntradayWo16OperationalControl",
    "MAX_WO16_REQUEST_BYTES",
    "WO16_CONTROL_IDENTITY",
    "WO16_CONTROL_ROUTE",
    "WO16_CONTROL_VERSION",
    "WO16_PRODUCT_ROUTE",
    "WO16_STATUS_ROUTE",
    "operation_document",
]
