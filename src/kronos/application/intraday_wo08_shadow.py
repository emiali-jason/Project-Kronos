"""Option A frozen research handoff and counted bounded collector.

No Provider object, callback or lease enters a handoff. Capture is prospective,
post-Probables, research-only; no automatic replay, outcome acquisition or TTL.
"""
from collections import deque
from dataclasses import dataclass
from hashlib import sha256
import json
from threading import Condition, Lock, Thread

from kronos.intraday.wo08_shadow_contract import Wo08ShadowHandoff, canonical, digest, record
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator

MAX_ITEMS = 256
MAX_BYTES = 64 * 1024 * 1024
MAX_HANDOFF_BYTES = 8 * 1024 * 1024


def retained_run_ids(store):
    """Pre-invocation immutable identity inventory; never an arbitrary clock.

    The exact published run identity after return determines prospective versus
    already-retained capture. This is metadata only and uses no Provider access.
    """
    return frozenset(p.stem for p in (store.root / 'probables-v2' / 'runs').glob('*.json'))


def freeze_publication(*, run, mapping, execution, operation, native_publication,
                       assessments, newly_published, published_at, reconciliation, replay_envelope):
    from kronos.intraday.probables_v2_persistence import _to_wire
    replay_envelope.__post_init__()
    from kronos.intraday.probables_v2_persistence import _artifact_bytes
    replay_digest = sha256(_artifact_bytes(replay_envelope)).hexdigest()
    run.__post_init__()
    execution.run.__post_init__()
    if (len(run.results) != 98 or run.source_discovery_run_identity != execution.run.run_identity
            or run.analysis_boundary != execution.run.observation_boundary
            or run.universe_identity != execution.run.universe_identity
            or run.reconciliation_identity != reconciliation.publication_identity):
        raise ValueError('WO08_PUBLICATION_LINEAGE_INVALID')
    mappings = {m.mapping_identity: m for m in mapping.member_evidence}
    facts = {f.canonical_subject_identity: f for f in execution.probables_v2_facts}
    members = {m.universe_member_identity: m for m in reconciliation.members}
    if native_publication is None:
        raise ValueError('WO08_NATIVE_COMPANION_UNAVAILABLE')
    companion = json.loads((native_publication.store.root / 'runs' / (run.run_identity + '.json')).read_bytes())
    expected_results = [r.result_identity for r in run.results if r.source_mapping_identity is not None]
    if (companion['run_identity'] != run.run_identity or companion['result_identities'] != expected_results
            or len(companion['selections']) != len(expected_results)):
        raise ValueError('WO08_NATIVE_COMPANION_INCOMPLETE')
    run_id = 'WO08-RUN-' + digest(dict(run=run.run_identity, operation=operation))
    samples, supplements, excluded = [], [], {}
    for result in run.results:
        result.__post_init__()
        m = mappings.get(result.source_mapping_identity)
        f = facts.get(result.canonical_subject_identity)
        if m is None:
            # Schema has no unknown phase/calendar/selection. Preserve the
            # result in the 98 denominator with its truthful exclusion reason.
            excluded[result.result_identity] = '|'.join(str(x) for x in result.reasons)
            continue
        n = None
        if m is not None:
            m.__post_init__()
            if native_publication is None:
                raise ValueError('WO08_NATIVE_COMPANION_UNAVAILABLE')
            identity = native_publication.store.bound_identity(result.semantic_evidence_identity)
            if identity is None:
                raise ValueError('WO08_NATIVE_COMPANION_UNAVAILABLE')
            n = native_publication.store.load(identity)
            if identity not in companion['selections']:
                raise ValueError('WO08_NATIVE_COMPANION_LINEAGE_INVALID')
            if n.data['analysis_cycle'] != run.run_identity or n.data['probable_result_identity'] != result.result_identity:
                raise ValueError('WO08_NATIVE_COMPANION_LINEAGE_INVALID')
        if f is not None:
            f.__post_init__()
        member = members[result.universe_member_identity]
        family = member.sponsor_label
        mcx = result.canonical_subject_identity.startswith('MCX-')
        state = 'NOT_MCX'
        contract, binding = None, None
        exclusions = [str(x) for x in result.reasons]
        if mcx:
            state = 'MCX_BINDING_UNAVAILABLE'
            if n is not None:
                contract, binding = n.data['exact_contract'], n.data['roll_lineage']
                # 02A does not repair the separately governed 02B producer issue.
                state = ('MCX_BINDING_INVALID' if 'MCX_CONTRACT_BINDING_INVALID' in n.data['reasons']
                         else 'MCX_BINDING_VALID' if contract and binding else 'MCX_BINDING_UNAVAILABLE')
            exclusions.extend(['MCX_POSITIVE_METHOD_RESEARCH_NOT_COMMISSIONED', 'MCX_I3_I5_UNCOMMISSIONED'])
            if family == 'NATGAS':
                exclusions.append('NATGAS_COMMISSIONING_HELD')
        candles = []
        if m is not None:
            for item in m.completed_evidence.selected_candles:
                c = item.candle
                c.__post_init__()
                candles.append(dict(timeframe=c.timeframe.value, candle_id=c.candle_identity,
                    integrity=c.integrity_identity, start=c.candle_start.isoformat(), end=c.candle_end.isoformat(),
                    completion=c.completion_state, source_identity=c.provider_source_identity,
                    # Retrieval time does not prove official publication/revision availability.
                    kronos_acquired_at=None, provider_observed_at=None,
                    source_revision_id=None, kronos_published_at=None, oi=None))
        # Retain typed wire snapshots and complete raw/governed candle/fact content.
        raw = dict(run_reference=dict(identity=run.run_identity, integrity=run.integrity_identity,
                   universe=run.universe_identity, reconciliation=run.reconciliation_identity), result=_to_wire(result),
                   mapping=None if m is None else _to_wire(m),
                   facts_reference=None if f is None else dict(identity=f.facts_identity,
                       replay_envelope=replay_envelope.envelope_identity),
                   assessments=[] if assessments is None else [_to_wire(a) for a in assessments.observations
                       if a.canonical_subject_identity == result.canonical_subject_identity],
                   native=None if n is None else n.data,
                   discovery_reference=dict(identity=execution.run.run_identity, session=execution.run.market_session_identity), bundles=[_to_wire(b) for b in execution.bundles
                       if b.canonical_identity == result.canonical_subject_identity])
        supplement = canonical(raw)
        supplement_sha = sha256(supplement).hexdigest()
        sid = 'WO08-SAMPLE-' + digest(dict(run=run_id, result=result.result_identity))
        refs = [dict(kind='PROBABLES_REPLAY_ENVELOPE', identity=replay_envelope.envelope_identity,
                     integrity_sha256=replay_digest), dict(kind='PROBABLES_RESULT', identity=result.result_identity,
                     integrity_sha256=sha256(canonical(_to_wire(result))).hexdigest())]
        quality = 'PARTIAL' if mcx or m is None or f is None else 'COMPLETE'
        samples.append(record('T0', sample_id=sid, run_id=run_id, analysis_operation_id=operation,
            analysis_boundary=run.analysis_boundary.isoformat(), research_published_at=published_at.isoformat(),
            subject=result.canonical_subject_identity,
            market_family=('MCX_ENERGY' if family in {'CRUDE','NATGAS'} else 'MCX_METALS') if mcx else member.market_family.value,
            instrument_family=family, direction='UNKNOWN' if result.direction is None or str(result.direction)=='UNAVAILABLE' else str(result.direction),
            probables_state=result.state.value, discovery_id=run.source_discovery_run_identity,
            probables_run_id=run.run_identity, probables_member_id=result.result_identity,
            mapping_id=result.source_mapping_identity or 'MAPPING_UNAVAILABLE',
            phase=result.phase.value,
            session_id=result.market_session_identity,
            calendar_id=m.completed_evidence.calendar_identity if m else 'CALENDAR_UNAVAILABLE',
            calendar_version=m.completed_evidence.calendar_version if m else 'CALENDAR_UNAVAILABLE',
            completed_selection_id=result.completed_evidence_selection_identity or 'SELECTION_UNAVAILABLE',
            native_decision_id=None if n is None else n.identity,
            native_state='UNAVAILABLE' if n is None else n.data['result'],
            mcx_binding_class=state, exact_contract_id=contract, binding_id=binding,
            machine_fact_ids=[] if f is None else [f.facts_identity], candle_refs=candles,
            source_revision_status='SOURCE_REVISION_PROVENANCE_UNAVAILABLE', quality=quality,
            exclusion_reasons=exclusions, source_artifact_refs=refs,
            candle_supplement_identity='WO08-SUPPLEMENT-'+supplement_sha,
            candle_supplement_sha256=supplement_sha))
        supplements.append(supplement)
    manifest = record('RUN', manifest_id=run_id, analysis_operation_id=operation,
        probables_run_id=run.run_identity, analysis_boundary=run.analysis_boundary.isoformat(),
        run_integrity=run.integrity_identity, universe_identity=run.universe_identity, population_total=98,
        all_result_ids=[r.result_identity for r in run.results], selected_sample_ids=[s.identity for s in samples],
        excluded_result_reasons=excluded, sampling_policy_id='WO08_OPTION_A_COMPLETE_POPULATION_V1',
        sampling_seed=run.run_identity, inclusion_probabilities={r.result_identity:1 for r in run.results},
        capture_failures=[], recorded_at=published_at.isoformat())
    return Wo08ShadowHandoff(manifest, tuple(samples), tuple(supplements), newly_published)


