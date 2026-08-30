"""Typed WO-10 evidence-envelope contracts without factual producers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import TypeAlias

from kronos.intraday.completed_evidence import IntradayAnalysisPhase
from kronos.intraday.historical_semantic import SemanticDirection
from kronos.intraday.probables import ProbableState
from kronos.intraday.probables_v2 import ProbableMemberResultV2, ProbablesRunV2
from kronos.intraday.review_v2 import (
    ChartRevisionV2,
    ImportedVisualEvidenceV2,
    ReviewCycleV2,
    ReviewQuestionPackV2,
)
from kronos.intraday.universe import IntradayMarketFamily
from kronos.intraday.wo10 import (
    Wo10ContractError,
    Wo10PolicyBinding,
    _aware,
    _identity,
    _sha256,
    _text,
    _texts,
    _without,
    market_family_for_subject,
)
from kronos.intraday.wo10_facts import (
    Wo10RsiFact,
    Wo10SmaFacts,
    Wo10StructuralLocationFacts,
    Wo10VolumeFact,
)


WO10_EVIDENCE_SNAPSHOT_IDENTITY = "KRONOS-INTRADAY-WO10-EVIDENCE-SNAPSHOT-V1"
WO10_EVIDENCE_SNAPSHOT_VERSION = "1.0.0"
WO10_EVIDENCE_REFERENCE_IDENTITY = "KRONOS-INTRADAY-WO10-EVIDENCE-REFERENCE-V1"
WO10_EVIDENCE_REFERENCE_VERSION = "1.0.0"
WO10_COMMON_FACT_BINDINGS_IDENTITY = (
    "KRONOS-INTRADAY-WO10-COMMON-FACT-BINDINGS-V1"
)
WO10_FAMILY_EXTENSION_VERSION = "1.0.0"
WO10_EQUITY_EXTENSION_IDENTITY = "KRONOS-INTRADAY-WO10-EQUITY-EXTENSION-V1"
WO10_INDEX_EXTENSION_IDENTITY = "KRONOS-INTRADAY-WO10-INDEX-EXTENSION-V1"
WO10_MCX_EXTENSION_IDENTITY = "KRONOS-INTRADAY-WO10-MCX-EXTENSION-V1"


@dataclass(frozen=True, slots=True)
class Wo10EvidenceReference:
    evidence_identity: str
    evidence_integrity: str
    schema_identity: str = WO10_EVIDENCE_REFERENCE_IDENTITY
    schema_version: str = WO10_EVIDENCE_REFERENCE_VERSION

    def __post_init__(self) -> None:
        if (
            not _texts((self.evidence_identity, self.evidence_integrity))
            or self.schema_identity != WO10_EVIDENCE_REFERENCE_IDENTITY
            or self.schema_version != WO10_EVIDENCE_REFERENCE_VERSION
        ):
            raise Wo10ContractError("WO10_EVIDENCE_REFERENCE_INVALID")


@dataclass(frozen=True, slots=True)
class Wo10CommonFactBindings:
    one_day_structure: Wo10EvidenceReference | None
    one_hour_structure: Wo10EvidenceReference | None
    fifteen_minute_structure: Wo10EvidenceReference | None
    five_minute_progression: Wo10EvidenceReference | None
    rsi: Wo10EvidenceReference | None
    railway_track: Wo10EvidenceReference | None
    structural_location: Wo10EvidenceReference | None
    volume_telemetry: Wo10EvidenceReference | None
    integrity_identity: str
    schema_identity: str = WO10_COMMON_FACT_BINDINGS_IDENTITY
    schema_version: str = WO10_EVIDENCE_SNAPSHOT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "integrity_identity")
        references = (
            self.one_day_structure,
            self.one_hour_structure,
            self.fifteen_minute_structure,
            self.five_minute_progression,
            self.rsi,
            self.railway_track,
            self.structural_location,
            self.volume_telemetry,
        )
        if (
            any(
                item is not None and type(item) is not Wo10EvidenceReference
                for item in references
            )
            or self.schema_identity != WO10_COMMON_FACT_BINDINGS_IDENTITY
            or self.schema_version != WO10_EVIDENCE_SNAPSHOT_VERSION
            or self.integrity_identity
            != _identity("INTEGRITY-INTRADAY-WO10-COMMON-FACTS-", values)
        ):
            raise Wo10ContractError("WO10_COMMON_FACT_BINDINGS_INVALID")


def create_wo10_common_fact_bindings(
    *,
    one_day_structure: Wo10EvidenceReference | None,
    one_hour_structure: Wo10EvidenceReference | None,
    fifteen_minute_structure: Wo10EvidenceReference | None,
    five_minute_progression: Wo10EvidenceReference | None,
    rsi: Wo10EvidenceReference | None,
    railway_track: Wo10EvidenceReference | None,
    structural_location: Wo10EvidenceReference | None,
    volume_telemetry: Wo10EvidenceReference | None,
) -> Wo10CommonFactBindings:
    values = {
        "one_day_structure": one_day_structure,
        "one_hour_structure": one_hour_structure,
        "fifteen_minute_structure": fifteen_minute_structure,
        "five_minute_progression": five_minute_progression,
        "rsi": rsi,
        "railway_track": railway_track,
        "structural_location": structural_location,
        "volume_telemetry": volume_telemetry,
        "schema_identity": WO10_COMMON_FACT_BINDINGS_IDENTITY,
        "schema_version": WO10_EVIDENCE_SNAPSHOT_VERSION,
    }
    return Wo10CommonFactBindings(
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-WO10-COMMON-FACTS-", values
        ),
        **values,
    )


def create_wo10_common_fact_bindings_from_facts(
    *,
    one_day_structure: Wo10EvidenceReference | None,
    one_hour_structure: Wo10EvidenceReference | None,
    fifteen_minute_structure: Wo10EvidenceReference | None,
    five_minute_progression: Wo10EvidenceReference | None,
    rsi: Wo10RsiFact | None,
    railway_track: Wo10SmaFacts | None,
    structural_location: Wo10StructuralLocationFacts | None,
    volume_telemetry: Wo10VolumeFact | None,
) -> Wo10CommonFactBindings:
    """Adapt typed Slice-2 artifacts into the Slice-1 evidence envelope."""

    typed = (
        (rsi, Wo10RsiFact),
        (railway_track, Wo10SmaFacts),
        (structural_location, Wo10StructuralLocationFacts),
        (volume_telemetry, Wo10VolumeFact),
    )
    if any(value is not None and type(value) is not expected for value, expected in typed):
        raise Wo10ContractError("WO10_COMMON_FACT_ARTIFACT_INVALID")
    return create_wo10_common_fact_bindings(
        one_day_structure=one_day_structure,
        one_hour_structure=one_hour_structure,
        fifteen_minute_structure=fifteen_minute_structure,
        five_minute_progression=five_minute_progression,
        rsi=_fact_reference(rsi),
        railway_track=_fact_reference(railway_track),
        structural_location=_fact_reference(structural_location),
        volume_telemetry=_fact_reference(volume_telemetry),
    )


def _fact_reference(
    value: Wo10RsiFact | Wo10SmaFacts | Wo10StructuralLocationFacts | Wo10VolumeFact | None,
) -> Wo10EvidenceReference | None:
    if value is None:
        return None
    return Wo10EvidenceReference(value.evidence_identity, value.integrity_identity)


@dataclass(frozen=True, slots=True)
class Wo10EquityEvidenceExtension:
    nifty_fifteen_minute_context: Wo10EvidenceReference | None
    nifty_one_hour_context: Wo10EvidenceReference | None
    nifty_relationship: Wo10EvidenceReference | None
    integrity_identity: str
    market_family: IntradayMarketFamily = IntradayMarketFamily.NSE_EQUITY
    schema_identity: str = WO10_EQUITY_EXTENSION_IDENTITY
    schema_version: str = WO10_FAMILY_EXTENSION_VERSION

    def __post_init__(self) -> None:
        _validate_extension(
            self,
            IntradayMarketFamily.NSE_EQUITY,
            WO10_EQUITY_EXTENSION_IDENTITY,
            "INTEGRITY-INTRADAY-WO10-EQUITY-EXTENSION-",
            (
                self.nifty_fifteen_minute_context,
                self.nifty_one_hour_context,
                self.nifty_relationship,
            ),
        )


@dataclass(frozen=True, slots=True)
class Wo10IndexEvidenceExtension:
    weekly_structural_map: Wo10EvidenceReference | None
    daily_structural_map: Wo10EvidenceReference | None
    underlying_authority: Wo10EvidenceReference | None
    integrity_identity: str
    market_family: IntradayMarketFamily = IntradayMarketFamily.NSE_INDEX
    schema_identity: str = WO10_INDEX_EXTENSION_IDENTITY
    schema_version: str = WO10_FAMILY_EXTENSION_VERSION

    def __post_init__(self) -> None:
        _validate_extension(
            self,
            IntradayMarketFamily.NSE_INDEX,
            WO10_INDEX_EXTENSION_IDENTITY,
            "INTEGRITY-INTRADAY-WO10-INDEX-EXTENSION-",
            (
                self.weekly_structural_map,
                self.daily_structural_map,
                self.underlying_authority,
            ),
        )


@dataclass(frozen=True, slots=True)
class Wo10McxEvidenceExtension:
    actual_contract: Wo10EvidenceReference | None
    commissioning_publication: Wo10EvidenceReference | None
    roll_history: Wo10EvidenceReference | None
    reference_relationship: Wo10EvidenceReference | None
    paired_visual_evidence: Wo10EvidenceReference | None
    session_reference_context: Wo10EvidenceReference | None
    integrity_identity: str
    market_family: IntradayMarketFamily = IntradayMarketFamily.MCX
    schema_identity: str = WO10_MCX_EXTENSION_IDENTITY
    schema_version: str = WO10_FAMILY_EXTENSION_VERSION

    def __post_init__(self) -> None:
        _validate_extension(
            self,
            IntradayMarketFamily.MCX,
            WO10_MCX_EXTENSION_IDENTITY,
            "INTEGRITY-INTRADAY-WO10-MCX-EXTENSION-",
            (
                self.actual_contract,
                self.commissioning_publication,
                self.roll_history,
                self.reference_relationship,
                self.paired_visual_evidence,
                self.session_reference_context,
            ),
        )


Wo10FamilyEvidenceExtension: TypeAlias = (
    Wo10EquityEvidenceExtension
    | Wo10IndexEvidenceExtension
    | Wo10McxEvidenceExtension
)


def create_wo10_equity_extension(
    *,
    nifty_fifteen_minute_context: Wo10EvidenceReference | None,
    nifty_one_hour_context: Wo10EvidenceReference | None,
    nifty_relationship: Wo10EvidenceReference | None,
) -> Wo10EquityEvidenceExtension:
    values = {
        "nifty_fifteen_minute_context": nifty_fifteen_minute_context,
        "nifty_one_hour_context": nifty_one_hour_context,
        "nifty_relationship": nifty_relationship,
        "market_family": IntradayMarketFamily.NSE_EQUITY,
        "schema_identity": WO10_EQUITY_EXTENSION_IDENTITY,
        "schema_version": WO10_FAMILY_EXTENSION_VERSION,
    }
    return Wo10EquityEvidenceExtension(
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-WO10-EQUITY-EXTENSION-", values
        ),
        **values,
    )


def create_wo10_index_extension(
    *,
    weekly_structural_map: Wo10EvidenceReference | None,
    daily_structural_map: Wo10EvidenceReference | None,
    underlying_authority: Wo10EvidenceReference | None,
) -> Wo10IndexEvidenceExtension:
    values = {
        "weekly_structural_map": weekly_structural_map,
        "daily_structural_map": daily_structural_map,
        "underlying_authority": underlying_authority,
        "market_family": IntradayMarketFamily.NSE_INDEX,
        "schema_identity": WO10_INDEX_EXTENSION_IDENTITY,
        "schema_version": WO10_FAMILY_EXTENSION_VERSION,
    }
    return Wo10IndexEvidenceExtension(
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-WO10-INDEX-EXTENSION-", values
        ),
        **values,
    )


def create_wo10_mcx_extension(
    *,
    actual_contract: Wo10EvidenceReference | None,
    commissioning_publication: Wo10EvidenceReference | None,
    roll_history: Wo10EvidenceReference | None,
    reference_relationship: Wo10EvidenceReference | None,
    paired_visual_evidence: Wo10EvidenceReference | None,
    session_reference_context: Wo10EvidenceReference | None,
) -> Wo10McxEvidenceExtension:
    values = {
        "actual_contract": actual_contract,
        "commissioning_publication": commissioning_publication,
        "roll_history": roll_history,
        "reference_relationship": reference_relationship,
        "paired_visual_evidence": paired_visual_evidence,
        "session_reference_context": session_reference_context,
        "market_family": IntradayMarketFamily.MCX,
        "schema_identity": WO10_MCX_EXTENSION_IDENTITY,
        "schema_version": WO10_FAMILY_EXTENSION_VERSION,
    }
    return Wo10McxEvidenceExtension(
        integrity_identity=_identity(
            "INTEGRITY-INTRADAY-WO10-MCX-EXTENSION-", values
        ),
        **values,
    )


@dataclass(frozen=True, slots=True)
class Wo10EvidenceSnapshot:
    snapshot_identity: str
    snapshot_integrity: str
    market_family: IntradayMarketFamily
    canonical_subject_identity: str
    inherited_direction: SemanticDirection
    analysis_boundary: datetime
    persisted_phase: IntradayAnalysisPhase
    probables_run_identity: str
    probables_run_integrity: str
    probable_result_identity: str
    probable_result_integrity: str
    source_discovery_run_identity: str
    source_discovery_result_identity: str
    source_mapping_identity: str
    review_cycle_identity: str
    review_cycle_integrity: str
    chart_revision_identity: str
    chart_revision_integrity: str
    review_pack_identity: str
    review_pack_integrity: str
    imported_visual_evidence_identity: str
    imported_visual_evidence_integrity: str
    domain_001_resolution_identity: str
    domain_001_resolution_integrity: str
    domain_001_publication_identity: str
    domain_001_publication_version: str
    domain_001_publication_integrity: str
    methodology_identity: str
    methodology_version: str
    methodology_publication_identity: str
    methodology_checksum: str
    completed_evidence_identity: str
    completed_evidence_integrity: str
    semantic_evidence_identity: str
    semantic_evidence_integrity: str
    policy: Wo10PolicyBinding
    common_facts: Wo10CommonFactBindings
    family_extension: Wo10FamilyEvidenceExtension
    source_references: tuple[Wo10EvidenceReference, ...]
    provenance: tuple[str, ...]
    schema_identity: str = WO10_EVIDENCE_SNAPSHOT_IDENTITY
    schema_version: str = WO10_EVIDENCE_SNAPSHOT_VERSION

    def __post_init__(self) -> None:
        values = _without(self, "snapshot_identity", "snapshot_integrity")
        texts = (
            self.canonical_subject_identity,
            self.probables_run_identity,
            self.probables_run_integrity,
            self.probable_result_identity,
            self.probable_result_integrity,
            self.source_discovery_run_identity,
            self.source_discovery_result_identity,
            self.source_mapping_identity,
            self.review_cycle_identity,
            self.review_cycle_integrity,
            self.chart_revision_identity,
            self.chart_revision_integrity,
            self.review_pack_identity,
            self.review_pack_integrity,
            self.imported_visual_evidence_identity,
            self.imported_visual_evidence_integrity,
            self.domain_001_resolution_identity,
            self.domain_001_resolution_integrity,
            self.domain_001_publication_identity,
            self.domain_001_publication_version,
            self.domain_001_publication_integrity,
            self.methodology_identity,
            self.methodology_version,
            self.methodology_publication_identity,
            self.methodology_checksum,
            self.completed_evidence_identity,
            self.completed_evidence_integrity,
            self.semantic_evidence_identity,
            self.semantic_evidence_integrity,
        )
        if (
            type(self.market_family) is not IntradayMarketFamily
            or market_family_for_subject(self.canonical_subject_identity)
            is not self.market_family
            or self.inherited_direction
            not in {SemanticDirection.LONG, SemanticDirection.SHORT}
            or not _aware(self.analysis_boundary)
            or type(self.persisted_phase) is not IntradayAnalysisPhase
            or not _texts(texts)
            or _sha256(self.methodology_checksum) is None
            or type(self.policy) is not Wo10PolicyBinding
            or self.policy.supported_market_family is not self.market_family
            or type(self.common_facts) is not Wo10CommonFactBindings
            or not _extension_matches(self.family_extension, self.market_family)
            or not self.source_references
            or any(type(item) is not Wo10EvidenceReference for item in self.source_references)
            or tuple(sorted(
                self.source_references,
                key=lambda item: (item.evidence_identity, item.evidence_integrity),
            )) != self.source_references
            or len({item.evidence_identity for item in self.source_references})
            != len(self.source_references)
            or not _texts(self.provenance)
            or self.schema_identity != WO10_EVIDENCE_SNAPSHOT_IDENTITY
            or self.schema_version != WO10_EVIDENCE_SNAPSHOT_VERSION
            or self.snapshot_identity
            != _identity("INTRADAY-WO10-EVIDENCE-SNAPSHOT-", values)
            or self.snapshot_integrity
            != _identity("INTEGRITY-INTRADAY-WO10-EVIDENCE-SNAPSHOT-", values)
        ):
            raise Wo10ContractError("WO10_EVIDENCE_SNAPSHOT_INVALID")


def create_wo10_evidence_snapshot(
    *,
    run: ProbablesRunV2,
    result: ProbableMemberResultV2,
    cycle: ReviewCycleV2,
    chart: ChartRevisionV2,
    review_pack: ReviewQuestionPackV2,
    imported_visual_evidence: ImportedVisualEvidenceV2,
    market_family: IntradayMarketFamily,
    policy: Wo10PolicyBinding,
    common_facts: Wo10CommonFactBindings,
    family_extension: Wo10FamilyEvidenceExtension,
    source_references: tuple[Wo10EvidenceReference, ...],
    provenance: tuple[str, ...],
) -> Wo10EvidenceSnapshot:
    if (
        type(run) is not ProbablesRunV2
        or type(result) is not ProbableMemberResultV2
        or result not in run.results
        or result.state not in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}
        or result.direction not in {SemanticDirection.LONG, SemanticDirection.SHORT}
        or result.phase is None
        or not _text(result.source_mapping_identity)
        or type(cycle) is not ReviewCycleV2
        or type(chart) is not ChartRevisionV2
        or type(review_pack) is not ReviewQuestionPackV2
        or type(imported_visual_evidence) is not ImportedVisualEvidenceV2
        or type(market_family) is not IntradayMarketFamily
        or market_family_for_subject(result.canonical_subject_identity)
        is not market_family
        or type(policy) is not Wo10PolicyBinding
        or policy.supported_market_family is not market_family
        or type(common_facts) is not Wo10CommonFactBindings
        or not _extension_matches(family_extension, market_family)
        or not source_references
        or any(type(item) is not Wo10EvidenceReference for item in source_references)
        or not _texts(provenance)
        or not _v2_lineage_matches(
            run, result, cycle, chart, review_pack, imported_visual_evidence
        )
    ):
        raise Wo10ContractError("WO10_EVIDENCE_SNAPSHOT_INPUT_INVALID")
    ordered_sources = tuple(sorted(
        source_references,
        key=lambda item: (item.evidence_identity, item.evidence_integrity),
    ))
    if len({item.evidence_identity for item in ordered_sources}) != len(ordered_sources):
        raise Wo10ContractError("WO10_EVIDENCE_SOURCE_DUPLICATE")
    values = {
        "market_family": market_family,
        "canonical_subject_identity": result.canonical_subject_identity,
        "inherited_direction": result.direction,
        "analysis_boundary": result.analysis_boundary,
        "persisted_phase": result.phase,
        "probables_run_identity": run.run_identity,
        "probables_run_integrity": run.integrity_identity,
        "probable_result_identity": result.result_identity,
        "probable_result_integrity": result.integrity_identity,
        "source_discovery_run_identity": result.source_discovery_run_identity,
        "source_discovery_result_identity": result.source_discovery_member_identity,
        "source_mapping_identity": result.source_mapping_identity,
        "review_cycle_identity": cycle.cycle_identity,
        "review_cycle_integrity": cycle.integrity_identity,
        "chart_revision_identity": chart.chart_revision_identity,
        "chart_revision_integrity": chart.integrity_identity,
        "review_pack_identity": review_pack.review_pack_identity,
        "review_pack_integrity": review_pack.integrity_identity,
        "imported_visual_evidence_identity": (
            imported_visual_evidence.visual_evidence_identity
        ),
        "imported_visual_evidence_integrity": (
            imported_visual_evidence.integrity_identity
        ),
        "domain_001_resolution_identity": (
            imported_visual_evidence.visual_identity_relationship_identity
        ),
        "domain_001_resolution_integrity": (
            imported_visual_evidence.visual_identity_relationship_integrity_identity
        ),
        "domain_001_publication_identity": (
            imported_visual_evidence.visual_identity_publication_identity
        ),
        "domain_001_publication_version": (
            imported_visual_evidence.visual_identity_publication_version
        ),
        "domain_001_publication_integrity": (
            imported_visual_evidence.visual_identity_publication_integrity_identity
        ),
        "methodology_identity": result.methodology_identity,
        "methodology_version": result.methodology_version,
        "methodology_publication_identity": result.methodology_publication_identity,
        "methodology_checksum": result.methodology_checksum,
        "completed_evidence_identity": cycle.completed_evidence_selection_identity,
        "completed_evidence_integrity": cycle.completed_evidence_integrity_identity,
        "semantic_evidence_identity": cycle.semantic_evidence_identity,
        "semantic_evidence_integrity": cycle.semantic_evidence_integrity_identity,
        "policy": policy,
        "common_facts": common_facts,
        "family_extension": family_extension,
        "source_references": ordered_sources,
        "provenance": provenance,
        "schema_identity": WO10_EVIDENCE_SNAPSHOT_IDENTITY,
        "schema_version": WO10_EVIDENCE_SNAPSHOT_VERSION,
    }
    return Wo10EvidenceSnapshot(
        snapshot_identity=_identity("INTRADAY-WO10-EVIDENCE-SNAPSHOT-", values),
        snapshot_integrity=_identity(
            "INTEGRITY-INTRADAY-WO10-EVIDENCE-SNAPSHOT-", values
        ),
        **values,
    )


def _validate_extension(
    value: object,
    family: IntradayMarketFamily,
    schema: str,
    prefix: str,
    references: tuple[Wo10EvidenceReference | None, ...],
) -> None:
    values = _without(value, "integrity_identity")
    if (
        getattr(value, "market_family", None) is not family
        or getattr(value, "schema_identity", None) != schema
        or getattr(value, "schema_version", None) != WO10_FAMILY_EXTENSION_VERSION
        or any(
            item is not None and type(item) is not Wo10EvidenceReference
            for item in references
        )
        or getattr(value, "integrity_identity", None) != _identity(prefix, values)
    ):
        raise Wo10ContractError("WO10_FAMILY_EXTENSION_INVALID")


def _extension_matches(
    value: object,
    family: IntradayMarketFamily,
) -> bool:
    expected: dict[IntradayMarketFamily, type[object]] = {
        IntradayMarketFamily.NSE_EQUITY: Wo10EquityEvidenceExtension,
        IntradayMarketFamily.NSE_INDEX: Wo10IndexEvidenceExtension,
        IntradayMarketFamily.MCX: Wo10McxEvidenceExtension,
    }
    return type(value) is expected[family]


def _v2_lineage_matches(
    run: ProbablesRunV2,
    result: ProbableMemberResultV2,
    cycle: ReviewCycleV2,
    chart: ChartRevisionV2,
    pack: ReviewQuestionPackV2,
    visual: ImportedVisualEvidenceV2,
) -> bool:
    direction = result.direction.value if result.direction is not None else None
    return all((
        cycle.probables_run_identity == run.run_identity,
        cycle.probable_result_identity == result.result_identity,
        cycle.canonical_subject_identity == result.canonical_subject_identity,
        cycle.direction == direction,
        cycle.analysis_boundary == result.analysis_boundary,
        cycle.phase is result.phase,
        chart.review_cycle_identity == cycle.cycle_identity,
        chart.probables_run_identity == run.run_identity,
        chart.probable_result_identity == result.result_identity,
        chart.expected_canonical_subject_identity == result.canonical_subject_identity,
        chart.direction == direction,
        pack.probables_run_identity == run.run_identity,
        pack.probable_result_identity == result.result_identity,
        pack.review_cycle_identity == cycle.cycle_identity,
        pack.chart_revision_identity == chart.chart_revision_identity,
        pack.expected_canonical_subject_identity == result.canonical_subject_identity,
        pack.proposed_direction == direction,
        pack.analysis_boundary == result.analysis_boundary,
        pack.phase is result.phase,
        visual.probables_run_identity == run.run_identity,
        visual.probable_result_identity == result.result_identity,
        visual.review_pack_identity == pack.review_pack_identity,
        visual.review_cycle_identity == cycle.cycle_identity,
        visual.chart_revision_identity == chart.chart_revision_identity,
        visual.resolved_canonical_subject_identity == result.canonical_subject_identity,
        visual.proposed_direction == direction,
        visual.analysis_boundary == result.analysis_boundary,
        visual.phase is result.phase,
        cycle.methodology_identity == result.methodology_identity,
        cycle.methodology_version == result.methodology_version,
        cycle.methodology_publication_identity == result.methodology_publication_identity,
        cycle.methodology_checksum == result.methodology_checksum,
        pack.methodology_identity == result.methodology_identity,
        pack.methodology_version == result.methodology_version,
        pack.methodology_publication_identity == result.methodology_publication_identity,
        pack.methodology_checksum == result.methodology_checksum,
        visual.methodology_publication_identity == result.methodology_publication_identity,
        visual.methodology_checksum == result.methodology_checksum,
        pack.completed_evidence_selection_identity
        == cycle.completed_evidence_selection_identity,
        pack.completed_evidence_integrity_identity
        == cycle.completed_evidence_integrity_identity,
        pack.semantic_evidence_identity == cycle.semantic_evidence_identity,
        pack.semantic_evidence_integrity_identity
        == cycle.semantic_evidence_integrity_identity,
    ))


__all__ = [
    "WO10_COMMON_FACT_BINDINGS_IDENTITY",
    "WO10_EQUITY_EXTENSION_IDENTITY",
    "WO10_EVIDENCE_REFERENCE_IDENTITY",
    "WO10_EVIDENCE_SNAPSHOT_IDENTITY",
    "WO10_EVIDENCE_SNAPSHOT_VERSION",
    "WO10_FAMILY_EXTENSION_VERSION",
    "WO10_INDEX_EXTENSION_IDENTITY",
    "WO10_MCX_EXTENSION_IDENTITY",
    "Wo10CommonFactBindings",
    "Wo10EquityEvidenceExtension",
    "Wo10EvidenceReference",
    "Wo10EvidenceSnapshot",
    "Wo10FamilyEvidenceExtension",
    "Wo10IndexEvidenceExtension",
    "Wo10McxEvidenceExtension",
    "create_wo10_common_fact_bindings",
    "create_wo10_common_fact_bindings_from_facts",
    "create_wo10_equity_extension",
    "create_wo10_evidence_snapshot",
    "create_wo10_index_extension",
    "create_wo10_mcx_extension",
]
