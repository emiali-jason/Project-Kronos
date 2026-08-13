"""Canonical synthetic fixtures for the Swing V1 Pine evidence contract."""

from __future__ import annotations

from datetime import datetime, timezone

from kronos.swing.v1.pine_evidence import (
    InstrumentType,
    McxPineEvidenceExtension,
    NsePineEvidenceExtension,
    ObservationBoundaryState,
    PineDomainEvidence,
    PineEnvelopeProvenance,
    PineEvidenceAvailability,
    PineCompatibilityClass,
    PineEvidenceDerivation,
    PineEvidenceDomain,
    PineEvidenceEnvelope,
    PineEvidenceIntegrity,
    PineEvidenceProvenance,
    PineInstrumentIdentity,
    PineObservationBoundary,
    PineProducer,
    PineProducerType,
    PineProduct,
    PinePublisherRole,
    PineTimeframeIdentity,
    ProductContextEvidence,
    ProductTimeframeState,
    ReferenceMarket,
    build_pine_evidence_envelope,
)
from kronos.swing.v1.pine_registry import (
    ApprovedPineRegistry,
    ApprovedPineRegistryEntry,
    PineApprovalStatus,
)


UTC = timezone.utc
MCX_SOURCE_SHA256 = "d3048aa6d0f6f3a97585a4cc35d36d5839352d91ec8ff05d5989a495d341d54a"
NSE_SOURCE_SHA256 = "33ddbdd416d905bf4cb925d45d08d9d4efccfe6db969b668d5101164c96b48f2"
MCX_PRODUCTION_SOURCE_SHA256 = "d8043e5c1583b5ab798bb925aa917ecc53b0564508ad36b3722e42de16d17c9d"
NSE_PRODUCTION_SOURCE_SHA256 = "1" * 64
MCX_REGISTRY_ID = "KRONOS-SWING-V1-MCX-PINE-REGISTRY"
NSE_REGISTRY_ID = "KRONOS-SWING-V1-NSE-PINE-REGISTRY"


def _boundary(state: ObservationBoundaryState) -> PineObservationBoundary:
    return PineObservationBoundary(
        state=state,
        chart_bar_open_ts=datetime(2026, 8, 11, 3, 45, tzinfo=UTC),
        chart_bar_close_ts=datetime(2026, 8, 11, 4, 45, tzinfo=UTC),
        evaluated_ts=(
            datetime(2026, 8, 11, 4, 45, tzinfo=UTC)
            if state is ObservationBoundaryState.COMPLETED
            else datetime(2026, 8, 11, 4, 15, tzinfo=UTC)
        ),
        timeframe="60",
        confirmed=state is ObservationBoundaryState.COMPLETED,
        source_period_identity="60:2026-08-11T03:45:00Z",
    )


def _context(
    state: str,
    *,
    availability: PineEvidenceAvailability = PineEvidenceAvailability.AVAILABLE,
    integrity: PineEvidenceIntegrity = PineEvidenceIntegrity.VALID,
) -> ProductContextEvidence:
    return ProductContextEvidence(
        availability=availability,
        state=state,
        source_fields=("fixture_context",) if availability is PineEvidenceAvailability.AVAILABLE else (),
        integrity=integrity,
    )


def _evidence(
    producer_identity: str,
    boundary: PineObservationBoundary,
    *,
    unavailable: PineEvidenceDomain | None = None,
    not_applicable: PineEvidenceDomain | None = None,
) -> tuple[PineDomainEvidence, ...]:
    result: list[PineDomainEvidence] = []
    for domain in PineEvidenceDomain:
        availability = PineEvidenceAvailability.AVAILABLE
        integrity = PineEvidenceIntegrity.VALID
        state = "OBSERVED"
        value: str | None = f"{domain.value}_VALUE"
        source_fields = (f"fixture_{domain.value.lower()}",)
        if domain is unavailable:
            availability = PineEvidenceAvailability.UNAVAILABLE
            integrity = PineEvidenceIntegrity.INCOMPLETE
            state = "SOURCE_NOT_AVAILABLE"
            value = None
            source_fields = ()
        elif domain is not_applicable:
            availability = PineEvidenceAvailability.NOT_APPLICABLE
            integrity = PineEvidenceIntegrity.VALID
            state = "NOT_APPLICABLE_FOR_PRODUCT"
            value = None
            source_fields = ()
        result.append(
            PineDomainEvidence(
                question_id=domain,
                availability=availability,
                state=state,
                value=value,
                values=(),
                source_engine="KRONOS_PINE_FIXTURE_ENGINE",
                source_fields=source_fields,
                derivation=PineEvidenceDerivation.DIRECT,
                integrity=integrity,
                boundary_state=boundary.state,
                provenance=PineEvidenceProvenance(
                    producer_identity=producer_identity,
                    source_period_identity=boundary.source_period_identity,
                    calculation_identity=f"FIXTURE-{domain.value}-V1",
                ),
            )
        )
    return tuple(result)


