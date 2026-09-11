"""Exact WO-09 intake into existing geometry engines (ADR-0039)."""
from dataclasses import dataclass
from datetime import datetime

from kronos.intraday.wo09_readiness import (
    NextWoHandoff, ReadinessRecord, CurrentnessState, ReadinessState,
    CriterionId, CriterionState, HardGate, POLICY_IDENTITY, POLICY_VERSION, POLICY_CHECKSUM,
)
from kronos.intraday.wo09_persistence import CurrentPointer
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo13_handoff import Wo13SetupFamily
from kronos.intraday.wo10_futures_contract import record, digest, fresh, PROGRAMME


def validate_intake(handoff, readiness, pointer, *, now, session_identity):
    if (type(handoff) is not NextWoHandoff or type(readiness) is not ReadinessRecord
            or type(pointer) is not CurrentPointer):
        raise ValueError("WO10_EXACT_WO09_TYPES_REQUIRED")
    for value in (handoff, readiness, pointer):
        value.__post_init__()
    if (readiness.canonical_subject_identity == "MCX-NATGAS"
            or readiness.canonical_subject_identity.endswith("NATGAS")):
        raise ValueError("WO10_NATGAS_HELD")
    if (pointer.currentness is not CurrentnessState.CURRENT
            or readiness.currentness is not CurrentnessState.CURRENT
            or handoff.currentness is not CurrentnessState.CURRENT
            or pointer.readiness_identity != readiness.readiness_identity
            or pointer.readiness_integrity != readiness.integrity_identity
            or pointer.canonical_subject_identity != readiness.canonical_subject_identity
            or handoff.current_pointer_integrity != pointer.integrity_identity
            or handoff.current_readiness_identity != readiness.readiness_identity
            or readiness.outstanding_count != 0 or readiness.satisfied_count != 5
            or readiness.hard_gate is not HardGate.NONE
            or tuple(c.criterion_id for c in readiness.criteria) != tuple(CriterionId)
            or any(c.state is not CriterionState.SATISFIED for c in readiness.criteria)
            or readiness.readiness_state not in {ReadinessState.BUY_NOW, ReadinessState.SELL_NOW}
            or readiness.direction != ("LONG" if readiness.readiness_state is ReadinessState.BUY_NOW else "SHORT")
            or readiness.session_identity != session_identity
            or (readiness.policy_identity, readiness.policy_version, readiness.policy_checksum)
               != (POLICY_IDENTITY, POLICY_VERSION, POLICY_CHECKSUM)):
        raise ValueError("WO10_WO09_NOT_EXACT_CURRENT_FIVE_OF_FIVE")
    names = ("policy_identity", "policy_version", "policy_checksum", "canonical_subject_identity",
             "market_family", "direction", "exact_mcx_contract_identity", "exact_mcx_roll_lineage",
             "wo07f_identity", "wo07f_outcome", "criteria", "satisfied_count", "hard_gate",
             "readiness_state", "analysis_boundary", "session_identity", "machine_evidence_identities",
             "machine_evidence_integrity", "visual_evidence_identity", "visual_evidence_integrity")
    if (handoff.readiness_identity != readiness.readiness_identity
            or handoff.readiness_integrity != readiness.integrity_identity
            or any(getattr(handoff, n) != getattr(readiness, n) for n in names)):
        raise ValueError("WO10_HANDOFF_LINEAGE_MISMATCH")
    if (handoff.first_five_of_five_at is None
            or handoff.first_five_of_five_at > readiness.created_at
            or not fresh(handoff.first_five_of_five_at, now, 300)
            or not fresh(handoff.created_at, now, 300)):
        raise ValueError("WO10_WO09_STALE")


