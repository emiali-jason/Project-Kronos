"""Kite-local authenticated-profile translation for canonical EDD-003."""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Final

from kronos.provider.models.entitlement import (
    AccountContinuity,
    EntitlementAssessmentReason,
    EntitlementEvidenceIssue,
    ProviderEntitlementEvidence,
    ProviderEntitlementEvidenceItem,
    ProviderEntitlementIdentifier,
)


KITE_PROVIDER: Final = "KITE"
KITE_PROFILE_EVIDENCE_SOURCE: Final = (
    "https://kite.trade/docs/connect/v3/user/#user-profile"
)
KITE_API_BASIS: Final = "KITE_CONNECT_API_V3_USER_PROFILE"
KITE_SDK_BASIS: Final = "kiteconnect==5.2.0"

_PROFILE_FIELDS = {
    ProviderEntitlementIdentifier.EXCHANGE: "exchanges",
    ProviderEntitlementIdentifier.PRODUCT: "products",
    ProviderEntitlementIdentifier.ORDER_TYPE: "order_types",
}
_APPROVED_VOCABULARY = {
    ProviderEntitlementIdentifier.EXCHANGE: frozenset(
        {"NSE", "NFO", "BFO", "CDS", "BSE", "MCX", "BCD", "MF"}
    ),
    ProviderEntitlementIdentifier.PRODUCT: frozenset(
        {"CNC", "NRML", "MIS", "BO", "CO"}
    ),
    ProviderEntitlementIdentifier.ORDER_TYPE: frozenset(
        {"MARKET", "LIMIT", "SL", "SL-M"}
    ),
}
_SENSITIVE_PROFILE_FIELDS = frozenset(
    {
        "api_key",
        "api_secret",
        "request_token",
        "access_token",
        "public_token",
        "refresh_token",
        "enctoken",
        "authorization",
        "authorization_header",
        "checksum",
    }
)
_SENSITIVE_VALUE_MARKERS = (
    "api_secret",
    "request_token",
    "access_token",
    "refresh_token",
    "authorization:",
    "bearer ",
    "checksum",
)

AccountContinuityResolver = Callable[[str, str], AccountContinuity]


def translate_kite_authenticated_profile(
    profile: object,
    *,
    expected_account_context_reference: str,
    account_continuity_resolver: AccountContinuityResolver,
    evidence_time: datetime,
    adapter_revision: str,
) -> ProviderEntitlementEvidence:
    """Minimize one raw Kite profile entirely inside the adapter boundary."""

    if evidence_time.utcoffset() is None:
        raise ValueError("evidence time must be timezone-aware")
    if not expected_account_context_reference.strip():
        raise ValueError("expected account context reference is required")
    if not adapter_revision.strip():
        raise ValueError("adapter revision is required")
    if not isinstance(profile, Mapping):
        return _failed_evidence(
            evidence_time,
            adapter_revision,
            EntitlementAssessmentReason.MALFORMED_PROFILE,
        )
    if _contains_sensitive_profile_field(profile):
        return _failed_evidence(
            evidence_time,
            adapter_revision,
            EntitlementAssessmentReason.SECURITY_BOUNDARY_VIOLATION,
        )

    account_continuity = _account_continuity(
        profile.get("user_id"),
        expected_account_context_reference,
        account_continuity_resolver,
    )
    items: list[ProviderEntitlementEvidenceItem] = []
    issues: list[EntitlementEvidenceIssue] = []
    security_violation = False

    for identifier, field in _PROFILE_FIELDS.items():
        raw_values = profile.get(field)
        if raw_values is None:
            issues.append(_issue(identifier, evidence_time))
            continue
        if (
            not isinstance(raw_values, Sequence)
            or isinstance(raw_values, (str, bytes, bytearray))
        ):
            issues.append(
                _issue(
                    identifier,
                    evidence_time,
                    EntitlementAssessmentReason.MALFORMED_PROFILE,
                )
            )
            continue
        for raw_value in raw_values:
            if not isinstance(raw_value, str) or not raw_value.strip():
                issues.append(
                    _issue(
                        identifier,
                        evidence_time,
                        EntitlementAssessmentReason.MALFORMED_PROFILE,
                    )
                )
                continue
            value = raw_value.strip()
            if _contains_sensitive_material(value):
                security_violation = True
                continue
            if value not in _APPROVED_VOCABULARY[identifier]:
                issues.append(
                    _issue(
                        identifier,
                        evidence_time,
                        EntitlementAssessmentReason.UNRECOGNIZED_PROVIDER_VOCABULARY,
                    )
                )
                continue
            items.append(
                ProviderEntitlementEvidenceItem(
                    identifier=identifier,
                    reported_value=value,
                )
            )

    del profile
    if security_violation:
        return _failed_evidence(
            evidence_time,
            adapter_revision,
            EntitlementAssessmentReason.SECURITY_BOUNDARY_VIOLATION,
        )

    return ProviderEntitlementEvidence(
        provider=KITE_PROVIDER,
        evidence_source_reference=KITE_PROFILE_EVIDENCE_SOURCE,
        evidence_time=evidence_time,
        account_continuity=account_continuity,
        items=tuple(items),
        issues=tuple(issues),
        provider_api_basis=KITE_API_BASIS,
        sdk_version_basis=KITE_SDK_BASIS,
        adapter_revision_basis=adapter_revision,
        excluded_fields_disposed=True,
        security_check_passed=True,
    )


