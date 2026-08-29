"""Governed Phase-A request and provenance for explicit V2 Review creation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping


REVIEW_V2_CREATE_REQUEST_IDENTITY = "KRONOS-INTRADAY-REVIEW-V2-CREATE-REQUEST"
REVIEW_V2_CREATE_REQUEST_VERSION = "1.0.0"
REVIEW_V2_OPERATION_PROVENANCE_IDENTITY = (
    "KRONOS-INTRADAY-REVIEW-V2-OPERATION-PROVENANCE"
)
REVIEW_V2_OPERATION_PROVENANCE_VERSION = "1.0.0"
REVIEW_V2_CREATE_ROUTE = "/control/intraday-review/v2"


class ReviewV2OperationSource(StrEnum):
    SPONSOR_BROWSER_CONTROL = "SPONSOR_BROWSER_CONTROL"


class ReviewV2OperationOutcome(StrEnum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class ReviewV2CreateRequest:
    request_identity: str
    probables_run_identity: str
    expected_methodology_identity: str
    expected_methodology_version: str
    expected_methodology_publication_identity: str
    expected_methodology_checksum: str
    requested_at: datetime
    source: ReviewV2OperationSource
    integrity_identity: str
    contract_identity: str = REVIEW_V2_CREATE_REQUEST_IDENTITY
    contract_version: str = REVIEW_V2_CREATE_REQUEST_VERSION

    def __post_init__(self) -> None:
        core = _without(self, "integrity_identity")
        if (
            not all(_component(value) for value in (
                self.request_identity,
                self.probables_run_identity,
                self.expected_methodology_identity,
                self.expected_methodology_version,
                self.expected_methodology_publication_identity,
                self.expected_methodology_checksum,
            ))
            or not _aware(self.requested_at)
            or self.source is not ReviewV2OperationSource.SPONSOR_BROWSER_CONTROL
            or self.contract_identity != REVIEW_V2_CREATE_REQUEST_IDENTITY
            or self.contract_version != REVIEW_V2_CREATE_REQUEST_VERSION
            or self.integrity_identity != _identity(
                "INTEGRITY-INTRADAY-REVIEW-V2-CREATE-REQUEST-", core
            )
        ):
            raise ValueError("INTRADAY_REVIEW_V2_CREATE_REQUEST_INVALID")


@dataclass(frozen=True, slots=True)
class ReviewV2OperationProvenance:
    provenance_identity: str
    request_identity: str
    request_integrity_identity: str
    route_identity: str
    source: ReviewV2OperationSource
    backend_process_identity: str
    received_at: datetime
    operation_started_at: datetime | None
    operation_completed_at: datetime
    probables_run_identity: str | None
    methodology_identity: str | None
    methodology_version: str | None
    methodology_publication_identity: str | None
    methodology_checksum: str | None
    cycle_identities: tuple[str, ...]
    outcome: ReviewV2OperationOutcome
    failure_stage: str | None
    failure_reason: str | None
    integrity_identity: str
    contract_identity: str = REVIEW_V2_OPERATION_PROVENANCE_IDENTITY
    contract_version: str = REVIEW_V2_OPERATION_PROVENANCE_VERSION

    def __post_init__(self) -> None:
        core = _without(self, "provenance_identity", "integrity_identity")
        optional_components = (
            self.probables_run_identity,
            self.methodology_identity,
            self.methodology_version,
            self.methodology_publication_identity,
            self.methodology_checksum,
            self.failure_stage,
            self.failure_reason,
        )
        methodology = optional_components[1:5]
        if (
            not all(_component(value) for value in (
                self.request_identity,
                self.request_integrity_identity,
                self.backend_process_identity,
            ))
            or self.route_identity != REVIEW_V2_CREATE_ROUTE
            or self.source is not ReviewV2OperationSource.SPONSOR_BROWSER_CONTROL
            or not _aware(self.received_at)
            or self.operation_started_at is not None
            and not _aware(self.operation_started_at)
            or not _aware(self.operation_completed_at)
            or any(value is not None and not _component(value) for value in optional_components)
            or any(value is None for value in methodology)
            != all(value is None for value in methodology)
            or any(not _component(value) for value in self.cycle_identities)
            or len(set(self.cycle_identities)) != len(self.cycle_identities)
            or type(self.outcome) is not ReviewV2OperationOutcome
            or self.outcome is ReviewV2OperationOutcome.COMPLETE
            and (self.probables_run_identity is None or not self.cycle_identities)
            or self.outcome is ReviewV2OperationOutcome.COMPLETE
            and (self.failure_stage is not None or self.failure_reason is not None)
            or self.outcome is not ReviewV2OperationOutcome.COMPLETE
            and (self.failure_stage is None or self.failure_reason is None)
            or self.contract_identity != REVIEW_V2_OPERATION_PROVENANCE_IDENTITY
            or self.contract_version != REVIEW_V2_OPERATION_PROVENANCE_VERSION
            or self.provenance_identity != _identity(
                "INTRADAY-REVIEW-V2-OPERATION-PROVENANCE-", core
            )
            or self.integrity_identity != _identity(
                "INTEGRITY-INTRADAY-REVIEW-V2-OPERATION-PROVENANCE-", core
            )
        ):
            raise ValueError("INTRADAY_REVIEW_V2_OPERATION_PROVENANCE_INVALID")


def create_review_v2_request(**values: object) -> ReviewV2CreateRequest:
    core = {
        **values,
        "source": ReviewV2OperationSource.SPONSOR_BROWSER_CONTROL,
        "contract_identity": REVIEW_V2_CREATE_REQUEST_IDENTITY,
        "contract_version": REVIEW_V2_CREATE_REQUEST_VERSION,
    }
    return ReviewV2CreateRequest(
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-REVIEW-V2-CREATE-REQUEST-", core
        ),
        **core,
    )


def create_review_v2_provenance(**values: object) -> ReviewV2OperationProvenance:
    core = {
        **values,
        "contract_identity": REVIEW_V2_OPERATION_PROVENANCE_IDENTITY,
        "contract_version": REVIEW_V2_OPERATION_PROVENANCE_VERSION,
    }
    return ReviewV2OperationProvenance(
        provenance_identity=_identity(
            "INTRADAY-REVIEW-V2-OPERATION-PROVENANCE-", core
        ),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-REVIEW-V2-OPERATION-PROVENANCE-", core
        ),
        **core,
    )


def _without(value: object, *names: str) -> dict[str, object]:
    result = asdict(value)  # type: ignore[arg-type]
    for name in names:
        result.pop(name)
    return result


def _identity(prefix: str, value: object) -> str:
    payload = json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":")
    ).encode()
    return prefix + sha256(payload).hexdigest().upper()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _component(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value == value.strip()
        and len(value) <= 512
        and "/" not in value
        and "\\" not in value
    )


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "REVIEW_V2_CREATE_REQUEST_IDENTITY",
    "REVIEW_V2_CREATE_REQUEST_VERSION",
    "REVIEW_V2_CREATE_ROUTE",
    "REVIEW_V2_OPERATION_PROVENANCE_IDENTITY",
    "REVIEW_V2_OPERATION_PROVENANCE_VERSION",
    "ReviewV2CreateRequest",
    "ReviewV2OperationOutcome",
    "ReviewV2OperationProvenance",
    "ReviewV2OperationSource",
    "create_review_v2_provenance",
    "create_review_v2_request",
]
