"""Exact source-backed identity coverage; no market or Chart Analyst operations."""
from datetime import datetime,timedelta
from pathlib import Path
import json
import pytest
from kronos.instrument.visual_identity import (
    VisualIdentitySourceContext as C, VisualIdentityResolutionError,
    family_visual_context, parse_visual_identity_publication,
)
from kronos.instrument.visual_identity_persistence import load_visual_identity_resolver
from tests.unit.instrument.test_active_derivative_selection import _resolve

CASES=(('CRUDE','Crude Oil Futures','Light Crude Oil Futures','NYMEX','NYMEX-CRUDE-OIL'),
 ('COPPER','Copper Futures','Copper Futures','COMEX','COMEX-COPPER'),
 ('GOLDM','Gold Mini Futures','Gold Futures','COMEX','COMEX-GOLD'),
 ('NATGAS','Natural Gas Futures','Natural Gas Futures','NYMEX','NYMEX-NATURAL-GAS'),
 ('SILVERM','Silver Mini Futures','Silver Futures','COMEX','COMEX-SILVER'))
AT=datetime.fromisoformat('2026-09-11T10:15:00+05:30')
D=Path(__file__).resolve().parents[3]/'data/instruments/KRONOS-GOVERNED-VISUAL-IDENTITY-RELATIONSHIP-PUBLICATION-V1'
# tests/unit/instrument -> repository is parents[3]
COVERAGE=json.loads((D/'1.6.0-coverage.json').read_text())['coverage']


def resolve(label,context,at=AT):
 return load_visual_identity_resolver(publication_version='1.7.0').resolve(
  observed_visible_subject_identity=label,source_context=context,governed_observation_boundary=at)


@pytest.mark.parametrize('row',COVERAGE,ids=lambda r:r['canonical_identity'])
def test_all_91_exact_equities_preserve_relationship_and_interval(row):
 result=resolve(row['description'],C.TRADINGVIEW_VISUAL_CHART)
 assert result.canonical_subject_identity==row['canonical_identity']
 assert result.relationship_identity==row['relationship_identity']
 assert resolve(row['description'],C.TRADINGVIEW_VISUAL_CHART,datetime.fromisoformat(row['effective_from'])).relationship_identity==row['relationship_identity']


@pytest.mark.parametrize('label,canonical',[('Nifty 50 Index','NSE-INDEX-NIFTY'),('Nifty Bank Index','NSE-INDEX-BANKNIFTY')])
def test_exact_indices(label,canonical):
 assert resolve(label,C.TRADINGVIEW_VISUAL_CHART).canonical_subject_identity==canonical


@pytest.mark.parametrize('case',CASES,ids=lambda r:r[0])
@pytest.mark.parametrize('role',['NATIVE','REFERENCE'])
def test_native_and_reference_exact_family_venue_role(case,role):
 fam,native,reference,venue,ref=case
 label,ctx,target=(native,family_visual_context(role,'MCX'),'MCX-SUBJECT-'+fam) if role=='NATIVE' else (reference,family_visual_context(role,venue),'REFERENCE-SUBJECT-'+ref)
 result=resolve(label,ctx);assert result.canonical_subject_identity==target
 assert not result.canonical_subject_identity.startswith('MCX-FUT-')
 with pytest.raises(VisualIdentityResolutionError):resolve(label,ctx,datetime.fromisoformat('2026-09-10T17:03:00+05:30'))
 pub=load_visual_identity_resolver(publication_version='1.7.0').publication
 relationship=next(x for x in pub.relationships if x.relationship_identity==result.relationship_identity)
 assert resolve(label,ctx,relationship.effective_from).relationship_identity==relationship.relationship_identity
 with pytest.raises(VisualIdentityResolutionError):resolve(label,ctx,relationship.effective_from-timedelta(microseconds=1))


@pytest.mark.parametrize('case',CASES,ids=lambda r:r[0])
@pytest.mark.parametrize('change',['case','space','symbol','company_fallback','wrong_context'])
def test_unknown_labels_never_normalize_or_fall_back(case,change):
 fam,label,_,_,_=case;ctx=family_visual_context('NATIVE','MCX')
 if change=='case':label=label.upper()
 elif change=='space':label+=' '
 elif change=='symbol':label=fam+'26SEPFUT'
 elif change=='company_fallback':label='NSE-EQ-'+fam
 else:ctx=C.TRADINGVIEW_VISUAL_CHART
 with pytest.raises(VisualIdentityResolutionError):resolve(label,ctx)


@pytest.mark.parametrize('role,venue',[('NATIVE','COMEX'),('NATIVE','NYMEX'),('REFERENCE','MCX'),('NATIVE','mcx'),('WRONG','MCX')])
def test_role_venue_context_rejects(role,venue):
 with pytest.raises(VisualIdentityResolutionError):family_visual_context(role,venue)


@pytest.mark.parametrize('case',CASES,ids=lambda r:r[0])
def test_machine_rollover_changes_exact_contract_without_visual_publication(case):
 fam,label,*_=case
 before=_resolve(AT).for_subject(fam).binding;assert before is not None
 # A deterministic governed later trading day, following the exact old expiry.
 after=datetime.combine(before.contract_expiry+timedelta(days=1),AT.timetz())
 for _ in range(7):
  nxt=_resolve(after,previous={before.canonical_subject_id:before}).for_subject(fam).binding
  if nxt is not None:break
  after+=timedelta(days=1)
 if fam=='SILVERM':
  # Next retained contract expires in 2027, outside the governed 2026 calendar.
  # Stable identity remains available, but selection must not invent eligibility.
  assert nxt is None
  assert resolve(label,family_visual_context('NATIVE','MCX'),after).relationship_identity==resolve(label,family_visual_context('NATIVE','MCX'),AT).relationship_identity
  return
 assert nxt is not None and nxt.active_binding.derivative_contract_id!=before.active_binding.derivative_contract_id
 a=resolve(label,family_visual_context('NATIVE','MCX'),AT)
 b=resolve(label,family_visual_context('NATIVE','MCX'),after)
 assert a.relationship_identity==b.relationship_identity and a.publication_integrity_identity==b.publication_integrity_identity
 assert a.canonical_subject_identity==before.canonical_subject_id==nxt.canonical_subject_id


def test_successor_preserves_every_16_relationship_and_rejects_tampering():
 old=load_visual_identity_resolver(publication_version='1.6.0').publication
 new=load_visual_identity_resolver(publication_version='1.7.0').publication
 assert new.relationships[:95]==old.relationships and len(new.relationships)==106
 assert all('MCX-FUT-' not in x.canonical_subject_identity for x in new.relationships[95:])
 raw=(D/'1.7.0.json').read_bytes().replace(b'Gold Mini Futures',b'Gold Futures')
 with pytest.raises(VisualIdentityResolutionError):parse_visual_identity_publication(raw,canonical_subject_identities=tuple(x.canonical_subject_identity for x in new.relationships))
