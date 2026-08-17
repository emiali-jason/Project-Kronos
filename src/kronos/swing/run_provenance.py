"""Immutable execution and market-snapshot provenance for one Swing run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock
from uuid import uuid4

from kronos.swing.daily_data import SwingDailyDataset
from kronos.swing.run_identity import is_swing_analysis_run_id


SWING_RUN_PROVENANCE_SCHEMA = "KRONOS-SWING-V1-RUN-PROVENANCE-V1"
DEFAULT_SWING_RUN_PROVENANCE_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "swing-v1"
    / "run-provenance"
)
_SNAPSHOT_ID = re.compile(r"SWING-MARKET-DATA-SNAPSHOT-[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class SwingAnalysisRunProvenance:
    """Four independent immutable identities for an executed V1 analysis."""

    run_id: str
    run_created_at: datetime
    analysis_boundary: datetime
    market_data_snapshot_identity: str
    successful_completed_at: datetime | None = None
    schema_identity: str = SWING_RUN_PROVENANCE_SCHEMA

    def __post_init__(self) -> None:
        if (
            not is_swing_analysis_run_id(self.run_id)
            or not _aware(self.run_created_at)
            or not _aware(self.analysis_boundary)
            or (
                self.successful_completed_at is not None
                and (
                    not _aware(self.successful_completed_at)
                    or self.successful_completed_at < self.run_created_at
                )
            )
            or _SNAPSHOT_ID.fullmatch(self.market_data_snapshot_identity) is None
            or self.schema_identity != SWING_RUN_PROVENANCE_SCHEMA
        ):
            raise ValueError("SWING_RUN_PROVENANCE_INVALID")


def market_data_snapshot_identity(dataset: SwingDailyDataset) -> str:
    """Return a provider-neutral digest of the exact normalized Daily dataset."""

    if type(dataset) is not SwingDailyDataset:
        raise ValueError("SWING_MARKET_DATA_SNAPSHOT_INVALID")
    payload = {
        "history_depth": dataset.history_depth,
        "records": [
            {
                "canonical_identity": record.canonical_identity,
                "asset_class": record.asset_class.value,
                "status": record.status.value,
                "observation_boundary": (
                    record.observation_boundary.isoformat()
                    if record.observation_boundary is not None
                    else None
                ),
                "failure": record.failure.value if record.failure is not None else None,
                "candles": [
                    {
                        "timestamp": candle.timestamp.isoformat(),
                        "open": candle.open,
                        "high": candle.high,
                        "low": candle.low,
                        "close": candle.close,
                        "volume": candle.volume,
                    }
                    for candle in record.candles
                ],
            }
            for record in dataset.records
        ],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"SWING-MARKET-DATA-SNAPSHOT-{sha256(canonical).hexdigest()}"


class LocalSwingRunProvenanceStore:
    """Private append-only run provenance retained across Browser restarts."""

    def __init__(self, root: Path = DEFAULT_SWING_RUN_PROVENANCE_ROOT) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute() or root == Path("/"):
            raise ValueError("SWING_RUN_PROVENANCE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain(self, provenance: SwingAnalysisRunProvenance) -> None:
        if type(provenance) is not SwingAnalysisRunProvenance:
            raise ValueError("SWING_RUN_PROVENANCE_INVALID")
        with self._lock:
            destination = self._path(provenance.run_id)
            if destination.exists():
                if self.load(provenance.run_id) != provenance:
                    raise ValueError("SWING_RUN_PROVENANCE_IMMUTABLE")
                return
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                os.chmod(destination.parent, 0o700)
            except OSError:
                pass
            temporary = destination.with_name(
                f".{destination.name}.{uuid4().hex}.tmp"
            )
            payload = json.dumps(
                _to_dict(provenance),
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            try:
                descriptor = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, destination)
            finally:
                if temporary.exists():
                    temporary.unlink()

    def load(self, run_id: str) -> SwingAnalysisRunProvenance:
        if not is_swing_analysis_run_id(run_id):
            raise ValueError("SWING_ANALYSIS_RUN_IDENTITY_INVALID")
        with self._lock:
            path = self._path(run_id)
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError("SWING_RUN_PROVENANCE_UNAVAILABLE") from error
            try:
                provenance = SwingAnalysisRunProvenance(
                    run_id=payload["run_id"],
                    run_created_at=datetime.fromisoformat(payload["run_created_at"]),
                    analysis_boundary=datetime.fromisoformat(
                        payload["analysis_boundary"]
                    ),
                    market_data_snapshot_identity=payload[
                        "market_data_snapshot_identity"
                    ],
                    successful_completed_at=(
                        datetime.fromisoformat(payload["successful_completed_at"])
                        if payload.get("successful_completed_at") is not None
                        else None
                    ),
                    schema_identity=payload["schema_identity"],
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("SWING_RUN_PROVENANCE_INVALID") from error
            if provenance.run_id != run_id:
                raise ValueError("SWING_RUN_PROVENANCE_BINDING_MISMATCH")
            return provenance

    def latest(self) -> SwingAnalysisRunProvenance | None:
        """Return the latest valid successful run without mutating the store."""

        with self._lock:
            candidates = []
            for path in self._root.glob("SWING-RUN-*/run-provenance.json"):
                try:
                    provenance = self.load(path.parent.name)
                except ValueError:
                    continue
                if provenance.successful_completed_at is not None:
                    candidates.append(provenance)
            return max(
                candidates,
                key=lambda item: (item.successful_completed_at, item.run_id),
                default=None,
            )

    def _path(self, run_id: str) -> Path:
        return self._root / run_id / "run-provenance.json"


def _to_dict(provenance: SwingAnalysisRunProvenance) -> dict[str, str | None]:
    return {
        "schema_identity": provenance.schema_identity,
        "run_id": provenance.run_id,
        "run_created_at": provenance.run_created_at.isoformat(),
        "analysis_boundary": provenance.analysis_boundary.isoformat(),
        "market_data_snapshot_identity": provenance.market_data_snapshot_identity,
        "successful_completed_at": (
            provenance.successful_completed_at.isoformat()
            if provenance.successful_completed_at is not None
            else None
        ),
    }


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


__all__ = [
    "DEFAULT_SWING_RUN_PROVENANCE_ROOT",
    "LocalSwingRunProvenanceStore",
    "SWING_RUN_PROVENANCE_SCHEMA",
    "SwingAnalysisRunProvenance",
    "market_data_snapshot_identity",
]
