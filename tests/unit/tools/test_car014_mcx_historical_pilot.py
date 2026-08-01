from __future__ import annotations

import ast
from dataclasses import asdict, replace
from datetime import datetime, timezone
import importlib
import logging
from pathlib import Path
import socket
from typing import Any

import pytest

from tools.provider_pilots import car014_mcx_historical_gui as gui
from tools.provider_pilots import car014_mcx_historical_pilot as pilot


_NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
_FAKE_API_KEY = "offline-fake-api-key"
_FAKE_ACCESS_TOKEN = "offline-fake-access-token"
_RAW_FAILURE = "raw-provider-detail-must-not-escape"
_ROOT = Path(__file__).resolve().parents[3]
_ENGINE_SOURCE = _ROOT / "tools/provider_pilots/car014_mcx_historical_pilot.py"
_GUI_SOURCE = _ROOT / "tools/provider_pilots/car014_mcx_historical_gui.py"


@pytest.fixture(autouse=True)
def _reset_process_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pilot, "_execution_started", False)
    monkeypatch.setattr(pilot, "_authority_consumed", False)


def _activation(**changes: object) -> pilot.LiveActivationContext:
    activation = pilot.LiveActivationContext(
        car_id="CAR-014",
        car_version="1.1",
        implementation_sha="a" * 40,
        environment_id="OFFLINE-TEST",
        authority_expiry="2026-08-03T00:00:00+00:00",
        execution_date="2026-08-02",
        historical_start="2026-08-01T09:00:00+00:00",
        historical_end="2026-08-01T10:00:00+00:00",
        timezone="UTC",
    )
    return replace(activation, **changes)


def _plan(
    activation: pilot.LiveActivationContext | None = None,
    **changes: object,
) -> pilot.ExecutionPlan:
    plan = (activation or _activation()).execution_plan()
    return replace(plan, **changes)


def _gold_record(**changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "exchange": "MCX",
        "segment": "MCX-FUT",
        "name": "GOLD",
        "tradingsymbol": "GOLD26AUGFUT",
        "instrument_type": "FUT",
        "expiry": "2026-08-31",
        "instrument_token": 101,
    }
    record.update(changes)
    return record


def _gold_option_record(
    instrument_type: str,
    *,
    segment: object = "MCX-OPT",
) -> dict[str, object]:
    return _gold_record(
        segment=segment,
        tradingsymbol=f"GOLD26AUG100000{instrument_type}",
        instrument_type=instrument_type,
        instrument_token=201 if instrument_type == "CE" else 202,
    )


def _full_mixed_instrument_payload() -> list[object]:
    return [
        _gold_record(),
        _gold_option_record("CE"),
        _gold_option_record("PE"),
        _gold_record(
            name="GOLDM",
            tradingsymbol="GOLDM26AUGFUT",
            instrument_token=301,
        ),
        _gold_record(
            name="GOLDGUINEA",
            tradingsymbol="GOLDGUINEA26AUGFUT",
            instrument_token=302,
        ),
        _gold_record(
            name="GOLDPETAL",
            tradingsymbol="GOLDPETAL26AUGFUT",
            instrument_token=303,
        ),
        _gold_record(
            name="SILVER",
            tradingsymbol="SILVER26AUGFUT",
            instrument_token=401,
        ),
        {"exchange": "MCX", "name": "CRUDEOIL"},
        "opaque-off-scope-row",
    ]


def _mixed_payload_orders() -> list[list[object]]:
    records = _full_mixed_instrument_payload()
    rotations = [
        records[index:] + records[:index]
        for index in range(len(records))
    ]
    return rotations + [
        list(reversed(records)),
        records[::2] + records[1::2],
        records[1::2] + records[::2],
    ]


def _candles() -> list[dict[str, object]]:
    return [
        {
            "date": "2026-08-01T09:00:00+00:00",
            "open": 104520,
            "high": 104890.25,
            "low": 104400,
            "close": 104800.5,
            "volume": 812,
        },
        {
            "date": "2026-08-01T09:05:00+00:00",
            "open": 104800,
            "high": 104910.75,
            "low": 104700,
            "close": 104850.25,
            "volume": 620,
        },
    ]


