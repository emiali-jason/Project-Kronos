"""WO-06H immutable research contracts. Never production selection or trading authority."""
from dataclasses import dataclass
from datetime import datetime, timezone, date
from decimal import Decimal
from calendar import monthrange
from zoneinfo import ZoneInfo
import json
from hashlib import sha256
import re
from kronos.intraday.population_measurement import canonical, identity
from kronos.intraday.technical_context_research import decimal_policy

SCHEMA='KRONOS-INTRADAY-LIVE-SHADOW/1.0.0'
COHORT_A='PRODUCTION_ADMISSION'
COHORT_B='CPR_SOLE_BLOCKED_SHADOW'
NE='NOT_ESTABLISHED'
PRICE_MISSING='PRICE_NOT_RETAINED'
FEATURES=('sma20_side','sma50_side','vwap_side','5M','15M','nifty_relationship','local_structure')
CANDLE_FIELDS=('body_ratio','upper_wick_ratio','lower_wick_ratio','close_location','range_ratio','pair_range')
RESEARCH_INPUTS={
 'WO06E':'WO06E-RESEARCH-1d118f57ed95cc58a4d304e97a635ed1dc72cad5f6262a90d6bd7eddb314b015',
 'WO06F':'WO06F-RESEARCH-415176852e5b3e9e493af5db6259419babbea6b6fc7dac7c610d9cf04926ada3',
 'WO06G':'WO06G-RESEARCH-ab3c4f33ce7f2c5665b5a5a1de12dcf1605863734db5dceadb87ea9abd1e2515',
}
KINDS={'window','acceptance','operation','receipt','batch','intent','observation','outcome'}
KEY=re.compile(r'WO06H-[A-Z]+-[a-f0-9]{64}\Z')


class ShadowError(ValueError):
    """Bounded research-only error vocabulary."""


def aware(t):
    return type(t) is datetime and t.utcoffset() is not None


def instant(s):
    try:t=datetime.fromisoformat(s)
    except (TypeError,ValueError):raise ShadowError('SHADOW_TIME_INVALID') from None
    if not aware(t):raise ShadowError('SHADOW_TIME_INVALID')
    return t


def next_month(t):
    if not aware(t):raise ShadowError('SHADOW_TIME_INVALID')
    t=t.astimezone(ZoneInfo('Asia/Kolkata'));y=t.year+(t.month==12);m=t.month%12+1
    return t.replace(year=y,month=m,day=min(t.day,monthrange(y,m)[1]))


def key(kind,*parts):
    if kind not in KINDS:raise ShadowError('SHADOW_KIND_INVALID')
    return identity('WO06H-'+kind.upper()+'-', [SCHEMA,*parts])


@dataclass(frozen=True)
class Artifact:
    """Canonical bytes give deep immutability; body access returns a fresh copy."""
    kind: str
    key: str
    payload: bytes

    def __post_init__(self):
        try:
            d=json.loads(self.payload)
            if (self.kind not in KINDS or not KEY.fullmatch(self.key)
                    or not self.key.startswith('WO06H-'+self.kind.upper()+'-')
                    or set(d)!={'schema','kind','key','body','integrity'}
                    or d['schema']!=SCHEMA or d['kind']!=self.kind or d['key']!=self.key
                    or canonical(d)!=self.payload):raise ValueError
            b=d['body']
            if type(b) is not dict or d['integrity']!=identity('WO06H-INTEGRITY-', {k:v for k,v in d.items() if k!='integrity'}):raise ValueError
            if b.get('authority')!='RESEARCH_ONLY':raise ValueError
            validate_body(self.kind,b)
        except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError):
            raise ShadowError('SHADOW_ARTIFACT_INVALID') from None

    @property
    def body(self):return json.loads(self.payload)['body']

    @property
    def integrity(self):return json.loads(self.payload)['integrity']


def artifact(kind,identifier,body):
    d=dict(schema=SCHEMA,kind=kind,key=identifier,body=body)
    d['integrity']=identity('WO06H-INTEGRITY-',d)
    return Artifact(kind,identifier,canonical(d))


FIELDS={
 'operation':'authority window operation started_at runtime',
 'receipt':'authority window operation run batch disposition',
 'window':'authority start start_utc end runtime runtime_proof request research_inputs methodology schema definitions',
 'acceptance':'authority window runtime runtime_proof request accepted_at',
 'batch':'authority window run run_integrity operation boundary recorded_at expected classification_failures',
 'intent':'authority observation window run result cohort operation requested_at',
 'observation':'authority window run result mapping source_integrity subject native session schedule phase direction methodology boundary captured_at runtime cohort assessment features grouping baseline_state narrow cpr_source intent',
 'outcome':'authority observation window subject session native eod_native price time source source_integrity assessment_integrity move_pct state runtime',
}


