"""Append-only persistence for immutable DOMAIN-006 Provider snapshots."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.provider.contracts.instrument_master import (
    ProviderInstrumentMasterError,
    ProviderInstrumentMasterFailure,
)
from kronos.provider.instrument_master import (
    ProviderInstrumentSnapshot,
    encode_provider_instrument_snapshot,
    parse_provider_instrument_snapshot,
)


DEFAULT_PROVIDER_INSTRUMENT_SNAPSHOT_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "provider"
    / "instrument-master"
)


class ProviderInstrumentSnapshotStore:
    """Retain and load explicit identities; directory order has no authority."""

    __slots__ = ("_lock", "_root")

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("PROVIDER_INSTRUMENT_SNAPSHOT_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(self, snapshot: ProviderInstrumentSnapshot) -> Path:
        if type(snapshot) is not ProviderInstrumentSnapshot:
            raise ProviderInstrumentMasterError(
                ProviderInstrumentMasterFailure.SNAPSHOT_SCHEMA_INVALID
            )
        encoded = encode_provider_instrument_snapshot(snapshot)
        path = self.path_for(
            provider=snapshot.provider,
            dataset_identity=snapshot.dataset_identity,
            snapshot_identity=snapshot.snapshot_identity,
        )
        with self._lock:
            temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
            try:
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with temporary.open("xb") as stream:
                    temporary.chmod(0o600)
                    stream.write(encoded)
                    stream.flush()
                try:
                    path.hardlink_to(temporary)
                except FileExistsError:
                    existing = path.read_bytes()
                    if existing != encoded:
                        raise ProviderInstrumentMasterError(
                            ProviderInstrumentMasterFailure.SNAPSHOT_CONFLICT
                        )
                    parse_provider_instrument_snapshot(existing)
            except ProviderInstrumentMasterError:
                raise
            except OSError as error:
                raise ProviderInstrumentMasterError(
                    ProviderInstrumentMasterFailure.PERSISTENCE_FAILED
                ) from error
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        return path

    def load(
        self,
        *,
        provider: str,
        dataset_identity: str,
        snapshot_identity: str,
    ) -> ProviderInstrumentSnapshot:
        path = self.path_for(
            provider=provider,
            dataset_identity=dataset_identity,
            snapshot_identity=snapshot_identity,
        )
        with self._lock:
            try:
                encoded = path.read_bytes()
            except OSError as error:
                raise ProviderInstrumentMasterError(
                    ProviderInstrumentMasterFailure.PERSISTENCE_FAILED
                ) from error
        snapshot = parse_provider_instrument_snapshot(encoded)
        if (
            snapshot.provider != provider
            or snapshot.dataset_identity != dataset_identity
            or snapshot.snapshot_identity != snapshot_identity
        ):
            raise ProviderInstrumentMasterError(
                ProviderInstrumentMasterFailure.SNAPSHOT_INTEGRITY_INVALID
            )
        return snapshot

    def path_for(
        self,
        *,
        provider: str,
        dataset_identity: str,
        snapshot_identity: str,
    ) -> Path:
        if not all(_safe_component(item) for item in (
            provider,
            dataset_identity,
            snapshot_identity,
        )):
            raise ValueError("PROVIDER_INSTRUMENT_SNAPSHOT_IDENTITY_INVALID")
        return self._root / provider / dataset_identity / f"{snapshot_identity}.json"


def _safe_component(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and "/" not in value
        and "\\" not in value
        and value not in {".", ".."}
    )


__all__ = [
    "DEFAULT_PROVIDER_INSTRUMENT_SNAPSHOT_ROOT",
    "ProviderInstrumentSnapshotStore",
]
