"""Immutable WO-06H epochs; explicit pointer authority, never file recency."""
from contextlib import contextmanager
from hashlib import sha256
from threading import RLock
from uuid import uuid4
import fcntl
import json
import os
import re

from kronos.intraday.live_shadow import ShadowError, artifact, instant, key, next_month
from kronos.intraday.live_shadow_features import DEFINITIONS
from kronos.intraday.population_measurement import canonical, identity

POLICY = 'KRONOS-WO06H-ACCEPTANCE-EPOCH/1.0.0'
METHOD = 'KRONOS-INTRADAY-PROBABLES-METHODOLOGY-V2/2.2.0'
CPR = 'INTRADAY-PROBABLES-METHODOLOGY-V2-PUBLICATION-E7F8BD9316571148B39183E47220E97982D9A956E0309469D3AA9D4E8573A0E9'
MATERIAL = 'ACCEPTANCE_MATERIAL_CHANGE'
COLLATERAL = 'DIGEST_SCOPE_COLLATERAL'
ID = re.compile(r'WO06H-(EPOCH|TRANSITION|AUTHORIZATION|DIAGNOSIS|BRIDGE|COMPATIBILITY)-[a-f0-9]{64}\Z')
FIELDS = {
    'epoch': {'acceptance', 'window', 'start', 'end', 'proof', 'methodology', 'narrow_cpr', 'classification', 'created_at', 'predecessor', 'diagnosis', 'request'},
    'transition': {'epoch', 'previous', 'request', 'authorization', 'effective_at'},
    'authorization': {'request', 'predecessor', 'proof', 'diagnosis', 'expires_at', 'sponsor_reference'},
    'bridge': {'predecessor', 'predecessor_capability', 'current_proof', 'current_capability', 'diagnosis', 'classification', 'changed_capabilities', 'unchanged_capabilities', 'changed_semantics', 'unchanged_semantics', 'methodology', 'narrow_cpr', 'sponsor_reference'},
    'diagnosis': {'classification', 'subject_revision', 'predecessor_proof', 'calculation_digest', 'changed_semantics', 'report_sha256', 'sponsor_reference'},
    'compatibility': {'epoch', 'acceptance', 'window', 'historical_proof', 'corrected_proof', 'diagnosis',
        'classification', 'protected_sources', 'equivalence_evidence', 'sponsor_authorization'},
}
COLLATERAL_DIAGNOSIS_FIELDS = {'classification', 'epoch', 'acceptance', 'window', 'historical_proof',
    'corrected_proof', 'protected_sources', 'equivalence_evidence', 'report_sha256', 'sponsor_reference'}


def document(kind, body):
    # Old authorization envelopes remain readable; new commissioning requires
    # the additive bridge binding. Never rewrite historical authorization bytes.
    allowed = ((FIELDS[kind], FIELDS[kind] | {'bridge'}) if kind == 'authorization'
        else (FIELDS.get(kind), COLLATERAL_DIAGNOSIS_FIELDS) if kind == 'diagnosis'
        else (FIELDS.get(kind),))
    if kind not in FIELDS or set(body) not in allowed:
        raise ShadowError('SHADOW_EPOCH_DOCUMENT_INVALID')
    core = dict(policy=POLICY, kind=kind, body=body)
    core['identity'] = identity('WO06H-' + kind.upper() + '-', core)
    core['integrity'] = sha256(canonical(core)).hexdigest()
    return core


def validate(value):
    if type(value) is not dict or set(value) != {'policy', 'kind', 'body', 'identity', 'integrity'}:
        raise ShadowError('SHADOW_EPOCH_DOCUMENT_INVALID')
    if value != document(value['kind'], value['body']):
        raise ShadowError('SHADOW_EPOCH_INTEGRITY_INVALID')
    return value


def capabilities(proof):
    from kronos.application.intraday_live_shadow import IntradayLiveShadowService
    return IntradayLiveShadowService._validate_acceptance_proof(proof, proof['manifest'])['capabilities']


def compatible(a, b):
    return a['configuration'] == b['configuration'] and capabilities(a) == capabilities(b)


