"""Prospective V2 research projection linking Paper Observation evidence.

V2 is deliberately additive.  It references the immutable V1 decision row and
adds integrity-bound Paper Observation relationships; it never migrates or
reinterprets historical V1 rows and never creates trading authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import csv
import io
import json
import os
from pathlib import Path
import re
from threading import RLock

from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.observation_research_ledger import (
    ObservationLinkKind,
    ObservationResearchLedgerService,
    ObservationResearchProjectionV1,
)
from kronos.swing.v1.paper_observation_track import (
    LocalPaperObservationTrackStore,
    PAPER_OBSERVATION_TRACK_CONTRACT_ID,
    PAPER_OBSERVATION_TRACK_CONTRACT_VERSION,
    PaperObservationEventV1,
    PaperObservationMonitoringState,
    PaperObservationOutcome,
    PaperObservationTrackProjectionV1,
    PaperObservationTrackState,
    PaperObservationTrackV1,
)
from kronos.swing.v1.sponsor_observation_decision import (
    SponsorActivationDisposition,
)
from kronos.swing.v1.step31_observation import Step31WarningSeverity


OBSERVATION_RESEARCH_V2_CONTRACT_ID = (
    "KRONOS-SWING-OBSERVATION-RESEARCH-LEDGER-V2"
)
OBSERVATION_RESEARCH_V2_CONTRACT_VERSION = "2"
SPONSOR_OBSERVATION_PROJECTION_V2_CONTRACT_ID = (
    "KRONOS-SWING-SPONSOR-OBSERVATION-PROJECTION-V2"
)
SPONSOR_OBSERVATION_PROJECTION_V2_CONTRACT_VERSION = "2"
OBSERVATION_RESEARCH_V2_STORE_SCHEMA = (
    "KRONOS-SWING-OBSERVATION-RESEARCH-LEDGER-STORE-V2"
)
OBSERVATION_RESEARCH_V2_EXPORT_SCHEMA = (
    "KRONOS-SWING-OBSERVATION-RESEARCH-EXPORT-V2"
)
OBSERVATION_RESEARCH_V2_AUTHORITY = (
    "RESEARCH_EVIDENCE_ONLY_NO_ANALYTICAL_RISK_READINESS_POSITION_EXECUTION_"
    "OR_BROKER_AUTHORITY"
)


class PaperObservationLinkKind(StrEnum):
    TRACK = "PAPER_OBSERVATION_TRACK"
    EVENT = "PAPER_OBSERVATION_EVENT"
    OUTCOME = "PAPER_OBSERVATION_OUTCOME"


class ObservationProduct(StrEnum):
    SWING = "SWING"


class ObservationMode(StrEnum):
    PAPER = "PAPER"
    LIVE = "LIVE"
    IGNORE = "IGNORE"
    PAPER_OBSERVATION = "PAPER_OBSERVATION"


class ObservationOperationalRoute(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED_CURRENT_TRADING_DAY = "COMPLETED_CURRENT_TRADING_DAY"
    HISTORICAL = "HISTORICAL"


class WebSocketPresentationState(StrEnum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    IDLE = "IDLE"


@dataclass(frozen=True, slots=True)
class ObservationResearchRecordV2:
    record_identity: str
    v1_record_identity: str
    v1_record_integrity_sha256: str
    decision_identity: str
    native_run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    created_at: datetime
    integrity_sha256: str
    contract_identity: str = OBSERVATION_RESEARCH_V2_CONTRACT_ID
    contract_version: str = OBSERVATION_RESEARCH_V2_CONTRACT_VERSION
    authority: str = OBSERVATION_RESEARCH_V2_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not all(_identity(value) for value in (
                self.record_identity,
                self.v1_record_identity,
                self.decision_identity,
                self.native_run_identity,
            ))
            or not self.canonical_instrument
            or not all(_digest(value) for value in (
                self.v1_record_integrity_sha256,
                self.native_assessment_sha256,
                self.integrity_sha256,
            ))
            or not _aware(self.created_at)
            or self.contract_identity != OBSERVATION_RESEARCH_V2_CONTRACT_ID
            or self.contract_version != OBSERVATION_RESEARCH_V2_CONTRACT_VERSION
            or self.authority != OBSERVATION_RESEARCH_V2_AUTHORITY
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("OBSERVATION_RESEARCH_V2_RECORD_INVALID")


@dataclass(frozen=True, slots=True)
class PaperObservationResearchLinkV2:
    link_identity: str
    record_identity: str
    kind: PaperObservationLinkKind
    track_identity: str
    source_identity: str
    source_integrity_sha256: str
    source_state: str
    source_timestamp: datetime
    sponsor_decision_identity: str
    decision_snapshot_identity: str
    step31_observation_identity: str
    native_run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    direction: V1Direction
    integrity_sha256: str
    source_contract_identity: str = PAPER_OBSERVATION_TRACK_CONTRACT_ID
    source_contract_version: str = PAPER_OBSERVATION_TRACK_CONTRACT_VERSION
    contract_identity: str = OBSERVATION_RESEARCH_V2_CONTRACT_ID
    contract_version: str = OBSERVATION_RESEARCH_V2_CONTRACT_VERSION
    authority: str = OBSERVATION_RESEARCH_V2_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not all(_identity(value) for value in (
                self.link_identity,
                self.record_identity,
                self.track_identity,
                self.source_identity,
                self.sponsor_decision_identity,
                self.decision_snapshot_identity,
                self.step31_observation_identity,
                self.native_run_identity,
            ))
            or not self.canonical_instrument
            or not all(_digest(value) for value in (
                self.source_integrity_sha256,
                self.native_assessment_sha256,
                self.integrity_sha256,
            ))
            or type(self.kind) is not PaperObservationLinkKind
            or type(self.direction) is not V1Direction
            or not re.fullmatch(r"[A-Z0-9_ -]{1,128}", self.source_state)
            or not _aware(self.source_timestamp)
            or self.source_contract_identity != PAPER_OBSERVATION_TRACK_CONTRACT_ID
            or self.source_contract_version != PAPER_OBSERVATION_TRACK_CONTRACT_VERSION
            or self.contract_identity != OBSERVATION_RESEARCH_V2_CONTRACT_ID
            or self.contract_version != OBSERVATION_RESEARCH_V2_CONTRACT_VERSION
            or self.authority != OBSERVATION_RESEARCH_V2_AUTHORITY
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("OBSERVATION_RESEARCH_V2_LINK_INVALID")


@dataclass(frozen=True, slots=True)
class ObservationResearchProjectionV2:
    record: ObservationResearchRecordV2
    source: ObservationResearchProjectionV1
    paper_links: tuple[PaperObservationResearchLinkV2, ...]
    paper_track: PaperObservationTrackProjectionV1 | None
    paper_track_state: PaperObservationTrackState | None

    @property
    def objective_outcome_available(self) -> bool:
        return self.source.objective_outcome_available

    @property
    def sponsor_position_outcome_available(self) -> bool:
        return self.source.sponsor_position_outcome_available

    @property
    def paper_track_outcome_available(self) -> bool:
        return bool(
            self.paper_track is not None
            and self.paper_track.outcome_state
            not in {
                PaperObservationOutcome.ENTRY_NOT_OBSERVED,
                PaperObservationOutcome.ENTRY_OBSERVED,
                PaperObservationOutcome.OUTCOME_NOT_ESTABLISHED,
            }
        )


@dataclass(frozen=True, slots=True)
class ObservationResearchQueryV2:
    choices: tuple[SponsorTradeChoice, ...] = ()
    dispositions: tuple[SponsorActivationDisposition, ...] = ()
    severities: tuple[Step31WarningSeverity, ...] = ()
    risk_states: tuple[str, ...] = ()
    paper_track_states: tuple[PaperObservationTrackState, ...] = ()
    paper_monitoring_states: tuple[PaperObservationMonitoringState, ...] = ()
    sponsor_position_present: bool | None = None
    paper_track_present: bool | None = None
    objective_outcome_available: bool | None = None
    sponsor_position_outcome_available: bool | None = None

    def __post_init__(self) -> None:
        if (
            any(type(item) is not SponsorTradeChoice for item in self.choices)
            or any(type(item) is not SponsorActivationDisposition for item in self.dispositions)
            or any(type(item) is not Step31WarningSeverity for item in self.severities)
            or any(item not in {
                "RISK_APPROVED", "RISK_CONSTRAINED", "RISK_REJECTED", "RISK_UNAVAILABLE"
            } for item in self.risk_states)
            or any(type(item) is not PaperObservationTrackState for item in self.paper_track_states)
            or any(type(item) is not PaperObservationMonitoringState for item in self.paper_monitoring_states)
            or any(value not in {None, True, False} for value in (
                self.sponsor_position_present,
                self.paper_track_present,
                self.objective_outcome_available,
                self.sponsor_position_outcome_available,
            ))
        ):
            raise ValueError("OBSERVATION_RESEARCH_V2_QUERY_INVALID")


@dataclass(frozen=True, slots=True)
class CurrentMarketFactV2:
    canonical_instrument: str
    last_price: Decimal
    observed_at: datetime
    source_identity: str
    trusted: bool

    def __post_init__(self) -> None:
        if (
            not self.canonical_instrument
            or not _finite(self.last_price)
            or self.last_price < 0
            or not _aware(self.observed_at)
            or not _identity(self.source_identity)
            or type(self.trusted) is not bool
        ):
            raise ValueError("OBSERVATION_CURRENT_MARKET_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class GovernedPositionPresentationFactsV2:
    decision_identity: str
    sponsor_position_identity: str
    mode: SponsorTradeChoice
    state: str
    actual_entry: Decimal | None
    actual_exit: Decimal | None
    gross_pnl: Decimal | None
    completion_timestamp: datetime | None
    source_integrity_sha256: str

    def __post_init__(self) -> None:
        if (
            not _identity(self.decision_identity)
            or not _identity(self.sponsor_position_identity)
            or self.mode not in {SponsorTradeChoice.PAPER, SponsorTradeChoice.LIVE}
            or not re.fullmatch(r"[A-Z0-9_ -]{1,128}", self.state)
            or any(value is not None and not _finite(value) for value in (
                self.actual_entry, self.actual_exit, self.gross_pnl
            ))
            or (
                self.completion_timestamp is not None
                and not _aware(self.completion_timestamp)
            )
            or not _digest(self.source_integrity_sha256)
        ):
            raise ValueError("OBSERVATION_POSITION_PRESENTATION_FACT_INVALID")


@dataclass(frozen=True, slots=True)
class ObservationOperationalHandoffV2:
    product: ObservationProduct
    mode: ObservationMode
    instrument: str
    direction: V1Direction
    decision_identity: str
    decision_timestamp: datetime
    step31_severity: Step31WarningSeverity
    step31_warnings: tuple[str, ...]
    risk_state: str
    activation_disposition: SponsorActivationDisposition
    sponsor_position_identity: str | None
    sponsor_position_state: str
    paper_track_identity: str | None
    paper_track_state: str
    paper_track_latest_event: str
    paper_track_outcome: str
    objective_state: str
    objective_outcome: str
    entry: Decimal | None
    exit: Decimal | None
    position_gross_pnl: Decimal | None
    stop: Decimal | None
    target: Decimal | None
    current_ltp: Decimal | None
    current_ltp_observed_at: datetime | None
    distance_to_target: Decimal | None
    distance_to_stop: Decimal | None
    distance_to_target_state: str
    distance_to_stop_state: str
    monetary_pnl_state: str
    completion_timestamp: datetime | None
    operational_route: ObservationOperationalRoute
    websocket_state: WebSocketPresentationState
    projection_contract_identity: str = SPONSOR_OBSERVATION_PROJECTION_V2_CONTRACT_ID
    projection_contract_version: str = SPONSOR_OBSERVATION_PROJECTION_V2_CONTRACT_VERSION


class LocalObservationResearchLedgerV2Store:
    """Append-only V2 record/link store with deterministic replay."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("OBSERVATION_RESEARCH_V2_STORE_INVALID")
        self._lock = RLock()

    def retain_record(self, record: ObservationResearchRecordV2) -> ObservationResearchRecordV2:
        return self._retain(
            self.root / "records" / f"{record.record_identity}.json", "record", record
        )

    def retain_link(self, link: PaperObservationResearchLinkV2) -> PaperObservationResearchLinkV2:
        return self._retain(
            self.root / "links" / f"{link.link_identity}.json", "link", link
        )

    def load_records(self) -> tuple[ObservationResearchRecordV2, ...]:
        return tuple(
            self._load_record(path)
            for path in sorted((self.root / "records").glob("*.json"))
        )

    def load_links(self) -> tuple[PaperObservationResearchLinkV2, ...]:
        return tuple(
            self._load_link(path)
            for path in sorted((self.root / "links").glob("*.json"))
        )

    def _retain(self, path: Path, key: str, value):  # type: ignore[no-untyped-def]
        payload = {"schema": OBSERVATION_RESEARCH_V2_STORE_SCHEMA, key: _primitive(value)}
        with self._lock:
            if path.exists():
                restored = self._load_record(path) if key == "record" else self._load_link(path)
                if restored != value:
                    raise ValueError("OBSERVATION_RESEARCH_V2_IMMUTABILITY_VIOLATION")
                return restored
            _atomic(path, payload)
        return value

    def _load_record(self, path: Path) -> ObservationResearchRecordV2:
        return ObservationResearchRecordV2(**self._payload(path, "record"))

    def _load_link(self, path: Path) -> PaperObservationResearchLinkV2:
        data = self._payload(path, "link")
        data["kind"] = PaperObservationLinkKind(data["kind"])
        data["direction"] = V1Direction(data["direction"])
        data["source_timestamp"] = datetime.fromisoformat(str(data["source_timestamp"]))
        return PaperObservationResearchLinkV2(**data)

    @staticmethod
    def _payload(path: Path, key: str) -> dict[str, object]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema") != OBSERVATION_RESEARCH_V2_STORE_SCHEMA:
                raise ValueError
            data = dict(payload[key])
            if key == "record":
                data["created_at"] = datetime.fromisoformat(str(data["created_at"]))
            return data
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("OBSERVATION_RESEARCH_V2_STORED_RECORD_INVALID") from error


