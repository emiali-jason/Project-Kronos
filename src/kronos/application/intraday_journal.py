"""WO-14 source adapter and inert Sponsor-facing Intraday Journal projection."""

from __future__ import annotations

from datetime import datetime, timezone

from kronos.intraday.wo11_lifecycle import TERMINAL
from kronos.intraday.wo14_journal_contract import JournalSnapshot, revision


def _instant(value: object) -> datetime:
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("WO14_JOURNAL_AWARE_TIMESTAMP_REQUIRED")
    return result.astimezone(timezone.utc)


def _compact_geometry(data: dict[str, object] | None) -> dict[str, object] | None:
    if not data:
        return None
    return {key: data.get(key) for key in ("entry", "stop", "target")}


class IntradaySourceAdapter:
    """Consumes committed source identities and owns presentation state only."""

    revision_factory = staticmethod(revision)

    SOURCE_KINDS = frozenset({"SELECTION", "ACTION", "TRACK"})

    def __init__(self, *, research, futures, lifecycle, store) -> None:
        self.research, self.futures, self.lifecycle_application = research, futures, lifecycle
        self.lifecycle = getattr(lifecycle, "store", lifecycle)
        self.store = store
        self.last_failure: str | None = None

    def bind(self) -> None:
        # Separate product observer. Notification delivery and Journal projection
        # are peers; neither consumes the other's records.
        self.futures.journal_listener = self.consume_source
        self.lifecycle.journal_listener = self.consume_source

    def _origin(self, opportunity_identity: str):
        values = [item for item in self.research.records("WO12_OPPORTUNITY_ORIGIN_V1")
                  if item.data["opportunity_identity"] == opportunity_identity]
        if len(values) != 1:
            raise ValueError("WO14_JOURNAL_OPPORTUNITY_ORIGIN_NOT_RETAINED")
        return values[0]

    def _plan_origin(self, plan, opportunity_identity, *, intake=None):
        """Keep WO10's claim distinct from its explicitly retained original origin."""
        from kronos.intraday.wo09_experimental import AUTHORITY, ExperimentalReadinessRecord, origin_from
        from kronos.intraday.wo10_futures_contract import normalize
        source = plan.get("wo09") or {}
        if not isinstance(source, dict):
            raise ValueError("WO14_JOURNAL_WO09_SOURCE_INVALID")
        if source.get("authority") != AUTHORITY:
            if intake is not None and "experimental_authority" in intake:
                raise ValueError("WO14_JOURNAL_EXPERIMENTAL_LINEAGE_MISMATCH")
            return self._origin(opportunity_identity)
        from kronos.intraday.wo09_persistence import _readiness
        # WO10 normalizes copied datetime values to UTC; it is not a lossless
        # WO09 handoff serialization. Its embedded readiness/origin documents
        # remain exact original artifacts. Validate those, without restamping.
        readiness = _readiness(source["readiness_document"])
        if (type(readiness) is not ExperimentalReadinessRecord
                or readiness.satisfied_count != 5 or readiness.first_five_document is None):
            raise ValueError("WO14_JOURNAL_EXPERIMENTAL_SOURCE_REQUIRED")
        names = ("policy_identity", "policy_version", "policy_checksum", "canonical_subject_identity",
                 "session_identity", "direction", "methodology_identity", "methodology_version",
                 "methodology_checksum", "wo08_identity", "wo08_integrity", "opportunity_identity",
                 "first_five_document", "satisfied_count", "hard_gate", "readiness_state")
        if (source.get("readiness_identity") != readiness.readiness_identity
                or source.get("readiness_integrity") != readiness.integrity_identity
                or any(source.get(key) != normalize(getattr(readiness, key)) for key in names)
                or plan.get("subject") != readiness.canonical_subject_identity
                or plan.get("session_identity") != readiness.session_identity
                or plan.get("direction") != normalize(readiness.direction)):
            raise ValueError("WO14_JOURNAL_EXPERIMENTAL_LINEAGE_MISMATCH")
        origin = self._origin(readiness.opportunity_identity)
        expected = origin_from(readiness.origin_document)
        if (origin != expected
                or origin.data["canonical_subject_identity"] != readiness.canonical_subject_identity
                or origin.data["market_session_identity"] != readiness.session_identity):
            raise ValueError("WO14_JOURNAL_EXPERIMENTAL_ORIGIN_MISMATCH")
        if intake is not None:
            required = dict(experimental_authority=AUTHORITY,
                experimental_method_identity=readiness.methodology_identity,
                experimental_method_version=readiness.methodology_version,
                experimental_method_checksum=readiness.methodology_checksum,
                experimental_opportunity_identity=readiness.opportunity_identity,
                experimental_first_five_identity=readiness.first_five_document["fact_identity"],
                subject=readiness.canonical_subject_identity, session_identity=readiness.session_identity,
                direction=normalize(readiness.direction))
            if any(intake.get(key) != value for key, value in required.items()):
                raise ValueError("WO14_JOURNAL_EXPERIMENTAL_LINEAGE_MISMATCH")
        return origin

    def _monitoring(self, track_identity: str | None, stored: str, terminal: bool) -> str:
        if terminal:
            return "NOT_REQUIRED"
        resolver = getattr(self.lifecycle_application, "journal_monitoring_state", None)
        if resolver is None:
            return "UNAVAILABLE"
        try:
            return resolver(track_identity)
        except (ValueError, TypeError, KeyError, OSError):
            return "UNAVAILABLE"

    def consume_source(self, kind: str, identity: str) -> None:
        if kind not in self.SOURCE_KINDS:
            return
        try:
            if kind == "SELECTION":
                self._selection(self.futures.load(identity))
            elif kind == "ACTION":
                self._action(self.lifecycle.load(identity))
            else:
                self._track(self.lifecycle.load(identity))
            self.last_failure = None
        except (ValueError, TypeError, KeyError, OSError):
            self.last_failure = "WO14_JOURNAL_SOURCE_OR_LINEAGE_UNAVAILABLE"
            raise

    def _selection(self, selection) -> None:
        data = selection.data
        if data["choice"] != "NONE":
            return  # Selected Future is represented by the later WO-11 action/track.
        comparison = data["comparison"]
        plan = self.futures.load(comparison["plan_identity"]).data
        origin = self._plan_origin(plan, comparison["opportunity_identity"])
        expression = self.futures.load(comparison["expression_identity"]).data
        snapshot = self.futures.load(comparison["snapshot_identity"]).data
        self.store.publish(self._revision(
            origin=origin, subject=comparison["subject"], direction=comparison["direction"],
            session=plan["session_identity"], decision="NONE",
            decision_identity=selection.identity, decision_at=data["selected_at"], truth_class="NONE",
            comparison=comparison, plan=plan, selected_lots=data["sponsor_selected_lots"],
            future=expression.get("future"), future_geometry=_compact_geometry(expression),
            trading_date=(snapshot.get("contract") or {}).get("trading_date"),
            source_identities=[origin.identity, selection.identity, comparison["opportunity_identity"],
                               comparison["plan_identity"], comparison["expression_identity"]],
        ))

    def _action(self, action) -> None:
        data = action.data
        if data["action"] != "DO_NOTHING":
            return
        handoff = self.futures.load(data["handoff_identity"])
        selection = handoff.data["selection"]
        comparison = selection["comparison"]
        plan = handoff.data["plan"]
        origin = self._plan_origin(plan, comparison["opportunity_identity"])
        expression = handoff.data["expression"]
        snapshot = handoff.data["snapshot"]
        self.store.publish(self._revision(
            origin=origin, subject=comparison["subject"], direction=comparison["direction"],
            session=plan["session_identity"], decision="DO_NOTHING",
            decision_identity=action.identity, decision_at=data["action_at"], truth_class="DO_NOTHING",
            comparison=comparison, plan=plan, selected_lots=selection["sponsor_selected_lots"],
            future=expression.get("future"), future_geometry=_compact_geometry(expression),
            trading_date=(snapshot.get("contract") or {}).get("trading_date"),
            source_identities=[origin.identity, action.identity, handoff.identity,
                               comparison["opportunity_identity"], selection["comparison_identity"], comparison["plan_identity"],
                               comparison["expression_identity"]],
        ))

    def _track_extras(self, data):
        return {}

    def _track(self, current) -> None:
        data = current.data
        intake = data["intake"]
        auth = self.lifecycle.load(data["authorization_identity"])
        action = self.lifecycle.load(auth.data["action_identity"])
        plan = self.futures.load(intake["plan_identity"]).data
        origin = self._plan_origin(plan, intake["opportunity_identity"], intake=intake)
        expression = self.futures.load(intake["expression_identity"]).data
        metric = None if data["metrics"] is None else self.lifecycle.load(data["metrics"]).data
        monitoring = self._monitoring(data["track_identity"], data["monitoring"], data["state"] in TERMINAL)
        entry = None if data["entry"] is None else {
            key: data["entry"].get(key) for key in ("price", "at", "trigger_fact", "price_fact", "identity")
        }
        exit_value = None if data["exit"] is None else {
            key: data["exit"].get(key) for key in ("price", "at", "trigger_fact", "price_fact", "identity")
        }
        self.store.publish(self._revision(
            origin=origin, subject=intake["subject"], direction=intake["direction"],
            session=intake["session_identity"],
            decision="PAPER_POSITION" if data["truth_class"] == "PAPER_POSITION" else "PAPER_OBSERVATION",
            decision_identity=action.identity, decision_at=auth.data["armed_at"], truth_class=data["truth_class"],
            comparison={"opportunity_identity": intake["opportunity_identity"],
                        "plan_identity": intake["plan_identity"], "expression_identity": intake["expression_identity"],
                        "readiness_identity": (plan.get("wo09") or {}).get("readiness_identity")},
            plan=plan, selected_lots=intake["selected_lots"], track_identity=data["track_identity"],
            status=data["display_state"], terminal=data["state"] in TERMINAL, monitoring=monitoring,
            entry=entry, exit=exit_value, exit_reason=data["exit_reason"], terminal_status=data["terminal_status"],
            metrics=None if metric is None else {
                key: metric.get(key) for key in ("points", "model_r", "mfe", "mae", "gross_model_result",
                                                   "complete", "gaps", "samples", "coverage_label",
                                                   "coverage_start", "coverage_end")
            }, future=expression.get("future"), future_geometry=_compact_geometry(expression),
            trading_date=(intake.get("contract") or {}).get("trading_date"),
            **self._track_extras(data),
            source_identities=[origin.identity, current.identity, data["authorization_identity"], action.identity,
                               intake["opportunity_identity"], intake["plan_identity"], intake["expression_identity"],
                               *([data["metrics"]] if data["metrics"] else [])],
        ))

    def _revision(self, *, origin, subject, direction, session, decision, decision_identity,
                  decision_at, truth_class, comparison, plan, selected_lots, source_identities,
                  track_identity=None, status="NO_TRACK_CREATED", terminal=True, monitoring="NOT_REQUIRED",
                  entry=None, exit=None, exit_reason=None, terminal_status=None, metrics=None, future=None,
                  future_geometry=None, trading_date=None, observation=None):
        od = origin.data
        return self.revision_factory(
            opportunity_id=od["opportunity_id"], opportunity_identity=od["opportunity_identity"],
            subject=subject, direction=direction, session_identity=session, decision=decision,
            decision_identity=decision_identity, decision_at=_instant(decision_at).isoformat(),
            truth_class=truth_class, track_identity=track_identity, status=status, terminal=terminal,
            source_identities=sorted(set(source_identities)), monitoring=monitoring,
            model_lots=1 if track_identity else None, entry=entry, exit=exit, exit_reason=exit_reason,
            terminal_status=terminal_status, metrics=metrics,
            trade_plan_identity=comparison.get("plan_identity"), future=future,
            underlying_geometry=_compact_geometry(plan), future_geometry=future_geometry or ({
                "entry": comparison.get("entry"), "stop": comparison.get("stop"), "target": comparison.get("target")
            } if any(comparison.get(key) is not None for key in ("entry", "stop", "target")) else None),
            planned_rr=plan.get("model_rr"), selected_lots_context=selected_lots,
            setup_family=(plan.get("adapter") or {}).get("native_selection", {}).get("setup_family")
                         if isinstance(plan.get("adapter"), dict) else None,
            market_family=od["market_family"],
            origin_at=od["origin_at"], readiness_identity=comparison.get("readiness_identity"),
            highest_readiness=(plan.get("wo09") or {}).get("readiness_state")
                              if isinstance(plan.get("wo09"), dict) else None,
            decision_reason=comparison.get("reason"), holding_time=None, trading_date=trading_date,
            **({"observation": observation} if observation is not None else {}),
        )