def epoch_document(window, acceptance, *, predecessor=None, diagnosis=None, classification='INITIAL_ACCEPTANCE'):
    w, a = window.body, acceptance.body
    if a['window'] != window.key or a['runtime'] != a['runtime_proof']['manifest'] or w['runtime'] != w['runtime_proof']['manifest']:
        raise ShadowError('SHADOW_EPOCH_BINDING_INVALID')
    if acceptance.key != key('acceptance', window.key, a['runtime']) or not compatible(w['runtime_proof'], a['runtime_proof']):
        raise ShadowError('SHADOW_EPOCH_BINDING_INVALID')
    if (w['definitions'] != DEFINITIONS or not instant(w['start']) <= instant(a['accepted_at']) < instant(w['end'])
            or instant(w['end']) != next_month(instant(w['start']))
            or instant(w['runtime_proof']['startup']) > instant(w['start'])
            or instant(a['runtime_proof']['startup']) > instant(a['accepted_at'])
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', a['request'])):
        raise ShadowError('SHADOW_EPOCH_TIME_INVALID')
    return document('epoch', dict(acceptance=acceptance.key, window=window.key, start=w['start'], end=w['end'],
        proof=a['runtime_proof'], methodology=METHOD, narrow_cpr=CPR, classification=classification,
        created_at=a['accepted_at'], predecessor=predecessor, diagnosis=diagnosis, request=a['request']))


class EpochStore:
    """No-follow directory IO; process/file lock; pointer commit follows immutable records."""
    def __init__(self, raw):
        self.raw = raw
        self.root = raw.root / 'epochs-v1'
        self.lock = RLock()

    def _directory(self, create=False):
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in self.root.parts[1:]:
                try:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                except FileNotFoundError:
                    if not create:
                        os.close(fd)
                        return None
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd
        except Exception:
            os.close(fd)
            raise ShadowError('SHADOW_EPOCH_PATH_INVALID') from None

    def _read(self, name):
        fd = self._directory()
        if fd is None:
            return None
        try:
            try:
                f = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                return None
            with os.fdopen(f, 'rb') as stream:
                data = stream.read(1_000_001)
            value = json.loads(data)
            if len(data) > 1_000_000 or canonical(value) != data:
                raise ShadowError('SHADOW_EPOCH_ENCODING_INVALID')
            return validate(value)
        finally:
            os.close(fd)

    def load(self, identifier):
        if type(identifier) is not str or not ID.fullmatch(identifier):
            raise ShadowError('SHADOW_EPOCH_IDENTITY_INVALID')
        value = self._read(identifier + '.json')
        if value is None or value['identity'] != identifier:
            raise ShadowError('SHADOW_EPOCH_RECORD_MISSING')
        return value

    def retain(self, value):
        validate(value)
        fd = self._directory(True); temporary = '.' + uuid4().hex + '.tmp'
        try:
            f = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            with os.fdopen(f, 'wb') as stream:
                stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
            try:
                os.link(temporary, value['identity'] + '.json', src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
            except FileExistsError:
                if self.load(value['identity']) != value:
                    raise ShadowError('SHADOW_EPOCH_IMMUTABLE_CONFLICT')
            os.fsync(fd)
        finally:
            try: os.unlink(temporary, dir_fd=fd)
            except FileNotFoundError: pass
            os.close(fd)

    @contextmanager
    def transaction(self):
        with self.lock:
            fd = self._directory(True)
            f = os.open('LOCK', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN); os.close(f); os.close(fd)

    def pointer(self):
        value = self._read('CURRENT.json')
        if value is not None:
            if value['kind'] != 'transition' or self.load(value['identity']) != value:
                raise ShadowError('SHADOW_EPOCH_POINTER_INVALID')
        return value

    def anchor_legacy(self, epoch):
        self.retain(epoch)
        fd = self._directory(True)
        try:
            try: os.link(epoch['identity'] + '.json', 'LEGACY.json', src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
            except FileExistsError:
                if self._read('LEGACY.json') != epoch: raise ShadowError('SHADOW_EPOCH_LEGACY_CONFLICT')
            os.fsync(fd)
        finally: os.close(fd)

    def managed(self):
        return self.pointer() is not None or self._read('LEGACY.json') is not None

    def advance(self, transition, expected):
        if self.pointer() != expected:
            raise ShadowError('SHADOW_EPOCH_POINTER_CONFLICT')
        self.retain(transition)
        fd = self._directory(True); temporary = '.' + uuid4().hex + '.tmp'
        try:
            f = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            with os.fdopen(f, 'wb') as stream:
                stream.write(canonical(transition)); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, 'CURRENT.json', src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        finally:
            try: os.unlink(temporary, dir_fd=fd)
            except FileNotFoundError: pass
            os.close(fd)

    def legacy(self):
        anchor = self._read('LEGACY.json')
        if anchor is not None:
            if self.load(anchor['identity']) != anchor: raise ShadowError('SHADOW_EPOCH_LEGACY_ANCHOR_INVALID')
            self.bound(anchor)
            return anchor
        windows, acceptances = self.raw.all('window'), self.raw.all('acceptance')
        if not windows and not acceptances:
            return None
        if len(windows) != 1 or len(acceptances) != 1 or windows[0].key != key('window', 'INITIAL_ONE_MONTH'):
            raise ShadowError('SHADOW_RESTORATION_AUTHORITY_MISSING_OR_AMBIGUOUS')
        return epoch_document(windows[0], acceptances[0])

    def bound(self, epoch):
        validate(epoch)
        if epoch['kind'] != 'epoch':
            raise ShadowError('SHADOW_EPOCH_KIND_INVALID')
        b = epoch['body']; window = self.raw.load('window', b['window']); acceptance = self.raw.load('acceptance', b['acceptance'])
        if window is None or acceptance is None or epoch_document(window, acceptance, predecessor=b['predecessor'], diagnosis=b['diagnosis'], classification=b['classification']) != epoch:
            raise ShadowError('SHADOW_EPOCH_BINDING_INVALID')
        return window, acceptance

    def chain(self):
        pointer = self.pointer()
        if pointer is None:
            old = self.legacy()
            return [] if old is None else [old]
        result = []; seen = set(); transition = pointer
        while transition is not None:
            b = transition['body']; epoch = self.load(b['epoch']); self.bound(epoch)
            if epoch['identity'] in seen or epoch['body']['created_at'] != b['effective_at']:
                raise ShadowError('SHADOW_EPOCH_CHAIN_INVALID')
            seen.add(epoch['identity']); result.append(epoch)
            auth = self.load(b['authorization'])
            if auth['kind'] != 'authorization': raise ShadowError('SHADOW_EPOCH_CHAIN_INVALID')
            authority = auth['body']; eb = epoch['body']; diagnosis = self.load(eb['diagnosis'])
            if (diagnosis['kind'] != 'diagnosis' or diagnosis['body']['classification'] != MATERIAL
                    or eb['classification'] != MATERIAL or authority['diagnosis'] != diagnosis['identity']
                    or b['request'] != authority['request'] or eb['request'] != b['request']
                    or eb['proof'] != authority['proof'] or eb['predecessor'] != authority['predecessor']
                    or instant(eb['created_at']) > instant(authority['expires_at'])
                    or not authority['sponsor_reference']):
                raise ShadowError('SHADOW_EPOCH_CHAIN_INVALID')
            predecessor_epoch = self.load(eb['predecessor']); self.bound(predecessor_epoch)
            if 'bridge' in authority:
                from kronos.intraday.live_shadow_transition import validate_bridge
                validate_bridge(self.load(authority['bridge']), predecessor_epoch, eb['proof'], diagnosis, auth)
            if (instant(eb['start']) <= instant(predecessor_epoch['body']['start'])
                    or diagnosis['body']['predecessor_proof'] != predecessor_epoch['body']['proof']):
                raise ShadowError('SHADOW_EPOCH_CHAIN_INVALID')
            previous = b['previous']
            if previous is None:
                predecessor = epoch['body']['predecessor']
                if predecessor is not None:
                    legacy = self.legacy()
                    if legacy is None or legacy['identity'] != predecessor or legacy['body']['predecessor'] is not None:
                        raise ShadowError('SHADOW_EPOCH_CHAIN_INVALID')
                    result.append(legacy)
                break
            transition = self.load(previous)
            if transition['kind'] != 'transition' or transition['body']['epoch'] != epoch['body']['predecessor']:
                raise ShadowError('SHADOW_EPOCH_CHAIN_INVALID')
        if len({e['identity'] for e in result}) != len(result):
            raise ShadowError('SHADOW_EPOCH_CHAIN_INVALID')
        return result

    def equivalence(self, epoch, current):
        """Exact non-transitive 1.1.0 -> 1.2.0 semantic-equivalence authority."""
        from kronos.intraday.live_shadow_transition import capability_identity, validate_equivalence
        historical = capability_identity(epoch['body']['proof'])
        corrected = capability_identity(current)
        fd = self._directory()
        if fd is None:
            return False
        try:
            names = sorted(name for name in os.listdir(fd)
                if re.fullmatch(r'WO06H-COMPATIBILITY-[a-f0-9]{64}\.json', name))
        finally:
            os.close(fd)
        matches = []
        for name in names:
            value = self.load(name[:-5]); body = value['body']
            if (body['epoch'], body['historical_proof'], body['corrected_proof']) == (
                    epoch['identity'], historical, corrected):
                matches.append(value)
        if not matches:
            return False
        if len(matches) != 1:
            raise ShadowError('SHADOW_EPOCH_COMPATIBILITY_AMBIGUOUS')
        diagnosis = self.load(matches[0]['body']['diagnosis'])
        validate_equivalence(matches[0], epoch, current, diagnosis)
        return True


class EpochView:
    """Scoped reads and additive prospective observation binding; legacy bytes untouched."""
    def __init__(self, raw, epochs, window=None):
        self.raw, self.epochs, self.selected_window = raw, epochs, window
        self.root, self.lock = raw.root, raw.lock

    def _epoch(self):
        chain = self.epochs.chain()
        if self.selected_window is not None:
            return next(e for e in chain if e['body']['window'] == self.selected_window)
        return chain[0] if chain else None

    def all(self, kind):
        values = self.raw.all(kind)
        if not self.epochs.managed() and self.selected_window is None:
            return values
        epoch = self._epoch()
        if epoch is None: return ()
        b = epoch['body']
        if kind in {'window', 'acceptance'}:
            return tuple(a for a in values if a.key == b[kind])
        scoped = tuple(a for a in values if a.body['window'] == b['window'])
        if kind == 'observation':
            for a in scoped:
                body = a.body
                if ('epoch' in body and (body['epoch'] != epoch['identity'] or body['acceptance'] != b['acceptance'])) or (b['predecessor'] is not None and 'epoch' not in body):
                    raise ShadowError('SHADOW_EPOCH_OBSERVATION_BINDING_INVALID')
        return scoped

    def load(self, kind, identifier):
        value = self.raw.load(kind, identifier)
        if value is not None and (self.epochs.managed() or kind == 'observation'):
            selected = self._epoch(); epoch = selected['body']
            bound = value.key == epoch[kind] if kind in {'window', 'acceptance'} else value.body['window'] == epoch['window']
            if not bound: raise ShadowError('SHADOW_EPOCH_FOREIGN_RECORD')
            if kind == 'observation':
                body = value.body
                if ('epoch' in body and (body['epoch'] != selected['identity'] or body['acceptance'] != epoch['acceptance'])) or (epoch['predecessor'] is not None and 'epoch' not in body):
                    raise ShadowError('SHADOW_EPOCH_OBSERVATION_BINDING_INVALID')
        return value

    def retain(self, value, *, claim=False):
        if value.kind in {'window', 'acceptance'} and self.epochs.managed():
            epoch = self._epoch()
            if epoch is None or value.key != epoch['body'][value.kind]:
                raise ShadowError('SHADOW_EPOCH_EXPLICIT_SUCCESSOR_REQUIRED')
        if value.kind == 'observation':
            epoch = self._epoch()
            if epoch is None or value.body['window'] != epoch['body']['window']:
                raise ShadowError('SHADOW_EPOCH_OBSERVATION_UNBOUND')
            b = value.body
            if instant(b['captured_at']) < instant(epoch['body']['start']):
                raise ShadowError('SHADOW_EPOCH_OBSERVATION_BACKDATED')
            if ('epoch' in b and b['epoch'] != epoch['identity']) or ('acceptance' in b and b['acceptance'] != epoch['body']['acceptance']):
                raise ShadowError('SHADOW_EPOCH_OBSERVATION_BINDING_INVALID')
            b.update(epoch=epoch['identity'], acceptance=epoch['body']['acceptance'])
            value = artifact(value.kind, value.key, b)
        return self.raw.retain(value, claim=claim)
