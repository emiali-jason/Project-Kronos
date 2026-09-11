"""WO-06H inert-by-default research collector. Explicit acceptance is separate.

Research capture follows production publication and cannot change admission.
No scheduler, authentication, Review, execution, export or purge dependency.
"""
from dataclasses import replace
from datetime import timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from threading import RLock
import json
import os
import re

from kronos.intraday.live_shadow import (
    SCHEMA,COHORT_A,COHORT_B,NE,RESEARCH_INPUTS,ShadowError,artifact,key,
    instant,next_month,directional_move,
)
from kronos.intraday.live_shadow_persistence import ShadowStore
from kronos.intraday.live_shadow_features import classify,snapshot,DEFINITIONS
from kronos.intraday.live_shadow_quote import admission_pair,missing,native_context,capture
from kronos.intraday.population_measurement import identity
from kronos.intraday.runtime_identity import RuntimeManifest
from kronos.intraday.probables_v2 import _encode
from kronos.intraday.historical_semantic import GovernedHistoricalCandlePayload
from kronos.intraday.technical_context_research import native_binding,TF
from kronos.intraday.candles import expected_candle_boundaries
from kronos.market.schedule import MarketDaySchedule

REQUIRED={'WO_05A_TRUSTED_TIME_ADMISSION','WO_05B_OPERATION_ACCOUNTING',
          'INTRADAY_DISCOVERY_OPERATION','INTRADAY_V2_OPERATIONAL_CONTROL','WO_06H_LIVE_SHADOW'}


