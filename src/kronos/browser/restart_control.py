"""Private process-owned control record for safe KRONOS Browser restart."""

from __future__ import annotations

from dataclasses import dataclass, field
import hmac
import os
from pathlib import Path
import re
import secrets
import stat
from uuid import uuid4
from datetime import UTC, datetime
from kronos.common.maintenance import publish_drain_handoff, publish_handoff


BACKEND_CONTROL_SCHEMA = "KRONOS_BROWSER_BACKEND_CONTROL_V1"
DEFAULT_BACKEND_CONTROL_PATH = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "runtime"
    / "browser-backend-v1.control"
)
_TOKEN = re.compile(r"[0-9a-f]{64}\Z")


def _recovery_parent(path: Path) -> int:
    """Walk the fixed control parent without following any symlink."""
    if not path.is_absolute() or ".." in path.parts or path.name in {"", ".", ".."}:
        raise ValueError("FAILED_FENCED_CONTROL_CUSTODY_INVALID")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(path.anchor, flags)
    try:
        for component in path.parent.parts[1:]:
            child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        _recovery_parent_identity(fd)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _recovery_parent_identity(fd: int) -> tuple[int, ...]:
    info = os.fstat(fd)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError("FAILED_FENCED_CONTROL_CUSTODY_INVALID")
    # Directory link counts/timestamps can change because of this operation's
    # own unlink. Its identity, ownership and permission metadata cannot.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def _recovery_file_identity(info) -> tuple[int, ...]:
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise ValueError("FAILED_FENCED_CONTROL_CUSTODY_INVALID")
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _recovery_check_parent(path: Path, parent: int, expected: tuple[int, ...]) -> None:
    if _recovery_parent_identity(parent) != expected:
        raise ValueError("FAILED_FENCED_CONTROL_CUSTODY_INVALID")
    reopened = _recovery_parent(path)
    try:
        if _recovery_parent_identity(reopened) != expected:
            raise ValueError("FAILED_FENCED_CONTROL_CUSTODY_INVALID")
    finally:
        os.close(reopened)


def _recovery_check_named(parent: int, name: str, fd: int,
                          expected: tuple[int, ...]) -> None:
    actual = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if (_recovery_file_identity(actual) != expected
            or _recovery_file_identity(os.fstat(fd)) != expected):
        raise ValueError("FAILED_FENCED_CONTROL_CUSTODY_INVALID")


