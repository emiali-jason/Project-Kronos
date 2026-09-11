"""No acquisition occurs during runtime source composition or source inspection."""
from types import SimpleNamespace
import pytest
from kronos.application.intraday_futures_source import GovernedFuturesSource
from tests.unit.intraday.test_wo10_futures import NOW


def test_source_constructor_and_missing_master_never_acquire():
    calls=[]
    source=GovernedFuturesSource(master_store=None,master_identity=lambda:None,binding_store=None,calendar=None,
        provider=lambda:calls.append('LEASE'),clock=lambda:NOW)
    assert not calls
    with pytest.raises(ValueError,match='WO10_COMPLETE_DAILY_MASTER_REQUIRED'):
        source(SimpleNamespace(canonical_subject_identity='NSE-EQ-LUPIN'),None)
    assert not calls


def test_lazy_source_uses_exact_authority_and_refreshes_for_currentness(monkeypatch):
    import kronos.application.intraday_futures_source as module
    calls=[];state={'master':'A','underlying':'U','active_mcx':None,'economics':None,'configuration':None}
    source=GovernedFuturesSource(master_store=None,master_identity=lambda:None,binding_store=None,calendar=None,
        provider=lambda:calls.append('LEASE') or 'LEASE',clock=lambda:NOW)
    monkeypatch.setattr(source,'authority',lambda h:dict(state))
    result=source(SimpleNamespace(canonical_subject_identity='NSE-EQ-LUPIN'),None)
    assert calls==['LEASE'] and result['configuration'] is None and result['economics'] is None
    state['master']='B'
    assert result['authority_source']()['master']=='B'


def test_shared_capability_failure_is_explicit_unavailable(monkeypatch):
    def fail():raise RuntimeError('ISOLATED disconnected')
    source=GovernedFuturesSource(master_store=None,master_identity=lambda:None,binding_store=None,calendar=None,
        provider=fail,clock=lambda:NOW)
    monkeypatch.setattr(source,'authority',lambda h:{})
    with pytest.raises(ValueError,match='WO10_CURRENT_MARKET_AUTHORITY_UNAVAILABLE'):source(None,None)
