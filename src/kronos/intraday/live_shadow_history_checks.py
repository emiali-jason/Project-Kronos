"""Pure retained WO06H history checks for native recovery readers.

The application owner remains byte-identical for retained capability identity.
These AST-equivalent copies of its post-expiry predicates validate exact
retained epoch/relation facts and never grant collection or active acceptance.
"""
import os
import re

from kronos.intraday.live_shadow import ShadowError, instant
from kronos.intraday.live_shadow_epochs import compatible, validate
from kronos.intraday.live_shadow_transition import (
    capability_identity, validate_successor_relation, _validate_successor_body,
)


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
