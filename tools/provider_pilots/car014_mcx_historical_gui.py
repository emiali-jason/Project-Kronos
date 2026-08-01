"""Inspection-first tkinter interface for the CAR-014 pilot-local engine."""

from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from tools.provider_pilots.car014_mcx_historical_pilot import (
    Car014PilotEngine,
    ExecutionPlan,
    LiveActivationContext,
    PilotOutcome,
)


WINDOW_TITLE = "KRONOS — CAR-014 MCX GOLD Historical Verification Pilot"
INSPECTION_ONLY_STATUS = (
    "LIVE EXECUTION NOT AUTHORIZED — CAR-014 VERSION 1.1 REQUIRED"
)
_CONFIRMATION_TEXT = (
    "Beginning Stage 1 consumes the combined CAR-014 authority even if "
    "Stage 1 or Stage 2 fails. No retry or second attempt is permitted. "
    "Proceed with the one authorized execution?"
)


class Car014PilotGuiController:
    """Small controller with pilot-local view and confirmation seams."""

    __slots__ = (
        "__activation",
        "__confirmation",
        "__engine",
        "__execution_started",
        "__plan",
        "__view",
    )

    def __init__(
        self,
        *,
        engine: Car014PilotEngine,
        activation: LiveActivationContext | None,
        plan: ExecutionPlan | None,
        view: Any,
        confirmation: Callable[[str], bool],
    ) -> None:
        self.__engine = engine
        self.__activation = activation
        self.__plan = plan
        self.__view = view
        self.__confirmation = confirmation
        self.__execution_started = False

        if engine.activation_authorized(activation, plan):
            view.set_activation_enabled(True)
            view.set_status(
                "ACTIVATION CONTEXT VALID — ENTER CREDENTIALS LOCALLY"
            )
            self.credentials_changed()
        else:
            view.set_activation_enabled(False)
            view.set_status(INSPECTION_ONLY_STATUS)

    def credentials_changed(self) -> None:
        if self.__execution_started:
            self.__view.set_run_enabled(False)
            return
        api_key, access_token = self.__view.credential_values()
        self.__view.set_run_enabled(bool(api_key and access_token))
        del api_key, access_token

    def cancel(self) -> None:
        if not self.__execution_started:
            self.__view.clear_credentials()
        self.__view.close()

    def run_once(self) -> None:
        if self.__execution_started:
            return
        if not self.__engine.activation_authorized(
            self.__activation,
            self.__plan,
        ):
            self.__view.set_activation_enabled(False)
            self.__view.set_status(INSPECTION_ONLY_STATUS)
            return

        api_key, access_token = self.__view.credential_values()
        if not api_key or not access_token:
            self.__view.set_status("BOTH CREDENTIAL FIELDS ARE REQUIRED")
            self.__view.set_run_enabled(False)
            del api_key, access_token
            return
        del api_key, access_token

        if not self.__confirmation(_CONFIRMATION_TEXT):
            self.__view.set_status("EXECUTION CANCELLED — NO AUTHORITY CONSUMED")
            return

        self.__execution_started = True
        self.__view.disable_execution_controls()
        api_key, access_token = self.__view.credential_values()
        self.__view.clear_credentials()
        self.__view.hide_credentials()
        self.__view.set_status("ONE-TIME EXECUTION IN PROGRESS")

        try:
            outcome = self.__engine.execute(
                activation=self.__activation,
                plan=self.__plan,
                api_key=api_key,
                access_token=access_token,
            )
        except Exception:
            rendered = (
                "Overall outcome: LOCAL_GUI_FAILURE\n"
                "Stage 1 initiated: INDETERMINATE\n"
                "Stage 2 initiated: NO\n"
                "CAR-014 authority: CONSUMED\n"
                "Local cleanup: SANITIZED FAILURE"
            )
        else:
            rendered = render_sanitized_outcome(outcome)
        finally:
            del api_key, access_token

        self.__view.show_result(rendered)
        self.__view.set_status("EXECUTION COMPLETE — NO RETRY AUTHORIZED")
        self.__view.show_acknowledgement_only()


