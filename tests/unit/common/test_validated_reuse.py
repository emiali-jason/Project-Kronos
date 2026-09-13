"""PERF/LAG-01 deterministic integrity and work-count qualification."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
import json
import os

import pytest

from kronos.common.validated_reuse import ValidatedBytesReuse


@dataclass(frozen=True)
class Value:
    identity: str


@pytest.mark.parametrize("change", ["bytes", "path", "policy", "schema", "revision", "identity"])
def test_exact_domain_invalidates(change):
    cache = ValidatedBytesReuse()
    calls = []
    def validate(data):
        calls.append(data)
        return Value(data.decode())
    key = dict(path="a", encoded=b"a", token=("policy1", "schema1", "revision1", "identity1"))
    assert cache.load(**key, validate=validate) == Value("a")
    assert cache.load(**key, validate=validate) == Value("a")
    assert len(calls) == 1
    if change == "bytes":
        key["encoded"] = b"b"
    elif change == "path":
        key["path"] = "b"
    else:
        key["token"] = (change, "changed")
    cache.load(**key, validate=validate)
    assert len(calls) == 2


def test_concurrent_identical_validation_coalesces():
    cache = ValidatedBytesReuse()
    calls = []
    lock = Lock()
    def validate(data):
        with lock:
            calls.append(data)
        return Value("same")
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: cache.load("a", b"same", "v1", validate), range(30)))
    assert len(calls) == 1
    assert all(result is results[0] for result in results)


@pytest.mark.parametrize("limits", [dict(max_entries=1), dict(max_bytes=1)])
def test_bounded_eviction(limits):
    cache = ValidatedBytesReuse(**limits)
    calls = []
    def validate(data):
        calls.append(data)
        return Value(data.decode())
    for data in [b"a", b"b", b"a"]:
        cache.load("a", data, "v1", validate)
    assert len(calls) == 3


def test_mutable_results_never_escape_as_reusable_truth():
    cache = ValidatedBytesReuse()
    first = cache.load("a", b"a", "v1", lambda _: [1])
    first.append(2)
    assert cache.load("a", b"a", "v1", lambda _: [1]) == [1]


def test_failures_not_cached_and_restart_revalidates():
    calls = []
    def invalid(data):
        calls.append(data)
        raise ValueError("bad")
    cache = ValidatedBytesReuse()
    for _ in range(2):
        with pytest.raises(ValueError, match="bad"):
            cache.load("a", b"a", "v1", invalid)
    assert len(calls) == 2
    for cache in [cache, ValidatedBytesReuse()]:
        cache.load("a", b"a", "v1", lambda b: calls.append(b) or Value("a"))
    assert len(calls) == 4


@pytest.mark.parametrize("tamper", ["hash", "schema", "identity", "corrupt", "missing", "symlink"])
def test_probables_fresh_bytes_fail_closed(tmp_path, tamper):
    from kronos.intraday.probables_v2 import create_probables_v2_methodology, ProbablesV2Error
    from kronos.intraday.probables_v2_persistence import ProbablesV2Store
    store = ProbablesV2Store(tmp_path)
    value = create_probables_v2_methodology()
    path = store.retain_methodology(value)
    assert store.load_methodology(value.publication_identity) == value
    stat = path.stat()
    if tamper == "missing":
        path.unlink()
    elif tamper == "symlink":
        path.unlink()
        target = tmp_path / "bad.json"
        target.write_bytes(b"{}")
        path.symlink_to(target)
    else:
        doc = json.loads(path.read_bytes())
        if tamper == "hash":
            doc["document_integrity"] = "BAD"
        elif tamper == "schema":
            doc["artifact_type"] = "UnknownType"
        elif tamper == "identity":
            doc["artifact_identity"] = "FOREIGN"
        path.write_bytes(b"{" if tamper == "corrupt" else json.dumps(doc).encode())
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    with pytest.raises(ProbablesV2Error):
        store.load_methodology(value.publication_identity)


def test_probables_validation_count_pointer_and_registry(tmp_path, monkeypatch):
    import kronos.intraday.probables_v2_persistence as persistence
    from tests.unit.intraday.test_probables_v2 import _opening_inputs, _run
    *_, mapping = _opening_inputs()
    run = _run(mapping)
    store = persistence.ProbablesV2Store(tmp_path)
    store.retain_complete(run=run, mappings=(mapping,))
    original = persistence._artifact_from_bytes
    calls = []
    def counted(data):
        calls.append(data)
        return original(data)
    monkeypatch.setattr(persistence, "_artifact_from_bytes", counted)
    assert store.load_current_run() == run
    first = len(calls)
    assert store.load_current_run() == run
    # Current pointer remains freshly validated; typed immutable lineage reuses.
    assert len(calls) - first < first
    pointer = tmp_path / "refresh-v2" / "CURRENT-PROBABLES-V2.json"
    pointer.unlink()
    assert store.load_current_run() is None
    count = len(calls)
    monkeypatch.setattr(persistence, "_from_wire", lambda _: (_ for _ in ()).throw(ValueError("changed schema")))
    with pytest.raises(ValueError, match="changed schema"):
        store.load_run(run.run_identity)
    assert len(calls) == count + 1


def test_review_snapshot_validates_currentness_once(tmp_path, monkeypatch):
    from tests.unit.intraday.test_review_v2 import _application
    from tests.unit.intraday.test_probables_v2 import _opening_inputs
    *_, mapping = _opening_inputs()
    run, app = _application(tmp_path, mapping)
    app.create_eligible_cycles(run)
    original = app._currentness_locked
    calls = []
    def counted():
        calls.append(1)
        return original()
    monkeypatch.setattr(app, "_currentness_locked", counted)
    result = app.snapshot()
    assert result is not None and len(calls) == 1


@pytest.mark.parametrize("tamper", ["hash", "schema", "corrupt", "missing", "symlink", "bom", "utf16"])
def test_swing_fact_reuse_rechecks_bytes(tmp_path, monkeypatch, tamper):
    from datetime import timedelta
    from decimal import Decimal
    import kronos.swing.v1.paper_observation_track as paper
    from tests.unit.swing.v1.test_paper_observation_track import _blocked, NOW
    decision = _blocked(tmp_path)
    track = paper.create_paper_observation_track(decision, current_run_identity=decision.snapshot.native_run_identity, created_at=NOW)
    store = paper.LocalPaperObservationTrackStore(tmp_path / "tracks")
    store.retain_track(track)
    fact = paper.make_market_fact(track, last_price=Decimal("100"), observed_at=NOW + timedelta(minutes=1), received_at=NOW + timedelta(minutes=1), source_identity="KITE:SESSION:1", source_sequence=1, ordering_deterministic=True, recovered=False)
    store.append_fact(fact)
    original = paper._fact_from_dict
    calls = []
    def counted(data):
        calls.append(1)
        return original(data)
    monkeypatch.setattr(paper, "_fact_from_dict", counted)
    assert store.facts(track.track_identity) == (fact,)
    assert store.facts(track.track_identity) == (fact,)
    assert len(calls) == 1
    path = next((store.root / track.track_identity / "facts").glob("*.json"))
    if tamper == "missing":
        path.unlink()
        assert store.facts(track.track_identity) == ()
        return
    if tamper == "symlink":
        path.unlink()
        other = tmp_path / "invalid.json"
        other.write_bytes(b"{}")
        path.symlink_to(other)
    elif tamper == "bom":
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    elif tamper == "utf16":
        path.write_bytes(path.read_text(encoding="utf-8").encode("utf-16"))
    else:
        data = json.loads(path.read_bytes())
        if tamper == "schema":
            data["schema"] = "WRONG"
        else:
            data["fact"]["integrity_sha256"] = "0" * 64
        path.write_bytes(b"{" if tamper == "corrupt" else json.dumps(data).encode())
    with pytest.raises(ValueError, match="STORED_RECORD_INVALID"):
        store.facts(track.track_identity)


@pytest.mark.parametrize("completed", [True, False])
@pytest.mark.parametrize("date_kind", ["today", "older", "unavailable"])
def test_completion_routing_preserves_full_handoff(completed, date_kind):
    from dataclasses import replace
    from datetime import timedelta
    from tests.unit.browser.test_browser_reports import _record, NOW
    from kronos.swing.v1.observation_research_ledger_v2 import ObservationMode, ObservationOperationalRoute, with_completion_trading_dates
    item = _record("NSE-EQ-TEST", ObservationMode.PAPER_OBSERVATION)
    item = replace(item, completion_timestamp=NOW if completed else None)
    day = NOW.date()
    resolved = {"today": day, "older": day - timedelta(days=1), "unavailable": None}[date_kind]
    expected = ObservationOperationalRoute.ACTIVE if not completed else ObservationOperationalRoute.COMPLETED_CURRENT_TRADING_DAY if resolved == day else ObservationOperationalRoute.HISTORICAL
    assert with_completion_trading_dates((item,), day, lambda _: resolved) == (replace(item, operational_route=expected),)


from tests.unit.browser.test_intraday_portfolio_reports import server


@pytest.mark.parametrize("route", ["/reports?product=SWING", "/journal?product=SWING"])
def test_browser_constructs_swing_population_once(server, monkeypatch, route):
    from tests.unit.browser.test_intraday_portfolio_reports import get
    srv = server[0]
    original = srv.trade_window.observation_operational_handoffs_v2
    calls = []
    def counted(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(srv.trade_window, "observation_operational_handoffs_v2", counted)
    status, _ = get(srv, route)
    assert status == 200 and len(calls) == 1



def test_validator_replacement_cannot_inherit_result():
    cache = ValidatedBytesReuse()
    assert cache.load("a", b"a", "v1", lambda _: Value("old")) == Value("old")
    assert cache.load("a", b"a", "v1", lambda _: Value("new")) == Value("new")


def test_hash_collision_still_requires_actual_byte_equality(monkeypatch):
    import kronos.common.validated_reuse as reuse
    class Collision:
        def digest(self):
            return b"same-digest"
    monkeypatch.setattr(reuse, "sha256", lambda _: Collision())
    cache = ValidatedBytesReuse()
    def validate(data):
        return Value(data.decode())
    assert cache.load("a", b"a", "v1", validate) == Value("a")
    assert cache.load("a", b"b", "v1", validate) == Value("b")


def test_review_get_reuses_one_snapshot_and_status_rechecks_pointer(tmp_path, monkeypatch):
    from tests.unit.browser.test_intraday_review_v2_control import _control, _Workstation
    from tests.unit.browser.test_product_route_isolation import _snapshot
    from kronos.browser.intraday_routes import IntradayBrowserRoutes
    from kronos.browser.product_routes import BrowserGetRequest
    run, app, control = _control(tmp_path)
    app.create_eligible_cycles(run)
    expected = control.status_document()
    snapshot = app.snapshot()
    assert control.status_document(snapshot=snapshot) == expected
    routes = IntradayBrowserRoutes(_Workstation(run), review_v2_control=control)
    original = app.snapshot
    calls = []
    def counted():
        calls.append(1)
        return original()
    monkeypatch.setattr(app, "snapshot", counted)
    response = routes.handle_get(BrowserGetRequest("/intraday/review", {}), _snapshot)
    assert response.status == 200 and len(calls) == 1
    (app.probables_store.root / "refresh-v2" / "CURRENT-PROBABLES-V2.json").unlink()
    status = control.status_document(snapshot=snapshot)
    assert status["source_probables_run_identity"] is None
    assert status["cycle_count"] == 0
