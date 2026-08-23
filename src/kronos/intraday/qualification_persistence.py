"""Immutable explicit-identity retention for WO-06 qualification artifacts."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.qualification import (
    QualificationError,
    QualificationFailure,
    qualification_artifact_bytes,
    qualification_artifact_from_bytes,
    qualification_artifact_document,
)


DEFAULT_QUALIFICATION_ROOT = Path(__file__).resolve().parents[3] / "data" / "intraday"


class QualificationStore:
    """Retain artifacts by exact deterministic identity; no latest lookup exists."""

    def __init__(self, root: Path = DEFAULT_QUALIFICATION_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("QUALIFICATION_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(self, value: object) -> Path:
        artifact_type, identity = self._coordinates(value)
        path = self.path(artifact_type=artifact_type, artifact_identity=identity)
        encoded = qualification_artifact_bytes(value)
        with self._lock:
            self._retain(path, encoded)
        return path

    def load(self, *, artifact_type: str, artifact_identity: str) -> object:
        path = self.path(
            artifact_type=artifact_type,
            artifact_identity=artifact_identity,
        )
        try:
            encoded = path.read_bytes()
        except OSError as error:
            raise QualificationError(QualificationFailure.ARTIFACT_UNAVAILABLE) from error
        value = qualification_artifact_from_bytes(encoded)
        actual_type, actual_identity = self._coordinates(value)
        if actual_type != artifact_type or actual_identity != artifact_identity:
            raise QualificationError(QualificationFailure.INTEGRITY_INVALID)
        return value

    def path(self, *, artifact_type: str, artifact_identity: str) -> Path:
        if not _component(artifact_type) or not _component(artifact_identity):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        return self._root / "qualification" / artifact_type / f"{artifact_identity}.json"

    @staticmethod
    def _coordinates(value: object) -> tuple[str, str]:
        document = qualification_artifact_document(value)
        artifact_type = document["artifact_type"]
        artifact = document["artifact"]
        identity_names = {
            "NarrowCprFact": "fact_identity",
            "QualificationHypothesis": "hypothesis_identity",
            "FactualOutcomeDefinition": "definition_identity",
            "FactualOutcomeRecord": "outcome_identity",
            "QualificationObservation": "observation_identity",
            "PopulationDiagnostics": "diagnostics_identity",
            "QualificationCorpus": "corpus_identity",
            "QualificationReport": "report_identity",
        }
        identity = artifact[identity_names[artifact_type]]
        return artifact_type, identity

    @staticmethod
    def _retain(path: Path, encoded: bytes) -> None:
        if path.exists():
            try:
                current = path.read_bytes()
            except OSError as error:
                raise QualificationError(QualificationFailure.ARTIFACT_UNAVAILABLE) from error
            if current != encoded:
                raise QualificationError(QualificationFailure.PERSISTENCE_CONFLICT)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(encoded)
            temporary.replace(path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _component(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value == value.strip()
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
    )


__all__ = ["DEFAULT_QUALIFICATION_ROOT", "QualificationStore"]
