"""IWO-06A historical startup projection; no research acceptance or collection.

The accepted collector and its semantic capability stay frozen. This additive
owner validates retained history separately from active research restoration.
"""
from copy import copy
from dataclasses import replace
import os
import re

from kronos.application.intraday_live_shadow import IntradayLiveShadowService
from kronos.intraday.live_shadow import ShadowError, instant
from kronos.intraday.live_shadow_epochs import capabilities, compatible, validate
from kronos.intraday.live_shadow_transition import (
    capability_identity, validate_successor_relation, _validate_successor_body,
)

HISTORY_SCHEMA = 'KRONOS-WO06H-HISTORICAL-RESTORATION/1.0.0'
HISTORICAL_EXPIRED = 'HISTORICAL_ACCEPTANCE_EXPIRED'


def validate_historical_relation(record, epoch, current, now):
    """Require all existing exact relation checks at actual post-expiry time.

    The frozen operational validator checks approvals *after* its window gate.
    Check those independently first, then accept only that specific time denial.
    This never supplies a fabricated in-window time or grants active authority.
    """
    validate(record); validate(epoch)
    _validate_successor_body(record['body'])
    if any(row['disposition'] != 'APPROVED' for row in record['body']['owner_approvals']):
        raise ShadowError('SHADOW_SUCCESSOR_COMPATIBILITY_NOT_APPROVED')
    if now < instant(epoch['body']['end']):
        raise ShadowError('SHADOW_HISTORICAL_WINDOW_NOT_EXPIRED')
    try:
        validate_successor_relation(record, epoch, current, now)
    except ShadowError as error:
        if str(error) != 'SHADOW_RESTORATION_WINDOW_NOT_ACTIVE':
            raise
        return True
    raise ShadowError('SHADOW_HISTORICAL_WINDOW_INVALID')


def historical_compatible(store, epoch, current, now):
    if compatible(epoch['body']['proof'], current) or store.equivalence(epoch, current):
        return True
    source, target = capability_identity(epoch['body']['proof']), capability_identity(current)
    fd = store._directory()
    if fd is None:
        return False
    try:
        names = sorted(name for name in os.listdir(fd)
            if re.fullmatch(r'WO06H-SUCCESSOR_COMPATIBILITY-[a-f0-9]{64}\.json', name))
    finally:
        os.close(fd)
    matches = []
    for name in names:
        value = store.load(name[:-5]); body = value['body']
        if (body['epoch'], body['source_aggregate'], body['target_aggregate']) == (
                epoch['identity'], source, target):
            matches.append(value)
    if not matches:
        return False
    if len(matches) != 1:
        raise ShadowError('SHADOW_SUCCESSOR_COMPATIBILITY_AMBIGUOUS')
    return validate_historical_relation(matches[0], epoch, current, now)


class _HistoricalWriteBoundary:
    """Delegate existing epoch IO; expired authority cannot publish any artifact."""
    def __init__(self, store, service):
        self._store, self._service = store, service

    def __getattr__(self, name):
        return getattr(self._store, name)

    def retain(self, value, *, claim=False):
        window = self._service._window
        if window is not None and self._service.clock() >= instant(window.body['end']):
            raise ShadowError('SHADOW_RESTORATION_WINDOW_EXPIRED')
        return self._store.retain(value, claim=claim)


class HistoricalIntradayLiveShadowService(IntradayLiveShadowService):
    """Retain active behavior; expose expired-valid history without accepting it."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.store = _HistoricalWriteBoundary(self.store, self)

    def status(self):
        with self._lock:
            state = super().status()
            now = self.clock()
            if self._window is None or now < instant(self._window.body['end']):
                return state
            # Expiry is always collection-disabled, including a process that was
            # accepted before the boundary. No mutable acceptance is established.
            state.update(enabled=False, runtime_accepted=False,
                acceptance_disposition='NOT_ACCEPTED', historical_restoration=HISTORY_SCHEMA,
                collection_authority='EXPIRED', historical_evidence='NOT_ESTABLISHED')
            try:
                if self._failure or state['epoch_failure']:
                    return state
                if self._restoration_failure not in {None, 'SHADOW_RESTORATION_WINDOW_EXPIRED',
                        'SHADOW_RESTORATION_WINDOW_NOT_ACTIVE', 'SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE'}:
                    raise ShadowError(self._restoration_failure)
                replace(self._manifest); replace(self._manifest.startup)
                current = self._runtime_proof(); capabilities(current)
                if (current['pid'] != os.getpid() or current['source_state'] != 'CLEAN_COMMIT'
                        or instant(current['startup']) > now):
                    raise ShadowError('SHADOW_RESTORATION_RUNTIME_INVALID')
                chain = self._epochs.chain()
                if not chain:
                    raise ShadowError('SHADOW_EPOCH_CURRENT_MISSING')
                epoch = chain[0]; window, acceptance = self._epochs.bound(epoch)
                if window.payload != self._window.payload or now < instant(window.body['end']):
                    raise ShadowError('SHADOW_RESTORATION_WINDOW_CHANGED')
                if not historical_compatible(self._epochs, epoch, current, now):
                    raise ShadowError('SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE')
                projection = copy(self)
                projection._reconcile()  # Validate every current retained observation/receipt/outcome.
                state.update(acceptance_disposition=HISTORICAL_EXPIRED,
                    acceptance_identity=acceptance.key, historical_evidence='READABLE',
                    counts=dict(projection._summary), failure=None)
                state['epochs'] = [dict(row, compatibility='HISTORICALLY_COMPATIBLE')
                    if row['identity'] == epoch['identity'] else row for row in state['epochs']]
            except (ValueError, OSError, TypeError, KeyError, AttributeError) as error:
                state['failure'] = str(error) if isinstance(error, ShadowError) else 'SHADOW_HISTORICAL_RESTORATION_INVALID'
            return state

    @property
    def _accepted(self):
        # Denial applies to every inherited collector entry point, including EOD
        # in a process that crosses the boundary without restarting. Keep the
        # frozen calculation callables and their implementation identity intact.
        window = getattr(self, '_window', None)
        if window is not None and self.clock() >= instant(window.body['end']):
            return None
        return getattr(self, '_collection_acceptance', None)

    @_accepted.setter
    def _accepted(self, value):
        self._collection_acceptance = value