def canonical_mcx_fixture(
    state: ObservationBoundaryState = ObservationBoundaryState.COMPLETED,
    *,
    incomplete: bool = False,
    publisher_role: PinePublisherRole = PinePublisherRole.CANDIDATE,
    pine_identity: str | None = None,
    pine_source_sha256: str | None = None,
) -> PineEvidenceEnvelope:
    boundary = _boundary(state)
    producer = PineProducer(
        producer_type=PineProducerType.TRADINGVIEW_PINE,
        publisher_role=publisher_role,
        pine_identity=pine_identity or (
            "KRONOS_FUTURES_PRODUCTION"
            if publisher_role is PinePublisherRole.PRODUCTION
            else "KRONOS_FUTURES_V2_CANDIDATE"
        ),
        pine_version="0.6.0",
        pine_build="0005",
        pine_source_sha256=pine_source_sha256 or (
            MCX_PRODUCTION_SOURCE_SHA256
            if publisher_role is PinePublisherRole.PRODUCTION
            else MCX_SOURCE_SHA256
        ),
        evidence_contract_id="KRONOS-SWING-V1-PINE-EVIDENCE-V1",
        evidence_contract_version="1.1",
        compatibility_class=(
            PineCompatibilityClass.IMPLEMENTATION_CHANGE_CONTRACT_COMPATIBLE
        ),
        publisher_registry_id=MCX_REGISTRY_ID,
    )
    evidence = _evidence(
        producer.pine_identity,
        boundary,
        unavailable=(PineEvidenceDomain.SMA200 if incomplete else None),
    )
    extension = McxPineEvidenceExtension(
        analytical_identity="MCX:GOLD1!",
        reference_symbol="COMEX:GC1!",
        reference_market=ReferenceMarket.COMEX,
        reference_timeframe_states=(
            ProductTimeframeState(
                timeframe="D",
                availability=PineEvidenceAvailability.AVAILABLE,
                state="BULLISH",
                boundary_state=boundary.state,
            ),
            ProductTimeframeState(
                timeframe="240",
                availability=PineEvidenceAvailability.AVAILABLE,
                state="BULLISH",
                boundary_state=boundary.state,
            ),
        ),
        readiness_reference_context=_context("REFERENCE_ALIGNED"),
        commodity_workstation_semantics=(
            "MCX_FUTURES_ANALYSIS",
            "COMEX_REFERENCE_CONTEXT",
        ),
        now_trigger_evidence=_context("NOW_TRIGGER_PRESENT"),
    )
    integrity = (
        PineEvidenceIntegrity.INCOMPLETE
        if incomplete
        else PineEvidenceIntegrity.VALID
    )
    return build_pine_evidence_envelope(
        product=PineProduct.MCX,
        producer=producer,
        identity=PineInstrumentIdentity(
            canonical_instrument="MCX_GOLD_FUTURE",
            tradingview_symbol="MCX:GOLD1!",
            analysis_subject="MCX:GOLD1!",
            execution_subject="MCX:GOLDM_NEAREST_ELIGIBLE",
            exchange="MCX",
            instrument_type=InstrumentType.FUTURE,
            supported_instrument=True,
        ),
        timeframe=PineTimeframeIdentity(
            chart_timeframe="60",
            strategic_timeframe="D",
            trend_timeframe="240",
            structure_timeframe="60",
            execution_timeframe="60",
        ),
        observation_boundary=boundary,
        sequence_number=731,
        integrity=integrity,
        provenance=PineEnvelopeProvenance(
            publisher=producer.pine_identity,
            publisher_role=publisher_role,
            publisher_registry_id=MCX_REGISTRY_ID,
            lineage_identity=(
                "MCX-PRODUCTION-SR1"
                if publisher_role is PinePublisherRole.PRODUCTION
                else "MCX-CANDIDATE-SR2"
            ),
            publication_identity=(
                "PRODUCTION-SR1"
                if publisher_role is PinePublisherRole.PRODUCTION
                else "V2-SR2"
            ),
            calculation_basis="FROZEN_SYNTHETIC_CONTRACT_FIXTURE",
        ),
        evidence=evidence,
        mcx=extension,
    )


