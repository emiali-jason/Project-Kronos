"""Explicit immutable rendered-artifact recovery; never analytical recovery."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from io import BytesIO
import tempfile

from pypdf import PdfReader, PdfWriter
from pypdf.generic import IndirectObject, StreamObject

from kronos.swing.v1.pdf_visual_review_v3_live import (
    VISUAL_V3_LIVE_SELECTION_SCHEMA, _atomic_json, _primitive, _read,
    _verify_question_pdf, _write_answer_contract,
)

from kronos.swing.v1.pdf_visual_review_v3 import write_visual_v3_question_pack
from kronos.swing.v1.pdf_contract_layout_v3 import RENDERER_IDENTITY, RENDERER_VERSION

SCHEMA = "SWING_V3_REVIEW_ARTIFACT_RECOVERY_V1"
VERSION = "1.0.0"
CLASSIFICATION = "PDF_RENDERING_PLUS_STALE_EMBEDDED_IDENTITY"


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def artifact_projection(original, path, digest):
    path = Path(path)
    if not path.is_absolute() or path.resolve() == Path(original.question_path).resolve():
        raise ValueError("VISUAL_V3_RECOVERY_PATH_INVALID")
    return replace(
        original, question_filename=path.name, question_path=str(path),
        question_pdf_sha256=digest,
        candidate_packs=tuple(replace(
            item, question_path=str(path), question_pdf_sha256=digest,
        ) for item in original.candidate_packs),
    )


def validate_successor(record):
    path = Path(record.question_path)
    _verify_question_pdf(path, record)
    reader = PdfReader(path, strict=True)
    for generation, objects in reader.xref.items():
        for number in objects:
            if number:
                obj = reader.get_object(IndirectObject(number, generation, reader))
                if isinstance(obj, StreamObject):
                    obj.get_data()
    for page in reader.pages:
        page.extract_text()
    return len(reader.pages)


def render_successor_bytes(original, prepared):
    """Render the exact retained request population, without a new Review ID."""
    if len(prepared) != len(original.candidate_packs):
        raise ValueError("VISUAL_V3_RECOVERY_SOURCE_CONFLICT")
    for pack, requests in zip(original.candidate_packs, prepared, strict=True):
        if len(requests) != 4 or any(
            request.requirement.canonical_instrument != pack.canonical_instrument
            or request.requirement.native_run_identity != original.native_run_identity
            or request.requirement.thesis.native_assessment_sha256 != pack.native_assessment_sha256
            or request.request_timestamp != original.created_at
            or request.question_set_identity != original.question_set_identity
            or request.question_set_version != original.question_set_version
            for request in requests
        ) or (
            tuple((q.timeframe.value, q.chart_revision_sha256) for q in requests)
            != pack.chart_revisions
            or tuple((q.timeframe.value, q.machine_fact.integrity_sha256) for q in requests)
            != pack.machine_fact_bindings
        ):
            raise ValueError("VISUAL_V3_RECOVERY_SOURCE_CONFLICT")
    if max(q.observation_boundary for group in prepared for q in group) != original.observation_boundary:
        raise ValueError("VISUAL_V3_RECOVERY_SOURCE_CONFLICT")
    writer = PdfWriter()
    with tempfile.TemporaryDirectory(prefix="swing-artifact-render-") as directory:
        root = Path(directory)
        for index, requests in enumerate(prepared):
            path = root / f"candidate-{index}.pdf"
            write_visual_v3_question_pack(
                requests, path, review_pack_id=original.review_pack_id,
                created_at=original.created_at,
            )
            writer.append(path)
        contract = root / "contract.pdf"
        _write_answer_contract(
            contract, original.review_pack_id, prepared, original.expected_answer_filename,
        )
        writer.append(contract)
        output = BytesIO()
        writer.write(output)
        return output.getvalue()


def generate_successor(original, prepared, destination):
    """No-clobber, isolated authoring; no canonical store or pointer writes."""
    destination = Path(destination)
    projection = artifact_projection(original, destination, "0" * 64)
    payload = render_successor_bytes(original, prepared)
    projection = artifact_projection(original, destination, sha256(payload).hexdigest())
    with destination.open("xb") as stream:
        stream.write(payload)
    validate_successor(projection)
    return projection


def _validate_record(store, original, recovery):
    body = dict(recovery)
    checksum = body.pop("checksum", None)
    if (
        body.get("schema") != SCHEMA or body.get("version") != VERSION
        or checksum != _digest(body)
        or body.get("review_pack_id") != original.review_pack_id
        or body.get("canonical_pack_digest") != _digest(_primitive(original))
        or body.get("classification") != CLASSIFICATION
        or body.get("original_disposition") != "HISTORICAL_INVALID_RENDERED_ARTIFACT"
        or body.get("successor_disposition") != "CURRENT_VALID_RENDERED_ARTIFACT"
        or body.get("predecessor_path") != original.question_path
        or body.get("predecessor_sha256") != original.question_pdf_sha256
        or sha256(Path(original.question_path).read_bytes()).hexdigest()
        != original.question_pdf_sha256
        or not body.get("authorization") or not body.get("visual_qa_sha256")
        or body.get("renderer") != [RENDERER_IDENTITY, RENDERER_VERSION]
        or body.get("content_equivalence") != "EXACT_CANONICAL_RENDER_BYTES"
        or not isinstance(body.get("sources"), list) or not body["sources"]
    ):
        raise ValueError("VISUAL_V3_RECOVERY_BINDING_INVALID")
    selection = body.get("predecessor_selection")
    if selection != {"schema": VISUAL_V3_LIVE_SELECTION_SCHEMA,
                     "review_pack_id": original.review_pack_id}:
        raise ValueError("VISUAL_V3_RECOVERY_SELECTION_INVALID")
    for source in body["sources"]:
        if (not isinstance(source, dict) or set(source) != {"path", "sha256"}
            or not isinstance(source["path"], str) or not Path(source["path"]).is_absolute()):
            raise ValueError("VISUAL_V3_RECOVERY_SOURCE_INVALID")
        if sha256(Path(source["path"]).read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("VISUAL_V3_RECOVERY_SOURCE_CHANGED")
    projected = artifact_projection(original, body["successor_path"], body["successor_sha256"])
    validate_successor(projected)
    return projected


def resolve_selected_artifact(store, original, selection):
    identity = selection.get("artifact_recovery_sha256")
    if identity is None:
        return original
    if not isinstance(identity, str) or len(identity) != 64 or any(
        c not in "0123456789abcdef" for c in identity
    ):
        raise ValueError("VISUAL_V3_RECOVERY_ID_INVALID")
    recovery = _read(store.root / "artifact-recoveries" / f"{identity}.json")
    if recovery.get("checksum") != identity:
        raise ValueError("VISUAL_V3_RECOVERY_ID_INVALID")
    try:
        return _validate_record(store, original, recovery)
    except (KeyError, TypeError, OSError) as error:
        raise ValueError("VISUAL_V3_RECOVERY_BINDING_INVALID") from error


def supersede_selected_artifact(
    store, original, successor, *, prepared, sources, authorization, visual_qa_sha256,
    created_at: datetime, embedded_wrong_identity: str, structural_failure: str,
):
    """Explicit Sponsor-authorized commit point after external source/render QA.

    No API route, automatic invocation, Answer import, or restoration operation.
    Canonical pack and predecessor bytes remain immutable. Interrupted writes
    leave unselected evidence; selection is the sole final atomic commit point.
    """
    if (
        created_at.tzinfo is None or created_at.utcoffset() is None
        or not authorization or not sources or not structural_failure
        or len(visual_qa_sha256) != 64
        or any(c not in "0123456789abcdef" for c in visual_qa_sha256)
        or not embedded_wrong_identity.startswith("KRONOS-V3-REVIEW-")
        or embedded_wrong_identity == original.review_pack_id
    ):
        raise ValueError("VISUAL_V3_RECOVERY_AUTHORITY_INVALID")
    with store.cycle_lock:
        selection_path = store.root / "current-review-pack.json"
        selection = _read(selection_path)
        if selection.get("artifact_recovery_sha256"):
            current = resolve_selected_artifact(store, original, selection)
            retained = _read(store.root / "artifact-recoveries" / f"{selection['artifact_recovery_sha256']}.json")
            if (current != successor or retained["authorization"] != authorization
                or retained["sources"] != sources
                or retained["visual_qa_sha256"] != visual_qa_sha256
                or retained["embedded_wrong_identity"] != embedded_wrong_identity
                or retained["structural_failure"] != structural_failure):
                raise ValueError("VISUAL_V3_RECOVERY_REPLAY_CONFLICT")
            return retained
        if selection != {"schema": VISUAL_V3_LIVE_SELECTION_SCHEMA,
                         "review_pack_id": original.review_pack_id}:
            raise ValueError("VISUAL_V3_RECOVERY_SELECTION_INVALID")
        payload = _read(store.root / "review-packs" / f"{original.review_pack_id}.json")
        if payload.get("record") != _primitive(original):
            raise ValueError("VISUAL_V3_RECOVERY_CANONICAL_CONFLICT")
        if successor != artifact_projection(
            original, successor.question_path, successor.question_pdf_sha256,
        ):
            raise ValueError("VISUAL_V3_RECOVERY_ANALYTICAL_CHANGE")
        if sha256(render_successor_bytes(original, prepared)).hexdigest() != successor.question_pdf_sha256:
            raise ValueError("VISUAL_V3_RECOVERY_CONTENT_CONFLICT")
        try:
            _verify_question_pdf(Path(original.question_path), original)
        except ValueError:
            pass
        else:
            raise ValueError("VISUAL_V3_RECOVERY_ORIGINAL_NOT_INVALID")
        body = {
            "schema": SCHEMA, "version": VERSION,
            "review_pack_id": original.review_pack_id,
            "canonical_pack_digest": _digest(_primitive(original)),
            "predecessor_selection": selection,
            "predecessor_path": original.question_path,
            "predecessor_sha256": original.question_pdf_sha256,
            "successor_path": successor.question_path,
            "successor_sha256": successor.question_pdf_sha256,
            "classification": CLASSIFICATION,
            "structural_failure": structural_failure,
            "renderer": [RENDERER_IDENTITY, RENDERER_VERSION],
            "content_equivalence": "EXACT_CANONICAL_RENDER_BYTES",
            "embedded_wrong_identity": embedded_wrong_identity,
            "original_disposition": "HISTORICAL_INVALID_RENDERED_ARTIFACT",
            "successor_disposition": "CURRENT_VALID_RENDERED_ARTIFACT",
            "generation_policy": [original.transport_identity, original.transport_version,
                                  original.question_set_identity, original.question_set_version],
            "sources": sources, "authorization": authorization,
            "visual_qa_sha256": visual_qa_sha256,
            "created_at": created_at.isoformat(),
        }
        recovery = {**body, "checksum": _digest(body)}
        _validate_record(store, original, recovery)
        history = store.root / "selection-history" / f"{_digest(selection)}.json"
        store._retain(history, selection)
        store._retain(store.root / "artifact-recoveries" / f"{recovery['checksum']}.json", recovery)
        _atomic_json(selection_path, {
            **selection, "artifact_recovery_sha256": recovery["checksum"],
        }, replace_existing=True)
        return recovery
