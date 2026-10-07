"""Isolated exact-contract operation through the real hub and Kite adapter."""
from dataclasses import replace
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from threading import Event, Thread
from zoneinfo import ZoneInfo
import json
import pytest

from kronos.application.swing_mcx_observation import McxSelectedContractObservation
from kronos.application.shared_monitoring import SharedSwingMonitoringHub
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.instrument.runtime import create_provider_assertion
from kronos.provider.adapters.kite.monitoring import KiteReadOnlyMonitoringSession
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import MonitoringConnectionState, ProviderMarketTick
from kronos.swing.v1.mcx_contract_profile import McxFamily

NOW=datetime(2026,10,7,12,0,tzinfo=ZoneInfo('Asia/Kolkata'))


class Clock:
    now=NOW
    def __call__(self):return self.now


class Calendar:
    closed=False
    def schedule(self,exchange,day,*,observed_at):
        assert exchange=='MCX'
        return SimpleNamespace(trading_date=day,session_identity='MCX-SESSION',
            timezone='Asia/Kolkata',calendar_identity='GOVERNED-CALENDAR',calendar_version='1',
            windows=(SimpleNamespace(window_open=NOW.replace(hour=13 if self.closed else 9),
                                     window_close=NOW.replace(hour=23)),))


class Socket:
    MODE_FULL='full'
    def __init__(self,cap):self.cap=cap;self.tokens=[];self.closed=False
    def subscribe(self,tokens):self.tokens.extend(x for x in tokens if x not in self.tokens)
    def unsubscribe(self,tokens):self.tokens=[x for x in self.tokens if x not in tokens]
    def set_mode(self,mode,tokens):pass
    def connect(self,*,threaded):
        assert threaded
        if self.cap.mode=='provider_failure':raise RuntimeError('SECRET_MUST_NOT_LEAK')
        self.on_connect(self,{})
        self.cap.ready.set()
        if self.cap.mode=='held':return
        self.emit()
    def emit(self):
        self.cap.clock.now+=timedelta(milliseconds=1)
        stamp=self.cap.clock.now
        if self.cap.mode=='stale_quote':stamp=NOW-timedelta(seconds=1)
        token=999 if self.cap.mode=='raw_wrong_token'else self.tokens[0]
        self.on_ticks(self,[dict(instrument_token=token,last_price=100,
                                timestamp=stamp.replace(tzinfo=None))])
    def close(self):
        if self.cap.mode=='cleanup_failure':raise RuntimeError('PRIVATE_CLEANUP_DETAIL')
        self.closed=True


class Capability:
    active=True
    def __init__(self,instrument,clock,mode):
        self.instrument=instrument;self.clock=clock;self.mode=mode
        self.calls=[];self.sessions=[];self.sockets=[];self.ready=Event()
    def instrument_records(self,exchange):
        self.calls.append('records')
        if self.mode=='mapping_failure':raise RuntimeError('SECRET_PROVIDER_DETAIL')
        if self.mode=='wrong_expiry':return (replace(self.instrument,expiry=date(2026,11,19)),)
        if self.mode=='wrong_future':return (replace(self.instrument,trading_symbol='CRUDEOIL26NOVFUT'),)
        if self.mode=='duplicate_record':return (self.instrument,self.instrument)
        return (self.instrument,)
    def instrument_assertions(self,exchange,*,source_boundary,valid_through):
        self.calls.append('assertions')
        if self.mode=='stale_mapping':source_boundary-=timedelta(days=1)
        row=create_provider_assertion(provider='KITE',provider_symbol=self.instrument.trading_symbol,
            provider_instrument_token=303 if self.mode=='wrong_token'else 202,
            exchange='MCX',segment='MCX-FUT',instrument_type='FUT',
            asserted_tick_size=self.instrument.tick_size,asserted_lot_size=self.instrument.lot_size,
            binding_source_identity='CURRENT-PROVIDER-RETRIEVAL',
            source_boundary=source_boundary,valid_through=valid_through)
        return (row,row)if self.mode=='ambiguous_mapping'else ()if self.mode=='missing_mapping'else(row,)
    def open_monitoring_session(self,consumer):
        self.calls.append('session')
        socket=Socket(self);self.sockets.append(socket)
        session=KiteReadOnlyMonitoringSession(api_key='fixture',access_token='fixture',
            consumer=consumer,token_resolver=lambda i:202 if i==self.instrument else 101,
            clock=self.clock,socket_factory=lambda *args:socket)
        self.sessions.append(session)
        return session


