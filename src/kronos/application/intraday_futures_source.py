"""Lazy WO10 composition from retained master and existing DOMAIN owners.

No constructor/startup acquisition. Missing monetary authority is not replaced
with a budget or MCX multiplier inferred from Provider lot size.
"""
from kronos.intraday.wo10_futures_market import require_session
from kronos.provider.contracts.instrument_master import KITE_INSTRUMENT_MASTER_DATASET
from kronos.instrument.catalogue import load_canonical_instrument_catalogue
from kronos.instrument.runtime import create_provider_assertion
from kronos.browser.intraday_futures_control import domain008_session


class GovernedFuturesSource:
    def __init__(self, *, master_store, master_identity, binding_store, calendar, provider,
                 clock, catalogue=load_canonical_instrument_catalogue, economics_source=None, configuration_source=None, discovery_store=None, reconciliation=None):
        self.master_store,self.master_identity,self.binding_store=master_store,master_identity,binding_store
        self.calendar,self.provider,self.clock,self.catalogue=calendar,provider,clock,catalogue
        self.economics_source,self.configuration_source=economics_source,configuration_source
        self.discovery_store,self.reconciliation=discovery_store,reconciliation

    def authority(self,handoff):
        now=self.clock();subject=handoff.canonical_subject_identity
        mcx=subject.startswith('MCX-')
        binding=self.binding_store.load_current(canonical_subject_id=subject) if mcx else None
        if mcx and binding is None:raise ValueError('WO10_MCX_ACTIVE_AUTHORITY_REQUIRED')
        from kronos.intraday.wo09_experimental import ExperimentalNextWoHandoff
        discovery = None
        if type(handoff) is ExperimentalNextWoHandoff and self.discovery_store is not None:
            discovery = self.discovery_store.load_run(
                run_identity=handoff.readiness_document['assessment_document']['discovery_identity'])
            discovery.__post_init__()
            identities = [v for v in discovery.source_identities if v.startswith('PROVIDER-INSTRUMENT-SNAPSHOT-')
                and not v.startswith('PROVIDER-INSTRUMENT-SNAPSHOT-INTEGRITY-')]
            if len(identities) != 1:
                raise ValueError('WO10_COMPLETE_DAILY_MASTER_REQUIRED')
            identity = identities[0]
            if binding is not None and binding.provider_snapshot_identity != identity:
                raise ValueError('WO10_MCX_CONTRACT_LINEAGE_MISMATCH')
        else:
            identity=binding.provider_snapshot_identity if binding else self.master_identity()
        if not identity:raise ValueError('WO10_COMPLETE_DAILY_MASTER_REQUIRED')
        master=self.master_store.load(provider='KITE',dataset_identity=KITE_INSTRUMENT_MASTER_DATASET,snapshot_identity=identity)
        contract=None if binding is None else dict(name=binding.provider_contract_family,expiry=binding.contract_expiry.isoformat())
        session=domain008_session(self.calendar,subject,now,contract=contract)
        require_session(session,now,exchange='MCX' if mcx else 'NSE')
        underlying=None
        if discovery is not None and master.integrity_identity not in discovery.source_identities:
            raise ValueError('WO10_RETAINED_MASTER_BINDING_INVALID')
        if not mcx and discovery is not None:
            from kronos.intraday.wo10_reconciled_underlying import ReconciledNseUnderlying
            underlying=ReconciledNseUnderlying(self.reconciliation,discovery,subject)
            underlying.resolve(master,handoff,now)
        elif not mcx:
            catalogue=self.catalogue()
            end=max(w.closes_at for w in session.schedule.windows)
            assertions=tuple(create_provider_assertion(provider=r.provider,provider_symbol=r.trading_symbol,
                provider_instrument_token=r.provider_instrument_token,exchange=r.exchange,segment=r.segment,instrument_type=r.instrument_type,
                asserted_tick_size=r.tick_size,asserted_lot_size=r.lot_size,binding_source_identity=r.provider_record_identity,
                source_boundary=master.acquired_at,valid_through=end) for r in master.records if r.exchange=='NSE')
            underlying=catalogue.runtime_registry(provider_assertions=assertions,observed_at=now).lookup(subject)
        economics=None if self.economics_source is None else self.economics_source(handoff,binding)
        config=None if self.configuration_source is None else self.configuration_source(handoff)
        return dict(master=master,underlying=underlying,active_mcx=binding,economics=economics,configuration=config)

    def __call__(self,handoff,plan):
        try:
            authority=self.authority(handoff)
            # Full-quote lease is acquired lazily, only after exact plan construction.
            provider=self.provider()
        except RuntimeError as error:
            raise ValueError("WO10_CURRENT_MARKET_AUTHORITY_UNAVAILABLE") from error
        binding=authority['active_mcx']
        contract=None if binding is None else dict(name=binding.provider_contract_family,expiry=binding.contract_expiry.isoformat())
        return dict(**authority,provider=provider,authority_source=lambda:self.authority(handoff),
            session_source=lambda now:domain008_session(self.calendar,handoff.canonical_subject_identity,now,contract=contract))
