"""Immutable explicit-identity persistence for production Intraday Probables."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.probables import (
    ProbablesError,
    ProbablesFailure,
    ProbablesMethodologyPublication,
    ProbablesRun,
    probables_artifact_bytes,
    probables_artifact_from_bytes,
)


DEFAULT_PROBABLES_ROOT = Path(__file__).resolve().parents[3] / "data" / "intraday"


class ProbablesStore:
    """Append-only methodology/run store with no latest-file authority."""

    def __init__(self, root: Path = DEFAULT_PROBABLES_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_PROBABLES_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    def retain_methodology(self, value: ProbablesMethodologyPublication) -> Path:
        if type(value) is not ProbablesMethodologyPublication:
            raise ProbablesError(ProbablesFailure.INPUT_INVALID)
        path = self.methodology_path(value.publication_identity)
        with self._lock:
            self._retain(path, probables_artifact_bytes(value))
        return path

    def retain_run(self, value: ProbablesRun) -> Path:
        if type(value) is not ProbablesRun:
            raise ProbablesError(ProbablesFailure.INPUT_INVALID)
        with self._lock:
            for result in value.results:
                self._retain(
                    self.result_path(result.result_identity),
                    probables_artifact_bytes(result),
                )
            self._retain(
                self.diagnostics_path(value.diagnostics.diagnostics_identity),
                probables_artifact_bytes(value.diagnostics),
            )
            path = self.run_path(value.run_identity)
            self._retain(path, probables_artifact_bytes(value))
        return path

    def load_methodology(self, *, publication_identity: str) -> ProbablesMethodologyPublication:
        value = probables_artifact_from_bytes(self._read(self.methodology_path(publication_identity)))
        if type(value) is not ProbablesMethodologyPublication or value.publication_identity != publication_identity:
            raise ProbablesError(ProbablesFailure.INTEGRITY_INVALID)
        return value

    def load_run(self, *, run_identity: str) -> ProbablesRun:
        value = probables_artifact_from_bytes(self._read(self.run_path(run_identity)))
        if type(value) is not ProbablesRun or value.run_identity != run_identity:
            raise ProbablesError(ProbablesFailure.INTEGRITY_INVALID)
        return value

    def load_result(self, *, result_identity: str):  # type: ignore[no-untyped-def]
        from kronos.intraday.probables import ProbableMemberResult

        value = probables_artifact_from_bytes(self._read(self.result_path(result_identity)))
        if type(value) is not ProbableMemberResult or value.result_identity != result_identity:
            raise ProbablesError(ProbablesFailure.INTEGRITY_INVALID)
        return value

    def load_diagnostics(self, *, diagnostics_identity: str):  # type: ignore[no-untyped-def]
        from kronos.intraday.probables import ProbablesPopulationDiagnostics

        value = probables_artifact_from_bytes(
            self._read(self.diagnostics_path(diagnostics_identity))
        )
        if (
            type(value) is not ProbablesPopulationDiagnostics
            or value.diagnostics_identity != diagnostics_identity
        ):
            raise ProbablesError(ProbablesFailure.INTEGRITY_INVALID)
        return value

    def methodology_path(self, identity: str) -> Path:
        return self._path("methodologies", identity, "INTRADAY-PROBABLES-METHODOLOGY-")

    def run_path(self, identity: str) -> Path:
        return self._path("runs", identity, "INTRADAY-PROBABLES-RUN-")

    def result_path(self, identity: str) -> Path:
        return self._path("results", identity, "INTRADAY-PROBABLE-RESULT-")

    def diagnostics_path(self, identity: str) -> Path:
        return self._path("diagnostics", identity, "INTRADAY-PROBABLES-DIAGNOSTICS-")

    def _path(self, family: str, identity: str, prefix: str) -> Path:
        if not _component(identity) or not identity.startswith(prefix):
            raise ProbablesError(ProbablesFailure.INTEGRITY_INVALID)
        return self._root / "probables-v1" / family / f"{identity}.json"

    @staticmethod
    def _retain(path: Path, encoded: bytes) -> None:
        if path.exists():
            try:
                current = path.read_bytes()
            except OSError as error:
                raise ProbablesError(ProbablesFailure.ARTIFACT_UNAVAILABLE) from error
            if current != encoded:
                raise ProbablesError(ProbablesFailure.PERSISTENCE_CONFLICT)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(encoded)
            temporary.replace(path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _read(path: Path) -> bytes:
        try:
            return path.read_bytes()
        except OSError as error:
            raise ProbablesError(ProbablesFailure.ARTIFACT_UNAVAILABLE) from error


def _component(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value == value.strip()
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
    )


__all__ = ["DEFAULT_PROBABLES_ROOT", "ProbablesStore"]
