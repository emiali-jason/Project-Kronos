from __future__ import annotations

from dataclasses import dataclass
from asyncio import CancelledError
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from kronos.application.mcx_official_check import (
    ActivationEvidence, CheckFrequency, CheckLimits, CheckerState, FAMILIES,
    MAX_DOCUMENT_BYTES, MAX_PAGE_BYTES, McxOfficialCheckEngine, OfficialCheckError,
    OfficialHttpResponse, PRODUCT_PAGES, CIRCULARS_PAGE,
    StagedAuthorityCandidate,
)
from kronos.common.release_admission import ValidationBudget, monotonic_ns
import kronos.common.release_admission as release_admission
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.theta.operational import reviewed_owner


NOW = datetime(2026, 10, 28, 9, 30, tzinfo=timezone.utc)
PDF = b"%PDF-1.7\nMCX official fixture\n%%EOF\n"
DOC = "https://www.mcxindia.com/docs/fixture.pdf"


@dataclass(frozen=True)
class Row:
    identity: str
    family: str


@dataclass(frozen=True)
class Endpoint:
    series_identity: str
    expires_at: datetime


def fake_authority(active_payload=PDF):
    rows, endpoints = [], []
    for offset, family in enumerate(FAMILIES):
        for index, days in enumerate((10 + offset, 25 + offset, 50 + offset), 1):
            identity = f"MCX-OPT-SERIES-{family}-SYNTHETIC-{index}"
            rows.append(Row(identity, family))
            endpoints.append(Endpoint(identity, NOW + timedelta(days=days)))
    return SimpleNamespace(
        instrument=SimpleNamespace(
            pin=SimpleNamespace(reference="SYNTHETIC-INSTRUMENT/1.0.0/SHA256:" + "1" * 64),
            source_provenance=("SYNTHETIC/SHA256:" + sha256(active_payload).hexdigest(),),
            rows=tuple(rows),
        ),
        market=SimpleNamespace(
            pin=SimpleNamespace(reference="SYNTHETIC-MARKET/1.0.0/SHA256:" + "2" * 64),
            endpoints=tuple(endpoints),
        ),
        current_sha256="3" * 64,
        first=NOW - timedelta(days=1),
        last=NOW + timedelta(days=365),
    )


class FixtureTransport:
    def __init__(self, *, pdf=PDF, amendment=False):
        product_links = {
            family: (f'<section id="{family.lower()}section">'
                     '<a href="/docs/fixture.pdf">'
                     f'{" ".join(term.title() for term in family.split())} contract specification'
                     '</a></section>')
            for family in FAMILIES
        }
        circular_links = '<a href="/docs/fixture.pdf">Gold Mini Silver Mini Copper Crude Oil Natural Gas circular</a>'
        if amendment:
            circular_links += '<a href="/docs/amendment.pdf">Gold Mini amendment</a>'
        self.pages = {PRODUCT_PAGES[family]: product_links[family].encode()
                      for family in FAMILIES}
        self.pages[CIRCULARS_PAGE] = circular_links.encode()
        self.documents = {DOC: pdf}
        if amendment:
            self.documents["https://www.mcxindia.com/docs/amendment.pdf"] = (
                b"%PDF-1.7\nMCX amendment\n%%EOF\n")
        self.calls = []

    def __call__(self, url, **bounds):
        self.calls.append((url, bounds))
        if url in self.pages:
            return OfficialHttpResponse(
                url, url, 200, "text/html; charset=utf-8", self.pages[url],
                complete=True,
                circular_from=1 if url == CIRCULARS_PAGE else None,
                circular_through=552 if url == CIRCULARS_PAGE else None,
                page_number=1 if url == CIRCULARS_PAGE else None,
                page_count=1 if url == CIRCULARS_PAGE else None,
                page_item_count=(self.pages[url].count(b"<a ")
                                 if url == CIRCULARS_PAGE else None),
            )
        payload = self.documents[url]
        return OfficialHttpResponse(url, url, 200, "application/pdf", payload)


def activation():
    ready = b'{"schema":"TEST-ACTUAL-READY-RECEIPT","state":"READY"}'
    release = b'{"schema":"TEST-ACTUAL-CUSTODY-RELEASE","state":"RELEASED"}'
    return ActivationEvidence("a" * 64, ready, sha256(ready).hexdigest(),
                              release, sha256(release).hexdigest())


def joined_runner(callback):
    handle = Thread(target=callback, name="fixture-joined-runner")
    handle.start()
    handle.join(2)
    assert not handle.is_alive()
    return handle


def engine(tmp_path, *, transport=None, authority=None, runner=joined_runner,
           clock=lambda: NOW, replace=os.replace, candidate_supplier=None,
           frequency=CheckFrequency.DAILY, monotonic_clock=lambda: 100.0,
           check_limits=None):
    return McxOfficialCheckEngine(
        tmp_path / "mcx-check", transport=transport or FixtureTransport(),
        authority_provider=lambda: authority or fake_authority(),
        candidate_supplier=candidate_supplier, frequency=frequency,
        utc_clock=clock, monotonic_clock=monotonic_clock,
        background_runner=runner, check_limits=check_limits, replace=replace,
    )


class ControlledMonotonic:
    """Explicit whole-check clock; unrelated to shutdown ValidationBudget."""

    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


def run(engine):
    engine.activate(activation())
    assert engine.check_now() == "SCHEDULED"
    return engine.status_document()


def test_construction_is_dormant_and_activation_uses_exact_receipt_bytes(tmp_path):
    transport = FixtureTransport()
    value = engine(tmp_path, transport=transport)
    assert value.status_document()["lifecycle_state"] == "DORMANT"
    assert transport.calls == []
    assert not (tmp_path / "mcx-check").exists()
    with pytest.raises(OfficialCheckError, match="ACTIVATION_EVIDENCE_INVALID"):
        value.activate(True)
    value.activate(activation())
    assert transport.calls == []
    assert value.status_document()["activation_evidence_sha256"]


def test_unchanged_complete_evidence_is_current_and_receipt_is_immutable(tmp_path):
    transport = FixtureTransport()
    value = engine(tmp_path, transport=transport)
    status = run(value)
    assert status["checker_state"] == CheckerState.CURRENT.value, status
    assert status["last_failure"] is None
    receipt = tmp_path / "mcx-check/receipts" / f"{status['last_receipt_sha256']}.json"
    document = json.loads(receipt.read_bytes())
    assert document["scan_complete"] is True
    assert (document["circular_from"], document["circular_through"]) == (1, 552)
    assert document["semantic_mapping_approved"] is False
    authority = fake_authority()
    assert document["comparison_authority"] == {
        "instrument_reference": authority.instrument.pin.reference,
        "market_reference": authority.market.pin.reference,
        "current_sha256": authority.current_sha256,
    }
    assert document["discovery_inputs"]["product_pages"] == PRODUCT_PAGES
    assert document["discovery_inputs"]["circulars_page"] == CIRCULARS_PAGE
    assert all({"requested_url", "final_url", "redirects", "size", "sha256"}
               <= set(item) for item in document["observations"])
    discovery_hashes = {item["retained_object_sha256"]
                        for item in document["observations"]}
    source_hashes = {item["sha256"] for item in document["documents"]}
    assert discovery_hashes.isdisjoint(source_hashes)
    assert value.retained_discovery_pages(status["last_receipt_sha256"]) == tuple(
        transport.pages[item["requested_url"]] for item in document["observations"])
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert all(call[1]["max_redirects"] == 3 for call in transport.calls)


