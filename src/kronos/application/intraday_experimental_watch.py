"""Selective experimental PAPER watches; ticks retain advisory hints only.

Sponsor IWO-03 and approved experimental 0.1.0 design. This owner has no
Provider acquisition, connection, completed-candle or readiness producer API.
"""
from __future__ import annotations

from dataclasses import asdict
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock, Thread, current_thread

from kronos.intraday.wo09_readiness import CriterionId, CriterionState, CurrentnessState, HardGate, artifact_bytes
from kronos.intraday.wo09_watch import WatchState, transition_watch
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import ProviderMarketTick

POLICY = "KRONOS-INTRADAY-WO09-EXPERIMENTAL-PAPER-READINESS"
VERSION = "0.1.0"
BINDING = "WO09_EXPERIMENTAL_WATCH_BINDING_V1"
HINT = "WO09_EXPERIMENTAL_ADVISORY_WAKE_HINT_V1"
_LOCKS = {}
_LOCKS_GUARD = RLock()


def is_experimental(readiness):
    from kronos.intraday.wo09_experimental import ExperimentalReadinessRecord
    return type(readiness) is ExperimentalReadinessRecord


def watch_eligible(readiness, *, at=None):
    if not is_experimental(readiness):
        return False
    readiness.__post_init__()
    if at is not None and readiness.first_five_document is not None:
        from kronos.intraday.wo10_futures_contract import fresh
        if not fresh(readiness.first_five_of_five_at, at, 300):
            return False
    outstanding = [c for c in readiness.criteria if c.state is CriterionState.OUTSTANDING]
    return (readiness.policy_identity == POLICY and readiness.policy_version == VERSION
        and readiness.authority == "EXPERIMENTAL_PAPER_ONLY"
        and readiness.currentness is CurrentnessState.CURRENT
        and readiness.hard_gate is HardGate.NONE and readiness.satisfied_count == 4
        and readiness.outstanding_count == 1 and len(outstanding) == 1
        and outstanding[0].criterion_id in {CriterionId.I2, CriterionId.I3}
        and sum(c.state is CriterionState.SATISFIED for c in readiness.criteria) == 4
        and not any(c.state is CriterionState.UNAVAILABLE for c in readiness.criteria)
        and readiness.direction in {"LONG", "SHORT"}
        and not readiness.canonical_subject_identity.endswith("NATGAS")
        and bool(readiness.opportunity_identity)
        and (readiness.market_family != "MCX" or bool(
            readiness.exact_mcx_contract_identity and readiness.exact_mcx_roll_lineage)))


def _document(schema, **data):
    material = dict(schema=schema, **data)
    digest = sha256(artifact_bytes(material)).hexdigest()
    return dict(material, identity=schema + "-" + digest, integrity=digest)


def _validate(document):
    data = dict(document)
    identity, integrity = data.pop("identity"), data.pop("integrity")
    expected = _document(**data)
    if document != expected or identity != expected["identity"] or integrity != expected["integrity"]:
        raise ValueError("WO09_EXPERIMENTAL_WATCH_INTEGRITY_INVALID")
    if document["schema"] not in {BINDING, HINT}:
        raise ValueError("WO09_EXPERIMENTAL_WATCH_SCHEMA_INVALID")
    return document


def _instrument(instrument):
    values = asdict(instrument)
    values["expiry"] = None if instrument.expiry is None else instrument.expiry.isoformat()
    values["tick_size"] = None if instrument.tick_size is None else str(instrument.tick_size)
    return json.loads(artifact_bytes(values))