@dataclass(frozen=True, slots=True)
class Wo10ConstructionAdapter:
    """Explicit new epoch input, never a fabricated historical handoff."""
    handoff_identity: str
    handoff_integrity: str
    wo09: NextWoHandoff
    setup_family: Wo13SetupFamily
    setup_evidence_identity: str
    instrument_identity: str
    canonical_subject_identity: str
    market_family: IntradayMarketFamily
    inherited_direction: SemanticDirection
    analysis_boundary: datetime
    actual_contract_identity: str | None
    roll_lineage_identity: str | None
    native_selection: object = None
    programme_identity: str = PROGRAMME

    def __post_init__(self):
        material = {k: v for k, v in vars_from(self).items() if k not in {"handoff_identity", "handoff_integrity"}}
        native_bound = False
        if self.native_selection is not None:
            from kronos.intraday.native_structural_selection import NativeStructuralSelection, APPROVED_NATIVE_SELECTION_POLICIES
            if type(self.native_selection) is not NativeStructuralSelection:raise ValueError("WO10_NATIVE_SELECTION_INVALID")
            self.native_selection.__post_init__(); native=self.native_selection.data
            native_bound=(native.get("contract_version")=="1.1.0" and native.get("result")=="PULLBACK"
                and tuple(native[k] for k in ("policy_identity","policy_version","policy_checksum")) in APPROVED_NATIVE_SELECTION_POLICIES
                and self.setup_evidence_identity==native["setup_identity"]
                and native["machine_identity"] in self.wo09.machine_evidence_identities
                and native["machine_integrity"]==self.wo09.machine_evidence_integrity
                and native["subject"]==self.wo09.canonical_subject_identity
                and native["direction"]==self.wo09.direction
                and native["session"]==self.wo09.session_identity
                and native["exact_contract"]==self.wo09.exact_mcx_contract_identity
                and native["roll_lineage"]==self.wo09.exact_mcx_roll_lineage
                and self.setup_family is Wo13SetupFamily.INTRADAY_PULLBACK_CONTINUATION)
            if not native_bound:raise ValueError("WO10_NATIVE_SELECTION_INVALID")
        if (type(self.wo09) is not NextWoHandoff or self.programme_identity != PROGRAMME
                or not native_bound and self.setup_evidence_identity not in self.wo09.machine_evidence_identities
                or self.canonical_subject_identity != self.wo09.canonical_subject_identity
                or self.inherited_direction.value != self.wo09.direction
                or self.analysis_boundary != self.wo09.analysis_boundary
                or self.actual_contract_identity != self.wo09.exact_mcx_contract_identity
                or self.roll_lineage_identity != self.wo09.exact_mcx_roll_lineage
                or not self.instrument_identity
                or type(self.setup_family) is not Wo13SetupFamily
                or self.handoff_integrity != digest(material)
                or self.handoff_identity != "WO10_FROM_WO09_CONSTRUCTION_ADAPTER_V1-" + digest(material)):
            raise ValueError("WO10_CONSTRUCTION_ADAPTER_INVALID")
        self.wo09.__post_init__()


def vars_from(value):
    from dataclasses import fields
    return {field.name: getattr(value, field.name) for field in fields(value)}


def adapt_wo09(handoff, readiness, pointer, *, now, session_identity,
               setup_family, setup_evidence_identity, instrument_identity, native_selection=None):
    validate_intake(handoff, readiness, pointer, now=now, session_identity=session_identity)
    subject = handoff.canonical_subject_identity
    family = (IntradayMarketFamily.MCX if subject.startswith("MCX-") else
              IntradayMarketFamily.NSE_EQUITY if subject.startswith("NSE-EQ-") else IntradayMarketFamily.NSE_INDEX)
    values = dict(wo09=handoff, native_selection=native_selection, setup_family=setup_family, setup_evidence_identity=setup_evidence_identity,
                  instrument_identity=instrument_identity, canonical_subject_identity=subject,
                  market_family=family, inherited_direction=SemanticDirection(handoff.direction),
                  analysis_boundary=handoff.analysis_boundary,
                  actual_contract_identity=handoff.exact_mcx_contract_identity,
                  roll_lineage_identity=handoff.exact_mcx_roll_lineage, programme_identity=PROGRAMME)
    integrity = digest(values)
    return Wo10ConstructionAdapter(handoff_identity="WO10_FROM_WO09_CONSTRUCTION_ADAPTER_V1-" + integrity,
                                   handoff_integrity=integrity, **values)


