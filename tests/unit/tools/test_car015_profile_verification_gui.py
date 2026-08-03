from __future__ import annotations

import ast
from dataclasses import asdict
import importlib
import logging
from pathlib import Path
import socket
from typing import Any

import pytest

from tools.provider_pilots import car015_profile_verification_gui as pilot


_FAKE_API_KEY = "offline-fake-car015-api-key"
_FAKE_ACCESS_TOKEN = "offline-fake-car015-access-token"
_RAW_EXCEPTION = "raw-provider-profile-secret-must-not-escape"
_PROFILE_MARKERS = (
    "user_id",
    "account_id",
    "user_name",
    "email",
    "broker",
    "entitlements",
)
_ROOT = Path(__file__).resolve().parents[3]
_SOURCE = _ROOT / "tools/provider_pilots/car015_profile_verification_gui.py"


@pytest.fixture(autouse=True)
def _reset_process_latches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pilot, "_confirmation_presented", False)
    monkeypatch.setattr(pilot, "_execution_started", False)
    monkeypatch.setattr(pilot, "_authority_consumed", False)


class _Value:
    def __init__(self, value: str) -> None:
        self.value = value


class _Availability:
    def __init__(
        self,
        state: str = "AVAILABLE",
        error_code: str | None = None,
    ) -> None:
        self.state = _Value(state)
        self.error_code = None if error_code is None else _Value(error_code)


class _FakeView:
    def __init__(self) -> None:
        self.api_key = ""
        self.access_token = ""
        self.run_enabled: bool | None = None
        self.status = ""
        self.result = ""
        self.disabled = False
        self.cleared = False
        self.hidden = False
        self.closed = False
        self.acknowledgement_only = False
        self.credential_reads = 0
        self.controller: pilot.Car015ProfileVerificationController | None = None

    def bind(
        self,
        controller: pilot.Car015ProfileVerificationController,
    ) -> None:
        self.controller = controller

    def credential_values(self) -> tuple[str, str]:
        self.credential_reads += 1
        return self.api_key, self.access_token

    def set_run_enabled(self, enabled: bool) -> None:
        self.run_enabled = enabled

    def set_status(self, status: str) -> None:
        self.status = status

    def clear_credentials(self) -> None:
        self.api_key = ""
        self.access_token = ""
        self.cleared = True

    def hide_credentials(self) -> None:
        self.hidden = True

    def disable_execution_controls(self) -> None:
        self.disabled = True
        self.run_enabled = False

    def show_result(self, rendered: str) -> None:
        self.result = rendered

    def show_acknowledgement_only(self) -> None:
        self.acknowledgement_only = True
        self.run_enabled = False

    def close(self) -> None:
        self.closed = True


class _FakeSettingsFactory:
    def __init__(self, assertion: Any | None = None) -> None:
        self.calls = 0
        self.arguments: list[dict[str, object]] = []
        self.assertion = assertion

    def __call__(self, **arguments: object) -> object:
        self.calls += 1
        self.arguments.append(arguments)
        if self.assertion is not None:
            self.assertion()
        return object()


class _FakeService:
    def __init__(
        self,
        *,
        probe_result: object | None = None,
        shutdown_result: object | None = None,
        probe_error: Exception | None = None,
        shutdown_error: Exception | None = None,
        before_probe: Any | None = None,
    ) -> None:
        self.probe_result = probe_result or _Availability()
        self.shutdown_result = shutdown_result or _Availability(
            state="NOT_INITIALIZED"
        )
        self.probe_error = probe_error
        self.shutdown_error = shutdown_error
        self.before_probe = before_probe
        self.probe_calls = 0
        self.shutdown_calls = 0

    def probe(self) -> object:
        self.probe_calls += 1
        if self.before_probe is not None:
            self.before_probe()
        if self.probe_error is not None:
            raise self.probe_error
        return self.probe_result

    def shutdown(self) -> object:
        self.shutdown_calls += 1
        if self.shutdown_error is not None:
            raise self.shutdown_error
        return self.shutdown_result


