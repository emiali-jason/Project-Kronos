"""Immutable explicit-identity persistence for WO-06S semantic evidence."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.historical_semantic import (
    GovernedHistoricalCandlePayload,
    SemanticEvidenceError,
    SemanticQualificationEvidence,
    semantic_artifact_bytes,
    semantic_artifact_document,
    semantic_artifact_from_bytes,
    verify_semantic_artifact_document,
)


DEFAULT_HISTORICAL_SEMANTIC_ROOT = (
    Path(__file__).resolve().parents[3] / "data" / "intraday"
)


class HistoricalSemanticStore:
    """Append-only semantic evidence store with no latest-file authority."""

    def __init__(self, root: Path = DEFAULT_HISTORICAL_SEMANTIC_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("HISTORICAL_SEMANTIC_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(self, value: object) -> Path:
        document = semantic_artifact_document(value)
        path = self.path(
            artifact_type=str(document["artifact_type"]),
            artifact_identity=str(document["artifact_identity"]),
        )
        encoded = semantic_artifact_bytes(value)
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
            raise SemanticEvidenceError("SEMANTIC_ARTIFACT_UNAVAILABLE") from error
        value = semantic_artifact_from_bytes(encoded)
        document = semantic_artifact_document(value)
        if (
            document["artifact_type"] != artifact_type
            or document["artifact_identity"] != artifact_identity
        ):
            raise SemanticEvidenceError("SEMANTIC_DOCUMENT_INTEGRITY_INVALID")
        return value

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
            raise SemanticEvidenceError("SEMANTIC_ARTIFACT_UNAVAILABLE") from error
        if not isinstance(document, dict):
            raise SemanticEvidenceError("SEMANTIC_DOCUMENT_INVALID")
        verify_semantic_artifact_document(document)
        if (
            document.get("artifact_type") != artifact_type
            or document.get("artifact_identity") != artifact_identity
        ):
            raise SemanticEvidenceError("SEMANTIC_DOCUMENT_INTEGRITY_INVALID")
        return document

    def identities_for_operation(
        self, *, artifact_type: str, operation_identity: str
    ) -> tuple[str, ...]:
        """Return an explicit operation-bound set; filesystem order has no authority."""

        if not _component(artifact_type) or not _component(operation_identity):
            raise SemanticEvidenceError("SEMANTIC_QUERY_INVALID")
        directory = self._root / "historical-semantic" / artifact_type
        if not directory.exists():
            return ()
        identities = []
        for path in directory.glob("*.json"):
            try:
                document = json.loads(path.read_bytes())
            except (OSError, ValueError) as error:
                raise SemanticEvidenceError("SEMANTIC_DOCUMENT_INVALID") from error
            verify_semantic_artifact_document(document)
            artifact = document.get("artifact")
            if (
                isinstance(artifact, dict)
                and artifact.get("source_operation_identity") == operation_identity
            ):
                identities.append(str(document["artifact_identity"]))
        return tuple(sorted(identities))

    def path(self, *, artifact_type: str, artifact_identity: str) -> Path:
        if not _component(artifact_type) or not _component(artifact_identity):
            raise SemanticEvidenceError("SEMANTIC_PATH_INVALID")
        return (
            self._root
            / "historical-semantic"
            / artifact_type
            / f"{artifact_identity}.json"
        )

    @staticmethod
    def _retain(path: Path, encoded: bytes) -> None:
        if path.exists():
            try:
                current = path.read_bytes()
            except OSError as error:
                raise SemanticEvidenceError("SEMANTIC_ARTIFACT_UNAVAILABLE") from error
            if current != encoded:
                raise SemanticEvidenceError("SEMANTIC_PERSISTENCE_CONFLICT")
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


__all__ = [
    "DEFAULT_HISTORICAL_SEMANTIC_ROOT",
    "HistoricalSemanticStore",
]
