"""Version-isolated immutable persistence for Intraday Probables V2."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock
from typing import Mapping
from uuid import uuid4

from kronos.intraday.completed_evidence import (
    EvidenceSessionRole,
    IntradayAnalysisPhase,
    PhaseAwareCompletedEvidenceSelection,
    SelectedCompletedCandle,
)
from kronos.intraday.historical_semantic import (
    GovernedHistoricalCandlePayload,
    SemanticDirection,
)
from kronos.intraday.nifty_relative_context import (
    NiftyApplicability,
    NiftyFailure,
    NiftyRelationship,
    NiftyRelativeContextEvidence,
    NiftyRelativeContextFact,
    NiftyRelativeState,
    RelativeProgressionState,
)
from kronos.intraday.opening_semantic import (
    OpeningRelationship,
    OpeningSemanticEvidence,
    OpeningSemanticFact,
)
from kronos.intraday.probables import FactualSourceKind, PopulationBucket, ProbableState
from kronos.intraday.probables_v2 import (
    DiscoveryProbablesEvidenceV2,
    ProbableMemberResultV2,
    ProbableReasonV2,
    ProbablesMethodologyV2,
    ProbablesPopulationDiagnosticsV2,
    ProbablesRunV2,
    ProbablesV2Error,
    SemanticEvidenceRoleV2,
    SemanticQualificationEvidenceV2,
    SemanticQualificationFactV2,
)
from kronos.intraday.contracts import IntradayTimeframe


DEFAULT_PROBABLES_V2_ROOT = Path(__file__).resolve().parents[3] / "data" / "intraday"
CURRENT_POINTER_IDENTITY = "KRONOS-INTRADAY-CURRENT-PROBABLES-POINTER-V2"
CURRENT_POINTER_VERSION = "2.0.0"


@dataclass(frozen=True, slots=True)
class CurrentProbablesV2Pointer:
    run_identity: str
    source_discovery_run_identity: str
    analysis_boundary: datetime
    methodology_publication_identity: str
    integrity_identity: str
    schema_identity: str = CURRENT_POINTER_IDENTITY
    schema_version: str = CURRENT_POINTER_VERSION

    def __post_init__(self) -> None:
        core = {
            "run_identity": self.run_identity,
            "source_discovery_run_identity": self.source_discovery_run_identity,
            "analysis_boundary": self.analysis_boundary,
            "methodology_publication_identity": self.methodology_publication_identity,
            "schema_identity": self.schema_identity,
            "schema_version": self.schema_version,
        }
        if (
            not _component(self.run_identity)
            or not self.run_identity.startswith("INTRADAY-PROBABLES-V2-RUN-")
            or not _component(self.source_discovery_run_identity)
            or not _aware(self.analysis_boundary)
            or not _component(self.methodology_publication_identity)
            or self.schema_identity != CURRENT_POINTER_IDENTITY
            or self.schema_version != CURRENT_POINTER_VERSION
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-PROBABLES-V2-POINTER-", core)
        ):
            raise ProbablesV2Error("PROBABLES_V2_POINTER_INVALID")


def create_current_probables_v2_pointer(run: ProbablesRunV2) -> CurrentProbablesV2Pointer:
    if type(run) is not ProbablesRunV2:
        raise ProbablesV2Error("PROBABLES_V2_POINTER_INPUT_INVALID")
    core = {
        "run_identity": run.run_identity,
        "source_discovery_run_identity": run.source_discovery_run_identity,
        "analysis_boundary": run.analysis_boundary,
        "methodology_publication_identity": run.methodology.publication_identity,
        "schema_identity": CURRENT_POINTER_IDENTITY,
        "schema_version": CURRENT_POINTER_VERSION,
    }
    return CurrentProbablesV2Pointer(
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-PROBABLES-V2-POINTER-", core
        ),
        **core,
    )


class ProbablesV2Store:
    """Append-only V2 artifacts plus one integrity-bound explicit pointer."""

    def __init__(self, root: Path = DEFAULT_PROBABLES_V2_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_PROBABLES_V2_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_methodology(self, value: ProbablesMethodologyV2) -> Path:
        return self._retain_typed("methodologies", value.publication_identity, value)

    def retain_selection(self, value: PhaseAwareCompletedEvidenceSelection) -> Path:
        return self._retain_typed("completed-evidence", value.selection_identity, value)

    def retain_nifty(self, value: NiftyRelativeContextEvidence) -> Path:
        return self._retain_typed("nifty-relative", value.evidence_identity, value)

    def retain_opening(self, value: OpeningSemanticEvidence) -> Path:
        return self._retain_typed("opening-semantic", value.evidence_identity, value)

    def retain_semantic(self, value: SemanticQualificationEvidenceV2) -> Path:
        return self._retain_typed("semantic", value.evidence_identity, value)

    def retain_mapping(self, value: DiscoveryProbablesEvidenceV2) -> Path:
        return self._retain_typed("mappings", value.mapping_identity, value)

    def retain_result(self, value: ProbableMemberResultV2) -> Path:
        return self._retain_typed("results", value.result_identity, value)

    def retain_diagnostics(self, value: ProbablesPopulationDiagnosticsV2) -> Path:
        return self._retain_typed("diagnostics", value.diagnostics_identity, value)

    def retain_run(self, value: ProbablesRunV2) -> Path:
        return self._retain_typed("runs", value.run_identity, value)

    def retain_complete(
        self,
        *,
        run: ProbablesRunV2,
        mappings: tuple[DiscoveryProbablesEvidenceV2, ...],
    ) -> Path:
        if (
            type(run) is not ProbablesRunV2
            or any(type(item) is not DiscoveryProbablesEvidenceV2 for item in mappings)
            or {item.universe_member_identity for item in mappings}
            - {item.universe_member_identity for item in run.results}
        ):
            raise ProbablesV2Error("PROBABLES_V2_PERSISTENCE_INPUT_INVALID")
        with self._lock:
            self.retain_methodology(run.methodology)
            for item in mappings:
                self.retain_selection(item.completed_evidence)
                if item.nifty_relative is not None:
                    self.retain_nifty(item.nifty_relative)
                if item.opening_semantic is not None:
                    self.retain_opening(item.opening_semantic)
                self.retain_semantic(item.semantic_evidence)
                self.retain_mapping(item)
            for item in run.results:
                self.retain_result(item)
            self.retain_diagnostics(run.diagnostics)
            path = self.retain_run(run)
            self.save_current(create_current_probables_v2_pointer(run))
        return path

    def load_methodology(self, identity: str) -> ProbablesMethodologyV2:
        return self._load_typed("methodologies", identity, ProbablesMethodologyV2, "publication_identity")

    def load_selection(self, identity: str) -> PhaseAwareCompletedEvidenceSelection:
        return self._load_typed("completed-evidence", identity, PhaseAwareCompletedEvidenceSelection, "selection_identity")

    def load_nifty(self, identity: str) -> NiftyRelativeContextEvidence:
        return self._load_typed("nifty-relative", identity, NiftyRelativeContextEvidence, "evidence_identity")

    def load_opening(self, identity: str) -> OpeningSemanticEvidence:
        return self._load_typed("opening-semantic", identity, OpeningSemanticEvidence, "evidence_identity")

    def load_semantic(self, identity: str) -> SemanticQualificationEvidenceV2:
        return self._load_typed("semantic", identity, SemanticQualificationEvidenceV2, "evidence_identity")

    def load_mapping(self, identity: str) -> DiscoveryProbablesEvidenceV2:
        return self._load_typed("mappings", identity, DiscoveryProbablesEvidenceV2, "mapping_identity")

    def load_result(self, identity: str) -> ProbableMemberResultV2:
        return self._load_typed("results", identity, ProbableMemberResultV2, "result_identity")

    def load_diagnostics(self, identity: str) -> ProbablesPopulationDiagnosticsV2:
        return self._load_typed("diagnostics", identity, ProbablesPopulationDiagnosticsV2, "diagnostics_identity")

    def load_run(self, identity: str) -> ProbablesRunV2:
        return self._load_typed("runs", identity, ProbablesRunV2, "run_identity")

    def save_current(self, value: CurrentProbablesV2Pointer) -> Path:
        if type(value) is not CurrentProbablesV2Pointer:
            raise ProbablesV2Error("PROBABLES_V2_POINTER_INVALID")
        path = self._root / "refresh-v2" / "CURRENT-PROBABLES-V2.json"
        with self._lock:
            _replace_atomic(path, _artifact_bytes(value))
        return path

    def load_current(self) -> CurrentProbablesV2Pointer | None:
        path = self._root / "refresh-v2" / "CURRENT-PROBABLES-V2.json"
        if not path.exists():
            return None
        value = _artifact_from_bytes(_read(path))
        if type(value) is not CurrentProbablesV2Pointer:
            raise ProbablesV2Error("PROBABLES_V2_POINTER_INVALID")
        run = self.load_run(value.run_identity)
        if (
            run.source_discovery_run_identity != value.source_discovery_run_identity
            or run.analysis_boundary != value.analysis_boundary
            or run.methodology.publication_identity
            != value.methodology_publication_identity
        ):
            raise ProbablesV2Error("PROBABLES_V2_POINTER_BINDING_INVALID")
        return value

    def load_current_run(self) -> ProbablesRunV2 | None:
        pointer = self.load_current()
        if pointer is None:
            return None
        run = self.load_run(pointer.run_identity)
        self._verify_run_lineage(run)
        return run

    def _verify_run_lineage(self, run: ProbablesRunV2) -> None:
        if (
            self.load_methodology(run.methodology.publication_identity)
            != run.methodology
            or self.load_diagnostics(run.diagnostics.diagnostics_identity)
            != run.diagnostics
        ):
            raise ProbablesV2Error("PROBABLES_V2_RESTART_LINEAGE_INVALID")
        for result in run.results:
            if self.load_result(result.result_identity) != result:
                raise ProbablesV2Error("PROBABLES_V2_RESTART_LINEAGE_INVALID")
            if result.source_mapping_identity is None:
                continue
            mapping = self.load_mapping(result.source_mapping_identity)
            if (
                mapping.universe_member_identity != result.universe_member_identity
                or mapping.canonical_subject_identity
                != result.canonical_subject_identity
                or mapping.source_discovery_run_identity
                != result.source_discovery_run_identity
                or mapping.source_discovery_member_identity
                != result.source_discovery_member_identity
                or mapping.analysis_boundary != result.analysis_boundary
                or mapping.phase is not result.phase
                or mapping.completed_evidence.selection_identity
                != result.completed_evidence_selection_identity
                or mapping.semantic_evidence.evidence_identity
                != result.semantic_evidence_identity
            ):
                raise ProbablesV2Error("PROBABLES_V2_RESTART_LINEAGE_INVALID")
            if self.load_selection(
                mapping.completed_evidence.selection_identity
            ) != mapping.completed_evidence or self.load_semantic(
                mapping.semantic_evidence.evidence_identity
            ) != mapping.semantic_evidence:
                raise ProbablesV2Error("PROBABLES_V2_RESTART_LINEAGE_INVALID")
            if mapping.opening_semantic is not None and self.load_opening(
                mapping.opening_semantic.evidence_identity
            ) != mapping.opening_semantic:
                raise ProbablesV2Error("PROBABLES_V2_RESTART_LINEAGE_INVALID")
            if mapping.nifty_relative is not None and self.load_nifty(
                mapping.nifty_relative.evidence_identity
            ) != mapping.nifty_relative:
                raise ProbablesV2Error("PROBABLES_V2_RESTART_LINEAGE_INVALID")

    def _retain_typed(self, family: str, identity: str, value: object) -> Path:
        path = self._path(family, identity)
        encoded = _artifact_bytes(value)
        with self._lock:
            _retain_immutable(path, encoded)
        return path

    def _load_typed(self, family: str, identity: str, expected: type, identity_name: str):  # type: ignore[no-untyped-def]
        value = _artifact_from_bytes(_read(self._path(family, identity)))
        if type(value) is not expected or getattr(value, identity_name, None) != identity:
            raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_INTEGRITY_INVALID")
        return value

    def _path(self, family: str, identity: str) -> Path:
        if not _component(family) or not _component(identity):
            raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_PATH_INVALID")
        namespaces = {
            "methodologies": ("probables-v2", "methodologies"),
            "completed-evidence": ("completed-evidence-v1", "selections"),
            "nifty-relative": ("nifty-relative-v1", "evidence"),
            "opening-semantic": ("opening-semantic-v1", "evidence"),
            "semantic": ("semantic-v2", "evidence"),
            "mappings": ("probables-v2", "mappings"),
            "results": ("probables-v2", "results"),
            "diagnostics": ("probables-v2", "diagnostics"),
            "runs": ("probables-v2", "runs"),
        }
        namespace = namespaces.get(family)
        if namespace is None:
            raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_PATH_INVALID")
        return self._root.joinpath(*namespace, f"{identity}.json")


_DATACLASSES = {
    item.__name__: item
    for item in (
        GovernedHistoricalCandlePayload,
        SelectedCompletedCandle,
        PhaseAwareCompletedEvidenceSelection,
        NiftyRelativeContextFact,
        NiftyRelativeContextEvidence,
        OpeningSemanticFact,
        OpeningSemanticEvidence,
        ProbablesMethodologyV2,
        SemanticQualificationFactV2,
        SemanticQualificationEvidenceV2,
        DiscoveryProbablesEvidenceV2,
        ProbableMemberResultV2,
        ProbablesPopulationDiagnosticsV2,
        ProbablesRunV2,
        CurrentProbablesV2Pointer,
    )
}

_ENUMS = {
    item.__name__: item
    for item in (
        IntradayTimeframe,
        EvidenceSessionRole,
        IntradayAnalysisPhase,
        SemanticDirection,
        NiftyApplicability,
        NiftyFailure,
        NiftyRelationship,
        NiftyRelativeState,
        RelativeProgressionState,
        OpeningRelationship,
        SemanticEvidenceRoleV2,
        ProbableReasonV2,
        FactualSourceKind,
        PopulationBucket,
        ProbableState,
    )
}


def _artifact_bytes(value: object) -> bytes:
    artifact_identity = _artifact_identity(value)
    core = {
        "artifact_type": type(value).__name__,
        "artifact_identity": artifact_identity,
        "artifact": _to_wire(value),
    }
    document = {
        **core,
        "document_integrity": _identity(
            "INTEGRITY-INTRADAY-PROBABLES-V2-DOCUMENT-", core
        ),
    }
    return _encode(document) + b"\n"


def _artifact_from_bytes(encoded: bytes) -> object:
    try:
        document = json.loads(encoded)
    except (TypeError, ValueError) as error:
        raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_INVALID") from error
    if not isinstance(document, Mapping):
        raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_INVALID")
    core = {
        "artifact_type": document.get("artifact_type"),
        "artifact_identity": document.get("artifact_identity"),
        "artifact": document.get("artifact"),
    }
    if document.get("document_integrity") != _identity(
        "INTEGRITY-INTRADAY-PROBABLES-V2-DOCUMENT-", core
    ):
        raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_INTEGRITY_INVALID")
    value = _from_wire(core["artifact"])
    if (
        type(value).__name__ != core["artifact_type"]
        or _artifact_identity(value) != core["artifact_identity"]
    ):
        raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_INTEGRITY_INVALID")
    return value


def _artifact_identity(value: object) -> str:
    for name in (
        "publication_identity",
        "selection_identity",
        "evidence_identity",
        "mapping_identity",
        "result_identity",
        "diagnostics_identity",
        "run_identity",
    ):
        identity = getattr(value, name, None)
        if _component(identity):
            return identity
    if type(value) is CurrentProbablesV2Pointer:
        return CURRENT_POINTER_IDENTITY
    raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_TYPE_INVALID")


def _to_wire(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "$type": type(value).__name__,
            "fields": {field.name: _to_wire(getattr(value, field.name)) for field in fields(value)},
        }
    if isinstance(value, StrEnum):
        return {"$enum": type(value).__name__, "value": value.value}
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, tuple):
        return {"$tuple": [_to_wire(item) for item in value]}
    if isinstance(value, list):
        return {"$list": [_to_wire(item) for item in value]}
    if isinstance(value, Mapping):
        return {"$mapping": [[str(key), _to_wire(item)] for key, item in sorted(value.items())]}
    if value is None or type(value) in {str, int, bool}:
        return value
    raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_VALUE_INVALID")


def _from_wire(value: object) -> object:
    if value is None or type(value) in {str, int, bool}:
        return value
    if not isinstance(value, Mapping):
        raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_VALUE_INVALID")
    if set(value) == {"$datetime"}:
        return datetime.fromisoformat(str(value["$datetime"]))
    if set(value) == {"$decimal"}:
        return Decimal(str(value["$decimal"]))
    if set(value) == {"$tuple"} and isinstance(value["$tuple"], list):
        return tuple(_from_wire(item) for item in value["$tuple"])
    if set(value) == {"$list"} and isinstance(value["$list"], list):
        return [_from_wire(item) for item in value["$list"]]
    if set(value) == {"$mapping"} and isinstance(value["$mapping"], list):
        result: dict[str, object] = {}
        for pair in value["$mapping"]:
            if not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[0], str):
                raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_VALUE_INVALID")
            result[pair[0]] = _from_wire(pair[1])
        return result
    if set(value) == {"$enum", "value"}:
        enum_type = _ENUMS.get(str(value["$enum"]))
        if enum_type is None:
            raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_VALUE_INVALID")
        return enum_type(value["value"])
    if set(value) == {"$type", "fields"} and isinstance(value["fields"], Mapping):
        cls = _DATACLASSES.get(str(value["$type"]))
        if cls is None:
            raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_VALUE_INVALID")
        expected = {field.name for field in fields(cls)}
        if set(value["fields"]) != expected:
            raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_VALUE_INVALID")
        return cls(**{name: _from_wire(item) for name, item in value["fields"].items()})
    raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_VALUE_INVALID")


def _retain_immutable(path: Path, encoded: bytes) -> None:
    if path.exists():
        if _read(path) != encoded:
            raise ProbablesV2Error("PROBABLES_V2_PERSISTENCE_CONFLICT")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(encoded)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _replace_atomic(path: Path, encoded: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(encoded)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise ProbablesV2Error("PROBABLES_V2_ARTIFACT_UNAVAILABLE") from error


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_encode(value)).hexdigest().upper()


def _encode(value: object) -> bytes:
    return json.dumps(_json_normalize(value), sort_keys=True, separators=(",", ":")).encode("utf-8")


def _json_normalize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_normalize(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_normalize(item) for item in value]
    return value


def _component(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value == value.strip()
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
    )


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "CURRENT_POINTER_IDENTITY",
    "CURRENT_POINTER_VERSION",
    "DEFAULT_PROBABLES_V2_ROOT",
    "CurrentProbablesV2Pointer",
    "ProbablesV2Store",
    "create_current_probables_v2_pointer",
]