class IntradayLiveShadowService:
    def __init__(self,*,store:ShadowStore,clock,mcx_history_store=None,probables_store=None):
        from kronos.intraday.live_shadow_epochs import EpochStore,EpochView;self._epochs=EpochStore(store);self.store=EpochView(store,self._epochs);self.clock=clock;self._mcx_history_store=mcx_history_store;self._probables_store=probables_store;self._manifest=None;self._accepted=None
        self._lock=RLock();self._failure=None;self._last=None;self._restored_acceptance=None;self._restoration_failure=None
        self._summary=dict(cohort_a=0,cohort_b=0,expected_a=0,expected_b=0,missing_rows=0,
                           assessment_available=0,eod_available=0,classification_failures=0)
        self._window=None
        try:
            windows=self.store.all('window')
            if len(windows)>1:raise ShadowError('SHADOW_WINDOW_AMBIGUOUS')
            self._window=windows[0] if windows else None
            self._reconcile()
        except Exception:self._failure='SHADOW_RESTORATION_FAILED'

    def bind_runtime(self,manifest):
        if manifest is None:return
        if type(manifest) is not RuntimeManifest:raise ShadowError('SHADOW_RUNTIME_INVALID')
        replace(manifest);replace(manifest.startup)
        if self._manifest is not None and self._manifest!=manifest:raise ShadowError('SHADOW_RUNTIME_IMMUTABLE')
        self._manifest=manifest;self._restore_acceptance()

    def accept_runtime(self,*,expected_revision,request_identity):
        """Explicit future Sponsor acceptance only. No capture on acceptance/startup."""
        with self._lock:
            m=self._manifest
            if (m is None or m.startup.process_id!=os.getpid()
                or m.startup.source_state!='CLEAN_COMMIT'
                or m.startup.source_revision!=expected_revision
                or not re.fullmatch('[a-f0-9]{40}',expected_revision)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',request_identity)
                or not REQUIRED.issubset({c.identity for c in m.capabilities})
                or self._failure is not None):raise ShadowError('SHADOW_RUNTIME_ACCEPTANCE_REJECTED')
            replace(m);replace(m.startup);now=self.clock()
            if self._window is not None:
                initial={c['identity']:c for c in self._window.body['runtime_proof']['capabilities']}
                current={c['identity']:c for c in self._runtime_proof()['capabilities']}
                if initial.get('WO_06H_LIVE_SHADOW')!=current.get('WO_06H_LIVE_SHADOW'):
                    raise ShadowError('SHADOW_FROZEN_IMPLEMENTATION_CHANGED')
            if self._window is None:
                start=now.astimezone(ZoneInfo('Asia/Kolkata'))
                b=dict(authority='RESEARCH_ONLY',start=start.isoformat(),start_utc=now.astimezone(timezone.utc).isoformat(),end=next_month(start).isoformat(),
                    runtime_proof=self._runtime_proof(),
                    runtime=m.manifest_identity,request=request_identity,research_inputs=RESEARCH_INPUTS,
                    methodology='2.2.0',schema=SCHEMA,definitions=DEFINITIONS)
                window=artifact('window',key('window','INITIAL_ONE_MONTH'),b)
                self.store.retain(window)
                self._window=window
            if now<instant(self._window.body['start']):
                raise ShadowError('SHADOW_WINDOW_NOT_ACTIVE')
            aid=key('acceptance',self._window.key,m.manifest_identity)
            old=self.store.load('acceptance',aid)
            if old is None:
                self.store.retain(artifact('acceptance',aid,dict(authority='RESEARCH_ONLY',
                    window=self._window.key,runtime=m.manifest_identity,request=request_identity,
                    accepted_at=now.isoformat(),runtime_proof=self._runtime_proof())))
            self._accepted=m.manifest_identity
            return self.status()

    def _runtime_proof(self):
        m=self._manifest
        return dict(manifest=m.manifest_identity,pid=m.startup.process_id,revision=m.startup.source_revision,
            source_state=m.startup.source_state,startup=m.startup.startup_boundary_at.isoformat(),
            configuration=m.configuration_identity,capabilities=[dict(identity=c.identity,version=c.version,
                implementation_digest=c.implementation_digest) for c in m.capabilities])

    def _active(self,operation_start):
        if self._window is None or self._manifest is None or self._accepted!=self._manifest.manifest_identity:return False
        w=self._window.body;now=self.clock()
        return instant(w['start'])<=operation_start<=now<instant(w['end']) and self._epoch_current()

    def begin_operation(self,operation,started_at):
        if not self._active(started_at):return
        try:
            self.store.retain(artifact('operation',key('operation',self._window.key,operation),
                dict(authority='RESEARCH_ONLY',window=self._window.key,operation=operation,
                    started_at=started_at.isoformat(),runtime=self._manifest.manifest_identity)))
        except Exception:self._failure='SHADOW_OPERATION_JOURNAL_INCOMPLETE'

    def _receipt(self,operation,run,batch,disposition):
        self.store.retain(artifact('receipt',key('receipt',self._window.key,operation),
            dict(authority='RESEARCH_ONLY',window=self._window.key,operation=operation,
                run=run,batch=batch,disposition=disposition)))

    def capture_published(self,run,mappings,assessment,*,facts,source,operation,operation_start,newly_published):
        """Bounded failure stays research-only; publication has already succeeded."""
        with self._lock:
            if not self._active(operation_start):
                if (self._window is not None and self._accepted is not None
                    and self.store.load('operation',key('operation',self._window.key,operation)) is not None):
                    try:
                        self._receipt(operation,run.run_identity,None,'OUTSIDE_CAPTURE_WINDOW')
                        self._reconcile()
                    except Exception:self._failure='SHADOW_RECONCILIATION_FAILED'
                return
            try:
                self._capture(run,mappings,assessment,facts,source,operation,newly_published)
            except Exception:self._failure='SHADOW_CAPTURE_INCOMPLETE'
            try:self._reconcile()
            except Exception:self._failure='SHADOW_RECONCILIATION_FAILED'

    def _capture(self,run,mappings,assessment,facts,source,operation,newly_published):
        batch_id=key('batch',self._window.key,run.run_identity)
        old=self.store.load('batch',batch_id)
        # A historical replay cannot start a prospective population or acquire quotes.
        if not newly_published and old is None:
            self._receipt(operation,run.run_identity,None,'HISTORICAL_REPLAY_NO_CAPTURE');return
        fact_by_subject={f.canonical_subject_identity:f for f in facts}
        if len(fact_by_subject)!=len(facts):raise ShadowError('SHADOW_FACT_DUPLICATE')
        selected,failures=classify(run,mappings,assessment,{s:f.previous_session_facts.narrow_cpr for s,f in fact_by_subject.items()})
        expected={COHORT_A:[],COHORT_B:[]}
        for r,c in selected:expected[c].append(key('observation',self._window.key,run.run_identity,r.result_identity,c))
        for ids in expected.values():ids.sort()
        body=dict(authority='RESEARCH_ONLY',window=self._window.key,run=run.run_identity,
            run_integrity=run.integrity_identity,operation=operation,boundary=run.analysis_boundary.isoformat(),recorded_at=self.clock().isoformat(),
            expected=expected,classification_failures=sorted(failures))
        if old is not None:
            # Replays may use another request identity; original operation remains immutable.
            body['operation']=old.body['operation'];body['recorded_at']=old.body['recorded_at']
        self.store.retain(artifact('batch',batch_id,body))
        self._receipt(operation,run.run_identity,batch_id,'POPULATION_RECORDED')
        by_mapping={m.mapping_identity:m for m in mappings}
        pairs={} if assessment is None else {a.admission_identity:a for a in assessment.observations}
        for result,cohort in selected:
            oid=key('observation',self._window.key,run.run_identity,result.result_identity,cohort)
            if self.store.load('observation',oid) is not None:continue
            try:
                m=by_mapping[result.source_mapping_identity];f=fact_by_subject.get(result.canonical_subject_identity)
                now=self.clock()
                iid=key('intent',oid)
                fresh=self.store.retain(artifact('intent',iid,dict(authority='RESEARCH_ONLY',
                    observation=oid,window=self._window.key,run=run.run_identity,result=result.result_identity,
                    cohort=cohort,operation=operation,requested_at=now.isoformat())),claim=True)
                native=dict(state=NE,contract=None,binding=None)
                retained={}
                try:
                    _,native=native_context(source,result,run.analysis_boundary)
                    if native['state']=='AVAILABLE' and source._mcx_history_store is not None:
                        for c in source._mcx_history_store.load_contract(canonical_subject_identity=result.canonical_subject_identity,
                                canonical_contract_identity=native['contract']):
                            k=(c.canonical_subject_identity,c.source_operation_identity,c.timeframe,c.candle_start,c.candle_end)
                            retained.setdefault(k,[]).append(c)
                except Exception:pass
                features,_=snapshot(f,m,retained)
                if cohort==COHORT_A:pair=admission_pair(pairs.get(result.result_identity))
                elif fresh and newly_published and self.clock()<instant(self._window.body['end']):
                    pair=capture(source,result,operation=operation,boundary=run.analysis_boundary,clock=self.clock)
                else:pair=missing('WO06H_COHORT_B_RESEARCH_QUOTE','WINDOW_CLOSED_NO_QUOTE' if self.clock()>=instant(self._window.body['end']) else 'PRIOR_REQUEST_UNFINISHED_NO_REQUOTE')
                schedule=None if f is None else f.current_schedule
                schedule_doc=None if schedule is None else json.loads(_encode(schedule))
                b=dict(authority='RESEARCH_ONLY',window=self._window.key,run=run.run_identity,
                    result=result.result_identity,mapping=m.mapping_identity,source_integrity=m.integrity_identity,
                    subject=result.canonical_subject_identity,native=native,
                    session=m.market_session_identity,schedule=schedule_doc,
                    phase=result.phase.value,direction=result.direction.value,methodology=run.methodology.methodology_version,
                    boundary=run.analysis_boundary.isoformat(),captured_at=self.clock().isoformat(),
                    runtime=self._manifest.manifest_identity,cohort=cohort,assessment=pair,features=features,
                    grouping=identity('WO06H-SUBJECT-SESSION-', [result.canonical_subject_identity,m.market_session_identity]),
                    baseline_state=result.state.value,narrow=m.semantic_evidence.narrow_cpr_qualified,
                    cpr_source=m.semantic_evidence.narrow_cpr_fact_identity,intent=iid)
                self.store.retain(artifact('observation',oid,b));self._last=b['captured_at']
            except Exception:self._failure='SHADOW_MEMBER_INCOMPLETE'

    def complete_eod(self,observation,*,schedule,candle,retained=None):
        """Explicit retained-evidence completion; no acquisition or autonomous scheduler.

        Terminal completed native 5M close is EOD observation, never Assessment Price.
        Missing/invalid evidence leaves outcome absent and denominator unchanged.
        """
        with self._lock:
            if self._accepted is None:raise ShadowError('SHADOW_RUNTIME_NOT_ACCEPTED')
            row=self.store.load('observation',observation)
            if row is None:raise ShadowError('SHADOW_OBSERVATION_NOT_FOUND')
            b=row.body;now=self.clock()
            try:
                if type(schedule) is not MarketDaySchedule or type(candle) is not GovernedHistoricalCandlePayload:raise ValueError
                replace(schedule);replace(candle)
                if json.loads(_encode(schedule))!=b['schedule']:raise ValueError
                terminal=expected_candle_boundaries(schedule,TF.FIVE_MINUTES)[-1]
                if (candle.canonical_subject_identity!=b['subject'] or candle.market_session_identity!=b['session']
                    or candle.timeframe is not TF.FIVE_MINUTES or candle.candle_start!=terminal.start
                    or candle.candle_end!=terminal.end or candle.candle_end>now
                    or candle.observation_boundary>now or (b['assessment']['time'] is not None
                        and instant(b['assessment']['time'])>candle.candle_end)):raise ValueError
                if b['subject'].startswith('MCX-'):
                    n=native_binding((candle,),retained or {})
                    if n['state']!='AVAILABLE' or n['contract']!=b['native']['contract']:raise ValueError
                else:n=dict(state='NOT_APPLICABLE',contract=None,binding=None)
                if candle.close<=0:raise ValueError
                move,state=directional_move(b['direction'],b['assessment']['price'],str(candle.close))
                oid=key('outcome',observation)
                core=dict(authority='RESEARCH_ONLY',observation=observation,window=b['window'],subject=b['subject'],
                    session=b['session'],native=b['native'],eod_native=n,price=str(candle.close),time=candle.candle_end.isoformat(),
                    source=candle.candle_identity,source_integrity=candle.integrity_identity,
                    assessment_integrity=b['assessment']['integrity'],move_pct=move,state=state,
                    runtime=self._manifest.manifest_identity)
                value=artifact('outcome',oid,core)
                old=self.store.load('outcome',oid)
                if old is not None:
                    core['runtime']=old.body['runtime'];value=artifact('outcome',oid,core)
                self.store.retain(value);self._reconcile();return value
            except Exception:raise ShadowError('SHADOW_EOD_BINDING_OR_CONFLICT') from None

    def complete_from_envelope(self,observation,*,envelope):
        # Exact caller-selected retained artifact; no newest-file or live-data fallback.
        from kronos.intraday.probables_v2_diagnostics import ProbablesV2ReplayEnvelope
        if type(envelope) is not ProbablesV2ReplayEnvelope:raise ShadowError('SHADOW_EOD_SOURCE_INVALID')
        replace(envelope)
        row=self.store.load('observation',observation)
        if row is None:raise ShadowError('SHADOW_OBSERVATION_NOT_FOUND')
        matches=[f for f in envelope.probables_v2_facts if f.canonical_subject_identity==row.body['subject']]
        if len(matches)!=1:raise ShadowError('SHADOW_EOD_SOURCE_NOT_RETAINED')
        f=matches[0];replace(f)
        if not f.current_five_minute:raise ShadowError('SHADOW_EOD_SOURCE_NOT_RETAINED')
        retained={}
        if row.body['subject'].startswith('MCX-') and self._mcx_history_store is not None:
            for c in self._mcx_history_store.load_contract(canonical_subject_identity=row.body['subject'],canonical_contract_identity=row.body['native']['contract']):
                retained.setdefault((c.canonical_subject_identity,c.source_operation_identity,c.timeframe,c.candle_start,c.candle_end),[]).append(c)
        return self.complete_eod(observation,schedule=f.current_schedule,candle=f.current_five_minute[-1],retained=retained)

    def _reconcile(self):
        obs=self.store.all('observation');batches=self.store.all('batch');outcomes=self.store.all('outcome')
        operations=self.store.all('operation');receipts=self.store.all('receipt')
        receipt_ops={a.body['operation'] for a in receipts}
        incomplete_operations=sum(a.body['operation'] not in receipt_ops for a in operations)
        for receipt in receipts:
            if receipt.body['batch'] is not None and self.store.load('batch',receipt.body['batch']) is None:
                raise ShadowError('SHADOW_RECEIPT_BATCH_MISSING')
        expected={c:set() for c in (COHORT_A,COHORT_B)};classified=0
        for batch in batches:
            if self._window is None or batch.body['window']!=self._window.key:raise ShadowError('SHADOW_WINDOW_MISMATCH')
            for c in expected:
                ids=batch.body['expected'][c]
                if expected[c].intersection(ids):raise ShadowError('SHADOW_DUPLICATE_OBSERVATION')
                expected[c].update(ids)
            classified+=len(batch.body['classification_failures'])
        if expected[COHORT_A]&expected[COHORT_B]:raise ShadowError('SHADOW_COHORT_OVERLAP')
        original_pairs={}
        seen=set();counts={COHORT_A:0,COHORT_B:0};available=0
        for a in obs:
            b=a.body
            if a.key not in expected[b['cohort']] or b['window']!=self._window.key:raise ShadowError('SHADOW_UNEXPECTED_OBSERVATION')
            if b['features']['definitions']!=self._window.body['definitions']:raise ShadowError('SHADOW_DEFINITION_CHANGED')
            if b['features']['identity']!=identity('WO06H-FEATURE-',{k:v for k,v in b['features'].items() if k!='identity'}):raise ShadowError('SHADOW_FEATURE_INTEGRITY_INVALID')
            if b['cohort']==COHORT_A and self._probables_store is not None:
                if b['run'] not in original_pairs:
                    companion=self._probables_store.load_assessment_observations(b['run'])
                    original_pairs[b['run']]={} if companion is None else {x.admission_identity:x for x in companion.observations}
                if b['assessment']!=admission_pair(original_pairs[b['run']].get(b['result'])):
                    raise ShadowError('SHADOW_ADMISSION_PRICE_BINDING_INVALID')
            seen.add(a.key);counts[b['cohort']]+=1;available+=b['assessment']['state']=='AVAILABLE'
        for outcome in outcomes:
            b=outcome.body
            if b['observation'] not in seen:raise ShadowError('SHADOW_ORPHAN_OUTCOME')
            row=self.store.load('observation',b['observation']).body
            if (b['window']!=row['window'] or b['subject']!=row['subject'] or b['session']!=row['session']
                or b['native']!=row['native'] or b['assessment_integrity']!=row['assessment']['integrity']
                or (b['move_pct'],b['state'])!=directional_move(row['direction'],row['assessment']['price'],b['price'])):
                raise ShadowError('SHADOW_OUTCOME_INTEGRITY_INVALID')
        self._summary=dict(cohort_a=counts[COHORT_A],cohort_b=counts[COHORT_B],expected_a=len(expected[COHORT_A]),
            expected_b=len(expected[COHORT_B]),missing_rows=len(set.union(*expected.values())-seen),
            assessment_available=available,eod_available=len(outcomes),classification_failures=classified,
            observed_operations=len(operations),incomplete_operations=incomplete_operations)
        if obs:self._last=max((a.body['captured_at'] for a in obs),key=instant)

    def status(self):
        with self._lock:
            epochs = self.epoch_status()
            accepted = self._accepted is not None and epochs['epoch_failure'] is None and self._epoch_current()
            return dict(enabled=accepted and self._active(self.clock()), runtime_accepted=accepted,
                acceptance_disposition=('EXISTING_ACCEPTANCE_RESTORED' if self._restored_acceptance else 'NEW_ACCEPTANCE_GRANTED') if accepted else 'NOT_ACCEPTED',
                acceptance_identity=self._restored_acceptance or (key('acceptance',self._window.key,self._accepted) if accepted else None),
                window=None if self._window is None else dict(identity=self._window.key,start=self._window.body['start'],end=self._window.body['end']),
                schema=SCHEMA,runtime_proof=None if self._manifest is None else self._runtime_proof(),counts=dict(self._summary),last_capture=self._last,
                failure=self._failure or epochs['epoch_failure'] or (self._restoration_failure if not accepted else None),
                eod_scheduling_authority='EXPLICIT_RETAINED_EVIDENCE_ONLY',production_authority='NONE',**epochs)

    def monthly_ledger(self,month):
        """Temporary derived working projection; no final Excel or filesystem write."""
        if not re.fullmatch(r'\d{4}-\d{2}',month):raise ShadowError('SHADOW_MONTH_INVALID')
        self._reconcile();rows=[];outcomes={a.body['observation']:a.body for a in self.store.all('outcome')}
        batches=[a for a in self.store.all('batch') if instant(a.body['recorded_at']).astimezone(ZoneInfo('Asia/Kolkata')).strftime('%Y-%m')==month]
        expected={c:{k for a in batches for k in a.body['expected'][c]} for c in (COHORT_A,COHORT_B)}
        for a in self.store.all('observation'):
            b=a.body
            if a.key not in expected[b['cohort']]:continue
            o=outcomes.get(a.key,{})
            rows.append(dict(observation=a.key,security=b['subject'],cohort=b['cohort'],phase=b['phase'],direction=b['direction'],
                assessment_price=b['assessment']['price'],assessment_time=b['assessment']['time'],
                assessment_state=b['assessment']['state'],eod_price=o.get('price'),eod_time=o.get('time'),
                directional_move_pct=o.get('move_pct'),outcome=o.get('state',NE),features=b['features']['values'],feature_availability=b['features']['availability'],
                group=b['grouping']))
        rows.sort(key=lambda r:(r['security'],r['assessment_time'] or '',r['observation']))
        month_counts=dict(expected_a=len(expected[COHORT_A]),expected_b=len(expected[COHORT_B]),
            cohort_a=sum(r['cohort']==COHORT_A for r in rows),cohort_b=sum(r['cohort']==COHORT_B for r in rows),
            missing_rows=len(set.union(*expected.values()))-len(rows),
            assessment_available=sum(r['assessment_state']=='AVAILABLE' for r in rows),
            eod_available=sum(r['eod_price'] is not None for r in rows),
            classification_failures=sum(len(a.body['classification_failures']) for a in batches))
        return dict(authority='DERIVED_RESEARCH_PROJECTION',month=month,window=None if self._window is None else self._window.key,
            rows=rows,reconciliation=month_counts,window_reconciliation=dict(self._summary),raw_observations=len(rows),
            subject_session_groups=len({r['group'] for r in rows}),predictive_value=NE,final_excel=False,
            visible_columns=['security','cohort','phase','direction','assessment_price','assessment_time','assessment_state','eod_price','eod_time','directional_move_pct','outcome','features','feature_availability'],
            retention='TEMPORARY_CURRENT_MONTH_PLUS_5_DAYS',purge='NOT_IMPLEMENTED')


    def _restore_acceptance(self):
        """Bind retained authority to this process, without creating any artifact.

        Kept outside the frozen research functions: compatible process/revision
        changes must not change the accepted calculation capability identity.
        """
        with self._lock:
            if self._accepted is not None:
                return
            try:
                if self._failure is not None:
                    return
                if self._epochs.pointer() is not None:
                    from kronos.application.intraday_shadow_epochs import restore_epoch
                    restore_epoch(self)
                    return
                windows = self.store.all('window')
                acceptances = self.store.all('acceptance')
                if not windows and not acceptances:
                    return  # Fresh installation has no authority to restore.
                if len(windows) != 1 or len(acceptances) != 1:
                    raise ShadowError('SHADOW_RESTORATION_AUTHORITY_MISSING_OR_AMBIGUOUS')
                window, acceptance = windows[0], acceptances[0]
                if self._window is None or window.payload != self._window.payload:
                    raise ShadowError('SHADOW_RESTORATION_WINDOW_CHANGED')
                w, a = window.body, acceptance.body
                if (window.key != key('window', 'INITIAL_ONE_MONTH')
                        or a['window'] != window.key
                        or acceptance.key != key('acceptance', window.key, a['runtime'])
                        or w['definitions'] != DEFINITIONS):
                    raise ShadowError('SHADOW_RESTORATION_BINDING_INVALID')
                initial = self._validate_acceptance_proof(w['runtime_proof'], w['runtime'])
                accepted = self._validate_acceptance_proof(a['runtime_proof'], a['runtime'])
                m = self._manifest
                replace(m); replace(m.startup)
                if (m.startup.process_id != os.getpid()
                        or m.startup.source_state != 'CLEAN_COMMIT'
                        or not REQUIRED.issubset({c.identity for c in m.capabilities})):
                    raise ShadowError('SHADOW_RESTORATION_RUNTIME_INVALID')
                current = self._validate_acceptance_proof(self._runtime_proof(), m.manifest_identity)
                # Revision/PID/manifest legitimately change on restart. Exact
                # configuration and composed governed capabilities may not.
                for proof in (accepted, current):
                    if (proof['configuration'] != initial['configuration']
                            or proof['capabilities'] != initial['capabilities']):
                        raise ShadowError('SHADOW_RESTORATION_RUNTIME_INCOMPATIBLE')
                if (a['runtime'] == w['runtime'] and a['runtime_proof'] != w['runtime_proof']):
                    raise ShadowError('SHADOW_RESTORATION_BINDING_INVALID')
                start, end, at, now = instant(w['start']), instant(w['end']), instant(a['accepted_at']), self.clock()
                if (not re.fullmatch(''.join(('[A-Za-z0-9_-]', '{1,128}')), w['request'])
                        or not re.fullmatch(''.join(('[A-Za-z0-9_-]', '{1,128}')), a['request'])
                        or instant(w['runtime_proof']['startup']) > start
                        or instant(a['runtime_proof']['startup']) > at
                        or not start <= at < end
                        or instant(current['startup']) > now
                        or at > now):
                    raise ShadowError('SHADOW_RESTORATION_TIME_INVALID')
                if now < start:
                    raise ShadowError('SHADOW_RESTORATION_WINDOW_NOT_STARTED')
                if now >= end:
                    raise ShadowError('SHADOW_RESTORATION_WINDOW_EXPIRED')
                self._restored_acceptance = acceptance.key
                self._accepted = m.manifest_identity
                self._restoration_failure = None
            except ShadowError as error:
                self._restoration_failure = str(error)
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                self._restoration_failure = 'SHADOW_RESTORATION_AUTHORITY_INVALID'

    @staticmethod
    def _validate_acceptance_proof(proof, runtime):
        """Validate the existing persisted proof shape and composed declarations."""
        from kronos.intraday.runtime_identity import LoadedCapability
        if (type(proof) is not dict
                or set(proof) != {'manifest','pid','revision','source_state','startup','configuration','capabilities'}
                or proof['manifest'] != runtime
                or re.fullmatch(r'INTRADAY-RUNTIME-[a-f0-9]{64}', runtime) is None
                or type(proof['pid']) is not int or proof['pid'] < 1
                or proof['source_state'] != 'CLEAN_COMMIT'
                or re.fullmatch(''.join(('[a-f0-9]', '{40}')), proof['revision']) is None
                or re.fullmatch(r'INTRADAY-LAUNCHER-CONFIG-[a-f0-9]{64}', proof['configuration']) is None
                or type(proof['capabilities']) is not list):
            raise ShadowError('SHADOW_RESTORATION_PROOF_INVALID')
        instant(proof['startup'])
        declarations = [LoadedCapability(**c) for c in proof['capabilities']]
        capabilities = {c.identity: c for c in declarations}
        if len(capabilities) != len(declarations) or not REQUIRED.issubset(capabilities):
            raise ShadowError('SHADOW_RESTORATION_CAPABILITY_INVALID')
        return dict(proof, capabilities=capabilities)


    def epoch_status(self):
        from kronos.application.intraday_shadow_epochs import epoch_status
        return epoch_status(self)


    def _epoch_current(self):
        from kronos.intraday.live_shadow_epochs import compatible
        try:
            if not self._epochs.managed():
                return True  # Preserve ordinary single-window initial acceptance.
            epoch = self._epochs.chain()[0]['body']
            return (self._window is not None and self._window.key == epoch['window']
                and self._manifest is not None and compatible(epoch['proof'], self._runtime_proof()))
        except (ValueError, OSError, KeyError, TypeError, IndexError):
            return False
