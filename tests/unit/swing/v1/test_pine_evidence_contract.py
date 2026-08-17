from __future__ import annotations

from dataclasses import replace
import json

import pytest

from kronos.swing.v1.chart_evidence import (
    CHART_QUESTION_SET_V1_ID,
    ChartQuestionId,
    ManualChartEvidenceProvider,
)
from kronos.swing.v1.pine_evidence import (
    BROWSER_OWNED_QUESTION_IDS,
    KRONOS_OWNED_QUESTION_IDS,
    PINE_EVIDENCE_CONTRACT_ID,
    PINE_EVIDENCE_CONTRACT_VERSION,
    PINE_EVIDENCE_INTERNAL_MAX_BYTES,
    PINE_OWNED_QUESTION_IDS,
    TRADINGVIEW_PINE_ALERT_MESSAGE_CEILING,
    ObservationBoundaryState,
    PineEvidenceAvailability,
    PineEvidenceIntegrity,
    PineEvidenceValidationExpectations,
    PineEvidenceValidationIssueCode,
    PineCompatibilityClass,
    PineProduct,
    PinePublisherRole,
    build_pine_layer2_handoff,
    canonical_serialize,
    derive_event_id,
    payload_budget_headroom,
    validate_pine_evidence_payload,
)
from tests.fixtures.swing_v1_pine_evidence import (
    MCX_DEVELOPING,
    MCX_INVALID,
    MCX_PARTIAL_INCOMPLETE,
    MCX_PRODUCTION_COMPLETED,
    MCX_REGISTRY,
    MCX_SOURCE_SHA256,
    MCX_VALID_COMPLETED,
    NSE_DEVELOPING,
    NSE_INVALID,
    NSE_PARTIAL_INCOMPLETE,
    NSE_SOURCE_SHA256,
    NSE_VALID_COMPLETED,
    WRONG_PRODUCT_SEMANTICS,
)


def _payload(envelope):
    return json.loads(canonical_serialize(envelope))


def _expectations(envelope):
    return PineEvidenceValidationExpectations(
        product=envelope.product,
        publisher_role=envelope.producer.publisher_role,
        pine_identity=envelope.producer.pine_identity,
        pine_version=envelope.producer.pine_version,
        pine_build=envelope.producer.pine_build,
        pine_source_sha256=envelope.producer.pine_source_sha256,
        evidence_contract_id=envelope.producer.evidence_contract_id,
        evidence_contract_version=envelope.producer.evidence_contract_version,
        compatibility_class=envelope.producer.compatibility_class,
        publisher_registry_id=envelope.producer.publisher_registry_id,
    )


def test_contract_identity_version_and_question_ownership_are_frozen():
    assert PINE_EVIDENCE_CONTRACT_ID == "KRONOS-SWING-V1-PINE-EVIDENCE-V1"
    assert PINE_EVIDENCE_CONTRACT_VERSION == "1.1"
    assert len(PINE_OWNED_QUESTION_IDS) == 14
    assert BROWSER_OWNED_QUESTION_IDS == (ChartQuestionId.CHART_TEMPLATE_IDENTITY,)
    assert KRONOS_OWNED_QUESTION_IDS == (ChartQuestionId.CONTRADICTIONS,)
    assert set(PINE_OWNED_QUESTION_IDS).isdisjoint(BROWSER_OWNED_QUESTION_IDS)
    assert set(PINE_OWNED_QUESTION_IDS).isdisjoint(KRONOS_OWNED_QUESTION_IDS)


@pytest.mark.parametrize(
    "envelope, expected_product, expected_hash",
    (
        (MCX_VALID_COMPLETED, PineProduct.MCX, MCX_SOURCE_SHA256),
        (NSE_VALID_COMPLETED, PineProduct.NSE, NSE_SOURCE_SHA256),
    ),
)
def test_valid_completed_product_schemas(envelope, expected_product, expected_hash):
    result = validate_pine_evidence_payload(_payload(envelope), _expectations(envelope))
    assert result.valid
    assert result.issues == ()
    assert result.envelope == envelope
    assert envelope.product is expected_product
    assert envelope.producer.pine_source_sha256 == expected_hash


