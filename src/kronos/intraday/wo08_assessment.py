"""WO08 production assessment V1; existing machine authority, no trading authority.

I1 preserves ADR-0038. I2-I5 have no commissioned machine equivalents.
"""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from zoneinfo import ZoneInfo
from kronos.intraday.probables_v2 import DiscoveryProbablesEvidenceV2, ProbableMemberResultV2, _mapped_result_lineage_valid
from kronos.intraday.probables_v2_persistence import _from_wire, _to_wire
from kronos.intraday.native_structural_selection import create_native_selection
from kronos.intraday.wo10_futures_contract import normalize

SCHEMA = 'KRONOS-INTRADAY-WO08-ASSESSMENT-V1'
VERSION = '1.0.0'
METHODOLOGY = 'KRONOS-INTRADAY-WO08-GOVERNED-MACHINE-ASSESSMENT'
RULES = {
    'I1': 'ADR0038_EXACT_COMPLETED_1H_AND_15M_DIRECTION_SUPPORT',
    'I2': 'MACHINE_FOLLOW_THROUGH_METHOD_NOT_COMMISSIONED',
    'I3': 'MACHINE_PATH_CLEARANCE_METHOD_NOT_COMMISSIONED',
    'I4': 'MACHINE_SETUP_QUALITY_METHOD_NOT_COMMISSIONED',
    'I5': 'MACHINE_ANALYTICAL_EXTENSION_METHOD_NOT_COMMISSIONED',
    'opening': 'NORMAL_15M_STRUCTURE_NOT_ESTABLISHED',
    'native': 'STRUCTURAL_CONTEXT_ONLY_NOT_CRITERION_EQUIVALENCE',
    'authority': 'ANALYTICAL_ASSESSMENT_ONLY_NO_TRADING_AUTHORITY',
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return sha256(canonical(value)).hexdigest()


CHECKSUM = digest(dict(identity=METHODOLOGY, version=VERSION, rules=RULES))


def moment(value):
    result = datetime.fromisoformat(value) if type(value) is str else value
    if not isinstance(result, datetime) or result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('WO08_ASSESSMENT_TIMESTAMP_INVALID')
    return result


def validate_mapping(result, mapping):
    if type(result) is not ProbableMemberResultV2:
        raise ValueError('WO08_RESULT_TYPE_INVALID')
    result.__post_init__()
    if mapping is None:
        if result.source_mapping_identity is not None:
            raise ValueError('WO08_REQUIRED_MAPPING_MISSING')
        return
    if type(mapping) is not DiscoveryProbablesEvidenceV2:
        raise ValueError('WO08_MAPPING_TYPE_INVALID')
    mapping.__post_init__()
    mapping.completed_evidence.__post_init__()
    mapping.semantic_evidence.__post_init__()
    for selected in mapping.completed_evidence.selected_candles:
        selected.__post_init__()
        selected.candle.__post_init__()
    for fact in mapping.semantic_evidence.facts:
        fact.__post_init__()
    if not _mapped_result_lineage_valid(result, mapping):
        raise ValueError('WO08_SOURCE_BINDING_INVALID')


def _assessment_values(*, run_identity, run_integrity, result, mapping, native, created_at):
    validate_mapping(result, mapping)
    if not all(type(x) is str and x.strip() for x in (run_identity, run_integrity)):
        raise ValueError('WO08_RUN_IDENTITY_INVALID')
    at = moment(created_at)
    if at < result.analysis_boundary:
        raise ValueError('WO08_PUBLICATION_BEFORE_BOUNDARY')
    semantic = None if mapping is None else mapping.semantic_evidence
    selection = None if mapping is None else mapping.completed_evidence
    direction = None if result.direction is None else result.direction.value
    market = 'MCX' if result.canonical_subject_identity.startswith('MCX-') else 'NSE'
    native_value = None
    if mapping is not None:
        if native is None:
            raise ValueError('WO08_NATIVE_COMPANION_UNAVAILABLE')
        native.__post_init__()
        native_value = native.data
        expected = dict(analysis_cycle=run_identity, probable_result_identity=result.result_identity,
            subject=result.canonical_subject_identity, session=result.market_session_identity,
            analysis_boundary=normalize(result.analysis_boundary), machine_identity=semantic.evidence_identity,
            machine_integrity=semantic.integrity_identity,
            completed_evidence_identity=selection.selection_identity,
            direction=direction or 'UNAVAILABLE')
        if any(native_value.get(k) != v for k, v in expected.items()):
            raise ValueError('WO08_NATIVE_COMPANION_LINEAGE_INVALID')
        if moment(native_value['created_at']) > at:
            raise ValueError('WO08_NATIVE_PUBLICATION_AFTER_ASSESSMENT')
    elif native is not None:
        raise ValueError('WO08_UNMAPPED_NATIVE_AUTHORITY_INVALID')
    facts = {} if semantic is None else {f.family: f for f in semantic.facts}
    one, fifteen = facts.get('1H_REGIME'), facts.get('15M_STRUCTURE')
    inputs = [f for f in (one, fifteen) if f is not None]
    current = None if not inputs else ';'.join(f.family + '=' + f.direction.value for f in inputs)
    reasons = []
    if direction not in {'LONG', 'SHORT'}:
        state, reasons = 'UNAVAILABLE', ['INHERITED_DIRECTION_UNAVAILABLE']
    elif any(f is None or f.availability != 'AVAILABLE' or f.direction.value == 'UNAVAILABLE' for f in (one, fifteen)):
        state, reasons = 'UNAVAILABLE', ['NORMAL_15M_STRUCTURE_NOT_ESTABLISHED' if fifteen is None else 'REQUIRED_DIRECTION_FACT_UNAVAILABLE']
    elif all(f.direction.value == direction for f in inputs):
        state = 'DETERMINISTICALLY_ESTABLISHED'
    else:
        state, reasons = 'DETERMINISTICALLY_NEGATIVE', ['DIRECTION_STRUCTURE_NOT_SUPPORTING']
    criteria = [dict(criterion_id='I1', state=state, current_value=current,
        reason_codes=reasons, source_fact_identities=[f.fact_identity for f in inputs],
        source_fact_integrities=[f.integrity_identity for f in inputs], rule=RULES['I1'])]
    criteria.extend(dict(criterion_id='I'+str(i), state='NOT_COMMISSIONED', current_value=None,
        reason_codes=[RULES['I'+str(i)]], source_fact_identities=[], source_fact_integrities=[],
        rule=RULES['I'+str(i)]) for i in range(2, 6))
    gate = 'NONE'
    if result.canonical_subject_identity in {'MCX-SUBJECT-NATGAS', 'MCX-FUT-NATGAS', 'MCX-SUBJECT-NATURALGAS'}:
        gate = 'NATGAS_COMMISSIONING_HELD'
    elif direction in {'LONG', 'SHORT'} and any(f.direction.value in {'LONG', 'SHORT'} and f.direction.value != direction for f in inputs):
        gate = 'AUTHORITATIVE_GOVERNED_DIRECTIONAL_CONFLICT'
    elif result.state.value not in {'LONG_PROBABLE', 'SHORT_PROBABLE'}:
        gate = 'PROBABLES_NOT_ADMITTED' if result.state.value == 'NOT_ADMITTED' else 'PROBABLES_UNAVAILABLE'
    mcx_missing = market == 'MCX' and (native_value is None or not all(native_value.get(k) for k in ('exact_contract', 'roll_lineage')))
    if mcx_missing and gate == 'NONE':
        gate = 'MCX_CONTRACT_BINDING_UNAVAILABLE'
    machine_ids = [] if semantic is None else [semantic.evidence_identity, semantic.integrity_identity,
        selection.selection_identity, selection.integrity_identity]
    return dict(schema_identity=SCHEMA, schema_version=VERSION,
        methodology_identity=METHODOLOGY, methodology_version=VERSION, methodology_checksum=CHECKSUM,
        authority=RULES['authority'], trading_authority=False,
        run_identity=run_identity, run_integrity=run_integrity, generation=run_identity,
        probable_result_identity=result.result_identity, probable_result_integrity=result.integrity_identity,
        discovery_identity=result.source_discovery_run_identity, subject=result.canonical_subject_identity,
        market_family=market, direction=direction, probables_state=result.state.value,
        session_identity=result.market_session_identity,
        trading_date=result.analysis_boundary.astimezone(ZoneInfo('Asia/Kolkata')).date().isoformat(),
        analysis_boundary=result.analysis_boundary.isoformat(), created_at=at.isoformat(),
        phase=None if result.phase is None else result.phase.value,
        calendar_identity=None if selection is None else selection.calendar_identity,
        calendar_version=None if selection is None else selection.calendar_version,
        mapping_identity=result.source_mapping_identity,
        semantic_evidence_identity=None if semantic is None else semantic.evidence_identity,
        semantic_evidence_integrity=None if semantic is None else semantic.integrity_identity,
        completed_evidence_identity=None if selection is None else selection.selection_identity,
        completed_evidence_integrity=None if selection is None else selection.integrity_identity,
        machine_evidence_identities=machine_ids,
        native_decision_identity=None if native is None else native.identity,
        native_decision_integrity=None if native is None else native.integrity,
        exact_mcx_contract_identity=None if native_value is None else native_value['exact_contract'],
        exact_mcx_roll_lineage=None if native_value is None else native_value['roll_lineage'],
        criteria=criteria, hard_gate=gate,
        disposition='HARD_GATE' if gate != 'NONE' else 'ASSESSMENT_UNAVAILABLE',
        failure_stage='UPSTREAM_ADMISSION' if gate != 'NONE' else 'METHODOLOGY',
        failure_reason=gate if gate != 'NONE' else 'REQUIRED_CRITERIA_NOT_COMMISSIONED',
        provenance=['SPONSOR_WO08_PRODUCTION_SUCCESSOR_20261010', 'ADR0038_I1_RETAINED',
                    'NATIVE_STRUCTURAL_CONTEXT_ONLY', 'NO_WO07F_AUTHORITY'],
        source_document=dict(result=_to_wire(result), mapping=None if mapping is None else _to_wire(mapping),
                             native=native_value))


@dataclass(frozen=True, slots=True)
class Wo08Assessment:
    payload: bytes

    def __post_init__(self):
        if type(self.payload) is not bytes:
            raise ValueError('WO08_ASSESSMENT_NOT_FROZEN')
        d = json.loads(self.payload)
        if canonical(d) != self.payload:
            raise ValueError('WO08_ASSESSMENT_NOT_CANONICAL')
        source = d['source_document']
        if set(source) != {'result', 'mapping', 'native'}:
            raise ValueError('WO08_SOURCE_FIELDS_INVALID')
        result = _from_wire(source['result'])
        mapping = None if source['mapping'] is None else _from_wire(source['mapping'])
        native = None if source['native'] is None else create_native_selection(**source['native'])
        expected = _assessment_values(run_identity=d['run_identity'], run_integrity=d['run_integrity'],
            result=result, mapping=mapping, native=native, created_at=d['created_at'])
        integrity = digest(expected)
        if d != dict(expected, assessment_identity='WO08-ASSESSMENT-'+integrity, integrity_sha256=integrity):
            raise ValueError('WO08_ASSESSMENT_INTEGRITY_INVALID')

    @property
    def data(self):
        return json.loads(self.payload)

    @property
    def identity(self):
        return self.data['assessment_identity']

    @property
    def integrity(self):
        return self.data['integrity_sha256']


def assess(**kwargs):
    values = _assessment_values(**kwargs)
    integrity = digest(values)
    return Wo08Assessment(canonical(dict(values, assessment_identity='WO08-ASSESSMENT-'+integrity,
                                        integrity_sha256=integrity)))
