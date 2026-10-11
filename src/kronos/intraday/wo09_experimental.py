"""Prospective experimental PAPER readiness and original-event contracts.

Legacy machine V2 and visual V1 validators remain unchanged. A first-five fact
records a retained observation, never the historical first market occurrence.
"""
from dataclasses import dataclass, asdict
from datetime import datetime
from hashlib import sha256
from functools import lru_cache
import json

from kronos.intraday.wo09_machine_readiness import MachineReadinessRecord
from kronos.intraday.wo09_readiness import (
    NextWoHandoff, CriterionId, CriterionSnapshot, CriterionState, CurrentnessState,
    HardGate, Monitorability, ReadinessState, AttentionState, artifact_bytes,
    create_requirement, _without, _identity, _aware, _valid_state, _readiness_state, _attention,
)

POLICY_IDENTITY = 'KRONOS-INTRADAY-WO09-EXPERIMENTAL-PAPER-READINESS'
POLICY_VERSION = '0.1.0'
AUTHORITY = 'EXPERIMENTAL_PAPER_ONLY'
SCHEMA_IDENTITY = 'KRONOS-INTRADAY-WO09-EXPERIMENTAL-PAPER-READINESS-V1'
HANDOFF_SCHEMA = 'KRONOS-INTRADAY-WO09-EXPERIMENTAL-PAPER-HANDOFF-V1'
FIRST_FIVE_SCHEMA = 'KRONOS-INTRADAY-WO09-PROSPECTIVE-FIRST-FIVE-V1'
POLICY_CHECKSUM = sha256(artifact_bytes(dict(
    method='KRONOS-INTRADAY-WO08-EXPERIMENTAL-PULLBACK-PAPER/0.1.0',
    authority=AUTHORITY, first_five='IMMUTABLE_FIRST_RETAINED_SOURCE_VALID_OBSERVATION',
    watch='FOUR_OF_FIVE_I2_OR_I3_ONLY', tick='ADVISORY_ONLY',
    counts='0-2:NO_FOCUS;3:NEAR_READY;4:READY;5:NOW', freshness_seconds=300,
))).hexdigest()


@lru_cache(maxsize=128)
def _assessment_bytes(payload):
    # Validation reuse only: immutable payload bytes are the complete key.
    # Current pointers, source generations, origin and clocks are never cached.
    from kronos.intraday.wo08_experimental import ExperimentalWo08Assessment
    return ExperimentalWo08Assessment(payload)


def assessment_from(document):
    from kronos.intraday.wo08_assessment import canonical
    return _assessment_bytes(canonical(document))


def origin_from(document):
    from kronos.intraday.wo12_research_contract import ResearchRecord, require
    origin = ResearchRecord(**document)
    require(origin, 'WO12_OPPORTUNITY_ORIGIN_V1')
    return origin


def claim_for(assessment, origin):
    d, o = assessment.data, origin.data
    if (o['canonical_subject_identity'] != d['subject']
            or o['market_session_identity'] != d['session_identity']
            or datetime.fromisoformat(o['origin_at']) > datetime.fromisoformat(d['analysis_boundary'])):
        raise ValueError('EXPERIMENTAL_OPPORTUNITY_BINDING_INVALID')
    expiry = None
    if d['market_family'] == 'MCX' and d.get('exact_mcx_contract_identity') is not None:
        from kronos.intraday.native_pullback_decision import decode_source
        binding = decode_source(d['source_document']['native_source'])[3]
        if binding is None or binding.binding_identity != d['exact_mcx_roll_lineage']:
            raise ValueError('EXPERIMENTAL_CLAIM_CONTRACT_BINDING_INVALID')
        expiry = binding.contract_expiry.isoformat()
    # An operation binding includes observation boundary and provider snapshot.
    # It remains in the immutable source graph, but is not a contract roll. Exact
    # owner contract/expiry changes distinguish a roll without replaying history.
    return dict(opportunity_identity=o['opportunity_identity'], subject=d['subject'],
        direction=d['direction'], session_identity=d['session_identity'],
        exact_contract=d.get('exact_mcx_contract_identity'), contract_expiry=expiry,
        methodology_identity=d['methodology_identity'], methodology_version=d['methodology_version'],
        methodology_checksum=d['methodology_checksum'])


def claim_identity(claim):
    return _identity('INTRADAY-WO09-FIRST-FIVE-CLAIM-', claim)


