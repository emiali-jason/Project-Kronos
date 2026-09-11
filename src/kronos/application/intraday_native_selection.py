"""Prospective Native companion publication; never reconstruct historical runs."""
from kronos.intraday.native_pullback_policy import RULES, CHECKSUM, Reason
from kronos.intraday.native_pullback_decision import source_document,unavailable_source,retain_decision
from kronos.intraday.wo10_futures_contract import encoded,normalize,digest
from kronos.intraday.wo09_persistence import Wo09Store


class NativePullbackPublication:
    def __init__(self, store, *, clock, commissioned_at, binding_store=None):
        self.store,self.clock,self.commissioned_at,self.binding_store=store,clock,commissioned_at,binding_store

    def publish(self, run, mappings, *, facts=(), bundles=(), newly_published=False):
        # Runtime construction and historical restore never invoke selection.
        if not newly_published or run.analysis_boundary < self.commissioned_at:
            return ()
        run.__post_init__()
        source_facts={f.canonical_subject_identity:f for f in facts}
        source_bundles={b.bundle_identity:b for b in bundles}
        by_mapping={m.mapping_identity:m for m in mappings}
        policy=dict(rules=RULES,checksum=CHECKSUM,commissioned_at=normalize(self.commissioned_at))
        Wo09Store._retain(self.store.root/'policies'/(digest(policy)+'.json'),encoded(policy))
        decisions=[]
        for result in run.results:
            mapping=by_mapping.get(result.source_mapping_identity)
            if mapping is None:
                # No semantic/WO09 intake authority exists for unmapped members.
                continue
            existing=self.store.bound_identity(result.semantic_evidence_identity)
            if existing is not None:
                retained=self.store.load(existing)
                if retained.data['analysis_cycle']!=run.run_identity:raise ValueError('STRUCTURAL_SOURCE_BINDING_INVALID')
                decisions.append(retained);continue
            try:
                f=source_facts.get(result.canonical_subject_identity)
                if f is None:raise ValueError(Reason.INTEGRITY.value)
                bundle=source_bundles.get(f.discovery_bundle_identity)
                binding=None
                if result.canonical_subject_identity.startswith('MCX-'):
                    ids=[] if bundle is None else [x for x in bundle.source_identities if x.startswith('ACTIVE-DERIVATIVE-BINDING-ARTIFACT-')]
                    if len(ids)!=1 or self.binding_store is None:raise ValueError(Reason.MCX.value)
                    binding=self.binding_store.load(binding_identity=ids[0])
                source=source_document(f,mapping,result,run.run_identity,mcx_binding=binding,machine_bundle=bundle)
            except (ValueError,AttributeError,TypeError,OSError):
                reason=Reason.MCX.value if result.canonical_subject_identity.startswith('MCX-') else Reason.INTEGRITY.value
                source=unavailable_source(mapping,result,run.run_identity,reason)
            decisions.append(retain_decision(self.store,source,created_at=self.clock()))
        # A run manifest closes the exact companion population before publication.
        manifest=dict(run_identity=run.run_identity,policy_checksum=CHECKSUM,commissioned_at=normalize(self.commissioned_at),
            selections=[d.identity for d in decisions],result_identities=[d.data['probable_result_identity'] for d in decisions])
        Wo09Store._retain(self.store.root/'runs'/(run.run_identity+'.json'),encoded(manifest))
        return tuple(decisions)
