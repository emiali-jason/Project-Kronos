"""Exact Native MCX source binding, international separation and commissioning."""
from dataclasses import fields
import pytest
from tests.unit.intraday.test_native_pullback_decision import source_fixture,BOUNDARY
from tests.unit.instrument.test_active_derivative_selection import _resolve
from tests.unit.intraday.test_discovery_runtime import _publications,_bundle
from kronos.intraday.discovery_runtime import DiscoveryRunBoundary
from kronos.intraday.discovery import create_machine_fact_bundle
from kronos.intraday.native_pullback_decision import build_decision,decode_source,retain_decision,load_decision_source,source_document
from kronos.intraday.native_structural_selection import NativeStructuralStore


def mcx_source(family):
    subject='MCX-SUBJECT-'+family
    binding=_resolve(BOUNDARY).for_subject(subject).binding
    assert binding is not None
    _,reconciliation=_publications();member=next(m for m in reconciliation.members if m.canonical_identity==subject)
    bundle=_bundle(member,DiscoveryRunBoundary(BOUNDARY,binding.domain008_session_identity,'BOUNDARY'),reconciliation)
    values={f.name:getattr(bundle,f.name) for f in fields(bundle) if f.name!='bundle_identity'}
    values['source_identities']+=(binding.binding_identity,binding.provider_snapshot_identity)
    values['provenance']+=(binding.integrity_identity,binding.domain008_session_identity)
    bundle=create_machine_fact_bundle(**values)
    source,f,m,run=source_fixture(subject=subject,session=binding.domain008_session_identity,binding=binding,bundle=bundle)
    return source,f,m,run,binding,bundle

@pytest.mark.parametrize('family',['CRUDE','COPPER','GOLDM','SILVERM','NATGAS'])
def test_native_exact_contract_no_international_authority(tmp_path,family):
    source,f,m,run,binding,bundle=mcx_source(family)
    store=NativeStructuralStore(tmp_path/'native');d=retain_decision(store,source,created_at=BOUNDARY)
    assert d.data['result']==('NOT_ESTABLISHED' if family=='NATGAS' else 'PULLBACK'),d.data
    if family=='NATGAS':assert run.results[0].execution_eligibility!='ELIGIBLE'
    assert d.data['exact_contract']==binding.active_binding.derivative_contract_id
    assert d.data['roll_lineage']==binding.binding_identity
    assert load_decision_source(store,d,None)==source
    assert 'NYMEX' not in d.payload_json and 'COMEX' not in d.payload_json

@pytest.mark.parametrize('family',['CRUDE','COPPER','GOLDM','SILVERM','NATGAS'])
@pytest.mark.parametrize('case',['missing_binding','missing_bundle','different_family'])
def test_missing_or_different_binding_cannot_supply_native_authority(family,case):
    source,f,m,run,binding,bundle=mcx_source(family)
    if case=='missing_binding':binding=None
    elif case=='missing_bundle':bundle=None
    else:binding=_resolve(BOUNDARY).for_subject('MCX-SUBJECT-'+('COPPER' if family!='COPPER' else 'CRUDE')).binding
    with pytest.raises(ValueError,match='MCX_CONTRACT_BINDING_INVALID'):
        source_document(f,m,run.results[0],run.run_identity,mcx_binding=binding,machine_bundle=bundle)