@dataclass(frozen=True, slots=True)
class FirstFiveObservation:
    claim: dict
    claim_identity: str
    assessment_document: dict
    origin_document: dict
    observed_at: datetime
    source_boundary: datetime
    generation: str
    fact_identity: str
    integrity_identity: str
    schema_identity: str = FIRST_FIVE_SCHEMA
    schema_version: str = '0.1.0'
    authority: str = AUTHORITY

    def __post_init__(self):
        assessment = assessment_from(self.assessment_document)
        origin = origin_from(self.origin_document)
        data = assessment.data
        values = _without(self, 'fact_identity', 'integrity_identity')
        if (self.schema_identity != FIRST_FIVE_SCHEMA or self.schema_version != '0.1.0'
                or self.authority != AUTHORITY or self.claim != claim_for(assessment, origin)
                or self.claim_identity != claim_identity(self.claim)
                or not _aware(self.observed_at) or not _aware(self.source_boundary)
                or self.source_boundary != datetime.fromisoformat(data['analysis_boundary'])
                or self.observed_at < datetime.fromisoformat(data['created_at'])
                or self.observed_at < self.source_boundary or self.generation != data['generation']
                or data.get('hard_gate') not in {None, 'NONE'}
                or any(c['state'] != 'SATISFIED' for c in data['criteria'])
                or self.fact_identity != _identity('INTRADAY-WO09-FIRST-FIVE-', values)
                or self.integrity_identity != _identity('INTEGRITY-INTRADAY-WO09-FIRST-FIVE-', values)):
            raise ValueError('EXPERIMENTAL_FIRST_FIVE_INVALID')

    @property
    def document(self):
        return json.loads(artifact_bytes(self))


def first_five_from(document):
    d = dict(document)
    d['observed_at'] = datetime.fromisoformat(d['observed_at'])
    d['source_boundary'] = datetime.fromisoformat(d['source_boundary'])
    return FirstFiveObservation(**d)


def observe_first_five(assessment, origin, *, observed_at):
    claim = claim_for(assessment, origin)
    values = dict(claim=claim, claim_identity=claim_identity(claim),
        assessment_document=assessment.data, origin_document=asdict(origin), observed_at=observed_at,
        source_boundary=datetime.fromisoformat(assessment.data['analysis_boundary']),
        generation=assessment.data['generation'], schema_identity=FIRST_FIVE_SCHEMA,
        schema_version='0.1.0', authority=AUTHORITY)
    return FirstFiveObservation(fact_identity=_identity('INTRADAY-WO09-FIRST-FIVE-', values),
        integrity_identity=_identity('INTEGRITY-INTRADAY-WO09-FIRST-FIVE-', values), **values)


