"""Governed Sponsor control and inert projection for Intraday WO-14."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from threading import RLock
import types
from typing import get_args, get_origin, get_type_hints

from kronos.application.intraday_wo14 import (
    IntradayWo14Application,
    IntradayWo14RestorationService,
    Wo14ApplicationError,
)
from kronos.intraday.wo14 import (
    Wo14ContractError,
    Wo14ObservationRequest,
)
from kronos.intraday.wo14_persistence import Wo14PersistenceError


WO14_CONTROL_ROUTE = "/control/intraday-wo14"
WO14_STATUS_ROUTE = "/control/intraday-wo14/status"
WO14_PRODUCT_ROUTE = "/intraday/wo14"
WO14_CONTROL_IDENTITY = "KRONOS-INTRADAY-WO14-SPONSOR-CONTROL-V1"
WO14_CONTROL_VERSION = "1.0.0"
MAX_WO14_REQUEST_BYTES = 262_144


class IntradayWo14OperationalControl:
    """Admit only one exact immutable request; retain no Browser authority."""

    def __init__(
        self,
        application: IntradayWo14Application,
        restoration: IntradayWo14RestorationService,
    ) -> None:
        if (
            type(application) is not IntradayWo14Application
            or type(restoration) is not IntradayWo14RestorationService
        ):
            raise ValueError("WO14_OPERATIONAL_CONTROL_INVALID")
        self._application = application
        self._restoration_service = restoration
        self._state_lock = RLock()
        self._restoration = restoration.restore()
        self._active_request_identity: str | None = None
        self._last_operation: dict[str, object] | None = None

    @property
    def application(self) -> IntradayWo14Application:
        return self._application

    def status_document(self) -> dict[str, object]:
        with self._state_lock:
            restoration = self._restoration
            active = self._active_request_identity
            last = self._last_operation
        restored = restoration.restored
        latest_failure = restoration.latest_failure
        return {
            "control_identity": WO14_CONTROL_IDENTITY,
            "control_version": WO14_CONTROL_VERSION,
            "runtime_loaded": True,
            "restoration_state": restoration.state,
            "operation_state": "BUSY" if active is not None else "IDLE",
            "busy": active is not None,
            "active_request_identity": active,
            "current_observation": (
                None if restored is None else _observation_document(restored)
            ),
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
            "wo15_operations": 0,
            "upstream_operations": 0,
            "autonomous_operations": 0,
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
                    payload, "CONCURRENCY", "WO14_OPERATION_BUSY", "BUSY"
                )
                self._record(document)
                return document
            self._active_request_identity = request.request_identity
        try:
            execution = self._application.execute(request)
            restoration = self._restoration_service.restore()
            if (
                restoration.state != "LOADED"
                or restoration.restored is None
                or restoration.restored.observation != execution.observation
            ):
                raise Wo14ApplicationError("WO14_POST_EXECUTION_RESTORE_FAILED")
            with self._state_lock:
                self._restoration = restoration
            document = {
                "request_identity": request.request_identity,
                "outcome": "RETAINED" if execution.replayed else "COMPLETED",
                "idempotent": execution.replayed,
                "failure_stage": None,
                "failure_reason": None,
                "risk_observation": _observation_document(restoration.restored),
            }
        except Exception as error:
            reason = _failure_code(error)
            restoration = self._restoration_service.restore()
            with self._state_lock:
                self._restoration = restoration
            document = _failure_document(
                payload,
                "CONCURRENCY" if reason == "WO14_OPERATION_BUSY" else "APPLICATION",
                reason,
                "BUSY" if reason == "WO14_OPERATION_BUSY" else "FAILED",
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


def operation_document(request: Wo14ObservationRequest) -> dict[str, object]:
    if type(request) is not Wo14ObservationRequest:
        raise ValueError("WO14_OPERATION_DOCUMENT_INVALID")
    return {"request": _wire(request)}


def _parse_operation(payload: object) -> Wo14ObservationRequest:
    if type(payload) is not dict or set(payload) != {"request"}:
        raise ValueError("WO14_REQUEST_CONTRACT_INVALID")
    return _parse_value(payload["request"], Wo14ObservationRequest)


def _parse_value(raw: object, expected: object) -> object:
    origin = get_origin(expected)
    args = get_args(expected)
    if origin in {types.UnionType, getattr(types, "UnionType", object)}:
        if raw is None and type(None) in args:
            return None
        candidates = tuple(item for item in args if item is not type(None))
        for candidate in candidates:
            try:
                return _parse_value(raw, candidate)
            except (TypeError, ValueError):
                continue
        raise ValueError("WO14_REQUEST_CONTRACT_INVALID")
    if origin is tuple:
        if type(raw) is not list or len(args) != 2 or args[1] is not Ellipsis:
            raise ValueError("WO14_REQUEST_CONTRACT_INVALID")
        return tuple(_parse_value(item, args[0]) for item in raw)
    if expected is datetime:
        if type(raw) is not str:
            raise ValueError("WO14_REQUEST_CONTRACT_INVALID")
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("WO14_REQUEST_CONTRACT_INVALID")
        return value
    if expected is date:
        if type(raw) is not str:
            raise ValueError("WO14_REQUEST_CONTRACT_INVALID")
        return date.fromisoformat(raw)
    if expected is Decimal:
        if type(raw) is not str:
            raise ValueError("WO14_REQUEST_CONTRACT_INVALID")
        return Decimal(raw)
    if isinstance(expected, type) and issubclass(expected, StrEnum):
        if type(raw) is not str:
            raise ValueError("WO14_REQUEST_CONTRACT_INVALID")
        return expected(raw)
    if expected in {str, int, bool}:
        if type(raw) is not expected:
            raise ValueError("WO14_REQUEST_CONTRACT_INVALID")
        return raw
    if isinstance(expected, type) and is_dataclass(expected):
        if type(raw) is not dict:
            raise ValueError("WO14_REQUEST_CONTRACT_INVALID")
        expected_fields = {item.name for item in fields(expected)}
        if set(raw) != expected_fields:
            raise ValueError("WO14_REQUEST_CONTRACT_INVALID")
        hints = get_type_hints(expected)
        return expected(**{
            item.name: _parse_value(raw[item.name], hints[item.name])
            for item in fields(expected)
        })
    raise TypeError("WO14_REQUEST_CONTRACT_INVALID")


def _wire(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _wire(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, tuple):
        return [_wire(item) for item in value]
    if value is None or type(value) in {str, int, bool}:
        return value
    raise ValueError("WO14_OPERATION_DOCUMENT_INVALID")


def _observation_document(restored: object) -> dict[str, object]:
    observation = restored.observation
    request = restored.request
    pointer = restored.pointer
    binding = observation.plan_binding
    return {
        "observation_identity": observation.observation_identity,
        "observation_integrity": observation.observation_integrity,
        "request_identity": observation.request_identity,
        "trade_plan_identity": binding.trade_plan_identity,
        "trade_plan_integrity": binding.trade_plan_integrity,
        "canonical_subject_identity": binding.canonical_subject_identity,
        "market_family": binding.market_family.value,
        "direction": binding.direction.value,
        "setup_family": binding.setup_family.value,
        "analysis_boundary": binding.analysis_boundary.isoformat(),
        "instrument_identity": binding.instrument_identity,
        "actual_contract_identity": binding.actual_contract_identity,
        "state": observation.state.value,
        "alert_severity": observation.alert_severity.value,
        "structural_risk_per_price_unit": _decimal_text(
            observation.structural_risk_per_price_unit
        ),
        "risk_per_share": _decimal_text(observation.risk_per_share),
        "underlying_point_risk": _decimal_text(observation.underlying_point_risk),
        "monetary_risk_per_tradable_unit": _decimal_text(
            observation.monetary_risk_per_tradable_unit
        ),
        "reference_quantity": _decimal_text(observation.reference_quantity),
        "reference_quantity_semantics": (
            None if observation.reference_quantity_semantics is None
            else observation.reference_quantity_semantics.value
        ),
        "reference_quantity_source_identity": (
            None if request.reference_quantity is None
            else request.reference_quantity.source_identity
        ),
        "loss_at_stop": _decimal_text(observation.loss_at_stop),
        "reference_notional": _decimal_text(observation.reference_notional),
        "capital_reference": _decimal_text(observation.capital_reference),
        "capital_at_risk_fraction": _decimal_text(
            observation.capital_at_risk_fraction
        ),
        "existing_open_risk": _decimal_text(observation.existing_open_risk),
        "aggregate_open_risk_after_reference": _decimal_text(
            observation.aggregate_open_risk_after_reference
        ),
        "margin_context": _decimal_text(observation.margin_context),
        "currency": observation.currency,
        "capital_source_identity": (
            None if request.capital_reference is None
            else request.capital_reference.source_identity
        ),
        "portfolio_source_identity": (
            None if request.portfolio_snapshot is None
            else request.portfolio_snapshot.source_identity
        ),
        "margin_source_identity": (
            None if request.margin_context is None
            else request.margin_context.source_identity
        ),
        "model_rr": _decimal_text(binding.model_rr),
        "field_availability": [
            {
                "field": item.field.value,
                "availability": item.availability.value,
                "reason": item.reason,
            }
            for item in observation.field_availability
        ],
        "calculation_provenance": [
            {
                "field": item.field.value,
                "formula_identity": item.formula_identity,
                "source_identities": list(item.source_identities),
                "unit_semantics": item.unit_semantics,
            }
            for item in observation.calculation_provenance
        ],
        "unavailable_reasons": list(observation.unavailable_reasons),
        "policy_identity": observation.policy.policy_identity,
        "policy_version": observation.policy.policy_version,
        "authority": observation.authority,
        "evaluated_at": observation.evaluated_at.isoformat(),
        "pointer_identity": pointer.pointer_identity,
        "supersession_lineage_identity": pointer.supersession_lineage_identity,
    }


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


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
        "risk_observation": None,
    }


def _failure_code(error: Exception) -> str:
    if isinstance(error, (Wo14ApplicationError, Wo14ContractError)) and str(error):
        return str(error)
    if isinstance(error, Wo14PersistenceError):
        return "WO14_PERSISTENCE_UNAVAILABLE"
    if isinstance(error, (ValueError, TypeError)) and str(error).startswith("WO14_"):
        return str(error)
    return "WO14_OPERATION_FAILED"


__all__ = [
    "IntradayWo14OperationalControl", "MAX_WO14_REQUEST_BYTES",
    "WO14_CONTROL_IDENTITY", "WO14_CONTROL_ROUTE", "WO14_CONTROL_VERSION",
    "WO14_PRODUCT_ROUTE", "WO14_STATUS_ROUTE", "operation_document",
]
