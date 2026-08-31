"""Governed Sponsor control and inert projection for Intraday WO-13."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from threading import RLock
import types
from typing import get_args, get_origin, get_type_hints

from kronos.application.intraday_wo13 import (
    IntradayWo13Application,
    IntradayWo13RestorationService,
    Wo13ApplicationError,
    Wo13RestorationStatus,
)
from kronos.intraday.wo12_v2 import Wo13EligibilityV2
from kronos.intraday.wo12_v2_persistence import Wo12V2PersistenceError, Wo12V2Store
from kronos.intraday.wo13 import Wo13ConstructionRequest, Wo13ContractError
from kronos.intraday.wo13_breakout import Wo13BreakoutGeometryEvidence
from kronos.intraday.wo13_handoff import Wo13SetupFamily
from kronos.intraday.wo13_persistence import Wo13PersistenceError
from kronos.intraday.wo13_pullback import Wo13PullbackGeometryEvidence
from kronos.intraday.wo13_targets import Wo13TargetConstraintPopulation
from kronos.validation.kr370 import Kr370AnalyticalClassification


WO13_CONTROL_ROUTE = "/control/intraday-wo13"
WO13_STATUS_ROUTE = "/control/intraday-wo13/status"
WO13_PRODUCT_ROUTE = "/intraday/wo13"
WO13_CONTROL_IDENTITY = "KRONOS-INTRADAY-WO13-SPONSOR-CONTROL-V1"
WO13_CONTROL_VERSION = "1.0.0"
MAX_WO13_REQUEST_BYTES = 524_288
_OPERATION_FIELDS = {"request", "geometry_evidence", "target_population"}


class IntradayWo13OperationalControl:
    """Admit only an exact current WO-12 NOW handoff and explicit evidence."""

    def __init__(
        self,
        application: IntradayWo13Application,
        restoration: IntradayWo13RestorationService,
        wo12_store: Wo12V2Store,
    ) -> None:
        if (
            type(application) is not IntradayWo13Application
            or type(restoration) is not IntradayWo13RestorationService
            or type(wo12_store) is not Wo12V2Store
        ):
            raise ValueError("WO13_OPERATIONAL_CONTROL_INVALID")
        self._application = application
        self._restoration_service = restoration
        self._wo12_store = wo12_store
        self._state_lock = RLock()
        self._restoration = restoration.restore()
        self._active_request_identity: str | None = None
        self._last_operation: dict[str, object] | None = None

    @property
    def application(self) -> IntradayWo13Application:
        return self._application

    @property
    def restoration(self) -> Wo13RestorationStatus:
        with self._state_lock:
            return self._restoration

    def status_document(self) -> dict[str, object]:
        with self._state_lock:
            restoration = self._restoration
            active = self._active_request_identity
            last = self._last_operation
        restored = restoration.restored
        return {
            "control_identity": WO13_CONTROL_IDENTITY,
            "control_version": WO13_CONTROL_VERSION,
            "runtime_loaded": True,
            "restoration_state": restoration.state,
            "operation_state": "BUSY" if active is not None else "IDLE",
            "busy": active is not None,
            "active_request_identity": active,
            "current_plan": None if restored is None else _plan_document(restored),
            "last_operation": last,
            "failure_stage": restoration.failure_stage,
            "failure_reason": restoration.failure_reason,
            "provider_calls": 0,
            "upstream_operations": 0,
            "autonomous_operations": 0,
        }

    def execute_document(self, payload: object) -> dict[str, object]:
        try:
            request, evidence, population = _parse_operation(payload)
            self._validate_current_wo12(request)
        except Exception as error:
            document = _failure_document(
                payload, "REQUEST_VALIDATION", _failure_code(error), "REJECTED"
            )
            self._record(document)
            return document

        with self._state_lock:
            if self._active_request_identity is not None:
                document = _failure_document(
                    payload, "CONCURRENCY", "WO13_OPERATION_BUSY", "BUSY"
                )
                self._last_operation = {
                    key: document.get(key)
                    for key in (
                        "request_identity",
                        "outcome",
                        "failure_stage",
                        "failure_reason",
                    )
                }
                return document
            self._active_request_identity = request.request_identity
        try:
            execution = self._application.execute(request, evidence, population)
            restored = self._restoration_service.restore()
            if (
                restored.state != "LOADED"
                or restored.restored is None
                or restored.restored.trade_plan != execution.trade_plan
            ):
                raise Wo13ApplicationError("WO13_POST_EXECUTION_RESTORE_FAILED")
            with self._state_lock:
                self._restoration = restored
            document = {
                "request_identity": request.request_identity,
                "outcome": "RETAINED" if execution.replayed else "COMPLETED",
                "idempotent": execution.replayed,
                "failure_stage": None,
                "failure_reason": None,
                "trade_plan": _plan_document(restored.restored),
            }
        except Exception as error:
            reason = _failure_code(error)
            document = _failure_document(
                payload,
                "CONCURRENCY" if reason == "WO13_OPERATION_BUSY" else "APPLICATION",
                reason,
                "BUSY" if reason == "WO13_OPERATION_BUSY" else "FAILED",
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
                    "request_identity",
                    "outcome",
                    "failure_stage",
                    "failure_reason",
                )
            }

    def _validate_current_wo12(self, request: Wo13ConstructionRequest) -> None:
        try:
            current = self._wo12_store.restore_current()
        except (Wo12V2PersistenceError, OSError) as error:
            raise ValueError("WO13_CURRENT_WO12_UNAVAILABLE") from error
        if current is None:
            raise ValueError("WO13_CURRENT_WO12_UNAVAILABLE")
        handoff = request.handoff
        exact = (
            handoff.wo12_pointer_identity == current.pointer.pointer_identity
            and handoff.wo12_pointer_integrity == current.pointer.pointer_integrity
            and handoff.wo12_request_identity == current.request.request_identity
            and handoff.wo12_request_integrity == current.request.request_integrity
            and handoff.wo12_evidence_identity == current.evidence.evidence_identity
            and handoff.wo12_evidence_integrity == current.evidence.evidence_integrity
            and handoff.wo12_result_identity == current.result.result_identity
            and handoff.wo12_result_integrity == current.result.result_integrity
            and handoff.wo12_eligibility_identity
            == current.eligibility.eligibility_identity
            and handoff.wo12_eligibility_integrity
            == current.eligibility.eligibility_integrity
            and handoff.canonical_subject_identity
            == current.result.canonical_subject_identity
            and handoff.market_family is current.result.market_family
            and handoff.inherited_direction is current.result.inherited_direction
            and handoff.analysis_boundary == current.result.analysis_boundary
            and handoff.wo12_policy_identity == current.request.policy.policy_identity
            and handoff.wo12_policy_version == current.request.policy.policy_version
            and handoff.wo12_policy_checksum == current.request.policy.policy_checksum
        )
        now = current.result.classification in {
            Kr370AnalyticalClassification.BUY_NOW,
            Kr370AnalyticalClassification.SELL_NOW,
        }
        eligible = (
            current.eligibility.eligibility
            is Wo13EligibilityV2.ELIGIBLE_FOR_WO13_STEP31
        )
        if not exact:
            raise ValueError("WO13_SUPERSEDED_WO12_REJECTED")
        if not now or not eligible:
            raise ValueError("WO13_WO12_NOT_NOW")


def operation_document(
    request: Wo13ConstructionRequest,
    evidence: Wo13PullbackGeometryEvidence | Wo13BreakoutGeometryEvidence,
    target_population: Wo13TargetConstraintPopulation,
) -> dict[str, object]:
    """Serialize one already-validated operation for the bounded JSON transport."""

    if (
        type(request) is not Wo13ConstructionRequest
        or type(evidence)
        not in {Wo13PullbackGeometryEvidence, Wo13BreakoutGeometryEvidence}
        or type(target_population) is not Wo13TargetConstraintPopulation
    ):
        raise ValueError("WO13_OPERATION_DOCUMENT_INVALID")
    return {
        "request": _wire(request),
        "geometry_evidence": _wire(evidence),
        "target_population": _wire(target_population),
    }


def _parse_operation(payload: object) -> tuple[
    Wo13ConstructionRequest,
    Wo13PullbackGeometryEvidence | Wo13BreakoutGeometryEvidence,
    Wo13TargetConstraintPopulation,
]:
    if type(payload) is not dict or set(payload) != _OPERATION_FIELDS:
        raise ValueError("WO13_REQUEST_CONTRACT_INVALID")
    request = _parse_value(payload["request"], Wo13ConstructionRequest)
    evidence_type = (
        Wo13PullbackGeometryEvidence
        if request.handoff.setup_family
        is Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION
        else Wo13BreakoutGeometryEvidence
    )
    evidence = _parse_value(payload["geometry_evidence"], evidence_type)
    population = _parse_value(
        payload["target_population"], Wo13TargetConstraintPopulation
    )
    return request, evidence, population


def _parse_value(raw: object, expected: object) -> object:
    origin = get_origin(expected)
    args = get_args(expected)
    if origin in {types.UnionType, getattr(types, "UnionType", object)}:
        if raw is None and type(None) in args:
            return None
        candidates = tuple(item for item in args if item is not type(None))
        errors: list[Exception] = []
        for candidate in candidates:
            try:
                return _parse_value(raw, candidate)
            except (TypeError, ValueError) as error:
                errors.append(error)
        raise ValueError("WO13_REQUEST_CONTRACT_INVALID") from (errors[-1] if errors else None)
    if origin is tuple:
        if type(raw) is not list or len(args) != 2 or args[1] is not Ellipsis:
            raise ValueError("WO13_REQUEST_CONTRACT_INVALID")
        return tuple(_parse_value(item, args[0]) for item in raw)
    if expected is datetime:
        if type(raw) is not str:
            raise ValueError("WO13_REQUEST_CONTRACT_INVALID")
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("WO13_REQUEST_CONTRACT_INVALID")
        return value
    if expected is date:
        if type(raw) is not str:
            raise ValueError("WO13_REQUEST_CONTRACT_INVALID")
        return date.fromisoformat(raw)
    if expected is Decimal:
        if type(raw) is not str:
            raise ValueError("WO13_REQUEST_CONTRACT_INVALID")
        return Decimal(raw)
    if isinstance(expected, type) and issubclass(expected, StrEnum):
        if type(raw) is not str:
            raise ValueError("WO13_REQUEST_CONTRACT_INVALID")
        return expected(raw)
    if expected in {str, int, bool}:
        if type(raw) is not expected:
            raise ValueError("WO13_REQUEST_CONTRACT_INVALID")
        return raw
    if isinstance(expected, type) and is_dataclass(expected):
        if type(raw) is not dict:
            raise ValueError("WO13_REQUEST_CONTRACT_INVALID")
        expected_fields = {item.name for item in fields(expected)}
        if set(raw) != expected_fields:
            raise ValueError("WO13_REQUEST_CONTRACT_INVALID")
        hints = get_type_hints(expected)
        return expected(**{
            item.name: _parse_value(raw[item.name], hints[item.name])
            for item in fields(expected)
        })
    raise TypeError("WO13_REQUEST_CONTRACT_INVALID")


def _wire(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _wire(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, tuple):
        return [_wire(item) for item in value]
    if value is None or type(value) in {str, int, bool}:
        return value
    raise ValueError("WO13_OPERATION_DOCUMENT_INVALID")


def _plan_document(restored: object) -> dict[str, object]:
    plan = restored.trade_plan
    pointer = restored.pointer
    operation = restored.operation
    return {
        "trade_plan_identity": plan.trade_plan_identity,
        "trade_plan_integrity": plan.trade_plan_integrity,
        "request_identity": plan.request_identity,
        "source_handoff_identity": plan.source_handoff_identity,
        "source_wo12_result_identity": plan.source_wo12_result_identity,
        "canonical_subject_identity": plan.canonical_subject_identity,
        "market_family": plan.market_family.value,
        "direction": plan.direction.value,
        "setup_family": plan.setup_family.value,
        "analysis_boundary": plan.analysis_boundary.isoformat(),
        "phase": plan.phase.value,
        "instrument_identity": plan.instrument_identity,
        "actual_contract_identity": plan.actual_contract_identity,
        "entry_reference": _decimal_text(plan.entry_reference),
        "entry_condition": plan.entry_condition,
        "stop": _decimal_text(plan.stop),
        "stop_structural_basis": plan.stop_structural_basis,
        "thesis_invalidation_reference": _decimal_text(
            plan.thesis_invalidation_reference
        ),
        "thesis_invalidation_event": plan.thesis_invalidation_event,
        "setup_native_target": _decimal_text(plan.setup_native_target),
        "canonical_target": _decimal_text(plan.canonical_target),
        "target_structural_basis": plan.target_structural_basis,
        "constraining_objective": _decimal_text(plan.constraining_objective),
        "risk_distance": _decimal_text(plan.risk_distance),
        "reward_distance": _decimal_text(plan.reward_distance),
        "model_rr": _decimal_text(plan.model_rr),
        "geometry_availability": plan.geometry_availability.value,
        "field_availability": [
            {
                "field": item.field.value,
                "availability": item.availability.value,
                "reason": item.reason,
                "source_identities": list(item.source_identities),
            }
            for item in plan.field_availability
        ],
        "warnings": [item.value for item in plan.warnings],
        "policy_identity": plan.policy.policy_identity,
        "policy_version": plan.policy.policy_version,
        "policy_checksum": plan.policy.policy_checksum,
        "pointer_identity": pointer.pointer_identity,
        "operation_identity": operation.operation_identity,
        "operation_outcome": operation.outcome.value,
        "supersession_lineage_identity": pointer.supersession_lineage_identity,
        "source_evidence_identities": list(plan.source_evidence_identities),
        "provenance": list(plan.provenance),
    }


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


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
        "trade_plan": None,
    }


def _failure_code(error: Exception) -> str:
    if isinstance(error, (Wo13ApplicationError, Wo13ContractError)) and str(error):
        return str(error)
    failure = getattr(error, "failure", None)
    if isinstance(failure, StrEnum):
        return failure.value
    if isinstance(error, (Wo13PersistenceError, Wo12V2PersistenceError)):
        return "WO13_PERSISTENCE_UNAVAILABLE"
    if isinstance(error, (ValueError, TypeError)) and str(error).startswith("WO13_"):
        return str(error)
    return "WO13_OPERATION_FAILED"


__all__ = [
    "IntradayWo13OperationalControl",
    "MAX_WO13_REQUEST_BYTES",
    "WO13_CONTROL_IDENTITY",
    "WO13_CONTROL_ROUTE",
    "WO13_CONTROL_VERSION",
    "WO13_PRODUCT_ROUTE",
    "WO13_STATUS_ROUTE",
    "operation_document",
]
