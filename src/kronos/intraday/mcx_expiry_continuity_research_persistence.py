"""Immutable explicit-identity persistence for MCX expiry research."""

from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.mcx_expiry_continuity_research import (
    MCX_EXPIRY_CONTINUITY_IDENTITY,
    McxExpiryContinuityError,
    McxFamilyExpiryContinuityArtifact,
    mcx_expiry_continuity_bytes,
    parse_mcx_expiry_continuity,
)


DEFAULT_MCX_EXPIRY_CONTINUITY_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "intraday-v1"
    / "qualification-research"
    / "mcx-family-expiry-continuity"
)


class McxExpiryContinuityStore:
    def __init__(self, root: Path = DEFAULT_MCX_EXPIRY_CONTINUITY_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("MCX_EXPIRY_CONTINUITY_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(self, value: McxFamilyExpiryContinuityArtifact) -> Path:
        encoded = mcx_expiry_continuity_bytes(value)
        path = self.path_for(value.artifact_identity)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if path.exists():
                if path.read_bytes() != encoded:
                    raise McxExpiryContinuityError("MCX_EXPIRY_CONTINUITY_IMMUTABILITY_VIOLATION")
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
                        raise McxExpiryContinuityError("MCX_EXPIRY_CONTINUITY_IMMUTABILITY_VIOLATION")
            finally:
                temporary.unlink(missing_ok=True)
        return path

    def load(self, *, artifact_identity: str) -> McxFamilyExpiryContinuityArtifact:
        value = parse_mcx_expiry_continuity(self.path_for(artifact_identity).read_bytes())
        if value.artifact_identity != artifact_identity:
            raise McxExpiryContinuityError("MCX_EXPIRY_CONTINUITY_INTEGRITY_INVALID")
        return value

    def path_for(self, artifact_identity: str) -> Path:
        if (
            type(artifact_identity) is not str
            or not artifact_identity.startswith("INTRADAY-MCX-EXPIRY-CONTINUITY-")
            or "/" in artifact_identity
            or "\\" in artifact_identity
        ):
            raise McxExpiryContinuityError("MCX_EXPIRY_CONTINUITY_IDENTITY_INVALID")
        return self._root / MCX_EXPIRY_CONTINUITY_IDENTITY / f"{artifact_identity}.json"


__all__ = ["DEFAULT_MCX_EXPIRY_CONTINUITY_ROOT", "McxExpiryContinuityStore"]
