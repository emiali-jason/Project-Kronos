"""Fail-closed local delivery gate for Sponsor-mediated Swing NSE V3.2 Answers.

The producer prepares JSON and a draft PDF outside KRONOS evidence. This tool
checks the current governed request and the rendered PDF before making that PDF
available at its exact pack-owned filename. It never imports an Answer.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import tempfile

from kronos.swing.v1.pdf_visual_review_v3_live import extract_successor_answer_pdf
from kronos.swing.v1.review_evidence_binding import ReviewEvidenceError, strict_json
from kronos.swing.v1.review_evidence_store import ReviewEvidenceStore
from kronos.swing.v1.visual_evidence_v3 import validate_nse_successor_answer


_MAX_ANSWER_JSON = 8 * 1024 * 1024
_MAX_PDF = 128 * 1024 * 1024


@dataclass(frozen=True)
class ValidatedDraft:
    publication_identity: str
    mapping_payload: bytes
    answer_payload: bytes
    pack_identity: str
    answer_identity: str


def _bounded_read(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ReviewEvidenceError("ANSWER_DELIVERY_INPUT_INVALID", str(path))
    with path.open("rb") as source:
        payload = source.read(limit + 1)
    if len(payload) > limit:
        raise ReviewEvidenceError("ANSWER_DELIVERY_INPUT_OVERSIZED", str(path))
    return payload


def validate_draft(evidence_root: Path, question_pdf: Path, answer_json: Path) -> ValidatedDraft:
    """Read only: reject producer mistakes before any Answer PDF is delivered."""
    store = ReviewEvidenceStore(evidence_root)
    publication = store.load_current_request()
    if publication is None or publication.mapping.value["version"] != "2.0":
        raise ReviewEvidenceError("REVIEW_REQUEST_MISMATCH")
    mapping = publication.mapping
    pack_identity = mapping.value["review_pack_identity"]
    if question_pdf.name != pack_identity + "_QUESTIONS.pdf":
        raise ReviewEvidenceError("REVIEW_REQUEST_MISMATCH", "$.question_pdf.filename")
    question_payload = _bounded_read(question_pdf, _MAX_PDF)
    if sha256(question_payload).hexdigest() != mapping.value["review_pack_sha256"]:
        raise ReviewEvidenceError("REVIEW_ARTIFACT_DIGEST_MISMATCH", "$.question_pdf")
    answer_payload = _bounded_read(answer_json, _MAX_ANSWER_JSON)
    # The production validator enforces the complete closed Q1-Q10 contract:
    # exact canonical/response/observation echoes, original raw Q1 visible
    # strings, null rules, order, and chart revisions. It does not write.
    validate_nse_successor_answer(answer_payload, mapping)
    answer_identity = strict_json(answer_payload)["answer_identity"]
    return ValidatedDraft(publication.identity, mapping.payload, answer_payload,
                          pack_identity, answer_identity)


def deliver_pdf(evidence_root: Path, draft: ValidatedDraft, draft_pdf: Path,
                destination: Path) -> str:
    """Deliver the exact validated PDF without overwriting any prior Answer."""
    if destination.name != draft.pack_identity + "_ANSWERS.pdf":
        raise ReviewEvidenceError("ANSWER_DELIVERY_FILENAME_MISMATCH")
    payload = _bounded_read(draft_pdf, _MAX_PDF)
    extracted = extract_successor_answer_pdf(payload)
    if strict_json(extracted) != strict_json(draft.answer_payload):
        raise ReviewEvidenceError("ANSWER_DELIVERY_CONTENT_MISMATCH")
    if not destination.parent.is_dir() or destination.parent.is_symlink():
        raise ReviewEvidenceError("ANSWER_DELIVERY_DESTINATION_INVALID")
    store = ReviewEvidenceStore(evidence_root)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".answer-delivery-",
                                         delete=False) as stream:
            pending = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # The existing intake lock fences a request-pointer transition between
        # final currentness verification and exclusive local delivery.
        with store.intake_lock():
            publication = store.load_current_request()
            if (publication is None or publication.identity != draft.publication_identity
                    or publication.mapping.payload != draft.mapping_payload):
                raise ReviewEvidenceError("REVIEW_BINDING_STALE")
            validate_nse_successor_answer(extracted, publication.mapping)
            try:
                os.link(pending, destination)
            except FileExistsError as error:
                raise ReviewEvidenceError("ANSWER_DELIVERY_ALREADY_EXISTS") from error
            directory = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)
    return sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--question-pdf", required=True, type=Path)
    parser.add_argument("--answer-json", required=True, type=Path)
    parser.add_argument("--draft-pdf", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    try:
        draft = validate_draft(args.evidence_root, args.question_pdf, args.answer_json)
        digest = deliver_pdf(args.evidence_root, draft, args.draft_pdf, args.destination)
    except ReviewEvidenceError as error:
        parser.exit(2, f"{error.code} {error.path}\n")
    print(f"ANSWER_DELIVERY_VALIDATED {draft.answer_identity} {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