class ExperimentalWatchStore:
    """Append-only binding and one coalesced hint for each exact generation."""
    def __init__(self, wo09_store):
        self.wo09 = wo09_store
        self.root = wo09_store.root / "experimental-watch"
        with _LOCKS_GUARD:
            self.lock = _LOCKS.setdefault(self.root.resolve(), RLock())

    def retain(self, document):
        _validate(document)
        kind = "binding" if document["schema"] == BINDING else "hint"
        # A hint is unique per binding, independent of tick arrival count.
        name = document["identity"] if kind == "binding" else document["binding_identity"]
        path = self.root / kind / f"{name}.json"
        with self.lock:
            if path.exists():
                prior = _validate(json.loads(path.read_text()))
                if kind == "hint":
                    return prior
            self.wo09._retain(path, artifact_bytes(document))
            if _validate(json.loads(path.read_text())) != document:
                raise ValueError("WO09_EXPERIMENTAL_WATCH_READBACK_FAILED")
        return document

    def watch_history(self):
        from kronos.intraday.wo09_persistence import _watch
        return tuple(_watch(json.loads(path.read_text()))
                     for path in sorted(self.wo09.watches.glob("*.json")))

    def validate_binding(self, binding):
        _validate(binding)
        r = self.wo09.load_readiness(binding['readiness_identity'])
        r.__post_init__()
        watches = self.wo09.load_watches(r.readiness_identity)
        watch = next((w for w in watches if w.watch_identity == binding['watch_identity']), None)
        if watch is None or not watch_eligible(r):
            raise ValueError('WO09_EXPERIMENTAL_WATCH_SOURCE_INVALID')
        expected = dict(readiness_integrity=r.integrity_identity, assessment_identity=r.wo08_identity,
            assessment_integrity=r.wo08_integrity, opportunity_identity=r.opportunity_identity,
            subject=r.canonical_subject_identity, direction=r.direction, session_identity=r.session_identity,
            generation=r.generation, exact_contract_identity=r.exact_mcx_contract_identity,
            exact_roll_lineage=r.exact_mcx_roll_lineage, method_identity=r.methodology_identity,
            method_version=r.methodology_version, method_checksum=r.methodology_checksum,
            missing_criterion=watch.criterion_id.value, source_lineage=list(r.machine_evidence_identities),
            source_fact_identity=watch.source_fact_identity, watch_started_at=watch.activated_at.isoformat(),
            currentness=CurrentnessState.CURRENT.value, hint_levels=_source_levels(r),
            authority='ADVISORY_ONLY_NO_PROVIDER_OR_READINESS_AUTHORITY')
        if (watch.policy_identity != r.policy_identity or watch.policy_version != r.policy_version
                or watch.canonical_subject_identity != r.canonical_subject_identity
                or watch.exact_contract_identity != r.exact_mcx_contract_identity
                or watch.source_fact_identity != r.wo08_identity
                or any(binding.get(k) != v for k,v in expected.items())
                or set(binding) != set(expected) | {'identity','integrity','schema','watch_identity',
                    'readiness_identity','instrument','expires_at'}
                or datetime.fromisoformat(binding['expires_at']) <= watch.activated_at):
            raise ValueError('WO09_EXPERIMENTAL_WATCH_SOURCE_INVALID')
        return binding

    def records(self, schema=None):
        result = tuple(_validate(json.loads(path.read_text()))
            for path in sorted(self.root.glob("*/*.json")))
        bindings = {d['identity']:self.validate_binding(d) for d in result if d['schema'] == BINDING}
        for hint in (d for d in result if d['schema'] == HINT):
            binding = bindings.get(hint.get('binding_identity'))
            if binding is None:
                raise ValueError('WO09_EXPERIMENTAL_HINT_BINDING_INVALID')
            expected = {k:binding[k] for k in ('watch_identity','opportunity_identity','assessment_identity',
                'generation','instrument','session_identity')}
            expected.update(state='ADVISORY_WAKE_HINT',message='Possible change — awaiting completed Analysis',
                authority='NO_CRITERION_COMPLETION_NO_READINESS_NO_AUTOMATIC_ACQUISITION')
            observed, received = datetime.fromisoformat(hint['observed_at']), datetime.fromisoformat(hint['received_at'])
            price = Decimal(hint['last_price'])
            threshold = binding['hint_levels'].get(binding['missing_criterion'])
            beyond = threshold is not None and (price > Decimal(threshold) if binding['direction']=='LONG'
                                                else price < Decimal(threshold))
            if (any(hint.get(k) != v for k,v in expected.items())
                    or observed.tzinfo is None or received.tzinfo is None or observed > received
                    or not datetime.fromisoformat(binding['watch_started_at']) < observed < datetime.fromisoformat(binding['expires_at'])
                    or not price.is_finite() or not beyond
                    or type(hint.get('connection_identity')) is not str or not hint['connection_identity']
                    or hint.get('source_sequence') is not None and (type(hint['source_sequence']) is not int or hint['source_sequence'] < 0)
                    or set(hint) != set(expected) | {'identity','integrity','schema','binding_identity',
                        'observed_at','received_at','last_price','connection_identity','source_sequence'}
                    or binding['missing_criterion']=='I3' and not (
                        Decimal(binding['hint_levels']['corridor_lower']) < price < Decimal(binding['hint_levels']['corridor_upper']))):
                raise ValueError('WO09_EXPERIMENTAL_HINT_BINDING_INVALID')
        return tuple(d for d in result if schema is None or d["schema"] == schema)


