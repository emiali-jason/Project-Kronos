"""Append-only restart persistence for Slice 1E factual context."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.context import (
    Slice1EContext,
    slice1e_document,
    slice1e_from_document,
)


class LocalSlice1EContextStore:
    """Retain and load immutable evidence by explicit immutable identities."""

    def __init__(self, root: Path) -> None:
        root = Path(root).expanduser()
        if not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_SLICE_1E_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    @property
    def root(self) -> Path:
        return self._root

    def retain(self, evidence: Slice1EContext) -> None:
        if type(evidence) is not Slice1EContext:
            raise ValueError("INTRADAY_SLICE_1E_CONTEXT_INVALID")
        path = self._path(
            run_id=evidence.run.run_id,
            mapping_identity=evidence.instrument.mapping_identity,
            trading_date=evidence.previous_session.current_trading_date.isoformat(),
            evidence_id=evidence.evidence_id,
        )
        encoded = _encode(evidence)
        with self._lock:
            if path.exists():
                if path.read_bytes() != encoded:
                    raise ValueError("INTRADAY_SLICE_1E_EVIDENCE_IMMUTABLE")
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
        evidence_id: str,
    ) -> Slice1EContext:
        if not all(
            isinstance(item, str) and item
            for item in (run_id, mapping_identity, trading_date, evidence_id)
        ):
            raise ValueError("INTRADAY_SLICE_1E_IDENTITY_INVALID")
        path = self._path(
            run_id=run_id,
            mapping_identity=mapping_identity,
            trading_date=trading_date,
            evidence_id=evidence_id,
        )
        with self._lock:
            try:
                encoded = path.read_bytes()
                document = json.loads(encoded)
                evidence = slice1e_from_document(document)
            except (OSError, json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError) as error:
                raise ValueError("INTRADAY_SLICE_1E_EVIDENCE_UNAVAILABLE_OR_INVALID") from error
        if (
            evidence.run.run_id != run_id
            or evidence.instrument.mapping_identity != mapping_identity
            or evidence.previous_session.current_trading_date.isoformat() != trading_date
            or evidence.evidence_id != evidence_id
            or _encode(evidence) != encoded
        ):
            raise ValueError("INTRADAY_SLICE_1E_EVIDENCE_INTEGRITY_MISMATCH")
        return evidence

    def _path(
        self, *, run_id: str, mapping_identity: str, trading_date: str, evidence_id: str
    ) -> Path:
        return self._root / run_id / mapping_identity / trading_date / f"{evidence_id}.json"


def _encode(evidence: Slice1EContext) -> bytes:
    return json.dumps(
        slice1e_document(evidence), ensure_ascii=True, indent=2, sort_keys=True
    ).encode("utf-8")


__all__ = ["LocalSlice1EContextStore"]