def setup(tmp_path,mode='good',family=McxFamily.CRUDEOIL):
    clock=Clock();instrument=InstrumentRecord('KITE','MCX','MCX-FUT',
        family.value+'26OCTFUT',family.value,'FUT',date(2026,10,19),Decimal('1'),1)
    cap=Capability(instrument,clock,mode);hub=SharedSwingMonitoringHub();admission=MaintenanceAdmissionCoordinator()
    hub.bind_maintenance_admission(admission);calendar=Calendar();current=[True]
    def selected(run,fam,selection,pub):
        if (run,fam,selection,pub)!=('RUN',family,'a'*64,'b'*64)or not current[0]:
            raise ValueError('MCX_OBSERVATION_SELECTION_CHANGED')
        return dict(instrument=instrument,run=run,generation=18,selection_sha256=selection)
    owner=McxSelectedContractObservation(tmp_path/'observation',hub=hub,admission=admission,
        capability=lambda:cap,calendar=calendar,selected=selected,clock=clock,wait_seconds=.05)
    args=dict(operation='1'*32,run='RUN',family=family,selection_sha256='a'*64,publication_sha256='b'*64)
    return SimpleNamespace(owner=owner,args=args,cap=cap,hub=hub,admission=admission,
        calendar=calendar,clock=clock,instrument=instrument,current=current)


@pytest.mark.parametrize('family',list(McxFamily))
def test_exact_selected_future_observed_attributed_and_cleaned_for_each_family(tmp_path,family):
    f=setup(tmp_path,family=family);result=f.owner.observe(**f.args);r=result['record']
    assert r['state']=='OBSERVED'and r['cleanup']['complete']
    assert r['selection']['instrument']['trading_symbol']==f.instrument.trading_symbol
    assert r['selection']['instrument']['expiry']=='2026-10-19'
    assert r['mapping']['provider_instrument_token']==202
    q=r['observation'];assert q['tick']['last_price']=='100'
    assert q['tick']['instrument']['trading_symbol']==f.instrument.trading_symbol
    assert q['tick']['source']=='KITE_CONNECT_WEBSOCKET'
    assert q['tick']['received_at']==q['tick']['observed_at']
    assert q['subscription']['provider_instrument_token']==202
    assert q['subscription']['connection_id']==q['tick']['connection_id']
    assert q['session']['state']=='OPEN'and q['subscription_identity']
    assert q['distinct_exchange_timestamp']=='UNKNOWN'and q['trading_authority']=='NONE'
    assert f.cap.calls==['records','assertions','session']
    assert f.cap.sockets[0].closed and f.cap.sockets[0].tokens==[]
    assert f.hub.status_document()['owner_count']==0
    assert f.admission.snapshot()['owners']=={}
    assert sorted(p.name for p in tmp_path.iterdir())==['observation'] # no plan/position/advisory stores


@pytest.mark.parametrize('mode,reason',[
 ('wrong_expiry','CURRENT_CONTRACT_MISMATCH'),('wrong_future','CURRENT_CONTRACT_MISMATCH'),
 ('duplicate_record','CURRENT_CONTRACT_MISMATCH'),('missing_mapping','MAPPING_AMBIGUOUS_OR_CHANGED'),
 ('ambiguous_mapping','MAPPING_AMBIGUOUS_OR_CHANGED'),('stale_mapping','MAPPING_STALE'),
 ('wrong_token','QUOTE_INADMISSIBLE'),('stale_quote','QUOTE_INADMISSIBLE'),
 ('raw_wrong_token','PROVIDER_OR_VALIDATION_FAILED'),('provider_failure','PROVIDER_OR_VALIDATION_FAILED'),
 ('mapping_failure','PROVIDER_OR_VALIDATION_FAILED')])