def validate_body(kind,b):
    if set(b)!=set(FIELDS[kind].split()):raise ValueError
    if kind in {'batch','intent','observation','outcome','acceptance','operation','receipt'} and not KEY.fullmatch(b['window']):raise ValueError
    if kind=='operation':instant(b['started_at'])
    if kind=='receipt' and b['disposition'] not in {'POPULATION_RECORDED','HISTORICAL_REPLAY_NO_CAPTURE','OUTSIDE_CAPTURE_WINDOW'}:raise ValueError
    if kind=='batch':
        if set(b['expected'])!={COHORT_A,COHORT_B}:raise ValueError
        a,z=b['expected'][COHORT_A],b['expected'][COHORT_B]
        if a!=sorted(set(a)) or z!=sorted(set(z)) or set(a)&set(z):raise ValueError
        if any(not KEY.fullmatch(k) for k in a+z):raise ValueError
    if kind=='intent':
        if b['cohort'] not in {COHORT_A,COHORT_B}:raise ValueError
        instant(b['requested_at'])
    if kind=='window':
        if (b['end']!=next_month(instant(b['start'])).isoformat()
                or b['research_inputs']!=RESEARCH_INPUTS or b['methodology']!='2.2.0'
                or b['schema']!=SCHEMA or instant(b['start'])!=instant(b['start_utc'])):raise ValueError
    if kind=='observation':
        if b['cohort'] not in {COHORT_A,COHORT_B} or b['direction'] not in {'LONG','SHORT'} or b['methodology']!='2.2.0':raise ValueError
        if set(b['features']['values'])!=set(FEATURES):raise ValueError
        for tf in ('5M','15M'):
            c=b['features']['values'][tf]
            if set(c)!=set(CANDLE_FIELDS):raise ValueError
            if c['pair_range'] not in {'INSIDE','OUTSIDE','EQUAL','OTHER',NE}:raise ValueError
            for k in CANDLE_FIELDS[:-1]:
                if c[k] is not None and (not Decimal(c[k]).is_finite() or Decimal(c[k])<0 or (k!='range_ratio' and Decimal(c[k])>1)):raise ValueError
        for name in ('sma20_side','sma50_side','vwap_side'):
            if b['features']['values'][name] not in {'ABOVE','BELOW','AT',NE}:raise ValueError
        if type(b['narrow']) is not bool or (b['cohort']==COHORT_B and b['narrow']):raise ValueError
        if set(b['features'])!={'identity','definitions','values','availability','sources','unavailable'}:raise ValueError
        expected_availability={name:('AVAILABLE' if value!=NE else NE) if not isinstance(value,dict) else {k:('AVAILABLE' if v is not None and v!=NE else NE) for k,v in value.items()} for name,value in b['features']['values'].items()}
        if b['features']['availability']!=expected_availability:raise ValueError
        a=b['assessment']
        if set(a)!={'state','price','time','source','integrity','authority','reason','requested_at','received_at','observation','source_document'}:raise ValueError
        if a['state']==PRICE_MISSING:
            if any(a[k] is not None for k in ('price','time','source','integrity')):raise ValueError
        elif a['state']=='AVAILABLE':
            if (not Decimal(a['price']).is_finite() or Decimal(a['price'])<=0 or instant(a['time'])>instant(a['received_at'])
                    or not a['source'] or not a['integrity']):raise ValueError
        else:raise ValueError
        if b['cohort']==COHORT_B:
            if a['authority']!='WO06H_COHORT_B_RESEARCH_QUOTE':raise ValueError
            if a['state']=='AVAILABLE':
                from kronos.intraday.probables_v2 import _identity
                source=json.loads(a['source_document'])
                if (set(source)!={'instrument','last_price','timestamp'}
                    or Decimal(str(source['last_price']))!=Decimal(a['price'])
                    or instant(source['timestamp'])!=instant(a['time'])
                    or a['source']!='DOMAIN006-QUOTE:'+_identity('PROVIDER-QUOTE-INSTRUMENT-',source['instrument'])
                    or a['integrity']!=sha256(a['source_document'].encode()).hexdigest()):raise ValueError
        elif a['authority']!='WO06C_ADMISSION_PRICE' or a['source_document'] is not None:raise ValueError
        instant(b['boundary']);instant(b['captured_at'])
    if kind=='outcome':
        if b['state'] not in {'POSITIVE_DIRECTIONAL_MOVE','NEGATIVE_DIRECTIONAL_MOVE','FLAT_DIRECTIONAL_MOVE',NE}:raise ValueError
        if b['move_pct'] is not None and not Decimal(b['move_pct']).is_finite():raise ValueError
        if b['price'] is None:raise ValueError
        instant(b['time'])


@decimal_policy
def directional_move(direction,assessment,eod):
    if direction not in {'LONG','SHORT'}:raise ShadowError('SHADOW_DIRECTION_INVALID')
    if assessment is None or eod is None:return None,NE
    a,z=Decimal(assessment),Decimal(eod)
    if not a.is_finite() or not z.is_finite() or a<=0:return None,NE
    value=Decimal(100)*(z-a if direction=='LONG' else a-z)/a
    return str(value),('POSITIVE_DIRECTIONAL_MOVE' if value>0 else 'NEGATIVE_DIRECTIONAL_MOVE' if value<0 else 'FLAT_DIRECTIONAL_MOVE')


def retention_eligible(month,now,*,closed,reconciled,excel_exists,excel_integrity,excel_readable,conflicts):
    """Future eligibility predicate only; performs no deletion or workbook generation."""
    if not aware(now) or type(month) is not str or not re.fullmatch(r'\d{4}-\d{2}',month):raise ShadowError('RETENTION_INPUT_INVALID')
    y,m=map(int,month.split('-'));date(y,m,1)
    next_y,next_m=y+(m==12),m%12+1
    eligible_from=date(next_y,next_m,6)
    return (now.astimezone(ZoneInfo('Asia/Kolkata')).date()>=eligible_from
            and all(x is True for x in (closed,reconciled,excel_exists,excel_integrity,excel_readable)) and conflicts==0)