def test_changed_bytes_and_amendment_are_staged_without_changing_active_authority(tmp_path):
    authority = fake_authority()
    original = (authority.instrument.pin.reference, authority.market.pin.reference,
                authority.current_sha256)
    value = engine(tmp_path, transport=FixtureTransport(pdf=b"%PDF-1.7\nchanged\n%%EOF\n",
                                                        amendment=True), authority=authority)
    status = run(value)
    assert status["checker_state"] == CheckerState.UPDATE_AVAILABLE.value
    receipt = json.loads((tmp_path / "mcx-check/receipts" /
                         f"{status['last_receipt_sha256']}.json").read_bytes())
    assert len({item["sha256"] for item in receipt["documents"]}) == 2
    assert original == (authority.instrument.pin.reference, authority.market.pin.reference,
                        authority.current_sha256)


def test_identical_payloads_deduplicate_objects_but_not_check_history(tmp_path):
    times = iter((NOW, NOW + timedelta(minutes=1)))
    value = engine(tmp_path, clock=lambda: next(times))
    value.activate(activation())
    assert value.check_now() == "SCHEDULED"
    first = value.status_document()["last_receipt_sha256"]
    assert value.check_now() == "SCHEDULED"
    second = value.status_document()["last_receipt_sha256"]
    assert first != second
    receipt = json.loads((tmp_path / "mcx-check/receipts" / f"{second}.json").read_bytes())
    retained = ({item["sha256"] for item in receipt["documents"]}
                | {item["retained_object_sha256"]
                   for item in receipt["observations"]})
    assert {path.name for path in (tmp_path / "mcx-check/objects").iterdir()} == retained
    assert len(list((tmp_path / "mcx-check/receipts").iterdir())) == 2


@pytest.mark.parametrize("kind", ["offline", "tls", "timeout"])
def test_transport_failures_are_failed_and_never_current(tmp_path, kind):
    def failed(*_args, **_kwargs):
        raise {"offline": OSError, "tls": ConnectionError, "timeout": TimeoutError}[kind](kind)
    status = run(engine(tmp_path, transport=failed))
    assert status["checker_state"] == CheckerState.FAILED.value
    assert status["last_failure"] == "MCX_CHECK_TRANSPORT_FAILED"
    assert status["last_successful_check"] is None


@pytest.mark.parametrize("mutation,code", [
    ("redirect", "MCX_CHECK_REDIRECT_INVALID"),
    ("host", "MCX_CHECK_URL_DENIED"),
    ("type", "MCX_CHECK_MEDIA_TYPE_INVALID"),
    ("truncated", "MCX_CHECK_PDF_INVALID"),
    ("size", "MCX_CHECK_SIZE_INVALID"),
])
def test_document_redirect_type_size_and_envelope_fail_closed(tmp_path, mutation, code):
    base = FixtureTransport()
    def transport(url, **bounds):
        response = base(url, **bounds)
        if url == DOC:
            values = response.__dict__.copy()
            if mutation == "redirect": values["redirects"] = (url,) * 4
            if mutation == "host": values["final_url"] = "https://example.com/docs/fixture.pdf"
            if mutation == "type": values["media_type"] = "text/html"
            if mutation == "truncated": values["body"] = b"%PDF-1.7\ntruncated"
            if mutation == "size": values["body"] = b"%PDF-" + b"x" * MAX_DOCUMENT_BYTES + b"%%EOF"
            return OfficialHttpResponse(**values)
        return response
    status = run(engine(tmp_path, transport=transport))
    assert status["checker_state"] == CheckerState.FAILED.value
    assert status["last_failure"] == code


@pytest.mark.parametrize("failure", ["product", "circular-complete", "circular-range"])
def test_incomplete_product_or_circular_scan_cannot_be_current(tmp_path, failure):
    base = FixtureTransport()
    def transport(url, **bounds):
        response = base(url, **bounds)
        values = response.__dict__.copy()
        if failure == "product" and url == PRODUCT_PAGES["COPPER"]:
            values["body"] = b"<html>no document</html>"
        if failure == "circular-complete" and url == CIRCULARS_PAGE:
            values["complete"] = False
        if failure == "circular-range" and url == CIRCULARS_PAGE:
            values["circular_through"] = None
        return OfficialHttpResponse(**values)
    status = run(engine(tmp_path, transport=transport))
    assert status["checker_state"] == CheckerState.FAILED.value


def test_arbitrary_candidate_or_downloaded_pdf_cannot_claim_awaiting_review(tmp_path):
    value = engine(tmp_path, candidate_supplier=lambda _receipt: True)
    status = run(value)
    assert status["checker_state"] == CheckerState.FAILED.value
    assert status["last_failure"] == "MCX_CHECK_CANDIDATE_INVALID"


def test_existing_readers_must_validate_a_candidate_before_awaiting_review(tmp_path, monkeypatch):
    actual = reviewed_owner()
    from kronos.theta.target_authority import OwnerOptionAuthority
    candidate = OwnerOptionAuthority(current_filename="current-2026.1.0.json")
    sources = {}
    for owner in (actual, candidate):
        instrument_json = json.loads(
            (owner.instrument_root / owner.instrument.pin.filename).read_bytes())
        for source in instrument_json["sources"]:
            sources[source["official_uri"]] = (
                owner.instrument_root / source["filename"]).read_bytes()
    links = "".join(f'<a href="{url}">Gold Mini Silver Mini Copper Crude Oil Natural Gas</a>'
                    for url in sources)
    class ActualSourceTransport(FixtureTransport):
        def __init__(self):
            super().__init__()
            self.pages = {url: links.encode() for url in PRODUCT_PAGES.values()}
            self.pages[CIRCULARS_PAGE] = links.encode()
            self.documents = sources
    supplier = lambda _receipt: StagedAuthorityCandidate(
        candidate.instrument_root, candidate.market_root,
        current_filename="current-2026.1.0.json")
    value = engine(tmp_path, transport=ActualSourceTransport(), authority=actual,
                   candidate_supplier=supplier)
    status = run(value)
    assert status["checker_state"] == CheckerState.AWAITING_REVIEW.value
    assert (actual.instrument.pin.reference
            == reviewed_owner().instrument.pin.reference)


def test_already_active_reader_valid_candidate_remains_current(tmp_path):
    actual = reviewed_owner()
    sources = {}
    publication = json.loads(
        (actual.instrument_root / actual.instrument.pin.filename).read_bytes())
    for source in publication["sources"]:
        sources[source["official_uri"]] = (
            actual.instrument_root / source["filename"]).read_bytes()
    links = "".join(f'<a href="{url}">Gold Mini Silver Mini Copper Crude Oil Natural Gas</a>'
                    for url in sources)
    fixture = FixtureTransport()
    fixture.pages = {url: links.encode() for url in PRODUCT_PAGES.values()}
    fixture.pages[CIRCULARS_PAGE] = links.encode()
    fixture.documents = sources
    seen = []
    def supplier(receipt):
        seen.append(receipt)
        return StagedAuthorityCandidate(actual.instrument_root, actual.market_root)
    status = run(engine(tmp_path, transport=fixture, authority=actual,
                        candidate_supplier=supplier))
    staged = {item["sha256"] for item in seen[0]["documents"]}
    expected = {sha256(payload).hexdigest() for payload in sources.values()}
    assert status["last_failure"] is None, (status["last_failure"], expected - staged)
    assert status["checker_state"] == CheckerState.CURRENT.value, status


