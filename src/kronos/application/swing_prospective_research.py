"""Isolated WO-12 update engine. Production capture and Browser wiring are later gates."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import os
from pathlib import Path
import json
import shutil
from statistics import mean, median
from typing import Callable

from kronos.browser.swing_research_workbook import (
    TRACK_COLUMNS, SwingResearchProjection, export_swing_research_workbook,
    validate_swing_research_workbook,
)
from kronos.swing.v1.prospective_research import (
    CONTRACT, HORIZONS, IST, MARKETS, FollowupCandle, GovernedCalendar, GovernedSession,
    ProspectiveResearchStore, Record, _canonical, _digest, _fsync_dir,
    calendar_record, candle_record, evaluate, record,
)


CANONICAL_ROOT = Path.home() / "Documents" / "Project-KRONOS" / "Statistics" / "Swing"
MAX_NEW_CANDLE_REQUESTS = 60


@dataclass(frozen=True, slots=True)
class UpdateResult:
    operation_identity: str
    outcome: str
    new_candles: int
    updated_checkpoints: int
    pending: int
    unavailable: int
    expiry_limited: int
    workbooks: tuple[str, ...]
    last_successful_publication: str | None
    remaining_candle_requests: int | None = 0
    unavailable_sources: tuple[str, ...] = ()


class SwingProspectiveResearchApplication:
    """Explicit Sponsor update over already-admitted compact research records."""

    def __init__(self, *, store: ProspectiveResearchStore,
                 publication_root: Path = CANONICAL_ROOT,
                 clock: Callable[[], datetime] | None = None,
                 fault_hook: Callable[[str], None] | None = None) -> None:
        self.store = store
        self.publication_root = Path(publication_root)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.fault_hook = fault_hook or (lambda _: None)
        if not self.publication_root.is_absolute():
            raise ValueError("SWING_WO12_PUBLICATION_ROOT_INVALID")

    def capture_admitted(self, source: Record, *milestones: Record,
                         decision: Record | None = None) -> None:
        """A future owner hook calls this; no Browser/analysis path calls it yet."""
        with self.store.transaction():
            self.store.retain_origin(source)
            for item in milestones:
                if item.data["origin_identity"] != source.identity:
                    raise ValueError("SWING_WO12_MILESTONE_BINDING_INVALID")
                self.store.retain_milestone(item)
            if decision is not None:
                if decision.data["origin_identity"] != source.identity:
                    raise ValueError("SWING_WO12_DECISION_BINDING_INVALID")
                self.store.retain_decision(decision)

    def capture_lifecycle(self, source: Record, track: Record) -> None:
        """Retain a separate exact owner event after the source owner admits it."""
        if track.data["origin_identity"] != source.identity:
            raise ValueError("SWING_WO12_LIFECYCLE_BINDING_INVALID")
        with self.store.transaction():
            decision = next((d for d in self.store.records("DECISION")
                             if d.data["origin_identity"] == source.identity), None)
            truth = track.data["truth_class"]
            if truth != "OBJECTIVE_MODEL":
                if decision is None:
                    raise ValueError("SWING_WO12_SPONSOR_DECISION_MISSING")
                choice = decision.data["choice"]
                disposition = decision.data["activation_disposition"]
                if (truth == "PAPER_OBSERVATION" and not (choice == "PAPER" and disposition.startswith("BLOCKED_"))
                        or truth == "PAPER_POSITION" and not (choice == "PAPER" and disposition == "ACTIVATED")
                        or truth == "LIVE_SPONSOR" and not (choice == "LIVE" and disposition == "ACTIVATED")):
                    raise ValueError("SWING_WO12_LIFECYCLE_DECISION_BINDING_INVALID")
            self.store.retain_lifecycle_track(track)

    def capture_revised_candle(self, candle: FollowupCandle) -> None:
        """Explicit owner-supplied correction, never a silent Provider refresh."""
        with self.store.transaction():
            self.store.retain_candle(candle_record(candle))

    def status(self) -> dict[str, object]:
        """Observational status. No source repair, Provider or workbook write."""
        receipts = self.store.records("RECEIPT")
        verified = [r for r in receipts if self._receipt_verified(r)]
        latest = max(verified, key=lambda r: r.data["published_at"], default=None)
        return {"origins": len(self.store.origins()),
                "milestones": len(self.store.records("MILESTONE")),
                "publication_root": str(self.publication_root),
                "last_successful_publication": None if latest is None else latest.data["published_at"],
                "verified_months": sorted({r.data["year_month"] for r in verified})}

    def update(self, *, operation_identity: str,
               sessions: dict[str, GovernedCalendar],
               fetch_missing: Callable[[str, GovernedSession], FollowupCandle | None] | None,
               as_of: datetime | None = None,
               equity_basis: Callable[[Record, Record, tuple[GovernedSession, ...], int, datetime], tuple[str, str | None]] | None = None) -> UpdateResult:
        """One bounded, deduplicated explicit update; never implicit Connect."""
        if not isinstance(operation_identity, str) or not operation_identity or len(operation_identity) > 120:
            raise ValueError("SWING_WO12_OPERATION_IDENTITY_INVALID")
        observed = self.clock() if as_of is None else as_of
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError("SWING_WO12_AWARE_BOUNDARY_REQUIRED")
        if fetch_missing is not None and not callable(fetch_missing):
            raise ValueError("SWING_WO12_FETCH_BOUNDARY_INVALID")
        key = _digest({"operation_identity": operation_identity})
        with self.store.transaction():
            self._recover_interrupted_publications()
            prior = self.store.pointer("UPDATE", key)
            if prior is not None:
                data = prior.data
                return UpdateResult(operation_identity, "ALREADY_APPLIED",
                                    data["new_candles"], data["updated_checkpoints"],
                                    data["pending"], data["unavailable"],
                                    data["expiry_limited"], tuple(data["workbooks"]),
                                    data["last_successful_publication"],
                                    data.get("remaining_candle_requests", 0))
            origins = {o.identity: o for o in self.store.origins()}
            milestones = self.store.records("MILESTONE")
            required_markets = {origins[m.data["origin_identity"]].data["market"] for m in milestones}
            unavailable_sources = []
            verified_sessions: dict[str, tuple[GovernedSession, ...]] = {}
            for market in sorted(required_markets):
                calendar = sessions.get(market)
                if (type(calendar) is not GovernedCalendar or calendar.market != market
                        or calendar.complete_through < observed.astimezone(IST).date()
                        or calendar.observed_at > observed
                        or any(calendar.complete_from > datetime.fromisoformat(m.data["occurred_at"]).astimezone(IST).date()
                               for m in milestones if origins[m.data["origin_identity"]].data["market"] == market)):
                    unavailable_sources.append(market + ":CALENDAR_UNAVAILABLE_OR_TRUNCATED")
                    continue
                try:
                    self.store.retain_calendar(calendar_record(calendar))
                except ValueError as error:
                    if str(error) not in {"SWING_WO12_CALENDAR_HISTORY_CONFLICT",
                                          "SWING_WO12_CALENDAR_SOURCE_CONFLICT"}:
                        raise
                    unavailable_sources.append(market + ":" + str(error))
                    continue
                verified_sessions[market] = calendar.sessions
            if unavailable_sources:
                return UpdateResult(operation_identity, "CALENDAR_UNAVAILABLE", 0, 0, 0, 0, 0,
                                    (), self.status()["last_successful_publication"],
                                    None, tuple(unavailable_sources))
            retained_candles = self.store.current_candles()
            needed: dict[tuple[str, str], GovernedSession] = {}
            for m in milestones:
                o = origins[m.data["origin_identity"]]
                if m.data["reference_price"] is None:
                    continue
                market_sessions = verified_sessions[o.data["market"]]
                after = [s for s in market_sessions if s.trading_date >
                         datetime.fromisoformat(m.data["occurred_at"]).astimezone(IST).date()]
                expiry = o.data["expiry"]
                for s in after[:10]:
                    if s.closes_at > observed or (expiry is not None and s.trading_date.isoformat() > expiry):
                        continue
                    pair = (o.data["exact_contract_identity"], s.identity)
                    if pair not in retained_candles:
                        needed[pair] = s
            if needed and fetch_missing is None:
                return UpdateResult(operation_identity, "ACQUISITION_UNAVAILABLE", 0, 0,
                                    0, 0, 0, (), self.status()["last_successful_publication"],
                                    len(needed), ("FOLLOWUP_ACQUISITION_UNAVAILABLE",))
            new_candles = 0
            for (contract, session_identity), session in sorted(needed.items())[:MAX_NEW_CANDLE_REQUESTS]:
                if fetch_missing is None:
                    continue
                try:
                    supplied = fetch_missing(contract, session)
                except (ConnectionError, TimeoutError, OSError):
                    return UpdateResult(operation_identity, "ACQUISITION_UNAVAILABLE", new_candles,
                                        0, 0, 0, 0, (),
                                        self.status()["last_successful_publication"],
                                        len(needed) - new_candles,
                                        ("FOLLOWUP_ACQUISITION_INTERRUPTED:" + contract + ":" + session_identity,))
                if supplied is None:
                    return UpdateResult(operation_identity, "ACQUISITION_UNAVAILABLE", new_candles,
                                        0, 0, 0, 0, (),
                                        self.status()["last_successful_publication"],
                                        len(needed) - new_candles,
                                        ("FOLLOWUP_CANDLE_UNAVAILABLE:" + contract + ":" + session_identity,))
                if (type(supplied) is not FollowupCandle
                        or supplied.exact_contract_identity != contract
                        or supplied.session_identity != session_identity
                        or supplied.retrieved_at < session.closes_at):
                    raise ValueError("SWING_WO12_PROVIDER_CANDLE_BINDING_INVALID")
                retained = self.store.retain_candle(candle_record(supplied))
                retained_candles[(contract, session_identity)] = retained
                new_candles += 1
            remaining = len(needed) - new_candles
            if remaining:
                # The batch is durable, but incomplete source acquisition cannot
                # create PENDING/UNAVAILABLE checkpoints or replace a workbook.
                return UpdateResult(operation_identity, "CATCHUP_INCOMPLETE", new_candles,
                                    0, 0, 0, 0, (),
                                    self.status()["last_successful_publication"], remaining)
            updated = 0
            status_counts = {"PENDING": 0, "UNAVAILABLE": 0, "EXPIRY_LIMITED": 0}
            for m in milestones:
                o = origins[m.data["origin_identity"]]
                market_sessions = verified_sessions[o.data["market"]]
                contract_candles = {s.identity: retained_candles[(o.data["exact_contract_identity"], s.identity)]
                                    for s in market_sessions
                                    if (o.data["exact_contract_identity"], s.identity) in retained_candles}
                for horizon in HORIZONS:
                    basis_state, basis_identity = (
                        (None, None) if equity_basis is None else
                        equity_basis(m, o, market_sessions, horizon, observed))
                    result = evaluate(m, o, horizon=horizon, sessions=market_sessions,
                                      candles=contract_candles, as_of=observed,
                                      equity_basis_state=basis_state,
                                      equity_basis_identity=basis_identity)
                    pointer_key = _digest({"milestone": m.identity, "horizon": horizon})
                    current = self.store.pointer("CHECKPOINT", pointer_key)
                    if current != result:
                        self.store.retain(result)
                        self.store.publish_pointer("CHECKPOINT", pointer_key, result)
                        updated += 1
                    if result.data["status"] in status_counts:
                        status_counts[result.data["status"]] += 1
            months = sorted({o.data["origin_month"] for o in origins.values()})
            publications = []
            for month in months:
                publications.append(self._publish_month(month, observed))
            last = max((r.data["published_at"] for r in publications), default=None)
            outcome = "PUBLISHED" if any(r.data["publication_outcome"] == "PUBLISHED" for r in publications) else "ALREADY_UP_TO_DATE"
            completed = record("UPDATE", operation_identity=operation_identity,
                               analytical_cutoff=observed.isoformat(),
                               completed_at=self.clock().isoformat(), outcome=outcome,
                               new_candles=new_candles, updated_checkpoints=updated,
                               pending=status_counts["PENDING"],
                               unavailable=status_counts["UNAVAILABLE"],
                               expiry_limited=status_counts["EXPIRY_LIMITED"],
                               workbooks=[r.data["workbook_path"] for r in publications],
                               last_successful_publication=last,
                               remaining_candle_requests=0,
                               authority="RESEARCH_ONLY")
            self.store.retain(completed)
            self.store.publish_pointer("UPDATE", key, completed)
            return UpdateResult(operation_identity, outcome, new_candles, updated,
                                status_counts["PENDING"], status_counts["UNAVAILABLE"],
                                status_counts["EXPIRY_LIMITED"],
                                tuple(r.data["workbook_path"] for r in publications), last)

    def _projection(self, month: str, as_of: datetime) -> SwingResearchProjection:
        origins = tuple(o for o in self.store.origins() if o.data["origin_month"] == month)
        milestones = tuple(m for m in self.store.records("MILESTONE")
                           if any(o.identity == m.data["origin_identity"] for o in origins))
        decisions = {d.data["origin_identity"]: d for d in self.store.records("DECISION")}
        lifecycle_events = tuple(item for item in self.store.records("LIFECYCLE_TRACK")
                                 if any(o.identity == item.data["origin_identity"] for o in origins))
        latest_lifecycle: dict[tuple[str, str], Record] = {}
        for item in lifecycle_events:
            key = (item.data["origin_identity"], item.data["track_identity"])
            old = latest_lifecycle.get(key)
            if old is None or (item.data["observed_at"], item.identity) > (old.data["observed_at"], old.identity):
                latest_lifecycle[key] = item
        checkpoints = {}
        for m in milestones:
            for horizon in HORIZONS:
                key = _digest({"milestone": m.identity, "horizon": horizon})
                current = self.store.pointer("CHECKPOINT", key)
                if current is not None:
                    checkpoints[(m.identity, horizon)] = current
        by_origin = {}
        for m in milestones:
            by_origin.setdefault(m.data["origin_identity"], {})[m.data["score"]] = m
        opportunities = tuple((
            o.data["opportunity_identity"], o.data["origin_month"], o.data["market"],
            o.data["instrument"], o.data["exact_contract_identity"], o.data["expiry"],
            o.data["direction"], o.data["admitted_at"], o.data["source_identity"],
            o.data["source_version"],
            None if o.identity not in decisions else decisions[o.identity].data["choice"],
            None if o.identity not in decisions else decisions[o.identity].data["activation_disposition"],
            None if o.identity not in decisions else decisions[o.identity].data["source_identity"],
            None if 4 not in by_origin.get(o.identity, {}) else by_origin[o.identity][4].data["occurred_at"],
            None if 5 not in by_origin.get(o.identity, {}) else by_origin[o.identity][5].data["occurred_at"],
            o.data["reference_price"], o.data["price_observation_identity"], "RESEARCH_ONLY",
        ) for o in sorted(origins, key=lambda item: item.data["opportunity_identity"]))
        def track_row(values: dict[str, object]) -> tuple[object, ...]:
            return tuple(values.get(column) for column in TRACK_COLUMNS)

        checkpoint_rows = tuple(track_row({
            "opportunity_identity": c.data["opportunity_identity"],
            "track_kind": "DIRECTION_CHECKPOINT", "truth_class": "CANDLE_DIRECTION_ONLY",
            "track_identity": m.identity + ":" + str(horizon),
            "milestone_identity": m.identity, "market": c.data["market"],
            "exact_contract_identity": m.data["exact_contract_identity"],
            "direction": c.data["direction"], "readiness_score": c.data["score"],
            "readiness_state": m.data["readiness_state"], "milestone_at": m.data["occurred_at"],
            "milestone_reference_price": m.data["reference_price"],
            "price_observation_identity": m.data["price_observation_identity"],
            "price_received_at": m.data["price_received_at"],
            "horizon_sessions": c.data["horizon"],
            "due_session_identity": c.data["due_session_identity"],
            "status": c.data["status"], "reason": c.data["reason"],
            "actual_close": None if c.data["actual_close"] is None else float(c.data["actual_close"]),
            "raw_change_pct": None if c.data["raw_pct"] is None else float(c.data["raw_pct"]),
            "direction_adjusted_pct": None if c.data["direction_adjusted_pct"] is None else float(c.data["direction_adjusted_pct"]),
            "candle_favourable_pct": None if c.data["candle_excursion_favourable_pct"] is None else float(c.data["candle_excursion_favourable_pct"]),
            "candle_adverse_pct": None if c.data["candle_excursion_adverse_pct"] is None else float(c.data["candle_excursion_adverse_pct"]),
            "excursion_authority": c.data["excursion_authority"],
        }) for m in sorted(milestones, key=lambda item: (item.data["opportunity_identity"], item.data["score"]))
            for horizon in HORIZONS for c in [checkpoints.get((m.identity, horizon))] if c is not None)
        lifecycle_rows = tuple(track_row({
            "opportunity_identity": item.data["opportunity_identity"],
            "track_kind": "LIFECYCLE", "truth_class": item.data["truth_class"],
            "track_identity": item.data["track_identity"],
            "market": next(o.data["market"] for o in origins if o.identity == item.data["origin_identity"]),
            "exact_contract_identity": next(o.data["exact_contract_identity"] for o in origins if o.identity == item.data["origin_identity"]),
            "direction": next(o.data["direction"] for o in origins if o.identity == item.data["origin_identity"]),
            "lifecycle_state": item.data["state"],
            "entry_price": None if item.data["entry_price"] is None else float(item.data["entry_price"]),
            "exit_price": None if item.data["exit_price"] is None else float(item.data["exit_price"]),
            "source_gross_pnl": None if item.data["gross_pnl"] is None else float(item.data["gross_pnl"]),
            "sponsor_attested": item.data["sponsor_attested"],
        }) for item in sorted(latest_lifecycle.values(), key=lambda item: (item.data["opportunity_identity"],
                                                                              item.data["track_identity"])))
        tracks = checkpoint_rows + lifecycle_rows
        events = tuple(sorted((
            (o.data["opportunity_identity"], "ORIGIN", o.identity,
             o.data["admitted_at"], o.data["source_identity"]) for o in origins
        ), key=lambda row: (row[3], row[2]))) + tuple(sorted((
            (m.data["opportunity_identity"], "READINESS_" + str(m.data["score"]), m.identity,
             m.data["occurred_at"], m.data["source_identity"]) for m in milestones
        ), key=lambda row: (row[3], row[2]))) + tuple(sorted((
            (o.data["opportunity_identity"], "SPONSOR_DECISION", decisions[o.identity].identity,
             decisions[o.identity].data["decided_at"], decisions[o.identity].data["source_identity"])
            for o in origins if o.identity in decisions
        ), key=lambda row: (row[3], row[2]))) + tuple(sorted((
            (item.data["opportunity_identity"], "LIFECYCLE_" + item.data["truth_class"],
             item.identity, item.data["observed_at"], item.data["source_event_identity"])
            for item in lifecycle_events
        ), key=lambda row: (row[3], row[2])))
        events = tuple(sorted(events, key=lambda row: (row[3], row[2])))
        quality = tuple((c.data["opportunity_identity"], m.identity,
                         c.data["horizon"], c.data["status"], c.data["reason"])
                        for m in milestones for horizon in HORIZONS
                        for c in [checkpoints.get((m.identity, horizon))]
                        if c is not None and c.data["status"] in {"PENDING", "UNAVAILABLE", "EXPIRY_LIMITED"})
        analysis = self._analysis(origins, milestones, checkpoints)
        source_identity = _digest({"origins": [o.identity for o in origins],
                                   "milestones": [m.identity for m in milestones],
                                   "decisions": [decisions[o.identity].identity for o in origins if o.identity in decisions],
                                   "lifecycle": sorted(item.identity for item in lifecycle_events),
                                   "checkpoints": sorted(c.identity for c in checkpoints.values())})
        # Stable source boundary prevents a repeat click from rewriting an unchanged workbook.
        times = [datetime.fromisoformat(o.data["admitted_at"]) for o in origins]
        times += [datetime.fromisoformat(m.data["occurred_at"]) for m in milestones]
        generated = max(times, default=as_of).astimezone(timezone.utc)
        metadata = (("contract_identity", CONTRACT), ("contract_version", "1"),
                    ("source_boundary_identity", source_identity),
                    ("origin_month", month), ("generated_at", generated.isoformat()),
                    ("session_rule", "POST_MILESTONE_COMPLETED_GOVERNED_SESSIONS_EXCLUDE_MILESTONE_DATE"),
                    ("corporate_action_rule", "NSE_ACTION_WINDOW_UNAVAILABLE_WITHOUT_GOVERNED_COMMON_BASIS"),
                    ("excursion_rule", "SUBSEQUENT_COVERED_CANDLES_ONLY_NOT_LIFECYCLE_MFE_MAE"),
                    ("metric_authority", "DIRECTION_ONLY_NO_R_OR_MONETARY_METRICS"))
        projection_identity = _digest({"month": month, "source": source_identity,
                                       "opportunities": opportunities, "tracks": tracks,
                                       "analysis": analysis, "quality": quality})
        return SwingResearchProjection(month, generated, projection_identity,
                                       opportunities, tracks, events, analysis, quality, metadata)

    @staticmethod
    def _analysis(origins: tuple[Record, ...], milestones: tuple[Record, ...],
                  checkpoints: dict[tuple[str, int], Record]) -> tuple[tuple[object, ...], ...]:
        output = []
        for market in sorted(MARKETS):
            for score in (4, 5):
                for direction in ("LONG", "SHORT"):
                    origin_count = sum(o.data["market"] == market and o.data["direction"] == direction
                                       for o in origins)
                    selected = [m for m in milestones if m.data["market"] == market
                                and m.data["score"] == score and m.data["direction"] == direction]
                    for horizon in HORIZONS:
                        rows = [checkpoints[(m.identity, horizon)] for m in selected
                                if (m.identity, horizon) in checkpoints]
                        eligible = [c for c in rows if c.data["status"] in {
                            "WITH_PREDICTION", "AGAINST_PREDICTION", "UNCHANGED"}]
                        movements = [float(c.data["direction_adjusted_pct"]) for c in eligible]
                        success = sum(c.data["status"] == "WITH_PREDICTION" for c in eligible)
                        always_up = sum(Decimal(c.data["raw_pct"]) > 0 for c in eligible)
                        denominator = len(eligible)
                        output.append((market, score, direction, horizon, origin_count,
                                       len(selected), denominator,
                                       sum(c.data["status"] == "PENDING" for c in rows),
                                       sum(c.data["status"] == "UNAVAILABLE" for c in rows),
                                       sum(c.data["status"] == "EXPIRY_LIMITED" for c in rows),
                                       success,
                                       sum(c.data["status"] == "AGAINST_PREDICTION" for c in eligible),
                                       sum(c.data["status"] == "UNCHANGED" for c in eligible),
                                       None if not denominator else success / denominator,
                                       None if not denominator else always_up / denominator,
                                       None if not movements else mean(movements),
                                       None if not movements else median(movements),
                                       None if not movements else min(movements),
                                       None if not movements else max(movements),
                                       "SAME_EXACT_MILESTONE_HORIZON_ELIGIBLE_SAMPLE; LINKED_ROWS_NOT_INDEPENDENT"))
        return tuple(output)

    def _publish_month(self, month: str, as_of: datetime) -> Record:
        projection = self._projection(month, as_of)
        target = self.publication_root / f"KRONOS_Swing_Research_{month}.xlsx"
        current = self.store.pointer("RECEIPT", month)
        same_projection = current is not None and current.data["projection_identity"] == projection.projection_identity
        # New XLSX creation is factual. Exact replay/rebuild keeps the originally
        # receipted creation instant; legacy receipts retain their original bytes.
        generated_at = (datetime.fromisoformat(current.data["generated_at"])
                        if same_projection and current.data.get("generated_at") else
                        projection.generated_at if same_projection else self.clock())
        projection = replace(projection, generated_at=generated_at,
                             metadata=tuple((key, generated_at.isoformat() if key == "generated_at" else value)
                                            for key, value in projection.metadata))
        payload = export_swing_research_workbook(projection)
        checksum = sha256(payload).hexdigest()
        if (current is not None and current.data["projection_identity"] == projection.projection_identity
                and current.data["workbook_sha256"] == checksum and self._receipt_verified(current)):
            return record("PUBLICATION_RESULT", year_month=month, publication_outcome="ALREADY_UP_TO_DATE",
                          workbook_path=str(target), published_at=current.data["published_at"],
                          authority="RESEARCH_ONLY")
        if (current is not None and current.data["projection_identity"] == projection.projection_identity
                and current.data["workbook_sha256"] == checksum):
            # Rebuild the exact receipted bytes; no new source or receipt authority.
            _atomic_replace(target, payload)
            if not self._receipt_verified(current):
                raise ValueError("SWING_WO12_RECEIPTED_RECOVERY_FAILED")
            return record("PUBLICATION_RESULT", year_month=month, publication_outcome="RECOVERED",
                          workbook_path=str(target), published_at=current.data["published_at"],
                          authority="RESEARCH_ONLY")
        previous = target.read_bytes() if target.exists() else None
        stage = self.store.root / "staging" / (month + "-" + projection.projection_identity)
        stage.mkdir(parents=True, exist_ok=True)
        staged = stage / target.name
        _durable_write(staged, payload)
        if previous is not None:
            _durable_write(stage / "previous.xlsx", previous)
        _durable_write(stage / "intent.json", _canonical({
            "year_month": month, "target": str(target),
            "previous_sha256": None if previous is None else sha256(previous).hexdigest(),
            "current_receipt_identity": None if current is None else current.identity,
        }) + b"\n")
        validate_swing_research_workbook(staged.read_bytes(), projection)
        if staged.read_bytes() != payload:
            raise ValueError("SWING_WO12_STAGED_READBACK_MISMATCH")
        self.fault_hook("before_replace")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(staged, target)
            _fsync_dir(target.parent)
            self.fault_hook("after_replace")
            readback = target.read_bytes()
            validate_swing_research_workbook(readback, projection)
            if readback != payload or sha256(readback).hexdigest() != checksum:
                raise ValueError("SWING_WO12_PUBLISHED_READBACK_MISMATCH")
            receipt = record("RECEIPT", year_month=month, workbook_path=str(target),
                             workbook_sha256=checksum, workbook_bytes=len(payload),
                             projection_identity=projection.projection_identity,
                             generated_at=generated_at.isoformat(),
                             analytical_cutoff=as_of.isoformat(),
                             published_at=self.clock().isoformat(),
                             prior_workbook_sha256=None if previous is None else sha256(previous).hexdigest(),
                             readback_verified=True, authority="RESEARCH_ONLY")
            self.fault_hook("before_receipt")
            self.store.retain(receipt)
            self.store.publish_pointer("RECEIPT", month, receipt)
            shutil.rmtree(stage, ignore_errors=True)
            return record("PUBLICATION_RESULT", year_month=month, publication_outcome="PUBLISHED",
                          workbook_path=str(target), published_at=receipt.data["published_at"],
                          authority="RESEARCH_ONLY")
        except Exception:
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                _atomic_replace(target, previous)
            shutil.rmtree(stage, ignore_errors=True)
            raise

    def _recover_interrupted_publications(self) -> None:
        staging = self.store.root / "staging"
        if not staging.exists():
            return
        for stage in sorted(path for path in staging.iterdir() if path.is_dir()):
            intent_path = stage / "intent.json"
            if not intent_path.exists():
                continue
            intent = json.loads(intent_path.read_bytes())
            target = Path(intent["target"])
            month = intent["year_month"]
            if target != self.publication_root / f"KRONOS_Swing_Research_{month}.xlsx":
                raise ValueError("SWING_WO12_STAGING_TARGET_INVALID")
            current = self.store.pointer("RECEIPT", month)
            if current is not None and self._receipt_verified(current):
                shutil.rmtree(stage)
                continue
            previous_path = stage / "previous.xlsx"
            if intent["previous_sha256"] is None:
                target.unlink(missing_ok=True)
            else:
                previous = previous_path.read_bytes()
                if sha256(previous).hexdigest() != intent["previous_sha256"]:
                    raise ValueError("SWING_WO12_STAGING_BACKUP_INVALID")
                _atomic_replace(target, previous)
            shutil.rmtree(stage)

    @staticmethod
    def _receipt_verified(receipt: Record) -> bool:
        path = Path(receipt.data["workbook_path"])
        try:
            payload = path.read_bytes()
        except OSError:
            return False
        return (len(payload) == receipt.data["workbook_bytes"]
                and sha256(payload).hexdigest() == receipt.data["workbook_sha256"])


def _durable_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_dir(path.parent)


def _atomic_replace(path: Path, payload: bytes) -> None:
    staged = path.with_name(path.name + ".rollback")
    _durable_write(staged, payload)
    os.replace(staged, path)
    _fsync_dir(path.parent)
