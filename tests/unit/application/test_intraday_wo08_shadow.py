from threading import Event, Thread
import pytest
from kronos.application import intraday_wo08_shadow as module
from kronos.application.intraday_wo08_shadow import Wo08ShadowCollector
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.intraday.wo08_shadow_persistence import Wo08ShadowStore
from tests.unit.intraday.test_wo08_shadow_contract import handoff


def collector(tmp_path):
    c=Wo08ShadowCollector(Wo08ShadowStore(tmp_path));a=MaintenanceAdmissionCoordinator();c.bind_maintenance_admission(a)
    return c,a


def test_fenced_parent_cannot_admit_research_or_create_store(tmp_path):
    c,a=collector(tmp_path);parent=a.admit('BROWSER_POST');assert a.claim('a'*64)
    with parent.activate():
        result=c.submit(handoff());assert result.reason=='MAINTENANCE_FENCED'
    parent.release();assert a.snapshot()['owners']=={} and not c.store.root.exists();assert c.close()


def test_ticket_owned_through_final_sync_and_drain_without_readmission(tmp_path,monkeypatch):
    c,a=collector(tmp_path);h=handoff();entered=Event();release=Event();finished=Event();original=c.store._sync
    def sync(path):
        if path.name=='run':
            assert a.snapshot()['owners']=={'WO08_SHADOW':1}
            entered.set();assert release.wait(10)
        original(path)
    monkeypatch.setattr(c.store,'_sync',sync)
    assert c.submit(h).state=='QUEUED';assert entered.wait(10)
    assert a.claim('b'*64);a.draining('b'*64)
    result=[]
    t=Thread(target=lambda:(result.append(a.wait_for_zero('b'*64,10)),finished.set()));t.start()
    assert not finished.is_set();assert c.submit(h).reason=='MAINTENANCE_FENCED'
    release.set();t.join(10);assert result==[True];assert c.close()
    assert a.snapshot()['owners']=={} and c.store.load('RUN',h.manifest.identity)==h.manifest


@pytest.mark.parametrize('bound',['MAX_ITEMS','MAX_BYTES','MAX_HANDOFF_BYTES'])
def test_nonblocking_queue_limits_and_exact_release(tmp_path,monkeypatch,bound):
    c,a=collector(tmp_path);monkeypatch.setattr(module,bound,0)
    r=c.submit(handoff());assert r.state=='SHADOW_CAPTURE_NOT_ADMITTED'
    assert r.reason in {'QUEUE_SATURATED','HANDOFF_OVERSIZE'}
    assert a.snapshot()['owners']=={} and not c.store.root.exists();assert c.close()


def test_scheduling_failure_releases_once_and_no_false_durability(tmp_path,monkeypatch):
    c,a=collector(tmp_path)
    monkeypatch.setattr(module.Thread,'start',lambda _s: (_ for _ in ()).throw(RuntimeError('schedule')))
    assert c.submit(handoff()).reason=='SCHEDULING_FAILED'
    assert a.snapshot()['owners']=={};assert c.close();assert not c.store.root.exists()


def test_worker_failure_isolated_and_shutdown_refuses_new_work(tmp_path,monkeypatch):
    c,a=collector(tmp_path)
    monkeypatch.setattr(c.store,'retain_handoff',lambda _h: (_ for _ in ()).throw(OSError('disk')))
    h=handoff();c.submit(h);assert c.close()
    assert c.snapshot()['results'][h.manifest.identity].reason=='WORKER_OR_DURABILITY_FAILED'
    assert a.snapshot()['owners']=={} and c.submit(h).reason=='COLLECTOR_CLOSED'


def test_blocked_worker_prevents_zero_handoff_and_never_retries(tmp_path,monkeypatch):
    c,a=collector(tmp_path);entered=Event();release=Event();calls=[]
    def persist(h):
        calls.append(h);entered.set();assert release.wait(10)
    monkeypatch.setattr(c.store,'retain_handoff',persist)
    c.submit(handoff());assert entered.wait(10);assert a.claim('c'*64);a.draining('c'*64)
    assert a.wait_for_zero('c'*64,0) is False
    assert a.snapshot()['state']=='FAILED_FENCED';assert c.close(timeout=0) is False
    release.set();assert c.close();assert len(calls)==1


