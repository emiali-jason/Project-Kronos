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
    """Local personal install: any local launcher may start KRONOS.

    The signed-bundle parent check is retired (WO-7, Nov 2026). Source integrity
    is still enforced by qualify_repository/qualify_startup below.
    """
    return None


def qualify_repository(root):
    """Clean committed checkout, including staged and untracked source policy."""
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
        # WO-7: no branch/remote/network requirement. Any clean, committed
        # local revision may run; the exact revision is recorded as before.
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
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
