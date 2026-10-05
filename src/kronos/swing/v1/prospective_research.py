"""Prospective Swing direction research; no trading or publication authority."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
from zoneinfo import ZoneInfo


CONTRACT = "KRONOS-SWING-PROSPECTIVE-RESEARCH-V1"
VERSION = "1"
MARKETS = frozenset({"NSE", "GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS"})
HORIZONS = (1, 3, 5, 10)
TRUTH_CLASSES = frozenset({"OBJECTIVE_MODEL", "PAPER_OBSERVATION", "PAPER_POSITION", "LIVE_SPONSOR"})
IST = ZoneInfo("Asia/Kolkata")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _price(value: str | None) -> bool:
    if value is None:
        return True
    try:
        amount = Decimal(value)
    except (TypeError, ValueError, ArithmeticError):
        return False
    return amount.is_finite() and amount > 0


def _signed_amount(value: str | None) -> bool:
    if value is None:
        return True
    try:
        return Decimal(value).is_finite()
    except (TypeError, ValueError, ArithmeticError):
        return False


def _identity(value: str) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_.:/+ &-]{1,200}", value))


@dataclass(frozen=True, slots=True)
class Record:
    schema: str
    identity: str
    data: dict
    integrity_sha256: str

    def __post_init__(self) -> None:
        if (not re.fullmatch(r"SWING_WO12_[A-Z_]+_V1", self.schema)
                or self.identity != self.schema + "-" + self.integrity_sha256
                or self.integrity_sha256 != _digest({"schema": self.schema, "data": self.data})
                or self.data.get("contract_identity") != CONTRACT
                or self.data.get("contract_version") != VERSION):
            raise ValueError("SWING_WO12_RECORD_INVALID")


def record(kind: str, **data: object) -> Record:
    schema = "SWING_WO12_" + kind + "_V1"
    value = {"contract_identity": CONTRACT, "contract_version": VERSION, **data}
    digest = _digest({"schema": schema, "data": value})
    return Record(schema, schema + "-" + digest, value, digest)


def origin(*, continuity_identity: str, market: str, instrument: str,
           contract_identity: str, expiry: date | None, direction: str,
           admitted_at: datetime, source_identity: str, source_version: str,
           source_sha256: str, origin_run_identity: str,
           origin_assessment_sha256: str, native_setup_identity: str,
           contract_binding: dict[str, str | None] | None = None,
           reference_price: str | None = None,
           price_observation_identity: str | None = None,
           price_observed_at: datetime | None = None,
           price_received_at: datetime | None = None,
           price_source: str | None = None) -> Record:
    """One owner-admitted continuity instance, including non-progressors."""
    if (not all(_identity(v) for v in (continuity_identity, instrument,
                                      contract_identity, source_identity, source_version))
            or market not in MARKETS or direction not in {"LONG", "SHORT"}
            or not _aware(admitted_at)
            or not _identity(origin_run_identity) or not _identity(native_setup_identity)
            or not re.fullmatch(r"[a-f0-9]{64}", source_sha256)
            or not re.fullmatch(r"[a-f0-9]{64}", origin_assessment_sha256)
            or (market != "NSE" and expiry is None)
            or (expiry is not None and expiry < admitted_at.astimezone(IST).date())
            or not _price(reference_price)):
        raise ValueError("SWING_WO12_ORIGIN_INVALID")
    if contract_binding is not None:
        expected = {"canonical_instrument", "exchange", "provider", "segment",
                    "trading_symbol", "instrument_type", "expiry"}
        if (type(contract_binding) is not dict or set(contract_binding) != expected
                or contract_binding["canonical_instrument"] != instrument
                or contract_binding["exchange"] != ("NSE" if market == "NSE" else "MCX")
                or contract_binding["expiry"] != (None if expiry is None else expiry.isoformat())
                or any(not isinstance(contract_binding[key], str) or not contract_binding[key]
                       for key in expected - {"expiry"})):
            raise ValueError("SWING_WO12_CONTRACT_BINDING_INVALID")
    if reference_price is not None:
        if (not _identity(price_observation_identity) or not _identity(price_source)
                or not _aware(price_observed_at) or not _aware(price_received_at)
                or price_observed_at > admitted_at or price_received_at < price_observed_at
                or price_received_at > admitted_at):
            raise ValueError("SWING_WO12_ORIGIN_PRICE_BINDING_INVALID")
    elif any(value is not None for value in (price_observation_identity,
                                             price_observed_at, price_received_at, price_source)):
        raise ValueError("SWING_WO12_ORIGIN_PRICE_BINDING_INVALID")
    return record("ORIGIN", opportunity_identity=continuity_identity, market=market,
                  instrument=instrument, exact_contract_identity=contract_identity,
                  expiry=None if expiry is None else expiry.isoformat(), direction=direction,
                  admitted_at=admitted_at.isoformat(), origin_month=admitted_at.astimezone(IST).strftime("%Y_%m"),
                  source_identity=source_identity, source_version=source_version,
                  source_sha256=source_sha256,
                  contract_binding=contract_binding,
                  origin_run_identity=origin_run_identity,
                  origin_assessment_sha256=origin_assessment_sha256,
                  native_setup_identity=native_setup_identity,
                  reference_price=reference_price,
                  price_observation_identity=price_observation_identity,
                  price_observed_at=None if price_observed_at is None else price_observed_at.isoformat(),
                  price_received_at=None if price_received_at is None else price_received_at.isoformat(),
                  price_source=price_source, authority="RESEARCH_ONLY")


def milestone_from_v2_promotion(source: Record, promotion: object, *,
                                reference_price: str | None = None,
                                price_observation_identity: str | None = None,
                                price_observed_at: datetime | None = None,
                                price_received_at: datetime | None = None,
                                price_source: str | None = None) -> Record | None:
    """Adapt only an exact validated Swing KR-370 V2 owner record."""
    from kronos.swing.v1.analytical_promotion_v2 import V2PromotionRecord

    if source.schema != "SWING_WO12_ORIGIN_V1" or type(promotion) is not V2PromotionRecord:
        raise ValueError("SWING_WO12_V2_PROMOTION_REQUIRED")
    value = promotion.value
    factual = value["source"]
    if (factual["canonical_instrument"] != source.data["instrument"]
            or factual["direction"] != source.data["direction"]
            or factual["native_opportunity_identity"] != source.data["native_setup_identity"]
            or factual["market"] != ("NSE" if source.data["market"] == "NSE" else "MCX")):
        raise ValueError("SWING_WO12_PROMOTION_SOURCE_MISMATCH")
    count = value["satisfied_count"]
    if value["evaluation_disposition"] != "EVALUATED" or count not in {4, 5}:
        return None
    analytical_at = datetime.fromisoformat(factual["analysis_boundary"].replace("Z", "+00:00"))
    at = datetime.fromisoformat(value["created_at"].replace("Z", "+00:00"))
    return milestone(source, count=count, readiness_state=value["promotion_state"],
                     source_identity=promotion.identity,
                     source_version=value["contract_version"],
                     source_sha256=value["integrity_sha256"],
                     occurred_at=at, analytical_at=analytical_at,
                     reference_price=reference_price,
                     price_observation_identity=price_observation_identity,
                     price_observed_at=price_observed_at,
                     price_received_at=price_received_at,
                     price_source=price_source)


def milestone(source: Record, *, count: int, readiness_state: str,
              source_identity: str, source_version: str, source_sha256: str,
              occurred_at: datetime, analytical_at: datetime | None = None,
              reference_price: str | None = None,
              price_observation_identity: str | None = None,
              price_observed_at: datetime | None = None,
              price_received_at: datetime | None = None,
              price_source: str | None = None) -> Record:
    if source.schema != "SWING_WO12_ORIGIN_V1" or count not in {4, 5}:
        raise ValueError("SWING_WO12_MILESTONE_INVALID")
    if (not _aware(occurred_at) or occurred_at < datetime.fromisoformat(source.data["admitted_at"])
            or (analytical_at is not None and (not _aware(analytical_at) or analytical_at > occurred_at))
            or not _identity(readiness_state) or not _identity(source_identity)
            or not _identity(source_version) or not re.fullmatch(r"[a-f0-9]{64}", source_sha256)
            or not _price(reference_price)):
        raise ValueError("SWING_WO12_MILESTONE_INVALID")
    if reference_price is not None:
        if (not _identity(price_observation_identity) or not _identity(price_source)
                or not _aware(price_observed_at) or not _aware(price_received_at)
                or price_observed_at > occurred_at or price_received_at < price_observed_at
                or price_received_at > occurred_at):
            raise ValueError("SWING_WO12_MILESTONE_PRICE_BINDING_INVALID")
    elif any(v is not None for v in (price_observation_identity, price_observed_at,
                                     price_received_at, price_source)):
        raise ValueError("SWING_WO12_MILESTONE_PRICE_BINDING_INVALID")
    return record("MILESTONE", opportunity_identity=source.data["opportunity_identity"],
                  origin_identity=source.identity, market=source.data["market"],
                  exact_contract_identity=source.data["exact_contract_identity"],
                  direction=source.data["direction"], score=count,
                  readiness_state=readiness_state, source_identity=source_identity,
                  source_version=source_version, source_sha256=source_sha256,
                  occurred_at=occurred_at.isoformat(),
                  analytical_at=None if analytical_at is None else analytical_at.isoformat(),
                  reference_price=reference_price,
                  price_observation_identity=price_observation_identity,
                  price_observed_at=None if price_observed_at is None else price_observed_at.isoformat(),
                  price_received_at=None if price_received_at is None else price_received_at.isoformat(),
                  price_source=price_source, authority="RESEARCH_ONLY")


def decision(source: Record, *, choice: str, activation_disposition: str,
             source_identity: str, decided_at: datetime) -> Record:
    if (source.schema != "SWING_WO12_ORIGIN_V1" or choice not in {"LIVE", "PAPER", "IGNORE"}
            or not _identity(activation_disposition)
            or (choice == "IGNORE" and activation_disposition != "NOT_APPLICABLE_IGNORE")
            or (choice != "IGNORE" and activation_disposition == "NOT_APPLICABLE_IGNORE")
            or not _identity(source_identity) or not _aware(decided_at)
            or decided_at < datetime.fromisoformat(source.data["admitted_at"])):
        raise ValueError("SWING_WO12_DECISION_INVALID")
    return record("DECISION", opportunity_identity=source.data["opportunity_identity"],
                  origin_identity=source.identity, choice=choice,
                  activation_disposition=activation_disposition,
                  source_identity=source_identity, decided_at=decided_at.isoformat(),
                  authority="RESEARCH_ONLY")


def lifecycle_track(source: Record, *, truth_class: str, track_identity: str,
                    state: str, source_event_identity: str, source_version: str,
                    observed_at: datetime, entry_price: str | None = None,
                    exit_price: str | None = None, gross_pnl: str | None = None,
                    sponsor_attested: bool = False) -> Record:
    """Link only an already-governed lifecycle fact; never calculate a fill."""
    if (source.schema != "SWING_WO12_ORIGIN_V1" or truth_class not in TRUTH_CLASSES
            or not all(_identity(v) for v in (track_identity, state, source_event_identity, source_version))
            or not _aware(observed_at) or observed_at < datetime.fromisoformat(source.data["admitted_at"])
            or type(sponsor_attested) is not bool
            or any(v is not None and not _price(v) for v in (entry_price, exit_price))
            or not _signed_amount(gross_pnl)
            or (exit_price is not None and entry_price is None)
            or (gross_pnl is not None and entry_price is None)
            or (state in {"NO_ENTRY", "PAPER_ARMED", "CANCELLED_BEFORE_ENTRY"}
                and any(v is not None for v in (entry_price, exit_price, gross_pnl)))
            or (truth_class in {"OBJECTIVE_MODEL", "PAPER_OBSERVATION"} and gross_pnl is not None)
            or (truth_class != "LIVE_SPONSOR" and sponsor_attested)
            or (truth_class == "LIVE_SPONSOR" and (entry_price is not None or exit_price is not None or gross_pnl is not None)
                and not sponsor_attested)):
        raise ValueError("SWING_WO12_LIFECYCLE_TRUTH_INVALID")
    return record("LIFECYCLE_TRACK", opportunity_identity=source.data["opportunity_identity"],
                  origin_identity=source.identity, truth_class=truth_class,
                  track_identity=track_identity, state=state,
                  source_event_identity=source_event_identity,
                  source_version=source_version, observed_at=observed_at.isoformat(),
                  entry_price=entry_price, exit_price=exit_price,
                  gross_pnl=gross_pnl, sponsor_attested=sponsor_attested,
                  authority="LINKED_FACT_ONLY_NO_NEW_ACCOUNTING")


@dataclass(frozen=True, slots=True)
class GovernedSession:
    identity: str
    market: str
    trading_date: date
    opens_at: datetime
    closes_at: datetime

    def __post_init__(self) -> None:
        if (not _identity(self.identity) or self.market not in MARKETS
                or not _aware(self.opens_at) or not _aware(self.closes_at)
                or self.opens_at >= self.closes_at
                or self.trading_date != self.opens_at.astimezone(IST).date()):
            raise ValueError("SWING_WO12_SESSION_INVALID")


@dataclass(frozen=True, slots=True)
class GovernedCalendar:
    """Owner-attested complete session sequence through a governed date."""

    market: str
    source_identity: str
    source_version: str
    observed_at: datetime
    complete_from: date
    complete_through: date
    sessions: tuple[GovernedSession, ...]

    def __post_init__(self) -> None:
        if (self.market not in MARKETS
                or not _identity(self.source_identity) or not _identity(self.source_version)
                or not _aware(self.observed_at)
                or not isinstance(self.complete_from, date)
                or not isinstance(self.complete_through, date)
                or self.complete_from > self.complete_through
                or type(self.sessions) is not tuple
                or any(type(item) is not GovernedSession or item.market != self.market
                       or item.trading_date < self.complete_from for item in self.sessions)
                or tuple(sorted(self.sessions, key=lambda item: item.opens_at)) != self.sessions
                or len({item.identity for item in self.sessions}) != len(self.sessions)
                or len({item.trading_date for item in self.sessions}) != len(self.sessions)):
            raise ValueError("SWING_WO12_CALENDAR_INVALID")


def calendar_record(value: GovernedCalendar) -> Record:
    return record("CALENDAR", market=value.market,
                  source_identity=value.source_identity,
                  source_version=value.source_version,
                  observed_at=value.observed_at.isoformat(),
                  complete_from=value.complete_from.isoformat(),
                  complete_through=value.complete_through.isoformat(),
                  sessions=[(item.identity, item.trading_date.isoformat(),
                             item.opens_at.isoformat(), item.closes_at.isoformat())
                            for item in value.sessions],
                  authority="GOVERNED_CALENDAR_SEQUENCE")


@dataclass(frozen=True, slots=True)
class FollowupCandle:
    exact_contract_identity: str
    session_identity: str
    source_identity: str
    source_version: str
    retrieved_at: datetime
    close: str
    high: str
    low: str
    coverage_complete: bool
    corporate_action: bool = False
    supersedes_source_identity: str | None = None
    revision_reason: str | None = None
    price_basis_verified: bool = True

    def __post_init__(self) -> None:
        if (not all(_identity(v) for v in (self.exact_contract_identity,
                                          self.session_identity, self.source_identity,
                                          self.source_version))
                or not _aware(self.retrieved_at)
                or not all(_price(v) and v is not None for v in (self.close, self.high, self.low))
                or not (Decimal(self.low) <= Decimal(self.close) <= Decimal(self.high))
                or type(self.coverage_complete) is not bool or type(self.corporate_action) is not bool
                or type(self.price_basis_verified) is not bool
                or (self.supersedes_source_identity is None) != (self.revision_reason is None)
                or (self.supersedes_source_identity is not None and
                    (not _identity(self.supersedes_source_identity) or not _identity(self.revision_reason)))):
            raise ValueError("SWING_WO12_CANDLE_INVALID")


def candle_record(value: FollowupCandle) -> Record:
    return record("CANDLE", exact_contract_identity=value.exact_contract_identity,
                  session_identity=value.session_identity,
                  source_identity=value.source_identity,
                  source_version=value.source_version,
                  retrieved_at=value.retrieved_at.isoformat(), close=value.close,
                  high=value.high, low=value.low,
                  coverage_complete=value.coverage_complete,
                  corporate_action=value.corporate_action,
                  price_basis_verified=value.price_basis_verified,
                  supersedes_source_identity=value.supersedes_source_identity,
                  revision_reason=value.revision_reason, authority="RESEARCH_ONLY")


def evaluate(m: Record, o: Record, *, horizon: int,
             sessions: tuple[GovernedSession, ...], candles: dict[str, Record],
             as_of: datetime, equity_basis_state: str | None = None,
             equity_basis_identity: str | None = None) -> Record:
    """Count completed governed sessions after the milestone's IST trading day."""
    if (m.schema != "SWING_WO12_MILESTONE_V1" or o.identity != m.data["origin_identity"]
            or horizon not in HORIZONS or not _aware(as_of)
            or equity_basis_state not in {None, "UNKNOWN", "AFFECTED", "VERIFIED_NO_ACTION"}):
        raise ValueError("SWING_WO12_CHECKPOINT_INVALID")
    occurred = datetime.fromisoformat(m.data["occurred_at"])
    subsequent = tuple(s for s in sessions if s.trading_date > occurred.astimezone(IST).date())
    if (len({s.identity for s in sessions}) != len(sessions)
            or tuple(sorted(sessions, key=lambda s: s.opens_at)) != sessions
            or any(s.market != o.data["market"] for s in sessions)
            or len({s.trading_date for s in sessions}) != len(sessions)):
        raise ValueError("SWING_WO12_SESSION_SEQUENCE_INVALID")
    due = subsequent[horizon - 1] if len(subsequent) >= horizon else None
    expiry = None if o.data["expiry"] is None else date.fromisoformat(o.data["expiry"])
    status = "PENDING"
    reason = "HORIZON_NOT_YET_SCHEDULED"
    close = raw = adjusted = favourable = adverse = None
    source_ids: list[str] = []
    if expiry is not None and (due is None and sessions and sessions[-1].trading_date >= expiry
                               or due is not None and due.trading_date > expiry):
        status, reason = "EXPIRY_LIMITED", "EXACT_CONTRACT_EXPIRES_BEFORE_HORIZON"
    elif due is not None and due.closes_at <= as_of:
        window = subsequent[:horizon]
        available = [candles.get(s.identity) for s in window]
        if m.data["reference_price"] is None:
            status, reason = "UNAVAILABLE", "MILESTONE_REFERENCE_PRICE_MISSING"
        elif any(item is None for item in available):
            status, reason = "UNAVAILABLE", "COMPLETED_SESSION_CANDLE_MISSING"
        elif any(item.data["exact_contract_identity"] != o.data["exact_contract_identity"]
                 or item.data["session_identity"] != s.identity
                 for s, item in zip(window, available, strict=True)):
            raise ValueError("SWING_WO12_CANDLE_BINDING_INVALID")
        elif o.data["market"] == "NSE" and any(item.data["corporate_action"] for item in available):
            status, reason = "UNAVAILABLE", "CORPORATE_ACTION_BASIS_UNAVAILABLE"
        elif equity_basis_state == "AFFECTED":
            status, reason = "UNAVAILABLE", "CORPORATE_ACTION_BASIS_UNAVAILABLE"
        elif equity_basis_state == "UNKNOWN":
            status, reason = "UNAVAILABLE", "PRICE_BASIS_EVIDENCE_UNAVAILABLE"
        elif equity_basis_state != "VERIFIED_NO_ACTION" and not all(
                item.data.get("price_basis_verified", True) for item in available):
            status, reason = "UNAVAILABLE", "PRICE_BASIS_UNVERIFIED"
        elif not all(item.data["coverage_complete"] and
                     datetime.fromisoformat(item.data["retrieved_at"]) >= session.closes_at
                     for session, item in zip(window, available, strict=True)):
            status, reason = "UNAVAILABLE", "CANDLE_INTERVAL_COVERAGE_INCOMPLETE"
        else:
            reference = Decimal(m.data["reference_price"])
            close_value = Decimal(available[-1].data["close"])
            change = (close_value / reference - 1) * 100
            direction = 1 if m.data["direction"] == "LONG" else -1
            adjusted_value = change * direction
            high = max(Decimal(item.data["high"]) for item in available)
            low = min(Decimal(item.data["low"]) for item in available)
            favourable_value = (high / reference - 1) * 100 if direction == 1 else (1 - low / reference) * 100
            adverse_value = (1 - low / reference) * 100 if direction == 1 else (high / reference - 1) * 100
            status = "WITH_PREDICTION" if adjusted_value > 0 else "AGAINST_PREDICTION" if adjusted_value < 0 else "UNCHANGED"
            reason = "COMPLETED_COVERED_SESSIONS"
            close, raw, adjusted = str(close_value), str(change), str(adjusted_value)
            favourable, adverse = str(max(Decimal(0), favourable_value)), str(max(Decimal(0), adverse_value))
            source_ids = [item.data["source_identity"] for item in available]
    elif due is not None:
        reason = "DUE_SESSION_NOT_COMPLETE"
    return record("CHECKPOINT", milestone_identity=m.identity,
                  opportunity_identity=o.data["opportunity_identity"],
                  market=o.data["market"], direction=m.data["direction"],
                  score=m.data["score"], horizon=horizon, status=status,
                  reason=reason, due_session_identity=None if due is None else due.identity,
                  due_trading_date=None if due is None else due.trading_date.isoformat(),
                  actual_close=close, raw_pct=raw, direction_adjusted_pct=adjusted,
                  candle_excursion_favourable_pct=favourable,
                  candle_excursion_adverse_pct=adverse,
                  excursion_authority="CANDLE_RESEARCH_NOT_LIFECYCLE_MFE_MAE",
                  candle_source_identities=source_ids,
                  equity_basis_state=equity_basis_state,
                  equity_basis_identity=equity_basis_identity,
                  authority="RESEARCH_ONLY")


