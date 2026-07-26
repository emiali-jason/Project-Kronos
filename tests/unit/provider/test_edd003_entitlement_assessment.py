from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from kronos.provider.adapters.kite.entitlement import (
    KITE_PROFILE_EVIDENCE_SOURCE,
    KITE_PROVIDER,
    translate_kite_authenticated_profile,
)
from kronos.provider.models.context import (
    ContextReuseEligibility,
    ContextValidity,
)
from kronos.provider.models.entitlement import (
    AccountContinuity,
    EntitlementAssessmentOutcomeKind,
    EntitlementAssessmentReason,
    EntitlementAssessmentRequest,
    EntitlementCurrentness,
    ProviderEntitlementEvidence,
    ProviderEntitlementIdentifier,
)
from kronos.provider.services.entitlement import (
    ProviderEntitlementAssessmentService,
)


_NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
_AUTHORITY = "EDD-003:IMPLEMENTATION_AUTHORIZATION"
_CONFIGURATION_CONTEXT = "configuration-approval:001"
_ACCOUNT_REFERENCE = "protected-account:001"
_CONTEXT_REFERENCE = "provider-context:001"
_ADAPTER_REVISION = "edd003-test-revision"


def _account_continuity(
    raw_user_id: str,
    expected_reference: str,
) -> AccountContinuity:
    if raw_user_id == "AB1234" and expected_reference == _ACCOUNT_REFERENCE:
        return AccountContinuity.MATCHED
    return AccountContinuity.MISMATCHED


def _service() -> ProviderEntitlementAssessmentService:
    return ProviderEntitlementAssessmentService(
        provider=KITE_PROVIDER,
        approved_assessment_authorities=frozenset({_AUTHORITY}),
        approved_evidence_sources=frozenset(
            {KITE_PROFILE_EVIDENCE_SOURCE}
        ),
        approved_configuration_contexts=frozenset(
            {_CONFIGURATION_CONTEXT}
        ),
    )


def _request(
    *,
    assessment_id: str = "entitlement-assessment-001",
    provider: str = KITE_PROVIDER,
    context_validity: ContextValidity = ContextValidity.VALID,
    reuse: ContextReuseEligibility = ContextReuseEligibility.ELIGIBLE,
    prior_record_id: str | None = None,
    supersession_reason: str | None = None,
    assessment_time: datetime = _NOW,
) -> EntitlementAssessmentRequest:
    return EntitlementAssessmentRequest(
        assessment_id=assessment_id,
        provider=provider,
        provider_context_reference=_CONTEXT_REFERENCE,
        context_validity=context_validity,
        context_reuse_eligibility=reuse,
        expected_account_context_reference=_ACCOUNT_REFERENCE,
        entitlement_identifiers=tuple(ProviderEntitlementIdentifier),
        evidence_source_reference=KITE_PROFILE_EVIDENCE_SOURCE,
        assessment_authority_reference=_AUTHORITY,
        configuration_approval_context_reference=_CONFIGURATION_CONTEXT,
        assessment_time=assessment_time,
        authorization_context_reference="authorization-context:001",
        operating_environment_reference="environment:testing",
        lifecycle_boundary_reference="lifecycle:provider-context",
        sensitive_classification_reference="classification:sensitive",
        security_containment_available=True,
        prior_record_id=prior_record_id,
        supersession_reason=supersession_reason,
    )


def _profile(
    *,
    exchanges: object = ("NSE", "MCX"),
    products: object = ("CNC", "NRML"),
    order_types: object = ("MARKET", "LIMIT"),
) -> dict[str, object]:
    return {
        "user_id": "AB1234",
        "user_name": "Excluded Name",
        "user_shortname": "Excluded",
        "email": "excluded@example.com",
        "avatar_url": "https://example.com/avatar.png",
        "broker": "ZERODHA",
        "user_type": "individual",
        "meta": {"demat_consent": "physical"},
        "exchanges": exchanges,
        "products": products,
        "order_types": order_types,
    }


