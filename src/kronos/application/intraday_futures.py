"""Explicit prospective WO-10 orchestration; construction/restoration is inert."""
from datetime import datetime, timezone
from time import monotonic

from kronos.intraday.wo10_futures_contract import record, require, moment, fresh, digest, normalize
from kronos.intraday.wo10_construction import validate_intake, construct_plan
from kronos.intraday.wo10_futures_market import select_future, build_snapshot, map_future, require_session
from kronos.intraday.wo10_futures_risk import assess_risk, risk_advisory
from kronos.intraday.wo10_futures_store import FuturesStore


class IntradayFuturesApplication:
    def __init__(self, store, wo09_store, *, clock=None, operational_guard=None, structural_loader=None, acquisition_source=None):
        self.store = store
        self.wo09 = wo09_store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.operational_guard = operational_guard
        self.structural_loader = structural_loader
        self.acquisition_source = acquisition_source
        # Only snapshots commissioned in this process can be selected as current.
        self._current_process_snapshots = set()
        self._market_authorities = {}

    def _guard(self):
        if self.operational_guard is None or self.operational_guard() is not True:
            raise ValueError("WO10_OPERATIONAL_AUTHORITY_UNAVAILABLE")

    def _intake(self, handoff, now):
        r = self.wo09.load_readiness(handoff.readiness_identity)
        p = self.wo09.load_pointer(handoff.canonical_subject_identity)
        validate_intake(handoff, r, p, now=now, session_identity=handoff.session_identity)
        return r, p

    def construct_current(self, *, handoff_identity, request_identity):
        """Only exact identities enter the Sponsor composition; no geometry inputs."""
        self._guard()
        with self.store.transaction(construction=True):
            return self._construct_current(handoff_identity=handoff_identity, request_identity=request_identity)

    def _construct_current(self, *, handoff_identity, request_identity):
        from kronos.intraday.native_structural_selection import UNAVAILABLE
        from kronos.intraday.wo10_native_adapter import adapt_native
        self._guard()
        if not all(type(v) is str and v.strip() and "/" not in v and "\\" not in v
                   for v in (handoff_identity, request_identity)):
            raise ValueError("WO10_REQUEST_IDENTITY_REQUIRED")
        handoff = self.wo09.load_handoff(handoff_identity)
        readiness, pointer = self._intake(handoff, self.clock())
        # An identity is a commissioned attempt, including unavailable outcomes.
        previous = [r for r in self.store.records("WO10_CONSTRUCTION_OPERATION_V1")
                    if r.data["request_identity"] == request_identity]
        if previous:
            if len(previous) != 1 or previous[0].data["handoff_identity"] != handoff_identity:
                raise ValueError("WO10_REQUEST_IDEMPOTENCY_CONFLICT")
            result_id = previous[0].data.get("result_identity")
            if result_id is None:
                raise ValueError("WO10_INTERRUPTED_OPERATION_REQUIRES_NEW_REQUEST")
            return self.store.load(result_id)
        if any(r.data["request_identity"] == request_identity for r in self.store.records("WO10_CONSTRUCTION_REQUEST_V1")):
            raise ValueError("WO10_INTERRUPTED_OPERATION_REQUIRES_NEW_REQUEST")
        self.store.retain(record("WO10_CONSTRUCTION_REQUEST_V1", request_identity=request_identity,
            handoff_identity=handoff_identity, readiness_identity=readiness.readiness_identity,
            state="STARTED", attribution="EXPLICIT_CONSTRUCTION_REQUEST_ACTOR_NOT_ESTABLISHED", created_at=self.clock()))
        try:
            if self.structural_loader is None:
                raise ValueError(UNAVAILABLE)
            selection = self.structural_loader.load(handoff, now=self.clock())
            if selection.data.get("result") == "NOT_ESTABLISHED":
                return self._unavailable(handoff, request_identity, UNAVAILABLE, native_selection=selection)
            readiness, pointer = self._intake(handoff, self.clock())
            adapter, evidence, population = adapt_native(selection, handoff, readiness, pointer, now=self.clock())
            self._guard(); self._intake(handoff, self.clock())
        except (ValueError, OSError, KeyError, TypeError) as error:
            reason = str(error) if isinstance(error, ValueError) else "STRUCTURAL_SOURCE_INTEGRITY_INVALID"
            return self._unavailable(handoff, request_identity, reason)
        # Freeze source lineage before any possible acquisition. Recheck currentness
        # before retaining either a plan or the later comparison.
        with self.store.transaction():
            self._intake(handoff, self.clock())
            plan = construct_plan(adapter, evidence, population, now=self.clock())
            self._intake(handoff, self.clock())
            self.store.retain(plan)
        if plan.data["state"] != "AVAILABLE":
            return self._unavailable(handoff, request_identity, plan.data["reason"])
        if self.acquisition_source is None:
            return self._unavailable(handoff, request_identity, "WO10_ACQUISITION_COMPOSITION_UNAVAILABLE", plan=plan,
                                     state="FUTURE_SNAPSHOT_UNAVAILABLE")
        self._guard(); self._intake(handoff, self.clock())
        try:
            inputs = self.acquisition_source(handoff, plan)
            if not callable(inputs.get("authority_source")):
                raise ValueError("WO10_CURRENT_MARKET_AUTHORITY_UNAVAILABLE")
            comparison = self.evaluate(request_identity=request_identity, adapter=adapter, geometry_evidence=evidence,
                                       target_population=population, **inputs)
        except (ValueError, OSError, KeyError, TypeError) as error:
            reason = str(error) if isinstance(error, ValueError) else "WO10_ACQUISITION_INPUT_UNAVAILABLE"
            return self._unavailable(handoff, request_identity, reason, plan=plan, state="FUTURE_SNAPSHOT_UNAVAILABLE")
        self.store.retain(record("WO10_CONSTRUCTION_OPERATION_V1", request_identity=request_identity,
            handoff_identity=handoff_identity, native_selection_identity=selection.identity,
            native_selection_integrity=selection.integrity, target_population_identity=selection.data["target_population_identity"],
            result_identity=comparison.identity, state="COMPLETED", created_at=self.clock()))
        return comparison

    def _unavailable(self, handoff, request_identity, reason, *, plan=None, state="TRADE_PLAN_UNAVAILABLE", native_selection=None):
        with self.store.transaction():
            self._guard(); self._intake(handoff, self.clock())
            if plan is None:
                plan = record("WO10_CANONICAL_TRADE_PLAN_V1", state="TRADE_PLAN_UNAVAILABLE", reason=reason,
                    subject=handoff.canonical_subject_identity, direction=handoff.direction, wo09=handoff,
                    native_selection_identity=None if native_selection is None else native_selection.identity,
                    structural_reasons=[] if native_selection is None else native_selection.data["reasons"],
                    session_identity=handoff.session_identity, created_at=self.clock(), entry=None, stop=None, target=None,
                    invalidation=None, model_rr=None)
                self.store.retain(plan)
            result = record("WO10_CONSTRUCTION_UNAVAILABLE_V1", state=state, reason=reason,
                subject=handoff.canonical_subject_identity, direction=handoff.direction,
                handoff_identity=handoff.handoff_identity, readiness_identity=handoff.readiness_identity,
                pointer_integrity=handoff.current_pointer_integrity, plan_identity=plan.identity,
                created_at=self.clock(), request_identity=request_identity,
                request_attempts=max((r.data.get("request_attempts", 0) for r in self.store.records("WO10_ACQUISITION_OPERATION_V1")
                    if r.data["request_identity"] == request_identity), default=0))
            self._intake(handoff, self.clock())
            self.store.retain(result)
            self.store.retain(record("WO10_CONSTRUCTION_OPERATION_V1", request_identity=request_identity,
                handoff_identity=handoff.handoff_identity, result_identity=result.identity,
                state="UNAVAILABLE", created_at=self.clock()))
            return result

    def evaluate(self, *, request_identity, adapter, geometry_evidence, target_population,
                 master, provider, session_source, underlying=None, active_mcx=None,
                 economics=None, configuration=None, acquire_master=None, authority_source=None):
        self._guard()
        if not isinstance(request_identity, str) or not request_identity.strip():
            raise ValueError("WO10_REQUEST_IDENTITY_REQUIRED")
        now = self.clock()
        handoff = adapter.wo09
        readiness, pointer = self._intake(handoff, now)
        adapter.__post_init__()
        session = session_source(now)
        require_session(session, now, exchange="MCX" if handoff.market_family == "MCX" else "NSE")
        authority = dict(master=master, underlying=underlying, active_mcx=active_mcx, economics=economics, configuration=configuration)
        def revalidate_market():
            if authority_source is not None and digest({k:v for k,v in authority_source().items() if k not in {"configuration", "economics"}}) != digest({k:v for k,v in authority.items() if k not in {"configuration", "economics"}}):
                raise ValueError("WO10_CURRENT_MARKET_AUTHORITY_CHANGED")
        revalidate_market()
        fingerprint = digest(dict(adapter=adapter, geometry=geometry_evidence, targets=target_population,
                                  master=None if master is None else master.snapshot_identity,
                                  config=configuration, underlying=underlying, active_mcx=active_mcx, economics=economics))
        with self.store.transaction():
            for prior in self.store.records("WO10_ACQUISITION_OPERATION_V1"):
                d = prior.data
                if d["request_identity"] == request_identity:
                    if d["fingerprint"] != fingerprint:
                        raise ValueError("WO10_REQUEST_IDEMPOTENCY_CONFLICT")
                    if d["state"] == "COMPLETED":
                        return self.store.load(d["comparison_identity"])
                    if d["state"] == "FAILED":
                        raise ValueError(d["reason"])
            # An interrupted STARTED operation must never be retried implicitly.
            if any(x.data["request_identity"] == request_identity for x in self.store.records("WO10_ACQUISITION_OPERATION_V1")):
                raise ValueError("WO10_INTERRUPTED_OPERATION_REQUIRES_NEW_REQUEST")
            prior_opportunities = [x for x in self.store.records("WO10_OPPORTUNITY_V1")
                                   if x.data["readiness_identity"] == readiness.readiness_identity]
            if len(prior_opportunities) > 1:
                raise ValueError("WO10_OPPORTUNITY_DENOMINATOR_CONFLICT")
            opportunity = prior_opportunities[0] if prior_opportunities else self.store.retain(
                record("WO10_OPPORTUNITY_V1", readiness_identity=readiness.readiness_identity,
                       readiness_integrity=readiness.integrity_identity, subject=readiness.canonical_subject_identity,
                       wo07f_identity=readiness.wo07f_identity, session_identity=readiness.session_identity,
                       first_reached_at=now))
            started = self.store.retain(record("WO10_ACQUISITION_OPERATION_V1", request_identity=request_identity,
                                              fingerprint=fingerprint, opportunity_identity=opportunity.identity,
                                              state="STARTED", started_at=now, request_attempts=0))
            attempts = 0
            try:
                plan = construct_plan(adapter, geometry_evidence, target_population, now=now)
                self._guard(); self._intake(handoff, self.clock())
                self.store.retain(plan)
                if plan.data["state"] != "AVAILABLE":
                    raise ValueError("WO10_TRADE_PLAN_UNAVAILABLE")
                self._guard(); self._intake(handoff, self.clock())
                if master is None and acquire_master is not None:
                    attempts += 1
                    began_master = monotonic()
                    master = acquire_master(request_identity=request_identity + ":MASTER", timeout=7)
                    if monotonic() - began_master > 7:
                        raise ValueError("WO10_MASTER_ACQUISITION_TIMEOUT")
                contract, instruments = select_future(master, handoff, session, now=now,
                                                       underlying=underlying, active_mcx=active_mcx, economics=economics)
                self.store.retain(contract)
                self._guard(); self._intake(handoff, self.clock()); revalidate_market()
                self.store.retain(record("WO10_ACQUISITION_OPERATION_V1", request_identity=request_identity,
                                        fingerprint=fingerprint, state="QUOTE_REQUESTED", operation_identity=started.identity,
                                        started_at=self.clock(), instruments=[x.provider_record_identity for x in instruments],
                                        request_attempts=attempts+1, timeout_seconds=7, automatic_retries=0))
                began = monotonic(); attempts += 1
                quotes = provider.full_quotes(instruments, request_identity=request_identity + ":QUOTE", timeout=7)
                elapsed = monotonic() - began
                completed = self.clock()
                self.store.retain(record("WO10_ACQUISITION_OPERATION_V1", request_identity=request_identity,
                                        fingerprint=fingerprint, state="QUOTE_RECEIVED", operation_identity=started.identity,
                                        quote_request_identity=request_identity + ":QUOTE", received_at=completed,
                                        request_attempts=attempts, elapsed_seconds=elapsed, quotes=quotes,
                                        authority="FACTS_ONLY_NOT_CURRENT_SNAPSHOT"))
                if elapsed > 7:
                    raise ValueError("WO10_QUOTE_TIMEOUT")
                self._guard(); self._intake(handoff, completed)
                c = contract.data
                key = dict(contract_record=c["future"]["provider_record_identity"], provider=c["future"]["provider"],
                           master_identity=c["master_identity"], session_identity=c["session_identity"])
                baselines = [x for x in self.store.records("SESSION_FIRST_OBSERVED_OI_BASELINE_V1") if x.data["key"] == key]
                if len(baselines) > 1:
                    raise ValueError("WO10_OI_BASELINE_CONFLICT")
                snapshot, baseline = build_snapshot(contract, quotes, operation_identity=started.identity,
                                                     request_identity=request_identity + ":QUOTE", received_at=completed,
                                                     session=session_source(completed), baseline=baselines[0] if baselines else None)
                self.store.retain(snapshot)
                if baseline is not None:
                    self.store.retain(baseline)
                expression = self.store.retain(map_future(plan, snapshot))
                fact, advisory = assess_risk(expression, configuration, now=completed)
                if configuration is not None:
                    self.store.retain(configuration)
                self.store.retain(fact); self.store.retain(advisory)
                state = expression.data["state"]
                comparison = record("WO10_SPONSOR_COMPARISON_V1", subject=handoff.canonical_subject_identity,
                                    direction=handoff.direction, readiness_identity=handoff.readiness_identity,
                                    handoff_identity=handoff.handoff_identity, opportunity_identity=opportunity.identity,
                                    plan_identity=plan.identity, snapshot_identity=snapshot.identity,
                                    expression_identity=expression.identity, risk_fact_identity=fact.identity,
                                    advisory_identity=advisory.identity, reference_identity=advisory.data["reference_identity"], created_at=completed,
                                    executability=state, option_buy="NOT_COMMISSIONED_V1", option_sell="NOT_COMMISSIONED_V1")
                self._guard(); self._intake(handoff, self.clock()); revalidate_market()
                # Re-resolve against the current session/date before publishing.
                check, _ = select_future(master, handoff, session_source(self.clock()), now=self.clock(),
                                         underlying=underlying, active_mcx=active_mcx, economics=economics)
                if check.data["future"] != contract.data["future"]:
                    raise ValueError("WO10_FUTURE_CONTRACT_CHANGED")
                prior = self.store.current(handoff.canonical_subject_identity)
                self.store.publish(comparison, previous=None if prior is None else prior.identity)
                self.store.retain(record("WO10_ACQUISITION_OPERATION_V1", request_identity=request_identity,
                                        fingerprint=fingerprint, opportunity_identity=opportunity.identity,
                                        state="COMPLETED", operation_identity=started.identity,
                                        started_at=now, completed_at=completed, request_attempts=attempts,
                                        comparison_identity=comparison.identity))
                self._current_process_snapshots.add(snapshot.identity)
                if authority_source is not None:
                    self._market_authorities[snapshot.identity] = (authority_source, digest({k:v for k,v in authority.items() if k not in {"configuration", "economics"}}))
                return comparison
            except Exception as error:
                code = str(error) if isinstance(error, ValueError) and str(error).startswith("WO10_") else "WO10_ACQUISITION_OR_CONSTRUCTION_FAILED"
                self.store.retain(record("WO10_ACQUISITION_OPERATION_V1", request_identity=request_identity,
                                        fingerprint=fingerprint, opportunity_identity=opportunity.identity,
                                        state="FAILED", operation_identity=started.identity, reason=code,
                                        request_attempts=attempts, failed_at=self.clock()))
                raise ValueError(code) from error

    def decision_state(self, comparison, *, now, session):
        c = require(comparison, "WO10_SPONSOR_COMPARISON_V1")
        if self.store.current(c["subject"]) != comparison:
            return "SUPERSEDED"
        snapshot = self.store.load(c["snapshot_identity"])
        plan = self.store.load(c["plan_identity"])
        p = self.wo09.load_pointer(c["subject"])
        if p is None or p.readiness_identity != c["readiness_identity"] or p.currentness.value != "CURRENT":
            return "SUPERSEDED"
        authority = self._market_authorities.get(snapshot.identity)
        if authority is not None:
            try:
                current = authority[0]()
                if digest({k:v for k,v in current.items() if k not in {"configuration", "economics"}}) != authority[1]:
                    return "SUPERSEDED"
                h0 = self.wo09.load_handoff(c["handoff_identity"])
                contract, _ = select_future(current["master"], h0, session, now=now, underlying=current["underlying"],
                    active_mcx=current["active_mcx"], economics=current["economics"])
                if contract.data["future"] != snapshot.data["contract"]["future"]:
                    return "SUPERSEDED"
            except (ValueError, KeyError, OSError, TypeError):
                return "UNAVAILABLE"
        if snapshot.identity not in self._current_process_snapshots:
            return "HISTORICAL_REACQUISITION_REQUIRED"
        if not fresh(snapshot.data["received_at"], now, 30) or not fresh(plan.data["created_at"], now, 300):
            return "STALE"
        h = plan.data["wo09"]
        if p.integrity_identity != h["current_pointer_integrity"]:
            return "SUPERSEDED"
        if not fresh(h["first_five_of_five_at"], now, 300):
            return "STALE"
        try:
            require_session(session, now, exchange="MCX" if snapshot.data["contract"]["active_mcx"] else "NSE")
        except ValueError:
            return "MARKET_NOT_EXECUTABLE"
        if (session.schedule.session_id != h["session_identity"]
                or snapshot.data["contract"]["trading_date"] != session.trading_date.isoformat()):
            return "MARKET_NOT_EXECUTABLE"
        return c["executability"]

    def select(self, comparison_identity, *, choice, lots, session, action_identity):
        self._guard()
        if type(action_identity) is not str or not action_identity.strip() or choice not in {"SELECTED_FUTURE", "NONE"}:
            raise ValueError("WO10_SPONSOR_ACTION_INVALID")
        now = self.clock()
        with self.store.transaction():
            comparison = self.store.load(comparison_identity)
            c = require(comparison, "WO10_SPONSOR_COMPARISON_V1")
            for previous in self.store.records("WO10_SPONSOR_SELECTION_V1"):
                d = previous.data
                if d["comparison_identity"] == comparison_identity:
                    if d["choice"] != choice or d["sponsor_selected_lots"] != lots or d["action_identity"] != action_identity:
                        raise ValueError("WO10_SPONSOR_SELECTION_CONFLICT")
                    if choice == "SELECTED_FUTURE":
                        handoffs = [h for h in self.store.records("WO10_SELECTED_TRADE_HANDOFF_V1")
                                    if h.data["selection_identity"] == previous.identity]
                        if len(handoffs) != 1:
                            raise ValueError("WO10_SELECTION_HANDOFF_INCOMPLETE")
                    return previous
            try:
                self._intake(self.wo09.load_handoff(c["handoff_identity"]), now)
            except (ValueError, OSError):
                raise ValueError("WO10_SPONSOR_SELECTION_NOT_PERMITTED") from None
            if choice == "NONE":
                if lots is not None or self.store.current(c["subject"]) != comparison:
                    raise ValueError("WO10_NONE_SELECTION_INVALID")
            elif (self.decision_state(comparison, now=now, session=session) != "EXECUTABLE"
                  or type(lots) is not int or lots <= 0):
                raise ValueError("WO10_SPONSOR_SELECTION_NOT_PERMITTED")
            advisory = self.preview_risk(comparison.identity, lots=lots, now=now)
            self.store.retain(advisory)
            selection = record("WO10_SPONSOR_SELECTION_V1", comparison_identity=comparison.identity,
                               comparison=c, choice=choice, sponsor_selected_lots=lots,
                               risk_advisory_identity=advisory.identity, advisory_risk=advisory.data, action_identity=action_identity,
                               selected_at=now, session=session)
            self.store.retain(selection)
            if choice == "SELECTED_FUTURE":
                plan = self.store.load(c["plan_identity"])
                snapshot = self.store.load(c["snapshot_identity"])
                expression = self.store.load(c["expression_identity"])
                self.store.retain(record("WO10_SELECTED_TRADE_HANDOFF_V1", selection_identity=selection.identity,
                                        selection=selection.data, plan=plan.data, snapshot=snapshot.data,
                                        expression=expression.data, advisory_risk=advisory.data,
                                        selected_at=now, authority="SELECTED_TRADE_ONLY_NO_ACTIVATION"))
            return selection

    def preview_risk(self, comparison_identity, *, lots=None, now=None):
        """Pure read-only projection; no persisted preview or operational acquisition."""
        c = require(self.store.load(comparison_identity), "WO10_SPONSOR_COMPARISON_V1")
        fact = self.store.load(c["risk_fact_identity"])
        config = None if c["reference_identity"] is None else self.store.load(c["reference_identity"])
        reference_reason = economics_reason = None
        authority = self._market_authorities.get(c["snapshot_identity"])
        if authority is not None:
            try:
                current = authority[0]()
                if digest(current.get("configuration")) != digest(config):
                    reference_reason = "RISK_REFERENCE_SUPERSEDED"
                snapshot = self.store.load(c["snapshot_identity"])
                if digest(current.get("economics")) != digest(snapshot.data["contract"]["economics"]):
                    economics_reason = "MONETARY_ECONOMICS_SUPERSEDED"
            except (ValueError, TypeError, KeyError, OSError):
                reference_reason = "RISK_REFERENCE_CURRENTNESS_UNAVAILABLE"
                economics_reason = "MONETARY_ECONOMICS_CURRENTNESS_UNAVAILABLE"
        return risk_advisory(fact, config, now=now or self.clock(), lots=lots,
            reference_unavailable_reason=reference_reason, economics_unavailable_reason=economics_reason)

    def restore(self):
        # Reading never restores process-local executable authority or writes.
        from kronos.intraday.wo10_futures_contract import CHECKSUM
        return tuple(r for r in self.store.records("WO10_SPONSOR_COMPARISON_V1") if r.policy_checksum == CHECKSUM)
