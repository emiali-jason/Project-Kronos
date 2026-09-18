"""Immutable explicit-identity persistence for ADR-0017 bindings."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from threading import RLock
from weakref import WeakValueDictionary
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


_PAGE_LOCKS = WeakValueDictionary()
_PAGE_LOCKS_GUARD = RLock()


_PAGE_READ = ContextVar(__name__ + ".page_read", default=None)


def _page_bytes(path):
    scope = _PAGE_READ.get()
    return path.read_bytes() if scope is None else scope.read(path)


def _page_exists(path):
    scope = _PAGE_READ.get()
    return path.exists() if scope is None else scope.exists(path)


def _page_changed():
    scope = _PAGE_READ.get()
    if scope is not None:
        scope.invalidate()


def _page_once(method):
    @wraps(method)
    def selected(self, *args, **kwargs):
        scope = _PAGE_READ.get()
        if scope is None:
            return method(self, *args, **kwargs)
        return scope.memo((method, self, args, tuple(kwargs.items())),
                          lambda: method(self, *args, **kwargs))
    return selected


class ActiveDerivativeBindingStore:
    """Retain immutable bindings and one integrity-bound operational pointer."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError("ACTIVE_DERIVATIVE_BINDING_ROOT_INVALID")
        self._root = root
        with _PAGE_LOCKS_GUARD:
            self._lock = _PAGE_LOCKS.setdefault(root.resolve(), RLock())

    @contextmanager
    def page_read_scope(self, scope):
        """Caller-owned byte reuse; no authority, publication or rebuilding."""
        with self._lock:
            token = _PAGE_READ.set(scope)
            try:
                yield
            finally:
                _PAGE_READ.reset(token)

    def retain(self, value: ActiveDerivativeBindingArtifact) -> Path:
        if type(value) is not ActiveDerivativeBindingArtifact:
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.INTEGRITY_INVALID
            )
        encoded = active_derivative_binding_bytes(value)
        target = self.path_for(value.binding_identity)
        with self._lock:
            _page_changed()
            self._retain_immutable(target, encoded)
            self._write_current_pointer(value)
        return target

    @_page_once
    def load(self, *, binding_identity: str) -> ActiveDerivativeBindingArtifact:
        target = self.path_for(binding_identity)
        try:
            return parse_active_derivative_binding(_page_bytes(target))
        except ActiveDerivativeSelectionError:
            raise
        except OSError as error:
            raise ActiveDerivativeSelectionError(
                ActiveDerivativeSelectionFailure.ACTIVE_BINDING_UNAVAILABLE
            ) from error

    @_page_once
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
        if not _page_exists(pointer):
            return None
        try:
            raw = _page_bytes(pointer)
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
                if _page_bytes(target) != encoded:
                    raise ActiveDerivativeSelectionError(
                        ActiveDerivativeSelectionFailure.INTEGRITY_INVALID
                    )
                parse_active_derivative_binding(_page_bytes(target))
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
