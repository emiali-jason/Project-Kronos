"""Private read-only native traversal scope; actual parsing/pipe binding retained.

The existing receiver fixture explicitly substitutes kernel image/signature
facts only. The complete native roundtrip independently exercises real C.
"""
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor
import time

import pytest
from tests.unit.tools.test_failed_fenced_launcher import received_semantic_exchange
from kronos.common.failed_fenced_startup import NativeSemanticExchange, RecoveryStartupError
from kronos.common.failed_fenced_recovery import RecoveryError


def observe_images(monkeypatch):
    original=NativeSemanticExchange._native_image_identity;calls=[]
    def observed(pid,budget):
        calls.append(pid);return original(pid,budget)
    monkeypatch.setattr(NativeSemanticExchange,'_native_image_identity',staticmethod(observed))
    return calls


def test_readonly_nested_traversal_checks_complete_source_at_both_boundaries(received_semantic_exchange,monkeypatch):
    with received_semantic_exchange() as (exchange,raw):
        calls=observe_images(monkeypatch)
        with exchange._readonly_validation():
            for _ in range(8):
                exchange.require_current();exchange.authenticate(raw,external=False)
                with exchange._readonly_validation():exchange.require_current()
            assert len(calls)==1
        assert len(calls)==2
        exchange.require_current()
        assert len(calls)==3


@pytest.mark.parametrize('fault',['image','loaded-code','body','plan','modules','authentication','budget'])
def test_mutation_during_readonly_traversal_cannot_return_success(received_semantic_exchange,monkeypatch,fault):
    with received_semantic_exchange() as (exchange,raw):
        accepted=[]
        with pytest.raises((RecoveryStartupError,RecoveryError)):
            with exchange._readonly_validation():
                exchange.authenticate(raw,external=False)
                if fault=='image':
                    monkeypatch.setattr(NativeSemanticExchange,'_native_image_identity',staticmethod(lambda *args:('changed','0'*64)))
                elif fault=='loaded-code':
                    from tools import failed_fenced_launcher
                    monkeypatch.setattr(failed_fenced_launcher,'native_pinned_module',lambda *args:b'unapproved')
                elif fault=='body':exchange._body['operation']='changed'
                elif fault=='plan':exchange._plan['modules'][0]['digest']='0'*64
                elif fault=='modules':exchange._modules['unapproved.module']='f'*64
                elif fault=='authentication':next(iter(exchange._authenticated.values()))['bytes']='0'
                else:
                    stop=exchange.budget.stop_deadline_ns
                    monkeypatch.setattr(time,'clock_gettime_ns',lambda clock:stop)
            accepted.append(True)
        assert not accepted and not exchange._within_readonly_validation()


@pytest.mark.parametrize('kind',['FACT','PUBLISH','RESERVE','PROBE','EXCHANGE','FORK','SEND_GRANT','WAIT_READY','DONE'])
def test_readonly_traversal_cannot_issue_effect_or_release_authority(received_semantic_exchange,kind):
    with received_semantic_exchange() as (exchange,_):
        with exchange._readonly_validation():
            with pytest.raises(RecoveryStartupError,match='EFFECT_DURING_VALIDATION'):
                exchange.native_call(kind,{})


def test_copied_scope_never_suppresses_other_thread_or_later_checks(received_semantic_exchange,monkeypatch):
    with received_semantic_exchange() as (exchange,_):
        calls=observe_images(monkeypatch)
        with exchange._readonly_validation():
            copied=copy_context()
            with ThreadPoolExecutor(max_workers=1) as workers:
                assert workers.submit(copied.run,exchange._within_readonly_validation).result(timeout=5) is False
                workers.submit(copied.run,exchange.require_current).result(timeout=5)
            assert len(calls)==2
        assert copied.run(exchange._within_readonly_validation) is False
        copied.run(exchange.require_current)
        assert len(calls)==4


def test_exception_resets_scope_and_preserves_original_denial(received_semantic_exchange,monkeypatch):
    with received_semantic_exchange() as (exchange,_):
        with pytest.raises(ValueError,match='original-denial'):
            with exchange._readonly_validation():raise ValueError('original-denial')
        assert not exchange._within_readonly_validation()
        calls=observe_images(monkeypatch);exchange.require_current()
        assert len(calls)==1


def test_live_process_and_pipe_checks_still_run_inside_each_leaf(received_semantic_exchange,monkeypatch):
    with received_semantic_exchange() as (exchange,_):
        with pytest.raises(RecoveryStartupError,match='PROCESS_CHANGED'):
            with exchange._readonly_validation():
                monkeypatch.setattr(NativeSemanticExchange,'_native_process',staticmethod(lambda pid:{'seconds':'0','microseconds':'0'}))
                with pytest.raises(RecoveryStartupError,match='PROCESS_CHANGED'):exchange.require_current()
                # The unchanged full exit check must reject the same mutation.

def test_native_process_reuses_only_fixed_ffi_binding_and_reads_each_observation(monkeypatch):
    import ctypes
    from types import SimpleNamespace
    from kronos.common import failed_fenced_startup as module
    loads=[]; calls=[]
    class Function:
        def __call__(self,pid,flavor,arg,pointer,size):
            calls.append((pid,flavor,arg,size))
            pointer._obj.pid=pid
            pointer._obj.start_seconds=100+len(calls)
            pointer._obj.start_microseconds=len(calls)
            return size
    function=Function()
    def load(path,**kwargs):
        loads.append((path,kwargs));return SimpleNamespace(proc_pidinfo=function)
    monkeypatch.setattr(module,'_native_process_function',None)
    monkeypatch.setattr(ctypes,'CDLL',load)
    first=module.NativeSemanticExchange._native_process(123)
    second=module.NativeSemanticExchange._native_process(123)
    assert first=={'seconds':'101','microseconds':'1'}
    assert second=={'seconds':'102','microseconds':'2'}
    assert len(calls)==2 and all(row==(123,3,0,136) for row in calls)
    assert loads==[('/usr/lib/libproc.dylib',{'use_errno':True})]
    assert function.argtypes==[ctypes.c_int,ctypes.c_int,ctypes.c_uint64,ctypes.c_void_p,ctypes.c_int]
    assert function.restype is ctypes.c_int


@pytest.mark.parametrize('fault',['short','wrong-pid','gone','exception'])
def test_native_process_binding_reuse_never_reuses_prior_success(monkeypatch,fault):
    from kronos.common import failed_fenced_startup as module
    calls=[]
    def function(pid,flavor,arg,pointer,size):
        calls.append(pid);pointer._obj.pid=pid;pointer._obj.start_seconds=100
        if len(calls)==1:return size
        if fault=='exception':raise OSError('kernel observation unavailable')
        if fault=='wrong-pid':pointer._obj.pid=pid+1
        return 0 if fault=='gone' else size-1 if fault=='short' else size
    monkeypatch.setattr(module,'_native_process_function',function)
    assert module.NativeSemanticExchange._native_process(123)['seconds']=='100'
    with pytest.raises((RecoveryStartupError,OSError)):
        module.NativeSemanticExchange._native_process(123)
    assert calls==[123,123]
