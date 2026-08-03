from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys
from typing import Callable

import pytest

from kronos.provider.models.authentication import (
    AuthenticatedContextState,
    AuthenticationAttemptCancellationResult,
    AuthenticationAttemptState,
    ProviderAvailabilityState,
    SessionStatus,
)
from tools.provider_pilots import car016_provider_authentication_gui as pilot


_ROOT = Path(__file__).resolve().parents[3]
_SOURCE = _ROOT / "tools/provider_pilots/car016_provider_authentication_gui.py"


class _FakeRoot:
    def __init__(self) -> None:
        self.mainloop_count = 0

    def mainloop(self) -> None:
        self.mainloop_count += 1


class _FakeView:
    def __init__(self) -> None:
        self.controller: pilot.Car016AuthenticationPilotController | None = None
        self.notice = ""
        self.rendered = ""
        self.controls = {
            "login": False,
            "cancel": False,
            "verify": False,
            "end": False,
        }
        self.closed = False
        self.dispatch_count = 0
        self.before_close: Callable[[], None] | None = None

    def bind(self, controller: pilot.Car016AuthenticationPilotController) -> None:
        self.controller = controller

    def set_notice(self, notice: str) -> None:
        self.notice = notice

    def show_state(self, rendered: str) -> None:
        self.rendered = rendered

    def set_controls(self, **controls: bool) -> None:
        self.controls = controls

    def dispatch_to_main(self, operation: Callable[[], None]) -> None:
        self.dispatch_count += 1
        operation()

    def close(self) -> None:
        if self.before_close is not None:
            self.before_close()
        self.closed = True


class _DeferredWorker:
    def __init__(self) -> None:
        self.operations: list[Callable[[], None]] = []

    def submit(self, operation: Callable[[], None]) -> None:
        self.operations.append(operation)

    def run_once(self) -> None:
        self.operations.pop(0)()


class _FakeService:
    def __init__(self) -> None:
        self.handle = object()
        self.begin_count = 0
        self.complete_count = 0
        self.cancel_count = 0
        self.verify_count = 0
        self.end_count = 0
        self.status_count = 0
        self.attempt_state: AuthenticationAttemptState | None = None
        self.context_state = AuthenticatedContextState.ABSENT
        self.availability = ProviderAvailabilityState.NOT_VERIFIED
        self.attempt_active = False
        self.failure_code: object | None = None
        self.effect: Exception | None = None
        self.before_cancel: Callable[[], None] | None = None
        self.before_begin: Callable[[], None] | None = None

    def begin_login(self) -> object:
        if self.before_begin is not None:
            self.before_begin()
        self.begin_count += 1
        if self.effect is not None:
            raise self.effect
        self.attempt_state = AuthenticationAttemptState.AWAITING_CALLBACK
        self.attempt_active = True
        return self.handle

    def complete_callback(self, attempt: object) -> object:
        assert attempt is self.handle
        self.complete_count += 1
        if self.effect is not None:
            raise self.effect
        self.attempt_state = AuthenticationAttemptState.SUCCEEDED
        self.attempt_active = False
        self.context_state = AuthenticatedContextState.ACTIVE
        self.availability = ProviderAvailabilityState.NOT_VERIFIED
        return object()

    def cancel_authentication_attempt(
        self,
        attempt: object,
    ) -> AuthenticationAttemptCancellationResult:
        assert attempt is self.handle
        if self.before_cancel is not None:
            self.before_cancel()
        self.cancel_count += 1
        self.attempt_state = AuthenticationAttemptState.CANCELLED
        self.attempt_active = False
        return AuthenticationAttemptCancellationResult.CANCELLED

    def verify_provider_availability(self) -> ProviderAvailabilityState:
        self.verify_count += 1
        self.availability = ProviderAvailabilityState.AVAILABLE
        return self.availability

    def session_status(self) -> SessionStatus:
        self.status_count += 1
        return SessionStatus(
            attempt_state=self.attempt_state,
            context_state=self.context_state,
            provider_availability=self.availability,
            failure_code=self.failure_code,  # type: ignore[arg-type]
            attempt_active=self.attempt_active,
            context_reusable=self.context_state is AuthenticatedContextState.ACTIVE,
        )

    def authentication_attempt_status(self, _attempt: object) -> None:
        return None

    def end_kronos_session(self) -> None:
        self.end_count += 1
        self.context_state = AuthenticatedContextState.ENDED
        self.availability = ProviderAvailabilityState.NOT_VERIFIED


