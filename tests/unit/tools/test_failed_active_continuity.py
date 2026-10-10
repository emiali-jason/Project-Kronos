"""Disposable retained graphs; executed only by the kernel-isolated test runner."""
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tools.failed_active_continuity import verify_continuity, main


def _root(tmp_path, family):
    paths = {
        "paper": "swing-v1/native-review/paper-observation-track-v1",
        "lifecycle": "swing-v1/native-review/active-trade-lifecycle-v0",
        "wo11": "intraday-v1/prospective-v2-wo11-lifecycle",
        "wo17": "intraday-v1/wo17-position-evidence-active-lifecycle-monitoring-v1",
        "notifications": "swing-v1/notification-centre-v1/intraday-source-references-v1",
    }
    return tmp_path / "evidence" / paths[family]


def _bytes(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _wo11(tmp_path):
    from kronos.intraday.wo11_lifecycle import arm
    from kronos.intraday.wo11_lifecycle_contract import record
    from kronos.intraday.wo11_lifecycle_store import LifecycleStore
    from tests.unit.intraday.test_wo11_lifecycle import NOW
    intake = record("WO11_INTAKE_V1", selected_at=NOW, session_close=NOW + timedelta(hours=5),
        entry_cutoff=NOW + timedelta(hours=4), subject="NSE-EQ-LUPIN", direction="LONG",
        entry="102", stop="98", target="114", opportunity_identity="ISOLATED-OPPORTUNITY",
        semantic_expression="ISOLATED-EXPRESSION", selected_lots=25, monetary_units="100", planned_rr="3")
    transition = arm(intake, truth_class="PAPER_POSITION", action_identity="ISOLATED-ACTION", action_at=NOW)
    store = LifecycleStore(_root(tmp_path, "wo11"))
    authorization = next(x for x in transition.evidence if x.schema == "WO11_AUTHORIZATION_V1")
    store.publish(transition, claim=authorization.data["claim"], previous=None, emit_notifications=False)
    return store, transition.current


def _wo17(tmp_path):
    from kronos.application.intraday_wo17 import IntradayWo17Application
    from kronos.intraday.wo17_persistence import Wo17Store
    from tests.unit.intraday.test_wo17_lifecycle import _active
    from tests.unit.intraday.test_wo17_persistence import _request
    _, position = _active(tmp_path / "fixtures")
    store = Wo17Store(_root(tmp_path, "wo17"))
    IntradayWo17Application(store=store).execute(_request(position))
    return store


def _lifecycle(tmp_path, *, active=False, closed=False):
    from kronos.swing.v1.native_active_trade_lifecycle import LocalActiveTradeLifecycleStore, ActiveTradeLifecycleEngine
    from tests.unit.swing.v1.test_native_active_trade_lifecycle import _position, _observation
    position, *_ = _position()
    store = LocalActiveTradeLifecycleStore(_root(tmp_path, "lifecycle"))
    store.retain_position(position)
    if active or closed:
        for offset, price in ((1, "99"), (2, "102")) + (((3, "130"),) if closed else ()):
            position, events, notices, closure = ActiveTradeLifecycleEngine.observe(position, _observation(position, offset, price))
            for e in events:
                store.retain_event(e)
            for n in notices:
                store.retain_notification(n)
            if closure:
                store.retain_closure(closure)
            store.retain_position(position)
    return store, position


def _paper(tmp_path, *, compact=False, historical=False):
    if compact:
        from tests.unit.application.test_paper_observation_tracking import _compact_started, _tick
        from tests.unit.swing.v1.test_paper_observation_track import NOW
        workflow, store, started, instrument = _compact_started(tmp_path / "fixtures")
        workflow.observe_tick(started.track.track_identity, _tick(instrument, started.track.observation_entry_reference - 1, 1, NOW))
        workflow.observe_tick(started.track.track_identity, _tick(instrument, started.track.observation_entry_reference + 1, 2, NOW + timedelta(seconds=1)))
        track = started.track
    elif historical:
        from tests.unit.swing.v1.test_paper_observation_track import _selected_historical_fixture
        store, track, _ = _selected_historical_fixture(tmp_path / "fixtures")
    else:
        from tests.unit.swing.v1.test_paper_observation_track import _consolidation_history
        store, track = _consolidation_history(tmp_path / "fixtures")
    target = _root(tmp_path, "paper")
    shutil.copytree(store.root, target)
    return target / track.track_identity


def test_empty_estate_is_read_only_and_deterministic(tmp_path):
    root = tmp_path / "evidence"
    first = verify_continuity(root)
    assert first == verify_continuity(root)
    assert first.owner_count == 0
    assert not root.exists()


@pytest.mark.parametrize("root", [Path("relative"), Path("/")])
def test_explicit_absolute_root_required(root):
    with pytest.raises(ValueError, match="ROOT_REQUIRED"):
        verify_continuity(root)


@pytest.mark.parametrize("builder", [_wo11, _wo17, _lifecycle, _paper])
def test_real_store_graph_validates_without_writing(tmp_path, builder):
    builder(tmp_path)
    root = tmp_path / "evidence"
    before = _bytes(root)
    proof = verify_continuity(root)
    assert proof.owner_count == 1
    assert len(proof.sha256) == 64
    assert _bytes(root) == before
    assert verify_continuity(root) == proof


@pytest.mark.parametrize("mode", ["active", "closed"])
def test_swing_active_and_closed_graphs(tmp_path, mode):
    _lifecycle(tmp_path, **{mode: True})
    assert verify_continuity(tmp_path / "evidence").owner_count == 1


@pytest.mark.parametrize("mode", ["compact", "historical"])
def test_paper_governed_representations(tmp_path, mode):
    _paper(tmp_path, **{mode: True})
    assert verify_continuity(tmp_path / "evidence").owner_count == 1


@pytest.mark.parametrize("family", ["wo11", "wo17"])
def test_deleted_current_alias_cannot_look_empty(tmp_path, family):
    {"wo11": _wo11, "wo17": _wo17}[family](tmp_path)
    for path in (_root(tmp_path, family) / "current").glob("*.json"):
        path.unlink()
    with pytest.raises(ValueError, match="ORPHAN"):
        verify_continuity(tmp_path / "evidence")


@pytest.mark.parametrize("schema", ["WO11_INTAKE_V1", "WO11_ACTION_V1", "WO11_AUTHORIZATION_V1", "WO11_TRACK_V1", "WO11_POINTER_V1"])
def test_wo11_required_record_loss_blocks(tmp_path, schema):
    store, _ = _wo11(tmp_path)
    next((store.root / "records").glob(schema + "-*.json")).unlink()
    with pytest.raises((ValueError, OSError)):
        verify_continuity(tmp_path / "evidence")


@pytest.mark.parametrize("family", ["requests", "upstream-lineages", "upstream-snapshots", "position-states", "positions", "operations", "current-snapshots"])
def test_wo17_required_record_loss_blocks(tmp_path, family):
    store = _wo17(tmp_path)
    next((store.root / family).glob("*.json")).unlink()
    with pytest.raises(Exception):
        verify_continuity(tmp_path / "evidence")


@pytest.mark.parametrize("target", ["position.json", "events", "closure.json"])
def test_swing_orphan_or_required_reference_loss_blocks(tmp_path, target):
    store, position = _lifecycle(tmp_path, closed=True)
    directory = store.root / position.position_id
    path = next((directory / target).glob("*.json")) if target == "events" else directory / target
    path.unlink()
    with pytest.raises(ValueError):
        verify_continuity(tmp_path / "evidence")


@pytest.mark.parametrize("target", ["track.json", "current-applicability.json", "current-state.json", "transitions", "applicability"])
def test_paper_missing_required_control_blocks(tmp_path, target):
    directory = _paper(tmp_path, compact=True)
    path = next((directory / target).glob("*.json")) if target in {"transitions", "applicability"} else directory / target
    path.unlink()
    with pytest.raises((ValueError, OSError)):
        verify_continuity(tmp_path / "evidence")


@pytest.mark.parametrize("family", ["wo11", "wo17", "lifecycle", "paper"])
def test_corrupt_retained_bytes_block(tmp_path, family):
    {"wo11": _wo11, "wo17": _wo17, "lifecycle": _lifecycle, "paper": _paper}[family](tmp_path)
    next(_root(tmp_path, family).rglob("*.json")).write_text('{"corrupt":true}')
    assert main(["--evidence-root", str(tmp_path / "evidence")]) == 2


def _notification(tmp_path):
    root = _root(tmp_path, "notifications")
    root.mkdir(parents=True)
    ref = {"kind": "PROBABLES", "identity": "ISOLATED-SOURCE", "received_at": "2026-10-10T00:00:00+00:00"}
    path = root / (sha256((ref["kind"] + ":" + ref["identity"]).encode()).hexdigest() + ".pending")
    path.write_text(json.dumps(ref, sort_keys=True))
    return path


def test_notification_exact_signed_checkpoint_and_digest(tmp_path):
    path = _notification(tmp_path)
    first = verify_continuity(tmp_path / "evidence")
    checkpoint = dict(state=first.notification_state, pending_count=first.notification_pending_count, sha256=first.notification_sha256)
    assert verify_continuity(tmp_path / "evidence", expected_checkpoint=checkpoint) == first
    path.rename(path.with_suffix(".done"))
    with pytest.raises(ValueError, match="CHECKPOINT_MISMATCH"):
        verify_continuity(tmp_path / "evidence", expected_checkpoint=checkpoint)
    assert verify_continuity(tmp_path / "evidence").sha256 != first.sha256


@pytest.mark.parametrize("mutation", ["missing", "corrupt", "staged", "symlink"])
def test_notification_checkpoint_loss_or_invalidity_blocks(tmp_path, mutation):
    path = _notification(tmp_path)
    proof = verify_continuity(tmp_path / "evidence")
    checkpoint = dict(state=proof.notification_state, pending_count=1, sha256=proof.notification_sha256)
    if mutation == "missing":
        path.unlink()
    elif mutation == "corrupt":
        path.write_text("{}")
    elif mutation == "staged":
        path.rename(path.with_suffix(".staged"))
    else:
        target = tmp_path / "fixture-ref"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
    with pytest.raises(ValueError):
        verify_continuity(tmp_path / "evidence", expected_checkpoint=checkpoint)


def test_changed_during_validation_blocks(tmp_path, monkeypatch):
    import tools.failed_active_continuity as helper
    _wo11(tmp_path)
    reader = helper._wo11
    def changed(root):
        count = reader(root)
        (root / "records" / "unexpected.json").write_text("{}")
        return count
    monkeypatch.setattr(helper, "_wo11", changed)
    with pytest.raises(ValueError, match="CHANGED_DURING_READ"):
        helper.verify_continuity(tmp_path / "evidence")


def test_cli_bounded_success_and_failure_output(tmp_path, capsys):
    assert main(["--evidence-root", str(tmp_path / "evidence")]) == 0
    parts = capsys.readouterr().out.strip().split()
    assert parts[:2] == ["KRONOS_CONTINUITY_V1", "VALID"]
    assert len(parts) == 3 and len(parts[2]) == 64
    assert main(["--evidence-root", str(tmp_path / "evidence"), "--checkpoint-count", "0"]) == 2
    assert capsys.readouterr().out == "KRONOS_CONTINUITY_V1 INVALID NOTIFICATION_CHECKPOINT_ARGUMENTS_INVALID\n"


def test_cli_real_subprocess(tmp_path):
    script = Path(__file__).resolve().parents[3] / "tools" / "failed_active_continuity.py"
    result = subprocess.run([sys.executable, str(script), "--evidence-root", str(tmp_path / "evidence")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("KRONOS_CONTINUITY_V1 VALID ")
    assert not (tmp_path / "evidence").exists()


@pytest.mark.parametrize("family", ["wo11", "wo17", "paper", "lifecycle"])
def test_unrecognized_nested_retained_file_cannot_escape_validation(tmp_path, family):
    {"wo11": _wo11, "wo17": _wo17, "paper": _paper, "lifecycle": _lifecycle}[family](tmp_path)
    parent = _root(tmp_path, family) / "unrecognized" / "nested"
    parent.mkdir(parents=True)
    (parent / "artifact.json").write_text("{}")
    with pytest.raises(ValueError):
        verify_continuity(tmp_path / "evidence")


def test_symlinked_owner_root_blocks(tmp_path):
    root = _root(tmp_path, "wo11")
    root.parent.mkdir(parents=True)
    target = tmp_path / "surrogate"
    target.mkdir()
    root.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="PATH_INVALID"):
        verify_continuity(tmp_path / "evidence")


def test_paper_pointer_path_traversal_blocks_before_store_read(tmp_path):
    directory = _paper(tmp_path, compact=True)
    path = directory / "current-applicability.json"
    document = json.loads(path.read_bytes())
    document["current_applicability"]["record_identity"] = "../../outside"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="REFERENCE_PATH_INVALID"):
        verify_continuity(tmp_path / "evidence")


def _wo11_active(tmp_path):
    from kronos.intraday.wo11_lifecycle import timing, observe
    from kronos.intraday.wo11_lifecycle_contract import record
    from tests.unit.intraday.test_wo11_lifecycle import NOW, observation, tick
    store, current = _wo11(tmp_path)
    claim = store.load(current.data["authorization_identity"]).data["claim"]
    qualification = record("WO11_TIMING_V1", authorization_identity=current.data["authorization_identity"],
        completed_at=NOW + timedelta(seconds=1), qualified_at=NOW + timedelta(seconds=1), qualified=True)
    transition = timing(current, qualification)
    store.publish(transition, claim=claim, previous=current.identity, emit_notifications=False)
    current = transition.current
    transition = observe(current, observation(current, tick()))
    store.publish(transition, claim=claim, previous=current.identity, emit_notifications=False)
    return store


def test_wo11_active_history_with_observations_is_read_only(tmp_path):
    _wo11_active(tmp_path)
    before = _bytes(tmp_path / "evidence")
    assert verify_continuity(tmp_path / "evidence").owner_count == 1
    assert _bytes(tmp_path / "evidence") == before


@pytest.mark.parametrize("schema", ["WO11_MARKET_OBSERVATION_V1", "WO11_TIMING_V1", "WO11_EVENT_V1", "WO11_ENTRY_V1"])
def test_wo11_active_history_required_evidence_loss_blocks(tmp_path, schema):
    store = _wo11_active(tmp_path)
    next((store.root / "records").glob(schema + "-*.json")).unlink()
    with pytest.raises((OSError, ValueError)):
        verify_continuity(tmp_path / "evidence")


@pytest.mark.parametrize("nested", [False, True])
def test_unreadable_directory_never_becomes_empty_estate(tmp_path, monkeypatch, nested):
    root = _root(tmp_path, "wo11")
    inaccessible = root / "records" if nested else root
    inaccessible.mkdir(parents=True)
    original = Path.iterdir
    def guarded(path):
        if path == inaccessible:
            raise PermissionError("ISOLATED-DENIAL")
        return original(path)
    monkeypatch.setattr(Path, "iterdir", guarded)
    assert main(["--evidence-root", str(tmp_path / "evidence")]) == 2
