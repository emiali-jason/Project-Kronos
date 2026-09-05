"""Typed Sponsor control and inert status projection for Intraday WO-10 V2."""

from __future__ import annotations

from datetime import datetime
import re

from kronos.application.intraday_wo10 import Wo10ApplicationError
from kronos.application.intraday_wo10_runtime import IntradayWo10RuntimeService
from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import ProbablesRunV2, ProbablesV2Error
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10 import (
    WO10_CONTRACT_VERSION,
    WO10_REQUEST_IDENTITY,
    Wo10ContractError,
    Wo10PolicyBinding,
    Wo10ProbableBindingV2,
    Wo10ReconciliationRequest,
)
from kronos.intraday.wo10_persistence import Wo10PersistenceError
from kronos.intraday.wo10_policies import Wo10PolicyRegistry


WO10_CONTROL_ROUTE = "/control/intraday-wo10"
WO10_STATUS_ROUTE = "/control/intraday-wo10/status"
WO10_PRODUCT_ROUTE = "/intraday/wo10"
WO10_CONTROL_IDENTITY = "KRONOS-INTRADAY-WO10-SPONSOR-CONTROL-V1"
WO10_CONTROL_VERSION = "1.0.0"
MAX_WO10_REQUEST_BYTES = 131_072
_IDENTITY = re.compile(r"[A-Z0-9][A-Z0-9._:-]{2,255}\Z")
_REQUEST_FIELDS = {
    "request_identity",
    "request_integrity",
    "market_family",
    "probables_run_identity",
    "probables_run_integrity",
    "probable_bindings",
    "policy",
    "requested_at",
    "sponsor_operation_identity",
    "provenance",
    "schema_identity",
    "schema_version",
}
_BINDING_FIELDS = {
    "probable_result_identity",
    "probable_result_integrity",
    "canonical_subject_identity",
    "inherited_direction",
    "analysis_boundary",
    "persisted_phase",
}
_POLICY_FIELDS = {
    "policy_identity",
    "policy_version",
    "publication_identity",
    "policy_checksum",
    "supported_market_family",
    "integrity_identity",
    "schema_identity",
    "schema_version",
}


class IntradayWo10OperationalControl:
    """Validate exact retained members and invoke only on explicit POST."""

    def __init__(
        self,
        runtime: IntradayWo10RuntimeService,
        probables: ProbablesV2Store,
        policies: Wo10PolicyRegistry,
    ) -> None:
        if (
            type(runtime) is not IntradayWo10RuntimeService
            or type(probables) is not ProbablesV2Store
            or not isinstance(policies, Wo10PolicyRegistry)
        ):
            raise ValueError("WO10_OPERATIONAL_CONTROL_INVALID")
        self._runtime = runtime
        self._probables = probables
        self._policies = policies

    @property
    def runtime(self) -> IntradayWo10RuntimeService:
        return self._runtime

    def status_document(self) -> dict[str, object]:
        return {
            "control_identity": WO10_CONTROL_IDENTITY,
            "control_version": WO10_CONTROL_VERSION,
            "request_contract_identity": WO10_REQUEST_IDENTITY,
            "request_contract_version": WO10_CONTRACT_VERSION,
            "active_operation_identity": self._runtime.active_request_identity,
            "families": [
                _family_document(item) for item in self._runtime.family_statuses
            ],
            "provider_calls": 0,
            "autonomous_operations": 0,
        }

    def execute_document(self, payload: object) -> dict[str, object]:
        try:
            request = _parse_request(payload)
            self._policies.resolve(request.policy)
            self._validate_exact_members(request)
        except (ValueError, Wo10ContractError, ProbablesV2Error) as error:
            return _failure_document(
                payload, "REQUEST_VALIDATION", _failure_code(error), "REJECTED"
            )

        try:
            existing = self._runtime.store.load_request(request.request_identity)
        except Wo10PersistenceError as error:
            if isinstance(error.__cause__, FileNotFoundError):
                existing = None
            else:
                return _failure_document(payload, "RESTORATION", "WO10_REPLAY_BINDING_INVALID", "REJECTED")
        except OSError:
            return _failure_document(payload, "RESTORATION", "WO10_REPLAY_BINDING_INVALID", "REJECTED")
        if existing is not None:
            if existing != request:
                return _failure_document(
                    payload,
                    "REQUEST_VALIDATION",
                    "WO10_REQUEST_IDENTITY_CONFLICT",
                    "REJECTED",
                )
            try:
                restored = self._runtime.store.restore_request(request.request_identity)
            except (Wo10PersistenceError, OSError):
                return _failure_document(payload, "RESTORATION", "WO10_REPLAY_BINDING_INVALID", "REJECTED")
            return _execution_document(request, None, idempotent=True, restored=restored)

        try:
            execution = self._runtime.execute(request)
        except Wo10ApplicationError as error:
            reason = _failure_code(error)
            return _failure_document(
                payload,
                "CONCURRENCY" if reason == "WO10_OPERATION_BUSY" else _stage(reason),
                reason,
                "BUSY" if reason == "WO10_OPERATION_BUSY" else "FAILED",
            )
        return _execution_document(request, execution, idempotent=False)

    def _validate_exact_members(self, request: Wo10ReconciliationRequest) -> None:
        run = self._probables.load_run(request.probables_run_identity)
        if (
            type(run) is not ProbablesRunV2
            or run.integrity_identity != request.probables_run_integrity
        ):
            raise ValueError("WO10_PROBABLES_RUN_BINDING_INVALID")
        by_identity = {item.result_identity: item for item in run.results}
        for binding in request.probable_bindings:
            result = by_identity.get(binding.probable_result_identity)
            if (
                result is None
                or result.integrity_identity != binding.probable_result_integrity
                or result.canonical_subject_identity != binding.canonical_subject_identity
                or result.direction is not binding.inherited_direction
                or result.analysis_boundary != binding.analysis_boundary
                or result.phase is not binding.persisted_phase
                or result.state
                not in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}
            ):
                raise ValueError("WO10_PROBABLE_MEMBER_BINDING_INVALID")


