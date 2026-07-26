import ast
from dataclasses import fields
from pathlib import Path

from kronos.provider.models.capability import (
    CapabilityAssessmentRecord,
    CapabilityAssessmentRequest,
    CapabilityAuditEvidence,
    CapabilityEvidence,
    CapabilityGuiProjection,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_PROVIDER_ROOT = _REPOSITORY_ROOT / "src" / "kronos" / "provider"
_CAPABILITY_MODULES = (
    _PROVIDER_ROOT / "contracts" / "capability.py",
    _PROVIDER_ROOT / "models" / "capability.py",
    _PROVIDER_ROOT / "services" / "capability.py",
    _PROVIDER_ROOT / "adapters" / "kite" / "capability.py",
)
_FORBIDDEN_PROVIDER_OPERATIONS = {
    "connect",
    "historical_data",
    "instruments",
    "ltp",
    "ohlc",
    "profile",
    "quote",
    "subscribe",
}
_FORBIDDEN_DOMAINS = {
    "kronos.execution",
    "kronos.instrument",
    "kronos.observation",
    "kronos.portfolio",
    "kronos.risk",
    "kronos.validation",
}
_SENSITIVE_OR_OUT_OF_SCOPE_FIELDS = {
    "access_token",
    "account_entitlement",
    "acquisition_authority",
    "api_secret",
    "authorization_header",
    "dataset_permission",
    "request_token",
    "sdk_client",
    "sdk_exception",
}


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text())


def test_edd002_implementation_stays_inside_provider() -> None:
    for module in _CAPABILITY_MODULES:
        imported = set()
        for node in ast.walk(_tree(module)):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.add(node.module)

        assert _FORBIDDEN_DOMAINS.isdisjoint(imported)
        assert not any(name == "kiteconnect" for name in imported)


def test_edd002_invokes_no_provider_endpoint_or_capability() -> None:
    invoked = set()
    for module in _CAPABILITY_MODULES:
        invoked.update(
            node.func.attr
            for node in ast.walk(_tree(module))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        )

    assert _FORBIDDEN_PROVIDER_OPERATIONS.isdisjoint(invoked)


def test_provider_neutral_representations_expose_no_sensitive_or_scope_fields() -> None:
    model_types = (
        CapabilityAssessmentRequest,
        CapabilityEvidence,
        CapabilityAssessmentRecord,
        CapabilityAuditEvidence,
        CapabilityGuiProjection,
    )
    exposed = {
        field.name
        for model_type in model_types
        for field in fields(model_type)
    }

    assert _SENSITIVE_OR_OUT_OF_SCOPE_FIELDS.isdisjoint(exposed)


def test_provider_neutral_modules_do_not_import_kite_adapter() -> None:
    for module in _CAPABILITY_MODULES[:3]:
        imported = {
            node.module
            for node in ast.walk(_tree(module))
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert not any(
            name.startswith("kronos.provider.adapters.kite")
            for name in imported
        )
