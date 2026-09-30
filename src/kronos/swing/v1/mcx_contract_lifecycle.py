"""Contract-specific observation adapter for an existing Swing MCX position.

This does not admit a position or commission MCX entry.  It keeps an existing
position on its historical derivative when current selection later rolls.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from contextlib import AbstractContextManager
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from typing import Callable
from uuid import uuid4

from kronos.market.schedule import MarketSchedule
from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.contracts.monitoring import (
    MonitoringConnectionState, MonitoringSubscriptionEvidence, ProviderMarketTick,
)
from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.mcx_live_attestation import (
    LocalMcxLiveFillAttestationStore, McxLiveFillAttestation,
)
from kronos.swing.v1.mcx_trade_plan import MCX_V1_ADVISORY_AUTHORITY
from kronos.swing.v1.mcx_kr380_issuer import RULE_ID
from kronos.swing.v1.mcx_v1_advisory import (
    ADVISORY_RULE_ID, McxAdvisoryState, McxV1AdvisoryOutcome,
    LocalMcxV1AdvisoryStore,
)
from kronos.swing.v1.mcx_trade_plan import McxTradePlanRecord, LocalMcxTradePlanStore
from kronos.swing.v1.native_entry_timing import (
    Kr380EntryOutcomeV2, Kr380V2State, LocalKr380V2Store,
)
from kronos.swing.v1.native_sponsor_decision import LocalSponsorDecisionStore
from kronos.swing.v1.native_active_trade_lifecycle import (
    ActiveLifecyclePosition, ActiveTradeLifecycleService, TradeClosureRecord,
    TradeExitReason, ActiveLifecycleState, LifecycleEventType,
    admit_kite_lifecycle_observation,
)


_SCHEMA = "KRONOS-SWING-MCX-HISTORICAL-CONTRACT-MONITORING-V1"


@dataclass(frozen=True, slots=True)
class McxConfirmedOneHourEntry:
    """Fixture-bound KR-380 plus completed contract 1H evidence.

    Neither a generic tick nor this wrapper alone supplies production entry
    authority. The current owner must supply a guarded exact read-set check.
    This historical fixture form uses a synthetic contiguous sequence. The
    production V1 observation path below does not infer such a Kite sequence.
    """

    plan_id: str
    plan_sha256: str
    run_identity: str
    family: McxFamily
    contract_symbol: str
    expiry: str
    setup_one_hour_sha256: str
    completed_entry_one_hour_sha256: str
    completed_entry_boundary: datetime
    confirmed_close: Decimal
    outcome: Kr380EntryOutcomeV2
    paper_cmp_predecessor: ProviderMarketTick
    paper_entry_tick: ProviderMarketTick

    def __post_init__(self) -> None:
        if type(self.outcome) is not Kr380EntryOutcomeV2:
            raise ValueError("MCX_CONFIRMED_1H_ENTRY_INVALID")
        expected = (Kr380V2State.LONG_ENTRY_TRIGGERED
                    if self.outcome.direction == "LONG"
                    else Kr380V2State.SHORT_ENTRY_TRIGGERED)
        if (
            type(self.family) is not McxFamily
            or self.outcome.state is not expected
            or self.outcome.trade_plan_id != self.plan_id
            or self.outcome.trade_plan_sha256 != self.plan_sha256
            or self.outcome.native_run_identity != self.run_identity
            or self.outcome.canonical_instrument != self.family.value
            or self.outcome.observation_boundary != self.completed_entry_boundary
            or self.outcome.occurred_at < self.completed_entry_boundary
            or self.outcome.reason != "MCX_COMPLETED_1H_CLOSE_CROSS"
            or RULE_ID not in self.outcome.provenance
            or self.setup_one_hour_sha256 not in self.outcome.provenance
            or self.completed_entry_one_hour_sha256 not in self.outcome.provenance
            or len(self.outcome.source_observation_ids) != 2
            or any(len(value) != 64 for value in (
                self.plan_sha256, self.setup_one_hour_sha256,
                self.completed_entry_one_hour_sha256,
            ))
            or type(self.confirmed_close) is not Decimal
            or not self.confirmed_close.is_finite() or self.confirmed_close <= 0
            or type(self.paper_entry_tick) is not ProviderMarketTick
            or type(self.paper_cmp_predecessor) is not ProviderMarketTick
            or self.paper_entry_tick.last_price <= 0
            or self.paper_entry_tick.observed_at <= self.outcome.occurred_at
            or self.paper_cmp_predecessor.observed_at > self.outcome.occurred_at
            or self.paper_cmp_predecessor.received_at > self.outcome.occurred_at
            or self.paper_cmp_predecessor.source_sequence is None
            or self.paper_cmp_predecessor.source_sequence + 1
               != self.paper_entry_tick.source_sequence
            or self.paper_cmp_predecessor.connection_id
               != self.paper_entry_tick.connection_id
            or not self.paper_cmp_predecessor.session_continuous
            or not self.paper_cmp_predecessor.ordering_deterministic
            or self.paper_cmp_predecessor.recovered
            or _instrument_fields(self.paper_cmp_predecessor.instrument)
               != _instrument_fields(self.paper_entry_tick.instrument)
            or self.paper_entry_tick.source_sequence is None
            or not self.paper_entry_tick.previous_interval_available
            or not self.paper_entry_tick.session_continuous
            or not self.paper_entry_tick.ordering_deterministic
            or self.paper_entry_tick.recovered
            or self.paper_entry_tick.instrument.exchange != "MCX"
            or self.paper_entry_tick.instrument.segment != "MCX-FUT"
            or self.paper_entry_tick.instrument.trading_symbol != self.contract_symbol
            or self.paper_entry_tick.instrument.expiry is None
            or self.paper_entry_tick.instrument.expiry.isoformat() != self.expiry
            or self.completed_entry_boundary.tzinfo is None
            or not self.contract_symbol
            or date.fromisoformat(self.expiry) < self.completed_entry_boundary.date()
        ):
            raise ValueError("MCX_CONFIRMED_1H_ENTRY_INVALID")

    @property
    def paper_entry_observation_id(self) -> str:
        tick = self.paper_entry_tick
        return "MCX-PAPER-TICK-" + sha256(_canonical({
            "instrument": _instrument_fields(tick.instrument),
            "price": str(tick.last_price),
            "observed_at": tick.observed_at.isoformat(),
            "received_at": tick.received_at.isoformat(),
            "connection_id": tick.connection_id,
            "source_sequence": tick.source_sequence,
        })).hexdigest()

    @property
    def paper_predecessor_observation_id(self) -> str:
        tick = self.paper_cmp_predecessor
        return "MCX-PAPER-PREDECESSOR-" + sha256(_canonical({
            "instrument": _instrument_fields(tick.instrument),
            "price": str(tick.last_price),
            "observed_at": tick.observed_at.isoformat(),
            "received_at": tick.received_at.isoformat(),
            "connection_id": tick.connection_id,
            "source_sequence": tick.source_sequence,
        })).hexdigest()

    @property
    def identity_sha256(self) -> str:
        return sha256(_canonical({
            "plan_id": self.plan_id, "plan_sha256": self.plan_sha256,
            "run_identity": self.run_identity, "family": self.family.value,
            "contract_symbol": self.contract_symbol, "expiry": self.expiry,
            "setup_one_hour_sha256": self.setup_one_hour_sha256,
            "completed_entry_one_hour_sha256": self.completed_entry_one_hour_sha256,
            "completed_entry_boundary": self.completed_entry_boundary.isoformat(),
            "confirmed_close": str(self.confirmed_close),
            "outcome_sha256": self.outcome.integrity_sha256,
            "paper_predecessor_observation_id": self.paper_predecessor_observation_id,
            "paper_entry_observation_id": self.paper_entry_observation_id,
        })).hexdigest()


def _instrument_fields(instrument: InstrumentRecord) -> dict[str, str | int | None]:
    return {
        "provider": instrument.provider,
        "exchange": instrument.exchange,
        "segment": instrument.segment,
        "trading_symbol": instrument.trading_symbol,
        "name": instrument.name,
        "instrument_type": instrument.instrument_type,
        "expiry": None if instrument.expiry is None else instrument.expiry.isoformat(),
        "tick_size": None if instrument.tick_size is None else str(instrument.tick_size),
        "lot_size": instrument.lot_size,
    }


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _cmp_observation_id(tick: ProviderMarketTick) -> str:
    return "MCX-CMP-" + sha256(_canonical({
        "instrument": _instrument_fields(tick.instrument),
        "price": str(tick.last_price),
        "observed_at": tick.observed_at.isoformat(),
        "received_at": tick.received_at.isoformat(),
        "source": tick.source,
        "connection_id": tick.connection_id,
        "source_sequence": tick.source_sequence,
    })).hexdigest()


@dataclass(frozen=True, slots=True)
class McxHistoricalContractBinding:
    """Immutable contract identity for monitoring a position already admitted."""

    position_id: str
    decision_id: str
    trade_plan_hash: str
    family: McxFamily
    instrument: InstrumentRecord
    integrity_sha256: str

    def __post_init__(self) -> None:
        if (
            not self.position_id or "/" in self.position_id or ".." in self.position_id
            or not self.decision_id
            or len(self.trade_plan_hash) != 64
            or type(self.family) is not McxFamily
            or type(self.instrument) is not InstrumentRecord
            or self.instrument.provider != "KITE"
            or self.instrument.exchange != "MCX"
            or self.instrument.segment != "MCX-FUT"
            or self.instrument.instrument_type != "FUT"
            or self.instrument.name != self.family.value
            or type(self.instrument.expiry) is not date
            or not self.instrument.trading_symbol.startswith(self.family.value)
            or self.integrity_sha256 != self.digest()
        ):
            raise ValueError("MCX_HISTORICAL_CONTRACT_BINDING_INVALID")

    def digest(self) -> str:
        return sha256(_canonical({
            "schema": _SCHEMA,
            "position_id": self.position_id,
            "decision_id": self.decision_id,
            "trade_plan_hash": self.trade_plan_hash,
            "family": self.family.value,
            "instrument": _instrument_fields(self.instrument),
        })).hexdigest()

    @classmethod
    def create(cls, position: ActiveLifecyclePosition, instrument: InstrumentRecord):
        if type(position) is not ActiveLifecyclePosition:
            raise ValueError("MCX_HISTORICAL_POSITION_INVALID")
        family = McxFamily(position.canonical_instrument)
        digest = sha256(_canonical({
            "schema": _SCHEMA,
            "position_id": position.position_id,
            "decision_id": position.decision_id,
            "trade_plan_hash": position.trade_plan_hash,
            "family": family.value,
            "instrument": _instrument_fields(instrument),
        })).hexdigest()
        return cls(position.position_id, position.decision_id,
                   position.trade_plan_hash, family, instrument, digest)


class LocalMcxHistoricalContractStore:
    """Append-only binding store; no current-contract pointer or roll operation."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("MCX_HISTORICAL_CONTRACT_STORE_INVALID")
        self._lock = RLock()

    def _path(self, position_id: str) -> Path:
        if not position_id or "/" in position_id or ".." in position_id:
            raise ValueError("MCX_HISTORICAL_POSITION_ID_INVALID")
        return self.root / (position_id + ".json")

    def retain(self, binding: McxHistoricalContractBinding) -> Path:
        if type(binding) is not McxHistoricalContractBinding:
            raise TypeError("MCX_HISTORICAL_CONTRACT_BINDING_INVALID")
        path = self._path(binding.position_id)
        payload = _canonical({
            "schema": _SCHEMA,
            "position_id": binding.position_id,
            "decision_id": binding.decision_id,
            "trade_plan_hash": binding.trade_plan_hash,
            "family": binding.family.value,
            "instrument": _instrument_fields(binding.instrument),
            "integrity_sha256": binding.integrity_sha256,
        })
        with self._lock:
            if path.exists():
                if path.is_symlink() or path.read_bytes() != payload:
                    raise ValueError("MCX_HISTORICAL_CONTRACT_IMMUTABLE")
                return path
            path.parent.mkdir(parents=True, exist_ok=True)
            if self.root.is_symlink():
                raise ValueError("MCX_HISTORICAL_CONTRACT_STORE_INVALID")
            temporary = path.parent / ("." + binding.position_id + "." + uuid4().hex + ".pending")
            try:
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.link(temporary, path, follow_symlinks=False)
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                temporary.unlink(missing_ok=True)
        return path

    def load(self, position_id: str) -> McxHistoricalContractBinding:
        path = self._path(position_id)
        if path.is_symlink():
            raise ValueError("MCX_HISTORICAL_CONTRACT_INTEGRITY_INVALID")
        try:
            value = json.loads(path.read_bytes())
            if value["schema"] != _SCHEMA or value["position_id"] != position_id:
                raise ValueError
            fields = value["instrument"]
            instrument = InstrumentRecord(
                fields["provider"], fields["exchange"], fields["segment"],
                fields["trading_symbol"], fields["name"], fields["instrument_type"],
                date.fromisoformat(fields["expiry"]), fields["tick_size"], fields["lot_size"],
            )
            binding = McxHistoricalContractBinding(
                position_id, value["decision_id"], value["trade_plan_hash"],
                McxFamily(value["family"]), instrument,
                value["integrity_sha256"],
            )
            if path.read_bytes() != _canonical(value):
                raise ValueError
            return binding
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise ValueError("MCX_HISTORICAL_CONTRACT_INTEGRITY_INVALID") from error