def test_bad_current_mapping_quote_or_provider_fails_closed_and_preserves_cleanup(tmp_path,mode,reason):
    f=setup(tmp_path,mode);r=f.owner.observe(**f.args)['record']
    assert r['state']=='FAILED'and r['reason']=='MCX_OBSERVATION_'+reason
    assert r['observation']is None and r['cleanup']['complete']
    assert 'SECRET'not in json.dumps(r)
    assert f.hub.status_document()['owner_count']==0 and f.admission.snapshot()['owners']=={}


def test_session_gate_prevents_provider_and_persistence(tmp_path):
    f=setup(tmp_path);f.calendar.closed=True
    with pytest.raises(ValueError,match='SESSION_NOT_OPEN'):f.owner.observe(**f.args)
    assert not f.cap.calls and not f.owner.root.exists()


@pytest.mark.parametrize('key,value',[('run','OLD'),('selection_sha256','c'*64),('publication_sha256','c'*64)])
def test_stale_selected_input_rejects_before_provider_or_records(tmp_path,key,value):
    f=setup(tmp_path);f.args[key]=value
    with pytest.raises(ValueError,match='SELECTION_CHANGED'):f.owner.observe(**f.args)
    assert not f.cap.calls and not f.owner.root.exists()


def test_identical_replay_after_restart_is_immutable_no_acquisition_and_conflict_rejects(tmp_path):
    f=setup(tmp_path);first=f.owner.observe(**f.args)
    before={p:(p.stat().st_mtime_ns,p.stat().st_ctime_ns,p.read_bytes())for p in f.owner.root.rglob('*')if p.is_file()}
    successor=setup(tmp_path);assert successor.owner.observe(**successor.args)==first
    assert not successor.cap.calls
    successor.args['selection_sha256']='c'*64
    with pytest.raises(ValueError,match='REPLAY_CONFLICT'):successor.owner.observe(**successor.args)
    assert before=={p:(p.stat().st_mtime_ns,p.stat().st_ctime_ns,p.read_bytes())for p in f.owner.root.rglob('*')if p.is_file()}


def test_incomplete_operation_never_reacquires(tmp_path):
    f=setup(tmp_path);directory=f.owner.root/f.args['operation'];directory.mkdir(parents=True)
    (directory/'request.json').write_text(json.dumps({**f.args,'family':f.args['family'].value}))
    with pytest.raises(FileNotFoundError):f.owner.observe(**f.args)
    assert not f.cap.calls


def test_unavailable_receipt_get_is_write_free_and_symlinks_reject(tmp_path):
    f=setup(tmp_path)
    with pytest.raises(FileNotFoundError):f.owner.read('1'*32)
    assert not f.owner.root.exists()
    target=tmp_path/'target';target.mkdir();f.owner.root.symlink_to(target,target_is_directory=True)
    with pytest.raises(ValueError,match='PATH_INVALID'):f.owner.read('1'*32)
    assert not list(target.iterdir())


def test_cleanup_failure_holds_counted_owner_and_prevents_another_operation(tmp_path):
    f=setup(tmp_path,'cleanup_failure');r=f.owner.observe(**f.args)['record']
    assert r['state']=='FAILED'and r['reason']=='MCX_OBSERVATION_CLEANUP_INCOMPLETE'
    assert not r['cleanup']['complete']and f.admission.snapshot()['owners']=={'MONITORING_CALLBACK':1}
    with pytest.raises(ValueError,match='CLEANUP_UNRESOLVED'):
        f.owner.observe(**{**f.args,'operation':'2'*32})


