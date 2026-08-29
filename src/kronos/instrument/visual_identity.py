"""DOMAIN-001 governed visual-label relationship contracts and resolution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Iterable, Mapping


GOVERNED_VISUAL_IDENTITY_RELATIONSHIP_V1 = (
    "GOVERNED_VISUAL_IDENTITY_RELATIONSHIP_V1"
)
GOVERNED_VISUAL_IDENTITY_RELATIONSHIP_V1_VERSION = "1.0.0"
VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1 = (
    "KRONOS-GOVERNED-VISUAL-IDENTITY-RELATIONSHIP-PUBLICATION-V1"
)
VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_VERSION = "1.0.0"
VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_SUCCESSOR_VERSION = "1.1.0"
VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_SUPPORTED_VERSIONS = frozenset({
    VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_VERSION,
    VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_SUCCESSOR_VERSION,
})


class VisualIdentitySourceContext(StrEnum):
    TRADINGVIEW_VISUAL_CHART = "TRADINGVIEW_VISUAL_CHART"


class VisualIdentityRelationshipStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class VisualIdentityResolutionFailure(StrEnum):
    RELATIONSHIP_UNAVAILABLE = "VISUAL_IDENTITY_RELATIONSHIP_UNAVAILABLE"
    RELATIONSHIP_AMBIGUOUS = "VISUAL_IDENTITY_RELATIONSHIP_AMBIGUOUS"
    PUBLICATION_STALE = "VISUAL_IDENTITY_PUBLICATION_STALE"
    INTEGRITY_INVALID = "VISUAL_IDENTITY_INTEGRITY_INVALID"


class VisualIdentityResolutionError(RuntimeError):
    def __init__(self, failure: VisualIdentityResolutionFailure) -> None:
        self.failure = failure
        super().__init__(failure.value)


@dataclass(frozen=True, slots=True)
class GovernedVisualIdentityRelationship:
    relationship_identity: str
    canonical_subject_identity: str
    observed_visible_subject_identity: str
    source_context: VisualIdentitySourceContext
    effective_from: datetime
    effective_through: datetime
    status: VisualIdentityRelationshipStatus
    publication_identity: str
    source_identity: str
    provenance: tuple[str, ...]
    supersedes: str | None
    integrity_identity: str
    contract_identity: str = GOVERNED_VISUAL_IDENTITY_RELATIONSHIP_V1
    contract_version: str = GOVERNED_VISUAL_IDENTITY_RELATIONSHIP_V1_VERSION

    def __post_init__(self) -> None:
        fields = _without(self, "relationship_identity", "integrity_identity")
        if (
            self.contract_identity != GOVERNED_VISUAL_IDENTITY_RELATIONSHIP_V1
            or self.contract_version != GOVERNED_VISUAL_IDENTITY_RELATIONSHIP_V1_VERSION
            or self.publication_identity != VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1
            or not _text(self.canonical_subject_identity)
            or not _text_exact(self.observed_visible_subject_identity)
            or type(self.source_context) is not VisualIdentitySourceContext
            or type(self.status) is not VisualIdentityRelationshipStatus
            or not _interval(self.effective_from, self.effective_through)
            or not _text(self.source_identity)
            or not _texts(self.provenance)
            or (self.supersedes is not None and not _text(self.supersedes))
            or self.relationship_identity
            != _identity("VISUAL-IDENTITY-RELATIONSHIP-", fields)
            or self.integrity_identity
            != _identity("INTEGRITY-VISUAL-IDENTITY-RELATIONSHIP-", fields)
        ):
            raise VisualIdentityResolutionError(
                VisualIdentityResolutionFailure.INTEGRITY_INVALID
            )

    def active_at(self, observed_at: datetime) -> bool:
        return (
            self.status is VisualIdentityRelationshipStatus.ACTIVE
            and _aware(observed_at)
            and self.effective_from <= observed_at <= self.effective_through
        )


def create_visual_identity_relationship(
    **fields: object,
) -> GovernedVisualIdentityRelationship:
    values = dict(fields)
    values.setdefault("contract_identity", GOVERNED_VISUAL_IDENTITY_RELATIONSHIP_V1)
    values.setdefault(
        "contract_version", GOVERNED_VISUAL_IDENTITY_RELATIONSHIP_V1_VERSION
    )
    values.setdefault("publication_identity", VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1)
    identity_fields = dict(values)
    return GovernedVisualIdentityRelationship(
        relationship_identity=_identity(
            "VISUAL-IDENTITY-RELATIONSHIP-", identity_fields
        ),
        integrity_identity=_identity(
            "INTEGRITY-VISUAL-IDENTITY-RELATIONSHIP-", identity_fields
        ),
        **values,  # type: ignore[arg-type]
    )


@dataclass(frozen=True, slots=True)
class VisualIdentityRelationshipPublication:
    publication_identity: str
    publication_version: str
    effective_from: datetime
    effective_through: datetime
    source_identities: tuple[str, ...]
    provenance: tuple[str, ...]
    relationships: tuple[GovernedVisualIdentityRelationship, ...]
    supersedes: str | None
    integrity_identity: str
    schema_identity: str = VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1

    def __post_init__(self) -> None:
        relationship_ids = tuple(
            relationship.relationship_identity for relationship in self.relationships
        )
        if (
            self.schema_identity != VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1
            or self.publication_identity != VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1
            or self.publication_version
            not in VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_SUPPORTED_VERSIONS
            or not _interval(self.effective_from, self.effective_through)
            or not _texts(self.source_identities)
            or not _texts(self.provenance)
            or not self.relationships
            or any(
                type(item) is not GovernedVisualIdentityRelationship
                or item.publication_identity != self.publication_identity
                for item in self.relationships
            )
            or len(relationship_ids) != len(set(relationship_ids))
            or _conflicting_overlaps(self.relationships)
            or (self.supersedes is not None and not _text(self.supersedes))
            or self.integrity_identity
            != _identity(
                "INTEGRITY-VISUAL-IDENTITY-PUBLICATION-",
                _without(self, "integrity_identity"),
            )
        ):
            raise VisualIdentityResolutionError(
                VisualIdentityResolutionFailure.INTEGRITY_INVALID
            )

    def require_current(self, observed_at: datetime) -> None:
        if (
            not _aware(observed_at)
            or not self.effective_from <= observed_at <= self.effective_through
        ):
            raise VisualIdentityResolutionError(
                VisualIdentityResolutionFailure.PUBLICATION_STALE
            )


def create_visual_identity_publication(
    *,
    canonical_subject_identities: Iterable[str],
    **fields: object,
) -> VisualIdentityRelationshipPublication:
    values = dict(fields)
    values.setdefault("schema_identity", VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1)
    values.setdefault("publication_identity", VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1)
    publication = VisualIdentityRelationshipPublication(
        **values,  # type: ignore[arg-type]
        integrity_identity=_identity(
            "INTEGRITY-VISUAL-IDENTITY-PUBLICATION-", values
        ),
    )
    _require_canonical_subjects(publication, canonical_subject_identities)
    return publication


@dataclass(frozen=True, slots=True)
class VisualIdentityResolution:
    canonical_subject_identity: str
    observed_visible_subject_identity: str
    source_context: VisualIdentitySourceContext
    governed_observation_boundary: datetime
    relationship_identity: str
    relationship_integrity_identity: str
    publication_identity: str
    publication_version: str
    publication_integrity_identity: str


class VisualIdentityResolver:
    def __init__(self, publication: VisualIdentityRelationshipPublication) -> None:
        if type(publication) is not VisualIdentityRelationshipPublication:
            raise VisualIdentityResolutionError(
                VisualIdentityResolutionFailure.INTEGRITY_INVALID
            )
        self._publication = publication

    @property
    def publication(self) -> VisualIdentityRelationshipPublication:
        return self._publication

    def resolve(
        self,
        *,
        observed_visible_subject_identity: str,
        source_context: VisualIdentitySourceContext,
        governed_observation_boundary: datetime,
    ) -> VisualIdentityResolution:
        if (
            not _text_exact(observed_visible_subject_identity)
            or type(source_context) is not VisualIdentitySourceContext
            or not _aware(governed_observation_boundary)
        ):
            raise VisualIdentityResolutionError(
                VisualIdentityResolutionFailure.RELATIONSHIP_UNAVAILABLE
            )
        self._publication.require_current(governed_observation_boundary)
        matches = tuple(
            relationship
            for relationship in self._publication.relationships
            if relationship.observed_visible_subject_identity
            == observed_visible_subject_identity
            and relationship.source_context is source_context
            and relationship.active_at(governed_observation_boundary)
        )
        if not matches:
            raise VisualIdentityResolutionError(
                VisualIdentityResolutionFailure.RELATIONSHIP_UNAVAILABLE
            )
        if len(matches) != 1:
            raise VisualIdentityResolutionError(
                VisualIdentityResolutionFailure.RELATIONSHIP_AMBIGUOUS
            )
        relationship = matches[0]
        return VisualIdentityResolution(
            canonical_subject_identity=relationship.canonical_subject_identity,
            observed_visible_subject_identity=observed_visible_subject_identity,
            source_context=source_context,
            governed_observation_boundary=governed_observation_boundary,
            relationship_identity=relationship.relationship_identity,
            relationship_integrity_identity=relationship.integrity_identity,
            publication_identity=self._publication.publication_identity,
            publication_version=self._publication.publication_version,
            publication_integrity_identity=self._publication.integrity_identity,
        )


def encode_visual_identity_publication(
    publication: VisualIdentityRelationshipPublication,
) -> bytes:
    if type(publication) is not VisualIdentityRelationshipPublication:
        raise VisualIdentityResolutionError(
            VisualIdentityResolutionFailure.INTEGRITY_INVALID
        )
    return _canonical(_normalize(publication)) + b"\n"


def parse_visual_identity_publication(
    payload: bytes,
    *,
    canonical_subject_identities: Iterable[str],
) -> VisualIdentityRelationshipPublication:
    try:
        raw = json.loads(payload.decode("utf-8"))
        if type(raw) is not dict:
            raise ValueError
        values = dict(raw)
        values["effective_from"] = datetime.fromisoformat(values["effective_from"])
        values["effective_through"] = datetime.fromisoformat(values["effective_through"])
        values["source_identities"] = tuple(values["source_identities"])
        values["provenance"] = tuple(values["provenance"])
        relationships = []
        for item in values["relationships"]:
            relationship = dict(item)
            relationship["source_context"] = VisualIdentitySourceContext(
                relationship["source_context"]
            )
            relationship["status"] = VisualIdentityRelationshipStatus(
                relationship["status"]
            )
            relationship["effective_from"] = datetime.fromisoformat(
                relationship["effective_from"]
            )
            relationship["effective_through"] = datetime.fromisoformat(
                relationship["effective_through"]
            )
            relationship["provenance"] = tuple(relationship["provenance"])
            relationships.append(GovernedVisualIdentityRelationship(**relationship))
        values["relationships"] = tuple(relationships)
        publication = VisualIdentityRelationshipPublication(**values)
        _require_canonical_subjects(publication, canonical_subject_identities)
        return publication
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        VisualIdentityResolutionError,
    ) as error:
        if (
            isinstance(error, VisualIdentityResolutionError)
            and error.failure is VisualIdentityResolutionFailure.INTEGRITY_INVALID
        ):
            raise
        raise VisualIdentityResolutionError(
            VisualIdentityResolutionFailure.INTEGRITY_INVALID
        ) from error


def _require_canonical_subjects(
    publication: VisualIdentityRelationshipPublication,
    canonical_subject_identities: Iterable[str],
) -> None:
    canonical = tuple(canonical_subject_identities)
    if (
        not canonical
        or any(not _text(item) for item in canonical)
        or len(canonical) != len(set(canonical))
        or any(
            relationship.canonical_subject_identity not in canonical
            for relationship in publication.relationships
        )
    ):
        raise VisualIdentityResolutionError(
            VisualIdentityResolutionFailure.INTEGRITY_INVALID
        )


def _conflicting_overlaps(
    relationships: tuple[GovernedVisualIdentityRelationship, ...],
) -> bool:
    for index, left in enumerate(relationships):
        if left.status is not VisualIdentityRelationshipStatus.ACTIVE:
            continue
        for right in relationships[index + 1 :]:
            if (
                right.status is VisualIdentityRelationshipStatus.ACTIVE
                and left.observed_visible_subject_identity
                == right.observed_visible_subject_identity
                and left.source_context is right.source_context
                and max(left.effective_from, right.effective_from)
                <= min(left.effective_through, right.effective_through)
                and left.canonical_subject_identity
                != right.canonical_subject_identity
            ):
                return True
    return False


def _without(value: object, *names: str) -> dict[str, object]:
    return {
        name: item
        for name, item in asdict(value).items()
        if name not in names
    }


def _identity(prefix: str, value: object) -> str:
    return prefix + sha256(_canonical(_normalize(value))).hexdigest().upper()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _normalize(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return _normalize(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
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


def _interval(start: object, end: object) -> bool:
    return _aware(start) and _aware(end) and start <= end  # type: ignore[operator]


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _text_exact(value: object) -> bool:
    return type(value) is str and bool(value)


def _texts(values: Iterable[object]) -> bool:
    retained = tuple(values)
    return bool(retained) and all(_text(item) for item in retained)


__all__ = [
    "GOVERNED_VISUAL_IDENTITY_RELATIONSHIP_V1",
    "GOVERNED_VISUAL_IDENTITY_RELATIONSHIP_V1_VERSION",
    "VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1",
    "VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_SUCCESSOR_VERSION",
    "VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_SUPPORTED_VERSIONS",
    "VISUAL_IDENTITY_RELATIONSHIP_PUBLICATION_V1_VERSION",
    "GovernedVisualIdentityRelationship",
    "VisualIdentityRelationshipPublication",
    "VisualIdentityRelationshipStatus",
    "VisualIdentityResolution",
    "VisualIdentityResolutionError",
    "VisualIdentityResolutionFailure",
    "VisualIdentityResolver",
    "VisualIdentitySourceContext",
    "create_visual_identity_publication",
    "create_visual_identity_relationship",
    "encode_visual_identity_publication",
    "parse_visual_identity_publication",
]