class _FakeServiceFactory:
    def __init__(
        self,
        service: _FakeService | None = None,
        *,
        error: Exception | None = None,
        assertion: Any | None = None,
    ) -> None:
        self.service = service or _FakeService()
        self.error = error
        self.assertion = assertion
        self.calls = 0
        self.settings: list[object] = []

    def __call__(self, settings: object) -> _FakeService:
        self.calls += 1
        self.settings.append(settings)
        if self.assertion is not None:
            self.assertion()
        if self.error is not None:
            raise self.error
        return self.service


class _FakeRoot:
    def __init__(self) -> None:
        self.mainloop_calls = 0

    def mainloop(self) -> None:
        self.mainloop_calls += 1


def _controller(
    view: _FakeView,
    *,
    confirmation: Any = lambda _text: True,
    settings_factory: Any | None = None,
    service_factory: Any | None = None,
) -> pilot.Car015ProfileVerificationController:
    return pilot.Car015ProfileVerificationController(
        view=view,
        confirmation=confirmation,
        settings_factory=settings_factory or _FakeSettingsFactory(),
        service_factory=service_factory or _FakeServiceFactory(),
    )


def _ready_view() -> _FakeView:
    view = _FakeView()
    view.api_key = _FAKE_API_KEY
    view.access_token = _FAKE_ACCESS_TOKEN
    return view


def test_tkinter_module_imports_successfully() -> None:
    tkinter = importlib.import_module("tkinter")

    assert tkinter.TkVersion > 0


def test_opening_controller_causes_zero_provider_calls() -> None:
    view = _FakeView()
    service = _FakeService()

    _controller(view, service_factory=_FakeServiceFactory(service))

    assert service.probe_calls == 0
    assert service.shutdown_calls == 0


def test_opening_controller_constructs_no_service_or_settings() -> None:
    view = _FakeView()
    settings_factory = _FakeSettingsFactory()
    service_factory = _FakeServiceFactory()

    _controller(
        view,
        settings_factory=settings_factory,
        service_factory=service_factory,
    )

    assert settings_factory.calls == 0
    assert service_factory.calls == 0
    assert view.credential_reads == 0


def test_main_opening_with_fakes_constructs_no_runtime_object() -> None:
    root = _FakeRoot()
    view = _FakeView()
    settings_factory = _FakeSettingsFactory()
    service_factory = _FakeServiceFactory()

    pilot.main(
        root_factory=lambda: root,
        view_factory=lambda _root: view,
        confirmation=lambda _text: False,
        settings_factory=settings_factory,
        service_factory=service_factory,
    )

    assert root.mainloop_calls == 1
    assert settings_factory.calls == 0
    assert service_factory.calls == 0


def test_both_credential_entries_are_masked() -> None:
    source = _SOURCE.read_text()

    assert source.count('show="*"') == 2


@pytest.mark.parametrize(
    ("api_key", "access_token"),
    [("", ""), ("", _FAKE_ACCESS_TOKEN), (_FAKE_API_KEY, "")],
)
def test_run_remains_disabled_until_both_fields_are_non_empty(
    api_key: str,
    access_token: str,
) -> None:
    view = _FakeView()
    controller = _controller(view)
    view.api_key = api_key
    view.access_token = access_token

    controller.credentials_changed()

    assert view.run_enabled is False


def test_run_becomes_enabled_when_both_fields_are_non_empty() -> None:
    view = _ready_view()
    controller = _controller(view)

    controller.credentials_changed()

    assert view.run_enabled is True


def test_cancel_clears_credentials_and_makes_zero_provider_calls() -> None:
    view = _ready_view()
    service = _FakeService()
    controller = _controller(
        view,
        service_factory=_FakeServiceFactory(service),
    )

    controller.cancel()

    assert view.cleared is True
    assert view.closed is True
    assert service.probe_calls == 0


def test_rejecting_confirmation_makes_zero_provider_calls() -> None:
    view = _ready_view()
    settings_factory = _FakeSettingsFactory()
    service_factory = _FakeServiceFactory()
    controller = _controller(
        view,
        confirmation=lambda _text: False,
        settings_factory=settings_factory,
        service_factory=service_factory,
    )

    controller.run_once()

    assert settings_factory.calls == 0
    assert service_factory.calls == 0
    assert service_factory.service.probe_calls == 0
    assert pilot._authority_consumed is False
    assert view.cleared and view.hidden and view.disabled


