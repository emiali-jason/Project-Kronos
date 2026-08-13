from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import json

import pytest

from kronos.swing.v1.pine_evidence import (
    PINE_EVIDENCE_CONTRACT_ID,
    PINE_EVIDENCE_CONTRACT_VERSION,
    ParallelPineEvidenceRetention,
    PineCompatibilityClass,
    PineEvidenceRetentionKey,
    PinePublisherRole,
    build_pine_layer2_handoff,
    canonical_serialize,
    derive_event_id,
    validate_pine_evidence_payload,
)
from kronos.swing.v1.pine_registry import (
    ApprovedPineRegistry,
    ApprovedPineRegistryEntry,
    PineApprovalStatus,
    PineRegistryAuthority,
    PineRegistryOperation,
)
from tests.fixtures.swing_v1_pine_evidence import (
    MCX_PRODUCTION_COMPLETED,
    MCX_REGISTRY,
    MCX_SOURCE_SHA256,
    MCX_VALID_COMPLETED,
    NSE_PRODUCTION_COMPLETED,
    NSE_REGISTRY,
    NSE_VALID_COMPLETED,
    canonical_mcx_fixture,
)


UTC = timezone.utc


def test_production_and_candidate_have_distinct_event_and_storage_identity():
    production = MCX_PRODUCTION_COMPLETED
    candidate = MCX_VALID_COMPLETED
    assert production.observation_boundary == candidate.observation_boundary
    assert production.producer.publisher_role is PinePublisherRole.PRODUCTION
    assert candidate.producer.publisher_role is PinePublisherRole.CANDIDATE
    assert production.event_id != candidate.event_id
    assert production.stream_identity != candidate.stream_identity
    assert PineEvidenceRetentionKey.from_envelope(production) != PineEvidenceRetentionKey.from_envelope(candidate)


def test_simultaneous_production_and_candidate_evidence_is_retained_without_merge():
    retained = ParallelPineEvidenceRetention(()).retain(
        MCX_PRODUCTION_COMPLETED
    ).retain(MCX_VALID_COMPLETED)
    assert len(retained.envelopes) == 2
    assert {item.producer.publisher_role for item in retained.envelopes} == {
        PinePublisherRole.PRODUCTION,
        PinePublisherRole.CANDIDATE,
    }
    with pytest.raises(ValueError, match="COLLISION"):
        retained.retain(MCX_VALID_COMPLETED)


def test_candidate_is_shadow_only_and_cannot_reach_authoritative_handoff():
    assert MCX_REGISTRY.authority_for(MCX_VALID_COMPLETED) is PineRegistryAuthority.SHADOW_ONLY
    with pytest.raises(ValueError, match="AUTHORITY_DENIED"):
        build_pine_layer2_handoff(MCX_VALID_COMPLETED, MCX_REGISTRY)
    production_handoff = build_pine_layer2_handoff(
        MCX_PRODUCTION_COMPLETED, MCX_REGISTRY
    )
    with pytest.raises(ValueError, match="HANDOFF_INVALID"):
        replace(production_handoff, publisher_role=PinePublisherRole.CANDIDATE)


def test_registry_cannot_mark_candidate_active_for_authority():
    candidate = MCX_REGISTRY.entry("MCX-CANDIDATE-SR2")
    with pytest.raises(ValueError, match="REGISTRY_ENTRY_INVALID"):
        replace(
            candidate,
            approval_status=PineApprovalStatus.APPROVED,
            approved_at=datetime(2026, 8, 12, 0, 0, tzinfo=UTC),
            effective_from=datetime(2026, 8, 12, 0, 1, tzinfo=UTC),
            is_active_for_authority=True,
        )


def test_unknown_hash_is_rejected_for_authority():
    unknown = canonical_mcx_fixture(pine_source_sha256="e" * 64)
    assert (
        MCX_REGISTRY.authority_for(unknown)
        is PineRegistryAuthority.REJECTED_UNKNOWN_PUBLISHER
    )
    with pytest.raises(ValueError, match="AUTHORITY_DENIED"):
        build_pine_layer2_handoff(unknown, MCX_REGISTRY)


def test_approved_active_production_is_accepted_for_layer2_authority():
    assert (
        MCX_REGISTRY.authority_for(MCX_PRODUCTION_COMPLETED)
        is PineRegistryAuthority.AUTHORITATIVE
    )
    handoff = build_pine_layer2_handoff(MCX_PRODUCTION_COMPLETED, MCX_REGISTRY)
    assert handoff.publisher_role is PinePublisherRole.PRODUCTION
    assert handoff.registry_entry_id == "MCX-PRODUCTION-SR1"
    assert handoff.contract_version == PINE_EVIDENCE_CONTRACT_VERSION
    assert handoff.routine_openai_calls == 0


