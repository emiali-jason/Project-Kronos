from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
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
    CoordinatedConsumptionState,
)
from kronos.provider.kite.live_activation import (
    ActivationProvenanceKind,
    CanonicalRepositoryEvidence,
    CoordinatedActivationValues,
    LiveActivationContext,
    TrustedActivationReviewer,
)
from tools.provider_pilots import car016_provider_authentication_gui as pilot


_ROOT = Path(__file__).resolve().parents[3]
_SOURCE = _ROOT / "tools/provider_pilots/car016_provider_authentication_gui.py"
_IMPLEMENTATION_SHA = "a" * 40
class _Verifier:
    def verify(self, expected: object, observed: object, evidence: object) -> bool:
        return expected is observed and evidence is not None


def _accepted_activation() -> tuple[LiveActivationContext, object]:
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    values = CoordinatedActivationValues(
        coordinated_activation_identity="KRONOS-TEST-GUI-001",
        coordinated_governance_publication_sha=_IMPLEMENTATION_SHA,
        car016_logical_publication_ref="CAR-016-V1.2-TEST",
        car017_logical_publication_ref="CAR-017-V1.2-TEST",
        frozen_car016_implementation_sha="b" * 40,
        frozen_car017_implementation_sha="c" * 40,
        authority_effective_at=now - timedelta(hours=1),
        authority_effective_timezone="Asia/Kolkata",
        authority_expires_at=now + timedelta(hours=1),
        authority_expiry_timezone="Asia/Kolkata",
        authentication_attempt_timeout_seconds=300,
        sponsor_environment_ref="TEST-NONPROD",
        hostname="test.local",
        provider_identity="ZERODHA_KITE",
        operational_provider="KITE",
        provider_configuration_ref="ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY",
        application_registration_ref="ZERODHA-KITE-APP-REGISTRATION-PRIMARY",
        credential_ref="KITE-API-SECRET-PRIMARY",
        intended_principal_registration_ref="KITE-INTENDED-PRINCIPAL-PRIMARY",
        composition_dependency_set_ref="CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1",
        redirect_url="http://127.0.0.1:8765/kite/callback",
        attempt_cardinality="ONE",
        provider_availability_authority="WITHHELD",
        provider_availability_max_operations=0,
        car014_status="UNEXECUTED",
        consumption_state=CoordinatedConsumptionState.UNUSED,
    )
    review = TrustedActivationReviewer(
        _Verifier(),
        provenance_kind=ActivationProvenanceKind.FAKE_ONLY,
    ).review(
        expected=values,
        observed=values,
        repository_evidence=CanonicalRepositoryEvidence(
            branch="develop",
            head_sha=_IMPLEMENTATION_SHA,
            origin_develop_sha=_IMPLEMENTATION_SHA,
            working_tree_clean=True,
            car016_canonical=True,
            car017_canonical=True,
            car014_unexecuted=True,
        ),
        reviewed_at=now,
    )
    return review.context, review.capability


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
        self.cleanup_count = 0
        self.status_count = 0
        self.attempt_state: AuthenticationAttemptState | None = None
        self.context_state = AuthenticatedContextState.ABSENT
        self.availability = ProviderAvailabilityState.NOT_VERIFIED
        self.attempt_active = False
        self.failure_code: object | None = None
        self.effect: Exception | None = None
        self.before_cancel: Callable[[], None] | None = None
        self.before_begin: Callable[[], None] | None = None
        self.composition_count = 0
        self.composed_activation: object | None = None

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

    def cleanup_local(self) -> None:
        self.cleanup_count += 1


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
    activation, _ = _accepted_activation()
    view = _FakeView()
    worker = _DeferredWorker()

    def compose(received: LiveActivationContext) -> _FakeService:
        selected_service.composition_count += 1
        selected_service.composed_activation = received
        return selected_service

    controller = pilot.Car016AuthenticationPilotController(
        view=view,
        worker_submit=worker.submit,
        confirmation=confirmation,
        activation=activation,
        composition_factory=compose,
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


def test_stage1_activation_is_passed_once_without_interpretation() -> None:
    activation, _ = _accepted_activation()
    service = _FakeService()
    view = _FakeView()
    worker = _DeferredWorker()
    received: list[LiveActivationContext] = []

    def composition(context: LiveActivationContext) -> _FakeService:
        received.append(context)
        return service

    controller = pilot.Car016AuthenticationPilotController(
        view=view,
        worker_submit=worker.submit,
        confirmation=lambda: True,
        activation=activation,
        composition_factory=composition,
    )

    assert received == []
    assert view.controls["login"] is True
    assert view.notice == pilot.ACTIVATED_NOTICE
    controller.login()
    assert received == [activation]
    assert type(received[0]) is LiveActivationContext


def test_stage2_source_does_not_own_or_interpret_activation_context() -> None:
    source = _SOURCE.read_text()
    tree = ast.parse(source)
    class_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    activation_attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "activation"
    }

    assert "LiveActivationContext" not in class_names
    assert "from_reviewed_capability" not in called_attributes
    assert activation_attributes == set()
    assert "compose_kite_authentication" not in source
    assert "isinstance(activation" not in source
    assert "type(activation" not in source
    assert "_matches_" not in source


def test_explicit_main_injection_enables_only_the_composed_presentation() -> None:
    activation, _ = _accepted_activation()
    service = _FakeService()
    root = _FakeRoot()
    view = _FakeView()
    worker = _DeferredWorker()
    received: list[LiveActivationContext] = []

    def composition(context: LiveActivationContext) -> _FakeService:
        received.append(context)
        return service

    pilot.main(
        root_factory=lambda: root,
        view_factory=lambda _root: view,
        activation=activation,
        composition_factory=composition,
        worker_submit=worker.submit,
        confirmation=lambda: True,
    )

    assert received == []
    assert root.mainloop_count == 1
    assert view.controls == {
        "login": True,
        "cancel": False,
        "verify": False,
        "end": False,
    }