@dataclass(frozen=True, slots=True)
class CaptureResult:
    identity: str
    state: str
    reason: str | None = None


class Wo08ShadowCollector:
    def __init__(self, store):
        self._initialize(store)

    def _initialize(self, store):
        self.unavailable_reason = None
        self.unavailable_error_type = None
        self.store = store
        self.maintenance_coordinator = None
        self._condition = Condition(Lock())
        self._queue = deque()
        self._bytes = 0
        self._worker = None
        self._closed = False
        self._results = {}
        self._counts = dict(eligible=0, attempted=0, admitted=0, not_admitted=0,
                            captured=0, failed=0, partial=0, excluded=0)

    def bind_maintenance_admission(self, coordinator):
        if type(coordinator) is not MaintenanceAdmissionCoordinator:
            raise ValueError('WO08_COORDINATOR_INVALID')
        with self._condition:
            if self.maintenance_coordinator is not None and self.maintenance_coordinator is not coordinator:
                raise ValueError('WO08_COORDINATOR_ALREADY_BOUND')
            self.maintenance_coordinator = coordinator

    def snapshot(self):
        with self._condition:
            return dict(counts=dict(self._counts), queued=len(self._queue), queued_bytes=self._bytes,
                        results=dict(self._results), closed=self._closed,
                        availability=('AVAILABLE' if self.unavailable_reason is None else 'UNAVAILABLE'),
                        unavailable_reason=self.unavailable_reason,
                        unavailable_error_type=self.unavailable_error_type)

    def incomplete(self, identity, reason, members=98):
        with self._condition:
            self._counts['failed'] += members
            value = CaptureResult(identity, 'SHADOW_CAPTURE_FAILED', reason)
            self._results[identity] = value
            return value

    def submit(self, handoff):
        handoff.__post_init__()
        identity = handoff.manifest.identity
        size = len(handoff.encoded())
        with self._condition:
            self._counts['eligible'] += len(handoff.samples)
            self._counts['attempted'] += len(handoff.samples)
            self._counts['excluded'] += len(handoff.manifest.data['excluded_result_reasons'])
        if not handoff.newly_published:
            return self._refuse(identity, 'ALREADY_PUBLISHED_NO_BACKFILL', len(handoff.samples))
        if size > MAX_HANDOFF_BYTES:
            return self._refuse(identity, 'HANDOFF_OVERSIZE', len(handoff.samples))
        coordinator = self.maintenance_coordinator
        if coordinator is None:
            return self._refuse(identity, 'ADMISSION_UNAVAILABLE', len(handoff.samples))
        ticket = coordinator.admit_root('WO08_SHADOW')
        if ticket is None:
            return self._refuse(identity, 'MAINTENANCE_FENCED', len(handoff.samples))
        accepted = False
        try:
            with self._condition:
                if self._closed:
                    reason = 'COLLECTOR_CLOSED'
                elif len(self._queue) >= MAX_ITEMS or self._bytes + size > MAX_BYTES:
                    reason = 'QUEUE_SATURATED'
                else:
                    # The one lazy worker is created only under lawful admission.
                    if self._worker is None:
                        worker = Thread(target=self._run, name='WO08_SHADOW', daemon=True)
                        worker.start()
                        self._worker = worker
                    self._queue.append((handoff, size, ticket))
                    self._bytes += size
                    self._counts['admitted'] += len(handoff.samples)
                    value = CaptureResult(identity, 'QUEUED')
                    self._results[identity] = value
                    accepted = True
                    self._condition.notify_all()
                    return value
            return self._refuse(identity, reason, len(handoff.samples))
        except Exception:
            return self.incomplete(identity, 'SCHEDULING_FAILED', len(handoff.samples))
        finally:
            # Never signal coordinator while collector/domain lock is held.
            if not accepted:
                ticket.release()

    def _refuse(self, identity, reason, members):
        with self._condition:
            self._counts['not_admitted'] += members
            value = CaptureResult(identity, 'SHADOW_CAPTURE_NOT_ADMITTED', reason)
            self._results[identity] = value
            return value

    def _run(self):
        while True:
            with self._condition:
                while not self._queue and not self._closed:
                    self._condition.wait()
                if not self._queue:
                    return
                handoff, size, ticket = self._queue.popleft()
                self._bytes -= size
                self._results[handoff.manifest.identity] = CaptureResult(handoff.manifest.identity, 'PROCESSING')
            try:
                with self._condition:
                    self._results[handoff.manifest.identity] = CaptureResult(handoff.manifest.identity, 'FINALIZING')
                self.store.retain_handoff(handoff)
                captured = sum(s.data['quality'] == 'COMPLETE' for s in handoff.samples)
                partial = len(handoff.samples) - captured
                state = ('SHADOW_CAPTURE_PARTIAL' if partial or handoff.manifest.data['excluded_result_reasons']
                         else 'SHADOW_CAPTURED')
                with self._condition:
                    self._counts['captured'] += captured
                    self._counts['partial'] += partial
                    self._results[handoff.manifest.identity] = CaptureResult(handoff.manifest.identity, state)
            except Exception:
                self.incomplete(handoff.manifest.identity, 'WORKER_OR_DURABILITY_FAILED', len(handoff.samples))
            finally:
                ticket.release()
                with self._condition:
                    self._condition.notify_all()

    def close(self, timeout=10):
        with self._condition:
            self._closed = True
            worker = self._worker
            self._condition.notify_all()
        if worker is not None:
            worker.join(timeout)
            return not worker.is_alive()
        return True


class UnavailableWo08ShadowCollector(Wo08ShadowCollector):
    """Inert, observable research failure; no store fallback or constructor retry."""

    def __init__(self, error_type):
        # Initialize in-memory status without calling the failed constructor again.
        self._initialize(None)
        self.unavailable_reason = 'WO08_CONSTRUCTION_UNAVAILABLE'
        self.unavailable_error_type = error_type

    def submit(self, handoff):
        handoff.__post_init__()
        with self._condition:
            self._counts['eligible'] += len(handoff.samples)
            self._counts['attempted'] += len(handoff.samples)
            self._counts['excluded'] += len(handoff.manifest.data['excluded_result_reasons'])
        return self._refuse(handoff.manifest.identity, self.unavailable_reason,
                            len(handoff.samples))


def compose_wo08_shadow(root):
    """Canonical opt-in only; construction/binding never acquires research evidence."""
    from kronos.intraday.wo08_shadow_persistence import Wo08ShadowStore
    try:
        return Wo08ShadowCollector(Wo08ShadowStore(root))
    except Exception as error:
        # Research construction cannot invalidate unrelated operational startup.
        # No retry, alternate root, raw exception text, disk record or worker.
        return UnavailableWo08ShadowCollector(type(error).__name__)