class IntradayExperimentalWatchCoordinator:
    owner_identity = "INTRADAY_WO09_EXPERIMENTAL_WATCH"

    def __init__(self, wo09, *, clock, current_binding):
        if not callable(clock) or not callable(current_binding):
            raise ValueError("WO09_EXPERIMENTAL_WATCH_CONFIGURATION_INVALID")
        self.wo09, self.clock, self.current_binding = wo09, clock, current_binding
        self.store = ExperimentalWatchStore(wo09.store)
        self._observations = {}

    def _current(self, binding, at):
        pointer = self.wo09.store.load_pointer(binding["subject"])
        return (datetime.fromisoformat(binding["watch_started_at"]) <= at
            < datetime.fromisoformat(binding["expires_at"])
            and pointer is not None and pointer.currentness is CurrentnessState.CURRENT
            and pointer.readiness_identity == binding["readiness_identity"]
            and pointer.readiness_integrity == binding["readiness_integrity"]
            and watch_eligible(self.wo09.store.load_readiness(binding["readiness_identity"]), at=at)
            and self.current_binding(binding) is True)

    def synchronize(self, readiness, requirements, *, session_expires_at, instrument):
        """Called after successful ordinary Analysis publication with owner bindings."""
        now = self.clock()
        self.restore(at=now, subject=readiness.canonical_subject_identity)
        if not watch_eligible(readiness, at=now):
            return ()
        if (type(instrument) is not InstrumentRecord or session_expires_at.tzinfo is None
                or now.tzinfo is None or session_expires_at <= now):
            raise ValueError("WO09_EXPERIMENTAL_WATCH_SESSION_BINDING_INVALID")
        # A source-proven hint frontier is optional. Its absence never prevents
        # retaining a selective watch, but cannot be filled from a tick.
        levels = _source_levels(readiness)
        with self.store.lock:
            watches = self.wo09.register_reassessment_watches(readiness, requirements, at=now)
            result = []
            for watch in watches:
                existing = next((d for d in self.store.records(BINDING)
                    if d["watch_identity"] == watch.watch_identity), None)
                if existing is not None:
                    # Session expiry and first activation cannot be refreshed.
                    if (existing["instrument"] != _instrument(instrument)
                            or existing["expires_at"] != session_expires_at.isoformat()):
                        raise ValueError("WO09_EXPERIMENTAL_WATCH_BINDING_CONFLICT")
                    if self._current(existing, now):
                        result.append(existing)
                    continue
                binding = _document(BINDING, watch_identity=watch.watch_identity,
                    readiness_identity=readiness.readiness_identity,
                    readiness_integrity=readiness.integrity_identity,
                    assessment_identity=readiness.wo08_identity,
                    assessment_integrity=readiness.wo08_integrity,
                    opportunity_identity=readiness.opportunity_identity,
                    subject=readiness.canonical_subject_identity, direction=readiness.direction,
                    session_identity=readiness.session_identity, generation=readiness.generation,
                    exact_contract_identity=readiness.exact_mcx_contract_identity,
                    exact_roll_lineage=readiness.exact_mcx_roll_lineage,
                    method_identity=readiness.methodology_identity,
                    method_version=readiness.methodology_version,
                    method_checksum=readiness.methodology_checksum,
                    missing_criterion=watch.criterion_id.value,
                    source_lineage=list(readiness.machine_evidence_identities),
                    source_fact_identity=watch.source_fact_identity,
                    watch_started_at=watch.activated_at.isoformat(),
                    expires_at=session_expires_at.isoformat(), instrument=_instrument(instrument),
                    currentness=CurrentnessState.CURRENT.value, hint_levels=levels,
                    authority="ADVISORY_ONLY_NO_PROVIDER_OR_READINESS_AUTHORITY")
                if not self._current(binding, now):
                    self.wo09.store.retain_watch(transition_watch(watch, WatchState.STALE, at=now))
                    continue
                result.append(self.store.retain(binding))
            return tuple(result)

    def restore(self, *, at=None, subject=None):
        """Inert restart validation; stale generations never regain authority."""
        now = self.clock() if at is None else at
        with self.store.lock:
            watches = {w.watch_identity: w for w in self.wo09.store.load_watches()}
            active = []
            for binding in self.store.records(BINDING):
                if subject is not None and binding['subject'] != subject:
                    continue
                watch = watches.get(binding["watch_identity"])
                if watch is None or watch.state is not WatchState.ACTIVE:
                    continue
                if self._current(binding, now):
                    active.append(binding)
                else:
                    self.wo09.store.retain_watch(transition_watch(watch, WatchState.STALE,
                        at=max(now, watch.last_transition_at)))
            active_ids = {b["identity"] for b in active}
            if subject is None:
                self._observations = {k:v for k,v in self._observations.items() if k in active_ids}
            return tuple(active)

    def on_tick(self, tick, *, binding_identity=None):
        if type(tick) is not ProviderMarketTick:
            raise ValueError("WO09_EXPERIMENTAL_PROVIDER_TICK_REQUIRED")
        tick.__post_init__()
        now = self.clock()
        with self.store.lock:
            hints = []
            for binding in self.restore(at=now):
                if binding_identity is not None and binding['identity'] != binding_identity:
                    continue
                if binding["instrument"] != _instrument(tick.instrument):
                    continue
                if (tick.recovered or not tick.session_continuous
                        or not tick.previous_interval_available or not tick.ordering_deterministic):
                    watch = next(w for w in self.wo09.store.load_watches()
                                 if w.watch_identity == binding["watch_identity"])
                    self.wo09.store.retain_watch(transition_watch(watch, WatchState.STALE,
                        at=max(now, watch.last_transition_at)))
                    continue
                if (tick.received_at > now or tick.observed_at <= datetime.fromisoformat(binding["watch_started_at"])
                        or tick.observed_at >= datetime.fromisoformat(binding["expires_at"])):
                    continue
                previous = self._observations.get(binding["identity"])
                if previous is not None:
                    old_time, old_connection, old_sequence = previous
                    if old_connection != tick.connection_id:
                        self.on_disconnect(at=now)
                        continue
                    if tick.observed_at <= old_time or (old_sequence is not None
                            and tick.source_sequence is not None and tick.source_sequence <= old_sequence):
                        continue
                self._observations[binding["identity"]] = (tick.observed_at, tick.connection_id, tick.source_sequence)
                levels = binding["hint_levels"]
                threshold = levels.get(binding["missing_criterion"])
                if threshold is None:
                    continue
                beyond = tick.last_price > Decimal(threshold) if binding["direction"] == "LONG" else tick.last_price < Decimal(threshold)
                if not beyond:
                    continue
                if binding["missing_criterion"] == "I3" and not (
                        Decimal(levels["corridor_lower"]) < tick.last_price < Decimal(levels["corridor_upper"])):
                    continue
                hint = _document(HINT, binding_identity=binding["identity"],
                    watch_identity=binding["watch_identity"], opportunity_identity=binding["opportunity_identity"],
                    assessment_identity=binding["assessment_identity"], generation=binding["generation"],
                    state="ADVISORY_WAKE_HINT", last_price=str(tick.last_price),
                    observed_at=tick.observed_at.isoformat(), received_at=tick.received_at.isoformat(),
                    connection_identity=tick.connection_id, source_sequence=tick.source_sequence,
                    instrument=binding["instrument"], session_identity=binding["session_identity"],
                    message="Possible change — awaiting completed Analysis",
                    authority="NO_CRITERION_COMPLETION_NO_READINESS_NO_AUTOMATIC_ACQUISITION")
                hints.append(self.store.retain(hint))
            return tuple(hints)

    def attach_existing(self, hub, capability, instruments):
        """Opt-in to already lawful applied subscriptions; no transport effects."""
        return hub.observe_existing(capability, self, tuple(instruments))

    def on_market_tick(self, tick):
        return self.on_tick(tick)

    def on_order_update(self, update):
        return None

    def on_connection_state(self, state):
        from kronos.provider.contracts.monitoring import MonitoringConnectionState
        if state is not MonitoringConnectionState.CONNECTED:
            self.on_disconnect()

    def on_disconnect(self, *, at=None):
        with self.store.lock:
            self._observations.clear()
            return self.wo09.mark_disconnect_stale(at=self.clock() if at is None else at)

    def reassessed(self, readiness, *, governed_event_evidence_identity):
        """Only a source-validated ordinary Analysis caller may record this event."""
        with self.store.lock:
            now = self.clock()
            records = []
            for binding in self.restore(at=now):
                if binding["readiness_identity"] != readiness.readiness_identity:
                    continue
                watch = next(w for w in self.wo09.store.load_watches()
                             if w.watch_identity == binding["watch_identity"])
                records.append(self.wo09.record_reassessment_event(readiness, watch, at=now,
                    governed_event_evidence_identity=governed_event_evidence_identity))
            return tuple(records)


