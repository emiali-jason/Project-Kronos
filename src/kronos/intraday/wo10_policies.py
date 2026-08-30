"""Fail-closed family policies for deterministic WO-10 reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
from typing import Protocol, runtime_checkable

from kronos.instrument.active_derivative import ActiveDerivativeBindingArtifact
from kronos.intraday.contracts import IntradayTimeframe
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.mcx_commissioning import (
    McxCommissioningPublication,
    McxCommissioningState,
    load_mcx_commissioning_publication,
)
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
from kronos.intraday.review_mcx_paired import (
    MCX_PAIRED_ARCHITECTURE_IDENTITY,
    MCX_PAIRED_ARCHITECTURE_VERSION,
    McxPairedChartBundle,
    relationship_for_subject,
)
from kronos.intraday.review_mcx_paired_answer import (
    McxPairedImportedVisualEvidence,
)
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
    Wo10IndexEvidenceExtension,
    Wo10McxEvidenceExtension,
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

WO10_INDEX_POLICY_IDENTITY = (
    "KRONOS-INTRADAY-WO10I-INDEX-RECONCILIATION-POLICY-V1"
)
WO10_INDEX_POLICY_VERSION = "1.0.0"
WO10_INDEX_POLICY_PUBLICATION_IDENTITY = (
    "KRONOS-INTRADAY-WO-10-E-I-M-FROZEN-ARCHITECTURE-V1"
)
WO10_INDEX_POLICY_AUTHORITY_VERSION = "1.0.0"
WO10_INDEX_POLICY_EVIDENCE_IDENTITY = (
    "KRONOS-INTRADAY-WO10I-INDEX-POLICY-EVIDENCE-V1"
)
WO10_INDEX_POLICY_EVIDENCE_VERSION = "1.0.0"
WO10_INDEX_SUBJECTS = frozenset({"NSE-INDEX-NIFTY", "NSE-INDEX-BANKNIFTY"})
WO10_INDEX_POLICY_UNRESOLVED = (
    ("CONFLUENCE_DISTANCE", "INFORMATIONAL_DEFERRED"),
    ("EXTENSION_CHASE_THRESHOLD", "INFORMATIONAL_DEFERRED"),
    ("FLAT_TANGLED_SMA_THRESHOLD", "INFORMATIONAL_DEFERRED"),
    ("MATERIAL_RAILWAY_SEPARATION_CRISSCROSS", "INFORMATIONAL_DEFERRED"),
    ("MIDDLE_OF_RANGE_THRESHOLD", "INFORMATIONAL_DEFERRED"),
    ("NARROW_WIDE_CPR_PREDICTIVE_CONSEQUENCE", "INFORMATIONAL_DEFERRED"),
    ("VOLUME_CONSEQUENCE_THRESHOLD", "INFORMATIONAL_DEFERRED"),
    ("WEEKLY_DAILY_LOCATION_CONSEQUENCE_THRESHOLD", "INFORMATIONAL_DEFERRED"),
)

_INDEX_POLICY_DOCUMENT = {
    "authority_identity": WO10_INDEX_POLICY_PUBLICATION_IDENTITY,
    "authority_version": WO10_INDEX_POLICY_AUTHORITY_VERSION,
    "market_family": IntradayMarketFamily.NSE_INDEX.value,
    "subjects": tuple(sorted(WO10_INDEX_SUBJECTS)),
    "policy_identity": WO10_INDEX_POLICY_IDENTITY,
    "policy_version": WO10_INDEX_POLICY_VERSION,
    "precedence": tuple(item.value for item in Wo10State),
    "timeframe_authority": {
        "1W": "HIGHER_ORDER_STRUCTURAL_LOCATION_MAP",
        "1D": "CURRENT_SESSION_STRUCTURAL_CONTEXT",
        "1H": "INTRADAY_REGIME",
        "15M": "PRIMARY_INDEX_DIRECTIONAL_SETUP_STRUCTURE",
        "5M": "IMMEDIATE_ANALYTICAL_PROGRESSION",
    },
    "underlying": "SOLE_WO10I_DIRECTION_AUTHORITY",
    "option_premium": "NO_AUTHORITY",
    "rsi": "FACTUAL_ONLY_NO_DIRECTION_OR_STATE_AUTHORITY",
    "railway": "EXACT_LOWER_LEVEL_FACTS_ONLY_NO_SCORE",
    "structural_location": "FACTUAL_ONLY_NO_PROXIMITY_CONSEQUENCE",
    "narrow_cpr": "PRESERVE_SOURCE_AUTHORITY_NO_NEW_PREDICTION",
    "volume": "RAW_INFORMATIONAL_NO_THRESHOLD",
    "visual": "OBSERVATION_RECONCILED_WITH_NATIVE_NO_PROMOTION_AUTHORITY",
    "unresolved": WO10_INDEX_POLICY_UNRESOLVED,
}
WO10_INDEX_POLICY_CHECKSUM = sha256(json.dumps(
    _INDEX_POLICY_DOCUMENT,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")).hexdigest()

WO10_MCX_POLICY_IDENTITY = "KRONOS-INTRADAY-WO10M-MCX-RECONCILIATION-POLICY-V1"
WO10_MCX_POLICY_VERSION = "1.0.0"
WO10_MCX_POLICY_PUBLICATION_IDENTITY = (
    "KRONOS-INTRADAY-WO-10-E-I-M-FROZEN-ARCHITECTURE-V1"
)
WO10_MCX_POLICY_AUTHORITY_VERSION = "1.0.0"
WO10_MCX_USDINR_AMENDMENT_IDENTITY = (
    "KRONOS-INTRADAY-WO-10M-USDINR-BOUNDED-AMENDMENT-V1"
)
WO10_MCX_USDINR_AMENDMENT_VERSION = "1.0.0"
WO10_MCX_POLICY_EVIDENCE_IDENTITY = (
    "KRONOS-INTRADAY-WO10M-MCX-POLICY-EVIDENCE-V1"
)
WO10_MCX_POLICY_EVIDENCE_VERSION = "1.0.0"
WO10_MCX_SUBJECTS = frozenset({
    "MCX-SUBJECT-GOLDM",
    "MCX-SUBJECT-SILVERM",
    "MCX-SUBJECT-COPPER",
    "MCX-SUBJECT-NATGAS",
    "MCX-SUBJECT-CRUDE",
})
WO10_MCX_POLICY_UNRESOLVED = (
    ("CONFLUENCE_DISTANCE", "INFORMATIONAL_DEFERRED"),
    ("EXTENSION_CHASE", "INFORMATIONAL_DEFERRED"),
    ("FLAT_TANGLED", "INFORMATIONAL_DEFERRED"),
    ("INTERNATIONAL_OVERLAP", "INFORMATIONAL_DEFERRED"),
    ("MATERIAL_RAILWAY_SEPARATION_CRISSCROSS", "INFORMATIONAL_DEFERRED"),
    ("REFERENCE_DIVERGENCE_DURATION", "INFORMATIONAL_DEFERRED"),
    ("REFERENCE_DIVERGENCE_MATERIALITY", "INFORMATIONAL_DEFERRED"),
    ("SAME_TIME_VOLUME_MATERIALITY", "INFORMATIONAL_DEFERRED"),
    ("VOLUME_CONSEQUENCE", "INFORMATIONAL_DEFERRED"),
    ("FUTURE_METALS_ENERGY_POLICY_SPLIT", "INFORMATIONAL_DEFERRED"),
)

_MCX_POLICY_DOCUMENT = {
    "authority_identity": WO10_MCX_POLICY_PUBLICATION_IDENTITY,
    "authority_version": WO10_MCX_POLICY_AUTHORITY_VERSION,
    "usdinr_amendment_identity": WO10_MCX_USDINR_AMENDMENT_IDENTITY,
    "usdinr_amendment_version": WO10_MCX_USDINR_AMENDMENT_VERSION,
    "paired_architecture_identity": MCX_PAIRED_ARCHITECTURE_IDENTITY,
    "paired_architecture_version": MCX_PAIRED_ARCHITECTURE_VERSION,
    "market_family": IntradayMarketFamily.MCX.value,
    "subjects": tuple(sorted(WO10_MCX_SUBJECTS)),
    "policy_identity": WO10_MCX_POLICY_IDENTITY,
    "policy_version": WO10_MCX_POLICY_VERSION,
    "precedence": tuple(item.value for item in Wo10State),
    "timeframe_authority": {
        "machine_1D": "BROADER_CONTEXT",
        "machine_1H": "INTRADAY_REGIME",
        "machine_15M": "PRIMARY_DIRECTIONAL_SETUP_STRUCTURE",
        "machine_5M": "IMMEDIATE_ANALYTICAL_PROGRESSION",
        "visual_4H": "HIGHER_ORDER_VISUAL_CONTEXT_NOT_MACHINE_1H",
    },
    "direction": "INHERITED_NATIVE_MCX_ONLY",
    "reference": "CONTEXT_ONLY_NO_INDEPENDENT_STATE_AUTHORITY",
    "nifty": "NOT_APPLICABLE",
    "usdinr": "OPTIONAL_INFORMATIONAL_NO_STATE_AUTHORITY",
    "rsi": "FACTUAL_ONLY_NO_DIRECTION_OR_STATE_AUTHORITY",
    "railway": "FACTUAL_ONLY_NO_SCORE_OR_THRESHOLD",
    "volume": "RAW_INFORMATIONAL_15M_PRIMARY_NO_THRESHOLD",
    "roll": "EXACT_CONTRACT_AND_SESSION_NO_BACK_ADJUSTMENT",
    "natgas": "HELD_FAIL_CLOSED_BEFORE_ANALYTICAL_CONSEQUENCE",
    "score_weight_rank": "NONE",
    "unresolved": WO10_MCX_POLICY_UNRESOLVED,
}
WO10_MCX_POLICY_CHECKSUM = sha256(json.dumps(
    _MCX_POLICY_DOCUMENT,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")).hexdigest()


class Wo10McxReferenceContext(StrEnum):
    """Bounded factual synthesis with no independent state authority."""

    SUPPORTIVE = "SUPPORTIVE"
    DIVERGENT = "DIVERGENT"
    MIXED = "MIXED"
    UNCLEAR = "UNCLEAR"
    UNAVAILABLE = "UNAVAILABLE"


def derive_wo10_mcx_reference_context(
    evidence: McxPairedImportedVisualEvidence,
    inherited_direction: SemanticDirection,
) -> Wo10McxReferenceContext:
    """Derive contextual alignment from independent R01-R06 observations."""

    if (
        type(evidence) is not McxPairedImportedVisualEvidence
        or inherited_direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
    ):
        raise Wo10ContractError("WO10_MCX_REFERENCE_CONTEXT_INVALID")
    answers = {item.question_id: item.answer for item in evidence.reference_answers}
    if tuple(sorted(answers)) != tuple(f"R{number:02d}" for number in range(1, 7)):
        raise Wo10ContractError("WO10_MCX_REFERENCE_CONTEXT_INVALID")
    direction = answers["R03"]
    progression = answers["R04"]
    expected_direction = (
        "BULLISH" if inherited_direction is SemanticDirection.LONG else "BEARISH"
    )
    opposing_direction = (
        "BEARISH" if inherited_direction is SemanticDirection.LONG else "BULLISH"
    )
    expected_progression = (
        "ADVANCING" if inherited_direction is SemanticDirection.LONG else "DECLINING"
    )
    opposing_progression = (
        "DECLINING" if inherited_direction is SemanticDirection.LONG else "ADVANCING"
    )
    if direction == "NOT_VISIBLE" and progression == "NOT_VISIBLE":
        return Wo10McxReferenceContext.UNAVAILABLE
    if direction == expected_direction and progression == expected_progression:
        return Wo10McxReferenceContext.SUPPORTIVE
    if direction == opposing_direction and progression == opposing_progression:
        return Wo10McxReferenceContext.DIVERGENT
    if direction in {"UNCLEAR", "NOT_VISIBLE"} or progression in {"UNCLEAR", "NOT_VISIBLE"}:
        return Wo10McxReferenceContext.UNCLEAR
    return Wo10McxReferenceContext.MIXED


def wo10_equity_policy_binding() -> Wo10PolicyBinding:
    """Return the exact immutable WO-10E publication binding."""

    return create_wo10_policy_binding(
        policy_identity=WO10_EQUITY_POLICY_IDENTITY,
        policy_version=WO10_EQUITY_POLICY_VERSION,
        publication_identity=WO10_EQUITY_POLICY_PUBLICATION_IDENTITY,
        policy_checksum=WO10_EQUITY_POLICY_CHECKSUM,
        supported_market_family=IntradayMarketFamily.NSE_EQUITY,
    )


def wo10_index_policy_binding() -> Wo10PolicyBinding:
    """Return the exact immutable WO-10I publication binding."""

    return create_wo10_policy_binding(
        policy_identity=WO10_INDEX_POLICY_IDENTITY,
        policy_version=WO10_INDEX_POLICY_VERSION,
        publication_identity=WO10_INDEX_POLICY_PUBLICATION_IDENTITY,
        policy_checksum=WO10_INDEX_POLICY_CHECKSUM,
        supported_market_family=IntradayMarketFamily.NSE_INDEX,
    )


def wo10_mcx_policy_binding() -> Wo10PolicyBinding:
    """Return the exact immutable WO-10M publication binding."""

    return create_wo10_policy_binding(
        policy_identity=WO10_MCX_POLICY_IDENTITY,
        policy_version=WO10_MCX_POLICY_VERSION,
        publication_identity=WO10_MCX_POLICY_PUBLICATION_IDENTITY,
        policy_checksum=WO10_MCX_POLICY_CHECKSUM,
        supported_market_family=IntradayMarketFamily.MCX,
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
class Wo10IndexPolicyEvidence:
    """Exact loaded artifacts used by the pure Index policy adapter."""

    evidence_identity: str
    integrity_identity: str
    snapshot: Wo10EvidenceSnapshot
    source_semantic_evidence: SemanticQualificationEvidenceV2 | None
    weekly_structural_map: SemanticQualificationFactV2 | None
    daily_structural_map: SemanticQualificationFactV2 | None
    one_day_context: SemanticQualificationFactV2 | None
    one_hour_regime: SemanticQualificationFactV2 | None
    fifteen_minute_structure: SemanticQualificationFactV2 | None
    five_minute_progression: SemanticQualificationFactV2 | None
    rsi: Wo10RsiFact | None
    railway_track: Wo10SmaFacts | None
    structural_location: Wo10StructuralLocationFacts | None
    volume_telemetry: Wo10VolumeFact | None
    imported_visual_evidence: ImportedVisualEvidenceV2 | None
    schema_identity: str = WO10_INDEX_POLICY_EVIDENCE_IDENTITY
    schema_version: str = WO10_INDEX_POLICY_EVIDENCE_VERSION

    def __post_init__(self) -> None:
        values = _index_evidence_values(self)
        typed = (
            (self.source_semantic_evidence, SemanticQualificationEvidenceV2),
            (self.weekly_structural_map, SemanticQualificationFactV2),
            (self.daily_structural_map, SemanticQualificationFactV2),
            (self.one_day_context, SemanticQualificationFactV2),
            (self.one_hour_regime, SemanticQualificationFactV2),
            (self.fifteen_minute_structure, SemanticQualificationFactV2),
            (self.five_minute_progression, SemanticQualificationFactV2),
            (self.rsi, Wo10RsiFact),
            (self.railway_track, Wo10SmaFacts),
            (self.structural_location, Wo10StructuralLocationFacts),
            (self.volume_telemetry, Wo10VolumeFact),
            (self.imported_visual_evidence, ImportedVisualEvidenceV2),
        )
        if (
            type(self.snapshot) is not Wo10EvidenceSnapshot
            or self.snapshot.market_family is not IntradayMarketFamily.NSE_INDEX
            or any(
                item is not None and type(item) is not expected
                for item, expected in typed
            )
            or self.schema_identity != WO10_INDEX_POLICY_EVIDENCE_IDENTITY
            or self.schema_version != WO10_INDEX_POLICY_EVIDENCE_VERSION
            or self.evidence_identity
            != _identity("INTRADAY-WO10I-POLICY-EVIDENCE-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-WO10I-POLICY-EVIDENCE-", values)
        ):
            raise Wo10ContractError("WO10_INDEX_POLICY_EVIDENCE_INVALID")


def create_wo10_index_policy_evidence(
    *,
    snapshot: Wo10EvidenceSnapshot,
    source_semantic_evidence: SemanticQualificationEvidenceV2 | None,
    weekly_structural_map: SemanticQualificationFactV2 | None,
    daily_structural_map: SemanticQualificationFactV2 | None,
    one_day_context: SemanticQualificationFactV2 | None,
    one_hour_regime: SemanticQualificationFactV2 | None,
    fifteen_minute_structure: SemanticQualificationFactV2 | None,
    five_minute_progression: SemanticQualificationFactV2 | None,
    rsi: Wo10RsiFact | None,
    railway_track: Wo10SmaFacts | None,
    structural_location: Wo10StructuralLocationFacts | None,
    volume_telemetry: Wo10VolumeFact | None,
    imported_visual_evidence: ImportedVisualEvidenceV2 | None,
) -> Wo10IndexPolicyEvidence:
    values = {
        "snapshot": snapshot,
        "source_semantic_evidence": source_semantic_evidence,
        "weekly_structural_map": weekly_structural_map,
        "daily_structural_map": daily_structural_map,
        "one_day_context": one_day_context,
        "one_hour_regime": one_hour_regime,
        "fifteen_minute_structure": fifteen_minute_structure,
        "five_minute_progression": five_minute_progression,
        "rsi": rsi,
        "railway_track": railway_track,
        "structural_location": structural_location,
        "volume_telemetry": volume_telemetry,
        "imported_visual_evidence": imported_visual_evidence,
        "schema_identity": WO10_INDEX_POLICY_EVIDENCE_IDENTITY,
        "schema_version": WO10_INDEX_POLICY_EVIDENCE_VERSION,
    }
    identity_values = _equity_evidence_payload(values)
    return Wo10IndexPolicyEvidence(
        evidence_identity=_identity(
            "INTRADAY-WO10I-POLICY-EVIDENCE-", identity_values
        ),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-WO10I-POLICY-EVIDENCE-", identity_values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo10McxPolicyEvidence:
    """Exact loaded artifacts used by the pure MCX policy adapter."""

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
    active_derivative_binding: ActiveDerivativeBindingArtifact | None
    commissioning_publication: McxCommissioningPublication | None
    paired_chart_bundle: McxPairedChartBundle | None
    paired_visual_evidence: McxPairedImportedVisualEvidence | None
    schema_identity: str = WO10_MCX_POLICY_EVIDENCE_IDENTITY
    schema_version: str = WO10_MCX_POLICY_EVIDENCE_VERSION

    def __post_init__(self) -> None:
        values = _mcx_evidence_values(self)
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
            (self.active_derivative_binding, ActiveDerivativeBindingArtifact),
            (self.commissioning_publication, McxCommissioningPublication),
            (self.paired_chart_bundle, McxPairedChartBundle),
            (self.paired_visual_evidence, McxPairedImportedVisualEvidence),
        )
        if (
            type(self.snapshot) is not Wo10EvidenceSnapshot
            or self.snapshot.market_family is not IntradayMarketFamily.MCX
            or any(
                item is not None and type(item) is not expected
                for item, expected in typed
            )
            or self.schema_identity != WO10_MCX_POLICY_EVIDENCE_IDENTITY
            or self.schema_version != WO10_MCX_POLICY_EVIDENCE_VERSION
            or self.evidence_identity
            != _identity("INTRADAY-WO10M-POLICY-EVIDENCE-", values)
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-WO10M-POLICY-EVIDENCE-", values)
        ):
            raise Wo10ContractError("WO10_MCX_POLICY_EVIDENCE_INVALID")


def create_wo10_mcx_policy_evidence(
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
    active_derivative_binding: ActiveDerivativeBindingArtifact | None,
    commissioning_publication: McxCommissioningPublication | None,
    paired_chart_bundle: McxPairedChartBundle | None,
    paired_visual_evidence: McxPairedImportedVisualEvidence | None,
) -> Wo10McxPolicyEvidence:
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
        "active_derivative_binding": active_derivative_binding,
        "commissioning_publication": commissioning_publication,
        "paired_chart_bundle": paired_chart_bundle,
        "paired_visual_evidence": paired_visual_evidence,
        "schema_identity": WO10_MCX_POLICY_EVIDENCE_IDENTITY,
        "schema_version": WO10_MCX_POLICY_EVIDENCE_VERSION,
    }
    identity_values = _equity_evidence_payload(values)
    return Wo10McxPolicyEvidence(
        evidence_identity=_identity(
            "INTRADAY-WO10M-POLICY-EVIDENCE-", identity_values
        ),
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-WO10M-POLICY-EVIDENCE-", identity_values
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


class Wo10IndexPolicy:
    """Pure exact-artifact WO-10I policy with no product or Provider action."""

    def __init__(self, evidence: tuple[Wo10IndexPolicyEvidence, ...]) -> None:
        retained: dict[str, Wo10IndexPolicyEvidence] = {}
        for item in evidence:
            if (
                type(item) is not Wo10IndexPolicyEvidence
                or item.snapshot.snapshot_identity in retained
            ):
                raise Wo10ContractError("WO10_INDEX_POLICY_INPUT_INVALID")
            retained[item.snapshot.snapshot_identity] = item
        self._evidence = retained

    @property
    def binding(self) -> Wo10PolicyBinding:
        return wo10_index_policy_binding()

    def evaluate(
        self,
        *,
        request: Wo10ReconciliationRequest,
        evidence: Wo10EvidenceSnapshot,
    ) -> Wo10PolicyDecision:
        if (
            type(request) is not Wo10ReconciliationRequest
            or type(evidence) is not Wo10EvidenceSnapshot
            or request.market_family is not IntradayMarketFamily.NSE_INDEX
            or evidence.market_family is not IntradayMarketFamily.NSE_INDEX
            or evidence.canonical_subject_identity not in WO10_INDEX_SUBJECTS
            or request.policy != self.binding
            or evidence.policy != self.binding
        ):
            raise Wo10ContractError("WO10_INDEX_POLICY_FAMILY_INVALID")
        try:
            loaded = self._evidence[evidence.snapshot_identity]
        except KeyError as error:
            raise Wo10ContractError("WO10_INDEX_POLICY_EVIDENCE_NOT_LOADED") from error
        if loaded.snapshot != evidence:
            raise Wo10ContractError("WO10_INDEX_POLICY_EVIDENCE_CONFLICT")
        state, code = _evaluate_index(request, loaded)
        reason = Wo10ReasonCode(
            scope=Wo10ReasonScope.INDEX,
            code=code,
            policy_identity=self.binding.policy_identity,
        )
        return Wo10PolicyDecision(
            canonical_subject_identity=evidence.canonical_subject_identity,
            inherited_direction=evidence.inherited_direction,
            state=state,
            reasons=(reason,),
        )


class Wo10McxPolicy:
    """Pure WO-10M policy over exact retained Native and paired evidence."""

    def __init__(self, evidence: tuple[Wo10McxPolicyEvidence, ...]) -> None:
        retained: dict[str, Wo10McxPolicyEvidence] = {}
        for item in evidence:
            if (
                type(item) is not Wo10McxPolicyEvidence
                or item.snapshot.snapshot_identity in retained
            ):
                raise Wo10ContractError("WO10_MCX_POLICY_INPUT_INVALID")
            retained[item.snapshot.snapshot_identity] = item
        self._evidence = retained

    @property
    def binding(self) -> Wo10PolicyBinding:
        return wo10_mcx_policy_binding()

    def evaluate(
        self,
        *,
        request: Wo10ReconciliationRequest,
        evidence: Wo10EvidenceSnapshot,
    ) -> Wo10PolicyDecision:
        if (
            type(request) is not Wo10ReconciliationRequest
            or type(evidence) is not Wo10EvidenceSnapshot
            or request.market_family is not IntradayMarketFamily.MCX
            or evidence.market_family is not IntradayMarketFamily.MCX
            or evidence.canonical_subject_identity not in WO10_MCX_SUBJECTS
            or request.policy != self.binding
            or evidence.policy != self.binding
        ):
            raise Wo10ContractError("WO10_MCX_POLICY_FAMILY_INVALID")

        # Commissioning is checked before a policy state can be produced.
        # NATGAS therefore cannot receive even CONTEXT_INCOMPLETE as an
        # analytical consequence while its governed publication is HELD.
        _require_mcx_commissioned(evidence.canonical_subject_identity)
        try:
            loaded = self._evidence[evidence.snapshot_identity]
        except KeyError as error:
            raise Wo10ContractError("WO10_MCX_POLICY_EVIDENCE_NOT_LOADED") from error
        if loaded.snapshot != evidence:
            raise Wo10ContractError("WO10_MCX_POLICY_EVIDENCE_CONFLICT")
        state, code = _evaluate_mcx(request, loaded)
        reason = Wo10ReasonCode(
            scope=Wo10ReasonScope.MCX,
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


def _evaluate_index(
    request: Wo10ReconciliationRequest,
    loaded: Wo10IndexPolicyEvidence,
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
        or not _index_evidence_complete(loaded)
    ):
        return Wo10State.CONTEXT_INCOMPLETE, "REQUIRED_EVIDENCE_INCOMPLETE"

    inherited = snapshot.inherited_direction
    hourly = loaded.one_hour_regime
    fifteen = loaded.fifteen_minute_structure
    five = loaded.five_minute_progression
    visual = loaded.imported_visual_evidence
    assert hourly is not None and fifteen is not None and five is not None
    assert visual is not None

    # Governing completed 15M structure has precedence over every map,
    # indicator, visual observation, and lower-timeframe progression.
    if _opposes(fifteen.direction, inherited):
        return Wo10State.INVALIDATED, "GOVERNING_STRUCTURE_FAILED"

    answers = {item.question_id: item for item in visual.answers}
    visual_deterioration = (
        answers["Q5"].answer in {
            "STALLING_OR_FAILED_CONTINUATION",
            "OPPOSING_STRUCTURE_VISIBLE",
            "BOTH",
        }
        or answers["Q6"].answer in {"STALLING", "OPPOSING"}
        or answers["Q9"].answer == "REJECTION_AGAINST_DIRECTION"
    )
    if _opposes(five.direction, inherited) and visual_deterioration:
        return Wo10State.WEAKENING, "NATIVE_VISUAL_DETERIORATION"

    if (
        fifteen.direction is inherited
        and (
            _opposes(hourly.direction, inherited)
            or answers["Q2"].answer == "OPPOSING"
            or answers["Q4"].answer == "OPPOSING"
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


def _evaluate_mcx(
    request: Wo10ReconciliationRequest,
    loaded: Wo10McxPolicyEvidence,
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
        or not _mcx_evidence_complete(loaded)
    ):
        return Wo10State.CONTEXT_INCOMPLETE, "REQUIRED_EVIDENCE_INCOMPLETE"

    inherited = snapshot.inherited_direction
    hourly = loaded.one_hour_regime
    fifteen = loaded.fifteen_minute_structure
    five = loaded.five_minute_progression
    visual = loaded.paired_visual_evidence
    assert hourly is not None and fifteen is not None and five is not None
    assert visual is not None

    # Completed Native MCX 15M structure is the governing authority. Neither
    # international-reference evidence nor indicators can rescue its failure.
    if _opposes(fifteen.direction, inherited):
        return Wo10State.INVALIDATED, "GOVERNING_STRUCTURE_FAILED"

    native_answers = {item.question_id: item.answer for item in visual.native_answers}
    # Derived by KRONOS, never supplied by Chart Analyst. It is deliberately
    # retained as context and never branches the seven-state decision.
    reference_context = derive_wo10_mcx_reference_context(visual, inherited)
    assert type(reference_context) is Wo10McxReferenceContext
    expected_progression = (
        "ADVANCING" if inherited is SemanticDirection.LONG else "DECLINING"
    )
    native_visual_deterioration = (
        native_answers["M04"] == "PRESENT"
        or native_answers["M05"]
        not in {expected_progression, "UNCLEAR", "NOT_VISIBLE"}
    )
    if _opposes(five.direction, inherited) and native_visual_deterioration:
        return Wo10State.WEAKENING, "NATIVE_VISUAL_DETERIORATION"

    expected_visual = (
        "BULLISH" if inherited is SemanticDirection.LONG else "BEARISH"
    )
    opposing_visual = (
        "BEARISH" if inherited is SemanticDirection.LONG else "BULLISH"
    )
    if (
        fifteen.direction is inherited
        and (
            _opposes(hourly.direction, inherited)
            or native_answers["M03"] == opposing_visual
        )
    ):
        return Wo10State.HELD_BY_CONTRADICTION, "AUTHORITATIVE_EVIDENCE_CONFLICT"

    if (
        fifteen.direction is SemanticDirection.NON_DIRECTIONAL
        or hourly.direction is SemanticDirection.NON_DIRECTIONAL
        or native_answers["M03"]
        in {"NEUTRAL", "MIXED", "UNCLEAR", "NOT_VISIBLE"}
    ):
        return Wo10State.WAIT_SETUP_DEVELOPMENT, "PRIMARY_SETUP_DEVELOPING"

    if (
        five.direction is not inherited
        or native_answers["M05"] != expected_progression
    ):
        return Wo10State.WAIT_IMMEDIATE_CONFIRMATION, "IMMEDIATE_PROGRESSION_PENDING"

    # Reference, USDINR, RSI, Railway, volume, and 4H visual observations have
    # no independent promotion authority. Promotion follows only after all
    # authoritative Native gates above are coherent.
    assert native_answers["M03"] == expected_visual
    return Wo10State.PROMOTION_READY, "GOVERNED_EVIDENCE_COHERENT"


def _require_mcx_commissioned(canonical_subject_identity: str) -> None:
    if (
        canonical_subject_identity not in WO10_MCX_SUBJECTS
        or load_mcx_commissioning_publication()
        .subject(canonical_subject_identity).state
        is not McxCommissioningState.COMMISSIONED
    ):
        raise Wo10ContractError("WO10_MCX_COMMISSIONING_HELD")


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


def _index_evidence_complete(value: Wo10IndexPolicyEvidence) -> bool:
    snapshot = value.snapshot
    extension = snapshot.family_extension
    if (
        type(extension) is not Wo10IndexEvidenceExtension
        or snapshot.canonical_subject_identity not in WO10_INDEX_SUBJECTS
    ):
        return False
    required = (
        value.source_semantic_evidence,
        value.daily_structural_map,
        value.one_day_context,
        value.one_hour_regime,
        value.fifteen_minute_structure,
        value.five_minute_progression,
        value.rsi,
        value.railway_track,
        value.structural_location,
        value.volume_telemetry,
        value.imported_visual_evidence,
    )
    if any(item is None for item in required):
        return False
    semantic = value.source_semantic_evidence
    visual = value.imported_visual_evidence
    assert semantic is not None and visual is not None
    index_facts = (
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
            fact is None
            or fact.canonical_subject_identity != snapshot.canonical_subject_identity
            or fact.analysis_boundary != snapshot.analysis_boundary
            or fact.phase is not snapshot.persisted_phase
            or fact.family != family
            or fact.availability != "AVAILABLE"
            or fact.direction is SemanticDirection.UNAVAILABLE
            for fact, family in index_facts
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
        _reference_matches(extension.daily_structural_map, value.daily_structural_map),
    )):
        return False

    daily_map = value.daily_structural_map
    weekly_map = value.weekly_structural_map
    assert daily_map is not None
    if (
        daily_map.canonical_subject_identity != snapshot.canonical_subject_identity
        or daily_map.analysis_boundary != snapshot.analysis_boundary
        or daily_map.phase is not snapshot.persisted_phase
        or daily_map.family != "DAILY_STRUCTURAL_MAP"
        or daily_map.availability != "AVAILABLE"
        or daily_map.direction is not SemanticDirection.NON_DIRECTIONAL
        or (extension.weekly_structural_map is None) != (weekly_map is None)
        or (
            weekly_map is not None
            and (
                not _reference_matches(extension.weekly_structural_map, weekly_map)
                or weekly_map.canonical_subject_identity
                != snapshot.canonical_subject_identity
                or weekly_map.analysis_boundary != snapshot.analysis_boundary
                or weekly_map.phase is not snapshot.persisted_phase
                or weekly_map.family != "WEEKLY_STRUCTURAL_MAP"
                or weekly_map.availability != "AVAILABLE"
                or weekly_map.direction is not SemanticDirection.NON_DIRECTIONAL
            )
        )
        or extension.underlying_authority is None
        or extension.underlying_authority.evidence_identity
        != snapshot.probable_result_identity
        or extension.underlying_authority.evidence_integrity
        != snapshot.probable_result_integrity
    ):
        return False

    if (
        value.rsi.canonical_subject_identity != snapshot.canonical_subject_identity
        or value.rsi.market_family is not IntradayMarketFamily.NSE_INDEX
        or value.rsi.observation_boundary != snapshot.analysis_boundary
        or value.rsi.timeframe is not IntradayTimeframe.FIFTEEN_MINUTES
        or value.railway_track.canonical_subject_identity
        != snapshot.canonical_subject_identity
        or value.railway_track.market_family is not IntradayMarketFamily.NSE_INDEX
        or value.railway_track.observation_boundary != snapshot.analysis_boundary
        or value.railway_track.timeframe is not IntradayTimeframe.ONE_HOUR
        or value.structural_location.canonical_subject_identity
        != snapshot.canonical_subject_identity
        or value.structural_location.market_family is not IntradayMarketFamily.NSE_INDEX
        or value.structural_location.observation_boundary != snapshot.analysis_boundary
        or value.volume_telemetry.canonical_subject_identity
        != snapshot.canonical_subject_identity
        or value.volume_telemetry.market_family is not IntradayMarketFamily.NSE_INDEX
        or value.volume_telemetry.observation_boundary != snapshot.analysis_boundary
        or value.volume_telemetry.timeframe is not IntradayTimeframe.FIFTEEN_MINUTES
    ):
        return False
    return True


def _mcx_evidence_complete(value: Wo10McxPolicyEvidence) -> bool:
    snapshot = value.snapshot
    extension = snapshot.family_extension
    if (
        type(extension) is not Wo10McxEvidenceExtension
        or snapshot.canonical_subject_identity not in WO10_MCX_SUBJECTS
    ):
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
        value.active_derivative_binding,
        value.commissioning_publication,
        value.paired_chart_bundle,
        value.paired_visual_evidence,
    )
    if any(item is None for item in required):
        return False
    semantic = value.source_semantic_evidence
    active = value.active_derivative_binding
    publication = value.commissioning_publication
    bundle = value.paired_chart_bundle
    visual = value.paired_visual_evidence
    location = value.structural_location
    assert semantic is not None and active is not None and publication is not None
    assert bundle is not None and visual is not None and location is not None

    facts = (
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
        or any(
            fact is None
            or fact.canonical_subject_identity != snapshot.canonical_subject_identity
            or fact.analysis_boundary != snapshot.analysis_boundary
            or fact.phase is not snapshot.persisted_phase
            or fact.family != family
            or fact.availability != "AVAILABLE"
            or fact.direction is SemanticDirection.UNAVAILABLE
            for fact, family in facts
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
    )):
        return False

    if (
        value.rsi.canonical_subject_identity != snapshot.canonical_subject_identity
        or value.rsi.market_family is not IntradayMarketFamily.MCX
        or value.rsi.observation_boundary != snapshot.analysis_boundary
        or value.rsi.timeframe is not IntradayTimeframe.FIFTEEN_MINUTES
        or value.railway_track.canonical_subject_identity
        != snapshot.canonical_subject_identity
        or value.railway_track.market_family is not IntradayMarketFamily.MCX
        or value.railway_track.observation_boundary != snapshot.analysis_boundary
        or value.railway_track.timeframe is not IntradayTimeframe.ONE_HOUR
        or location.canonical_subject_identity != snapshot.canonical_subject_identity
        or location.market_family is not IntradayMarketFamily.MCX
        or location.observation_boundary != snapshot.analysis_boundary
        or value.volume_telemetry.canonical_subject_identity
        != snapshot.canonical_subject_identity
        or value.volume_telemetry.market_family is not IntradayMarketFamily.MCX
        or value.volume_telemetry.observation_boundary != snapshot.analysis_boundary
        or value.volume_telemetry.timeframe is not IntradayTimeframe.FIFTEEN_MINUTES
    ):
        return False

    expected_relationship = relationship_for_subject(snapshot.canonical_subject_identity)
    native = bundle.native_identity_binding
    if (
        bundle.architecture_identity != MCX_PAIRED_ARCHITECTURE_IDENTITY
        or bundle.architecture_version != MCX_PAIRED_ARCHITECTURE_VERSION
        or bundle.canonical_mcx_subject_identity != snapshot.canonical_subject_identity
        or bundle.probables_run_identity != snapshot.probables_run_identity
        or bundle.probable_result_identity != snapshot.probable_result_identity
        or bundle.review_cycle_identity != snapshot.review_cycle_identity
        or bundle.direction != snapshot.inherited_direction.value
        or bundle.phase != snapshot.persisted_phase.value
        or bundle.analysis_boundary != snapshot.analysis_boundary
        or bundle.reference_relationship != expected_relationship
        or native.canonical_subject_identity != snapshot.canonical_subject_identity
        or native.observation_boundary != snapshot.analysis_boundary
        or native.commissioning_state is not McxCommissioningState.COMMISSIONED
        or active.canonical_subject_id != snapshot.canonical_subject_identity
        or active.observation_boundary != snapshot.analysis_boundary
        or active.binding_identity != native.active_binding_identity
        or active.integrity_identity != native.active_binding_integrity_identity
        or active.active_binding.derivative_contract_id
        != native.actual_derivative_contract_identity
        or active.provider_symbol != native.provider_symbol
        or active.contract_expiry.isoformat() != native.contract_expiry
        or location.actual_contract_identity
        != native.actual_derivative_contract_identity
        or location.roll_lineage_identity != native.roll_history_identity
    ):
        return False

    try:
        commissioned = publication.subject(snapshot.canonical_subject_identity)
    except Exception:
        return False
    if (
        publication != load_mcx_commissioning_publication()
        or commissioned.state is not McxCommissioningState.COMMISSIONED
        or publication.publication_identity
        != native.commissioning_publication_identity
        or publication.integrity_identity
        != native.commissioning_publication_integrity_identity
    ):
        return False

    if (
        visual.paired_bundle_identity != bundle.bundle_identity
        or visual.review_cycle_identity != bundle.review_cycle_identity
        or visual.canonical_mcx_subject_identity != snapshot.canonical_subject_identity
        or visual.actual_derivative_contract_identity
        != native.actual_derivative_contract_identity
        or visual.active_binding_identity != native.active_binding_identity
        or visual.direction != snapshot.inherited_direction.value
        or visual.phase != snapshot.persisted_phase.value
        or visual.analysis_boundary != snapshot.analysis_boundary
        or visual.native_resolution.canonical_subject_identity
        != snapshot.canonical_subject_identity
        or visual.reference_resolution.canonical_subject_identity
        != expected_relationship.reference_analytical_subject_identity
        or visual.reference_observed_visible_identity
        != expected_relationship.governed_visible_identity
        or tuple(item.question_id for item in visual.native_answers)
        != tuple(f"M{number:02d}" for number in range(1, 11))
        or tuple(item.question_id for item in visual.reference_answers)
        != tuple(f"R{number:02d}" for number in range(1, 7))
        or visual.escape_hatch_answer.question_id != "X01"
    ):
        return False

    if not all((
        _reference_exact(
            extension.actual_contract,
            active.binding_identity,
            active.integrity_identity,
        ),
        _reference_exact(
            extension.commissioning_publication,
            publication.publication_identity,
            publication.integrity_identity,
        ),
        _reference_exact(
            extension.roll_history,
            native.roll_history_identity,
            active.integrity_identity,
        ),
        _reference_exact(
            extension.reference_relationship,
            visual.reference_resolution.relationship_identity,
            visual.reference_resolution.relationship_integrity_identity,
        ),
        _reference_exact(
            extension.paired_visual_evidence,
            visual.visual_evidence_identity,
            visual.integrity_identity,
        ),
    )):
        return False

    usdinr = bundle.usdinr_evidence
    if usdinr is None:
        return extension.session_reference_context is None
    return _reference_exact(
        extension.session_reference_context,
        usdinr.evidence_identity,
        usdinr.integrity_identity,
    )


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


def _reference_exact(
    reference: Wo10EvidenceReference | None,
    identity: str,
    integrity: str,
) -> bool:
    return (
        reference is not None
        and reference.evidence_identity == identity
        and reference.evidence_integrity == integrity
    )


def _opposes(value: SemanticDirection, inherited: SemanticDirection) -> bool:
    return value in {SemanticDirection.LONG, SemanticDirection.SHORT} and value is not inherited


def _equity_evidence_values(value: Wo10EquityPolicyEvidence) -> dict[str, object]:
    return _equity_evidence_payload({
        name: getattr(value, name)
        for name in value.__dataclass_fields__
        if name not in {"evidence_identity", "integrity_identity"}
    })


def _index_evidence_values(value: Wo10IndexPolicyEvidence) -> dict[str, object]:
    return _equity_evidence_payload({
        name: getattr(value, name)
        for name in value.__dataclass_fields__
        if name not in {"evidence_identity", "integrity_identity"}
    })


def _mcx_evidence_values(value: Wo10McxPolicyEvidence) -> dict[str, object]:
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
    "WO10_INDEX_POLICY_AUTHORITY_VERSION",
    "WO10_INDEX_POLICY_CHECKSUM",
    "WO10_INDEX_POLICY_EVIDENCE_IDENTITY",
    "WO10_INDEX_POLICY_EVIDENCE_VERSION",
    "WO10_INDEX_POLICY_IDENTITY",
    "WO10_INDEX_POLICY_PUBLICATION_IDENTITY",
    "WO10_INDEX_POLICY_UNRESOLVED",
    "WO10_INDEX_POLICY_VERSION",
    "WO10_INDEX_SUBJECTS",
    "WO10_MCX_POLICY_AUTHORITY_VERSION",
    "WO10_MCX_POLICY_CHECKSUM",
    "WO10_MCX_POLICY_EVIDENCE_IDENTITY",
    "WO10_MCX_POLICY_EVIDENCE_VERSION",
    "WO10_MCX_POLICY_IDENTITY",
    "WO10_MCX_POLICY_PUBLICATION_IDENTITY",
    "WO10_MCX_POLICY_UNRESOLVED",
    "WO10_MCX_POLICY_VERSION",
    "WO10_MCX_SUBJECTS",
    "WO10_MCX_USDINR_AMENDMENT_IDENTITY",
    "WO10_MCX_USDINR_AMENDMENT_VERSION",
    "Wo10McxReferenceContext",
    "Wo10EquityPolicy",
    "Wo10EquityPolicyEvidence",
    "Wo10FamilyPolicy",
    "Wo10IndexPolicy",
    "Wo10IndexPolicyEvidence",
    "Wo10McxPolicy",
    "Wo10McxPolicyEvidence",
    "Wo10PolicyDecision",
    "Wo10PolicyRegistry",
    "create_wo10_equity_policy_evidence",
    "create_wo10_index_policy_evidence",
    "create_wo10_mcx_policy_evidence",
    "derive_wo10_mcx_reference_context",
    "wo10_equity_policy_binding",
    "wo10_index_policy_binding",
    "wo10_mcx_policy_binding",
]
