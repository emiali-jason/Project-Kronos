"""One explicit selected-future observation, without position/trading authority.

No acquisition, recovery or persistence occurs at construction or read time.
The existing Provider capability, subscription hub and Market owner are used;
this owner supplies only bounded orchestration and an immutable factual receipt.
"""
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Event, Lock
from time import monotonic
from zoneinfo import ZoneInfo
import json
import re

from kronos.common.connection_governance import immutable_write, private_directory
from kronos.instrument.runtime import ProviderInstrumentAssertion
from kronos.market.schedule import (
    InMemoryMarketScheduleSource, MarketDaySchedule, MarketSessionService,
    MarketSessionState, MarketWindow, TradingDayStatus,
)
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState, MonitoringSubscriptionEvidence, ProviderMarketTick,
)

_IST = ZoneInfo('Asia/Kolkata')
_SCHEMA = 'KRONOS-SWING-MCX-EXACT-OBSERVATION-V1'
_WAIT_SECONDS = 15.0  # Existing Settings observation wait, not a trading policy.


def _value(value):
    return json.loads(json.dumps(value, default=lambda x:
        asdict(x) if is_dataclass(x) else
        x.isoformat() if hasattr(x, 'isoformat') else str(x)))


def _digest(value):
    return sha256(json.dumps(_value(value), sort_keys=True,
                            separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _operation(value):
    if type(value) is not str or re.fullmatch('[a-f0-9]{32}', value) is None:
        raise ValueError('MCX_OBSERVATION_ID_INVALID')
    return value


def session_fact(calendar, moment):
    """Field-preserving adapter of the existing governed Market publication."""
    day = moment.astimezone(_IST).date()
    schedule = calendar.schedule('MCX', day, observed_at=moment)
    if schedule is None:
        raise ValueError('MCX_OBSERVATION_SESSION_UNAVAILABLE')
    normalized = MarketDaySchedule('MCX', schedule.trading_date,
        schedule.session_identity, schedule.timezone, TradingDayStatus.TRADING,
        tuple(MarketWindow(w.window_open, w.window_close) for w in schedule.windows),
        schedule.calendar_identity, schedule.calendar_version)
    fact = MarketSessionService(InMemoryMarketScheduleSource((normalized,))).facts(
        exchange='MCX', trading_date=day, observed_at=moment)
    if fact.state is not MarketSessionState.OPEN:
        raise ValueError('MCX_OBSERVATION_SESSION_NOT_OPEN')
    return fact


class _Consumer:
    """Callback copies one normalized tick only; no disk or Provider calls."""
    def __init__(self, identity):
        self.owner_identity = identity
        self.event = Event()
        self.lock = Lock()
        self.tick = None

    def on_market_tick(self, tick):
        with self.lock:
            if not self.event.is_set():
                self.tick = tick
                self.event.set()

    def on_connection_state(self, _state):
        pass  # The applied/current subscription evidence is checked by the owner.

    def on_order_update(self, _update):
        pass  # No order/position authority or evidence is consumed.


class McxSelectedContractObservation:
    def __init__(self, root, *, hub, admission, capability, calendar,
                 selected, clock=lambda: datetime.now(UTC), wait_seconds=_WAIT_SECONDS):
        if type(wait_seconds) is not float or not 0 < wait_seconds <= _WAIT_SECONDS:
            raise ValueError('MCX_OBSERVATION_WAIT_INVALID')
        self.root = Path(root)
        self.hub, self.admission = hub, admission
        self.capability, self.calendar, self.selected = capability, calendar, selected
        self.clock = clock
        self.wait_seconds = wait_seconds
        self._exclusive = Lock()
        self._cleanup_ticket = None

    def _path(self, operation):
        path = self.root / _operation(operation)
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('MCX_OBSERVATION_PATH_INVALID')
        return path

    def read(self, operation):
        """Observational receipt read, including unavailable/incomplete paths."""
        directory = self._path(operation)
        path = directory / 'receipt.json'
        if path.is_symlink():
            raise ValueError('MCX_OBSERVATION_PATH_INVALID')
        value = json.loads(path.read_bytes())
        if (set(value) != {'record', 'sha256'} or
                _digest(value['record']) != value['sha256'] or
                value['record'].get('schema') != _SCHEMA or
                value['record'].get('operation') != operation):
            raise ValueError('MCX_OBSERVATION_RECEIPT_INVALID')
        return value

    def observe(self, *, operation, run, family, selection_sha256, publication_sha256):
        """One synchronous counted operation. Duplicate IDs never reacquire."""
        directory = self._path(operation)
        request = dict(operation=operation, run=run, family=family.value,
            selection_sha256=selection_sha256, publication_sha256=publication_sha256)
        if not self._exclusive.acquire(blocking=False):
            raise ValueError('MCX_OBSERVATION_BUSY')
        ticket = registration = None
        cleanup_complete = True
        claimed = durable_complete = False
        try:
            if self._cleanup_ticket is not None:
                raise ValueError('MCX_OBSERVATION_CLEANUP_UNRESOLVED')
            if directory.exists():
                # Exact identical replay returns historical receipt, never live-now.
                retained = directory / 'request.json'
                if retained.is_symlink() or json.loads(retained.read_bytes()) != request:
                    raise ValueError('MCX_OBSERVATION_REPLAY_CONFLICT')
                return self.read(operation)
            ticket = self.admission.admit('MONITORING_CALLBACK')
            if ticket is None:
                raise ValueError('MCX_OBSERVATION_FENCED')
            with ticket.activate():
                initial = self.selected(run, family, selection_sha256, publication_sha256)
                started = self.clock()
                market = session_fact(self.calendar, started)
                capability = self.capability()
                if getattr(capability, 'active', False) is not True:
                    raise ValueError('MCX_OBSERVATION_CAPABILITY_UNAVAILABLE')
                private_directory(self.root)
                directory.mkdir(mode=0o700)  # exclusive durable operation claim
                claimed = True
                import os
                descriptor = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                immutable_write(directory / 'request.json', request)
                record = dict(schema=_SCHEMA, **request, started_at=started,
                    selection=initial, observation=None, mapping=None,
                    state='FAILED', reason='MCX_OBSERVATION_INCOMPLETE')
                wall_deadline = monotonic() + self.wait_seconds
                valid_through = started + timedelta(seconds=self.wait_seconds)
                try:
                    instrument = initial['instrument']
                    # Existing current mechanisms: normalized exact expiry record,
                    # then a typed Provider assertion with current token custody.
                    records = capability.instrument_records('MCX')
                    matches = tuple(x for x in records if x == instrument)
                    if len(matches) != 1:
                        raise ValueError('MCX_OBSERVATION_CURRENT_CONTRACT_MISMATCH')
                    assertions = capability.instrument_assertions('MCX',
                        source_boundary=started, valid_through=valid_through)
                    matches = tuple(x for x in assertions
                        if type(x) is ProviderInstrumentAssertion
                        and x.provider == instrument.provider
                        and x.provider_symbol == instrument.trading_symbol
                        and x.exchange == instrument.exchange
                        and x.segment == instrument.segment
                        and x.instrument_type == instrument.instrument_type
                        and x.asserted_tick_size == instrument.tick_size
                        and x.asserted_lot_size == instrument.lot_size)
                    if len(matches) != 1:
                        raise ValueError('MCX_OBSERVATION_MAPPING_AMBIGUOUS_OR_CHANGED')
                    mapping = matches[0]
                    if (mapping.source_boundary != started or
                            mapping.valid_through != valid_through or
                            not started <= self.clock() < valid_through):
                        raise ValueError('MCX_OBSERVATION_MAPPING_STALE')
                    record['mapping'] = asdict(mapping)
                    consumer = _Consumer('MCX-OBSERVATION-' + operation)
                    registration = self.hub.open(capability, consumer)
                    registration.subscribe((instrument,))
                    registration.connect()
                    remaining = wall_deadline - monotonic()
                    if remaining <= 0 or not consumer.event.wait(remaining):
                        raise ValueError('MCX_OBSERVATION_NO_ADMISSIBLE_QUOTE')
                    tick = consumer.tick
                    context = registration.observation_context(instrument)
                    now = self.clock()
                    if (type(tick) is not ProviderMarketTick or
                            type(context) is not MonitoringSubscriptionEvidence or
                            not registration.active or
                            registration.connection_state is not MonitoringConnectionState.CONNECTED or
                            context.state is not MonitoringConnectionState.CONNECTED or
                            context.instrument != instrument or not context.admits(tick) or
                            context.provider_instrument_token != mapping.provider_instrument_token or
                            tick.instrument != instrument or tick.last_price <= 0 or
                            not started <= context.subscribed_at < tick.observed_at <= tick.received_at <= now < valid_through or
                            monotonic() >= wall_deadline or not capability.active):
                        raise ValueError('MCX_OBSERVATION_QUOTE_INADMISSIBLE')
                    observed_market = session_fact(self.calendar, tick.observed_at)
                    received_market = session_fact(self.calendar, tick.received_at)
                    final_market = session_fact(self.calendar, now)
                    if any(x.schedule != market.schedule or x.active_window != market.active_window
                           for x in (observed_market, received_market, final_market)):
                        raise ValueError('MCX_OBSERVATION_SESSION_CHANGED')
                    if self.selected(run, family, selection_sha256, publication_sha256) != initial:
                        raise ValueError('MCX_OBSERVATION_SELECTION_CHANGED')
                    if (registration.observation_context(instrument) != context
                            or not registration.active or not capability.active
                            or self.clock() >= valid_through or monotonic() >= wall_deadline):
                        raise ValueError('MCX_OBSERVATION_FINAL_FENCE_CHANGED')
                    record.update(state='OBSERVED', reason=None, observation=dict(
                        tick=asdict(tick), subscription=asdict(context),
                        subscription_identity=_digest(asdict(context)),
                        owner_identity=consumer.owner_identity,
                        provider_timestamp_kind='PROVIDER_NORMALIZED_TIMESTAMP',
                        distinct_exchange_timestamp='UNKNOWN',
                        session=asdict(observed_market),
                        freshness='POST_REQUEST_POST_SUBSCRIPTION_WITHIN_BOUNDED_OPERATION',
                        intrabar_trade_continuity='UNVERIFIED', trading_authority='NONE'))
                except Exception as error:
                    reason = str(error)
                    record['reason'] = (reason if re.fullmatch('MCX_OBSERVATION_[A-Z_]+', reason)
                                        else 'MCX_OBSERVATION_PROVIDER_OR_VALIDATION_FAILED')
                    record['error_type'] = type(error).__name__
                finally:
                    if registration is not None:
                        try:
                            registration.disconnect()  # reference-counted, never disconnect another owner
                        except Exception:
                            cleanup_complete = False
                    # A failure to prove cleanup or retain final bookkeeping
                    # must keep counted ownership, rather than permit retirement.
                    status = None
                    prior_cleanup = cleanup_complete
                    cleanup_complete = False
                    status = self.hub.status_document()
                    cleanup_complete = prior_cleanup
                    if (registration is not None and any(x['owner_identity'] == registration.owner_identity
                            for x in status['owners'])) or status['transport_cleanup']['state'] != 'COMPLETE':
                        cleanup_complete = False
                    record['cleanup'] = dict(complete=cleanup_complete, hub=status)
                    record['completed_at'] = self.clock()
                    if not cleanup_complete:
                        record.update(state='FAILED', reason='MCX_OBSERVATION_CLEANUP_INCOMPLETE')
                    receipt = dict(record=_value(record), sha256=_digest(record))
                    immutable_write(directory / 'receipt.json', receipt)
                    durable_complete = True
                return receipt
        finally:
            # Count ownership through cleanup, receipt publication and bookkeeping.
            if ticket is not None:
                if not claimed or (cleanup_complete and durable_complete):
                    ticket.release()
                else:
                    self._cleanup_ticket = ticket  # unresolved cleanup blocks retirement/new observation
            self._exclusive.release()
