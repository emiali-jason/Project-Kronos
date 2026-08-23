"""Immutable explicit-identity persistence for Native Discovery V0."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.discovery import (
    DiscoveryError,
    DiscoveryFailure,
    DiscoveryMemberResult,
    NativeDiscoveryMachineFactBundle,
    NativeDiscoveryRun,
    discovery_result_bytes,
    discovery_run_bytes,
    machine_fact_bundle_bytes,
    parse_machine_fact_bundle,
    parse_discovery_result,
    parse_discovery_run,
)


DEFAULT_DISCOVERY_ROOT = Path(__file__).resolve().parents[3] / "data" / "intraday"


class NativeDiscoveryStore:
    """Retain immutable runs/results; filenames have no current-truth authority."""

    def __init__(self, root: Path = DEFAULT_DISCOVERY_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("INTRADAY_DISCOVERY_STORE_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    def retain_run(
        self,
        run: NativeDiscoveryRun,
        *,
        bundles: tuple[NativeDiscoveryMachineFactBundle, ...] = (),
    ) -> Path:
        if type(run) is not NativeDiscoveryRun:
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
        with self._lock:
            bundle_identities = {item.bundle_identity for item in bundles}
            required = {
                item.machine_fact_bundle_identity
                for item in run.results
                if item.machine_fact_bundle_identity is not None
            }
            if bundle_identities != required or any(
                type(item) is not NativeDiscoveryMachineFactBundle
                for item in bundles
            ):
                raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
            for bundle in bundles:
                self._retain(
                    self.bundle_path(bundle.bundle_identity),
                    machine_fact_bundle_bytes(bundle),
                )
            for result in run.results:
                self._retain(
                    self.result_path(result.persistence_identity),
                    discovery_result_bytes(result),
                )
            path = self.run_path(run.run_identity)
            self._retain(path, discovery_run_bytes(run))
        return path

    def retain_bundle(self, bundle: NativeDiscoveryMachineFactBundle) -> Path:
        if type(bundle) is not NativeDiscoveryMachineFactBundle:
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
        with self._lock:
            path = self.bundle_path(bundle.bundle_identity)
            self._retain(path, machine_fact_bundle_bytes(bundle))
        return path

    def retain_result(self, result: DiscoveryMemberResult) -> Path:
        if type(result) is not DiscoveryMemberResult:
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
        with self._lock:
            path = self.result_path(result.persistence_identity)
            self._retain(path, discovery_result_bytes(result))
        return path

    def load_run(self, *, run_identity: str) -> NativeDiscoveryRun:
        return parse_discovery_run(self._read(self.run_path(run_identity)))

    def load_result(self, *, persistence_identity: str) -> DiscoveryMemberResult:
        return parse_discovery_result(
            self._read(self.result_path(persistence_identity))
        )

    def load_bundle(
        self, *, bundle_identity: str
    ) -> NativeDiscoveryMachineFactBundle:
        return parse_machine_fact_bundle(
            self._read(self.bundle_path(bundle_identity))
        )

    def run_path(self, run_identity: str) -> Path:
        if not _component(run_identity) or not run_identity.startswith(
            "INTRADAY-DISCOVERY-RUN-"
        ):
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
        return self._root / "native-discovery" / "runs" / f"{run_identity}.json"

    def result_path(self, persistence_identity: str) -> Path:
        if not _component(persistence_identity) or not persistence_identity.startswith(
            "INTRADAY-DISCOVERY-RESULT-PERSISTENCE-"
        ):
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
        return (
            self._root
            / "native-discovery"
            / "results"
            / f"{persistence_identity}.json"
        )

    def bundle_path(self, bundle_identity: str) -> Path:
        if not _component(bundle_identity) or not bundle_identity.startswith(
            "INTRADAY-DISCOVERY-FACT-BUNDLE-"
        ):
            raise DiscoveryError(DiscoveryFailure.INTEGRITY_INVALID)
        return (
            self._root
            / "native-discovery"
            / "machine-fact-bundles"
            / f"{bundle_identity}.json"
        )

    def _retain(self, path: Path, encoded: bytes) -> None:
        if path.exists():
            try:
                current = path.read_bytes()
            except OSError as error:
                raise DiscoveryError(DiscoveryFailure.PUBLICATION_UNAVAILABLE) from error
            if current != encoded:
                raise DiscoveryError(DiscoveryFailure.PERSISTENCE_CONFLICT)
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
            raise DiscoveryError(DiscoveryFailure.PUBLICATION_UNAVAILABLE) from error


def _component(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value == value.strip()
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
    )


__all__ = ["DEFAULT_DISCOVERY_ROOT", "NativeDiscoveryStore"]