class ProspectiveResearchStore:
    """Compact immutable facts and atomic current pointers in a distinct V1 root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        if not self.root.is_absolute():
            raise ValueError("SWING_WO12_STORE_ROOT_INVALID")

    @contextmanager
    def transaction(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / ".operation.lock").open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("SWING_WO12_UPDATE_BUSY") from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def retain(self, value: Record) -> Record:
        value.__post_init__()
        target = self.root / "records" / value.schema / (value.identity + ".json")
        payload = _canonical({"schema": value.schema, "identity": value.identity,
                              "data": value.data, "integrity_sha256": value.integrity_sha256}) + b"\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=target.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if target.read_bytes() != payload:
                    raise ValueError("SWING_WO12_IMMUTABLE_CONFLICT") from None
        finally:
            os.unlink(temporary)
        _fsync_dir(target.parent)
        return value

    def records(self, kind: str) -> tuple[Record, ...]:
        schema = "SWING_WO12_" + kind + "_V1"
        directory = self.root / "records" / schema
        if not directory.exists():
            return ()
        values = []
        for path in sorted(directory.glob("*.json")):
            value = Record(**json.loads(path.read_bytes()))
            if value.identity != path.stem:
                raise ValueError("SWING_WO12_RECORD_PATH_INVALID")
            values.append(value)
        return tuple(values)

    def origins(self) -> tuple[Record, ...]:
        return self.records("ORIGIN")

    def retain_origin(self, value: Record) -> Record:
        if value.schema != "SWING_WO12_ORIGIN_V1":
            raise ValueError("SWING_WO12_ORIGIN_REQUIRED")
        prior = [o for o in self.origins() if o.data["opportunity_identity"] == value.data["opportunity_identity"]]
        if prior:
            if len(prior) != 1 or prior[0] != value:
                raise ValueError("SWING_WO12_ORIGIN_IDENTITY_CONFLICT")
            return prior[0]
        return self.retain(value)

    def retain_milestone(self, value: Record) -> Record:
        if value.schema != "SWING_WO12_MILESTONE_V1":
            raise ValueError("SWING_WO12_MILESTONE_REQUIRED")
        origin_matches = [o for o in self.origins() if o.identity == value.data["origin_identity"]]
        if len(origin_matches) != 1:
            raise ValueError("SWING_WO12_ORIGIN_MISSING")
        prior = [m for m in self.records("MILESTONE")
                 if m.data["origin_identity"] == value.data["origin_identity"]
                 and m.data["score"] == value.data["score"]]
        if prior:
            first = prior[0]
            if datetime.fromisoformat(value.data["occurred_at"]) < datetime.fromisoformat(first.data["occurred_at"]):
                raise ValueError("SWING_WO12_EARLIER_MILESTONE_REQUIRES_REVISION")
            return first
        earlier = [m for m in self.records("MILESTONE")
                   if m.data["origin_identity"] == value.data["origin_identity"]
                   and m.data["score"] == 5]
        if value.data["score"] == 4 and earlier:
            raise ValueError("SWING_WO12_LATE_FOUR_MILESTONE_INVALID")
        if value.data["score"] == 5:
            fours = [m for m in self.records("MILESTONE")
                     if m.data["origin_identity"] == value.data["origin_identity"]
                     and m.data["score"] == 4]
            if fours and datetime.fromisoformat(value.data["occurred_at"]) < datetime.fromisoformat(fours[0].data["occurred_at"]):
                raise ValueError("SWING_WO12_FIVE_PRECEDES_FOUR_INVALID")
        return self.retain(value)

    def retain_decision(self, value: Record) -> Record:
        if value.schema != "SWING_WO12_DECISION_V1":
            raise ValueError("SWING_WO12_DECISION_REQUIRED")
        if not any(o.identity == value.data["origin_identity"] for o in self.origins()):
            raise ValueError("SWING_WO12_ORIGIN_MISSING")
        prior = [d for d in self.records("DECISION") if d.data["origin_identity"] == value.data["origin_identity"]]
        if prior:
            if len(prior) != 1 or prior[0] != value:
                raise ValueError("SWING_WO12_DECISION_CONFLICT")
            return prior[0]
        return self.retain(value)

    def retain_candle(self, value: Record) -> Record:
        if value.schema != "SWING_WO12_CANDLE_V1":
            raise ValueError("SWING_WO12_CANDLE_REQUIRED")
        prior = [c for c in self.records("CANDLE")
                 if c.data["exact_contract_identity"] == value.data["exact_contract_identity"]
                 and c.data["session_identity"] == value.data["session_identity"]]
        if value in prior:
            return value
        if prior:
            latest = max(prior, key=lambda c: (c.data["retrieved_at"], c.identity))
            if (value.data["supersedes_source_identity"] != latest.data["source_identity"]
                    or value.data["source_identity"] == latest.data["source_identity"]
                    or value.data["revision_reason"] is None
                    or datetime.fromisoformat(value.data["retrieved_at"]) <=
                    datetime.fromisoformat(latest.data["retrieved_at"])):
                raise ValueError("SWING_WO12_CANDLE_REVISION_REQUIRES_OWNER_REVIEW")
        elif value.data["supersedes_source_identity"] is not None:
            raise ValueError("SWING_WO12_CANDLE_REVISION_SOURCE_MISSING")
        return self.retain(value)

    def retain_calendar(self, value: Record) -> Record:
        if value.schema != "SWING_WO12_CALENDAR_V1":
            raise ValueError("SWING_WO12_CALENDAR_REQUIRED")
        prior = [item for item in self.records("CALENDAR")
                 if item.data["market"] == value.data["market"]]
        for item in prior:
            if (item.data["source_identity"] == value.data["source_identity"]
                    and item.identity != value.identity):
                raise ValueError("SWING_WO12_CALENDAR_SOURCE_CONFLICT")
            overlap_end = min(item.data["complete_through"], value.data["complete_through"])
            overlap_start = max(item.data["complete_from"], value.data["complete_from"])
            if overlap_start <= overlap_end:
                previous = {row[1]: tuple(row) for row in item.data["sessions"]
                            if overlap_start <= row[1] <= overlap_end}
                candidate = {row[1]: tuple(row) for row in value.data["sessions"]
                             if overlap_start <= row[1] <= overlap_end}
                if previous != candidate:
                    raise ValueError("SWING_WO12_CALENDAR_HISTORY_CONFLICT")
        return self.retain(value)

    def current_candles(self) -> dict[tuple[str, str], Record]:
        current = {}
        for item in sorted(self.records("CANDLE"), key=lambda c: (c.data["retrieved_at"], c.identity)):
            key = (item.data["exact_contract_identity"], item.data["session_identity"])
            old = current.get(key)
            if old is None:
                if item.data["supersedes_source_identity"] is not None:
                    raise ValueError("SWING_WO12_CANDLE_REVISION_SOURCE_MISSING")
            elif (item.data["supersedes_source_identity"] != old.data["source_identity"]
                  or datetime.fromisoformat(item.data["retrieved_at"]) <=
                  datetime.fromisoformat(old.data["retrieved_at"])):
                raise ValueError("SWING_WO12_CANDLE_REVISION_CHAIN_INVALID")
            current[key] = item
        return current

    def retain_lifecycle_track(self, value: Record) -> Record:
        if value.schema != "SWING_WO12_LIFECYCLE_TRACK_V1":
            raise ValueError("SWING_WO12_LIFECYCLE_TRACK_REQUIRED")
        if not any(o.identity == value.data["origin_identity"] for o in self.origins()):
            raise ValueError("SWING_WO12_ORIGIN_MISSING")
        prior = [item for item in self.records("LIFECYCLE_TRACK")
                 if item.data["source_event_identity"] == value.data["source_event_identity"]]
        if prior:
            if len(prior) != 1 or prior[0] != value:
                raise ValueError("SWING_WO12_LIFECYCLE_EVENT_CONFLICT")
            return prior[0]
        return self.retain(value)

    def pointer(self, kind: str, key: str) -> Record | None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", key):
            raise ValueError("SWING_WO12_POINTER_KEY_INVALID")
        path = self.root / "current" / kind / (key + ".json")
        if not path.exists():
            return None
        value = Record(**json.loads(path.read_bytes()))
        if value not in self.records(kind):
            raise ValueError("SWING_WO12_POINTER_UNRETAINED")
        return value

    def publish_pointer(self, kind: str, key: str, value: Record) -> None:
        if value.schema != "SWING_WO12_" + kind + "_V1" or value not in self.records(kind):
            raise ValueError("SWING_WO12_POINTER_SOURCE_INVALID")
        path = self.root / "current" / kind / (key + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _canonical({"schema": value.schema, "identity": value.identity,
                              "data": value.data, "integrity_sha256": value.integrity_sha256}) + b"\n"
        descriptor, temporary = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            _fsync_dir(path.parent)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