def _parse_request(payload: object) -> Wo10ReconciliationRequest:
    if type(payload) is not dict or set(payload) != _REQUEST_FIELDS:
        raise ValueError("WO10_REQUEST_CONTRACT_INVALID")
    if (
        payload["schema_identity"] != WO10_REQUEST_IDENTITY
        or payload["schema_version"] != WO10_CONTRACT_VERSION
        or type(payload["probable_bindings"]) is not list
        or not payload["probable_bindings"]
        or type(payload["policy"]) is not dict
        or set(payload["policy"]) != _POLICY_FIELDS
        or type(payload["provenance"]) is not list
        or not _valid_identity(payload["sponsor_operation_identity"])
    ):
        raise ValueError("WO10_REQUEST_CONTRACT_INVALID")
    family = IntradayMarketFamily(payload["market_family"])
    policy_payload = payload["policy"]
    policy = Wo10PolicyBinding(
        policy_identity=policy_payload["policy_identity"],
        policy_version=policy_payload["policy_version"],
        publication_identity=policy_payload["publication_identity"],
        policy_checksum=policy_payload["policy_checksum"],
        supported_market_family=IntradayMarketFamily(
            policy_payload["supported_market_family"]
        ),
        integrity_identity=policy_payload["integrity_identity"],
        schema_identity=policy_payload["schema_identity"],
        schema_version=policy_payload["schema_version"],
    )
    bindings = []
    for raw in payload["probable_bindings"]:
        if type(raw) is not dict or set(raw) != _BINDING_FIELDS:
            raise ValueError("WO10_REQUEST_CONTRACT_INVALID")
        bindings.append(Wo10ProbableBindingV2(
            probable_result_identity=raw["probable_result_identity"],
            probable_result_integrity=raw["probable_result_integrity"],
            canonical_subject_identity=raw["canonical_subject_identity"],
            inherited_direction=SemanticDirection(raw["inherited_direction"]),
            analysis_boundary=_timestamp(raw["analysis_boundary"]),
            persisted_phase=IntradayAnalysisPhase(raw["persisted_phase"]),
        ))
    return Wo10ReconciliationRequest(
        request_identity=payload["request_identity"],
        request_integrity=payload["request_integrity"],
        market_family=family,
        probables_run_identity=payload["probables_run_identity"],
        probables_run_integrity=payload["probables_run_integrity"],
        probable_bindings=tuple(bindings),
        policy=policy,
        requested_at=_timestamp(payload["requested_at"]),
        sponsor_operation_identity=payload["sponsor_operation_identity"],
        provenance=tuple(payload["provenance"]),
        schema_identity=payload["schema_identity"],
        schema_version=payload["schema_version"],
    )


def _family_document(item):  # type: ignore[no-untyped-def]
    restored = item.restored
    if restored is None:
        return {
            "market_family": item.market_family.value,
            "state": item.state,
            "failure_stage": item.failure_stage,
            "failure_reason": item.failure_reason,
        }
    request = restored.request
    batch = restored.batch
    return {
        "market_family": item.market_family.value,
        "state": item.state,
        "request_identity": request.request_identity,
        "source_probables_run_identity": request.probables_run_identity,
        "policy": _policy_document(request.policy),
        "batch_identity": batch.batch_identity,
        "candidate_count": len(restored.results),
        "state_counts": {
            count.state.value: count.count for count in batch.state_counts
        },
        "pointer_identity": restored.pointer.pointer_identity,
        "pointer_integrity": restored.pointer.pointer_integrity,
        "results": [_result_document(result, snapshot) for result, snapshot in zip(
            restored.results, restored.evidence_snapshots, strict=True
        )],
        "failure_stage": None,
        "failure_reason": None,
    }


