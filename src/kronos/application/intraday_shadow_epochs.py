"""Bounded successor commissioning; no analytical/Provider operation dependencies."""
from copy import copy
from datetime import timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import os
import re
import subprocess

from kronos.intraday.live_shadow import ShadowError, artifact, key, instant, next_month, SCHEMA, RESEARCH_INPUTS
from kronos.intraday.live_shadow_features import DEFINITIONS
from kronos.intraday.live_shadow_epochs import EpochView, document, epoch_document, capabilities, compatible, MATERIAL

ROUTE = '/control/intraday-live-shadow/successor-epoch/v1'
ACTION = 'COMMISSION_SUCCESSOR_EPOCH'


def repository_gate(revision, diagnosed_revision):
    root = Path(__file__).resolve().parents[3]
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.DEVNULL, timeout=20).decode().strip()
    if (git('branch', '--show-current') != 'develop' or git('rev-parse', 'HEAD') != revision
            or git('rev-parse', 'origin/develop') != revision
            or git('status', '--porcelain=v1', '--untracked-files=all')
            or git('ls-remote', '--exit-code', 'origin', 'refs/heads/develop').split()[0] != revision
            or git('merge-base', revision, diagnosed_revision) != diagnosed_revision):
        raise ShadowError('SHADOW_EPOCH_REPOSITORY_DRIFT')
    return True


def restore_epoch(service):
    chain = service._epochs.chain()
    if not chain: raise ShadowError('SHADOW_EPOCH_CURRENT_MISSING')
    epoch = chain[0]; window, acceptance = service._epochs.bound(epoch)
    current = service._runtime_proof()
    capabilities(current)
    if current['pid'] != os.getpid() or current['source_state'] != 'CLEAN_COMMIT':
        raise ShadowError('SHADOW_RESTORATION_RUNTIME_INVALID')
    if not compatible(epoch['body']['proof'], current):
        raise ShadowError('SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE')
    now = service.clock()
    if instant(current['startup']) > now or not instant(window.body['start']) <= now < instant(window.body['end']):
        raise ShadowError('SHADOW_RESTORATION_WINDOW_NOT_ACTIVE')
    service._window = window
    service._last = None  # Current status must not inherit a historical capture timestamp.
    service._restored_acceptance = acceptance.key
    service._accepted = current['manifest']
    service._restoration_failure = None
    service._reconcile()


def epoch_status(service):
    try:
        chain = service._epochs.chain(); rows = []
        for i, epoch in enumerate(chain):
            b = epoch['body']; projection = copy(service)
            projection.store = EpochView(service._epochs.raw, service._epochs, b['window'])
            projection._window = service._epochs.bound(epoch)[0]
            projection._reconcile()
            rows.append(dict(identity=epoch['identity'], acceptance=b['acceptance'], window=b['window'],
                start=b['start'], end=b['end'], methodology=b['methodology'], narrow_cpr=b['narrow_cpr'],
                predecessor=b['predecessor'], successor=None if i == 0 else chain[i-1]['identity'],
                superseded_at=None if i == 0 else chain[i-1]['body']['start'], current=i == 0,
                compatibility='COMPATIBLE' if service._manifest and compatible(b['proof'], service._runtime_proof()) else 'INCOMPATIBLE',
                counts=projection._summary))
        return dict(current_epoch=None if not rows else rows[0]['identity'], epochs=rows,
            all_epoch_counts={k:sum(r['counts'][k] for r in rows) for k in ('cohort_a', 'cohort_b', 'eod_available')},
            epoch_failure=None)
    except Exception:
        return dict(current_epoch=None, epochs=[], all_epoch_counts=None, epoch_failure='SHADOW_EPOCH_READ_FAILED')