def _functional_controller(
    *,
    service: _FakeService | None = None,
    availability_authorized: bool = False,
    confirmation: Callable[[], bool] = lambda: True,
) -> tuple[
    pilot.Car016AuthenticationPilotController,
    _FakeView,
    _FakeService,
    _DeferredWorker,
]:
    selected_service = service or _FakeService()
    view = _FakeView()
    worker = _DeferredWorker()
    controller = pilot.Car016AuthenticationPilotController(
        view=view,
        service=selected_service,  # type: ignore[arg-type]
        worker_submit=worker.submit,
        confirmation=confirmation,
        activation=pilot._OFFLINE_FAKE_ACTIVATION,
        availability_authorized=availability_authorized,
    )
    return controller, view, selected_service, worker


def test_direct_import_is_silent_and_effect_free() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import tools.provider_pilots.car016_provider_authentication_gui",
        ],
        cwd=_ROOT,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_ordinary_direct_launch_is_inspection_only() -> None:
    root = _FakeRoot()
    view = _FakeView()

    pilot.main(root_factory=lambda: root, view_factory=lambda _root: view)

    assert root.mainloop_count == 1
    assert view.controls == {
        "login": False,
        "cancel": False,
        "verify": False,
        "end": False,
    }
    assert view.notice == pilot.INSPECTION_NOTICE


def test_controller_construction_without_fake_capability_is_inert() -> None:
    view = _FakeView()
    service = _FakeService()
    worker = _DeferredWorker()

    controller = pilot.Car016AuthenticationPilotController(
        view=view,
        service=service,  # type: ignore[arg-type]
        worker_submit=worker.submit,
    )
    controller.login()
    controller.cancel()
    controller.verify_provider_availability()
    controller.end_kronos_session()

    assert service.begin_count == 0
    assert service.complete_count == 0
    assert service.cancel_count == 0
    assert service.verify_count == 0
    assert service.end_count == 0
    assert worker.operations == []


def test_pilot_has_four_explicit_controls_and_no_input_widget() -> None:
    tree = ast.parse(_SOURCE.read_text())
    strings = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    assert {
        "Login to Kite",
        "Cancel",
        "Verify Provider Availability",
        "End KRONOS Session",
    }.issubset(strings)
    assert "Entry" not in attributes
    assert "Text" not in attributes


def test_source_has_no_real_composition_or_external_effect_import() -> None:
    source = _SOURCE.read_text()

    for prohibited in (
        "AppleKeychain",
        "Settings",
        "LoopbackAuthenticationCallback",
        "KiteAuthenticationAdapter",
        "KiteConnect",
        "webbrowser",
        "socket",
        "urlopen",
        "requests",
    ):
        assert prohibited not in source


def test_fake_login_runs_one_attempt_and_one_worker_completion() -> None:
    controller, view, service, worker = _functional_controller()

    controller.login()

    assert service.begin_count == 1
    assert service.complete_count == 0
    assert len(worker.operations) == 1
    assert view.controls["login"] is False
    assert view.controls["cancel"] is True

    worker.run_once()

    assert service.complete_count == 1
    assert view.dispatch_count == 1
    assert "Authentication Attempt: SUCCEEDED" in view.rendered
    assert "Authenticated Context: ACTIVE" in view.rendered
    assert "Provider Availability: NOT_VERIFIED" in view.rendered


def test_confirmation_precedes_begin_login() -> None:
    ordering: list[str] = []
    service = _FakeService()
    service.before_begin = lambda: ordering.append("begin")
    controller, _, _, _ = _functional_controller(
        service=service,
        confirmation=lambda: ordering.append("confirm") or True,
    )

    controller.login()

    assert ordering == ["confirm", "begin"]


def test_declined_confirmation_performs_no_lifecycle_operation() -> None:
    controller, view, service, worker = _functional_controller(
        confirmation=lambda: False
    )

    controller.login()

    assert service.begin_count == 0
    assert service.complete_count == 0
    assert worker.operations == []
    assert view.controls["login"] is True


def test_second_login_is_unreachable_after_first_initiation() -> None:
    controller, _, service, worker = _functional_controller()

    controller.login()
    controller.login()
    worker.run_once()
    controller.login()

    assert service.begin_count == 1
    assert service.complete_count == 1