def test_inflight_ownership_fence_conflict_and_changed_selection(tmp_path):
    f=setup(tmp_path,'held');f.owner.wait_seconds=1.0;result=[]
    worker=Thread(target=lambda:result.append(f.owner.observe(**f.args)));worker.start()
    assert f.cap.ready.wait(2)
    with pytest.raises(ValueError,match='BUSY'):f.owner.observe(**{**f.args,'operation':'2'*32})
    assert f.admission.snapshot()['owners']=={'MONITORING_CALLBACK':1}
    assert f.admission.claim('f'*64)
    f.current[0]=False
    f.cap.sockets[0].emit() # callback fencing means no admitted quote; cannot manufacture a pass
    worker.join(2);assert not worker.is_alive()
    assert result[0]['record']['state']=='FAILED'
    assert f.admission.snapshot()['owners']=={}
    with pytest.raises(ValueError,match='FENCED'):f.owner.observe(**{**f.args,'operation':'3'*32})


def test_wrong_connection_or_contract_tick_rejected_after_normalization(tmp_path,monkeypatch):
    f=setup(tmp_path)
    original=f.cap.open_monitoring_session
    def open_session(consumer):
        session=original(consumer);on_tick=consumer.on_market_tick
        consumer.on_market_tick=lambda t:on_tick(replace(t,connection_id='OTHER-CONNECTION'))
        return session
    monkeypatch.setattr(f.cap,'open_monitoring_session',open_session)
    assert f.owner.observe(**f.args)['record']['reason']=='MCX_OBSERVATION_QUOTE_INADMISSIBLE'


def test_selection_change_after_tick_withholds_receipt(tmp_path,monkeypatch):
    f=setup(tmp_path);original=f.cap.open_monitoring_session
    def open_session(consumer):
        session=original(consumer);on_tick=consumer.on_market_tick
        def changed(t):f.current[0]=False;on_tick(t)
        consumer.on_market_tick=changed
        return session
    monkeypatch.setattr(f.cap,'open_monitoring_session',open_session)
    r=f.owner.observe(**f.args)['record'];assert r['state']=='FAILED'and r['observation']is None
    assert r['reason']=='MCX_OBSERVATION_SELECTION_CHANGED'


@pytest.mark.parametrize('changed', ['instrument', 'subscription', 'state', 'token', 'final-context'])
def test_applied_context_must_remain_exact_and_connected(tmp_path, monkeypatch, changed):
    f = setup(tmp_path)
    original = f.cap.open_monitoring_session
    def open_session(consumer):
        session = original(consumer)
        read = session.observation_context
        calls = [0]
        def context(instrument):
            value = read(instrument); calls[0] += 1
            if changed == 'instrument':
                return replace(value, instrument=replace(instrument, expiry=date(2026, 11, 19)))
            if changed == 'subscription':
                return replace(value, subscribed_at=f.clock.now + timedelta(seconds=1))
            if changed == 'state':
                return replace(value, state=MonitoringConnectionState.CONTEXT_INCOMPLETE)
            if changed == 'token':
                return replace(value, provider_instrument_token=None)
            return replace(value, connection_id='CHANGED') if calls[0] > 1 else value
        session.observation_context = context
        return session
    monkeypatch.setattr(f.cap, 'open_monitoring_session', open_session)
    r = f.owner.observe(**f.args)['record']
    assert r['state'] == 'FAILED' and r['observation'] is None and r['cleanup']['complete']
    assert f.admission.snapshot()['owners'] == {}


def test_session_change_after_quote_rejects_with_cleanup(tmp_path, monkeypatch):
    f = setup(tmp_path); original = f.cap.open_monitoring_session
    def open_session(consumer):
        session = original(consumer); receive = consumer.on_market_tick
        def tick(value):
            f.calendar.closed = True
            receive(value)
        consumer.on_market_tick = tick
        return session
    monkeypatch.setattr(f.cap, 'open_monitoring_session', open_session)
    r = f.owner.observe(**f.args)['record']
    assert r['reason'] == 'MCX_OBSERVATION_SESSION_NOT_OPEN' and r['cleanup']['complete']
    assert r['observation'] is None