def test_actual_five_family_roster_rollover_and_warning_boundaries(tmp_path):
    value = McxOfficialCheckEngine(tmp_path / "mcx-check", transport=FixtureTransport(),
                                   authority_provider=reviewed_owner)
    coverage = value.coverage(NOW)
    assert set(coverage["families"]) == set(FAMILIES)
    assert all(item["authority_health"] == "USABLE"
               for item in coverage["families"].values())
    assert coverage["families"]["GOLDM"]["e1"].endswith("2026-10-29")
    assert coverage["earliest_shared_coverage_loss"] == {
        "family": "CRUDEOIL", "at": "2026-11-17T23:55:00+05:30"}
    assert coverage["families"]["CRUDEOIL"]["warning"] == "30 DAYS"
    after_rollover = value.coverage(datetime(2026, 10, 29, 18, 26, tzinfo=timezone.utc))
    assert after_rollover["families"]["GOLDM"]["e1"].endswith("2026-11-27")
    synthetic = fake_authority()
    synthetic.first = NOW - timedelta(days=365)
    checker = engine(tmp_path, authority=synthetic)
    loss = datetime.fromisoformat(
        checker.coverage(NOW)["families"]["CRUDEOIL"]["coverage_loss_at"])
    for days, expected in ((31, "NONE"), (30, "30 DAYS"), (14, "14 DAYS"),
                           (7, "7 DAYS"), (0, "UNAVAILABLE")):
        assert checker.coverage(loss - timedelta(days=days))["families"][
            "CRUDEOIL"]["warning"] == expected


def test_frequency_single_flight_manual_and_scheduled_use_one_owned_worker(tmp_path):
    release = Event()
    handles = []
    def blocked_runner(callback):
        handle = Thread(target=lambda: (release.wait(2), callback()),
                        name="fixture-frequency-runner")
        handles.append(handle); handle.start(); return handle
    value = engine(tmp_path, runner=blocked_runner,
                   frequency=CheckFrequency.EVERY_THREE_DAYS)
    value.activate(activation())
    assert value.trigger_scheduled(observed=99.0) == "NOT_DUE"
    assert value.trigger_scheduled(observed=100.0) == "SCHEDULED"
    assert value.check_now() == "PENDING"
    assert value.trigger_scheduled(observed=999999.0) == "PENDING"
    assert value.status_document()["owned_workers"] == 1
    release.set(); handles[0].join(2)
    assert value.status_document()["owned_workers"] == 0
    value.set_frequency(CheckFrequency.WEEKLY)
    assert value.status_document()["frequency"] == "WEEKLY"


def test_runner_activation_failure_fences_all_later_work(tmp_path):
    failure = RuntimeError("fixture runner unavailable")
    def runner(_callback):
        raise failure
    value = engine(tmp_path, runner=runner)
    value.activate(activation())
    with pytest.raises(RuntimeError) as caught:
        value.check_now()
    assert caught.value is failure
    assert value.check_now() == "DENIED"
    assert value.status_document()["lifecycle_state"] == "ACTIVATION_FAILED"


def test_existing_maintenance_admission_fences_new_root_work(tmp_path):
    admission = MaintenanceAdmissionCoordinator()
    value = engine(tmp_path)
    value.bind_maintenance_admission(admission)
    value.activate(activation())
    assert value.check_now() == "SCHEDULED"
    assert admission.claim("f" * 64) is True
    assert value.check_now() == "DENIED"


def test_drain_and_close_use_same_absolute_budget_and_report_owned_worker(tmp_path):
    release = Event()
    handles = []
    def blocked_runner(callback):
        handle = Thread(target=lambda: (release.wait(2), callback()),
                        name="fixture-drain-runner")
        handles.append(handle); handle.start(); return handle
    value = engine(tmp_path, runner=blocked_runner)
    value.activate(activation())
    assert value.check_now() == "SCHEDULED"
    value.drain()
    assert value.check_now() == "DENIED"
    budget = ValidationBudget(monotonic_ns() + 20_000_000)
    outcome = value.close(budget)
    assert outcome.state == "UNRESOLVED"
    assert outcome.owned_workers == 1
    assert outcome.budget_deadline_ns == budget.deadline_ns
    release.set(); handles[0].join(2)


def test_successful_close_separates_application_cleanup_from_fixture_teardown(tmp_path,
        record_testsuite_property):
    value = engine(tmp_path)
    run(value)
    budget = ValidationBudget(monotonic_ns() + 1_000_000_000)
    outcome = value.close(budget)
    assert outcome.state == "CLOSED"
    assert outcome.unfinished_durable_writes == 0
    record_testsuite_property("application_cleanup",
                              json.dumps(outcome.__dict__, sort_keys=True))
    record_testsuite_property("fixture_teardown",
                              "pytest tmp_path cleanup occurs after assertions")


def test_interrupted_atomic_write_is_unresolved_and_restart_recovers_regular_temp(tmp_path):
    calls = 0
    def replace(_source, _target):
        nonlocal calls
        calls += 1
        raise OSError("synthetic interrupted replace")
    failed = engine(tmp_path, replace=replace)
    with pytest.raises(OfficialCheckError, match="DURABLE_WRITE_UNRESOLVED"):
        failed.activate(activation())
    assert failed.status_document()["durable_write_ownership"] == "UNKNOWN"
    assert list((tmp_path / "mcx-check").glob(".*.tmp"))
    recovered = engine(tmp_path)
    recovered.activate(activation())
    assert not list((tmp_path / "mcx-check").glob(".*.tmp"))
    assert recovered.status_document()["lifecycle_state"] == "IDLE"


def test_restart_recovers_last_success_and_persisted_frequency(tmp_path):
    value = engine(tmp_path)
    run(value)
    value.set_frequency(CheckFrequency.EVERY_THREE_DAYS)
    previous = value.status_document()
    recovered = engine(tmp_path, frequency=CheckFrequency.WEEKLY)
    recovered.activate(activation())
    status = recovered.status_document()
    assert status["checker_state"] == previous["checker_state"]
    assert status["last_successful_check"] == previous["last_successful_check"]
    assert status["last_receipt_sha256"] == previous["last_receipt_sha256"]
    assert status["frequency"] == CheckFrequency.EVERY_THREE_DAYS.value


def test_failure_preserves_last_success_separately(tmp_path):
    fixture = FixtureTransport()
    value = engine(tmp_path, transport=fixture)
    run(value)
    first_success = value.status_document()["last_successful_check"]
    fixture.pages.pop(PRODUCT_PAGES["GOLDM"])
    assert value.check_now() == "SCHEDULED"
    status = value.status_document()
    assert status["checker_state"] == CheckerState.FAILED.value
    assert status["last_successful_check"] == first_success


def test_unsafe_store_and_recovery_paths_deny(tmp_path):
    relative = McxOfficialCheckEngine
    with pytest.raises(OfficialCheckError, match="STORE_PATH_INVALID"):
        relative(Path("relative"), transport=FixtureTransport(),
                 authority_provider=fake_authority)
    outside = tmp_path / "outside"; outside.mkdir()
    symlink = tmp_path / "store-link"; symlink.symlink_to(outside, target_is_directory=True)
    value = McxOfficialCheckEngine(symlink, transport=FixtureTransport(),
                                   authority_provider=fake_authority)
    with pytest.raises(OfficialCheckError, match="STORE_PATH_INVALID"):
        value.activate(activation())


def test_symlinked_persisted_configuration_denies_restart(tmp_path):
    root = tmp_path / "mcx-check"
    root.mkdir(mode=0o700)
    target = tmp_path / "outside.json"
    target.write_text('{"fixture":"not checker state"}\n')
    (root / "configuration.json").symlink_to(target)
    value = engine(tmp_path)
    with pytest.raises(OfficialCheckError, match="LOCAL_STATE_INVALID"):
        value.activate(activation())