def test_mcx_and_nse_extensions_are_isolated():
    assert MCX_VALID_COMPLETED.mcx is not None
    assert MCX_VALID_COMPLETED.nse is None
    assert MCX_VALID_COMPLETED.mcx.reference_market.value == "COMEX"
    assert NSE_VALID_COMPLETED.mcx is None
    assert NSE_VALID_COMPLETED.nse is not None
    assert NSE_VALID_COMPLETED.nse.sector_index == "NSE:CNXENERGY"
    assert NSE_VALID_COMPLETED.nse.now.availability is PineEvidenceAvailability.NOT_APPLICABLE
    assert NSE_VALID_COMPLETED.nse.now.state == "NOT_IN_NSE_V1"
    assert NSE_VALID_COMPLETED.integrity is PineEvidenceIntegrity.VALID


def test_boundary_states_preserve_completed_and_developing_meaning():
    assert MCX_VALID_COMPLETED.observation_boundary.state is ObservationBoundaryState.COMPLETED
    assert MCX_VALID_COMPLETED.observation_boundary.confirmed
    assert MCX_DEVELOPING.observation_boundary.state is ObservationBoundaryState.DEVELOPING
    assert not MCX_DEVELOPING.observation_boundary.confirmed
    assert NSE_DEVELOPING.observation_boundary.state is ObservationBoundaryState.DEVELOPING


def test_availability_and_integrity_models_preserve_partial_evidence():
    mcx_sma200 = next(
        item for item in MCX_PARTIAL_INCOMPLETE.evidence if item.question_id.value == "SMA200"
    )
    nse_volume = next(
        item
        for item in NSE_PARTIAL_INCOMPLETE.evidence
        if item.question_id.value == "VOLUME_CONTEXT"
    )
    assert mcx_sma200.availability is PineEvidenceAvailability.UNAVAILABLE
    assert nse_volume.availability is PineEvidenceAvailability.UNAVAILABLE
    assert MCX_PARTIAL_INCOMPLETE.integrity is PineEvidenceIntegrity.INCOMPLETE
    assert NSE_PARTIAL_INCOMPLETE.integrity is PineEvidenceIntegrity.INCOMPLETE


def test_canonical_serialization_and_event_identity_are_deterministic():
    first = canonical_serialize(MCX_VALID_COMPLETED)
    second = canonical_serialize(MCX_VALID_COMPLETED)
    assert first == second
    assert derive_event_id(MCX_VALID_COMPLETED) == MCX_VALID_COMPLETED.event_id
    assert canonical_serialize(json.loads(first)) == first


def test_changed_evidence_changes_event_identity():
    original = MCX_VALID_COMPLETED
    item = original.evidence[0]
    changed_item = replace(item, value="CHANGED")
    changed_evidence = (changed_item, *original.evidence[1:])
    from kronos.swing.v1.pine_evidence import build_pine_evidence_envelope

    changed = build_pine_evidence_envelope(
        product=original.product,
        producer=original.producer,
        identity=original.identity,
        timeframe=original.timeframe,
        observation_boundary=original.observation_boundary,
        sequence_number=original.sequence_number,
        integrity=original.integrity,
        provenance=original.provenance,
        evidence=changed_evidence,
        mcx=original.mcx,
    )
    assert changed.event_id != original.event_id


@pytest.mark.parametrize("payload", (MCX_INVALID, NSE_INVALID))
def test_invalid_fixture_rejects_tampered_event_identity(payload):
    result = validate_pine_evidence_payload(payload)
    assert not result.valid
    assert result.integrity is PineEvidenceIntegrity.INVALID
    assert PineEvidenceValidationIssueCode.INVALID_EVENT_ID in result.issues


def test_wrong_product_semantics_are_rejected():
    result = validate_pine_evidence_payload(WRONG_PRODUCT_SEMANTICS)
    assert not result.valid
    assert PineEvidenceValidationIssueCode.INVALID_PRODUCT_SPECIFIC_FIELDS in result.issues


def test_wrong_contract_version_is_explicit():
    payload = _payload(MCX_VALID_COMPLETED)
    payload["contract_version"] = "2.0"
    result = validate_pine_evidence_payload(payload)
    assert not result.valid
    assert PineEvidenceValidationIssueCode.UNSUPPORTED_CONTRACT_VERSION in result.issues


def test_missing_required_field_is_explicit():
    payload = _payload(MCX_VALID_COMPLETED)
    del payload["producer"]
    result = validate_pine_evidence_payload(payload)
    assert not result.valid
    assert result.issues == (PineEvidenceValidationIssueCode.MISSING_MANDATORY_FIELD,)


