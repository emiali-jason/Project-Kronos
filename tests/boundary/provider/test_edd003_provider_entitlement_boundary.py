import ast
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

import pytest

from kronos.provider.adapters.kite.entitlement import (
    translate_kite_authenticated_profile,
)
from kronos.provider.models.entitlement import (
    AccountContinuity,
    EntitlementAssessmentProvenance,
    EntitlementAssessmentRequest,
    EntitlementAuditEvidence,
    EntitlementGuiProjection,
    EntitlementIndeterminate,
    ProviderEntitlementAssessmentRecord,
    ProviderEntitlementEvidence,
    ProviderEntitlementIdentifier,
    ProviderReportedEntitlement,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_PROVIDER_ROOT = _REPOSITORY_ROOT / "src" / "kronos" / "provider"
_ENTITLEMENT_MODULES = (
    _PROVIDER_ROOT / "contracts" / "entitlement.py",
    _PROVIDER_ROOT / "models" / "entitlement.py",
    _PROVIDER_ROOT / "services" / "entitlement.py",
    _PROVIDER_ROOT / "adapters" / "kite" / "entitlement.py",
)
_NEUTRAL_MODULES = _ENTITLEMENT_MODULES[:3]
_FORBIDDEN_DOMAINS = {
    "kronos.audit",
    "kronos.event",
    "kronos.execution",
    "kronos.instrument",
    "kronos.market",
    "kronos.observation",
    "kronos.portfolio",
    "kronos.risk",
    "kronos.validation",
}
_FORBIDDEN_OPERATIONS = {
    "connect",
    "historical_data",
    "instruments",
    "ltp",
    "margins",
    "ohlc",
    "orders",
    "place_order",
    "positions",
    "profile",
    "quote",
    "subscribe",
}
_PROHIBITED_NEUTRAL_FIELDS = {
    "access_token",
    "api_key",
    "api_secret",
    "authorization_header",
    "avatar",
    "broker",
    "checksum",
    "email",
    "profile",
    "raw_payload",
    "refresh_token",
    "request_token",
    "sdk_client",
    "sdk_exception",
    "user_id",
    "user_name",
}


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text())


def _imports(path: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def test_edd003_neutral_modules_have_no_kite_sdk_or_business_imports() -> None:
    for module in _NEUTRAL_MODULES:
        imported = _imports(module)
        assert _FORBIDDEN_DOMAINS.isdisjoint(imported)
        assert not any(
            name == "kiteconnect" or name.startswith("kiteconnect.")
            for name in imported
        )
        assert not any(
            name.startswith("kronos.provider.adapters.kite")
            for name in imported
        )


def test_edd003_implementation_invokes_no_provider_endpoint() -> None:
    invoked = {
        node.func.attr
        for module in _ENTITLEMENT_MODULES
        for node in ast.walk(_tree(module))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert _FORBIDDEN_OPERATIONS.isdisjoint(invoked)


def test_only_kite_adapter_names_provider_profile_fields() -> None:
    provider_fields = {"exchanges", "products", "order_types", "user_id"}

    for module in _NEUTRAL_MODULES:
        constants = {
            node.value
            for node in ast.walk(_tree(module))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert provider_fields.isdisjoint(constants)


def test_neutral_representations_expose_no_sensitive_or_sdk_fields() -> None:
    model_types = (
        EntitlementAssessmentRequest,
        ProviderEntitlementEvidence,
        ProviderReportedEntitlement,
        EntitlementIndeterminate,
        EntitlementAssessmentProvenance,
        ProviderEntitlementAssessmentRecord,
        EntitlementAuditEvidence,
        EntitlementGuiProjection,
    )
    exposed = {
        field.name
        for model_type in model_types
        for field in fields(model_type)
    }

    assert _PROHIBITED_NEUTRAL_FIELDS.isdisjoint(exposed)


def test_edd003_does_not_import_or_reproduce_capability_assessment() -> None:
    for module in _ENTITLEMENT_MODULES:
        imported = _imports(module)
        assert "kronos.provider.models.capability" not in imported
        assert "kronos.provider.services.capability" not in imported
        assert "kronos.provider.contracts.capability" not in imported
        assert "kronos.provider.adapters.kite.capability" not in imported


def test_adapter_has_only_the_three_approved_entitlement_mappings() -> None:
    adapter = _ENTITLEMENT_MODULES[-1].read_text()

    assert adapter.count('"exchanges"') == 1
    assert adapter.count('"products"') == 1
    assert adapter.count('"order_types"') == 1


@pytest.mark.parametrize(
    ("field", "value", "expected_identifier"),
    [
        ("exchanges", "NSE", ProviderEntitlementIdentifier.EXCHANGE),
        ("products", "CNC", ProviderEntitlementIdentifier.PRODUCT),
        ("order_types", "MARKET", ProviderEntitlementIdentifier.ORDER_TYPE),
    ],
)
def test_provider_boundary_behaviorally_enforces_exact_mapping(
    field: str,
    value: str,
    expected_identifier: ProviderEntitlementIdentifier,
) -> None:
    profile: dict[str, object] = {
        "user_id": "adapter-private-account",
        "exchanges": (),
        "products": (),
        "order_types": (),
        "additional_category": ("MUST_NOT_CROSS",),
    }
    profile[field] = (value,)

    evidence = translate_kite_authenticated_profile(
        profile,
        expected_account_context_reference="protected-account-reference",
        account_continuity_resolver=lambda _raw, _expected: (
            AccountContinuity.MATCHED
        ),
        evidence_time=datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc),
        adapter_revision="boundary-test-revision",
    )

    assert tuple(
        (item.identifier, item.reported_value)
        for item in evidence.items
    ) == ((expected_identifier, value),)
    assert "MUST_NOT_CROSS" not in repr(evidence)


def test_provider_boundary_classifies_malformed_values_without_leakage() -> None:
    evidence = translate_kite_authenticated_profile(
        {
            "user_id": "adapter-private-account",
            "exchanges": ("NSE", object()),
            "products": (),
            "order_types": (),
        },
        expected_account_context_reference="protected-account-reference",
        account_continuity_resolver=lambda _raw, _expected: (
            AccountContinuity.MATCHED
        ),
        evidence_time=datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc),
        adapter_revision="boundary-test-revision",
    )

    assert tuple(
        (item.identifier, item.reported_value)
        for item in evidence.items
    ) == ((ProviderEntitlementIdentifier.EXCHANGE, "NSE"),)
    assert tuple(issue.identifier for issue in evidence.issues) == (
        ProviderEntitlementIdentifier.EXCHANGE,
    )
