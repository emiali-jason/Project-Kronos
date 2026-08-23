"""Immutable explicit-identity persistence for WO-06 Part-2 research."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.qualification import (
    QualificationError,
    QualificationFailure,
)
from kronos.intraday.qualification_research import (
    research_artifact_bytes,
    research_artifact_document,
    verify_research_artifact_document,
)


DEFAULT_RESEARCH_ROOT = Path(__file__).resolve().parents[3] / "data" / "intraday"


class QualificationResearchStore:
    """Retain Part-2 artifacts by exact identity; no latest lookup exists."""

    def __init__(self, root: Path = DEFAULT_RESEARCH_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("QUALIFICATION_RESEARCH_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(self, value: object) -> Path:
        document = research_artifact_document(value)
        path = self.path(
            artifact_type=str(document["artifact_type"]),
            artifact_identity=str(document["artifact_identity"]),
        )
        encoded = research_artifact_bytes(value)
        with self._lock:
            self._retain(path, encoded)
        return path

    def load_document(
        self, *, artifact_type: str, artifact_identity: str
    ) -> dict[str, object]:
        path = self.path(
            artifact_type=artifact_type,
            artifact_identity=artifact_identity,
        )
        try:
            document = json.loads(path.read_bytes())
        except (OSError, ValueError) as error:
            raise QualificationError(QualificationFailure.ARTIFACT_UNAVAILABLE) from error
        if not isinstance(document, dict):
            raise QualificationError(QualificationFailure.INTEGRITY_INVALID)
        verify_research_artifact_document(document)
        if (
            document.get("artifact_type") != artifact_type
            or document.get("artifact_identity") != artifact_identity
        ):
            raise QualificationError(QualificationFailure.INTEGRITY_INVALID)
        return document

    def path(self, *, artifact_type: str, artifact_identity: str) -> Path:
        if not _component(artifact_type) or not _component(artifact_identity):
            raise QualificationError(QualificationFailure.INPUT_INVALID)
        return (
            self._root
            / "qualification-research"
            / artifact_type
            / f"{artifact_identity}.json"
        )

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


__all__ = ["DEFAULT_RESEARCH_ROOT", "QualificationResearchStore"]
