"""Sanitized immutable provenance for Native Discovery machine-fact failures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.reconciliation import ReconciliationMember


DISCOVERY_FAILURE_PROVENANCE_SCHEMA = (
    "KRONOS-INTRADAY-DISCOVERY-MACHINE-FACT-FAILURE-PROVENANCE-V1"
)
DISCOVERY_FAILURE_PROVENANCE_VERSION = "1.0.0"
DISCOVERY_FAILURE_PROVENANCE_POLICY = (
    "KRONOS-INTRADAY-DISCOVERY-MACHINE-FACT-FAILURE-PROVENANCE-POLICY-V1"
)
DISCOVERY_FAILURE_PROVENANCE_POLICY_VERSION = "1.0.0"


class MachineFactFailureStage(StrEnum):
    SCHEDULE_SESSION_BINDING = "SCHEDULE_SESSION_BINDING"
    PROVIDER_SYMBOL_BINDING = "PROVIDER_SYMBOL_BINDING"
    CANDLE_ACQUISITION = "CANDLE_ACQUISITION"
    INTERVAL_SELECTION = "INTERVAL_SELECTION"
    COMPLETION_VALIDATION = "COMPLETION_VALIDATION"
    REQUIRED_TIMEFRAME_ABSENCE = "REQUIRED_TIMEFRAME_ABSENCE"
    BUNDLE_CONSTRUCTION = "BUNDLE_CONSTRUCTION"
    BUNDLE_VALIDATION = "BUNDLE_VALIDATION"
    PERSISTENCE = "PERSISTENCE"


class MachineFactFailureComponent(StrEnum):
    MARKET_SESSION = "MARKET_SESSION"
    PROVIDER_SYMBOL = "PROVIDER_SYMBOL"
    PREVIOUS_COMPLETED_DAILY_EVIDENCE = "PREVIOUS_COMPLETED_DAILY_EVIDENCE"
    PRIOR_SESSION_1H_EVIDENCE = "PRIOR_SESSION_1H_EVIDENCE"
    CURRENT_SESSION_1H_EVIDENCE = "CURRENT_SESSION_1H_EVIDENCE"
    CURRENT_OPENING_15M_EVIDENCE = "CURRENT_OPENING_15M_EVIDENCE"
    CURRENT_SESSION_15M_EVIDENCE = "CURRENT_SESSION_15M_EVIDENCE"
    CURRENT_CONSTITUENT_5M_EVIDENCE = "CURRENT_CONSTITUENT_5M_EVIDENCE"
    MACHINE_FACT_BUNDLE = "MACHINE_FACT_BUNDLE"
    FAILURE_PROVENANCE_ARTIFACT = "FAILURE_PROVENANCE_ARTIFACT"


class MachineFactFailureAvailability(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    INCOMPLETE = "INCOMPLETE"
    NOT_COMPLETED = "NOT_COMPLETED"
    INVALID = "INVALID"
    CONFLICTING = "CONFLICTING"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"


@dataclass(frozen=True, slots=True)
class MachineFactFailureDetail:
    """In-memory bounded detail carried across a factual-source boundary."""

    stage: MachineFactFailureStage
    component: MachineFactFailureComponent
    required_timeframe: IntradayTimeframe | None
    expected_candle_interval: str | None
    availability_failure: MachineFactFailureAvailability
    sanitized_failure_code: str
    provider_symbol_binding: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.stage) is not MachineFactFailureStage
            or type(self.component) is not MachineFactFailureComponent
            or (
                self.required_timeframe is not None
                and type(self.required_timeframe) is not IntradayTimeframe
            )
            or (
                self.expected_candle_interval is not None
                and not _safe_atom(self.expected_candle_interval)
            )
            or type(self.availability_failure) is not MachineFactFailureAvailability
            or not _code(self.sanitized_failure_code)
            or (
                self.provider_symbol_binding is not None
                and not _text(self.provider_symbol_binding)
            )
        ):
            raise ValueError("DISCOVERY_FAILURE_DETAIL_INVALID")


@dataclass(frozen=True, slots=True)
class DiscoveryMachineFactFailureProvenance:
    failure_identity: str
    discovery_run_identity: str
    universe_member_identity: str
    canonical_subject_identity: str
    canonical_instrument_identity: str
    market_family: str
    analysis_boundary: datetime
    trading_date: date
    market_session_identity: str
    provider_symbol_binding: str | None
    failure_stage: MachineFactFailureStage
    required_component: MachineFactFailureComponent
    required_timeframe: IntradayTimeframe | None
    expected_candle_interval: str | None
    availability_failure: MachineFactFailureAvailability
    sanitized_failure_code: str
    operation_identity: str
    policy_identity: str
    policy_version: str
    integrity_hash: str
    analytical_authority: str = "NONE"
    probable_authority: str = "NONE"
    current_pointer_authority: str = "NONE"
    schema_identity: str = DISCOVERY_FAILURE_PROVENANCE_SCHEMA
    schema_version: str = DISCOVERY_FAILURE_PROVENANCE_VERSION

    def __post_init__(self) -> None:
        values = _payload(self, include_identity=False, include_integrity=False)
        integrity = sha256(_encode(values)).hexdigest()
        if (
            not self.failure_identity.startswith(
                "INTRADAY-DISCOVERY-FAILURE-PROVENANCE-"
            )
            or not self.discovery_run_identity.startswith("INTRADAY-DISCOVERY-RUN-")
            or not all(_text(value) for value in (
                self.universe_member_identity,
                self.canonical_subject_identity,
                self.canonical_instrument_identity,
                self.market_family,
                self.market_session_identity,
                self.operation_identity,
            ))
            or not self.operation_identity.startswith(
                "KRONOS-INTRADAY-DISCOVERY-OPERATION-"
            )
            or not _aware(self.analysis_boundary)
            or type(self.trading_date) is not date
            or (
                self.provider_symbol_binding is not None
                and not _text(self.provider_symbol_binding)
            )
            or type(self.failure_stage) is not MachineFactFailureStage
            or type(self.required_component) is not MachineFactFailureComponent
            or (
                self.required_timeframe is not None
                and type(self.required_timeframe) is not IntradayTimeframe
            )
            or (
                self.expected_candle_interval is not None
                and not _safe_atom(self.expected_candle_interval)
            )
            or type(self.availability_failure) is not MachineFactFailureAvailability
            or not _code(self.sanitized_failure_code)
            or self.policy_identity != DISCOVERY_FAILURE_PROVENANCE_POLICY
            or self.policy_version != DISCOVERY_FAILURE_PROVENANCE_POLICY_VERSION
            or self.integrity_hash != integrity
            or self.failure_identity
            != "INTRADAY-DISCOVERY-FAILURE-PROVENANCE-" + integrity
            or any(value != "NONE" for value in (
                self.analytical_authority,
                self.probable_authority,
                self.current_pointer_authority,
            ))
            or self.schema_identity != DISCOVERY_FAILURE_PROVENANCE_SCHEMA
            or self.schema_version != DISCOVERY_FAILURE_PROVENANCE_VERSION
        ):
            raise ValueError("DISCOVERY_FAILURE_PROVENANCE_INVALID")


def create_discovery_failure_provenance(
    *,
    member: ReconciliationMember,
    discovery_run_identity: str,
    analysis_boundary: datetime,
    market_session_identity: str,
    operation_identity: str,
    detail: MachineFactFailureDetail,
) -> DiscoveryMachineFactFailureProvenance:
    if type(member) is not ReconciliationMember or type(detail) is not MachineFactFailureDetail:
        raise ValueError("DISCOVERY_FAILURE_PROVENANCE_INPUT_INVALID")
    values = {
        "discovery_run_identity": discovery_run_identity,
        "universe_member_identity": member.universe_member_identity,
        "canonical_subject_identity": member.canonical_identity,
        "canonical_instrument_identity": member.canonical_identity,
        "market_family": member.market_family.value,
        "analysis_boundary": analysis_boundary,
        "trading_date": analysis_boundary.astimezone(
            ZoneInfo("Asia/Kolkata")
        ).date(),
        "market_session_identity": market_session_identity,
        "provider_symbol_binding": (
            detail.provider_symbol_binding
            if detail.provider_symbol_binding is not None
            else member.provider_symbol
        ),
        "failure_stage": detail.stage,
        "required_component": detail.component,
        "required_timeframe": detail.required_timeframe,
        "expected_candle_interval": detail.expected_candle_interval,
        "availability_failure": detail.availability_failure,
        "sanitized_failure_code": detail.sanitized_failure_code,
        "operation_identity": operation_identity,
        "policy_identity": DISCOVERY_FAILURE_PROVENANCE_POLICY,
        "policy_version": DISCOVERY_FAILURE_PROVENANCE_POLICY_VERSION,
        "analytical_authority": "NONE",
        "probable_authority": "NONE",
        "current_pointer_authority": "NONE",
        "schema_identity": DISCOVERY_FAILURE_PROVENANCE_SCHEMA,
        "schema_version": DISCOVERY_FAILURE_PROVENANCE_VERSION,
    }
    integrity = sha256(_encode(values)).hexdigest()
    return DiscoveryMachineFactFailureProvenance(
        failure_identity="INTRADAY-DISCOVERY-FAILURE-PROVENANCE-" + integrity,
        integrity_hash=integrity,
        **values,
    )


def discovery_failure_provenance_bytes(
    value: DiscoveryMachineFactFailureProvenance,
) -> bytes:
    if type(value) is not DiscoveryMachineFactFailureProvenance:
        raise ValueError("DISCOVERY_FAILURE_PROVENANCE_INVALID")
    return _encode(_payload(value))


def parse_discovery_failure_provenance(
    encoded: bytes,
) -> DiscoveryMachineFactFailureProvenance:
    try:
        payload = json.loads(encoded)
        if set(payload) != set(DiscoveryMachineFactFailureProvenance.__dataclass_fields__):
            raise ValueError
        payload["analysis_boundary"] = datetime.fromisoformat(payload["analysis_boundary"])
        payload["trading_date"] = date.fromisoformat(payload["trading_date"])
        payload["failure_stage"] = MachineFactFailureStage(payload["failure_stage"])
        payload["required_component"] = MachineFactFailureComponent(
            payload["required_component"]
        )
        payload["required_timeframe"] = (
            None
            if payload["required_timeframe"] is None
            else IntradayTimeframe(payload["required_timeframe"])
        )
        payload["availability_failure"] = MachineFactFailureAvailability(
            payload["availability_failure"]
        )
        value = DiscoveryMachineFactFailureProvenance(**payload)
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise ValueError("DISCOVERY_FAILURE_PROVENANCE_INVALID") from error
    if discovery_failure_provenance_bytes(value) != encoded:
        raise ValueError("DISCOVERY_FAILURE_PROVENANCE_INVALID")
    return value


def _payload(
    value: DiscoveryMachineFactFailureProvenance,
    *,
    include_identity: bool = True,
    include_integrity: bool = True,
) -> dict[str, object]:
    payload = asdict(value)
    if not include_identity:
        payload.pop("failure_identity")
    if not include_integrity:
        payload.pop("integrity_hash")
    return payload


def _encode(value: object) -> bytes:
    return json.dumps(
        value,
        default=lambda item: item.value if isinstance(item, StrEnum) else item.isoformat(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _code(value: object) -> bool:
    return _text(value) and value.replace("_", "").isalnum() and value.upper() == value


def _safe_atom(value: object) -> bool:
    return _text(value) and value.replace("_", "").replace("-", "").isalnum()


__all__ = [
    "DISCOVERY_FAILURE_PROVENANCE_POLICY",
    "DISCOVERY_FAILURE_PROVENANCE_POLICY_VERSION",
    "DISCOVERY_FAILURE_PROVENANCE_SCHEMA",
    "DISCOVERY_FAILURE_PROVENANCE_VERSION",
    "DiscoveryMachineFactFailureProvenance",
    "MachineFactFailureAvailability",
    "MachineFactFailureComponent",
    "MachineFactFailureDetail",
    "MachineFactFailureStage",
    "create_discovery_failure_provenance",
    "discovery_failure_provenance_bytes",
    "parse_discovery_failure_provenance",
]