def _account_continuity(
    raw_user_id: object,
    expected_reference: str,
    resolver: AccountContinuityResolver,
) -> AccountContinuity:
    if not isinstance(raw_user_id, str) or not raw_user_id:
        return AccountContinuity.UNDETERMINED
    try:
        result = resolver(raw_user_id, expected_reference)
    except Exception:
        return AccountContinuity.UNDETERMINED
    finally:
        del raw_user_id
    return (
        result
        if isinstance(result, AccountContinuity)
        else AccountContinuity.UNDETERMINED
    )


def _issue(
    identifier: ProviderEntitlementIdentifier,
    evidence_time: datetime,
    cause: EntitlementAssessmentReason = (
        EntitlementAssessmentReason.INSUFFICIENT_EVIDENCE
    ),
) -> EntitlementEvidenceIssue:
    return EntitlementEvidenceIssue(
        identifier=identifier,
        cause=cause,
        evidence_source_reference=KITE_PROFILE_EVIDENCE_SOURCE,
        evidence_time=evidence_time,
    )


def _failed_evidence(
    evidence_time: datetime,
    adapter_revision: str,
    reason: EntitlementAssessmentReason,
) -> ProviderEntitlementEvidence:
    return ProviderEntitlementEvidence(
        provider=KITE_PROVIDER,
        evidence_source_reference=KITE_PROFILE_EVIDENCE_SOURCE,
        evidence_time=evidence_time,
        account_continuity=AccountContinuity.UNDETERMINED,
        items=(),
        issues=(),
        provider_api_basis=KITE_API_BASIS,
        sdk_version_basis=KITE_SDK_BASIS,
        adapter_revision_basis=adapter_revision,
        excluded_fields_disposed=True,
        security_check_passed=(
            reason is not EntitlementAssessmentReason.SECURITY_BOUNDARY_VIOLATION
        ),
        fatal_reason=reason,
    )


def _contains_sensitive_material(value: str) -> bool:
    normalized = value.casefold().replace("-", "_")
    return any(marker in normalized for marker in _SENSITIVE_VALUE_MARKERS)


def _contains_sensitive_profile_field(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if (
                isinstance(key, str)
                and key.casefold().replace("-", "_")
                in _SENSITIVE_PROFILE_FIELDS
            ):
                return True
            if _contains_sensitive_profile_field(nested):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return any(_contains_sensitive_profile_field(item) for item in value)
    return False
