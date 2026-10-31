"""TE-03A: real exchange bytes, candidate facts, synthetic review/method gates.

Fixture review references are NOT owner approvals. No production composition,
Provider, acquisition, broker, network or genuine Question is commissioned.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo

import pytest

from kronos.instrument.option_series import (
    DEFAULT_OPTION_ROOT, FAMILIES, OptionAuthorityError, PublicationPin, SETTLEMENT,
    aware, canonical_bytes, load_option_series, read_exact)
from kronos.market.calendar import MarketCalendarPublisher
from kronos.market.option_authority import OptionAuthorityReview
from kronos.market.option_expiry import DEFAULT_EXPIRY_ROOT, load_option_expiries
from kronos.theta.contracts import SUBJECTS, ThetaError, encode
from kronos.theta.target_authority import OwnerOptionAuthority, ThetaTargetAuthorityAdapter
from tests.unit.theta.test_question_packs import packs, commission, question

HISTORICAL_AT = datetime.fromisoformat("2026-10-12T12:00:00+05:30")
AT = datetime.fromisoformat("2026-10-28T14:00:00+05:30")
EXPECTED = {
    "GOLDM": (("2026-10-29","2026-11-05"),("2026-11-27","2026-12-04")),
    "SILVERM": (("2026-11-23","2026-11-30"),("2026-12-28","2027-02-26")),
    "COPPER": (("2026-11-23","2026-11-30"),("2026-12-23","2026-12-31")),
    "CRUDEOIL": (("2026-11-17","2026-11-19"),("2026-12-16","2026-12-18")),
    "NATURALGAS": (("2026-11-20","2026-11-24"),("2026-12-23","2026-12-28")),
}
LOSS = {
    "GOLDM": "2026-11-27T23:55:00+05:30",
    "SILVERM": "2026-11-23T23:55:00+05:30",
    "COPPER": "2026-11-23T23:55:00+05:30",
    "CRUDEOIL": "2026-11-17T23:55:00+05:30",
    "NATURALGAS": "2026-11-20T23:55:00+05:30",
}
UNITS = {"GOLDM":"INR per 10 grams","SILVERM":"INR per kilogram",
         "COPPER":"INR per kilogram","CRUDEOIL":"INR per barrel","NATURALGAS":"INR per MMBtu"}


@pytest.fixture
def owner():
    return OwnerOptionAuthority()


@pytest.fixture
def files(tmp_path):
    instrument = tmp_path.resolve()/"instrument"
    market = tmp_path.resolve()/"market"
    shutil.copytree(DEFAULT_OPTION_ROOT,instrument)
    shutil.copytree(DEFAULT_EXPIRY_ROOT,market)
    return instrument, market


def update(files, mutate_instrument=None, mutate_market=None, mutate_current=None):
    """Build a newly pinned TEST candidate. Never edit the retained publication."""
    i,m=files
    current=json.loads((m/"current.json").read_bytes())
    instrument=json.loads((i/current["instrument"]["filename"]).read_bytes())
    market=json.loads((m/current["market"]["filename"]).read_bytes())
    if mutate_instrument:
        mutate_instrument(instrument)
        payload=canonical_bytes(instrument)
        (i/current["instrument"]["filename"]).write_bytes(payload)
        current["instrument"]["sha256"]=sha256(payload).hexdigest()
        market["instrument_reference"]=PublicationPin(**current["instrument"]).reference
    if mutate_market: mutate_market(market)
    payload=canonical_bytes(market)
    (m/current["market"]["filename"]).write_bytes(payload)
    current["market"]["sha256"]=sha256(payload).hexdigest()
    if mutate_current: mutate_current(current)
    (m/"current.json").write_bytes(canonical_bytes(current))
    return current


def local_owner(files):
    return OwnerOptionAuthority(instrument_root=files[0],market_root=files[1])


def predecessor_owner(files):
    """Select exact retained 2026.2.0 bytes with a synthetic test pointer."""
    i,m=files
    current=json.loads((m/"current-2026.1.0.json").read_bytes())
    current.update(identity="SYNTHETIC-TEST-CURRENT-2026.2.0",
        effective_from="2026-10-12T04:32:40Z",
        effective_through="2026-12-31T23:59:59+05:30",
        supersedes=current["identity"],owner_reviews={k:None for k in current["owner_reviews"]})
    for key,root,name in (("instrument",i,"2026.2.0.json"),("market",m,"2026.2.0.json")):
        payload=(root/name).read_bytes()
        value=json.loads(payload)
        current[key]={"identity":value["publication_identity"],"version":"2026.2.0",
                      "sha256":sha256(payload).hexdigest(),"filename":name}
    (m/"current.json").write_bytes(canonical_bytes(current))
    return local_owner(files)


def test_retained_candidate_is_not_owner_qualified(owner):
    assert len(owner.instrument.rows)==25
    assert set(r.family for r in owner.instrument.rows)==set(SUBJECTS)
    assert all(v is None for v in owner.current["owner_reviews"].values())
    with pytest.raises(ThetaError,match="THETA_TARGET_OWNER_QUALIFICATION_REQUIRED"):
        ThetaTargetAuthorityAdapter(owner)(SUBJECTS,AT)


@pytest.mark.parametrize("family",SUBJECTS)
def test_five_families_exact_source_bound_candidate_targets(owner,family):
    targets=owner.resolve(family,AT)
    assert [t.horizon for t in targets]==["E1","E2"]
    assert tuple((t.series.expiry.isoformat(),t.series.futures_expiry.isoformat()) for t in targets)==EXPECTED[family]
    for t in targets:
        assert t.series.quotation_unit==UNITS[family] and t.series.settlement_reference==SETTLEMENT
        assert t.endpoint.expires_at.date()==t.series.expiry and t.endpoint.expires_at.tzinfo.key=="Asia/Kolkata"
        assert t.series.identity in t.endpoint.session_identity
        assert t.instrument_reference==owner.instrument.pin.reference
        assert t.market_reference==owner.market.pin.reference
        assert t.endpoint.source_provenance and all("SHA256:" in p for p in t.endpoint.source_provenance)
        assert not t.owner_qualified
    assert owner.resolve(family,AT+timedelta(days=1))[0].series.identity==targets[0].series.identity


def test_actual_current_clock_selects_two_for_all_five_families(owner,record_property):
    observed=datetime.now(ZoneInfo("Asia/Kolkata"))
    assert owner.first <= observed <= owner.last
    assert {family:tuple((t.series.expiry.isoformat(),t.series.futures_expiry.isoformat())
            for t in owner.resolve(family,observed)) for family in SUBJECTS}==EXPECTED
    record_property("actual_IST_observed",observed.isoformat())
    record_property("owner_qualified","false; successor review pending")


def test_corrected_silver_future_differs_and_historical_same_future_remains(files,owner):
    silver=owner.resolve("SILVERM",AT)
    assert silver[0].series.underlying_future!=silver[1].series.underlying_future
    assert silver[0].series.series_kind=="BI_MONTHLY" and silver[1].series.series_kind=="MONTHLY"
    historical=predecessor_owner(files).resolve("SILVERM",HISTORICAL_AT)
    assert historical[0].series.underlying_future==historical[1].series.underlying_future
    for family in set(SUBJECTS)-{"SILVERM"}:
        t=owner.resolve(family,AT)
        assert t[0].series.underlying_future!=t[1].series.underlying_future


def test_parsed_dates_and_actual_instant_not_string_or_source_order(files):
    update(files,mutate_instrument=lambda d:d["series"].reverse())
    owner=local_owner(files)
    assert owner.resolve("SILVERM",AT)==owner.resolve("SILVERM",AT.astimezone(timezone.utc))
    e1=owner.resolve("GOLDM",AT)[0]
    assert owner.resolve("GOLDM",e1.endpoint.expires_at-timedelta(microseconds=1))[0]==e1
    moved=owner.resolve("GOLDM",e1.endpoint.expires_at)
    assert tuple(t.series.expiry.isoformat() for t in moved)==("2026-11-27","2026-12-29")


def test_copper_option_session_not_future_cutoff_and_calendar_issue_explicit(files,owner):
    targets=owner.resolve("COPPER",AT)
    assert targets[0].endpoint.expires_at.hour==23
    assert targets[0].endpoint.expires_at.minute==55
    assert "OPTION_SESSION" in targets[0].endpoint.session_identity
    assert targets[0].endpoint.expires_at.hour!=17
    # Additive option authority uses the explicit MCX DST-dependent rule and
    # retained NIST 2026 evidence. It DOES NOT rewrite futures calendar clocks.
    assert targets[1].endpoint.expires_at.minute==55
    base=MarketCalendarPublisher().publication("MCX")
    assert base.trading_dates[targets[1].series.expiry].windows[0].window_close.minute==30
    historical=predecessor_owner(files).resolve("COPPER",HISTORICAL_AT)
    assert historical[0].endpoint.expires_at.minute==30
    assert not targets[1].owner_qualified


@pytest.mark.parametrize("field,value,code",[
    ("underlying_future","","UNDERLYING_INVALID"),
    ("underlying_future","MCX-FUT-GOLDM-2026-11-05","UNDERLYING_INVALID"),
    ("settlement_reference","","SETTLEMENT_UNAVAILABLE"),
    ("settlement_reference","FUTURES_EXPIRY_DDR","SETTLEMENT_UNAVAILABLE"),
    ("quotation_unit","","UNIT_UNAVAILABLE"),
    ("source_ids",[],"SOURCE_INVALID"),
    ("source_ids",["FOREIGN"],"SOURCE_INVALID"),
])
def test_missing_conflicting_relationship_reference_unit_source_fail_closed(files,field,value,code):
    update(files,mutate_instrument=lambda d:d["series"][-1].update({field:value}))
    with pytest.raises(OptionAuthorityError,match=code): local_owner(files)


def test_ambiguous_series_not_tied_by_symbol_token_or_directory_order(files):
    update(files,mutate_instrument=lambda d:d["series"].append(deepcopy(d["series"][-1])))
    with pytest.raises(OptionAuthorityError,match="SERIES_AMBIGUOUS"): local_owner(files)


@pytest.mark.parametrize("change,code",[
    (lambda d:d.update(instrument_reference="FOREIGN"),"OWNER_CONFLICT"),
    (lambda d:d.update(base_calendar_reference="FOREIGN"),"CALENDAR_STALE"),
    (lambda d:d.update(coverage_end="2027-01-31"),"COVERAGE_UNAVAILABLE"),
    (lambda d:d["rules"][3].update(expiry_rule="UNAPPROVED_RULE"),"RULE_UNAVAILABLE"),
    (lambda d:d["rules"][3].update(session_rule="FUTURES_17_00"),"INTEGRITY_INVALID"),
])
def test_market_authority_conflicts_and_no_calendar_extrapolation(files,change,code):
    update(files,mutate_market=change)
    with pytest.raises(OptionAuthorityError,match=code): local_owner(files)


def test_missing_second_target_and_stale_2027_fail_closed(owner):
    with pytest.raises(OptionAuthorityError,match="E2_UNAVAILABLE"):
        owner.resolve("CRUDEOIL",datetime.fromisoformat("2026-11-18T12:00:00+05:30"))
    with pytest.raises(OptionAuthorityError,match="PUBLICATION_STALE"):
        owner.resolve("GOLDM",datetime.fromisoformat("2027-01-01T12:00:00+05:30"))
    with pytest.raises(OptionAuthorityError,match="PUBLICATION_STALE"):
        owner.resolve("GOLDM",AT-timedelta(days=1))


def test_source_bytes_tamper_not_accepted(files):
    p=files[0]/"sources/goldm-options.pdf"
    p.write_bytes(p.read_bytes()+b"tamper")
    with pytest.raises(OptionAuthorityError,match="SOURCE_INVALID"): local_owner(files)


@pytest.mark.parametrize("name,operation,code",[
    ("silverm-options-december-2026-onwards.pdf","missing","ARTIFACT_UNAVAILABLE"),
    ("silverm-futures-february-2027-onwards.pdf","corrupt","SOURCE_INVALID"),
    ("mcx-circular-552-2026.pdf","missing","ARTIFACT_UNAVAILABLE"),
    ("mcx-circular-552-2026.pdf","corrupt","SOURCE_INVALID"),
    ("mcx-circular-095-2026.pdf","missing","ARTIFACT_UNAVAILABLE"),
    ("mcx-circular-095-2026.pdf","corrupt","SOURCE_INVALID"),
])
def test_new_official_source_missing_or_corrupt_fails_closed(files,name,operation,code):
    path=files[0]/"sources"/name
    if operation=="missing": path.unlink()
    else: path.write_bytes(path.read_bytes()+b"corrupt")
    with pytest.raises(OptionAuthorityError,match=code): local_owner(files)


def test_exact_date_publications_are_pinned_and_bound_to_the_owning_rows(files,owner):
    instrument=json.loads((files[0]/"2026.3.0.json").read_bytes())
    sources={source["identity"]:source for source in instrument["sources"]}
    expected={
        "MCX-TRD-552-2026":{
            "filename":"sources/mcx-circular-552-2026.pdf",
            "reference":"MCX/TRD/552/2026",
            "published_on":"2026-09-29",
            "sha256":"8dd99b01ea1d1d9f10f29f4439dc34bb336df2a0a745312be3e7bfc6de39df03",
            "page":"page 3",
        },
        "MCX-TRD-095-2026":{
            "filename":"sources/mcx-circular-095-2026.pdf",
            "reference":"MCX/TRD/095/2026",
            "published_on":"2026-02-26",
            "sha256":"13a0433578982b2ae9a44e6ccf8ab473aa998c45b8be347a720b0766d0e94b94",
            "page":"page 5",
        },
    }
    for identity,binding in expected.items():
        source=sources[identity]
        assert all(source[field]==value for field,value in binding.items() if field!="page")
        assert binding["page"] in source["effective_scope"]
        assert sha256((files[0]/source["filename"]).read_bytes()).hexdigest()==source["sha256"]
        assert f"{identity}/SHA256:{source['sha256']}" in owner.instrument.source_provenance

    silver_spec=sources["SILVERM-FUT-FEB2027-ONWARDS"]
    assert silver_spec["published_on"]=="2026-07-17"
    assert "exact consolidated-specification publication date remains unavailable" in silver_spec["effective_scope"]
    assert "not the exact 26 February date" in silver_spec["effective_scope"]

    rows={(row["family"],row["expiry"]):row for row in instrument["series"]}
    gold=rows[("GOLDM","2026-12-29")]
    silver=rows[("SILVERM","2026-12-28")]
    assert "MCX-TRD-552-2026" in gold["source_ids"] and "Annexure 2 page 3" in gold["source_locator"]
    assert "MCX-TRD-095-2026" in silver["source_ids"] and "Annexure 2 page 5" in silver["source_locator"]
    assert "without independently proving the exact date" in silver["source_locator"]

    current=json.loads((files[1]/"current.json").read_bytes())
    market=json.loads((files[1]/current["market"]["filename"]).read_bytes())
    rules={(rule["family"],rule["series_kind"]):rule for rule in market["rules"]}
    assert "MCX-TRD-552-2026" in rules[("GOLDM","MONTHLY")]["source_ids"]
    assert "MCX-TRD-095-2026" in rules[("SILVERM","MONTHLY")]["source_ids"]


@pytest.mark.parametrize("filename",["../escape.json","/escape.json","sources/../../escape.json"])
def test_path_traversal_fails_closed(files,filename):
    with pytest.raises(OptionAuthorityError,match="PATH_INVALID"): read_exact(files[0],filename)


def test_symlink_source_fails_closed(files):
    p=files[0]/"sources/goldm-options.pdf"; payload=p.read_bytes(); p.unlink()
    outside=files[0].parent/"outside.pdf"; outside.write_bytes(payload); p.symlink_to(outside)
    with pytest.raises(OptionAuthorityError,match="ARTIFACT_UNAVAILABLE"): local_owner(files)


def test_explicit_pin_no_latest_mtime_authority(files):
    owner=local_owner(files)
    (files[0]/"9999-latest.json").write_bytes(b"{}")
    (files[1]/"9999-latest.json").write_bytes(b"{}")
    assert local_owner(files).resolve("SILVERM",AT)==owner.resolve("SILVERM",AT)


def test_owner_currentness_supersession_no_cached_fallback(files):
    old=local_owner(files); before=deepcopy(old.instrument)
    update(files,mutate_current=lambda d:d.update(identity="SUCCESSOR-CURRENT",supersedes=d["identity"]))
    with pytest.raises(OptionAuthorityError,match="PUBLICATION_SUPERSEDED"): old.resolve("COPPER",AT)
    new=local_owner(files)
    assert new.resolve("COPPER",AT)[0].authority_currentness_reference!=before.pin.reference
    assert old.instrument==before


def test_publication_successor_keeps_predecessor_bytes_and_historical_records(files):
    i,m=files; old=local_owner(files); historical=old.resolve("SILVERM",AT)
    before_i=(i/old.instrument.pin.filename).read_bytes(); before_m=(m/old.market.pin.filename).read_bytes()
    instrument=json.loads(before_i); market=json.loads(before_m)
    instrument.update(publication_version="2026.3.1",supersedes=old.instrument.pin.reference)
    # Explicit successor TEST publication, not mtime/filename currentness.
    instrument["series"][-1]["source_locator"]+="; SYNTHETIC TEST amendment/requalification"
    encoded=canonical_bytes(instrument); (i/"2026.3.1.json").write_bytes(encoded)
    ip=PublicationPin(old.instrument.pin.identity,"2026.3.1",sha256(encoded).hexdigest(),"2026.3.1.json")
    market.update(publication_version="2026.3.1",supersedes=old.market.pin.reference,
                  instrument_reference=ip.reference)
    encoded=canonical_bytes(market); (m/"2026.3.1.json").write_bytes(encoded)
    mp=PublicationPin(old.market.pin.identity,"2026.3.1",sha256(encoded).hexdigest(),"2026.3.1.json")
    current=deepcopy(old.current)
    current.update(identity="SYNTHETIC-SUCCESSOR-CURRENT",supersedes=old.current["identity"],
                   instrument=asdict(ip),market=asdict(mp),owner_reviews={k:None for k in current["owner_reviews"]})
    (m/"current.json").write_bytes(canonical_bytes(current))
    successor=local_owner(files).resolve("SILVERM",AT)
    assert successor[0].series.expiry==historical[0].series.expiry
    assert successor[0].instrument_reference!=historical[0].instrument_reference
    assert successor[0].market_reference!=historical[0].market_reference
    assert (i/old.instrument.pin.filename).read_bytes()==before_i and (m/old.market.pin.filename).read_bytes()==before_m
    assert historical[0].series.expiry.isoformat()=="2026-11-23"
    with pytest.raises(OptionAuthorityError,match="PUBLICATION_SUPERSEDED"): old.resolve("SILVERM",AT)


@pytest.mark.parametrize("mutation",[
    lambda d:d["supporting_source"].update(sha256="0"*64),
    lambda d:d["supporting_source"].update(official_uri="https://foreign.example/dst"),
    lambda d:d.update(session_periods=[]),
    lambda d:d["session_periods"][1].update(start="2026-11-02"),
    lambda d:d["session_periods"][1].update(normal_close="17:00:00"),
])
def test_session_provenance_gaps_and_unsupported_clock_fail_closed(files,mutation):
    update(files,mutate_market=mutation)
    with pytest.raises(OptionAuthorityError): local_owner(files)


def qualified_fixture(files):
    owner=local_owner(files)
    review=OptionAuthorityReview("SYNTHETIC-TEST-REVIEW-NOT-OWNER-APPROVAL",
        owner.instrument.pin.reference,owner.market.pin.reference,owner.current_sha256,
        "APPROVED","APPROVED")
    return OwnerOptionAuthority(instrument_root=files[0],market_root=files[1],review=review)


def test_adapter_provider_neutral_and_methodology_separate(files):
    owner=qualified_fixture(files)
    adapter=ThetaTargetAuthorityAdapter(owner)
    assert len(adapter.resolve_targets(SUBJECTS,AT))==10
    with pytest.raises(ThetaError,match="THETA_METHODOLOGY_UNAVAILABLE"): adapter(SUBJECTS,AT)
    bundle=ThetaTargetAuthorityAdapter(owner,methodology_reference="SYNTHETIC-TEST-METHOD",
        methodology_instructions="SYNTHETIC ONLY NOT FOR GENUINE FORECASTING")(SUBJECTS,AT)
    payload=encode(bundle.for_subjects(SUBJECTS,AT)).upper()
    assert not any(word in payload for word in [b"KITE",b"TOKEN",b"PROVIDER",b"BROKER",b"ACCOUNT"])
    assert all(unit in bundle.methodology_instructions for unit in UNITS.values())


def test_te02_target_gate_reports_owner_then_methodology_not_conflated(packs,files):
    packs.clock=lambda:AT
    packs.authority_provider=ThetaTargetAuthorityAdapter(local_owner(files))
    result=packs.commission_questions(SUBJECTS)
    assert {s["failure"] for s in result["states"].values()}=={"THETA_TARGET_OWNER_QUALIFICATION_REQUIRED"}
    packs.authority_provider=ThetaTargetAuthorityAdapter(qualified_fixture(files))
    result=packs.commission_questions(SUBJECTS)
    assert {s["failure"] for s in result["states"].values()}=={"THETA_METHODOLOGY_UNAVAILABLE"}
    assert packs.store.current().get("question_batch") is None


def test_te02_exact_exchange_candidate_targets_synthetic_method_and_historical_immutability(packs,files):
    old=commission(packs)
    previous={s:(question(packs,old,s),packs.transport(old["states"][s]["question_id"],"pdf")) for s in SUBJECTS}
    packs.clock=lambda:AT
    packs.authority_provider=ThetaTargetAuthorityAdapter(qualified_fixture(files),
        methodology_reference="SYNTHETIC-TEST-METHOD",methodology_instructions="SYNTHETIC ONLY")
    new=commission(packs)
    for subject in SUBJECTS:
        q=question(packs,new,subject)
        assert q["synthetic"] and all(t["settlement_reference"]==SETTLEMENT for t in q["targets"])
        assert tuple((t["option_expiry"],t["futures_expiry"]) for t in q["targets"])==EXPECTED[subject]
        oldq,oldpdf=previous[subject]
        assert packs.store.question(oldq["question_id"])==oldq
        assert packs.transport(oldq["question_id"],"pdf")==oldpdf


def test_retained_evidence_report(owner,request):
    destination=request.config.getoption("--theta-qualification-output")
    if destination is None: return
    path=Path(destination).resolve(); path.mkdir(parents=True,exist_ok=True)
    report={"status":"CANDIDATE_NOT_OWNER_QUALIFIED", "commissioning_test_boundary":AT.isoformat(),
        "source_count":len(owner.instrument.source_provenance),"series_count":len(owner.instrument.rows),
        "instrument_pin":asdict(owner.instrument.pin),"market_pin":asdict(owner.market.pin),
        "owner_reviews":owner.current["owner_reviews"],
        "methodology_authority":"NOT_ESTABLISHED", "provider_calls":0,"broker_operations":0,
        "november_endpoint":"CANDIDATE DERIVED 23:55 from MCX option specifications + NIST DST 2026; owner qualification pending; futures clocks unchanged",
        "targets":{s:[asdict(t) for t in owner.resolve(s,AT)] for s in SUBJECTS}}
    (path/"te03a-target-evidence.json").write_text(json.dumps(report,indent=2,default=str)+"\n")


@pytest.mark.parametrize("family",SUBJECTS)
def test_exact_endpoint_rollover_for_every_family(owner,family):
    original=owner.resolve(family,AT)
    endpoint=original[0].endpoint.expires_at
    assert owner.resolve(family,endpoint-timedelta(microseconds=1))==original
    for at in (endpoint,endpoint+timedelta(microseconds=1),endpoint.astimezone(timezone.utc)):
        if family != "GOLDM":
            with pytest.raises(OptionAuthorityError,match="E2_UNAVAILABLE"):
                owner.resolve(family,at)
        else:
            moved=owner.resolve(family,at)
            assert moved[0].series==original[1].series
            assert moved[0].horizon=="E1" and moved[1].horizon=="E2"
            assert moved[1].series.expiry.month==12
            assert moved[1].series.identity!=original[1].series.identity


@pytest.mark.parametrize("family",SUBJECTS)
def test_first_two_expiry_coverage_loss_instant_drives_warning_boundary(owner,family):
    loss=datetime.fromisoformat(LOSS[family])
    before=owner.resolve(family,loss-timedelta(microseconds=1))
    assert len(before)==2 and before[0].endpoint.expires_at==loss
    with pytest.raises(OptionAuthorityError,match="E2_UNAVAILABLE"):
        owner.resolve(family,loss)


@pytest.mark.parametrize("field",["instrument_reference","market_reference","current_sha256",
                                  "instrument_disposition","market_disposition"])
def test_review_is_bound_to_both_domains_and_exact_current_bytes(files,field):
    owner=qualified_fixture(files)
    review=replace(owner.review,**{field:"FOREIGN"})
    with pytest.raises(OptionAuthorityError,match="REVIEW_INVALID"):
        OwnerOptionAuthority(instrument_root=files[0],market_root=files[1],review=review)


def test_nonempty_strings_do_not_commission_a_review(files):
    update(files,mutate_current=lambda d:d.update(owner_reviews={k:"APPROVED" for k in d["owner_reviews"]}))
    with pytest.raises(ThetaError,match="OWNER_QUALIFICATION_REQUIRED"):
        ThetaTargetAuthorityAdapter(local_owner(files))(SUBJECTS,AT)


def test_real_static_owner_review_activates_exact_current_bytes():
    from kronos.theta.operational import (
        CURRENT_SHA256, INSTRUMENT_REFERENCE, MARKET_REFERENCE, reviewed_owner)
    owner=reviewed_owner()
    assert owner.review.review_reference=="KRONOS-S3-01-O1-ATTRIBUTED-OWNER-REVIEW-20261028"
    assert owner.review.instrument_reference==owner.instrument.pin.reference==INSTRUMENT_REFERENCE
    assert owner.review.market_reference==owner.market.pin.reference==MARKET_REFERENCE
    assert owner.review.current_sha256==owner.current_sha256==CURRENT_SHA256
    assert all(v is None for v in owner.current["owner_reviews"].values())
    assert all(t.owner_qualified for subject in SUBJECTS for t in owner.resolve(subject,AT))


def test_predecessor_static_review_cannot_activate_new_current_bytes():
    review=OptionAuthorityReview("KRONOS-CA-TE03A-20261012",
        "KRONOS-MCX-OPTION-SERIES-2026/2026.2.0/SHA256:6fb82deb2485d1098f848257b23417caf494eece91fbdeced7988edab284a97e",
        "KRONOS-MCX-OPTION-EXPIRY-2026/2026.2.0/SHA256:c34f63e6c59c8c02edb0d21ebeeef1479583e6653422bc2b73bd0213c3adde05",
        "bfd2f9c50c823455e124cccf50722d05a92cacaf8665d6b6968d1327940dda1d",
        "APPROVED","APPROVED")
    with pytest.raises(OptionAuthorityError,match="OPTION_AUTHORITY_REVIEW_INVALID"):
        OwnerOptionAuthority(review=review)


def test_loaded_authority_detects_later_source_corruption(files):
    owner=qualified_fixture(files)
    p=files[0]/"sources/copper-options.pdf"
    p.write_bytes(p.read_bytes()+b"tamper")
    with pytest.raises(OptionAuthorityError,match="SOURCE_INVALID"):
        owner.resolve("COPPER",AT)


@pytest.mark.parametrize("mutate",[
    lambda d:d["series"][0].update(futures_expiry="invalid"),
    lambda d:d["series"][0].pop("futures_expiry"),
    lambda d:d["series"][0].update(quotation_unit="INR per wrong unit"),
    lambda d:d["series"][0].update(identity="FOREIGN"),
    lambda d:d.update(series=None),
    lambda d:d.update(sources=None),
])
def test_malformed_publications_have_typed_failures(files,mutate):
    update(files,mutate_instrument=mutate)
    with pytest.raises(OptionAuthorityError,match="OPTION_AUTHORITY_"): local_owner(files)


def test_qualification_does_not_transfer_to_amended_publication(files):
    old=qualified_fixture(files)
    update(files,mutate_instrument=lambda d:d["series"][0].update(source_locator="Amended source assertion"))
    with pytest.raises(OptionAuthorityError,match="REVIEW_INVALID"):
        OwnerOptionAuthority(instrument_root=files[0],market_root=files[1],review=old.review)


def test_te04a_binding_compatibility_without_contract_changes(files):
    from kronos.theta.contracts_v3 import make_question_v3,make_question_batch_v3,combined_answer_template
    from tests.unit.theta.v3_fixture import synthetic_contracts
    from kronos.theta.target_authority import target_record
    owner=qualified_fixture(files)
    adapter=ThetaTargetAuthorityAdapter(owner)
    questions,_,_=synthetic_contracts()
    for subject in SUBJECTS:
        values=adapter.v3_inputs(subject,AT)
        q=questions[subject]
        q["binding"]["target_authority"]=values["target_authority"]
        questions[subject]=make_question_v3(binding=q["binding"],targets=values["targets"],
            created_at=AT.isoformat(),authority_valid_through=values["authority_valid_through"],
            methodology_instructions=q["methodology_instructions"],synthetic=True)
        assert values["target_authority"]["sha256"]==owner.current_sha256
        for t in owner.resolve(subject,AT):
            target=questions[subject]["targets"][t.horizon]
            assert target["price_unit"]==UNITS[subject]
            assert target["authority_reference"]=="MCXA-"+sha256(canonical_bytes(target_record(t))).hexdigest()
            assert "KITE" not in encode(target).decode().upper()
    batch=make_question_batch_v3(questions)
    combined=combined_answer_template(batch,questions)
    assert set(combined["answers"])==set(SUBJECTS)
    for subject in SUBJECTS:
        assert combined["answers"][subject]["binding"]["target_authority"]==owner.descriptor


def test_predecessor_publication_and_source_bytes_stay_readable(files,owner):
    old=OwnerOptionAuthority(current_filename="current-2026.1.0.json")
    predecessor=predecessor_owner(files)
    assert len(old.instrument.rows)==20
    assert old.instrument.pin.version=="2026.1.0"
    assert predecessor.instrument.supersedes==old.instrument.pin.reference
    assert predecessor.market.supersedes==old.market.pin.reference
    assert owner.instrument.supersedes==predecessor.instrument.pin.reference
    assert owner.market.supersedes==predecessor.market.pin.reference
    assert old.resolve("SILVERM",HISTORICAL_AT)[0].series==predecessor.resolve("SILVERM",HISTORICAL_AT)[0].series