def test_duplicate_and_restart_never_backfill_existing_operational_run(tmp_path):
    c,a=collector(tmp_path);assert c.submit(handoff(False)).reason=='ALREADY_PUBLISHED_NO_BACKFILL'
    assert not c.store.root.exists();assert c.close()
    restored=Wo08ShadowCollector(c.store);assert restored.snapshot()['queued']==0
    assert restored.maintenance_coordinator is None and restored._worker is None
    assert restored.submit(handoff()).reason=='ADMISSION_UNAVAILABLE';assert restored.close()


def test_default_absent_has_no_background_or_store(tmp_path):
    from kronos.application.intraday_runtime import create_intraday_runtime
    from tests.unit.application.test_intraday_discovery_operation import _configured_shared,OBSERVED
    shared,_,factories,requests=_configured_shared()
    r=create_intraday_runtime(shared,evidence_root=tmp_path,clock=lambda:OBSERVED)
    assert r.wo08_shadow is r.discovery_v2_operation.wo08_shadow is None
    assert not (tmp_path/'wo08-research-only-v1').exists() and requests==[0] and factories==[]


def test_explicit_collector_injection_remains_supported(tmp_path):
    from kronos.application.intraday_runtime import create_intraday_runtime
    from tests.unit.application.test_intraday_discovery_operation import _configured_shared, OBSERVED
    shared, _, factories, requests = _configured_shared()
    owner = Wo08ShadowCollector(Wo08ShadowStore(tmp_path))
    runtime = create_intraday_runtime(shared, evidence_root=tmp_path, clock=lambda: OBSERVED,
                                      wo08_shadow=owner)
    assert runtime.wo08_shadow is runtime.discovery_v2_operation.wo08_shadow is owner
    assert owner.maintenance_coordinator is None and owner._worker is None
    assert not owner.store.root.exists() and requests == [0] and factories == []
    assert owner.close()


def test_ambiguous_factory_and_collector_does_not_construct_second_owner(tmp_path):
    from kronos.application.intraday_runtime import create_intraday_runtime
    from tests.unit.application.test_intraday_discovery_operation import _configured_shared, OBSERVED
    shared, _, factories, requests = _configured_shared()
    owner = Wo08ShadowCollector(Wo08ShadowStore(tmp_path))
    with pytest.raises(ValueError, match='^WO08_COMPOSITION_AMBIGUOUS$'):
        create_intraday_runtime(shared, evidence_root=tmp_path, clock=lambda: OBSERVED,
            wo08_shadow=owner,
            wo08_shadow_factory=lambda: pytest.fail('ambiguous composition called factory'))
    assert requests == [0] and factories == []
    assert not owner.store.root.exists() and owner._worker is None
    assert owner.close()


@pytest.mark.parametrize('excluded',[97,98])
def test_member_counts_reconcile_retained_samples_and_truthful_exclusions(tmp_path,excluded):
    c,a=collector(tmp_path);h=handoff(excluded=excluded);c.submit(h);assert c.close()
    counts=c.snapshot()['counts'];selected=98-excluded
    assert counts==dict(eligible=selected,attempted=selected,admitted=selected,not_admitted=0,
        captured=0,partial=selected,failed=0,excluded=excluded)
    assert counts['captured']+counts['partial']+counts['excluded']==98
    assert c.snapshot()['results'][h.manifest.identity].state=='SHADOW_CAPTURE_PARTIAL'
    restored=c.store.load('RUN',h.manifest.identity)
    assert len(restored.data['selected_sample_ids'])==selected
    assert len(restored.data['excluded_result_reasons'])==excluded
    assert a.snapshot()['owners']=={}


