"""Exact CSV source, immutable 1.6.0 authority and historical-boundary tests."""
from dataclasses import asdict
from datetime import datetime,timedelta
from hashlib import sha256
from io import StringIO
from pathlib import Path
import csv,json

import pytest

from kronos.instrument.tradingview_equity_export import (
    TRADINGVIEW_91_COLUMNS,TRADINGVIEW_91_RETAINED_AT,TRADINGVIEW_91_SOURCE_SHA256,
    qualify_tradingview_equity_export,build_tradingview_equity_successor,
)
from kronos.instrument.visual_identity import (
    VisualIdentityResolutionError,VisualIdentitySourceContext,VisualIdentityResolver,
    create_visual_identity_relationship,create_visual_identity_publication,
    encode_visual_identity_publication,parse_visual_identity_publication,
)
from kronos.instrument.visual_identity_persistence import load_visual_identity_resolver,resolver_for_retained_publication
from kronos.instrument.semantic_v2_persistence import InstrumentSemanticV2Store
from kronos.intraday.universe import load_intraday_universe_publication

ROOT=Path(__file__).resolve().parents[3]
DATA=ROOT/'data/instruments/KRONOS-GOVERNED-VISUAL-IDENTITY-RELATIONSHIP-PUBLICATION-V1'
AUDIT=json.loads((DATA/'1.6.0-coverage.json').read_bytes())
SOURCE=(DATA/AUDIT['source_path']).read_bytes()
BINDINGS=tuple(tuple(x) for x in AUDIT['source_bindings'])
ROWS=AUDIT['coverage']
AT=TRADINGVIEW_91_RETAINED_AT
REVIEW=datetime.fromisoformat('2026-09-10T17:03:00+05:30')
SEVEN=('INDIGO','JUBLFOOD','LUPIN','MOTHERSON','NTPC','VEDL','YESBANK')
CANONICAL=tuple(x['canonical_id'] for x in json.loads((ROOT/'data/instruments/KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2/1.2.0.json').read_bytes())['semantic_objects'])


def resolve(label,at=AT,source=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART):
    return load_visual_identity_resolver(publication_version='1.6.0').resolve(
        observed_visible_subject_identity=label,source_context=source,governed_observation_boundary=at)


def test_csv_exact_bytes_and_governed_universe_reconciliation():
    assert sha256(SOURCE).hexdigest()==TRADINGVIEW_91_SOURCE_SHA256
    assert tuple(next(csv.reader(StringIO(SOURCE.decode()))))==TRADINGVIEW_91_COLUMNS
    qualified=qualify_tradingview_equity_export(SOURCE,symbol_bindings=BINDINGS)
    assert qualified.row_count==len(qualified.matched)==91
    assert not qualified.missing and not qualified.extra
    catalogue=InstrumentSemanticV2Store(ROOT/'data/instruments').load(
        publication_identity='KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V2',publication_version='1.2.0')
    members=[m for m in load_intraday_universe_publication().members if m.market_family.value=='NSE_EQUITY']
    assert len(members)==91
    for member in members:
        objects=[x for x in catalogue.semantic_objects if x.source_identity==member.membership_identity]
        assert len(objects)==1
        assert objects[0].classification.value=='NSE_CASH_EQUITY' and objects[0].exchange=='NSE'
        assert dict(BINDINGS)['NSE:'+member.sponsor_label]==objects[0].canonical_id
    assert dict(BINDINGS)['NSE:BAJAJ_AUTO']=='NSE-EQ-BAJAJ-AUTO'
    assert dict(BINDINGS)['NSE:RELIANCE']=='RELIANCE'