def test_final_confirmation_is_presented_only_once_per_process() -> None:
    view = _ready_view()
    confirmations = 0

    def reject(_text: str) -> bool:
        nonlocal confirmations
        confirmations += 1
        return False

    controller = _controller(view, confirmation=reject)
    controller.run_once()
    controller.run_once()

    assert confirmations == 1


def test_execution_started_before_settings_construction() -> None:
    view = _ready_view()
    settings_factory = _FakeSettingsFactory(
        assertion=lambda: (
            pilot._execution_started is True
            or (_ for _ in ()).throw(AssertionError())
        )
    )

    _controller(view, settings_factory=settings_factory).run_once()

    assert settings_factory.calls == 1


def test_authority_consumed_before_service_construction() -> None:
    view = _ready_view()
    service_factory = _FakeServiceFactory(
        assertion=lambda: (
            pilot._authority_consumed is True
            or (_ for _ in ()).throw(AssertionError())
        )
    )

    _controller(view, service_factory=service_factory).run_once()

    assert service_factory.calls == 1


def test_settings_receive_only_required_ephemeral_values() -> None:
    view = _ready_view()
    settings_factory = _FakeSettingsFactory()

    _controller(view, settings_factory=settings_factory).run_once()

    assert settings_factory.arguments == [
        {
            "provider": "KITE",
            "kite_api_key": _FAKE_API_KEY,
            "kite_api_secret": "",
            "kite_access_token": _FAKE_ACCESS_TOKEN,
            "kite_redirect_url": "",
        }
    ]


def test_credentials_are_disabled_cleared_and_hidden_before_probe() -> None:
    view = _ready_view()

    def assert_boundary() -> None:
        assert view.disabled is True
        assert view.cleared is True
        assert view.hidden is True
        assert view.api_key == ""
        assert view.access_token == ""

    service = _FakeService(before_probe=assert_boundary)

    _controller(
        view,
        service_factory=_FakeServiceFactory(service),
    ).run_once()

    assert service.probe_calls == 1


def test_local_credential_container_is_cleared_before_probe_call_site() -> None:
    source = _SOURCE.read_text()
    service_construction = source.index("self.__service_factory(settings)")
    credential_clear = source.index("credentials.clear()", service_construction)
    probe = source.index("service.probe()")

    assert service_construction < credential_clear < probe


def test_confirmed_execution_invokes_probe_and_shutdown_exactly_once() -> None:
    view = _ready_view()
    service = _FakeService()
    controller = _controller(
        view,
        service_factory=_FakeServiceFactory(service),
    )

    controller.run_once()

    assert service.probe_calls == 1
    assert service.shutdown_calls == 1


def test_probe_failure_causes_no_retry_and_is_sanitized() -> None:
    view = _ready_view()
    service = _FakeService(probe_error=RuntimeError(_RAW_EXCEPTION))
    controller = _controller(
        view,
        service_factory=_FakeServiceFactory(service),
    )

    controller.run_once()

    assert service.probe_calls == 1
    assert service.shutdown_calls == 1
    assert "LOCAL_PROBE_FAILURE" in view.result
    assert _RAW_EXCEPTION not in view.result


def test_second_run_cannot_probe_again() -> None:
    view = _ready_view()
    service = _FakeService()
    controller = _controller(
        view,
        service_factory=_FakeServiceFactory(service),
    )

    controller.run_once()
    controller.run_once()

    assert service.probe_calls == 1
    assert service.shutdown_calls == 1


def test_shutdown_failure_is_sanitized() -> None:
    view = _ready_view()
    service = _FakeService(shutdown_error=RuntimeError(_RAW_EXCEPTION))

    _controller(
        view,
        service_factory=_FakeServiceFactory(service),
    ).run_once()

    assert service.shutdown_calls == 1
    assert "Local shutdown: SANITIZED FAILURE" in view.result
    assert _RAW_EXCEPTION not in view.result


