"""Explicit Sponsor control and inert projection for Intraday WO-12 V2."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import re

from kronos.application.intraday_wo12_v2 import (
    IntradayWo12V2RuntimeService,
    Wo12V2ApplicationError,
)
from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.probables_v2 import (
    SemanticEvidenceRoleV2,
    SemanticQualificationFactV2,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo12 import Wo12ContractError, create_wo12_handoff
from kronos.intraday.wo12_facts import (
    Wo12CprAcceptanceFact,
    Wo12PathClearanceFact,
    Wo12PathState,
    Wo12SetupQualityFact,
    Wo12SetupQualityState,
)
from kronos.intraday.wo12_v2 import (
    WO12_V2_CONTRACT_VERSION,
    WO12_V2_POLICY_IDENTITY,
    WO12_V2_REQUEST_IDENTITY,
    Wo12EvidenceInputsV2,
    Wo12RequestV2,
    create_wo12_request_v2,
)
from kronos.intraday.wo12_v2_persistence import Wo12V2PersistenceError


WO12_V2_CONTROL_ROUTE = "/control/intraday-wo12"
WO12_V2_STATUS_ROUTE = "/control/intraday-wo12/status"
WO12_V2_PRODUCT_ROUTE = "/intraday/wo12"
WO12_V2_CONTROL_IDENTITY = "KRONOS-INTRADAY-WO12-V2-SPONSOR-CONTROL-V1"
WO12_V2_CONTROL_VERSION = "1.0.0"
MAX_WO12_V2_REQUEST_BYTES = 131_072
_IDENTITY = re.compile(r"[A-Z0-9][A-Z0-9._:-]{2,255}\Z")
_REQUEST_FIELDS = {
    "request_identity",
    "request_integrity",
    "handoff",
    "policy",
    "requested_at",
    "sponsor_operation_identity",
    "provenance",
    "schema_identity",
    "schema_version",
    "evidence_inputs",
}
_INPUT_FIELDS = {
    "fifteen_minute_structure",
    "cpr_acceptance",
    "path_clearance",
    "setup_quality",
    "governing_15m_structure_failed",
    "authoritative_directional_conflict",
}


class IntradayWo12V2OperationalControl:
    """Require exact retained lineage and pre-acquired K1-K4 evidence."""

    def __init__(self, runtime: IntradayWo12V2RuntimeService) -> None:
        if type(runtime) is not IntradayWo12V2RuntimeService:
            raise ValueError("WO12_V2_OPERATIONAL_CONTROL_INVALID")
        self._runtime = runtime

    @property
    def runtime(self) -> IntradayWo12V2RuntimeService:
        return self._runtime

    def status_document(self) -> dict[str, object]:
        status = self._runtime.status
        return {
            "control_identity": WO12_V2_CONTROL_IDENTITY,
            "control_version": WO12_V2_CONTROL_VERSION,
            "request_contract_identity": WO12_V2_REQUEST_IDENTITY,
            "request_contract_version": WO12_V2_CONTRACT_VERSION,
            "policy_identity": WO12_V2_POLICY_IDENTITY,
            "policy_version": WO12_V2_CONTRACT_VERSION,
            "active_operation_identity": self._runtime.active_request_identity,
            "state": status.state,
            "restored_result": (
                None if status.restored is None else _restored_document(status.restored)
            ),
            "failure_stage": status.failure_stage,
            "failure_reason": status.failure_reason,
            "provider_calls": 0,
            "upstream_operations": 0,
            "autonomous_operations": 0,
        }

    def execute_document(self, payload: object) -> dict[str, object]:
        try:
            request, inputs = self._parse_exact_operation(payload)
        except (ValueError, Wo12ContractError, Wo12V2PersistenceError) as error:
            reason = self._request_failure(payload, error)
            return _failure_document(payload, "REQUEST_VALIDATION", reason, "REJECTED")

        try:
            existing = self._runtime.store.load_request(request.request_identity)
        except (Wo12V2PersistenceError, OSError):
            existing = None
        if existing is not None:
            if existing != request:
                return _failure_document(
                    payload,
                    "REQUEST_VALIDATION",
                    "WO12_V2_REQUEST_IDENTITY_CONFLICT",
                    "REJECTED",
                )
            restored = self._runtime.status.restored
            if restored is None or restored.request != request:
                return _failure_document(
                    payload,
                    "RESTORATION",
                    "WO12_V2_REQUEST_RETAINED_INCOMPLETE",
                    "FAILED",
                )
            return _execution_document(restored, idempotent=True, outcome="RETAINED")

        try:
            execution = self._runtime.execute(request, inputs)
        except Wo12V2ApplicationError as error:
            reason = _failure_code(error)
            return _failure_document(
                payload,
                "CONCURRENCY" if reason == "WO12_V2_OPERATION_BUSY" else _stage(reason),
                reason,
                "BUSY" if reason == "WO12_V2_OPERATION_BUSY" else "FAILED",
            )
        restored = self._runtime.status.restored
        if restored is None or restored.result != execution.result:
            return _failure_document(
                payload, "RESTORATION", "WO12_V2_POST_EXECUTION_RESTORE_FAILED", "FAILED"
            )
        return _execution_document(restored, idempotent=False, outcome="COMPLETED")

    def _parse_exact_operation(
        self, payload: object
    ) -> tuple[Wo12RequestV2, Wo12EvidenceInputsV2]:
        if type(payload) is not dict or set(payload) != _REQUEST_FIELDS:
            raise ValueError("WO12_V2_REQUEST_CONTRACT_INVALID")
        handoff_payload = payload["handoff"]
        if type(handoff_payload) is not dict:
            raise ValueError("WO12_V2_REQUEST_CONTRACT_INVALID")
        publication_identity = handoff_payload.get("wo11_publication_identity")
        member_identity = handoff_payload.get("wo11_member_identity")
        if not _valid_identity(publication_identity) or not _valid_identity(member_identity):
            raise ValueError("WO12_V2_EXACT_WO11_BINDING_INVALID")
        publication = self._runtime.application.wo11_store.load_publication(
            publication_identity
        )
        member = self._runtime.application.wo11_store.load_member(member_identity)
        reference = self._runtime.application.wo11_store.load_handoff(
            publication_identity, member_identity
        )
        handoff = create_wo12_handoff(
            publication=publication,
            member=member,
            wo11_handoff=reference,
        )
        if handoff_payload != _wire(handoff):
            raise ValueError("WO12_V2_EXACT_WO11_BINDING_INVALID")
        request = create_wo12_request_v2(
            handoff=handoff,
            requested_at=_timestamp(payload["requested_at"]),
            sponsor_operation_identity=_identity(payload["sponsor_operation_identity"]),
            provenance=_text_tuple(payload["provenance"]),
        )
        request_document = _wire(request)
        supplied_request = {
            key: value for key, value in payload.items() if key != "evidence_inputs"
        }
        if supplied_request != request_document:
            raise ValueError("WO12_V2_REQUEST_IDENTITY_OR_CONTENT_INVALID")
        inputs = _parse_inputs(payload["evidence_inputs"])
        return request, inputs

    def _request_failure(self, payload: object, error: Exception) -> str:
        identity = payload.get("request_identity") if type(payload) is dict else None
        if _valid_identity(identity):
            try:
                self._runtime.store.load_request(identity)
            except (Wo12V2PersistenceError, OSError):
                pass
            else:
                return "WO12_V2_REQUEST_IDENTITY_CONFLICT"
        return _failure_code(error)


def _parse_inputs(payload: object) -> Wo12EvidenceInputsV2:
    if type(payload) is not dict or set(payload) != _INPUT_FIELDS:
        raise ValueError("WO12_V2_EVIDENCE_INPUTS_INVALID")
    if (
        type(payload["governing_15m_structure_failed"]) is not bool
        or type(payload["authoritative_directional_conflict"]) is not bool
    ):
        raise ValueError("WO12_V2_EVIDENCE_INPUTS_INVALID")
    return Wo12EvidenceInputsV2(
        fifteen_minute_structure=_semantic_fact(payload["fifteen_minute_structure"]),
        cpr_acceptance=_cpr_fact(payload["cpr_acceptance"]),
        path_clearance=_path_fact(payload["path_clearance"]),
        setup_quality=_quality_fact(payload["setup_quality"]),
        governing_15m_structure_failed=payload["governing_15m_structure_failed"],
        authoritative_directional_conflict=payload[
            "authoritative_directional_conflict"
        ],
    )


def _semantic_fact(raw: object) -> SemanticQualificationFactV2:
    _exact_dataclass_fields(raw, SemanticQualificationFactV2)
    return SemanticQualificationFactV2(
        fact_identity=raw["fact_identity"],
        family=raw["family"],
        canonical_subject_identity=raw["canonical_subject_identity"],
        analysis_boundary=_timestamp(raw["analysis_boundary"]),
        phase=IntradayAnalysisPhase(raw["phase"]),
        availability=raw["availability"],
        direction=SemanticDirection(raw["direction"]),
        evidence_role=SemanticEvidenceRoleV2(raw["evidence_role"]),
        source_evidence_identities=_text_tuple(raw["source_evidence_identities"]),
        attributes=_attributes(raw["attributes"]),
        integrity_identity=raw["integrity_identity"],
        schema_identity=raw["schema_identity"],
        schema_version=raw["schema_version"],
    )


def _cpr_fact(raw: object) -> Wo12CprAcceptanceFact:
    _exact_dataclass_fields(raw, Wo12CprAcceptanceFact)
    return Wo12CprAcceptanceFact(
        fact_identity=raw["fact_identity"],
        fact_integrity=raw["fact_integrity"],
        canonical_subject_identity=raw["canonical_subject_identity"],
        market_family=IntradayMarketFamily(raw["market_family"]),
        analysis_boundary=_timestamp(raw["analysis_boundary"]),
        completed_close=_optional_decimal(raw["completed_close"]),
        cpr_lower=_optional_decimal(raw["cpr_lower"]),
        cpr_upper=_optional_decimal(raw["cpr_upper"]),
        completed_candle_identity=_optional_identity(raw["completed_candle_identity"]),
        cpr_evidence_identity=_optional_identity(raw["cpr_evidence_identity"]),
        source_evidence_integrities=_text_tuple(raw["source_evidence_integrities"]),
        schema_identity=raw["schema_identity"],
        schema_version=raw["schema_version"],
    )


def _path_fact(raw: object) -> Wo12PathClearanceFact:
    _exact_dataclass_fields(raw, Wo12PathClearanceFact)
    return Wo12PathClearanceFact(
        fact_identity=raw["fact_identity"],
        fact_integrity=raw["fact_integrity"],
        canonical_subject_identity=raw["canonical_subject_identity"],
        market_family=IntradayMarketFamily(raw["market_family"]),
        analysis_boundary=_timestamp(raw["analysis_boundary"]),
        state=Wo12PathState(raw["state"]),
        source_evidence_identities=_text_tuple(raw["source_evidence_identities"]),
        source_evidence_integrities=_text_tuple(raw["source_evidence_integrities"]),
        predicate_identity=raw["predicate_identity"],
        schema_identity=raw["schema_identity"],
        schema_version=raw["schema_version"],
    )


def _quality_fact(raw: object) -> Wo12SetupQualityFact:
    _exact_dataclass_fields(raw, Wo12SetupQualityFact)
    return Wo12SetupQualityFact(
        fact_identity=raw["fact_identity"],
        fact_integrity=raw["fact_integrity"],
        canonical_subject_identity=raw["canonical_subject_identity"],
        market_family=IntradayMarketFamily(raw["market_family"]),
        analysis_boundary=_timestamp(raw["analysis_boundary"]),
        state=Wo12SetupQualityState(raw["state"]),
        source_evidence_identities=_text_tuple(raw["source_evidence_identities"]),
        source_evidence_integrities=_text_tuple(raw["source_evidence_integrities"]),
        adapter_identity=raw["adapter_identity"],
        schema_identity=raw["schema_identity"],
        schema_version=raw["schema_version"],
    )


def _restored_document(restored: object) -> dict[str, object]:
    request = restored.request
    result = restored.result
    eligibility = restored.eligibility
    return {
        "request_identity": request.request_identity,
        "request_integrity": request.request_integrity,
        "source_wo11_publication_identity": request.handoff.wo11_publication_identity,
        "source_wo11_member_identity": request.handoff.wo11_member_identity,
        "source_wo10_result_identity": request.handoff.wo10_result_identity,
        "source_probables_run_identity": request.handoff.probables_run_identity,
        "canonical_subject_identity": result.canonical_subject_identity,
        "market_family": result.market_family.value,
        "inherited_direction": result.inherited_direction.value,
        "analysis_boundary": result.analysis_boundary.isoformat(),
        "phase": result.phase.value,
        "criteria": [
            {
                "identity": item.identity.value,
                "state": item.state.value,
                "reason": item.reason,
                "evidence_identities": list(item.evidence_identities),
                "evidence_integrities": list(item.evidence_integrities),
            }
            for item in result.criteria
        ],
        "satisfied_count": result.satisfied_count,
        "criterion_count": 4,
        "unavailable_criteria": [item.value for item in result.unavailable_criteria],
        "hard_gates": [item.value for item in result.hard_gates],
        "classification": result.classification.value,
        "wo13_eligibility": eligibility.eligibility.value,
        "policy_identity": result.policy.policy_identity,
        "policy_version": result.policy.policy_version,
        "policy_checksum": result.policy.policy_checksum,
        "result_identity": result.result_identity,
        "result_integrity": result.result_integrity,
        "pointer_identity": restored.pointer.pointer_identity,
        "pointer_integrity": restored.pointer.pointer_integrity,
        "provenance": list(result.provenance),
    }


def _execution_document(restored: object, *, idempotent: bool, outcome: str) -> dict[str, object]:
    return {
        "request_identity": restored.request.request_identity,
        "outcome": outcome,
        "idempotent": idempotent,
        "failure_stage": None,
        "failure_reason": None,
        "result": _restored_document(restored),
    }


def _failure_document(payload: object, stage: str, reason: str, outcome: str) -> dict[str, object]:
    identity = payload.get("request_identity") if type(payload) is dict else None
    return {
        "request_identity": identity if _valid_identity(identity) else None,
        "outcome": outcome,
        "idempotent": False,
        "failure_stage": stage,
        "failure_reason": reason,
        "result": None,
    }


def _wire(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _wire(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple):
        return [_wire(item) for item in value]
    if type(value) is dict:
        return {str(key): _wire(item) for key, item in value.items()}
    return value


def operation_document(request: object, inputs: Wo12EvidenceInputsV2) -> dict[str, object]:
    """Return the exact JSON operation contract for an already-built request."""

    document = _wire(request)
    if type(document) is not dict or type(inputs) is not Wo12EvidenceInputsV2:
        raise ValueError("WO12_V2_OPERATION_DOCUMENT_INVALID")
    return {**document, "evidence_inputs": _wire(inputs)}


def _exact_dataclass_fields(raw: object, expected: type) -> None:
    if type(raw) is not dict or set(raw) != {item.name for item in fields(expected)}:
        raise ValueError("WO12_V2_EVIDENCE_INPUTS_INVALID")


def _timestamp(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError("WO12_V2_TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("WO12_V2_TIMESTAMP_INVALID") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("WO12_V2_TIMESTAMP_INVALID")
    return parsed


def _identity(value: object) -> str:
    if not _valid_identity(value):
        raise ValueError("WO12_V2_IDENTITY_INVALID")
    return value


def _optional_identity(value: object) -> str | None:
    return None if value is None else _identity(value)


def _text_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not list or not value or any(type(item) is not str for item in value):
        raise ValueError("WO12_V2_TEXT_SEQUENCE_INVALID")
    return tuple(value)


def _attributes(value: object) -> tuple[tuple[str, str], ...]:
    if (
        type(value) is not list
        or any(type(item) is not list or len(item) != 2 for item in value)
        or any(type(part) is not str for item in value for part in item)
    ):
        raise ValueError("WO12_V2_ATTRIBUTES_INVALID")
    return tuple((item[0], item[1]) for item in value)


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError("WO12_V2_DECIMAL_INVALID")
    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise ValueError("WO12_V2_DECIMAL_INVALID") from error


def _valid_identity(value: object) -> bool:
    return type(value) is str and _IDENTITY.fullmatch(value) is not None


def _failure_code(error: Exception) -> str:
    value = error.args[0] if error.args else None
    return (
        value
        if type(value) is str and value.startswith("WO12_") and len(value) <= 128
        else "WO12_V2_REQUEST_REJECTED"
    )


def _stage(reason: str) -> str:
    if "WO11" in reason or "WO10" in reason or "LINEAGE" in reason:
        return "SOURCE_RELOAD"
    if "PERSIST" in reason or "RESTORE" in reason:
        return "PERSISTENCE"
    return "EVIDENCE_EVALUATION"


__all__ = [
    "IntradayWo12V2OperationalControl",
    "MAX_WO12_V2_REQUEST_BYTES",
    "WO12_V2_CONTROL_ROUTE",
    "WO12_V2_PRODUCT_ROUTE",
    "WO12_V2_STATUS_ROUTE",
    "operation_document",
]
