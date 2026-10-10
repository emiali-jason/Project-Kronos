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


def _publication_fixture(tmp_path, family='CRUDE'):
    from kronos.application.intraday_native_selection import NativePullbackPublication
    from kronos.instrument.active_derivative_persistence import ActiveDerivativeBindingStore
    source, facts, mapping, run, binding, bundle = mcx_source(family)
    bindings = ActiveDerivativeBindingStore((tmp_path / 'bindings').resolve())
    bindings.retain(binding)
    native = NativeStructuralStore(tmp_path / 'native')
    publisher = NativePullbackPublication(native, clock=lambda: BOUNDARY,
        commissioned_at=BOUNDARY, binding_store=bindings)
    return publisher, native, bindings, source, facts, mapping, run, binding, bundle


def _lookup_bundle(family, identities, *, provenance=None):
    # Rebind the owner-validated facts to the deliberately varied bundle identity.
    _, _, _, _, binding, original = mcx_source(family)
    values = {f.name: getattr(original, f.name) for f in fields(original)
              if f.name != 'bundle_identity'}
    values['source_identities'] = tuple(identities)
    if provenance is not None:
        values['provenance'] = tuple(provenance)
    bundle = create_machine_fact_bundle(**values)
    from unittest.mock import patch
    # Generate typed owner facts/mapping even when the deliberate bundle variant
    # cannot pass final Native validation. The real publisher validates it below.
    with patch('tests.unit.intraday.test_native_pullback_decision.source_document', return_value=None):
        source, facts, mapping, run = source_fixture(subject=binding.canonical_subject_id,
            session=binding.domain008_session_identity, binding=binding, bundle=bundle)
    return source, facts, mapping, run, binding, bundle


