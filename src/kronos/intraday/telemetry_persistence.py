"""Append-only persistence for Intraday Slice 3 shadow telemetry."""

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
from kronos.intraday.telemetry import (
    SHADOW_TELEMETRY_SCHEMA,
    FactualComparison,
    ShadowTelemetryEvidence,
    TelemetryAttribute,
    TelemetryMeasure,
    TelemetryType,
    TelemetryValue,
    shadow_telemetry_payload,
)


class LocalShadowTelemetryStore:
    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_SHADOW_TELEMETRY_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain(self, evidence: ShadowTelemetryEvidence) -> None:
        if type(evidence) is not ShadowTelemetryEvidence:
            raise ValueError("INTRADAY_SHADOW_TELEMETRY_INVALID")
        path = self._path(
            evidence.run.run_id, evidence.instrument.mapping_identity,
            evidence.trading_date.isoformat(), evidence.timeframe, evidence.evidence_id,
        )
        encoded = _encode(evidence)
        with self._lock:
            if path.exists():
                if path.read_bytes() != encoded:
                    raise ValueError("INTRADAY_SHADOW_TELEMETRY_IMMUTABLE")
                return
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
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
        self, *, run_id: str, mapping_identity: str, trading_date: str,
        timeframe: IntradayTimeframe, evidence_id: str,
    ) -> ShadowTelemetryEvidence:
        path = self._path(run_id, mapping_identity, trading_date, timeframe, evidence_id)
        with self._lock:
            try:
                encoded = path.read_bytes()
                evidence = shadow_telemetry_from_document(json.loads(encoded))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError) as error:
                raise ValueError("INTRADAY_SHADOW_TELEMETRY_UNAVAILABLE_OR_INVALID") from error
        if (
            evidence.run.run_id != run_id
            or evidence.instrument.mapping_identity != mapping_identity
            or evidence.trading_date.isoformat() != trading_date
            or evidence.timeframe is not timeframe
            or evidence.evidence_id != evidence_id
            or _encode(evidence) != encoded
        ):
            raise ValueError("INTRADAY_SHADOW_TELEMETRY_INTEGRITY_MISMATCH")
        return evidence

    def _path(
        self, run_id: str, mapping_identity: str, trading_date: str,
        timeframe: IntradayTimeframe, evidence_id: str,
    ) -> Path:
        if not all(isinstance(item, str) and item for item in (
            run_id, mapping_identity, trading_date, evidence_id
        )) or type(timeframe) is not IntradayTimeframe:
            raise ValueError("INTRADAY_SHADOW_TELEMETRY_IDENTITY_INVALID")
        return self._root / run_id / mapping_identity / trading_date / timeframe.value / f"{evidence_id}.json"


def shadow_telemetry_document(value: ShadowTelemetryEvidence) -> dict[str, object]:
    instrument = value.instrument
    return {
        "schema_identity": value.schema_identity,
        "evidence_id": value.evidence_id,
        "integrity_identity": value.integrity_identity,
        "run": {
            "run_id": value.run.run_id, "created_at": value.run.created_at.isoformat(),
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
        "evidence": shadow_telemetry_payload(value),
    }


def shadow_telemetry_from_document(document: dict[str, object]) -> ShadowTelemetryEvidence:
    if not isinstance(document, dict) or set(document) != {
        "schema_identity", "evidence_id", "integrity_identity", "run", "instrument", "evidence"
    }:
        raise ValueError
    run_data, instrument_data, payload = document["run"], document["instrument"], document["evidence"]
    if not all(isinstance(item, dict) for item in (run_data, instrument_data, payload)):
        raise ValueError
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
    measures = tuple(_measure(item) for item in payload["measures"])
    evidence = ShadowTelemetryEvidence(
        evidence_id=document["evidence_id"], run=run, instrument=instrument,
        trading_date=date.fromisoformat(payload["trading_date"]),
        timeframe=IntradayTimeframe(payload["timeframe"]),
        observation_boundary=ObservationBoundary(datetime.fromisoformat(payload["observation_boundary"])),
        governed_candle_ids=tuple(payload["governed_candle_ids"]), measures=measures,
        availability=DataAvailability(payload["availability"]), provenance=provenance,
        integrity_identity=document["integrity_identity"], schema_identity=document["schema_identity"],
    )
    if shadow_telemetry_document(evidence) != document:
        raise ValueError
    return evidence


def _measure(envelope: object) -> TelemetryMeasure:
    if not isinstance(envelope, dict) or not isinstance(envelope.get("measure"), dict):
        raise ValueError
    payload = envelope["measure"]
    return TelemetryMeasure(
        telemetry_id=envelope["telemetry_id"],
        telemetry_type=TelemetryType(payload["telemetry_type"]),
        timeframe=IntradayTimeframe(payload["timeframe"]),
        values=tuple(TelemetryValue(item["name"], Decimal(item["value"])) for item in payload["values"]),
        attributes=tuple(TelemetryAttribute(item["name"], item["value"]) for item in payload["attributes"]),
        comparison=FactualComparison(payload["comparison"]),
        source_candle_ids=tuple(payload["source_candle_ids"]),
        source_reference_ids=tuple(payload["source_reference_ids"]),
        availability=DataAvailability(payload["availability"]),
        policy_version=payload["policy_version"],
        integrity_identity=envelope["integrity_identity"],
    )


def _provenance(payload: object) -> SourceProvenance:
    if not isinstance(payload, dict):
        raise ValueError
    return SourceProvenance(
        provider=payload["provider"], source_identity=payload["source_identity"],
        retrieved_at=datetime.fromisoformat(payload["retrieved_at"]),
        source_version=payload["source_version"],
    )


def _encode(evidence: ShadowTelemetryEvidence) -> bytes:
    return json.dumps(
        shadow_telemetry_document(evidence), ensure_ascii=True, indent=2, sort_keys=True
    ).encode("utf-8")


__all__ = [
    "LocalShadowTelemetryStore", "shadow_telemetry_document",
    "shadow_telemetry_from_document",
]
