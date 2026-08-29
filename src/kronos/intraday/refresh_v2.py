"""Governed request and sanitized provenance contracts for V2 Refresh."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping

from kronos.intraday.probables_v2 import (
    PROBABLES_V2_METHODOLOGY_IDENTITY,
    PROBABLES_V2_SUCCESSOR_METHODOLOGY_CHECKSUM as PROBABLES_V2_METHODOLOGY_CHECKSUM,
    PROBABLES_V2_SUCCESSOR_METHODOLOGY_VERSION as PROBABLES_V2_METHODOLOGY_VERSION,
    PROBABLES_V2_SUCCESSOR_PUBLICATION_IDENTITY as PROBABLES_V2_PUBLICATION_IDENTITY,
    probables_v2_methodology_binding_supported,
)


REFRESH_V2_REQUEST_IDENTITY = "KRONOS-INTRADAY-PROBABLES-V2-REFRESH-REQUEST"
REFRESH_V2_REQUEST_VERSION = "1.0.0"
REFRESH_V2_PROVENANCE_IDENTITY = "KRONOS-INTRADAY-PROBABLES-V2-REQUEST-PROVENANCE"
REFRESH_V2_PROVENANCE_VERSION = "1.1.0"
REFRESH_V2_LEGACY_PROVENANCE_VERSION = "1.0.0"
REFRESH_V2_ROUTE = "/control/intraday-discovery/v2"
REFRESH_V2_OPERATION_TYPE = "INTRADAY_PROBABLES_V2_REFRESH"


class RefreshV2SourceClass(StrEnum):
    SPONSOR_BROWSER_CONTROL = "SPONSOR_BROWSER_CONTROL"


class RefreshV2Outcome(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class RefreshV2Request:
    request_identity: str
    observation_boundary: datetime
    request_created_at: datetime
    source_class: RefreshV2SourceClass
    integrity_identity: str
    contract_identity: str = REFRESH_V2_REQUEST_IDENTITY
    contract_version: str = REFRESH_V2_REQUEST_VERSION
    methodology_identity: str = PROBABLES_V2_METHODOLOGY_IDENTITY
    methodology_version: str = PROBABLES_V2_METHODOLOGY_VERSION
    methodology_publication_identity: str = PROBABLES_V2_PUBLICATION_IDENTITY
    methodology_checksum: str = PROBABLES_V2_METHODOLOGY_CHECKSUM
    operation_type: str = REFRESH_V2_OPERATION_TYPE

    def __post_init__(self) -> None:
        core = _request_core(self)
        if (
            not _component(self.request_identity)
            or not _aware(self.observation_boundary)
            or not _aware(self.request_created_at)
            or self.request_created_at > self.observation_boundary
            or type(self.source_class) is not RefreshV2SourceClass
            or self.contract_identity != REFRESH_V2_REQUEST_IDENTITY
            or self.contract_version != REFRESH_V2_REQUEST_VERSION
            or not probables_v2_methodology_binding_supported(
                self.methodology_identity,
                self.methodology_version,
                self.methodology_publication_identity,
                self.methodology_checksum,
            )
            or self.operation_type != REFRESH_V2_OPERATION_TYPE
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-PROBABLES-V2-REFRESH-REQUEST-", core)
        ):
            raise ValueError("INTRADAY_PROBABLES_V2_REFRESH_REQUEST_INVALID")


@dataclass(frozen=True, slots=True)
class RefreshV2ProvenanceRecord:
    provenance_identity: str
    request_identity: str
    request_integrity_identity: str
    route_identity: str
    methodology_identity: str
    methodology_version: str
    methodology_publication_identity: str
    methodology_checksum: str
    observation_boundary: datetime | None
    received_at: datetime
    operation_started_at: datetime | None
    operation_completed_at: datetime
    resulting_refresh_identity: str | None
    resulting_discovery_identity: str | None
    resulting_probables_identity: str | None
    replay_envelope_identity: str | None
    failure_detail_identity: str | None
    outcome: RefreshV2Outcome
    failure: str | None
    source_class: RefreshV2SourceClass
    backend_process_identity: str
    remote_address_class: str
    origin_validation: str
    host_validation: str
    integrity_identity: str
    contract_identity: str = REFRESH_V2_PROVENANCE_IDENTITY
    contract_version: str = REFRESH_V2_PROVENANCE_VERSION

    def __post_init__(self) -> None:
        core = _provenance_core(self)
        identities = (
            self.resulting_refresh_identity,
            self.resulting_discovery_identity,
            self.resulting_probables_identity,
            self.replay_envelope_identity,
            self.failure_detail_identity,
        )
        if (
            not self.provenance_identity.startswith("INTRADAY-PROBABLES-V2-REQUEST-PROVENANCE-")
            or not _component(self.request_identity)
            or not _component(self.request_integrity_identity)
            or self.route_identity != REFRESH_V2_ROUTE
            or not probables_v2_methodology_binding_supported(
                self.methodology_identity,
                self.methodology_version,
                self.methodology_publication_identity,
                self.methodology_checksum,
            )
            or (self.observation_boundary is not None and not _aware(self.observation_boundary))
            or not _aware(self.received_at)
            or (self.operation_started_at is not None and not _aware(self.operation_started_at))
            or not _aware(self.operation_completed_at)
            or any(value is not None and not _component(value) for value in identities)
            or type(self.outcome) is not RefreshV2Outcome
            or (self.failure is not None and not _component(self.failure))
            or type(self.source_class) is not RefreshV2SourceClass
            or not all(_component(value) for value in (
                self.backend_process_identity,
                self.remote_address_class,
                self.origin_validation,
                self.host_validation,
            ))
            or self.contract_identity != REFRESH_V2_PROVENANCE_IDENTITY
            or self.contract_version not in {
                REFRESH_V2_LEGACY_PROVENANCE_VERSION,
                REFRESH_V2_PROVENANCE_VERSION,
            }
            or self.provenance_identity
            != _identity("INTRADAY-PROBABLES-V2-REQUEST-PROVENANCE-", core)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-PROBABLES-V2-REQUEST-PROVENANCE-", core)
        ):
            raise ValueError("INTRADAY_PROBABLES_V2_PROVENANCE_INVALID")


def create_refresh_v2_request(
    *,
    request_identity: str,
    observation_boundary: datetime,
    request_created_at: datetime,
) -> RefreshV2Request:
    values = {
        "request_identity": request_identity,
        "observation_boundary": observation_boundary,
        "request_created_at": request_created_at,
        "source_class": RefreshV2SourceClass.SPONSOR_BROWSER_CONTROL,
        "contract_identity": REFRESH_V2_REQUEST_IDENTITY,
        "contract_version": REFRESH_V2_REQUEST_VERSION,
        "methodology_identity": PROBABLES_V2_METHODOLOGY_IDENTITY,
        "methodology_version": PROBABLES_V2_METHODOLOGY_VERSION,
        "methodology_publication_identity": PROBABLES_V2_PUBLICATION_IDENTITY,
        "methodology_checksum": PROBABLES_V2_METHODOLOGY_CHECKSUM,
        "operation_type": REFRESH_V2_OPERATION_TYPE,
    }
    return RefreshV2Request(
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-PROBABLES-V2-REFRESH-REQUEST-", values
        ),
        **values,
    )


def create_refresh_v2_provenance(**values: object) -> RefreshV2ProvenanceRecord:
    core = dict(values)
    core.setdefault("replay_envelope_identity", None)
    core.setdefault("failure_detail_identity", None)
    core.update({
        "contract_identity": REFRESH_V2_PROVENANCE_IDENTITY,
        "contract_version": REFRESH_V2_PROVENANCE_VERSION,
    })
    return RefreshV2ProvenanceRecord(
        provenance_identity=_identity(
            "INTRADAY-PROBABLES-V2-REQUEST-PROVENANCE-", core
        ),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-PROBABLES-V2-REQUEST-PROVENANCE-", core
        ),
        **core,
    )


def _request_core(value: RefreshV2Request) -> dict[str, object]:
    result = asdict(value)
    result.pop("integrity_identity")
    return result


def _provenance_core(value: RefreshV2ProvenanceRecord) -> dict[str, object]:
    result = asdict(value)
    result.pop("provenance_identity")
    result.pop("integrity_identity")
    if value.contract_version == REFRESH_V2_LEGACY_PROVENANCE_VERSION:
        result.pop("replay_envelope_identity")
        result.pop("failure_detail_identity")
    return result


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest().upper()


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


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _component(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value == value.strip()
        and len(value) <= 256
        and "/" not in value
        and "\\" not in value
    )


__all__ = [
    "REFRESH_V2_OPERATION_TYPE",
    "REFRESH_V2_PROVENANCE_IDENTITY",
    "REFRESH_V2_LEGACY_PROVENANCE_VERSION",
    "REFRESH_V2_PROVENANCE_VERSION",
    "REFRESH_V2_REQUEST_IDENTITY",
    "REFRESH_V2_REQUEST_VERSION",
    "REFRESH_V2_ROUTE",
    "RefreshV2Outcome",
    "RefreshV2ProvenanceRecord",
    "RefreshV2Request",
    "RefreshV2SourceClass",
    "create_refresh_v2_provenance",
    "create_refresh_v2_request",
]