def _evidence(profile: object):
    return translate_kite_authenticated_profile(
        profile,
        expected_account_context_reference=_ACCOUNT_REFERENCE,
        account_continuity_resolver=_account_continuity,
        evidence_time=_NOW,
        adapter_revision=_ADAPTER_REVISION,
    )


def test_successful_assessment_creates_positive_provider_entitlements() -> None:
    service = _service()

    result = service.assess(_request(), _evidence(_profile()))

    assert result.outcome.kind is EntitlementAssessmentOutcomeKind.COMPLETED
    assert result.record is not None
    assert result.record.account_continuity is AccountContinuity.MATCHED
    assert result.record.currentness is EntitlementCurrentness.CURRENT
    assert len(result.record.entitlements) == 6
    assert result.record.indeterminate == ()
    assert {
        (item.identifier, item.reported_value)
        for item in result.record.entitlements
    } == {
        (ProviderEntitlementIdentifier.EXCHANGE, "NSE"),
        (ProviderEntitlementIdentifier.EXCHANGE, "MCX"),
        (ProviderEntitlementIdentifier.PRODUCT, "CNC"),
        (ProviderEntitlementIdentifier.PRODUCT, "NRML"),
        (ProviderEntitlementIdentifier.ORDER_TYPE, "MARKET"),
        (ProviderEntitlementIdentifier.ORDER_TYPE, "LIMIT"),
    }
    assert service.current_record() is result.record
    assert len(service.audit_evidence()) == 1


def test_valid_empty_entitlement_categories_complete_without_denial() -> None:
    service = _service()

    result = service.assess(
        _request(),
        _evidence(_profile(exchanges=(), products=(), order_types=())),
    )

    assert result.outcome.kind is EntitlementAssessmentOutcomeKind.COMPLETED
    assert result.outcome.reason is None
    assert result.record is not None
    assert result.record.entitlements == ()
    assert result.record.indeterminate == ()
    assert "DENIED" not in repr(result)


def test_completed_assessment_preserves_positive_and_indeterminate_entries() -> None:
    service = _service()
    evidence = _evidence(
        _profile(
            exchanges=("NSE",),
            products=("UNRECOGNIZED_PRODUCT",),
            order_types=None,
        )
    )

    result = service.assess(_request(), evidence)

    assert result.outcome.kind is EntitlementAssessmentOutcomeKind.COMPLETED
    assert result.record is not None
    assert tuple(
        (item.identifier, item.reported_value)
        for item in result.record.entitlements
    ) == ((ProviderEntitlementIdentifier.EXCHANGE, "NSE"),)
    assert {
        (item.identifier, item.cause)
        for item in result.record.indeterminate
    } == {
        (
            ProviderEntitlementIdentifier.PRODUCT,
            EntitlementAssessmentReason.UNRECOGNIZED_PROVIDER_VOCABULARY,
        ),
        (
            ProviderEntitlementIdentifier.ORDER_TYPE,
            EntitlementAssessmentReason.INSUFFICIENT_EVIDENCE,
        ),
    }
    assert "UNRECOGNIZED_PRODUCT" not in repr(result)


