"""Explicit Sponsor POST and inert status projection for Intraday WO-11."""

from __future__ import annotations

from datetime import datetime
import re

from kronos.application.intraday_wo11 import (
    IntradayWo11RuntimeService,
    Wo11ApplicationError,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10 import Wo10PolicyBinding
from kronos.intraday.wo11 import (
    WO11_CONTRACT_VERSION,
    WO11_PUBLICATION_IDENTITY,
    WO11_REQUEST_IDENTITY,
    Wo11ContractError,
    Wo11PublicationRequest,
    Wo11SourceBatchBinding,
)
from kronos.intraday.wo11_persistence import Wo11PersistenceError


WO11_CONTROL_ROUTE = "/control/intraday-wo11"
WO11_STATUS_ROUTE = "/control/intraday-wo11/status"
WO11_PRODUCT_ROUTE = "/intraday/wo11"
WO11_CONTROL_IDENTITY = "KRONOS-INTRADAY-WO11-SPONSOR-CONTROL-V1"
WO11_CONTROL_VERSION = "1.0.0"
MAX_WO11_REQUEST_BYTES = 65_536
_IDENTITY = re.compile(r"[A-Z0-9][A-Z0-9._:-]{2,255}\Z")
_REQUEST_FIELDS = {
    "request_identity", "request_integrity", "source_batches", "requested_at",
    "sponsor_operation_identity", "provenance", "schema_identity", "schema_version",
}
_SOURCE_FIELDS = {
    "market_family", "batch_identity", "batch_integrity", "request_identity",
    "request_integrity", "operation_identity", "operation_integrity",
    "policy", "probables_run_identity", "probables_run_integrity",
    "published_population",
}
_POLICY_FIELDS = {
    "policy_identity", "policy_version", "publication_identity", "policy_checksum",
    "supported_market_family", "integrity_identity", "schema_identity", "schema_version",
}


class IntradayWo11OperationalControl:
    """Accept only an exact, fully identity-bound WO-11 publication request."""

    def __init__(self, runtime: IntradayWo11RuntimeService) -> None:
        if type(runtime) is not IntradayWo11RuntimeService:
            raise ValueError("WO11_OPERATIONAL_CONTROL_INVALID")
        self._runtime = runtime

    @property
    def runtime(self) -> IntradayWo11RuntimeService:
        return self._runtime

    def status_document(self) -> dict[str, object]:
        status = self._runtime.status
        restored = status.restored
        return {
            "control_identity": WO11_CONTROL_IDENTITY,
            "control_version": WO11_CONTROL_VERSION,
            "publication_contract_identity": WO11_PUBLICATION_IDENTITY,
            "publication_contract_version": WO11_CONTRACT_VERSION,
            "request_contract_identity": WO11_REQUEST_IDENTITY,
            "request_contract_version": WO11_CONTRACT_VERSION,
            "active_operation_identity": self._runtime.active_request_identity,
            "state": status.state,
            "publication": None if restored is None else _publication_document(restored),
            "failure_stage": status.failure_stage,
            "failure_reason": status.failure_reason,
            "provider_calls": 0,
            "wo10_reruns": 0,
            "analytical_evaluations": 0,
            "autonomous_operations": 0,
        }

    def execute_document(self, payload: object) -> dict[str, object]:
        try:
            request = _parse_request(payload)
        except (ValueError, Wo11ContractError) as error:
            return _failure_document(payload, "REQUEST_VALIDATION", _failure_code(error), "REJECTED")

        try:
            existing = self._runtime.store.load_request(request.request_identity)
        except (Wo11PersistenceError, OSError):
            existing = None
        if existing is not None:
            if existing != request:
                return _failure_document(
                    payload, "REQUEST_VALIDATION", "WO11_REQUEST_IDENTITY_CONFLICT", "REJECTED"
                )
            restored = self._runtime.status.restored
            if restored is None or restored.request != request:
                return _failure_document(
                    payload, "REQUEST_VALIDATION", "WO11_REQUEST_RETAINED_INCOMPLETE", "FAILED"
                )
            return _execution_document(restored, idempotent=True)

        try:
            execution = self._runtime.execute(request)
        except Wo11ApplicationError as error:
            reason = _failure_code(error)
            return _failure_document(
                payload,
                "CONCURRENCY" if reason == "WO11_OPERATION_BUSY" else _stage(reason),
                reason,
                "BUSY" if reason == "WO11_OPERATION_BUSY" else "FAILED",
            )
        return {
            "request_identity": request.request_identity,
            "outcome": "COMPLETED",
            "idempotent": False,
            "failure_stage": None,
            "failure_reason": None,
            "publication": _execution_publication_document(execution.publication, execution.members),
        }


def _parse_request(payload: object) -> Wo11PublicationRequest:
    if (
        type(payload) is not dict
        or set(payload) != _REQUEST_FIELDS
        or payload["schema_identity"] != WO11_REQUEST_IDENTITY
        or payload["schema_version"] != WO11_CONTRACT_VERSION
        or type(payload["source_batches"]) is not list
        or not payload["source_batches"]
        or type(payload["provenance"]) is not list
        or not _valid_identity(payload["sponsor_operation_identity"])
    ):
        raise ValueError("WO11_REQUEST_CONTRACT_INVALID")
    sources = []
    for raw in payload["source_batches"]:
        if (
            type(raw) is not dict
            or set(raw) != _SOURCE_FIELDS
            or type(raw["policy"]) is not dict
            or set(raw["policy"]) != _POLICY_FIELDS
        ):
            raise ValueError("WO11_REQUEST_CONTRACT_INVALID")
        policy_raw = raw["policy"]
        sources.append(Wo11SourceBatchBinding(
            market_family=IntradayMarketFamily(raw["market_family"]),
            batch_identity=raw["batch_identity"],
            batch_integrity=raw["batch_integrity"],
            request_identity=raw["request_identity"],
            request_integrity=raw["request_integrity"],
            operation_identity=raw["operation_identity"],
            operation_integrity=raw["operation_integrity"],
            policy=Wo10PolicyBinding(
                policy_identity=policy_raw["policy_identity"],
                policy_version=policy_raw["policy_version"],
                publication_identity=policy_raw["publication_identity"],
                policy_checksum=policy_raw["policy_checksum"],
                supported_market_family=IntradayMarketFamily(
                    policy_raw["supported_market_family"]
                ),
                integrity_identity=policy_raw["integrity_identity"],
                schema_identity=policy_raw["schema_identity"],
                schema_version=policy_raw["schema_version"],
            ),
            probables_run_identity=raw["probables_run_identity"],
            probables_run_integrity=raw["probables_run_integrity"],
            published_population=raw["published_population"],
        ))
    return Wo11PublicationRequest(
        request_identity=payload["request_identity"],
        request_integrity=payload["request_integrity"],
        source_batches=tuple(sources),
        requested_at=_timestamp(payload["requested_at"]),
        sponsor_operation_identity=payload["sponsor_operation_identity"],
        provenance=tuple(payload["provenance"]),
        schema_identity=payload["schema_identity"],
        schema_version=payload["schema_version"],
    )


def _publication_document(restored):  # type: ignore[no-untyped-def]
    return _execution_publication_document(restored.publication, restored.members)


def _execution_publication_document(publication, members):  # type: ignore[no-untyped-def]
    return {
        "publication_identity": publication.publication_identity,
        "publication_integrity": publication.publication_integrity,
        "publication_boundary": publication.published_at.isoformat(),
        "source_wo10_batches": [item.batch_identity for item in publication.source_batches],
        "member_count": publication.member_count,
        "family_counts": {item.market_family.value: item.count for item in publication.family_counts},
        "state_counts": {item.state.value: item.count for item in publication.state_counts},
        "eligible_count": publication.eligible_count,
        "eligible_member_identities": list(publication.eligible_member_identities),
        "members": [{
            "canonical_subject_identity": item.canonical_subject_identity,
            "market_family": item.market_family.value,
            "inherited_direction": item.inherited_direction.value,
            "wo10_state": item.wo10_state.value,
            "wo10_reasons": [reason.code for reason in item.wo10_reasons],
            "wo10_policy_identity": item.wo10_policy.policy_identity,
            "wo10_policy_version": item.wo10_policy.policy_version,
            "downstream_eligibility": item.downstream_eligibility.value,
            "wo10_result_identity": item.wo10_result_identity,
            "evidence_snapshot_identity": item.evidence_snapshot_identity,
            "analysis_boundary": item.analysis_boundary.isoformat(),
            "persisted_phase": item.persisted_phase.value,
            "member_identity": item.member_identity,
        } for item in members],
    }


def _execution_document(restored, *, idempotent: bool):  # type: ignore[no-untyped-def]
    return {
        "request_identity": restored.request.request_identity,
        "outcome": "RETAINED",
        "idempotent": idempotent,
        "failure_stage": None,
        "failure_reason": None,
        "publication": _publication_document(restored),
    }


def _failure_document(payload, stage, reason, outcome):  # type: ignore[no-untyped-def]
    identity = payload.get("request_identity") if type(payload) is dict else None
    return {
        "request_identity": identity if _valid_identity(identity) else None,
        "outcome": outcome,
        "idempotent": False,
        "failure_stage": stage,
        "failure_reason": reason,
        "publication": None,
    }


def _timestamp(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError("WO11_REQUEST_TIMESTAMP_INVALID")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("WO11_REQUEST_TIMESTAMP_INVALID")
    return parsed


def _valid_identity(value: object) -> bool:
    return type(value) is str and _IDENTITY.fullmatch(value) is not None


def _failure_code(error: Exception) -> str:
    value = error.args[0] if error.args else None
    return value if _valid_identity(value) else "WO11_REQUEST_REJECTED"


def _stage(reason: str) -> str:
    if "BATCH" in reason or "SOURCE" in reason:
        return "WO10_BATCH_RELOAD"
    if "RESULT" in reason or "EVIDENCE" in reason:
        return "WO10_RESULT_VALIDATION"
    if "PERSIST" in reason:
        return "PUBLICATION_PERSISTENCE"
    return "COLLATION"


__all__ = [
    "IntradayWo11OperationalControl",
    "MAX_WO11_REQUEST_BYTES",
    "WO11_CONTROL_ROUTE",
    "WO11_PRODUCT_ROUTE",
    "WO11_STATUS_ROUTE",
]
