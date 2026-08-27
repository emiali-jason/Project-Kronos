"""Immutable Sponsor transport metadata for one Intraday Review batch."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Mapping
from zoneinfo import ZoneInfo

from kronos.intraday.review import ReviewError, ReviewFailure
from kronos.intraday.review_batch import ReviewBatchPdf


REVIEW_BATCH_TRANSPORT_IDENTITY = "KRONOS-INTRADAY-REVIEW-BATCH-TRANSPORT-V1"
REVIEW_BATCH_TRANSPORT_VERSION = "1.0.0"
_IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True, slots=True)
class ReviewBatchTransport:
    transport_identity: str
    review_batch_identity: str
    probables_run_identity: str
    generated_at: datetime
    question_filename: str
    expected_answer_filename: str
    candidate_count: int
    integrity_identity: str
    schema_identity: str = REVIEW_BATCH_TRANSPORT_IDENTITY
    schema_version: str = REVIEW_BATCH_TRANSPORT_VERSION

    def __post_init__(self) -> None:
        values = _transport_values(self)
        if (
            not self.transport_identity.startswith("INTRADAY-REVIEW-BATCH-TRANSPORT-")
            or not self.review_batch_identity.startswith("INTRADAY-REVIEW-BATCH-PDF-")
            or not self.probables_run_identity.startswith("INTRADAY-PROBABLES-RUN-")
            or self.generated_at.tzinfo is None
            or self.generated_at.utcoffset() is None
            or self.candidate_count < 1
            or self.question_filename != f"{review_batch_stem(self)}_QUESTIONS.pdf"
            or self.expected_answer_filename != f"{review_batch_stem(self)}_ANSWERS.json"
            or self.schema_identity != REVIEW_BATCH_TRANSPORT_IDENTITY
            or self.schema_version != REVIEW_BATCH_TRANSPORT_VERSION
            or self.transport_identity != _identity("INTRADAY-REVIEW-BATCH-TRANSPORT-", values)
            or self.integrity_identity != _identity("INTEGRITY-REVIEW-BATCH-TRANSPORT-", values)
        ):
            raise ReviewError(ReviewFailure.INTEGRITY_INVALID)


def create_review_batch_transport(
    batch: ReviewBatchPdf,
    *,
    generated_at: datetime,
) -> ReviewBatchTransport:
    if (
        type(batch) is not ReviewBatchPdf
        or not isinstance(generated_at, datetime)
        or generated_at.tzinfo is None
        or generated_at.utcoffset() is None
    ):
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    stamp = generated_at.astimezone(_IST).strftime("%Y%m%d_%H%M%S")
    suffix = batch.batch_identity.rsplit("-", 1)[-1][:8]
    stem = f"KRONOS_INTRADAY_REVIEW_{stamp}_IST_{suffix}"
    values = {
        "review_batch_identity": batch.batch_identity,
        "probables_run_identity": batch.probables_run_identity,
        "generated_at": generated_at,
        "question_filename": f"{stem}_QUESTIONS.pdf",
        "expected_answer_filename": f"{stem}_ANSWERS.json",
        "candidate_count": len(batch.members),
        "schema_identity": REVIEW_BATCH_TRANSPORT_IDENTITY,
        "schema_version": REVIEW_BATCH_TRANSPORT_VERSION,
    }
    return ReviewBatchTransport(
        transport_identity=_identity("INTRADAY-REVIEW-BATCH-TRANSPORT-", values),
        integrity_identity=_identity("INTEGRITY-REVIEW-BATCH-TRANSPORT-", values),
        **values,
    )


def review_batch_stem(value: ReviewBatchTransport) -> str:
    if type(value) is not ReviewBatchTransport:
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    stamp = value.generated_at.astimezone(_IST).strftime("%Y%m%d_%H%M%S")
    suffix = value.review_batch_identity.rsplit("-", 1)[-1][:8]
    return f"KRONOS_INTRADAY_REVIEW_{stamp}_IST_{suffix}"


def transport_artifact_bytes(value: ReviewBatchTransport) -> bytes:
    if type(value) is not ReviewBatchTransport:
        raise ReviewError(ReviewFailure.INPUT_INVALID)
    return _canonical({"artifact_type": "ReviewBatchTransport", "value": _normalize(value)})


def transport_from_bytes(encoded: bytes) -> ReviewBatchTransport:
    try:
        document = json.loads(encoded.decode("utf-8"))
        if document["artifact_type"] != "ReviewBatchTransport":
            raise ValueError
        raw = document["value"]
        value = ReviewBatchTransport(
            transport_identity=raw["transport_identity"],
            review_batch_identity=raw["review_batch_identity"],
            probables_run_identity=raw["probables_run_identity"],
            generated_at=datetime.fromisoformat(raw["generated_at"]),
            question_filename=raw["question_filename"],
            expected_answer_filename=raw["expected_answer_filename"],
            candidate_count=raw["candidate_count"],
            integrity_identity=raw["integrity_identity"],
            schema_identity=raw["schema_identity"],
            schema_version=raw["schema_version"],
        )
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError, ReviewError) as error:
        raise ReviewError(ReviewFailure.INTEGRITY_INVALID) from error
    return value


def _transport_values(value: ReviewBatchTransport) -> dict[str, object]:
    return {
        "review_batch_identity": value.review_batch_identity,
        "probables_run_identity": value.probables_run_identity,
        "generated_at": value.generated_at,
        "question_filename": value.question_filename,
        "expected_answer_filename": value.expected_answer_filename,
        "candidate_count": value.candidate_count,
        "schema_identity": value.schema_identity,
        "schema_version": value.schema_version,
    }


def _identity(prefix: str, values: Mapping[str, object]) -> str:
    return prefix + sha256(_canonical(values)).hexdigest().upper()


def _canonical(value: object) -> bytes:
    return json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


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
    "REVIEW_BATCH_TRANSPORT_IDENTITY",
    "REVIEW_BATCH_TRANSPORT_VERSION",
    "ReviewBatchTransport",
    "create_review_batch_transport",
    "review_batch_stem",
    "transport_artifact_bytes",
    "transport_from_bytes",
]
