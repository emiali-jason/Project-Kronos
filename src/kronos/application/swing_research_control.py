"""Explicit Swing WO-12 Sponsor update over governed calendar and Provider facts."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
import json
import re
from threading import Lock
from zoneinfo import ZoneInfo

from kronos.common.maintenance_admission import AdmissionTicket
from kronos.application.swing_research_integration import SwingResearchEventCapture
from kronos.application.swing_nse_equity_basis import NseEquityBasisStore
from kronos.application.swing_prospective_research import SwingProspectiveResearchApplication
from kronos.provider.contracts.market_data import HistoricalCandleRequest, HistoricalInterval
from kronos.swing.v1.prospective_research import (
    FollowupCandle, GovernedCalendar, GovernedSession, MARKETS, record,
)


IST = ZoneInfo("Asia/Kolkata")


def _digest(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             default=str).encode()).hexdigest()


class SwingResearchControl:
    """No constructor, GET, or startup mutation; update is the only acquirer."""

    def __init__(self, *, application, intake, research: SwingProspectiveResearchApplication,
                 capture: SwingResearchEventCapture, calendar, clock=None,
                 native_review=None, trade_window=None, mcx_control=None,
                 equity_basis: NseEquityBasisStore | None = None,
                 release_verifier=None) -> None:
        self.application = application
        self.intake = intake
        self.research = research
        self.capture = capture
        self.calendar = calendar
        self.clock = clock or (lambda: datetime.now(UTC))
        self.native_review = native_review
        self.trade_window = trade_window
        self.mcx_control = mcx_control
        self.equity_basis = equity_basis
        # Read the existing retained corporate-action owner; never acquire data.
        self.research.local_outcome_basis = self._local_outcome_basis
        self.release_verifier = release_verifier
        self._worker_lock = Lock()
        self._authority_lock = Lock()
        self._worker = ThreadPoolExecutor(max_workers=1,
                                          thread_name_prefix="kronos-swing-research")
        self._active_operation: str | None = None
        self._worker_closed = False

    def status(self) -> dict:
        commissioning = self.research.store.pointer("COMMISSIONING", "active")
        operation = self.research.store.pointer("OPERATION", "latest")
        return {**self.research.status(),
                "commissioned_at": None if commissioning is None else commissioning.data["commissioned_at"],
                "admission_capture": self.application.research_capture_status(),
                "v2_capture": None if self.intake is None else self.intake.research_capture_failure,
                "decision_capture": None if self.native_review is None else self.native_review.research_capture_failure,
                "observation_capture": None if self.trade_window is None else self.trade_window.research_capture_failure,
                "mcx_capture": None if self.mcx_control is None else self.mcx_control.research_capture_failure,
                "operation": None if operation is None else operation.data,
                "capture_receipts": None if self.capture.inbox is None else self.capture.inbox.count(),
                "daily": self.daily_status()}

    def _operation_state(self, identity: str, state: str, *, phase: str,
                         result=None, failure: str | None = None) -> dict:
        value = record("OPERATION", operation_identity=identity, state=state,
                       phase=phase, changed_at=self.clock().isoformat(),
                       outcome=None if result is None else result.outcome,
                       remaining_candle_requests=(None if result is None else
                                                  result.remaining_candle_requests),
                       failure=failure, authority="EXPLICIT_RESEARCH_UPDATE")
        with self.research.store.transaction():
            self.research.store.retain(value)
            self.research.store.publish_pointer("OPERATION", identity, value)
            self.research.store.publish_pointer("OPERATION", "latest", value)
        return value.data

    def submit_update(self, identity: str, parent: AdmissionTicket) -> dict:
        """Durably admit one bounded worker while the Browser POST ticket lives."""
        if re.fullmatch(r"[0-9a-f]{32}", identity) is None:
            raise ValueError("SWING_RESEARCH_OPERATION_IDENTITY_INVALID")
        self.capture.commissioned_at()
        if type(parent) is not AdmissionTicket or parent._released:
            raise ValueError("SWING_RESEARCH_MAINTENANCE_PARENT_INVALID")
        with self._worker_lock:
            if self._worker_closed:
                raise ValueError("SWING_RESEARCH_WORKER_CLOSED")
            if self._active_operation is not None:
                if self._active_operation != identity:
                    return {"operation_identity": identity, "state": "BUSY",
                            "phase": "ANOTHER_UPDATE_ACTIVE"}
                prior = self.research.store.pointer("OPERATION", identity)
                return prior.data if prior is not None else {
                    "operation_identity": identity, "state": "QUEUED", "phase": "ADMITTED"}
            prior = self.research.store.pointer("OPERATION", identity)
            if prior is not None and prior.data["state"] == "COMPLETED":
                return prior.data
            ticket = parent.fork("SWING_RESEARCH")
            try:
                admitted = self._operation_state(identity, "QUEUED", phase="ADMITTED")
                self._active_operation = identity
                self._worker.submit(self._run_update, identity, ticket)
            except Exception:
                self._active_operation = None
                ticket.release()
                raise
            return admitted

    def _run_update(self, identity: str, ticket: AdmissionTicket) -> None:
        try:
            with ticket.activate():
                self._operation_state(identity, "RUNNING", phase="REPLAY")
                result = self.update(identity,
                    progress=lambda phase: self._operation_state(
                        identity, "RUNNING", phase=phase))
                self._operation_state(identity, "COMPLETED", phase="RESULT", result=result)
        except Exception as error:
            try:
                self._operation_state(identity, "FAILED", phase="RETRYABLE",
                                      failure=type(error).__name__)
            except Exception:
                pass  # The retained QUEUED/RUNNING record remains resumable.
        finally:
            with self._worker_lock:
                self._active_operation = None
            ticket.release()

    def close(self) -> None:
        with self._worker_lock:
            self._worker_closed = True
        self._worker.shutdown(wait=True, cancel_futures=False)

    def commission(self, *, release_identity: str, source_manifest_sha256: str,
                   manifest_bytes: bytes):
        """Explicit counted control only; independently validate release on each invocation."""
        if self.release_verifier is None:
            raise ValueError("SWING_RESEARCH_RELEASE_VERIFIER_UNAVAILABLE")
        proof = self.release_verifier.verify(release_identity, manifest_bytes, source_manifest_sha256)
        with self.research.store.transaction():
            receipts = self.research.store.records("COMMISSIONING")
            prior = self.research.store.pointer("COMMISSIONING", "active")
            if prior is None and receipts:
                if len(receipts) != 1:
                    raise ValueError("SWING_RESEARCH_COMMISSIONING_CONFLICT")
                prior = receipts[0]  # Crash after immutable receipt, before pointer.
            if prior is not None:
                if (prior.data["release_identity"] != release_identity
                        or prior.data["source_manifest_sha256"] != source_manifest_sha256):
                    raise ValueError("SWING_RESEARCH_ALREADY_COMMISSIONED")
                if self.research.store.pointer("COMMISSIONING", "active") is None:
                    self.research.store.publish_pointer("COMMISSIONING", "active", prior)
                return prior
            if (any(path.is_symlink() or path.is_file() and path != self.research.store.root / ".operation.lock"
                        for path in self.research.store.root.rglob("*"))
                    or self._active_operation is not None
                    or any(self.research.store.records(kind) for kind in (
                        "ORIGIN", "MILESTONE", "DECISION", "LIFECYCLE_TRACK", "CANDLE",
                        "CHECKPOINT", "RECEIPT", "UPDATE", "OPERATION"))
                    or self.capture.inbox is None or not self.capture.inbox.empty_for_commissioning()):
                raise ValueError("SWING_RESEARCH_COMMISSIONING_STORE_NOT_EMPTY")
            if self.application.research_capture_status() is not None or any(
                    owner is not None and getattr(owner, "research_capture_failure", "UNAVAILABLE") is not None
                    for owner in (self.intake, self.native_review, self.trade_window, self.mcx_control)):
                raise ValueError("SWING_RESEARCH_CAPTURE_HEALTH_UNAVAILABLE")
            history = self.application.committed_research_replay_history()
            # Revalidate actual source immediately before the durable boundary.
            if self.release_verifier.verify(release_identity, manifest_bytes, source_manifest_sha256) != proof:
                raise ValueError("SWING_RESEARCH_RELEASE_DRIFT")
            marker = record("COMMISSIONING", **proof,
                            owner_manifest_sha256=(None if not history else
                                                   history[-1].reference["sha256"]),
                            commissioned_at=self.clock().isoformat(),
                            authority="PROSPECTIVE_CAPTURE_BOUNDARY")
            self.research.store.retain(marker)
            self.research.store.publish_pointer("COMMISSIONING", "active", marker)
            return marker

    def import_actions(self, fields: dict, csv_bytes: bytes) -> str:
        from kronos.application.swing_research_authority import import_official_actions
        if self.equity_basis is None:
            raise ValueError("SWING_NSE_ACTION_STORE_UNAVAILABLE")
        # Do not let an authenticated import change evidence midway through one
        # UPDATE, or hold a Browser request waiting on historical acquisition.
        if not self._authority_lock.acquire(blocking=False):
            raise ValueError("SWING_RESEARCH_AUTHORITY_BUSY")
        try:
            return import_official_actions(self.equity_basis, self.calendar, fields,
                                           csv_bytes, received_at=self.clock())
        finally:
            self._authority_lock.release()

    def _calendars(self, as_of: datetime) -> dict[str, GovernedCalendar]:
        origins = {item.identity: item for item in self.research.store.origins()}
        milestones = self.research.store.records("MILESTONE")
        result = {}
        for market in sorted({origins[item.data["origin_identity"]].data["market"]
                              for item in milestones}):
            if market not in MARKETS or self.calendar is None:
                continue
            exchange = "NSE" if market == "NSE" else "MCX"
            try:
                publication = self.calendar.publication(exchange)
                start = min(datetime.fromisoformat(item.data["occurred_at"]).astimezone(IST).date()
                            for item in milestones
                            if origins[item.data["origin_identity"]].data["market"] == market)
                end = as_of.astimezone(IST).date()
                if (publication.coverage_start > start or publication.coverage_end < end
                        or publication.source_boundary > as_of):
                    continue
                sessions = []
                for trading_date in sorted(publication.trading_dates):
                    if trading_date < start or trading_date > publication.coverage_end:
                        continue
                    schedule = self.calendar.schedule(exchange, trading_date,
                                                       observed_at=as_of)
                    if schedule is None or not schedule.windows:
                        raise ValueError("SWING_RESEARCH_CALENDAR_SESSION_MISSING")
                    windows = schedule.windows
                    identity = (market + ":" + trading_date.isoformat() + ":" +
                                _digest([(w.window_open.isoformat(), w.window_close.isoformat())
                                         for w in windows]))
                    sessions.append(GovernedSession(identity, market, trading_date,
                                                    windows[0].window_open,
                                                    windows[-1].window_close))
                result[market] = GovernedCalendar(
                    market, publication.calendar_identity + ":" + publication.publication_sha256,
                    publication.calendar_version, publication.source_boundary,
                    publication.coverage_start, publication.coverage_end, tuple(sessions))
            except (OSError, ValueError, KeyError):
                # The WO-12 engine reports the exact affected market as
                # CALENDAR_UNAVAILABLE without changing verified workbooks.
                continue
        return result

    def _fetcher(self, as_of: datetime):
        origins = self.research.store.origins()
        by_contract = {}
        for item in origins:
            binding = item.data.get("contract_binding")
            if binding is None:
                continue
            key = item.data["exact_contract_identity"]
            if key in by_contract and by_contract[key] != (binding, item.data["market"]):
                raise ValueError("SWING_RESEARCH_CONTRACT_BINDING_CONFLICT")
            by_contract[key] = (binding, item.data["market"])
        capability = None
        masters = {}

        def fetch(contract_identity: str, session: GovernedSession) -> FollowupCandle | None:
            nonlocal capability
            bound = by_contract.get(contract_identity)
            if bound is None:
                return None
            binding, market = bound
            if session.market != market:
                return None
            if capability is None:
                capability = self.application.authenticated_read_only_capability()
            if capability is None or capability.active is not True:
                return None
            exchange = binding["exchange"]
            if exchange not in masters:
                masters[exchange] = capability.instrument_records(exchange)
            records = [item for item in masters[exchange]
                       if all(getattr(item, key) == binding[key]
                              for key in ("provider", "exchange", "segment",
                                          "trading_symbol", "instrument_type"))
                       and (None if item.expiry is None else item.expiry.isoformat())
                       == binding["expiry"]]
            if len(records) != 1:
                return None
            schedule = self.calendar.schedule(exchange, session.trading_date,
                                              observed_at=as_of)
            if market != "NSE":
                expiry = date.fromisoformat(binding["expiry"])
                profile = self.calendar.mcx_contract_session_profile(
                    contract_family=market, contract_expiry=expiry,
                    trading_date=session.trading_date,
                    observed_at=datetime.combine(session.trading_date, time.min, IST))
                if not profile.contract_eligible:
                    return None
                schedule = profile.continuous_trading
            if schedule is None or not schedule.windows:
                return None
            windows = schedule.windows
            if (windows[-1].window_close > as_of
                    or any(window.window_open >= window.window_close for window in windows)
                    or any(previous.window_close > following.window_open
                           for previous, following in zip(windows, windows[1:]))):
                return None
            # One exact-contract request covers every governed window, while
            # verification excludes the breaks. This preserves R2's 60-call
            # bound even for MCX sessions with multiple trading windows.
            request = HistoricalCandleRequest(records[0], windows[0].window_open,
                                              windows[-1].window_close, HistoricalInterval.MINUTE)
            candles = capability.historical_candles(request)
            received_at = self.clock()
            if received_at.tzinfo is None or received_at < as_of:
                raise ValueError("SWING_RESEARCH_RECEIPT_TIME_INVALID")
            if not candles:
                return None
            actual = tuple(sorted(candles, key=lambda item: item.timestamp))
            expected = tuple(window.window_open + timedelta(minutes=index)
                             for window in windows
                             for index in range(int((window.window_close - window.window_open)
                                                    .total_seconds() // 60)))
            if (len(actual) != len(expected)
                    or any(item.timestamp != timestamp
                           for item, timestamp in zip(actual, expected))):
                return None
            source_identity = _digest({
                "contract": contract_identity, "session": session.identity,
                "request": (request.start.isoformat(), request.end.isoformat(), request.interval.value),
                "candles": [(item.timestamp.isoformat(), item.open, item.high,
                             item.low, item.close, item.volume) for item in actual]})
            # Equity corporate-action normalization is not yet owner-attested.
            # Keep those checkpoints unavailable instead of asserting a false
            # common price basis. NSE indices and MCX have no equity action.
            price_basis_unverified = market == "NSE" and binding["canonical_instrument"] not in {
                "NIFTY", "BANK NIFTY"}
            return FollowupCandle(contract_identity, session.identity,
                                  source_identity, "PROVIDER_MINUTE_V1", received_at,
                                  str(actual[-1].close),
                                  str(max(item.high for item in actual)),
                                  str(min(item.low for item in actual)), True,
                                  price_basis_verified=not price_basis_unverified)

        return fetch

    def _basis_for(self, milestone, origin,
                   sessions: tuple[GovernedSession, ...], horizon: int,
                   as_of: datetime) -> tuple[str | None, str | None]:
        binding = origin.data.get("contract_binding") or {}
        if (origin.data["market"] != "NSE" or binding.get("instrument_type") != "EQ"
                or binding.get("canonical_instrument") in {"NIFTY", "BANK NIFTY"}):
            return None, None
        if self.equity_basis is None:
            return "UNKNOWN", None
        event_day = datetime.fromisoformat(
            milestone.data["occurred_at"]).astimezone(IST).date()
        subsequent = tuple(session for session in sessions
                           if session.trading_date > event_day)
        if len(subsequent) < horizon or subsequent[horizon - 1].closes_at > as_of:
            return "UNKNOWN", None
        return self.equity_basis.basis(
            binding["trading_symbol"], "EQ", event_day,
            subsequent[horizon - 1].trading_date, as_of=as_of)

    def update(self, operation_identity: str, *, progress=None):
        """One explicit UPDATE observes one stable corporate-action authority."""
        with self._authority_lock:
            return self._update_with_authority(operation_identity, progress=progress)

    def _update_with_authority(self, operation_identity: str, *, progress=None):
        """Admitted workers may wait for a bounded import; tickets stay counted."""
        self.capture.commissioned_at()
        if self.intake is None:
            raise ValueError("SWING_RESEARCH_V2_OWNER_UNAVAILABLE")
        sponsors, lifecycle = (((), None) if self.native_review is None
                               else self.native_review.retained_research_events())
        decisions, tracks = (((), ()) if self.trade_window is None
                             else self.trade_window.retained_research_events())
        self.capture.replay_retained(
            self.application.committed_research_replay_history(),
            self.intake.retained_research_promotions(),
            sponsor_results=sponsors, lifecycle=lifecycle,
            observation_decisions=decisions,
            paper_observation_tracks=tracks)
        if progress is not None:
            progress("ACQUISITION_AND_PUBLICATION")
        as_of = self.clock()
        return self.research.update(operation_identity=operation_identity,
                                    sessions=self._calendars(as_of),
                                    fetch_missing=self._fetcher(as_of), as_of=as_of,
                                    equity_basis=self._basis_for)

    def _local_outcome_basis(self, origin, start, through, as_of):
        binding = origin.data.get('contract_binding') or {}
        if self.equity_basis is None or binding.get('instrument_type') != 'EQ':
            return 'UNKNOWN', None
        if not self._authority_lock.acquire(blocking=False):
            return 'UNKNOWN', None
        try:
            return self.equity_basis.basis(binding['trading_symbol'], 'EQ', start, through, as_of=as_of)
        finally:
            self._authority_lock.release()

    def configure_daily(self, *, admission, shutdown_lock, shutdown_started, ready, source_runtime=lambda: {"availability":"UNAVAILABLE"}):
        """Reuse service pulse/executor and existing ordinary-Exit handshake."""
        from kronos.application.swing_daily_research import daily_chain
        self._daily_admission = admission
        self._daily_shutdown_lock = shutdown_lock
        self._daily_shutdown_started = shutdown_started
        self._daily_ready = ready
        self._daily_source_runtime = source_runtime
        self._daily_stopping = False
        self._daily_epoch = None
        self._daily_attempted = set()
        self._daily_next_check = 0.0
        self._daily_restore_failure = None
        self._last_daily_result = None
        self._daily_receipts = ()
        try:
            values = self.research.store.records('DAILY_PUBLICATION')
            for day in sorted({r.data['reporting_date'] for r in values}):
                daily_chain(self.research.store, day, self.research.publication_root)
            self._daily_receipts = values
        except (ValueError, OSError, TypeError, KeyError):
            self._daily_restore_failure = 'DAILY_RESTORATION_UNAVAILABLE'

    def daily_status(self):
        if not hasattr(self, '_daily_ready'):
            return {'state': 'NOT_CONFIGURED', 'publications': [], 'last_attempt': None}
        with self._worker_lock:
            return {'state': ('BLOCKED' if self._daily_restore_failure else
                             'STOPPED' if self._daily_stopping else 'READY'),
                    'failure': self._daily_restore_failure,
                    'timezone': 'Asia/Kolkata', 'scheduled_time': '23:00',
                    'last_attempt': self._last_daily_result,
                    'publications': [dict(identity=r.identity, **r.data)
                                     for r in self._daily_receipts]}

    def work_status(self):
        with self._worker_lock:
            return {'state': ('RUNNING' if self._active_operation is not None else
                              'STOPPED' if self._worker_closed else 'IDLE'),
                    'owned_workers': int(self._active_operation is not None),
                    'queued_items': 0, 'cleanup_state': 'COMPLETE' if self._active_operation is None else 'OWNED',
                    'closed': self._worker_closed}

    def quiesce_daily(self):
        with self._worker_lock:
            self._daily_stopping = True

    def submit_daily(self, identity, parent=None, *, reporting_date=None, trigger='MANUAL'):
        if re.fullmatch(r'[0-9a-f]{32}',identity) is None:
            raise ValueError('SWING_RESEARCH_OPERATION_IDENTITY_INVALID')
        if not hasattr(self,'_daily_ready') or not self._daily_ready() or self._daily_restore_failure:
            raise ValueError('SWING_DAILY_NOT_READY')
        self.capture.commissioned_at()
        now=self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError('SWING_DAILY_CLOCK_UNAVAILABLE')
        day = reporting_date or now.astimezone(IST).date()
        if parent is not None and (type(parent) is not AdmissionTicket or parent._released
                or parent._owner is not self._daily_admission):
            raise ValueError('SWING_DAILY_PARENT_INVALID')
        ticket = (self._daily_admission.admit_root('SWING_RESEARCH') if parent is None
                  else parent.fork('SWING_RESEARCH'))
        if ticket is None:
            return {'state':'FENCED','operation_identity':identity}
        accepted = False
        try:
            with self._daily_shutdown_lock:
                with self._worker_lock:
                    if self._daily_shutdown_started() or self._daily_stopping or self._worker_closed or not self._daily_ready():
                        return {'state':'STOPPED','operation_identity':identity}
                    if self._active_operation is not None:
                        return {'state':'BUSY','operation_identity':identity}
                    # Register before leaving ordinary Exit's short lock. No I/O
                    # or research record exists before this registration wins.
                    self._active_operation = 'DAILY:' + identity
                    self._last_daily_result = {'state':'QUEUED','operation_identity':identity,
                                               'reporting_date':day.isoformat()}
                    try:
                        self._worker.submit(self._run_daily, identity, day, trigger, ticket)
                    except BaseException:
                        self._active_operation = None
                        raise
                    accepted = True
            return dict(self._last_daily_result)
        finally:
            if not accepted:
                ticket.release()

    def _run_daily(self, identity, day, trigger, ticket):
        result = {'state':'FAILED','operation_identity':identity,'reporting_date':day.isoformat()}
        try:
            with ticket.activate():
                prior=[r for r in self.research.store.records('DAILY_ATTEMPT')
                       if r.data['operation_identity']==identity]
                if len(prior)>1:raise ValueError('SWING_DAILY_OPERATION_CONFLICT')
                if prior:
                    if prior[0].data['reporting_date']!=day.isoformat():
                        raise ValueError('SWING_DAILY_OPERATION_CONFLICT')
                    result=dict(prior[0].data['result'],attempt_receipt=prior[0].identity)
                    return
                status=self.application.publication_status()
                control={k:status.get(k) for k in ('control','reconciliation_unavailable')}
                # Canonical archival read: stream large facts, no full MTF replay.
                history = self.application.retained_daily_research_sources(day)
                after=self.application.publication_status()
                if control!={k:after.get(k) for k in ('control','reconciliation_unavailable')}:
                    raise ValueError('SWING_DAILY_SOURCE_CHANGED')
                receipts=[]
                if self.capture.inbox is not None:
                    for kind in sorted(self.capture.inbox.KINDS):
                        for path in sorted((self.capture.inbox.root/kind).glob('*.json')):
                            if path.is_symlink():raise ValueError('SWING_DAILY_INBOX_INVALID')
                            envelope=json.loads(path.read_bytes())
                            self.capture.inbox.read(kind,envelope['event_identity'])
                            receipts.append({'kind':kind,'event_identity':envelope['event_identity'],
                                'sha256':sha256(path.read_bytes()).hexdigest(),
                                'captured_at':None,'capture_time_authority':'NOT_RETAINED_IN_LEGACY_ENVELOPE'})
                            if len(receipts)>5000:raise ValueError('SWING_DAILY_CAPACITY_UNAVAILABLE')
                result.update(self.research.record_daily(reporting_date=day,trigger=trigger,
                    history=history,attempt_identity=identity, publication_control=control,
                    capture_receipts=receipts,source_runtime=self._daily_source_runtime()))
        except Exception as error:
            result.update(state='FAILED',failure=type(error).__name__,
                          reason=str(error) if re.fullmatch(r'[A-Z0-9_]{1,120}',str(error)) else 'RETAINED_EVIDENCE_UNAVAILABLE')
        finally:
            # Retain completion/failure while registration and counted ticket
            # still own all final writes. No failure is an empty-day success.
            try:
                if 'attempt_receipt' in result:
                    value=None
                else:
                    value=record('DAILY_ATTEMPT',operation_identity=identity,reporting_date=day.isoformat(),
                    trigger=trigger,result=result,completed_at=self.clock().isoformat(),
                    authority='RETAINED_RESEARCH_ONLY')
                if value is not None:
                    with self.research.store.transaction():self.research.store.retain(value)
                    result['attempt_receipt']=value.identity
            except (ValueError,OSError):
                result['attempt_receipt']='UNAVAILABLE'
            try:
                receipts=self.research.store.records('DAILY_PUBLICATION')
            except (ValueError,OSError):
                receipts=()
            with self._worker_lock:
                self._daily_receipts=receipts
                self._last_daily_result=result
                self._active_operation=None
            ticket.release()

    def poll_daily(self):
        """Cheap post-READY dispatch in existing server pulse, no new timer."""
        from time import monotonic
        from uuid import uuid4
        if not hasattr(self,'_daily_ready') or self._daily_stopping or not self._daily_ready():
            return
        moment=monotonic()
        if moment < self._daily_next_check:return
        self._daily_next_check=moment+1
        if self._daily_restore_failure:return
        observed=self.clock()
        if observed.tzinfo is None or observed.utcoffset() is None:
            self._daily_restore_failure='DAILY_CLOCK_UNAVAILABLE'
            return
        now=observed.astimezone(IST)
        try:
            marker=self.capture.commissioned_at()
            if marker is None:return
            start=marker.astimezone(IST).date()
        except (OSError,ValueError):return
        today=now.date();last=today if now.time() >= time(23) else today-timedelta(days=1)
        if last < start:return
        epoch=today.isoformat()+('AFTER_2300' if last==today else 'CATCHUP')
        if epoch!=self._daily_epoch:
            self._daily_epoch=epoch;self._daily_attempted=set()
        # Finite catch-up: one day per existing worker task. Current due day
        # first, then oldest unexamined date; no futures backlog or retry loop.
        if (last-start).days>3660:
            self._daily_restore_failure='DAILY_CATCHUP_RANGE_UNAVAILABLE'
            return
        dates=[last]+[start+timedelta(days=i) for i in range((last-start).days)]
        day=next((d for d in dates if d not in self._daily_attempted),None)
        if day is None:return
        try:
            result=self.submit_daily(uuid4().hex,reporting_date=day,
                                     trigger='SCHEDULE' if day==today else 'CATCHUP')
        except (ValueError,OSError,RuntimeError,TypeError,KeyError):
            # A product recorder failure must not terminate the shared server
            # pulse. Block this component; never manufacture a publication.
            self._daily_restore_failure='DAILY_DISPATCH_UNAVAILABLE'
            return
        if result['state'] not in {'BUSY','FENCED','STOPPED'}:
            self._daily_attempted.add(day)