def _result_document(result, snapshot):  # type: ignore[no-untyped-def]
    extension = snapshot.family_extension
    context = {
        "nifty_context": getattr(extension, "nifty_relationship", None) is not None,
        "weekly_map": getattr(extension, "weekly_structural_map", None) is not None,
        "daily_map": getattr(extension, "daily_structural_map", None) is not None,
        "actual_contract": _ref_identity(getattr(extension, "actual_contract", None)),
        "reference_relationship": _ref_identity(
            getattr(extension, "reference_relationship", None)
        ),
        "usdinr_context": _ref_identity(
            getattr(extension, "session_reference_context", None)
        ),
        "commissioning": _ref_identity(
            getattr(extension, "commissioning_publication", None)
        ),
        "roll_history": _ref_identity(getattr(extension, "roll_history", None)),
    }
    return {
        "canonical_subject_identity": result.canonical_subject_identity,
        "market_family": result.market_family.value,
        "inherited_direction": result.inherited_direction.value,
        "policy_identity": result.policy.policy_identity,
        "policy_version": result.policy.policy_version,
        "source_probables_run_identity": snapshot.probables_run_identity,
        "analysis_boundary": result.analysis_boundary.isoformat(),
        "persisted_phase": result.persisted_phase.value,
        "state": result.state.value,
        "reasons": [item.code for item in result.reasons],
        "evidence_snapshot_identity": result.evidence_snapshot_identity,
        "evidence_source_count": len(snapshot.source_references),
        "context": context,
        "result_identity": result.result_identity,
    }


def _execution_document(
    request, execution, *, idempotent, restored=None
):  # type: ignore[no-untyped-def]
    if execution is None:
        candidates = [] if restored is None else [
            {
                "canonical_subject_identity": result.canonical_subject_identity,
                "result_identity": result.result_identity,
                "state": result.state.value,
                "failure_reason": None,
            }
            for result in restored.results
        ]
        batch_identity = None if restored is None else restored.batch.batch_identity
        outcome = "RETAINED" if restored is not None else "FAILED"
    else:
        candidates = [
            {
                "canonical_subject_identity": item.canonical_subject_identity,
                "result_identity": item.reconciliation_result_identity,
                "state": item.state,
                "failure_reason": item.failure_reason,
            }
            for item in execution.candidates
        ]
        batch_identity = None if execution.batch is None else execution.batch.batch_identity
        outcome = "COMPLETED" if execution.completed else "FAILED"
    return {
        "request_identity": request.request_identity,
        "market_family": request.market_family.value,
        "outcome": outcome,
        "idempotent": idempotent,
        "failure_stage": None if outcome in {"COMPLETED", "RETAINED"} else "EVALUATION",
        "failure_reason": (
            None
            if outcome in {"COMPLETED", "RETAINED"}
            else "WO10_RETAINED_INCOMPLETE"
            if execution is None
            else "WO10_BATCH_INCOMPLETE"
        ),
        "batch_identity": batch_identity,
        "candidates": candidates,
    }


def _failure_document(payload, stage, reason, outcome):  # type: ignore[no-untyped-def]
    identity = payload.get("request_identity") if type(payload) is dict else None
    return {
        "request_identity": identity if _valid_identity(identity) else None,
        "market_family": payload.get("market_family") if type(payload) is dict else None,
        "outcome": outcome,
        "idempotent": False,
        "failure_stage": stage,
        "failure_reason": reason,
        "batch_identity": None,
        "candidates": [],
    }


def _policy_document(value: Wo10PolicyBinding) -> dict[str, str]:
    return {
        "identity": value.policy_identity,
        "version": value.policy_version,
        "publication": value.publication_identity,
        "checksum": value.policy_checksum,
    }


def _ref_identity(value: object) -> str | None:
    return getattr(value, "evidence_identity", None)


def _timestamp(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError("WO10_REQUEST_TIMESTAMP_INVALID")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("WO10_REQUEST_TIMESTAMP_INVALID")
    return parsed


def _valid_identity(value: object) -> bool:
    return type(value) is str and _IDENTITY.fullmatch(value) is not None


def _failure_code(error: Exception) -> str:
    value = error.args[0] if error.args else None
    return value if _valid_identity(value) else "WO10_REQUEST_REJECTED"


def _stage(reason: str) -> str:
    if "RUN" in reason:
        return "RUN_RELOAD"
    if "MEMBER" in reason or "BINDING" in reason:
        return "CANDIDATE_BINDING"
    if "EVIDENCE" in reason or "CHART" in reason or "REVIEW" in reason:
        return "EVIDENCE_SNAPSHOT"
    if "POLICY" in reason:
        return "POLICY_DISPATCH"
    if "PERSIST" in reason:
        return "RESULT_PERSISTENCE"
    return "EVALUATION"


__all__ = [
    "IntradayWo10OperationalControl",
    "MAX_WO10_REQUEST_BYTES",
    "WO10_CONTROL_ROUTE",
    "WO10_PRODUCT_ROUTE",
    "WO10_STATUS_ROUTE",
]