def _projection(assessment, *, observed_at, origin, first_five):
    d = assessment.data
    if not _aware(observed_at) or observed_at < datetime.fromisoformat(d['created_at']):
        raise ValueError('EXPERIMENTAL_OBSERVATION_TIME_INVALID')
    boundary = datetime.fromisoformat(d['analysis_boundary'])
    gate = HardGate.NONE
    if d.get('hard_gate') not in {None, 'NONE'}:
        try:
            gate = HardGate(d['hard_gate'])
        except ValueError:
            gate = HardGate.INVALID_EXACT_EVIDENCE_BINDING
    if d['subject'].endswith('NATGAS'):
        gate = HardGate.NATGAS_COMMISSIONING_HELD
    categories = ('DIRECTION_STRUCTURE', 'ESTABLISHMENT_FOLLOW_THROUGH', 'PATH_OBSTACLE_CLEARANCE',
                  'SETUP_QUALITY', 'ANALYTICAL_VISUAL_EXTENSION')
    criteria = tuple(CriterionSnapshot(criterion_id=CriterionId(c['criterion_id']),
        category=categories[i], state=CriterionState.NOT_APPLICABLE if gate is not HardGate.NONE else CriterionState(c['state']),
        current_value=c.get('current_value'), required_value=None,
        gap='NONE' if c['state'] == 'SATISFIED' else 'NUMERIC_GAP_NOT_GOVERNED', unit=None,
        authority=AUTHORITY, source_evidence_identity=assessment.identity, observation_boundary=boundary,
        monitorability=(Monitorability.FRESH_MACHINE_ANALYSIS_REQUIRED,),
        next_reassessment_trigger='NEXT_GOVERNED_MACHINE_ANALYSIS', reason_codes=tuple(c['reason_codes']))
        for i, c in enumerate(d['criteria']))
    evaluable = gate is HardGate.NONE and all(c.state in {CriterionState.SATISFIED, CriterionState.OUTSTANDING} for c in criteria)
    count = sum(c.state is CriterionState.SATISFIED for c in criteria) if evaluable else None
    state = (ReadinessState.HARD_GATE if gate is not HardGate.NONE else
             _readiness_state(d['direction'], count) if evaluable else ReadinessState.READINESS_UNAVAILABLE)
    if origin is not None:
        claim = claim_for(assessment, origin)
        if first_five is not None and (first_five.claim != claim or first_five.observed_at > observed_at):
            raise ValueError('EXPERIMENTAL_FIRST_FIVE_CLAIM_MISMATCH')
    elif first_five is not None or evaluable:
        raise ValueError('EXPERIMENTAL_RETAINED_OPPORTUNITY_REQUIRED')
    return dict(canonical_subject_identity=d['subject'], market_family=d['market_family'],
        exact_mcx_contract_identity=d.get('exact_mcx_contract_identity'), exact_mcx_roll_lineage=d.get('exact_mcx_roll_lineage'),
        direction=d['direction'] or 'UNAVAILABLE', wo08_identity=assessment.identity, wo08_integrity=assessment.integrity,
        methodology_identity=d['methodology_identity'], methodology_version=d['methodology_version'],
        methodology_checksum=d['methodology_checksum'], assessment_disposition=d['disposition'],
        failure_stage=d.get('failure_stage'), failure_reason=d.get('failure_reason'),
        probables_run_identity=d['run_identity'], probable_result_identity=d['probable_result_identity'],
        machine_evidence_identities=tuple(d['machine_evidence_identities']), machine_evidence_integrity=d.get('semantic_evidence_integrity'),
        analysis_boundary=boundary, session_identity=d['session_identity'], trading_date=d['trading_date'],
        generation=d['generation'], criteria=criteria, hard_gate=gate, satisfied_count=count,
        outstanding_count=5-count if evaluable else None, readiness_state=state, attention_state=_attention(state),
        currentness=CurrentnessState.CURRENT, created_at=observed_at,
        assessment_published_at=datetime.fromisoformat(d['created_at']),
        opportunity_identity=None if origin is None else origin.data['opportunity_identity'],
        origin_document=None if origin is None else asdict(origin), assessment_document=d,
        first_five_document=None if first_five is None else first_five.document,
        source_provenance=('WO08_EXPERIMENTAL_SOURCE_VALIDATED', 'PROSPECTIVE_OBSERVATION_ONLY'),
        source_authority='WO08', policy_identity=POLICY_IDENTITY, policy_version=POLICY_VERSION,
        policy_checksum=POLICY_CHECKSUM, authority=AUTHORITY, schema_identity=SCHEMA_IDENTITY, schema_version='0.1.0')


@dataclass(frozen=True, slots=True)
class ExperimentalReadinessRecord(MachineReadinessRecord):
    assessment_published_at: datetime | None = None
    opportunity_identity: str | None = None
    origin_document: dict | None = None
    assessment_document: dict | None = None
    first_five_document: dict | None = None

    def __post_init__(self):
        assessment = assessment_from(self.assessment_document)
        origin = None if self.origin_document is None else origin_from(self.origin_document)
        first = None if self.first_five_document is None else first_five_from(self.first_five_document)
        expected = _projection(assessment, observed_at=self.created_at, origin=origin, first_five=first)
        values = _without(self, 'readiness_identity', 'integrity_identity')
        if (values != expected or not _valid_state(self)
                or self.readiness_identity != _identity('INTRADAY-WO09-EXPERIMENTAL-', values)
                or self.integrity_identity != _identity('INTEGRITY-INTRADAY-WO09-EXPERIMENTAL-', values)):
            raise ValueError('EXPERIMENTAL_READINESS_INVALID')

    @property
    def first_five_of_five_at(self):
        return None if self.first_five_document is None else first_five_from(self.first_five_document).observed_at


def evaluate_experimental_readiness(assessment, *, observed_at, origin=None, first_five=None):
    from kronos.intraday.wo08_experimental import ExperimentalWo08Assessment
    if type(assessment) is not ExperimentalWo08Assessment:
        raise ValueError('EXPERIMENTAL_ASSESSMENT_REQUIRED')
    assessment = _assessment_bytes(assessment.payload)
    values = _projection(assessment, observed_at=observed_at, origin=origin, first_five=first_five)
    record = ExperimentalReadinessRecord(readiness_identity=_identity('INTRADAY-WO09-EXPERIMENTAL-', values),
        integrity_identity=_identity('INTEGRITY-INTRADAY-WO09-EXPERIMENTAL-', values), **values)
    return record, tuple(create_requirement(record, c, observed_at) for c in record.criteria)


