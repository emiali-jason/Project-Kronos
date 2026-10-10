"""WO09 successor projection of exact WO08 machine assessment authority.

Historical V1 records retain their original bytes. This separately versioned
record never represents missing visual evidence as a reconciliation.
"""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from kronos.intraday.wo09_readiness import (
    AttentionState, CriterionId, CriterionSnapshot, CriterionState, CurrentnessState,
    HardGate, Monitorability, ReadinessState, ZERO_AUTHORITY, _aware, _identity,
    _texts, _valid_state, _without, artifact_bytes, create_requirement,
)

SCHEMA_IDENTITY = "KRONOS-INTRADAY-WO-09-MACHINE-READINESS-RECORD-V2"
POLICY_IDENTITY = "KRONOS-INTRADAY-WO-09-MACHINE-PROMOTION-READINESS-POLICY"
POLICY_VERSION = "2.0.0"
POLICY_CHECKSUM = sha256(artifact_bytes({
    "source": "WO08_VERSIONED_ASSESSMENT", "criteria": ("I1", "I2", "I3", "I4", "I5"),
    "counts": {"0-2": "NO_FOCUS", "3": "NEAR_READY", "4": "DIRECTION_READY", "5": "DIRECTION_NOW"},
    "unestablished": "READINESS_UNAVAILABLE", "current_method": "I2_I5_NOT_COMMISSIONED",
    "first_five": "FIRST_FIVE_TIME_NOT_ESTABLISHED", "authority": ZERO_AUTHORITY,
})).hexdigest()


@dataclass(frozen=True, slots=True)
class MachineReadinessRecord:
    readiness_identity: str
    integrity_identity: str
    canonical_subject_identity: str
    market_family: str
    exact_mcx_contract_identity: str | None
    exact_mcx_roll_lineage: str | None
    direction: str
    wo08_identity: str
    wo08_integrity: str
    methodology_identity: str
    methodology_version: str
    methodology_checksum: str
    assessment_disposition: str
    failure_stage: str | None
    failure_reason: str | None
    probables_run_identity: str
    probable_result_identity: str
    machine_evidence_identities: tuple[str, ...]
    machine_evidence_integrity: str | None
    analysis_boundary: datetime
    session_identity: str
    trading_date: str
    generation: str
    criteria: tuple[CriterionSnapshot, ...]
    hard_gate: HardGate
    satisfied_count: int | None
    outstanding_count: int | None
    readiness_state: ReadinessState
    attention_state: AttentionState
    currentness: CurrentnessState
    created_at: datetime
    source_provenance: tuple[str, ...]
    source_authority: str = "WO08"
    policy_identity: str = POLICY_IDENTITY
    policy_version: str = POLICY_VERSION
    policy_checksum: str = POLICY_CHECKSUM
    authority: str = ZERO_AUTHORITY
    schema_identity: str = SCHEMA_IDENTITY
    schema_version: str = "2.0.0"

    def __post_init__(self):
        values = _without(self, "readiness_identity", "integrity_identity")
        if (not _texts((self.canonical_subject_identity, self.wo08_identity, self.wo08_integrity,
                        self.methodology_identity, self.methodology_version, self.methodology_checksum,
                        self.probables_run_identity, self.probable_result_identity, self.session_identity,
                        self.trading_date, self.generation, self.assessment_disposition))
                or self.market_family not in {"NSE", "MCX"}
                or self.direction not in {"LONG", "SHORT", "UNAVAILABLE", "UNKNOWN", "NON_DIRECTIONAL", "CONFLICTING"}
                or not _aware(self.analysis_boundary) or not _aware(self.created_at)
                or tuple(item.criterion_id for item in self.criteria) != tuple(CriterionId)
                or any(type(item) is not CriterionSnapshot for item in self.criteria)
                or type(self.hard_gate) is not HardGate or type(self.currentness) is not CurrentnessState
                or not _valid_state(self)
                # The commissioned successor cannot establish visual-derived criteria.
                or any(item.state not in {CriterionState.UNAVAILABLE, CriterionState.NOT_APPLICABLE}
                       for item in self.criteria[1:])
                or self.readiness_state not in {ReadinessState.HARD_GATE, ReadinessState.READINESS_UNAVAILABLE}
                or self.source_authority != "WO08"
                or (self.policy_identity, self.policy_version, self.policy_checksum) !=
                   (POLICY_IDENTITY, POLICY_VERSION, POLICY_CHECKSUM)
                or (self.schema_identity, self.schema_version) != (SCHEMA_IDENTITY, "2.0.0")
                or self.authority != ZERO_AUTHORITY or not _texts(self.source_provenance)
                or self.readiness_identity != _identity("INTRADAY-WO09-MACHINE-READINESS-", values)
                or self.integrity_identity != _identity("INTEGRITY-INTRADAY-WO09-MACHINE-READINESS-", values)):
            raise ValueError("WO09_MACHINE_READINESS_INVALID")

    @property
    def outstanding(self):
        return tuple(item for item in self.criteria if item.state is CriterionState.OUTSTANDING)

    # Historical presentation compatibility only. No invented source identities
    # enter the successor record, serialized evidence, integrity or authority.
    wo07f_identity = property(lambda self: None)
    wo07f_integrity = property(lambda self: None)
    wo07f_outcome = property(lambda self: None)
    review_cycle_identity = property(lambda self: None)
    review_pack_identity = property(lambda self: None)
    chart_revision_identity = property(lambda self: None)
    answer_pack_identity = property(lambda self: None)
    answer_source_sha256 = property(lambda self: None)
    correspondence_identity = property(lambda self: None)
    visual_evidence_identity = property(lambda self: None)
    visual_evidence_integrity = property(lambda self: None)