@pytest.mark.parametrize(
    ("request_change", "reason"),
    [
        (
            {"assessment_id": ""},
            EntitlementAssessmentReason.INVALID_REQUEST,
        ),
        (
            {"provider_context_reference": ""},
            EntitlementAssessmentReason.CONTEXT_MISSING,
        ),
        (
            {"context_validity": ContextValidity.INVALID},
            EntitlementAssessmentReason.CONTEXT_INVALID,
        ),
        (
            {"context_reuse_eligibility": ContextReuseEligibility.INELIGIBLE},
            EntitlementAssessmentReason.CONTEXT_REUSE_INELIGIBLE,
        ),
        (
            {"context_reuse_eligibility": None},
            EntitlementAssessmentReason.CONTEXT_REUSE_INELIGIBLE,
        ),
        (
            {"provider": "OTHER"},
            EntitlementAssessmentReason.PROVIDER_MISMATCH,
        ),
        (
            {"expected_account_context_reference": ""},
            EntitlementAssessmentReason.EXPECTED_ACCOUNT_CONTEXT_MISSING,
        ),
        (
            {"configuration_approval_context_reference": "config:unapproved"},
            EntitlementAssessmentReason.CONFIGURATION_CONTEXT_MISMATCH,
        ),
        (
            {"evidence_source_reference": "evidence:unapproved"},
            EntitlementAssessmentReason.UNAPPROVED_EVIDENCE_SOURCE,
        ),
        (
            {"assessment_authority_reference": "authority:missing"},
            EntitlementAssessmentReason.MISSING_ASSESSMENT_AUTHORITY,
        ),
        (
            {"assessment_time": datetime(2026, 7, 26, 12, 0)},
            EntitlementAssessmentReason.INVALID_REQUEST,
        ),
        (
            {"assessment_time": None},
            EntitlementAssessmentReason.INVALID_REQUEST,
        ),
        (
            {"authorization_context_reference": ""},
            EntitlementAssessmentReason.INVALID_REQUEST,
        ),
        (
            {"operating_environment_reference": ""},
            EntitlementAssessmentReason.INVALID_REQUEST,
        ),
        (
            {"lifecycle_boundary_reference": ""},
            EntitlementAssessmentReason.INVALID_REQUEST,
        ),
        (
            {"sensitive_classification_reference": ""},
            EntitlementAssessmentReason.INVALID_REQUEST,
        ),
        (
            {"security_containment_available": False},
            EntitlementAssessmentReason.SECURITY_CONTAINMENT_UNAVAILABLE,
        ),
    ],
)
def test_each_pre_boundary_failure_produces_only_not_performed(
    request_change: dict[str, object],
    reason: EntitlementAssessmentReason,
) -> None:
    service = _service()
    submitted_request = replace(_request(), **request_change)

    result = service.assess(submitted_request, _evidence(_profile()))

    assert result.outcome.kind is EntitlementAssessmentOutcomeKind.NOT_PERFORMED
    assert result.outcome.reason is reason
    assert result.record is None
    assert service.records() == ()
    audit = service.audit_evidence()
    assert len(audit) == 1
    assert audit[0].outcome is EntitlementAssessmentOutcomeKind.NOT_PERFORMED
    assert audit[0].record_id is None
    assert audit[0].positive_entitlement_count == 0
    assert audit[0].indeterminate_count == 0


def test_duplicate_assessment_identity_is_pre_boundary_failure() -> None:
    service = _service()
    first = service.assess(_request(), _evidence(_profile()))
    record_count = len(service.records())

    duplicate = service.assess(_request(), _evidence(_profile()))

    assert first.outcome.kind is EntitlementAssessmentOutcomeKind.COMPLETED
    assert duplicate.outcome.kind is EntitlementAssessmentOutcomeKind.NOT_PERFORMED
    assert (
        duplicate.outcome.reason
        is EntitlementAssessmentReason.DUPLICATE_ASSESSMENT_ID
    )
    assert duplicate.record is None
    assert len(service.records()) == record_count
    assert service.audit_evidence()[-1].record_id is None


def test_activity_failure_creates_one_safe_indeterminate_record() -> None:
    service = _service()

    result = service.assess(_request(), None)

    assert result.outcome.kind is EntitlementAssessmentOutcomeKind.FAILED
    assert result.outcome.reason is EntitlementAssessmentReason.PROFILE_UNAVAILABLE
    assert result.record is not None
    assert result.record.entitlements == ()
    assert len(result.record.indeterminate) == 1
    assert (
        result.record.indeterminate[0].cause
        is EntitlementAssessmentReason.PROFILE_UNAVAILABLE
    )
    assert len(service.records()) == 1


