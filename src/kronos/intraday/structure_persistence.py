"""Immutable restart persistence for Intraday Slice 2 structural evidence."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.contracts import (
    DataAvailability,
    IntradayInstrumentReference,
    IntradayRun,
    IntradayTimeframe,
    ObservationBoundary,
    SourceProvenance,
)
from kronos.intraday.structure import (
    STRUCTURAL_FACT_SCHEMA,
    FactualDirection,
    StructuralAttribute,
    StructuralBarrier,
    StructuralEvidence,
    StructuralFact,
    StructuralFactType,
    StructuralValue,
    structural_evidence_payload,
)


class LocalStructuralEvidenceStore:
    """Append-only storage addressed only by immutable evidence identities."""

    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_STRUCTURAL_EVIDENCE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain(self, evidence: StructuralEvidence) -> None:
        if type(evidence) is not StructuralEvidence:
            raise ValueError("INTRADAY_STRUCTURAL_EVIDENCE_INVALID")
        path = self._path(
            run_id=evidence.run.run_id,
            mapping_identity=evidence.instrument.mapping_identity,
            trading_date=evidence.trading_date.isoformat(),
            timeframe=evidence.timeframe,
            evidence_id=evidence.evidence_id,
        )
        encoded = _encode(evidence)
        with self._lock:
            if path.exists():
                if path.read_bytes() != encoded:
                    raise ValueError("INTRADAY_STRUCTURAL_EVIDENCE_IMMUTABLE")
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

    def load(
        self,
        *,
        run_id: str,
        mapping_identity: str,
        trading_date: str,
        timeframe: IntradayTimeframe,
        evidence_id: str,
    ) -> StructuralEvidence:
        if (
            not all(isinstance(item, str) and item for item in (
                run_id, mapping_identity, trading_date, evidence_id
            ))
            or type(timeframe) is not IntradayTimeframe
        ):
            raise ValueError("INTRADAY_STRUCTURAL_EVIDENCE_IDENTITY_INVALID")
        path = self._path(
            run_id=run_id, mapping_identity=mapping_identity,
            trading_date=trading_date, timeframe=timeframe, evidence_id=evidence_id,
        )
        with self._lock:
            try:
                encoded = path.read_bytes()
                evidence = structural_evidence_from_document(json.loads(encoded))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError) as error:
                raise ValueError("INTRADAY_STRUCTURAL_EVIDENCE_UNAVAILABLE_OR_INVALID") from error
        if (
            evidence.run.run_id != run_id
            or evidence.instrument.mapping_identity != mapping_identity
            or evidence.trading_date.isoformat() != trading_date
            or evidence.timeframe is not timeframe
            or evidence.evidence_id != evidence_id
            or _encode(evidence) != encoded
        ):
            raise ValueError("INTRADAY_STRUCTURAL_EVIDENCE_INTEGRITY_MISMATCH")
        return evidence

    def _path(
        self, *, run_id: str, mapping_identity: str, trading_date: str,
        timeframe: IntradayTimeframe, evidence_id: str,
    ) -> Path:
        return (
            self._root / run_id / mapping_identity / trading_date / timeframe.value
            / f"{evidence_id}.json"
        )


def structural_evidence_document(value: StructuralEvidence) -> dict[str, object]:
    instrument = value.instrument
    return {
        "schema_identity": value.schema_identity,
        "evidence_id": value.evidence_id,
        "integrity_identity": value.integrity_identity,
        "run": {
            "run_id": value.run.run_id,
            "created_at": value.run.created_at.isoformat(),
            "observation_boundary": value.run.observation_boundary.observed_at.isoformat(),
            "schema_identity": value.run.schema_identity,
        },
        "instrument": {
            "canonical_instrument_id": instrument.canonical_instrument_id,
            "exchange": instrument.exchange, "segment": instrument.segment,
            "instrument_type": instrument.instrument_type, "provider": instrument.provider,
            "provider_symbol": instrument.provider_symbol,
            "provider_instrument_token": instrument.provider_instrument_token,
            "tick_size": str(instrument.tick_size), "lot_size": instrument.lot_size,
            "price_precision": instrument.price_precision,
            "mapping_identity": instrument.mapping_identity,
        },
        "evidence": structural_evidence_payload(value),
    }


def structural_evidence_from_document(document: dict[str, object]) -> StructuralEvidence:
    if not isinstance(document, dict) or set(document) != {
        "schema_identity", "evidence_id", "integrity_identity", "run", "instrument", "evidence"
    }:
        raise ValueError("INTRADAY_STRUCTURAL_EVIDENCE_DOCUMENT_INVALID")
    run_data, instrument_data, payload = document["run"], document["instrument"], document["evidence"]
    if not all(isinstance(item, dict) for item in (run_data, instrument_data, payload)):
        raise ValueError("INTRADAY_STRUCTURAL_EVIDENCE_DOCUMENT_INVALID")
    run = IntradayRun(
        run_id=run_data["run_id"], created_at=datetime.fromisoformat(run_data["created_at"]),
        observation_boundary=ObservationBoundary(datetime.fromisoformat(run_data["observation_boundary"])),
        schema_identity=run_data["schema_identity"],
    )
    instrument = IntradayInstrumentReference(
        canonical_instrument_id=instrument_data["canonical_instrument_id"],
        exchange=instrument_data["exchange"], segment=instrument_data["segment"],
        instrument_type=instrument_data["instrument_type"], provider=instrument_data["provider"],
        provider_symbol=instrument_data["provider_symbol"],
        provider_instrument_token=instrument_data["provider_instrument_token"],
        tick_size=Decimal(instrument_data["tick_size"]), lot_size=instrument_data["lot_size"],
        price_precision=instrument_data["price_precision"],
        mapping_identity=instrument_data["mapping_identity"],
    )
    provenance = _provenance(payload["provenance"])
    barriers = tuple(_barrier(item) for item in payload["barriers"])
    facts = tuple(_fact(item) for item in payload["facts"])
    evidence = StructuralEvidence(
        evidence_id=document["evidence_id"], run=run, instrument=instrument,
        trading_date=date.fromisoformat(payload["trading_date"]),
        timeframe=IntradayTimeframe(payload["timeframe"]),
        observation_boundary=ObservationBoundary(datetime.fromisoformat(payload["observation_boundary"])),
        governed_candle_ids=tuple(payload["governed_candle_ids"]),
        barriers=barriers, facts=facts,
        availability=DataAvailability(payload["availability"]), provenance=provenance,
        integrity_identity=document["integrity_identity"],
        schema_identity=document["schema_identity"],
    )
    if structural_evidence_document(evidence) != document:
        raise ValueError("INTRADAY_STRUCTURAL_EVIDENCE_DOCUMENT_INTEGRITY_MISMATCH")
    return evidence


def _fact(envelope: object) -> StructuralFact:
    if not isinstance(envelope, dict) or not isinstance(envelope.get("fact"), dict):
        raise ValueError
    payload = envelope["fact"]
    return StructuralFact(
        fact_id=envelope["fact_id"], run_id=payload["run_id"],
        canonical_instrument_id=payload["canonical_instrument_id"],
        mapping_identity=payload["mapping_identity"],
        trading_date=date.fromisoformat(payload["trading_date"]),
        timeframe=IntradayTimeframe(payload["timeframe"]),
        observation_boundary=ObservationBoundary(datetime.fromisoformat(payload["observation_boundary"])),
        fact_type=StructuralFactType(payload["fact_type"]),
        direction=FactualDirection(payload["direction"]),
        values=tuple(StructuralValue(item["name"], Decimal(item["value"])) for item in payload["values"]),
        attributes=tuple(StructuralAttribute(item["name"], item["value"]) for item in payload["attributes"]),
        source_candle_ids=tuple(payload["source_candle_ids"]),
        source_reference_ids=tuple(payload["source_reference_ids"]),
        start_boundary=_optional_datetime(payload["start_boundary"]),
        end_boundary=_optional_datetime(payload["end_boundary"]),
        confirmation_boundary=_optional_datetime(payload["confirmation_boundary"]),
        availability=DataAvailability(payload["availability"]),
        provenance=_provenance(payload["provenance"]),
        policy_version=payload["policy_version"],
        integrity_identity=envelope["integrity_identity"],
        schema_identity=payload["schema_identity"],
    )


def _barrier(payload: object) -> StructuralBarrier:
    if not isinstance(payload, dict):
        raise ValueError
    return StructuralBarrier(
        barrier_id=payload["barrier_id"], barrier_family=payload["barrier_family"],
        reference_name=payload["reference_name"],
        price=None if payload["price"] is None else Decimal(payload["price"]),
        origin_trading_date=date.fromisoformat(payload["origin_trading_date"]),
        origin_timeframe=IntradayTimeframe(payload["origin_timeframe"]),
        origin_session_id=payload["origin_session_id"],
        source_identity=payload["source_identity"], provenance=_provenance(payload["provenance"]),
        availability=DataAvailability(payload["availability"]),
    )


def _provenance(payload: object) -> SourceProvenance:
    if not isinstance(payload, dict):
        raise ValueError
    return SourceProvenance(
        provider=payload["provider"], source_identity=payload["source_identity"],
        retrieved_at=datetime.fromisoformat(payload["retrieved_at"]),
        source_version=payload["source_version"],
    )


def _optional_datetime(value: object) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _encode(evidence: StructuralEvidence) -> bytes:
    return json.dumps(
        structural_evidence_document(evidence), ensure_ascii=True, indent=2, sort_keys=True
    ).encode("utf-8")


__all__ = [
    "LocalStructuralEvidenceStore", "structural_evidence_document",
    "structural_evidence_from_document",
]