def test_ambient_and_gui_state_cannot_create_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activation, _ = _accepted_activation()
    service = _FakeService()
    root = _FakeRoot()
    view = _FakeView()
    composition_calls = 0

    def composition(_context: LiveActivationContext) -> _FakeService:
        nonlocal composition_calls
        composition_calls += 1
        return service

    monkeypatch.setenv("KRONOS_LIVE_ACTIVATION", "enabled")
    monkeypatch.setattr(pilot, "ambient_activation", activation, raising=False)
    view.activation = activation

    pilot.main(
        root_factory=lambda: root,
        view_factory=lambda _root: view,
        composition_factory=composition,
        worker_submit=lambda _operation: None,
        confirmation=lambda: True,
    )

    assert composition_calls == 0
    assert service.begin_count == 0
    assert view.controls["login"] is False
    assert view.notice == pilot.INSPECTION_NOTICE


def test_composition_rejection_is_sanitized_and_keeps_controls_disabled() -> None:
    activation, _ = _accepted_activation()
    view = _FakeView()
    worker = _DeferredWorker()

    def reject(_context: LiveActivationContext) -> _FakeService:
        raise RuntimeError("raw-composition-material")

    controller = pilot.Car016AuthenticationPilotController(
        view=view,
        worker_submit=worker.submit,
        confirmation=lambda: True,
        activation=activation,
        composition_factory=reject,
    )
    controller.login()

    assert "raw-composition-material" not in view.rendered
    assert view.notice == pilot.INSPECTION_NOTICE
    assert all(enabled is False for enabled in view.controls.values())
    assert worker.operations == []


@pytest.mark.parametrize("missing", ["composition", "worker", "confirmation"])
def test_incomplete_injected_seams_remain_inspection_only(missing: str) -> None:
    activation, _ = _accepted_activation()
    service = _FakeService()
    view = _FakeView()
    worker = _DeferredWorker()
    composition_calls = 0

    def composition(_context: LiveActivationContext) -> _FakeService:
        nonlocal composition_calls
        composition_calls += 1
        return service

    pilot.Car016AuthenticationPilotController(
        view=view,
        worker_submit=None if missing == "worker" else worker.submit,
        confirmation=None if missing == "confirmation" else lambda: True,
        activation=activation,
        composition_factory=None if missing == "composition" else composition,
    )

    assert composition_calls == 0
    assert view.notice == pilot.INSPECTION_NOTICE
    assert all(enabled is False for enabled in view.controls.values())


def test_fake_activation_cannot_enable_real_composition_dependencies() -> None:
    activation, _ = _accepted_activation()
    view = _FakeView()
    worker = _DeferredWorker()
    def composition(_context: LiveActivationContext) -> object:
        raise RuntimeError("FAKE_ACTIVATION_CANNOT_ENABLE_LIVE_DEPENDENCIES")

    controller = pilot.Car016AuthenticationPilotController(
        view=view,
        worker_submit=worker.submit,
        confirmation=lambda: True,
        activation=activation,
        composition_factory=composition,  # type: ignore[arg-type]
    )
    controller.login()

    assert "FAKE_ACTIVATION" not in view.rendered
    assert all(enabled is False for enabled in view.controls.values())
    assert worker.operations == []


def test_controller_construction_without_fake_capability_is_inert() -> None:
    view = _FakeView()
    service = _FakeService()
    worker = _DeferredWorker()

    def composition(_activation: LiveActivationContext) -> _FakeService:
        service.composition_count += 1
        return service

    controller = pilot.Car016AuthenticationPilotController(
        view=view,
        worker_submit=worker.submit,
        confirmation=lambda: True,
        composition_factory=composition,
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
    assert service.composition_count == 0
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

    assert service.composition_count == 1
    assert type(service.composed_activation) is LiveActivationContext
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


def test_verify_remains_withheld_after_active_context() -> None:
    controller, view, service, worker = _functional_controller(
        availability_authorized=True
    )
    controller.login()
    worker.run_once()

    assert view.controls["verify"] is False
    controller.verify_provider_availability()

    assert service.verify_count == 0
    assert "Provider Availability: NOT_VERIFIED" in view.rendered


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

    controller.login()
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


def test_begin_failure_runs_local_cleanup_once() -> None:
    service = _FakeService()
    service.effect = RuntimeError("synthetic begin failure")
    controller, _, _, _ = _functional_controller(service=service)

    controller.login()

    assert service.begin_count == 1
    assert service.cleanup_count == 1


def test_callback_failure_runs_local_cleanup_once() -> None:
    service = _FakeService()
    controller, _, _, worker = _functional_controller(service=service)
    controller.login()
    service.effect = RuntimeError("synthetic callback failure")

    worker.run_once()

    assert service.complete_count == 1
    assert service.cleanup_count == 1


def test_close_after_runtime_construction_runs_local_cleanup() -> None:
    controller, view, service, _ = _functional_controller()
    controller.login()

    controller.close()

    assert view.closed is True
    assert service.cleanup_count == 1


def test_close_before_confirmation_constructs_no_runtime_for_cleanup() -> None:
    controller, view, service, _ = _functional_controller()

    controller.close()

    assert view.closed is True
    assert service.composition_count == 0
    assert service.cleanup_count == 0


def test_repeated_close_does_not_repeat_local_cleanup() -> None:
    controller, _, service, _ = _functional_controller()
    controller.login()

    controller.close()
    controller.close()

    assert service.cleanup_count == 1


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