def test_account_continuity_mismatch_fails_without_positive_entitlement() -> None:
    service = _service()
    evidence = translate_kite_authenticated_profile(
        _profile(),
        expected_account_context_reference=_ACCOUNT_REFERENCE,
        account_continuity_resolver=lambda _raw, _expected: (
            AccountContinuity.MISMATCHED
        ),
        evidence_time=_NOW,
        adapter_revision=_ADAPTER_REVISION,
    )

    result = service.assess(_request(), evidence)

    assert result.outcome.kind is EntitlementAssessmentOutcomeKind.FAILED
    assert (
        result.outcome.reason
        is EntitlementAssessmentReason.ACCOUNT_CONTINUITY_MISMATCH
    )
    assert result.record is not None
    assert result.record.entitlements == ()


def test_account_continuity_undetermined_fails_without_entitlement() -> None:
    service = _service()
    profile = _profile()
    profile.pop("user_id")

    result = service.assess(_request(), _evidence(profile))

    assert result.outcome.kind is EntitlementAssessmentOutcomeKind.FAILED
    assert (
        result.outcome.reason
        is EntitlementAssessmentReason.ACCOUNT_CONTINUITY_UNDETERMINED
    )
    assert result.record is not None
    assert result.record.entitlements == ()
    assert len(result.record.indeterminate) == 1


def test_malformed_category_value_becomes_bounded_indeterminate() -> None:
    result = _service().assess(
        _request(),
        _evidence(
            _profile(
                exchanges=("NSE", 17),
                products=(),
                order_types=(),
            )
        ),
    )

    assert result.outcome.kind is EntitlementAssessmentOutcomeKind.COMPLETED
    assert result.record is not None
    assert tuple(
        (item.identifier, item.reported_value)
        for item in result.record.entitlements
    ) == ((ProviderEntitlementIdentifier.EXCHANGE, "NSE"),)
    assert tuple(
        (item.identifier, item.cause)
        for item in result.record.indeterminate
    ) == (
        (
            ProviderEntitlementIdentifier.EXCHANGE,
            EntitlementAssessmentReason.MALFORMED_PROFILE,
        ),
    )


@pytest.mark.parametrize(
    ("field", "value", "identifier"),
    [
        ("exchanges", "NSE", ProviderEntitlementIdentifier.EXCHANGE),
        ("products", "CNC", ProviderEntitlementIdentifier.PRODUCT),
        ("order_types", "MARKET", ProviderEntitlementIdentifier.ORDER_TYPE),
    ],
)
def test_exact_entitlement_mapping_matrix_is_behavioral(
    field: str,
    value: str,
    identifier: ProviderEntitlementIdentifier,
) -> None:
    profile = _profile(exchanges=(), products=(), order_types=())
    profile[field] = (value,)
    profile["unexpected_entitlement_category"] = ("MUST_NOT_MAP",)

    result = _service().assess(_request(), _evidence(profile))

    assert result.outcome.kind is EntitlementAssessmentOutcomeKind.COMPLETED
    assert result.record is not None
    assert tuple(
        (item.identifier, item.reported_value)
        for item in result.record.entitlements
    ) == ((identifier, value),)
    assert "MUST_NOT_MAP" not in repr(result)


def test_excluded_field_disposal_failure_creates_one_safe_record() -> None:
    evidence = replace(_evidence(_profile()), excluded_fields_disposed=False)

    result = _service().assess(_request(), evidence)

    assert result.outcome.kind is EntitlementAssessmentOutcomeKind.FAILED
    assert (
        result.outcome.reason
        is EntitlementAssessmentReason.EXCLUDED_FIELD_DISPOSAL_FAILURE
    )
    assert result.record is not None
    assert result.record.entitlements == ()
    assert len(result.record.indeterminate) == 1