def _source_levels(readiness):
    """Only completed evidence retained in the exact hashed assessment is usable."""
    document = readiness.assessment_document
    from kronos.intraday.wo09_experimental import assessment_from
    assessment = assessment_from(document)
    assessment.__post_init__()
    if assessment.identity != readiness.wo08_identity or assessment.integrity != readiness.wo08_integrity:
        raise ValueError("WO09_EXPERIMENTAL_WATCH_ASSESSMENT_MISMATCH")
    levels = assessment.data.get("experimental_watch_levels", {})
    for key, value in levels.items():
        if key not in {"I2", "I3", "corridor_lower", "corridor_upper"}:
            raise ValueError("WO09_EXPERIMENTAL_WATCH_LEVEL_INVALID")
        if value is not None and not Decimal(value).is_finite():
            raise ValueError("WO09_EXPERIMENTAL_WATCH_LEVEL_INVALID")
    if levels.get("I3") is not None and not all(levels.get(k) is not None
            for k in ("corridor_lower", "corridor_upper")):
        raise ValueError("WO09_EXPERIMENTAL_WATCH_CORRIDOR_REQUIRED")
    return levels


class _BoundWatchObserver:
    """Each passive callback retains its exact immutable watch generation."""
    owner_identity = IntradayExperimentalWatchCoordinator.owner_identity

    def __init__(self, coordinator, binding_identity):
        self.coordinator, self.binding_identity = coordinator, binding_identity

    def on_market_tick(self, tick):
        return self.coordinator.on_market_tick(tick, binding_identity=self.binding_identity)

    def on_subscription_lost(self):
        return self.coordinator.on_subscription_lost(self.binding_identity)

    def on_connection_state(self, state):
        return self.coordinator.on_connection_state(state)

    def on_order_update(self, update):
        return None


