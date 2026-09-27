from pathlib import Path
import os
import json

import pytest

from kronos.browser.restart_control import (
    BACKEND_CONTROL_SCHEMA,
    BrowserBackendRestartControl,
)


def test_control_proves_only_matching_current_process_record(tmp_path: Path) -> None:
    control = BrowserBackendRestartControl.create(
        tmp_path / "browser.control",
        process_id=os.getpid(),
        token="a" * 64,
    )
    assert control.owns_current_process()
    control.path.write_text(
        f"{BACKEND_CONTROL_SCHEMA}\n{os.getpid()}\n{'b' * 64}\n",
        encoding="ascii",
    )
    assert not control.owns_current_process()
    other = BrowserBackendRestartControl(
        control.path,
        os.getpid() + 1,
        "b" * 64,
    )
    assert not other.owns_current_process()


def test_control_record_is_private_process_bound_and_removable(tmp_path) -> None:
    path = tmp_path / "runtime" / "browser.control"
    control = BrowserBackendRestartControl.create(
        path,
        process_id=4242,
        token="a" * 64,
    )

    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert path.read_text(encoding="ascii") == (
        f"{BACKEND_CONTROL_SCHEMA}\n4242\n{'a' * 64}\n"
    )
    assert control.authorized(process_id="4242", token="a" * 64)
    assert not control.authorized(process_id="4243", token="a" * 64)
    assert not control.authorized(process_id="4242", token="b" * 64)

    control.remove()
    assert not path.exists()


def test_v2_drain_handoff_requires_current_process_control_and_zero_proof(tmp_path) -> None:
    control = BrowserBackendRestartControl.create(
        tmp_path / "runtime" / "browser.control",
        process_id=os.getpid(), token="a" * 64,
    )
    drain = {name: 0 for name in (
        "coordinator_owners", "wo11_owned", "wo11_queued", "wo17_owned",
        "wo17_queued", "housekeeping_owned", "bulk_owned",
        "notification_scheduled", "monitoring_sessions", "provider_owned",
        "provider_leases",
    )}
    drain["notification_checkpoint"] = {"state": "EMPTY", "pending_count": 0,
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}
    generation = "b" * 64
    control.maintenance_drain_handoff(
        generation, "c" * 64, "d" * 40, drain
    )
    source = control.path.parent / "maintenance" / f"{generation}.json"
    document = json.loads(source.read_text())
    assert document["record"]["schema"] == "KRONOS_MAINTENANCE_HANDOFF_V2"
    assert document["record"]["drain"] == drain
    control.path.write_text("incompatible control", encoding="ascii")
    with pytest.raises(ValueError, match="MAINTENANCE_FOREIGN_PROCESS"):
        control.maintenance_drain_handoff("e" * 64, "c" * 64, "d" * 40, drain)
    assert not (control.path.parent / "maintenance" / f"{'e' * 64}.json").exists()


@pytest.mark.parametrize(
    ("process_id", "token"),
    ((1, "a" * 64), (4242, "short"), (4242, "G" * 64)),
)
def test_control_record_rejects_invalid_authority(
    tmp_path: Path,
    process_id: int,
    token: str,
) -> None:
    with pytest.raises(ValueError, match="BROWSER_BACKEND_CONTROL_INVALID"):
        BrowserBackendRestartControl.create(
            tmp_path / "browser.control",
            process_id=process_id,
            token=token,
        )