@pytest.mark.parametrize(
    "mismatched_evidence",
    [
        replace(_evidence(_profile()), provider="OTHER"),
        replace(
            _evidence(_profile()),
            evidence_source_reference="evidence:mismatched",
        ),
        replace(
            _evidence(_profile()),
            evidence_time=_NOW + timedelta(seconds=1),
        ),
    ],
)
def test_evidence_consistency_failure_does_not_preserve_untrusted_provenance(
    mismatched_evidence: ProviderEntitlementEvidence,
) -> None:
    result = _service().assess(_request(), mismatched_evidence)

    assert result.outcome.kind is EntitlementAssessmentOutcomeKind.FAILED
    assert result.outcome.reason is EntitlementAssessmentReason.EVIDENCE_MISMATCH
    assert result.record is not None
    assert result.record.provenance.evidence_time is None
    assert result.record.provenance.provider_api_basis == "NOT_ESTABLISHED"
    assert result.record.provenance.sdk_version_basis == "NOT_ESTABLISHED"
    assert result.record.provenance.adapter_revision_basis == "NOT_ESTABLISHED"


def test_failed_record_preserves_accepted_non_sensitive_provenance() -> None:
    evidence = _evidence({**_profile(), "access_token": "must-not-survive"})

    result = _service().assess(_request(), evidence)

    assert result.outcome.kind is EntitlementAssessmentOutcomeKind.FAILED
    assert (
        result.outcome.reason
        is EntitlementAssessmentReason.SECURITY_BOUNDARY_VIOLATION
    )
    assert result.record is not None
    assert result.record.evidence_time == _NOW
    assert result.record.provenance.evidence_time == _NOW
    assert result.record.provenance.provider_api_basis == (
        "KITE_CONNECT_API_V3_USER_PROFILE"
    )
    assert result.record.provenance.sdk_version_basis == "kiteconnect==5.2.0"
    assert result.record.provenance.adapter_revision_basis == _ADAPTER_REVISION
    assert "must-not-survive" not in repr(result)


def test_duplicate_explicit_values_create_one_semantic_entitlement() -> None:
    result = _service().assess(
        _request(),
        _evidence(
            _profile(
                exchanges=("NSE", "NSE"),
                products=(),
                order_types=(),
            )
        ),
    )

    assert result.record is not None
    assert tuple(
        (item.identifier, item.reported_value)
        for item in result.record.entitlements
    ) == ((ProviderEntitlementIdentifier.EXCHANGE, "NSE"),)


def test_record_and_nested_representations_are_immutable() -> None:
    result = _service().assess(_request(), _evidence(_profile()))
    assert result.record is not None

    with pytest.raises(FrozenInstanceError):
        result.record.currentness = EntitlementCurrentness.STALE  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.record.entitlements[0].reported_value = "BSE"  # type: ignore[misc]


def test_reassessment_creates_new_record_and_non_destructive_supersession() -> None:
    service = _service()
    first = service.assess(_request(), _evidence(_profile()))
    assert first.record is not None
    snapshot = repr(first.record)

    second_request = _request(
        assessment_id="entitlement-assessment-002",
        prior_record_id=first.record.record_id,
        supersession_reason="governed reassessment",
        assessment_time=_NOW + timedelta(minutes=1),
    )
    second_evidence = translate_kite_authenticated_profile(
        _profile(exchanges=("BSE",), products=(), order_types=()),
        expected_account_context_reference=_ACCOUNT_REFERENCE,
        account_continuity_resolver=_account_continuity,
        evidence_time=_NOW + timedelta(minutes=1),
        adapter_revision=_ADAPTER_REVISION,
    )
    second = service.assess(second_request, second_evidence)

    assert second.outcome.kind is EntitlementAssessmentOutcomeKind.COMPLETED
    assert second.record is not None
    assert second.record is not first.record
    assert second.record.supersedes_record_id == first.record.record_id
    assert (
        service.record_currentness(first.record.record_id)
        is EntitlementCurrentness.SUPERSEDED
    )
    assert service.current_record() is second.record
    assert repr(first.record) == snapshot


