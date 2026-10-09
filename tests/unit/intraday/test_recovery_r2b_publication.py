"""Retained R2B protections migrated to fixed owners and all-writer WO09 CAS.

The historical escaping-writer counterexample remains in the immutable R2B
package. Here the same writer must participate in the sealed protocol.
"""
from datetime import timedelta
from threading import Event, Thread
import pytest
from kronos.application.intraday_evidence_currentness import IntradayPublicationBoundary
from kronos.intraday.evidence_currentness import NewWorkNotEligible, EligibilityReason
from kronos.intraday.wo09_persistence import Wo09PublicationConflict
from kronos.intraday.wo09_readiness import CurrentnessState
from tests.unit.intraday.test_wo11_lifecycle_application import early_source_fixture, BOUNDARY
from tests.unit.intraday.recovery_r2b_fixtures import governed_graph, historical_handoff


def fixture(tmp_path):
    _,facts,mapping,run=early_source_fixture()
    graph=governed_graph(tmp_path,mapping,run,facts,clock=lambda:BOUNDARY)
    r=graph.readiness
    graph.wo09.retain(r,graph.requirements,expected=graph.wo09.expectation(r.canonical_subject_identity))
    h=historical_handoff(graph.wo09,r,created_at=BOUNDARY,first_five_of_five_at=BOUNDARY)
    return graph,h


@pytest.mark.parametrize('change',['generation','eligibility'])
def test_final_changed_authority_has_no_pointer_or_notification(tmp_path,monkeypatch,change):
    g,h=fixture(tmp_path);b=g.boundary;expected=b.capture_futures(handoff_identity=h.handoff_identity)
    if change=='generation':
        g.review.upload_chart(g.readiness.review_cycle_identity,media_type='image/png',payload=__import__(
            'tests.unit.intraday.test_review',fromlist=['_png'])._png(92))
    else:
        monkeypatch.setattr(g.probables,'load_current',lambda:None)
    effects=[]
    intermediate=tmp_path/'immutable-preparation';intermediate.write_text('lawful intermediate')
    with pytest.raises(NewWorkNotEligible):
        with b.final_futures(expected):effects.extend(['accepted','pointer','notification'])
    assert effects==[] and intermediate.read_text()=='lawful intermediate'
    assert g.futures.current(h.canonical_subject_identity) is None


def test_owner_lock_is_held_until_final_pointer_but_notice_follows_release(tmp_path,monkeypatch):
    g,h=fixture(tmp_path);b=g.boundary;expected=b.capture_futures(handoff_identity=h.handoff_identity)
    attempted=Event();done=Event();events=[];errors=[]
    from kronos.intraday import wo09_persistence as owner
    from threading import Lock
    key=(expected.wo09.root_key,expected.wo09.canonical_subject_identity)
    class TraceLock:
        def __init__(self):self.lock=Lock()
        def __enter__(self):attempted.set();self.lock.acquire();return self
        def __exit__(self,*args):self.lock.release()
    controller=TraceLock();monkeypatch.setitem(owner._MUTATION_CONTROLLERS,key,controller)
    def writer():
        try:
            g.wo09.mark_currentness(h.canonical_subject_identity,CurrentnessState.SUPERSEDED,
                updated_at=BOUNDARY+timedelta(seconds=1),expected=expected.wo09)
            events.append('supersession')
        except Exception as exc:errors.append(exc)
        finally:done.set()
    with b.final_futures(expected):
        attempted.clear();t=Thread(target=writer);t.start();assert attempted.wait(3)
        assert controller.lock.locked() and not done.is_set()
        events.append('final-effect')
    t.join(3)
    assert not t.is_alive() and errors==[] and events==['final-effect','supersession']
    assert done.is_set()


def test_captured_expectation_is_not_reusable_authorization(tmp_path):
    g,h=fixture(tmp_path);expected=g.boundary.capture_futures(handoff_identity=h.handoff_identity)
    g.wo09.mark_currentness(h.canonical_subject_identity,CurrentnessState.REASSESSMENT_DUE,
        updated_at=BOUNDARY+timedelta(seconds=1),expected=expected.wo09)
    with pytest.raises(Wo09PublicationConflict):
        with g.boundary.final_futures(expected):pytest.fail('must compare exact predecessor')


def test_storage_error_is_preserved(tmp_path,monkeypatch):
    g,h=fixture(tmp_path);expected=g.boundary.capture_futures(handoff_identity=h.handoff_identity)
    def broken(*args):raise OSError('INTEGRITY_READ_FAILED')
    monkeypatch.setattr(g.probables,'load_current',broken)
    with pytest.raises(OSError,match='INTEGRITY_READ_FAILED'):
        with g.boundary.final_futures(expected):pytest.fail('must not publish')


def test_reentrant_assessor_cannot_be_installed_in_fixed_constructor():
    with pytest.raises(TypeError):
        IntradayPublicationBoundary(scope=lambda:None,read=lambda *args:(),assess=lambda *args:True)