def commission(service, payload, *, maintenance, idle, repository=repository_gate):
    if (type(payload) is not dict or set(payload) != {'action', 'request_identity', 'authorization_identity'}
            or payload['action'] != ACTION or type(payload['request_identity']) is not str
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', payload['request_identity'])):
        raise ShadowError('SHADOW_EPOCH_REQUEST_INVALID')
    # These booleans are supplied by server-owned state, never JSON fields.
    if maintenance is not True or idle is not True:
        raise ShadowError('SHADOW_EPOCH_MAINTENANCE_OR_QUIESCENCE_REQUIRED')
    with service._lock, service._epochs.transaction():
        store = service._epochs
        try:
            auth = store.load(payload['authorization_identity'])
        except ShadowError as error:
            raise ShadowError('SHADOW_SUCCESSOR_AUTHORIZATION_MISSING') from error
        if auth['kind'] != 'authorization': raise ShadowError('SHADOW_EPOCH_AUTHORIZATION_REQUIRED')
        a = auth['body']
        try:
            diagnosis = store.load(a['diagnosis'])
        except ShadowError as error:
            raise ShadowError('SHADOW_COMPATIBILITY_DIAGNOSIS_MISSING') from error
        if diagnosis['kind'] != 'diagnosis': raise ShadowError('SHADOW_EPOCH_DIAGNOSIS_REQUIRED')
        d = diagnosis['body']; current = service._runtime_proof(); now = service.clock()
        if current['source_state'] != 'CLEAN_COMMIT':
            raise ShadowError('SHADOW_CURRENT_RUNTIME_NOT_CLEAN_COMMIT')
        try:
            # Revalidate the frozen process manifest, not caller-supplied JSON.
            from dataclasses import replace
            replace(service._manifest.startup)
            replace(service._manifest)
            capabilities(current)
        except (ValueError, TypeError) as error:
            raise ShadowError('SHADOW_CURRENT_CAPABILITY_INVALID') from error
        if d['classification'] != MATERIAL:
            raise ShadowError('SHADOW_COMPATIBILITY_CLASSIFICATION_NOT_MATERIAL')
        if a['proof']['revision'] != current['revision']:
            raise ShadowError('SHADOW_SUCCESSOR_REVISION_MISMATCH')
        if (a['request'] != payload['request_identity'] or a['proof'] != current
                or current['pid'] != os.getpid() or current['source_state'] != 'CLEAN_COMMIT'
                or not a['sponsor_reference'] or not d['sponsor_reference']
                or d['classification'] != MATERIAL or not d['changed_semantics']
                or not re.fullmatch(r'[a-f0-9]{64}', d['report_sha256'])
                or not re.fullmatch(r'[a-f0-9]{40}', d['subject_revision'])
                or instant(current['startup']) > now):
            raise ShadowError('SHADOW_EPOCH_AUTHORITY_MISMATCH')
        if repository(current['revision'], d['subject_revision']) is not True:
            raise ShadowError('SHADOW_EPOCH_REPOSITORY_DRIFT')
        try:
            pointer = store.pointer(); chain = store.chain()
        except (ValueError, OSError) as error:
            raise ShadowError('SHADOW_PREDECESSOR_EPOCH_INVALID') from error
        if pointer and pointer['body']['request'] == a['request']:
            if pointer['body']['authorization'] != auth['identity']:
                raise ShadowError('SHADOW_EPOCH_REQUEST_CONFLICT')
            if instant(chain[0]['body']['start']) <= now < instant(chain[0]['body']['end']):
                restore_epoch(service)
            return dict(outcome='ALREADY_ESTABLISHED', epoch=chain[0]['identity'], status=service.status())
        if any(e['body']['request'] == a['request'] for e in chain):
            raise ShadowError('SHADOW_EPOCH_REQUEST_CONFLICT')
        if instant(a['expires_at']) < now:
            raise ShadowError('SHADOW_EPOCH_AUTHORIZATION_EXPIRED')
        if not chain or chain[0]['identity'] != a['predecessor']:
            raise ShadowError('SHADOW_EPOCH_PREDECESSOR_CONFLICT')
        old = chain[0]
        if d['predecessor_proof'] != old['body']['proof']:
            raise ShadowError('SHADOW_EPOCH_DIAGNOSIS_BINDING_INVALID')
        if compatible(old['body']['proof'], current):
            raise ShadowError('SHADOW_EPOCH_COMPATIBLE_CURRENT_EXISTS')
        if 'bridge' not in a:
            raise ShadowError('SHADOW_SUCCESSOR_CAPABILITY_NOT_BOUND')
        from kronos.intraday.live_shadow_transition import validate_bridge
        validate_bridge(store.load(a['bridge']), old, current, diagnosis, auth)
        # Verify historical accounting before any new acceptance/window publication.
        if service._failure is not None or epoch_status(service)['epoch_failure'] is not None:
            raise ShadowError('SHADOW_EPOCH_PREDECESSOR_INVALID')
        start = now.astimezone(ZoneInfo('Asia/Kolkata'))
        if start <= instant(old['body']['start']): raise ShadowError('SHADOW_EPOCH_START_INVALID')
        window_id = key('window', 'SUCCESSOR', old['identity'], auth['identity'], a['request'])
        acceptance_id = key('acceptance', window_id, current['manifest'])
        existing = store.raw.load('window', window_id)
        if existing is not None:
            # Failed unpublished preparation cannot backdate a later commissioning.
            raise ShadowError('SHADOW_EPOCH_INCOMPLETE_PUBLICATION_REQUIRES_REVIEW')
        window = artifact('window', window_id, dict(authority='RESEARCH_ONLY', start=start.isoformat(),
            start_utc=now.astimezone(timezone.utc).isoformat(), end=next_month(start).isoformat(),
            runtime_proof=current, runtime=current['manifest'], request=a['request'], research_inputs=RESEARCH_INPUTS,
            methodology='2.2.0', schema=SCHEMA, definitions=DEFINITIONS))
        acceptance = artifact('acceptance', acceptance_id, dict(authority='RESEARCH_ONLY', window=window_id,
            runtime=current['manifest'], request=a['request'], accepted_at=now.isoformat(), runtime_proof=current))
        epoch = epoch_document(window, acceptance, predecessor=old['identity'], diagnosis=diagnosis['identity'], classification=MATERIAL)
        transition = document('transition', dict(epoch=epoch['identity'], previous=None if pointer is None else pointer['identity'],
            request=a['request'], authorization=auth['identity'], effective_at=now.isoformat()))
        if pointer is None: store.anchor_legacy(old)
        else: store.retain(old)
        store.raw.retain(window); store.raw.retain(acceptance); store.retain(epoch)
        store.bound(epoch)
        store.advance(transition, pointer)  # Sole current-authority commit point.
        service._failure = None
        restore_epoch(service)
        return dict(outcome='ESTABLISHED', epoch=epoch['identity'], status=service.status())


def epoch_capability():
    """Declare loaded epoch infrastructure separately from frozen research arithmetic."""
    import marshal
    from hashlib import sha256
    from types import FunctionType
    from kronos.intraday import live_shadow_epochs, live_shadow_transition
    from kronos.intraday.runtime_identity import LoadedCapability
    from kronos.intraday.population_measurement import canonical
    from kronos.intraday.live_shadow import validate_body
    from kronos.application.intraday_live_shadow import IntradayLiveShadowService as Service
    functions = [restore_epoch, epoch_status, commission, repository_gate, validate_body, Service.__init__,
        Service._active, Service._epoch_current, Service.status, Service._restore_acceptance]
    for name, value in sorted(vars(live_shadow_epochs).items()):
        if isinstance(value, FunctionType) and value.__module__ == live_shadow_epochs.__name__:
            functions.append(value)
        elif isinstance(value, type) and value.__module__ == live_shadow_epochs.__name__:
            functions.extend(v for _,v in sorted(vars(value).items()) if isinstance(v, FunctionType))
    functions.extend(value for _, value in sorted(vars(live_shadow_transition).items())
        if isinstance(value, FunctionType) and value.__module__ == live_shadow_transition.__name__)
    payload = canonical(dict(policy=live_shadow_epochs.POLICY, methodology=live_shadow_epochs.METHOD,
        narrow_cpr=live_shadow_epochs.CPR, fields={k:sorted(v) for k,v in live_shadow_epochs.FIELDS.items()},
        transition_invariants=live_shadow_transition.INVARIANT_SEMANTICS))
    payload += b''.join(marshal.dumps(f.__code__) for f in functions)
    return LoadedCapability('WO_06H_ACCEPTANCE_EPOCH', '1.1.0', sha256(payload).hexdigest())
