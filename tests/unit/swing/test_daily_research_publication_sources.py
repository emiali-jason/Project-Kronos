"""Canonical archival source cut: stream fact bytes, never replay analysis."""
from datetime import timedelta
from hashlib import sha256
import pytest
from kronos.swing.v1.prospective_research import IST
from tests.unit.swing.test_run_publication import checkpoint, scenario


def test_exact_retained_day_native_and_hashes_without_mtf_deserialization(checkpoint, monkeypatch):
 co,snapshot,bindings,committed=checkpoint
 before={str(p):p.read_bytes() for p in co.root.rglob('*') if p.is_file()}
 def forbidden(*a,**k):raise AssertionError('NO_FULL_FACT_REPLAY')
 monkeypatch.setattr(co.mtf_store,'load',forbidden)
 day=committed.provenance.successful_completed_at.astimezone(IST).date()
 result=co.retained_daily_sources(day)
 assert len(result)==1 and result[0]['run_identity']==snapshot.run_identity
 assert result[0]['publication']==committed.reference
 assert result[0]['artifacts']==committed.manifest['artifacts']
 assert len(result[0]['assessments'])==len(committed.native.assessments)
 assert co.retained_daily_sources(day-timedelta(days=1))==()
 assert {str(p):p.read_bytes() for p in co.root.rglob('*') if p.is_file()}==before

@pytest.mark.parametrize('kind',['native','mtf','relative','provenance'])
def test_changed_exact_artifact_fails_closed(checkpoint,kind):
 co,_,_,c=checkpoint
 p=co._paths(c.native.run_identity)[kind];p.write_bytes(p.read_bytes()+b' ')
 with pytest.raises(ValueError):co.retained_daily_sources(c.provenance.successful_completed_at.astimezone(IST).date())


def test_admission_during_cut_fails_without_writes(checkpoint,monkeypatch):
 co,_,_,c=checkpoint;read=co._control;calls=[]
 def changed():
  v=read();calls.append(None)
  if len(calls)>1:v={**v,'admission_generation':v['admission_generation']+1}
  return v
 monkeypatch.setattr(co,'_control',changed)
 with pytest.raises(ValueError):co.retained_daily_sources(c.provenance.successful_completed_at.astimezone(IST).date())

@pytest.mark.parametrize('gap',['superseded','failed','interrupted'])
def test_lawful_admission_gaps_preserve_exact_committed_ancestry(checkpoint,gap):
 from tests.unit.swing.test_run_publication import prepared
 co,snapshot,bindings,original=checkpoint
 a,av=prepared(co,snapshot,bindings,2)
 if gap=='failed': assert co.fail(a,av['mtf'].observed_at)
 if gap=='interrupted': co.recover(av['mtf'].observed_at)
 b,bv=prepared(co,snapshot,bindings,3)
 assert co.publish(b,co.prepare(b,**bv),bv['mtf'].observed_at)
 history=co.committed_history()
 assert [x.manifest['generation'] for x in history]==[0,2]
 before={str(p):p.read_bytes() for p in co.root.rglob('*') if p.is_file()}
 for bundle in history:
  day=bundle.provenance.successful_completed_at.astimezone(IST).date()
  observed=co.retained_daily_sources(day)
  expected=[x for x in history if x.provenance.successful_completed_at.astimezone(IST).date()==day]
  assert [x['publication'] for x in observed]==[x.reference for x in expected]
 assert {str(p):p.read_bytes() for p in co.root.rglob('*') if p.is_file()}==before

@pytest.mark.parametrize('invalid',['equal','reversed','missing_link','wrong_hash','invalid_root'])
def test_invalid_ancestry_still_rejected(checkpoint,monkeypatch,invalid):
 import json
 from tests.unit.swing.test_run_publication import prepared
 co,snapshot,bindings,root=checkpoint
 a,av=prepared(co,snapshot,bindings,2)
 ref=co.prepare(a,**av);co.publish(a,ref,av['mtf'].observed_at)
 top=json.loads(co._manifest_path(ref).read_bytes())
 if invalid in ('equal','reversed'):top['generation']=0 if invalid=='equal' else -1
 elif invalid=='invalid_root':top['predecessor_manifest']=None
 elif invalid=='missing_link':top['predecessor_manifest']={'path':'manifests/'+('f'*64)+'.json','sha256':'f'*64}
 else:top['predecessor_manifest']={**root.reference,'sha256':'f'*64}
 raw=json.dumps(top,sort_keys=True,separators=(',',':')).encode();h=sha256(raw).hexdigest()
 forged={'path':'manifests/'+h+'.json','sha256':h};co._manifest_path(forged).write_bytes(raw)
 control=co._control();monkeypatch.setattr(co,'_control',lambda:{**control,'current_manifest':forged})
 with pytest.raises((ValueError,FileNotFoundError)):
  co.retained_daily_sources(av['mtf'].observed_at.astimezone(IST).date())