def test_verify_is_disabled_without_later_authority() -> None:
    controller, view, service, worker = _functional_controller()
    controller.login()
    worker.run_once()

    controller.verify_provider_availability()

    assert view.controls["verify"] is False
    assert service.verify_count == 0


def test_verify_requires_active_context_even_with_fake_authority() -> None:
    controller, view, service, _ = _functional_controller(
        availability_authorized=True
    )

    controller.verify_provider_availability()

    assert view.controls["verify"] is False
    assert service.verify_count == 0


def test_verify_runs_once_only_after_active_context_and_fake_authority() -> None:
    controller, view, service, worker = _functional_controller(
        availability_authorized=True
    )
    controller.login()
    worker.run_once()

    assert view.controls["verify"] is True
    controller.verify_provider_availability()

    assert service.verify_count == 1
    assert "Provider Availability: AVAILABLE" in view.rendered


def test_explicit_cancel_mutates_only_a_nonterminal_attempt() -> None:
    controller, _, service, _ = _functional_controller()
    controller.login()

    controller.cancel()
    controller.cancel()

    assert service.cancel_count == 1
    assert service.complete_count == 0


def test_close_cancels_one_nonterminal_attempt_before_closing() -> None:
    controller, view, service, _ = _functional_controller()
    ordering: list[str] = []
    service.before_cancel = lambda: ordering.append("cancel")
    view.before_close = lambda: ordering.append("close")
    controller.login()

    controller.close()

    assert service.cancel_count == 1
    assert view.closed is True
    assert ordering == ["cancel", "close"]


def test_worker_completion_after_close_never_dispatches_to_closed_view() -> None:
    controller, view, service, worker = _functional_controller()
    controller.login()
    controller.close()

    worker.run_once()

    assert service.cancel_count == 1
    assert view.closed is True
    assert view.dispatch_count == 0


def test_close_with_terminal_attempt_performs_no_lifecycle_mutation() -> None:
    controller, view, service, worker = _functional_controller()
    controller.login()
    worker.run_once()

    controller.close()

    assert service.cancel_count == 0
    assert service.end_count == 0
    assert view.closed is True


def test_close_without_attempt_performs_no_lifecycle_mutation() -> None:
    controller, view, service, _ = _functional_controller()

    controller.close()

    assert service.cancel_count == 0
    assert service.end_count == 0
    assert view.closed is True


def test_end_session_requires_active_context_and_is_local_service_call() -> None:
    controller, view, service, worker = _functional_controller()
    controller.end_kronos_session()
    controller.login()
    worker.run_once()

    controller.end_kronos_session()
    controller.end_kronos_session()

    assert service.end_count == 1
    assert service.verify_count == 0
    assert "Authenticated Context: ENDED" in view.rendered


class _UntrustedValue:
    value = "raw-material-must-not-render"


def test_unrecognized_values_are_sanitized_without_rendering_raw_value() -> None:
    service = _FakeService()
    service.failure_code = _UntrustedValue()
    controller, view, _, _ = _functional_controller(service=service)

    controller.refresh_state()

    assert "raw-material-must-not-render" not in view.rendered
    assert "Controlled outcome: INDETERMINATE" in view.rendered


def test_raw_exception_is_never_displayed_or_raised() -> None:
    service = _FakeService()
    service.effect = RuntimeError("raw-exception-material-must-not-render")
    controller, view, _, _ = _functional_controller(service=service)

    controller.login()

    assert "raw-exception-material-must-not-render" not in view.rendered
    assert "Controlled outcome: SANITIZED_LOCAL_FAILURE" in view.rendered


def test_all_fake_interactions_write_nothing_to_stdout_or_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    controller, _, _, worker = _functional_controller(
        availability_authorized=True
    )

    controller.login()
    worker.run_once()
    controller.verify_provider_availability()
    controller.end_kronos_session()
    controller.close()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_rendered_state_has_only_four_sanitized_projection_lines() -> None:
    rendered = pilot.SanitizedPilotState().render()

    assert rendered.splitlines() == [
        "Authentication Attempt: NONE",
        "Authenticated Context: ABSENT",
        "Provider Availability: NOT_VERIFIED",
        "Controlled outcome: NONE",
    ]
