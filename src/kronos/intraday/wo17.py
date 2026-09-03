"""Immutable WO-17 exact-upstream binding contracts.

Slice 1 records no position, fill, monitoring observation, lifecycle event, or
current-position pointer.  It only preserves the exact admitted WO-13 through
WO-16 and DOMAIN-008 graph needed by later governed slices.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13_handoff import Wo13SetupFamily
from kronos.intraday.wo14 import Wo14ObservationState
from kronos.intraday.wo15 import Wo15TimingState
from kronos.intraday.wo16 import (
    Wo16LifecycleAdmissionDisposition,
    Wo16SponsorDecision,
)


WO17_CONTRACT_VERSION = "1.0.0"
WO17_PRODUCT_IDENTITY = (
    "KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-V1"
)
WO17_AUTHORITY = "FACTUAL_POSITION_EVIDENCE_AND_READ_ONLY_LIFECYCLE_MONITORING_ONLY"
WO17_POLICY_IDENTITY = (
    "KRONOS-INTRADAY-WO17-POSITION-EVIDENCE-AND-ACTIVE-LIFECYCLE-MONITORING-"
    "POLICY-V1"
)
WO17_POLICY_VERSION = "1.0.0"
WO17_POLICY_CHECKSUM = (
    "4fafb49ef2ffb95c60d53e4061f3658237134c82995db9bd128be99637d38a1a"
)
WO17_UPSTREAM_LINEAGE_IDENTITY = "KRONOS-INTRADAY-WO17-UPSTREAM-LINEAGE-V1"
WO17_UPSTREAM_SNAPSHOT_IDENTITY = "KRONOS-INTRADAY-WO17-UPSTREAM-SNAPSHOT-V1"


class Wo17ContractError(ValueError):
    """Sanitized WO-17 contract failure."""


@dataclass(frozen=True, slots=True)
class Wo17PolicyBinding:
    policy_identity: str = WO17_POLICY_IDENTITY
    policy_version: str = WO17_POLICY_VERSION
    policy_checksum: str = WO17_POLICY_CHECKSUM
    product_identity: str = WO17_PRODUCT_IDENTITY
    authority: str = WO17_AUTHORITY
    maximum_non_closed_positions_per_subject: int = 1
    prior_session_non_closed_position_blocks_activation: bool = True
    successor_wo16_evidence_may_coexist: bool = True
    automatic_mcx_roll_migration: str = "PROHIBITED"
    position_creation_authority: bool = False
    current_position_pointer_authority: bool = False
    provider_acquisition_authority: bool = False
    monitoring_operation_authority: bool = False
    fill_authority: bool = False
    quantity_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False
    monetary_pnl_authority: bool = False
    realised_r_authority: bool = False
    closure_authority: bool = False
    notification_delivery_authority: bool = False
    journal_analytics_authority: bool = False

    def __post_init__(self) -> None:
        if (
            self.policy_identity != WO17_POLICY_IDENTITY
            or self.policy_version != WO17_POLICY_VERSION
            or self.policy_checksum != WO17_POLICY_CHECKSUM
            or self.product_identity != WO17_PRODUCT_IDENTITY
            or self.authority != WO17_AUTHORITY
            or self.maximum_non_closed_positions_per_subject != 1
            or self.prior_session_non_closed_position_blocks_activation is not True
            or self.successor_wo16_evidence_may_coexist is not True
            or self.automatic_mcx_roll_migration != "PROHIBITED"
            or any(
                value
                for name, value in asdict(self).items()
                if name.endswith("_authority")
            )
        ):
            raise Wo17ContractError("WO17_POLICY_BINDING_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17UpstreamLineage:
    lineage_identity: str
    lineage_integrity: str
    current_wo16_pointer_identity: str
    current_wo16_pointer_integrity: str
    wo13_trade_plan_identity: str
    wo13_trade_plan_integrity: str
    wo14_observation_identity: str
    wo14_observation_integrity: str
    wo15_handoff_identity: str
    wo15_handoff_integrity: str
    wo16_snapshot_identity: str
    wo16_snapshot_integrity: str
    wo16_decision_identity: str
    wo16_decision_integrity: str
    wo16_admission_identity: str
    wo16_admission_integrity: str
    domain_008_session_binding_identity: str
    domain_008_session_binding_integrity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    direction: SemanticDirection
    setup_family: Wo13SetupFamily
    instrument_identity: str
    actual_contract_identity: str | None
    contract_expiry: date | None
    roll_lineage_identity: str | None
    trading_date: date
    session_identity: str
    calendar_identity: str
    calendar_version: str
    active_window_opens_at: datetime
    active_window_closes_at: datetime
    entry_reference: Decimal
    entry_condition: str
    stop: Decimal
    thesis_invalidation_reference: Decimal
    thesis_invalidation_event: str
    canonical_target: Decimal
    risk_distance: Decimal
    reward_distance: Decimal
    model_rr: Decimal
    risk_observation_state: Wo14ObservationState
    timing_state: Wo15TimingState
    timing_evidence_boundary: datetime
    sponsor_decision: Wo16SponsorDecision
    lifecycle_admission: Wo16LifecycleAdmissionDisposition
    wo13_policy_identity: str
    wo13_policy_version: str
    wo13_policy_checksum: str
    wo14_policy_identity: str
    wo14_policy_version: str
    wo14_policy_checksum: str
    wo15_policy_identity: str
    wo15_policy_version: str
    wo15_policy_checksum: str
    wo16_policy_identity: str
    wo16_policy_version: str
    wo16_policy_checksum: str
    provenance: tuple[str, ...]
    schema_identity: str = WO17_UPSTREAM_LINEAGE_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    upstream_recalculation_authority: bool = False
    risk_permission_authority: bool = False
    risk_veto_authority: bool = False
    sponsor_decision_authority: bool = False
    position_creation_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        _reject_non_decimal(
            self.entry_reference,
            self.stop,
            self.thesis_invalidation_reference,
            self.canonical_target,
            self.risk_distance,
            self.reward_distance,
            self.model_rr,
        )
        values = _without(self, "lineage_identity", "lineage_integrity")
        mcx = self.market_family is IntradayMarketFamily.MCX
        mcx_values = (
            self.actual_contract_identity,
            self.contract_expiry,
            self.roll_lineage_identity,
        )
        if (
            not _texts(
                (
                    self.current_wo16_pointer_identity,
                    self.current_wo16_pointer_integrity,
                    self.wo13_trade_plan_identity,
                    self.wo13_trade_plan_integrity,
                    self.wo14_observation_identity,
                    self.wo14_observation_integrity,
                    self.wo15_handoff_identity,
                    self.wo15_handoff_integrity,
                    self.wo16_snapshot_identity,
                    self.wo16_snapshot_integrity,
                    self.wo16_decision_identity,
                    self.wo16_decision_integrity,
                    self.wo16_admission_identity,
                    self.wo16_admission_integrity,
                    self.domain_008_session_binding_identity,
                    self.domain_008_session_binding_integrity,
                    self.canonical_subject_identity,
                    self.instrument_identity,
                    self.session_identity,
                    self.calendar_identity,
                    self.calendar_version,
                    self.entry_condition,
                    self.thesis_invalidation_event,
                    self.wo13_policy_identity,
                    self.wo13_policy_version,
                    self.wo13_policy_checksum,
                    self.wo14_policy_identity,
                    self.wo14_policy_version,
                    self.wo14_policy_checksum,
                    self.wo15_policy_identity,
                    self.wo15_policy_version,
                    self.wo15_policy_checksum,
                    self.wo16_policy_identity,
                    self.wo16_policy_version,
                    self.wo16_policy_checksum,
                    *self.provenance,
                )
            )
            or type(self.market_family) is not IntradayMarketFamily
            or self.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or type(self.setup_family) is not Wo13SetupFamily
            or type(self.trading_date) is not date
            or not all(
                _aware(value)
                for value in (
                    self.active_window_opens_at,
                    self.active_window_closes_at,
                    self.timing_evidence_boundary,
                )
            )
            or self.active_window_opens_at >= self.active_window_closes_at
            or type(self.risk_observation_state) is not Wo14ObservationState
            or self.timing_state is not Wo15TimingState.TIMING_QUALIFIED
            or self.sponsor_decision not in {
                Wo16SponsorDecision.PAPER,
                Wo16SponsorDecision.LIVE,
            }
            or self.lifecycle_admission
            is not Wo16LifecycleAdmissionDisposition.PENDING_POSITION_EVIDENCE
            or mcx != all(value is not None for value in mcx_values)
            or (not mcx and any(value is not None for value in mcx_values))
            or self.schema_identity != WO17_UPSTREAM_LINEAGE_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or any(
                (
                    self.upstream_recalculation_authority,
                    self.risk_permission_authority,
                    self.risk_veto_authority,
                    self.sponsor_decision_authority,
                    self.position_creation_authority,
                    self.execution_authority,
                    self.broker_authority,
                )
            )
            or self.lineage_identity != _identity("INTRADAY-WO17-LINEAGE-", values)
            or self.lineage_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-LINEAGE-", values)
        ):
            raise Wo17ContractError("WO17_UPSTREAM_LINEAGE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo17UpstreamSnapshot:
    snapshot_identity: str
    snapshot_integrity: str
    lineage: Wo17UpstreamLineage
    bound_at: datetime
    policy: Wo17PolicyBinding
    provenance: tuple[str, ...]
    schema_identity: str = WO17_UPSTREAM_SNAPSHOT_IDENTITY
    schema_version: str = WO17_CONTRACT_VERSION
    position_identity: None = None
    current_position_pointer_identity: None = None
    fill: str = "UNAVAILABLE"
    quantity: str = "UNAVAILABLE"
    monetary_pnl: str = "UNAVAILABLE"
    realised_r: str = "UNAVAILABLE"
    position_creation_authority: bool = False
    monitoring_operation_authority: bool = False
    closure_authority: bool = False
    notification_delivery_authority: bool = False
    execution_authority: bool = False
    broker_authority: bool = False

    def __post_init__(self) -> None:
        values = _without(self, "snapshot_identity", "snapshot_integrity")
        if (
            type(self.lineage) is not Wo17UpstreamLineage
            or not _aware(self.bound_at)
            or type(self.policy) is not Wo17PolicyBinding
            or not _texts(self.provenance)
            or self.position_identity is not None
            or self.current_position_pointer_identity is not None
            or any(
                value != "UNAVAILABLE"
                for value in (
                    self.fill,
                    self.quantity,
                    self.monetary_pnl,
                    self.realised_r,
                )
            )
            or self.schema_identity != WO17_UPSTREAM_SNAPSHOT_IDENTITY
            or self.schema_version != WO17_CONTRACT_VERSION
            or any(
                (
                    self.position_creation_authority,
                    self.monitoring_operation_authority,
                    self.closure_authority,
                    self.notification_delivery_authority,
                    self.execution_authority,
                    self.broker_authority,
                )
            )
            or self.snapshot_identity != _identity("INTRADAY-WO17-SNAPSHOT-", values)
            or self.snapshot_integrity
            != _identity("INTEGRITY-INTRADAY-WO17-SNAPSHOT-", values)
        ):
            raise Wo17ContractError("WO17_UPSTREAM_SNAPSHOT_INVALID")


def create_wo17_upstream_lineage(**values: object) -> Wo17UpstreamLineage:
    values = {
        **values,
        "schema_identity": WO17_UPSTREAM_LINEAGE_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "upstream_recalculation_authority": False,
        "risk_permission_authority": False,
        "risk_veto_authority": False,
        "sponsor_decision_authority": False,
        "position_creation_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo17UpstreamLineage(
        lineage_identity=_identity("INTRADAY-WO17-LINEAGE-", values),
        lineage_integrity=_identity("INTEGRITY-INTRADAY-WO17-LINEAGE-", values),
        **values,  # type: ignore[arg-type]
    )


def create_wo17_upstream_snapshot(
    *,
    lineage: Wo17UpstreamLineage,
    bound_at: datetime,
    provenance: tuple[str, ...] = ("ADR-0027", "WO-17-SLICE-1"),
) -> Wo17UpstreamSnapshot:
    values = {
        "lineage": lineage,
        "bound_at": bound_at,
        "policy": Wo17PolicyBinding(),
        "provenance": provenance,
        "schema_identity": WO17_UPSTREAM_SNAPSHOT_IDENTITY,
        "schema_version": WO17_CONTRACT_VERSION,
        "position_identity": None,
        "current_position_pointer_identity": None,
        "fill": "UNAVAILABLE",
        "quantity": "UNAVAILABLE",
        "monetary_pnl": "UNAVAILABLE",
        "realised_r": "UNAVAILABLE",
        "position_creation_authority": False,
        "monitoring_operation_authority": False,
        "closure_authority": False,
        "notification_delivery_authority": False,
        "execution_authority": False,
        "broker_authority": False,
    }
    return Wo17UpstreamSnapshot(
        snapshot_identity=_identity("INTRADAY-WO17-SNAPSHOT-", values),
        snapshot_integrity=_identity("INTEGRITY-INTRADAY-WO17-SNAPSHOT-", values),
        **values,
    )


def canonical_document_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            _normalize(value), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except Wo17ContractError:
        raise
    except (TypeError, ValueError) as error:
        raise Wo17ContractError("WO17_CANONICAL_DOCUMENT_INVALID") from error


def canonical_sha256(value: object) -> str:
    return sha256(canonical_document_bytes(value)).hexdigest()


def wo17_policy_from_dict(payload: Mapping[str, object]) -> Wo17PolicyBinding:
    """Strict external boundary: missing and unknown fields are rejected."""

    if type(payload) is not dict or set(payload) != {
        item.name for item in fields(Wo17PolicyBinding)
    }:
        raise Wo17ContractError("WO17_CONTRACT_FIELDS_INVALID")
    try:
        return Wo17PolicyBinding(**payload)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise Wo17ContractError("WO17_POLICY_BINDING_INVALID") from error


def _without(value: object, *names: str) -> dict[str, object]:
    return {key: item for key, item in asdict(value).items() if key not in names}


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(canonical_document_bytes(value)).hexdigest().upper()


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        if not _aware(value):
            raise Wo17ContractError("WO17_TIMESTAMP_TIMEZONE_REQUIRED")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise Wo17ContractError("WO17_DECIMAL_INVALID")
        return format(value, "f")
    if isinstance(value, float):
        raise Wo17ContractError("WO17_FLOAT_PROHIBITED")
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise Wo17ContractError("WO17_CANONICAL_KEY_INVALID")
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    if value is None or type(value) in {str, int, bool}:
        return value
    raise Wo17ContractError("WO17_CANONICAL_VALUE_INVALID")


def _reject_non_decimal(*values: object) -> None:
    if any(type(value) is not Decimal or not value.is_finite() for value in values):
        raise Wo17ContractError("WO17_DECIMAL_INVALID")


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _texts(values: Sequence[object]) -> bool:
    return bool(values) and all(_text(value) for value in values)


__all__ = [
    name
    for name in globals()
    if name.startswith(("WO17_", "Wo17", "create_", "canonical_", "wo17_"))
]