def test_failed_reassessment_does_not_supersede_prior_record() -> None:
    service = _service()
    first = service.assess(_request(), _evidence(_profile()))
    assert first.record is not None
    failed_request = _request(
        assessment_id="entitlement-assessment-002",
        prior_record_id=first.record.record_id,
        supersession_reason="governed reassessment",
        assessment_time=_NOW + timedelta(minutes=1),
    )

    failed = service.assess(failed_request, None)

    assert failed.outcome.kind is EntitlementAssessmentOutcomeKind.FAILED
    assert failed.record is not None
    assert failed.record.supersedes_record_id is None
    assert (
        service.record_currentness(first.record.record_id)
        is EntitlementCurrentness.CURRENT
    )
    assert service.current_record() is first.record


def test_context_invalidation_makes_record_stale_without_mutation() -> None:
    service = _service()
    result = service.assess(_request(), _evidence(_profile()))
    assert result.record is not None
    snapshot = repr(result.record)

    service.context_became_ineligible(_CONTEXT_REFERENCE)

    assert (
        service.record_currentness(result.record.record_id)
        is EntitlementCurrentness.STALE
    )
    assert service.current_record() is None
    assert repr(result.record) == snapshot


def test_security_violation_discards_payload_and_fails_closed() -> None:
    service = _service()
    secret = "must-not-survive"
    raw = _profile()
    raw["access_token"] = secret

    evidence = _evidence(raw)
    result = service.assess(_request(), evidence)
    rendered = repr((evidence, result, service.audit_evidence()))

    assert result.outcome.kind is EntitlementAssessmentOutcomeKind.FAILED
    assert (
        result.outcome.reason
        is EntitlementAssessmentReason.SECURITY_BOUNDARY_VIOLATION
    )
    assert result.record is not None
    assert result.record.entitlements == ()
    assert secret not in rendered
    assert "access_token" not in rendered


def test_nested_authentication_material_is_detected_and_discarded() -> None:
    raw = _profile()
    raw["unexpected"] = {"authorization-header": "must-not-survive"}

    evidence = _evidence(raw)
    result = _service().assess(_request(), evidence)

    assert result.outcome.kind is EntitlementAssessmentOutcomeKind.FAILED
    assert (
        result.outcome.reason
        is EntitlementAssessmentReason.SECURITY_BOUNDARY_VIOLATION
    )
    assert "must-not-survive" not in repr((evidence, result))


def test_account_identity_and_profile_metadata_do_not_cross_boundary() -> None:
    evidence = _evidence(_profile())
    rendered = repr(evidence)

    assert evidence.account_continuity is AccountContinuity.MATCHED
    for excluded in (
        "AB1234",
        "Excluded Name",
        "excluded@example.com",
        "avatar.png",
        "ZERODHA",
        "individual",
        "demat_consent",
    ):
        assert excluded not in rendered


def test_gui_projection_is_read_only_and_uses_derived_currentness() -> None:
    service = _service()
    result = service.assess(_request(), _evidence(_profile()))
    assert result.record is not None
    service.context_became_ineligible(_CONTEXT_REFERENCE)

    projection = service.gui_projection(result.record)

    assert projection.currentness is EntitlementCurrentness.STALE
    assert all(
        item.currentness is EntitlementCurrentness.STALE
        for item in projection.entitlements
    )


def test_wrong_identifier_family_is_pre_boundary_failure() -> None:
    request = replace(
        _request(),
        entitlement_identifiers=(
            ProviderEntitlementIdentifier.EXCHANGE,
            ProviderEntitlementIdentifier.PRODUCT,
        ),
    )

    result = _service().assess(request, _evidence(_profile()))

    assert result.outcome.kind is EntitlementAssessmentOutcomeKind.NOT_PERFORMED
    assert (
        result.outcome.reason
        is EntitlementAssessmentReason.IDENTIFIER_FAMILY_MISMATCH
    )
    assert result.record is None
