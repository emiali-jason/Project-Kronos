"""Immutable persistence for explicit Intraday Native universe versions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import RLock

from kronos.intraday.universe import (
    INTRADAY_NATIVE_UNIVERSE_IDENTITY,
    IntradayUniverseError,
    IntradayUniverseFailure,
    IntradayUniversePublication,
    parse_intraday_universe_publication,
    seal_intraday_universe_document,
)


class IntradayUniversePublicationStore:
    """Retain and resolve explicit versions; there is no latest-file authority."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("INTRADAY_UNIVERSE_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    def retain_source(self, document: dict[str, object]) -> IntradayUniversePublication:
        encoded = seal_intraday_universe_document(document)
        publication = parse_intraday_universe_publication(encoded)
        path = self._path(publication.publication_version)
        with self._lock:
            if path.exists():
                try:
                    existing = path.read_bytes()
                except OSError as error:
                    raise ValueError("INTRADAY_UNIVERSE_STORE_UNAVAILABLE") from error
                if existing != encoded:
                    raise IntradayUniverseError(IntradayUniverseFailure.VERSION_CONFLICT)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(".tmp")
                temporary.write_bytes(encoded)
                temporary.replace(path)
        return publication

    def load(self, *, publication_version: str) -> IntradayUniversePublication:
        path = self._path(publication_version)
        with self._lock:
            try:
                encoded = path.read_bytes()
            except OSError as error:
                raise IntradayUniverseError(
                    IntradayUniverseFailure.PUBLICATION_UNAVAILABLE
                ) from error
        return parse_intraday_universe_publication(encoded)

    def resolve_at(
        self,
        *,
        publication_versions: tuple[str, ...],
        observed_at: datetime,
    ) -> IntradayUniversePublication:
        """Resolve among caller-governed versions, never directory ordering."""

        if (
            not publication_versions
            or len(set(publication_versions)) != len(publication_versions)
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
        ):
            raise ValueError("INTRADAY_UNIVERSE_HISTORY_REQUEST_INVALID")
        candidates = tuple(
            publication
            for publication in (
                self.load(publication_version=version)
                for version in publication_versions
            )
            if publication.valid_from <= observed_at <= publication.valid_through
        )
        if len(candidates) != 1:
            failure = (
                IntradayUniverseFailure.VERSION_CONFLICT
                if len(candidates) > 1
                else IntradayUniverseFailure.PUBLICATION_STALE
            )
            raise IntradayUniverseError(failure)
        return candidates[0]

    def _path(self, version: str) -> Path:
        if (
            type(version) is not str
            or len(version.split(".")) != 3
            or not all(part.isdigit() for part in version.split("."))
        ):
            raise ValueError("INTRADAY_UNIVERSE_VERSION_INVALID")
        return self._root / INTRADAY_NATIVE_UNIVERSE_IDENTITY / f"{version}.json"


__all__ = ["IntradayUniversePublicationStore"]