def canonical_nse_fixture(
    state: ObservationBoundaryState = ObservationBoundaryState.COMPLETED,
    *,
    incomplete: bool = False,
    publisher_role: PinePublisherRole = PinePublisherRole.CANDIDATE,
    pine_identity: str | None = None,
    pine_source_sha256: str | None = None,
) -> PineEvidenceEnvelope:
    boundary = _boundary(state)
    producer = PineProducer(
        producer_type=PineProducerType.TRADINGVIEW_PINE,
        publisher_role=publisher_role,
        pine_identity=pine_identity or (
            "KRONOS_NSE_V1_PRODUCTION_FIXTURE"
            if publisher_role is PinePublisherRole.PRODUCTION
            else "KRONOS_NSE_V1_CANDIDATE"
        ),
        pine_version="0.6.0",
        pine_build="0005",
        pine_source_sha256=pine_source_sha256 or (
            NSE_PRODUCTION_SOURCE_SHA256
            if publisher_role is PinePublisherRole.PRODUCTION
            else NSE_SOURCE_SHA256
        ),
        evidence_contract_id="KRONOS-SWING-V1-PINE-EVIDENCE-V1",
        evidence_contract_version="1.1",
        compatibility_class=(
            PineCompatibilityClass.IMPLEMENTATION_CHANGE_CONTRACT_COMPATIBLE
        ),
        publisher_registry_id=NSE_REGISTRY_ID,
    )
    evidence = _evidence(
        producer.pine_identity,
        boundary,
        unavailable=(PineEvidenceDomain.VOLUME_CONTEXT if incomplete else None),
        not_applicable=PineEvidenceDomain.PINE_DISPLAY,
    )
    extension = NsePineEvidenceExtension(
        cash_analysis_symbol="NSE:RELIANCE",
        futures_to_underlying_provenance="FUTURES_INPUT_ROUTED_TO_CASH_UNDERLYING",
        sector_index="NSE:CNXENERGY",
        parent_index="NSE:NIFTY",
        sector_context=_context("SECTOR_ALIGNED"),
        broad_market_context=_context("BROAD_MARKET_ALIGNED"),
        relative_alignment=_context("RELATIVE_OUTPERFORMANCE"),
        reference_completeness=(
            PineEvidenceIntegrity.INCOMPLETE
            if incomplete
            else PineEvidenceIntegrity.VALID
        ),
        readiness_context=_context("BUY_READY"),
        now=_context(
            "NOT_IN_NSE_V1",
            availability=PineEvidenceAvailability.NOT_APPLICABLE,
            integrity=PineEvidenceIntegrity.VALID,
        ),
    )
    integrity = (
        PineEvidenceIntegrity.INCOMPLETE
        if incomplete
        else PineEvidenceIntegrity.VALID
    )
    return build_pine_evidence_envelope(
        product=PineProduct.NSE,
        producer=producer,
        identity=PineInstrumentIdentity(
            canonical_instrument="NSE_RELIANCE_EQUITY",
            tradingview_symbol="NSE:RELIANCE",
            analysis_subject="NSE:RELIANCE",
            execution_subject="NFO:RELIANCE_NEAREST_ELIGIBLE",
            exchange="NSE",
            instrument_type=InstrumentType.EQUITY,
            supported_instrument=True,
        ),
        timeframe=PineTimeframeIdentity(
            chart_timeframe="60",
            strategic_timeframe="D",
            trend_timeframe="240",
            structure_timeframe="60",
            execution_timeframe="60",
        ),
        observation_boundary=boundary,
        sequence_number=1189,
        integrity=integrity,
        provenance=PineEnvelopeProvenance(
            publisher=producer.pine_identity,
            publisher_role=publisher_role,
            publisher_registry_id=NSE_REGISTRY_ID,
            lineage_identity=(
                "NSE-PRODUCTION-SR1"
                if publisher_role is PinePublisherRole.PRODUCTION
                else "NSE-CANDIDATE-SR1"
            ),
            publication_identity=(
                "NSE-PRODUCTION-SR1"
                if publisher_role is PinePublisherRole.PRODUCTION
                else "NSE-V1-SR1"
            ),
            calculation_basis="FROZEN_SYNTHETIC_CONTRACT_FIXTURE",
        ),
        evidence=evidence,
        nse=extension,
    )


MCX_VALID_COMPLETED = canonical_mcx_fixture()
MCX_DEVELOPING = canonical_mcx_fixture(ObservationBoundaryState.DEVELOPING)
MCX_PARTIAL_INCOMPLETE = canonical_mcx_fixture(incomplete=True)
NSE_VALID_COMPLETED = canonical_nse_fixture()
NSE_DEVELOPING = canonical_nse_fixture(ObservationBoundaryState.DEVELOPING)
NSE_PARTIAL_INCOMPLETE = canonical_nse_fixture(incomplete=True)
MCX_PRODUCTION_COMPLETED = canonical_mcx_fixture(
    publisher_role=PinePublisherRole.PRODUCTION
)
NSE_PRODUCTION_COMPLETED = canonical_nse_fixture(
    publisher_role=PinePublisherRole.PRODUCTION
)


