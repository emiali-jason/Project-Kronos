"""Research-only same-operation native quote; never a production admission."""
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from kronos.intraday.live_shadow import PRICE_MISSING, ShadowError, instant, aware
from kronos.intraday.operation_accounting import ProviderRequestCategory as Category
from kronos.intraday.probables_v2 import _encode, _identity
from kronos.provider.contracts.market_data import QuoteSnapshot


def missing(authority, reason):
    return dict(state=PRICE_MISSING,price=None,time=None,source=None,integrity=None,
                authority=authority,reason=reason,requested_at=None,received_at=None,observation=None,source_document=None)


def admission_pair(item):
    authority='WO06C_ADMISSION_PRICE'
    if item is None or item.proof is None:return missing(authority,'ADMISSION_PRICE_NOT_RETAINED')
    replace(item);p=item.proof;replace(p)
    return dict(state='AVAILABLE',price=str(p.price),time=p.observation_time.isoformat(),
        source=p.source_identity,integrity=p.integrity_identity,authority=authority,
        reason=item.reason,requested_at=p.capture_started_at.isoformat() if p.capture_started_at else None,
        received_at=p.available_at.isoformat(),observation=p.observation_identity,source_document=None)


def native_context(source,result,boundary):
    subject,record=source._admission_records[result.universe_member_identity]
    if subject!=result.canonical_subject_identity:raise ShadowError('SHADOW_NATIVE_BINDING_INVALID')
    replace(record)
    if record.exchange=='NSE' and not subject.startswith('MCX-'):
        if record.exchange!='NSE' or record.expiry is not None or record.instrument_type in {'FUT','CE','PE'}:
            raise ShadowError('SHADOW_NATIVE_BINDING_INVALID')
        if subject.startswith('NSE-INDEX-') and record.segment!='INDICES':raise ShadowError('SHADOW_NATIVE_BINDING_INVALID')
        return record,dict(state='NOT_APPLICABLE',contract=None,binding=None)
    if not subject.startswith('MCX-SUBJECT-'):raise ShadowError('SHADOW_NATIVE_BINDING_INVALID')
    binding=source._active_derivative_resolutions.for_subject(subject).binding
    replace(binding);replace(binding.active_binding)
    if (binding.canonical_subject_id!=subject or binding.observation_boundary!=boundary
        or record.exchange!='MCX' or record.trading_symbol!=binding.provider_symbol
        or record.expiry!=binding.contract_expiry or record.segment!=binding.segment
        or record.instrument_type!=binding.provider_instrument_type or record.tick_size!=binding.tick_size
        or record.lot_size!=binding.lot_size
        or not binding.active_binding.effective_from<=boundary<=binding.active_binding.effective_through):raise ShadowError('SHADOW_NATIVE_BINDING_INVALID')
    return record,dict(state='AVAILABLE',contract=binding.active_binding.derivative_contract_id,
                       binding=binding.active_binding.binding_identity)


def capture(source,result,*,operation,boundary,clock):
    authority='WO06H_COHORT_B_RESEARCH_QUOTE'
    started=received=None
    try:
        record,native=native_context(source,result,boundary)
        started=clock()
        quote=source._request_counter.invoke(Category.COHORT_B_SHADOW_OBSERVATION_REQUEST,
            source._lease.quote,record,benchmark=result.canonical_subject_identity=='NSE-INDEX-NIFTY')
        received=clock()
        if type(quote) is not QuoteSnapshot or quote.instrument!=record:raise ShadowError('SHADOW_QUOTE_BINDING_INVALID')
        replace(quote)
        price=Decimal(str(quote.last_price))
        if not price.is_finite() or price<=0 or quote.timestamp>received or started>received:
            raise ShadowError('SHADOW_QUOTE_TIME_OR_PRICE_INVALID')
        # Retain only the non-secret native instrument and the same quote pair.
        source_document=_encode(dict(instrument=quote.instrument,last_price=quote.last_price,timestamp=quote.timestamp)).decode()
        digest=sha256(source_document.encode()).hexdigest()
        observation=_identity('WO06H-QUOTE-',dict(operation=operation,result=result.result_identity,
            subject=result.canonical_subject_identity,native=native,source=digest,
            requested=started,received=received))
        return dict(state='AVAILABLE',price=str(price),time=quote.timestamp.isoformat(),
            source='DOMAIN006-QUOTE:'+_identity('PROVIDER-QUOTE-INSTRUMENT-',record),
            integrity=digest,authority=authority,reason='SAME_OPERATION_NATIVE_RESEARCH_QUOTE',
            requested_at=started.isoformat(),received_at=received.isoformat(),observation=observation,source_document=source_document)
    except Exception:
        value=missing(authority,'SHADOW_NATIVE_QUOTE_UNAVAILABLE')
        value['requested_at']=started.isoformat() if aware(started) else None
        value['received_at']=received.isoformat() if aware(received) else None
        return value