@pytest.mark.parametrize('failure', ['cleanup-proof', 'receipt'])
def test_unproved_cleanup_or_failed_final_bookkeeping_retains_ownership(tmp_path, monkeypatch, failure):
    import kronos.application.swing_mcx_observation as module
    f = setup(tmp_path)
    if failure == 'cleanup-proof':
        def unavailable(): raise OSError('isolated status failure')
        monkeypatch.setattr(f.hub, 'status_document', unavailable)
    else:
        write = module.immutable_write
        def unavailable(path, value):
            if path.name == 'receipt.json': raise OSError('isolated receipt failure')
            write(path, value)
        monkeypatch.setattr(module, 'immutable_write', unavailable)
    with pytest.raises(OSError): f.owner.observe(**f.args)
    assert f.cap.sockets[0].closed
    assert f.admission.snapshot()['owners'] == {'MONITORING_CALLBACK': 1}
    with pytest.raises(ValueError, match='CLEANUP_UNRESOLVED'):
        f.owner.observe(**{**f.args, 'operation': '2' * 32})


def test_temporary_mcx_observation_does_not_detach_existing_nse_owner(tmp_path, monkeypatch):
    import kronos.application.swing_mcx_observation as module
    f = setup(tmp_path, 'held')
    nse = InstrumentRecord('KITE', 'NSE', 'NSE', 'RELIANCE', 'RELIANCE', 'EQ', None)
    consumer = SimpleNamespace(owner_identity='EXISTING-NSE', ticks=[],
        on_connection_state=lambda state: None, on_order_update=lambda value: None)
    consumer.on_market_tick = consumer.ticks.append
    registration = f.hub.open(f.cap, consumer)
    registration.subscribe((nse,)); registration.connect()
    socket = f.cap.sockets[0]
    original_event = module.Event
    class QuoteEvent:
        def __init__(self): self.inner = original_event()
        def is_set(self): return self.inner.is_set()
        def set(self): return self.inner.set()
        def wait(self, seconds):
            f.clock.now += timedelta(milliseconds=1)
            socket.on_ticks(socket, [dict(instrument_token=202, last_price=100,
                timestamp=f.clock.now.replace(tzinfo=None))])
            return self.inner.wait(seconds)
    monkeypatch.setattr(module, 'Event', QuoteEvent)
    r = f.owner.observe(**f.args)['record']
    assert r['state'] == 'OBSERVED' and r['cleanup']['complete']
    assert f.hub.status_document()['owner_count'] == 1
    assert f.hub.status_document()['owners'][0]['owner_identity'] == 'EXISTING-NSE'
    assert not socket.closed and socket.tokens == [101]
    assert not consumer.ticks  # MCX quote was not misdelivered to NSE.
    assert f.cap.calls.count('session') == 1
    registration.disconnect()
    assert socket.closed and f.hub.status_document()['owner_count'] == 0


@pytest.mark.parametrize('mode,failed', [
    ('wrong_token', 'subscribed_token'),
    ('stale_quote', 'subscription_admits_tick'),
])
def test_rejected_quote_retains_actual_normalized_evidence_and_first_guard(tmp_path, mode, failed):
    f = setup(tmp_path, mode)
    result = f.owner.observe(**f.args); r = result['record']
    assert r['state'] == 'FAILED' and r['observation'] is None
    d = r['quote_validation']
    assert d['schema'] == 'KRONOS-MCX-QUOTE-VALIDATION-DIAGNOSTIC/1.0'
    assert d['first_rejection'] == failed
    assert d['checks'][failed] == 'FAIL'
    assert d['tick']['instrument']['trading_symbol'] == f.instrument.trading_symbol
    assert d['subscription']['provider_instrument_token'] == 202
    assert d['subscription_identity']
    assert d['checks']['capability_active'] == 'UNKNOWN' # short-circuit preserved
    assert r['cleanup']['complete'] and f.hub.status_document()['owner_count'] == 0
    assert f.admission.snapshot()['owners'] == {}
    retained = f.owner.read(f.args['operation'])
    assert retained == result
    calls = list(f.cap.calls)
    assert f.owner.observe(**f.args) == result and f.cap.calls == calls


