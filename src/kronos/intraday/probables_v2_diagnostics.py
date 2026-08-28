"""Immutable, Provider-independent replay and sanitized V2 failure evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Mapping

from kronos.intraday.discovery import NativeDiscoveryMachineFactBundle, NativeDiscoveryRun
from kronos.intraday.discovery_runtime import DiscoveryRuntimeExecution
from kronos.intraday.probables_v2 import (
    PROBABLES_V2_METHODOLOGY_CHECKSUM,
    PROBABLES_V2_METHODOLOGY_IDENTITY,
    PROBABLES_V2_METHODOLOGY_VERSION,
    PROBABLES_V2_PUBLICATION_IDENTITY,
)
from kronos.intraday.probables_v2_refresh import (
    DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY,
    DISCOVERY_PROBABLES_V2_REFRESH_VERSION,
    DiscoveryProbablesV2Facts,
    DiscoveryProbablesV2Mapping,
    map_discovery_execution_to_probables_v2,
)
from kronos.intraday.reconciliation import ReconciliationPublication


PROBABLES_V2_REPLAY_ENVELOPE_IDENTITY = (
    "KRONOS-INTRADAY-PROBABLES-V2-REPLAY-ENVELOPE-V1"
)
PROBABLES_V2_REPLAY_ENVELOPE_VERSION = "1.0.0"
PROBABLES_V2_FAILURE_DETAIL_IDENTITY = (
    "KRONOS-INTRADAY-PROBABLES-V2-FAILURE-DETAIL-V1"
)
PROBABLES_V2_FAILURE_DETAIL_VERSION = "1.0.0"
FAILURE_DETAIL_MAX_LENGTH = 240


class ProbablesV2ExceptionCategory(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    IDENTITY_ERROR = "IDENTITY_ERROR"
    BOUNDARY_ERROR = "BOUNDARY_ERROR"
    MAPPING_ERROR = "MAPPING_ERROR"
    PHASE_SELECTION_ERROR = "PHASE_SELECTION_ERROR"
    SEMANTIC_ERROR = "SEMANTIC_ERROR"
    NIFTY_CONTEXT_ERROR = "NIFTY_CONTEXT_ERROR"
    SCHEMA_ERROR = "SCHEMA_ERROR"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"
    VALUE_ERROR = "VALUE_ERROR"
    TYPE_ERROR = "TYPE_ERROR"
    KEY_ERROR = "KEY_ERROR"
    UNEXPECTED_INTERNAL_ERROR = "UNEXPECTED_INTERNAL_ERROR"


@dataclass(frozen=True, slots=True)
class ProbablesV2ReplayEnvelope:
    envelope_identity: str
    request_identity: str
    operation_identity: str
    analysis_boundary: datetime
    discovery_run: NativeDiscoveryRun
    machine_fact_bundles: tuple[NativeDiscoveryMachineFactBundle, ...]
    probables_v2_facts: tuple[DiscoveryProbablesV2Facts, ...]
    reconciliation: ReconciliationPublication
    pre_evaluable_count: int
    prerequisite_unavailable_count: int
    timeframe_fact_requests: int
    source_operation_count: int
    methodology_identity: str
    methodology_version: str
    methodology_publication_identity: str
    methodology_checksum: str
    mapping_policy_identity: str
    mapping_policy_version: str
    created_at: datetime
    provenance: tuple[str, ...]
    integrity_identity: str
    contract_identity: str = PROBABLES_V2_REPLAY_ENVELOPE_IDENTITY
    contract_version: str = PROBABLES_V2_REPLAY_ENVELOPE_VERSION

    def __post_init__(self) -> None:
        core = _without(self, "envelope_identity", "integrity_identity")
        member_ids = tuple(item.universe_member_identity for item in self.probables_v2_facts)
        bundle_ids = tuple(item.bundle_identity for item in self.machine_fact_bundles)
        if (
            not self.envelope_identity.startswith("INTRADAY-PROBABLES-V2-REPLAY-ENVELOPE-")
            or not _component(self.request_identity)
            or not _component(self.operation_identity)
            or not _aware(self.analysis_boundary)
            or type(self.discovery_run) is not NativeDiscoveryRun
            or self.discovery_run.observation_boundary != self.analysis_boundary
            or any(type(item) is not NativeDiscoveryMachineFactBundle for item in self.machine_fact_bundles)
            or len(bundle_ids) != len(set(bundle_ids))
            or any(type(item) is not DiscoveryProbablesV2Facts for item in self.probables_v2_facts)
            or len(member_ids) != len(set(member_ids))
            or any(item.observation_boundary != self.analysis_boundary for item in self.probables_v2_facts)
            or type(self.reconciliation) is not ReconciliationPublication
            or self.reconciliation.integrity_identity != self.discovery_run.reconciliation_integrity_identity
            or any(type(value) is not int or value < 0 for value in (
                self.pre_evaluable_count,
                self.prerequisite_unavailable_count,
                self.timeframe_fact_requests,
                self.source_operation_count,
            ))
            or self.methodology_identity != PROBABLES_V2_METHODOLOGY_IDENTITY
            or self.methodology_version != PROBABLES_V2_METHODOLOGY_VERSION
            or self.methodology_publication_identity != PROBABLES_V2_PUBLICATION_IDENTITY
            or self.methodology_checksum != PROBABLES_V2_METHODOLOGY_CHECKSUM
            or self.mapping_policy_identity != DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY
            or self.mapping_policy_version != DISCOVERY_PROBABLES_V2_REFRESH_VERSION
            or not _aware(self.created_at)
            or not _texts(self.provenance)
            or self.contract_identity != PROBABLES_V2_REPLAY_ENVELOPE_IDENTITY
            or self.contract_version != PROBABLES_V2_REPLAY_ENVELOPE_VERSION
            or self.envelope_identity != _identity("INTRADAY-PROBABLES-V2-REPLAY-ENVELOPE-", core)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-PROBABLES-V2-REPLAY-ENVELOPE-", core)
        ):
            raise ValueError("INTRADAY_PROBABLES_V2_REPLAY_ENVELOPE_INVALID")


@dataclass(frozen=True, slots=True)
class ProbablesV2FailureDetail:
    failure_identity: str
    request_identity: str
    operation_identity: str
    replay_envelope_identity: str | None
    operation_stage: str
    typed_reason_code: str
    exception_category: ProbablesV2ExceptionCategory
    sanitized_detail: str
    affected_canonical_subject_identity: str | None
    affected_result_identity: str | None
    analysis_boundary: datetime
    methodology_identity: str
    methodology_version: str
    methodology_publication_identity: str
    methodology_checksum: str
    created_at: datetime
    integrity_identity: str
    contract_identity: str = PROBABLES_V2_FAILURE_DETAIL_IDENTITY
    contract_version: str = PROBABLES_V2_FAILURE_DETAIL_VERSION

    def __post_init__(self) -> None:
        core = _without(self, "failure_identity", "integrity_identity")
        if (
            not self.failure_identity.startswith("INTRADAY-PROBABLES-V2-FAILURE-")
            or not _component(self.request_identity)
            or not _component(self.operation_identity)
            or (self.replay_envelope_identity is not None and not _component(self.replay_envelope_identity))
            or not _component(self.operation_stage)
            or not _component(self.typed_reason_code)
            or type(self.exception_category) is not ProbablesV2ExceptionCategory
            or not _safe_detail(self.sanitized_detail)
            or any(value is not None and not _component(value) for value in (
                self.affected_canonical_subject_identity,
                self.affected_result_identity,
            ))
            or not _aware(self.analysis_boundary)
            or self.methodology_identity != PROBABLES_V2_METHODOLOGY_IDENTITY
            or self.methodology_version != PROBABLES_V2_METHODOLOGY_VERSION
            or self.methodology_publication_identity != PROBABLES_V2_PUBLICATION_IDENTITY
            or self.methodology_checksum != PROBABLES_V2_METHODOLOGY_CHECKSUM
            or not _aware(self.created_at)
            or self.contract_identity != PROBABLES_V2_FAILURE_DETAIL_IDENTITY
            or self.contract_version != PROBABLES_V2_FAILURE_DETAIL_VERSION
            or self.failure_identity != _identity("INTRADAY-PROBABLES-V2-FAILURE-", core)
            or self.integrity_identity != _identity("INTEGRITY-INTRADAY-PROBABLES-V2-FAILURE-", core)
        ):
            raise ValueError("INTRADAY_PROBABLES_V2_FAILURE_DETAIL_INVALID")


def create_probables_v2_replay_envelope(
    *, request_identity: str, operation_identity: str,
    execution: DiscoveryRuntimeExecution, reconciliation: ReconciliationPublication,
    created_at: datetime,
) -> ProbablesV2ReplayEnvelope:
    if type(execution) is not DiscoveryRuntimeExecution:
        raise ValueError("INTRADAY_PROBABLES_V2_REPLAY_ENVELOPE_INPUT_INVALID")
    values = {
        "request_identity": request_identity,
        "operation_identity": operation_identity,
        "analysis_boundary": execution.run.observation_boundary,
        "discovery_run": execution.run,
        "machine_fact_bundles": execution.bundles,
        "probables_v2_facts": execution.probables_v2_facts,
        "reconciliation": reconciliation,
        "pre_evaluable_count": execution.pre_evaluable_count,
        "prerequisite_unavailable_count": execution.prerequisite_unavailable_count,
        "timeframe_fact_requests": execution.timeframe_fact_requests,
        "source_operation_count": execution.source_operation_count,
        "methodology_identity": PROBABLES_V2_METHODOLOGY_IDENTITY,
        "methodology_version": PROBABLES_V2_METHODOLOGY_VERSION,
        "methodology_publication_identity": PROBABLES_V2_PUBLICATION_IDENTITY,
        "methodology_checksum": PROBABLES_V2_METHODOLOGY_CHECKSUM,
        "mapping_policy_identity": DISCOVERY_PROBABLES_V2_REFRESH_IDENTITY,
        "mapping_policy_version": DISCOVERY_PROBABLES_V2_REFRESH_VERSION,
        "created_at": created_at,
        "provenance": (
            "KRONOS-INTRADAY-V2-LIVE-DIAGNOSTIC-INSTRUMENTATION",
            execution.run.run_identity,
            reconciliation.integrity_identity,
            "IMMUTABLE_REPLAY_EVIDENCE_ONLY",
        ),
        "contract_identity": PROBABLES_V2_REPLAY_ENVELOPE_IDENTITY,
        "contract_version": PROBABLES_V2_REPLAY_ENVELOPE_VERSION,
    }
    return ProbablesV2ReplayEnvelope(
        envelope_identity=_identity("INTRADAY-PROBABLES-V2-REPLAY-ENVELOPE-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-PROBABLES-V2-REPLAY-ENVELOPE-", values),
        **values,
    )


def reconstruct_v2_execution(envelope: ProbablesV2ReplayEnvelope) -> DiscoveryRuntimeExecution:
    if type(envelope) is not ProbablesV2ReplayEnvelope:
        raise ValueError("INTRADAY_PROBABLES_V2_REPLAY_ENVELOPE_INVALID")
    return DiscoveryRuntimeExecution(
        run=envelope.discovery_run,
        bundles=envelope.machine_fact_bundles,
        evidence=(),
        probables_facts=(),
        pre_evaluable_count=envelope.pre_evaluable_count,
        prerequisite_unavailable_count=envelope.prerequisite_unavailable_count,
        timeframe_fact_requests=envelope.timeframe_fact_requests,
        source_operation_count=envelope.source_operation_count,
        probables_v2_facts=envelope.probables_v2_facts,
    )


def replay_v2_mapping(envelope: ProbablesV2ReplayEnvelope) -> DiscoveryProbablesV2Mapping:
    return map_discovery_execution_to_probables_v2(
        execution=reconstruct_v2_execution(envelope),
        reconciliation=envelope.reconciliation,
    )


def create_probables_v2_failure_detail(
    *, request_identity: str, operation_identity: str,
    replay_envelope_identity: str | None, operation_stage: str,
    error: BaseException, analysis_boundary: datetime, created_at: datetime,
) -> ProbablesV2FailureDetail:
    diagnostic_error = _bounded_cause(error)
    category = _category(diagnostic_error, operation_stage)
    affected_subject = _safe_component(
        getattr(diagnostic_error, "canonical_subject_identity", None)
    )
    affected_result = _safe_component(getattr(diagnostic_error, "result_identity", None))
    values = {
        "request_identity": request_identity,
        "operation_identity": operation_identity,
        "replay_envelope_identity": replay_envelope_identity,
        "operation_stage": operation_stage,
        "typed_reason_code": f"PROBABLES_V2_{category.value}",
        "exception_category": category,
        "sanitized_detail": sanitize_failure_detail(diagnostic_error, category),
        "affected_canonical_subject_identity": affected_subject,
        "affected_result_identity": affected_result,
        "analysis_boundary": analysis_boundary,
        "methodology_identity": PROBABLES_V2_METHODOLOGY_IDENTITY,
        "methodology_version": PROBABLES_V2_METHODOLOGY_VERSION,
        "methodology_publication_identity": PROBABLES_V2_PUBLICATION_IDENTITY,
        "methodology_checksum": PROBABLES_V2_METHODOLOGY_CHECKSUM,
        "created_at": created_at,
        "contract_identity": PROBABLES_V2_FAILURE_DETAIL_IDENTITY,
        "contract_version": PROBABLES_V2_FAILURE_DETAIL_VERSION,
    }
    return ProbablesV2FailureDetail(
        failure_identity=_identity("INTRADAY-PROBABLES-V2-FAILURE-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-PROBABLES-V2-FAILURE-", values),
        **values,
    )


def sanitize_failure_detail(error: BaseException, category: ProbablesV2ExceptionCategory) -> str:
    text = str(error).strip()
    if category is ProbablesV2ExceptionCategory.UNEXPECTED_INTERNAL_ERROR:
        return category.value
    if any(term in text.lower() for term in (
        "token", "secret", "cookie", "authorization", "credential", "password",
        "api_key", "api-key", "access_token", "refresh_token", "bearer ",
    )):
        return category.value
    if text != text.upper():
        return category.value
    if not re.fullmatch(r"[A-Za-z0-9_:. ()\[\],=+\-]{1,240}", text):
        return category.value
    return text[:FAILURE_DETAIL_MAX_LENGTH]


def _category(error: BaseException, stage: str) -> ProbablesV2ExceptionCategory:
    detail = str(error).upper()
    if "NIFTY" in detail:
        return ProbablesV2ExceptionCategory.NIFTY_CONTEXT_ERROR
    if "OPENING" in detail or "SEMANTIC" in detail:
        return ProbablesV2ExceptionCategory.SEMANTIC_ERROR
    if "PHASE" in detail or "COMPLETED_EVIDENCE" in detail:
        return ProbablesV2ExceptionCategory.PHASE_SELECTION_ERROR
    if "PERSIST" in stage or "PERSIST" in detail or isinstance(error, OSError):
        return ProbablesV2ExceptionCategory.PERSISTENCE_ERROR
    if "INTEGRITY" in detail:
        return ProbablesV2ExceptionCategory.INTEGRITY_ERROR
    if "IDENTITY" in detail:
        return ProbablesV2ExceptionCategory.IDENTITY_ERROR
    if "BOUNDARY" in detail:
        return ProbablesV2ExceptionCategory.BOUNDARY_ERROR
    if "SCHEMA" in detail:
        return ProbablesV2ExceptionCategory.SCHEMA_ERROR
    if "MAPPING" in stage:
        return ProbablesV2ExceptionCategory.MAPPING_ERROR
    if type(error) is TypeError:
        return ProbablesV2ExceptionCategory.TYPE_ERROR
    if type(error) is KeyError:
        return ProbablesV2ExceptionCategory.KEY_ERROR
    if type(error) is ValueError:
        return ProbablesV2ExceptionCategory.VALUE_ERROR
    return ProbablesV2ExceptionCategory.UNEXPECTED_INTERNAL_ERROR


def _bounded_cause(error: BaseException) -> BaseException:
    """Inspect at most one explicit cause; never persist traceback or exception repr."""

    cause = error.__cause__
    return cause if isinstance(cause, BaseException) else error


def _without(value: object, *names: str) -> dict[str, object]:
    result = asdict(value)
    for name in names:
        result.pop(name)
    return result


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(json.dumps(_normalize(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest().upper()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _component(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip() and len(value) <= 256 and "/" not in value and "\\" not in value


def _safe_component(value: object) -> str | None:
    return value if _component(value) else None


def _texts(values: tuple[str, ...]) -> bool:
    return bool(values) and all(_component(item) for item in values)


def _safe_detail(value: object) -> bool:
    return type(value) is str and 0 < len(value) <= FAILURE_DETAIL_MAX_LENGTH and "\n" not in value and "\r" not in value


__all__ = [
    "FAILURE_DETAIL_MAX_LENGTH",
    "PROBABLES_V2_FAILURE_DETAIL_IDENTITY",
    "PROBABLES_V2_FAILURE_DETAIL_VERSION",
    "PROBABLES_V2_REPLAY_ENVELOPE_IDENTITY",
    "PROBABLES_V2_REPLAY_ENVELOPE_VERSION",
    "ProbablesV2ExceptionCategory",
    "ProbablesV2FailureDetail",
    "ProbablesV2ReplayEnvelope",
    "create_probables_v2_failure_detail",
    "create_probables_v2_replay_envelope",
    "reconstruct_v2_execution",
    "replay_v2_mapping",
    "sanitize_failure_detail",
]
