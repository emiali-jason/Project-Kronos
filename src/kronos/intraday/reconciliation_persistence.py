"""Immutable explicit-version persistence for Intraday reconciliation."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.reconciliation import (
    RECONCILIATION_IDENTITY,
    ReconciliationError,
    ReconciliationFailure,
    ReconciliationPublication,
    parse_reconciliation_publication,
    reconciliation_publication_bytes,
)


DEFAULT_RECONCILIATION_ROOT = Path(__file__).resolve().parents[3] / "data" / "intraday"


class IntradayReconciliationStore:
    """Retain immutable versions; directory order has no resolution authority."""

    def __init__(self, root: Path = DEFAULT_RECONCILIATION_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_RECONCILIATION_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    def path_for(self, *, publication_identity: str, publication_version: str) -> Path:
        if publication_identity != RECONCILIATION_IDENTITY or not _version(publication_version):
            raise ReconciliationError(ReconciliationFailure.INPUT_INVALID)
        return self._root / publication_identity / f"{publication_version}.json"

    def retain(self, publication: ReconciliationPublication) -> Path:
        if type(publication) is not ReconciliationPublication:
            raise ReconciliationError(ReconciliationFailure.INPUT_INVALID)
        target = self.path_for(
            publication_identity=publication.publication_identity,
            publication_version=publication.publication_version,
        )
        encoded = reconciliation_publication_bytes(publication)
        with self._lock:
            if target.exists():
                try:
                    current = target.read_bytes()
                except OSError as error:
                    raise ReconciliationError(ReconciliationFailure.PUBLICATION_UNAVAILABLE) from error
                if current != encoded:
                    raise ReconciliationError(ReconciliationFailure.VERSION_CONFLICT)
                return target
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
            try:
                temporary.write_bytes(encoded)
                temporary.replace(target)
            finally:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
        return target

    def load(
        self, *, publication_identity: str, publication_version: str
    ) -> ReconciliationPublication:
        target = self.path_for(
            publication_identity=publication_identity,
            publication_version=publication_version,
        )
        with self._lock:
            try:
                encoded = target.read_bytes()
            except OSError as error:
                raise ReconciliationError(ReconciliationFailure.PUBLICATION_UNAVAILABLE) from error
        return parse_reconciliation_publication(encoded)


def _version(value: object) -> bool:
    return (
        type(value) is str
        and len(value.split(".")) == 3
        and all(part.isdigit() for part in value.split("."))
    )


__all__ = ["DEFAULT_RECONCILIATION_ROOT", "IntradayReconciliationStore"]
