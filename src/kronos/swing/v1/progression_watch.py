"""Swing progression requirements and non-trading watch state.

The contract is deliberately narrower than Readiness, Trade Construction, and
execution.  A reached condition requests reassessment only.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re

from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.mtf_facts import FactualTimeframe
from kronos.swing.v1.native_readiness import (
    LevelAvailability,
    NativeLayer2ReadinessRecord,
    NextConditionEvidence,
    NextConditionState,
    ThesisIntact,
)


PROGRESSION_WATCH_POLICY_ID = "SWING-UX-08-PROGRESSION-WATCH-V0"
PROGRESSION_WATCH_POLICY_VERSION = "0"
PROGRESSION_WATCH_AUTHORITY = "REASSESSMENT_ONLY_NO_READINESS_TRADE_OR_EXECUTION_AUTHORITY"
DEFAULT_PROGRESSION_WATCH_ROOT = (
    Path.home() / "Library" / "Application Support" / "KRONOS" / "evidence"
    / "swing-v1" / "progression-watches-v0"
)


class ProgressionRequirementState(StrEnum):
    SATISFIED = "SATISFIED"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    NOT_WATCHABLE = "NOT_WATCHABLE"
    WATCH_AVAILABLE = "WATCH_AVAILABLE"
    WATCH_ACTIVE = "WATCH_ACTIVE"
    ALREADY_SATISFIED = "ALREADY_SATISFIED"


class ProgressionComparator(StrEnum):
    BAR_CLOSE_ABOVE = "BAR_CLOSE_ABOVE"
    BAR_CLOSE_BELOW = "BAR_CLOSE_BELOW"


class ProgressionWatchState(StrEnum):
    ACTIVE = "ACTIVE"
    TRIGGERED = "TRIGGERED"
    INACTIVE = "INACTIVE"
    STALE = "STALE"


class ProgressionWatchEventType(StrEnum):
    ACTIVATED = "ACTIVATED"
    DEACTIVATED = "DEACTIVATED"
    REACTIVATED = "REACTIVATED"
    TRIGGERED = "TRIGGERED"
    STALE = "STALE"
    DELETED = "DELETED"


_WATCHABLE_EVENTS = {
    "COMPLETED_ONE_HOUR_CLOSE_ABOVE": (
        FactualTimeframe.ONE_HOUR, ProgressionComparator.BAR_CLOSE_ABOVE,
    ),
    "COMPLETED_ONE_HOUR_CLOSE_BELOW": (
        FactualTimeframe.ONE_HOUR, ProgressionComparator.BAR_CLOSE_BELOW,
    ),
    "COMPLETED_FOUR_HOUR_CLOSE_ABOVE": (
        FactualTimeframe.FOUR_HOUR, ProgressionComparator.BAR_CLOSE_ABOVE,
    ),
    "COMPLETED_FOUR_HOUR_CLOSE_BELOW": (
        FactualTimeframe.FOUR_HOUR, ProgressionComparator.BAR_CLOSE_BELOW,
    ),
}


@dataclass(frozen=True, slots=True)
class ProgressionRequirement:
    requirement_id: str
    product: str
    canonical_instrument: str
    direction: V1Direction
    native_run_identity: str
    native_assessment_sha256: str
    source_analytical_state: str
    condition_identity: str
    summary: str
    state: ProgressionRequirementState
    timeframe: FactualTimeframe | None
    comparator: ProgressionComparator | None
    price: float | None
    zone_low: float | None
    zone_high: float | None
    source_evidence_ids: tuple[str, ...]
    observation_boundary: datetime
    provenance: tuple[str, ...]
    policy_identity: str = PROGRESSION_WATCH_POLICY_ID
    policy_version: str = PROGRESSION_WATCH_POLICY_VERSION
    authority: str = PROGRESSION_WATCH_AUTHORITY

    def __post_init__(self) -> None:
        watchable = self.state in {
            ProgressionRequirementState.WATCH_AVAILABLE,
            ProgressionRequirementState.WATCH_ACTIVE,
            ProgressionRequirementState.ALREADY_SATISFIED,
        }
        if (
            not _digest(self.requirement_id)
            or self.product != "SWING"
            or not self.canonical_instrument
            or self.direction not in {V1Direction.LONG, V1Direction.SHORT}
            or not is_swing_analysis_run_id(self.native_run_identity)
            or not _digest(self.native_assessment_sha256)
            or not _code(self.source_analytical_state)
            or not _code(self.condition_identity)
            or not self.summary
            or type(self.state) is not ProgressionRequirementState
            or (self.timeframe is not None and type(self.timeframe) is not FactualTimeframe)
            or (self.comparator is not None and type(self.comparator) is not ProgressionComparator)
            or not _level_shape(self.price, self.zone_low, self.zone_high)
            or (watchable and (self.timeframe is None or self.comparator is None or self.price is None))
            or (not watchable and self.comparator is not None)
            or not self.source_evidence_ids
            or not _aware(self.observation_boundary)
            or not self.provenance
            or self.policy_identity != PROGRESSION_WATCH_POLICY_ID
            or self.policy_version != PROGRESSION_WATCH_POLICY_VERSION
            or self.authority != PROGRESSION_WATCH_AUTHORITY
        ):
            raise ValueError("PROGRESSION_REQUIREMENT_INVALID")


@dataclass(frozen=True, slots=True)
class GovernedCompletedBar:
    canonical_instrument: str
    timeframe: FactualTimeframe
    close: float
    observation_boundary: datetime
    source_identity: str
    calendar_identity: str
    calendar_version: str
    session_identity: str
    provenance: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.canonical_instrument
            or self.timeframe not in {FactualTimeframe.ONE_HOUR, FactualTimeframe.FOUR_HOUR}
            or type(self.close) is not float
            or not math.isfinite(self.close)
            or self.close < 0.0
            or not _aware(self.observation_boundary)
            or not all((self.source_identity, self.calendar_identity, self.calendar_version, self.session_identity))
            or not self.provenance
        ):
            raise ValueError("GOVERNED_COMPLETED_BAR_INVALID")


@dataclass(frozen=True, slots=True)
class ProgressionWatchEvent:
    event_id: str
    event_type: ProgressionWatchEventType
    occurred_at: datetime
    summary: str

    def __post_init__(self) -> None:
        if (
            not _digest(self.event_id)
            or type(self.event_type) is not ProgressionWatchEventType
            or not _aware(self.occurred_at)
            or not self.summary
        ):
            raise ValueError("PROGRESSION_WATCH_EVENT_INVALID")


@dataclass(frozen=True, slots=True)
class ProgressionWatch:
    watch_id: str
    requirement: ProgressionRequirement
    state: ProgressionWatchState
    activated_at: datetime
    triggered_at: datetime | None = None
    trigger_bar: GovernedCompletedBar | None = None
    consequence: str = "REASSESSMENT_REQUIRED"
    workspace_hidden: bool = False
    history: tuple[ProgressionWatchEvent, ...] = ()

    def __post_init__(self) -> None:
        triggered = self.state is ProgressionWatchState.TRIGGERED
        if (
            not _digest(self.watch_id)
            or type(self.requirement) is not ProgressionRequirement
            or self.requirement.state not in {
                ProgressionRequirementState.WATCH_AVAILABLE,
                ProgressionRequirementState.WATCH_ACTIVE,
                ProgressionRequirementState.ALREADY_SATISFIED,
            }
            or type(self.state) is not ProgressionWatchState
            or not _aware(self.activated_at)
            or triggered != (self.triggered_at is not None and self.trigger_bar is not None)
            or (self.triggered_at is not None and not _aware(self.triggered_at))
            or (
                self.trigger_bar is not None
                and (
                    self.trigger_bar.canonical_instrument != self.requirement.canonical_instrument
                    or self.trigger_bar.timeframe is not self.requirement.timeframe
                )
            )
            or self.consequence != "REASSESSMENT_REQUIRED"
            or type(self.workspace_hidden) is not bool
            or type(self.history) is not tuple
            or any(type(item) is not ProgressionWatchEvent for item in self.history)
            or len({item.event_id for item in self.history}) != len(self.history)
            or any(
                later.occurred_at < earlier.occurred_at
                for earlier, later in zip(self.history, self.history[1:])
            )
        ):
            raise ValueError("PROGRESSION_WATCH_INVALID")


def derive_progression_requirements(
    *,
    canonical_instrument: str,
    direction: V1Direction,
    native_run_identity: str,
    native_assessment_sha256: str,
    source_analytical_state: str,
    observation_boundary: datetime,
    provenance: tuple[str, ...],
    readiness: NativeLayer2ReadinessRecord | None,
    missing_evidence: tuple[str, ...] = (),
) -> tuple[ProgressionRequirement, ...]:
    """Project governed state without creating a new analytical predicate."""

    common = dict(
        canonical_instrument=canonical_instrument,
        direction=direction,
        native_run_identity=native_run_identity,
        native_assessment_sha256=native_assessment_sha256,
        source_analytical_state=source_analytical_state,
        observation_boundary=observation_boundary,
        provenance=provenance,
    )
    result = [_requirement(
        **common,
        condition_identity="NATIVE_THESIS_INTACT",
        summary="Native thesis intact",
        state=(
            ProgressionRequirementState.SATISFIED
            if readiness is not None and readiness.conditions.thesis_intact is ThesisIntact.YES
            else ProgressionRequirementState.EVIDENCE_REQUIRED
        ),
        source_evidence_ids=(native_assessment_sha256,),
    )]
    for label in missing_evidence:
        result.append(_requirement(
            **common,
            condition_identity="EVIDENCE_" + re.sub(r"[^A-Z0-9]+", "_", label.upper()).strip("_"),
            summary=f"{label} must be established",
            state=ProgressionRequirementState.EVIDENCE_REQUIRED,
            source_evidence_ids=(native_assessment_sha256,),
        ))
    if readiness is None:
        result.append(_requirement(
            **common,
            condition_identity="GOVERNED_REVIEW_READINESS",
            summary="Governed Review and Readiness evidence must be established",
            state=ProgressionRequirementState.EVIDENCE_REQUIRED,
            source_evidence_ids=(native_assessment_sha256,),
        ))
    elif readiness.conditions.next_condition_state is NextConditionState.AVAILABLE:
        assert readiness.conditions.next_condition is not None
        result.append(_from_next_condition(common, readiness.conditions.next_condition))
    elif readiness.conditions.next_condition_state is NextConditionState.UNAVAILABLE:
        result.append(_requirement(
            **common,
            condition_identity="GOVERNED_NEXT_CONDITION",
            summary="A deterministic next condition is not established",
            state=ProgressionRequirementState.NOT_WATCHABLE,
            source_evidence_ids=(readiness.result_sha256,),
        ))
    return tuple(result)


def activate_watch(requirement: ProgressionRequirement, *, activated_at: datetime) -> ProgressionWatch:
    if requirement.state is not ProgressionRequirementState.WATCH_AVAILABLE or not _aware(activated_at):
        raise ValueError("PROGRESSION_WATCH_ACTIVATION_NOT_PERMITTED")
    watch_id = _identity("SWING-PROGRESSION-WATCH", requirement.requirement_id)
    event = _event(watch_id, ProgressionWatchEventType.ACTIVATED, activated_at)
    return ProgressionWatch(
        watch_id, requirement, ProgressionWatchState.ACTIVE, activated_at,
        history=(event,),
    )


def observe_completed_bar(watch: ProgressionWatch, bar: GovernedCompletedBar) -> ProgressionWatch:
    """Apply only a completed governed bar; ticks have no trigger authority."""

    if type(watch) is not ProgressionWatch or type(bar) is not GovernedCompletedBar:
        raise TypeError("PROGRESSION_WATCH_OBSERVATION_INVALID")
    if watch.state is not ProgressionWatchState.ACTIVE:
        return watch
    requirement = watch.requirement
    if (
        bar.canonical_instrument != requirement.canonical_instrument
        or bar.timeframe is not requirement.timeframe
        or bar.observation_boundary <= requirement.observation_boundary
    ):
        return watch
    reached = (
        bar.close > requirement.price
        if requirement.comparator is ProgressionComparator.BAR_CLOSE_ABOVE
        else bar.close < requirement.price
    )
    if not reached:
        return watch
    event = _event(watch.watch_id, ProgressionWatchEventType.TRIGGERED, bar.observation_boundary)
    return replace(
        watch,
        state=ProgressionWatchState.TRIGGERED,
        triggered_at=bar.observation_boundary,
        trigger_bar=bar,
        history=(*watch.history, event),
    )


def mark_watch_stale(
    watch: ProgressionWatch, *, occurred_at: datetime | None = None,
) -> ProgressionWatch:
    if watch.state not in {ProgressionWatchState.ACTIVE, ProgressionWatchState.INACTIVE}:
        return watch
    timestamp = occurred_at or datetime.now(watch.activated_at.tzinfo)
    event = _event(watch.watch_id, ProgressionWatchEventType.STALE, timestamp)
    return replace(
        watch, state=ProgressionWatchState.STALE,
        history=(*watch.history, event),
    )


def deactivate_watch(watch: ProgressionWatch, *, occurred_at: datetime) -> ProgressionWatch:
    if watch.state is ProgressionWatchState.INACTIVE:
        return watch
    if watch.state is not ProgressionWatchState.ACTIVE or not _aware(occurred_at):
        raise ValueError("PROGRESSION_WATCH_DEACTIVATION_NOT_PERMITTED")
    event = _event(watch.watch_id, ProgressionWatchEventType.DEACTIVATED, occurred_at)
    return replace(
        watch, state=ProgressionWatchState.INACTIVE,
        history=(*watch.history, event),
    )


def reactivate_watch(watch: ProgressionWatch, *, occurred_at: datetime) -> ProgressionWatch:
    if watch.state is ProgressionWatchState.ACTIVE:
        return watch
    if (
        watch.state is not ProgressionWatchState.INACTIVE
        or watch.workspace_hidden
        or not _aware(occurred_at)
    ):
        raise ValueError("PROGRESSION_WATCH_REACTIVATION_NOT_PERMITTED")
    event = _event(watch.watch_id, ProgressionWatchEventType.REACTIVATED, occurred_at)
    return replace(
        watch, state=ProgressionWatchState.ACTIVE,
        history=(*watch.history, event),
    )


def hide_watch(watch: ProgressionWatch, *, occurred_at: datetime) -> ProgressionWatch:
    if watch.workspace_hidden:
        return watch
    if not _aware(occurred_at):
        raise ValueError("PROGRESSION_WATCH_DELETE_NOT_PERMITTED")
    event = _event(watch.watch_id, ProgressionWatchEventType.DELETED, occurred_at)
    state = (
        ProgressionWatchState.INACTIVE
        if watch.state is ProgressionWatchState.ACTIVE else watch.state
    )
    return replace(
        watch, state=state, workspace_hidden=True,
        history=(*watch.history, event),
    )


def tradingview_instruction(requirement: ProgressionRequirement) -> tuple[tuple[str, str], ...]:
    if requirement.state not in {
        ProgressionRequirementState.WATCH_AVAILABLE,
        ProgressionRequirementState.WATCH_ACTIVE,
        ProgressionRequirementState.ALREADY_SATISFIED,
    }:
        raise ValueError("TRADINGVIEW_PROGRESSION_INSTRUCTION_UNAVAILABLE")
    direction = "above" if requirement.comparator is ProgressionComparator.BAR_CLOSE_ABOVE else "below"
    return (
        ("Instrument", requirement.canonical_instrument),
        ("Timeframe", requirement.timeframe.value),
        ("Condition", f"Bar close crosses {direction} {requirement.price:g}"),
        ("Purpose", "KRONOS progression watch"),
    )


class ProgressionWatchStore:
    def __init__(self, root: Path = DEFAULT_PROGRESSION_WATCH_ROOT) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("PROGRESSION_WATCH_STORE_ROOT_INVALID")

    def retain(self, watch: ProgressionWatch) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = _watch_to_dict(watch)
        path = self.root / f"{watch.watch_id}.json"
        if path.exists():
            current = _watch_from_dict(json.loads(path.read_text(encoding="utf-8")))
            allowed = current == watch or (
                current.watch_id == watch.watch_id
                and current.requirement == watch.requirement
                and current.activated_at == watch.activated_at
                and not current.workspace_hidden
                and watch.history[:len(current.history)] == current.history
                and len(watch.history) > len(current.history)
                and (
                    (current.state is ProgressionWatchState.ACTIVE and watch.state in {
                        ProgressionWatchState.TRIGGERED,
                        ProgressionWatchState.STALE,
                        ProgressionWatchState.INACTIVE,
                    })
                    or (current.state is ProgressionWatchState.INACTIVE and watch.state in {
                        ProgressionWatchState.ACTIVE,
                        ProgressionWatchState.STALE,
                        ProgressionWatchState.INACTIVE,
                    })
                    or (current.state is watch.state and watch.workspace_hidden)
                )
            )
            if not allowed:
                raise ValueError("PROGRESSION_WATCH_TRANSITION_INVALID")
        for event in watch.history:
            event_payload = _event_to_dict(event, watch.watch_id)
            event_path = self.root / "events" / f"{event.event_id}.json"
            if event_path.exists() and json.loads(event_path.read_text(encoding="utf-8")) != event_payload:
                raise ValueError("PROGRESSION_WATCH_EVENT_IMMUTABLE")
            if not event_path.exists():
                _atomic_payload(event_path, event_payload)
        _atomic_payload(path, payload)

    def load(self) -> tuple[ProgressionWatch, ...]:
        if not self.root.exists():
            return ()
        return tuple(_watch_from_dict(json.loads(path.read_text(encoding="utf-8"))) for path in sorted(self.root.glob("*.json")))


def _from_next_condition(common: dict[str, object], value: NextConditionEvidence) -> ProgressionRequirement:
    bound = dict(common)
    bound["observation_boundary"] = value.observation_boundary
    watch_shape = _WATCHABLE_EVENTS.get(value.required_event)
    if (
        watch_shape is None
        or value.level_availability is not LevelAvailability.AVAILABLE
        or value.price is None
        or value.zone_low is not None
        or value.zone_high is not None
        or value.timeframe is not watch_shape[0]
    ):
        return _requirement(
            **bound,
            condition_identity=value.condition_type,
            summary=value.required_event.replace("_", " ").title(),
            state=ProgressionRequirementState.NOT_WATCHABLE,
            timeframe=value.timeframe,
            price=value.price,
            zone_low=value.zone_low,
            zone_high=value.zone_high,
            source_evidence_ids=value.source_evidence_ids,
        )
    comparator = watch_shape[1]
    word = "above" if comparator is ProgressionComparator.BAR_CLOSE_ABOVE else "below"
    return _requirement(
        **bound,
        condition_identity=value.condition_type,
        summary=f"{value.timeframe.value} close {word} {value.price:g}",
        state=ProgressionRequirementState.WATCH_AVAILABLE,
        timeframe=value.timeframe,
        comparator=comparator,
        price=value.price,
        source_evidence_ids=value.source_evidence_ids,
    )


def _requirement(
    *,
    canonical_instrument: str,
    direction: V1Direction,
    native_run_identity: str,
    native_assessment_sha256: str,
    source_analytical_state: str,
    condition_identity: str,
    summary: str,
    state: ProgressionRequirementState,
    source_evidence_ids: tuple[str, ...],
    observation_boundary: datetime,
    provenance: tuple[str, ...],
    timeframe: FactualTimeframe | None = None,
    comparator: ProgressionComparator | None = None,
    price: float | None = None,
    zone_low: float | None = None,
    zone_high: float | None = None,
) -> ProgressionRequirement:
    material = (
        native_run_identity, native_assessment_sha256, canonical_instrument,
        condition_identity, timeframe.value if timeframe else "NONE",
        comparator.value if comparator else "NONE", price, zone_low, zone_high,
    )
    return ProgressionRequirement(
        _identity("SWING-PROGRESSION-REQUIREMENT", *material), "SWING",
        canonical_instrument, direction, native_run_identity,
        native_assessment_sha256, source_analytical_state, condition_identity,
        summary, state, timeframe, comparator, price, zone_low, zone_high,
        source_evidence_ids, observation_boundary, provenance,
    )


def _identity(prefix: str, *values: object) -> str:
    return sha256(json.dumps((prefix, values), sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _event(
    watch_id: str, event_type: ProgressionWatchEventType, occurred_at: datetime,
) -> ProgressionWatchEvent:
    return ProgressionWatchEvent(
        _identity("SWING-PROGRESSION-WATCH-EVENT", watch_id, event_type.value, occurred_at.isoformat()),
        event_type, occurred_at, event_type.value.replace("_", " ").title(),
    )


def _event_to_dict(value: ProgressionWatchEvent, watch_id: str) -> dict[str, object]:
    return {
        "event_id": value.event_id,
        "watch_id": watch_id,
        "event_type": value.event_type.value,
        "occurred_at": value.occurred_at.isoformat(),
        "summary": value.summary,
    }


def _watch_to_dict(value: ProgressionWatch) -> dict[str, object]:
    requirement = value.requirement
    return {
        "watch_id": value.watch_id,
        "state": value.state.value,
        "activated_at": value.activated_at.isoformat(),
        "triggered_at": None if value.triggered_at is None else value.triggered_at.isoformat(),
        "consequence": value.consequence,
        "workspace_hidden": value.workspace_hidden,
        "history": tuple(_event_to_dict(item, value.watch_id) for item in value.history),
        "requirement": {
            "requirement_id": requirement.requirement_id,
            "product": requirement.product,
            "canonical_instrument": requirement.canonical_instrument,
            "direction": requirement.direction.value,
            "native_run_identity": requirement.native_run_identity,
            "native_assessment_sha256": requirement.native_assessment_sha256,
            "source_analytical_state": requirement.source_analytical_state,
            "condition_identity": requirement.condition_identity,
            "summary": requirement.summary,
            "state": requirement.state.value,
            "timeframe": None if requirement.timeframe is None else requirement.timeframe.value,
            "comparator": None if requirement.comparator is None else requirement.comparator.value,
            "price": requirement.price,
            "zone_low": requirement.zone_low,
            "zone_high": requirement.zone_high,
            "source_evidence_ids": requirement.source_evidence_ids,
            "observation_boundary": requirement.observation_boundary.isoformat(),
            "provenance": requirement.provenance,
        },
        "trigger_bar": None if value.trigger_bar is None else {
            "canonical_instrument": value.trigger_bar.canonical_instrument,
            "timeframe": value.trigger_bar.timeframe.value,
            "close": value.trigger_bar.close,
            "observation_boundary": value.trigger_bar.observation_boundary.isoformat(),
            "source_identity": value.trigger_bar.source_identity,
            "calendar_identity": value.trigger_bar.calendar_identity,
            "calendar_version": value.trigger_bar.calendar_version,
            "session_identity": value.trigger_bar.session_identity,
            "provenance": value.trigger_bar.provenance,
        },
    }


def _watch_from_dict(value: dict[str, object]) -> ProgressionWatch:
    raw = value["requirement"]
    assert isinstance(raw, dict)
    requirement = ProgressionRequirement(
        raw["requirement_id"], raw["product"], raw["canonical_instrument"],
        V1Direction(raw["direction"]), raw["native_run_identity"],
        raw["native_assessment_sha256"], raw["source_analytical_state"],
        raw["condition_identity"], raw["summary"], ProgressionRequirementState(raw["state"]),
        None if raw["timeframe"] is None else FactualTimeframe(raw["timeframe"]),
        None if raw["comparator"] is None else ProgressionComparator(raw["comparator"]),
        raw["price"], raw["zone_low"], raw["zone_high"],
        tuple(raw["source_evidence_ids"]), datetime.fromisoformat(raw["observation_boundary"]),
        tuple(raw["provenance"]),
    )
    bar_raw = value["trigger_bar"]
    bar = None if bar_raw is None else GovernedCompletedBar(
        bar_raw["canonical_instrument"], FactualTimeframe(bar_raw["timeframe"]),
        bar_raw["close"], datetime.fromisoformat(bar_raw["observation_boundary"]),
        bar_raw["source_identity"], bar_raw["calendar_identity"],
        bar_raw["calendar_version"], bar_raw["session_identity"], tuple(bar_raw["provenance"]),
    )
    history = tuple(
        ProgressionWatchEvent(
            item["event_id"], ProgressionWatchEventType(item["event_type"]),
            datetime.fromisoformat(item["occurred_at"]), item["summary"],
        )
        for item in value.get("history", ())
    )
    if not history:
        activated_at = datetime.fromisoformat(value["activated_at"])
        history = (_event(value["watch_id"], ProgressionWatchEventType.ACTIVATED, activated_at),)
        state = ProgressionWatchState(value["state"])
        if state is ProgressionWatchState.TRIGGERED:
            history += (_event(value["watch_id"], ProgressionWatchEventType.TRIGGERED, datetime.fromisoformat(value["triggered_at"])),)
        elif state is ProgressionWatchState.STALE:
            history += (_event(value["watch_id"], ProgressionWatchEventType.STALE, activated_at),)
    return ProgressionWatch(
        value["watch_id"], requirement, ProgressionWatchState(value["state"]),
        datetime.fromisoformat(value["activated_at"]),
        None if value["triggered_at"] is None else datetime.fromisoformat(value["triggered_at"]),
        bar, value["consequence"], bool(value.get("workspace_hidden", False)), history,
    )


def _atomic_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _code(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", value) is not None


def _level_shape(price: object, low: object, high: object) -> bool:
    numbers = (price, low, high)
    if any(
        value is not None
        and (
            type(value) is not float
            or not math.isfinite(value)
            or value < 0.0
        )
        for value in numbers
    ):
        return False
    if price is not None:
        return low is None and high is None
    if low is None and high is None:
        return True
    return low is not None and high is not None and low <= high


__all__ = [
    "DEFAULT_PROGRESSION_WATCH_ROOT", "GovernedCompletedBar",
    "PROGRESSION_WATCH_AUTHORITY", "PROGRESSION_WATCH_POLICY_ID",
    "ProgressionComparator", "ProgressionRequirement",
    "ProgressionRequirementState", "ProgressionWatch", "ProgressionWatchState",
    "ProgressionWatchEvent", "ProgressionWatchEventType",
    "ProgressionWatchStore", "activate_watch", "derive_progression_requirements",
    "deactivate_watch", "hide_watch", "mark_watch_stale", "observe_completed_bar",
    "reactivate_watch", "tradingview_instruction",
]