class McxContractBoundLifecycle:
    """Run existing Swing lifecycle only after exact historical tick selection."""

    def __init__(self, service: ActiveTradeLifecycleService,
                 bindings: LocalMcxHistoricalContractStore) -> None:
        if type(service) is not ActiveTradeLifecycleService or type(bindings) is not LocalMcxHistoricalContractStore:
            raise TypeError("MCX_LIFECYCLE_ADAPTER_INVALID")
        self.service = service
        self.bindings = bindings

    def _position(self, position_id: str) -> ActiveLifecyclePosition:
        matches = tuple(item for item in self.service.snapshot().positions
                        if item.position_id == position_id)
        if len(matches) != 1:
            raise ValueError("MCX_HISTORICAL_POSITION_UNAVAILABLE")
        return matches[0]

    def _bound_position(self, position_id: str) -> tuple[McxHistoricalContractBinding, ActiveLifecyclePosition]:
        binding = self.bindings.load(position_id)
        position = self._position(position_id)
        if (position.canonical_instrument != binding.family.value
                or position.decision_id != binding.decision_id
                or position.trade_plan_hash != binding.trade_plan_hash):
            raise ValueError("MCX_HISTORICAL_POSITION_BINDING_CHANGED")
        return binding, position

    def retain_existing(self, position_id: str, instrument: InstrumentRecord) -> McxHistoricalContractBinding:
        binding = McxHistoricalContractBinding.create(self._position(position_id), instrument)
        self.bindings.retain(binding)
        return binding

    def observe_tick(self, position_id: str, tick: ProviderMarketTick,
                     schedule: MarketSchedule) -> ActiveLifecyclePosition:
        binding, position = self._bound_position(position_id)
        if (type(tick) is not ProviderMarketTick
                or _instrument_fields(tick.instrument) != _instrument_fields(binding.instrument)
                or schedule.exchange != "MCX"):
            raise ValueError("MCX_HISTORICAL_CONTRACT_TICK_MISMATCH")
        if (position.mcx_v1_contract_symbol is not None
                and position.state is ActiveLifecycleState.MONITORING_UNAVAILABLE
                and (position.monitoring_outage_started_at is None
                     or tick.observed_at <= position.monitoring_outage_started_at)):
            raise ValueError("MCX_V1_POST_OUTAGE_OBSERVATION_STALE")
        if (position.mcx_quantity is not None
                and position.mode.value == "PAPER"
                and position.state is ActiveLifecycleState.PAPER_ACTIVE
                and (tick.last_price <= 0 or tick.recovered
                     or tick.source_sequence is None
                     or not tick.previous_interval_available
                     or not tick.session_continuous
                     or not tick.ordering_deterministic
                     or position.entry_timestamp is None
                     or tick.observed_at <= position.entry_timestamp
                     or (position.last_observed_at is not None
                         and tick.observed_at <= position.last_observed_at))):
            raise ValueError("MCX_FACTUAL_EXIT_CMP_UNAVAILABLE")
        observation = admit_kite_lifecycle_observation(position, tick, schedule)
        observation = replace(observation, provenance=(*observation.provenance,
            _cmp_observation_id(tick), tick.connection_id,
            str(tick.source_sequence), tick.observed_at.isoformat(),
            tick.received_at.isoformat()))
        return self.service.observe(position_id, observation)

    def activate_confirmed_entry(
        self, position_id: str, plan: McxTradePlanRecord,
        authority: McxConfirmedOneHourEntry, *,
        schedule: MarketSchedule,
        plan_store: LocalMcxTradePlanStore,
        sponsor_store: LocalSponsorDecisionStore,
        outcome_store: LocalKr380V2Store,
        commit_guard: Callable[[], AbstractContextManager[object]],
        current_readset: Callable[[], tuple[McxTradePlanRecord, McxConfirmedOneHourEntry]],
    ) -> ActiveLifecyclePosition:
        """Use only the exact current KR-380 and completed contract 1H read set.

        The owner guard encloses currentness recheck and lifecycle commit.
        It acquires Review publication/intake locks before lifecycle locks;
        current read-set stores are read before the lifecycle lock is taken.
        """

        if (type(plan) is not McxTradePlanRecord
                or type(authority) is not McxConfirmedOneHourEntry
                or type(schedule) is not MarketSchedule
                or type(plan_store) is not LocalMcxTradePlanStore
                or type(sponsor_store) is not LocalSponsorDecisionStore
                or type(outcome_store) is not LocalKr380V2Store
                or not callable(commit_guard) or not callable(current_readset)):
            raise ValueError("MCX_CONFIRMED_ENTRY_UNAVAILABLE")
        with commit_guard():
            current_plan, current_authority = current_readset()
            if current_plan != plan or current_authority != authority:
                raise ValueError("MCX_CONFIRMED_ENTRY_STALE")
            binding, position = self._bound_position(position_id)
            outcome = authority.outcome
            retained = sponsor_store.load_plan(plan.native_run_identity, plan.trade_plan_id)
            decision = retained.decision
            if (
                plan_store.load(plan_store._path(plan)) != plan
                or decision is None or retained.position is None
                or retained.position.position_id != position_id
                or decision.decision_id != position.decision_id
                or decision.trade_plan_integrity_hash != plan.integrity_hash
                or len(decision.risk_hash) != 64
                or decision.risk_id != outcome.risk_result_id
                or outcome_store.load_for_plan(plan.trade_plan_id) != outcome
            ):
                raise ValueError("MCX_CONFIRMED_ENTRY_RETAINED_AUTHORITY_INVALID")
            if (
                position.trade_plan_id != plan.trade_plan_id
                or position.trade_plan_hash != plan.integrity_hash
                or position.mcx_quantity != plan.quantity
                or position.lots != 1 or plan.quantity.lots != 1
                or binding.instrument.trading_symbol != plan.contract_symbol
                or binding.instrument.expiry.isoformat() != plan.expiry
                or (authority.plan_id, authority.plan_sha256,
                    authority.run_identity, authority.family,
                    authority.contract_symbol, authority.expiry,
                    authority.setup_one_hour_sha256)
                   != (plan.trade_plan_id, plan.integrity_hash,
                       plan.native_run_identity, plan.family,
                       plan.contract_symbol, plan.expiry,
                       plan.completed_one_hour_sha256)
                or authority.completed_entry_boundary < plan.observation_boundary
                or outcome.kr370_source_identity != plan.readiness_record_identity
                or outcome.direction != plan.native_direction.value
                or outcome.occurred_at >= plan.entry_eligibility_boundary
                or authority.paper_entry_tick.observed_at >= plan.entry_eligibility_boundary
                or authority.paper_entry_tick.received_at >= plan.entry_eligibility_boundary
                or schedule.exchange != "MCX"
                or schedule.window_at(authority.paper_entry_tick.observed_at) is None
                or schedule.window_at(authority.paper_entry_tick.received_at) is None
                or schedule.window_at(authority.completed_entry_boundary) is None
                or _instrument_fields(authority.paper_entry_tick.instrument)
                   != _instrument_fields(binding.instrument)
                or (plan.native_direction.value == "LONG" and not
                    plan.stop < authority.paper_entry_tick.last_price < plan.canonical_target)
                or (plan.native_direction.value == "SHORT" and not
                    plan.canonical_target < authority.paper_entry_tick.last_price < plan.stop)
                or plan.quantity.stop_risk(
                    authority.paper_entry_tick.last_price, plan.stop,
                ) > plan.maximum_stop_risk
            ):
                raise ValueError("MCX_CONFIRMED_ENTRY_BINDING_INVALID")

            return self.service._activate_mcx_confirmed(
                position_id, expected_position_hash=position.integrity_hash,
                outcome_id=outcome.entry_outcome_id,
                outcome_sha256=authority.identity_sha256,
                entry_price=authority.paper_entry_tick.last_price,
                entry_at=authority.paper_entry_tick.received_at,
                completed_boundary=authority.completed_entry_boundary,
                completed_one_hour_sha256=authority.completed_entry_one_hour_sha256,
                source_observation_ids=(*outcome.source_observation_ids,
                                        authority.paper_predecessor_observation_id,
                                        authority.paper_entry_observation_id,
                                        authority.paper_entry_tick.source,
                                        authority.paper_entry_tick.connection_id,
                                        str(authority.paper_entry_tick.source_sequence),
                                        authority.paper_entry_tick.observed_at.isoformat(),
                                        authority.paper_entry_tick.received_at.isoformat()),
            )

    def activate_v1_paper_at_observed_cmp(
        self, position_id: str, plan: McxTradePlanRecord,
        outcome: McxV1AdvisoryOutcome, tick: ProviderMarketTick,
        schedule: MarketSchedule, *, plan_store: LocalMcxTradePlanStore,
        sponsor_store: LocalSponsorDecisionStore,
        outcome_store: LocalMcxV1AdvisoryStore,
        connection_state: MonitoringConnectionState,
        commit_guard: Callable[[], AbstractContextManager[object]],
        current_readset: Callable[[], tuple[McxTradePlanRecord,
                                             McxV1AdvisoryOutcome,
                                             ProviderMarketTick]],
        subscription_evidence: MonitoringSubscriptionEvidence | None = None,
        current_subscription: Callable | None = None,
    ) -> ActiveLifecyclePosition:
        """Capture only a post-signal CMP observed by this exact owner.

        The caller must deliver each newly observed quote in receipt order.
        A missing, interrupted or wrong-contract quote does not backfill a fill.
        Review currentness is rechecked under the owner guard before writing.
        """
        if (type(plan) is not McxTradePlanRecord
                or plan.authority != MCX_V1_ADVISORY_AUTHORITY
                or type(outcome) is not McxV1AdvisoryOutcome
                or type(tick) is not ProviderMarketTick
                or type(schedule) is not MarketSchedule
                or type(plan_store) is not LocalMcxTradePlanStore
                or type(sponsor_store) is not LocalSponsorDecisionStore
                or type(outcome_store) is not LocalMcxV1AdvisoryStore
                or connection_state not in {MonitoringConnectionState.CONNECTED,
                                            MonitoringConnectionState.CONTEXT_INCOMPLETE}
                or not callable(commit_guard) or not callable(current_readset)):
            raise ValueError("MCX_V1_ENTRY_INPUT_INVALID")
        with commit_guard():
            if (subscription_evidence is not None
                    or connection_state is MonitoringConnectionState.CONTEXT_INCOMPLETE):
                if (type(subscription_evidence) is not MonitoringSubscriptionEvidence
                        or subscription_evidence.state is not connection_state
                        or not subscription_evidence.admits(tick)
                        or not callable(current_subscription)
                        or current_subscription() != subscription_evidence):
                    raise ValueError("MCX_V1_ENTRY_SUBSCRIPTION_CHANGED")
            if current_readset() != (plan, outcome, tick):
                raise ValueError("MCX_V1_ENTRY_READ_SET_CHANGED")
            binding, position = self._bound_position(position_id)
            retained = sponsor_store.load_plan(plan.native_run_identity,
                                               plan.trade_plan_id)
            if (plan_store.load(plan_store._path(plan)) != plan
                    or outcome_store.load_for_plan(plan.trade_plan_id) != outcome
                    or retained.position is None or retained.decision is None
                    or retained.position.position_id != position_id
                    or retained.decision.decision_id != position.decision_id
                    or retained.decision.trade_plan_integrity_hash
                       != plan.integrity_hash
                    or retained.decision.risk_id != outcome.risk_result_id
                    or position.trade_plan_id != plan.trade_plan_id
                    or position.trade_plan_hash != plan.integrity_hash
                    or position.mcx_v1_contract_symbol != plan.contract_symbol
                    or position.lots != 1
                    or binding.instrument.trading_symbol != plan.contract_symbol
                    or binding.instrument.expiry.isoformat() != plan.expiry
                    or _instrument_fields(tick.instrument)
                       != _instrument_fields(binding.instrument)
                    or outcome.trade_plan_id != plan.trade_plan_id
                    or outcome.trade_plan_sha256 != plan.integrity_hash
                    or outcome.native_run_identity != plan.native_run_identity
                    or outcome.canonical_instrument != plan.family.value
                    or outcome.kr370_source_identity
                       != plan.readiness_record_identity
                    or outcome.direction != plan.native_direction.value
                    or outcome.reason != "MCX_COMPLETED_1H_ADVISORY_CLOSE_CROSS"
                    or ADVISORY_RULE_ID not in outcome.provenance
                    or (outcome.contract_symbol, outcome.expiry)
                       != (plan.contract_symbol, plan.expiry)
                    or outcome.session_identity != schedule.session_identity
                    or plan.completed_one_hour_sha256 not in outcome.provenance
                    or plan.receipt_integrity_sha256 not in outcome.provenance
                    or plan.promotion_integrity_sha256 not in outcome.provenance
                    or outcome.state is not (
                        McxAdvisoryState.LONG_CONFIRMED
                        if plan.native_direction.value == "LONG" else
                        McxAdvisoryState.SHORT_CONFIRMED)
                    or outcome.occurred_at < plan.observation_boundary
                    or tick.last_price <= 0 or tick.recovered
                    or tick.source != "KITE_CONNECT_WEBSOCKET"
                    or tick.observed_at <= outcome.occurred_at
                    or tick.received_at <= outcome.occurred_at
                    or tick.received_at <= outcome.confirmed_at
                    or tick.received_at <= position.created_at
                    or (position.state is ActiveLifecycleState.MONITORING_UNAVAILABLE
                        and (position.monitoring_outage_started_at is None
                             or tick.observed_at
                                <= position.monitoring_outage_started_at))
                    or tick.received_at >= plan.entry_eligibility_boundary
                    or schedule.exchange != "MCX"
                    or schedule.window_at(outcome.occurred_at) is None
                    or schedule.window_at(tick.observed_at) is None
                    or schedule.window_at(tick.received_at) is None):
                raise ValueError("MCX_V1_ENTRY_AUTHORITY_UNAVAILABLE")
            quote_id = _cmp_observation_id(tick)
            if (position.mcx_activation_outcome_sha256 is not None
                    and (position.mcx_activation_outcome_sha256
                         != outcome.integrity_sha256
                         or position.actual_entry != tick.last_price
                         or position.entry_timestamp != tick.received_at
                         or not any(
                             event.position_id == position_id
                             and event.event_type is LifecycleEventType.PAPER_ENTRY_CAPTURED
                             and quote_id in event.provider_provenance
                             for event in self.service.snapshot().events
                         ))):
                raise ValueError("MCX_V1_ENTRY_REPLAY_MISMATCH")
            return self.service._activate_mcx_confirmed(
                position_id, expected_position_hash=position.integrity_hash,
                outcome_id=outcome.entry_outcome_id,
                outcome_sha256=outcome.integrity_sha256,
                entry_price=tick.last_price, entry_at=tick.received_at,
                completed_boundary=outcome.observation_boundary,
                completed_one_hour_sha256=outcome.provenance[-2],
                source_observation_ids=(*outcome.source_observation_ids,
                                        quote_id, tick.source,
                                        tick.connection_id,
                                        connection_state.value,
                                        tick.observed_at.isoformat(),
                                        tick.received_at.isoformat(),
                                        *(() if subscription_evidence is None else (
                                            "MCX_OBSERVATION_SUBSCRIPTION_VERIFIED",
                                            subscription_evidence.subscribed_at.isoformat(),
                                        ))),
            )

    def manual_paper_exit_current(self, position_id: str) -> TradeClosureRecord:
        _, position = self._bound_position(position_id)
        if (position.mcx_quantity is not None
                or position.mcx_v1_contract_symbol is not None):
            raise ValueError("MCX_FACTUAL_EXIT_CMP_REQUIRED")
        return self.service.manual_paper_exit_current(position_id)

    def manual_paper_exit_at_cmp(self, position_id: str, tick: ProviderMarketTick,
                                 schedule: MarketSchedule) -> TradeClosureRecord:
        """Close a newly admitted PAPER lot at its exact factual contract CMP."""

        binding, position = self._bound_position(position_id)
        if ((position.mcx_quantity is None
             and position.mcx_v1_contract_symbol is None)
                or position.lots != 1
                or position.state is not ActiveLifecycleState.PAPER_ACTIVE
                or type(tick) is not ProviderMarketTick
                or _instrument_fields(tick.instrument) != _instrument_fields(binding.instrument)
                or tick.last_price <= 0 or tick.recovered
                or (position.mcx_quantity is not None
                    and tick.source_sequence is None)
                or (position.mcx_quantity is not None
                    and (not tick.previous_interval_available
                         or not tick.session_continuous
                         or not tick.ordering_deterministic))
                or tick.source != "KITE_CONNECT_WEBSOCKET"
                or position.entry_timestamp is None
                or tick.received_at <= position.entry_timestamp
                or schedule.exchange != "MCX"
                or schedule.window_at(tick.observed_at) is None
                or schedule.window_at(tick.received_at) is None):
            raise ValueError("MCX_FACTUAL_EXIT_CMP_UNAVAILABLE")
        observed = self.observe_tick(position_id, tick, schedule)
        if observed.state is ActiveLifecycleState.CLOSED:
            return next(item for item in self.service.snapshot().closures
                        if item.position_id == position_id)
        return self.service.manual_paper_exit_current(position_id)

    def monitoring_unavailable(self, position_id: str, *, occurred_at: datetime,
                               provider_context: str) -> ActiveLifecyclePosition:
        """Keep an admitted historical position observable during Provider outage."""

        self._bound_position(position_id)
        return self.service.monitoring_unavailable(
            position_id, occurred_at=occurred_at,
            provider_context=provider_context,
        )

    def record_live_exit(self, position_id: str, *, actual_exit: Decimal | None,
                         exit_timestamp: datetime,
                         reason: TradeExitReason,
                         attestation: McxLiveFillAttestation | None = None,
                         attestation_store: LocalMcxLiveFillAttestationStore | None = None,
                         broker_store: object | None = None,
                         broker_bytes: bytes | None = None,
                         ) -> TradeClosureRecord | None:
        binding, position = self._bound_position(position_id)
        if (position.mcx_quantity is not None
                or position.mcx_v1_contract_symbol is not None):
            if (type(attestation) is not McxLiveFillAttestation
                    or type(attestation_store) is not LocalMcxLiveFillAttestationStore
                    or actual_exit is None
                    or attestation.fill_price != actual_exit
                    or attestation.fill_at != exit_timestamp
                    or attestation.plan_id != position.trade_plan_id
                    or attestation.plan_sha256 != position.trade_plan_hash
                    or attestation.family is not binding.family
                    or attestation.contract_symbol != binding.instrument.trading_symbol
                    or attestation.expiry != binding.instrument.expiry.isoformat()
                    or attestation.lots != position.lots
                    or (position.mcx_quantity is not None and
                        attestation.provider_order_quantity
                        != position.mcx_quantity.provider_order_quantity)
                    or (position.mcx_v1_contract_symbol is not None and
                        (not attestation.v1_manual
                         or attestation.provider_order_quantity is not None
                         or position.mcx_v1_contract_symbol
                            != attestation.contract_symbol))
                    or position.entry_timestamp is None
                    or attestation.fill_at <= position.entry_timestamp):
                raise ValueError("MCX_LIVE_EXIT_ATTESTATION_UNAVAILABLE")
            entry = attestation_store.load(position.trade_plan_id)
            if (entry.run_identity != attestation.run_identity
                    or entry.plan_sha256 != attestation.plan_sha256
                    or entry.model_relation != attestation.model_relation
                    or entry.entry_outcome_id != attestation.entry_outcome_id
                    or entry.entry_outcome_sha256 != attestation.entry_outcome_sha256):
                raise ValueError("MCX_LIVE_EXIT_ATTESTATION_UNAVAILABLE")
            if position.mcx_v1_contract_symbol is not None:
                from kronos.swing.v1.mcx_broker_fill_evidence import (
                    LocalMcxBrokerFillEvidenceStore, McxBrokerFillCapture,
                )
                if (type(broker_store) is not LocalMcxBrokerFillEvidenceStore
                        or type(broker_bytes) is not bytes):
                    raise ValueError("MCX_V1_LIVE_EXIT_BROKER_EVIDENCE_REQUIRED")
                capture = McxBrokerFillCapture.from_attestation(
                    position_id, attestation, broker_bytes)
                if capture.evidence_sha256 != attestation.broker_evidence_sha256:
                    raise ValueError("MCX_V1_LIVE_EXIT_BROKER_EVIDENCE_MISMATCH")
            if position.state is ActiveLifecycleState.CLOSED:
                retained = attestation_store.load_exit(position_id)
                closure = next((item for item in self.service.snapshot().closures
                                if item.position_id == position_id), None)
                if (retained != attestation or closure is None
                        or closure.exit_reason is not reason
                        or closure.actual_exit != actual_exit
                        or closure.exit_timestamp != exit_timestamp):
                    raise ValueError("MCX_LIVE_EXIT_REPLAY_MISMATCH")
                if position.mcx_v1_contract_symbol is not None:
                    broker_store.verify_exit(capture, attestation,
                                             closure, binding)
                # Completed pre-2F fixture records have no intent sidecar.
                # Their immutable closure supplies the reason and fill; do not
                # rewrite historical evidence merely to replay a closed exit.
                intent_path = attestation_store.root / (position_id + ".exit-intent.json")
                if intent_path.exists() or intent_path.is_symlink():
                    intent_hash, intent_reason = attestation_store.load_exit_intent(position_id)
                    if (intent_hash != attestation.integrity_sha256
                            or intent_reason != reason.value):
                        raise ValueError("MCX_LIVE_EXIT_REPLAY_MISMATCH")
                return closure
            outage_exit = (position.mcx_v1_contract_symbol is not None
                and position.mode.value == "LIVE"
                and (position.state is ActiveLifecycleState.EVENT_UNRESOLVED
                     or (position.state is ActiveLifecycleState.MONITORING_UNAVAILABLE
                         and position.prior_state in {ActiveLifecycleState.LIVE_ACTIVE,
                                                      ActiveLifecycleState.EVENT_UNRESOLVED})))
            if ((position.state is not ActiveLifecycleState.LIVE_ACTIVE and not outage_exit)
                    or reason not in {
                        TradeExitReason.SPONSOR_EXIT_AFTER_TARGET_NOTIFICATION,
                        TradeExitReason.SPONSOR_EXIT_AFTER_STOP_NOTIFICATION,
                        TradeExitReason.SPONSOR_EXIT_AFTER_INVALIDATION_NOTIFICATION,
                        TradeExitReason.SPONSOR_MANUAL_EXIT,
                    }):
                raise ValueError("MCX_LIVE_EXIT_UNAVAILABLE")
            existing_closure = next((item for item in self.service.snapshot().closures
                                     if item.position_id == position_id), None)
            if (existing_closure is not None
                    and (existing_closure.actual_exit != actual_exit
                         or existing_closure.exit_timestamp != exit_timestamp
                         or existing_closure.exit_reason is not reason)):
                raise ValueError("MCX_LIVE_EXIT_RECOVERY_CONFLICT")
            if position.mcx_v1_contract_symbol is not None:
                broker_store.capture(capture, broker_bytes)
            attestation_store.retain_exit_intent(position_id, attestation, reason.value)
            attestation_store.retain_exit(position_id, attestation)
        return self.service.record_live_exit(
            position_id, actual_exit=actual_exit, exit_timestamp=exit_timestamp,
            reason=reason,
        )

    def recover_retained_live_exit(
        self, position_id: str,
        attestation_store: LocalMcxLiveFillAttestationStore,
        broker_store: object | None = None,
    ) -> TradeClosureRecord:
        """Complete one retained exact exit after restart; never infer a fill.

        The immutable intent precedes the attestation. An incomplete pair is
        held for review. The lifecycle store deduplicates the deterministic
        event and closure, including interruption between those writes.
        """
        intent_hash, reason_name = attestation_store.load_exit_intent(position_id)
        attestation = attestation_store.load_exit(position_id)
        if intent_hash != attestation.integrity_sha256:
            raise ValueError("MCX_LIVE_EXIT_RECOVERY_CONFLICT")
        try:
            reason = TradeExitReason(reason_name)
        except ValueError as error:
            raise ValueError("MCX_LIVE_EXIT_RECOVERY_CONFLICT") from error
        broker_bytes = None
        _, position = self._bound_position(position_id)
        if position.mcx_v1_contract_symbol is not None:
            from kronos.swing.v1.mcx_broker_fill_evidence import (
                LocalMcxBrokerFillEvidenceStore, McxBrokerFillCapture,
            )
            if type(broker_store) is not LocalMcxBrokerFillEvidenceStore:
                raise ValueError("MCX_V1_LIVE_EXIT_BROKER_EVIDENCE_REQUIRED")
            capture = McxBrokerFillCapture(
                position_id, attestation.plan_id, attestation.integrity_sha256,
                attestation.broker_evidence_id,
                attestation.broker_evidence_sha256,
                1, attestation.contract_symbol, attestation.expiry,
                attestation.lots, attestation.fill_price, attestation.fill_at)
            byte_path, _ = broker_store._paths(capture)
            if byte_path.is_symlink():
                raise ValueError("MCX_V1_LIVE_EXIT_BROKER_EVIDENCE_REQUIRED")
            try:
                broker_bytes = byte_path.read_bytes()
            except OSError as error:
                raise ValueError("MCX_V1_LIVE_EXIT_BROKER_EVIDENCE_REQUIRED") from error
        closure = self.record_live_exit(
            position_id, actual_exit=attestation.fill_price,
            exit_timestamp=attestation.fill_at, reason=reason,
            attestation=attestation, attestation_store=attestation_store,
            broker_store=broker_store, broker_bytes=broker_bytes,
        )
        if closure is None:
            raise ValueError("MCX_LIVE_EXIT_RECOVERY_INCOMPLETE")
        return closure