@pytest.mark.parametrize('family', ['GOLDM', 'SILVERM', 'COPPER', 'CRUDE', 'NATGAS'])
def test_publisher_loads_exact_canonical_binding_and_restores_immutable_source(tmp_path, family, monkeypatch):
    import json
    from kronos.instrument.active_derivative import active_derivative_binding_bytes
    publisher, native, bindings, source, facts, mapping, run, binding, bundle = _publication_fixture(tmp_path, family)
    calls = []
    load = bindings.load
    def exact_load(*, binding_identity):
        calls.append(binding_identity)
        return load(binding_identity=binding_identity)
    monkeypatch.setattr(bindings, 'load', exact_load)
    monkeypatch.setattr(bindings, 'load_current', lambda **kw: pytest.fail('no latest binding lookup'))
    decision, = publisher.publish(run, (mapping,), facts=(facts,), bundles=(bundle,), newly_published=True)
    assert calls == [binding.binding_identity]
    assert decision.data['subject'] == binding.canonical_subject_id
    assert decision.data['exact_contract'] == binding.active_binding.derivative_contract_id
    assert decision.data['roll_lineage'] == binding.binding_identity
    assert decision.data['session'] == binding.domain008_session_identity
    restored_source = load_decision_source(NativeStructuralStore(native.root), decision, None)
    assert restored_source == source
    restored_binding = decode_source(restored_source)[3]
    assert restored_binding == binding
    assert restored_binding.contract_expiry == binding.active_binding.contract_expiry
    assert restored_binding.provider_contract_family == binding.provider_contract_family
    assert restored_binding.integrity_identity == binding.integrity_identity
    assert restored_source['mcx_binding'].encode() == active_derivative_binding_bytes(binding)
    assert 'MCX_CONTRACT_BINDING_INVALID' not in decision.data['reasons']
    if family == 'NATGAS':
        assert decision.data['result'] == 'NOT_ESTABLISHED'
        assert run.results[0].execution_eligibility != 'ELIGIBLE'
        assert decision.data['roles'] == {} and decision.data['cycle'] is None
    manifest = json.loads((native.root / 'runs' / (run.run_identity + '.json')).read_bytes())
    assert manifest['selections'] == [decision.identity]
    assert manifest['result_identities'] == [run.results[0].result_identity]
    before = {p: p.read_bytes() for p in native.root.rglob('*') if p.is_file()}
    assert publisher.publish(run, (mapping,), facts=(facts,), bundles=(bundle,), newly_published=True) == (decision,)
    assert calls == [binding.binding_identity]  # Existing evidence is never reselected.
    assert before == {p: p.read_bytes() for p in native.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('case', ['zero', 'multiple', 'artifact_only', 'provenance_only',
    'uppercase', 'short', 'long', 'trailing_space', 'leading_space', 'nonhex', 'path'])
def test_publisher_requires_exact_one_lookup_class_without_fallback(tmp_path, case, monkeypatch):
    publisher, native, bindings, _, _, _, _, binding, original = _publication_fixture(tmp_path)
    identity = binding.binding_identity
    invalid = {
        'zero': ('UNRELATED',),
        'multiple': (identity, 'ACTIVE-DERIVATIVE-BINDING-' + 'a' * 64),
        'artifact_only': (binding.integrity_identity,),
        'provenance_only': ('UNRELATED',),
        'uppercase': (identity.upper(),),
        'short': (identity[:-1],),
        'long': (identity + 'a',),
        'trailing_space': (identity + ' ',),
        'leading_space': (' ' + identity,),
        'nonhex': ('ACTIVE-DERIVATIVE-BINDING-' + 'g' * 64,),
        'path': (identity + '/other',),
    }
    # MachineFactBundle already rejects padded strings; no normalization is lawful.
    if case in {'trailing_space', 'leading_space'}:
        from kronos.intraday.discovery import DiscoveryError
        with pytest.raises(DiscoveryError, match='INTEGRITY_INVALID'):
            _lookup_bundle('CRUDE', invalid[case])
        return
    _, facts, mapping, run, _, bundle = _lookup_bundle('CRUDE', invalid[case],
        provenance=original.provenance + ((identity,) if case == 'provenance_only' else ()))
    monkeypatch.setattr(bindings, 'load', lambda **kw: pytest.fail('no authoritative exact-one lookup'))
    decision, = publisher.publish(run, (mapping,), facts=(facts,), bundles=(bundle,), newly_published=True)
    assert (decision.data['result'], decision.data['reasons']) == (
        'NOT_ESTABLISHED', ['MCX_CONTRACT_BINDING_INVALID'])
    assert decision.data['exact_contract'] is None and decision.data['roll_lineage'] is None
    assert decision.data['cycle'] is None and decision.data['roles'] == {}
    assert decision.data['target_manifest'] is None
    assert load_decision_source(native, decision, None)['failure'] == 'MCX_CONTRACT_BINDING_INVALID'
    assert native.load(decision.identity) == decision


@pytest.mark.parametrize('case', ['missing', 'corrupt_json', 'integrity', 'subject',
                                  'family', 'contract', 'expiry', 'snapshot'])
def test_binding_store_failures_propagate_before_native_run_closure(tmp_path, case):
    import json
    from kronos.instrument.active_derivative import ActiveDerivativeSelectionError
    publisher, native, bindings, _, facts, mapping, run, binding, bundle = _publication_fixture(tmp_path)
    path = bindings.path_for(binding.binding_identity)
    if case == 'missing':
        path.unlink()
    elif case == 'corrupt_json':
        path.write_bytes(b'{')
    else:
        raw = json.loads(path.read_bytes())
        if case == 'integrity': raw['integrity_identity'] = 'ACTIVE-DERIVATIVE-BINDING-ARTIFACT-' + '0' * 64
        if case == 'subject': raw['canonical_subject_id'] = 'MCX-SUBJECT-COPPER'
        if case == 'family': raw['provider_contract_family'] = 'COPPER'
        if case == 'contract': raw['active_binding']['derivative_contract_id'] = 'WRONG-CONTRACT'
        if case == 'expiry': raw['contract_expiry'] = '2026-10-01'
        if case == 'snapshot': raw['provider_snapshot_identity'] = 'WRONG-SNAPSHOT'
        path.write_text(json.dumps(raw))
    reason = 'ACTIVE_DERIVATIVE_BINDING_UNAVAILABLE' if case == 'missing' else 'ACTIVE_DERIVATIVE_BINDING_INTEGRITY_INVALID'
    with pytest.raises(ActiveDerivativeSelectionError, match=reason):
        publisher.publish(run, (mapping,), facts=(facts,), bundles=(bundle,), newly_published=True)
    assert not (native.root / 'runs' / (run.run_identity + '.json')).exists()
    assert native.bound_identity(mapping.semantic_evidence.evidence_identity) is None


@pytest.mark.parametrize('case', ['different_family', 'session', 'stale', 'artifact_provenance'])
def test_valid_stored_artifact_cannot_substitute_wrong_lineage(tmp_path, case):
    from dataclasses import replace
    from datetime import timedelta
    from kronos.instrument.active_derivative import active_derivative_binding_payload, _identity
    from kronos.instrument.active_derivative_persistence import ActiveDerivativeBindingStore
    publisher, native, _, _, _, _, _, binding, original = _publication_fixture(tmp_path)
    if case == 'artifact_provenance':
        _, facts, mapping, run, _, bundle = _lookup_bundle('CRUDE',
            (binding.binding_identity,), provenance=('ISOLATED_NO_ARTIFACT_INTEGRITY',))
    else:
        other = _resolve(BOUNDARY - timedelta(days=1) if case == 'stale' else BOUNDARY).for_subject(
            'COPPER' if case == 'different_family' else 'CRUDE').binding
        if case == 'session':
            other = replace(other, domain008_session_identity='OTHER-DOMAIN008-SESSION',
                integrity_identity=_identity('ACTIVE-DERIVATIVE-BINDING-ARTIFACT',
                    {**active_derivative_binding_payload(other, include_integrity=False),
                     'domain008_session_identity': 'OTHER-DOMAIN008-SESSION'}))
        alternate = ActiveDerivativeBindingStore((tmp_path / 'alternate').resolve())
        alternate.retain(other)
        publisher.binding_store = alternate
        _, facts, mapping, run, _, bundle = _lookup_bundle('CRUDE',
            (other.binding_identity,), provenance=(other.integrity_identity,))
    decision, = publisher.publish(run, (mapping,), facts=(facts,), bundles=(bundle,), newly_published=True)
    assert decision.data['result'] == 'NOT_ESTABLISHED'
    assert decision.data['reasons'] == ['MCX_CONTRACT_BINDING_INVALID']
    assert decision.data['exact_contract'] is None and decision.data['roles'] == {}


def test_nse_publisher_never_uses_mcx_binding_store(tmp_path):
    from kronos.application.intraday_native_selection import NativePullbackPublication
    class NoMcxLookup:
        def load(self, **kw): pytest.fail('NSE must not enter MCX lookup branch')
    source, facts, mapping, run = source_fixture()
    native = NativeStructuralStore(tmp_path / 'native')
    decision, = NativePullbackPublication(native, clock=lambda: BOUNDARY,
        commissioned_at=BOUNDARY, binding_store=NoMcxLookup()).publish(
            run, (mapping,), facts=(facts,), newly_published=True)
    assert decision.data['result'] == 'PULLBACK'
    assert decision.data['exact_contract'] is None and decision.data['roll_lineage'] is None
    assert load_decision_source(native, decision, None) == source


@pytest.mark.parametrize('family', ['GOLDM', 'SILVERM', 'COPPER', 'CRUDE', 'NATGAS'])
def test_corrected_publisher_preserves_retained_historical_mcx_negative(tmp_path, family, monkeypatch):
    from kronos.intraday.native_pullback_decision import unavailable_source
    publisher, native, bindings, _, facts, mapping, run, _, bundle = _publication_fixture(tmp_path, family)
    historical = retain_decision(native, unavailable_source(mapping, run.results[0], run.run_identity,
        'MCX_CONTRACT_BINDING_INVALID'), created_at=BOUNDARY)
    retained = {p: p.read_bytes() for p in native.root.rglob('*') if p.is_file()}
    monkeypatch.setattr(bindings, 'load', lambda **kw: pytest.fail('historical decisions must not be reselected'))
    # Complete the existing run manifest, then compare every retained byte on retry.
    assert publisher.publish(run, (mapping,), facts=(facts,), bundles=(bundle,), newly_published=True) == (historical,)
    assert all(p.read_bytes() == raw for p, raw in retained.items())
    before = {p: p.read_bytes() for p in native.root.rglob('*') if p.is_file()}
    assert publisher.publish(run, (mapping,), facts=(facts,), bundles=(bundle,), newly_published=True) == (historical,)
    assert before == {p: p.read_bytes() for p in native.root.rglob('*') if p.is_file()}
    assert native.load(historical.identity) == historical
    assert historical.data['result'] == 'NOT_ESTABLISHED'
    assert historical.data['reasons'] == ['MCX_CONTRACT_BINDING_INVALID']
    assert historical.data['exact_contract'] is None and historical.data['roll_lineage'] is None
    assert historical.data['cycle'] is None and historical.data['roles'] == {}
    assert historical.data['target_manifest'] is None