def evaluate_machine_readiness(assessment, *, created_at):
    from kronos.intraday.wo08_assessment import Wo08Assessment
    if type(assessment) is not Wo08Assessment or not _aware(created_at):
        raise ValueError("WO09_WO08_ASSESSMENT_REQUIRED")
    assessment.__post_init__()
    data = assessment.data
    if created_at != datetime.fromisoformat(data["created_at"]):
        raise ValueError("WO09_WO08_PUBLICATION_TIME_MISMATCH")
    boundary = datetime.fromisoformat(data["analysis_boundary"])
    gate_value = data.get("hard_gate")
    gate = HardGate.NONE
    if gate_value and gate_value != "NONE":
        try:
            gate = HardGate(gate_value)
        except ValueError:
            gate = HardGate.INVALID_EXACT_EVIDENCE_BINDING
    if data["subject"].endswith("NATGAS"):
        gate = HardGate.NATGAS_COMMISSIONING_HELD
    categories = ("DIRECTION_STRUCTURE", "ESTABLISHMENT_FOLLOW_THROUGH", "PATH_OBSTACLE_CLEARANCE",
                  "SETUP_QUALITY", "ANALYTICAL_VISUAL_EXTENSION")
    criteria = []
    for position, criterion in enumerate(data["criteria"]):
        state = {"DETERMINISTICALLY_ESTABLISHED": CriterionState.SATISFIED,
                 "DETERMINISTICALLY_NEGATIVE": CriterionState.OUTSTANDING}.get(
                     criterion["state"], CriterionState.UNAVAILABLE)
        if gate is not HardGate.NONE:
            state = CriterionState.NOT_APPLICABLE
        criteria.append(CriterionSnapshot(
            criterion_id=CriterionId(criterion["criterion_id"]), category=categories[position], state=state,
            current_value=criterion.get("current_value"), required_value=None,
            gap="NONE" if state is CriterionState.SATISFIED else "NUMERIC_GAP_NOT_GOVERNED", unit=None,
            authority="WO08_MACHINE_ASSESSMENT", source_evidence_identity=assessment.identity,
            observation_boundary=boundary,
            monitorability=(Monitorability.FRESH_MACHINE_ANALYSIS_REQUIRED,),
            next_reassessment_trigger="NEXT_GOVERNED_MACHINE_ANALYSIS",
            reason_codes=tuple(criterion["reason_codes"])))
    values = dict(canonical_subject_identity=data["subject"], market_family=data["market_family"],
        exact_mcx_contract_identity=data.get("exact_mcx_contract_identity"),
        exact_mcx_roll_lineage=data.get("exact_mcx_roll_lineage"), direction=data["direction"] or "UNAVAILABLE",
        wo08_identity=assessment.identity, wo08_integrity=assessment.integrity,
        methodology_identity=data["methodology_identity"], methodology_version=data["methodology_version"],
        methodology_checksum=data["methodology_checksum"], assessment_disposition=data["disposition"],
        failure_stage=data.get("failure_stage"), failure_reason=data.get("failure_reason"),
        probables_run_identity=data["run_identity"], probable_result_identity=data["probable_result_identity"],
        machine_evidence_identities=tuple(data["machine_evidence_identities"]),
        machine_evidence_integrity=data.get("semantic_evidence_integrity"),
        analysis_boundary=boundary, session_identity=data["session_identity"], trading_date=data["trading_date"],
        generation=data["generation"], criteria=tuple(criteria), hard_gate=gate,
        satisfied_count=None, outstanding_count=None,
        readiness_state=ReadinessState.HARD_GATE if gate is not HardGate.NONE else ReadinessState.READINESS_UNAVAILABLE,
        attention_state=AttentionState.NONE, currentness=CurrentnessState.CURRENT, created_at=created_at,
        source_provenance=("WO08_IMMUTABLE_MACHINE_ASSESSMENT", "WO09_MACHINE_POLICY_V2"),
        source_authority="WO08", policy_identity=POLICY_IDENTITY, policy_version=POLICY_VERSION,
        policy_checksum=POLICY_CHECKSUM, authority=ZERO_AUTHORITY,
        schema_identity=SCHEMA_IDENTITY, schema_version="2.0.0")
    readiness = MachineReadinessRecord(
        readiness_identity=_identity("INTRADAY-WO09-MACHINE-READINESS-", values),
        integrity_identity=_identity("INTEGRITY-INTRADAY-WO09-MACHINE-READINESS-", values), **values)
    return readiness, tuple(create_requirement(readiness, item, created_at) for item in readiness.criteria)
