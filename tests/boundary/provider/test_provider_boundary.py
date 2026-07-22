import ast
from pathlib import Path

from kronos.provider.models.availability import ProviderAvailabilityState


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SOURCE_ROOT = _REPOSITORY_ROOT / "src" / "kronos"
_KITE_ADAPTER_ROOT = _SOURCE_ROOT / "provider" / "adapters" / "kite"
_KITE_CLIENT_MODULE = _KITE_ADAPTER_ROOT / "client.py"
_FORBIDDEN_KITE_CALLS = {
    "basket_order_margins",
    "cancel_order",
    "connect",
    "convert_position",
    "delete_gtt",
    "exit_order",
    "generate_session",
    "get_gtt",
    "get_gtts",
    "historical_data",
    "holdings",
    "instruments",
    "ltp",
    "margins",
    "modify_gtt",
    "modify_order",
    "ohlc",
    "order_history",
    "order_margins",
    "orders",
    "place_gtt",
    "place_order",
    "positions",
    "quote",
    "renew_access_token",
    "set_access_token",
    "trades",
}


def _python_sources() -> list[Path]:
    return sorted(_SOURCE_ROOT.rglob("*.py"))


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_kite_sdk_imports_are_adapter_local_and_client_import_is_isolated() -> None:
    sdk_importers: list[Path] = []
    client_importers: list[Path] = []

    for source in _python_sources():
        tree = ast.parse(source.read_text())
        imported_modules = _imported_modules(tree)
        if any(module == "kiteconnect" or module.startswith("kiteconnect.") for module in imported_modules):
            sdk_importers.append(source)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module != "kiteconnect":
                continue
            if any(alias.name == "KiteConnect" for alias in node.names):
                client_importers.append(source)

    assert all(source.is_relative_to(_KITE_ADAPTER_ROOT) for source in sdk_importers)
    assert client_importers == [_KITE_CLIENT_MODULE]


def test_kite_adapter_invokes_profile_only() -> None:
    invoked: list[str] = []
    for source in sorted(_KITE_ADAPTER_ROOT.rglob("*.py")):
        tree = ast.parse(source.read_text())
        invoked.extend(
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        )

    assert invoked.count("profile") == 1
    assert _FORBIDDEN_KITE_CALLS.isdisjoint(invoked)


def test_provider_does_not_read_environment_or_import_business_domains() -> None:
    provider_root = _SOURCE_ROOT / "provider"
    forbidden_imports = {
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

    for source in sorted(provider_root.rglob("*.py")):
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {node.module or ""}
            else:
                continue

            assert "os" not in names
            assert forbidden_imports.isdisjoint(names)


def test_provider_availability_has_exactly_five_internal_states() -> None:
    assert set(ProviderAvailabilityState) == {
        ProviderAvailabilityState.NOT_INITIALIZED,
        ProviderAvailabilityState.AVAILABLE,
        ProviderAvailabilityState.CONFIGURATION_INVALID,
        ProviderAvailabilityState.AUTHENTICATION_REJECTED,
        ProviderAvailabilityState.TEMPORARILY_UNAVAILABLE,
    }


def test_provider_contract_package_remains_empty() -> None:
    contracts = _SOURCE_ROOT / "provider" / "contracts" / "__init__.py"

    assert contracts.read_text().strip() == ""
