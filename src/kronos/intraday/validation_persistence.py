"""Append-only, explicit-identity persistence for Slice 3V validation evidence."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.validation import (
    ComparisonItem,
    ComparisonResult,
    DiscrepancyFamily,
    DiscrepancyRecord,
    FactualValueKind,
    SLICE3V_COMPARISON_POLICY,
    SLICE3V_QUESTION_SET,
    SLICE3V_VALIDATION_RECORD_SCHEMA,
    SLICE3V_VISUAL_ANSWER_SCHEMA,
    Slice3VContractError,
    ValidationEvidenceFamily,
    ValidationFailureState,
    ValidationQuestion,
    ValidationRecord,
    VisualAnswer,
    VisualPrecision,
    accept_visual_answer,
    validation_record_payload,
    visual_answer_payload,
    visual_answer_payload_from_dict,
)


class LocalSlice3VValidationStore:
    """Immutable store; selection is by identity and never by newest file."""

    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute() or root == Path("/"):
            raise ValueError("SLICE3V_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain_visual_answer(self, value: VisualAnswer) -> None:
        if type(value) is not VisualAnswer:
            raise ValueError("SLICE3V_VISUAL_ANSWER_INVALID")
        answer_path = self._root / "visual-answers" / f"{value.visual_evidence_identity}.json"
        binding_identity = visual_answer_binding_identity(value)
        binding_path = self._root / "visual-bindings" / f"{binding_identity}.json"
        answer_encoded = _encode(visual_answer_document(value))
        binding_encoded = _encode(
            {
                "binding_identity": binding_identity,
                "visual_evidence_identity": value.visual_evidence_identity,
                "question_set_identity": value.payload.question_set_identity,
                "visual_answer_schema_identity": value.payload.schema_identity,
            }
        )
        with self._lock:
            if binding_path.exists():
                try:
                    existing = json.loads(binding_path.read_bytes())
                except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
                    raise ValueError("SLICE3V_VISUAL_BINDING_INVALID") from error
                if (
                    not isinstance(existing, dict)
                    or existing.get("binding_identity") != binding_identity
                    or existing.get("visual_evidence_identity")
                    != value.visual_evidence_identity
                    or _encode(existing) != binding_path.read_bytes()
                ):
                    raise Slice3VContractError(
                        ValidationFailureState.DUPLICATE_CONFLICTING_ANSWER,
                        "SLICE3V_VISUAL_ANSWER_CONFLICT",
                    )
            _write_immutable(answer_path, answer_encoded, "SLICE3V_VISUAL_ANSWER_IMMUTABLE")
            _write_immutable(binding_path, binding_encoded, "SLICE3V_VISUAL_BINDING_IMMUTABLE")

    def load_visual_answer(self, *, visual_evidence_identity: str) -> VisualAnswer:
        if not isinstance(visual_evidence_identity, str) or not visual_evidence_identity:
            raise ValueError("SLICE3V_VISUAL_EVIDENCE_IDENTITY_INVALID")
        path = self._root / "visual-answers" / f"{visual_evidence_identity}.json"
        with self._lock:
            encoded = _read(path, "SLICE3V_VISUAL_ANSWER_UNAVAILABLE_OR_INVALID")
            try:
                value = visual_answer_from_document(json.loads(encoded))
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError) as error:
                raise ValueError("SLICE3V_VISUAL_ANSWER_UNAVAILABLE_OR_INVALID") from error
        if value.visual_evidence_identity != visual_evidence_identity or _encode(
            visual_answer_document(value)
        ) != encoded:
            raise ValueError("SLICE3V_VISUAL_ANSWER_INTEGRITY_MISMATCH")
        return value

    def retain_validation_record(self, value: ValidationRecord) -> None:
        if type(value) is not ValidationRecord:
            raise ValueError("SLICE3V_VALIDATION_RECORD_INVALID")
        path = self._root / "validation-records" / f"{value.validation_record_identity}.json"
        with self._lock:
            _write_immutable(
                path,
                _encode(validation_record_document(value)),
                "SLICE3V_VALIDATION_RECORD_IMMUTABLE",
            )

    def load_validation_record(
        self, *, validation_record_identity: str
    ) -> ValidationRecord:
        if not isinstance(validation_record_identity, str) or not validation_record_identity:
            raise ValueError("SLICE3V_VALIDATION_RECORD_IDENTITY_INVALID")
        path = (
            self._root
            / "validation-records"
            / f"{validation_record_identity}.json"
        )
        with self._lock:
            encoded = _read(path, "SLICE3V_VALIDATION_RECORD_UNAVAILABLE_OR_INVALID")
            try:
                value = validation_record_from_document(json.loads(encoded))
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError) as error:
                raise ValueError("SLICE3V_VALIDATION_RECORD_UNAVAILABLE_OR_INVALID") from error
        if value.validation_record_identity != validation_record_identity or _encode(
            validation_record_document(value)
        ) != encoded:
            raise ValueError("SLICE3V_VALIDATION_RECORD_INTEGRITY_MISMATCH")
        return value


def visual_answer_binding_identity(value: VisualAnswer) -> str:
    payload = value.payload
    binding = {
        "visible_symbol": payload.visible_symbol,
        "exchange": payload.exchange,
        "trading_date": payload.trading_date.isoformat(),
        "timeframe": payload.timeframe.value,
        "observation_boundary": payload.observation_boundary.isoformat(),
        "question_set_identity": payload.question_set_identity,
        "visual_answer_schema_identity": payload.schema_identity,
    }
    return _identity("SLICE3V-VISUAL-BINDING-", binding)


def visual_answer_document(value: VisualAnswer) -> dict[str, object]:
    return {
        "visual_evidence_identity": value.visual_evidence_identity,
        "integrity_identity": value.integrity_identity,
        "visual_answer": visual_answer_payload(value.payload),
    }


def visual_answer_from_document(document: dict[str, object]) -> VisualAnswer:
    if not isinstance(document, dict) or set(document) != {
        "visual_evidence_identity", "integrity_identity", "visual_answer"
    } or not isinstance(document["visual_answer"], dict):
        raise ValueError("SLICE3V_VISUAL_ANSWER_DOCUMENT_INVALID")
    value = accept_visual_answer(
        visual_answer_payload_from_dict(document["visual_answer"])
    )
    if (
        value.visual_evidence_identity != document["visual_evidence_identity"]
        or value.integrity_identity != document["integrity_identity"]
        or visual_answer_document(value) != document
    ):
        raise ValueError("SLICE3V_VISUAL_ANSWER_DOCUMENT_INTEGRITY_MISMATCH")
    return value


def validation_record_document(value: ValidationRecord) -> dict[str, object]:
    return {
        "validation_record_identity": value.validation_record_identity,
        "validation_run_identity": value.validation_run_identity,
        "integrity_identity": value.integrity_identity,
        "validation_record": validation_record_payload(value),
    }


def validation_record_from_document(document: dict[str, object]) -> ValidationRecord:
    if not isinstance(document, dict) or set(document) != {
        "validation_record_identity",
        "validation_run_identity",
        "integrity_identity",
        "validation_record",
    } or not isinstance(document["validation_record"], dict):
        raise ValueError("SLICE3V_VALIDATION_RECORD_DOCUMENT_INVALID")
    payload = document["validation_record"]
    expected = {
        "canonical_instrument_id",
        "trading_date",
        "observation_boundary",
        "timeframe",
        "machine_evidence_identity",
        "visual_evidence_identity",
        "evidence_family",
        "question_set_identity",
        "visual_answer_schema_identity",
        "comparison_policy_identity",
        "compared_at",
        "comparison_results",
        "discrepancies",
        "schema_identity",
    }
    if set(payload) != expected:
        raise ValueError("SLICE3V_VALIDATION_RECORD_DOCUMENT_INVALID")
    value = ValidationRecord(
        validation_record_identity=document["validation_record_identity"],
        validation_run_identity=document["validation_run_identity"],
        canonical_instrument_id=payload["canonical_instrument_id"],
        trading_date=date.fromisoformat(payload["trading_date"]),
        observation_boundary=datetime.fromisoformat(payload["observation_boundary"]),
        timeframe=IntradayTimeframe(payload["timeframe"]),
        machine_evidence_identity=payload["machine_evidence_identity"],
        visual_evidence_identity=payload["visual_evidence_identity"],
        evidence_family=ValidationEvidenceFamily(payload["evidence_family"]),
        compared_at=datetime.fromisoformat(payload["compared_at"]),
        comparison_results=tuple(
            _comparison_item(item) for item in payload["comparison_results"]
        ),
        discrepancies=tuple(
            _discrepancy(item) for item in payload["discrepancies"]
        ),
        integrity_identity=document["integrity_identity"],
        question_set_identity=payload["question_set_identity"],
        visual_answer_schema_identity=payload["visual_answer_schema_identity"],
        comparison_policy_identity=payload["comparison_policy_identity"],
        schema_identity=payload["schema_identity"],
    )
    if validation_record_document(value) != document:
        raise ValueError("SLICE3V_VALIDATION_RECORD_DOCUMENT_INTEGRITY_MISMATCH")
    return value


def _comparison_item(value: object) -> ComparisonItem:
    expected = {
        "question",
        "fact_key",
        "result",
        "machine_value_kind",
        "machine_value",
        "visual_precision",
        "visual_value_kind",
        "visual_value",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError
    machine_kind = _optional_kind(value["machine_value_kind"])
    visual_kind = _optional_kind(value["visual_value_kind"])
    return ComparisonItem(
        question=ValidationQuestion(value["question"]),
        fact_key=value["fact_key"],
        result=ComparisonResult(value["result"]),
        machine_value_kind=machine_kind,
        machine_value=_parsed_value(machine_kind, value["machine_value"]),
        visual_precision=(
            None
            if value["visual_precision"] is None
            else VisualPrecision(value["visual_precision"])
        ),
        visual_value_kind=visual_kind,
        visual_value=_parsed_value(visual_kind, value["visual_value"]),
    )


def _discrepancy(value: object) -> DiscrepancyRecord:
    if not isinstance(value, dict) or set(value) != {
        "question", "fact_key", "family", "factual_explanation"
    }:
        raise ValueError
    return DiscrepancyRecord(
        question=ValidationQuestion(value["question"]),
        fact_key=value["fact_key"],
        family=DiscrepancyFamily(value["family"]),
        factual_explanation=value["factual_explanation"],
    )


def _optional_kind(value: object) -> FactualValueKind | None:
    return None if value is None else FactualValueKind(value)


def _parsed_value(
    kind: FactualValueKind | None, value: object
) -> Decimal | str | bool | None:
    if kind is None:
        if value is not None:
            raise ValueError
        return None
    if kind is FactualValueKind.NUMERIC:
        return Decimal(value)
    if kind is FactualValueKind.BOOLEAN:
        if type(value) is not bool:
            raise ValueError
        return value
    if not isinstance(value, str):
        raise ValueError
    return value


def _write_immutable(path: Path, encoded: bytes, error_code: str) -> None:
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError(error_code)
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read(path: Path, code: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise ValueError(code) from error


def _encode(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True).encode("utf-8")


def _identity(prefix: str, payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return f"{prefix}{sha256(canonical.encode('utf-8')).hexdigest()}"


__all__ = [
    "LocalSlice3VValidationStore",
    "validation_record_document",
    "validation_record_from_document",
    "visual_answer_binding_identity",
    "visual_answer_document",
    "visual_answer_from_document",
]
