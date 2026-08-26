from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from kronos.intraday.probables_refresh_persistence import (
    RefreshOperationalStateError,
    RefreshOperationalStateStore,
    create_refresh_operational_state,
)


IST = ZoneInfo("Asia/Kolkata")
BOUNDARY = datetime(2026, 8, 24, 11, 17, tzinfo=IST)


def _state(*, failure: str | None = None):  # type: ignore[no-untyped-def]
    return create_refresh_operational_state(
        operation_identity="KRONOS-INTRADAY-DISCOVERY-OPERATION-WO06VA",
        observation_boundary=BOUNDARY,
        completed_at=BOUNDARY + timedelta(seconds=1),
        last_successful_discovery_run_identity="INTRADAY-DISCOVERY-RUN-A",
        last_successful_probables_run_identity="INTRADAY-PROBABLES-RUN-A",
        current_failure_stage=None if failure is None else "PROBABLES_INVOCATION",
        current_failure=failure,
    )


def test_explicit_current_state_reload_retains_both_run_identities(
    tmp_path: Path,
) -> None:
    store = RefreshOperationalStateStore(tmp_path.resolve())
    state = _state()

    retained = store.retain(state)

    assert retained.name == f"{state.state_identity}.json"
    assert store.load(state_identity=state.state_identity) == state
    assert store.load_current() == state
    assert store.retain(state) == retained


def test_later_failure_preserves_last_successful_identities(
    tmp_path: Path,
) -> None:
    store = RefreshOperationalStateStore(tmp_path.resolve())
    success = _state()
    failed = _state(failure="PROBABLES_REFRESH_FAILURE")

    store.retain(success)
    store.retain(failed)

    assert store.load(state_identity=success.state_identity) == success
    assert store.load_current() == failed
    assert failed.last_successful_discovery_run_identity == (
        success.last_successful_discovery_run_identity
    )
    assert failed.last_successful_probables_run_identity == (
        success.last_successful_probables_run_identity
    )


def test_current_pointer_tampering_fails_closed(tmp_path: Path) -> None:
    store = RefreshOperationalStateStore(tmp_path.resolve())
    store.retain(_state())
    pointer = tmp_path / "refresh-v1" / "current-state.json"
    pointer.write_text("{}\n", encoding="utf-8")

    with pytest.raises(
        RefreshOperationalStateError,
        match="INTRADAY_REFRESH_POINTER_INVALID",
    ):
        store.load_current()