def test_controlled_shutdown_error_is_sanitized() -> None:
    view = _ready_view()
    service = _FakeService(
        shutdown_result=_Availability(
            state="NOT_INITIALIZED",
            error_code="SHUTDOWN_FAILURE",
        )
    )

    _controller(
        view,
        service_factory=_FakeServiceFactory(service),
    ).run_once()

    assert "Local shutdown: SANITIZED FAILURE" in view.result


@pytest.mark.parametrize(
    ("failure_stage", "expected_code"),
    [
        ("settings", "LOCAL_SETTINGS_CONSTRUCTION_FAILURE"),
        ("service", "LOCAL_SERVICE_CONSTRUCTION_FAILURE"),
    ],
)
def test_local_construction_failure_leaves_authority_consumed(
    failure_stage: str,
    expected_code: str,
) -> None:
    view = _ready_view()

    class FailingSettings:
        def __call__(self, **_arguments: object) -> object:
            raise RuntimeError(_RAW_EXCEPTION)

    settings_factory: Any = (
        FailingSettings() if failure_stage == "settings" else _FakeSettingsFactory()
    )
    service_factory = _FakeServiceFactory(
        error=(
            RuntimeError(_RAW_EXCEPTION)
            if failure_stage == "service"
            else None
        )
    )
    _controller(
        view,
        settings_factory=settings_factory,
        service_factory=service_factory,
    ).run_once()

    assert pilot._execution_started is True
    assert pilot._authority_consumed is True
    assert expected_code in view.result
    assert _RAW_EXCEPTION not in view.result
    assert "Traceback" not in view.result


@pytest.mark.parametrize(
    ("state", "error_code", "connectivity"),
    [
        ("AVAILABLE", None, "AVAILABLE"),
        ("CONFIGURATION_INVALID", "CONFIGURATION_INVALID", "UNAVAILABLE"),
        ("AUTHENTICATION_REJECTED", "AUTHENTICATION_REJECTED", "UNAVAILABLE"),
        (
            "CONTEXT_INVALID",
            "ACCESS_TOKEN_INVALID_OR_EXPIRED",
            "UNAVAILABLE",
        ),
        ("TEMPORARILY_UNAVAILABLE", "NETWORK_TIMEOUT", "UNAVAILABLE"),
        ("UNKNOWN_RAW_STATE", "UNKNOWN_RAW_CODE", "INDETERMINATE"),
    ],
)
def test_provider_result_is_reduced_to_controlled_fields(
    state: str,
    error_code: str | None,
    connectivity: str,
) -> None:
    view = _ready_view()
    service = _FakeService(probe_result=_Availability(state, error_code))

    _controller(
        view,
        service_factory=_FakeServiceFactory(service),
    ).run_once()

    assert f"Profile connectivity: {connectivity}" in view.result
    assert "UNKNOWN_RAW_STATE" not in view.result
    assert "UNKNOWN_RAW_CODE" not in view.result


def test_rendered_result_contains_exactly_four_approved_lines() -> None:
    result = pilot.SanitizedProfileResult(
        profile_connectivity="AVAILABLE",
        controlled_error_code="NONE",
        local_shutdown="SUCCESS",
    )

    rendered = pilot.render_sanitized_result(result)

    assert rendered.splitlines() == [
        "Profile connectivity: AVAILABLE",
        "Controlled error code: NONE",
        "Local shutdown: SUCCESS",
        "CAR-015 authority: CONSUMED",
    ]


def test_arbitrary_local_or_provider_text_is_not_rendered() -> None:
    result = pilot.SanitizedProfileResult(
        profile_connectivity=_RAW_EXCEPTION,
        controlled_error_code="LOCAL_" + _RAW_EXCEPTION,
        local_shutdown=_RAW_EXCEPTION,
    )

    rendered = pilot.render_sanitized_result(result)

    assert _RAW_EXCEPTION not in rendered
    assert "Profile connectivity: INDETERMINATE" in rendered
    assert "LOCAL_RESULT_SANITIZATION_FAILURE" in rendered
    assert "Local shutdown: SANITIZED FAILURE" in rendered


