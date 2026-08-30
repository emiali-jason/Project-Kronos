"""Immutable explicit-identity persistence for DOMAIN-001 visual relationships."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.instrument.visual_identity import (
    VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
    VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_MCX_REFERENCE_VERSION,
    VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_VERSION,
    VISUAL_IDENTITY_REFERENCE_ANALYTICAL_SUBJECTS,
    VisualIdentityRelationshipPublication,
    VisualIdentityResolutionError,
    VisualIdentityResolutionFailure,
    VisualIdentityResolver,
    encode_visual_identity_publication,
    parse_visual_identity_publication,
)
from kronos.instrument.semantic_v2_persistence import (
    DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT,
    InstrumentSemanticV2Store,
)


DEFAULT_VISUAL_IDENTITY_ROOT = Path(__file__).resolve().parents[3] / "data" / "instruments"
VISUAL_IDENTITY_CANONICAL_CATALOGUE_VERSION = "1.2.0"


class VisualIdentityRelationshipStore:
    """Retain immutable publications; directory order has no authority."""

    def __init__(self, root: Path = DEFAULT_VISUAL_IDENTITY_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("VISUAL_IDENTITY_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(
        self,
        publication: VisualIdentityRelationshipPublication,
        *,
        canonical_subject_identities: tuple[str, ...],
    ) -> Path:
        if type(publication) is not VisualIdentityRelationshipPublication:
            raise VisualIdentityResolutionError(
                VisualIdentityResolutionFailure.INTEGRITY_INVALID
            )
        encoded = encode_visual_identity_publication(publication)
        parse_visual_identity_publication(
            encoded,
            canonical_subject_identities=canonical_subject_identities,
        )
        target = self.path_for(
            publication_identity=publication.publication_identity,
            publication_version=publication.publication_version,
        )
        with self._lock:
            if target.exists():
                try:
                    existing = target.read_bytes()
                except OSError as error:
                    raise VisualIdentityResolutionError(
                        VisualIdentityResolutionFailure.INTEGRITY_INVALID
                    ) from error
                if existing != encoded:
                    raise VisualIdentityResolutionError(
                        VisualIdentityResolutionFailure.INTEGRITY_INVALID
                    )
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
        canonical_subject_identities: tuple[str, ...],
    ) -> VisualIdentityRelationshipPublication:
        target = self.path_for(
            publication_identity=publication_identity,
            publication_version=publication_version,
        )
        try:
            encoded = target.read_bytes()
        except OSError as error:
            raise VisualIdentityResolutionError(
                VisualIdentityResolutionFailure.RELATIONSHIP_UNAVAILABLE
            ) from error
        return parse_visual_identity_publication(
            encoded,
            canonical_subject_identities=canonical_subject_identities,
        )

    def path_for(self, *, publication_identity: str, publication_version: str) -> Path:
        if not _component(publication_identity) or not _component(publication_version):
            raise VisualIdentityResolutionError(
                VisualIdentityResolutionFailure.INTEGRITY_INVALID
            )
        return self._root / publication_identity / f"{publication_version}.json"


def load_default_visual_identity_resolver() -> VisualIdentityResolver:
    return load_visual_identity_resolver(
        publication_version=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_VERSION
    )


def load_visual_identity_resolver(
    *, publication_version: str,
) -> VisualIdentityResolver:
    canonical = InstrumentSemanticV2Store(DEFAULT_INSTRUMENT_SEMANTIC_V2_ROOT).load(
        publication_identity="KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2",
        publication_version=VISUAL_IDENTITY_CANONICAL_CATALOGUE_VERSION,
    )
    canonical_subjects = tuple(
        item.canonical_id for item in canonical.semantic_objects
    )
    if publication_version == VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_MCX_REFERENCE_VERSION:
        canonical_subjects += VISUAL_IDENTITY_REFERENCE_ANALYTICAL_SUBJECTS
    publication = VisualIdentityRelationshipStore().load(
        publication_identity=VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1,
        publication_version=publication_version,
        canonical_subject_identities=canonical_subjects,
    )
    return VisualIdentityResolver(publication)


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
    "DEFAULT_VISUAL_IDENTITY_ROOT",
    "VISUAL_IDENTITY_CANONICAL_CATALOGUE_VERSION",
    "VisualIdentityRelationshipStore",
    "load_default_visual_identity_resolver",
    "load_visual_identity_resolver",
]
