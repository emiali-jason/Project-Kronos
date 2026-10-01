"""Swing MCX selected-run workflow, installed only by its explicit composition.

V1 advice and manual records are distinct from isolated contract-proof paths.
Neither path grants broker execution or silently changes historical contracts.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from collections.abc import Callable

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.provider.instrument_master_persistence import ProviderInstrumentSnapshotStore
from kronos.market.schedule import MarketDaySchedule, TradingDayStatus
from kronos.swing.run_publication import SwingRunPublication
from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.mcx_contract_selection import (
    LocalMcxSponsorSelectionStore,
    McxAnalysisProcessHandoff,
    McxContractAdmissionFacts,
    McxContractOffer,
    McxSelectionRole,
    choose_mcx_contract,
    prepare_mcx_contract_offer,
    require_mcx_choice_matches_handoff,
    selected_mcx_instrument_before_acquisition,
)
from kronos.swing.v1.mcx_prepared_plan_store import (
    LocalMcxPreparedPlanStore,
    McxPreparedPlanEvidence,
    mcx_sponsor_admission_reasons,
)
from kronos.swing.v1.mcx_step31_construction import (
    McxContractProofPrerequisites,
    McxOneHourGeometry,
    McxPendingPlan,
    prepare_mcx_pending_from_owner,
    select_owner_current_mcx_handoff,
)
from kronos.swing.v1.mcx_trade_plan import (
    LocalMcxTradePlanStore, McxIsolatedAdmissionFacts, McxTradePlanRecord,
    admit_isolated_mcx_paper, construct_isolated_mcx_trade_plan,
    construct_v1_mcx_advisory_plan, admit_v1_mcx_paper,
    MCX_V1_ADVISORY_AUTHORITY,
)
from kronos.swing.v1.mcx_contract_lifecycle import (
    LocalMcxHistoricalContractStore, McxContractBoundLifecycle,
)
from kronos.swing.v1.mcx_live_attestation import (
    LocalMcxLiveFillAttestationStore, McxLiveFillAttestation,
    admit_isolated_mcx_live, admit_v1_mcx_manual_live,
)
from kronos.swing.v1.mcx_broker_fill_evidence import LocalMcxBrokerFillEvidenceStore
from kronos.swing.v1.native_active_trade_lifecycle import ActiveTradeLifecycleService
from kronos.swing.v1.native_entry_timing import Kr380EntryOutcomeV2, LocalKr380V2Store
from kronos.swing.v1.mcx_v1_advisory import McxV1AdvisoryOutcome, LocalMcxV1AdvisoryStore
from kronos.swing.v1.native_discovery import NativeOpportunityIdentity
from kronos.swing.v1.native_sponsor_decision import LocalSponsorDecisionStore
from kronos.swing.v1.step32 import BusinessJudgment, RiskApproval


class SwingMcxIntegratedWorkflow:
    """One reserved-run owner; externally missing facts remain fixture-only."""

    def __init__(
        self, publication: SwingRunPublication,
        selections: LocalMcxSponsorSelectionStore,
        plans: LocalMcxPreparedPlanStore,
        run_identity: str, generation: int,
        offers: dict[McxFamily, McxContractOffer],
        sponsor_identity: str,
        clock: Callable[[], datetime] | None = None,
        *, reservation_token: object | None = None,
        predecessor: object | None = None,
        reserved_at: datetime | None = None,
    ) -> None:
        if (
            type(publication) is not SwingRunPublication
            or type(selections) is not LocalMcxSponsorSelectionStore
            or type(plans) is not LocalMcxPreparedPlanStore
            or type(generation) is not int or generation <= 0
            or set(offers) != set(McxFamily)
            or any(offer.run_identity != run_identity or offer.family is not family
                   for family, offer in offers.items())
            or type(sponsor_identity) is not str or not sponsor_identity.strip()
        ):
            raise ValueError("MCX_INTEGRATED_WORKFLOW_INVALID")
        self.publication = publication
        self.selections = selections
        self.plans = plans
        self.run_identity = run_identity
        self.generation = generation
        self.offers = dict(offers)
        self.sponsor_identity = sponsor_identity
        self.clock = clock or (lambda: datetime.now().astimezone())
        self.reservation_token = reservation_token
        self.predecessor = predecessor
        self.reserved_at = reserved_at

    @classmethod
    def reserve(
        cls, publication: SwingRunPublication,
        selections: LocalMcxSponsorSelectionStore,
        plans: LocalMcxPreparedPlanStore,
        run_identity: str,
        facts: dict[McxFamily, tuple[McxContractAdmissionFacts, ...]],
        *, observed_at: datetime, sponsor_identity: str,
        clock: Callable[[], datetime] | None = None,
        selection_policy: str = "STRICT_VERIFIED_ENTRY",
    ) -> SwingMcxIntegratedWorkflow:
        if set(facts) != set(McxFamily):
            raise ValueError("MCX_INTEGRATED_FACTS_INCOMPLETE")
        # No publication write happens until all five offers are valid.
        offers = {family: prepare_mcx_contract_offer(
            run_identity, family, facts[family], observed_at=observed_at,
            selection_policy=selection_policy,
        ) for family in McxFamily}
        if any(not offer.selectable() for offer in offers.values()):
            raise ValueError("MCX_INTEGRATED_OFFER_UNAVAILABLE")
        token, predecessor = publication.admit(run_identity, observed_at)
        return cls(publication, selections, plans, run_identity,
                   token.generation, offers, sponsor_identity, clock,
                   reservation_token=token, predecessor=predecessor,
                   reserved_at=observed_at)

    def _current(self) -> None:
        control = self.publication.status()
        attempt = control["latest_attempt"]
        if (control["admission_generation"] != self.generation
                or attempt["run_id"] != self.run_identity):
            raise ValueError("MCX_RESERVED_RUN_STALE")
        if attempt["state"] == "RUNNING":
            if attempt["predecessor_manifest"] != control["current_manifest"]:
                raise ValueError("MCX_RESERVED_RUN_STALE")
        elif attempt["state"] == "SUCCEEDED":
            current = self.publication.current()
            if (current.reference != control["current_manifest"]
                    or current.native.run_identity != self.run_identity
                    or current.manifest["generation"] != self.generation):
                raise ValueError("MCX_PUBLISHED_RUN_STALE")
        else:
            raise ValueError("MCX_RESERVED_RUN_STALE")

    def _reserved(self) -> None:
        control = self.publication.status()
        attempt = control["latest_attempt"]
        if (control["admission_generation"] != self.generation
                or attempt["run_id"] != self.run_identity
                or attempt["state"] != "RUNNING"
                or attempt["predecessor_manifest"] != control["current_manifest"]):
            raise ValueError("MCX_RESERVED_RUN_STALE")

    def offer(self, family: McxFamily) -> McxContractOffer:
        """Observational Browser GET; no store or pointer publication."""

        self._reserved()
        if type(family) is not McxFamily:
            raise ValueError("MCX_OFFER_FAMILY_INVALID")
        return self.offers[family]

    def choose(
        self, family: McxFamily, role: McxSelectionRole,
        offer_sha256: str, *, recorded_at: datetime,
    ):
        """Explicit Sponsor POST; one immutable choice under publication order."""

        if type(family) is not McxFamily or type(role) is not McxSelectionRole:
            raise ValueError("MCX_CHOICE_FORM_INVALID")
        offer = self.offers[family]
        if offer_sha256 != offer.offer_sha256:
            raise ValueError("MCX_CHOICE_OFFER_STALE")
        with self.publication._lock():
            self._reserved()
            if self.selections._path(self.run_identity, family).exists():
                raise ValueError("MCX_CHOICE_REPLAY")
            selection = choose_mcx_contract(
                offer, role, sponsor_authorization_identity=self.sponsor_identity,
                recorded_at=recorded_at,
            )
            self.selections.retain(selection)
            return selection

    def process_handoff(self) -> McxAnalysisProcessHandoff:
        """All five recorded selections must match the reserved generation."""

        with self.publication._lock():
            self._reserved()
            handoff = McxAnalysisProcessHandoff.create(
                self.run_identity, self.generation, self.offers, self.selections,
            )
            handoff.analysis_choices()
            # A retained choice never gains a later expiry implicitly. Reject
            # a closed V1 future before dispatch or any Provider acquisition.
            checked_at = self.clock()
            for family, offer in self.offers.items():
                if offer.selection_policy != "MCX_V1_ADVISORY_SELECTION":
                    continue
                selected = self.selections.load(self.run_identity, family)
                chosen = (offer.near if selected.role is McxSelectionRole.NEAR
                          else offer.next_eligible)
                if chosen is None or chosen.v1_reasons(checked_at):
                    raise ValueError("MCX_CONTRACT_SELECTION_INELIGIBLE")
            return handoff

    def selected_contract(
        self, family: McxFamily, current_master: tuple[InstrumentRecord, ...],
        *, acquired_at: datetime,
    ) -> InstrumentRecord:
        self._reserved()
        return selected_mcx_instrument_before_acquisition(
            self.selections, self.offers[family], current_master,
            acquired_at=acquired_at,
        )

    def retained_selected_contract(
        self, family: McxFamily, store: ProviderInstrumentSnapshotStore,
        *, acquired_at: datetime,
    ):
        """Read the exact retained Provider record for the Sponsor choice.

        Historical master identity is factual lineage only. This deliberately
        returns a non-authorizing match and does not infer a live master,
        effective specification, or Provider order-quantity conversion.
        """

        from kronos.application.swing_mcx_evidence import read_retained_mcx_master_match

        selected = self.selections.load(self.run_identity, family)
        self._current()
        offer = self.offers[family]
        fact = (offer.near if selected.role is McxSelectionRole.NEAR
                else offer.next_eligible)
        if fact is None or not fact.provider_snapshot_identity or not fact.provider_record_identity:
            raise ValueError("MCX_RETAINED_CONTRACT_REFERENCE_UNAVAILABLE")
        instrument = selected_mcx_instrument_before_acquisition(
            self.selections, offer, (fact.instrument,), acquired_at=acquired_at,
        )
        return read_retained_mcx_master_match(
            store, snapshot_identity=fact.provider_snapshot_identity,
            record_identity=fact.provider_record_identity, family=family,
            normalized_contract=instrument, observed_at=acquired_at,
        )

    def prepare_durable_plan(
        self, review_owner: object, family: McxFamily,
        derivative: InstrumentRecord,
        proof: McxContractProofPrerequisites,
        geometry: McxOneHourGeometry,
        *, prepared_at: datetime, lots: int, maximum_stop_risk: Decimal,
    ) -> tuple[McxPendingPlan, McxPreparedPlanEvidence, Path]:
        """Use real Review/V2 currentness and retain a held prepared plan."""

        self._current()
        selected = self.selections.load(self.run_identity, family)
        if (selected.trading_symbol != derivative.trading_symbol
                or selected.expiry != derivative.expiry.isoformat()):
            raise ValueError("MCX_PLAN_SELECTION_CHANGED")
        owner_selection = select_owner_current_mcx_handoff(
            review_owner, family, derivative, prepared_at=prepared_at,
        )
        require_mcx_choice_matches_handoff(selected, owner_selection.prepared)
        pending = prepare_mcx_pending_from_owner(
            review_owner, family, derivative, proof, geometry,
            prepared_at=prepared_at, lots=lots,
            maximum_stop_risk=maximum_stop_risk,
        )
        record = McxPreparedPlanEvidence.create(pending, owner_selection.prepared)
        # A retained proposal has no current pointer and cannot enter Step-32.
        # The owner's final fence takes WO-05 then WO-07 in that order. Repeat
        # the reserved-run and immutable-choice checks inside it immediately
        # before the append-only write; never nest a second publication lock.
        with owner_selection.final_fence():
            self._current()
            if self.selections.load(self.run_identity, family) != selected:
                raise ValueError("MCX_PLAN_SELECTION_CHANGED")
            path = self.plans.retain(record)
        return pending, record, path

    def sponsor_admission_reasons(
        self, record: McxPreparedPlanEvidence, pending: McxPendingPlan,
        current, proof: McxContractProofPrerequisites,
        *, observed_at: datetime,
    ) -> tuple[str, ...]:
        self._current()
        return mcx_sponsor_admission_reasons(
            record, pending, current, proof, observed_at=observed_at,
        )

    def construct_isolated_trade_plan(
        self, review_owner: object, family: McxFamily, derivative: InstrumentRecord,
        prepared: McxPreparedPlanEvidence, pending: McxPendingPlan,
        geometry: McxOneHourGeometry, proof: McxContractProofPrerequisites,
        facts: McxIsolatedAdmissionFacts, store: LocalMcxTradePlanStore,
        *, opportunity: NativeOpportunityIdentity, created_at: datetime,
    ) -> tuple[McxTradePlanRecord, Path]:
        """Retain a real plan only under the selected Review owner's final fence.

        The fixture-origin fact type has no production composition or Browser
        ingress. Ordinary prepared-plan admission remains held.
        """

        self._current()
        selected = self.selections.load(self.run_identity, family)
        owner = select_owner_current_mcx_handoff(
            review_owner, family, derivative, prepared_at=created_at,
        )
        require_mcx_choice_matches_handoff(selected, owner.prepared)
        plan = construct_isolated_mcx_trade_plan(
            prepared, pending, owner.prepared, geometry, proof, facts,
            selection_sha256=selected.integrity_sha256, opportunity=opportunity,
            created_at=created_at,
        )
        with owner.final_fence():
            self._current()
            if self.selections.load(self.run_identity, family) != selected:
                raise ValueError("MCX_TRADE_PLAN_SELECTION_CHANGED")
            path = store.retain(plan)
        return plan, path

    def construct_v1_advisory_plan(
        self, review_owner: object, family: McxFamily,
        derivative: InstrumentRecord, geometry: McxOneHourGeometry,
        master: ProviderInstrumentSnapshotStore,
        schedule: MarketDaySchedule, store: LocalMcxTradePlanStore,
        *, opportunity: NativeOpportunityIdentity, created_at: datetime,
        geometry_fence: object | None = None,
    ) -> tuple[McxTradePlanRecord, Path]:
        """Retain price advice only from exact selected and current Review bytes.

        Specification, conversion and broker facts are deliberately UNKNOWN;
        the selected authenticated master record proves identity only.
        """
        self._current()
        selected = self.selections.load(self.run_identity, family)
        owner = select_owner_current_mcx_handoff(
            review_owner, family, derivative, prepared_at=created_at)
        require_mcx_choice_matches_handoff(selected, owner.prepared)
        match = self.retained_selected_contract(family, master, acquired_at=created_at)
        if match.normalized_contract != derivative:
            raise ValueError("MCX_V1_SELECTED_MASTER_CHANGED")
        if (type(schedule) is not MarketDaySchedule or schedule.exchange != "MCX"
                or schedule.status is not TradingDayStatus.TRADING
                or schedule.trading_date != created_at.astimezone(
                    ZoneInfo(schedule.timezone)).date()
                or schedule.trading_date > derivative.expiry):
            raise ValueError("MCX_V1_SESSION_UNAVAILABLE")
        windows = tuple(window for window in schedule.windows
                        if window.opens_at <= created_at < window.closes_at)
        if len(windows) != 1:
            raise ValueError("MCX_V1_SESSION_UNAVAILABLE")
        plan = construct_v1_mcx_advisory_plan(
            owner.prepared, selected, geometry, opportunity=opportunity,
            provider_snapshot_identity=match.snapshot_identity,
            provider_record_identity=match.record_identity,
            normalized_instrument_sha256=selected.instrument_sha256,
            session_identity=schedule.session_id,
            entry_session_until=windows[0].closes_at, created_at=created_at,
        )
        master_path = master.path_for(provider="KITE",
            dataset_identity="KITE-INSTRUMENT-MASTER",
            snapshot_identity=match.snapshot_identity)
        with owner.final_fence():
            self._current()
            if geometry_fence is not None:
                from kronos.swing.v1.review_evidence_store import PreparedReadFence
                if type(geometry_fence) is not PreparedReadFence:
                    raise ValueError("MCX_V1_GEOMETRY_FENCE_INVALID")
                geometry_fence.check()
            if self.selections.load(self.run_identity, family) != selected:
                raise ValueError("MCX_V1_SELECTION_CHANGED")
            if (master_path.is_symlink()
                    or sha256(master_path.read_bytes()).hexdigest()
                    != match.snapshot_file_sha256):
                raise ValueError("MCX_V1_MASTER_CHANGED")
            path = store.retain(plan)
        return plan, path

    def admit_isolated_paper_position(
        self, review_owner: object, family: McxFamily, derivative: InstrumentRecord,
        plan: McxTradePlanRecord, plan_store: LocalMcxTradePlanStore,
        sponsor_store: LocalSponsorDecisionStore,
        lifecycle: ActiveTradeLifecycleService,
        historical: LocalMcxHistoricalContractStore,
        judgment: BusinessJudgment, risk: RiskApproval, *, decided_at: datetime,
    ):
        """One exact fixture plan enters the existing Sponsor/lifecycle owners."""

        self._current()
        selected = self.selections.load(self.run_identity, family)
        owner = select_owner_current_mcx_handoff(
            review_owner, family, derivative, prepared_at=plan.created_at,
        )
        require_mcx_choice_matches_handoff(selected, owner.prepared)
        if (
            type(plan) is not McxTradePlanRecord
            or plan.native_run_identity != self.run_identity
            or plan.family is not family
            or (plan.contract_symbol, plan.expiry)
               != (derivative.trading_symbol, derivative.expiry.isoformat())
            or plan.selection_sha256 != selected.integrity_sha256
            or plan.handoff_integrity_sha256 != owner.prepared.integrity_sha256
            or plan_store.load(plan_store._path(plan)) != plan
        ):
            raise ValueError("MCX_SPONSOR_EXACT_PLAN_CHANGED")
        with owner.final_fence():
            self._current()
            if self.selections.load(self.run_identity, family) != selected:
                raise ValueError("MCX_SPONSOR_SELECTION_CHANGED")
            if plan_store.load(plan_store._path(plan)) != plan:
                raise ValueError("MCX_SPONSOR_EXACT_PLAN_CHANGED")
            result = admit_isolated_mcx_paper(
                plan, judgment, risk, sponsor_store,
                current_plan_id=plan.trade_plan_id, decided_at=decided_at,
            )
            position = lifecycle.register(result, plan)
            if position is None:
                raise ValueError("MCX_SPONSOR_POSITION_UNAVAILABLE")
            binding = McxContractBoundLifecycle(lifecycle, historical).retain_existing(
                position.position_id, derivative,
            )
        return result, position, binding

    def admit_isolated_live_position(
        self, review_owner: object, family: McxFamily, derivative: InstrumentRecord,
        plan: McxTradePlanRecord, plan_store: LocalMcxTradePlanStore,
        sponsor_store: LocalSponsorDecisionStore,
        attestation_store: LocalMcxLiveFillAttestationStore,
        attestation: McxLiveFillAttestation,
        outcome: Kr380EntryOutcomeV2, outcome_store: LocalKr380V2Store,
        lifecycle: ActiveTradeLifecycleService,
        historical: LocalMcxHistoricalContractStore,
        judgment: BusinessJudgment, risk: RiskApproval, *, decided_at: datetime,
    ):
        """Fixture-only LIVE admission, with attestation before position commit."""

        self._current()
        selected = self.selections.load(self.run_identity, family)
        owner = select_owner_current_mcx_handoff(
            review_owner, family, derivative, prepared_at=plan.created_at,
        )
        require_mcx_choice_matches_handoff(selected, owner.prepared)
        if (type(plan) is not McxTradePlanRecord
                or plan.native_run_identity != self.run_identity
                or plan.family is not family
                or (plan.contract_symbol, plan.expiry)
                   != (derivative.trading_symbol, derivative.expiry.isoformat())
                or plan.selection_sha256 != selected.integrity_sha256
                or plan.handoff_integrity_sha256 != owner.prepared.integrity_sha256
                or plan_store.load(plan_store._path(plan)) != plan):
            raise ValueError("MCX_SPONSOR_EXACT_PLAN_CHANGED")
        with owner.final_fence():
            self._current()
            if self.selections.load(self.run_identity, family) != selected:
                raise ValueError("MCX_SPONSOR_SELECTION_CHANGED")
            if plan_store.load(plan_store._path(plan)) != plan:
                raise ValueError("MCX_SPONSOR_EXACT_PLAN_CHANGED")
            result = admit_isolated_mcx_live(
                plan, judgment, risk, outcome, outcome_store,
                attestation, attestation_store,
                sponsor_store, current_plan_id=plan.trade_plan_id,
                decided_at=decided_at,
            )
            position = lifecycle.register(result, plan)
            if position is None:
                raise ValueError("MCX_SPONSOR_POSITION_UNAVAILABLE")
            binding = McxContractBoundLifecycle(lifecycle, historical).retain_existing(
                position.position_id, derivative,
            )
        return result, position, binding

    def _v1_current_plan_owner(
        self, review_owner: object, family: McxFamily,
        derivative: InstrumentRecord, plan: McxTradePlanRecord,
        plan_store: LocalMcxTradePlanStore,
    ):
        self._current()
        selected = self.selections.load(self.run_identity, family)
        owner = select_owner_current_mcx_handoff(
            review_owner, family, derivative, prepared_at=plan.created_at)
        require_mcx_choice_matches_handoff(selected, owner.prepared)
        if (type(plan) is not McxTradePlanRecord
                or plan.authority != MCX_V1_ADVISORY_AUTHORITY
                or plan.native_run_identity != self.run_identity
                or plan.family is not family
                or (plan.contract_symbol, plan.expiry)
                   != (derivative.trading_symbol,
                       derivative.expiry.isoformat())
                or plan.selection_sha256 != selected.integrity_sha256
                or plan.handoff_integrity_sha256
                   != owner.prepared.integrity_sha256
                or plan.receipt_integrity_sha256
                   != owner.prepared.bound.receipt_integrity_sha256
                or plan.promotion_integrity_sha256
                   != owner.prepared.bound.promotion_integrity_sha256
                or plan.completed_one_hour_sha256
                   != owner.prepared.bound.completed_one_hour_sha256
                or plan.observation_boundary
                   != owner.prepared.bound.completed_one_hour_boundary
                or plan.manifest_sha256 != owner.prepared.bound.manifest_sha256
                or plan.assessment_sha256 != owner.prepared.bound.assessment_sha256
                or plan_store.load(plan_store._path(plan)) != plan):
            raise ValueError("MCX_V1_EXACT_PLAN_CHANGED")
        return selected, owner

    def admit_v1_paper_position(
        self, review_owner: object, family: McxFamily,
        derivative: InstrumentRecord, plan: McxTradePlanRecord,
        plan_store: LocalMcxTradePlanStore,
        sponsor_store: LocalSponsorDecisionStore,
        lifecycle: ActiveTradeLifecycleService,
        historical: LocalMcxHistoricalContractStore,
        judgment: BusinessJudgment, risk: RiskApproval,
        *, decided_at: datetime,
    ):
        selected, owner = self._v1_current_plan_owner(
            review_owner, family, derivative, plan, plan_store)
        with owner.final_fence():
            self._current()
            if (self.selections.load(self.run_identity, family) != selected
                    or plan_store.load(plan_store._path(plan)) != plan):
                raise ValueError("MCX_V1_EXACT_PLAN_CHANGED")
            result = admit_v1_mcx_paper(
                plan, judgment, risk, sponsor_store,
                current_plan_id=plan.trade_plan_id, decided_at=decided_at)
            position = lifecycle.register(result, plan)
            if position is None:
                raise ValueError("MCX_V1_POSITION_UNAVAILABLE")
            binding = McxContractBoundLifecycle(lifecycle, historical).retain_existing(
                position.position_id, derivative)
        return result, position, binding

    def admit_v1_manual_live_position(
        self, review_owner: object, family: McxFamily,
        derivative: InstrumentRecord, plan: McxTradePlanRecord,
        plan_store: LocalMcxTradePlanStore,
        sponsor_store: LocalSponsorDecisionStore,
        attestation_store: LocalMcxLiveFillAttestationStore,
        broker_store: LocalMcxBrokerFillEvidenceStore,
        broker_bytes: bytes, attestation: McxLiveFillAttestation,
        outcome: McxV1AdvisoryOutcome | None, outcome_store: LocalMcxV1AdvisoryStore,
        lifecycle: ActiveTradeLifecycleService,
        historical: LocalMcxHistoricalContractStore,
        judgment: BusinessJudgment, risk: RiskApproval,
        *, decided_at: datetime,
    ):
        selected, owner = self._v1_current_plan_owner(
            review_owner, family, derivative, plan, plan_store)
        with owner.final_fence():
            self._current()
            if (self.selections.load(self.run_identity, family) != selected
                    or plan_store.load(plan_store._path(plan)) != plan):
                raise ValueError("MCX_V1_EXACT_PLAN_CHANGED")
            result = admit_v1_mcx_manual_live(
                plan, judgment, risk, outcome, outcome_store,
                attestation, attestation_store, broker_store, broker_bytes,
                sponsor_store, current_plan_id=plan.trade_plan_id,
                decided_at=decided_at)
            position = lifecycle.register(result, plan)
            if position is None:
                raise ValueError("MCX_V1_POSITION_UNAVAILABLE")
            binding = McxContractBoundLifecycle(lifecycle, historical).retain_existing(
                position.position_id, derivative)
        return result, position, binding
