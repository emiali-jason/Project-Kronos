from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone

import pytest

from kronos.provider.adapters.kite.capability import (
    KITE_API_BASIS,
    KITE_PROVIDER,
    KITE_SDK_BASIS,
    kite_approved_evidence_references,
    kite_capability_evidence,
    kite_implementation_evidence,
)
from kronos.provider.models.capability import (
    CapabilityAssessmentOutcomeKind,
    CapabilityAssessmentReason,
    CapabilityAssessmentRequest,
    CapabilityEvidence,
    CapabilityIdentifier,
    EvidenceAssertion,
    EvidenceClass,
    EvidenceCurrentness,
    EvidenceScope,
    ImplementationDisposition,
    ImplementationDispositionEvidence,
    ProviderSupport,
)
from kronos.provider.services.capability import (
    ProviderCapabilityAssessmentService,
)


_NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
_REVISION = "edd002-test-revision"
_AUTHORITY = "EDD-002:IMPLEMENTATION_AUTHORIZATION"
_CAPABILITY = CapabilityIdentifier.INSTRUMENT_REFERENCE
_EXPECTED_KITE_LIMITATIONS = {
    CapabilityIdentifier.INSTRUMENT_REFERENCE: (
        (
            "data-currentness",
            "The documented instrument dump is generated once daily.",
        ),
        (
            "other-documented-technical-constraint",
            "The documented instrument dump is large and is not a lightweight "
            "current-state response.",
        ),
        (
            "data-currentness",
            "The documented last_price value in the instrument dump is not "
            "real-time.",
        ),
        (
            "other-documented-technical-constraint",
            "Instrument tokens may be reused by the Provider and are not a "
            "permanent identity by themselves.",
        ),
    ),
    CapabilityIdentifier.FULL_QUOTE_SNAPSHOT: (
        (
            "request-size",
            "The documented maximum is 500 instruments per request.",
        ),
        (
            "other-documented-technical-constraint",
            "Requested keys may be absent when data is unavailable.",
        ),
    ),
    CapabilityIdentifier.OHLC_SNAPSHOT: (
        (
            "request-size",
            "The documented maximum is 1000 instruments per request.",
        ),
        (
            "data-currentness",
            "The response is a current snapshot, not a completed historical candle.",
        ),
        (
            "other-documented-technical-constraint",
            "Requested instrument keys may be absent when data is unavailable.",
        ),
    ),
    CapabilityIdentifier.LTP_SNAPSHOT: (
        (
            "request-size",
            "The documented maximum is 1000 instruments per request.",
        ),
        (
            "other-documented-technical-constraint",
            "Requested keys may be absent when data is unavailable.",
        ),
    ),
    CapabilityIdentifier.HISTORICAL_OBSERVATION: (
        (
            "interval-support",
            "Documented intervals are minute, day, 3minute, 5minute, "
            "10minute, 15minute, 30minute and 60minute.",
        ),
        (
            "provider-scope",
            "Continuous history is limited to documented NFO and MCX futures "
            "behaviour and day candles.",
        ),
    ),
    CapabilityIdentifier.LIVE_OBSERVATION_STREAMING: (
        (
            "other-documented-technical-constraint",
            "The documented streaming modes are ltp, quote and full.",
        ),
        (
            "subscription-count",
            "The documented maximum is 3000 instruments per connection.",
        ),
        (
            "connection-count",
            "The documented maximum is three WebSocket connections per API key.",
        ),
    ),
}


def _implementation_evidence(
    selected: ImplementationDisposition = ImplementationDisposition.NOT_IMPLEMENTED,
) -> dict[CapabilityIdentifier, ImplementationDispositionEvidence]:
    result = kite_implementation_evidence(_REVISION)
    if selected is ImplementationDisposition.IMPLEMENTED:
        result[_CAPABILITY] = ImplementationDispositionEvidence(
            capability_identifier=_CAPABILITY,
            disposition=selected,
            authority_reference="EDD-002:IMPLEMENTATION_AUTHORIZATION",
            contract_reference="kronos.provider.contracts.capability",
            adapter_reference="kronos.provider.adapters.kite.capability",
            repository_revision=_REVISION,
            dependency_basis=KITE_SDK_BASIS,
            boundary_verified=True,
        )
    elif selected is ImplementationDisposition.DEFERRED:
        result[_CAPABILITY] = ImplementationDispositionEvidence(
            capability_identifier=_CAPABILITY,
            disposition=selected,
            authority_reference="ADR-007:CURRENT_PHASE_ROADMAP",
            repository_revision=_REVISION,
            reason="Outside the current authorized phase.",
        )
    return result


