"""WO-12 capture at retained Swing owner events; no admission authority."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from hashlib import sha256
import json

from kronos.application.swing_prospective_research import SwingProspectiveResearchApplication
from kronos.application.swing_research_inbox import (
    SwingResearchInbox, restore_price_fact, serialise_price_fact,
)
from kronos.provider.contracts.monitoring import ProviderMarketTick
from kronos.swing.v1.analytical_promotion_v2 import V2PromotionRecord
from kronos.swing.v1.opportunity_continuity import ContinuityDisposition, PreparedContinuity
from kronos.swing.v1.prospective_research import (
    decision, lifecycle_track, milestone_from_v2_promotion, origin,
)


def _binding(row) -> dict[str, str | None]:
    binding = row.source_binding
    if binding is None:
        raise ValueError("SWING_WO12_EXACT_CONTRACT_UNAVAILABLE")
    return asdict(binding)


def _contract_identity(binding: dict[str, str | None]) -> str:
    """Content identity includes provider, segment, symbol, type and expiry."""
    payload = json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()
    return sha256(payload).hexdigest()


def _price_at(binding: dict[str, str | None], boundary: datetime,
              ticks: tuple[ProviderMarketTick, ...]) -> dict:
    eligible = []
    for tick in ticks:
        if type(tick) is not ProviderMarketTick or tick.last_price <= 0:
            continue
        instrument = tick.instrument
        if (instrument.provider != binding["provider"]
                or instrument.exchange != binding["exchange"]
                or instrument.segment != binding["segment"]
                or instrument.trading_symbol != binding["trading_symbol"]
                or instrument.instrument_type != binding["instrument_type"]
                or (None if instrument.expiry is None else instrument.expiry.isoformat()) != binding["expiry"]
                or tick.observed_at > boundary or tick.received_at > boundary):
            continue
        eligible.append(tick)
    if not eligible:
        return {}
    tick = max(eligible, key=lambda value: (value.observed_at, value.received_at))
    identity = sha256(json.dumps({
        "binding": binding, "price": str(tick.last_price),
        "observed_at": tick.observed_at.isoformat(),
        "received_at": tick.received_at.isoformat(),
        "source": tick.source, "connection_id": tick.connection_id,
        "sequence": tick.source_sequence,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return dict(reference_price=str(tick.last_price), price_observation_identity=identity,
                price_observed_at=tick.observed_at, price_received_at=tick.received_at,
                price_source=tick.source)


class SwingResearchEventCapture:
    """Idempotent projection of already committed events into WO-12 evidence."""

    def __init__(self, research: SwingProspectiveResearchApplication, *,
                 require_commissioning: bool = False,
                 inbox: SwingResearchInbox | None = None) -> None:
        self.research = research
        self.require_commissioning = require_commissioning
        self.inbox = inbox

    def retain_admission_event(self, contribution: PreparedContinuity, *,
                               ticks: tuple[ProviderMarketTick, ...] = ()) -> None:
        """Record timely price facts without entering the long research lock."""
        if self.inbox is None:
            self.capture_committed(contribution, ticks=ticks)
            return
        contribution.validate()
        facts = {row.opportunity_id: serialise_price_fact(
                    _price_at(_binding(row), row.first_admitted, ticks))
                 for row in contribution.rows
                 if row.disposition is ContinuityDisposition.ADMITTED}
        self.inbox.retain("ADMISSION", contribution.native_run.run_identity,
                          {"continuity_sha256": contribution.integrity_sha256,
                           "prices": facts})

    def retain_v2_event(self, contribution: PreparedContinuity,
                        promotion: V2PromotionRecord, *,
                        ticks: tuple[ProviderMarketTick, ...] = ()) -> None:
        if self.inbox is None:
            self.capture_v2(contribution, promotion, ticks=ticks)
            return
        contribution.validate()
        if type(promotion) is not V2PromotionRecord:
            raise ValueError("SWING_WO12_V2_PROMOTION_REQUIRED")
        source = promotion.value["source"]
        if source["native_run_identity"] != contribution.native_run.run_identity:
            raise ValueError("SWING_WO12_V2_RUN_MISMATCH")
        rows = [row for row in contribution.rows
                if row.canonical_instrument == source["canonical_instrument"]]
        if len(rows) != 1 or rows[0].source_binding is None:
            raise ValueError("SWING_WO12_V2_ASSESSMENT_MISMATCH")
        at = datetime.fromisoformat(promotion.value["created_at"].replace("Z", "+00:00"))
        self.inbox.retain("V2", promotion.identity,
                          {"run": source["native_run_identity"],
                           "assessment": source["native_assessment_sha256"],
                           "price": serialise_price_fact(_price_at(_binding(rows[0]), at, ticks))})

    def retain_owner_event(self, kind: str, value) -> None:
        if self.inbox is None:
            return
        identities = {
            "SPONSOR": lambda: value.decision.decision_id,
            "OBSERVATION_DECISION": lambda: value.decision.decision_identity,
            "PAPER_OBSERVATION": lambda: value.track.integrity_sha256,
            "LIFECYCLE": lambda: (value.lifecycle_event_ids[-1]
                                   if value.lifecycle_event_ids else value.integrity_hash),
            "CLOSURE": lambda: value.closure_id,
        }
        if kind not in identities:
            raise ValueError("SWING_RESEARCH_OWNER_EVENT_INVALID")
        self.inbox.retain("OWNER", kind + ":" + identities[kind](), {"kind": kind})

    def capture_enabled(self) -> bool:
        """The future release boundary; no pre-commission owner capture."""
        return (not self.require_commissioning or
                self.research.store.pointer("COMMISSIONING", "active") is not None)

    def commissioned_at(self) -> datetime | None:
        marker = self.research.store.pointer("COMMISSIONING", "active")
        if marker is None:
            if self.require_commissioning:
                raise ValueError("SWING_RESEARCH_COMMISSIONING_REQUIRED")
            return None
        return datetime.fromisoformat(marker.data["commissioned_at"])

    def capture_committed(self, contribution: PreparedContinuity, *,
                          ticks: tuple[ProviderMarketTick, ...] = (),
                          price_facts: dict | None = None) -> int:
        contribution.validate()
        commissioned = self.commissioned_at()
        assessments = {item.canonical_instrument: item
                       for item in contribution.native_run.assessments}
        count = 0
        for row in contribution.rows:
            if row.disposition is not ContinuityDisposition.ADMITTED:
                continue
            if commissioned is not None and row.first_admitted is not None and row.first_admitted < commissioned:
                continue
            if (row.opportunity_id is None or row.first_admitted is None
                    or row.origin_run != contribution.native_run.run_identity
                    or row.origin_assessment is None):
                raise ValueError("SWING_WO12_ADMISSION_BINDING_INVALID")
            prior = [item for item in self.research.store.origins()
                     if item.data["opportunity_identity"] == row.opportunity_id]
            if prior:
                if (len(prior) != 1 or prior[0].data["origin_run_identity"] != row.origin_run
                        or prior[0].data["origin_assessment_sha256"] != row.origin_assessment
                        or prior[0].data["contract_binding"] != _binding(row)
                        or prior[0].data["source_sha256"] != contribution.integrity_sha256):
                    raise ValueError("SWING_WO12_ORIGIN_REPLAY_CONFLICT")
                continue
            assessment = assessments[row.canonical_instrument]
            if (assessment.result_sha256 != row.origin_assessment
                    or assessment.opportunity_identity is None
                    or assessment.direction.value not in {"LONG", "SHORT"}):
                raise ValueError("SWING_WO12_ADMISSION_ASSESSMENT_INVALID")
            binding = _binding(row)
            market = ("NSE" if binding["exchange"] == "NSE"
                      else row.canonical_instrument)
            if market not in {"NSE", "GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS"}:
                raise ValueError("SWING_WO12_MARKET_UNCOMMISSIONED")
            expiry = None if binding["expiry"] is None else date.fromisoformat(binding["expiry"])
            source = origin(
                continuity_identity=row.opportunity_id, market=market,
                instrument=row.canonical_instrument,
                contract_identity=_contract_identity(binding), expiry=expiry,
                contract_binding=binding, direction=assessment.direction.value,
                admitted_at=row.first_admitted,
                source_identity="SWING-CONTINUITY:" + contribution.native_run.run_identity,
                source_version="1", source_sha256=contribution.integrity_sha256,
                origin_run_identity=row.origin_run,
                origin_assessment_sha256=row.origin_assessment,
                native_setup_identity=assessment.opportunity_identity.value,
                **(price_facts.get(row.opportunity_id, {}) if price_facts is not None
                   else _price_at(binding, row.first_admitted, ticks)))
            self.research.capture_admitted(source)
            count += 1
        return count

    def capture_v2(self, contribution: PreparedContinuity, promotion: V2PromotionRecord, *,
                   ticks: tuple[ProviderMarketTick, ...] = (),
                   price_fact: dict | None = None) -> bool:
        contribution.validate()
        commissioned = self.commissioned_at()
        if type(promotion) is not V2PromotionRecord:
            raise TypeError("SWING_WO12_V2_PROMOTION_REQUIRED")
        value = promotion.value
        source = value["source"]
        if source["native_run_identity"] != contribution.native_run.run_identity:
            raise ValueError("SWING_WO12_V2_RUN_MISMATCH")
        rows = [row for row in contribution.rows
                if row.canonical_instrument == source["canonical_instrument"]]
        assessments = [item for item in contribution.native_run.assessments
                       if item.canonical_instrument == source["canonical_instrument"]]
        if (len(rows) != 1 or len(assessments) != 1
                or assessments[0].result_sha256 != source["native_assessment_sha256"]
                or rows[0].opportunity_id is None):
            raise ValueError("SWING_WO12_V2_ASSESSMENT_MISMATCH")
        at = datetime.fromisoformat(value["created_at"].replace("Z", "+00:00"))
        if (commissioned is not None and
                (at < commissioned or rows[0].first_admitted < commissioned)):
            return False
        origins = [item for item in self.research.store.origins()
                   if item.data["opportunity_identity"] == rows[0].opportunity_id]
        if len(origins) != 1:
            raise ValueError("SWING_WO12_V2_ORIGIN_UNAVAILABLE")
        item = milestone_from_v2_promotion(origins[0], promotion,
                                          **(price_fact if price_fact is not None else
                                             _price_at(_binding(rows[0]), at, ticks)))
        if item is None:
            return False
        with self.research.store.transaction():
            self.research.store.retain_milestone(item)
        return True

    def _origin_for(self, contribution: PreparedContinuity, run: str, instrument: str):
        if contribution.native_run.run_identity != run:
            raise ValueError("SWING_WO12_OWNER_RUN_MISMATCH")
        rows = [row for row in contribution.rows if row.canonical_instrument == instrument]
        if len(rows) != 1 or rows[0].opportunity_id is None:
            raise ValueError("SWING_WO12_OWNER_OPPORTUNITY_UNAVAILABLE")
        commissioned = self.commissioned_at()
        if (commissioned is not None and rows[0].first_admitted is not None
                and rows[0].first_admitted < commissioned):
            return None
        origins = [item for item in self.research.store.origins()
                   if item.data["opportunity_identity"] == rows[0].opportunity_id]
        if len(origins) != 1:
            raise ValueError("SWING_WO12_OWNER_ORIGIN_UNAVAILABLE")
        return origins[0]

    def capture_native_sponsor(self, contribution: PreparedContinuity, result) -> None:
        """A retained Sponsor decision and optional position are distinct facts."""
        factual = result.decision
        if factual is None:
            return
        source = self._origin_for(contribution, factual.native_run_identity,
                                  factual.canonical_instrument)
        if source is None:
            return
        choice = factual.decision.value
        disposition = ("NOT_APPLICABLE_IGNORE" if choice == "IGNORE" else
                       "ACTIVATED" if result.position is not None else
                       "BLOCKED_" + result.state.value)
        self.research.capture_admitted(source, decision=decision(
            source, choice=choice, activation_disposition=disposition,
            source_identity=factual.decision_id, decided_at=factual.decision_timestamp))
        if result.position is not None:
            position = result.position
            live = position.mode.value == "LIVE"
            self.research.capture_lifecycle(source, lifecycle_track(
                source, truth_class="LIVE_SPONSOR" if live else "PAPER_POSITION",
                track_identity=position.position_id, state=position.state.value,
                source_event_identity=position.integrity_hash,
                source_version=position.contract_version, observed_at=position.created_at,
                entry_price=None if position.actual_entry is None else str(position.actual_entry),
                sponsor_attested=live and position.actual_entry is not None))

    def capture_observation_decision(self, contribution: PreparedContinuity, result) -> None:
        """Only terminal activation facts enter the one immutable decision row."""
        factual, activation = result.decision, result.activation
        disposition = activation.disposition.value
        if disposition == "PENDING_ENTRY_CONFIRMATION":
            return
        source = self._origin_for(contribution, factual.native_run_identity,
                                  factual.canonical_instrument)
        if source is None:
            return
        self.research.capture_admitted(source, decision=decision(
            source, choice=factual.choice.value,
            activation_disposition=disposition,
            source_identity=factual.decision_identity,
            decided_at=factual.decision_timestamp))

    def capture_paper_observation(self, contribution: PreparedContinuity, projection) -> None:
        self.capture_paper_observation_track(contribution, projection.track)

    def capture_paper_observation_track(self, contribution: PreparedContinuity, track) -> None:
        source = self._origin_for(contribution, track.native_run_identity,
                                  track.canonical_instrument)
        if source is None:
            return
        if any(item.data["source_event_identity"] == track.integrity_sha256
               for item in self.research.store.records("LIFECYCLE_TRACK")):
            return
        self.research.capture_lifecycle(source, lifecycle_track(
            source, truth_class="PAPER_OBSERVATION",
            track_identity=track.track_identity, state="STARTED",
            source_event_identity=track.integrity_sha256,
            source_version=track.contract_version, observed_at=track.created_at))

    def capture_native_closure(self, closure) -> None:
        prior = [item for item in self.research.store.records("LIFECYCLE_TRACK")
                 if item.data["track_identity"] == closure.position_id]
        if not prior:
            if self.require_commissioning:
                return
            raise ValueError("SWING_WO12_POSITION_ORIGIN_UNAVAILABLE")
        origins = [item for item in self.research.store.origins()
                   if item.identity == prior[0].data["origin_identity"]]
        if len(origins) != 1 or any(item.data["origin_identity"] != origins[0].identity
                                    for item in prior):
            raise ValueError("SWING_WO12_POSITION_ORIGIN_CONFLICT")
        source = origins[0]
        live = closure.mode.value == "LIVE"
        self.research.capture_lifecycle(source, lifecycle_track(
            source, truth_class="LIVE_SPONSOR" if live else "PAPER_POSITION",
            track_identity=closure.position_id, state="CLOSED",
            source_event_identity=closure.closure_id,
            source_version=closure.contract_version,
            observed_at=closure.exit_timestamp,
            entry_price=str(closure.actual_entry), exit_price=str(closure.actual_exit),
            gross_pnl=None if closure.gross_pnl is None else str(closure.gross_pnl),
            sponsor_attested=live))

    def capture_active_position(self, position) -> None:
        """Link a new governed lifecycle event without sampling every tick."""
        prior = [item for item in self.research.store.records("LIFECYCLE_TRACK")
                 if item.data["track_identity"] == position.position_id]
        if not prior:
            if self.require_commissioning:
                return
            raise ValueError("SWING_WO12_POSITION_ORIGIN_UNAVAILABLE")
        event_identity = (position.lifecycle_event_ids[-1] if position.lifecycle_event_ids
                          else position.integrity_hash)
        if any(item.data["source_event_identity"] == event_identity for item in prior):
            return
        origins = [item for item in self.research.store.origins()
                   if item.identity == prior[0].data["origin_identity"]]
        if len(origins) != 1:
            raise ValueError("SWING_WO12_POSITION_ORIGIN_CONFLICT")
        source = origins[0]
        live = position.mode.value == "LIVE"
        self.research.capture_lifecycle(source, lifecycle_track(
            source, truth_class="LIVE_SPONSOR" if live else "PAPER_POSITION",
            track_identity=position.position_id, state=position.state.value,
            source_event_identity=event_identity,
            source_version=position.policy_version, observed_at=position.updated_at,
            entry_price=None if position.actual_entry is None else str(position.actual_entry),
            sponsor_attested=live and position.actual_entry is not None))

    def capture_lifecycle_event(self, event) -> None:
        prior = [item for item in self.research.store.records("LIFECYCLE_TRACK")
                 if item.data["track_identity"] == event.position_id]
        if not prior:
            raise ValueError("SWING_WO12_POSITION_ORIGIN_UNAVAILABLE")
        if any(item.data["source_event_identity"] == event.event_id for item in prior):
            return
        origins = [item for item in self.research.store.origins()
                   if item.identity == prior[0].data["origin_identity"]]
        if len(origins) != 1:
            raise ValueError("SWING_WO12_POSITION_ORIGIN_CONFLICT")
        source = origins[0]
        live = event.mode.value == "LIVE"
        self.research.capture_lifecycle(source, lifecycle_track(
            source, truth_class="LIVE_SPONSOR" if live else "PAPER_POSITION",
            track_identity=event.position_id, state=event.event_type.value,
            source_event_identity=event.event_id, source_version=event.contract_version,
            observed_at=event.event_timestamp,
            entry_price=None if event.actual_entry is None else str(event.actual_entry),
            sponsor_attested=live and event.actual_entry is not None))

    def replay_retained(self, bundles: tuple, promotions: tuple[V2PromotionRecord, ...],
                        sponsor_results: tuple = (), lifecycle=None,
                        observation_decisions: tuple = (),
                        paper_observation_tracks: tuple = ()) -> None:
        """Explicit, read-verified maintenance replay; never called by startup/GET."""
        commissioned = self.commissioned_at()
        by_run = {}
        for bundle in bundles:
            if bundle.continuity is None:
                continue
            contribution = bundle.continuity.contribution
            by_run[bundle.native.run_identity] = bundle
            receipt = (None if self.inbox is None else self.inbox.read(
                "ADMISSION", contribution.native_run.run_identity))
            if receipt is not None and receipt["continuity_sha256"] != contribution.integrity_sha256:
                raise ValueError("SWING_RESEARCH_ADMISSION_RECEIPT_CONFLICT")
            prices = (None if receipt is None else
                      {key: restore_price_fact(value)
                       for key, value in receipt["prices"].items()})
            self.capture_committed(contribution, price_facts=prices)
        for promotion in promotions:
            if (commissioned is not None and
                    datetime.fromisoformat(promotion.value["created_at"].replace("Z", "+00:00"))
                    < commissioned):
                continue
            source = promotion.value["source"]
            bundle = by_run.get(source["native_run_identity"])
            if (bundle is None or bundle.reference["sha256"]
                    != source["committed_run_manifest_identity"]):
                raise ValueError("SWING_WO12_V2_PUBLICATION_MISMATCH")
            receipt = (None if self.inbox is None else self.inbox.read("V2", promotion.identity))
            if receipt is not None and (receipt["run"] != source["native_run_identity"]
                                        or receipt["assessment"] != source["native_assessment_sha256"]):
                raise ValueError("SWING_RESEARCH_V2_RECEIPT_CONFLICT")
            self.capture_v2(bundle.continuity.contribution, promotion,
                            price_fact=None if receipt is None else
                            restore_price_fact(receipt["price"]))
        for result in sorted(sponsor_results, key=lambda item: item.decision.decision_timestamp):
            bundle = by_run.get(result.decision.native_run_identity)
            if bundle is not None:
                self.capture_native_sponsor(bundle.continuity.contribution, result)
        for result in sorted(observation_decisions,
                             key=lambda item: item.decision.decision_timestamp):
            bundle = by_run.get(result.decision.native_run_identity)
            if bundle is not None:
                self.capture_observation_decision(bundle.continuity.contribution, result)
        for track in sorted(paper_observation_tracks, key=lambda item: item.created_at):
            bundle = by_run.get(track.native_run_identity)
            if bundle is not None:
                self.capture_paper_observation_track(bundle.continuity.contribution, track)
        if lifecycle is not None:
            for event in sorted(lifecycle.events, key=lambda item: (item.event_timestamp, item.event_id)):
                if any(item.data["track_identity"] == event.position_id
                       for item in self.research.store.records("LIFECYCLE_TRACK")):
                    self.capture_lifecycle_event(event)
            for closure in sorted(lifecycle.closures, key=lambda item: item.exit_timestamp):
                if any(item.data["track_identity"] == closure.position_id
                       for item in self.research.store.records("LIFECYCLE_TRACK")):
                    self.capture_native_closure(closure)