class _FakeAdapter:
    def __init__(
        self,
        *,
        records: object | None = None,
        candles: object | None = None,
        instrument_error: Exception | None = None,
        historical_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.records = [_gold_record()] if records is None else records
        self.candles = _candles() if candles is None else candles
        self.instrument_error = instrument_error
        self.historical_error = historical_error
        self.close_error = close_error
        self.instrument_calls = 0
        self.historical_calls = 0
        self.historical_arguments: list[tuple[int, pilot.ExecutionPlan]] = []
        self.close_calls = 0

    def instruments(self) -> object:
        self.instrument_calls += 1
        if self.instrument_error is not None:
            raise self.instrument_error
        return self.records

    def historical_data(
        self,
        instrument_token: int,
        plan: pilot.ExecutionPlan,
    ) -> object:
        self.historical_calls += 1
        self.historical_arguments.append((instrument_token, plan))
        if self.historical_error is not None:
            raise self.historical_error
        return self.candles

    def close(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


class _Factory:
    def __init__(
        self,
        adapter: _FakeAdapter | None = None,
        error: Exception | None = None,
    ) -> None:
        self.adapter = adapter or _FakeAdapter()
        self.error = error
        self.calls = 0
        self.arguments: list[tuple[str, str]] = []

    def __call__(self, api_key: str, access_token: str) -> Any:
        self.calls += 1
        self.arguments.append((api_key, access_token))
        if self.error is not None:
            raise self.error
        return self.adapter


def _engine(factory: _Factory) -> pilot.Car014PilotEngine:
    return pilot.Car014PilotEngine(
        adapter_factory=factory,
        clock=lambda: _NOW,
    )


def _execute(
    engine: pilot.Car014PilotEngine,
    *,
    activation: pilot.LiveActivationContext | None = None,
    plan: pilot.ExecutionPlan | None = None,
    api_key: str = _FAKE_API_KEY,
    access_token: str = _FAKE_ACCESS_TOKEN,
) -> pilot.PilotOutcome:
    active = activation or _activation()
    return engine.execute(
        activation=active,
        plan=plan or _plan(active),
        api_key=api_key,
        access_token=access_token,
    )


class _FakeView:
    def __init__(self) -> None:
        self.api_key = ""
        self.access_token = ""
        self.activation_enabled: bool | None = None
        self.run_enabled: bool | None = None
        self.status = ""
        self.cleared = False
        self.hidden = False
        self.disabled = False
        self.closed = False
        self.result = ""
        self.acknowledgement_only = False
        self.controller: gui.Car014PilotGuiController | None = None

    def bind(self, controller: gui.Car014PilotGuiController) -> None:
        self.controller = controller

    def set_activation_enabled(self, enabled: bool) -> None:
        self.activation_enabled = enabled
        self.run_enabled = False

    def credential_values(self) -> tuple[str, str]:
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

    def close(self) -> None:
        self.closed = True


class _FakeRoot:
    def __init__(self) -> None:
        self.mainloop_calls = 0

    def mainloop(self) -> None:
        self.mainloop_calls += 1


@pytest.mark.parametrize(
    ("activation", "plan_mutation"),
    [
        (None, None),
        (_activation(car_version="1.0"), None),
        (_activation(car_id="CAR-999"), None),
        (_activation(authority_expiry="2026-08-02T11:59:59+00:00"), None),
        (_activation(implementation_sha=""), None),
        (_activation(environment_id=""), None),
        (_activation(historical_start=""), None),
        (_activation(historical_end=""), None),
        (_activation(timezone=""), None),
        (
            _activation(
                historical_start="2026-08-01T10:00:00+00:00",
                historical_end="2026-08-01T09:00:00+00:00",
            ),
            None,
        ),
        (_activation(interval="minute"), None),
        (_activation(continuous=True), None),
        (_activation(oi=True), None),
        (
            _activation(historical_end="2026-08-01T09:30:00+00:00"),
            None,
        ),
        (_activation(), {"historical_end": "2026-08-01T09:55:00+00:00"}),
    ],
)
def test_invalid_activation_prevents_factory_and_provider_reachability(
    activation: pilot.LiveActivationContext | None,
    plan_mutation: dict[str, object] | None,
) -> None:
    factory = _Factory()
    engine = _engine(factory)
    plan = None if activation is None else _plan(activation)
    if plan is not None and plan_mutation is not None:
        plan = replace(plan, **plan_mutation)

    outcome = engine.execute(
        activation=activation,
        plan=plan,
        api_key=_FAKE_API_KEY,
        access_token=_FAKE_ACCESS_TOKEN,
    )

    assert outcome.outcome_category == pilot.LIVE_EXECUTION_NOT_AUTHORIZED
    assert outcome.stage1.initiated is False
    assert outcome.stage2.initiated is False
    assert outcome.authority_consumed is False
    assert factory.calls == 0


def test_activation_gate_rejects_naive_expiry_without_raising() -> None:
    factory = _Factory()
    engine = _engine(factory)
    activation = _activation(authority_expiry="2026-08-03T00:00:00")

    assert engine.activation_authorized(activation, _plan(activation)) is False
    assert factory.calls == 0


def test_empty_api_key_makes_zero_provider_calls() -> None:
    factory = _Factory()
    outcome = _execute(_engine(factory), api_key="")

    assert outcome.outcome_category == "CREDENTIAL_INPUT_INVALID"
    assert outcome.authority_consumed is False
    assert factory.calls == 0


def test_empty_access_token_makes_zero_provider_calls() -> None:
    factory = _Factory()
    outcome = _execute(_engine(factory), access_token="")

    assert outcome.outcome_category == "CREDENTIAL_INPUT_INVALID"
    assert outcome.authority_consumed is False
    assert factory.calls == 0


def test_authority_is_consumed_before_sdk_construction() -> None:
    adapter = _FakeAdapter()

    def factory(_api_key: str, _access_token: str) -> _FakeAdapter:
        assert pilot._execution_started is True
        assert pilot._authority_consumed is True
        return adapter

    outcome = _execute(
        pilot.Car014PilotEngine(adapter_factory=factory, clock=lambda: _NOW)
    )

    assert outcome.authority_consumed is True


def test_sdk_construction_failure_consumes_authority() -> None:
    factory = _Factory(error=RuntimeError(_RAW_FAILURE))
    outcome = _execute(_engine(factory))

    assert factory.calls == 1
    assert outcome.authority_consumed is True
    assert outcome.stage1.initiated is True
    assert outcome.stage1.completed is False
    assert outcome.stage1.outcome_category == "SDK_CONSTRUCTION_FAILURE"
    assert outcome.stage2.initiated is False
    assert _RAW_FAILURE not in repr(outcome)


def test_stage1_failure_consumes_authority_and_never_starts_stage2() -> None:
    adapter = _FakeAdapter(instrument_error=RuntimeError(_RAW_FAILURE))
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.authority_consumed is True
    assert outcome.stage1.initiated is True
    assert outcome.stage1.completed is False
    assert outcome.stage2.initiated is False
    assert adapter.instrument_calls == 1
    assert adapter.historical_calls == 0


def test_no_qualifying_contract_consumes_authority_and_blocks_stage2() -> None:
    adapter = _FakeAdapter(records=[_gold_record(name="GOLDM")])
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.authority_consumed is True
    assert outcome.stage1.outcome_category == "NO_QUALIFYING_GOLD_FUTURES"
    assert outcome.stage2.initiated is False
    assert adapter.historical_calls == 0


def test_ambiguous_selection_consumes_authority_and_blocks_stage2() -> None:
    adapter = _FakeAdapter(
        records=[_gold_record(instrument_token=101), _gold_record(instrument_token=202)]
    )
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.authority_consumed is True
    assert outcome.stage1.outcome_category == "AMBIGUOUS_GOLD_SELECTION"
    assert outcome.stage1.ambiguity_category == "SEMANTICALLY_IDENTICAL_TOKEN_VARIANTS"
    assert outcome.stage2.initiated is False


def test_second_engine_execution_is_rejected_without_factory_reentry() -> None:
    factory = _Factory()
    engine = _engine(factory)
    first = _execute(engine)
    second = _execute(engine)

    assert first.authority_consumed is True
    assert second.outcome_category == "SECOND_EXECUTION_NOT_AUTHORIZED"
    assert second.authority_consumed is True
    assert factory.calls == 1


def test_stage2_has_no_independent_public_engine_entrypoint() -> None:
    public_methods = {
        name
        for name in dir(pilot.Car014PilotEngine)
        if not name.startswith("_")
    }

    assert public_methods == {"activation_authorized", "execute"}


def test_direct_version_1_gui_launch_is_inspection_only() -> None:
    root = _FakeRoot()
    view = _FakeView()

    gui.main(
        root_factory=lambda: root,
        view_factory=lambda _root: view,
        confirmation=lambda _text: False,
    )

    assert root.mainloop_calls == 1
    assert view.activation_enabled is False
    assert view.run_enabled is False
    assert view.status == gui.INSPECTION_ONLY_STATUS


def test_opening_gui_constructs_no_adapter_factory() -> None:
    factory = _Factory()
    view = _FakeView()

    gui.Car014PilotGuiController(
        engine=_engine(factory),
        activation=None,
        plan=None,
        view=view,
        confirmation=lambda _text: True,
    )

    assert factory.calls == 0


def test_cancel_clears_credentials_and_makes_zero_provider_calls() -> None:
    factory = _Factory()
    activation = _activation()
    view = _FakeView()
    view.api_key = _FAKE_API_KEY
    view.access_token = _FAKE_ACCESS_TOKEN
    controller = gui.Car014PilotGuiController(
        engine=_engine(factory),
        activation=activation,
        plan=_plan(activation),
        view=view,
        confirmation=lambda _text: True,
    )

    controller.cancel()

    assert view.closed is True
    assert view.cleared is True
    assert factory.calls == 0


def test_rejecting_confirmation_makes_zero_provider_calls() -> None:
    factory = _Factory()
    activation = _activation()
    view = _FakeView()
    view.api_key = _FAKE_API_KEY
    view.access_token = _FAKE_ACCESS_TOKEN
    controller = gui.Car014PilotGuiController(
        engine=_engine(factory),
        activation=activation,
        plan=_plan(activation),
        view=view,
        confirmation=lambda _text: False,
    )

    controller.run_once()

    assert factory.calls == 0
    assert pilot._authority_consumed is False
    assert "NO AUTHORITY CONSUMED" in view.status


def test_gui_empty_fields_keep_run_disabled_and_make_zero_calls() -> None:
    factory = _Factory()
    activation = _activation()
    view = _FakeView()
    controller = gui.Car014PilotGuiController(
        engine=_engine(factory),
        activation=activation,
        plan=_plan(activation),
        view=view,
        confirmation=lambda _text: True,
    )

    controller.credentials_changed()
    controller.run_once()

    assert view.run_enabled is False
    assert factory.calls == 0


def test_gui_clears_and_hides_credentials_before_stage1() -> None:
    view = _FakeView()
    view.api_key = _FAKE_API_KEY
    view.access_token = _FAKE_ACCESS_TOKEN
    adapter = _FakeAdapter()

    def factory(_api_key: str, _access_token: str) -> _FakeAdapter:
        assert view.cleared is True
        assert view.hidden is True
        assert view.disabled is True
        return adapter

    activation = _activation()
    controller = gui.Car014PilotGuiController(
        engine=pilot.Car014PilotEngine(
            adapter_factory=factory,
            clock=lambda: _NOW,
        ),
        activation=activation,
        plan=_plan(activation),
        view=view,
        confirmation=lambda _text: True,
    )

    controller.run_once()

    assert view.acknowledgement_only is True
    assert view.run_enabled is False
    assert "Retry authorized: NO" in view.result


def test_reopening_gui_does_not_restore_process_authority() -> None:
    activation = _activation()
    first_factory = _Factory()
    _execute(_engine(first_factory), activation=activation)
    second_factory = _Factory()
    second_view = _FakeView()

    gui.Car014PilotGuiController(
        engine=_engine(second_factory),
        activation=activation,
        plan=_plan(activation),
        view=second_view,
        confirmation=lambda _text: True,
    )

    assert second_view.activation_enabled is False
    assert second_view.run_enabled is False
    assert second_factory.calls == 0


def test_importing_modules_invokes_no_sdk_constructor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kiteconnect

    def forbidden_constructor(**_arguments: object) -> object:
        raise AssertionError("constructor reached during import")

    monkeypatch.setattr(kiteconnect, "KiteConnect", forbidden_constructor)

    importlib.reload(pilot)
    importlib.reload(gui)


def test_modules_and_gui_emit_nothing_on_import(capsys: pytest.CaptureFixture[str]) -> None:
    importlib.reload(pilot)
    importlib.reload(gui)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_credentials_do_not_enter_output_logs_or_gui(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    view = _FakeView()
    view.api_key = _FAKE_API_KEY
    view.access_token = _FAKE_ACCESS_TOKEN
    activation = _activation()
    controller = gui.Car014PilotGuiController(
        engine=_engine(_Factory()),
        activation=activation,
        plan=_plan(activation),
        view=view,
        confirmation=lambda _text: True,
    )

    controller.run_once()

    captured = capsys.readouterr()
    combined = captured.out + captured.err + caplog.text + view.result
    assert _FAKE_API_KEY not in combined
    assert _FAKE_ACCESS_TOKEN not in combined


def test_raw_exception_never_enters_gui_result() -> None:
    view = _FakeView()
    view.api_key = _FAKE_API_KEY
    view.access_token = _FAKE_ACCESS_TOKEN
    activation = _activation()
    controller = gui.Car014PilotGuiController(
        engine=_engine(
            _Factory(
                _FakeAdapter(instrument_error=RuntimeError(_RAW_FAILURE))
            )
        ),
        activation=activation,
        plan=_plan(activation),
        view=view,
        confirmation=lambda _text: True,
    )

    controller.run_once()

    assert _RAW_FAILURE not in view.result
    assert "Traceback" not in view.result
    assert "STAGE_1_PROVIDER_FAILURE" in view.result


def test_instruments_mcx_is_invoked_exactly_once() -> None:
    adapter = _FakeAdapter()
    _execute(_engine(_Factory(adapter)))

    assert adapter.instrument_calls == 1


def test_bounded_record_iteration_does_not_repeat_endpoint_call() -> None:
    records = [
        _gold_record(name="GOLDM", tradingsymbol=f"GOLDM26{month}FUT")
        for month in ("AUG", "SEP", "OCT", "NOV")
    ] + [_gold_record()]
    adapter = _FakeAdapter(records=records)
    _execute(_engine(_Factory(adapter)))

    assert adapter.instrument_calls == 1
    assert adapter.historical_calls == 1


def test_no_retry_after_stage1_failure() -> None:
    adapter = _FakeAdapter(instrument_error=RuntimeError(_RAW_FAILURE))
    _execute(_engine(_Factory(adapter)))

    assert adapter.instrument_calls == 1
    assert adapter.historical_calls == 0


def test_exact_gold_name_and_fut_are_selected() -> None:
    outcome = _execute(_engine(_Factory()))

    assert outcome.stage1.completed is True
    assert outcome.stage1.outcome_category == "STANDARD_GOLD_FUTURE_SELECTED"
    assert outcome.stage1.selected_exchange == "MCX"
    assert outcome.stage1.selected_instrument_type == "FUT"
    assert outcome.stage1.fut_observed is True


def test_original_public_trading_symbol_is_preserved_after_normalized_match() -> None:
    adapter = _FakeAdapter(
        records=[_gold_record(tradingsymbol=" gold26augfut ")]
    )
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.selected_trading_symbol == "gold26augfut"


@pytest.mark.parametrize("variant", ["GOLDM", "GOLDGUINEA", "GOLDPETAL"])
def test_gold_variants_are_excluded(variant: str) -> None:
    adapter = _FakeAdapter(
        records=[
            _gold_record(name=variant, tradingsymbol=f"{variant}26AUGFUT")
        ]
    )
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.qualifying_record_count == 0
    assert outcome.stage2.initiated is False


@pytest.mark.parametrize("instrument_type", ["CE", "PE"])
def test_definitive_gold_options_are_cleanly_excluded(
    instrument_type: str,
) -> None:
    adapter = _FakeAdapter(records=[_gold_option_record(instrument_type)])
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == "NO_QUALIFYING_GOLD_FUTURES"
    assert outcome.stage1.definitive_option_record_count == 1
    assert outcome.stage1.target_blocking_issue_count == 0
    assert outcome.stage1.fut_observed is False
    assert outcome.stage2.initiated is False
    assert adapter.historical_calls == 0


def test_unknown_non_fut_value_is_unresolved() -> None:
    adapter = _FakeAdapter(records=[_gold_record(instrument_type="OPT")])
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == "FUTURES_CLASSIFICATION_UNRESOLVED"
    assert outcome.stage1.ambiguity_category == "NON_FUT_INSTRUMENT_TYPE"
    assert outcome.stage1.target_blocking_issue_count == 1
    assert outcome.stage2.initiated is False
    assert adapter.historical_calls == 0


@pytest.mark.parametrize("instrument_type", ["CE", "PE"])
@pytest.mark.parametrize("segment", [None, "", "MCX", "MCX-OPT", "MCX-OPTION"])
def test_gold_options_are_excluded_before_segment_and_symbol_validation(
    instrument_type: str,
    segment: object,
) -> None:
    adapter = _FakeAdapter(
        records=[
            _gold_record(),
            _gold_option_record(instrument_type, segment=segment),
        ]
    )
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == "STANDARD_GOLD_FUTURE_SELECTED"
    assert outcome.stage1.selected_trading_symbol == "GOLD26AUGFUT"
    assert outcome.stage1.definitive_option_record_count == 1
    assert outcome.stage1.target_blocking_issue_count == 0
    assert outcome.stage2.initiated is True
    assert adapter.historical_calls == 1


def test_realistic_full_mixed_payload_selects_standard_gold_future() -> None:
    adapter = _FakeAdapter(records=_full_mixed_instrument_payload())
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == "STANDARD_GOLD_FUTURE_SELECTED"
    assert outcome.stage1.selected_exchange == "MCX"
    assert outcome.stage1.selected_trading_symbol == "GOLD26AUGFUT"
    assert outcome.stage1.selected_expiry == "2026-08-31"
    assert outcome.stage1.selected_instrument_type == "FUT"
    assert outcome.stage1.definitive_option_record_count == 2
    assert outcome.stage1.excluded_variant_record_count == 3
    assert outcome.stage1.off_scope_structural_issue_count == 1
    assert outcome.stage1.target_record_count == 1
    assert outcome.stage1.target_blocking_issue_count == 0
    assert outcome.stage2.initiated is True
    assert adapter.instrument_calls == 1
    assert adapter.historical_calls == 1


def test_full_mixed_payload_is_record_order_invariant() -> None:
    results: set[tuple[object, ...]] = set()

    for records in _mixed_payload_orders():
        adapter = _FakeAdapter(records=records)
        outcome = _execute(_engine(_Factory(adapter)))
        results.add(
            (
                outcome.stage1.outcome_category,
                outcome.stage1.selected_exchange,
                outcome.stage1.selected_trading_symbol,
                outcome.stage1.selected_expiry,
                outcome.stage1.selected_instrument_type,
                outcome.stage1.definitive_option_record_count,
                outcome.stage1.excluded_variant_record_count,
                outcome.stage1.off_scope_structural_issue_count,
                adapter.historical_calls,
            )
        )
        pilot._execution_started = False
        pilot._authority_consumed = False

    assert len(_mixed_payload_orders()) == 12
    assert results == {
        (
            "STANDARD_GOLD_FUTURE_SELECTED",
            "MCX",
            "GOLD26AUGFUT",
            "2026-08-31",
            "FUT",
            2,
            3,
            1,
            1,
        )
    }


def test_expired_contract_is_excluded() -> None:
    adapter = _FakeAdapter(records=[_gold_record(expiry="2026-08-02")])
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == "NO_QUALIFYING_GOLD_FUTURES"
    assert outcome.stage2.initiated is False


@pytest.mark.parametrize(
    "missing_field",
    [
        "exchange",
        "tradingsymbol",
        "instrument_type",
        "expiry",
        "instrument_token",
    ],
)
def test_missing_required_field_blocks_selection(missing_field: str) -> None:
    record = _gold_record()
    record.pop(missing_field)
    adapter = _FakeAdapter(records=[record])
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage2.initiated is False
    assert outcome.stage1.deterministic_selection_result == "BLOCKED"


def test_missing_name_and_underlying_blocks_selection() -> None:
    record = _gold_record()
    record.pop("name")
    adapter = _FakeAdapter(records=[record])
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == "REQUIRED_FIELDS_MISSING"
    assert outcome.stage1.target_blocking_issue_count == 1
    assert outcome.stage2.initiated is False


def test_missing_instrument_type_on_exact_gold_target_blocks() -> None:
    record = _gold_record()
    record.pop("instrument_type")
    adapter = _FakeAdapter(records=[record])
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == "REQUIRED_FIELDS_MISSING"
    assert outcome.stage1.ambiguity_category == "MISSING_INSTRUMENT_TYPE"
    assert outcome.stage1.target_blocking_issue_count == 1
    assert outcome.stage2.initiated is False
    assert adapter.historical_calls == 0


def test_malformed_instrument_type_on_exact_gold_target_blocks() -> None:
    adapter = _FakeAdapter(records=[_gold_record(instrument_type=7)])
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == "FUTURES_CLASSIFICATION_UNRESOLVED"
    assert outcome.stage1.ambiguity_category == "MALFORMED_INSTRUMENT_TYPE"
    assert outcome.stage2.initiated is False


def test_conflicting_exact_gold_name_and_underlying_blocks_deterministically() -> None:
    records = [_gold_record(), _gold_record(underlying="GOLDM")]
    adapter = _FakeAdapter(records=records)
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == "STANDARD_GOLD_CLASSIFICATION_UNRESOLVED"
    assert outcome.stage1.ambiguity_category == "CONFLICTING_NAME_AND_UNDERLYING"
    assert outcome.stage1.target_blocking_issue_count == 1
    assert outcome.stage2.initiated is False


def test_target_failure_precedence_is_record_order_invariant() -> None:
    failures = [
        _gold_record(expiry="not-a-date", instrument_token=501),
        _gold_record(instrument_token="not-a-token"),
        _gold_record(segment="MCX-OPT", instrument_token=502),
        _gold_record(underlying="GOLDM", instrument_token=503),
        _gold_record(),
        {"exchange": "MCX", "name": "SILVER"},
    ]
    outcomes: set[tuple[str, str, int, bool]] = set()
    orders = [
        failures,
        list(reversed(failures)),
        failures[2:] + failures[:2],
        failures[1::2] + failures[::2],
    ]

    for records in orders:
        adapter = _FakeAdapter(records=records)
        outcome = _execute(_engine(_Factory(adapter)))
        outcomes.add(
            (
                outcome.stage1.outcome_category,
                outcome.stage1.ambiguity_category,
                outcome.stage1.target_blocking_issue_count,
                outcome.stage2.initiated,
            )
        )
        assert adapter.historical_calls == 0
        pilot._execution_started = False
        pilot._authority_consumed = False

    assert outcomes == {
        (
            "STANDARD_GOLD_CLASSIFICATION_UNRESOLVED",
            "CONFLICTING_NAME_AND_UNDERLYING",
            4,
            False,
        )
    }


def test_later_unrelated_or_valid_rows_cannot_erase_target_blocker() -> None:
    records = [
        _gold_record(expiry="not-a-date", instrument_token=501),
        {"exchange": "MCX", "name": "SILVER"},
        _gold_record(),
    ]
    adapter = _FakeAdapter(records=records)
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == "EXPIRY_PARSE_FAILED"
    assert outcome.stage1.target_blocking_issue_count == 1
    assert outcome.stage2.initiated is False
    assert adapter.historical_calls == 0


def test_unrelated_incomplete_mapping_does_not_affect_target_evidence() -> None:
    adapter = _FakeAdapter(
        records=[_gold_record(), {"exchange": "MCX", "name": "SILVER"}]
    )
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == "STANDARD_GOLD_FUTURE_SELECTED"
    assert all(dict(outcome.stage1.required_field_presence_matrix).values())
    assert outcome.stage1.target_record_count == 1
    assert outcome.stage1.target_blocking_issue_count == 0
    assert adapter.historical_calls == 1


def test_non_mapping_row_is_tolerated_and_recorded_safely() -> None:
    adapter = _FakeAdapter(records=[None, _gold_record()])
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == "STANDARD_GOLD_FUTURE_SELECTED"
    assert outcome.stage1.off_scope_structural_issue_count == 1
    assert outcome.stage1.target_blocking_issue_count == 0
    assert adapter.historical_calls == 1


def test_malformed_proven_variant_does_not_block_valid_target() -> None:
    adapter = _FakeAdapter(
        records=[
            _gold_record(),
            {"exchange": "MCX", "name": "GOLDPETAL"},
        ]
    )
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == "STANDARD_GOLD_FUTURE_SELECTED"
    assert outcome.stage1.excluded_variant_record_count == 1
    assert outcome.stage1.target_blocking_issue_count == 0
    assert adapter.historical_calls == 1


def test_unrelated_future_does_not_set_target_scoped_fut_observation() -> None:
    adapter = _FakeAdapter(
        records=[
            _gold_record(
                name="SILVER",
                tradingsymbol="SILVER26AUGFUT",
            )
        ]
    )
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == "NO_QUALIFYING_GOLD_FUTURES"
    assert outcome.stage1.fut_observed is False
    assert outcome.stage1.target_record_count == 0


def test_aggregate_evidence_contains_only_sanitized_counts() -> None:
    token = 987654321
    records = _full_mixed_instrument_payload()
    records[0] = _gold_record(instrument_token=token)
    adapter = _FakeAdapter(records=records)
    outcome = _execute(_engine(_Factory(adapter)))
    serialized = str(asdict(outcome))

    assert outcome.stage1.off_scope_structural_issue_count == 1
    assert outcome.stage1.definitive_option_record_count == 2
    assert outcome.stage1.excluded_variant_record_count == 3
    assert outcome.stage1.target_record_count == 1
    assert outcome.stage1.target_blocking_issue_count == 0
    assert str(token) not in repr(outcome)
    assert str(token) not in serialized
    assert "opaque-off-scope-row" not in repr(outcome)
    assert "opaque-off-scope-row" not in serialized


def test_unparseable_expiry_blocks_stage2() -> None:
    adapter = _FakeAdapter(records=[_gold_record(expiry="not-a-date")])
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == "EXPIRY_PARSE_FAILED"
    assert outcome.stage2.initiated is False


@pytest.mark.parametrize(
    ("changes", "category", "ambiguity"),
    [
        (
            {"segment": "MCX-OPT"},
            "STANDARD_GOLD_CLASSIFICATION_UNRESOLVED",
            "CONFLICTING_SEGMENT",
        ),
        (
            {"tradingsymbol": "GOLDM26AUGFUT"},
            "STANDARD_GOLD_CLASSIFICATION_UNRESOLVED",
            "STANDARD_VARIANT_DISTINCTION_UNRESOLVED",
        ),
        (
            {"expiry": "not-a-date"},
            "EXPIRY_PARSE_FAILED",
            "EXPIRY_PARSE_FAILED",
        ),
        (
            {"instrument_token": "not-a-token"},
            "TOKEN_REPRESENTATION_INVALID",
            "TOKEN_REPRESENTATION_INVALID",
        ),
    ],
)
def test_potential_target_failures_block_with_stable_categories(
    changes: dict[str, object],
    category: str,
    ambiguity: str,
) -> None:
    adapter = _FakeAdapter(records=[_gold_record(**changes), _gold_record()])
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.outcome_category == category
    assert outcome.stage1.ambiguity_category == ambiguity
    assert outcome.stage1.target_blocking_issue_count == 1
    assert outcome.stage2.initiated is False
    assert adapter.instrument_calls == 1
    assert adapter.historical_calls == 0


def test_earliest_expiry_is_selected() -> None:
    adapter = _FakeAdapter(
        records=[
            _gold_record(
                expiry="2026-09-30",
                tradingsymbol="GOLD26SEPFUT",
                instrument_token=202,
            ),
            _gold_record(
                expiry="2026-08-31",
                tradingsymbol="GOLD26AUGFUT",
                instrument_token=303,
            ),
        ]
    )
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.selected_trading_symbol == "GOLD26AUGFUT"


def test_trading_symbol_is_second_tie_break() -> None:
    adapter = _FakeAdapter(
        records=[
            _gold_record(tradingsymbol="GOLD26SEPFUT", instrument_token=202),
            _gold_record(tradingsymbol="GOLD26AUGFUT", instrument_token=303),
        ]
    )
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.selected_trading_symbol == "GOLD26AUGFUT"


def test_numeric_token_is_internal_final_sort_key_but_token_only_ties_block() -> None:
    source = _ENGINE_SOURCE.read_text()
    adapter = _FakeAdapter(
        records=[_gold_record(instrument_token=303), _gold_record(instrument_token=202)]
    )
    outcome = _execute(_engine(_Factory(adapter)))

    assert "candidate.token," in source
    assert outcome.stage1.ambiguity_category == "SEMANTICALLY_IDENTICAL_TOKEN_VARIANTS"
    assert outcome.stage2.initiated is False


def test_conflicting_duplicate_public_facts_block_stage2() -> None:
    adapter = _FakeAdapter(
        records=[
            _gold_record(expiry="2026-08-31", instrument_token=101),
            _gold_record(expiry="2026-09-30", instrument_token=202),
        ]
    )
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.ambiguity_category == "CONFLICTING_DUPLICATE_PUBLIC_FACTS"
    assert outcome.stage2.initiated is False


def test_raw_instrument_rows_are_absent_from_evidence() -> None:
    raw_marker = "raw-row-marker"
    adapter = _FakeAdapter(records=[_gold_record(extra=raw_marker)])
    outcome = _execute(_engine(_Factory(adapter)))

    assert raw_marker not in repr(outcome)
    assert raw_marker not in str(asdict(outcome))


def test_numeric_token_is_absent_from_evidence_repr_serialization_and_gui() -> None:
    token = 987654321
    adapter = _FakeAdapter(records=[_gold_record(instrument_token=token)])
    outcome = _execute(_engine(_Factory(adapter)))
    rendered = gui.render_sanitized_outcome(outcome)

    assert str(token) not in repr(outcome)
    assert str(token) not in str(asdict(outcome))
    assert str(token) not in rendered
    assert outcome.stage1.numeric_token_retained_in_evidence is False


def test_private_selected_contract_repr_hides_token() -> None:
    selected = pilot._SelectedContract(
        exchange="MCX",
        expiry=datetime(2026, 8, 31).date(),
        instrument_type="FUT",
        token=987654321,
        trading_symbol="GOLD26AUGFUT",
    )

    assert "987654321" not in repr(selected)


def test_historical_data_runs_once_after_valid_selection() -> None:
    adapter = _FakeAdapter()
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage2.initiated is True
    assert outcome.stage2.completed is True
    assert adapter.historical_calls == 1


def test_bounded_candle_iteration_does_not_repeat_endpoint_call() -> None:
    candles = _candles() * 20
    adapter = _FakeAdapter(candles=candles)
    _execute(_engine(_Factory(adapter)))

    assert adapter.historical_calls == 1


def test_sdk_adapter_uses_exact_frozen_historical_arguments() -> None:
    class FakeSession:
        def close(self) -> None:
            return None

    class FakeClient:
        def __init__(self) -> None:
            self.reqsession = FakeSession()
            self.calls: list[dict[str, object]] = []

        def historical_data(self, **arguments: object) -> list[object]:
            self.calls.append(arguments)
            return []

    client = FakeClient()
    adapter = pilot._PilotSdkAdapter(client)
    plan = _plan()

    adapter.historical_data(101, plan)

    assert client.calls == [
        {
            "instrument_token": 101,
            "from_date": plan.historical_start,
            "to_date": plan.historical_end,
            "interval": "5minute",
            "continuous": False,
            "oi": False,
        }
    ]


def test_sdk_adapter_hardcodes_mcx_instrument_scope() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.exchanges: list[str] = []

        def instruments(self, exchange: str) -> list[object]:
            self.exchanges.append(exchange)
            return []

    client = FakeClient()
    adapter = pilot._PilotSdkAdapter(client)

    adapter.instruments()

    assert client.exchanges == ["MCX"]


def test_exact_frozen_plan_is_used_by_engine() -> None:
    activation = _activation()
    plan = _plan(activation)
    adapter = _FakeAdapter()
    _execute(_engine(_Factory(adapter)), activation=activation, plan=plan)

    assert adapter.historical_arguments[0][1] == plan
    assert adapter.historical_arguments[0][1].interval == "5minute"
    assert adapter.historical_arguments[0][1].continuous is False
    assert adapter.historical_arguments[0][1].oi is False


def test_no_retry_after_stage2_failure() -> None:
    adapter = _FakeAdapter(historical_error=RuntimeError(_RAW_FAILURE))
    outcome = _execute(_engine(_Factory(adapter)))

    assert adapter.instrument_calls == 1
    assert adapter.historical_calls == 1
    assert outcome.stage2.outcome_category == "STAGE_2_PROVIDER_FAILURE"
    assert _RAW_FAILURE not in repr(outcome)


@pytest.mark.parametrize(
    "numeric_value",
    ["104520", "104890.25", "104400", "104800.5", "812"],
)
def test_ohlcv_numeric_values_are_absent_from_evidence_and_gui(
    numeric_value: str,
) -> None:
    outcome = _execute(_engine(_Factory()))
    combined = repr(outcome) + str(asdict(outcome)) + gui.render_sanitized_outcome(outcome)

    assert numeric_value not in combined


def test_raw_candle_rows_are_absent_from_evidence() -> None:
    candles = _candles()
    candles[0]["raw_marker"] = "raw-candle-row-marker"
    outcome = _execute(_engine(_Factory(_FakeAdapter(candles=candles))))

    assert "raw-candle-row-marker" not in repr(outcome)
    assert "raw-candle-row-marker" not in str(asdict(outcome))


def test_stage2_retains_only_sanitized_shape_and_timing_evidence() -> None:
    outcome = _execute(_engine(_Factory()))
    stage2 = outcome.stage2

    assert stage2.row_count == 2
    assert dict(stage2.key_presence_matrix) == {
        "date": True,
        "open": True,
        "high": True,
        "low": True,
        "close": True,
        "volume": True,
    }
    assert dict(stage2.value_type_matrix)["open"] == "int"
    assert dict(stage2.value_type_matrix)["high"] == "float"
    assert stage2.first_returned_timestamp == "2026-08-01T09:00:00+00:00"
    assert stage2.last_returned_timestamp == "2026-08-01T09:05:00+00:00"
    assert stage2.timezone_or_offset_observation == "UTC_OFFSET_PRESENT"
    assert stage2.chronological_order_result == "ASCENDING"
    assert stage2.duplicate_timestamp_count == 0
    assert stage2.interval_spacing_result == "EXACT_5_MINUTE"
    assert stage2.null_value_count == 0
    assert stage2.missing_value_count == 0
    assert stage2.raw_payload_discarded is True


def test_duplicate_timestamps_are_counted() -> None:
    candles = _candles()
    candles[1]["date"] = candles[0]["date"]
    outcome = _execute(_engine(_Factory(_FakeAdapter(candles=candles))))

    assert outcome.stage2.duplicate_timestamp_count == 1
    assert outcome.stage2.interval_spacing_result == "IRREGULAR"


def test_out_of_order_and_irregular_spacing_are_assessed() -> None:
    candles = _candles()
    candles.reverse()
    outcome = _execute(_engine(_Factory(_FakeAdapter(candles=candles))))

    assert outcome.stage2.chronological_order_result == "OUT_OF_ORDER"
    assert outcome.stage2.interval_spacing_result == "IRREGULAR"


def test_null_and_missing_values_are_counted() -> None:
    candles = _candles()
    candles[0]["open"] = None
    candles[1].pop("volume")
    outcome = _execute(_engine(_Factory(_FakeAdapter(candles=candles))))

    assert outcome.stage2.null_value_count == 1
    assert outcome.stage2.missing_value_count == 1


def test_oi_is_neither_requested_nor_retained_as_data() -> None:
    adapter = _FakeAdapter()
    outcome = _execute(_engine(_Factory(adapter)))

    assert adapter.historical_arguments[0][1].oi is False
    assert "oi" not in dict(outcome.stage2.key_presence_matrix)


def test_cleanup_is_attempted_exactly_once() -> None:
    adapter = _FakeAdapter()
    outcome = _execute(_engine(_Factory(adapter)))

    assert adapter.close_calls == 1
    assert outcome.local_cleanup == "SUCCESS"


def test_cleanup_failure_is_sanitized() -> None:
    adapter = _FakeAdapter(close_error=RuntimeError(_RAW_FAILURE))
    outcome = _execute(_engine(_Factory(adapter)))

    assert adapter.close_calls == 1
    assert outcome.local_cleanup == "SANITIZED_FAILURE"
    assert _RAW_FAILURE not in repr(outcome)


def test_no_network_activity_occurs_with_fakes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_socket(*_arguments: object, **_keywords: object) -> object:
        raise AssertionError("network reached")

    monkeypatch.setattr(socket, "socket", forbidden_socket)

    outcome = _execute(_engine(_Factory()))

    assert outcome.stage2.completed is True


def test_no_real_sdk_client_is_used_in_offline_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kiteconnect

    def forbidden_constructor(**_arguments: object) -> object:
        raise AssertionError("real SDK constructor reached")

    monkeypatch.setattr(kiteconnect, "KiteConnect", forbidden_constructor)

    outcome = _execute(_engine(_Factory()))

    assert outcome.stage2.completed is True


def test_pilot_adapter_exposes_only_two_operations_and_local_close() -> None:
    public_methods = {
        name
        for name, value in vars(pilot._PilotSdkAdapter).items()
        if callable(value) and not name.startswith("_")
    }

    assert public_methods == {"instruments", "historical_data", "close"}


def _called_attributes(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    return [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]


@pytest.mark.parametrize(
    "forbidden_call",
    [
        "profile",
        "login_url",
        "generate_session",
        "invalidate_access_token",
        "quote",
        "ltp",
        "ohlc",
        "connect",
        "orders",
        "trades",
        "holdings",
        "positions",
        "funds",
        "margins",
        "place_gtt",
        "modify_gtt",
        "delete_gtt",
        "place_order",
        "modify_order",
        "cancel_order",
    ],
)
def test_no_unapproved_provider_operation_is_reachable(
    forbidden_call: str,
) -> None:
    assert forbidden_call not in _called_attributes(_ENGINE_SOURCE)
    assert forbidden_call not in _called_attributes(_GUI_SOURCE)


@pytest.mark.parametrize(
    "forbidden_name",
    [
        "requests",
        "urllib",
        "httpx",
        "tenacity",
        "retrying",
        "schedule",
        "apscheduler",
        "dotenv",
        "load_dotenv",
        "pathlib",
        "pickle",
        "sqlite3",
    ],
)
def test_no_retry_polling_scheduling_network_or_persistence_dependency(
    forbidden_name: str,
) -> None:
    source = _ENGINE_SOURCE.read_text().lower() + _GUI_SOURCE.read_text().lower()
    assert forbidden_name not in source


@pytest.mark.parametrize(
    "forbidden_prompt",
    [
        "api secret",
        "request token",
        "password",
        "pin",
        "totp",
        "browser login",
    ],
)
def test_gui_does_not_request_unapproved_authentication_material(
    forbidden_prompt: str,
) -> None:
    tree = ast.parse(_GUI_SOURCE.read_text())
    executable_strings = {
        node.value.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert all(forbidden_prompt not in value for value in executable_strings)


def test_no_endpoint_call_occurs_inside_iteration() -> None:
    tree = ast.parse(_ENGINE_SOURCE.read_text())
    endpoint_names = {"instruments", "historical_data"}

    for node in ast.walk(tree):
        if not isinstance(node, (ast.For, ast.While, ast.comprehension)):
            continue
        assert all(
            not (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr in endpoint_names
            )
            for child in ast.walk(node)
        )


def test_no_while_loop_or_automation_entrypoint_exists() -> None:
    for source in (_ENGINE_SOURCE, _GUI_SOURCE):
        tree = ast.parse(source.read_text())
        assert not any(isinstance(node, ast.While) for node in ast.walk(tree))


def test_no_file_persistence_call_exists() -> None:
    forbidden_calls = {
        "open",
        "write",
        "write_text",
        "write_bytes",
        "dump",
        "dumps",
    }
    for source in (_ENGINE_SOURCE, _GUI_SOURCE):
        tree = ast.parse(source.read_text())
        names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        attributes = set(_called_attributes(source))
        assert forbidden_calls.isdisjoint(names | attributes)


def test_default_sdk_factory_is_lazy_and_called_only_from_execute() -> None:
    tree = ast.parse(_ENGINE_SOURCE.read_text())
    top_level_calls = [
        node
        for node in tree.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
    ]

    assert top_level_calls == []
    assert pilot.Car014PilotEngine().activation_authorized(None, None) is False


def test_gui_rendering_contains_only_outcome_dataclass_fields() -> None:
    outcome = _execute(_engine(_Factory()))
    rendered = gui.render_sanitized_outcome(outcome)

    assert "SDK object" not in rendered
    assert "raw-provider" not in rendered
    assert "Numeric token retained in evidence: NO" in rendered
    assert "Traceback" not in rendered


def test_gui_exposes_no_retry_action_after_execution() -> None:
    view = _FakeView()
    view.api_key = _FAKE_API_KEY
    view.access_token = _FAKE_ACCESS_TOKEN
    activation = _activation()
    controller = gui.Car014PilotGuiController(
        engine=_engine(_Factory()),
        activation=activation,
        plan=_plan(activation),
        view=view,
        confirmation=lambda _text: True,
    )

    controller.run_once()
    controller.run_once()

    assert view.acknowledgement_only is True
    assert view.run_enabled is False


def test_stage_flags_are_separate_in_sanitized_outcome() -> None:
    adapter = _FakeAdapter(historical_error=RuntimeError(_RAW_FAILURE))
    outcome = _execute(_engine(_Factory(adapter)))

    assert outcome.stage1.initiated is True
    assert outcome.stage1.completed is True
    assert outcome.stage2.initiated is True
    assert outcome.stage2.completed is False
    assert outcome.authority_consumed is True
