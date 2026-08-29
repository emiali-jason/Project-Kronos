"""Explicit-identity persistence for MCX continuous research artifacts."""

from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.intraday.mcx_continuous_research import (
    MCX_CONTINUOUS_RESEARCH_IDENTITY,
    McxContinuousResearchArtifact,
    McxContinuousResearchError,
    mcx_continuous_research_bytes,
    parse_mcx_continuous_research,
)


DEFAULT_MCX_CONTINUOUS_RESEARCH_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "KRONOS"
    / "evidence"
    / "intraday-v1"
    / "qualification-research"
    / "mcx-v2-continuous-research"
)


class McxContinuousResearchStore:
    def __init__(self, root: Path = DEFAULT_MCX_CONTINUOUS_RESEARCH_ROOT) -> None:
        if not isinstance(root, Path) or not root.is_absolute() or root == Path("/"):
            raise ValueError("MCX_CONTINUOUS_RESEARCH_ROOT_INVALID")
        self._root = root
        self._lock = RLock()

    def retain(self, value: McxContinuousResearchArtifact) -> Path:
        encoded = mcx_continuous_research_bytes(value)
        path = self.path_for(value.artifact_identity)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if path.exists():
                if path.read_bytes() != encoded:
                    raise McxContinuousResearchError("MCX_CONTINUOUS_IMMUTABILITY_VIOLATION")
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
                        raise McxContinuousResearchError(
                            "MCX_CONTINUOUS_IMMUTABILITY_VIOLATION"
                        )
            finally:
                temporary.unlink(missing_ok=True)
        return path

    def load(self, *, artifact_identity: str) -> McxContinuousResearchArtifact:
        value = parse_mcx_continuous_research(
            self.path_for(artifact_identity).read_bytes()
        )
        if value.artifact_identity != artifact_identity:
            raise McxContinuousResearchError("MCX_CONTINUOUS_INTEGRITY_INVALID")
        return value

    def path_for(self, artifact_identity: str) -> Path:
        if (
            type(artifact_identity) is not str
            or not artifact_identity.startswith("INTRADAY-MCX-CONTINUOUS-RESEARCH-")
            or "/" in artifact_identity
            or "\\" in artifact_identity
        ):
            raise McxContinuousResearchError("MCX_CONTINUOUS_IDENTITY_INVALID")
        return (
            self._root
            / MCX_CONTINUOUS_RESEARCH_IDENTITY
            / f"{artifact_identity}.json"
        )


__all__ = [
    "DEFAULT_MCX_CONTINUOUS_RESEARCH_ROOT",
    "McxContinuousResearchStore",
]
