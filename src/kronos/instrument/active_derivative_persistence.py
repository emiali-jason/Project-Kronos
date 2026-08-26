"""Immutable explicit-identity persistence for ADR-0017 bindings."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.instrument.active_derivative import (
    ActiveDerivativeBindingArtifact,
    ActiveDerivativeSelectionError,
    ActiveDerivativeSelectionFailure,
    active_derivative_binding_bytes,
    parse_active_derivative_binding,
)


DEFAULT_ACTIVE_DERIVATIVE_BINDING_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "instrument"
    / "active-derivative-bindings"
)


class ActiveDerivativeBindingStore:
    """Retain immutable bindings and one integrity-bound operational pointer."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("ACTIVE_DERIVATIVE_BINDING_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(self, value: ActiveDerivativeBindingArtifact) -> Path:
        if type(value) is not ActiveDerivativeBindingArtifact:
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.INTEGRITY_INVALID
            )
        encoded = active_derivative_binding_bytes(value)
        target = self.path_for(value.binding_identity)
        with self._lock:
            self._retain_immutable(target, encoded)
            self._write_current_pointer(value)
        return target

    def load(self, *, binding_identity: str) -> ActiveDerivativeBindingArtifact:
        target = self.path_for(binding_identity)
        try:
            return parse_active_derivative_binding(target.read_bytes())
        except ActiveDerivativeSelectionError:
            raise
        except OSError as error:
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.ACTIVE_BINDING_UNAVAILABLE
            ) from error

    def load_current(
        self,
        *,
        canonical_subject_id: str,
    ) -> ActiveDerivativeBindingArtifact | None:
        if not _component(canonical_subject_id):
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.INTEGRITY_INVALID
            )
        pointer = self._root / "current" / f"{canonical_subject_id}.json"
        if not pointer.exists():
            return None
        try:
            raw = pointer.read_bytes()
            import json

            document = json.loads(raw)
            expected = _pointer_identity(
                canonical_subject_id=document["canonical_subject_id"],
                binding_identity=document["binding_identity"],
                binding_integrity_identity=document["binding_integrity_identity"],
            )
            if (
                document["canonical_subject_id"] != canonical_subject_id
                or document["pointer_integrity_identity"] != expected
            ):
                raise ValueError
            value = self.load(binding_identity=document["binding_identity"])
            if (
                value.canonical_subject_id != canonical_subject_id
                or value.integrity_identity
                != document["binding_integrity_identity"]
            ):
                raise ValueError
            return value
        except ActiveDerivativeSelectionError:
            raise
        except Exception as error:
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.INTEGRITY_INVALID
            ) from error

    def path_for(self, binding_identity: str) -> Path:
        if not _component(binding_identity):
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.INTEGRITY_INVALID
            )
        return self._root / "bindings" / f"{binding_identity}.json"

    def _retain_immutable(self, target: Path, encoded: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = target.parent / f".{target.name}.{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as stream:
                temporary.chmod(0o600)
                stream.write(encoded)
                stream.flush()
            try:
                target.hardlink_to(temporary)
            except FileExistsError:
                if target.read_bytes() != encoded:
                    raise ActiveDerivativeSelectionError(
                        ActiveDerivativeSelectionFailure.INTEGRITY_INVALID
                    )
                parse_active_derivative_binding(target.read_bytes())
        finally:
            temporary.unlink(missing_ok=True)

    def _write_current_pointer(self, value: ActiveDerivativeBindingArtifact) -> None:
        import json

        pointer = self._root / "current" / f"{value.canonical_subject_id}.json"
        pointer.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        document = {
            "canonical_subject_id": value.canonical_subject_id,
            "binding_identity": value.binding_identity,
            "binding_integrity_identity": value.integrity_identity,
        }
        document["pointer_integrity_identity"] = _pointer_identity(**document)
        encoded = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
        temporary = pointer.parent / f".{pointer.name}.{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as stream:
                temporary.chmod(0o600)
                stream.write(encoded)
                stream.flush()
            temporary.replace(pointer)
        finally:
            temporary.unlink(missing_ok=True)


def _pointer_identity(
    *,
    canonical_subject_id: str,
    binding_identity: str,
    binding_integrity_identity: str,
) -> str:
    from hashlib import sha256

    encoded = "\x1f".join((
        canonical_subject_id,
        binding_identity,
        binding_integrity_identity,
    )).encode("ascii")
    return "ACTIVE-DERIVATIVE-POINTER-" + sha256(encoded).hexdigest()


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
    "ActiveDerivativeBindingStore",
    "DEFAULT_ACTIVE_DERIVATIVE_BINDING_ROOT",
]