class ObservationResearchLedgerV2Service:
    """Prospectively link exact Paper evidence to V1 decision rows."""

    def __init__(
        self,
        store: LocalObservationResearchLedgerV2Store,
        v1: ObservationResearchLedgerService,
        paper: LocalPaperObservationTrackStore,
    ) -> None:
        if (
            type(store) is not LocalObservationResearchLedgerV2Store
            or type(v1) is not ObservationResearchLedgerService
            or type(paper) is not LocalPaperObservationTrackStore
        ):
            raise TypeError("OBSERVATION_RESEARCH_V2_SERVICE_INPUT_INVALID")
        self.store = store
        self.v1 = v1
        self.paper = paper

    def retain_observation(
        self, source: ObservationResearchProjectionV1
    ) -> ObservationResearchRecordV2:
        values = dict(
            record_identity="OBSERVATION-RESEARCH-V2-" + sha256(
                source.record.decision_identity.encode("utf-8")
            ).hexdigest(),
            v1_record_identity=source.record.record_identity,
            v1_record_integrity_sha256=source.record.integrity_sha256,
            decision_identity=source.record.decision_identity,
            native_run_identity=source.record.native_run_identity,
            canonical_instrument=source.record.canonical_instrument,
            native_assessment_sha256=source.record.native_assessment_sha256,
            created_at=source.record.decision_timestamp,
            integrity_sha256="",
        )
        return self.store.retain_record(ObservationResearchRecordV2(**(
            values | {"integrity_sha256": _values_digest(values)}
        )))

    def retain_decision(self, decision_identity: str) -> ObservationResearchRecordV2:
        matches = tuple(
            item for item in self.v1.snapshot()
            if item.record.decision_identity == decision_identity
        )
        if len(matches) != 1:
            raise ValueError("OBSERVATION_RESEARCH_V2_DECISION_NOT_FOUND")
        return self.retain_observation(matches[0])

    def synchronize(self) -> tuple[ObservationResearchProjectionV2, ...]:
        records = self.store.load_records()
        by_decision = {record.decision_identity: record for record in records}
        tracks = self.paper.load_all_tracks()
        for track in tracks:
            record = by_decision.get(track.sponsor_decision_identity)
            if record is None:
                continue
            source = self._source(record)
            self._validate_track(source, track)
            self.store.retain_link(self._link_for_track(record, track))
            events = self.paper.events(track.track_identity)
            for event in events:
                self.store.retain_link(self._link_for_event(record, track, event))
            terminal = tuple(
                item for item in events
                if item.outcome in {
                    PaperObservationOutcome.STOP_LEVEL_TOUCHED,
                    PaperObservationOutcome.TARGET_LEVEL_TOUCHED,
                    PaperObservationOutcome.BOTH_ORDERING_UNRESOLVED,
                    PaperObservationOutcome.OUTCOME_NOT_ESTABLISHED,
                }
            )
            if len(terminal) > 1:
                raise ValueError("OBSERVATION_RESEARCH_V2_DUPLICATE_OR_CORRUPT_OUTCOME")
            if terminal:
                self.store.retain_link(self._link_for_event(
                    record, track, terminal[0], kind=PaperObservationLinkKind.OUTCOME
                ))
        return self.snapshot()

    def snapshot(
        self, query: ObservationResearchQueryV2 | None = None
    ) -> tuple[ObservationResearchProjectionV2, ...]:
        query = query or ObservationResearchQueryV2()
        links = self.store.load_links()
        projections = tuple(self._projection(record, links) for record in self.store.load_records())
        return tuple(sorted(
            (item for item in projections if _matches(item, query)),
            key=lambda item: (
                -item.source.record.decision_timestamp.timestamp(), item.record.record_identity
            ),
        ))

    def export_structured(
        self, query: ObservationResearchQueryV2 | None = None
    ) -> tuple[dict[str, object], ...]:
        return tuple(_export_row(item) for item in self.synchronize() if _matches(item, query or ObservationResearchQueryV2()))

    def export_json(self, query: ObservationResearchQueryV2 | None = None) -> str:
        return json.dumps({
            "schema": OBSERVATION_RESEARCH_V2_EXPORT_SCHEMA,
            "authority": OBSERVATION_RESEARCH_V2_AUTHORITY,
            "records": list(self.export_structured(query)),
        }, sort_keys=True, separators=(",", ":")) + "\n"

    def export_csv(self, query: ObservationResearchQueryV2 | None = None) -> str:
        rows = self.export_structured(query)
        target = io.StringIO()
        fields = tuple(_export_row_fields())
        writer = csv.DictWriter(target, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return target.getvalue()

    def operational_handoffs(
        self,
        *,
        current_facts: dict[str, CurrentMarketFactV2] | None = None,
        governed_current_trading_date: date,
        completion_trading_dates: dict[str, date] | None = None,
        position_facts: dict[str, GovernedPositionPresentationFactsV2] | None = None,
        websocket_state: WebSocketPresentationState = WebSocketPresentationState.IDLE,
    ) -> tuple[ObservationOperationalHandoffV2, ...]:
        current_facts = current_facts or {}
        completion_trading_dates = completion_trading_dates or {}
        position_facts = position_facts or {}
        return tuple(
            _operational_handoff(
                item,
                current_facts.get(item.record.canonical_instrument),
                governed_current_trading_date,
                completion_trading_dates.get(item.record.decision_identity),
                websocket_state,
                position_facts.get(item.record.decision_identity),
            )
            for item in self.synchronize()
        )

    def _source(self, record: ObservationResearchRecordV2) -> ObservationResearchProjectionV1:
        matches = tuple(
            item for item in self.v1.snapshot()
            if item.record.decision_identity == record.decision_identity
        )
        if (
            len(matches) != 1
            or matches[0].record.record_identity != record.v1_record_identity
            or matches[0].record.integrity_sha256 != record.v1_record_integrity_sha256
            or matches[0].record.native_run_identity != record.native_run_identity
            or matches[0].record.canonical_instrument != record.canonical_instrument
            or matches[0].record.native_assessment_sha256 != record.native_assessment_sha256
        ):
            raise ValueError("OBSERVATION_RESEARCH_V2_SOURCE_BINDING_INVALID")
        return matches[0]

    def _projection(
        self,
        record: ObservationResearchRecordV2,
        links: tuple[PaperObservationResearchLinkV2, ...],
    ) -> ObservationResearchProjectionV2:
        source = self._source(record)
        bound = tuple(sorted(
            (link for link in links if link.record_identity == record.record_identity),
            key=lambda item: (item.source_timestamp, item.kind.value, item.link_identity),
        ))
        track_links = tuple(link for link in bound if link.kind is PaperObservationLinkKind.TRACK)
        if len(track_links) > 1:
            raise ValueError("OBSERVATION_RESEARCH_V2_DUPLICATE_OR_CORRUPT_TRACK")
        paper_projection = None
        state = _paper_state_without_track(source)
        if track_links:
            track = self.paper.load_track(track_links[0].track_identity)
            self._validate_track(source, track)
            paper_projection = self.paper.projection(track.track_identity)
            state = paper_projection.track_state
        return ObservationResearchProjectionV2(record, source, bound, paper_projection, state)

    @staticmethod
    def _validate_track(source: ObservationResearchProjectionV1, track: PaperObservationTrackV1) -> None:
        decision = source.source
        snapshot = decision.snapshot
        if (
            decision.decision.choice is not SponsorTradeChoice.PAPER
            or decision.activation.disposition is SponsorActivationDisposition.ACTIVATED
            or track.sponsor_decision_identity != decision.decision.decision_identity
            or track.sponsor_decision_sha256 != decision.decision.integrity_sha256
            or track.decision_snapshot_identity != snapshot.snapshot_identity
            or track.decision_snapshot_sha256 != snapshot.integrity_sha256
            or track.step31_observation_identity != snapshot.step31_observation_identity
            or track.step31_observation_sha256 != snapshot.step31_observation_sha256
            or track.native_run_identity != snapshot.native_run_identity
            or track.canonical_instrument != snapshot.canonical_instrument
            or track.native_assessment_sha256 != snapshot.native_assessment_sha256
            or track.direction is not snapshot.direction
        ):
            raise ValueError("OBSERVATION_RESEARCH_V2_TRACK_BINDING_INVALID")

    @staticmethod
    def _link_for_track(
        record: ObservationResearchRecordV2, track: PaperObservationTrackV1
    ) -> PaperObservationResearchLinkV2:
        return _make_link(
            record, track, PaperObservationLinkKind.TRACK,
            track.track_identity, track.integrity_sha256,
            PaperObservationTrackState.ACTIVE.value, track.created_at,
        )

    @staticmethod
    def _link_for_event(
        record: ObservationResearchRecordV2,
        track: PaperObservationTrackV1,
        event: PaperObservationEventV1,
        *,
        kind: PaperObservationLinkKind = PaperObservationLinkKind.EVENT,
    ) -> PaperObservationResearchLinkV2:
        if event.track_identity != track.track_identity:
            raise ValueError("OBSERVATION_RESEARCH_V2_EVENT_BINDING_INVALID")
        return _make_link(
            record, track, kind, event.event_identity, event.integrity_sha256,
            event.outcome.value, event.observed_at,
        )


def _make_link(
    record: ObservationResearchRecordV2,
    track: PaperObservationTrackV1,
    kind: PaperObservationLinkKind,
    source_identity: str,
    source_integrity_sha256: str,
    source_state: str,
    source_timestamp: datetime,
) -> PaperObservationResearchLinkV2:
    values = dict(
        link_identity="OBSERVATION-RESEARCH-V2-LINK-" + sha256("|".join((
            record.record_identity, kind.value, source_identity, source_integrity_sha256,
        )).encode("utf-8")).hexdigest(),
        record_identity=record.record_identity,
        kind=kind,
        track_identity=track.track_identity,
        source_identity=source_identity,
        source_integrity_sha256=source_integrity_sha256,
        source_state=source_state,
        source_timestamp=source_timestamp,
        sponsor_decision_identity=track.sponsor_decision_identity,
        decision_snapshot_identity=track.decision_snapshot_identity,
        step31_observation_identity=track.step31_observation_identity,
        native_run_identity=track.native_run_identity,
        canonical_instrument=track.canonical_instrument,
        native_assessment_sha256=track.native_assessment_sha256,
        direction=track.direction,
        integrity_sha256="",
        source_contract_identity=PAPER_OBSERVATION_TRACK_CONTRACT_ID,
        source_contract_version=PAPER_OBSERVATION_TRACK_CONTRACT_VERSION,
    )
    return PaperObservationResearchLinkV2(**(
        values | {"integrity_sha256": _values_digest(values)}
    ))


def _paper_state_without_track(
    source: ObservationResearchProjectionV1,
) -> PaperObservationTrackState | None:
    decision = source.source
    if decision.decision.choice is not SponsorTradeChoice.PAPER:
        return None
    if decision.activation.disposition is SponsorActivationDisposition.ACTIVATED:
        return PaperObservationTrackState.NOT_APPLICABLE_POSITION_ACTIVATED
    if decision.activation.disposition.value.startswith("BLOCKED_"):
        return PaperObservationTrackState.AVAILABLE
    return PaperObservationTrackState.OUTCOME_NOT_ESTABLISHED


def _matches(item: ObservationResearchProjectionV2, query: ObservationResearchQueryV2) -> bool:
    source = item.source.source
    paper = item.paper_track
    return (
        (not query.choices or source.decision.choice in query.choices)
        and (not query.dispositions or source.activation.disposition in query.dispositions)
        and (not query.severities or source.snapshot.step31_severity in query.severities)
        and (not query.risk_states or source.snapshot.risk_state in query.risk_states)
        and (not query.paper_track_states or item.paper_track_state in query.paper_track_states)
        and (
            not query.paper_monitoring_states
            or (paper is not None and paper.monitoring_state in query.paper_monitoring_states)
        )
        and (
            query.sponsor_position_present is None
            or (source.activation.sponsor_position_identity is not None)
            is query.sponsor_position_present
        )
        and (
            query.paper_track_present is None
            or (paper is not None) is query.paper_track_present
        )
        and (
            query.objective_outcome_available is None
            or item.objective_outcome_available is query.objective_outcome_available
        )
        and (
            query.sponsor_position_outcome_available is None
            or item.sponsor_position_outcome_available
            is query.sponsor_position_outcome_available
        )
    )


def _export_row_fields() -> tuple[str, ...]:
    return (
        "record_identity", "v1_record_identity", "decision_identity",
        "decision_timestamp", "product", "mode", "native_run_identity",
        "canonical_instrument", "native_assessment_sha256", "direction",
        "step31_severity", "step31_warnings", "risk_state",
        "activation_disposition", "sponsor_position_identity",
        "sponsor_position_state", "sponsor_position_outcome",
        "sponsor_position_outcome_available", "paper_track_identity",
        "paper_track_state", "paper_track_monitoring_state",
        "observation_entry_reference", "paper_track_entry_state",
        "paper_track_latest_event", "paper_track_outcome",
        "paper_track_created_at", "paper_track_last_observation_at",
        "paper_track_monetary_pnl", "objective_kr380_state",
        "objective_kr390_state", "objective_outcome",
        "objective_outcome_available", "paper_link_identities",
    )


def _export_row(item: ObservationResearchProjectionV2) -> dict[str, object]:
    source = item.source.source
    snapshot = source.snapshot
    paper = item.paper_track
    v1_links = item.source.links
    position_outcome = _latest_v1(v1_links, ObservationLinkKind.SPONSOR_POSITION_OUTCOME)
    kr380 = _latest_v1(v1_links, ObservationLinkKind.KR380_ENTRY_OUTCOME)
    model = _latest_v1(v1_links, ObservationLinkKind.KR390_OBJECTIVE_MODEL)
    objective = _latest_v1(v1_links, ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME)
    mode = (
        ObservationMode.PAPER_OBSERVATION.value
        if paper is not None
        else source.decision.choice.value
    )
    return {
        "record_identity": item.record.record_identity,
        "v1_record_identity": item.record.v1_record_identity,
        "decision_identity": item.record.decision_identity,
        "decision_timestamp": item.record.created_at.isoformat(),
        "product": ObservationProduct.SWING.value,
        "mode": mode,
        "native_run_identity": item.record.native_run_identity,
        "canonical_instrument": item.record.canonical_instrument,
        "native_assessment_sha256": item.record.native_assessment_sha256,
        "direction": snapshot.direction.value,
        "step31_severity": snapshot.step31_severity.value,
        "step31_warnings": "|".join(snapshot.step31_warnings) or "NONE",
        "risk_state": snapshot.risk_state,
        "activation_disposition": source.activation.disposition.value,
        "sponsor_position_identity": source.activation.sponsor_position_identity or "UNAVAILABLE",
        "sponsor_position_state": (
            "AVAILABLE" if source.activation.sponsor_position_identity else "UNAVAILABLE"
        ),
        "sponsor_position_outcome": "UNAVAILABLE" if position_outcome is None else position_outcome.source_state,
        "sponsor_position_outcome_available": "AVAILABLE" if item.sponsor_position_outcome_available else "UNAVAILABLE",
        "paper_track_identity": "UNAVAILABLE" if paper is None else paper.track.track_identity,
        "paper_track_state": "NOT_APPLICABLE" if item.paper_track_state is None else item.paper_track_state.value,
        "paper_track_monitoring_state": "NOT_APPLICABLE" if paper is None else paper.monitoring_state.value,
        "observation_entry_reference": "UNAVAILABLE" if paper is None or paper.track.observation_entry_reference is None else str(paper.track.observation_entry_reference),
        "paper_track_entry_state": "NOT_APPLICABLE" if paper is None else paper.entry_state.value,
        "paper_track_latest_event": "NOT_APPLICABLE" if paper is None else paper.latest_event.value,
        "paper_track_outcome": "NOT_APPLICABLE" if paper is None else paper.outcome_state.value,
        "paper_track_created_at": "UNAVAILABLE" if paper is None else paper.created_at.isoformat(),
        "paper_track_last_observation_at": "UNAVAILABLE" if paper is None or paper.last_factual_observation_at is None else paper.last_factual_observation_at.isoformat(),
        "paper_track_monetary_pnl": "UNAVAILABLE",
        "objective_kr380_state": "UNAVAILABLE" if kr380 is None else kr380.source_state,
        "objective_kr390_state": "UNAVAILABLE" if model is None else model.source_state,
        "objective_outcome": "UNAVAILABLE" if objective is None else objective.source_state,
        "objective_outcome_available": "AVAILABLE" if item.objective_outcome_available else "UNAVAILABLE",
        "paper_link_identities": "|".join(link.link_identity for link in item.paper_links) or "UNAVAILABLE",
    }


def _operational_handoff(
    item: ObservationResearchProjectionV2,
    market: CurrentMarketFactV2 | None,
    current_trading_date: date,
    completion_trading_date: date | None,
    websocket_state: WebSocketPresentationState,
    position_fact: GovernedPositionPresentationFactsV2 | None,
) -> ObservationOperationalHandoffV2:
    source = item.source.source
    snapshot = source.snapshot
    paper = item.paper_track
    if market is not None and (
        market.canonical_instrument != snapshot.canonical_instrument or not market.trusted
    ):
        market = None
    target_state, target_distance = _distance(
        snapshot.direction, None if market is None else market.last_price,
        snapshot.target, "TARGET", paper,
    )
    stop_state, stop_distance = _distance(
        snapshot.direction, None if market is None else market.last_price,
        snapshot.stop, "STOP", paper,
    )
    position = source.activation.sponsor_position_identity
    if position_fact is not None and (
        position is None
        or position_fact.decision_identity != source.decision.decision_identity
        or position_fact.sponsor_position_identity != position
        or position_fact.mode is not source.decision.choice
    ):
        raise ValueError("OBSERVATION_POSITION_PRESENTATION_BINDING_INVALID")
    track_completion = None
    if paper is not None and paper.track_state is PaperObservationTrackState.COMPLETE:
        events = tuple(
            link for link in item.paper_links
            if link.kind is PaperObservationLinkKind.OUTCOME
        )
        track_completion = None if not events else events[-1].source_timestamp
    completion = (
        track_completion
        if paper is not None
        else None if position_fact is None else position_fact.completion_timestamp
    )
    route = (
        ObservationOperationalRoute.ACTIVE
        if completion_trading_date is None and completion is None
        else (
            ObservationOperationalRoute.COMPLETED_CURRENT_TRADING_DAY
            if completion_trading_date == current_trading_date
            else ObservationOperationalRoute.HISTORICAL
        )
    )
    objective = _latest_v1(item.source.links, ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME)
    model = _latest_v1(item.source.links, ObservationLinkKind.KR390_OBJECTIVE_MODEL)
    mode = (
        ObservationMode.PAPER_OBSERVATION
        if paper is not None
        else ObservationMode(source.decision.choice.value)
    )
    return ObservationOperationalHandoffV2(
        product=ObservationProduct.SWING,
        mode=mode,
        instrument=snapshot.canonical_instrument,
        direction=snapshot.direction,
        decision_identity=source.decision.decision_identity,
        decision_timestamp=source.decision.decision_timestamp,
        step31_severity=snapshot.step31_severity,
        step31_warnings=snapshot.step31_warnings,
        risk_state=snapshot.risk_state,
        activation_disposition=source.activation.disposition,
        sponsor_position_identity=position,
        sponsor_position_state="AVAILABLE" if position else "UNAVAILABLE",
        paper_track_identity=None if paper is None else paper.track.track_identity,
        paper_track_state="NOT_APPLICABLE" if item.paper_track_state is None else item.paper_track_state.value,
        paper_track_latest_event="NOT_APPLICABLE" if paper is None else paper.latest_event.value,
        paper_track_outcome="NOT_APPLICABLE" if paper is None else paper.outcome_state.value,
        objective_state="UNAVAILABLE" if model is None else model.source_state,
        objective_outcome="UNAVAILABLE" if objective is None else objective.source_state,
        entry=(
            snapshot.entry
            if paper is not None
            else None if position_fact is None else position_fact.actual_entry
        ),
        exit=None if position_fact is None else position_fact.actual_exit,
        position_gross_pnl=None if position_fact is None else position_fact.gross_pnl,
        stop=snapshot.stop,
        target=snapshot.target,
        current_ltp=None if market is None else market.last_price,
        current_ltp_observed_at=None if market is None else market.observed_at,
        distance_to_target=target_distance,
        distance_to_stop=stop_distance,
        distance_to_target_state=target_state,
        distance_to_stop_state=stop_state,
        monetary_pnl_state=(
            "UNAVAILABLE"
            if paper is not None or position_fact is None
            else "AVAILABLE" if position_fact.gross_pnl is not None else "NOT_YET_ESTABLISHED"
        ),
        completion_timestamp=completion,
        operational_route=route,
        websocket_state=websocket_state,
    )


def _distance(
    direction: V1Direction,
    ltp: Decimal | None,
    level: Decimal | None,
    kind: str,
    paper: PaperObservationTrackProjectionV1 | None,
) -> tuple[str, Decimal | None]:
    if paper is not None:
        touched = (
            paper.outcome_state is PaperObservationOutcome.TARGET_LEVEL_TOUCHED
            if kind == "TARGET"
            else paper.outcome_state is PaperObservationOutcome.STOP_LEVEL_TOUCHED
        )
        if touched:
            return f"{kind}_LEVEL_TOUCHED", None
        if paper.outcome_state is PaperObservationOutcome.BOTH_ORDERING_UNRESOLVED:
            return "BOTH_ORDERING_UNRESOLVED", None
    if ltp is None or level is None:
        return "UNAVAILABLE", None
    if direction is V1Direction.LONG:
        value = level - ltp if kind == "TARGET" else ltp - level
    else:
        value = ltp - level if kind == "TARGET" else level - ltp
    return "AVAILABLE", value


def websocket_presentation_state(
    *, monitoring_required: bool, connection_state: object | None
) -> WebSocketPresentationState:
    """Project actual shared-monitoring truth; REST Provider state is not input."""

    if not monitoring_required:
        return WebSocketPresentationState.IDLE
    value = getattr(connection_state, "value", connection_state)
    return (
        WebSocketPresentationState.CONNECTED
        if value == "CONNECTED"
        else WebSocketPresentationState.DISCONNECTED
    )


def _latest_v1(links, kind):  # type: ignore[no-untyped-def]
    matches = tuple(link for link in links if link.kind is kind)
    return None if not matches else matches[-1]


def _atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _primitive(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {key: _primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value


def _record_digest(record: object) -> str:
    value = _primitive(record)
    value["integrity_sha256"] = ""
    value.pop("contract_identity", None)
    value.pop("contract_version", None)
    value.pop("authority", None)
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _values_digest(values: dict[str, object]) -> str:
    return sha256(json.dumps(_primitive(values), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _identity(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:@|+/-]{1,512}", value) is not None


def _digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _finite(value: object) -> bool:
    return isinstance(value, Decimal) and value.is_finite()


__all__ = [
    "CurrentMarketFactV2",
    "GovernedPositionPresentationFactsV2",
    "LocalObservationResearchLedgerV2Store",
    "OBSERVATION_RESEARCH_V2_CONTRACT_ID",
    "OBSERVATION_RESEARCH_V2_CONTRACT_VERSION",
    "ObservationMode",
    "ObservationOperationalHandoffV2",
    "ObservationOperationalRoute",
    "ObservationProduct",
    "ObservationResearchLedgerV2Service",
    "ObservationResearchProjectionV2",
    "ObservationResearchQueryV2",
    "ObservationResearchRecordV2",
    "PaperObservationLinkKind",
    "PaperObservationResearchLinkV2",
    "SPONSOR_OBSERVATION_PROJECTION_V2_CONTRACT_ID",
    "WebSocketPresentationState",
    "websocket_presentation_state",
]