def _construct_plan(adapter, evidence, target_population, *, now):
    from kronos.intraday.wo13_pullback import Wo13PullbackGeometryEvidence, construct_wo13_pullback_geometry
    from kronos.intraday.wo13_breakout import Wo13BreakoutGeometryEvidence, construct_wo13_breakout_geometry
    from kronos.intraday.wo13_adapters import finalize_wo13_family_geometry
    from kronos.intraday.wo13 import WO13_POLICY_IDENTITY, WO13_POLICY_CHECKSUM
    if type(adapter) is not Wo10ConstructionAdapter or evidence.handoff != adapter:
        raise ValueError("WO10_GEOMETRY_SOURCE_MISMATCH")
    adapter.__post_init__()
    evidence.__post_init__()
    constructors = {Wo13PullbackGeometryEvidence: construct_wo13_pullback_geometry,
                    Wo13BreakoutGeometryEvidence: construct_wo13_breakout_geometry}
    if type(evidence) not in constructors:
        raise ValueError("WO10_SETUP_EVIDENCE_INVALID")
    geometry = constructors[type(evidence)](evidence)
    selection = finalize_wo13_family_geometry(setup_geometry=geometry, candidate_population=target_population).selection
    entry, stop, target = (selection.entry_reference.selected_fact, geometry.stop.selected_fact,
                           selection.canonical_target.selected_fact)
    inv = geometry.thesis_invalidation_reference.selected_fact
    values = {"entry": None if entry is None else entry.price,
              "stop": None if stop is None else stop.price, "target": None if target is None else target.price}
    valid = all(v is not None for v in values.values()) and inv is not None and geometry.thesis_invalidation_event is not None
    if valid:
        sign = 1 if adapter.wo09.direction == "LONG" else -1
        valid = sign * (values["target"] - values["entry"]) > 0 and sign * (values["entry"] - values["stop"]) > 0
    return record("WO10_CANONICAL_TRADE_PLAN_V1", **values,
                  state="AVAILABLE" if valid else "TRADE_PLAN_UNAVAILABLE",
                  reason=None if valid else "GOVERNED_GEOMETRY_UNAVAILABLE_OR_NON_FORWARD",
                  adapter=adapter, wo09=adapter.wo09, created_at=now,
                  session_identity=adapter.wo09.session_identity, subject=adapter.canonical_subject_identity,
                  direction=adapter.wo09.direction, invalidation_reference=None if inv is None else inv.price,
                  invalidation=geometry.thesis_invalidation_event, entry_condition=geometry.entry_condition,
                  stop_basis=None if stop is None else stop.structural_role,
                  target_basis=None if target is None else target.structural_role,
                  risk_distance=selection.risk_distance, reward_distance=selection.reward_distance,
                  model_rr=selection.model_rr, geometry=geometry, selection=selection,
                  construction_subpolicy=WO13_POLICY_IDENTITY, construction_checksum=WO13_POLICY_CHECKSUM)


def construct_plan(adapter, evidence, target_population, *, now):
    try:
        return _construct_plan(adapter, evidence, target_population, now=now)
    except ValueError as error:
        # Mathematical source unavailability is retained; hard trust errors still reject.
        if str(error) not in {"NATIVE_TARGET_NOT_FORWARD", "SETUP_GEOMETRY_INVALID"}:
            raise
        return record("WO10_CANONICAL_TRADE_PLAN_V1", state="TRADE_PLAN_UNAVAILABLE",
                      reason=str(error), adapter=adapter, wo09=adapter.wo09, created_at=now,
                      subject=adapter.canonical_subject_identity, direction=adapter.wo09.direction,
                      session_identity=adapter.wo09.session_identity, source_evidence=evidence,
                      target_population=target_population, entry=None, stop=None, target=None,
                      risk_distance=None, reward_distance=None, model_rr=None,
                      invalidation=None, invalidation_reference=None, entry_condition=None,
                      stop_basis=None, target_basis=None)
