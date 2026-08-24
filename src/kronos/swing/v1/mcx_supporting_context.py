"""MCX-CONTEXT-01 immutable twice-daily supporting visual evidence.

This evidence family is descriptive only.  It has no Native Discovery,
Readiness, KR-370, trade-construction, risk, timing, or execution authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock


MCX_CONTEXT_CONTRACT_ID = "KRONOS-SWING-MCX-DAILY-SUPPORTING-CONTEXT-V1"
MCX_CONTEXT_CONTRACT_VERSION = "1.0"
MCX_CONTEXT_QUESTION_SCHEMA = "KRONOS-SWING-MCX-CONTEXT-QUESTION-V1"
MCX_CONTEXT_ANSWER_SCHEMA = "KRONOS-SWING-MCX-CONTEXT-ANSWER-V1"
MCX_CONTEXT_AUTHORITY = "SUPPORTING_EVIDENCE_ONLY"
MCX_CONTEXT_POLICY_STATE = "UNAVAILABLE_POLICY_NOT_COMMISSIONED"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class McxContextSlot(StrEnum):
    MORNING = "MORNING"
    EVENING = "EVENING"


class McxContextFamily(StrEnum):
    METALS = "METALS"
    ENERGY = "ENERGY"


class PanelValidation(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    UNREADABLE = "UNREADABLE"


class DirectionState(StrEnum):
    RISING = "RISING"
    FALLING = "FALLING"
    RANGE = "RANGE"
    UNCLEAR = "UNCLEAR"


class EvidenceQuality(StrEnum):
    CLEAR = "CLEAR"
    PARTIAL = "PARTIAL"
    UNREADABLE = "UNREADABLE"


class StructuralCondition(StrEnum):
    TRENDING = "TRENDING"
    CONSOLIDATING = "CONSOLIDATING"
    TRANSITIONING = "TRANSITIONING"
    UNCLEAR = "UNCLEAR"


class AlignmentState(StrEnum):
    ALIGNED = "ALIGNED"
    DIVERGENT = "DIVERGENT"
    UNCLEAR = "UNCLEAR"


class ContextAvailability(StrEnum):
    VALID = "VALID"
    NOT_PROVIDED = "NOT_PROVIDED"
    INVALID_INCOMPLETE = "INVALID_INCOMPLETE"
    NOT_REQUIRED = "NOT_REQUIRED"


@dataclass(frozen=True, slots=True)
class McxContextPanelDefinition:
    panel_id: str
    expected_identity: str
    expected_timeframe: str
    accepted_visible_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.panel_id
            or not self.expected_identity
            or self.expected_timeframe not in {"1D", "1H", "4H"}
            or not self.accepted_visible_identities
            or self.expected_identity not in self.accepted_visible_identities
            or len(set(self.accepted_visible_identities))
            != len(self.accepted_visible_identities)
            or any(
                type(value) is not str or not value
                for value in self.accepted_visible_identities
            )
        ):
            raise ValueError("MCX_CONTEXT_PANEL_DEFINITION_INVALID")


class McxContextPanelField(StrEnum):
    IDENTITY = "IDENTITY"
    TIMEFRAME = "TIMEFRAME"
    VALIDATION = "VALIDATION"
    EVIDENCE_QUALITY = "EVIDENCE_QUALITY"


@dataclass(frozen=True, slots=True)
class McxContextPanelValidationFailure:
    family: McxContextFamily
    panel_id: str
    failed_field: McxContextPanelField
    expected: str
    observed: str
    machine_code: str = "MCX_CONTEXT_PANEL_INVALID_INCOMPLETE"

    def __post_init__(self) -> None:
        if (
            type(self.family) is not McxContextFamily
            or not self.panel_id
            or type(self.failed_field) is not McxContextPanelField
            or not self.expected
            or not self.observed
            or self.machine_code != "MCX_CONTEXT_PANEL_INVALID_INCOMPLETE"
        ):
            raise ValueError("MCX_CONTEXT_PANEL_DIAGNOSTIC_INVALID")


METALS_PANELS = (
    McxContextPanelDefinition("M1", "US Dollar Index Futures / DXY", "1D", ("US Dollar Index Futures / DXY", "US Dollar Index Futures")),
    McxContextPanelDefinition("M2", "US Government Bonds 10Y Yield", "1D", ("US Government Bonds 10Y Yield", "US Government Bonds 10 YR Yield")),
    McxContextPanelDefinition("M3", "US Government Bonds 30Y Yield", "1D", ("US Government Bonds 30Y Yield", "US Government Bonds 30 YR")),
    McxContextPanelDefinition("M4", "USD / INR", "1D", ("USD / INR", "U.S. Dollar / Indian Rupee")),
    McxContextPanelDefinition("M5", "COMEX Copper Futures", "1D", ("COMEX Copper Futures", "Copper Futures")),
    McxContextPanelDefinition("M6", "USD / CNH", "1D", ("USD / CNH", "USD/CNH")),
    McxContextPanelDefinition("M7", "CSI 300", "1D", ("CSI 300", "CSI 300 Index Futures")),
    McxContextPanelDefinition("M8", "COMEX Gold Futures", "1D", ("COMEX Gold Futures", "Gold Futures")),
)
ENERGY_PANELS = (
    McxContextPanelDefinition("E1", "NYMEX / Henry Hub Natural Gas", "1D", ("NYMEX / Henry Hub Natural Gas", "Natural Gas Futures")),
    McxContextPanelDefinition("E2", "NYMEX / Henry Hub Natural Gas", "4H", ("NYMEX / Henry Hub Natural Gas", "Natural Gas Futures")),
    McxContextPanelDefinition("E3", "USD / INR", "1H", ("USD / INR", "U.S. Dollar / Indian Rupee")),
    McxContextPanelDefinition("E4", "WTI / NYMEX Light Crude Oil", "1D", ("WTI / NYMEX Light Crude Oil", "Light Crude Oil Futures")),
    McxContextPanelDefinition("E5", "Brent Crude Oil", "1D", ("Brent Crude Oil", "Crude Oil Brent Cash")),
    McxContextPanelDefinition("E6", "DXY", "1H", ("DXY", "U.S. Dollar Index")),
)
MCX_CONTEXT_INSTRUMENT_FAMILIES = {
    "GOLDM": McxContextFamily.METALS,
    "SILVERM": McxContextFamily.METALS,
    "COPPER": McxContextFamily.METALS,
    "CRUDEOIL": McxContextFamily.ENERGY,
    "NATURALGAS": McxContextFamily.ENERGY,
}


def panels_for(family: McxContextFamily) -> tuple[McxContextPanelDefinition, ...]:
    return METALS_PANELS if family is McxContextFamily.METALS else ENERGY_PANELS


_TIMEFRAME_EQUIVALENTS = {
    "1D": "1D",
    "1d": "1D",
    "1H": "1H",
    "1h": "1H",
    "4H": "4H",
    "4h": "4H",
}


def canonical_mcx_context_timeframe(value: str) -> str | None:
    """Return only an explicitly approved equivalent timeframe spelling."""

    return _TIMEFRAME_EQUIVALENTS.get(value) if type(value) is str else None


def panel_validation_failure(
    family: McxContextFamily,
    definition: McxContextPanelDefinition,
    observation: McxContextPanelObservation,
) -> McxContextPanelValidationFailure | None:
    """Validate raw visible evidence without rewriting the observation."""

    if observation.observed_identity not in definition.accepted_visible_identities:
        return McxContextPanelValidationFailure(
            family, definition.panel_id, McxContextPanelField.IDENTITY,
            definition.expected_identity, observation.observed_identity,
        )
    if canonical_mcx_context_timeframe(observation.observed_timeframe) != definition.expected_timeframe:
        return McxContextPanelValidationFailure(
            family, definition.panel_id, McxContextPanelField.TIMEFRAME,
            definition.expected_timeframe, observation.observed_timeframe,
        )
    if observation.validation is not PanelValidation.MATCH:
        return McxContextPanelValidationFailure(
            family, definition.panel_id, McxContextPanelField.VALIDATION,
            PanelValidation.MATCH.value, observation.validation.value,
        )
    if observation.evidence_quality is EvidenceQuality.UNREADABLE:
        return McxContextPanelValidationFailure(
            family, definition.panel_id, McxContextPanelField.EVIDENCE_QUALITY,
            "CLEAR_OR_PARTIAL", observation.evidence_quality.value,
        )
    return None


@dataclass(frozen=True, slots=True)
class McxContextPanelObservation:
    panel_id: str
    observed_identity: str
    observed_timeframe: str
    validation: PanelValidation
    direction: DirectionState
    evidence_quality: EvidenceQuality
    structural_condition: StructuralCondition

    def __post_init__(self) -> None:
        if (
            not self.panel_id
            or not self.observed_identity
            or not self.observed_timeframe
            or type(self.validation) is not PanelValidation
            or type(self.direction) is not DirectionState
            or type(self.evidence_quality) is not EvidenceQuality
            or type(self.structural_condition) is not StructuralCondition
        ):
            raise ValueError("MCX_CONTEXT_PANEL_OBSERVATION_INVALID")


@dataclass(frozen=True, slots=True)
class McxSupportingContextRecord:
    record_id: str
    trading_date: date
    slot: McxContextSlot
    family: McxContextFamily
    revision: int
    question_pack_identity: str
    answer_pack_identity: str
    captured_at: datetime
    imported_at: datetime
    panels: tuple[McxContextPanelObservation, ...]
    wti_brent_alignment: AlignmentState | None
    natural_gas_alignment: AlignmentState | None
    integrity_sha256: str
    product: str = "SWING"
    market: str = "MCX"
    availability: ContextAvailability = ContextAvailability.VALID
    authority: str = MCX_CONTEXT_AUTHORITY
    policy_state: str = MCX_CONTEXT_POLICY_STATE
    schema_identity: str = MCX_CONTEXT_CONTRACT_ID
    schema_version: str = MCX_CONTEXT_CONTRACT_VERSION

    def __post_init__(self) -> None:
        expected = panels_for(self.family)
        energy = self.family is McxContextFamily.ENERGY
        if (
            not self.record_id.startswith("MCX-CONTEXT-")
            or type(self.trading_date) is not date
            or type(self.slot) is not McxContextSlot
            or type(self.family) is not McxContextFamily
            or type(self.revision) is not int or self.revision < 1
            or not self.question_pack_identity
            or not self.answer_pack_identity
            or not _aware(self.captured_at)
            or not _aware(self.imported_at)
            or self.imported_at < self.captured_at
            or tuple(item.panel_id for item in self.panels)
            != tuple(item.panel_id for item in expected)
            or any(
                panel_validation_failure(self.family, definition, item) is not None
                for item, definition in zip(self.panels, expected, strict=True)
            )
            or energy != (self.wti_brent_alignment is not None)
            or energy != (self.natural_gas_alignment is not None)
            or self.product != "SWING" or self.market != "MCX"
            or self.availability is not ContextAvailability.VALID
            or self.authority != MCX_CONTEXT_AUTHORITY
            or self.policy_state != MCX_CONTEXT_POLICY_STATE
            or self.schema_identity != MCX_CONTEXT_CONTRACT_ID
            or self.schema_version != MCX_CONTEXT_CONTRACT_VERSION
            or _DIGEST.fullmatch(self.integrity_sha256) is None
            or self.integrity_sha256 != _record_integrity(self)
        ):
            raise ValueError("MCX_SUPPORTING_CONTEXT_RECORD_INVALID")


class McxSupportingContextStore:
    """Append-only context store with boundary-aware family selection."""

    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute():
            raise ValueError("MCX_CONTEXT_STORE_ROOT_INVALID")
        self.root = root
        self._lock = RLock()

    def retain(self, value: McxSupportingContextRecord) -> Path:
        if type(value) is not McxSupportingContextRecord:
            raise TypeError("MCX_CONTEXT_RECORD_REQUIRED")
        path = (
            self.root / value.trading_date.isoformat() / value.slot.value
            / value.family.value / f"REV{value.revision}.json"
        )
        payload = _primitive(value)
        with self._lock:
            if path.exists():
                if _read(path) != payload:
                    raise ValueError("MCX_CONTEXT_RECORD_IMMUTABLE")
                return path
            _atomic_json(path, payload)
        return path

    def records(
        self, *, trading_date: date | None = None,
        slot: McxContextSlot | None = None,
        family: McxContextFamily | None = None,
    ) -> tuple[McxSupportingContextRecord, ...]:
        if not self.root.exists():
            return ()
        values = []
        for path in sorted(self.root.glob("*/*/*/REV*.json")):
            value = _record_from_dict(_read(path))
            if (
                (trading_date is None or value.trading_date == trading_date)
                and (slot is None or value.slot is slot)
                and (family is None or value.family is family)
            ):
                values.append(value)
        return tuple(values)

    def next_revision(
        self, trading_date: date, slot: McxContextSlot, family: McxContextFamily,
    ) -> int:
        current = self.records(trading_date=trading_date, slot=slot, family=family)
        return max((item.revision for item in current), default=0) + 1

    def latest_valid(
        self, trading_date: date, family: McxContextFamily, *, boundary: datetime,
    ) -> McxSupportingContextRecord | None:
        eligible = tuple(
            value for value in self.records(trading_date=trading_date, family=family)
            if value.imported_at <= boundary
        )
        return max(
            eligible,
            key=lambda item: (item.imported_at, item.revision, item.record_id),
            default=None,
        )


def build_context_record(
    *, trading_date: date, slot: McxContextSlot, family: McxContextFamily,
    revision: int, question_pack_identity: str, answer_pack_identity: str,
    captured_at: datetime, imported_at: datetime,
    panels: tuple[McxContextPanelObservation, ...],
    wti_brent_alignment: AlignmentState | None = None,
    natural_gas_alignment: AlignmentState | None = None,
) -> McxSupportingContextRecord:
    seed = {
        "trading_date": trading_date.isoformat(), "slot": slot.value,
        "family": family.value, "revision": revision,
        "question_pack_identity": question_pack_identity,
        "answer_pack_identity": answer_pack_identity,
        "imported_at": imported_at.isoformat(),
    }
    record_id = "MCX-CONTEXT-" + sha256(_canonical(seed)).hexdigest().upper()
    payload = {
        "record_id": record_id,
        "trading_date": trading_date.isoformat(),
        "slot": slot.value,
        "family": family.value,
        "revision": revision,
        "question_pack_identity": question_pack_identity,
        "answer_pack_identity": answer_pack_identity,
        "captured_at": captured_at.isoformat(),
        "imported_at": imported_at.isoformat(),
        "panels": [
            {
                "panel_id": item.panel_id,
                "observed_identity": item.observed_identity,
                "observed_timeframe": item.observed_timeframe,
                "validation": item.validation.value,
                "direction": item.direction.value,
                "evidence_quality": item.evidence_quality.value,
                "structural_condition": item.structural_condition.value,
            }
            for item in panels
        ],
        "wti_brent_alignment": None if wti_brent_alignment is None else wti_brent_alignment.value,
        "natural_gas_alignment": None if natural_gas_alignment is None else natural_gas_alignment.value,
        "integrity_sha256": None,
        "product": "SWING", "market": "MCX",
        "availability": ContextAvailability.VALID.value,
        "authority": MCX_CONTEXT_AUTHORITY,
        "policy_state": MCX_CONTEXT_POLICY_STATE,
        "schema_identity": MCX_CONTEXT_CONTRACT_ID,
        "schema_version": MCX_CONTEXT_CONTRACT_VERSION,
    }
    integrity = sha256(_canonical(payload)).hexdigest()
    return McxSupportingContextRecord(
        record_id, trading_date, slot, family, revision,
        question_pack_identity, answer_pack_identity, captured_at, imported_at,
        panels, wti_brent_alignment, natural_gas_alignment,
        integrity,
    )


def _record_integrity(value: McxSupportingContextRecord) -> str:
    payload = _primitive(value)
    payload["integrity_sha256"] = None
    return sha256(_canonical(payload)).hexdigest()


def _record_from_dict(value: object) -> McxSupportingContextRecord:
    if type(value) is not dict:
        raise ValueError("MCX_CONTEXT_RECORD_RESTORE_INVALID")
    try:
        panels = tuple(
            McxContextPanelObservation(
                item["panel_id"], item["observed_identity"], item["observed_timeframe"],
                PanelValidation(item["validation"]), DirectionState(item["direction"]),
                EvidenceQuality(item["evidence_quality"]),
                StructuralCondition(item["structural_condition"]),
            ) for item in value["panels"]
        )
        return McxSupportingContextRecord(
            value["record_id"], date.fromisoformat(value["trading_date"]),
            McxContextSlot(value["slot"]), McxContextFamily(value["family"]),
            value["revision"], value["question_pack_identity"],
            value["answer_pack_identity"], datetime.fromisoformat(value["captured_at"]),
            datetime.fromisoformat(value["imported_at"]), panels,
            None if value["wti_brent_alignment"] is None else AlignmentState(value["wti_brent_alignment"]),
            None if value["natural_gas_alignment"] is None else AlignmentState(value["natural_gas_alignment"]),
            value["integrity_sha256"], value["product"], value["market"],
            ContextAvailability(value["availability"]), value["authority"],
            value["policy_state"], value["schema_identity"], value["schema_version"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("MCX_CONTEXT_RECORD_RESTORE_INVALID") from error


def _primitive(value: object) -> dict[str, object]:
    def convert(item: object) -> object:
        if isinstance(item, StrEnum): return item.value
        if isinstance(item, (date, datetime)): return item.isoformat()
        if isinstance(item, tuple): return [convert(part) for part in item]
        if isinstance(item, dict): return {str(k): convert(v) for k, v in item.items()}
        return item
    return convert(asdict(value))  # type: ignore[return-value]


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("MCX_CONTEXT_RECORD_READ_FAILED") from error
    if type(value) is not dict:
        raise ValueError("MCX_CONTEXT_RECORD_READ_FAILED")
    return value


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", delete=False,
        ) as stream:
            temporary = stream.name
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, 0o600); os.replace(temporary, path)
    except OSError as error:
        if temporary:
            try: os.unlink(temporary)
            except OSError: pass
        raise ValueError("MCX_CONTEXT_RECORD_WRITE_FAILED") from error


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


__all__ = [name for name in globals() if name.startswith("MCX_") or name.startswith("Mcx") or name in {
    "AlignmentState", "ContextAvailability", "DirectionState", "EvidenceQuality",
    "McxContextPanelField", "McxContextPanelValidationFailure",
    "PanelValidation", "StructuralCondition", "build_context_record",
    "canonical_mcx_context_timeframe", "panel_validation_failure", "panels_for",
}]
