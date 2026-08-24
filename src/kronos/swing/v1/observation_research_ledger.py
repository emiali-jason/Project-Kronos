"""Prospective, authority-free research ledger for Sponsor observations.

The ledger links immutable SPONSOR-OBS-01 decision evidence to later governed
facts.  It never creates an outcome, position, Risk decision, or trading
authority and deliberately exposes no performance analytics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import csv
import io
import json
import os
from pathlib import Path
import re
from threading import RLock

from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.sponsor_observation_decision import (
    LocalSponsorObservationDecisionStore,
    SponsorActivationDisposition,
    SponsorObservationDecisionResult,
)
from kronos.swing.v1.step31_observation import Step31WarningSeverity


OBSERVATION_RESEARCH_CONTRACT_ID = (
    "KRONOS-SWING-OBSERVATION-RESEARCH-LEDGER-V1"
)
OBSERVATION_RESEARCH_CONTRACT_VERSION = "1"
OBSERVATION_RESEARCH_STORE_SCHEMA = (
    "KRONOS-SWING-OBSERVATION-RESEARCH-LEDGER-STORE-V1"
)
OBSERVATION_RESEARCH_AUTHORITY = (
    "RESEARCH_EVIDENCE_ONLY_NO_ANALYTICAL_RISK_READINESS_POSITION_EXECUTION_OR_BROKER_AUTHORITY"
)


class ObservationLinkKind(StrEnum):
    KR380_ENTRY_OUTCOME = "KR380_ENTRY_OUTCOME"
    KR390_OBJECTIVE_MODEL = "KR390_OBJECTIVE_MODEL"
    OBJECTIVE_MODEL_OUTCOME = "OBJECTIVE_MODEL_OUTCOME"
    SPONSOR_POSITION = "SPONSOR_POSITION"
    SPONSOR_POSITION_OUTCOME = "SPONSOR_POSITION_OUTCOME"


@dataclass(frozen=True, slots=True)
class ObservationResearchRecordV1:
    record_identity: str
    snapshot_identity: str
    snapshot_sha256: str
    decision_identity: str
    decision_sha256: str
    activation_identity: str
    activation_sha256: str
    native_run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    choice: SponsorTradeChoice
    activation_disposition: SponsorActivationDisposition
    decision_timestamp: datetime
    integrity_sha256: str
    contract_identity: str = OBSERVATION_RESEARCH_CONTRACT_ID
    contract_version: str = OBSERVATION_RESEARCH_CONTRACT_VERSION
    authority: str = OBSERVATION_RESEARCH_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not all(_identity(item) for item in (
                self.record_identity, self.snapshot_identity,
                self.decision_identity, self.activation_identity,
                self.native_run_identity,
            ))
            or not self.canonical_instrument
            or not all(_digest(item) for item in (
                self.snapshot_sha256, self.decision_sha256,
                self.activation_sha256, self.native_assessment_sha256,
                self.integrity_sha256,
            ))
            or type(self.choice) is not SponsorTradeChoice
            or type(self.activation_disposition) is not SponsorActivationDisposition
            or not _aware(self.decision_timestamp)
            or self.contract_identity != OBSERVATION_RESEARCH_CONTRACT_ID
            or self.contract_version != OBSERVATION_RESEARCH_CONTRACT_VERSION
            or self.authority != OBSERVATION_RESEARCH_AUTHORITY
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("OBSERVATION_RESEARCH_RECORD_INVALID")


@dataclass(frozen=True, slots=True)
class ObservationResearchLinkV1:
    link_identity: str
    record_identity: str
    kind: ObservationLinkKind
    native_run_identity: str
    canonical_instrument: str
    native_assessment_sha256: str
    trade_plan_identity: str | None
    trade_plan_sha256: str | None
    source_contract_identity: str
    source_contract_version: str
    source_record_identity: str
    source_integrity_sha256: str
    source_state: str
    source_timestamp: datetime
    sponsor_position_identity: str | None
    integrity_sha256: str
    contract_identity: str = OBSERVATION_RESEARCH_CONTRACT_ID
    contract_version: str = OBSERVATION_RESEARCH_CONTRACT_VERSION
    authority: str = OBSERVATION_RESEARCH_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not all(_identity(item) for item in (
                self.link_identity, self.record_identity,
                self.native_run_identity, self.source_contract_identity,
                self.source_record_identity,
            ))
            or not self.canonical_instrument
            or not _digest(self.native_assessment_sha256)
            or (self.trade_plan_identity is None) != (self.trade_plan_sha256 is None)
            or (self.trade_plan_identity is not None and (
                not _identity(self.trade_plan_identity)
                or not _digest(self.trade_plan_sha256)
            ))
            or type(self.kind) is not ObservationLinkKind
            or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", self.source_contract_version)
            or not _digest(self.source_integrity_sha256)
            or not re.fullmatch(r"[A-Z0-9_ -]{1,128}", self.source_state)
            or not _aware(self.source_timestamp)
            or (self.sponsor_position_identity is not None
                and not _identity(self.sponsor_position_identity))
            or self.contract_identity != OBSERVATION_RESEARCH_CONTRACT_ID
            or self.contract_version != OBSERVATION_RESEARCH_CONTRACT_VERSION
            or self.authority != OBSERVATION_RESEARCH_AUTHORITY
            or self.integrity_sha256 != _record_digest(self)
        ):
            raise ValueError("OBSERVATION_RESEARCH_LINK_INVALID")


@dataclass(frozen=True, slots=True)
class ObservationResearchProjectionV1:
    record: ObservationResearchRecordV1
    source: SponsorObservationDecisionResult
    links: tuple[ObservationResearchLinkV1, ...]

    @property
    def objective_outcome_available(self) -> bool:
        return any(item.kind is ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME for item in self.links)

    @property
    def sponsor_position_outcome_available(self) -> bool:
        return any(item.kind is ObservationLinkKind.SPONSOR_POSITION_OUTCOME for item in self.links)


@dataclass(frozen=True, slots=True)
class ObservationResearchQueryV1:
    choices: tuple[SponsorTradeChoice, ...] = ()
    dispositions: tuple[SponsorActivationDisposition, ...] = ()
    severities: tuple[Step31WarningSeverity, ...] = ()
    kr370_states: tuple[str, ...] = ()
    risk_states: tuple[str, ...] = ()
    objective_outcome_available: bool | None = None
    sponsor_position_outcome_available: bool | None = None

    def __post_init__(self) -> None:
        if (
            any(type(item) is not SponsorTradeChoice for item in self.choices)
            or any(type(item) is not SponsorActivationDisposition for item in self.dispositions)
            or any(type(item) is not Step31WarningSeverity for item in self.severities)
            or any(item not in {"BUY_NOW", "SELL_NOW"} for item in self.kr370_states)
            or any(item not in {"RISK_APPROVED", "RISK_CONSTRAINED", "RISK_REJECTED", "RISK_UNAVAILABLE"} for item in self.risk_states)
            or self.objective_outcome_available not in {None, True, False}
            or self.sponsor_position_outcome_available not in {None, True, False}
        ):
            raise ValueError("OBSERVATION_RESEARCH_QUERY_INVALID")


class LocalObservationResearchLedgerStore:
    """Append-only event store with deterministic replay and idempotency."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("OBSERVATION_RESEARCH_STORE_INVALID")
        self._lock = RLock()

    def retain_record(self, record: ObservationResearchRecordV1) -> ObservationResearchRecordV1:
        return self._retain(self.root / "records" / f"{record.record_identity}.json", "record", record)

    def retain_link(self, link: ObservationResearchLinkV1) -> ObservationResearchLinkV1:
        return self._retain(self.root / "links" / f"{link.link_identity}.json", "link", link)

    def load_records(self) -> tuple[ObservationResearchRecordV1, ...]:
        return tuple(self._load_record(path) for path in sorted((self.root / "records").glob("*.json")))

    def load_links(self) -> tuple[ObservationResearchLinkV1, ...]:
        return tuple(self._load_link(path) for path in sorted((self.root / "links").glob("*.json")))

    def _retain(self, path: Path, key: str, value):  # type: ignore[no-untyped-def]
        payload = {"schema": OBSERVATION_RESEARCH_STORE_SCHEMA, key: _primitive(value)}
        with self._lock:
            if path.exists():
                restored = self._load_record(path) if key == "record" else self._load_link(path)
                if restored != value:
                    raise ValueError("OBSERVATION_RESEARCH_IMMUTABILITY_VIOLATION")
                return restored
            _atomic(path, payload)
        return value

    def _load_record(self, path: Path) -> ObservationResearchRecordV1:
        data = self._payload(path, "record")
        data["choice"] = SponsorTradeChoice(data["choice"])
        data["activation_disposition"] = SponsorActivationDisposition(data["activation_disposition"])
        data["decision_timestamp"] = datetime.fromisoformat(data["decision_timestamp"])
        return ObservationResearchRecordV1(**data)

    def _load_link(self, path: Path) -> ObservationResearchLinkV1:
        data = self._payload(path, "link")
        data["kind"] = ObservationLinkKind(data["kind"])
        data["source_timestamp"] = datetime.fromisoformat(data["source_timestamp"])
        return ObservationResearchLinkV1(**data)

    @staticmethod
    def _payload(path: Path, key: str) -> dict[str, object]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema") != OBSERVATION_RESEARCH_STORE_SCHEMA:
                raise ValueError
            return dict(payload[key])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("OBSERVATION_RESEARCH_STORED_RECORD_INVALID") from error