def test_status_and_config_are_private_atomic_documents(tmp_path):
    value = engine(tmp_path)
    run(value)
    root = tmp_path / "mcx-check"
    for name in ("configuration.json", "status.json"):
        path = root / name
        assert path.stat().st_mode & 0o777 == 0o600
        assert json.loads(path.read_bytes())["schema"].endswith("-V1")
    assert not list(root.glob(".*.tmp"))


def test_c01_truncated_object_cannot_receive_successful_check_disposition(
        tmp_path, monkeypatch):
    fixture = FixtureTransport()
    value = engine(tmp_path, transport=fixture)
    value.activate(activation())
    actual_write = os.write
    calls = 0

    def one_interrupted_write(fd, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return actual_write(fd, payload[:max(1, len(payload) // 2)])
        if calls == 2:
            return 0
        return actual_write(fd, payload)

    monkeypatch.setattr("kronos.application.mcx_official_check.os.write",
                        one_interrupted_write)
    assert value.check_now() == "SCHEDULED"
    status = value.status_document()
    assert status["checker_state"] == CheckerState.FAILED.value
    assert status["last_receipt_sha256"] is None
    assert status["durable_write_ownership"] == "UNKNOWN"
    objects = list((tmp_path / "mcx-check/objects").iterdir())
    assert len(objects) == 1
    assert objects[0].stat().st_size < len(fixture.pages[PRODUCT_PAGES["GOLDM"]])


def test_c01_prefix_write_cannot_replace_a_valid_atomic_document(tmp_path, monkeypatch):
    value = engine(tmp_path)
    value.activate(activation())
    path = tmp_path / "mcx-check/configuration.json"
    original = path.read_bytes()
    actual_write = os.write
    calls = 0

    def prefix_then_zero(fd, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return actual_write(fd, payload[:max(1, len(payload) // 2)])
        return 0

    monkeypatch.setattr("kronos.application.mcx_official_check.os.write",
                        prefix_then_zero)
    with pytest.raises(OfficialCheckError, match="DURABLE_WRITE_UNRESOLVED"):
        value._atomic_document("configuration.json", {"replacement": "must-not-land"})
    assert path.read_bytes() == original
    assert list((tmp_path / "mcx-check").glob(".configuration.json.*.tmp"))


def test_c02_actual_worker_termination_is_observed_within_original_deadline(tmp_path):
    callback_done = Event()
    release = Event()
    handles = []

    def runner(callback):
        def target():
            callback()
            callback_done.set()
            release.wait(2)
        handle = Thread(target=target, name="fixture-timely-runner")
        handles.append(handle); handle.start(); return handle

    value = engine(tmp_path, runner=runner)
    value.activate(activation())
    assert value.check_now() == "SCHEDULED"
    assert callback_done.wait(2)
    release.set()
    budget = ValidationBudget(monotonic_ns() + 1_000_000_000)
    outcome = value.close(budget)
    assert outcome.state == "CLOSED"
    assert outcome.worker_thread_identity == handles[0].ident
    assert outcome.worker_termination == "OBSERVED_WITHIN_DEADLINE"
    assert outcome.budget_deadline_ns == budget.deadline_ns


def test_c02_runner_failure_retains_unknown_launch_ownership(tmp_path):
    failure = RuntimeError("synthetic runner launch uncertainty")
    value = engine(tmp_path, runner=lambda _callback: (_ for _ in ()).throw(failure))
    value.activate(activation())
    with pytest.raises(RuntimeError) as caught:
        value.check_now()
    assert caught.value is failure
    status = value.status_document()
    assert status["worker_launch_ownership"] == "UNKNOWN"
    outcome = value.close(ValidationBudget(monotonic_ns() + 50_000_000))
    assert outcome.state == "UNRESOLVED"
    assert outcome.owned_workers == 1


def test_c02_completion_observed_only_after_deadline_stays_unresolved(tmp_path):
    callback_done = Event()
    release = Event()
    handles = []

    def runner(callback):
        def target():
            callback(); callback_done.set(); release.wait(2)
        handle = Thread(target=target, name="fixture-expired-runner")
        handles.append(handle); handle.start(); return handle

    value = engine(tmp_path, runner=runner)
    value.activate(activation())
    assert value.check_now() == "SCHEDULED"
    assert callback_done.wait(2)
    budget = ValidationBudget(monotonic_ns() - 1)
    outcome = value.close(budget)
    assert outcome.state == "UNRESOLVED"
    assert outcome.budget_deadline_ns == budget.deadline_ns
    release.set(); handles[0].join(2)
    assert value.status_document()["worker_termination"] == "OBSERVED"
    assert outcome.state == "UNRESOLVED"


def test_c03_close_cannot_acknowledge_entered_configuration_write(tmp_path, monkeypatch):
    entered = Event()
    release = Event()
    errors = []
    value = engine(tmp_path)
    value.activate(activation())
    actual = value._atomic_document

    def blocked_document(name, payload):
        if name == "configuration.json":
            entered.set(); release.wait(2)
        return actual(name, payload)

    monkeypatch.setattr(value, "_atomic_document", blocked_document)
    handle = Thread(target=lambda: _capture_error(
        errors, value.set_frequency, CheckFrequency.WEEKLY))
    handle.start()
    assert entered.wait(2)
    try:
        outcome = value.close(ValidationBudget(monotonic_ns() + 20_000_000))
        assert outcome.state == "UNRESOLVED"
        assert outcome.entered_operations == 1
    finally:
        release.set(); handle.join(2)
    assert errors and str(errors[0]) == "MCX_CHECK_CONFIGURATION_CANCELLED"
    assert value.frequency == CheckFrequency.DAILY


def test_c04_incomplete_circular_pagination_fails_closed(tmp_path):
    fixture = FixtureTransport()

    def incomplete(url, **bounds):
        response = fixture(url, **bounds)
        if url == CIRCULARS_PAGE:
            values = response.__dict__.copy()
            values["page_count"] = 2
            values["next_page_url"] = None
            return OfficialHttpResponse(**values)
        return response

    status = run(engine(tmp_path, transport=incomplete))
    assert status["checker_state"] == CheckerState.FAILED.value
    assert status["last_failure"] == "MCX_CHECK_PAGINATION_INCOMPLETE"


def test_c04_complete_two_page_circular_range_is_auditable(tmp_path):
    fixture = FixtureTransport()
    page_two = CIRCULARS_PAGE + "?page=2"
    first = b'<a href="/docs/fixture.pdf">Gold Mini circular</a>'
    second = b'<a href="/docs/calendar.pdf">Contract Launch Calendar December 2026</a>'
    fixture.documents["https://www.mcxindia.com/docs/calendar.pdf"] = (
        b"%PDF-1.7\nCalendar\n%%EOF\n")

    def paginated(url, **bounds):
        if url in PRODUCT_PAGES.values():
            return fixture(url, **bounds)
        if url == CIRCULARS_PAGE:
            return OfficialHttpResponse(url, url, 200, "text/html", first,
                                        circular_from=1, circular_through=300,
                                        page_number=1, page_count=2,
                                        page_item_count=1, next_page_url=page_two)
        if url == page_two:
            return OfficialHttpResponse(url, url, 200, "text/html", second,
                                        circular_from=301, circular_through=552,
                                        page_number=2, page_count=2,
                                        page_item_count=1, next_page_url=None)
        return fixture(url, **bounds)

    status = run(engine(tmp_path, transport=paginated))
    receipt = json.loads((tmp_path / "mcx-check/receipts" /
                         f"{status['last_receipt_sha256']}.json").read_bytes())
    pages = [item for item in receipt["observations"]
             if item["kind"] == "CIRCULAR_INDEX_PAGE"]
    assert [(item["page_number"], item["circular_from"], item["circular_through"])
            for item in pages] == [(1, 1, 300), (2, 301, 552)]
    assert (receipt["circular_from"], receipt["circular_through"]) == (1, 552)


@pytest.mark.parametrize("limit_kind", ["requests", "documents", "duration"])
def test_c04_exhausted_check_limits_fail_closed(tmp_path, limit_kind):
    fixture = FixtureTransport(amendment=True)
    limits = CheckLimits(max_requests=6) if limit_kind == "requests" else (
        CheckLimits(max_documents=1) if limit_kind == "documents" else
        CheckLimits(max_duration_seconds=15.0))
    clock = (lambda: 100.0)
    if limit_kind == "duration":
        ticks = iter(range(0, 1000, 10))
        clock = lambda: float(next(ticks))
    status = run(engine(tmp_path, transport=fixture, check_limits=limits,
                        monotonic_clock=clock))
    assert status["checker_state"] == CheckerState.FAILED.value
    assert status["last_failure"] == (
        "MCX_CHECK_DEADLINE_EXPIRED" if limit_kind == "duration"
        else "MCX_CHECK_LIMIT_EXHAUSTED")


@pytest.mark.parametrize("target", ["object", "receipt", "document"])
def test_reviewed_reproduction_c01_prefix_then_zero_write_is_never_acknowledged(
        tmp_path, monkeypatch, target):
    """Reviewed S3.02 wrote once and acknowledged a prefix as complete."""
    value = engine(tmp_path)
    value.activate(activation())
    actual_write = os.write
    calls = 0

    def prefix_then_zero(fd, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return actual_write(fd, payload[:max(1, len(payload) // 2)])
        return 0

    monkeypatch.setattr("kronos.application.mcx_official_check.os.write",
                        prefix_then_zero)
    with pytest.raises(OfficialCheckError, match="DURABLE_WRITE_UNRESOLVED"):
        if target == "object":
            value._object(b"prefix-only-object")
        elif target == "receipt":
            value._immutable_receipt({"schema": "PREFIX-ONLY-RECEIPT"})
        else:
            value._atomic_document("prefix-only.json", {"value": "complete"})
    assert value.status_document()["durable_write_ownership"] == "UNKNOWN"


def test_reviewed_reproduction_c02_callback_completion_is_not_thread_termination(tmp_path):
    """The callback may return while the runner's actual thread is still alive."""
    callback_done = Event()
    release_thread = Event()
    handles = []

    def runner(callback):
        def target():
            callback()
            callback_done.set()
            release_thread.wait(2)
        handle = Thread(target=target, name="fixture-owned-runner")
        handles.append(handle)
        handle.start()
        return handle

    value = engine(tmp_path, runner=runner)
    value.activate(activation())
    assert value.check_now() == "SCHEDULED"
    assert callback_done.wait(2)
    try:
        budget = ValidationBudget(monotonic_ns() + 20_000_000)
        outcome = value.close(budget)
        assert outcome.state == "UNRESOLVED"
        assert handles[0].is_alive()
    finally:
        release_thread.set()
        handles[0].join(2)


def test_reviewed_reproduction_c03_post_enable_clock_exception_fences_work(tmp_path):
    def failed_clock():
        raise RuntimeError("synthetic post-enable clock failure")

    value = engine(tmp_path, clock=lambda: NOW)
    value._monotonic_clock = failed_clock
    with pytest.raises(RuntimeError, match="post-enable clock failure"):
        value.activate(activation())
    assert value.status_document()["lifecycle_state"] == "ACTIVATION_FAILED"
    assert value.check_now() == "DENIED"


def test_reviewed_reproduction_c03_close_cannot_overtake_entered_activation(
        tmp_path, monkeypatch):
    entered = Event()
    release = Event()
    errors = []
    value = engine(tmp_path)
    actual = value._ensure_store

    def blocked_ensure_store():
        entered.set()
        release.wait(2)
        actual()

    monkeypatch.setattr(value, "_ensure_store", blocked_ensure_store)
    handle = Thread(target=lambda: _capture_error(errors, value.activate, activation()))
    handle.start()
    assert entered.wait(2)
    try:
        outcome = value.close(ValidationBudget(monotonic_ns() + 20_000_000))
        assert outcome.state == "UNRESOLVED"
    finally:
        release.set()
        handle.join(2)
    assert errors
    assert value.status_document()["lifecycle_state"] == "STOPPED"


def _capture_error(errors, function, *args):
    try:
        function(*args)
    except BaseException as error:  # retained test observation
        errors.append(error)


def test_reviewed_reproduction_c04_mixed_product_sections_are_not_cross_assigned(tmp_path):
    fixture = FixtureTransport()
    fixture.pages[PRODUCT_PAGES["GOLDM"]] = (
        b'<section id="goldminisection"><a href="/docs/goldm.pdf">Contract specification</a></section>'
        b'<section id="goldtensection"><a href="/docs/goldten.pdf">Contract specification</a></section>')
    fixture.documents["https://www.mcxindia.com/docs/goldm.pdf"] = (
        b"%PDF-1.7\nGold Mini\n%%EOF\n")
    fixture.documents["https://www.mcxindia.com/docs/goldten.pdf"] = (
        b"%PDF-1.7\nGold Ten\n%%EOF\n")
    status = run(engine(tmp_path, transport=fixture))
    receipt = json.loads((tmp_path / "mcx-check/receipts" /
                         f"{status['last_receipt_sha256']}.json").read_bytes())
    gold_urls = {item["source_url"] for item in receipt["documents"]
                 if "GOLDM" in item.get("families", (item.get("family"),))}
    assert "https://www.mcxindia.com/docs/goldm.pdf" in gold_urls
    assert "https://www.mcxindia.com/docs/goldten.pdf" not in gold_urls


def test_reviewed_reproduction_c04_generic_governing_calendar_is_retained(tmp_path):
    fixture = FixtureTransport()
    fixture.pages[CIRCULARS_PAGE] += (
        b'<a href="/docs/launch-calendar.pdf">Contract Launch Calendar December 2026</a>')
    fixture.documents["https://www.mcxindia.com/docs/launch-calendar.pdf"] = (
        b"%PDF-1.7\nLaunch calendar\n%%EOF\n")
    status = run(engine(tmp_path, transport=fixture))
    receipt = json.loads((tmp_path / "mcx-check/receipts" /
                         f"{status['last_receipt_sha256']}.json").read_bytes())
    records = [item for item in receipt["documents"]
               if item["source_url"].endswith("launch-calendar.pdf")]
    assert len(records) == 1
    assert records[0]["classification"] == "MARKET_WIDE_GOVERNING_CANDIDATE"
    assert set(records[0]["families"]) == set(FAMILIES)


def test_reviewed_reproduction_c04_response_request_mismatch_fails_closed(tmp_path):
    fixture = FixtureTransport()

    def mismatched(url, **bounds):
        response = fixture(url, **bounds)
        if url == DOC:
            values = response.__dict__.copy()
            values["requested_url"] = DOC + "?different=1"
            return OfficialHttpResponse(**values)
        return response

    status = run(engine(tmp_path, transport=mismatched))
    assert status["checker_state"] == CheckerState.FAILED.value
    assert status["last_failure"] == "MCX_CHECK_RESPONSE_MISMATCH"


def test_residual_reproduction_c02_exact_deadline_before_closed_is_unresolved(
        tmp_path, monkeypatch):
    value = engine(tmp_path)
    value.activate(activation())
    budget = ValidationBudget(11)
    budget_times = iter((10, 10, 11))
    monkeypatch.setattr(release_admission, "monotonic_ns",
                        lambda: next(budget_times))
    monkeypatch.setattr("kronos.application.mcx_official_check.monotonic_ns",
                        lambda: 10)
    outcome = value.close(budget)
    assert outcome.state == "UNRESOLVED"
    assert outcome.budget_deadline_ns == 11


def test_residual_reproduction_c02_thread_observed_at_deadline_is_unresolved(
        tmp_path, monkeypatch):
    handles = []

    def completed_runner(callback):
        handle = Thread(target=callback, name="fixture-exact-deadline-runner")
        handles.append(handle); handle.start(); handle.join(2)
        return handle

    value = engine(tmp_path, runner=completed_runner)
    value.activate(activation())
    assert value.check_now() == "SCHEDULED"
    assert handles[0].ident is not None and not handles[0].is_alive()
    budget = ValidationBudget(11)
    budget_times = iter((10, 10, 11))
    observed_times = iter((10, 10, 11))
    monkeypatch.setattr(release_admission, "monotonic_ns",
                        lambda: next(budget_times))
    monkeypatch.setattr("kronos.application.mcx_official_check.monotonic_ns",
                        lambda: next(observed_times))
    outcome = value.close(budget)
    assert outcome.state == "UNRESOLVED"
    assert outcome.worker_thread_identity == handles[0].ident
    assert outcome.worker_termination == "NOT_OBSERVED_WITHIN_DEADLINE"
    assert outcome.budget_deadline_ns == 11


def test_residual_reproduction_c03_queued_callback_denied_after_runner_failure(tmp_path):
    transport = FixtureTransport()
    callback_ready = Event()
    release_callback = Event()
    handles = []
    failure = RuntimeError("exact queued-runner failure")

    def failed_after_queue(callback):
        def target():
            callback_ready.set(); release_callback.wait(2); callback()
        handle = Thread(target=target, name="fixture-queued-failed-runner")
        handles.append(handle); handle.start()
        assert callback_ready.wait(2)
        raise failure

    value = engine(tmp_path, transport=transport, runner=failed_after_queue)
    value.activate(activation())
    caught = None
    result = None
    try:
        result = value.check_now()
    except BaseException as error:
        caught = error
    finally:
        release_callback.set(); handles[0].join(2)
    assert (caught is failure, result, len(transport.calls)) == (True, None, 0)
    status = value.status_document()
    assert status["worker_launch_ownership"] == "UNKNOWN"
    assert status["owned_workers"] == 1
    assert value.check_now() == "DENIED"


@pytest.mark.parametrize("failure", [
    RuntimeError("exact runtime transition failure"),
    KeyboardInterrupt("exact keyboard transition cancellation"),
    CancelledError("exact asyncio transition cancellation"),
], ids=("RuntimeError", "KeyboardInterrupt", "CancelledError"))
def test_residual_reproduction_c03_transition_baseexception_is_propagated_and_latched(
        tmp_path, failure):
    def failed_runner(_callback):
        raise failure

    value = engine(tmp_path, runner=failed_runner)
    value.activate(activation())
    caught = None
    result = None
    try:
        result = value.check_now()
    except BaseException as error:
        caught = error
    status = value.status_document()
    assert (caught is failure, result, status["lifecycle_state"],
            status["worker_launch_ownership"], status["owned_workers"]) == (
                True, None, "ACTIVATION_FAILED", "UNKNOWN", 1)
    assert value.check_now() == "DENIED"
    cleanup = value.close(ValidationBudget(monotonic_ns() + 50_000_000))
    assert cleanup.state == "UNRESOLVED"
    assert cleanup.owned_workers == 1


def test_c03_committed_receipt_survives_later_exact_runner_failure(tmp_path):
    calls = 0
    failure = CancelledError("exact later runner cancellation")

    def runner(callback):
        nonlocal calls
        calls += 1
        if calls == 1:
            return joined_runner(callback)
        raise failure

    value = engine(tmp_path, runner=runner)
    value.activate(activation())
    assert value.check_now() == "SCHEDULED"
    committed = value.status_document()["last_receipt_sha256"]
    receipt = tmp_path / "mcx-check/receipts" / f"{committed}.json"
    committed_bytes = receipt.read_bytes()
    with pytest.raises(CancelledError) as caught:
        value.check_now()
    assert caught.value is failure
    assert receipt.read_bytes() == committed_bytes
    assert value.status_document()["last_receipt_sha256"] == committed
    assert value.check_now() == "DENIED"


def test_residual_reproduction_c04_discovery_pages_are_retained_for_readback(tmp_path):
    value = engine(tmp_path)
    status = run(value)
    receipt = json.loads((tmp_path / "mcx-check/receipts" /
                         f"{status['last_receipt_sha256']}.json").read_bytes())
    page_hashes = [item["retained_object_sha256"]
                   for item in receipt["observations"]]
    assert len(page_hashes) == len(PRODUCT_PAGES) + 1
    assert value.retained_discovery_pages(status["last_receipt_sha256"]) == tuple(
        (tmp_path / "mcx-check/objects" / digest).read_bytes()
        for digest in page_hashes)


def test_residual_reproduction_c04_product_page_cannot_be_circular_next_page(tmp_path):
    fixture = FixtureTransport()
    wrong_next = PRODUCT_PAGES["COPPER"]
    first = b'<a href="/docs/fixture.pdf">Gold Mini circular</a>'
    second = b'<a href="/docs/fixture.pdf">Copper circular</a>'

    def wrong_path(url, **bounds):
        if url in PRODUCT_PAGES.values() and url != wrong_next:
            return fixture(url, **bounds)
        if url == CIRCULARS_PAGE:
            return OfficialHttpResponse(url, url, 200, "text/html", first,
                                        circular_from=1, circular_through=300,
                                        page_number=1, page_count=2,
                                        page_item_count=1, next_page_url=wrong_next)
        if url == wrong_next:
            return OfficialHttpResponse(url, url, 200, "text/html", second,
                                        circular_from=301, circular_through=552,
                                        page_number=2, page_count=2,
                                        page_item_count=1, next_page_url=None)
        return fixture(url, **bounds)

    status = run(engine(tmp_path, transport=wrong_path))
    assert status["checker_state"] == CheckerState.FAILED.value
    assert status["last_failure"] == "MCX_CHECK_PAGINATION_INVALID"


def test_c04_changed_discovery_page_retains_history_without_update_available(tmp_path):
    fixture = FixtureTransport()
    times = iter((NOW, NOW + timedelta(minutes=1)))
    value = engine(tmp_path, transport=fixture, clock=lambda: next(times))
    value.activate(activation())
    assert value.check_now() == "SCHEDULED"
    first = value.status_document()["last_receipt_sha256"]
    first_pages = value.retained_discovery_pages(first)
    fixture.pages[PRODUCT_PAGES["GOLDM"]] += b"<!-- official-page-byte-change -->"
    assert value.check_now() == "SCHEDULED"
    status = value.status_document()
    second = status["last_receipt_sha256"]
    second_pages = value.retained_discovery_pages(second)
    assert status["checker_state"] == CheckerState.CURRENT.value
    assert first != second
    assert first_pages[0] != second_pages[0]
    assert first_pages[1:] == second_pages[1:]
    assert (tmp_path / "mcx-check/objects" /
            sha256(first_pages[0]).hexdigest()).read_bytes() == first_pages[0]
    assert (tmp_path / "mcx-check/objects" /
            sha256(second_pages[0]).hexdigest()).read_bytes() == second_pages[0]


@pytest.mark.parametrize("damage", ["missing", "corrupted"])
def test_c04_missing_or_corrupted_discovery_evidence_denies_readback(
        tmp_path, damage):
    value = engine(tmp_path)
    status = run(value)
    receipt = json.loads((tmp_path / "mcx-check/receipts" /
                         f"{status['last_receipt_sha256']}.json").read_bytes())
    digest = receipt["observations"][0]["retained_object_sha256"]
    path = tmp_path / "mcx-check/objects" / digest
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(b"corrupted retained discovery evidence")
    with pytest.raises(OfficialCheckError, match="DISCOVERY_EVIDENCE_INVALID"):
        value.retained_discovery_pages(status["last_receipt_sha256"])


def test_c04_whole_check_candidate_validation_after_deadline_denies_success(
        tmp_path, monkeypatch):
    clock = ControlledMonotonic()
    value = engine(tmp_path, monotonic_clock=clock,
                   check_limits=CheckLimits(max_duration_seconds=10.0))
    actual = value._validate_candidate

    def late_validation(*args):
        result = actual(*args)
        clock.value = 10.5
        return result

    monkeypatch.setattr(value, "_validate_candidate", late_validation)
    status = run(value)
    assert status["checker_state"] == CheckerState.FAILED.value
    assert status["last_failure"] == "MCX_CHECK_DEADLINE_EXPIRED"
    assert status["last_successful_check"] is None


def test_c04_whole_check_receipt_persistence_after_deadline_denies_success(
        tmp_path, monkeypatch):
    clock = ControlledMonotonic()
    value = engine(tmp_path, monotonic_clock=clock,
                   check_limits=CheckLimits(max_duration_seconds=10.0))
    actual = value._immutable_receipt
    committed = []

    def late_receipt(receipt):
        digest = actual(receipt)
        committed.append(digest)
        clock.value = 10.5
        return digest

    monkeypatch.setattr(value, "_immutable_receipt", late_receipt)
    status = run(value)
    assert status["checker_state"] == CheckerState.FAILED.value
    assert status["last_failure"] == "MCX_CHECK_DEADLINE_EXPIRED"
    assert status["last_successful_check"] is None
    assert status["last_receipt_sha256"] is None
    assert (tmp_path / "mcx-check/receipts" / f"{committed[0]}.json").is_file()


def test_c04_whole_check_status_persistence_after_deadline_records_failure(
        tmp_path, monkeypatch):
    clock = ControlledMonotonic()
    value = engine(tmp_path, monotonic_clock=clock,
                   check_limits=CheckLimits(max_duration_seconds=10.0))
    actual = value._atomic_document
    success_status_committed = []

    def late_status(name, document):
        digest = actual(name, document)
        if (name == "status.json"
                and document.get("checker_state") != CheckerState.FAILED.value
                and not success_status_committed):
            success_status_committed.append(digest)
            clock.value = 10.5
        return digest

    monkeypatch.setattr(value, "_atomic_document", late_status)
    status = run(value)
    persisted = json.loads((tmp_path / "mcx-check/status.json").read_bytes())
    assert success_status_committed
    assert status["checker_state"] == CheckerState.FAILED.value
    assert status["last_failure"] == "MCX_CHECK_DEADLINE_EXPIRED"
    assert status["last_successful_check"] is None
    assert persisted["checker_state"] == CheckerState.FAILED.value
    assert persisted["failure"] == "MCX_CHECK_DEADLINE_EXPIRED"


def test_c04_whole_check_exact_deadline_is_denied(tmp_path, monkeypatch):
    clock = ControlledMonotonic()
    value = engine(tmp_path, monotonic_clock=clock,
                   check_limits=CheckLimits(max_duration_seconds=10.0))
    actual = value._immutable_receipt

    def exact_deadline(receipt):
        digest = actual(receipt)
        clock.value = 10.0
        return digest

    monkeypatch.setattr(value, "_immutable_receipt", exact_deadline)
    status = run(value)
    assert status["checker_state"] == CheckerState.FAILED.value
    assert status["last_failure"] == "MCX_CHECK_DEADLINE_EXPIRED"
    assert status["last_successful_check"] is None


def test_c04_whole_check_completion_inside_original_deadline_succeeds(
        tmp_path, monkeypatch):
    clock = ControlledMonotonic()
    value = engine(tmp_path, monotonic_clock=clock,
                   check_limits=CheckLimits(max_duration_seconds=10.0))
    actual = value._atomic_document

    def timely_status(name, document):
        digest = actual(name, document)
        if name == "status.json":
            clock.value = 9.999
        return digest

    monkeypatch.setattr(value, "_atomic_document", timely_status)
    status = run(value)
    assert status["checker_state"] == CheckerState.CURRENT.value
    assert status["last_failure"] is None
    assert status["last_successful_check"] == NOW.isoformat()


def test_c04_whole_check_late_attempt_preserves_prior_success_and_evidence(
        tmp_path, monkeypatch):
    clock = ControlledMonotonic()
    utc_times = iter((NOW, NOW + timedelta(minutes=1)))
    value = engine(tmp_path, clock=lambda: next(utc_times), monotonic_clock=clock,
                   check_limits=CheckLimits(max_duration_seconds=10.0))
    value.activate(activation())
    assert value.check_now() == "SCHEDULED"
    prior = value.status_document()
    prior_receipts = {path.name for path in (tmp_path / "mcx-check/receipts").iterdir()}
    prior_objects = {path.name for path in (tmp_path / "mcx-check/objects").iterdir()}
    actual = value._immutable_receipt
    clock.value = 100.0

    def late_receipt(receipt):
        digest = actual(receipt)
        clock.value = 110.0
        return digest

    monkeypatch.setattr(value, "_immutable_receipt", late_receipt)
    assert value.check_now() == "SCHEDULED"
    status = value.status_document()
    persisted = json.loads((tmp_path / "mcx-check/status.json").read_bytes())
    final_receipts = {path.name for path in (tmp_path / "mcx-check/receipts").iterdir()}
    assert status["checker_state"] == CheckerState.FAILED.value
    assert status["last_failure"] == "MCX_CHECK_DEADLINE_EXPIRED"
    assert status["last_successful_check"] == prior["last_successful_check"]
    assert status["last_receipt_sha256"] == prior["last_receipt_sha256"]
    assert prior_receipts < final_receipts
    assert prior_objects <= {path.name for path in (tmp_path / "mcx-check/objects").iterdir()}
    late_receipt = (final_receipts - prior_receipts).pop().removesuffix(".json")
    assert persisted["attempt_receipt_sha256"] == late_receipt


def test_s303_preferences_off_keeps_manual_checks_and_survives_restart(tmp_path):
    transport = FixtureTransport()
    value = engine(tmp_path, transport=transport)
    value.activate(activation())
    value.configure(automatic_check_enabled=False, frequency=CheckFrequency.WEEKLY)
    assert value.trigger_scheduled(observed=99999999.0) == 'DISABLED'
    assert transport.calls == []
    assert value.check_now() == 'SCHEDULED'
    assert transport.calls
    recovered = engine(tmp_path, transport=FixtureTransport())
    recovered.activate(activation())
    assert recovered.status_document()['automatic_check_enabled'] is False
    assert recovered.frequency is CheckFrequency.WEEKLY
    assert recovered.trigger_scheduled(observed=99999999.0) == 'DISABLED'
    assert recovered.check_now() == 'SCHEDULED'


def test_s303_restart_catch_up_uses_retained_attempt_not_restart_time(tmp_path):
    first = engine(tmp_path)
    first.activate(activation())
    assert first.trigger_scheduled() == 'SCHEDULED'
    original_due = first.status_document()['next_scheduled_check']
    for offset in (timedelta(hours=12), timedelta(hours=20)):
        transport = FixtureTransport()
        restarted = engine(tmp_path, transport=transport, clock=lambda: NOW + offset)
        restarted.activate(activation())
        assert restarted.status_document()['next_scheduled_check'] == original_due
        assert restarted.trigger_scheduled() == 'NOT_DUE'
        assert transport.calls == []
    overdue = engine(tmp_path, clock=lambda: NOW + timedelta(days=2))
    assert overdue.trigger_scheduled() == 'DENIED'
    overdue.activate(activation())
    assert overdue.trigger_scheduled() == 'SCHEDULED'


def test_s303_settings_projection_has_no_network_or_persistence(tmp_path):
    transport = FixtureTransport()
    value = engine(tmp_path, transport=transport)
    assert value.settings_status()['coverage']['families']['GOLDM']['e2']
    assert not value.store_root.exists() and transport.calls == []
    value.activate(activation())
    before = {p.relative_to(value.store_root): p.read_bytes()
              for p in value.store_root.rglob('*') if p.is_file()}
    for _ in range(3):
        assert 'worker_thread_identity' not in value.settings_status()
    assert before == {p.relative_to(value.store_root): p.read_bytes()
                      for p in value.store_root.rglob('*') if p.is_file()}
    assert transport.calls == []


@pytest.mark.parametrize('status,location', [(403, None), (302, 'https://example.invalid/denied')])
def test_s303_real_transport_denials_retain_exact_response_without_external_network(
        tmp_path, monkeypatch, status, location):
    import kronos.application.mcx_official_check as module
    calls = []
    body = b'<html><title>Access Denied</title></html>'
    class Response:
        def __init__(self):
            self.status = status
        def getheader(self, key, default=None):
            return {'Content-Type': 'text/html', 'Location': location}.get(key, default)
        def read(self, limit):
            assert limit == MAX_PAGE_BYTES + 1
            return body
    class Connection:
        def __init__(self, host, **kwargs):
            calls.append((host, kwargs)); self.sock = self
        def connect(self): pass
        def settimeout(self, value): assert 0 < value <= 15
        def request(self, method, path, headers):
            assert method == 'GET' and path == '/products/bullion/gold'
        def getresponse(self): return Response()
        def close(self): calls.append('CLOSED')
    monkeypatch.setattr(module.http.client, 'HTTPSConnection', Connection)
    value = engine(tmp_path, transport=module.OfficialHttpsTransport())
    result = run(value)
    assert result['checker_state'] == 'FAILED'
    assert len(calls) == 2 and calls[-1] == 'CLOSED'
    assert (value.store_root / 'objects' / sha256(body).hexdigest()).read_bytes() == body
    persisted = json.loads((value.store_root / 'status.json').read_bytes())
    failed = json.loads((value.store_root / 'receipts' /
                        (persisted['failure_receipt_sha256'] + '.json')).read_bytes())
    assert failed['scan_complete'] is False and failed['observed_requests'] == 1
    assert failed['responses'][0]['retained_object_sha256'] == sha256(body).hexdigest()


def test_s303_redirect_requests_share_original_aggregate_limits(tmp_path):
    import kronos.application.mcx_official_check as module
    calls = []
    destination = PRODUCT_PAGES['SILVERM']
    def redirected(url, **bounds):
        calls.append(url)
        if len(calls) == 1:
            return OfficialHttpResponse(url, url, 302, 'text/html', b'redirect', location=destination)
        return OfficialHttpResponse(url, url, 200, 'text/html', b'page')
    value = engine(tmp_path, transport=redirected, check_limits=CheckLimits(max_requests=1))
    value.activate(activation())
    scope = module._CheckScope(100.0)
    with pytest.raises(OfficialCheckError, match='LIMIT_EXHAUSTED'):
        value._fetch(PRODUCT_PAGES['GOLDM'], document=False, scope=scope)
    assert calls == [PRODUCT_PAGES['GOLDM']]
    assert scope.requests == 2


@pytest.mark.parametrize('family,filename,digest', [
    ('GOLDM','gold','123c2131d4120b1389dfc6aa6ddd293d40e76418849306681fca425fafc1cf93'),
    ('SILVERM','silver','8e569e6cefc78de66f9ef60c1a057c7c5a06ac0b506bee7b65602e9b265b0018'),
    ('COPPER','copper','488dff78365574b7909324eab302bc03a070266136aa821cb9724f15b44139f3'),
    ('CRUDEOIL','crude-oil','6cf383ce0c2583f1207870574332e5d5c76b56b3fd755c8048da3a68528d232b'),
    ('NATURALGAS','natural-gas','6fcf5ddfbeb1b0ec20d42335293b5f53f039aa228afef813e2c4ce2946a9570c')])
def test_s303_observed_official_product_parser(tmp_path, family, filename, digest):
    """Exact Chrome rendered DOM capture, not an invented HTTP response."""
    import kronos.application.mcx_official_check as module
    evidence = Path(__file__).resolve().parents[4] / 'evidence/official'
    raw = (evidence / (filename + '.rendered-dom.html')).read_bytes()
    assert sha256(raw).hexdigest() == digest
    parser = module._Links(); parser.feed(raw.decode())
    selected = [(url, text) for url, text, section in parser.links
                if section == family and '.pdf' in url.lower()]
    assert selected
    assert any('contract' in url.lower() or 'contract' in text.lower() for url, text in selected)
    if family in {'CRUDEOIL','NATURALGAS'}:
        # The actual full Natural Gas section links a shared leaflet whose
        # filename contains "mini". Contract accordions must still exclude
        # the separate Mini contract section; discovery is not semantic approval.
        assert all('mini' not in url.lower() for url, _ in selected
                   if 'leaflet' not in url.lower())


def test_s303_observed_circular_page_cannot_supply_invented_completeness(tmp_path, monkeypatch):
    import kronos.application.mcx_official_check as module
    evidence = Path(__file__).resolve().parents[4] / 'evidence/official'
    raw = (evidence / 'circulars.rendered-dom.html').read_bytes()
    assert sha256(raw).hexdigest() == 'b73c9c73d9626e2ab8b201b579ddc5666d88ba38b3c6601a384fae30b29be8fc'
    assert b'data-page="2"' in raw and b'href="#"' in raw
    class Response:
        status = 200
        def getheader(self, name, default=None): return 'text/html' if name == 'Content-Type' else default
        def read(self, size): return raw
    class Connection:
        def __init__(self,*a,**k): self.sock = self
        def connect(self): pass
        def settimeout(self,*a): pass
        def request(self,*a,**k): pass
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr(module.http.client, 'HTTPSConnection', Connection)
    response = module.OfficialHttpsTransport()(CIRCULARS_PAGE, connect_timeout_seconds=5,
        read_timeout_seconds=15, max_bytes=MAX_PAGE_BYTES, max_redirects=3)
    assert response.complete is False
    assert response.page_count is None and response.circular_through is None
    with pytest.raises(OfficialCheckError):
        module._validate_response(response, expected_url=CIRCULARS_PAGE, document=False)
