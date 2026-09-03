from __future__ import annotations

from kronos.application.intraday_runtime import create_intraday_runtime
from tests.unit.provider.test_shared_provider_runtime import _shared


def _fingerprint(root):  # type: ignore[no-untyped-def]
    if not root.exists():
        return ()
    return tuple(
        (str(path.relative_to(root)), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def test_runtime_composes_wo17_restore_only_and_provider_inert(tmp_path) -> None:
    shared, provider, factory_calls = _shared()
    root = tmp_path.resolve()

    runtime = create_intraday_runtime(shared, evidence_root=root)

    assert runtime.wo17_store.root == (
        root / "wo17-position-evidence-active-lifecycle-monitoring-v1"
    )
    assert runtime.wo17_application.store is runtime.wo17_store
    assert runtime.wo17_restored.state.value == "NOT_YET_RUN"
    assert runtime.wo17_monitoring.status_document()["bindings"] == []
    assert provider.capability.calls == 0
    assert provider.begin_count == 0
    assert factory_calls == []
    assert _fingerprint(runtime.wo17_store.root) == ()


def test_corrupt_wo17_restore_does_not_block_runtime(tmp_path) -> None:
    root = tmp_path.resolve()
    alias = root / "wo17-position-evidence-active-lifecycle-monitoring-v1" / "current"
    alias.mkdir(parents=True)
    (alias / "CURRENT-WO17-BROKEN.json").write_text("{}", encoding="utf-8")
    before = _fingerprint(alias.parent)
    shared, provider, factory_calls = _shared()

    runtime = create_intraday_runtime(shared, evidence_root=root)

    assert runtime.wo17_restored.state.value == "CORRUPT"
    assert runtime.discovery_application is not None
    assert _fingerprint(alias.parent) == before
    assert provider.capability.calls == 0
    assert factory_calls == []