@dataclass(frozen=True, slots=True)
class ExperimentalNextWoHandoff(NextWoHandoff):
    methodology_identity: str | None = None
    methodology_version: str | None = None
    methodology_checksum: str | None = None
    wo08_identity: str | None = None
    wo08_integrity: str | None = None
    opportunity_identity: str | None = None
    first_five_document: dict | None = None
    readiness_document: dict | None = None

    def __post_init__(self):
        from kronos.intraday.wo09_persistence import _readiness
        record = _readiness(self.readiness_document)
        if type(record) is not ExperimentalReadinessRecord:
            raise ValueError('EXPERIMENTAL_HANDOFF_SOURCE_REQUIRED')
        expected = _handoff_values(record, created_at=self.created_at,
            current_readiness_identity=self.current_readiness_identity,
            current_pointer_integrity=self.current_pointer_integrity, currentness=self.currentness,
            superseded_readiness_identity=self.superseded_readiness_identity)
        values = _without(self, 'handoff_identity', 'integrity_identity')
        if (values != expected or self.handoff_identity != _identity('INTRADAY-WO09-EXPERIMENTAL-HANDOFF-', values)
                or self.integrity_identity != _identity('INTEGRITY-INTRADAY-WO09-EXPERIMENTAL-HANDOFF-', values)):
            raise ValueError('EXPERIMENTAL_HANDOFF_INVALID')


def _handoff_values(r, *, created_at, current_readiness_identity, current_pointer_integrity,
                    currentness, superseded_readiness_identity):
    from kronos.intraday.wo10_futures_contract import fresh
    if (type(r) is not ExperimentalReadinessRecord or r.satisfied_count != 5
            or r.hard_gate is not HardGate.NONE or r.first_five_document is None
            or currentness is not CurrentnessState.CURRENT or r.currentness is not CurrentnessState.CURRENT
            or current_readiness_identity != r.readiness_identity or not current_pointer_integrity
            or not _aware(created_at) or created_at < r.created_at
            or not fresh(r.first_five_of_five_at, created_at, 300)):
        raise ValueError('EXPERIMENTAL_HANDOFF_NOT_CURRENT_FIVE')
    names = ('policy_identity', 'policy_version', 'policy_checksum', 'canonical_subject_identity',
        'market_family', 'direction', 'exact_mcx_contract_identity', 'exact_mcx_roll_lineage',
        'criteria', 'satisfied_count', 'hard_gate', 'readiness_state', 'analysis_boundary', 'session_identity',
        'machine_evidence_identities', 'machine_evidence_integrity', 'methodology_identity', 'methodology_version',
        'methodology_checksum', 'wo08_identity', 'wo08_integrity', 'opportunity_identity', 'first_five_document')
    values = {name: getattr(r, name) for name in names}
    return dict(values, readiness_identity=r.readiness_identity, readiness_integrity=r.integrity_identity,
        current_readiness_identity=current_readiness_identity, current_pointer_integrity=current_pointer_integrity,
        currentness=currentness, superseded_readiness_identity=superseded_readiness_identity,
        wo07f_identity=None, wo07f_outcome=None, visual_evidence_identity=None, visual_evidence_integrity=None,
        created_at=created_at, first_five_of_five_at=r.first_five_of_five_at,
        readiness_document=json.loads(artifact_bytes(r)), authority=AUTHORITY,
        schema_identity=HANDOFF_SCHEMA, schema_version='0.1.0')


def create_experimental_handoff(readiness, **kwargs):
    supplied = kwargs.pop('first_five_of_five_at', None)
    if supplied is not None and supplied != readiness.first_five_of_five_at:
        raise ValueError('EXPERIMENTAL_CALLER_FIRST_FIVE_NOT_AUTHORITY')
    values = _handoff_values(readiness, **kwargs)
    return ExperimentalNextWoHandoff(handoff_identity=_identity('INTRADAY-WO09-EXPERIMENTAL-HANDOFF-', values),
        integrity_identity=_identity('INTEGRITY-INTRADAY-WO09-EXPERIMENTAL-HANDOFF-', values), **values)
