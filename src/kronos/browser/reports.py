"""Deterministic Sponsor-facing historical Reports projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
import csv
import io
import json
from zoneinfo import ZoneInfo

from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_trade_journal import (
    JournalRecordType,
    TradeJournalSnapshot,
)
from kronos.swing.v1.observation_research_ledger_v2 import (
    ObservationMode,
    ObservationOperationalHandoffV2,
    ObservationOperationalRoute,
)


_IST = ZoneInfo("Asia/Kolkata")
REPORTS_EXPORT_SCHEMA = "KRONOS-SPONSOR-HISTORICAL-REPORTS-V1"
REPORTS_AUTHORITY = "FACTUAL_HISTORY_ONLY_NO_RESEARCH_TRADING_OR_BROKER_AUTHORITY"


class ReportProduct(StrEnum):
    SWING = "SWING"
    INTRADAY = "INTRADAY"


class ReportView(StrEnum):
    OVERVIEW = "OVERVIEW"
    PAPER = "PAPER"
    LIVE = "LIVE"
    PAPER_OBSERVATIONS = "PAPER_OBSERVATIONS"
    ALL_RECORDS = "ALL_RECORDS"


class ReportFamily(StrEnum):
    PAPER = "PAPER"
    LIVE = "LIVE"
    PAPER_OBSERVATION = "PAPER_OBSERVATION"


@dataclass(frozen=True, slots=True)
class ReportsQuery:
    product: ReportProduct = ReportProduct.SWING
    view: ReportView = ReportView.OVERVIEW
    from_date: date | None = None
    to_date: date | None = None
    instrument: str = ""
    direction: V1Direction | None = None
    status: str = ""
    page: int = 1
    page_size: int = 25

    def __post_init__(self) -> None:
        if (
            type(self.product) is not ReportProduct
            or type(self.view) is not ReportView
            or (self.from_date is not None and type(self.from_date) is not date)
            or (self.to_date is not None and type(self.to_date) is not date)
            or (
                self.from_date is not None and self.to_date is not None
                and self.from_date > self.to_date
            )
            or type(self.instrument) is not str
            or len(self.instrument) > 80
            or self.direction not in {None, V1Direction.LONG, V1Direction.SHORT}
            or type(self.status) is not str
            or len(self.status) > 80
            or type(self.page) is not int or self.page < 1
            or type(self.page_size) is not int or not 1 <= self.page_size <= 100
        ):
            raise ValueError("REPORTS_QUERY_INVALID")


@dataclass(frozen=True, slots=True)
class HistoricalReportRecord:
    record_identity: str
    decision_identity: str
    record_date: date
    relevant_timestamp: datetime
    instrument: str
    direction: V1Direction
    family: ReportFamily
    status: str
    entry: Decimal | None
    exit: Decimal | None
    pnl: Decimal | None
    target: Decimal | None
    stop: Decimal | None
    sponsor_position_outcome: str
    paper_track_outcome: str
    objective_outcome: str
    step31_severity: str
    risk_state: str
    activation_disposition: str
    source_contract_identity: str
    source_contract_version: str


@dataclass(frozen=True, slots=True)
class ReportsOverview:
    records: int
    paper_positions: int
    live_positions: int
    paper_observations: int
    completed_records: int
    net_pnl: Decimal | None
    win_rate: None = None
    average_r: None = None
    max_drawdown: None = None
    daily_pnl: None = None
    effectiveness: None = None


@dataclass(frozen=True, slots=True)
class HistoricalReportsProjection:
    query: ReportsQuery
    governed_current_trading_date: date | None
    records: tuple[HistoricalReportRecord, ...]
    page_records: tuple[HistoricalReportRecord, ...]
    overview: ReportsOverview
    page_count: int
    total_records: int


def project_historical_reports(
    operational: tuple[ObservationOperationalHandoffV2, ...],
    journal: TradeJournalSnapshot,
    query: ReportsQuery,
    *,
    governed_current_trading_date: date | None,
) -> HistoricalReportsProjection:
    """Project immutable evidence into one filtered, paginated historical book."""

    if query.product is ReportProduct.INTRADAY:
        return HistoricalReportsProjection(
            query, governed_current_trading_date, (), (), _overview(()), 0, 0
        )
    by_decision: dict[str, HistoricalReportRecord] = {}
    for item in operational:
        record = _from_operational(item)
        if record is not None:
            by_decision[record.decision_identity] = record
    for item in journal.records:
        if (
            item.record_type is not JournalRecordType.TRADE
            or item.sponsor_decision_id in by_decision
        ):
            continue
        by_decision[item.sponsor_decision_id] = HistoricalReportRecord(
            record_identity=item.journal_record_id,
            decision_identity=item.sponsor_decision_id,
            record_date=(item.exit_timestamp or item.created_at).astimezone(_IST).date(),
            relevant_timestamp=item.exit_timestamp or item.created_at,
            instrument=item.instrument,
            direction=item.direction,
            family=(
                ReportFamily.PAPER
                if item.mode.value == "PAPER" else ReportFamily.LIVE
            ),
            status="EXITED",
            entry=item.actual_entry,
            exit=item.actual_exit,
            pnl=item.gross_pnl,
            target=item.model_target,
            stop=item.model_stop,
            sponsor_position_outcome=item.exit_reason or item.outcome.value,
            paper_track_outcome="NOT_APPLICABLE",
            objective_outcome="UNAVAILABLE",
            step31_severity="UNAVAILABLE",
            risk_state="UNAVAILABLE",
            activation_disposition="ACTIVATED",
            source_contract_identity=item.contract_identity,
            source_contract_version=item.contract_version,
        )
    ordered = tuple(sorted(
        by_decision.values(),
        key=lambda item: (-item.relevant_timestamp.timestamp(), item.record_identity),
    ))
    filtered = tuple(item for item in ordered if _matches(item, query))
    total = len(filtered)
    page_count = (total + query.page_size - 1) // query.page_size
    start = (query.page - 1) * query.page_size
    page_records = filtered[start:start + query.page_size]
    return HistoricalReportsProjection(
        query, governed_current_trading_date, filtered, page_records,
        _overview(filtered), page_count, total,
    )


def export_reports_json(projection: HistoricalReportsProjection) -> bytes:
    return (json.dumps({
        "schema": REPORTS_EXPORT_SCHEMA,
        "authority": REPORTS_AUTHORITY,
        "product": projection.query.product.value,
        "filters": _filters(projection.query),
        "records": [_export_record(item) for item in projection.records],
    }, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def export_reports_csv(projection: HistoricalReportsProjection) -> bytes:
    target = io.StringIO()
    fields = tuple(_export_record_fields())
    writer = csv.DictWriter(target, fieldnames=fields)
    writer.writeheader()
    writer.writerows(_export_record(item) for item in projection.records)
    return target.getvalue().encode("utf-8")


def _from_operational(
    item: ObservationOperationalHandoffV2,
) -> HistoricalReportRecord | None:
    if item.operational_route is ObservationOperationalRoute.ACTIVE:
        return None
    observation = item.mode is ObservationMode.PAPER_OBSERVATION
    if observation:
        if item.paper_track_identity is None:
            return None
        family = ReportFamily.PAPER_OBSERVATION
    elif (
        item.mode in {ObservationMode.PAPER, ObservationMode.LIVE}
        and item.sponsor_position_identity is not None
        and item.activation_disposition.value == "ACTIVATED"
    ):
        family = ReportFamily(item.mode.value)
    else:
        return None
    relevant = item.completion_timestamp or item.decision_timestamp
    return HistoricalReportRecord(
        record_identity=(item.paper_track_identity or item.sponsor_position_identity or item.decision_identity),
        decision_identity=item.decision_identity,
        record_date=relevant.astimezone(_IST).date(),
        relevant_timestamp=relevant,
        instrument=item.instrument,
        direction=item.direction,
        family=family,
        status=(
            "COMPLETE" if observation and item.paper_track_state == "COMPLETE"
            else "OUTCOME NOT ESTABLISHED" if observation
            else "EXITED"
        ),
        entry=item.entry,
        exit=None if observation else item.exit,
        pnl=None if observation else item.position_gross_pnl,
        target=item.target,
        stop=item.stop,
        sponsor_position_outcome=(
            "NOT_APPLICABLE" if observation
            else "CLOSED" if item.exit is not None else "UNAVAILABLE"
        ),
        paper_track_outcome=(
            item.paper_track_outcome if observation else "NOT_APPLICABLE"
        ),
        objective_outcome=item.objective_outcome,
        step31_severity=item.step31_severity.value,
        risk_state=item.risk_state,
        activation_disposition=item.activation_disposition.value,
        source_contract_identity=item.projection_contract_identity,
        source_contract_version=item.projection_contract_version,
    )


def _matches(item: HistoricalReportRecord, query: ReportsQuery) -> bool:
    family = {
        ReportView.PAPER: ReportFamily.PAPER,
        ReportView.LIVE: ReportFamily.LIVE,
        ReportView.PAPER_OBSERVATIONS: ReportFamily.PAPER_OBSERVATION,
    }.get(query.view)
    return (
        (family is None or item.family is family)
        and (query.from_date is None or item.record_date >= query.from_date)
        and (query.to_date is None or item.record_date <= query.to_date)
        and (not query.instrument or query.instrument.casefold() in item.instrument.casefold())
        and (query.direction is None or item.direction is query.direction)
        and (not query.status or query.status.casefold() in (
            item.status + " " + item.sponsor_position_outcome + " "
            + item.paper_track_outcome
        ).casefold())
    )


def _overview(records: tuple[HistoricalReportRecord, ...]) -> ReportsOverview:
    positions = tuple(
        item for item in records
        if item.family in {ReportFamily.PAPER, ReportFamily.LIVE}
    )
    net_pnl = (
        None if not positions or any(item.pnl is None for item in positions)
        else sum((item.pnl for item in positions if item.pnl is not None), Decimal("0"))
    )
    return ReportsOverview(
        records=len(records),
        paper_positions=sum(item.family is ReportFamily.PAPER for item in records),
        live_positions=sum(item.family is ReportFamily.LIVE for item in records),
        paper_observations=sum(
            item.family is ReportFamily.PAPER_OBSERVATION for item in records
        ),
        completed_records=len(records),
        net_pnl=net_pnl,
    )


def _filters(query: ReportsQuery) -> dict[str, object]:
    return {
        "view": query.view.value,
        "from": None if query.from_date is None else query.from_date.isoformat(),
        "to": None if query.to_date is None else query.to_date.isoformat(),
        "instrument": query.instrument,
        "direction": None if query.direction is None else query.direction.value,
        "status": query.status,
    }


def _export_record(item: HistoricalReportRecord) -> dict[str, object]:
    return {
        "record_identity": item.record_identity,
        "decision_identity": item.decision_identity,
        "evidence_family": item.family.value,
        "record_date": item.record_date.isoformat(),
        "timestamp": item.relevant_timestamp.isoformat(),
        "instrument": item.instrument,
        "direction": item.direction.value,
        "status": item.status,
        "entry": _value(item.entry),
        "exit": _value(item.exit),
        "pnl": "UNAVAILABLE" if item.family is ReportFamily.PAPER_OBSERVATION else _value(item.pnl),
        "target": _value(item.target),
        "stop": _value(item.stop),
        "sponsor_position_outcome": item.sponsor_position_outcome,
        "paper_track_outcome": item.paper_track_outcome,
        "objective_outcome": item.objective_outcome,
        "step31_severity": item.step31_severity,
        "risk_state": item.risk_state,
        "source_contract_identity": item.source_contract_identity,
        "source_contract_version": item.source_contract_version,
    }


def _export_record_fields() -> tuple[str, ...]:
    return (
        "record_identity", "decision_identity", "evidence_family", "record_date",
        "timestamp", "instrument", "direction", "status", "entry", "exit",
        "pnl", "target", "stop", "sponsor_position_outcome",
        "paper_track_outcome", "objective_outcome", "step31_severity",
        "risk_state", "source_contract_identity", "source_contract_version",
    )


def _value(value: Decimal | None) -> str:
    return "UNAVAILABLE" if value is None else str(value)


__all__ = [
    "HistoricalReportRecord", "HistoricalReportsProjection", "ReportFamily",
    "ReportProduct", "ReportsOverview", "ReportsQuery", "ReportView",
    "export_reports_csv", "export_reports_json", "project_historical_reports",
]
