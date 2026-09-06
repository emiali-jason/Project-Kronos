"""Immutable local publication; one active writer instance per root only."""

import os
from pathlib import Path
import re
import stat
import tempfile
from threading import RLock

from .contracts import (
    CoreFailureCode, CoreRecord, RecordRef, TvcaCoreError,
    _canonical, _decode, _fail, _validate_successor,
)


class _RecordStore:
    def __init__(self, root: Path) -> None:
        if (not isinstance(root, Path) or not root.is_absolute()
                or root == Path(root.anchor) or ".." in root.parts):
            _fail(CoreFailureCode.STORAGE_ROOT_INVALID)
        self._root = root
        self._lock = RLock()
        self._check_root()

    def _safe(self, path: Path) -> None:
        if not path.is_relative_to(self._root):
            _fail(CoreFailureCode.STORAGE_ROOT_INVALID)
        # Bounded no-symlink policy, not protection from hostile concurrent mutation.
        for component in (*reversed(path.parents), path):
            try:
                info = component.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode):
                _fail(CoreFailureCode.STORAGE_ROOT_INVALID)

    def _check_root(self) -> None:
        try:
            self._safe(self._root)
            if not self._root.is_dir():
                _fail(CoreFailureCode.STORAGE_ROOT_INVALID)
        except OSError:
            _fail(CoreFailureCode.STORAGE_IO_FAILURE)

    def _path(self, request_id: str, revision: int) -> Path:
        path = self._root / "records" / request_id / f"{revision}.json"
        self._safe(path)
        return path

    def _read(self, path: Path) -> bytes:
        self._safe(path)
        if not path.is_file():
            if not path.exists():
                raise FileNotFoundError
            _fail(CoreFailureCode.INTEGRITY_FAILURE)
        return path.read_bytes()

    @staticmethod
    def _link_valid(previous: CoreRecord, record: CoreRecord) -> None:
        try:
            _validate_successor(previous, record)
        except TvcaCoreError:
            _fail(CoreFailureCode.INTEGRITY_FAILURE)

    def _chain(self, request_id: str) -> list[CoreRecord]:
        directory = self._path(request_id, 0).parent
        if not directory.exists():
            return []
        slots = {}
        for path in directory.iterdir():
            self._safe(path)
            if path.name.startswith(".tmp-"):
                continue
            if re.fullmatch(r"(0|[1-9][0-9]*)\.json", path.name) is None:
                _fail(CoreFailureCode.INTEGRITY_FAILURE)
            slots[int(path.stem)] = path
        if set(slots) != set(range(len(slots))):
            _fail(CoreFailureCode.INTEGRITY_FAILURE)
        chain = []
        # Numeric continuity is checked only for integrity, never to select a base.
        for revision in range(len(slots)):
            record = _decode(self._read(slots[revision]))
            if record.request_id != request_id or record.revision != revision:
                _fail(CoreFailureCode.INTEGRITY_FAILURE)
            if chain:
                self._link_valid(chain[-1], record)
            chain.append(record)
        return chain

    def restore(self, ref: RecordRef) -> CoreRecord:
        if type(ref) is not RecordRef:
            _fail(CoreFailureCode.INVALID_INPUT)
        with self._lock:
            self._check_root()
            try:
                target = self._path(ref.request_id, ref.revision)
                try:
                    record = _decode(self._read(target))
                except FileNotFoundError:
                    _fail(CoreFailureCode.RECORD_NOT_FOUND)
                if record.ref != ref:
                    _fail(CoreFailureCode.INTEGRITY_FAILURE)
                previous = None
                for revision in range(ref.revision + 1):
                    try:
                        item = record if revision == ref.revision else _decode(
                            self._read(self._path(ref.request_id, revision)))
                    except FileNotFoundError:
                        _fail(CoreFailureCode.INTEGRITY_FAILURE)
                    if item.request_id != ref.request_id or item.revision != revision:
                        _fail(CoreFailureCode.INTEGRITY_FAILURE)
                    if previous is not None:
                        self._link_valid(previous, item)
                    previous = item
                return record
            except OSError:
                _fail(CoreFailureCode.STORAGE_IO_FAILURE)

    @staticmethod
    def _sync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _durability(self, directory: Path) -> None:
        # Also durably retain newly created request/records directory entries.
        for path in (directory, directory.parent, self._root):
            self._sync_directory(path)

    def retain(self, record: CoreRecord) -> CoreRecord:
        if type(record) is not CoreRecord:
            _fail(CoreFailureCode.INVALID_INPUT)
        data = _canonical(record)
        with self._lock:
            self._check_root()
            try:
                path = self._path(record.request_id, record.revision)
                exists = path.exists()
                if exists and self._read(path) != data:
                    _fail(CoreFailureCode.RECORD_CONFLICT)
                chain = self._chain(record.request_id)
                if exists:
                    # Replay must resolve an earlier publication/durability uncertainty.
                    with path.open("rb") as stream:
                        os.fsync(stream.fileno())
                    self._durability(path.parent)
                    return _decode(data)
                if record.revision != len(chain):
                    _fail(CoreFailureCode.RECORD_CONFLICT)
                if chain:
                    _validate_successor(chain[-1], record)
                path.parent.mkdir(parents=True, exist_ok=True)
                self._safe(path)
                self._publish(path, data)
                return _decode(data)
            except OSError:
                _fail(CoreFailureCode.STORAGE_IO_FAILURE)

    def _publish(self, path: Path, data: bytes) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", prefix=".tmp-",
                                             dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                # Same-filesystem hard link publishes complete bytes without replacement.
                os.link(temporary, path)
            except FileExistsError:
                if self._read(path) != data:
                    _fail(CoreFailureCode.RECORD_CONFLICT)
            temporary.unlink()
            temporary = None
            self._durability(path.parent)
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    # An orphan temp is never restoration authority.
                    pass
