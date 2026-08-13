"""Private process-owned control record for safe KRONOS Browser restart."""

from __future__ import annotations

from dataclasses import dataclass
import hmac
import os
from pathlib import Path
import re
import secrets
from uuid import uuid4


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


@dataclass(slots=True)
class BrowserBackendRestartControl:
    """One-use-at-a-time shutdown authority owned by the active process."""

    path: Path
    process_id: int
    _token: str

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
        control._publish()
        return control

    def authorized(self, *, process_id: str | None, token: str | None) -> bool:
        """Accept only the exact active-process binding and private token."""

        if process_id is None or token is None:
            return False
        return hmac.compare_digest(process_id, str(self.process_id)) and (
            hmac.compare_digest(token, self._token)
        )

    def remove(self) -> None:
        """Remove only this process's still-matching control record."""

        try:
            if self.path.read_text(encoding="ascii") != self._serialized():
                return
            self.path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

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
