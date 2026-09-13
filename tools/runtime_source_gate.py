"""RUNTIME-01 startup-only source qualification; no runtime or evidence writes."""
from __future__ import annotations

import ctypes
from hashlib import sha1
from dataclasses import replace
from pathlib import Path
import os
import re
import subprocess
import sys

CANONICAL = Path("/Applications/KRONOS.app")
EXECUTABLE = CANONICAL / "Contents/MacOS/KRONOS"


def canonical_parent():
    """Kernel parent image plus strict bundle seal; no environment authority."""
    if sys.platform != "darwin":
        raise ValueError("CANONICAL_LAUNCHER_REQUIRED")
    try:
        buffer = ctypes.create_string_buffer(4096)
        library = ctypes.CDLL("/usr/lib/libproc.dylib")
        if (library.proc_pidpath(os.getppid(), buffer, len(buffer)) <= 0
                or Path(os.fsdecode(buffer.value)) != EXECUTABLE
                or EXECUTABLE.resolve() != EXECUTABLE):
            raise ValueError("CANONICAL_LAUNCHER_REQUIRED")
        subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict",
            "-R", '=identifier "com.project-kronos.browser-v1"', str(CANONICAL)],
            check=True, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        raise ValueError("CANONICAL_SIGNATURE_INVALID") from None


def qualify_repository(root):
    """Exact develop publication, including staged and untracked source policy."""
    root = Path(root).resolve()
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root,
            stderr=subprocess.DEVNULL, timeout=20).decode().strip()
    try:
        if Path(git("rev-parse", "--show-toplevel")).resolve() != root:
            raise ValueError("SOURCE_PROOF_UNAVAILABLE")
        if git("status", "--porcelain=v1", "--untracked-files=all"):
            raise ValueError("SOURCE_NOT_CLEAN")
        revision = git("rev-parse", "HEAD")
        if (not re.fullmatch(r"[a-f0-9]{40}", revision)
                or git("branch", "--show-current") != "develop"
                or git("rev-parse", "origin/develop") != revision
                or git("ls-remote", "--exit-code", "origin", "refs/heads/develop").split()
                    != [revision, "refs/heads/develop"]):
            raise ValueError("SOURCE_REVISION_NOT_AUTHORIZED")
        # Do not trust index stat caches, assume-unchanged or ignored Python files.
        tree = git("ls-tree", "-r", revision, "--", "src/kronos", "tools")
        blobs = {line.split("\t", 1)[1]: line.split("\t", 1)[0].split()[2]
                 for line in tree.splitlines()}
        seen = set()
        for prefix in ("src/kronos", "tools"):
            for path in (root / prefix).rglob("*.py"):
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    raise ValueError("SOURCE_NOT_CLEAN")
                seen.add(str(path.relative_to(root)))
                payload = path.read_bytes()
                actual = sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
                if blobs.get(str(path.relative_to(root))) != actual:
                    raise ValueError("SOURCE_NOT_CLEAN")
        if seen != {name for name in blobs if name.endswith(".py")}:
            raise ValueError("SOURCE_NOT_CLEAN")
        if git("rev-parse", "HEAD") != revision or git("status", "--porcelain=v1", "--untracked-files=all"):
            raise ValueError("SOURCE_NOT_CLEAN")
        return revision
    except (OSError, subprocess.SubprocessError, IndexError):
        raise ValueError("SOURCE_PROOF_UNAVAILABLE") from None


def qualify_startup(root, evidence):
    canonical_parent()
    revision = qualify_repository(root)
    try:
        replace(evidence)
        if (evidence.source_revision != revision or evidence.source_state != "CLEAN_COMMIT"
                or evidence.process_id != os.getpid()
                or evidence.load_verification != "PINNED_STARTUP_IMPORTS"
                or not evidence.source_snapshot_digest):
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("SOURCE_PROOF_UNAVAILABLE") from None
    return revision


if __name__ == "__main__":
    try:
        canonical_parent()
        qualify_repository(Path(__file__).resolve().parents[1])
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
