"""Temporary one-attempt tkinter harness authorized only by CAR-015."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from kronos.configuration.settings import Settings
from kronos.provider.services.connectivity import KiteConnectivityService


WINDOW_TITLE = "KRONOS — CAR-015 One-Time Kite Profile Verification"
WARNING_TEXT = """This utility does not store credentials.
Running the verification consumes CAR-015 authority whether it succeeds or
fails.
No retry or second attempt is permitted.
Restarting this utility does not create new authority."""
CONFIRMATION_TEXT = """Execution consumes CAR-015 authority.
Failure also consumes CAR-015 authority.
No retry is permitted.
No second attempt is permitted.

Proceed with the one authorized profile verification?"""

_CONTROLLED_PROVIDER_ERROR_CODES = frozenset(
    {
        "CONFIGURATION_INVALID",
        "AUTHENTICATION_REJECTED",
        "ACCESS_TOKEN_INVALID_OR_EXPIRED",
        "NETWORK_TIMEOUT",
        "CONNECTION_FAILURE",
        "RATE_LIMITED",
        "PROVIDER_SERVICE_FAILURE",
        "UNEXPECTED_RESPONSE",
        "INTERNAL_ADAPTER_DEFECT",
        "SHUTDOWN_FAILURE",
    }
)
_CONTROLLED_LOCAL_ERROR_CODES = frozenset(
    {
        "LOCAL_EXECUTION_FAILURE",
        "LOCAL_SETTINGS_CONSTRUCTION_FAILURE",
        "LOCAL_SERVICE_CONSTRUCTION_FAILURE",
        "LOCAL_PROBE_FAILURE",
        "LOCAL_RESULT_SANITIZATION_FAILURE",
    }
)
_UNAVAILABLE_STATES = frozenset(
    {
        "CONFIGURATION_INVALID",
        "AUTHENTICATION_REJECTED",
        "CONTEXT_INVALID",
        "TEMPORARILY_UNAVAILABLE",
    }
)
_confirmation_presented = False
_execution_started = False
_authority_consumed = False


@dataclass(frozen=True, slots=True)
class SanitizedProfileResult:
    profile_connectivity: str
    controlled_error_code: str
    local_shutdown: str


_SettingsFactory = Callable[..., Any]
_ServiceFactory = Callable[[Any], Any]


class Car015ProfileVerificationController:
    """Pilot-local controller with injectable offline construction seams."""

    __slots__ = (
        "__confirmation",
        "__service_factory",
        "__settings_factory",
        "__view",
    )

    def __init__(
        self,
        *,
        view: Any,
        confirmation: Callable[[str], bool],
        settings_factory: _SettingsFactory = Settings,
        service_factory: _ServiceFactory = KiteConnectivityService,
    ) -> None:
        self.__view = view
        self.__confirmation = confirmation
        self.__settings_factory = settings_factory
        self.__service_factory = service_factory

        if _confirmation_presented or _execution_started or _authority_consumed:
            view.set_run_enabled(False)
            view.disable_execution_controls()
            view.clear_credentials()
            view.hide_credentials()
            view.set_status(
                "NO IN-PROCESS AUTHORITY AVAILABLE — CLOSE THIS UTILITY"
            )
            view.show_acknowledgement_only()
        else:
            view.set_run_enabled(False)
            view.set_status("ENTER BOTH EPHEMERAL CREDENTIALS LOCALLY")

    def credentials_changed(self) -> None:
        if _confirmation_presented or _execution_started or _authority_consumed:
            self.__view.set_run_enabled(False)
            return
        api_key, access_token = self.__view.credential_values()
        self.__view.set_run_enabled(bool(api_key and access_token))
        del api_key, access_token

    def cancel(self) -> None:
        if not _execution_started:
            self.__view.clear_credentials()
        self.__view.close()

    def run_once(self) -> None:
        global _authority_consumed, _confirmation_presented, _execution_started

        if _confirmation_presented or _execution_started or _authority_consumed:
            self.__view.set_run_enabled(False)
            return

        api_key, access_token = self.__view.credential_values()
        if not api_key or not access_token:
            self.__view.set_status("BOTH CREDENTIAL FIELDS ARE REQUIRED")
            self.__view.set_run_enabled(False)
            del api_key, access_token
            return
        del api_key, access_token

        _confirmation_presented = True
        try:
            confirmed = self.__confirmation(CONFIRMATION_TEXT)
        except Exception:
            confirmed = False
        if not confirmed:
            self.__view.disable_execution_controls()
            self.__view.clear_credentials()
            self.__view.hide_credentials()
            self.__view.set_status(
                "FINAL CONFIRMATION DECLINED — NO AUTHORITY CONSUMED"
            )
            self.__view.show_acknowledgement_only()
            return

        _execution_started = True
        _authority_consumed = True
        credentials: list[str] = []
        try:
            self.__view.disable_execution_controls()
            api_key, access_token = self.__view.credential_values()
            credentials.extend((api_key, access_token))
            del api_key, access_token
            self.__view.clear_credentials()
            self.__view.hide_credentials()
            self.__view.set_status("ONE-TIME PROFILE VERIFICATION IN PROGRESS")
            result = self.__execute_confirmed(credentials)
        except Exception:
            credentials.clear()
            self.__lock_consumed_view()
            result = SanitizedProfileResult(
                profile_connectivity="INDETERMINATE",
                controlled_error_code="LOCAL_EXECUTION_FAILURE",
                local_shutdown="SANITIZED FAILURE",
            )
        finally:
            credentials.clear()
            del credentials

        try:
            self.__view.show_result(render_sanitized_result(result))
            self.__view.set_status("EXECUTION COMPLETE — NO RETRY AUTHORIZED")
            self.__view.show_acknowledgement_only()
        except Exception:
            return

    def __execute_confirmed(
        self,
        credentials: list[str],
    ) -> SanitizedProfileResult:
        service: Any | None = None
        try:
            settings = self.__settings_factory(
                provider="KITE",
                kite_api_key=credentials[0],
                kite_api_secret="",
                kite_access_token=credentials[1],
                kite_redirect_url="",
            )
        except Exception:
            credentials.clear()
            return SanitizedProfileResult(
                profile_connectivity="INDETERMINATE",
                controlled_error_code="LOCAL_SETTINGS_CONSTRUCTION_FAILURE",
                local_shutdown="SANITIZED FAILURE",
            )

        try:
            service = self.__service_factory(settings)
        except Exception:
            credentials.clear()
            del settings
            return SanitizedProfileResult(
                profile_connectivity="INDETERMINATE",
                controlled_error_code="LOCAL_SERVICE_CONSTRUCTION_FAILURE",
                local_shutdown="SANITIZED FAILURE",
            )

        credentials.clear()
        del settings
        try:
            try:
                provider_result = service.probe()
            except Exception:
                connectivity = "INDETERMINATE"
                error_code = "LOCAL_PROBE_FAILURE"
            else:
                connectivity, error_code = _sanitize_probe_result(
                    provider_result
                )
                del provider_result
        finally:
            try:
                shutdown_result = service.shutdown()
            except Exception:
                shutdown = "SANITIZED FAILURE"
            else:
                shutdown = _sanitize_shutdown_result(shutdown_result)
                del shutdown_result
            service = None

        return SanitizedProfileResult(
            profile_connectivity=connectivity,
            controlled_error_code=error_code,
            local_shutdown=shutdown,
        )

    def __lock_consumed_view(self) -> None:
        for operation in (
            self.__view.disable_execution_controls,
            self.__view.clear_credentials,
            self.__view.hide_credentials,
        ):
            try:
                operation()
            except Exception:
                continue


def render_sanitized_result(result: SanitizedProfileResult) -> str:
    connectivity = (
        result.profile_connectivity
        if result.profile_connectivity
        in {"AVAILABLE", "UNAVAILABLE", "INDETERMINATE"}
        else "INDETERMINATE"
    )
    error_code = (
        result.controlled_error_code
        if result.controlled_error_code == "NONE"
        or result.controlled_error_code in _CONTROLLED_PROVIDER_ERROR_CODES
        or result.controlled_error_code in _CONTROLLED_LOCAL_ERROR_CODES
        else "LOCAL_RESULT_SANITIZATION_FAILURE"
    )
    shutdown = (
        result.local_shutdown
        if result.local_shutdown in {"SUCCESS", "SANITIZED FAILURE"}
        else "SANITIZED FAILURE"
    )
    return "\n".join(
        (
            f"Profile connectivity: {connectivity}",
            f"Controlled error code: {error_code}",
            f"Local shutdown: {shutdown}",
            "CAR-015 authority: CONSUMED",
        )
    )


def _sanitize_probe_result(result: object) -> tuple[str, str]:
    state = _enum_value(_safe_attribute(result, "state"))
    error_code = _enum_value(_safe_attribute(result, "error_code"))
    sanitized_error = (
        error_code if error_code in _CONTROLLED_PROVIDER_ERROR_CODES else "NONE"
    )
    if state == "AVAILABLE" and sanitized_error == "NONE":
        return "AVAILABLE", "NONE"
    if state in _UNAVAILABLE_STATES:
        return "UNAVAILABLE", sanitized_error
    return "INDETERMINATE", sanitized_error


def _sanitize_shutdown_result(result: object) -> str:
    error = _safe_attribute(result, "error_code")
    return "SUCCESS" if error is None else "SANITIZED FAILURE"


def _safe_attribute(value: object, name: str) -> object:
    try:
        return getattr(value, name)
    except Exception:
        return object()


def _enum_value(value: object) -> str | None:
    try:
        candidate = getattr(value, "value")
    except Exception:
        return None
    return candidate if isinstance(candidate, str) else None


class _TkView:
    __slots__ = (
        "__access_token",
        "__api_entry",
        "__api_key",
        "__cancel_button",
        "__credential_frame",
        "__result",
        "__root",
        "__run_button",
        "__status",
        "__token_entry",
    )

    def __init__(self, root: tk.Tk) -> None:
        self.__root = root
        root.title(WINDOW_TITLE)
        root.resizable(False, False)

        frame = ttk.Frame(root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(frame, text=WARNING_TEXT, wraplength=660).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 12),
        )

        self.__credential_frame = ttk.LabelFrame(
            frame,
            text="Ephemeral local credentials",
            padding=10,
        )
        self.__credential_frame.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
        )
        self.__api_key = tk.StringVar()
        self.__access_token = tk.StringVar()

        ttk.Label(self.__credential_frame, text="Kite API key").grid(
            row=0,
            column=0,
            sticky="w",
        )
        self.__api_entry = ttk.Entry(
            self.__credential_frame,
            textvariable=self.__api_key,
            show="*",
            width=58,
        )
        self.__api_entry.grid(row=0, column=1, padx=(8, 0))

        ttk.Label(
            self.__credential_frame,
            text="Newly obtained Kite access token",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.__token_entry = ttk.Entry(
            self.__credential_frame,
            textvariable=self.__access_token,
            show="*",
            width=58,
        )
        self.__token_entry.grid(row=1, column=1, padx=(8, 0), pady=(8, 0))

        self.__status = tk.StringVar()
        ttk.Label(frame, textvariable=self.__status, wraplength=660).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(12, 8),
        )

        self.__run_button = ttk.Button(
            frame,
            text="Run One-Time Profile Verification",
            state="disabled",
        )
        self.__run_button.grid(row=3, column=0, sticky="w")
        self.__cancel_button = ttk.Button(frame, text="Cancel")
        self.__cancel_button.grid(row=3, column=1, sticky="e")

        self.__result = tk.Text(frame, width=82, height=8, state="disabled")
        self.__result.grid(row=4, column=0, columnspan=2, pady=(12, 0))

    def bind(self, controller: Car015ProfileVerificationController) -> None:
        self.__run_button.configure(command=controller.run_once)
        self.__cancel_button.configure(command=controller.cancel)
        self.__api_key.trace_add(
            "write",
            lambda *_arguments: controller.credentials_changed(),
        )
        self.__access_token.trace_add(
            "write",
            lambda *_arguments: controller.credentials_changed(),
        )

    def credential_values(self) -> tuple[str, str]:
        return self.__api_key.get(), self.__access_token.get()

    def set_run_enabled(self, enabled: bool) -> None:
        self.__run_button.configure(state="normal" if enabled else "disabled")

    def set_status(self, status: str) -> None:
        self.__status.set(status)

    def clear_credentials(self) -> None:
        self.__api_key.set("")
        self.__access_token.set("")

    def hide_credentials(self) -> None:
        self.__credential_frame.grid_remove()

    def disable_execution_controls(self) -> None:
        self.set_run_enabled(False)
        self.__api_entry.configure(state="disabled")
        self.__token_entry.configure(state="disabled")

    def show_result(self, rendered: str) -> None:
        self.__result.configure(state="normal")
        self.__result.delete("1.0", "end")
        self.__result.insert("1.0", rendered)
        self.__result.configure(state="disabled")

    def show_acknowledgement_only(self) -> None:
        self.__run_button.grid_remove()
        self.__cancel_button.configure(text="Acknowledge and Close")

    def close(self) -> None:
        self.__root.destroy()


def main(
    *,
    root_factory: Callable[[], Any] = tk.Tk,
    view_factory: Callable[[Any], Any] = _TkView,
    confirmation: Callable[[str], bool] | None = None,
    settings_factory: _SettingsFactory = Settings,
    service_factory: _ServiceFactory = KiteConnectivityService,
) -> None:
    root = root_factory()
    view = view_factory(root)
    controller = Car015ProfileVerificationController(
        view=view,
        confirmation=confirmation
        or (
            lambda text: messagebox.askyesno(
                "Confirm CAR-015 execution",
                text,
            )
        ),
        settings_factory=settings_factory,
        service_factory=service_factory,
    )
    view.bind(controller)
    root.mainloop()


if __name__ == "__main__":
    main()
