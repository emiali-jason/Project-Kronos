"""ADR-0044: exact successor authority, never a same-epoch compatibility exception."""
from dataclasses import asdict
import re

from kronos.intraday.live_shadow import ShadowError
from kronos.intraday.live_shadow_epochs import capabilities, METHOD, CPR, MATERIAL
from kronos.intraday.population_measurement import identity

INVARIANT_SEMANTICS = ('METHODOLOGY_2_2_0', 'NARROW_CPR', 'TRUSTED_TIME_ADMISSION', 'WO_06H_CALCULATION')


def capability_identity(proof):
    """Identity of a complete declared capability boundary, including configuration."""
    caps = capabilities(proof)
    return identity('WO06H-CAPABILITY-', dict(configuration=proof['configuration'],
        capabilities=[asdict(caps[n]) for n in sorted(caps)]))


def capability_delta(before, after):
    a, b = capabilities(before), capabilities(after)
    changed, unchanged = [], []
    for name in sorted(a.keys() | b.keys()):
        old = None if name not in a else asdict(a[name])
        new = None if name not in b else asdict(b[name])
        if old == new:
            unchanged.append(old)
        else:
            changed.append(dict(identity=name, predecessor=old, successor=new))
    return changed, unchanged


def validate_bridge(bridge, predecessor, current, diagnosis, authorization):
    """Validate reviewed A→B evidence against exact retained A and server-derived B."""
    from kronos.intraday.live_shadow_epochs import validate
    validate(bridge)
    if bridge['kind'] != 'bridge':
        raise ShadowError('SHADOW_SUCCESSOR_CAPABILITY_NOT_BOUND')
    b, p, d, a = bridge['body'], predecessor['body'], diagnosis['body'], authorization['body']
    if diagnosis['kind'] != 'diagnosis' or d['classification'] != MATERIAL:
        raise ShadowError('SHADOW_COMPATIBILITY_CLASSIFICATION_NOT_MATERIAL')
    if (b['diagnosis'] != diagnosis['identity'] or a['diagnosis'] != diagnosis['identity']
            or a.get('bridge') != bridge['identity'] or b['classification'] != MATERIAL):
        raise ShadowError('SHADOW_COMPATIBILITY_DIAGNOSIS_MISMATCH')
    if (b['predecessor'] != predecessor['identity'] or a['predecessor'] != predecessor['identity']
            or d['predecessor_proof'] != p['proof']
            or b['predecessor_capability'] != capability_identity(p['proof'])):
        raise ShadowError('SHADOW_PREDECESSOR_CAPABILITY_INVALID')
    if b['current_proof']['revision'] != current['revision'] or a['proof']['revision'] != current['revision']:
        raise ShadowError('SHADOW_SUCCESSOR_REVISION_MISMATCH')
    if (b['current_proof'] != current or a['proof'] != current
            or b['current_capability'] != capability_identity(current)):
        raise ShadowError('SHADOW_SUCCESSOR_CAPABILITY_NOT_BOUND')
    changed, unchanged = capability_delta(p['proof'], current)
    if b['changed_capabilities'] != changed or b['unchanged_capabilities'] != unchanged:
        raise ShadowError('SHADOW_COMPATIBILITY_DIAGNOSIS_MISMATCH')
    if (not changed or not isinstance(d['changed_semantics'], str) or not d['changed_semantics'].strip()
            or b['changed_semantics'] != d['changed_semantics']
            or b['unchanged_semantics'] != list(INVARIANT_SEMANTICS)
            or not re.fullmatch(r'[a-f0-9]{64}', d['report_sha256'])
            or not d['sponsor_reference'] or not a['sponsor_reference']
            or b['sponsor_reference'] != a['sponsor_reference']):
        raise ShadowError('SHADOW_COMPATIBILITY_DIAGNOSIS_MISMATCH')
    if (b['methodology'] != METHOD or p['methodology'] != METHOD
            or b['narrow_cpr'] != CPR or p['narrow_cpr'] != CPR):
        raise ShadowError('SHADOW_EPOCH_POLICY_MISMATCH')
    # Research arithmetic remains frozen. The composed WO-05A declaration can
    # differ: reviewed semantics and exact declared changes are bound above.
    old_calc = capabilities(p['proof'])['WO_06H_LIVE_SHADOW']
    new_calc = capabilities(current)['WO_06H_LIVE_SHADOW']
    if old_calc != new_calc or old_calc.implementation_digest != d['calculation_digest']:
        raise ShadowError('SHADOW_FROZEN_IMPLEMENTATION_CHANGED')
