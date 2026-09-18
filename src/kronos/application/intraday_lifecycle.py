"""Prospective lifecycle owner. Construction and GET projections are inert."""
from collections import deque
from threading import RLock, Thread
from datetime import timedelta
from typing import Callable
from kronos.intraday.wo11_lifecycle_contract import record, require, instant, digest, websocket_observation
from kronos.intraday.wo11_lifecycle import arm, observe, timing, gap, boundary, request_close, research_handoff, terminal_at, TERMINAL
from kronos.application.intraday_lifecycle_intake import load_intake, instrument_record
from kronos.provider.contracts.monitoring import MonitoringConnectionState


_MAX_QUEUED_WORK = 64
_MAX_QUEUED_BYTES = 32 * 1024
def _start_thread(operation, name):
    Thread(target=operation, name=name, daemon=True).start()


class IntradayLifecycleApplication:
    def __init__(self, *, futures, store, clock, session_source, timing_source,
                 operational_guard, contract_source=None,
                 background_runner: Callable[[Callable[[], None], str], object] = _start_thread):
        if not callable(background_runner):
            raise ValueError("WO11_BACKGROUND_RUNNER_INVALID")
        self.futures, self.store, self.clock = futures, store, clock
        self.session_source, self.timing_source = session_source, timing_source
        self.operational_guard = operational_guard
        self.contract_source = contract_source
        self._hub = None
        self._capability = lambda: None
        self._registrations = {}
        self._lock = RLock()
        self._projection_lock = RLock()
        self._prepared_cards = {}
        self._attached_track_identities = frozenset()
        self._timing_boundaries = {}
        self.last_failure = None
        self._background_runner = background_runner
        self._work_lock = RLock()
        self._work_queue = deque()
        self._pending_work = set()
        self._work_queued_bytes = 0
        self._work_generation = 0
        self._work_active = False
        self._work_state = "IDLE"
        self._work_failure = None
        self._work_cancel_requested = False
        self._pulse_pending = False
        self._continuity_gap_required = False
        self._continuity_state = "COMPLETE"
        self._coalesced_pulses = 0
        self._coalesced_work = 0
        self._saturation_count = 0
        self._rejected_work = 0
        self._completed_work = 0
        try:
            for current in self.store.restore():
                self._prepare_current(current)
        except (KeyError, OSError, TypeError, ValueError):
            self.last_failure = "WO11_RESTORATION_FAILED"

    def bind_monitoring(self, hub, capability):
        self._hub, self._capability = hub, capability

    def work_status(self):
        """Return bounded worker facts without entering lifecycle/store locks."""

        with self._work_lock:
            return {
                "state": self._work_state,
                "generation": self._work_generation if self._work_active else None,
                "owned_workers": int(self._work_active),
                "maximum_workers": 1,
                "queued_items": len(self._work_queue),
                "maximum_queued_items": _MAX_QUEUED_WORK,
                "queued_bytes": self._work_queued_bytes,
                "maximum_queued_bytes": _MAX_QUEUED_BYTES,
                "maximum_live_items": _MAX_QUEUED_WORK + 1,
                "retained_work_generations": 0,
                "maximum_retained_work_generations": 0,
                "coalesced_pulses": self._coalesced_pulses,
                "coalesced_work": self._coalesced_work,
                "saturation_count": self._saturation_count,
                "rejected_work": self._rejected_work,
                "completed_work": self._completed_work,
                "continuity": self._continuity_state,
                "failure": self._work_failure,
            }

    def request_pulse(self) -> bool:
        """Coalesce one runtime pulse behind the Intraday-owned worker."""

        return self._admit_work("PULSE", None, None, 0)

    def request_market_tick(self, track_identity, tick) -> bool:
        return self._admit_work("TICK", track_identity, tick, _work_size(tick))

    def request_connection_state(self, track_identity, state) -> bool:
        return self._admit_work(
            "CONNECTION", track_identity, state, _work_size(state)
        )

    def _admit_work(self, kind, track_identity, value, accounted_bytes):
        dispatch = None
        key = _work_key(kind, track_identity, value)
        with self._work_lock:
            if self._work_cancel_requested or self._work_state == "FAILED":
                self._rejected_work += 1
                return False
            if key in self._pending_work:
                self._coalesced_work += 1
                if kind == "PULSE":
                    self._coalesced_pulses += 1
                return True
            if (
                len(self._work_queue) >= _MAX_QUEUED_WORK
                or self._work_queued_bytes + accounted_bytes > _MAX_QUEUED_BYTES
            ):
                self._saturation_count += 1
                self._rejected_work += 1
                self._continuity_gap_required = True
                self._continuity_state = "GAP_PENDING"
                self._work_failure = "WO11_WORK_QUEUE_SATURATED"
                self.last_failure = self._work_failure
                return False
            self._work_queue.append(
                (kind, track_identity, value, accounted_bytes, key)
            )
            self._pending_work.add(key)
            self._work_queued_bytes += accounted_bytes
            if kind == "PULSE":
                self._pulse_pending = True
            if not self._work_active:
                self._work_generation += 1
                generation = self._work_generation
                self._work_active = True
                self._work_state = "RUNNING"
                dispatch = lambda: self._drain_work(generation)
        if dispatch is not None:
            try:
                self._background_runner(dispatch, "kronos-intraday-wo11")
            except Exception:
                with self._work_lock:
                    self._work_queue.clear()
                    self._pending_work.clear()
                    self._work_queued_bytes = 0
                    self._pulse_pending = False
                    self._work_active = False
                    self._work_state = "FAILED"
                    self._work_failure = "WO11_WORKER_DISPATCH_FAILED"
                    self._continuity_state = "INCOMPLETE"
                    self.last_failure = self._work_failure
                return False
        return True

    def _drain_work(self, generation):
        try:
            while True:
                with self._work_lock:
                    if generation != self._work_generation:
                        self._rejected_work += len(self._work_queue)
                        self._work_queue.clear()
                        self._pending_work.clear()
                        self._work_queued_bytes = 0
                        self._pulse_pending = False
                        return
                    if self._work_cancel_requested:
                        self._rejected_work += len(self._work_queue)
                        self._work_queue.clear()
                        self._pending_work.clear()
                        self._work_queued_bytes = 0
                        self._pulse_pending = False
                        self._work_state = "CANCELLATION_REQUESTED"
                        break
                    if self._work_queue:
                        kind, track_identity, value, accounted_bytes, key = (
                            self._work_queue.popleft()
                        )
                        self._work_queued_bytes -= accounted_bytes
                    elif self._continuity_gap_required:
                        self._continuity_gap_required = False
                        kind, track_identity, value, key = "GAP", None, None, None
                    else:
                        self._work_active = False
                        self._work_state = "IDLE"
                        return
                if kind == "PULSE":
                    self.pulse()
                elif kind == "TICK":
                    self._tick(track_identity, value)
                elif kind == "CONNECTION":
                    self._connection(track_identity, value)
                else:
                    self._retain_queue_gap()
                with self._work_lock:
                    if key is not None:
                        self._pending_work.discard(key)
                    if kind == "PULSE":
                        self._pulse_pending = False
                    if kind == "GAP":
                        self._continuity_state = "GAP_RETAINED"
                    self._completed_work += 1
        except BaseException:
            with self._work_lock:
                self._rejected_work += len(self._work_queue)
                self._work_queue.clear()
                self._pending_work.clear()
                self._work_queued_bytes = 0
                self._pulse_pending = False
                self._work_active = False
                self._work_state = "FAILED"
                self._work_failure = "WO11_WORKER_FAILED"
                self._continuity_state = "INCOMPLETE"
                self.last_failure = self._work_failure
            return
        with self._work_lock:
            self._work_active = False
            self._work_state = "TERMINATED"

    def _retain_queue_gap(self):
        with self._lock:
            tracks = tuple(self._registrations)
        for track_identity in tracks:
            self._connection(
                track_identity, MonitoringConnectionState.CONTEXT_INCOMPLETE
            )

    def _guard(self):
        if self._work_cancelled():
            raise ValueError("WO11_LIFECYCLE_TERMINATED")
        if self.operational_guard() is not True:
            raise ValueError("WO11_OPERATIONAL_AUTHORITY_UNAVAILABLE")

    def action(self, *, handoff_identity, action, action_identity):
        self._guard()
        if action not in {"ACTIVATE_PAPER", "OBSERVE", "DO_NOTHING"}:
            raise ValueError("LIVE_POSITION_NOT_COMMISSIONED_V1")
        h = self.futures.store.load(handoff_identity)
        subject = h.data["selection"]["comparison"]["subject"]
        now = self.clock()
        intake = load_intake(self.futures, handoff_identity, session=self.session_source(subject,now), now=now)
        if action == "DO_NOTHING":
            with self.store.transaction():
                retained = self.store.retain(record("WO11_ACTION_V1", action=action,
                    action_identity=action_identity, handoff_identity=handoff_identity, action_at=now))
            from kronos.application.notifications import notify_journal_persisted
            notify_journal_persisted(self.store, "ACTION", retained.identity)
            return retained
        truth = "PAPER_POSITION" if action == "ACTIVATE_PAPER" else "PAPER_OBSERVATION"
        transition = arm(intake, truth_class=truth, action_identity=action_identity, action_at=now)
        claim = next(r.data["claim"] for r in transition.evidence if r.schema=="WO11_AUTHORIZATION_V1")
        with self._lock, self.store.transaction():
            current = self.store.current(claim)
            if current is not None:
                a = self.store.load(current.data["authorization_identity"])
                old = self.store.load(a.data["action_identity"])
                if old.data["action_identity"] == action_identity and a.data["truth_class"] == truth:
                    return current
                raise ValueError("WO11_OPPORTUNITY_EXPRESSION_ALREADY_CLAIMED")
            result = self.store.publish(transition, claim=claim, previous=None)
        self._prepare_current(result)
        self._attach(result, restored=False)
        return result

    def _commit(self, old, transition):
        if transition.current == old:
            for item in transition.evidence:
                self.store.retain(item)
            return old
        auth = self.store.load(old.data["authorization_identity"])
        result = self.store.publish(transition, claim=auth.data["claim"], previous=old.identity)
        if result.data["state"] in TERMINAL:
            metric = self.store.load(result.data["metrics"]) if result.data["metrics"] else None
            self.store.retain(research_handoff(result, retained_metrics=metric))
            self.store.retain(record("WO11_CLOSURE_V1", current_identity=result.identity,
                authorization_identity=result.data["authorization_identity"], at=result.data["updated_at"],
                state=result.data["display_state"], exit=result.data["exit"],
                exit_reason=result.data["exit_reason"], terminal_status=result.data["terminal_status"]))
        self._prepare_current(result)
        return result

    def close_track(self, *, claim, action_identity):
        self._guard()
        with self._lock, self.store.transaction():
            current = self.store.current(claim)
            if current is None:
                raise ValueError("WO11_TRACK_NOT_FOUND")
            return self._commit(current, request_close(current, at=self.clock(), reason="SPONSOR_EXIT", source_identity=action_identity))

    def _current_for(self, track):
        auth = self.store.load(track.data["authorization_identity"])
        return self.store.current(auth.data["claim"])

    def _attach(self, current, *, restored):
        if (
            self._work_cancelled()
            or current.data["state"] in TERMINAL
            or current.data["track_identity"] in self._registrations
        ):
            return
        capability = self._capability()
        if self._hub is None or capability is None or getattr(capability,"active",False) is not True:
            return
        consumer = _Consumer(self, current.data["track_identity"])
        registration = self._hub.open(capability, consumer)
        registration.subscribe((instrument_record(current.data["intake"]["future"]),))
        self._registrations[consumer.track_identity] = (registration, capability)
        self._attached_track_identities = frozenset(self._registrations)
        try:
            if self._dispose_cancelled_registration(
                consumer.track_identity, registration
            ):
                return
            if restored:
                with self.store.transaction():
                    current = self._commit(current, gap(current, at=self.clock(), reason="PROCESS_RESTORATION"))
            with self.store.transaction():
                self.store.retain(record("WO11_MONITORING_V1", authorization_identity=current.data["authorization_identity"],
                    track_identity=consumer.track_identity, intake=current.data["intake"],
                    truth_class=current.data["truth_class"], state="ATTACHING", at=self.clock(),
                    capability_identity=getattr(capability,"capability_identity",None), owner_identity=consumer.owner_identity))
            registration.connect()
            self._dispose_cancelled_registration(
                consumer.track_identity, registration
            )
        except Exception:
            self._registrations.pop(consumer.track_identity,None)
            self._attached_track_identities = frozenset(self._registrations)
            registration.disconnect()
            raise

    def _work_cancelled(self):
        with self._work_lock:
            return self._work_cancel_requested

    def _dispose_cancelled_registration(self, track_identity, registration):
        if not self._work_cancelled():
            return False
        attached = self._registrations.get(track_identity)
        if attached is not None and attached[0] is registration:
            self._registrations.pop(track_identity, None)
            self._attached_track_identities = frozenset(self._registrations)
        registration.disconnect()
        return True

    def _authority_failure(self, current, error, now):
        code = str(error) if isinstance(error, ValueError) and str(error).startswith("WO11_") else "WO11_SOURCE_UNAVAILABLE"
        superseded = code in {"WO11_HANDOFF_SUPERSEDED", "WO11_UPSTREAM_SUPERSEDED"}
        check = record("WO11_AUTHORITY_CHECK_V1", authorization_identity=current.data["authorization_identity"],
            handoff_identity=current.data["intake"]["handoff_identity"], at=now, reason=code,
            result="SUPERSEDED" if superseded else "UNAVAILABLE")
        with self.store.transaction():
            self.store.retain(check)
            transition = request_close(current,at=now,reason="UPSTREAM_SUPERSEDED",source_identity=check.identity) if superseded and current.data["entry"] is None else gap(current,at=now,reason=code)
            return self._commit(current, transition)

    def _contract_terminal(self, current, now):
        if now >= terminal_at(current):
            return boundary(current, at=now)
        i = current.data["intake"]
        if i["contract"]["active_mcx"] is not None:
            if self.contract_source is None:
                raise ValueError("WO11_CURRENT_CONTRACT_SOURCE_UNAVAILABLE")
            latest = self.contract_source(i["subject"])
            if latest is None:
                raise ValueError("WO11_CURRENT_CONTRACT_SOURCE_UNAVAILABLE")
            latest.__post_init__()
            if latest.active_binding.derivative_contract_id != i["contract"]["active_mcx"]["active_binding"]["derivative_contract_id"]:
                return boundary(current, at=now, contract_evidence=latest)
        return None

    def pulse(self):
        """Called by the runtime service loop, never by a GET projection."""
        with self._lock:
            try:
                self._guard()
            except (ValueError,RuntimeError):
                return
            for current in self.store.restore():
                now = self.clock(); i = current.data["intake"]
                attached = self._registrations.get(current.data["track_identity"])
                if attached is not None and (now >= terminal_at(current) or not getattr(attached[1], "active", False) or self._capability() is not attached[1]):
                    self._registrations.pop(current.data["track_identity"])
                    self._attached_track_identities = frozenset(self._registrations)
                    attached[0].disconnect()
                    current = self._current_for(current)
                if current.data["state"] in TERMINAL:
                    continue
                if now >= terminal_at(current):
                    with self.store.transaction():
                        self._commit(current,boundary(current,at=now))
                    continue
                try:
                    terminal = self._contract_terminal(current, now)
                    if terminal is not None:
                        with self.store.transaction():
                            self._commit(current, terminal)
                        continue
                    # Currentness cancels unentered eligibility only. The original
                    # WO10 thesis is not a post-entry reassessment/exit authority.
                    if current.data["entry"] is None:
                        load_intake(self.futures,i["handoff_identity"],session=self.session_source(i["subject"],now),now=now,arming=False)
                except (ValueError,OSError,KeyError,TypeError) as error:
                    self._authority_failure(current,error,now)
                    continue
                try:
                    self._attach(current,restored=True)
                    if current.data["track_identity"] not in self._registrations:
                        continue
                    # One read per new possible 5M boundary; never a historical search.
                    key=int(now.timestamp())//300
                    if current.data["state"]=="AWAITING_TIMING" and self._timing_boundaries.get(current.data["track_identity"])!=key:
                        self._timing_boundaries[current.data["track_identity"]]=key
                        qualified=self.timing_source(current)
                        with self.store.transaction():
                            self._commit(self._current_for(current),timing(self._current_for(current),qualified))
                except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
                    self.last_failure = str(error) if isinstance(error,ValueError) else "WO11_SOURCE_UNAVAILABLE"
            # Preserve registration for closed timestamp-conflict evidence until shutdown;
            # terminal tracks never resume price/model consequences.

    def _tick(self, track_identity, tick):
        with self._lock:
            try:
                self._guard()
                auth=self.store.load(track_identity)
                current=self.store.current(auth.data["claim"])
                i=current.data["intake"];now=self.clock()
                attached = self._registrations.get(track_identity)
                if attached is None or not getattr(attached[1], "active", False) or self._capability() is not attached[1]:
                    raise ValueError("WO11_MONITORING_CAPABILITY_UNAVAILABLE")
                if current.data["state"] not in TERMINAL:
                    try:
                        terminal = self._contract_terminal(current, now)
                    except (ValueError,OSError,KeyError,TypeError) as error:
                        self._authority_failure(current,error,now)
                        return
                    if terminal is not None:
                        with self.store.transaction():
                            self._commit(current, terminal)
                        return
                if current.data["entry"] is None and current.data["state"] not in TERMINAL:
                    try:
                        load_intake(self.futures,i["handoff_identity"],session=self.session_source(i["subject"],now),now=now,arming=False)
                    except (ValueError,OSError,KeyError,TypeError) as error:
                        self._authority_failure(current,error,now)
                        return
                session=self.session_source(i["subject"],tick.observed_at)
                observed=websocket_observation(tick,authorization_identity=track_identity,
                    instrument=instrument_record(i["future"]), session_identity=session.schedule.session_id if session.schedule else None,
                    expected_session_identity=i["session_identity"], causal_at=current.data["armed_at"],decision_at=now)
                with self.store.transaction():
                    next_state=self._commit(current,observe(current,observed))
                    if observed.data["reason"] in {"WEBSOCKET_CONTINUITY_NOT_ESTABLISHED","WEBSOCKET_OBSERVATION_STALE","WEBSOCKET_RECOVERED_OBSERVATION"} and next_state.data["state"] not in TERMINAL:
                        self._commit(next_state,gap(next_state,at=now,reason=observed.data["reason"]))
            except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
                self.last_failure = str(error) if isinstance(error,ValueError) else "WO11_OBSERVATION_UNAVAILABLE"

    def _connection(self, track_identity, state):
        if getattr(state,"value",state)=="CONNECTED":
            return
        with self._lock, self.store.transaction():
            auth=self.store.load(track_identity);current=self.store.current(auth.data["claim"])
            if current.data["state"] not in TERMINAL:
                self._commit(current,gap(current,at=self.clock(),reason=str(state)))

    def projection(self):
        with self._projection_lock:
            prepared = tuple(self._prepared_cards.values())
        attached = self._attached_track_identities
        cards = [
            dict(
                card,
                monitoring=(
                    card["retained_monitoring"]
                    if card["track_identity"] in attached
                    else "UNATTACHED"
                ),
            )
            for card in prepared
        ]
        for card in cards:
            card.pop("retained_monitoring")
            card.pop("track_identity")
        return dict(cards=cards,last_failure=self.last_failure,live="LIVE_POSITION_NOT_COMMISSIONED_V1")

    def _prepare_current(self, current):
        d=current.data;auth=self.store.load(d["authorization_identity"])
        metric=None if d["metrics"] is None else self.store.load(d["metrics"]).data
        card=dict(identity=current.identity,claim=auth.data["claim"],subject=d["intake"]["subject"],
            comparison_identity=d["intake"]["comparison_identity"],truth_class=d["truth_class"],lots=1,
            state=d["display_state"],terminal=d["state"] in TERMINAL,entry=d["entry"],exit=d["exit"],
            exit_reason=d["exit_reason"],terminal_status=d["terminal_status"],
            stop=d["intake"]["stop"],target=d["intake"]["target"],metrics=metric,
            retained_monitoring=d["monitoring"],track_identity=d["track_identity"],
            gaps=d["gaps"],selected_lots_context=d["intake"]["selected_lots"],
            original_thesis_invalidation=d["intake"].get("invalidation"),
            post_entry_analytical_invalidation=d["post_entry_analytical_invalidation"])
        with self._projection_lock:
            self._prepared_cards[auth.data["claim"]] = card

    def portfolio_observation(self, track_identity, retained):
        """Read exact owner/latest accepted observation; never acquire market data."""
        result = dict(monitoring="UNAVAILABLE", price=None, observed_at=None)
        retained = retained or {}
        with self._lock:
            if retained.get("monitoring") == "INTERRUPTED" or retained.get("baseline_required"):
                return dict(result, monitoring="INTERRUPTED")
            attached = self._registrations.get(track_identity)
            if attached is None:
                return dict(result, monitoring="IDLE" if self._hub is not None else "UNAVAILABLE")
            registration, capability = attached
            if not getattr(capability, "active", False) or not registration.active:
                return dict(result, monitoring="INTERRUPTED")
            if getattr(registration.connection_state, "value", None) != "CONNECTED":
                return dict(result, monitoring="INTERRUPTED")
            result["monitoring"] = "LIVE"
            # Match process-local fact and exact owned contract to the last fact
            # accepted by WO11. A newer rejected tick cannot expose an old price.
            for tick in self._hub.latest_market_ticks:
                owners = self._hub.subscription_owner_identities(tick.instrument)
                if "INTRADAY-WO11-LIFECYCLE:" + track_identity not in owners:
                    continue
                from dataclasses import asdict
                from kronos.intraday.wo11_lifecycle_contract import digest
                if "WO11_SOURCE_FACT-" + digest(asdict(tick)) != retained.get("last_fact_identity"):
                    continue
                if (tick.connection_id != retained.get("last_connection")
                        or tick.observed_at != instant(retained.get("last_observed_at"))
                        or tick.source_sequence != retained.get("last_sequence")
                        or str(tick.last_price) != retained.get("last_price")
                        or tick.recovered or not tick.session_continuous
                        or not tick.ordering_deterministic
                        or not tick.previous_interval_available):
                    continue
                lateness = (tick.received_at - tick.observed_at).total_seconds()
                if 0 <= lateness <= 5 and retained.get("last_fact_identity"):
                    result.update(price=retained["last_price"], observed_at=retained["last_observed_at"])
            return result

    def journal_monitoring_state(self, track_identity):
        """Read-only exact owner state for WO-14; creates no owner or subscription."""
        if not isinstance(track_identity, str):
            raise ValueError("WO11_TRACK_IDENTITY_REQUIRED")
        authorization = self.store.load(track_identity)
        current = self.store.current(authorization.data["claim"])
        if current is None:
            raise ValueError("WO11_TRACK_NOT_FOUND")
        data = current.data
        if data["state"] in TERMINAL:
            return "NOT_REQUIRED"
        if data["monitoring"] == "INTERRUPTED":
            return "INTERRUPTED"
        attached = self._registrations.get(track_identity)
        if attached is not None:
            return "LIVE" if getattr(attached[1], "active", False) else "INTERRUPTED"
        capability = self._capability()
        if self._hub is None or capability is None:
            return "UNAVAILABLE"
        return "IDLE" if getattr(capability, "active", False) else "INTERRUPTED"

    def shutdown(self):
        with self._work_lock:
            self._work_cancel_requested = True
            if self._work_active:
                self._work_state = "CANCELLATION_REQUESTED"
            else:
                self._rejected_work += len(self._work_queue)
                self._work_queue.clear()
                self._pending_work.clear()
                self._work_queued_bytes = 0
                self._pulse_pending = False
                self._work_state = "TERMINATED"
        registrations = self._registrations
        self._registrations = {}
        self._attached_track_identities = frozenset()
        for registration,_ in tuple(registrations.values()):
            registration.disconnect()


class _Consumer:
    def __init__(self,application,track_identity):
        self.application,self.track_identity=application,track_identity
        self.owner_identity="INTRADAY-WO11-LIFECYCLE:"+track_identity
    def on_market_tick(self,tick):
        self.application.request_market_tick(self.track_identity,tick)
    def on_order_update(self,update):
        pass  # Orders are not model prices or broker-verified lifecycle facts.
    def on_connection_state(self,state):
        self.application.request_connection_state(self.track_identity,state)


def _work_size(value):
    """Bound the retained representation of a small callback fact."""

    return len(repr(value).encode("utf-8"))


def _work_key(kind, track_identity, value):
    if kind == "PULSE":
        return (kind,)
    if kind == "CONNECTION":
        return (kind, track_identity, getattr(value, "value", value))
    return (
        kind,
        track_identity,
        getattr(value, "connection_id", None),
        getattr(value, "source_sequence", None),
        getattr(value, "observed_at", None),
        getattr(value, "last_price", None),
    )
