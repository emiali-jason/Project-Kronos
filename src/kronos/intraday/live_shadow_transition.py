"""ADR-0044: exact successor authority, never a same-epoch compatibility exception."""
from dataclasses import asdict
import re

from kronos.intraday.live_shadow import ShadowError
from kronos.intraday.live_shadow_epochs import capabilities, METHOD, CPR, MATERIAL, COLLATERAL
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


def validate_equivalence(record, epoch, current, diagnosis):
    """Validate one exact, immutable historical-1.1 to deterministic-1.2 binding."""
    from kronos.intraday.live_shadow_epoch_capability import PROTECTED_CALLABLES
    from kronos.intraday.live_shadow_epochs import validate
    validate(record); validate(diagnosis)
    if record['kind'] != 'compatibility' or diagnosis['kind'] != 'diagnosis':
        raise ShadowError('SHADOW_EPOCH_COMPATIBILITY_INVALID')
    b, d, e = record['body'], diagnosis['body'], epoch['body']
    historical, corrected = capabilities(e['proof']), capabilities(current)
    old = historical.get('WO_06H_ACCEPTANCE_EPOCH')
    new = corrected.get('WO_06H_ACCEPTANCE_EPOCH')
    if (b['classification'] != COLLATERAL or d['classification'] != COLLATERAL
            or b['diagnosis'] != diagnosis['identity']
            or b['epoch'] != epoch['identity'] or d['epoch'] != epoch['identity']
            or b['acceptance'] != e['acceptance'] or d['acceptance'] != e['acceptance']
            or b['window'] != e['window'] or d['window'] != e['window']
            or b['historical_proof'] != capability_identity(e['proof'])
            or d['historical_proof'] != b['historical_proof']
            or b['corrected_proof'] != capability_identity(current)
            or d['corrected_proof'] != b['corrected_proof']
            or b['protected_sources'] != d['protected_sources']
            or b['equivalence_evidence'] != d['equivalence_evidence']
            or not b['sponsor_authorization'] or not d['sponsor_reference']
            or not re.fullmatch(r'[a-f0-9]{64}', d['report_sha256'])):
        raise ShadowError('SHADOW_EPOCH_COMPATIBILITY_BINDING_INVALID')
    if (old is None or new is None or old.identity != new.identity
            or old.version != '1.1.0' or new.version != '1.2.0'):
        raise ShadowError('SHADOW_EPOCH_COMPATIBILITY_VERSION_INVALID')
    if (e['proof']['configuration'] != current['configuration']
            or {key:value for key,value in historical.items() if key != old.identity}
               != {key:value for key,value in corrected.items() if key != new.identity}):
        raise ShadowError('SHADOW_EPOCH_COMPATIBILITY_SCOPE_INVALID')
    old_calc = historical.get('WO_06H_LIVE_SHADOW')
    new_calc = corrected.get('WO_06H_LIVE_SHADOW')
    if old_calc is None or old_calc != new_calc:
        raise ShadowError('SHADOW_FROZEN_IMPLEMENTATION_CHANGED')
    sources = b['protected_sources']; evidence = b['equivalence_evidence']
    protected_modules = sorted({module for module, _ in PROTECTED_CALLABLES})
    if (type(sources) is not list or not sources
            or any(type(row) is not dict or set(row) != {'module', 'historical_sha256', 'corrected_sha256'}
                   or not isinstance(row['module'], str)
                   or any(re.fullmatch(r'[a-f0-9]{64}', row[key]) is None
                          for key in ('historical_sha256', 'corrected_sha256')) for row in sources)
            or [row['module'] for row in sources] != protected_modules
            or type(evidence) is not list or not evidence
            or any(re.fullmatch(r'[a-f0-9]{64}', value) is None for value in evidence)
            or len(evidence) != len(set(evidence))):
        raise ShadowError('SHADOW_EPOCH_COMPATIBILITY_EVIDENCE_INVALID')
    return True