def test_profile_and_account_fields_are_absent_from_output() -> None:
    view = _ready_view()
    _controller(view).run_once()

    lowered = view.result.lower()
    assert all(marker not in lowered for marker in _PROFILE_MARKERS)


def test_credentials_are_absent_from_gui_stdout_stderr_and_logs(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    view = _ready_view()
    _controller(view).run_once()
    captured = capsys.readouterr()
    combined = captured.out + captured.err + caplog.text + view.result

    assert _FAKE_API_KEY not in combined
    assert _FAKE_ACCESS_TOKEN not in combined
    assert captured.out == ""
    assert captured.err == ""


def test_raw_exception_and_traceback_are_absent_everywhere(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    view = _ready_view()
    service = _FakeService(probe_error=RuntimeError(_RAW_EXCEPTION))
    _controller(
        view,
        service_factory=_FakeServiceFactory(service),
    ).run_once()
    captured = capsys.readouterr()
    combined = captured.out + captured.err + caplog.text + view.result

    assert _RAW_EXCEPTION not in combined
    assert "Traceback" not in combined


def test_post_confirmation_view_failure_is_contained(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FailingDisableView(_FakeView):
        def disable_execution_controls(self) -> None:
            raise RuntimeError(_RAW_EXCEPTION)

    view = FailingDisableView()
    view.api_key = _FAKE_API_KEY
    view.access_token = _FAKE_ACCESS_TOKEN

    _controller(view).run_once()
    captured = capsys.readouterr()

    assert pilot._execution_started is True
    assert pilot._authority_consumed is True
    assert _RAW_EXCEPTION not in captured.out + captured.err + view.result
    assert "Traceback" not in captured.out + captured.err + view.result


def test_no_unapproved_credential_input_or_retry_control_exists() -> None:
    source = _SOURCE.read_text()
    tree = ast.parse(source)
    init = next(
        node
        for node in next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "_TkView"
        ).body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    entry_calls = [
        node
        for node in ast.walk(init)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Entry"
    ]
    button_texts = {
        keyword.value.value
        for node in ast.walk(init)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Button"
        for keyword in node.keywords
        if keyword.arg == "text"
        and isinstance(keyword.value, ast.Constant)
        and isinstance(keyword.value.value, str)
    }

    assert len(entry_calls) == 2
    assert button_texts == {"Run One-Time Profile Verification", "Cancel"}
    assert "retry" not in {text.lower() for text in button_texts}


def test_no_reset_or_reauthorization_api_exists() -> None:
    public_methods = {
        name
        for name in dir(pilot.Car015ProfileVerificationController)
        if not name.startswith("_")
    }

    assert public_methods == {"cancel", "credentials_changed", "run_once"}


def test_reconstructing_controller_does_not_restore_process_authority() -> None:
    first_view = _ready_view()
    first_service = _FakeService()
    _controller(
        first_view,
        service_factory=_FakeServiceFactory(first_service),
    ).run_once()

    second_view = _ready_view()
    second_service_factory = _FakeServiceFactory()
    second = _controller(
        second_view,
        service_factory=second_service_factory,
    )
    second.run_once()

    assert first_service.probe_calls == 1
    assert second_service_factory.calls == 0
    assert second_view.disabled and second_view.hidden
    assert second_view.acknowledgement_only


def test_only_probe_and_shutdown_service_methods_are_exposed() -> None:
    tree = ast.parse(_SOURCE.read_text())
    controller = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "Car015ProfileVerificationController"
    )
    execute = next(
        node
        for node in controller.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "__execute_confirmed"
    )
    provider_calls = [
        node.func.attr
        for node in ast.walk(execute)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"probe", "shutdown"}
    ]

    assert provider_calls.count("probe") == 1
    assert provider_calls.count("shutdown") == 1


def test_only_approved_kronos_runtime_imports_exist() -> None:
    tree = ast.parse(_SOURCE.read_text())
    kronos_imports = {
        (node.module, tuple(alias.name for alias in node.names))
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").startswith("kronos.")
    }

    assert kronos_imports == {
        ("kronos.configuration.settings", ("Settings",)),
        (
            "kronos.provider.services.connectivity",
            ("KiteConnectivityService",),
        ),
    }


def test_single_construction_sites_follow_consumption_latches() -> None:
    source = _SOURCE.read_text()

    assert source.count("self.__settings_factory(") == 1
    assert source.count("self.__service_factory(") == 1
    assert source.index("_execution_started = True") < source.index(
        "self.__settings_factory("
    )
    assert source.index("_authority_consumed = True") < source.index(
        "self.__service_factory("
    )


def test_production_harness_has_no_print_or_logging_call() -> None:
    tree = ast.parse(_SOURCE.read_text())
    forbidden = {"print", "pprint", "debug", "info", "warning", "error"}
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    } | {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert forbidden.isdisjoint(calls)


def test_no_retry_polling_scheduling_or_secondary_endpoint_exists() -> None:
    source = _SOURCE.read_text()
    tree = ast.parse(source)
    forbidden_imports = {
        "dotenv",
        "requests",
        "urllib",
        "httpx",
        "retrying",
        "schedule",
        "apscheduler",
    }
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    forbidden_methods = {
        "instruments",
        "historical_data",
        "quote",
        "ltp",
        "ohlc",
        "orders",
        "trades",
        "holdings",
        "positions",
        "margins",
        "generate_session",
        "invalidate_access_token",
        "renew_access_token",
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert not any(name.split(".")[0] in forbidden_imports for name in imports)
    assert forbidden_methods.isdisjoint(called_attributes)
    assert not any(isinstance(node, ast.While) for node in ast.walk(tree))


def test_no_env_loader_or_file_persistence_call_exists() -> None:
    tree = ast.parse(_SOURCE.read_text())
    forbidden = {
        "load_dotenv",
        "dotenv_values",
        "getenv",
        "open",
        "write",
        "write_text",
        "write_bytes",
        "dump",
        "dumps",
    }
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    } | {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert forbidden.isdisjoint(calls)


def test_no_real_sdk_client_is_constructed(monkeypatch: pytest.MonkeyPatch) -> None:
    import kiteconnect

    def forbidden_constructor(*_arguments: object, **_keywords: object) -> None:
        raise AssertionError("real Kite SDK construction attempted")

    monkeypatch.setattr(kiteconnect, "KiteConnect", forbidden_constructor)
    view = _ready_view()
    service = _FakeService()
    _controller(
        view,
        service_factory=_FakeServiceFactory(service),
    ).run_once()

    assert service.probe_calls == 1


def test_no_network_call_occurs(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_socket(*_arguments: object, **_keywords: object) -> object:
        raise AssertionError("network attempted")

    monkeypatch.setattr(socket, "socket", forbidden_socket)
    view = _ready_view()
    service = _FakeService()
    _controller(
        view,
        service_factory=_FakeServiceFactory(service),
    ).run_once()

    assert service.probe_calls == 1


def test_sanitized_result_dataclass_contains_no_sensitive_field() -> None:
    result = pilot.SanitizedProfileResult(
        profile_connectivity="AVAILABLE",
        controlled_error_code="NONE",
        local_shutdown="SUCCESS",
    )
    serialized = str(asdict(result)).lower()

    assert all(marker not in serialized for marker in _PROFILE_MARKERS)
    assert "api_key" not in serialized
    assert "access_token" not in serialized


def test_warning_and_confirmation_preserve_one_attempt_boundary() -> None:
    assert pilot.WARNING_TEXT == (
        "This utility does not store credentials.\n"
        "Running the verification consumes CAR-015 authority whether it "
        "succeeds or\n"
        "fails.\n"
        "No retry or second attempt is permitted.\n"
        "Restarting this utility does not create new authority."
    )
    assert "failure also consumes car-015 authority" in (
        pilot.CONFIRMATION_TEXT.lower()
    )
    assert "no retry is permitted" in pilot.CONFIRMATION_TEXT.lower()
    assert "no second attempt is permitted" in pilot.CONFIRMATION_TEXT.lower()
