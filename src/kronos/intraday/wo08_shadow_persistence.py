"""Immutable research namespace: no operational pointer or recovery replay.

A caller owns counted maintenance admission through the final directory fsync.
Interrupted temporary files are ignored by exact-ID readers, never repaired.
"""
import errno
import json
import os
from pathlib import Path
import re
import stat
from threading import Lock
from uuid import uuid4
from hashlib import sha256

from kronos.intraday.wo08_shadow_contract import ResearchRecord, canonical, outcome_for, validate_outcome_supplement, validate_t0_supplement


class Wo08ShadowStore:
    def __init__(self, root):
        root = Path(root)
        if not root.is_absolute() or root == Path('/'):
            raise ValueError('WO08_STORE_ROOT_INVALID')
        # Construction is inert; no mkdir/read/recovery/worker at startup.
        self.root = root / 'wo08-research-only-v1'
        self._lock = Lock()

    def _path(self, kind, identity):
        if kind not in {'T0', 'RUN', 'LINK', 'OUTCOME', 'SUPPLEMENT'} or not re.fullmatch(r'WO08-[A-Z]+-[a-f0-9]{64}', identity):
            raise ValueError('WO08_IDENTITY_INVALID')
        return self.root / kind.lower() / (identity + '.json')

    @staticmethod
    def _open_directory(path, *, create=False):
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in path.parts[1:]:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        pass
                try:
                    next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                except OSError as error:
                    if error.errno in {errno.ENOTDIR, errno.ELOOP}:
                        raise ValueError('WO08_SYMLINK_FORBIDDEN') from error
                    raise
                os.close(fd)
                fd = next_fd
            result, fd = fd, None
            return result
        finally:
            if fd is not None:
                os.close(fd)

    @classmethod
    def _sync(cls, path):
        fd = cls._open_directory(path)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _read_at(directory, name):
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise ValueError('WO08_SYMLINK_FORBIDDEN') from error
            raise
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('WO08_ARTIFACT_NOT_REGULAR')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                return stream.read()
        finally:
            os.close(fd)

    def _read(self, path):
        directory = self._open_directory(path.parent)
        try:
            return self._read_at(directory, path.name)
        finally:
            os.close(directory)

    def _retain(self, path, payload):
        # Every ancestor is opened relative to a pinned no-follow descriptor.
        # A concurrent ancestor replacement cannot redirect publication writes.
        directory = self._open_directory(path.parent, create=True)
        temp = '.' + path.name + '.' + uuid4().hex + '.tmp'
        fd = None
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(fd)
            try:
                os.link(temp, path.name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            except FileExistsError:
                if self._read_at(directory, path.name) != payload:
                    raise ValueError('WO08_IMMUTABLE_COLLISION') from None
            os.fsync(directory)
            self._sync(path.parent)
            if self._read(path) != payload:
                raise ValueError('WO08_READBACK_MISMATCH')
        finally:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(temp, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.close(directory)

    def retain(self, record):
        record.__post_init__()
        if record.kind == 'T0':
            validate_t0_supplement(record, self._read(self._path(
                'SUPPLEMENT', record.data['candle_supplement_identity'])))
        elif record.kind == 'OUTCOME':
            s = self.load('T0', record.data['sample_id'])
            rebuilt = outcome_for(s, **{k: v for k, v in record.data.items()
                if k not in {'schema_identity', 'schema_version', 'authority',
                             'operational_authority', 'trading_authority', 'integrity_sha256'}})
            if record.data['state'] == 'COMPLETE_SAME_CONTRACT':
                payload = self._read(self._path('SUPPLEMENT', record.data['outcome_candle_supplement_identity']))
                validate_outcome_supplement(s, record, payload, t0_supplement=self._read(
                    self._path('SUPPLEMENT', s.data['candle_supplement_identity'])))
            if rebuilt != record:
                raise ValueError('WO08_OUTCOME_LINEAGE_INVALID')
        elif record.kind == 'LINK':
            s = self.load('T0', record.data['sample_id'])
            if s.data['integrity_sha256'] != record.data['t0_integrity']:
                raise ValueError('WO08_LINK_LINEAGE_INVALID')
            for identity in record.data['outcome_ids']:
                if self.load('OUTCOME', identity).data['sample_id'] != s.identity:
                    raise ValueError('WO08_LINK_LINEAGE_INVALID')
        with self._lock:
            self._retain(self._path(record.kind, record.identity), record.payload)
        return record

    def retain_outcome(self, value, *, supplement=None):
        """Explicit lawful T1+ append, owned by caller's counted ticket.

        No scheduling, replay, acquisition or operational latest pointer.
        """
        value.__post_init__()
        if value.kind != 'OUTCOME':
            raise ValueError('WO08_RECORD_KIND_INVALID')
        if supplement is not None:
            s = self.load('T0', value.data['sample_id'])
            validate_outcome_supplement(s, value, supplement, t0_supplement=self._read(
                self._path('SUPPLEMENT', s.data['candle_supplement_identity'])))
            with self._lock:
                self._retain(self._path('SUPPLEMENT', value.data['outcome_candle_supplement_identity']), supplement)
        return self.retain(value)

    def retain_handoff(self, handoff):
        handoff.__post_init__()
        with self._lock:
            for sample, supplement in zip(handoff.samples, handoff.supplements):
                s = sample.data
                self._retain(self._path('SUPPLEMENT', s['candle_supplement_identity']), supplement)
                self._retain(self._path('T0', sample.identity), sample.payload)
            # Run manifest closes the complete retained 98-member research set.
            # Interrupted runs cannot be loaded as complete merely from some samples.
            self._retain(self._path('RUN', handoff.manifest.identity), handoff.manifest.payload)
            for sample in handoff.samples:
                self.load('T0', sample.identity)
        return handoff.manifest

    def load(self, kind, identity):
        raw = self._read(self._path(kind, identity))
        result = ResearchRecord(kind, raw)
        if result.identity != identity:
            raise ValueError('WO08_IDENTITY_MISMATCH')
        if kind == 'T0':
            s = result.data
            supplement = self._read(self._path('SUPPLEMENT', s['candle_supplement_identity']))
            validate_t0_supplement(result, supplement)
        if kind == 'OUTCOME':
            d = result.data
            s = self.load('T0', d['sample_id'])
            rebuilt = outcome_for(s, **{k: v for k, v in d.items() if k not in {
                'schema_identity', 'schema_version', 'authority', 'operational_authority',
                'trading_authority', 'integrity_sha256'}})
            if rebuilt != result:
                raise ValueError('WO08_OUTCOME_LINEAGE_INVALID')
            if d['state'] == 'COMPLETE_SAME_CONTRACT':
                validate_outcome_supplement(s, result, self._read(self._path('SUPPLEMENT', d['outcome_candle_supplement_identity'])),
                    t0_supplement=self._read(self._path('SUPPLEMENT', s.data['candle_supplement_identity'])))
        if kind == 'LINK':
            d = result.data
            s = self.load('T0', d['sample_id'])
            if s.data['integrity_sha256'] != d['t0_integrity']:
                raise ValueError('WO08_LINK_LINEAGE_INVALID')
            if d['previous_sample_id'] is not None:
                previous = self.load('T0', d['previous_sample_id'])
                if any(s.data[k] != previous.data[k] for k in ('subject', 'session_id')):
                    raise ValueError('WO08_LINK_LINEAGE_INVALID')
            for identity in d['outcome_ids']:
                if self.load('OUTCOME', identity).data['sample_id'] != s.identity:
                    raise ValueError('WO08_LINK_LINEAGE_INVALID')
        if kind == 'RUN':
            d = result.data
            samples = [self.load('T0', i).data for i in d['selected_sample_ids']]
            refs = [json.loads(self._read(self._path('SUPPLEMENT', s['candle_supplement_identity'])))['run_reference'] for s in samples]
            ids = [s['probables_member_id'] for s in samples]
            if (len(set(ids)) != len(ids) or set(ids) & set(d['excluded_result_reasons'])
                    or len({s['subject'] for s in samples}) != len(samples)
                    or any(r['integrity'] != d['run_integrity'] or r['universe'] != d['universe_identity'] for r in refs)
                    or set(s['probables_member_id'] for s in samples) | set(d['excluded_result_reasons']) != set(d['all_result_ids'])
                    or any(s['run_id'] != identity or any(s[k] != d[k] for k in ('analysis_operation_id', 'probables_run_id', 'analysis_boundary')) for s in samples)):
                raise ValueError('WO08_RUN_INCOMPLETE')
        return result
