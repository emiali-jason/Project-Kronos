#!/usr/bin/env python3
"""Read-only retained-owner proof for ADR-0061 failed-active retirement.

Explicit roots only. This is neither operational restoration nor a drain proof:
the launcher must separately fence/count/drain and verify the signed V2 handoff.
Run before shutdown and again after exit, with the signed notification checkpoint.
Final writes may change the digest between those two independently valid reads.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import stat
import sys
from threading import RLock
from types import SimpleNamespace

# Direct launcher execution does not depend on inherited PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class ContinuityError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ContinuityError(code)


@dataclass(frozen=True)
class ContinuityProof:
    sha256: str
    owner_count: int
    notification_state: str
    notification_pending_count: int
    notification_sha256: str


def _inventory(roots):
    """Bind every retained byte and reject links/special files and interrupted writes."""
    def entries(directory):
        # Unlike glob/rglob, iterdir propagates unreadable-directory errors.
        # An uninspectable retained subtree must never become an empty estate.
        for path in sorted(directory.iterdir()):
            mode = path.lstat().st_mode
            require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), "CONTINUITY_PATH_INVALID")
            yield path, mode
            if stat.S_ISDIR(mode):
                yield from entries(path)

    result = []
    for label, root in roots.items():
        for parent in (root, *root.parents):
            try:
                require(not stat.S_ISLNK(parent.lstat().st_mode), "CONTINUITY_PATH_INVALID")
            except FileNotFoundError:
                pass
        try:
            mode = root.lstat().st_mode
        except FileNotFoundError:
            result.append((label, None))
            continue
        require(stat.S_ISDIR(mode), "CONTINUITY_PATH_INVALID")
        for path, mode in entries(root):
            relative = path.relative_to(root).as_posix()
            if stat.S_ISDIR(mode):
                result.append((label + "/" + relative + "/", None))
                continue
            # Existing WO11 flock file has no durable business authority.
            if label == "wo11" and relative == ".operation.lock":
                continue
            require(path.suffix in {".json", ".pending", ".done"}, "CONTINUITY_UNRECOGNIZED_FILE")
            digest = sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            result.append((label + "/" + relative, digest.hexdigest()))
    return tuple(result)


def _wo11(root):
    from kronos.intraday.wo11_lifecycle_store import LifecycleStore
    from kronos.intraday.wo11_lifecycle_contract import LifecycleRecord, digest, require as schema
    store = LifecycleStore(root)
    records = {path.stem: store.load(path.stem) for path in (root / "records").glob("*.json")}
    facts = {(r.data["authorization_identity"], r.data["fact_identity"])
             for r in records.values() if r.schema == "WO11_MARKET_OBSERVATION_V1"}
    current = store.restore()
    claims = {}
    for path in (root / "current").glob("*.json"):
        pointer = LifecycleRecord(**json.loads(path.read_bytes()))
        d = schema(pointer, "WO11_POINTER_V1")
        require(path.stem == digest(d["claim"]) and records.get(pointer.identity) == pointer,
                "WO11_RETAINED_POINTER_MISSING")
        claims[digest(d["claim"])] = d["claim"]
    for item in records.values():
        data = item.data
        for field in ("authorization_identity", "intake_identity", "current_identity"):
            if data.get(field) is not None:
                store.load(data[field])
        if item.schema == "WO11_AUTHORIZATION_V1":
            require(digest(item.data["claim"]) in claims, "WO11_ORPHAN_AUTHORIZATION")
        if item.schema == "WO11_TRACK_V1":
            authorization = store.load(item.data["authorization_identity"])
            claim = authorization.data["claim"]
            require(digest(claim) in claims, "WO11_ORPHAN_TRACK")
            store._validate_track_graph(item, claim)
            require(all((item.data["authorization_identity"], identity) in facts
                        for identity in item.data["observations"]), "WO11_SOURCE_FACT_MISSING")
            require(all((item.data["authorization_identity"], sample["fact_identity"]) in facts
                        for sample in item.data["samples"]), "WO11_SOURCE_FACT_MISSING")
        if item.schema == "WO11_POINTER_V1":
            d = item.data
            require(digest(d["claim"]) in claims, "WO11_ORPHAN_POINTER")
            target = store.load(d["current_identity"])
            require(d["previous"] == target.data["predecessor"], "WO11_POINTER_PREDECESSOR_MISMATCH")
            store._validate_track_graph(target, d["claim"])
            if d["previous"] is not None:
                store.load(d["previous"])
    expected = {root / "records" / (identity + ".json") for identity in records}
    expected.update((root / "current").glob("*.json"))
    require({p for p in root.rglob("*") if p.is_file() and p != root / ".operation.lock"}
            == expected, "WO11_LAYOUT_INVALID")
    return len(current)


def _wo17(root):
    from kronos.intraday.wo17_persistence import Wo17Store
    store = Wo17Store(root)
    restored = store.restore_all()
    subjects = set(store.current_subjects())
    # The codec's generic artifact identity can be a request reference for a
    # pointer/operation; filenames bind the owning family's identity instead.
    identity_fields = {
        "requests": "request_identity", "upstream-lineages": "lineage_identity",
        "upstream-snapshots": "snapshot_identity", "position-states": "state_identity",
        "positions": "position_identity", "entry-observations": "observation_identity",
        "live-entry-attestations": "attestation_identity", "pre-entry-invalidations": "fact_identity",
        "lifecycle-states": "state_identity", "lifecycle-observations": "observation_identity",
        "lifecycle-assessments": "assessment_identity", "session-end-facts": "fact_identity",
        "closure-states": "state_identity", "live-exit-attestations": "attestation_identity",
        "closures": "closure_identity", "events": "event_identity", "operations": "operation_identity",
        "invalid": "invalid_identity", "successors": "lineage_identity", "current-snapshots": "pointer_identity",
    }
    expected = set()
    for family in store._FAMILIES:
        for path in (root / family).glob("*.json"):
            value = store._load(family, path.stem)
            require(getattr(value, identity_fields[family], None) == path.stem, "WO17_ARTIFACT_PATH_MISMATCH")
            expected.add(path)
            if family == "current-snapshots":
                require(value.canonical_subject_identity in subjects, "WO17_ORPHAN_POINTER")
                store.restore_pointer(value)
                if value.predecessor_pointer_identity is not None:
                    predecessor = store.load_pointer_snapshot(value.predecessor_pointer_identity)
                    require(predecessor.canonical_subject_identity == value.canonical_subject_identity,
                            "WO17_PREDECESSOR_BINDING_INVALID")
            if family == "position-states":
                require(value.upstream_snapshot.lineage.canonical_subject_identity in subjects,
                        "WO17_ORPHAN_POSITION")
            if family == "positions":
                require(value.canonical_subject_identity in subjects, "WO17_ORPHAN_POSITION")
            if family in {"lifecycle-states", "closure-states"}:
                require(value.position.upstream_snapshot.lineage.canonical_subject_identity in subjects,
                        "WO17_ORPHAN_LIFECYCLE")
    for subject in store.failure_subjects():
        value = store.load_latest_failure(subject)
        require(store._load("invalid", value.invalid_identity) == value, "WO17_FAILURE_REFERENCE_INVALID")
    aliases = {store._current_path(s) for s in subjects} | {
        store._failure_path(s) for s in store.failure_subjects()}
    require(set((root / "current").glob("*.json")) == aliases, "WO17_ALIAS_INVALID")
    require({p for p in root.rglob("*") if p.is_file()} == expected | aliases, "WO17_LAYOUT_INVALID")
    return len(restored)


def _swing_lifecycle(root):
    from kronos.swing.v1.native_active_trade_lifecycle import LocalActiveTradeLifecycleStore, ActiveLifecycleState
    snapshot = LocalActiveTradeLifecycleStore(root).load()
    positions = {p.position_id: p for p in snapshot.positions}
    events = {e.event_id: e for e in snapshot.events}
    notices = {n.notification_id: n for n in snapshot.notifications}
    closures = {c.position_id: c for c in snapshot.closures}
    require(len(positions) == len(snapshot.positions) and len(events) == len(snapshot.events)
            and len(notices) == len(snapshot.notifications) and len(closures) == len(snapshot.closures),
            "SWING_LIFECYCLE_DUPLICATE")
    expected = set()
    for p in positions.values():
        expected.add(root / p.position_id / "position.json")
        require(all(e in events and events[e].position_id == p.position_id for e in p.lifecycle_event_ids),
                "SWING_LIFECYCLE_EVENT_MISSING")
        require(all(n in notices and notices[n].position_id == p.position_id for n in p.outstanding_notification_ids),
                "SWING_LIFECYCLE_NOTIFICATION_MISSING")
        require((p.state is ActiveLifecycleState.CLOSED) == (p.position_id in closures),
                "SWING_LIFECYCLE_CLOSURE_MISSING")
    for e in snapshot.events:
        p = positions.get(e.position_id)
        require(p is not None and e.event_id in p.lifecycle_event_ids
                and (e.decision_id, e.trade_plan_id, e.trade_plan_hash, e.mode, e.instrument, e.direction)
                == (p.decision_id, p.trade_plan_id, p.trade_plan_hash, p.mode, p.canonical_instrument, p.direction),
                "SWING_LIFECYCLE_EVENT_ORPHAN")
        expected.add(root / e.position_id / "events" / (e.event_id + ".json"))
    for n in snapshot.notifications:
        require(n.position_id in positions and n.event_id in events
                and events[n.event_id].position_id == n.position_id, "SWING_LIFECYCLE_NOTIFICATION_ORPHAN")
        expected.add(root / n.position_id / "notifications" / (n.notification_id + ".json"))
    for c in snapshot.closures:
        p = positions.get(c.position_id)
        require(p is not None and (c.decision_id, c.trade_plan_id, c.trade_plan_hash)
                == (p.decision_id, p.trade_plan_id, p.trade_plan_hash)
                and c.lifecycle_event_ids == p.lifecycle_event_ids, "SWING_LIFECYCLE_CLOSURE_ORPHAN")
        expected.add(root / c.position_id / "closure.json")
    require({p for p in root.rglob("*") if p.is_file()} == expected, "SWING_LIFECYCLE_LAYOUT_INVALID")
    return len(positions)


def _paper(root):
    from kronos.swing.v1 import paper_observation_track as domain
    store = domain.LocalPaperObservationTrackStore(root)
    tracks = store.load_all_tracks()
    require({p.name for p in root.iterdir()} == {t.track_identity for t in tracks}
            if root.exists() else not tracks, "SWING_PAPER_ORPHAN_TRACK")
    for track in tracks:
        identity = track.track_identity
        directory = root / identity
        expected = {directory / "track.json"}
        # Legacy paper identities are text fields, so check the identities used
        # as filesystem references before asking the existing readers to follow
        # them. No record may redirect this explicit-root proof elsewhere.
        def check_references(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {"record_identity", "predecessor_applicability_identity", "applicability_identity"} and item is not None:
                        require(isinstance(item, str) and item not in {".", ".."}
                                and "/" not in item and "\\" not in item,
                                "SWING_PAPER_REFERENCE_PATH_INVALID")
                    check_references(item)
            elif isinstance(value, list):
                for item in value:
                    check_references(item)
        for path in [directory / "current-applicability.json", directory / "current-state.json",
                     *(directory / "applicability").glob("*.json")]:
            if path.exists():
                check_references(json.loads(path.read_bytes()))
        for family, reader, id_field in (
            ("events", store.events, "event_identity"),
            ("monitoring", store.monitoring, "record_identity"),
            ("applicability", store.applicability, "record_identity"),
        ):
            for value in reader(identity):
                require(value.track_identity == identity, "SWING_PAPER_BINDING_INVALID")
                expected.add(directory / family / (getattr(value, id_field) + ".json"))
        applicability = {a.record_identity: a for a in store.applicability(identity)}
        current = store.current_applicability(identity)
        require(not applicability or current is not None, "SWING_PAPER_APPLICABILITY_POINTER_MISSING")
        if current is not None:
            expected.add(directory / "current-applicability.json")
        for value in applicability.values():
            predecessor = value.predecessor_applicability_identity
            require(predecessor is None or predecessor in applicability, "SWING_PAPER_APPLICABILITY_PREDECESSOR_MISSING")
            authority = value.authority
            require((authority.sponsor_decision_identity, authority.native_assessment_sha256,
                     authority.direction, authority.geometry_identity, authority.geometry_sha256,
                     authority.canonical_instrument)
                    == (track.sponsor_decision_identity, track.native_assessment_sha256, track.direction,
                        track.step31_observation_identity, track.step31_observation_sha256, track.canonical_instrument),
                    "SWING_PAPER_APPLICABILITY_BINDING_INVALID")
        if store._has_historical_selection(identity):
            store.load_historical_consolidation(identity)
            expected.add(directory / "historical-representation.json")
            # Existing consolidation reader validates the selected representation;
            # retained raw facts still receive their ordinary record validation.
        for path in (directory / "facts").glob("*.json"):
            fact = store._load_fact(path)
            require(fact.track_identity == identity and fact.fact_identity == path.stem, "SWING_PAPER_FACT_BINDING_INVALID")
            expected.add(path)
        if store.is_compact(identity):
            state = store.load_compact(identity)
            expected.add(directory / "current-state.json")
            seen = set()
            head = state.material_head
            while head is not None:
                require(head not in seen, "SWING_PAPER_TRANSITION_CYCLE")
                seen.add(head)
                path = directory / "transitions" / (head + ".json")
                transition = domain._read(path)["transition"]
                require(sha256(domain._canonical(transition)).hexdigest() == head
                        and transition["track_identity"] == identity
                        and transition["kind"] in domain.COMPACT_TRANSITIONS
                        and transition["applicability_identity"] in applicability,
                        "SWING_PAPER_TRANSITION_INVALID")
                expected.add(path)
                head = transition["predecessor_transition"]
            require(len(seen) == state.material_count, "SWING_PAPER_TRANSITION_MISSING")
        else:
            store.restoration_projection(identity)
        for path in (directory / "historical-consolidations").glob("*.json"):
            # Content-addressed prepared historical artifacts may predate selection.
            data = json.loads(path.read_bytes())
            require(sha256(path.read_bytes()).hexdigest() == path.stem
                    and data["track"] == domain._primitive(track), "SWING_PAPER_CONSOLIDATION_INVALID")
            expected.add(path)
        require({p for p in directory.rglob("*") if p.is_file()} == expected, "SWING_PAPER_LAYOUT_INVALID")
    return len(tracks)


def verify_continuity(evidence_root: Path, *, expected_checkpoint=None) -> ContinuityProof:
    require(isinstance(evidence_root, Path) and evidence_root.is_absolute()
            and evidence_root != Path("/"), "CONTINUITY_ROOT_REQUIRED")
    native = evidence_root / "swing-v1" / "native-review"
    intraday = evidence_root / "intraday-v1"
    roots = dict(paper=native / "paper-observation-track-v1",
                 lifecycle=native / "active-trade-lifecycle-v0",
                 wo11=intraday / "prospective-v2-wo11-lifecycle",
                 wo17=intraday / "wo17-position-evidence-active-lifecycle-monitoring-v1",
                 notifications=native / "notification-centre-v1" / "intraday-source-references-v1")
    before = _inventory(roots)
    owners = _paper(roots["paper"]) + _swing_lifecycle(roots["lifecycle"]) + _wo11(roots["wo11"]) + _wo17(roots["wo17"])
    from kronos.application.intraday_notifications import IntradayNotifications
    from kronos.common.maintenance import _valid_notification_checkpoint
    # Invoke the existing pure reader without constructing an operational adapter,
    # executor, listeners, source projection, Provider or network transport.
    reader = SimpleNamespace(root=roots["notifications"], _lock=RLock(), KINDS=IntradayNotifications.KINDS)
    checkpoint = IntradayNotifications.checkpoint(reader)
    require(_valid_notification_checkpoint(checkpoint), "NOTIFICATION_CHECKPOINT_INVALID")
    if expected_checkpoint is not None:
        require(_valid_notification_checkpoint(expected_checkpoint)
                and checkpoint == expected_checkpoint, "NOTIFICATION_CHECKPOINT_MISMATCH")
    require(before == _inventory(roots), "CONTINUITY_CHANGED_DURING_READ")
    digest = sha256(json.dumps({"version": 1, "files": before, "checkpoint": checkpoint},
                               sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ContinuityProof(digest, owners, checkpoint["state"], checkpoint["pending_count"], checkpoint["sha256"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--checkpoint-state", choices=("EMPTY", "VALID_PENDING"))
    parser.add_argument("--checkpoint-count", type=int)
    parser.add_argument("--checkpoint-sha256")
    args = parser.parse_args(argv)
    try:
        values = (args.checkpoint_state, args.checkpoint_count, args.checkpoint_sha256)
        require(all(v is None for v in values) or all(v is not None for v in values), "NOTIFICATION_CHECKPOINT_ARGUMENTS_INVALID")
        expected = None if args.checkpoint_state is None else dict(
            state=args.checkpoint_state, pending_count=args.checkpoint_count, sha256=args.checkpoint_sha256)
        result = verify_continuity(args.evidence_root, expected_checkpoint=expected)
    except Exception as error:
        code = str(error) if isinstance(error, ContinuityError) else "CONTINUITY_EVIDENCE_INVALID"
        print("KRONOS_CONTINUITY_V1 INVALID " + code)
        return 2
    print("KRONOS_CONTINUITY_V1 VALID " + result.sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