@pytest.mark.parametrize('family', list(McxFamily))
def test_success_diagnostics_are_factual_not_trading_authority(tmp_path, family):
    f = setup(tmp_path, family=family); r = f.owner.observe(**f.args)['record']
    d = r['quote_validation']
    assert r['state'] == 'OBSERVED' and d['first_rejection'] is None
    assert set(d['checks'].values()) == {'PASS'}
    assert d['tick'] == r['observation']['tick']
    assert d['subscription'] == r['observation']['subscription']
    assert d['subscription_identity'] == r['observation']['subscription_identity']
    assert d['diagnostic_only'] is True and d['distinct_exchange_timestamp'] == 'UNKNOWN'
    assert 'SECRET' not in json.dumps(d) and 'access_token' not in json.dumps(d)


@pytest.mark.parametrize('changed,failed', [
    ('instrument', 'subscription_instrument'),
    ('subscription', 'subscription_admits_tick'),
    ('state', 'subscription_connected'),
    ('token', 'subscribed_token'),
    ('missing', 'subscription_type'),
])
def test_rejection_diagnostics_preserve_strict_context_guard(tmp_path, monkeypatch, changed, failed):
    f = setup(tmp_path); original = f.cap.open_monitoring_session
    def open_session(consumer):
        session = original(consumer); read = session.observation_context
        def context(_session, instrument):
            value = read(instrument)
            if changed == 'missing': return None
            if changed == 'instrument': return replace(value, instrument=replace(instrument, expiry=date(2026,11,19)))
            if changed == 'subscription': return replace(value, subscribed_at=f.clock.now + timedelta(seconds=1))
            if changed == 'state': return replace(value, state=MonitoringConnectionState.CONTEXT_INCOMPLETE)
            return replace(value, provider_instrument_token=None)
        monkeypatch.setattr(type(session), 'observation_context', context)
        return session
    monkeypatch.setattr(f.cap, 'open_monitoring_session', open_session)
    r = f.owner.observe(**f.args)['record']
    assert 'quote_validation' in r, (r.get('reason'), r.get('error_type'))
    d = r['quote_validation']
    assert r['state'] == 'FAILED' and r['observation'] is None
    assert d['first_rejection'] == failed and d['checks'][failed] == 'FAIL'
    assert (d['subscription'] is None) == (changed == 'missing')
    assert r['cleanup']['complete'] and f.admission.snapshot()['owners'] == {}


@pytest.mark.parametrize('changed,failed', [('connection','subscription_admits_tick'),
    ('recovered','subscription_admits_tick'),('price','positive_price')])
def test_rejected_tick_is_retained_without_becoming_an_observation(tmp_path, monkeypatch, changed, failed):
    f = setup(tmp_path); original = f.cap.open_monitoring_session
    def open_session(consumer):
        session = original(consumer); read = consumer.on_market_tick
        def tick(t):
            updates = {'connection_id':'WRONG'} if changed == 'connection' else {'recovered':True} if changed == 'recovered' else {'last_price':Decimal('0')}
            read(replace(t, **updates))
        consumer.on_market_tick = tick
        return session
    monkeypatch.setattr(f.cap, 'open_monitoring_session', open_session)
    r = f.owner.observe(**f.args)['record']
    assert r['reason'] == 'MCX_OBSERVATION_QUOTE_INADMISSIBLE'
    assert r['quote_validation']['first_rejection'] == failed
    assert r['observation'] is None and r['cleanup']['complete']


def test_legacy_failed_receipt_replay_does_not_add_diagnostics(tmp_path):
    from kronos.application.swing_mcx_observation import _digest
    f = setup(tmp_path, 'wrong_token'); first = f.owner.observe(**f.args)
    first['record'].pop('quote_validation', None)
    first['sha256'] = _digest(first['record'])
    path = f.owner.root / f.args['operation'] / 'receipt.json'
    path.write_text(json.dumps(first)) # isolated historical-schema fixture only
    before = path.read_bytes(); calls = list(f.cap.calls)
    assert f.owner.observe(**f.args) == first
    assert path.read_bytes() == before and f.cap.calls == calls