class ObservationResearchLedgerService:
    """Join exact decision evidence to append-only downstream factual links."""

    def __init__(self, store: LocalObservationResearchLedgerStore,
                 decisions: LocalSponsorObservationDecisionStore) -> None:
        if (type(store) is not LocalObservationResearchLedgerStore
                or type(decisions) is not LocalSponsorObservationDecisionStore):
            raise TypeError("OBSERVATION_RESEARCH_SERVICE_INPUT_INVALID")
        self.store = store
        self.decisions = decisions

    def retain_observation(self, result: SponsorObservationDecisionResult) -> ObservationResearchRecordV1:
        values = dict(
            record_identity="OBSERVATION-RESEARCH-" + sha256(
                result.decision.decision_identity.encode("utf-8")
            ).hexdigest(),
            snapshot_identity=result.snapshot.snapshot_identity,
            snapshot_sha256=result.snapshot.integrity_sha256,
            decision_identity=result.decision.decision_identity,
            decision_sha256=result.decision.integrity_sha256,
            activation_identity=result.activation.disposition_identity,
            activation_sha256=result.activation.integrity_sha256,
            native_run_identity=result.snapshot.native_run_identity,
            canonical_instrument=result.snapshot.canonical_instrument,
            native_assessment_sha256=result.snapshot.native_assessment_sha256,
            choice=result.decision.choice,
            activation_disposition=result.activation.disposition,
            decision_timestamp=result.decision.decision_timestamp,
            integrity_sha256="",
        )
        record = ObservationResearchRecordV1(**(
            values | {"integrity_sha256": _values_digest(values)}
        ))
        return self.store.retain_record(record)

    def append_link(self, decision_identity: str, *, kind: ObservationLinkKind,
                    source_contract_identity: str, source_contract_version: str,
                    source_record_identity: str, source_integrity_sha256: str,
                    source_state: str, source_timestamp: datetime,
                    native_run_identity: str, canonical_instrument: str,
                    native_assessment_sha256: str,
                    trade_plan_identity: str | None,
                    trade_plan_sha256: str | None,
                    sponsor_position_identity: str | None = None,
                    ) -> ObservationResearchLinkV1:
        projection = self._projection_for_decision(decision_identity)
        source = projection.source
        snapshot = source.snapshot
        if (
            native_run_identity != snapshot.native_run_identity
            or canonical_instrument != snapshot.canonical_instrument
            or native_assessment_sha256 != snapshot.native_assessment_sha256
            or trade_plan_identity != snapshot.conventional_trade_plan_identity
            or trade_plan_sha256 != snapshot.conventional_trade_plan_sha256
        ):
            raise ValueError("OBSERVATION_RESEARCH_LINK_BINDING_INVALID")
        _validate_kind(kind, source, source_contract_identity, source_contract_version,
                       source_state, sponsor_position_identity)
        values = dict(
            link_identity="OBSERVATION-LINK-" + sha256("|".join((
                projection.record.record_identity, kind.value,
                source_record_identity, source_integrity_sha256,
            )).encode("utf-8")).hexdigest(),
            record_identity=projection.record.record_identity,
            kind=kind,
            native_run_identity=native_run_identity,
            canonical_instrument=canonical_instrument,
            native_assessment_sha256=native_assessment_sha256,
            trade_plan_identity=trade_plan_identity,
            trade_plan_sha256=trade_plan_sha256,
            source_contract_identity=source_contract_identity,
            source_contract_version=source_contract_version,
            source_record_identity=source_record_identity,
            source_integrity_sha256=source_integrity_sha256,
            source_state=source_state,
            source_timestamp=source_timestamp,
            sponsor_position_identity=sponsor_position_identity,
            integrity_sha256="",
        )
        link = ObservationResearchLinkV1(**(
            values | {"integrity_sha256": _values_digest(values)}
        ))
        existing = tuple(
            item for item in self.store.load_links()
            if item.record_identity == link.record_identity
            and item.kind is link.kind
            and link.kind in {
                ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME,
                ObservationLinkKind.SPONSOR_POSITION_OUTCOME,
            }
        )
        if existing and existing != (link,):
            raise ValueError("OBSERVATION_RESEARCH_DUPLICATE_OR_CORRUPT_LINK")
        return self.store.retain_link(link)

    def snapshot(self, query: ObservationResearchQueryV1 | None = None) -> tuple[ObservationResearchProjectionV1, ...]:
        query = query or ObservationResearchQueryV1()
        records = self.store.load_records()
        links = self.store.load_links()
        projections = tuple(self._projection(item, links) for item in records)
        filtered = tuple(item for item in projections if _matches(item, query))
        return tuple(sorted(filtered, key=lambda item: (
            -item.record.decision_timestamp.timestamp(), item.record.record_identity
        )))

    def export_json(self, query: ObservationResearchQueryV1 | None = None) -> str:
        return json.dumps({
            "schema": "KRONOS-SWING-OBSERVATION-RESEARCH-EXPORT-V1",
            "authority": OBSERVATION_RESEARCH_AUTHORITY,
            "records": [_export_row(item) for item in self.snapshot(query)],
        }, sort_keys=True, separators=(",", ":")) + "\n"

    def export_csv(self, query: ObservationResearchQueryV1 | None = None) -> str:
        target = io.StringIO()
        fields = tuple(_export_row_fields())
        writer = csv.DictWriter(target, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in self.snapshot(query):
            writer.writerow(_export_row(item))
        return target.getvalue()

    def _projection_for_decision(self, decision_identity: str) -> ObservationResearchProjectionV1:
        matches = tuple(item for item in self.snapshot()
                        if item.record.decision_identity == decision_identity)
        if len(matches) != 1:
            raise ValueError("OBSERVATION_RESEARCH_DECISION_NOT_FOUND")
        return matches[0]

    def _projection(self, record: ObservationResearchRecordV1,
                    links: tuple[ObservationResearchLinkV1, ...]) -> ObservationResearchProjectionV1:
        matches = tuple(item for item in self.decisions.load_all()
                        if item.decision.decision_identity == record.decision_identity)
        if len(matches) != 1 or not _record_binding(record, matches[0]):
            raise ValueError("OBSERVATION_RESEARCH_SOURCE_BINDING_INVALID")
        bound = tuple(sorted(
            (item for item in links if item.record_identity == record.record_identity),
            key=lambda item: (item.source_timestamp, item.link_identity),
        ))
        return ObservationResearchProjectionV1(record, matches[0], bound)


def _record_binding(record: ObservationResearchRecordV1,
                    source: SponsorObservationDecisionResult) -> bool:
    return (
        record.snapshot_identity == source.snapshot.snapshot_identity
        and record.snapshot_sha256 == source.snapshot.integrity_sha256
        and record.decision_sha256 == source.decision.integrity_sha256
        and record.activation_identity == source.activation.disposition_identity
        and record.activation_sha256 == source.activation.integrity_sha256
        and record.native_run_identity == source.snapshot.native_run_identity
        and record.canonical_instrument == source.snapshot.canonical_instrument
        and record.native_assessment_sha256 == source.snapshot.native_assessment_sha256
        and record.choice is source.decision.choice
        and record.activation_disposition is source.activation.disposition
        and record.decision_timestamp == source.decision.decision_timestamp
    )


def _validate_kind(kind: ObservationLinkKind, source: SponsorObservationDecisionResult,
                   contract: str, version: str, state: str,
                   position: str | None) -> None:
    allowed = {
        ObservationLinkKind.KR380_ENTRY_OUTCOME: ("KRONOS-KR-380-ENTRY-OUTCOME-V2", "2"),
        ObservationLinkKind.KR390_OBJECTIVE_MODEL: ("KRONOS-SWING-OBJECTIVE-MODEL-TRADE-V1", "1"),
        ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME: ("KRONOS-SWING-OBJECTIVE-MODEL-TRADE-V1", "1"),
        ObservationLinkKind.SPONSOR_POSITION: ("KRONOS-SWING-V1-SPONSOR-POSITION-V0", "0"),
        ObservationLinkKind.SPONSOR_POSITION_OUTCOME: ("KRONOS-SWING-V1-TRADE-CLOSURE-V1", "1"),
    }
    if allowed[kind] != (contract, version):
        raise ValueError("OBSERVATION_RESEARCH_LINK_CONTRACT_INVALID")
    if (
        kind is ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME
        and state not in {"CLOSED", "MODEL_TRADE_CLOSED"}
    ):
        raise ValueError("OBSERVATION_RESEARCH_OBJECTIVE_OUTCOME_INVALID")
    if kind in {ObservationLinkKind.SPONSOR_POSITION,
                ObservationLinkKind.SPONSOR_POSITION_OUTCOME}:
        expected = source.activation.sponsor_position_identity
        if expected is None or position != expected:
            raise ValueError("OBSERVATION_RESEARCH_POSITION_BINDING_INVALID")
    elif position is not None:
        raise ValueError("OBSERVATION_RESEARCH_POSITION_BINDING_INVALID")


def _matches(item: ObservationResearchProjectionV1,
             query: ObservationResearchQueryV1) -> bool:
    source = item.source
    return (
        (not query.choices or source.decision.choice in query.choices)
        and (not query.dispositions or source.activation.disposition in query.dispositions)
        and (not query.severities or source.snapshot.step31_severity in query.severities)
        and (not query.kr370_states or source.snapshot.kr370_state in query.kr370_states)
        and (not query.risk_states or source.snapshot.risk_state in query.risk_states)
        and (query.objective_outcome_available is None
             or item.objective_outcome_available is query.objective_outcome_available)
        and (query.sponsor_position_outcome_available is None
             or item.sponsor_position_outcome_available is query.sponsor_position_outcome_available)
    )


def _export_row_fields() -> tuple[str, ...]:
    return (
        "record_identity", "decision_identity", "decision_timestamp",
        "native_run_identity", "canonical_instrument", "native_assessment_sha256",
        "choice", "sponsor_reason", "activation_disposition", "direction",
        "kr370_state", "kr370_criteria", "step31_severity", "step31_warnings",
        "entry", "stop", "target", "risk_reward_ratio", "risk_state",
        "objective_kr380_state", "objective_kr390_identity",
        "objective_kr390_state", "objective_outcome",
        "objective_outcome_available", "sponsor_position_identity",
        "sponsor_position_outcome", "sponsor_position_outcome_available",
        "mcx_supporting_context_identity", "link_identities",
    )


def _export_row(item: ObservationResearchProjectionV1) -> dict[str, object]:
    source = item.source
    snapshot = source.snapshot
    kr380 = tuple(
        link for link in item.links
        if link.kind is ObservationLinkKind.KR380_ENTRY_OUTCOME
    )
    model = tuple(
        link for link in item.links
        if link.kind in {
            ObservationLinkKind.KR390_OBJECTIVE_MODEL,
            ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME,
        }
    )
    objective_outcome = tuple(
        link for link in item.links
        if link.kind is ObservationLinkKind.OBJECTIVE_MODEL_OUTCOME
    )
    position_outcome = tuple(
        link for link in item.links
        if link.kind is ObservationLinkKind.SPONSOR_POSITION_OUTCOME
    )
    latest_kr380 = None if not kr380 else kr380[-1]
    latest_model = None if not model else model[-1]
    latest_objective_outcome = None if not objective_outcome else objective_outcome[-1]
    latest_position_outcome = None if not position_outcome else position_outcome[-1]
    return {
        "record_identity": item.record.record_identity,
        "decision_identity": item.record.decision_identity,
        "decision_timestamp": item.record.decision_timestamp.isoformat(),
        "native_run_identity": item.record.native_run_identity,
        "canonical_instrument": item.record.canonical_instrument,
        "native_assessment_sha256": item.record.native_assessment_sha256,
        "choice": item.record.choice.value,
        "sponsor_reason": (
            "UNAVAILABLE" if source.decision.sponsor_reason is None
            else source.decision.sponsor_reason.value
        ),
        "activation_disposition": item.record.activation_disposition.value,
        "direction": snapshot.direction.value,
        "kr370_state": snapshot.kr370_state,
        "kr370_criteria": "|".join(
            identity + "=" + state for identity, state in snapshot.kr370_criteria
        ),
        "step31_severity": snapshot.step31_severity.value,
        "step31_warnings": "|".join(snapshot.step31_warnings) or "NONE",
        "entry": "UNAVAILABLE" if snapshot.entry is None else str(snapshot.entry),
        "stop": "UNAVAILABLE" if snapshot.stop is None else str(snapshot.stop),
        "target": "UNAVAILABLE" if snapshot.target is None else str(snapshot.target),
        "risk_reward_ratio": (
            "UNAVAILABLE" if snapshot.risk_reward_ratio is None
            else str(snapshot.risk_reward_ratio)
        ),
        "risk_state": snapshot.risk_state,
        "objective_kr380_state": (
            "UNAVAILABLE" if latest_kr380 is None else latest_kr380.source_state
        ),
        "objective_kr390_identity": (
            "UNAVAILABLE" if latest_model is None else latest_model.source_record_identity
        ),
        "objective_kr390_state": (
            "UNAVAILABLE" if latest_model is None else latest_model.source_state
        ),
        "objective_outcome": (
            "UNAVAILABLE" if latest_objective_outcome is None
            else latest_objective_outcome.source_state
        ),
        "objective_outcome_available": (
            "AVAILABLE" if item.objective_outcome_available else "UNAVAILABLE"
        ),
        "sponsor_position_identity": source.activation.sponsor_position_identity or "UNAVAILABLE",
        "sponsor_position_outcome": (
            "UNAVAILABLE" if latest_position_outcome is None
            else latest_position_outcome.source_state
        ),
        "sponsor_position_outcome_available": (
            "AVAILABLE" if item.sponsor_position_outcome_available else "UNAVAILABLE"
        ),
        "mcx_supporting_context_identity": (
            snapshot.mcx_supporting_context_identity or "NOT_APPLICABLE_OR_UNAVAILABLE"
        ),
        "link_identities": "|".join(link.link_identity for link in item.links) or "UNAVAILABLE",
    }


def _atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _primitive(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
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
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _values_digest(values: dict[str, object]) -> str:
    return sha256(json.dumps(_primitive(values), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _identity(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:@|+/-]{1,512}", value) is not None


def _digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "LocalObservationResearchLedgerStore", "OBSERVATION_RESEARCH_AUTHORITY",
    "OBSERVATION_RESEARCH_CONTRACT_ID", "ObservationLinkKind",
    "ObservationResearchLedgerService", "ObservationResearchLinkV1",
    "ObservationResearchProjectionV1", "ObservationResearchQueryV1",
    "ObservationResearchRecordV1",
]
