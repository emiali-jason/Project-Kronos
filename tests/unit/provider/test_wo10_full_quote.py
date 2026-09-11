"""Isolated full-quote normalization and physical batch boundary tests."""
from datetime import timedelta
from decimal import Decimal
import pytest

from kronos.provider.adapters.kite.client import _KiteCandidateClientHandle, _KiteSessionState
from kronos.provider.adapters.kite.full_quote import normalize_full_quotes
from tests.unit.intraday.test_wo10_futures import master, raw_quotes


def instruments():
    m,_=master()
    return m.records[:2]


class Client:
    timeout=19
    def __init__(self):
        self.calls=[]
    def quote(self, rows):
        self.calls.append((rows,self.timeout))
        return {"retained":"fake response"}


def test_one_batch_two_legs_and_restored_timeout():
    client=Client(); handle=_KiteCandidateClientHandle(client,_KiteSessionState())
    assert handle.full_quotes(("NSE:LUPIN","NFO:LUPINFUT"),timeout=7)=={"retained":"fake response"}
    assert client.calls==[(["NSE:LUPIN","NFO:LUPINFUT"],7)]
    assert client.timeout==19
    with pytest.raises(ValueError,match="RATE_LIMIT"):
        handle.full_quotes(("NSE:LUPIN",),timeout=7)
    assert len(client.calls)==1


def test_provider_failure_does_not_retry():
    class Failing(Client):
        def quote(self,rows):
            self.calls.append(rows)
            raise RuntimeError("fixture failure")
    client=Failing();handle=_KiteCandidateClientHandle(client,_KiteSessionState())
    with pytest.raises(RuntimeError): handle.full_quotes(("NSE:LUPIN",))
    assert len(client.calls)==1 and client.timeout==19


@pytest.mark.parametrize("rows",[(),("a","b","c"),("a","a")])
def test_bounded_request_population(rows):
    client=Client();handle=_KiteCandidateClientHandle(client,_KiteSessionState())
    with pytest.raises(ValueError): handle.full_quotes(rows)
    assert client.calls==[]


def test_depth_and_total_quantity_are_not_conflated():
    rows=instruments();raw=raw_quotes(rows)
    for item in raw.values():
        item["depth"]["buy"]=[dict(price=100-i,quantity=i+1,orders=2) for i in range(5)]
    result=normalize_full_quotes(raw,rows)
    assert len(result[0].bids)==5 and result[0].bids[0].quantity==1
    assert result[0].total_bid_quantity==300 and result[0].oi==1000
    assert dict(result[0].provenance)["bids"]=="KITE_FULL_QUOTE:depth.buy"


@pytest.mark.parametrize("field,value",[("instrument_token",999),("volume",-1),("oi",1.5),("last_price","NaN"),("timestamp","invented")])
def test_invalid_raw_facts_rejected(field,value):
    rows=instruments();raw=raw_quotes(rows)
    next(iter(raw.values()))[field]=value
    with pytest.raises(ValueError): normalize_full_quotes(raw,rows)


def test_missing_fields_are_not_fabricated():
    rows=instruments();raw=raw_quotes(rows)
    for item in raw.values():
        item.pop("oi");item.pop("depth");item.pop("last_trade_time")
    q=normalize_full_quotes(raw,rows)[0]
    assert q.oi is None and q.bids==() and q.last_trade_timestamp is None
    assert dict(q.availability)["oi"]=="UNAVAILABLE"


def test_missing_ohlc_has_explicit_per_field_unavailability():
    rows=instruments(); response=raw_quotes(rows)
    for item in response.values():
        item.pop("ohlc",None)
    q=normalize_full_quotes(response,rows)[0]
    assert all(dict(q.availability)["ohlc."+k]=="UNAVAILABLE" for k in ("open","high","low","close"))


@pytest.mark.parametrize("status",[200,301,302,307,308])
def test_quote_transport_never_follows_redirect_or_repeats(monkeypatch,status):
    from requests import Session, Response
    from kronos.provider.adapters.kite.client import _SingleQuoteSession
    calls=[]
    def fake_request(self,method,url,**kwargs):
        calls.append((method,url,kwargs));response=Response();response.status_code=status
        response.headers["Location"]="https://example.invalid/another"
        return response
    monkeypatch.setattr(Session,"request",fake_request)
    with _SingleQuoteSession() as transport:
        if status==200:
            assert transport.request("GET","https://example.invalid/quote",allow_redirects=True).status_code==200
        else:
            with pytest.raises(ValueError,match="REDIRECT_PROHIBITED"):
                transport.request("GET","https://example.invalid/quote",allow_redirects=True)
        with pytest.raises(ValueError,match="REPEAT_REQUEST_PROHIBITED"):
            transport.request("GET","https://example.invalid/quote")
    assert len(calls)==1
    assert calls[0][2]["allow_redirects"] is False and calls[0][2]["timeout"]==7


def test_quote_private_transport_never_changes_shared_client():
    class Observed(Client):
        def quote(self,rows):
            assert self is not original
            assert self.reqsession is not original.reqsession
            assert original.timeout==19
            return super().quote(rows)
    original=Observed();original.reqsession=object();transport=original.reqsession
    handle=_KiteCandidateClientHandle(original,_KiteSessionState())
    handle.full_quotes(("NSE:LUPIN",))
    assert original.reqsession is transport and original.timeout==19