def test_existing_wo09_writer_can_no_longer_escape_publication(tmp_path):
    g,h=fixture(tmp_path);expected=g.boundary.capture_futures(handoff_identity=h.handoff_identity)
    g.wo09.mark_currentness(h.canonical_subject_identity,CurrentnessState.SUPERSEDED,
        updated_at=BOUNDARY+timedelta(seconds=1),expected=expected.wo09)
    before=g.wo09.load_pointer(h.canonical_subject_identity)
    with pytest.raises(Wo09PublicationConflict):
        with g.boundary.final_futures(expected):pytest.fail('escaped writer accepted')
    assert g.wo09.load_pointer(h.canonical_subject_identity)==before


def test_missing_generation_is_unavailable_not_invented_supersession(tmp_path,monkeypatch):
    g,h=fixture(tmp_path);expected=g.boundary.capture_futures(handoff_identity=h.handoff_identity)
    monkeypatch.setattr(g.probables,'load_current',lambda:None)
    with pytest.raises(NewWorkNotEligible) as caught:
        with g.boundary.final_futures(expected):pytest.fail('missing authority must deny')
    assert caught.value.reason is EligibilityReason.SOURCE_LINEAGE_NOT_ESTABLISHED
    with pytest.raises(NewWorkNotEligible) as caught:
        g.boundary.capture_futures(handoff_identity=h.handoff_identity)
    assert caught.value.reason is EligibilityReason.SOURCE_LINEAGE_NOT_ESTABLISHED


def test_actual_wo09_handoff_check_then_retain_gap_is_closed(tmp_path):
    g,h=fixture(tmp_path);old=g.wo09.expectation(h.canonical_subject_identity)
    g.wo09.mark_currentness(h.canonical_subject_identity,CurrentnessState.SUPERSEDED,
        updated_at=BOUNDARY+timedelta(seconds=1),expected=old)
    before={p:p.read_bytes() for p in g.wo09.root.rglob('*') if p.is_file()}
    with pytest.raises(Wo09PublicationConflict):g.wo09.retain_handoff(h,expected=old)
    assert {p:p.read_bytes() for p in g.wo09.root.rglob('*') if p.is_file()}==before
    assert g.wo09.load_handoff(h.handoff_identity)==h  # retained history readable


def test_domain008_market_independence_history_and_missing_authority(tmp_path,monkeypatch):
    from kronos.market.calendar import MarketCalendarPublisher
    from tests.unit.intraday.test_wo10_futures import _mcx_component_inputs,NOW
    from tests.unit.intraday.test_native_pullback_policy import START
    from kronos.intraday.wo09_readiness import ReadinessState
    nse,h=fixture(tmp_path/'nse')
    _,binding,_,market=_mcx_component_inputs('CRUDE')
    _,facts,mapping,run=early_source_fixture(subject=binding.canonical_subject_id,session=market.schedule.session_id,native_source=False)
    mcx=governed_graph(tmp_path/'mcx',mapping,run,facts,clock=lambda:NOW,binding=binding)
    assert nse.readiness.satisfied_count==5
    assert mcx.readiness.readiness_state is ReadinessState.READINESS_UNAVAILABLE
    # Use the commissioned DOMAIN008 publisher, independently for each venue.
    nse.boundary.calendar=MarketCalendarPublisher();mcx.boundary.calendar=MarketCalendarPublisher()
    # The disposable NSE graph uses a fixture session label. Bind that exact
    # label only on its original day; preserve real DOMAIN008 window/date rules.
    from dataclasses import replace
    from types import SimpleNamespace
    actual_profile=nse.boundary.calendar.instrument_session_profile
    def fixture_label(exchange,day,**kwargs):
        profile=actual_profile(exchange,day,**kwargs)
        if profile is not None and day==NOW.date():
            return SimpleNamespace(continuous_trading=replace(profile.continuous_trading,
                session_identity=nse.readiness.session_identity),closing_auction_session=profile.closing_auction_session)
        return profile
    monkeypatch.setattr(nse.boundary.calendar,'instrument_session_profile',fixture_label)
    nse.boundary._session(nse.readiness,'futures');mcx.boundary._session(mcx.readiness,'futures')
    after_nse_close=START.replace(hour=16,minute=0)
    nse.boundary.clock=mcx.boundary.clock=lambda:after_nse_close
    with pytest.raises(ValueError):nse.boundary._session(nse.readiness,'futures')
    assert mcx.boundary._session(mcx.readiness,'futures')==after_nse_close
    # October historical pointers remain readable, but cannot authorize new work.
    historical=NOW.replace(month=10,day=1)
    nse.boundary.clock=lambda:historical
    with pytest.raises(NewWorkNotEligible) as caught:
        nse.boundary.capture_futures(handoff_identity=h.handoff_identity)
    assert caught.value.reason is EligibilityReason.HISTORICAL_SESSION
    assert nse.wo09.load_handoff(h.handoff_identity)==h
    before={p:p.read_bytes() for p in nse.wo09.root.rglob('*') if p.is_file()}
    nse.boundary.clock=lambda:NOW
    monkeypatch.setattr(nse.boundary.calendar,'instrument_session_profile',lambda *args,**kwargs:None)
    with pytest.raises(ValueError):nse.boundary.capture_futures(handoff_identity=h.handoff_identity)
    assert {p:p.read_bytes() for p in nse.wo09.root.rglob('*') if p.is_file()}==before
    assert mcx.boundary._session(mcx.readiness,'futures')==after_nse_close