def _service(
    disposition: ImplementationDisposition = ImplementationDisposition.NOT_IMPLEMENTED,
) -> ProviderCapabilityAssessmentService:
    approved_references = kite_approved_evidence_references()
    approved_references[_CAPABILITY] = (
        approved_references[_CAPABILITY]
        | {"https://provider.example/capability"}
    )
    return ProviderCapabilityAssessmentService(
        KITE_PROVIDER,
        _implementation_evidence(disposition),
        frozenset({_AUTHORITY}),
        approved_references,
    )


def _evidence(
    *,
    assertion: EvidenceAssertion = EvidenceAssertion.SUPPORTS,
    evidence_class: EvidenceClass = EvidenceClass.OFFICIAL_PROVIDER_DOCUMENTATION,
    currentness: EvidenceCurrentness = EvidenceCurrentness.CURRENT,
    source_reference: str = "https://provider.example/capability",
    provider: str = KITE_PROVIDER,
    capability_identifier: CapabilityIdentifier = _CAPABILITY,
) -> CapabilityEvidence:
    return CapabilityEvidence(
        evidence_id=f"evidence:{assertion.value}:{evidence_class.value}",
        evidence_class=evidence_class,
        provider=provider,
        capability_identifier=capability_identifier,
        source_reference=source_reference,
        assertion=assertion,
        provider_api_basis=KITE_API_BASIS,
        currentness=currentness,
        scope=EvidenceScope.PROVIDER_WIDE,
        evidence_time=_NOW,
        sdk_version_basis=(
            KITE_SDK_BASIS
            if evidence_class
            is EvidenceClass.APPROVED_ADAPTER_LOCKED_SDK_COMPATIBILITY
            else None
        ),
        adapter_revision_basis=(
            _REVISION
            if evidence_class
            is EvidenceClass.APPROVED_ADAPTER_LOCKED_SDK_COMPATIBILITY
            else None
        ),
    )


def _request(
    evidence: tuple[CapabilityEvidence, ...],
    *,
    assessment_id: str = "assessment-001",
    capability_identifier: CapabilityIdentifier | str = _CAPABILITY,
    requested_evidence_classes: tuple[EvidenceClass | str, ...] | None = None,
    evidence_references: tuple[str, ...] | None = None,
    authority: str = _AUTHORITY,
    prior_record_id: str | None = None,
    supersession_reason: str | None = None,
    provider_context_reference: str | None = None,
) -> CapabilityAssessmentRequest:
    return CapabilityAssessmentRequest(
        assessment_id=assessment_id,
        provider=KITE_PROVIDER,
        capability_identifier=capability_identifier,
        requested_evidence_classes=(
            requested_evidence_classes
            if requested_evidence_classes is not None
            else tuple(item.evidence_class for item in evidence)
        ),
        evidence_references=(
            evidence_references
            if evidence_references is not None
            else tuple(item.source_reference for item in evidence)
        ),
        assessment_authority_reference=authority,
        compatibility_basis=KITE_API_BASIS,
        assessment_time=_NOW,
        prior_record_id=prior_record_id,
        supersession_reason=supersession_reason,
        provider_context_reference=provider_context_reference,
    )


def test_initial_kite_mapping_assesses_all_six_capabilities() -> None:
    service = _service()
    records = []

    for index, identifier in enumerate(CapabilityIdentifier, start=1):
        bundle = kite_capability_evidence(
            identifier,
            evidence_time=_NOW,
            adapter_revision=_REVISION,
        )
        request = CapabilityAssessmentRequest(
            assessment_id=f"initial-{index}",
            provider=KITE_PROVIDER,
            capability_identifier=identifier,
            requested_evidence_classes=bundle.evidence_classes,
            evidence_references=bundle.references,
            assessment_authority_reference=_AUTHORITY,
            compatibility_basis=KITE_API_BASIS,
            assessment_time=_NOW,
        )

        result = service.assess(
            request,
            bundle.evidence,
            bundle.limitations,
        )

        assert result.outcome.kind is CapabilityAssessmentOutcomeKind.COMPLETED
        assert result.record is not None
        assert result.record.provider_support is ProviderSupport.SUPPORTED
        actual_limitations = tuple(
            (limitation.category.value, limitation.description)
            for limitation in result.record.limitations
        )
        assert actual_limitations == _EXPECTED_KITE_LIMITATIONS[identifier]
        assert result.record.sdk_version_basis == (KITE_SDK_BASIS,)
        records.append(result.record)

    assert len(records) == 6
    assert sum(
        record.implementation_disposition
        is ImplementationDisposition.NOT_IMPLEMENTED
        for record in records
    ) == 5
    assert sum(
        record.implementation_disposition is ImplementationDisposition.DEFERRED
        for record in records
    ) == 1


