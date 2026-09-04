"""DOMAIN-008 directional compatibility for derived MCX schedules.

Clock equality is deliberately insufficient.  A compatibility artifact can be
published only from the current governed base calendar and the exact
family-specific expiry-session publication loaded by ``MarketCalendarPublisher``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Mapping

from kronos.market.calendar import (
    MARKET_CALENDAR_CONTRACT_ID,
    MCX_CONTRACT_FAMILY_SESSION_CONTRACT_ID,
    MarketCalendarPublisher,
    McxContractSessionClassification,
)
from kronos.market.schedule import (
    MarketDaySchedule,
    MarketSchedule,
    MarketWindow,
    TradingDayStatus,
)


MARKET_SCHEDULE_COMPATIBILITY_IDENTITY = (
    "KRONOS-MARKET-SCHEDULE-COMPATIBILITY-V1"
)
MARKET_SCHEDULE_COMPATIBILITY_VERSION = "1.0.0"
MARKET_SCHEDULE_COMPATIBILITY_POLICY = (
    "KRONOS-DOMAIN-008-MCX-FAMILY-SCHEDULE-DERIVATION-POLICY-V1"
)
MARKET_SCHEDULE_COMPATIBILITY_POLICY_VERSION = "1.0.0"


class MarketScheduleCompatibilityError(ValueError):
    """Sanitized failure at the DOMAIN-008 compatibility boundary."""


class MarketScheduleCompatibilityStatus(StrEnum):
    CURRENT = "CURRENT"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True, slots=True)
class MarketScheduleCompatibilityArtifact:
    """Immutable directional proof from a base schedule to a specialization."""

    compatibility_identity: str
    contract_family: str
    exchange: str
    market_identity: str
    base_segment: str
    derived_segment: str
    timezone: str
    trading_date: date
    previous_trading_date: date
    analysis_boundary: datetime
    current_session_identity: str
    previous_session_identity: str
    base_session_identity: str
    base_session_sha256: str
    base_schedule_identity: str
    base_schedule_version: str
    base_publication_identity: str
    base_publication_version: str
    base_publication_sha256: str
    base_source_boundary: datetime
    derived_schedule_identity: str
    derived_schedule_version: str
    derived_session_sha256: str
    derived_publication_identity: str
    derived_publication_version: str
    derived_publication_sha256: str
    derived_source_boundary: datetime
    derivation_relationship: str
    effective_from: date
    effective_through: date
    status: MarketScheduleCompatibilityStatus
    superseded_by_identity: str | None
    roll_continuity_authority: bool
    analytical_authority: bool
    trading_authority: bool
    provenance: tuple[str, ...]
    integrity_identity: str
    policy_identity: str = MARKET_SCHEDULE_COMPATIBILITY_POLICY
    policy_version: str = MARKET_SCHEDULE_COMPATIBILITY_POLICY_VERSION
    schema_identity: str = MARKET_SCHEDULE_COMPATIBILITY_IDENTITY
    schema_version: str = MARKET_SCHEDULE_COMPATIBILITY_VERSION

    def __post_init__(self) -> None:
        values = asdict(self)
        values.pop("compatibility_identity")
        values.pop("integrity_identity")
        if (
            not self.compatibility_identity.startswith(
                "MARKET-SCHEDULE-COMPATIBILITY-"
            )
            or self.contract_family
            not in {"GOLDM", "SILVERM", "COPPER", "NATURALGAS", "CRUDEOIL"}
            or self.exchange != "MCX"
            or self.market_identity != "MCX_NON_AGRI"
            or self.base_segment != "FUTURES_NON_AGRI"
            or self.derived_segment != "MCX_FUTURES"
            or self.timezone != "Asia/Kolkata"
            or type(self.trading_date) is not date
            or type(self.previous_trading_date) is not date
            or self.previous_trading_date >= self.trading_date
            or not _aware(self.analysis_boundary)
            or self.analysis_boundary.astimezone().tzinfo is None
            or not _texts(
                (
                    self.current_session_identity,
                    self.previous_session_identity,
                    self.base_session_identity,
                    self.base_schedule_identity,
                    self.base_schedule_version,
                    self.base_publication_identity,
                    self.base_publication_version,
                    self.derived_schedule_identity,
                    self.derived_schedule_version,
                    self.derived_publication_identity,
                    self.derived_publication_version,
                    self.derivation_relationship,
                )
            )
            or self.base_schedule_identity != MARKET_CALENDAR_CONTRACT_ID
            or self.derived_schedule_identity
            != MCX_CONTRACT_FAMILY_SESSION_CONTRACT_ID
            or len(self.base_session_sha256) != 64
            or len(self.derived_session_sha256) != 64
            or len(self.base_publication_sha256) != 64
            or len(self.derived_publication_sha256) != 64
            or not _aware(self.base_source_boundary)
            or not _aware(self.derived_source_boundary)
            or self.base_source_boundary > self.analysis_boundary
            or self.derived_source_boundary > self.analysis_boundary
            or self.derivation_relationship
            != "FAMILY_SPECIFIC_EXPIRY_SESSION_SPECIALIZATION"
            or type(self.effective_from) is not date
            or type(self.effective_through) is not date
            or not self.effective_from <= self.trading_date <= self.effective_through
            or type(self.status) is not MarketScheduleCompatibilityStatus
            or (
                (self.status is MarketScheduleCompatibilityStatus.CURRENT)
                != (self.superseded_by_identity is None)
            )
            or (
                self.superseded_by_identity is not None
                and not _text(self.superseded_by_identity)
            )
            or self.roll_continuity_authority is not False
            or self.analytical_authority is not False
            or self.trading_authority is not False
            or not _texts(self.provenance)
            or self.policy_identity != MARKET_SCHEDULE_COMPATIBILITY_POLICY
            or self.policy_version
            != MARKET_SCHEDULE_COMPATIBILITY_POLICY_VERSION
            or self.schema_identity != MARKET_SCHEDULE_COMPATIBILITY_IDENTITY
            or self.schema_version != MARKET_SCHEDULE_COMPATIBILITY_VERSION
            or self.compatibility_identity
            != _identity("MARKET-SCHEDULE-COMPATIBILITY-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-MARKET-SCHEDULE-COMPATIBILITY-", values)
        ):
            raise MarketScheduleCompatibilityError(
                "MARKET_SCHEDULE_COMPATIBILITY_INVALID"
            )


def publish_mcx_schedule_compatibility(
    *,
    calendar_publisher: MarketCalendarPublisher,
    contract_family: str,
    contract_expiry: date,
    current_schedule: MarketDaySchedule,
    previous_schedule: MarketDaySchedule,
    analysis_boundary: datetime,
) -> MarketScheduleCompatibilityArtifact:
    """Publish one exact compatibility proof from current DOMAIN-008 facts."""

    if (
        type(calendar_publisher) is not MarketCalendarPublisher
        or type(contract_expiry) is not date
        or type(current_schedule) is not MarketDaySchedule
        or type(previous_schedule) is not MarketDaySchedule
        or not _aware(analysis_boundary)
    ):
        raise MarketScheduleCompatibilityError(
            "MARKET_SCHEDULE_COMPATIBILITY_INPUT_INVALID"
        )
    try:
        family_publication = (
            calendar_publisher.mcx_contract_family_session_publication
        )
        rule = family_publication.rule_for(contract_family)
        profile = calendar_publisher.mcx_contract_session_profile(
            contract_family=contract_family,
            contract_expiry=contract_expiry,
            trading_date=current_schedule.trading_date,
            observed_at=analysis_boundary,
        )
        base_publication = calendar_publisher.publication("MCX")
        base_schedule = calendar_publisher.schedule(
            "MCX",
            current_schedule.trading_date,
            observed_at=analysis_boundary,
        )
        previous_base = calendar_publisher.schedule(
            "MCX",
            previous_schedule.trading_date,
            observed_at=analysis_boundary,
        )
    except Exception as error:
        raise MarketScheduleCompatibilityError(
            "MARKET_SCHEDULE_COMPATIBILITY_SOURCE_UNAVAILABLE"
        ) from error
    if (
        profile.classification
        is not McxContractSessionClassification.EXPIRY_SESSION_BEFORE_CUTOFF
        or not profile.contract_eligible
        or profile.continuous_trading is None
        or base_schedule is None
        or previous_base is None
        or current_schedule != _as_day_schedule(profile.continuous_trading)
        or previous_schedule != _as_day_schedule(previous_base)
        or current_schedule.source_identity
        == previous_schedule.source_identity
        and current_schedule.source_version == previous_schedule.source_version
        or base_publication.exchange != family_publication.exchange
        or base_publication.timezone != family_publication.timezone
        or profile.contract_family != rule.contract_family
        or profile.publication_identity != family_publication.publication_identity
        or profile.publication_version != family_publication.publication_version
        or profile.publication_sha256 != family_publication.publication_sha256
    ):
        raise MarketScheduleCompatibilityError(
            "MARKET_SCHEDULE_COMPATIBILITY_SOURCE_MISMATCH"
        )
    values = {
        "contract_family": rule.contract_family,
        "exchange": base_publication.exchange,
        "market_identity": base_publication.market_identity,
        "base_segment": base_publication.segment,
        "derived_segment": family_publication.segment,
        "timezone": base_publication.timezone,
        "trading_date": current_schedule.trading_date,
        "previous_trading_date": previous_schedule.trading_date,
        "analysis_boundary": analysis_boundary,
        "current_session_identity": current_schedule.session_id,
        "previous_session_identity": previous_schedule.session_id,
        "base_session_identity": base_schedule.session_identity,
        "base_session_sha256": _schedule_sha256(previous_schedule),
        "base_schedule_identity": base_schedule.source_identity,
        "base_schedule_version": base_schedule.calendar_version,
        "base_publication_identity": base_publication.calendar_identity,
        "base_publication_version": base_publication.calendar_version,
        "base_publication_sha256": base_publication.publication_sha256,
        "base_source_boundary": base_publication.source_boundary,
        "derived_schedule_identity": current_schedule.source_identity,
        "derived_schedule_version": current_schedule.source_version,
        "derived_session_sha256": _schedule_sha256(current_schedule),
        "derived_publication_identity": family_publication.publication_identity,
        "derived_publication_version": family_publication.publication_version,
        "derived_publication_sha256": family_publication.publication_sha256,
        "derived_source_boundary": family_publication.source_boundary,
        "derivation_relationship": (
            "FAMILY_SPECIFIC_EXPIRY_SESSION_SPECIALIZATION"
        ),
        "effective_from": max(
            base_publication.coverage_start,
            family_publication.coverage_start,
            rule.contract_expiry_effective_from,
        ),
        "effective_through": min(
            base_publication.coverage_end,
            family_publication.coverage_end,
            rule.contract_expiry_effective_through,
        ),
        "status": MarketScheduleCompatibilityStatus.CURRENT,
        "superseded_by_identity": None,
        "roll_continuity_authority": False,
        "analytical_authority": False,
        "trading_authority": False,
        "provenance": (
            "ADR-0028",
            base_publication.publication_sha256,
            family_publication.publication_sha256,
            rule.source_artifact_identity,
        ),
        "policy_identity": MARKET_SCHEDULE_COMPATIBILITY_POLICY,
        "policy_version": MARKET_SCHEDULE_COMPATIBILITY_POLICY_VERSION,
        "schema_identity": MARKET_SCHEDULE_COMPATIBILITY_IDENTITY,
        "schema_version": MARKET_SCHEDULE_COMPATIBILITY_VERSION,
    }
    return MarketScheduleCompatibilityArtifact(
        compatibility_identity=_identity(
            "MARKET-SCHEDULE-COMPATIBILITY-", values
        ),
        integrity_identity=_identity(
            "INTEGRITY-MARKET-SCHEDULE-COMPATIBILITY-", values
        ),
        **values,
    )


def require_mcx_schedule_compatibility(
    artifact: MarketScheduleCompatibilityArtifact,
    *,
    current_schedule: MarketDaySchedule,
    previous_schedule: MarketDaySchedule,
    analysis_boundary: datetime,
) -> None:
    """Fail closed unless ``artifact`` authorizes this exact directional pair."""

    try:
        artifact.__post_init__()
    except (AttributeError, MarketScheduleCompatibilityError) as error:
        raise MarketScheduleCompatibilityError(
            "MARKET_SCHEDULE_COMPATIBILITY_NOT_APPLICABLE"
        ) from error
    if (
        type(artifact) is not MarketScheduleCompatibilityArtifact
        or type(current_schedule) is not MarketDaySchedule
        or type(previous_schedule) is not MarketDaySchedule
        or not _aware(analysis_boundary)
        or current_schedule.status is not TradingDayStatus.TRADING
        or previous_schedule.status is not TradingDayStatus.TRADING
        or previous_schedule.trading_date >= current_schedule.trading_date
        or artifact.status is not MarketScheduleCompatibilityStatus.CURRENT
        or artifact.analysis_boundary != analysis_boundary
        or artifact.trading_date != current_schedule.trading_date
        or artifact.previous_trading_date != previous_schedule.trading_date
        or artifact.current_session_identity != current_schedule.session_id
        or artifact.previous_session_identity != previous_schedule.session_id
        or artifact.derived_session_sha256 != _schedule_sha256(current_schedule)
        or artifact.base_session_sha256 != _schedule_sha256(previous_schedule)
        or artifact.exchange != current_schedule.exchange
        or artifact.exchange != previous_schedule.exchange
        or artifact.timezone != current_schedule.timezone
        or artifact.timezone != previous_schedule.timezone
        or artifact.derived_schedule_identity != current_schedule.source_identity
        or artifact.derived_schedule_version != current_schedule.source_version
        or artifact.base_schedule_identity != previous_schedule.source_identity
        or artifact.base_schedule_version != previous_schedule.source_version
        or artifact.current_session_identity == artifact.base_session_identity
        or artifact.roll_continuity_authority
        or artifact.analytical_authority
        or artifact.trading_authority
    ):
        raise MarketScheduleCompatibilityError(
            "MARKET_SCHEDULE_COMPATIBILITY_NOT_APPLICABLE"
        )


def _as_day_schedule(value: MarketSchedule) -> MarketDaySchedule:
    return MarketDaySchedule(
        exchange=value.exchange,
        trading_date=value.trading_date,
        session_id=value.session_identity,
        timezone=value.timezone,
        status=TradingDayStatus.TRADING,
        windows=tuple(
            MarketWindow(item.window_open, item.window_close)
            for item in value.windows
        ),
        source_identity=value.source_identity,
        source_version=value.calendar_version,
        special_session="EXPIRY" in value.session_type,
    )


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(value)).hexdigest().upper()


def _schedule_sha256(value: MarketDaySchedule) -> str:
    return sha256(_encode(value)).hexdigest()


def _encode(value: object) -> bytes:
    return json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {name: _normalize(item) for name, item in asdict(value).items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(name): _normalize(item) for name, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _texts(values: tuple[object, ...]) -> bool:
    return bool(values) and all(_text(item) for item in values)


__all__ = [
    "MARKET_SCHEDULE_COMPATIBILITY_IDENTITY",
    "MARKET_SCHEDULE_COMPATIBILITY_POLICY",
    "MARKET_SCHEDULE_COMPATIBILITY_POLICY_VERSION",
    "MARKET_SCHEDULE_COMPATIBILITY_VERSION",
    "MarketScheduleCompatibilityArtifact",
    "MarketScheduleCompatibilityError",
    "MarketScheduleCompatibilityStatus",
    "publish_mcx_schedule_compatibility",
    "require_mcx_schedule_compatibility",
]
