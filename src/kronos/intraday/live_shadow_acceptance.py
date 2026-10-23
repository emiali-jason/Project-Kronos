"""Existing WO-06H persisted acceptance proof validation, without application imports.

These checks are AST-equivalent to the unchanged live-shadow owner validator.
The owner remains byte-identical to preserve its retained code capability.
This pure copy avoids application, PDF, Provider and presentation imports in
the counted native recovery reader; parity is qualified explicitly.
"""
import re

from kronos.intraday.live_shadow import ShadowError, instant

REQUIRED={'WO_05A_TRUSTED_TIME_ADMISSION','WO_05B_OPERATION_ACCOUNTING',
          'INTRADAY_DISCOVERY_OPERATION','INTRADAY_V2_OPERATIONAL_CONTROL','WO_06H_LIVE_SHADOW'}


def validate_acceptance_proof(proof, runtime):
    """Validate the existing persisted proof shape and composed declarations."""
    from kronos.intraday.runtime_identity import LoadedCapability
    if (type(proof) is not dict
            or set(proof) != {'manifest','pid','revision','source_state','startup','configuration','capabilities'}
            or proof['manifest'] != runtime
            or re.fullmatch(r'INTRADAY-RUNTIME-[a-f0-9]{64}', runtime) is None
            or type(proof['pid']) is not int or proof['pid'] < 1
            or proof['source_state'] != 'CLEAN_COMMIT'
            or re.fullmatch(''.join(('[a-f0-9]', '{40}')), proof['revision']) is None
            or re.fullmatch(r'INTRADAY-LAUNCHER-CONFIG-[a-f0-9]{64}', proof['configuration']) is None
            or type(proof['capabilities']) is not list):
        raise ShadowError('SHADOW_RESTORATION_PROOF_INVALID')
    instant(proof['startup'])
    declarations = [LoadedCapability(**c) for c in proof['capabilities']]
    capabilities = {c.identity: c for c in declarations}
    if len(capabilities) != len(declarations) or not REQUIRED.issubset(capabilities):
        raise ShadowError('SHADOW_RESTORATION_CAPABILITY_INVALID')
    return dict(proof, capabilities=capabilities)
