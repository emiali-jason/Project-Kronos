"""Immutable transport-only membership for Intraday Review batch PDFs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Mapping, Sequence

from kronos.intraday.review import ReviewError, ReviewFailure, ReviewQuestionPack


REVIEW_BATCH_PDF_IDENTITY = "KRONOS-INTRADAY-REVIEW-BATCH-PDF-V1"
REVIEW_BATCH_PDF_VERSION = "1.0.0"


def _text(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


@dataclass(frozen=True, slots=True)
class ReviewBatchMember:
    canonical_subject_identity: str
    direction: str
    review_cycle_identity: str
    chart_revision_identity: str
    review_pack_identity: str

    def __post_init__(self) -> None:
        if (
            not all(_text(value) for value in (
                self.canonical_subject_identity,
                self.direction,
                self.review_cycle_identity,
                self.chart_revision_identity,
                self.review_pack_identity,
            ))
            or self.direction not in {"LONG", "SHORT"}
            or not self.review_cycle_identity.startswith("INTRADAY-REVIEW-CYCLE-")
            or not self.chart_revision_identity.startswith("INTRADAY-CHART-REVISION-")
            or not self.review_pack_identity.startswith("INTRADAY-REVIEW-PACK-")
        ):
            raise ReviewError(ReviewFailure.INPUT_INVALID)


@dataclass(frozen=True, slots=True)
class ReviewBatchPdf:
    batch_identity: str
    probables_run_identity: str
    members: tuple[ReviewBatchMember, ...]
    created_at: datetime
    provenance: tuple[str, ...]
    integrity_identity: str
    schema_identity: str = REVIEW_BATCH_PDF_IDENTITY
    schema_version: str = REVIEW_BATCH_PDF_VERSION

    def __post_init__(self) -> None:
        values = _batch_values(self)
        if (
            not self.batch_identity.startswith("INTRADAY-REVIEW-BATCH-PDF-")
            or not self.probables_run_identity.startswith("INTRADAY-PROBABLES-RUN-")
            or not self.members
            or any(type(item) is not ReviewBatchMember for item in self.members)
            or tuple(sorted(self.members, key=lambda item: item.canonical_subject_identity)) != self.members
            or len({item.canonical_subject_identity for item in self.members}) != len(self.members)
            or len({item.review_pack_identity for item in self.members}) != len(self.members)
            or not _aware(self.created_at)
            or not self.provenance
            or any(not _text(item) for item in self.provenance)
            or self.schema_identity != REVIEW_BATCH_PDF_IDENTITY
            or self.schema_version != REVIEW_BATCH_PDF_VERSION
            or self.batch_identity != _identity("INTRADAY-REVIEW-BATCH-PDF-", values)
            or self.integrity_identity != _identity("INTEGRITY-REVIEW-BATCH-PDF-", values)
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


def create_review_batch(
    probables_run_identity: str,
    packs: Sequence[ReviewQuestionPack],
) -> ReviewBatchPdf:
    retained = tuple(packs)
    if (
        not _text(probables_run_identity)
        or not retained
        or any(type(pack) is not ReviewQuestionPack for pack in retained)
        or any(pack.probables_run_identity != probables_run_identity for pack in retained)
    ):
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    ordered = tuple(sorted(retained, key=lambda pack: pack.expected_canonical_subject_identity))
    members = tuple(
        ReviewBatchMember(
            canonical_subject_identity=pack.expected_canonical_subject_identity,
            direction=pack.proposed_direction,
            review_cycle_identity=pack.review_cycle_identity,
            chart_revision_identity=pack.chart_revision_identity,
            review_pack_identity=pack.review_pack_identity,
        )
        for pack in ordered
    )
    created_at = max(pack.created_at for pack in ordered)
    values = {
        "probables_run_identity": probables_run_identity,
        "members": members,
        "created_at": created_at,
        "provenance": ("WO-07A", probables_run_identity, *(pack.review_pack_identity for pack in ordered)),
        "schema_identity": REVIEW_BATCH_PDF_IDENTITY,
        "schema_version": REVIEW_BATCH_PDF_VERSION,
    }
    return ReviewBatchPdf(
        batch_identity=_identity("INTRADAY-REVIEW-BATCH-PDF-", values),
        integrity_identity=_identity("INTEGRITY-REVIEW-BATCH-PDF-", values),
        **values,
    )


def batch_artifact_bytes(value: ReviewBatchPdf) -> bytes:
    if type(value) is not ReviewBatchPdf:
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    return _canonical({"artifact_type": "ReviewBatchPdf", "value": _normalize(value)})


def batch_from_bytes(encoded: bytes) -> ReviewBatchPdf:
    try:
        document = json.loads(encoded.decode("utf-8"))
        if document["artifact_type"] != "ReviewBatchPdf":
            raise ValueError
        raw = document["value"]
        value = ReviewBatchPdf(
            batch_identity=raw["batch_identity"],
            probables_run_identity=raw["probables_run_identity"],
            members=tuple(ReviewBatchMember(**item) for item in raw["members"]),
            created_at=datetime.fromisoformat(raw["created_at"]),
            provenance=tuple(raw["provenance"]),
            integrity_identity=raw["integrity_identity"],
            schema_identity=raw["schema_identity"],
            schema_version=raw["schema_version"],
        )
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError, ReviewError) as error:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error
    return value


def _batch_values(value: ReviewBatchPdf) -> dict[str, object]:
    return {
        "probables_run_identity": value.probables_run_identity,
        "members": value.members,
        "created_at": value.created_at,
        "provenance": value.provenance,
        "schema_identity": value.schema_identity,
        "schema_version": value.schema_version,
    }


def _identity(prefix: str, values: Mapping[str, object]) -> str:
    return prefix + sha256(_canonical(values)).hexdigest().upper()


def _canonical(value: object) -> bytes:
    return json.dumps(_normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _normalize(value: object) -> object:
    if hasattr(value, "__dataclass_fields__"):
        return _normalize(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


__all__ = [
    "REVIEW_BATCH_PDF_IDENTITY",
    "REVIEW_BATCH_PDF_VERSION",
    "ReviewBatchMember",
    "ReviewBatchPdf",
    "batch_artifact_bytes",
    "batch_from_bytes",
    "create_review_batch",
]
