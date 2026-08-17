"""Immutable restart-safe persistence for Intraday Slice-1 factual evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo

from kronos.intraday.candles import (
    CandleReconciliation,
    ReconciliationFailure,
    ReconciliationResult,
)
from kronos.intraday.contracts import (
    CandleBoundary,
    CandleCompletion,
    DataAvailability,
    GovernedCandle,
    INTRADAY_FACT_SCHEMA,
    IntradayInstrumentReference,
    IntradayRun,
    IntradayTimeframe,
    ObservationBoundary,
    SourceProvenance,
)
from kronos.market.schedule import (
    MarketDaySchedule,
    MarketWindow,
    TradingDayStatus,
)


INTRADAY_EVIDENCE_SCHEMA = "KRONOS-INTRADAY-V1-FACTUAL-EVIDENCE-V1"


@dataclass(frozen=True, slots=True)
class IntradayFactualEvidence:
    evidence_id: str
    run: IntradayRun
    reconciliation: CandleReconciliation
    schema_identity: str = INTRADAY_EVIDENCE_SCHEMA

    def __post_init__(self) -> None:
        if (
            not self.evidence_id.startswith("INTRADAY-EVIDENCE-")
            or len(self.evidence_id) != len("INTRADAY-EVIDENCE-") + 64
            or type(self.run) is not IntradayRun
            or type(self.reconciliation) is not CandleReconciliation
            or self.run.observation_boundary != self.reconciliation.observation_boundary
            or self.evidence_id != _evidence_identity(self.run, self.reconciliation)
            or self.schema_identity != INTRADAY_EVIDENCE_SCHEMA
        ):
            raise ValueError("INTRADAY_FACTUAL_EVIDENCE_INVALID")


def create_factual_evidence(
    run: IntradayRun,
    reconciliation: CandleReconciliation,
) -> IntradayFactualEvidence:
    if type(run) is not IntradayRun or type(reconciliation) is not CandleReconciliation:
        raise ValueError("INTRADAY_FACTUAL_EVIDENCE_INVALID")
    return IntradayFactualEvidence(
        evidence_id=_evidence_identity(run, reconciliation),
        run=run,
        reconciliation=reconciliation,
    )


class LocalIntradayFactualEvidenceStore:
    """Append-only evidence store with explicit identity-based reads."""

    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_EVIDENCE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain(self, evidence: IntradayFactualEvidence) -> None:
        if type(evidence) is not IntradayFactualEvidence:
            raise ValueError("INTRADAY_FACTUAL_EVIDENCE_INVALID")
        path = self._path(evidence)
        encoded = _encode(evidence)
        with self._lock:
            if path.exists():
                if path.read_bytes() != encoded:
                    raise ValueError("INTRADAY_FACTUAL_EVIDENCE_IMMUTABLE")
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
        timeframe: IntradayTimeframe,
        evidence_id: str,
    ) -> IntradayFactualEvidence:
        if (
            not isinstance(run_id, str)
            or not isinstance(mapping_identity, str)
            or type(timeframe) is not IntradayTimeframe
            or not isinstance(evidence_id, str)
        ):
            raise ValueError("INTRADAY_FACTUAL_EVIDENCE_IDENTITY_INVALID")
        path = self._root / run_id / mapping_identity / timeframe.value / f"{evidence_id}.json"
        with self._lock:
            try:
                raw = path.read_bytes()
                payload = json.loads(raw)
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
                raise ValueError("INTRADAY_FACTUAL_EVIDENCE_UNAVAILABLE") from error
            try:
                evidence = _from_dict(payload)
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("INTRADAY_FACTUAL_EVIDENCE_INTEGRITY_MISMATCH") from error
            reconciliation = evidence.reconciliation
            if (
                evidence.run.run_id != run_id
                or reconciliation.instrument.mapping_identity != mapping_identity
                or reconciliation.timeframe is not timeframe
                or evidence.evidence_id != evidence_id
                or _encode(evidence) != raw
            ):
                raise ValueError("INTRADAY_FACTUAL_EVIDENCE_INTEGRITY_MISMATCH")
            return evidence

    def _path(self, evidence: IntradayFactualEvidence) -> Path:
        reconciliation = evidence.reconciliation
        return (
            self._root
            / evidence.run.run_id
            / reconciliation.instrument.mapping_identity
            / reconciliation.timeframe.value
            / f"{evidence.evidence_id}.json"
        )


def _evidence_identity(run: IntradayRun, reconciliation: CandleReconciliation) -> str:
    payload = _to_dict(run, reconciliation)
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return f"INTRADAY-EVIDENCE-{sha256(canonical.encode('utf-8')).hexdigest()}"


def _encode(evidence: IntradayFactualEvidence) -> bytes:
    envelope = {
        "schema_identity": evidence.schema_identity,
        "evidence_id": evidence.evidence_id,
        "evidence": _to_dict(evidence.run, evidence.reconciliation),
    }
    canonical = json.dumps(envelope, ensure_ascii=True, indent=2, sort_keys=True)
    return canonical.encode("utf-8")


def _to_dict(run: IntradayRun, item: CandleReconciliation) -> dict[str, object]:
    return {
        "run": {
            "run_id": run.run_id,
            "created_at": run.created_at.isoformat(),
            "observation_boundary": run.observation_boundary.observed_at.isoformat(),
            "schema_identity": run.schema_identity,
        },
        "instrument": {
            "canonical_instrument_id": item.instrument.canonical_instrument_id,
            "exchange": item.instrument.exchange,
            "segment": item.instrument.segment,
            "instrument_type": item.instrument.instrument_type,
            "provider": item.instrument.provider,
            "provider_symbol": item.instrument.provider_symbol,
            "provider_instrument_token": item.instrument.provider_instrument_token,
            "tick_size": str(item.instrument.tick_size),
            "lot_size": item.instrument.lot_size,
            "price_precision": item.instrument.price_precision,
            "mapping_identity": item.instrument.mapping_identity,
        },
        "schedule": _schedule_dict(item.schedule),
        "timeframe": item.timeframe.value,
        "observation_boundary": item.observation_boundary.observed_at.isoformat(),
        "provenance": _provenance_dict(item.provenance),
        "expected_boundaries": [_boundary_dict(value) for value in item.expected_boundaries],
        "received_boundaries": [_boundary_dict(value) for value in item.received_boundaries],
        "missing_boundaries": [_boundary_dict(value) for value in item.missing_boundaries],
        "duplicate_boundaries": [_boundary_dict(value) for value in item.duplicate_boundaries],
        "partial_current_boundary": (
            _boundary_dict(item.partial_current_boundary)
            if item.partial_current_boundary is not None
            else None
        ),
        "unexpected_provider_timestamps": [value.isoformat() for value in item.unexpected_provider_timestamps],
        "out_of_order": item.out_of_order,
        "observations": [_candle_dict(value) for value in item.observations],
        "structural_candle_ids": [value.candle_id for value in item.structural_candles],
        "availability": item.availability.value,
        "result": item.result.value,
        "failures": [value.value for value in item.failures],
        "backfill_required": item.backfill_required,
    }


def _from_dict(envelope: dict[str, object]) -> IntradayFactualEvidence:
    if envelope["schema_identity"] != INTRADAY_EVIDENCE_SCHEMA:
        raise ValueError
    payload = envelope["evidence"]
    if not isinstance(payload, dict):
        raise ValueError
    run_data = payload["run"]
    instrument_data = payload["instrument"]
    if not isinstance(run_data, dict) or not isinstance(instrument_data, dict):
        raise ValueError
    run = IntradayRun(
        run_id=run_data["run_id"],
        created_at=datetime.fromisoformat(run_data["created_at"]),
        observation_boundary=ObservationBoundary(datetime.fromisoformat(run_data["observation_boundary"])),
        schema_identity=run_data["schema_identity"],
    )
    instrument = IntradayInstrumentReference(
        canonical_instrument_id=instrument_data["canonical_instrument_id"],
        exchange=instrument_data["exchange"],
        segment=instrument_data["segment"],
        instrument_type=instrument_data["instrument_type"],
        provider=instrument_data["provider"],
        provider_symbol=instrument_data["provider_symbol"],
        provider_instrument_token=instrument_data["provider_instrument_token"],
        tick_size=Decimal(instrument_data["tick_size"]),
        lot_size=instrument_data["lot_size"],
        price_precision=instrument_data["price_precision"],
        mapping_identity=instrument_data["mapping_identity"],
    )
    schedule = _schedule_from_dict(payload["schedule"])
    timeframe = IntradayTimeframe(payload["timeframe"])
    observation_boundary = ObservationBoundary(datetime.fromisoformat(payload["observation_boundary"]))
    provenance = _provenance_from_dict(payload["provenance"])
    observations = tuple(_candle_from_dict(value, provenance) for value in payload["observations"])
    by_id = {value.candle_id: value for value in observations}
    reconciliation = CandleReconciliation(
        instrument=instrument,
        timeframe=timeframe,
        schedule=schedule,
        observation_boundary=observation_boundary,
        provenance=provenance,
        expected_boundaries=tuple(_boundary_from_dict(value) for value in payload["expected_boundaries"]),
        received_boundaries=tuple(_boundary_from_dict(value) for value in payload["received_boundaries"]),
        missing_boundaries=tuple(_boundary_from_dict(value) for value in payload["missing_boundaries"]),
        duplicate_boundaries=tuple(_boundary_from_dict(value) for value in payload["duplicate_boundaries"]),
        partial_current_boundary=(
            _boundary_from_dict(payload["partial_current_boundary"])
            if payload["partial_current_boundary"] is not None
            else None
        ),
        unexpected_provider_timestamps=tuple(datetime.fromisoformat(value) for value in payload["unexpected_provider_timestamps"]),
        out_of_order=payload["out_of_order"],
        observations=observations,
        structural_candles=tuple(by_id[value] for value in payload["structural_candle_ids"]),
        availability=DataAvailability(payload["availability"]),
        result=ReconciliationResult(payload["result"]),
        failures=tuple(ReconciliationFailure(value) for value in payload["failures"]),
        backfill_required=payload["backfill_required"],
    )
    return IntradayFactualEvidence(
        evidence_id=envelope["evidence_id"],
        run=run,
        reconciliation=reconciliation,
        schema_identity=envelope["schema_identity"],
    )


def _schedule_dict(value: MarketDaySchedule) -> dict[str, object]:
    return {
        "exchange": value.exchange,
        "trading_date": value.trading_date.isoformat(),
        "session_id": value.session_id,
        "timezone": value.timezone,
        "status": value.status.value,
        "windows": [
            {"opens_at": item.opens_at.isoformat(), "closes_at": item.closes_at.isoformat()}
            for item in value.windows
        ],
        "source_identity": value.source_identity,
        "source_version": value.source_version,
        "special_session": value.special_session,
        "schema_identity": value.schema_identity,
    }


def _schedule_from_dict(value: object) -> MarketDaySchedule:
    if not isinstance(value, dict):
        raise ValueError
    zone = ZoneInfo(value["timezone"])
    return MarketDaySchedule(
        exchange=value["exchange"],
        trading_date=date.fromisoformat(value["trading_date"]),
        session_id=value["session_id"],
        timezone=value["timezone"],
        status=TradingDayStatus(value["status"]),
        windows=tuple(
            MarketWindow(
                datetime.fromisoformat(item["opens_at"]).astimezone(zone),
                datetime.fromisoformat(item["closes_at"]).astimezone(zone),
            )
            for item in value["windows"]
        ),
        source_identity=value["source_identity"],
        source_version=value["source_version"],
        special_session=value["special_session"],
        schema_identity=value["schema_identity"],
    )


def _boundary_dict(value: CandleBoundary) -> dict[str, str]:
    return {
        "trading_date": value.trading_date.isoformat(),
        "session_id": value.session_id,
        "timeframe": value.timeframe.value,
        "start": value.start.isoformat(),
        "end": value.end.isoformat(),
    }


def _boundary_from_dict(value: object) -> CandleBoundary:
    if not isinstance(value, dict):
        raise ValueError
    return CandleBoundary(
        trading_date=date.fromisoformat(value["trading_date"]),
        session_id=value["session_id"],
        timeframe=IntradayTimeframe(value["timeframe"]),
        start=datetime.fromisoformat(value["start"]),
        end=datetime.fromisoformat(value["end"]),
    )


def _provenance_dict(value: SourceProvenance) -> dict[str, str]:
    return {
        "provider": value.provider,
        "source_identity": value.source_identity,
        "retrieved_at": value.retrieved_at.isoformat(),
        "source_version": value.source_version,
    }


def _provenance_from_dict(value: object) -> SourceProvenance:
    if not isinstance(value, dict):
        raise ValueError
    return SourceProvenance(
        provider=value["provider"],
        source_identity=value["source_identity"],
        retrieved_at=datetime.fromisoformat(value["retrieved_at"]),
        source_version=value["source_version"],
    )


def _candle_dict(value: GovernedCandle) -> dict[str, object]:
    return {
        "candle_id": value.candle_id,
        "canonical_instrument_id": value.canonical_instrument_id,
        "boundary": _boundary_dict(value.boundary),
        "open": str(value.open),
        "high": str(value.high),
        "low": str(value.low),
        "close": str(value.close),
        "volume": value.volume,
        "completion": value.completion.value,
        "observation_boundary": value.observation_boundary.observed_at.isoformat(),
        "schema_identity": value.schema_identity,
    }


def _candle_from_dict(value: object, provenance: SourceProvenance) -> GovernedCandle:
    if not isinstance(value, dict):
        raise ValueError
    return GovernedCandle(
        candle_id=value["candle_id"],
        canonical_instrument_id=value["canonical_instrument_id"],
        boundary=_boundary_from_dict(value["boundary"]),
        open=Decimal(value["open"]),
        high=Decimal(value["high"]),
        low=Decimal(value["low"]),
        close=Decimal(value["close"]),
        volume=value["volume"],
        completion=CandleCompletion(value["completion"]),
        observation_boundary=ObservationBoundary(datetime.fromisoformat(value["observation_boundary"])),
        provenance=provenance,
        schema_identity=value["schema_identity"],
    )


__all__ = [
    "INTRADAY_EVIDENCE_SCHEMA",
    "IntradayFactualEvidence",
    "LocalIntradayFactualEvidenceStore",
    "create_factual_evidence",
]