def canonical_registry(
    production: PineEvidenceEnvelope,
    candidate: PineEvidenceEnvelope,
) -> ApprovedPineRegistry:
    approved_at = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    effective_from = datetime(2026, 8, 1, 0, 1, tzinfo=UTC)
    return ApprovedPineRegistry(
        registry_id=production.producer.publisher_registry_id,
        product=production.product,
        entries=(
            ApprovedPineRegistryEntry(
                registry_entry_id=f"{production.product.value}-PRODUCTION-SR1",
                publisher_registry_id=production.producer.publisher_registry_id,
                product=production.product,
                publisher_role=PinePublisherRole.PRODUCTION,
                pine_identity=production.producer.pine_identity,
                pine_version=production.producer.pine_version,
                pine_build=production.producer.pine_build,
                pine_source_sha256=production.producer.pine_source_sha256,
                evidence_contract_id=production.producer.evidence_contract_id,
                evidence_contract_version=production.producer.evidence_contract_version,
                compatibility_class=production.producer.compatibility_class,
                approval_status=PineApprovalStatus.APPROVED,
                approved_at=approved_at,
                effective_from=effective_from,
                supersedes=None,
                superseded_by=None,
                rollback_parent=None,
                validation_reference=f"{production.product.value}-PRODUCTION-VALIDATION",
                is_active_for_authority=True,
            ),
            ApprovedPineRegistryEntry(
                registry_entry_id=f"{candidate.product.value}-CANDIDATE-SR2",
                publisher_registry_id=candidate.producer.publisher_registry_id,
                product=candidate.product,
                publisher_role=PinePublisherRole.CANDIDATE,
                pine_identity=candidate.producer.pine_identity,
                pine_version=candidate.producer.pine_version,
                pine_build=candidate.producer.pine_build,
                pine_source_sha256=candidate.producer.pine_source_sha256,
                evidence_contract_id=candidate.producer.evidence_contract_id,
                evidence_contract_version=candidate.producer.evidence_contract_version,
                compatibility_class=candidate.producer.compatibility_class,
                approval_status=PineApprovalStatus.VALIDATED,
                approved_at=None,
                effective_from=None,
                supersedes=None,
                superseded_by=None,
                rollback_parent=None,
                validation_reference=f"{candidate.product.value}-CANDIDATE-VALIDATION",
                is_active_for_authority=False,
            ),
        ),
    )


MCX_REGISTRY = canonical_registry(MCX_PRODUCTION_COMPLETED, MCX_VALID_COMPLETED)
NSE_REGISTRY = canonical_registry(NSE_PRODUCTION_COMPLETED, NSE_VALID_COMPLETED)


def invalid_event_fixture(envelope: PineEvidenceEnvelope) -> dict[str, object]:
    from kronos.swing.v1.pine_evidence import canonical_serialize
    import json

    payload = json.loads(canonical_serialize(envelope))
    payload["event_id"] = "0" * 64
    return payload


MCX_INVALID = invalid_event_fixture(MCX_VALID_COMPLETED)
NSE_INVALID = invalid_event_fixture(NSE_VALID_COMPLETED)
WRONG_PRODUCT_SEMANTICS = {
    **invalid_event_fixture(MCX_VALID_COMPLETED),
    "product": "NSE",
}


__all__ = [
    "MCX_DEVELOPING",
    "MCX_INVALID",
    "MCX_PARTIAL_INCOMPLETE",
    "MCX_PRODUCTION_COMPLETED",
    "MCX_PRODUCTION_SOURCE_SHA256",
    "MCX_REGISTRY",
    "MCX_REGISTRY_ID",
    "MCX_SOURCE_SHA256",
    "MCX_VALID_COMPLETED",
    "NSE_DEVELOPING",
    "NSE_INVALID",
    "NSE_PARTIAL_INCOMPLETE",
    "NSE_PRODUCTION_COMPLETED",
    "NSE_PRODUCTION_SOURCE_SHA256",
    "NSE_REGISTRY",
    "NSE_REGISTRY_ID",
    "NSE_SOURCE_SHA256",
    "NSE_VALID_COMPLETED",
    "WRONG_PRODUCT_SEMANTICS",
    "canonical_mcx_fixture",
    "canonical_nse_fixture",
    "canonical_registry",
]