class IntradayJournalApplication(IntradaySourceAdapter):
    """Independent Journal presentation and suppression authority."""

    def snapshot(self, *, search: str = "", truth: str = "ALL", status: str = "ALL",
                 monitoring: str = "ALL", scope: str = "ALL", include_suppressed: bool = False) -> JournalSnapshot:
        # This is an indexed compact-pointer read. It never scans WO-10/11/12.
        snapshot = self.store.snapshot()
        records = snapshot.records if include_suppressed else tuple(
            item for item in snapshot.records if item.journal_identity not in snapshot.suppressed)
        needle = search.strip().casefold()
        if needle:
            records = tuple(item for item in records if needle in " ".join((
                str(item.data["opportunity_id"]), str(item.data["subject"]),
                str(item.data["direction"]), str(item.data["truth_class"]),
                str(item.data["status"]), str(item.data["exit_reason"] or ""),
            )).casefold())
        if truth != "ALL":
            records = tuple(item for item in records if item.data["truth_class"] == truth)
        if status != "ALL":
            records = tuple(item for item in records if item.data["status"] == status)
        effective_monitoring = {
            item.journal_identity: self._monitoring(
                item.data["track_identity"], str(item.data["monitoring"]), bool(item.data["terminal"])
            ) for item in records
        }
        if monitoring != "ALL":
            records = tuple(item for item in records if effective_monitoring[item.journal_identity] == monitoring)
        if scope == "CURRENT":
            records = tuple(item for item in records if not item.data["terminal"])
        elif scope == "HISTORY":
            records = tuple(item for item in records if item.data["terminal"])
        records = tuple(sorted(records, key=lambda item: (
            -_instant(item.data["decision_at"]).timestamp(), item.journal_identity)))
        return JournalSnapshot(records, snapshot.suppressed, tuple(
            sorted((item.journal_identity, effective_monitoring[item.journal_identity]) for item in records)
        ))

    def suppress(self, *, journal_identity: str, revision_identity: str, action_identity: str) -> None:
        self.store.suppress(journal_identity, revision_identity=revision_identity, action_identity=action_identity)


__all__ = ["IntradayJournalApplication"]
