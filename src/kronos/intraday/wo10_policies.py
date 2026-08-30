"""Fail-closed policy protocol and deterministic WO-10 Equity policy."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Protocol, runtime_checkable

from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.nifty_relative_context import (
    NiftyApplicability,
    NiftyRelativeContextEvidence,
    NiftyRelationship,
)
from kronos.intraday.probables_v2 import (
    SemanticQualificationEvidenceV2,
    SemanticQualificationFactV2,
)
from kronos.intraday.review import ObservationStatus
from kronos.intraday.review_v2 import ImportedVisualEvidenceV2
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10 import (
    Wo10ContractError,
    Wo10PolicyBinding,
    Wo10ReasonCode,
    Wo10ReasonScope,
    Wo10ReconciliationRequest,
    Wo10State,
    create_wo10_policy_binding,
    _identity,
    _reason_key,
    _text,
    reason_applies_to_family,
)
from kronos.intraday.wo10_evidence import (
    Wo10EquityEvidenceExtension,
    Wo10EvidenceReference,
    Wo10EvidenceSnapshot,
)
from kronos.intraday.wo10_facts import (
    Wo10RsiFact,
    Wo10SmaFacts,
    Wo10StructuralLocationFacts,
    Wo10VolumeFact,
)


WO10_EQUITY_POLICY_IDENTITY = (
    "KRONOS-INTRADAY-WO10E-EQUITY-RECONCILIATION-POLICY-V1"
)
WO10_EQUITY_POLICY_VERSION = "1.0.0"
WO10_EQUITY_POLICY_PUBLICATION_IDENTITY = (
    "KRONOS-INTRADAY-WO-10-E-I-M-FROZEN-ARCHITECTURE-V1"
)
WO10_EQUITY_POLICY_AUTHORITY_VERSION = "1.0.0"
WO10_EQUITY_POLICY_EVIDENCE_IDENTITY = (
    "KRONOS-INTRADAY-WO10E-EQUITY-POLICY-EVIDENCE-V1"
)
WO10_EQUITY_POLICY_EVIDENCE_VERSION = "1.0.0"

WO10_EQUITY_POLICY_UNRESOLVED = (
    ("CONFLUENCE_DISTANCE", "INFORMATIONAL_DEFERRED"),
    ("EXTENSION_CHASE_THRESHOLD", "INFORMATIONAL_DEFERRED"),
    ("FLAT_TANGLED_THRESHOLD", "INFORMATIONAL_DEFERRED"),
    ("MATERIAL_CRISSCROSS", "INFORMATIONAL_DEFERRED"),
    ("MATERIAL_RAILWAY_SEPARATION", "INFORMATIONAL_DEFERRED"),
    ("MIDDLE_OF_RANGE", "INFORMATIONAL_DEFERRED"),
    ("NEW_CPR_PREDICTIVE_CONSEQUENCE", "INFORMATIONAL_DEFERRED"),
    ("RELATIVE_STRENGTH_MATERIALITY", "INFORMATIONAL_DEFERRED"),
    ("VOLUME_CONSEQUENCE", "INFORMATIONAL_DEFERRED"),
)

_EQUITY_POLICY_DOCUMENT = {
    "authority_identity": WO10_EQUITY_POLICY_PUBLICATION_IDENTITY,
    "authority_version": WO10_EQUITY_POLICY_AUTHORITY_VERSION,
    "market_family": IntradayMarketFamily.NSE_EQUITY.value,
    "policy_identity": WO10_EQUITY_POLICY_IDENTITY,
    "policy_version": WO10_EQUITY_POLICY_VERSION,
    "precedence": tuple(item.value for item in Wo10State),
    "timeframe_authority": {
        "1D": "BROADER_CONTEXT",
        "1H": "INTRADAY_REGIME",
        "15M": "PRIMARY_DIRECTIONAL_SETUP_STRUCTURE",
        "5M": "IMMEDIATE_ANALYTICAL_PROGRESSION",
    },
    "nifty": {
        "15M": "PRIMARY_BENCHMARK_COMPARISON_INFORMATIONAL",
        "1H": "BROADER_BENCHMARK_CONTEXT_INFORMATIONAL",
        "5M": "NOT_MANDATORY_WO10E",
        "opposition_alone": "NO_VETO",
        "rescue_stock_failure": False,
    },
    "rsi": "FACTUAL_ONLY_NO_DIRECTION_OR_STATE_AUTHORITY",
    "railway": "EXACT_LOWER_LEVEL_FACTS_ONLY_NO_SCORE",
    "structural_location": "FACTUAL_ONLY_NO_PROXIMITY_CONSEQUENCE",
    "volume": "RAW_INFORMATIONAL_NO_THRESHOLD",
    "visual": "OBSERVATION_RECONCILED_WITH_NATIVE_NO_PROMOTION_AUTHORITY",
    "unresolved": WO10_EQUITY_POLICY_UNRESOLVED,
}
WO10_EQUITY_POLICY_CHECKSUM = sha256(json.dumps(
    _EQUITY_POLICY_DOCUMENT,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")).hexdigest()


def wo10_equity_policy_binding() -> Wo10PolicyBinding:
    """Return the exact immutable WO-10E publication binding."""

    return create_wo10_policy_binding(
        policy_identity=WO10_EQUITY_POLICY_IDENTITY,
        policy_version=WO10_EQUITY_POLICY_VERSION,
        publication_identity=WO10_EQUITY_POLICY_PUBLICATION_IDENTITY,
        policy_checksum=WO10_EQUITY_POLICY_CHECKSUM,
        supported_market_family=IntradayMarketFamily.NSE_EQUITY,
    )


@dataclass(frozen=True, slots=True)
class Wo10EquityPolicyEvidence:
    """Exact loaded artifacts used by the pure Equity policy adapter.

    The common snapshot intentionally retains references.  This immutable
    adapter supplies their exact values to the policy and is not a persistence
    or runtime contract.
    """

    evidence_identity: str
    integrity_identity: str
    snapshot: Wo10EvidenceSnapshot
    source_semantic_evidence: SemanticQualificationEvidenceV2 | None
    one_day_context: SemanticQualificationFactV2 | None
    one_hour_regime: SemanticQualificationFactV2 | None
    fifteen_minute_structure: SemanticQualificationFactV2 | None
    five_minute_progression: SemanticQualificationFactV2 | None
    rsi: Wo10RsiFact | None
    railway_track: Wo10SmaFacts | None
    structural_location: Wo10StructuralLocationFacts | None
    volume_telemetry: Wo10VolumeFact | None
    nifty_fifteen_minute_context: SemanticQualificationFactV2 | None
    nifty_one_hour_context: SemanticQualificationFactV2 | None
    nifty_relationship: NiftyRelativeContextEvidence | None
    imported_visual_evidence: ImportedVisualEvidenceV2 | None
    schema_identity: str = WO10_EQUITY_POLICY_EVIDENCE_IDENTITY
    schema_version: str = WO10_EQUITY_POLICY_EVIDENCE_VERSION

    def __post_init__(self) -> None:
        values = _equity_evidence_values(self)
        typed = (
            (self.source_semantic_evidence, SemanticQualificationEvidenceV2),
            (self.one_day_context, SemanticQualificationFactV2),
            (self.one_hour_regime, SemanticQualificationFactV2),
            (self.fifteen_minute_structure, SemanticQualificationFactV2),
            (self.five_minute_progression, SemanticQualificationFactV2),
            (self.rsi, Wo10RsiFact),
            (self.railway_track, Wo10SmaFacts),
            (self.structural_location, Wo10StructuralLocationFacts),
            (self.volume_telemetry, Wo10VolumeFact),
            (self.nifty_fifteen_minute_context, SemanticQualificationFactV2),
            (self.nifty_one_hour_context, SemanticQualificationFactV2),
            (self.nifty_relationship, NiftyRelativeContextEvidence),
            (self.imported_visual_evidence, ImportedVisualEvidenceV2),
        )
        if (
            type(self.snapshot) is not Wo10EvidenceSnapshot
            or self.snapshot.market_family is not IntradayMarketFamily.NSE_EQUITY
            or any(
                item is not None and type(item) is not expected
                for item, expected in typed
            )
            or self.schema_identity != WO10_EQUITY_POLICY_EVIDENCE_IDENTITY
            or self.schema_version != WO10_EQUITY_POLICY_EVIDENCE_VERSION
            or self.evidence_identity
            != _identity("INTRADAY-WO10E-POLICY-EVIDENCE-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-WO10E-POLICY-EVIDENCE-", values)
        ):
            raise Wo10ContractError("WO10_EQUITY_POLICY_EVIDENCE_INVALID")


def create_wo10_equity_policy_evidence(
    *,
    snapshot: Wo10EvidenceSnapshot,
    source_semantic_evidence: SemanticQualificationEvidenceV2 | None,
    one_day_context: SemanticQualificationFactV2 | None,
    one_hour_regime: SemanticQualificationFactV2 | None,
    fifteen_minute_structure: SemanticQualificationFactV2 | None,
    five_minute_progression: SemanticQualificationFactV2 | None,
    rsi: Wo10RsiFact | None,
    railway_track: Wo10SmaFacts | None,
    structural_location: Wo10StructuralLocationFacts | None,
    volume_telemetry: Wo10VolumeFact | None,
    nifty_fifteen_minute_context: SemanticQualificationFactV2 | None,
    nifty_one_hour_context: SemanticQualificationFactV2 | None,
    nifty_relationship: NiftyRelativeContextEvidence | None,
    imported_visual_evidence: ImportedVisualEvidenceV2 | None,
) -> Wo10EquityPolicyEvidence:
    values = {
        "snapshot": snapshot,
        "source_semantic_evidence": source_semantic_evidence,
        "one_day_context": one_day_context,
        "one_hour_regime": one_hour_regime,
        "fifteen_minute_structure": fifteen_minute_structure,
        "five_minute_progression": five_minute_progression,
        "rsi": rsi,
        "railway_track": railway_track,
        "structural_location": structural_location,
        "volume_telemetry": volume_telemetry,
        "nifty_fifteen_minute_context": nifty_fifteen_minute_context,
        "nifty_one_hour_context": nifty_one_hour_context,
        "nifty_relationship": nifty_relationship,
        "imported_visual_evidence": imported_visual_evidence,
        "schema_identity": WO10_EQUITY_POLICY_EVIDENCE_IDENTITY,
        "schema_version": WO10_EQUITY_POLICY_EVIDENCE_VERSION,
    }
    identity_values = _equity_evidence_payload(values)
    return Wo10EquityPolicyEvidence(
        evidence_identity=_identity(
            "INTRADAY-WO10E-POLICY-EVIDENCE-", identity_values
        ),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-WO10E-POLICY-EVIDENCE-", identity_values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo10PolicyDecision:
    canonical_subject_identity: str
    inherited_direction: SemanticDirection
    state: Wo10State
    reasons: tuple[Wo10ReasonCode, ...]

    def __post_init__(self) -> None:
        if (
            not _text(self.canonical_subject_identity)
            or self.inherited_direction
            not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or type(self.state) is not Wo10State
            or not self.reasons
            or any(type(item) is not Wo10ReasonCode for item in self.reasons)
            or tuple(sorted(self.reasons, key=_reason_key)) != self.reasons
        ):
            raise Wo10ContractError("WO10_POLICY_DECISION_INVALID")


@runtime_checkable
class Wo10FamilyPolicy(Protocol):
    @property
    def binding(self) -> Wo10PolicyBinding:
        """Return the exact immutable family-policy publication binding."""

    def evaluate(
        self,
        *,
        request: Wo10ReconciliationRequest,
        evidence: Wo10EvidenceSnapshot,
    ) -> Wo10PolicyDecision:
        """Deterministically evaluate one bound candidate without side effects."""


class Wo10PolicyRegistry:
    """Exact-tuple registry with no default, cross-family, or latest fallback."""

    def __init__(self, policies: tuple[Wo10FamilyPolicy, ...]) -> None:
        entries: dict[
            tuple[str, str, str, str, IntradayMarketFamily],
            Wo10FamilyPolicy,
        ] = {}
        for policy in policies:
            if not isinstance(policy, Wo10FamilyPolicy):
                raise Wo10ContractError("WO10_POLICY_PROTOCOL_INVALID")
            binding = policy.binding
            if type(binding) is not Wo10PolicyBinding or binding.key in entries:
                raise Wo10ContractError("WO10_POLICY_REGISTRY_INVALID")
            entries[binding.key] = policy
        self._entries = entries

    def resolve(self, binding: Wo10PolicyBinding) -> Wo10FamilyPolicy:
        if type(binding) is not Wo10PolicyBinding:
            raise Wo10ContractError("WO10_POLICY_BINDING_INVALID")
        try:
            policy = self._entries[binding.key]
        except KeyError as error:
            raise Wo10ContractError("WO10_POLICY_UNKNOWN") from error
        if policy.binding != binding:
            raise Wo10ContractError("WO10_POLICY_BINDING_CONFLICT")
        return policy

    def evaluate(
        self,
        *,
        request: Wo10ReconciliationRequest,
        evidence: Wo10EvidenceSnapshot,
    ) -> Wo10PolicyDecision:
        if (
            type(request) is not Wo10ReconciliationRequest
            or type(evidence) is not Wo10EvidenceSnapshot
            or request.policy != evidence.policy
            or request.market_family is not evidence.market_family
        ):
            raise Wo10ContractError("WO10_POLICY_EVALUATION_BINDING_INVALID")
        policy = self.resolve(request.policy)
        decision = policy.evaluate(request=request, evidence=evidence)
        if (
            type(decision) is not Wo10PolicyDecision
            or decision.canonical_subject_identity
            != evidence.canonical_subject_identity
            or decision.inherited_direction is not evidence.inherited_direction
            or any(
                not reason_applies_to_family(item, evidence.market_family)
                for item in decision.reasons
            )
            or any(item.policy_identity != request.policy.policy_identity for item in decision.reasons)
        ):
            raise Wo10ContractError("WO10_POLICY_DECISION_BINDING_INVALID")
        return decision


class Wo10EquityPolicy:
    """Pure exact-artifact WO-10E policy with no product or Provider action."""

    def __init__(self, evidence: tuple[Wo10EquityPolicyEvidence, ...]) -> None:
        retained: dict[str, Wo10EquityPolicyEvidence] = {}
        for item in evidence:
            if (
                type(item) is not Wo10EquityPolicyEvidence
                or item.snapshot.snapshot_identity in retained
            ):
                raise Wo10ContractError("WO10_EQUITY_POLICY_INPUT_INVALID")
            retained[item.snapshot.snapshot_identity] = item
        self._evidence = retained

    @property
    def binding(self) -> Wo10PolicyBinding:
        return wo10_equity_policy_binding()

    def evaluate(
        self,
        *,
        request: Wo10ReconciliationRequest,
        evidence: Wo10EvidenceSnapshot,
    ) -> Wo10PolicyDecision:
        if (
            type(request) is not Wo10ReconciliationRequest
            or type(evidence) is not Wo10EvidenceSnapshot
            or request.market_family is not IntradayMarketFamily.NSE_EQUITY
            or evidence.market_family is not IntradayMarketFamily.NSE_EQUITY
            or request.policy != self.binding
            or evidence.policy != self.binding
        ):
            raise Wo10ContractError("WO10_EQUITY_POLICY_FAMILY_INVALID")
        try:
            loaded = self._evidence[evidence.snapshot_identity]
        except KeyError as error:
            raise Wo10ContractError("WO10_EQUITY_POLICY_EVIDENCE_NOT_LOADED") from error
        if loaded.snapshot != evidence:
            raise Wo10ContractError("WO10_EQUITY_POLICY_EVIDENCE_CONFLICT")
        state, code = _evaluate_equity(request, loaded)
        reason = Wo10ReasonCode(
            scope=Wo10ReasonScope.EQUITY,
            code=code,
            policy_identity=self.binding.policy_identity,
        )
        return Wo10PolicyDecision(
            canonical_subject_identity=evidence.canonical_subject_identity,
            inherited_direction=evidence.inherited_direction,
            state=state,
            reasons=(reason,),
        )


def _evaluate_equity(
    request: Wo10ReconciliationRequest,
    loaded: Wo10EquityPolicyEvidence,
) -> tuple[Wo10State, str]:
    snapshot = loaded.snapshot
    binding = next((
        item for item in request.probable_bindings
        if item.probable_result_identity == snapshot.probable_result_identity
    ), None)
    if (
        binding is None
        or binding.canonical_subject_identity != snapshot.canonical_subject_identity
        or binding.inherited_direction is not snapshot.inherited_direction
        or binding.analysis_boundary != snapshot.analysis_boundary
        or binding.persisted_phase is not snapshot.persisted_phase
        or request.probables_run_identity != snapshot.probables_run_identity
        or not _equity_evidence_complete(loaded)
    ):
        return Wo10State.CONTEXT_INCOMPLETE, "REQUIRED_EVIDENCE_INCOMPLETE"

    inherited = snapshot.inherited_direction
    hourly = loaded.one_hour_regime
    fifteen = loaded.fifteen_minute_structure
    five = loaded.five_minute_progression
    assert hourly is not None and fifteen is not None and five is not None

    if _opposes(fifteen.direction, inherited):
        return Wo10State.INVALIDATED, "GOVERNING_STRUCTURE_FAILED"

    answers = {
        item.question_id: item
        for item in loaded.imported_visual_evidence.answers  # type: ignore[union-attr]
    }
    q5 = answers["Q5"].answer
    q6 = answers["Q6"].answer
    q9 = answers["Q9"].answer
    native_immediate_deterioration = _opposes(five.direction, inherited)
    visual_deterioration = (
        q5 in {
            "STALLING_OR_FAILED_CONTINUATION",
            "OPPOSING_STRUCTURE_VISIBLE",
            "BOTH",
        }
        or q6 in {"STALLING", "OPPOSING"}
        or q9 == "REJECTION_AGAINST_DIRECTION"
    )
    if native_immediate_deterioration and visual_deterioration:
        return Wo10State.WEAKENING, "NATIVE_VISUAL_DETERIORATION"

    q2 = answers["Q2"].answer
    q4 = answers["Q4"].answer
    if (
        fifteen.direction is inherited
        and (
            _opposes(hourly.direction, inherited)
            or q2 == "OPPOSING"
            or q4 == "OPPOSING"
        )
    ):
        return Wo10State.HELD_BY_CONTRADICTION, "AUTHORITATIVE_EVIDENCE_CONFLICT"

    if (
        fifteen.direction is SemanticDirection.NON_DIRECTIONAL
        or hourly.direction is SemanticDirection.NON_DIRECTIONAL
    ):
        return Wo10State.WAIT_SETUP_DEVELOPMENT, "PRIMARY_SETUP_DEVELOPING"

    if five.direction is not inherited:
        return Wo10State.WAIT_IMMEDIATE_CONFIRMATION, "IMMEDIATE_PROGRESSION_PENDING"

    return Wo10State.PROMOTION_READY, "GOVERNED_EVIDENCE_COHERENT"


def _equity_evidence_complete(value: Wo10EquityPolicyEvidence) -> bool:
    snapshot = value.snapshot
    extension = snapshot.family_extension
    if type(extension) is not Wo10EquityEvidenceExtension:
        return False
    required = (
        value.source_semantic_evidence,
        value.one_day_context,
        value.one_hour_regime,
        value.fifteen_minute_structure,
        value.five_minute_progression,
        value.rsi,
        value.railway_track,
        value.structural_location,
        value.volume_telemetry,
        value.nifty_fifteen_minute_context,
        value.nifty_one_hour_context,
        value.nifty_relationship,
        value.imported_visual_evidence,
    )
    if any(item is None for item in required):
        return False
    semantic = value.source_semantic_evidence
    visual = value.imported_visual_evidence
    stock_facts = (
        (value.one_day_context, "1D_CONTEXT"),
        (value.one_hour_regime, "1H_REGIME"),
        (value.fifteen_minute_structure, "15M_STRUCTURE"),
        (value.five_minute_progression, "5M_PROGRESSION"),
    )
    if (
        semantic.evidence_identity != snapshot.semantic_evidence_identity
        or semantic.integrity_identity != snapshot.semantic_evidence_integrity
        or semantic.canonical_subject_identity != snapshot.canonical_subject_identity
        or semantic.analysis_boundary != snapshot.analysis_boundary
        or semantic.phase is not snapshot.persisted_phase
        or visual.visual_evidence_identity != snapshot.imported_visual_evidence_identity
        or visual.integrity_identity != snapshot.imported_visual_evidence_integrity
        or visual.resolved_canonical_subject_identity
        != snapshot.canonical_subject_identity
        or visual.proposed_direction != snapshot.inherited_direction.value
        or visual.analysis_boundary != snapshot.analysis_boundary
        or visual.global_observation_status
        not in {ObservationStatus.OBSERVED, ObservationStatus.PARTIAL}
        or any(
            fact.canonical_subject_identity != snapshot.canonical_subject_identity
            or fact.analysis_boundary != snapshot.analysis_boundary
            or fact.phase is not snapshot.persisted_phase
            or fact.family != family
            or fact.availability != "AVAILABLE"
            or fact.direction is SemanticDirection.UNAVAILABLE
            for fact, family in stock_facts
        )
    ):
        return False
    common = snapshot.common_facts
    if not all((
        _reference_matches(common.one_day_structure, value.one_day_context),
        _reference_matches(common.one_hour_structure, value.one_hour_regime),
        _reference_matches(common.fifteen_minute_structure, value.fifteen_minute_structure),
        _reference_matches(common.five_minute_progression, value.five_minute_progression),
        _reference_matches(common.rsi, value.rsi),
        _reference_matches(common.railway_track, value.railway_track),
        _reference_matches(common.structural_location, value.structural_location),
        _reference_matches(common.volume_telemetry, value.volume_telemetry),
        _reference_matches(
            extension.nifty_fifteen_minute_context,
            value.nifty_fifteen_minute_context,
        ),
        _reference_matches(extension.nifty_one_hour_context, value.nifty_one_hour_context),
        _reference_matches(extension.nifty_relationship, value.nifty_relationship),
    )):
        return False
    nifty_fifteen = value.nifty_fifteen_minute_context
    nifty_hour = value.nifty_one_hour_context
    relationship = value.nifty_relationship
    if (
        nifty_fifteen.canonical_subject_identity != "NSE-INDEX-NIFTY"
        or nifty_fifteen.family != "15M_STRUCTURE"
        or nifty_fifteen.analysis_boundary != snapshot.analysis_boundary
        or nifty_fifteen.availability != "AVAILABLE"
        or nifty_fifteen.direction is SemanticDirection.UNAVAILABLE
        or nifty_hour.canonical_subject_identity != "NSE-INDEX-NIFTY"
        or nifty_hour.family != "1H_REGIME"
        or nifty_hour.analysis_boundary != snapshot.analysis_boundary
        or nifty_hour.availability != "AVAILABLE"
        or nifty_hour.direction is SemanticDirection.UNAVAILABLE
        or relationship.fact.canonical_subject_identity
        != snapshot.canonical_subject_identity
        or relationship.fact.analysis_boundary != snapshot.analysis_boundary
        or relationship.fact.applicability is not NiftyApplicability.APPLICABLE
        or relationship.relationship is NiftyRelationship.UNAVAILABLE
    ):
        return False
    if (
        value.rsi.canonical_subject_identity != snapshot.canonical_subject_identity
        or value.rsi.observation_boundary != snapshot.analysis_boundary
        or value.rsi.timeframe is not IntradayTimeframe.FIFTEEN_MINUTES
        or value.railway_track.canonical_subject_identity
        != snapshot.canonical_subject_identity
        or value.railway_track.observation_boundary != snapshot.analysis_boundary
        or value.railway_track.timeframe is not IntradayTimeframe.ONE_HOUR
        or value.structural_location.canonical_subject_identity
        != snapshot.canonical_subject_identity
        or value.structural_location.observation_boundary != snapshot.analysis_boundary
        or value.volume_telemetry.canonical_subject_identity
        != snapshot.canonical_subject_identity
        or value.volume_telemetry.observation_boundary != snapshot.analysis_boundary
        or value.volume_telemetry.timeframe is not IntradayTimeframe.FIFTEEN_MINUTES
    ):
        return False
    return True


def _reference_matches(reference: Wo10EvidenceReference | None, value: object) -> bool:
    if reference is None or value is None:
        return False
    identity = getattr(value, "evidence_identity", None)
    if identity is None:
        identity = getattr(value, "fact_identity", None)
    return (
        reference.evidence_identity == identity
        and reference.evidence_integrity == getattr(value, "integrity_identity", None)
    )


def _opposes(value: SemanticDirection, inherited: SemanticDirection) -> bool:
    return value in {SemanticDirection.LONG, SemanticDirection.SHORT} and value is not inherited


def _equity_evidence_values(value: Wo10EquityPolicyEvidence) -> dict[str, object]:
    return _equity_evidence_payload({
        name: getattr(value, name)
        for name in value.__dataclass_fields__
        if name not in {"evidence_identity", "integrity_identity"}
    })


def _equity_evidence_payload(values: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for name, item in values.items():
        if item is None or isinstance(item, str):
            payload[name] = item
            continue
        if type(item) is Wo10EvidenceSnapshot:
            payload[name] = {
                "identity": item.snapshot_identity,
                "integrity": item.snapshot_integrity,
            }
            continue
        identity = (
            getattr(item, "evidence_identity", None)
            or getattr(item, "fact_identity", None)
            or getattr(item, "visual_evidence_identity", None)
        )
        payload[name] = {
            "identity": identity,
            "integrity": getattr(item, "integrity_identity", None),
        }
    return payload


__all__ = [
    "WO10_EQUITY_POLICY_AUTHORITY_VERSION",
    "WO10_EQUITY_POLICY_CHECKSUM",
    "WO10_EQUITY_POLICY_EVIDENCE_IDENTITY",
    "WO10_EQUITY_POLICY_EVIDENCE_VERSION",
    "WO10_EQUITY_POLICY_IDENTITY",
    "WO10_EQUITY_POLICY_PUBLICATION_IDENTITY",
    "WO10_EQUITY_POLICY_UNRESOLVED",
    "WO10_EQUITY_POLICY_VERSION",
    "Wo10EquityPolicy",
    "Wo10EquityPolicyEvidence",
    "Wo10FamilyPolicy",
    "Wo10PolicyDecision",
    "Wo10PolicyRegistry",
    "create_wo10_equity_policy_evidence",
    "wo10_equity_policy_binding",
]
