"""Prospective lifecycle owner. Construction and GET projections are inert."""
from threading import RLock
from datetime import timedelta
from kronos.intraday.wo11_lifecycle_contract import record, require, instant, digest, websocket_observation
from kronos.intraday.wo11_lifecycle import arm, observe, timing, gap, boundary, request_close, research_handoff, terminal_at, TERMINAL
from kronos.application.intraday_lifecycle_intake import load_intake, instrument_record


class IntradayLifecycleApplication:
    def __init__(self, *, futures, store, clock, session_source, timing_source, operational_guard, contract_source=None):
        self.futures, self.store, self.clock = futures, store, clock
        self.session_source, self.timing_source = session_source, timing_source
        self.operational_guard = operational_guard
        self.contract_source = contract_source
        self._hub = None
        self._capability = lambda: None
        self._registrations = {}
        self._lock = RLock()
        self._timing_boundaries = {}
        self.last_failure = None

    def bind_monitoring(self, hub, capability):
        self._hub, self._capability = hub, capability

    def _guard(self):
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
                return self.store.retain(record("WO11_ACTION_V1", action=action,
                    action_identity=action_identity, handoff_identity=handoff_identity, action_at=now))
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
        if current.data["state"] in TERMINAL or current.data["track_identity"] in self._registrations:
            return
        capability = self._capability()
        if self._hub is None or capability is None or getattr(capability,"active",False) is not True:
            return
        consumer = _Consumer(self, current.data["track_identity"])
        registration = self._hub.open(capability, consumer)
        registration.subscribe((instrument_record(current.data["intake"]["future"]),))
        self._registrations[consumer.track_identity] = (registration, capability)
        try:
            if restored:
                with self.store.transaction():
                    current = self._commit(current, gap(current, at=self.clock(), reason="PROCESS_RESTORATION"))
            with self.store.transaction():
                self.store.retain(record("WO11_MONITORING_V1", authorization_identity=current.data["authorization_identity"],
                    track_identity=consumer.track_identity, intake=current.data["intake"],
                    truth_class=current.data["truth_class"], state="ATTACHING", at=self.clock(),
                    capability_identity=getattr(capability,"capability_identity",None), owner_identity=consumer.owner_identity))
            registration.connect()
        except Exception:
            self._registrations.pop(consumer.track_identity,None)
            registration.disconnect()
            raise

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
        cards=[]
        for current in self.store.restore():
            d=current.data;auth=self.store.load(d["authorization_identity"])
            metric=None if d["metrics"] is None else self.store.load(d["metrics"]).data
            cards.append(dict(identity=current.identity,claim=auth.data["claim"],subject=d["intake"]["subject"],
                comparison_identity=d["intake"]["comparison_identity"],truth_class=d["truth_class"],lots=1,
                state=d["display_state"],terminal=d["state"] in TERMINAL,entry=d["entry"],exit=d["exit"],
                exit_reason=d["exit_reason"],terminal_status=d["terminal_status"],
                stop=d["intake"]["stop"],target=d["intake"]["target"],metrics=metric,
                monitoring=d["monitoring"] if d["track_identity"] in self._registrations else "UNATTACHED",
                gaps=d["gaps"],selected_lots_context=d["intake"]["selected_lots"],
                original_thesis_invalidation=d["intake"].get("invalidation"),
                post_entry_analytical_invalidation=d["post_entry_analytical_invalidation"]))
        return dict(cards=cards,last_failure=self.last_failure,live="LIVE_POSITION_NOT_COMMISSIONED_V1")

    def shutdown(self):
        for registration,_ in tuple(self._registrations.values()):
            registration.disconnect()
        self._registrations.clear()


class _Consumer:
    def __init__(self,application,track_identity):
        self.application,self.track_identity=application,track_identity
        self.owner_identity="INTRADAY-WO11-LIFECYCLE:"+track_identity
    def on_market_tick(self,tick):
        self.application._tick(self.track_identity,tick)
    def on_order_update(self,update):
        pass  # Orders are not model prices or broker-verified lifecycle facts.
    def on_connection_state(self,state):
        self.application._connection(self.track_identity,state)
