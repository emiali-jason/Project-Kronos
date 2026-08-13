from pathlib import Path

import pytest

from kronos.browser.restart_control import (
    BACKEND_CONTROL_SCHEMA,
    BrowserBackendRestartControl,
)


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