class GovernedExperimentalWatchCoordinator(IntradayExperimentalWatchCoordinator):
    """Canonical adapter over existing source/session and monitoring owners."""
    def __init__(self, wo09, *, boundary, factual_source, clock, instrument_source=None):
        self.boundary, self.factual_source = boundary, factual_source
        self.instrument_source = instrument_source
        self.hub = self.capability_supplier = self.maintenance = None
        self.registrations = {}
        self.last_failure = None
        self._interrupted = False
        self._interruption_generation = 0
        self._binding_interruptions = set()
        self._queue_lock = RLock()
        self._queue = {}
        self._queue_instruments = {}
        self._worker_thread = None
        self._queue_epoch = 0
        self._queue_closed = False
        self._queue_failure = None
        self._queue_coalesced = 0
        self._disconnect_pending = None
        self._disconnect_running = False
        super().__init__(wo09, clock=clock, current_binding=self._source_current)

    def bind_monitoring(self, hub, capability_supplier, maintenance):
        self.hub, self.capability_supplier, self.maintenance = hub, capability_supplier, maintenance
        # Startup restores persisted authority only; never attaches/reacquires.
        return self.restore()

    def _source_current(self, binding):
        from kronos.intraday.evidence_currentness import NewWorkNotEligible
        readiness = self.wo09.store.load_readiness(binding['readiness_identity'])
        if self._interrupted or binding['identity'] in self._binding_interruptions:
            return False
        try:
            with self.boundary._sources(readiness):
                self.boundary._source(readiness, 'readiness')
                try:
                    self.boundary._session(readiness, 'readiness')
                except (NewWorkNotEligible, ValueError):
                    return False
            expiry, instrument = self._session_instrument(readiness)
            if binding['expires_at'] != expiry.isoformat() or binding['instrument'] != _instrument(instrument):
                raise ValueError('WO09_EXPERIMENTAL_WATCH_OWNER_BINDING_INVALID')
            return (readiness.generation == binding['generation']
                and readiness.opportunity_identity == binding['opportunity_identity']
                and readiness.exact_mcx_contract_identity == binding['exact_contract_identity']
                and readiness.exact_mcx_roll_lineage == binding['exact_roll_lineage'])
        except NewWorkNotEligible:
            return False

    def _session_instrument(self, readiness):
        from kronos.browser.intraday_futures_control import domain008_session
        from kronos.intraday.wo10_futures_market import require_session
        now = self.clock()
        if self.instrument_source is not None:
            instrument, contract = self.instrument_source(readiness)
            session = domain008_session(self.boundary.calendar, readiness.canonical_subject_identity, now, contract=contract)
            require_session(session, now, exchange=readiness.market_family)
            if session.schedule.session_id != readiness.session_identity:
                raise ValueError('WO09_WATCH_SESSION_MISMATCH')
            return max(w.closes_at for w in session.schedule.windows), instrument
        authority = self.factual_source.authority(readiness)
        master, active = authority['master'], authority['active_mcx']
        if active is not None:
            if (active.binding_identity != readiness.exact_mcx_roll_lineage
                    or active.active_binding.derivative_contract_id != readiness.exact_mcx_contract_identity
                    or not active.active_binding.active_at(now)):
                raise ValueError('WO09_WATCH_EXACT_CONTRACT_MISMATCH')
            rows = [r for r in master.records if r.provider_record_identity == active.provider_record_identity]
            contract = dict(name=active.provider_contract_family, expiry=active.contract_expiry.isoformat())
        else:
            underlying = authority['underlying']
            if underlying is None or underlying.provider_binding is None:
                raise ValueError('WO09_WATCH_UNDERLYING_BINDING_REQUIRED')
            underlying.__post_init__()
            from kronos.instrument.runtime import InstrumentFreshness, ProviderBindingStatus
            if (underlying.canonical.canonical_instrument_id != readiness.canonical_subject_identity
                    or underlying.canonical_freshness is not InstrumentFreshness.CURRENT
                    or underlying.binding_status is not ProviderBindingStatus.BOUND
                    or not underlying.provider_binding.source_boundary <= now <= underlying.provider_binding.valid_through):
                raise ValueError('WO09_WATCH_UNDERLYING_BINDING_REQUIRED')
            binding = underlying.provider_binding
            rows = [r for r in master.records if r.provider_instrument_token == binding.provider_instrument_token
                and r.provider == binding.provider and r.trading_symbol == binding.provider_symbol and r.exchange == 'NSE']
            contract = None
        if len(rows) != 1:
            raise ValueError('WO09_WATCH_EXACT_INSTRUMENT_REQUIRED')
        session = domain008_session(self.boundary.calendar, readiness.canonical_subject_identity, now, contract=contract)
        require_session(session, now, exchange=readiness.market_family)
        if session.schedule.session_id != readiness.session_identity:
            raise ValueError('WO09_WATCH_SESSION_MISMATCH')
        row = rows[0]
        row.__post_init__()
        instrument = InstrumentRecord(**{name: getattr(row, name) for name in (
            'provider', 'exchange', 'segment', 'trading_symbol', 'name',
            'instrument_type', 'expiry', 'tick_size', 'lot_size')})
        return max(w.closes_at for w in session.schedule.windows), instrument

    @contextmanager
    def _admitted(self):
        ticket = None if self.maintenance is None else self.maintenance.admit('PROGRESSION')
        if self.maintenance is not None and ticket is None:
            self._mark_interrupted()
            yield False
            return
        try:
            if ticket is None:
                yield True
            else:
                with ticket.activate():
                    yield True
        finally:
            if ticket is not None:
                ticket.release()

    def after_analysis(self, readiness, requirements):
        with self._admitted() as admitted:
            if not admitted:
                return ()
            return self._after_analysis(readiness, requirements)

    def _after_analysis(self, readiness, requirements):
        if not watch_eligible(readiness, at=self.clock()):
            if watch_eligible(readiness) and readiness.first_five_document is not None:
                self.last_failure = 'ORIGINAL_FIRST_FIVE_FRESHNESS_EXPIRED'
            if any(w.canonical_subject_identity == readiness.canonical_subject_identity
                    and w.state is WatchState.ACTIVE for w in self.wo09.store.load_watches()):
                self.restore(subject=readiness.canonical_subject_identity)
            return ()
        # Source guards precede watch locks; all canonical callbacks use this order.
        with self.boundary._sources(readiness):
            self.boundary._source(readiness, 'readiness')
            self.boundary._session(readiness, 'readiness')
            expiry, instrument = self._session_instrument(readiness)
            bindings = self.synchronize(readiness, requirements, session_expires_at=expiry, instrument=instrument)
        if bindings and self.hub is not None and self.capability_supplier is not None:
            for binding in bindings:
                identity = binding['identity']
                previous = self.registrations.get(identity)
                if previous is not None and previous.active:
                    continue
                if previous is not None:
                    previous.disconnect()
                try:
                    with self._queue_lock:
                        self._queue_instruments[identity] = instrument
                    registration = self.hub.observe_existing(self.capability_supplier(),
                        _BoundWatchObserver(self, identity), (instrument,))
                    self.registrations[identity] = registration
                    if not registration.active:
                        self.on_subscription_lost(identity)
                    self.last_failure = None
                except (ValueError, RuntimeError) as error:
                    with self._queue_lock:
                        self._queue_instruments.pop(identity, None)
                    # Persistence remains usable by ordinary Analysis. Missing
                    # lawful subscriptions do not authorize new Provider work.
                    self.last_failure = str(error)
        return bindings

    def before_analysis(self, successor):
        """Called under the source-validated ordinary publication guards."""
        pointer = self.wo09.store.load_pointer(successor.canonical_subject_identity)
        if pointer is None or pointer.currentness is not CurrentnessState.CURRENT:
            return ()
        previous = self.wo09.store.load_readiness(pointer.readiness_identity)
        if (not is_experimental(previous) or previous.readiness_identity == successor.readiness_identity
                or previous.opportunity_identity != successor.opportunity_identity
                or previous.session_identity != successor.session_identity
                or previous.exact_mcx_contract_identity != successor.exact_mcx_contract_identity):
            return ()
        now = self.clock()
        records = []
        with self._admitted() as admitted:
            if not admitted:
                return ()
            return self._record_previous(successor, previous, now)

    def _record_previous(self, successor, previous, now):
        records = []
        with self.store.lock:
            bindings = {b['watch_identity']: b for b in self.store.records(BINDING)}
            for watch in self.wo09.store.load_watches(previous.readiness_identity):
                binding = bindings.get(watch.watch_identity)
                if (watch.state in {WatchState.ACTIVE, WatchState.STALE} and binding is not None
                        and now < datetime.fromisoformat(binding['expires_at'])):
                    records.append(self.wo09.record_reassessment_event(previous, watch, at=now,
                        governed_event_evidence_identity=successor.wo08_identity))
        return tuple(records)

    def restore(self, *, at=None, subject=None):
        with self._admitted() as admitted:
            if not admitted:
                return ()
            bindings = self.store.records(BINDING)
            if not bindings:
                # A denied empty startup has no retained authority to retire.
                # Clear its interruption only after lawful admission resumes.
                if self._interrupted:
                    generation = self._interruption_generation
                    self._detach_interrupted_observers()
                    self._clear_interruption(generation)
                return ()
            readiness = self.wo09.store.load_readiness(bindings[0]['readiness_identity'])
            with self.boundary._sources(readiness):
                interrupted = self._interrupted
                generation = self._interruption_generation
                # The gap applies to every subject. Keep the flag set while
                # _source_current makes all old bindings fail closed.
                scope = None if interrupted else subject
                values = super().restore(at=at, subject=scope)
                if interrupted:
                    self._detach_interrupted_observers()
                    self._clear_interruption(generation)
                else:
                    active = {b['identity'] for b in values}
                    for identity in tuple(self.registrations):
                        binding = next((b for b in bindings if b['identity']==identity), None)
                        if identity not in active and (scope is None or binding is not None and binding['subject']==scope):
                            self.registrations.pop(identity).disconnect()
                            with self._queue_lock:
                                self._queue_instruments.pop(identity, None)
                                self._binding_interruptions.discard(identity)
            return values

    def _detach_interrupted_observers(self):
        self._cancel_queued()
        for identity in tuple(self.registrations):
            self.registrations.pop(identity).disconnect()
        with self._queue_lock:
            self._queue_instruments.clear()
            self._binding_interruptions.clear()
        self._observations.clear()

    def _mark_interrupted(self):
        with self._queue_lock:
            self._interrupted = True
            self._interruption_generation += 1

    def _clear_interruption(self, generation):
        with self._queue_lock:
            if generation == self._interruption_generation:
                self._interrupted = False

    def on_tick(self, tick, *, binding_identity=None):
        with self._admitted() as admitted:
            if not admitted:
                return ()
            bindings = self.store.records(BINDING)
            if not bindings:
                return ()
            readiness = self.wo09.store.load_readiness(bindings[0]['readiness_identity'])
            with self.boundary._sources(readiness):
                return super().on_tick(tick, binding_identity=binding_identity)

    def on_subscription_lost(self, binding_identity):
        """Fence only the observer generation that actually lost ownership."""
        with self._queue_lock:
            if (binding_identity not in self._queue_instruments
                    and binding_identity not in self.registrations
                    and binding_identity not in self._binding_interruptions):
                return ()
            self._binding_interruptions.add(binding_identity)
            self._queue_instruments.pop(binding_identity, None)
            queued = self._queue.pop(binding_identity, None)
        if queued is not None and queued[1] is not None:
            queued[1].release()
        return self._schedule_disconnect_cleanup()

    def _retire_interrupted_bindings(self, *, at=None):
        """Deferred retirement by immutable binding id, never by instrument."""
        with self._admitted() as admitted:
            if not admitted:
                return ()
            with self._queue_lock:
                identities = frozenset(self._binding_interruptions)
            if not identities:
                return ()
            bindings = tuple(b for b in self.store.records(BINDING) if b['identity'] in identities)
            if not bindings:
                return ()
            readiness = self.wo09.store.load_readiness(bindings[0]['readiness_identity'])
            now = self.clock() if at is None else at
            with self.boundary._sources(readiness):
                with self.store.lock:
                    watches = {w.watch_identity:w for w in self.wo09.store.load_watches()}
                    for binding in bindings:
                        watch = watches.get(binding['watch_identity'])
                        if watch is not None and watch.state is WatchState.ACTIVE:
                            self.wo09.store.retain_watch(transition_watch(watch, WatchState.STALE,
                                at=max(now,watch.last_transition_at)))
                        self._observations.pop(binding['identity'], None)
                for binding in bindings:
                    identity = binding['identity']
                    registration = self.registrations.pop(identity, None)
                    if registration is not None:
                        registration.disconnect()
                    with self._queue_lock:
                        self._queue_instruments.pop(identity, None)
                        self._binding_interruptions.discard(identity)
            return ()

    def on_disconnect(self, *, at=None):
        """Fence immediately; shared callbacks never acquire source/store locks."""
        with self._queue_lock:
            self._interrupted = True
            self._interruption_generation += 1
            self._queue_epoch += 1
            queued = tuple(self._queue.values())
            self._queue.clear()
            self._queue_instruments.clear()
        for _, queued_ticket, _ in queued:
            if queued_ticket is not None:
                queued_ticket.release()
        return self._schedule_disconnect_cleanup(at=at)

    def _schedule_disconnect_cleanup(self, *, at=None):
        ticket = None if self.maintenance is None else self.maintenance.admit('PROGRESSION')
        if self.maintenance is not None and ticket is None:
            # Admission denial is a runtime-wide maintenance interruption even
            # when the event that encountered it concerned one subscription.
            self._mark_interrupted()
        with self._queue_lock:
            if self._queue_closed or self.maintenance is not None and ticket is None:
                if ticket is not None:
                    ticket.release()
                return ()
            if self._disconnect_pending is None:
                self._disconnect_pending = (at, ticket)
            else:
                self._queue_coalesced += 1
                if ticket is not None:
                    ticket.release()
            self._start_worker_locked()
        return ()

    def on_market_tick(self, tick, *, binding_identity=None):
        """Bounded latest observation queue; never decode sources on shared callbacks."""
        if type(tick) is not ProviderMarketTick:
            return False
        ticket = None if self.maintenance is None else self.maintenance.admit('PROGRESSION')
        if self.maintenance is not None and ticket is None:
            self._mark_interrupted()
            return False
        with self._queue_lock:
            if binding_identity is None:
                matches = [identity for identity,instrument in self._queue_instruments.items()
                    if instrument == tick.instrument]
                binding_identity = matches[0] if len(matches) == 1 else None
            # Keys are limited to exact generations of attached selective watches.
            if (self._queue_closed or self._interrupted
                    or binding_identity in self._binding_interruptions
                    or self._queue_instruments.get(binding_identity) != tick.instrument):
                if ticket is not None:
                    ticket.release()
                return False
            prior = self._queue.get(binding_identity)
            if prior is not None:
                self._queue_coalesced += 1
                self._queue[binding_identity] = (tick, prior[1], self._queue_epoch)
                if ticket is not None:
                    ticket.release()
                return True
            self._queue[binding_identity] = (tick, ticket, self._queue_epoch)
            self._start_worker_locked()
        return True

    def _start_worker_locked(self):
        if self._worker_thread is None:
            self._worker_thread = Thread(target=self._drain_ticks,
                name='Intraday experimental advisory watch', daemon=False)
            self._worker_thread.start()

    def _drain_ticks(self):
        try:
            while True:
                with self._queue_lock:
                    disconnect = self._disconnect_pending
                    if disconnect is not None:
                        self._disconnect_pending = None
                        self._disconnect_running = True
                        at, ticket = disconnect
                    elif not self._queue or self._queue_closed:
                        self._worker_thread = None
                        return
                    else:
                        key = next(iter(self._queue))
                        tick, ticket, epoch = self._queue.pop(key)
                try:
                    if disconnect is not None:
                        if ticket is None:
                            self._disconnect_cleanup(at=at)
                        else:
                            with ticket.activate():
                                self._disconnect_cleanup(at=at)
                    else:
                        with self._queue_lock:
                            accepted = (not self._queue_closed and epoch == self._queue_epoch
                                and key in self._queue_instruments and key not in self._binding_interruptions)
                        if accepted:
                            if ticket is None:
                                self.on_tick(tick, binding_identity=key)
                            else:
                                with ticket.activate():
                                    self.on_tick(tick, binding_identity=key)
                except Exception:
                    self._queue_failure = ('ADVISORY_DISCONNECT_WORK_FAILED' if disconnect is not None
                        else 'ADVISORY_REASSESSMENT_WORK_FAILED')
                finally:
                    if disconnect is not None:
                        with self._queue_lock:
                            self._disconnect_running = False
                    if ticket is not None:
                        ticket.release()
        finally:
            with self._queue_lock:
                if self._worker_thread is current_thread():
                    self._worker_thread = None

    def _disconnect_cleanup(self, *, at=None):
        if self._interrupted:
            return self.restore(at=at)
        return self._retire_interrupted_bindings(at=at)

    def _cancel_queued(self):
        with self._queue_lock:
            self._queue_epoch += 1
            queued = tuple(self._queue.values())
            self._queue.clear()
        for _, ticket, _ in queued:
            if ticket is not None:
                ticket.release()

    def shutdown(self):
        with self._queue_lock:
            self._queue_closed = True
            self._queue_instruments.clear()
            worker = self._worker_thread
        self._cancel_queued()
        if worker is not None and worker is not current_thread():
            worker.join(timeout=5)
            if worker.is_alive():
                raise RuntimeError('WO09_ADVISORY_WORK_NOT_DRAINED')
        for registration in tuple(self.registrations.values()):
            registration.disconnect()
        self.registrations.clear()

    def runtime_status_document(self):
        """In-memory configuration and worker state, never persisted eligibility."""
        from kronos.intraday.wo08_experimental import METHOD
        with self._queue_lock:
            work = dict(pending=len(self._queue) + int(self._disconnect_pending is not None), running=self._worker_thread is not None,
                coalesced=self._queue_coalesced, closed=self._queue_closed, failure=self._queue_failure)
        registrations = tuple(sorted(self.registrations.items()))
        failures = []
        attached = 0
        for identity, registration in registrations:
            attached += bool(registration.active)
            failure = registration.advisory_failure
            if failure is not None:
                failures.append(dict(binding_identity=identity, failure=failure))
        return dict(owner=self.owner_identity,
            method=dict(identity=METHOD[0], version=METHOD[1], checksum=METHOD[2]),
            policy=dict(identity=POLICY, version=VERSION),
            configuration=dict(method_available=True, watch_path_available=True,
                persistence_configured=self.store is not None,
                source_validation_configured=self.boundary is not None and self.instrument_source is not None,
                monitoring_configured=self.hub is not None and callable(self.capability_supplier),
                maintenance_admission_configured=self.maintenance is not None),
            monitoring_availability='EXISTING_SUBSCRIPTIONS_ONLY',
            attached_observers=attached, advisory_callback_failures=failures, work=work,
            last_failure=work['failure'] or self.last_failure or (failures[0]['failure'] if failures else None),
            automatic_provider_acquisition=False, websocket_can_promote=False,
            authority='EXPERIMENTAL_PAPER_ADVISORY_ONLY')

    def status_document(self):
        document = self.runtime_status_document()
        document.update(persisted_bindings=len(self.store.records(BINDING)),
            pending_hints=len(self.store.records(HINT)))
        return document