def test_mcx_and_nse_registries_are_product_isolated_and_version_independent():
    assert (
        MCX_REGISTRY.authority_for(NSE_PRODUCTION_COMPLETED)
        is PineRegistryAuthority.REJECTED_WRONG_PRODUCT
    )
    assert (
        NSE_REGISTRY.authority_for(MCX_PRODUCTION_COMPLETED)
        is PineRegistryAuthority.REJECTED_WRONG_PRODUCT
    )
    promoted_mcx = _promote_mcx()
    assert promoted_mcx.transitions[-1].product.value == "MCX"
    assert NSE_REGISTRY.transitions == ()
    assert (
        NSE_REGISTRY.authority_for(NSE_PRODUCTION_COMPLETED)
        is PineRegistryAuthority.AUTHORITATIVE
    )


@pytest.mark.parametrize("compatibility_class", tuple(PineCompatibilityClass))
def test_compatibility_classes_serialize_and_validate_without_inference(
    compatibility_class,
):
    producer = replace(
        MCX_VALID_COMPLETED.producer,
        compatibility_class=compatibility_class,
    )
    provenance = MCX_VALID_COMPLETED.provenance
    from kronos.swing.v1.pine_evidence import build_pine_evidence_envelope

    envelope = build_pine_evidence_envelope(
        product=MCX_VALID_COMPLETED.product,
        producer=producer,
        identity=MCX_VALID_COMPLETED.identity,
        timeframe=MCX_VALID_COMPLETED.timeframe,
        observation_boundary=MCX_VALID_COMPLETED.observation_boundary,
        sequence_number=MCX_VALID_COMPLETED.sequence_number,
        integrity=MCX_VALID_COMPLETED.integrity,
        provenance=provenance,
        evidence=MCX_VALID_COMPLETED.evidence,
        mcx=MCX_VALID_COMPLETED.mcx,
    )
    payload = json.loads(canonical_serialize(envelope))
    assert payload["producer"]["compatibility_class"] == compatibility_class.value
    assert validate_pine_evidence_payload(payload).valid


def _promote_mcx() -> ApprovedPineRegistry:
    return MCX_REGISTRY.promote(
        candidate_entry_id="MCX-CANDIDATE-SR2",
        current_production_entry_id="MCX-PRODUCTION-SR1",
        production_entry_id="MCX-PRODUCTION-SR2",
        approved_at=datetime(2026, 8, 12, 5, 0, tzinfo=UTC),
        effective_from=datetime(2026, 8, 12, 5, 1, tzinfo=UTC),
        validation_reference="MCX-SR2-PROMOTION-APPROVAL",
    )


def test_promotion_creates_production_lineage_without_relabelling_candidate():
    original_approved_at = MCX_REGISTRY.entry("MCX-PRODUCTION-SR1").approved_at
    promoted_registry = _promote_mcx()
    new_production = promoted_registry.entry("MCX-PRODUCTION-SR2")
    old_production = promoted_registry.entry("MCX-PRODUCTION-SR1")
    candidate = promoted_registry.entry("MCX-CANDIDATE-SR2")
    assert promoted_registry.transitions[-1].operation is PineRegistryOperation.PROMOTION
    assert new_production.publisher_role is PinePublisherRole.PRODUCTION
    assert new_production.promotion_source == candidate.registry_entry_id
    assert new_production.supersedes == old_production.registry_entry_id
    assert new_production.rollback_parent == old_production.registry_entry_id
    assert new_production.is_active_for_authority
    assert not old_production.is_active_for_authority
    assert old_production.approved_at == original_approved_at
    assert candidate.publisher_role is PinePublisherRole.CANDIDATE
    assert not candidate.is_active_for_authority


def test_old_production_does_not_regain_authority_from_traffic_and_rollback_is_explicit():
    promoted_registry = _promote_mcx()
    assert (
        promoted_registry.authority_for(MCX_PRODUCTION_COMPLETED)
        is PineRegistryAuthority.REJECTED_INACTIVE_PRODUCTION
    )
    rolled_back = promoted_registry.rollback(
        current_production_entry_id="MCX-PRODUCTION-SR2",
        rollback_entry_id="MCX-PRODUCTION-SR1",
        approved_at=datetime(2026, 8, 12, 6, 0, tzinfo=UTC),
        effective_from=datetime(2026, 8, 12, 6, 1, tzinfo=UTC),
        validation_reference="MCX-SR2-EXPLICIT-ROLLBACK",
    )
    assert rolled_back.transitions[-1].operation is PineRegistryOperation.ROLLBACK
    assert rolled_back.entry("MCX-PRODUCTION-SR1").is_active_for_authority
    assert not rolled_back.entry("MCX-PRODUCTION-SR2").is_active_for_authority


def test_historical_publisher_role_and_event_provenance_are_immutable():
    candidate = MCX_VALID_COMPLETED
    original_event_id = candidate.event_id
    with pytest.raises(FrozenInstanceError):
        candidate.producer.publisher_role = PinePublisherRole.PRODUCTION
    assert candidate.producer.publisher_role is PinePublisherRole.CANDIDATE
    assert candidate.event_id == original_event_id
    assert derive_event_id(candidate) == original_event_id


def test_registry_authority_is_not_present_in_webhook_or_arrival_metadata():
    payload = json.loads(canonical_serialize(MCX_VALID_COMPLETED))
    assert "approval_status" not in payload
    assert "is_active_for_authority" not in payload
    assert PINE_EVIDENCE_CONTRACT_ID == payload["producer"]["evidence_contract_id"]