@pytest.mark.parametrize('row',ROWS,ids=lambda r:r['symbol'])
def test_each_equity_exact_resolver_and_provenance(row):
    result=resolve(row['description'])
    assert result.canonical_subject_identity==row['canonical_identity']
    assert result.observed_visible_subject_identity==row['description']
    assert result.relationship_identity==row['relationship_identity']
    assert result.publication_version=='1.6.0'
    assert result.publication_integrity_identity==AUDIT['publication_integrity']
    source_row=list(csv.reader(StringIO(SOURCE.decode())))[row['row_number']-1]
    assert source_row[:2]==[row['symbol'],row['description']]
    assert sha256(json.dumps(source_row,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()==row['row_sha256']


@pytest.mark.parametrize('row',ROWS,ids=lambda r:r['symbol'])
def test_each_equity_before_at_after_exact_effective_boundary(row):
    start=datetime.fromisoformat(row['effective_from'])
    with pytest.raises(VisualIdentityResolutionError): resolve(row['description'],start-timedelta(microseconds=1))
    for at in (start,start+timedelta(microseconds=1)):
        assert resolve(row['description'],at).canonical_subject_identity==row['canonical_identity']


@pytest.mark.parametrize('symbol',SEVEN)
def test_current_seven_preserve_1703_limit_and_new_boundary_support(symbol):
    row=next(r for r in ROWS if r['symbol']==symbol)
    if symbol in ('INDIGO','NTPC','VEDL'):
        assert resolve(row['description'],REVIEW).canonical_subject_identity==row['canonical_identity']
    else:
        with pytest.raises(VisualIdentityResolutionError,match='UNAVAILABLE'):resolve(row['description'],REVIEW)
        assert datetime.fromisoformat(row['effective_from'])==AT
    assert resolve(row['description'],AT).canonical_subject_identity==row['canonical_identity']


def test_successor_reproducible_preserves_all_49_old_records_and_adds_46():
    old=load_visual_identity_resolver(publication_version='1.5.0').publication
    new=load_visual_identity_resolver(publication_version='1.6.0').publication
    made=build_tradingview_equity_successor(old,SOURCE,symbol_bindings=BINDINGS,canonical_subject_identities=CANONICAL)
    assert encode_visual_identity_publication(made)==(DATA/'1.6.0.json').read_bytes()
    assert made==new and new.relationships[:49]==old.relationships
    assert len(new.relationships)==95 and new.supersedes==old.integrity_identity
    for r in new.relationships[49:]:
        assert r.effective_from==AT
        row=next(x for x in ROWS if x['relationship_identity']==r.relationship_identity)
        assert 'TRADINGVIEW-SYMBOL:'+row['symbol'] in r.provenance
        assert 'TRADINGVIEW-DESCRIPTION:'+row['description'] in r.provenance
        assert 'CSV-SHA256-'+TRADINGVIEW_91_SOURCE_SHA256 in r.provenance
    assert len({r.canonical_subject_identity for r in new.relationships if not r.canonical_subject_identity.startswith('NSE-INDEX-')})==91


@pytest.mark.parametrize('old_label,new_label,canonical',[
    ('Divis Laboratories Limited',"Divi's Laboratories Limited",'NSE-EQ-DIVISLAB'),
    ('Persistent Systems Ltd.','Persistent Systems Limited','NSE-EQ-PERSISTENT'),
    ('RBL Bank Ltd','RBL Bank Ltd.','NSE-EQ-RBLBANK'),
])
def test_new_alternate_spellings_do_not_rewrite_old_exact_authority(old_label,new_label,canonical):
    assert resolve(old_label).canonical_subject_identity==resolve(new_label).canonical_subject_identity==canonical
    assert resolve(old_label,REVIEW).canonical_subject_identity==canonical
    with pytest.raises(VisualIdentityResolutionError):resolve(new_label,REVIEW)


def test_mm_and_separate_indices_and_mcx():
    row=next(x for x in ROWS if x['symbol']=='M&M')
    assert row['canonical_identity']=='NSE-EQ-M&M' and row['description']=='Mahindra & Mahindra Ltd.'
    assert resolve(row['description']).canonical_subject_identity=='NSE-EQ-M&M'
    assert resolve('Nifty Bank Index').canonical_subject_identity=='NSE-INDEX-BANKNIFTY'
    for label in ['NIFTY','Nifty 50','Nifty 50 Index','M&M','Mahindra and Mahindra Ltd.','CRUDEOILU2026','NGV2026']:
        with pytest.raises(VisualIdentityResolutionError):resolve(label)


@pytest.mark.parametrize('label',['Unknown Company','Jubilant Foodworks Ltd','jubilant foodworks limited',
    'Jubilant Foodworks Limited ','Lupin Limited.','JUBLFOOD','NSE-EQ-JUBLFOOD','Mahindra & Mahindra Ltd'])
def test_unknown_wrong_description_symbol_and_unsupported_variants_fail_closed(label):
    with pytest.raises(VisualIdentityResolutionError):resolve(label)


def test_wrong_source_and_outside_interval():
    for source in ('PROVIDER_INSTRUMENT_MASTER','KITE','TRADINGVIEW_VISUAL_CHART'):
        with pytest.raises(VisualIdentityResolutionError):resolve('Lupin Limited',source=source)
    with pytest.raises(VisualIdentityResolutionError):resolve('Lupin Limited',datetime.fromisoformat('2020-01-01T00:00:00+00:00'))


def altered(change):
    rows=list(csv.reader(StringIO(SOURCE.decode())));change(rows)
    out=StringIO(newline='');csv.writer(out).writerows(rows);return out.getvalue().encode()


@pytest.mark.parametrize('change',[
    lambda r:r[1].__setitem__(0,'WRONG_SYMBOL'),
    lambda r:r[1].__setitem__(1,'Wrong Description'),
    lambda r:r[1].__setitem__(1,r[2][1]),
    lambda r:r[1].__setitem__(0,r[2][0]),
])
def test_wrong_symbol_description_foreign_pair_and_duplicate_tamper_rejected(change):
    payload=altered(change)
    with pytest.raises(ValueError,match='INTEGRITY'):qualify_tradingview_equity_export(payload,symbol_bindings=BINDINGS)
    with pytest.raises(ValueError,match='INTEGRITY'):
        build_tradingview_equity_successor(load_visual_identity_resolver(publication_version='1.5.0').publication,
            payload,symbol_bindings=BINDINGS,canonical_subject_identities=CANONICAL)


@pytest.mark.parametrize('change,code',[
    (lambda r:r.append(r[1].copy()),'DUPLICATE_SYMBOL'),
    (lambda r:r[1].__setitem__(0,r[2][0]),'DUPLICATE_SYMBOL'),
    (lambda r:r[1].__setitem__(1,r[2][1]),'AMBIGUOUS_DESCRIPTION'),
    (lambda r:r[1].__setitem__(0,''),'BLANK_OR_PADDED'),
    (lambda r:r[1].__setitem__(1,''),'BLANK_OR_PADDED'),
    (lambda r:r[1].pop(),'COLUMNS_INVALID'),
    (lambda r:r[0].__setitem__(0,'Ticker'),'COLUMNS_INVALID'),
])
def test_integrity_alone_does_not_replace_structural_validation(change,code):
    payload=altered(change)
    with pytest.raises(ValueError,match=code):qualify_tradingview_equity_export(payload,symbol_bindings=BINDINGS,expected_sha256=sha256(payload).hexdigest())


def test_missing_extra_and_wrong_symbol_are_reported_and_never_matched():
    payload=altered(lambda r:r[1].__setitem__(0,'NYSE:ADANIENT'))
    result=qualify_tradingview_equity_export(payload,symbol_bindings=BINDINGS,expected_sha256=sha256(payload).hexdigest())
    assert result.missing==('NSE:ADANIENT',) and result.extra==('NYSE:ADANIENT',)
    assert len(result.matched)==90 and all(x.canonical_identity!='NSE-EQ-ADANIENT' for x in result.matched)


def test_wrong_source_and_governed_bindings_reject():
    with pytest.raises(ValueError,match='SOURCE_INVALID'):qualify_tradingview_equity_export(SOURCE,symbol_bindings=BINDINGS,source_authority='TRADINGVIEW_API')
    for bindings in (BINDINGS+(BINDINGS[0],), (('NSE:OTHER',BINDINGS[0][1]),)+BINDINGS[1:],
        ((BINDINGS[0][0],BINDINGS[1][1]),)+BINDINGS[1:]):
        with pytest.raises(ValueError,match='BINDING_INVALID'):qualify_tradingview_equity_export(SOURCE,symbol_bindings=bindings)


@pytest.mark.parametrize('version',['1.0.0','1.1.0','1.2.0','1.3.0','1.4.0','1.5.0'])
def test_historical_publication_replay_selects_original_exact_bytes(version):
    current=load_visual_identity_resolver(publication_version='1.6.0')
    old=load_visual_identity_resolver(publication_version=version)
    restored=resolver_for_retained_publication(current,publication_identity=old.publication.publication_identity,
        publication_version=version,publication_integrity_identity=old.publication.integrity_identity)
    assert encode_visual_identity_publication(restored.publication)==(DATA/(version+'.json')).read_bytes()


def test_tampered_publication_duplicate_conflict_and_ambiguous_relationships():
    pub=load_visual_identity_resolver(publication_version='1.6.0').publication
    payload=encode_visual_identity_publication(pub).replace(b'Jubilant Foodworks Limited',b'Wrong Description')
    with pytest.raises(VisualIdentityResolutionError):parse_visual_identity_publication(payload,canonical_subject_identities=CANONICAL)
    values=asdict(pub);values.pop('integrity_identity');values['relationships']=pub.relationships+(pub.relationships[-1],)
    with pytest.raises(VisualIdentityResolutionError):create_visual_identity_publication(canonical_subject_identities=CANONICAL,**values)
    fields=asdict(pub.relationships[-1]);fields.pop('relationship_identity');fields.pop('integrity_identity')
    fields['canonical_subject_identity']='NSE-EQ-JUBLFOOD'
    conflict=create_visual_identity_relationship(**fields);values['relationships']=pub.relationships+(conflict,)
    with pytest.raises(VisualIdentityResolutionError):create_visual_identity_publication(canonical_subject_identities=CANONICAL,**values)
    fields['canonical_subject_identity']=pub.relationships[-1].canonical_subject_identity;fields['source_identity']='SECOND_SOURCE'
    ambiguous=create_visual_identity_relationship(**fields);values['relationships']=pub.relationships+(ambiguous,)
    sealed=create_visual_identity_publication(canonical_subject_identities=CANONICAL,**values)
    with pytest.raises(VisualIdentityResolutionError,match='AMBIGUOUS'):
        VisualIdentityResolver(sealed).resolve(observed_visible_subject_identity=ambiguous.observed_visible_subject_identity,
            source_context=ambiguous.source_context,governed_observation_boundary=AT)


def test_export_only_boundary_cannot_be_backdated_by_builder():
    with pytest.raises(ValueError,match='AUTHORITY_INVALID'):
        build_tradingview_equity_successor(load_visual_identity_resolver(publication_version='1.5.0').publication,
            SOURCE,symbol_bindings=BINDINGS,canonical_subject_identities=CANONICAL,effective_from=REVIEW)