class GovernedWatchInstrumentSource:
    """Exact retained Analysis master and commissioned Intraday mapping only.

    Discovery already binds its consolidated master in source_identities. This
    route is restart-safe and performs no Provider reads or symbol inference.
    """
    def __init__(self, *, master_store, discovery_store, reconciliation, bindings, clock):
        self.master_store, self.discovery_store = master_store, discovery_store
        self.reconciliation, self.bindings, self.clock = reconciliation, bindings, clock

    def __call__(self, readiness):
        from kronos.provider.contracts.instrument_master import KITE_INSTRUMENT_MASTER_DATASET
        self.reconciliation.__post_init__()
        discovery = self.discovery_store.load_run(run_identity=readiness.assessment_document['discovery_identity'])
        discovery.__post_init__()
        if (discovery.reconciliation_identity != self.reconciliation.publication_identity
                or discovery.reconciliation_version != self.reconciliation.publication_version
                or discovery.reconciliation_integrity_identity != self.reconciliation.integrity_identity):
            raise ValueError('WO09_WATCH_RECONCILIATION_BINDING_INVALID')
        identities = [v for v in discovery.source_identities if v.startswith('PROVIDER-INSTRUMENT-SNAPSHOT-')]
        # Integrity prefixes are distinct and cannot be mistaken for identities.
        identities = [v for v in identities if not v.startswith('PROVIDER-INSTRUMENT-SNAPSHOT-INTEGRITY-')]
        if len(identities) != 1:
            raise ValueError('WO09_WATCH_RETAINED_MASTER_REQUIRED')
        master = self.master_store.load(provider='KITE',dataset_identity=KITE_INSTRUMENT_MASTER_DATASET,
            snapshot_identity=identities[0])
        if master.integrity_identity not in discovery.source_identities:
            raise ValueError('WO09_WATCH_RETAINED_MASTER_BINDING_INVALID')
        member = next((m for m in self.reconciliation.members
            if m.canonical_identity == readiness.canonical_subject_identity), None)
        if member is None:
            raise ValueError('WO09_WATCH_RECONCILIATION_MEMBER_REQUIRED')
        member.__post_init__()
        if readiness.market_family == 'MCX':
            active = self.bindings.load_current(canonical_subject_id=readiness.canonical_subject_identity)
            if (active is None or active.binding_identity != readiness.exact_mcx_roll_lineage
                    or active.active_binding.derivative_contract_id != readiness.exact_mcx_contract_identity
                    or active.provider_snapshot_identity != master.snapshot_identity
                    or not active.active_binding.active_at(self.clock())):
                raise ValueError('WO09_WATCH_EXACT_CONTRACT_MISMATCH')
            rows = [r for r in master.records if r.provider_record_identity == active.provider_record_identity]
            contract = dict(name=active.provider_contract_family,expiry=active.contract_expiry.isoformat())
        else:
            if member.exchange != 'NSE' or not member.provider_symbol or not member.provider_directive_identities:
                raise ValueError('WO09_WATCH_EXACT_NSE_MAPPING_REQUIRED')
            rows = [r for r in master.records if r.provider=='KITE' and r.exchange==member.exchange
                    and r.trading_symbol==member.provider_symbol]
            contract = None
        if len(rows) != 1:
            raise ValueError('WO09_WATCH_EXACT_INSTRUMENT_REQUIRED')
        row = rows[0]
        row.__post_init__()
        return InstrumentRecord(**{name:getattr(row,name) for name in (
            'provider','exchange','segment','trading_symbol','name','instrument_type','expiry','tick_size','lot_size')}), contract