@pytest.mark.parametrize(
    ("submitted_request", "expected_reason"),
    [
        (
            _request(
                (_evidence(),),
                capability_identifier="UNKNOWN_CAPABILITY",
            ),
            CapabilityAssessmentReason.UNKNOWN_CAPABILITY_IDENTIFIER,
        ),
        (
            _request((_evidence(),), authority=""),
            CapabilityAssessmentReason.MISSING_PREREQUISITE,
        ),
        (
            _request((_evidence(),), authority="UNAPPROVED_AUTHORITY"),
            CapabilityAssessmentReason.MISSING_PREREQUISITE,
        ),
        (
            _request(
                (_evidence(),),
                evidence_references=("https://unapproved.example/evidence",),
            ),
            CapabilityAssessmentReason.UNAPPROVED_EVIDENCE_SOURCE,
        ),
        (
            _request(
                (_evidence(),),
                requested_evidence_classes=(
                    EvidenceClass.AUTHORIZED_PROVIDER_ENDPOINT_EVIDENCE,
                ),
                provider_context_reference="opaque-context",
            ),
            CapabilityAssessmentReason.UNAUTHORIZED_EVIDENCE_CLASS,
        ),
    ],
)
def test_pre_boundary_failure_produces_outcome_only(
    submitted_request: CapabilityAssessmentRequest,
    expected_reason: CapabilityAssessmentReason,
) -> None:
    service = _service()

    result = service.assess(submitted_request, (_evidence(),))

    assert result.outcome.kind is CapabilityAssessmentOutcomeKind.NOT_PERFORMED
    assert result.outcome.reason is expected_reason
    assert result.record is None
    assert service.records() == ()
    assert service.audit_evidence()[-1].record_id is None


def test_sensitive_material_is_rejected_before_assessment_and_not_retained() -> None:
    sensitive = "access_token=do-not-retain"
    evidence = _evidence(source_reference=sensitive)
    request = _request((evidence,))
    service = _service()

    result = service.assess(request, (evidence,))
    rendered = repr((result, service.records(), service.audit_evidence()))

    assert result.outcome.kind is CapabilityAssessmentOutcomeKind.NOT_PERFORMED
    assert result.outcome.reason is CapabilityAssessmentReason.SENSITIVE_INPUT
    assert result.record is None
    assert sensitive not in rendered
    assert "do-not-retain" not in rendered


@pytest.mark.parametrize(
    ("provider_support", "disposition"),
    [
        (support, disposition)
        for support in ProviderSupport
        for disposition in ImplementationDisposition
    ],
)
def test_all_nine_support_and_implementation_combinations(
    provider_support: ProviderSupport,
    disposition: ImplementationDisposition,
) -> None:
    if provider_support is ProviderSupport.SUPPORTED:
        evidence = (_evidence(assertion=EvidenceAssertion.SUPPORTS),)
    elif provider_support is ProviderSupport.UNSUPPORTED:
        evidence = (_evidence(assertion=EvidenceAssertion.DOES_NOT_SUPPORT),)
    else:
        evidence = (
            _evidence(
                assertion=EvidenceAssertion.COMPATIBLE,
                evidence_class=(
                    EvidenceClass.APPROVED_ADAPTER_LOCKED_SDK_COMPATIBILITY
                ),
            ),
        )
    service = _service(disposition)

    result = service.assess(_request(evidence), evidence)

    assert result.record is not None
    assert result.record.provider_support is provider_support
    assert result.record.implementation_disposition is disposition
    if (
        provider_support is ProviderSupport.UNSUPPORTED
        and disposition is ImplementationDisposition.IMPLEMENTED
    ):
        assert (
            result.record.reason
            is CapabilityAssessmentReason.GOVERNANCE_CONFLICT
        )


def test_sdk_compatibility_alone_cannot_establish_provider_support() -> None:
    evidence = (
        _evidence(
            assertion=EvidenceAssertion.COMPATIBLE,
            evidence_class=(
                EvidenceClass.APPROVED_ADAPTER_LOCKED_SDK_COMPATIBILITY
            ),
        ),
    )

    result = _service().assess(_request(evidence), evidence)

    assert result.record is not None
    assert result.record.provider_support is ProviderSupport.UNDETERMINED
    assert result.record.reason is CapabilityAssessmentReason.EVIDENCE_ABSENT


@pytest.mark.parametrize(
    ("evidence", "reason"),
    [
        (
            (
                _evidence(
                    assertion=EvidenceAssertion.SUPPORTS,
                    currentness=EvidenceCurrentness.STALE,
                ),
            ),
            CapabilityAssessmentReason.EVIDENCE_STALE,
        ),
        (
            (
                _evidence(assertion=EvidenceAssertion.SUPPORTS),
                replace(
                    _evidence(assertion=EvidenceAssertion.DOES_NOT_SUPPORT),
                    evidence_id="evidence:contradiction",
                ),
            ),
            CapabilityAssessmentReason.EVIDENCE_CONFLICT,
        ),
    ],
)
def test_stale_or_conflicting_evidence_is_undetermined(
    evidence: tuple[CapabilityEvidence, ...],
    reason: CapabilityAssessmentReason,
) -> None:
    result = _service().assess(_request(evidence), evidence)

    assert result.record is not None
    assert result.record.provider_support is ProviderSupport.UNDETERMINED
    assert result.record.reason is reason


