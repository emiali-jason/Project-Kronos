"""Immutable production assessments, complete run manifests and atomic current alias.

No assessment is created during construction or reads. Partial record retention
never constitutes a published run. Existing no-follow/fsync primitives are reused.
"""
from contextlib import contextmanager
from collections import OrderedDict
import fcntl
import json
import os
from pathlib import Path
import re
from threading import RLock
from uuid import uuid4

from kronos.intraday.wo08_assessment import Wo08Assessment, canonical, digest, moment, VERSION, CHECKSUM
from kronos.intraday.wo08_shadow_persistence import Wo08ShadowStore
from kronos.intraday.probables_v2 import ProbablesRunV2
from kronos.intraday.probables_v2_persistence import _from_wire, _to_wire

_LOCKS = {}
_LOCKS_GUARD = RLock()
_UNSPECIFIED = object()


class Wo08AssessmentStore:
    def __init__(self, root):
        root = Path(root)
        if not root.is_absolute() or root == Path('/'):
            raise ValueError('WO08_STORE_ROOT_INVALID')
        self.root = root / 'wo08-assessment-v1'
        # Reuse byte retention primitives only, never research record semantics.
        self._io = Wo08ShadowStore(root)
        self._validated_records = OrderedDict()
        self._validated_runs = OrderedDict()
        self._cache_lock = RLock()
        with _LOCKS_GUARD:
            self._lock = _LOCKS.setdefault(str(self.root), RLock())

    def _record_path(self, identity):
        if type(identity) is not str or re.fullmatch(r'WO08-ASSESSMENT-[a-f0-9]{64}', identity) is None:
            raise ValueError('WO08_ASSESSMENT_IDENTITY_INVALID')
        return self.root / 'records' / (identity + '.json')

    def _manifest_path(self, identity):
        if type(identity) is not str or re.fullmatch(r'INTRADAY-PROBABLES-V2-RUN-[A-Fa-f0-9]{64}', identity) is None:
            raise ValueError('WO08_RUN_IDENTITY_INVALID')
        return self.root / 'runs' / (identity + '.json')

    @contextmanager
    def _scope(self, *, write=False):
        with self._lock:
            directory = descriptor = None
            try:
                try:
                    directory = self._io._open_directory(self.root, create=write)
                    descriptor = os.open('publication.lock', os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if write else 0), 0o600, dir_fd=directory)
                except FileNotFoundError:
                    if write:
                        raise
                if descriptor is not None:
                    fcntl.flock(descriptor, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
                yield
            finally:
                if descriptor is not None:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                    os.close(descriptor)
                if directory is not None:
                    os.close(directory)

    @contextmanager
    def page_read_scope(self, _context=None):
        with self._scope():
            yield self

    def load(self, identity):
        payload = self._io._read(self._record_path(identity))
        # ADR-0055: every read obtains exact fresh bytes. Reuse only validation
        # of identical immutable bytes; no pointer/lineage/freshness cache.
        with self._cache_lock:
            value = self._validated_records.get(payload)
            if value is None:
                value = Wo08Assessment(payload)
                self._validated_records[payload] = value
                if len(self._validated_records) > 256:
                    self._validated_records.popitem(last=False)
            else:
                self._validated_records.move_to_end(payload)
        if value.identity != identity:
            raise ValueError('WO08_ASSESSMENT_IDENTITY_MISMATCH')
        return value

    def _manifest(self, run_identity):
        raw = self._io._read(self._manifest_path(run_identity))
        d = json.loads(raw)
        keys = {'schema_identity', 'schema_version', 'methodology_checksum', 'run_identity', 'run_integrity',
                'run_source', 'assessment_identities', 'result_identities', 'created_at', 'population_total',
                'manifest_identity', 'integrity_sha256'}
        if type(d) is not dict or set(d) != keys or canonical(d) != raw:
            raise ValueError('WO08_MANIFEST_SCHEMA_INVALID')
        core = {k: v for k, v in d.items() if k not in {'manifest_identity', 'integrity_sha256'}}
        if (d['schema_identity'] != 'KRONOS-INTRADAY-WO08-COMPLETE-RUN-V1' or d['schema_version'] != VERSION
                or d['methodology_checksum'] != CHECKSUM or d['integrity_sha256'] != digest(core)
                or d['manifest_identity'] != 'WO08-MANIFEST-' + digest(core)
                or d['run_identity'] != run_identity or d['population_total'] != 98):
            raise ValueError('WO08_MANIFEST_INTEGRITY_INVALID')
        with self._cache_lock:
            run = self._validated_runs.get(raw)
            if run is None:
                run = _from_wire(d['run_source'])
                validate_run(run)
                self._validated_runs[raw] = run
                if len(self._validated_runs) > 4:
                    self._validated_runs.popitem(last=False)
            else:
                self._validated_runs.move_to_end(raw)
        if (run.run_identity != run_identity or run.integrity_identity != d['run_integrity']
                or [r.result_identity for r in run.results] != d['result_identities']
                or len(d['assessment_identities']) != 98 or len(set(d['assessment_identities'])) != 98):
            raise ValueError('WO08_MANIFEST_POPULATION_INVALID')
        records = tuple(self.load(identity) for identity in d['assessment_identities'])
        for result, record in zip(run.results, records):
            v = record.data
            if (v['run_identity'] != run_identity or v['run_integrity'] != run.integrity_identity
                    or v['probable_result_identity'] != result.result_identity
                    or v['source_document']['result'] != _to_wire(result)
                    or v['created_at'] != d['created_at']):
                raise ValueError('WO08_MANIFEST_MEMBER_BINDING_INVALID')
        return d, records

    def load_run(self, run_identity):
        return self._manifest(run_identity)[1]

    def records(self):
        """Read complete historical populations only; partial records stay inert."""
        with self.page_read_scope():
            return tuple(record for path in sorted((self.root / "runs").glob("*.json"))
                         for record in self.load_run(path.stem))

    def current_pointer(self):
        try:
            raw = self._io._read(self.root / 'current.json')
        except FileNotFoundError:
            return None
        d = json.loads(raw)
        keys = {'run_identity', 'run_integrity', 'manifest_identity', 'manifest_integrity', 'generation',
                'previous_pointer_integrity', 'integrity_sha256'}
        if type(d) is not dict or set(d) != keys or raw != canonical(d):
            raise ValueError('WO08_POINTER_SCHEMA_INVALID')
        core = {k: v for k, v in d.items() if k != 'integrity_sha256'}
        if d['integrity_sha256'] != digest(core) or type(d['generation']) is not int or d['generation'] < 1:
            raise ValueError('WO08_POINTER_INTEGRITY_INVALID')
        self._manifest_path(d['run_identity'])
        return d

    def current_run(self):
        with self.page_read_scope():
            pointer = self.current_pointer()
            if pointer is None:
                return ()
            manifest, records = self._manifest(pointer['run_identity'])
            if (manifest['manifest_identity'] != pointer['manifest_identity']
                    or manifest['integrity_sha256'] != pointer['manifest_integrity']
                    or manifest['run_integrity'] != pointer['run_integrity']):
                raise ValueError('WO08_CURRENT_MANIFEST_MISMATCH')
            return records

    def _atomic_pointer(self, payload):
        directory = self._io._open_directory(self.root, create=True)
        name = '.current.' + uuid4().hex + '.tmp'
        descriptor = None
        try:
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(descriptor, 'wb', closefd=False) as output:
                output.write(payload)
                output.flush()
                os.fsync(descriptor)
            os.replace(name, 'current.json', src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
            if self._io._read_at(directory, 'current.json') != payload:
                raise ValueError('WO08_CURRENT_READBACK_MISMATCH')
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                os.unlink(name, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.close(directory)

    def publish(self, run, records, *, expected_pointer=_UNSPECIFIED):
        validate_run(run)
        records = tuple(records)
        if len(records) != 98 or any(type(r) is not Wo08Assessment for r in records):
            raise ValueError('WO08_COMPLETE_POPULATION_REQUIRED')
        for result, record in zip(run.results, records):
            record.__post_init__()
            d = record.data
            if (d['run_identity'] != run.run_identity or d['run_integrity'] != run.integrity_identity
                    or d['source_document']['result'] != _to_wire(result)):
                raise ValueError('WO08_PUBLICATION_MEMBER_BINDING_INVALID')
        times = {r.data['created_at'] for r in records}
        if len(times) != 1:
            raise ValueError('WO08_PUBLICATION_TIME_MISMATCH')
        created = times.pop()
        core = dict(schema_identity='KRONOS-INTRADAY-WO08-COMPLETE-RUN-V1', schema_version=VERSION,
            methodology_checksum=CHECKSUM, run_identity=run.run_identity, run_integrity=run.integrity_identity,
            run_source=_to_wire(run), assessment_identities=[r.identity for r in records],
            result_identities=[r.result_identity for r in run.results], created_at=created, population_total=98)
        manifest = dict(core, manifest_identity='WO08-MANIFEST-' + digest(core), integrity_sha256=digest(core))
        with self._scope(write=True):
            current = self.current_pointer()
            if expected_pointer is not _UNSPECIFIED and current != expected_pointer:
                raise ValueError('WO08_PUBLICATION_CONFLICT')
            if current is not None:
                previous, _ = self._manifest(current['run_identity'])
                if current['run_identity'] == run.run_identity:
                    if previous != manifest:
                        raise ValueError('WO08_PUBLICATION_CONFLICT')
                    return self.load_run(run.run_identity)
                old = _from_wire(previous['run_source'])
                if run.analysis_boundary <= old.analysis_boundary:
                    raise ValueError('WO08_PUBLICATION_NOT_NEWER')
            for record in records:
                self._io._retain(self._record_path(record.identity), record.payload)
            self._io._retain(self._manifest_path(run.run_identity), canonical(manifest))
            # Read back the entire population before exposing authority.
            self._manifest(run.run_identity)
            pointer_core = dict(run_identity=run.run_identity, run_integrity=run.integrity_identity,
                manifest_identity=manifest['manifest_identity'], manifest_integrity=manifest['integrity_sha256'],
                generation=1 if current is None else current['generation'] + 1,
                previous_pointer_integrity=None if current is None else current['integrity_sha256'])
            pointer = dict(pointer_core, integrity_sha256=digest(pointer_core))
            self._io._retain(self.root / 'generations' / (str(pointer['generation']) + '.json'), canonical(pointer))
            self._atomic_pointer(canonical(pointer))
        return records


def validate_run(run):
    if type(run) is not ProbablesRunV2:
        raise ValueError('WO08_RUN_TYPE_INVALID')
    run.__post_init__()
    run.methodology.__post_init__()
    run.diagnostics.__post_init__()
    for result in run.results:
        result.__post_init__()
    if len(run.results) != 98 or len({r.canonical_subject_identity for r in run.results}) != 98:
        raise ValueError('WO08_COMPLETE_POPULATION_REQUIRED')