def test_wrong_producer_expectations_are_explicit():
    envelope = MCX_VALID_COMPLETED
    expected = replace(
        _expectations(envelope),
        product=PineProduct.NSE,
        publisher_role=PinePublisherRole.PRODUCTION,
        pine_identity="WRONG",
        pine_version="9.9",
        pine_build="9999",
        pine_source_sha256="f" * 64,
        evidence_contract_id=PINE_EVIDENCE_CONTRACT_ID,
        evidence_contract_version=PINE_EVIDENCE_CONTRACT_VERSION,
        compatibility_class=PineCompatibilityClass.NEW_EVIDENCE_ADDITION,
        publisher_registry_id="WRONG-REGISTRY",
    )
    result = validate_pine_evidence_payload(_payload(envelope), expected)
    assert not result.valid
    assert set(result.issues) == {
        PineEvidenceValidationIssueCode.WRONG_PRODUCT,
        PineEvidenceValidationIssueCode.WRONG_PUBLISHER_ROLE,
        PineEvidenceValidationIssueCode.WRONG_PINE_IDENTITY,
        PineEvidenceValidationIssueCode.WRONG_PINE_VERSION,
        PineEvidenceValidationIssueCode.WRONG_PINE_BUILD,
        PineEvidenceValidationIssueCode.WRONG_SOURCE_HASH,
        PineEvidenceValidationIssueCode.WRONG_COMPATIBILITY_CLASS,
        PineEvidenceValidationIssueCode.WRONG_PUBLISHER_REGISTRY,
    }


@pytest.mark.parametrize(
    "section, field, value, issue",
    (
        ("timeframe", "chart_timeframe", "ONE_HOUR", PineEvidenceValidationIssueCode.INVALID_TIMEFRAME_REPRESENTATION),
        ("observation_boundary", "state", "FINAL", PineEvidenceValidationIssueCode.INVALID_BOUNDARY_REPRESENTATION),
    ),
)
def test_invalid_timeframe_and_boundary_representations(section, field, value, issue):
    payload = _payload(MCX_VALID_COMPLETED)
    payload[section][field] = value
    result = validate_pine_evidence_payload(payload)
    assert not result.valid
    assert issue in result.issues


def test_fixture_sizes_stay_inside_internal_budget_with_large_headroom():
    fixtures = (
        MCX_VALID_COMPLETED,
        MCX_DEVELOPING,
        MCX_PARTIAL_INCOMPLETE,
        NSE_VALID_COMPLETED,
        NSE_DEVELOPING,
        NSE_PARTIAL_INCOMPLETE,
    )
    largest = max(len(canonical_serialize(item)) for item in fixtures)
    budget = payload_budget_headroom(largest)
    assert largest < PINE_EVIDENCE_INTERNAL_MAX_BYTES
    assert PINE_EVIDENCE_INTERNAL_MAX_BYTES < TRADINGVIEW_PINE_ALERT_MESSAGE_CEILING / 2
    assert budget["internal_headroom_bytes"] > 0
    assert budget["tradingview_headroom"] > 24_000


def test_existing_layer2_provider_contract_remains_compatible_and_separate():
    handoff = build_pine_layer2_handoff(MCX_PRODUCTION_COMPLETED, MCX_REGISTRY)
    assert handoff.question_set_identity == CHART_QUESTION_SET_V1_ID
    assert handoff.routine_openai_calls == 0
    assert handoff.browser_owned_questions == (ChartQuestionId.CHART_TEMPLATE_IDENTITY,)
    assert handoff.kronos_owned_questions == (ChartQuestionId.CONTRADICTIONS,)
    assert handoff.mcx == MCX_PRODUCTION_COMPLETED.mcx
    assert handoff.observation_boundary == MCX_PRODUCTION_COMPLETED.observation_boundary
    assert handoff.provenance == MCX_PRODUCTION_COMPLETED.provenance
    assert callable(getattr(ManualChartEvidenceProvider, "analyze"))
    assert isinstance(ManualChartEvidenceProvider.provider_identity, property)


def test_stream_identity_excludes_arrival_time_and_tracks_stream_tuple():
    assert len(MCX_VALID_COMPLETED.stream_identity) == 64
    assert MCX_VALID_COMPLETED.stream_identity != NSE_VALID_COMPLETED.stream_identity