@dataclass(slots=True)
class BrowserBackendRestartControl:
    """One-use-at-a-time shutdown authority owned by the active process."""

    path: Path
    process_id: int
    _token: str
    _ff_composition: object = field(default=None, init=False, repr=False, compare=False)
    _ff_callback_lock: object = field(default=None, init=False, repr=False, compare=False)
    _ff_active_callbacks: int = field(default=0, init=False, repr=False, compare=False)
    _ff_callback_failed: bool = field(default=False, init=False, repr=False, compare=False)
    _ff_control_removed: bool = field(default=False, init=False, repr=False, compare=False)
    _ff_control_parent: tuple[int, ...] | None = field(default=None, init=False, repr=False, compare=False)

    @classmethod
    def create(
        cls,
        path: Path = DEFAULT_BACKEND_CONTROL_PATH,
        *,
        process_id: int | None = None,
        token: str | None = None,
    ) -> BrowserBackendRestartControl:
        resolved = Path(path).expanduser()
        pid = os.getpid() if process_id is None else process_id
        value = secrets.token_hex(32) if token is None else token
        if (
            not resolved.is_absolute()
            or resolved == Path("/")
            or type(pid) is not int
            or pid < 2
            or _TOKEN.fullmatch(value) is None
        ):
            raise ValueError("BROWSER_BACKEND_CONTROL_INVALID")
        control = cls(resolved, pid, value)
        from kronos.application.failed_fenced_owners import (
            active_composition, register_owner,
        )
        register_owner("CONTROL", control, __file__)
        composition = active_composition()
        if composition is not None:
            composition.resource(control, control.path, "CONTROL_FILE",
                parent=composition.resource_identity(control),
                cleanup_action="REMOVE_CONTROL", cleanup=control.remove_for_recovery)
        control._publish()
        return control

    def authorized(self, *, process_id: str | None, token: str | None) -> bool:
        """Accept only the exact active-process binding and private token."""

        if process_id is None or token is None:
            return False
        return hmac.compare_digest(process_id, str(self.process_id)) and (
            hmac.compare_digest(token, self._token)
        )

    def owns_current_process(self) -> bool:
        """Prove that this control record belongs to the calling KRONOS process."""

        if self.process_id != os.getpid():
            return False
        try:
            return hmac.compare_digest(
                self.path.read_text(encoding="ascii"),
                self._serialized(),
            )
        except OSError:
            return False

    def maintenance_handoff(self, generation: str, runtime_identity: str) -> None:
        if not self.owns_current_process():
            raise ValueError("MAINTENANCE_FOREIGN_PROCESS")
        publish_handoff(self.path.parent / "maintenance", generation=generation,
            parent_pid=self.process_id, proof=self._token,
            runtime_identity=runtime_identity, now=datetime.now(UTC))

    def maintenance_drain_handoff(self, generation: str, runtime_identity: str,
                                  loaded_revision: str,
                                  drain: dict[str, int]) -> None:
        if not self.owns_current_process():
            raise ValueError("MAINTENANCE_FOREIGN_PROCESS")
        publish_drain_handoff(
            self.path.parent / "maintenance", generation=generation,
            parent_pid=self.process_id, proof=self._token,
            runtime_identity=runtime_identity, loaded_revision=loaded_revision,
            drain=drain, now=datetime.now(UTC),
        )

    def remove(self) -> None:
        """Remove only this process's still-matching control record."""
        if self._ff_composition is not None and self._ff_composition._journal_registered:
            from kronos.application.failed_fenced_owners import recorded_cleanup
            recorded_cleanup("REMOVE_CONTROL")(type(self).remove_for_recovery)(self)
            return
        try:
            if self.path.read_text(encoding="ascii") != self._serialized():
                return
            self.path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def private_bytes_for_recovery(self) -> bytes:
        """Read exact private custody bytes; never return them to an HTTP client.

        Ordinary V1/V2 ownership semantics remain unchanged. R3 requires the
        stronger native file custody boundary and separately validates the
        retained controller, process birth, boot and capability proofs.
        """
        if self.process_id != os.getpid():
            raise ValueError("FAILED_FENCED_CONTROL_CUSTODY_INVALID")
        parent = _recovery_parent(self.path)
        try:
            directory = _recovery_parent_identity(parent)
            fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=parent)
            try:
                identity = _recovery_file_identity(os.fstat(fd))
                _recovery_check_named(parent, self.path.name, fd, identity)
                raw = os.read(fd, 256)
                if (os.read(fd, 1) or not hmac.compare_digest(
                        raw, self._serialized().encode("ascii"))):
                    raise ValueError("FAILED_FENCED_CONTROL_CUSTODY_INVALID")
                _recovery_check_named(parent, self.path.name, fd, identity)
                _recovery_check_parent(self.path, parent, directory)
                return raw
            finally:
                os.close(fd)
        finally:
            os.close(parent)

    def remove_for_recovery(self) -> None:
        """Strict once-only pre-SEAL native removal, with durable readback.

        A missing, replaced, permissive or foreign control is a failure. This
        operation never repairs custody and never treats a silent unlink as
        proof. Its original cleanup journal owns the once-only execution.
        """
        if self.process_id != os.getpid() or self._ff_control_removed:
            raise ValueError("FAILED_FENCED_CONTROL_CUSTODY_INVALID")
        parent = _recovery_parent(self.path)
        try:
            directory = _recovery_parent_identity(parent)
            fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=parent)
            try:
                identity = _recovery_file_identity(os.fstat(fd))
                _recovery_check_named(parent, self.path.name, fd, identity)
                if (os.read(fd, 256) != self._serialized().encode("ascii")
                        or os.read(fd, 1)):
                    raise ValueError("FAILED_FENCED_CONTROL_CUSTODY_INVALID")
                _recovery_check_named(parent, self.path.name, fd, identity)
                _recovery_check_parent(self.path, parent, directory)
                os.unlink(self.path.name, dir_fd=parent)
                os.fsync(parent)
                removed = os.fstat(fd)
                if ((removed.st_dev, removed.st_ino) != identity[:2]
                        or removed.st_nlink != 0):
                    raise ValueError("FAILED_FENCED_CONTROL_REMOVAL_UNPROVEN")
                _recovery_check_parent(self.path, parent, directory)
                try:
                    os.stat(self.path.name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    _recovery_check_parent(self.path, parent, directory)
                    self._ff_control_parent = directory
                    self._ff_control_removed = True
                    return
                else:
                    raise ValueError("FAILED_FENCED_CONTROL_REMOVAL_UNPROVEN")
            finally:
                os.close(fd)
        finally:
            os.close(parent)

    def failed_fenced_owner_status(self, owner: str) -> dict:
        if owner != "CONTROL" or self.process_id != os.getpid():
            raise ValueError("FAILED_FENCED_NATIVE_OWNER_STATUS_UNSUPPORTED")
        # This reports only native cleanup facts. Original custody/process and
        # the once-only cleanup journal must independently validate this owner.
        if self._ff_control_removed:
            parent = _recovery_parent(self.path)
            try:
                if _recovery_parent_identity(parent) != self._ff_control_parent:
                    raise ValueError("FAILED_FENCED_CONTROL_REMOVAL_UNPROVEN")
                try:
                    os.stat(self.path.name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    _recovery_check_parent(self.path, parent, self._ff_control_parent)
                else:
                    raise ValueError("FAILED_FENCED_CONTROL_REMOVAL_UNPROVEN")
            finally:
                os.close(parent)
            removed = True
        else:
            self.private_bytes_for_recovery()
            removed = False
        return {"owned_workers": 0, "queued_items": 0, "durable_writes": 0,
                "control_removed": removed}

    def _publish(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="ascii") as handle:
                handle.write(self._serialized())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _serialized(self) -> str:
        return f"{BACKEND_CONTROL_SCHEMA}\n{self.process_id}\n{self._token}\n"


__all__ = [
    "BACKEND_CONTROL_SCHEMA",
    "BrowserBackendRestartControl",
    "DEFAULT_BACKEND_CONTROL_PATH",
]
