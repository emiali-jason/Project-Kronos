"""Immutable explicit-identity persistence for DOMAIN-001 V2 publications."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.instrument.semantic_v2 import (
    InstrumentSemanticPublicationV2,
    V2ResolutionError,
    V2ResolutionFailure,
    encode_semantic_publication_v2,
    parse_semantic_publication_v2,
)


DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT = (
    Path(__file__).resolve().parents[3] / "data" / "instruments"
)


class InstrumentSemanticV2Store:
    """Retain immutable versions; directory order has no resolution authority."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("INSTRUMENT_V2_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(self, publication: InstrumentSemanticPublicationV2) -> Path:
        if type(publication) is not InstrumentSemanticPublicationV2:
            raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)
        encoded = encode_semantic_publication_v2(publication)
        target = self.path_for(
            publication_identity=publication.publication_identity,
            publication_version=publication.publication_version,
        )
        with self._lock:
            if target.exists():
                try:
                    existing = target.read_bytes()
                except OSError as error:
                    raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID) from error
                if existing != encoded:
                    raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)
                return target
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
            try:
                temporary.write_bytes(encoded)
                temporary.replace(target)
            finally:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
            return target

    def load(
        self,
        *,
        publication_identity: str,
        publication_version: str,
    ) -> InstrumentSemanticPublicationV2:
        target = self.path_for(
            publication_identity=publication_identity,
            publication_version=publication_version,
        )
        try:
            encoded = target.read_bytes()
        except OSError as error:
            raise V2ResolutionError(V2ResolutionFailure.CANONICAL_SUBJECT_UNAVAILABLE) from error
        return parse_semantic_publication_v2(encoded)

    def path_for(self, *, publication_identity: str, publication_version: str) -> Path:
        if not _component(publication_identity) or not _component(publication_version):
            raise V2ResolutionError(V2ResolutionFailure.INTEGRITY_INVALID)
        return self._root / publication_identity / f"{publication_version}.json"


def _component(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
        and value == value.strip()
    )


__all__ = [
    "DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT",
    "InstrumentSemanticV2Store",
]