def render_sanitized_outcome(outcome: PilotOutcome) -> str:
    stage1 = outcome.stage1
    stage2 = outcome.stage2
    stage1_presence = _render_matrix(stage1.required_field_presence_matrix)
    stage2_presence = _render_matrix(stage2.key_presence_matrix)
    stage2_types = _render_matrix(stage2.value_type_matrix)
    return "\n".join(
        (
            f"Overall outcome: {outcome.outcome_category}",
            f"Stage 1 initiated: {_yes_no(stage1.initiated)}",
            f"Stage 1 completed: {_yes_no(stage1.completed)}",
            f"Stage 1 outcome: {stage1.outcome_category}",
            f"Total Instrument Master records: {stage1.total_record_count}",
            f"Qualifying records: {stage1.qualifying_record_count}",
            f"Required-field presence: {stage1_presence}",
            f"Expected futures value: {stage1.expected_futures_value}",
            f"Exact FUT observed: {_yes_no(stage1.fut_observed)}",
            f"Expiry representation: {stage1.expiry_representation_type}",
            f"Token representation: {stage1.token_representation_type}",
            f"Selected exchange: {stage1.selected_exchange}",
            f"Selected trading symbol: {stage1.selected_trading_symbol}",
            f"Selected expiry: {stage1.selected_expiry}",
            f"Selected instrument type: {stage1.selected_instrument_type}",
            f"Selection result: {stage1.deterministic_selection_result}",
            f"Ambiguity category: {stage1.ambiguity_category}",
            f"Instrument payload discarded: {_yes_no(stage1.payload_discarded)}",
            "Numeric token retained in evidence: NO",
            f"Stage 2 initiated: {_yes_no(stage2.initiated)}",
            f"Stage 2 completed: {_yes_no(stage2.completed)}",
            f"Stage 2 outcome: {stage2.outcome_category}",
            f"Requested interval: {stage2.requested_interval}",
            f"Historical start: {stage2.historical_start}",
            f"Historical end: {stage2.historical_end}",
            f"Timezone: {stage2.timezone}",
            f"Continuous: {_yes_no(stage2.continuous)}",
            f"OI requested: {_yes_no(stage2.oi)}",
            f"Candle row count: {stage2.row_count}",
            f"Candle key presence: {stage2_presence}",
            f"Candle value types: {stage2_types}",
            f"First returned timestamp: {stage2.first_returned_timestamp}",
            f"Last returned timestamp: {stage2.last_returned_timestamp}",
            (
                "Timezone or offset observation: "
                f"{stage2.timezone_or_offset_observation}"
            ),
            f"Chronological ordering: {stage2.chronological_order_result}",
            f"Duplicate timestamps: {stage2.duplicate_timestamp_count}",
            f"Interval spacing: {stage2.interval_spacing_result}",
            f"Null values: {stage2.null_value_count}",
            f"Missing values: {stage2.missing_value_count}",
            (
                "Historical payload discarded: "
                f"{_yes_no(stage2.raw_payload_discarded)}"
            ),
            f"CAR-014 authority: {'CONSUMED' if outcome.authority_consumed else 'NOT CONSUMED'}",
            f"Local cleanup: {outcome.local_cleanup}",
            "Retry authorized: NO",
        )
    )


class _TkView:
    __slots__ = (
        "__access_token",
        "__api_key",
        "__cancel_button",
        "__credential_frame",
        "__result",
        "__root",
        "__run_button",
        "__status",
    )

    def __init__(self, root: tk.Tk) -> None:
        self.__root = root
        root.title(WINDOW_TITLE)
        root.resizable(False, False)

        frame = ttk.Frame(root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(
            frame,
            text=(
                "Stage 1: One MCX Instrument Master request and deterministic "
                "in-memory standard GOLD futures selection."
            ),
            wraplength=680,
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            frame,
            text=(
                "Stage 2: One 5-minute historical-data request for the frozen "
                "completed 60-minute window."
            ),
            wraplength=680,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Label(
            frame,
            text=(
                "One combined authority is consumed when Stage 1 begins. "
                "Stage 2 runs only after deterministic Stage 1 success. No "
                "retry is permitted. Raw payloads and the numeric token are "
                "not retained. Restarting this utility creates no new authority."
            ),
            wraplength=680,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 12))

        self.__credential_frame = ttk.LabelFrame(
            frame,
            text="Local credentials",
            padding=10,
        )
        self.__credential_frame.grid(
            row=3,
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
        api_entry = ttk.Entry(
            self.__credential_frame,
            textvariable=self.__api_key,
            show="*",
            width=58,
        )
        api_entry.grid(row=0, column=1, padx=(8, 0))
        ttk.Label(self.__credential_frame, text="Existing Kite access token").grid(
            row=1,
            column=0,
            sticky="w",
            pady=(8, 0),
        )
        token_entry = ttk.Entry(
            self.__credential_frame,
            textvariable=self.__access_token,
            show="*",
            width=58,
        )
        token_entry.grid(row=1, column=1, padx=(8, 0), pady=(8, 0))

        self.__status = tk.StringVar()
        ttk.Label(
            frame,
            textvariable=self.__status,
            wraplength=680,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 8))

        self.__run_button = ttk.Button(frame, text="Run Combined One-Time Test")
        self.__run_button.grid(row=5, column=0, sticky="w")
        self.__cancel_button = ttk.Button(frame, text="Cancel")
        self.__cancel_button.grid(row=5, column=1, sticky="e")

        self.__result = tk.Text(frame, width=88, height=28, state="disabled")
        self.__result.grid(row=6, column=0, columnspan=2, pady=(12, 0))

    def bind(self, controller: Car014PilotGuiController) -> None:
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

    def set_activation_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for child in self.__credential_frame.winfo_children():
            if isinstance(child, ttk.Entry):
                child.configure(state=state)
        self.set_run_enabled(False)

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
        for child in self.__credential_frame.winfo_children():
            if isinstance(child, ttk.Entry):
                child.configure(state="disabled")

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


def _render_matrix(matrix: tuple[tuple[str, object], ...]) -> str:
    if not matrix:
        return "NONE"
    return ", ".join(f"{key}={value}" for key, value in matrix)


def _yes_no(value: bool) -> str:
    return "YES" if value else "NO"


def main(
    *,
    activation: LiveActivationContext | None = None,
    plan: ExecutionPlan | None = None,
    engine: Car014PilotEngine | None = None,
    root_factory: Callable[[], Any] = tk.Tk,
    view_factory: Callable[[Any], Any] = _TkView,
    confirmation: Callable[[str], bool] | None = None,
) -> None:
    root = root_factory()
    view = view_factory(root)
    controller = Car014PilotGuiController(
        engine=engine or Car014PilotEngine(),
        activation=activation,
        plan=plan,
        view=view,
        confirmation=confirmation
        or (lambda text: messagebox.askyesno("Confirm CAR-014 execution", text)),
    )
    view.bind(controller)
    root.mainloop()


if __name__ == "__main__":
    main()
