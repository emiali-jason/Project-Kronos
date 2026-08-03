"""Inspection-safe CAR-016 authentication lifecycle presentation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from kronos.provider.contracts.provider_authentication import (
    ProviderAuthenticationService,
)

if TYPE_CHECKING:
    from kronos.provider.kite.composition import LiveActivationContext


WINDOW_TITLE = "KRONOS — CAR-016 Authentication Inspection"
INSPECTION_NOTICE = (
    "INSPECTION ONLY — CAR-016 Version 1.0 grants no live authority. "
    "All lifecycle controls are disabled."
)
ACTIVATED_NOTICE = (
    "REVIEWED ACTIVATION CAPABILITY — no live authority is granted here. "
    "Provider availability requires separate authority."
)

CompositionFactory = Callable[
    ["LiveActivationContext"],
    ProviderAuthenticationService,
]

_ATTEMPT_STATES = frozenset(
    {
        "NONE",
        "CREATED",
        "LISTENER_READY",
        "BROWSER_OPEN_REQUESTED",
        "AWAITING_CALLBACK",
        "CALLBACK_ACCEPTED",
        "EXCHANGING",
        "BINDING_PRINCIPAL",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        "TIMED_OUT",
    }
)
_CONTEXT_STATES = frozenset({"ABSENT", "ACTIVE", "EXPIRED", "ENDED"})
_AVAILABILITY_STATES = frozenset(
    {"NOT_VERIFIED", "VERIFYING", "AVAILABLE", "UNAVAILABLE", "INDETERMINATE"}
)
_FAILURE_CODES = frozenset(
    {
        "NONE",
        "CONFIGURATION_INELIGIBLE",
        "ATTEMPT_ALREADY_ACTIVE",
        "CREDENTIAL_UNAVAILABLE",
        "LOGIN_INITIATION_FAILED",
        "CALLBACK_REJECTED",
        "CALLBACK_TIMED_OUT",
        "TOKEN_EXCHANGE_REJECTED",
        "TOKEN_EXCHANGE_UNAVAILABLE",
        "PRINCIPAL_MISMATCHED",
        "PRINCIPAL_UNCONFIRMED",
        "PRINCIPAL_BINDING_UNAVAILABLE",
        "ACCESS_TOKEN_INVALID_OR_EXPIRED",
        "PROVIDER_UNAVAILABLE",
        "ATTEMPT_TIMED_OUT",
        "LOCAL_CLEANUP_FAILED",
        "INTERNAL_FAILURE",
        "SANITIZED_LOCAL_FAILURE",
    }
)


@dataclass(frozen=True, slots=True)
class SanitizedPilotState:
    attempt: str = "NONE"
    context: str = "ABSENT"
    availability: str = "NOT_VERIFIED"
    failure: str = "NONE"

    def render(self) -> str:
        return "\n".join(
            (
                f"Authentication Attempt: {self.attempt}",
                f"Authenticated Context: {self.context}",
                f"Provider Availability: {self.availability}",
                f"Controlled outcome: {self.failure}",
            )
        )


class Car016AuthenticationPilotController:
    """Thin presentation controller consuming one injected Stage 1 capability."""

    __slots__ = (
        "__attempt",
        "__availability_authorized",
        "__closed",
        "__confirmation",
        "__functional",
        "__login_started",
        "__service",
        "__view",
        "__worker_submit",
    )

    def __init__(
        self,
        *,
        view: Any,
        worker_submit: Callable[[Callable[[], None]], None] | None = None,
        confirmation: Callable[[], bool] | None = None,
        activation: LiveActivationContext | None = None,
        composition_factory: CompositionFactory | None = None,
        availability_authorized: bool = False,
    ) -> None:
        composition_ready = (
            activation is not None
            and callable(composition_factory)
            and worker_submit is not None
            and confirmation is not None
        )
        service: ProviderAuthenticationService | None = None
        if composition_ready and composition_factory is not None:
            try:
                service = composition_factory(activation)
            except Exception:
                service = None
        del activation
        functional = service is not None
        self.__view = view
        self.__service = service if functional else None
        self.__worker_submit = worker_submit if functional else None
        self.__confirmation = confirmation if functional else None
        self.__availability_authorized = functional and availability_authorized
        self.__functional = functional
        self.__attempt: object | None = None
        self.__closed = False
        self.__login_started = False
        view.bind(self)
        view.show_state(SanitizedPilotState().render())
        if functional:
            view.set_notice(ACTIVATED_NOTICE)
            self.__set_controls(login=True)
        else:
            view.set_notice(INSPECTION_NOTICE)
            self.__set_controls()

    def login(self) -> None:
        """Begin at most one composed attempt and complete it on a worker."""

        service = self.__service
        submit = self.__worker_submit
        confirmation = self.__confirmation
        if (
            not self.__functional
            or service is None
            or submit is None
            or confirmation is None
        ):
            return
        if self.__login_started:
            return
        try:
            confirmed = confirmation()
        except Exception:
            self.__show_local_failure()
            return
        if confirmed is not True:
            return
        self.__login_started = True
        self.__set_controls()
        try:
            attempt = service.begin_login()
        except Exception:
            self.__show_local_failure()
            return
        self.__attempt = attempt
        self.refresh_state()
        try:
            submit(lambda: self.__complete_on_worker(attempt))
        except Exception:
            self.__show_local_failure()

    def cancel(self) -> None:
        """Cancel only the current non-terminal composed attempt."""

        service = self.__service
        attempt = self.__attempt
        if not self.__functional or service is None or attempt is None:
            return
        state = self.__status()
        if state is None or not state.attempt_active:
            return
        try:
            service.cancel_authentication_attempt(attempt)
        except Exception:
            self.__show_local_failure()
            return
        self.refresh_state()

    def verify_provider_availability(self) -> None:
        """Verify only with later authority and an ACTIVE context."""

        service = self.__service
        if (
            not self.__functional
            or not self.__availability_authorized
            or service is None
        ):
            return
        state = self.__status()
        if (
            state is None
            or _controlled_value(state.context_state, _CONTEXT_STATES) != "ACTIVE"
        ):
            return
        self.__set_controls()
        try:
            service.verify_provider_availability()
        except Exception:
            self.__show_local_failure()
            return
        self.refresh_state()

    def end_kronos_session(self) -> None:
        """End only an ACTIVE composed local session."""

        service = self.__service
        if not self.__functional or service is None:
            return
        state = self.__status()
        if (
            state is None
            or _controlled_value(state.context_state, _CONTEXT_STATES) != "ACTIVE"
        ):
            return
        self.__set_controls()
        try:
            service.end_kronos_session()
        except Exception:
            self.__show_local_failure()
            return
        self.refresh_state()

    def close(self) -> None:
        """Cancel a proven active attempt locally, then close the view."""

        if self.__closed:
            return
        service = self.__service
        attempt = self.__attempt
        if self.__functional and service is not None and attempt is not None:
            state = self.__status()
            if state is not None and state.attempt_active:
                try:
                    service.cancel_authentication_attempt(attempt)
                except Exception:
                    pass
        self.__closed = True
        self.__view.close()

    def refresh_state(self) -> None:
        """Render only allow-listed service projections on the view thread."""

        state = self.__status()
        if state is None:
            self.__show_local_failure()
            return
        sanitized = SanitizedPilotState(
            attempt=_controlled_value(state.attempt_state, _ATTEMPT_STATES, "NONE"),
            context=_controlled_value(state.context_state, _CONTEXT_STATES),
            availability=_controlled_value(
                state.provider_availability,
                _AVAILABILITY_STATES,
            ),
            failure=(
                "NONE"
                if state.failure_code is None
                else _controlled_value(state.failure_code, _FAILURE_CODES)
            ),
        )
        self.__view.show_state(sanitized.render())
        context_active = sanitized.context == "ACTIVE"
        attempt_active = bool(state.attempt_active)
        self.__set_controls(
            login=(self.__functional and not self.__login_started),
            cancel=(self.__functional and attempt_active),
            verify=(
                self.__functional
                and self.__availability_authorized
                and context_active
            ),
            end=(self.__functional and context_active),
        )

    def __complete_on_worker(self, attempt: object) -> None:
        service = self.__service
        if service is None:
            return
        try:
            service.complete_callback(attempt)
        except Exception:
            if not self.__closed:
                self.__view.dispatch_to_main(self.__show_local_failure)
            return
        if not self.__closed:
            self.__view.dispatch_to_main(self.refresh_state)

    def __status(self) -> Any | None:
        service = self.__service
        if service is None:
            return None
        try:
            return service.session_status()
        except Exception:
            return None

    def __show_local_failure(self) -> None:
        self.__view.show_state(
            SanitizedPilotState(
                availability="INDETERMINATE",
                failure="SANITIZED_LOCAL_FAILURE",
            ).render()
        )
        self.__set_controls()

    def __set_controls(
        self,
        *,
        login: bool = False,
        cancel: bool = False,
        verify: bool = False,
        end: bool = False,
    ) -> None:
        self.__view.set_controls(
            login=login,
            cancel=cancel,
            verify=verify,
            end=end,
        )


class _TkView:
    """Inspection-only tkinter view containing no sensitive input widgets."""

    __slots__ = (
        "__cancel",
        "__end",
        "__login",
        "__notice",
        "__root",
        "__state",
        "__verify",
    )

    def __init__(self, root: tk.Tk) -> None:
        self.__root = root
        root.title(WINDOW_TITLE)
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(
            frame,
            text="Provider Authentication and Authenticated Context Establishment",
        ).grid(row=0, column=0, columnspan=4, sticky="w")
        self.__notice = tk.StringVar(value=INSPECTION_NOTICE)
        ttk.Label(
            frame,
            textvariable=self.__notice,
            wraplength=700,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 12))
        self.__state = tk.StringVar(value=SanitizedPilotState().render())
        ttk.Label(
            frame,
            textvariable=self.__state,
            justify="left",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(0, 14))
        self.__login = ttk.Button(frame, text="Login to Kite", state="disabled")
        self.__cancel = ttk.Button(frame, text="Cancel", state="disabled")
        self.__verify = ttk.Button(
            frame,
            text="Verify Provider Availability",
            state="disabled",
        )
        self.__end = ttk.Button(
            frame,
            text="End KRONOS Session",
            state="disabled",
        )
        self.__login.grid(row=3, column=0, padx=(0, 8))
        self.__cancel.grid(row=3, column=1, padx=(0, 8))
        self.__verify.grid(row=3, column=2, padx=(0, 8))
        self.__end.grid(row=3, column=3)

    def bind(self, controller: Car016AuthenticationPilotController) -> None:
        self.__login.configure(command=controller.login)
        self.__cancel.configure(command=controller.cancel)
        self.__verify.configure(command=controller.verify_provider_availability)
        self.__end.configure(command=controller.end_kronos_session)
        self.__root.protocol("WM_DELETE_WINDOW", controller.close)

    def set_notice(self, notice: str) -> None:
        self.__notice.set(notice)

    def show_state(self, rendered: str) -> None:
        self.__state.set(rendered)

    def set_controls(
        self,
        *,
        login: bool,
        cancel: bool,
        verify: bool,
        end: bool,
    ) -> None:
        for button, enabled in (
            (self.__login, login),
            (self.__cancel, cancel),
            (self.__verify, verify),
            (self.__end, end),
        ):
            button.configure(state="normal" if enabled else "disabled")

    def dispatch_to_main(self, operation: Callable[[], None]) -> None:
        self.__root.after(0, operation)

    def close(self) -> None:
        self.__root.destroy()


def _controlled_value(
    value: object,
    allowed: frozenset[str],
    absent: str = "INDETERMINATE",
) -> str:
    if value is None:
        return absent
    candidate = value if isinstance(value, str) else getattr(value, "value", None)
    return candidate if isinstance(candidate, str) and candidate in allowed else absent


def main(
    *,
    root_factory: Callable[[], Any] = tk.Tk,
    view_factory: Callable[[Any], Any] = _TkView,
    activation: LiveActivationContext | None = None,
    composition_factory: CompositionFactory | None = None,
    worker_submit: Callable[[Callable[[], None]], None] | None = None,
    confirmation: Callable[[], bool] | None = None,
    availability_authorized: bool = False,
) -> None:
    """Open inspection mode unless reviewed activation seams are injected."""

    root = root_factory()
    view = view_factory(root)
    Car016AuthenticationPilotController(
        view=view,
        worker_submit=worker_submit,
        confirmation=confirmation,
        activation=activation,
        composition_factory=composition_factory,
        availability_authorized=availability_authorized,
    )
    root.mainloop()


if __name__ == "__main__":
    main()