@pytest.mark.parametrize('bound',['items','bytes'])
def test_actual_queue_bounds_keep_every_queued_item_counted(tmp_path,monkeypatch,bound):
    from kronos.intraday.wo08_shadow_contract import Wo08ShadowHandoff
    c,a=collector(tmp_path);entered=Event();release=Event();h=handoff()
    calls=[]
    def persist(value):
        calls.append(value)
        if len(calls)==1:entered.set();assert release.wait(30)
    monkeypatch.setattr(c.store,'retain_handoff',persist)
    # Byte-budget seam is exercised at the commissioned constants. Handoff
    # canonical payload/lineage is separately qualified, never changed here.
    if bound=='bytes':monkeypatch.setattr(Wo08ShadowHandoff,'encoded',lambda self: bytes(module.MAX_HANDOFF_BYTES))
    assert c.submit(h).state=='QUEUED';assert entered.wait(10)
    limit=module.MAX_ITEMS if bound=='items' else module.MAX_BYTES//module.MAX_HANDOFF_BYTES
    for _ in range(limit):assert c.submit(h).state=='QUEUED'
    assert c.snapshot()['queued']==limit
    assert a.snapshot()['owners']=={'WO08_SHADOW':limit+1}
    assert c.submit(h).reason=='QUEUE_SATURATED'
    assert a.snapshot()['owners']=={'WO08_SHADOW':limit+1}
    assert a.claim('d'*64);a.draining('d'*64);assert a.wait_for_zero('d'*64,0) is False
    release.set();assert c.close(timeout=30);assert len(calls)==limit+1
    assert a.snapshot()['owners']=={}


def test_actual_handoff_byte_boundary_is_inclusive(tmp_path,monkeypatch):
    from kronos.intraday.wo08_shadow_contract import Wo08ShadowHandoff
    c,a=collector(tmp_path);h=handoff()
    monkeypatch.setattr(Wo08ShadowHandoff,'encoded',lambda self:bytes(module.MAX_HANDOFF_BYTES+1))
    assert c.submit(h).reason=='HANDOFF_OVERSIZE';assert a.snapshot()['owners']=={}
    monkeypatch.setattr(Wo08ShadowHandoff,'encoded',lambda self:bytes(module.MAX_HANDOFF_BYTES))
    assert c.submit(h).state=='QUEUED';assert c.close();assert a.snapshot()['owners']=={}


@pytest.mark.parametrize('failure', ['store', 'collector'])
def test_canonical_construction_failure_is_observable_and_never_admits(tmp_path, monkeypatch, failure):
    from kronos.intraday import wo08_shadow_persistence as persistence
    from kronos.application.intraday_wo08_shadow import compose_wo08_shadow, UnavailableWo08ShadowCollector
    calls = []

    def fail(*args):
        calls.append(args)
        raise OSError('construction unavailable')

    monkeypatch.setattr(persistence if failure == 'store' else module,
                        'Wo08ShadowStore' if failure == 'store' else 'Wo08ShadowCollector', fail)
    owner = compose_wo08_shadow(tmp_path)
    assert type(owner) is UnavailableWo08ShadowCollector
    assert len(calls) == 1  # no constructor retry
    admission = MaintenanceAdmissionCoordinator()
    owner.bind_maintenance_admission(admission)
    assert owner.maintenance_coordinator is admission
    initial = owner.snapshot()
    assert initial['availability'] == 'UNAVAILABLE'
    assert initial['unavailable_reason'] == 'WO08_CONSTRUCTION_UNAVAILABLE'
    assert initial['unavailable_error_type'] == 'OSError'
    assert owner.store is None and owner._worker is None
    monkeypatch.setattr(admission, 'admit_root', lambda *_: pytest.fail('unavailable research admitted'))
    result = owner.submit(handoff())
    assert result.state == 'SHADOW_CAPTURE_NOT_ADMITTED'
    assert result.reason == 'WO08_CONSTRUCTION_UNAVAILABLE'
    assert owner.snapshot()['counts'] == dict(
        eligible=1, attempted=1, admitted=0, not_admitted=1,
        captured=0, failed=0, partial=0, excluded=97,
    )
    assert owner.snapshot()['counts']['not_admitted'] + owner.snapshot()['counts']['excluded'] == 98
    assert admission.snapshot()['owners'] == {}
    assert not (tmp_path / 'wo08-research-only-v1').exists()
    assert owner.close() and owner.snapshot()['closed']
