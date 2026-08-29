"""Immutable persistence for the research-only MCX historical corpus."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.mcx_historical_research import (
    MCX_HISTORICAL_RESEARCH_CORPUS_IDENTITY,
    McxHistoricalResearchCorpus,
    McxHistoricalResearchError,
    McxHistoricalResearchFailure,
    mcx_historical_research_corpus_bytes,
    parse_mcx_historical_research_corpus,
)


DEFAULT_MCX_HISTORICAL_RESEARCH_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "intraday-v1"
    / "qualification-research"
    / "mcx-v2-historical-corpus"
)


class McxHistoricalResearchCorpusStore:
    """Retain and reload only by explicit immutable corpus identity."""

    def __init__(self, root: Path = DEFAULT_MCX_HISTORICAL_RESEARCH_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("MCX_HISTORICAL_RESEARCH_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(self, value: McxHistoricalResearchCorpus) -> Path:
        if type(value) is not McxHistoricalResearchCorpus:
            raise McxHistoricalResearchError(
                McxHistoricalResearchFailure.INPUT_INVALID
            )
        encoded = mcx_historical_research_corpus_bytes(value)
        path = self.path_for(value.corpus_identity)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if path.exists():
                if path.read_bytes() != encoded:
                    raise McxHistoricalResearchError(
                        McxHistoricalResearchFailure.INTEGRITY_INVALID
                    )
                parse_mcx_historical_research_corpus(encoded)
                return path
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            try:
                with temporary.open("xb") as stream:
                    temporary.chmod(0o600)
                    stream.write(encoded)
                    stream.flush()
                try:
                    path.hardlink_to(temporary)
                except FileExistsError:
                    if path.read_bytes() != encoded:
                        raise McxHistoricalResearchError(
                            McxHistoricalResearchFailure.INTEGRITY_INVALID
                        )
            finally:
                temporary.unlink(missing_ok=True)
        return path

    def load(self, *, corpus_identity: str) -> McxHistoricalResearchCorpus:
        path = self.path_for(corpus_identity)
        try:
            value = parse_mcx_historical_research_corpus(path.read_bytes())
        except McxHistoricalResearchError:
            raise
        except OSError as error:
            raise McxHistoricalResearchError(
                McxHistoricalResearchFailure.SNAPSHOT_UNAVAILABLE
            ) from error
        if value.corpus_identity != corpus_identity:
            raise McxHistoricalResearchError(
                McxHistoricalResearchFailure.INTEGRITY_INVALID
            )
        return value

    def path_for(self, corpus_identity: str) -> Path:
        if not _component(corpus_identity):
            raise McxHistoricalResearchError(
                McxHistoricalResearchFailure.INPUT_INVALID
            )
        return (
            self._root
            / MCX_HISTORICAL_RESEARCH_CORPUS_IDENTITY
            / f"{corpus_identity}.json"
        )


def _component(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value == value.strip()
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
    )


__all__ = [
    "DEFAULT_MCX_HISTORICAL_RESEARCH_ROOT",
    "McxHistoricalResearchCorpusStore",
]
