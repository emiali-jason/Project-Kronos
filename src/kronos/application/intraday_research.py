"""WO-12 immutable research ledger and explicit local publication operation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
import os
import re
import tempfile

from kronos.intraday.probables import ProbableState
from kronos.intraday.wo12_research_contract import (
    LOCAL_PUBLICATION_ROOT, POLICY_CHECKSUM, POLICY_IDENTITY, POLICY_VERSION,
    WORKBOOK_SCHEMA, WORKBOOK_VERSION, digest, opportunity_origin, record,
)


IST = ZoneInfo("Asia/Kolkata")


OPPORTUNITY_COLUMNS = (
    "opportunity_id", "opportunity_identity", "canonical_subject_identity", "market_family",
    "market_session_identity", "opportunity_origin_at", "research_date", "day_state", "direction",
    "probable_state", "probable_result_identity", "probables_run_identity",
    "review_cycle_identity", "review_pack_identity", "chart_revision_identity", "answer_pack_identity",
    "wo07f_identity", "wo07f_outcome", "wo09_readiness_identity", "wo09_readiness_state",
    "wo09_highest_satisfied_count", "wo09_first_three_of_five_at", "wo09_first_four_of_five_at",
    "wo09_first_five_of_five_at", "wo09_i1_state", "wo09_i2_state", "wo09_i3_state",
    "wo09_i4_state", "wo09_i5_state", "wo09_outstanding_criteria", "wo09_hard_gate",
    "wo10_opportunity_identity", "wo10_plan_state", "wo10_plan_reason", "setup_family",
    "underlying_entry", "underlying_stop", "underlying_target", "planned_rr",
    "future_contract_identity", "future_trading_symbol", "future_expiry", "future_entry",
    "future_stop", "future_target", "future_basis", "future_spread", "future_volume",
    "future_oi", "future_delta_oi", "future_snapshot_at", "executability",
    "risk_warning_state", "risk_per_lot", "risk_reference_amount", "sponsor_decision",
    "sponsor_decision_at", "wo10_selected_lots_context", "wo11_sponsor_action",
    "discovery_to_three_seconds", "three_to_four_seconds", "four_to_five_seconds",
    "five_to_trade_plan_seconds", "trade_plan_to_sponsor_decision_seconds",
    "sponsor_decision_to_wo11_action_seconds",
    "paper_position_state", "paper_observation_state",
    "paper_entry_price", "paper_exit_price", "paper_points", "paper_model_r",
    "paper_gross_model_result", "observation_entry_price", "observation_exit_price",
    "observation_points", "observation_model_r", "observation_gross_model_result",
    "data_quality_issue_count", "research_authority",
)

TRACK_COLUMNS = (
    "opportunity_id", "opportunity_identity", "track_identity", "truth_class", "model_lots",
    "state", "terminal", "direction", "future_contract_identity", "future_trading_symbol",
    "armed_at", "entry_at", "entry_price", "exit_at", "exit_price", "exit_reason",
    "terminal_status", "points", "model_r", "planned_rr", "gross_model_result", "holding_seconds", "mfe", "mae",
    "full_path_mfe", "full_path_mae", "monitoring_complete", "monitoring_gap_count",
    "eligible_sample_count", "gap_duration_seconds", "coverage_start", "coverage_end", "source_current_identity",
)

EVENT_COLUMNS = (
    "opportunity_id", "opportunity_identity", "event_at", "event_type", "state",
    "source_schema", "source_identity", "truth_class", "fact_identity", "reason",
)

ANALYSIS_COLUMNS = ("metric", "numerator", "denominator", "rate_or_value", "inclusion_rule")
QUALITY_COLUMNS = (
    "opportunity_id", "opportunity_identity", "quality_code", "severity", "source_stage",
    "source_identity", "detail",
)
METADATA_COLUMNS = ("key", "value")


@dataclass(frozen=True, slots=True)
class Formula:
    expression: str
    cached: int | float | str | None = None

    def __post_init__(self):
        object.__setattr__(self, "expression", _portable_formula(self.expression))


@dataclass(frozen=True, slots=True)
class ResearchProjection:
    year_month: str
    generated_at: datetime
    projection_identity: str
    opportunities: tuple[tuple[object, ...], ...]
    tracks: tuple[tuple[object, ...], ...]
    events: tuple[tuple[object, ...], ...]
    analysis: tuple[tuple[object, ...], ...]
    data_quality: tuple[tuple[object, ...], ...]
    metadata: tuple[tuple[object, ...], ...]


@dataclass(frozen=True, slots=True)
class PublicationResult:
    receipt_identity: str
    workbook_path: Path
    workbook_sha256: str
    workbook_bytes: int
    projection_identity: str
    idempotent: bool
    outcome: str = "PUBLISHED"


class IntradayResearchApplication:
    """Compose retained upstream evidence; only ``update`` writes WO-12 state."""

    def __init__(self, *, probables, wo09, futures, lifecycle, store,
                 publication_root: Path = Path(LOCAL_PUBLICATION_ROOT), clock=None) -> None:
        self.probables = probables
        self.wo09 = wo09
        self.futures = futures
        self.lifecycle = lifecycle
        self.store = store
        self.publication_root = Path(publication_root)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _runs(self):
        root = self.probables.root / "runs"
        return tuple(sorted((self.probables.load_run(path.stem) for path in root.glob("*.json")),
                            key=lambda item: (item.analysis_boundary, item.run_identity))) if root.exists() else ()

    def _source_origins(self):
        first = {}
        for run in self._runs():
            for item in run.results:
                if item.state not in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}:
                    continue
                key = (item.canonical_subject_identity, item.market_session_identity)
                candidate = (item.analysis_boundary, item.result_identity, run.run_identity, item)
                if key not in first or candidate[:3] < first[key][:3]:
                    first[key] = candidate
        return tuple(first[key] for key in sorted(first))

    def _ensure_origins(self):
        origins = []
        for at, result_identity, run_identity, result in self._source_origins():
            existing = self.store.origin_for(result.canonical_subject_identity, result.market_session_identity)
            expected = opportunity_origin(
                canonical_subject_identity=result.canonical_subject_identity,
                market_family="MCX" if result.canonical_subject_identity.startswith("MCX-") else "NSE",
                session_identity=result.market_session_identity,
                origin_at=at,
                probable_result_identity=result_identity,
                probables_run_identity=run_identity,
            )
            if existing is not None:
                data = existing.data
                if any(data[key] != expected.data[key] for key in (
                    "opportunity_id", "opportunity_identity", "origin_at",
                    "probable_result_identity", "probables_run_identity",
                )):
                    raise ValueError("WO12_OPPORTUNITY_ORIGIN_IMMUTABILITY_CONFLICT")
                origins.append(existing)
            else:
                origins.append(self.store.retain(expected))
        # A later same-session origin is lawful only after a retained terminal
        # WO-11 track.  A refresh, direction change, or elapsed time is never a
        # reset by itself.
        terminal_states = {"CLOSED", "CANCELLED_BEFORE_ENTRY", "INVALIDATED_BEFORE_ENTRY",
                           "EXPIRED_BEFORE_ENTRY", "CLOSED_OUTCOME_UNAVAILABLE", "OUTCOME_AMBIGUOUS"}
        events = {}
        for at, result_identity, run_identity, result in self._source_origins_all():
            events.setdefault((result.canonical_subject_identity, result.market_session_identity), []).append(
                (at, result_identity, run_identity, result))
        for current in self.lifecycle.restore():
            data = current.data
            if data["state"] not in terminal_states:
                continue
            intake = data["intake"]
            key = (intake["subject"], intake["session_identity"])
            later = [item for item in events.get(key, ()) if item[0] > datetime.fromisoformat(data["updated_at"])]
            if not later:
                continue
            at, result_identity, run_identity, result = later[0]
            if any(item.data["origin_at"] == at.astimezone(timezone.utc).isoformat()
                   for item in self.store.origins_for(*key)):
                continue
            reset = record("WO12_OPPORTUNITY_RESET_V1",
                canonical_subject_identity=key[0], market_session_identity=key[1],
                prior_wo10_opportunity_identity=intake["opportunity_identity"],
                terminal_track_identity=current.identity, terminal_status=data["terminal_status"],
                reset_at=data["updated_at"], next_probable_result_identity=result_identity,
                reset_authority="RETAINED_TERMINAL_WO11_THEN_LATER_ADMITTED_PROBABLE")
            self.store.retain(reset)
            successor = opportunity_origin(canonical_subject_identity=key[0],
                market_family="MCX" if key[0].startswith("MCX-") else "NSE",
                session_identity=key[1], origin_at=at, probable_result_identity=result_identity,
                probables_run_identity=run_identity, reset_identity=reset.identity)
            existing = [item for item in self.store.origins_for(*key)
                        if item.data["reset_identity"] == reset.identity]
            if len(existing) > 1:
                raise ValueError("WO12_OPPORTUNITY_ORIGIN_CONFLICT")
            origins.append(existing[0] if existing else self.store.retain(successor))
        return tuple(origins)

    def _source_origins_all(self):
        values = []
        for run in self._runs():
            for item in run.results:
                if item.state in {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}:
                    values.append((item.analysis_boundary, item.result_identity, run.run_identity, item))
        return tuple(sorted(values, key=lambda item: (item[0], item[1])))

    def project(self, *, generated_at: datetime | None = None, ensure_origins: bool = False) -> ResearchProjection:
        now = generated_at or self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("WO12_AWARE_TIMESTAMP_REQUIRED")
        origins = self._ensure_origins() if ensure_origins else self.store.records("WO12_OPPORTUNITY_ORIGIN_V1")
        local_now = now.astimezone(IST)
        month = local_now.strftime("%Y_%m")
        readiness_history = self._readiness_history_by_result()
        opportunities = self.futures.records("WO10_OPPORTUNITY_V1")
        comparisons = self.futures.records("WO10_SPONSOR_COMPARISON_V1")
        unavailable = self.futures.records("WO10_CONSTRUCTION_UNAVAILABLE_V1")
        selections = self.futures.records("WO10_SPONSOR_SELECTION_V1")
        tracks = self.lifecycle.restore()
        actions = self.lifecycle.records("WO11_ACTION_V1")
        lifecycle_events = self.lifecycle.records("WO11_EVENT_V1")
        rows, track_rows, event_rows, quality_rows = [], [], [], []
        for origin in sorted(origins, key=lambda item: (item.data["origin_at"], item.data["opportunity_id"])):
            od = origin.data
            origin_at = datetime.fromisoformat(str(od["origin_at"]))
            if origin_at.astimezone(IST).strftime("%Y_%m") != month:
                continue
            history = readiness_history.get(od["probable_result_identity"], ())
            r = history[-1] if history else None
            wo10 = [item for item in opportunities if r is not None and item.data["readiness_identity"] == r.readiness_identity]
            if len(wo10) > 1:
                raise ValueError("WO12_WO10_OPPORTUNITY_CONFLICT")
            w = wo10[0] if wo10 else None
            cs = [item for item in comparisons if w is not None and item.data.get("opportunity_identity") == w.identity]
            c = max(cs, key=lambda item: (item.data["created_at"], item.identity)) if cs else None
            us = [item for item in unavailable if r is not None and item.data["readiness_identity"] == r.readiness_identity]
            u = max(us, key=lambda item: (item.data["created_at"], item.identity)) if us else None
            ss = [item for item in selections if c is not None and item.data["comparison_identity"] == c.identity]
            if len(ss) > 1:
                raise ValueError("WO12_SPONSOR_DECISION_CONFLICT")
            s = ss[0] if ss else None
            related = [item for item in tracks if w is not None and item.data["intake"]["opportunity_identity"] == w.identity]
            related_actions = self._related_actions(w, s, actions)
            related_track_ids = {item.data["track_identity"] for item in related}
            related_events = [item for item in lifecycle_events
                              if item.data.get("track_identity") in related_track_ids]
            by_truth = {item.data["truth_class"]: item for item in related}
            direction = self.probables.load_result(od["probable_result_identity"]).direction.value
            plan_state = "NOT_REACHED"
            plan = expression = snapshot = advisory = None
            if c is not None:
                plan = self.futures.load(c.data["plan_identity"]).data
                expression = self.futures.load(c.data["expression_identity"]).data
                snapshot = self.futures.load(c.data["snapshot_identity"]).data
                advisory = self.futures.load(c.data["advisory_identity"]).data
                plan_state = plan["state"]
            elif u is not None:
                plan_state = u.data["state"]
            pos = self._track_values(by_truth.get("PAPER_POSITION"))
            obs = self._track_values(by_truth.get("PAPER_OBSERVATION"))
            first_three = self._first_count_at(history, 3)
            first_four = self._first_count_at(history, 4)
            first_five = self._first_count_at(history, 5)
            plan_at = None if plan is None else plan.get("created_at")
            decision_at = None if s is None else s.data.get("selected_at")
            action_at = None if not related_actions else related_actions[-1].data.get("action_at")
            terminal_states = {
                "CLOSED", "CANCELLED_BEFORE_ENTRY", "INVALIDATED_BEFORE_ENTRY",
                "EXPIRED_BEFORE_ENTRY", "CLOSED_OUTCOME_UNAVAILABLE", "OUTCOME_AMBIGUOUS",
            }
            # Calendar rollover is not DOMAIN-008 completion authority.  A day
            # becomes final here only when the retained Sponsor action ended
            # the path without a track, or every created track is terminal.
            terminal_without_track = any(
                item.data["action"] == "DO_NOTHING" for item in related_actions
            )
            terminal_tracks = bool(related) and all(
                item.data["state"] in terminal_states for item in related
            )
            day_state = "FINALIZED" if terminal_without_track or terminal_tracks else "PUBLISHED"
            criteria = {} if r is None else {item.criterion_id.value: item.state.value for item in r.criteria}
            future = {} if expression is None else expression.get("future", {})
            quality = self._quality(od, r, w, c, s, related, snapshot, expression, advisory, related_actions)
            row_values = {
                "opportunity_id": od["opportunity_id"], "opportunity_identity": od["opportunity_identity"],
                "canonical_subject_identity": od["canonical_subject_identity"], "market_family": od["market_family"],
                "market_session_identity": od["market_session_identity"], "opportunity_origin_at": od["origin_at"],
                "research_date": origin_at.astimezone(IST).date().isoformat(), "day_state": day_state,
                "direction": direction, "probable_state": "ADMITTED",
                "probable_result_identity": od["probable_result_identity"], "probables_run_identity": od["probables_run_identity"],
                "review_cycle_identity": None if r is None else r.review_cycle_identity,
                "review_pack_identity": None if r is None else r.review_pack_identity,
                "chart_revision_identity": None if r is None else r.chart_revision_identity,
                "answer_pack_identity": None if r is None else r.answer_pack_identity,
                "wo07f_identity": None if r is None else r.wo07f_identity,
                "wo07f_outcome": None if r is None else r.wo07f_outcome.value,
                "wo09_readiness_identity": None if r is None else r.readiness_identity,
                "wo09_readiness_state": None if r is None else r.readiness_state.value,
                "wo09_highest_satisfied_count": self._highest_count(history),
                "wo09_first_three_of_five_at": first_three,
                "wo09_first_four_of_five_at": first_four,
                "wo09_first_five_of_five_at": first_five,
                **{f"wo09_{key.lower()}_state": criteria.get(key) for key in ("I1", "I2", "I3", "I4", "I5")},
                "wo09_outstanding_criteria": None if r is None else ",".join(
                    item.criterion_id.value for item in r.criteria if item.state.value != "SATISFIED"),
                "wo09_hard_gate": None if r is None else r.hard_gate.value,
                "wo10_opportunity_identity": None if w is None else w.identity,
                "wo10_plan_state": plan_state,
                "wo10_plan_reason": (u.data.get("reason") if u is not None else None if plan is None else plan.get("reason")),
                "setup_family": _path(plan, "adapter", "setup_family"),
                "underlying_entry": _number(None if plan is None else plan.get("entry")),
                "underlying_stop": _number(None if plan is None else plan.get("stop")),
                "underlying_target": _number(None if plan is None else plan.get("target")),
                "planned_rr": _number(None if plan is None else plan.get("model_rr")),
                "future_contract_identity": future.get("provider_record_identity"),
                "future_trading_symbol": future.get("trading_symbol"), "future_expiry": future.get("expiry"),
                "future_entry": _number(None if expression is None else expression.get("entry")),
                "future_stop": _number(None if expression is None else expression.get("stop")),
                "future_target": _number(None if expression is None else expression.get("target")),
                "future_basis": _number(None if snapshot is None else snapshot.get("basis")),
                "future_spread": _number(None if snapshot is None else snapshot.get("spread")),
                "future_volume": _number(None if snapshot is None else snapshot.get("volume")),
                "future_oi": _number(None if snapshot is None else snapshot.get("oi")),
                "future_delta_oi": _number(None if snapshot is None else snapshot.get("delta_oi")),
                "future_snapshot_at": None if snapshot is None else snapshot.get("received_at"),
                "executability": None if c is None else c.data.get("executability"),
                "risk_warning_state": None if advisory is None else advisory.get("risk_warning_state"),
                "risk_per_lot": _number(None if advisory is None else advisory.get("risk_per_lot")),
                "risk_reference_amount": _number(None if advisory is None else advisory.get("risk_reference_amount")),
                "sponsor_decision": "PENDING" if s is None else s.data["choice"],
                "sponsor_decision_at": None if s is None else s.data.get("selected_at"),
                "wo10_selected_lots_context": None if s is None else s.data["sponsor_selected_lots"],
                "wo11_sponsor_action": "PENDING" if not related_actions else related_actions[-1].data["action"],
                "discovery_to_three_seconds": _duration_seconds(od["origin_at"], first_three),
                "three_to_four_seconds": _duration_seconds(first_three, first_four),
                "four_to_five_seconds": _duration_seconds(first_four, first_five),
                "five_to_trade_plan_seconds": _duration_seconds(first_five, plan_at),
                "trade_plan_to_sponsor_decision_seconds": _duration_seconds(plan_at, decision_at),
                "sponsor_decision_to_wo11_action_seconds": _duration_seconds(decision_at, action_at),
                "paper_position_state": pos[0], "paper_entry_price": pos[1], "paper_exit_price": pos[2],
                "paper_points": pos[3], "paper_model_r": pos[4], "paper_gross_model_result": pos[5],
                "paper_observation_state": obs[0], "observation_entry_price": obs[1],
                "observation_exit_price": obs[2], "observation_points": obs[3],
                "observation_model_r": obs[4], "observation_gross_model_result": obs[5],
                "data_quality_issue_count": len(quality), "research_authority": "RESEARCH_ONLY_NO_TRADING_AUTHORITY",
            }
            row = tuple(row_values.get(column) for column in OPPORTUNITY_COLUMNS)
            rows.append(row)
            event_rows.extend(self._events(origin, history, w, c, s, related, related_actions, related_events))
            for item in related:
                track_rows.append(self._track_row(od, item))
            quality_rows.extend(quality)
        analysis = self._analysis(rows, track_rows)
        month_state = "FINALIZED_MONTH" if datetime.strptime(month, "%Y_%m").date().replace(day=28) < local_now.date().replace(day=1) else "OPEN_MONTH"
        material = dict(year_month=month, generated_at=now, opportunities=rows, tracks=track_rows,
                        events=event_rows, analysis=analysis, data_quality=quality_rows)
        projection_identity = "WO12-RESEARCH-PROJECTION-" + digest(material)
        metadata = (
            ("workbook_schema", f"{WORKBOOK_SCHEMA} / {WORKBOOK_VERSION}"),
            ("policy_identity", POLICY_IDENTITY), ("policy_version", POLICY_VERSION),
            ("policy_checksum", POLICY_CHECKSUM), ("projection_identity", projection_identity),
            ("generated_at", now), ("year_month", month), ("month_state", month_state),
            ("publication_root", str(self.publication_root)),
            ("publication_transport", "ATOMIC_LOCAL_FILESYSTEM"),
            ("google_drive", "NOT_COMMISSIONED"),
            ("authority", "RESEARCH_ONLY_NO_TRADING_AUTHORITY"),
        )
        return ResearchProjection(month, now, projection_identity, tuple(rows), tuple(track_rows),
                                  tuple(sorted(event_rows, key=lambda row: (str(row[2]), str(row[6])))),
                                  tuple(analysis), tuple(quality_rows), metadata)

    def update(self, *, operation_identity: str) -> PublicationResult:
        if not isinstance(operation_identity, str) or not operation_identity.strip() or len(operation_identity) > 160:
            raise ValueError("WO12_OPERATION_IDENTITY_INVALID")
        with self.store.transaction():
            prior_operation = self.store.operation(operation_identity)
            if prior_operation is not None:
                data = prior_operation.data
                if prior_operation.schema == "WO12_LOCAL_PUBLICATION_FAILURE_V1":
                    raise ValueError(str(data["reason"]))
                receipt = (prior_operation if prior_operation.schema == "WO12_LOCAL_PUBLICATION_RECEIPT_V1"
                           else self.store.load(str(data["receipt_identity"])))
                return self._result(receipt, idempotent=True, outcome=str(data.get("outcome", "PUBLISHED")))
            projection = self.project(ensure_origins=True)
            source_boundary_identity = "WO12-SOURCE-BOUNDARY-" + digest({
                "source_events": tuple((row[2], row[4], row[5], row[6], row[8]) for row in projection.events),
                "track_currents": tuple(row[-1] for row in projection.tracks),
                "opportunity_origins": tuple((
                    row[OPPORTUNITY_COLUMNS.index("opportunity_id")],
                    row[OPPORTUNITY_COLUMNS.index("opportunity_identity")],
                    row[OPPORTUNITY_COLUMNS.index("probable_result_identity")],
                    row[OPPORTUNITY_COLUMNS.index("probables_run_identity")],
                ) for row in projection.opportunities),
            })
            current_receipt = self.store.current_receipt(projection.year_month)
            if (current_receipt is not None
                    and current_receipt.data.get("source_boundary_identity") == source_boundary_identity):
                if self._receipt_verified(current_receipt):
                    update = record("WO12_RESEARCH_UPDATE_V1", operation_identity=operation_identity,
                        receipt_identity=current_receipt.identity, projection_identity=current_receipt.data["projection_identity"],
                        source_boundary_identity=source_boundary_identity, completed_at=projection.generated_at,
                        outcome="ALREADY_UP_TO_DATE")
                    self.store.retain(update)
                    return self._result(current_receipt, idempotent=True, outcome="ALREADY_UP_TO_DATE")
                return self._recover_receipted_workbook(
                    current_receipt, operation_identity=operation_identity,
                    completed_at=projection.generated_at,
                )
            daily_package = record("WO12_DAILY_PACKAGE_V1",
                research_boundary=projection.generated_at,
                research_date=projection.generated_at.astimezone(IST).date().isoformat(),
                source_boundary_identity=source_boundary_identity,
                monthly_projection_identity=projection.projection_identity,
                opportunity_ids=[row[0] for row in projection.opportunities],
                day_state="PUBLISHED", authority="RESEARCH_ONLY")
            self.store.retain(daily_package)
            projection = replace(projection, metadata=projection.metadata + (
                ("source_boundary_identity", source_boundary_identity),
                ("daily_package_identity", daily_package.identity),
            ))
            from kronos.browser.intraday_research import export_research_workbook, validate_research_workbook
            payload = export_research_workbook(projection)
            sha = digest_bytes(payload)
            target = self.publication_root / f"KRONOS_Intraday_Research_{projection.year_month}.xlsx"
            previous = target.read_bytes() if target.exists() else None
            stage_dir = self.store.root / "staging" / digest(operation_identity)
            stage_dir.mkdir(parents=True, exist_ok=False)
            staged = stage_dir / target.name
            try:
                _durable_write(staged, payload)
                staged_readback = staged.read_bytes()
                validate_research_workbook(staged_readback, projection)
                if staged_readback != payload:
                    raise ValueError("WO12_STAGED_READBACK_MISMATCH")
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged, target)
                _sync(target.parent)
                readback = target.read_bytes()
                validate_research_workbook(readback, projection)
                if digest_bytes(readback) != sha or readback != payload:
                    if previous is not None:
                        _atomic_replace(target, previous)
                    else:
                        target.unlink(missing_ok=True)
                    raise ValueError("WO12_PUBLISHED_READBACK_MISMATCH")
                receipt = record("WO12_LOCAL_PUBLICATION_RECEIPT_V1",
                    operation_identity=operation_identity, year_month=projection.year_month,
                    research_boundary=projection.generated_at, daily_package_identity=daily_package.identity,
                    source_boundary_identity=source_boundary_identity,
                    workbook_path=str(target), workbook_path_identity="WO12-WORKBOOK-PATH-" + digest({"root": str(self.publication_root), "filename": target.name}),
                    workbook_filename=target.name, workbook_sha256=sha, workbook_bytes=len(payload),
                    projection_identity=projection.projection_identity, published_at=projection.generated_at,
                    prior_workbook_sha256=None if previous is None else digest_bytes(previous),
                    policy_identity=POLICY_IDENTITY, policy_version=POLICY_VERSION,
                    policy_checksum=POLICY_CHECKSUM, schema_identity=WORKBOOK_SCHEMA,
                    schema_version=WORKBOOK_VERSION, generator_identity="KRONOS-WO12-LOCAL-XLSX-GENERATOR-V1",
                    atomic_replace=True, readback_verified=True, status="VERIFIED", authority="RESEARCH_ONLY")
                try:
                    self.store.publish_receipt(receipt)
                except Exception:
                    if previous is not None:
                        _atomic_replace(target, previous)
                    else:
                        target.unlink(missing_ok=True)
                    raise
                update = record("WO12_RESEARCH_UPDATE_V1", operation_identity=operation_identity,
                    receipt_identity=receipt.identity, projection_identity=projection.projection_identity,
                    source_boundary_identity=source_boundary_identity,
                    completed_at=projection.generated_at, outcome="PUBLISHED")
                # The verified receipt is the publication authority.  This
                # companion is useful audit detail and cannot invalidate a
                # receipt that is already durable and current.
                try:
                    self.store.retain(update)
                except OSError:
                    pass
                staged.unlink(missing_ok=True)
                stage_dir.rmdir()
                return self._result(receipt, idempotent=False, outcome="PUBLISHED")
            except Exception as error:
                self.store.retain(record("WO12_LOCAL_PUBLICATION_FAILURE_V1",
                    operation_identity=operation_identity, projection_identity=projection.projection_identity,
                    failed_at=self.clock(), reason=str(error) if isinstance(error, ValueError) else "WO12_LOCAL_PUBLICATION_FAILED"))
                raise

    def _recover_receipted_workbook(self, receipt, *, operation_identity: str,
                                    completed_at: datetime) -> PublicationResult:
        """Recreate the exact receipted workbook without creating new authority."""
        data = receipt.data
        boundary = datetime.fromisoformat(str(data["research_boundary"]))
        projection = self.project(generated_at=boundary, ensure_origins=False)
        if projection.projection_identity != data["projection_identity"]:
            raise ValueError("WO12_RECEIPTED_PROJECTION_NOT_REPRODUCIBLE")
        projection = replace(projection, metadata=projection.metadata + (
            ("source_boundary_identity", data["source_boundary_identity"]),
            ("daily_package_identity", data["daily_package_identity"]),
        ))
        from kronos.browser.intraday_research import export_research_workbook, validate_research_workbook
        payload = export_research_workbook(projection)
        if (digest_bytes(payload) != data["workbook_sha256"]
                or len(payload) != data["workbook_bytes"]):
            raise ValueError("WO12_RECEIPTED_WORKBOOK_NOT_REPRODUCIBLE")
        target = Path(str(data["workbook_path"]))
        stage_dir = self.store.root / "staging" / digest(operation_identity)
        stage_dir.mkdir(parents=True, exist_ok=False)
        staged = stage_dir / str(data["workbook_filename"])
        try:
            _durable_write(staged, payload)
            staged_readback = staged.read_bytes()
            validate_research_workbook(staged_readback, projection)
            if staged_readback != payload:
                raise ValueError("WO12_STAGED_READBACK_MISMATCH")
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, target)
            _sync(target.parent)
            published = target.read_bytes()
            validate_research_workbook(published, projection)
            if published != payload or digest_bytes(published) != data["workbook_sha256"]:
                raise ValueError("WO12_RECOVERED_READBACK_MISMATCH")
            update = record("WO12_RESEARCH_UPDATE_V1", operation_identity=operation_identity,
                receipt_identity=receipt.identity, projection_identity=data["projection_identity"],
                source_boundary_identity=data["source_boundary_identity"], completed_at=completed_at,
                outcome="RECOVERED_CANONICAL_WORKBOOK")
            self.store.retain(update)
            staged.unlink(missing_ok=True)
            stage_dir.rmdir()
            return self._result(receipt, idempotent=True, outcome="RECOVERED_CANONICAL_WORKBOOK")
        except Exception as error:
            self.store.retain(record("WO12_LOCAL_PUBLICATION_FAILURE_V1",
                operation_identity=operation_identity, projection_identity=data["projection_identity"],
                failed_at=self.clock(), reason=str(error) if isinstance(error, ValueError)
                else "WO12_LOCAL_RECOVERY_FAILED"))
            raise

    def open_current(self, year_month: str) -> tuple[Path, bytes, str]:
        if not isinstance(year_month, str) or len(year_month) != 7 or year_month[4] != "_":
            raise ValueError("WO12_YEAR_MONTH_INVALID")
        receipt = self.store.current_receipt(year_month)
        if receipt is None:
            raise ValueError("WO12_VERIFIED_MONTHLY_PUBLICATION_UNAVAILABLE")
        data = receipt.data
        path = Path(str(data["workbook_path"]))
        payload = path.read_bytes()
        if digest_bytes(payload) != data["workbook_sha256"] or len(payload) != data["workbook_bytes"]:
            raise ValueError("WO12_MONTHLY_PUBLICATION_VERIFICATION_FAILED")
        return path, payload, receipt.identity

    def status_document(self) -> dict[str, object]:
        now = self.clock().astimezone(IST)
        month = now.strftime("%Y_%m")
        receipt = self.store.current_receipt(month)
        return {
            "policy_identity": POLICY_IDENTITY, "policy_version": POLICY_VERSION,
            "policy_checksum": POLICY_CHECKSUM, "current_month": month,
            "publication_root": str(self.publication_root), "receipt_identity": None if receipt is None else receipt.identity,
            "workbook_verified": False if receipt is None else self._receipt_verified(receipt),
            "automatic_schedule": "NONE_V1", "google_drive": "NOT_COMMISSIONED",
            "production_operations": 0,
        }

    def _receipt_verified(self, receipt) -> bool:
        try:
            data = receipt.data
            payload = Path(str(data["workbook_path"])).read_bytes()
            return digest_bytes(payload) == data["workbook_sha256"] and len(payload) == data["workbook_bytes"]
        except OSError:
            return False

    def _result(self, receipt, *, idempotent, outcome="PUBLISHED"):
        data = receipt.data
        return PublicationResult(receipt.identity, Path(str(data["workbook_path"])), str(data["workbook_sha256"]),
                                 int(data["workbook_bytes"]), str(data["projection_identity"]), idempotent, outcome)

    def _readiness_history_by_result(self):
        result = {}
        for path in sorted(self.wo09.readiness.glob("*.json")):
            item = self.wo09.load_readiness(path.stem)
            result.setdefault(item.probable_result_identity, []).append(item)
        return {key: tuple(sorted(values, key=lambda item: (item.created_at, item.readiness_identity)))
                for key, values in result.items()}

    @staticmethod
    def _highest_count(history):
        values = [item.satisfied_count for item in history if item.satisfied_count is not None]
        return max(values) if values else None

    @staticmethod
    def _first_count_at(history, threshold):
        values = [item.created_at for item in history
                  if item.satisfied_count is not None and item.satisfied_count >= threshold]
        return min(values) if values else None

    def _related_actions(self, opportunity, selection, actions):
        if opportunity is None:
            return []
        result = []
        for item in actions:
            data = item.data
            if data.get("intake_identity"):
                intake = self.lifecycle.load(data["intake_identity"]).data
                if intake.get("opportunity_identity") == opportunity.identity:
                    result.append(item)
            elif data.get("handoff_identity") and selection is not None:
                handoff = self.futures.load(data["handoff_identity"])
                if handoff.data.get("selection_identity") == selection.identity:
                    result.append(item)
        return sorted(result, key=lambda item: (item.data["action_at"], item.identity))

    def _track_values(self, item):
        if item is None:
            return ("NOT_CREATED", None, None, None, None, None)
        d = item.data
        metrics = None if d.get("metrics") is None else self.lifecycle.load(d["metrics"]).data
        return (d["display_state"], _number(None if d["entry"] is None else d["entry"]["price"]),
                _number(None if d["exit"] is None else d["exit"]["price"]),
                _number(None if metrics is None else metrics.get("points")),
                _number(None if metrics is None else metrics.get("model_r")),
                _number(None if metrics is None else metrics.get("gross_model_result")))

    def _track_row(self, origin, item):
        d = item.data; i = d["intake"]; m = None if d["metrics"] is None else self.lifecycle.load(d["metrics"]).data
        entry_at = None if d["entry"] is None else d["entry"]["at"]
        exit_at = None if d["exit"] is None else d["exit"]["at"]
        return (
            origin["opportunity_id"], origin["opportunity_identity"], d["track_identity"], d["truth_class"], 1,
            d["display_state"], d["state"] in {"CLOSED", "CANCELLED_BEFORE_ENTRY", "INVALIDATED_BEFORE_ENTRY", "EXPIRED_BEFORE_ENTRY", "CLOSED_OUTCOME_UNAVAILABLE", "OUTCOME_AMBIGUOUS"},
            i["direction"], i["future"]["provider_record_identity"], i["future"]["trading_symbol"], d["armed_at"],
            entry_at, _number(None if d["entry"] is None else d["entry"]["price"]),
            exit_at, _number(None if d["exit"] is None else d["exit"]["price"]),
            d["exit_reason"], d["terminal_status"], _number(None if m is None else m["points"]),
            _number(None if m is None else m["model_r"]), _number(i.get("planned_rr")),
            _number(None if m is None else m["gross_model_result"]), _duration_seconds(entry_at, exit_at),
            _number(None if m is None else m["mfe"]), _number(None if m is None else m["mae"]),
            _number(None if m is None else m["full_path_mfe"]), _number(None if m is None else m["full_path_mae"]),
            None if m is None else m["complete"], len(d["gaps"]), None if m is None else m["samples"], None,
            None if m is None else m["coverage_start"],
            None if m is None else m["coverage_end"], item.identity,
        )

    @staticmethod
    def _events(origin, readiness_history, opportunity, comparison, selection, tracks, actions, lifecycle_events):
        values = [(origin.data["opportunity_id"], origin.data["opportunity_identity"], origin.data["origin_at"],
                   "OPPORTUNITY_ORIGIN", "ADMITTED", origin.schema, origin.identity, None, None, origin.data["origin_authority"])]
        for readiness in readiness_history:
            values.append((origin.data["opportunity_id"], origin.data["opportunity_identity"], readiness.created_at,
                           "WO09_READINESS", readiness.readiness_state.value, readiness.schema_identity,
                           readiness.readiness_identity, None, None,
                           f"{readiness.satisfied_count}/5" if readiness.satisfied_count is not None else readiness.hard_gate.value))
        for item, kind, state in ((opportunity, "WO10_OPPORTUNITY", "REACHED"),
                                  (comparison, "WO10_CONSTRUCTION", "AVAILABLE"),
                                  (selection, "WO10_SPONSOR_DECISION", None if selection is None else selection.data["choice"])):
            if item is None: continue
            identity = getattr(item, "identity", getattr(item, "readiness_identity", ""))
            schema = getattr(item, "schema", getattr(item, "schema_identity", ""))
            data = item.data
            at = (getattr(item, "created_at", None) or data.get("created_at")
                  or data.get("first_reached_at") or data.get("selected_at"))
            values.append((origin.data["opportunity_id"], origin.data["opportunity_identity"], at, kind, state,
                           schema, identity, None, None, None))
        for action in actions:
            data = action.data
            truth = ("PAPER_POSITION" if data["action"] == "ACTIVATE_PAPER" else
                     "PAPER_OBSERVATION" if data["action"] == "OBSERVE" else None)
            values.append((origin.data["opportunity_id"], origin.data["opportunity_identity"], data["action_at"],
                           "WO11_SPONSOR_ACTION", data["action"], action.schema, action.identity, truth,
                           None, data["action_identity"]))
        truth_by_track = {item.data["track_identity"]: item.data["truth_class"] for item in tracks}
        for event in lifecycle_events:
            data = event.data
            evidence = data.get("evidence", ())
            values.append((origin.data["opportunity_id"], origin.data["opportunity_identity"], data["at"],
                           "WO11_LIFECYCLE_EVENT", f"{data['from_state']}→{data['to_state']}", event.schema,
                           event.identity, truth_by_track.get(data["track_identity"]),
                           evidence[0] if len(evidence) == 1 else None, data["reason"]))
        for current in tracks:
            d = current.data
            values.append((origin.data["opportunity_id"], origin.data["opportunity_identity"], d["updated_at"],
                           "WO11_TRACK", d["display_state"], current.schema, current.identity, d["truth_class"],
                           d["last_fact_identity"], d["event_identity"]))
        return values

    @staticmethod
    def _quality(origin, readiness, opportunity, comparison, selection, tracks,
                 snapshot, expression, advisory, actions):
        result = []
        for missing, code, stage in ((readiness is None, "WO09_NOT_REACHED", "WO09"),
                                     (opportunity is None, "WO10_OPPORTUNITY_NOT_REACHED", "WO10"),
                                     (comparison is None, "TRADE_PLAN_NOT_AVAILABLE", "WO10"),
                                     (selection is None, "SPONSOR_DECISION_PENDING", "WO10"),
                                     (not actions, "WO11_ACTION_PENDING", "WO11"),
                                     (not tracks and not any(item.data["action"] == "DO_NOTHING" for item in actions),
                                      "WO11_TRACK_NOT_CREATED", "WO11")):
            if missing:
                result.append((origin["opportunity_id"], origin["opportunity_identity"], code, "INFO", stage,
                               None, "Counted in the opportunity denominator; excluded only where the metric rule requires downstream eligibility."))
        for missing, code in ((snapshot is not None and snapshot.get("oi") is None, "OI_UNAVAILABLE"),
                              (snapshot is not None and snapshot.get("delta_oi") is None, "DELTA_OI_UNAVAILABLE"),
                              (expression is not None and expression.get("monetary_economics") is None,
                               "MONETARY_ECONOMICS_UNAVAILABLE"),
                              (advisory is not None and advisory.get("risk_per_lot") is None,
                               "RISK_PER_LOT_UNAVAILABLE")):
            if missing:
                result.append((origin["opportunity_id"], origin["opportunity_identity"], code, "INFO", "WO10",
                               None, "Retained as unavailable; no substitute value is inferred."))
        for track in tracks:
            d = track.data
            if d["gaps"]:
                result.append((origin["opportunity_id"], origin["opportunity_identity"], "MONITORING_GAP", "WARNING", "WO11",
                               track.identity, "Gap retained; full-path MFE/MAE excluded."))
            if d["terminal_status"] in {"OUTCOME_AMBIGUOUS", "SESSION_ENDED", "CONTRACT_ENDED"} and d["exit"] is None:
                result.append((origin["opportunity_id"], origin["opportunity_identity"], "OUTCOME_UNAVAILABLE", "WARNING", "WO11",
                               track.identity, "No model R is inferred without a governed exit price."))
        return result

    @staticmethod
    def _analysis(opportunities, tracks):
        count = len(opportunities)
        return (
            ("Opportunity count", count, count, count, "All governed opportunity origins in the month"),
            ("WO09 3/5 reached rate", Formula('COUNTIF(Opportunities[wo09_highest_satisfied_count],">=3")'), count,
             Formula('IFERROR(B3/C3,0)'), "All opportunities denominator"),
            ("WO09 4/5 reached rate", Formula('COUNTIF(Opportunities[wo09_highest_satisfied_count],">=4")'), count,
             Formula('IFERROR(B4/C4,0)'), "All opportunities denominator"),
            ("WO09 5/5 reached rate", Formula('COUNTIF(Opportunities[wo09_highest_satisfied_count],5)'), count,
             Formula('IFERROR(B5/C5,0)'), "All opportunities denominator"),
            ("Trade-plan availability", Formula('COUNTIF(Opportunities[wo10_plan_state],"AVAILABLE")'),
             Formula('COUNTIF(Opportunities[wo09_highest_satisfied_count],5)'), Formula('IFERROR(B6/C6,0)'), "Among 5/5 opportunities"),
            ("Sponsor selection rate", Formula('COUNTIF(Opportunities[sponsor_decision],"SELECTED_FUTURE")'),
             Formula('COUNTIFS(Opportunities[sponsor_decision],"<>PENDING",Opportunities[sponsor_decision],"<>")'), Formula('IFERROR(B7/C7,0)'), "Among decided WO-10 opportunities"),
            ("PAPER activation rate", Formula('COUNTIF(Tracks[truth_class],"PAPER_POSITION")'),
             Formula('COUNTIF(Opportunities[sponsor_decision],"SELECTED_FUTURE")'), Formula('IFERROR(B8/C8,0)'), "Among selected futures"),
            ("Observation activation rate", Formula('COUNTIF(Tracks[truth_class],"PAPER_OBSERVATION")'),
             Formula('COUNTIF(Opportunities[sponsor_decision],"SELECTED_FUTURE")'), Formula('IFERROR(B9/C9,0)'), "Among selected futures"),
            ("No-entry rate", Formula('COUNTIFS(Tracks[terminal],TRUE,Tracks[entry_price],"")'), Formula('COUNTIF(Tracks[terminal],TRUE)'), Formula('IFERROR(B10/C10,0)'), "Terminal tracks without a governed model Entry"),
            ("STOP_LOSS rate", Formula('COUNTIF(Tracks[exit_reason],"STOP_LOSS")'), Formula('COUNT(Tracks[model_r])'), Formula('IFERROR(B11/C11,0)'), "Among priced model-R outcomes"),
            ("TARGET rate", Formula('COUNTIF(Tracks[exit_reason],"TARGET")'), Formula('COUNT(Tracks[model_r])'), Formula('IFERROR(B12/C12,0)'), "Among priced model-R outcomes"),
            ("SPONSOR_EXIT rate", Formula('COUNTIF(Tracks[exit_reason],"SPONSOR_EXIT")'), Formula('COUNT(Tracks[model_r])'), Formula('IFERROR(B13/C13,0)'), "Among priced model-R outcomes"),
            ("Ambiguous outcome rate", Formula('COUNTIF(Tracks[terminal_status],"OUTCOME_AMBIGUOUS")'), len(tracks), Formula('IFERROR(B14/C14,0)'), "All created tracks denominator"),
            ("Unavailable outcome rate", Formula('COUNTIFS(Tracks[terminal],TRUE,Tracks[model_r],"")'), len(tracks), Formula('IFERROR(B15/C15,0)'), "Terminal tracks without governed model R"),
            ("Monitoring-complete rate", Formula('COUNTIF(Tracks[monitoring_complete],TRUE)'), len(tracks), Formula('IFERROR(B16/C16,0)'), "All created tracks denominator"),
            ("Average model R", Formula('IFERROR(AVERAGE(Tracks[model_r]),0)'), Formula('COUNT(Tracks[model_r])'), Formula('B17'), "Governed numeric R only; zero included"),
            ("Total model R", Formula('SUM(Tracks[model_r])'), Formula('COUNT(Tracks[model_r])'), Formula('B18'), "Governed numeric R only"),
            ("Win rate", Formula('COUNTIF(Tracks[model_r],">0")'), Formula('COUNT(Tracks[model_r])'), Formula('IFERROR(B19/C19,0)'), "Positive model R / numeric R outcomes"),
            ("Loss rate", Formula('COUNTIF(Tracks[model_r],"<0")'), Formula('COUNT(Tracks[model_r])'), Formula('IFERROR(B20/C20,0)'), "Negative model R / numeric R outcomes"),
            ("Average win R", Formula('IFERROR(AVERAGEIFS(Tracks[model_r],Tracks[model_r],">0"),0)'), Formula('COUNTIF(Tracks[model_r],">0")'), Formula('B21'), "Breakeven excluded"),
            ("Average loss R", Formula('IFERROR(AVERAGEIFS(Tracks[model_r],Tracks[model_r],"<0"),0)'), Formula('COUNTIF(Tracks[model_r],"<0")'), Formula('B22'), "Breakeven excluded"),
            ("Payoff ratio", Formula('IF(OR(B21=0,B22=0),"n.a.",ABS(B21/B22))'), Formula('COUNT(Tracks[model_r])'), Formula('B23'), "Absolute average win R / average loss R; unavailable without both"),
            ("PAPER Position expectancy R", Formula('IFERROR(AVERAGEIFS(Tracks[model_r],Tracks[truth_class],"PAPER_POSITION"),0)'), Formula('COUNTIFS(Tracks[truth_class],"PAPER_POSITION",Tracks[model_r],"<>")'), Formula('B24'), "PAPER Position only; exactly one model lot"),
            ("Paper Observation expectancy R", Formula('IFERROR(AVERAGEIFS(Tracks[model_r],Tracks[truth_class],"PAPER_OBSERVATION"),0)'), Formula('COUNTIFS(Tracks[truth_class],"PAPER_OBSERVATION",Tracks[model_r],"<>")'), Formula('B25'), "Counterfactual Paper Observation only; exactly one model lot"),
            ("PAPER Position gross model result", Formula('SUMIFS(Tracks[gross_model_result],Tracks[truth_class],"PAPER_POSITION")'), Formula('COUNTIFS(Tracks[truth_class],"PAPER_POSITION",Tracks[gross_model_result],"<>")'), Formula('B26'), "PAPER Position monetary result remains separate"),
            ("Paper Observation gross model result", Formula('SUMIFS(Tracks[gross_model_result],Tracks[truth_class],"PAPER_OBSERVATION")'), Formula('COUNTIFS(Tracks[truth_class],"PAPER_OBSERVATION",Tracks[gross_model_result],"<>")'), Formula('B27'), "Counterfactual monetary result remains separate"),
            ("Average holding seconds", Formula('IFERROR(AVERAGE(Tracks[holding_seconds]),0)'), Formula('COUNT(Tracks[holding_seconds])'), Formula('B28'), "Governed priced entries and exits only"),
            ("Complete-path MFE average", Formula('IFERROR(AVERAGEIFS(Tracks[full_path_mfe],Tracks[monitoring_complete],TRUE),0)'), Formula('COUNTIFS(Tracks[monitoring_complete],TRUE,Tracks[full_path_mfe],"<>")'), Formula('B29'), "Monitoring-complete tracks only"),
            ("Complete-path MAE average", Formula('IFERROR(AVERAGEIFS(Tracks[full_path_mae],Tracks[monitoring_complete],TRUE),0)'), Formula('COUNTIFS(Tracks[monitoring_complete],TRUE,Tracks[full_path_mae],"<>")'), Formula('B30'), "Monitoring-complete tracks only"),
            ("Median model R", Formula('IFERROR(MEDIAN(Tracks[model_r]),0)'), Formula('COUNT(Tracks[model_r])'), Formula('B31'), "Governed numeric R only; zero included"),
            ("Median holding seconds", Formula('IFERROR(MEDIAN(Tracks[holding_seconds]),0)'), Formula('COUNT(Tracks[holding_seconds])'), Formula('B32'), "Governed priced entries and exits only"),
            ("Complete-path MFE median", Formula('IFERROR(MEDIAN(Tracks[full_path_mfe]),0)'), Formula('COUNT(Tracks[full_path_mfe])'), Formula('B33'), "Incomplete paths are blank and excluded"),
            ("Complete-path MAE median", Formula('IFERROR(MEDIAN(Tracks[full_path_mae]),0)'), Formula('COUNT(Tracks[full_path_mae])'), Formula('B34'), "Incomplete paths are blank and excluded"),
        )


def digest_bytes(payload: bytes) -> str:
    from hashlib import sha256
    return sha256(payload).hexdigest()


def _number(value):
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
    except Exception:
        return None
    return result if result.is_finite() else None


def _path(value, *keys):
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _portable_formula(expression):
    def substitute(match):
        sheet, column = match.groups()
        columns = OPPORTUNITY_COLUMNS if sheet == "Opportunities" else TRACK_COLUMNS
        index = columns.index(column) + 1
        letter = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            letter = chr(65 + remainder) + letter
        return f"'{sheet}'!${letter}$2:${letter}$1048576"
    return re.sub(r"\b(Opportunities|Tracks)\[([A-Za-z0-9_]+)\]", substitute, expression)


def _duration_seconds(start, end):
    if start is None or end is None:
        return None
    try:
        left = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        right = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
    except ValueError:
        return None
    if left.tzinfo is None or right.tzinfo is None or right < left:
        return None
    return Decimal(str((right - left).total_seconds()))


def _durable_write(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())


def _atomic_replace(path: Path, payload: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path); _sync(path.parent)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def _sync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


__all__ = [
    "ANALYSIS_COLUMNS", "EVENT_COLUMNS", "Formula", "IntradayResearchApplication",
    "METADATA_COLUMNS", "OPPORTUNITY_COLUMNS", "PublicationResult", "QUALITY_COLUMNS",
    "ResearchProjection", "TRACK_COLUMNS", "digest_bytes",
]