def test_activity_failure_produces_safe_record_with_both_determinations() -> None:
    evidence = (_evidence(provider="OTHER"),)
    request = _request(
        evidence,
        evidence_references=(evidence[0].source_reference,),
    )
    service = _service()

    result = service.assess(request, evidence)

    assert result.outcome.kind is CapabilityAssessmentOutcomeKind.FAILED
    assert result.outcome.reason is CapabilityAssessmentReason.EVIDENCE_MISMATCH
    assert result.record is not None
    assert result.record.provider_support is ProviderSupport.UNDETERMINED
    assert (
        result.record.implementation_disposition
        is ImplementationDisposition.NOT_IMPLEMENTED
    )
    assert result.record.evidence == ()
    assert service.audit_evidence()[-1].record_id == result.record.record_id


def test_reassessment_is_non_destructive_and_failure_preserves_current_record() -> None:
    evidence = (_evidence(),)
    service = _service()
    first = service.assess(_request(evidence), evidence)
    assert first.record is not None

    second_request = _request(
        evidence,
        assessment_id="assessment-002",
        prior_record_id=first.record.record_id,
        supersession_reason="Governed reassessment with current evidence.",
    )
    second = service.assess(second_request, evidence)
    assert second.record is not None
    assert second.record.supersedes_record_id == first.record.record_id
    assert second.record.supersession_reason is not None
    assert service.current_record(_CAPABILITY) == second.record
    assert service.gui_projection(first.record).superseded is True
    assert service.gui_projection(second.record).superseded is False

    mismatch = (_evidence(provider="OTHER"),)
    failed_request = _request(
        mismatch,
        assessment_id="assessment-003",
        prior_record_id=second.record.record_id,
        supersession_reason="Governed reassessment encountered a failure.",
    )
    failed = service.assess(failed_request, mismatch)

    assert failed.record is not None
    assert failed.record.outcome is CapabilityAssessmentOutcomeKind.FAILED
    assert failed.record.supersedes_record_id is None
    assert service.current_record(_CAPABILITY) == second.record
    assert service.records() == (first.record, second.record, failed.record)


def test_records_are_immutable_and_gui_projection_adds_no_authority() -> None:
    evidence = (_evidence(),)
    service = _service()
    result = service.assess(_request(evidence), evidence)
    assert result.record is not None

    with pytest.raises(FrozenInstanceError):
        result.record.provider_support = (  # type: ignore[misc]
            ProviderSupport.UNSUPPORTED
        )

    projection = service.gui_projection(result.record)
    assert projection.provider_support is ProviderSupport.SUPPORTED
    assert (
        projection.implementation_disposition
        is ImplementationDisposition.NOT_IMPLEMENTED
    )
    assert not hasattr(projection, "entitlement")
    assert not hasattr(projection, "availability")
    assert not hasattr(projection, "acquisition_authority")
    assert not hasattr(projection, "execute")


def test_provenance_and_audit_preserve_required_non_sensitive_meanings() -> None:
    evidence = (
        _evidence(),
        replace(
            _evidence(
                assertion=EvidenceAssertion.COMPATIBLE,
                evidence_class=(
                    EvidenceClass.APPROVED_ADAPTER_LOCKED_SDK_COMPATIBILITY
                ),
            ),
            evidence_id="evidence:sdk",
        ),
    )
    service = _service()

    result = service.assess(_request(evidence), evidence)

    assert result.record is not None
    provenance = result.record.provenance
    audit = service.audit_evidence()[-1]
    assert provenance.evidence_references == tuple(
        item.source_reference for item in evidence
    )
    assert provenance.evidence_classes == tuple(
        item.evidence_class for item in evidence
    )
    assert provenance.sdk_version_basis == (KITE_SDK_BASIS,)
    assert provenance.provider_support is ProviderSupport.SUPPORTED
    assert (
        provenance.implementation_disposition
        is ImplementationDisposition.NOT_IMPLEMENTED
    )
    assert audit.determination_rules_applied is True
    assert audit.sensitive_data_check_passed is True
    assert audit.supersession_established is False


def test_duplicate_assessment_identity_is_pre_boundary_not_performed() -> None:
    evidence = (_evidence(),)
    service = _service()
    first = service.assess(_request(evidence), evidence)
    duplicate = service.assess(_request(evidence), evidence)

    assert first.record is not None
    assert duplicate.record is None
    assert (
        duplicate.outcome.reason
        is CapabilityAssessmentReason.DUPLICATE_ASSESSMENT_ID
    )
    assert len(service.records()) == 1
