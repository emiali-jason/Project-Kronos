"""Pre-acquisition Swing MCX expiry choice; no entry commissioning authority.

The Sponsor choice is immutable for one analysis run and family.  A selected
contract can acquire its own candle history only after that choice is durable.
The current production analysis route is not wired to this preparatory path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from typing import Callable, TypeVar
from uuid import uuid4
from zoneinfo import ZoneInfo

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.v1.mcx_contract_profile import (
    McxFamily, McxSettlement, mcx_contract_name_matches,
)
from kronos.swing.v1.mcx_step31_prepared_handoff import McxStep31PreparedHandoff


SCHEMA = "KRONOS-SWING-MCX-SPONSOR-CONTRACT-SELECTION-V1"
TEN_CALENDAR_DAYS = 10
V1_ADVISORY_SELECTION = "MCX_V1_ADVISORY_SELECTION"
_IST = ZoneInfo("Asia/Kolkata")
_T = TypeVar("_T")


def _aware(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _instrument_value(instrument: InstrumentRecord) -> dict[str, object]:
    value = asdict(instrument)
    value["expiry"] = None if instrument.expiry is None else instrument.expiry.isoformat()
    value["tick_size"] = None if instrument.tick_size is None else str(instrument.tick_size)
    return value


def _hex(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _v1_expiry_session_reasons(
    family: McxFamily, expiry: date | None, observed_at: datetime,
) -> tuple[str, ...]:
    """Swing new-selection adapter; DOMAIN-008 candle semantics stay unchanged.

    Ordinary overnight closure cannot expire a later contract. On expiry day,
    use only the governed family/expiry boundary, never generic MCX hours. The
    close is exclusive for new selection even though a candle can complete at
    that exact boundary. This read acquires no business or Provider lock.
    """
    today = observed_at.astimezone(_IST).date()
    if expiry is None or today > expiry:
        return ("MCX_CONTRACT_EXPIRED",)
    if today < expiry:
        return ()
    from kronos.market.calendar import MarketCalendarPublisher

    try:
        profile = MarketCalendarPublisher().mcx_contract_session_profile(
            contract_family=family.value, contract_expiry=expiry,
            trading_date=today, observed_at=observed_at,
        )
    except (OSError, ValueError):
        return ("MCX_EXPIRY_SESSION_UNAVAILABLE",)
    if observed_at >= profile.expiry_eligibility_boundary:
        return ("MCX_EXPIRY_SESSION_CLOSED",)
    return ()


class McxSelectionRole(StrEnum):
    NEAR = "NEAR"
    NEXT_ELIGIBLE = "NEXT_ELIGIBLE"


@dataclass(frozen=True, slots=True)
class McxContractAdmissionFacts:
    """Caller-supplied proof references; absent values withhold selection."""

    family: McxFamily
    instrument: InstrumentRecord
    verified_expiry: date | None
    expiry_proof_sha256: str | None
    provider_snapshot_identity: str | None
    provider_record_identity: str | None
    master_valid_until: datetime | None
    effective_specification_sha256: str | None
    settlement: McxSettlement | None
    entry_until: datetime | None
    delivery_start: datetime | None
    broker_entry_until: datetime | None
    snapshot_acquired_at: datetime | None = None

    def __post_init__(self) -> None:
        if (
            type(self.family) is not McxFamily
            or not mcx_contract_name_matches(self.family, self.instrument)
            or (self.verified_expiry is not None and type(self.verified_expiry) is not date)
            or any(value is not None and not _hex(value) for value in (
                self.expiry_proof_sha256, self.effective_specification_sha256,
            ))
            or any(value is not None and (type(value) is not str or not value.strip())
                   for value in (self.provider_snapshot_identity, self.provider_record_identity))
            or any(value is not None and not _aware(value) for value in (
                self.master_valid_until, self.entry_until, self.delivery_start,
                self.broker_entry_until, self.snapshot_acquired_at,
            ))
            or (self.settlement is not None and type(self.settlement) is not McxSettlement)
        ):
            raise ValueError("MCX_CONTRACT_ADMISSION_FACTS_INVALID")

    def reasons(self, observed_at: datetime) -> tuple[str, ...]:
        if not _aware(observed_at):
            raise ValueError("MCX_CONTRACT_OBSERVATION_INVALID")
        reasons = []
        if self.verified_expiry != self.instrument.expiry or self.expiry_proof_sha256 is None:
            reasons.append("MCX_VERIFIED_EXPIRY_UNAVAILABLE")
        if not self.provider_snapshot_identity or not self.provider_record_identity:
            reasons.append("MCX_AUTHENTICATED_CONTRACT_UNAVAILABLE")
        if self.master_valid_until is None or observed_at >= self.master_valid_until:
            reasons.append("MCX_MASTER_FRESHNESS_UNAVAILABLE")
        if self.effective_specification_sha256 is None or self.settlement is None:
            reasons.append("MCX_EFFECTIVE_SPECIFICATION_UNAVAILABLE")
        if self.entry_until is None or observed_at >= self.entry_until:
            reasons.append("MCX_ENTRY_SESSION_CLOSED_OR_UNVERIFIED")
        if self.settlement is McxSettlement.PHYSICAL and (
            self.delivery_start is None or observed_at >= self.delivery_start
        ):
            reasons.append("MCX_DELIVERY_RESTRICTION_ACTIVE_OR_UNVERIFIED")
        if self.broker_entry_until is None or observed_at >= self.broker_entry_until:
            reasons.append("MCX_BROKER_ENTRY_CLOSED_OR_UNVERIFIED")
        if self.verified_expiry is not None and observed_at.astimezone(_IST).date() > self.verified_expiry:
            reasons.append("MCX_CONTRACT_EXPIRED")
        return tuple(reasons)

    def v1_reasons(self, observed_at: datetime) -> tuple[str, ...]:
        """Facts that can bar a V1 manual/PAPER selection, without inventing policy.

        A retained authenticated master proves listed identity, not exchange
        expiry-session, broker cutoff, monetary conversion or current validity.
        Those unknowns are shown as advice and rechecked where factual evidence
        exists; they are not manufactured as selection approvals.
        """
        if not _aware(observed_at):
            raise ValueError("MCX_CONTRACT_OBSERVATION_INVALID")
        reasons = []
        if not self.provider_snapshot_identity or not self.provider_record_identity:
            reasons.append("MCX_AUTHENTICATED_CONTRACT_UNAVAILABLE")
        reasons.extend(_v1_expiry_session_reasons(
            self.family, self.instrument.expiry, observed_at))
        if self.entry_until is not None and observed_at >= self.entry_until:
            reasons.append("MCX_KNOWN_ENTRY_SESSION_CLOSED")
        return tuple(reasons)

    @property
    def identity(self) -> str:
        fields = {
            "family": self.family.value, "instrument": _instrument_value(self.instrument),
            "verified_expiry": None if self.verified_expiry is None else self.verified_expiry.isoformat(),
            "expiry_proof_sha256": self.expiry_proof_sha256,
            "provider_snapshot_identity": self.provider_snapshot_identity,
            "provider_record_identity": self.provider_record_identity,
            "master_valid_until": None if self.master_valid_until is None else self.master_valid_until.isoformat(),
            "effective_specification_sha256": self.effective_specification_sha256,
            "settlement": None if self.settlement is None else self.settlement.value,
            "entry_until": None if self.entry_until is None else self.entry_until.isoformat(),
            "delivery_start": None if self.delivery_start is None else self.delivery_start.isoformat(),
            "broker_entry_until": None if self.broker_entry_until is None else self.broker_entry_until.isoformat(),
        }
        if self.snapshot_acquired_at is not None:
            fields["snapshot_acquired_at"] = self.snapshot_acquired_at.isoformat()
        return _digest(fields)


@dataclass(frozen=True, slots=True)
class McxContractOffer:
    run_identity: str
    family: McxFamily
    observed_at: datetime
    near: McxContractAdmissionFacts
    days_to_verified_expiry: int
    near_reasons: tuple[str, ...]
    next_eligible: McxContractAdmissionFacts | None
    offer_sha256: str
    selection_policy: str = "STRICT_VERIFIED_ENTRY"
    withheld_contracts: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def __post_init__(self) -> None:
        if (
            not is_swing_analysis_run_id(self.run_identity)
            or type(self.family) is not McxFamily
            or not _aware(self.observed_at)
            or type(self.near) is not McxContractAdmissionFacts
            or self.near.family is not self.family
            or type(self.days_to_verified_expiry) is not int
            or self.days_to_verified_expiry < 0
            or self.selection_policy not in {"STRICT_VERIFIED_ENTRY", V1_ADVISORY_SELECTION}
            or type(self.withheld_contracts) is not tuple
            or (self.selection_policy == "STRICT_VERIFIED_ENTRY" and self.withheld_contracts)
            or any(type(item) is not tuple or len(item) != 2
                   or type(item[0]) is not str or not item[0]
                   or type(item[1]) is not tuple or not item[1]
                   or any(type(reason) is not str or not reason for reason in item[1])
                   for item in self.withheld_contracts)
            or (self.selection_policy == "STRICT_VERIFIED_ENTRY"
                and self.near.verified_expiry is None)
            or self.days_to_verified_expiry != (
                ((self.near.verified_expiry if self.selection_policy == "STRICT_VERIFIED_ENTRY"
                  else self.near.instrument.expiry) - self.observed_at.astimezone(_IST).date())
            ).days
            or self.near_reasons != (self.near.reasons(self.observed_at)
                if self.selection_policy == "STRICT_VERIFIED_ENTRY"
                else self.near.v1_reasons(self.observed_at))
            or (self.next_eligible is not None and (
                type(self.next_eligible) is not McxContractAdmissionFacts
                or self.next_eligible.family is not self.family
                or self.next_eligible.provider_snapshot_identity
                   != self.near.provider_snapshot_identity
                or self.next_eligible.instrument.expiry <= self.near.instrument.expiry
                or (self.selection_policy == "STRICT_VERIFIED_ENTRY"
                    and self.next_eligible.reasons(self.observed_at))
                or (self.selection_policy == "STRICT_VERIFIED_ENTRY"
                    and self.days_to_verified_expiry > TEN_CALENDAR_DAYS)
            ))
            or self.offer_sha256 != self.digest()
        ):
            raise ValueError("MCX_CONTRACT_OFFER_INVALID")

    def digest(self) -> str:
        fields = {
            "schema": SCHEMA, "run_identity": self.run_identity,
            "family": self.family.value, "observed_at": self.observed_at.isoformat(),
            "near": self.near.identity, "days_to_verified_expiry": self.days_to_verified_expiry,
            "near_reasons": self.near_reasons,
            "next_eligible": None if self.next_eligible is None else self.next_eligible.identity,
        }
        if self.selection_policy != "STRICT_VERIFIED_ENTRY":
            fields["selection_policy"] = self.selection_policy
        if self.withheld_contracts:
            fields["withheld_contracts"] = self.withheld_contracts
        return _digest(fields)

    def selectable(self, observed_at: datetime | None = None) -> tuple[McxSelectionRole, ...]:
        observed_at = self.observed_at if observed_at is None else observed_at
        if not _aware(observed_at) or observed_at < self.observed_at:
            raise ValueError("MCX_CONTRACT_OBSERVATION_INVALID")
        roles = []
        if (not self.near_reasons and (self.selection_policy == "STRICT_VERIFIED_ENTRY"
                                      or not self.near.v1_reasons(observed_at))):
            roles.append(McxSelectionRole.NEAR)
        if (self.next_eligible is not None
                and (self.selection_policy == "STRICT_VERIFIED_ENTRY"
                     or not self.next_eligible.v1_reasons(observed_at))):
            roles.append(McxSelectionRole.NEXT_ELIGIBLE)
        return tuple(roles)


def prepare_mcx_contract_offer(
    run_identity: str, family: McxFamily,
    facts: tuple[McxContractAdmissionFacts, ...], *, observed_at: datetime,
    selection_policy: str = "STRICT_VERIFIED_ENTRY",
) -> McxContractOffer:
    """Offer first eligible later expiry at an inclusive 10-calendar-day boundary."""

    if (selection_policy not in {"STRICT_VERIFIED_ENTRY", V1_ADVISORY_SELECTION}
            or not is_swing_analysis_run_id(run_identity) or type(family) is not McxFamily
            or type(facts) is not tuple or not facts or not _aware(observed_at)
            or any(type(item) is not McxContractAdmissionFacts or item.family is not family
                   for item in facts)
            or len({item.provider_snapshot_identity for item in facts}) != 1):
        raise ValueError("MCX_CONTRACT_OFFER_INPUT_INVALID")
    ordered = sorted(facts, key=lambda item: (item.instrument.expiry, item.instrument.trading_symbol))
    if len({item.instrument.expiry for item in ordered}) != len(ordered):
        raise ValueError("MCX_CONTRACT_EXPIRY_AMBIGUOUS")
    today = observed_at.astimezone(_IST).date()
    future = tuple(item for item in ordered if item.instrument.expiry >= today)
    withheld = ()
    if selection_policy == V1_ADVISORY_SELECTION:
        evaluated = tuple((item, item.v1_reasons(observed_at)) for item in future)
        withheld = tuple((item.instrument.trading_symbol, reasons)
                         for item, reasons in evaluated if reasons)
        future = tuple(item for item, reasons in evaluated if not reasons)
    if not future:
        raise ValueError("MCX_CONTRACT_EXPIRY_UNAVAILABLE")
    near = future[0]
    if (selection_policy == "STRICT_VERIFIED_ENTRY"
            and (near.verified_expiry != near.instrument.expiry
                 or near.expiry_proof_sha256 is None)):
        raise ValueError("MCX_NEAR_EXPIRY_UNVERIFIED")
    days = ((near.verified_expiry if selection_policy == "STRICT_VERIFIED_ENTRY"
             else near.instrument.expiry) - today).days
    next_eligible = None
    if selection_policy == V1_ADVISORY_SELECTION:
        next_eligible = future[1] if len(future) > 1 else None
    elif days <= TEN_CALENDAR_DAYS:
        next_eligible = next((item for item in future[1:]
                              if not (item.reasons(observed_at)
                                  if selection_policy == "STRICT_VERIFIED_ENTRY"
                                  else item.v1_reasons(observed_at))), None)
    reasons = (near.reasons(observed_at) if selection_policy == "STRICT_VERIFIED_ENTRY"
               else near.v1_reasons(observed_at))
    values = dict(run_identity=run_identity, family=family, observed_at=observed_at,
                  near=near, days_to_verified_expiry=days,
                  near_reasons=reasons, next_eligible=next_eligible,
                  selection_policy=selection_policy, withheld_contracts=withheld)
    digest_fields = {
        "schema": SCHEMA, "run_identity": run_identity, "family": family.value,
        "observed_at": observed_at.isoformat(), "near": near.identity,
        "days_to_verified_expiry": days, "near_reasons": reasons,
        "next_eligible": None if next_eligible is None else next_eligible.identity,
    }
    if selection_policy != "STRICT_VERIFIED_ENTRY":
        digest_fields["selection_policy"] = selection_policy
    if withheld:
        digest_fields["withheld_contracts"] = withheld
    unsigned = _digest(digest_fields)
    return McxContractOffer(**values, offer_sha256=unsigned)


@dataclass(frozen=True, slots=True)
class McxSponsorContractSelection:
    run_identity: str
    family: McxFamily
    role: McxSelectionRole
    trading_symbol: str
    expiry: str
    instrument_sha256: str
    offer_sha256: str
    sponsor_authorization_identity: str
    recorded_at: datetime
    integrity_sha256: str

    def __post_init__(self) -> None:
        if (
            not is_swing_analysis_run_id(self.run_identity)
            or type(self.family) is not McxFamily
            or type(self.role) is not McxSelectionRole
            or not self.trading_symbol or not self.expiry
            or not all(_hex(x) for x in (
                self.instrument_sha256, self.offer_sha256, self.integrity_sha256,
            ))
            or not self.sponsor_authorization_identity
            or not _aware(self.recorded_at)
            or self.integrity_sha256 != self.digest()
        ):
            raise ValueError("MCX_SPONSOR_CONTRACT_SELECTION_INVALID")

    def digest(self) -> str:
        return _digest({
            "schema": SCHEMA, "run_identity": self.run_identity,
            "family": self.family.value, "role": self.role.value,
            "trading_symbol": self.trading_symbol, "expiry": self.expiry,
            "instrument_sha256": self.instrument_sha256,
            "offer_sha256": self.offer_sha256,
            "sponsor_authorization_identity": self.sponsor_authorization_identity,
            "recorded_at": self.recorded_at.isoformat(),
        })


def choose_mcx_contract(
    offer: McxContractOffer, role: McxSelectionRole, *,
    sponsor_authorization_identity: str, recorded_at: datetime,
) -> McxSponsorContractSelection:
    if (type(offer) is not McxContractOffer or type(role) is not McxSelectionRole
            or role not in offer.selectable() or not _aware(recorded_at)
            or recorded_at < offer.observed_at or not sponsor_authorization_identity):
        raise ValueError("MCX_SPONSOR_CONTRACT_CHOICE_REJECTED")
    chosen = offer.near if role is McxSelectionRole.NEAR else offer.next_eligible
    assert chosen is not None
    if (chosen.reasons(recorded_at) if offer.selection_policy == "STRICT_VERIFIED_ENTRY"
            else chosen.v1_reasons(recorded_at)):
        raise ValueError("MCX_SPONSOR_CONTRACT_CHOICE_REJECTED")
    values = dict(run_identity=offer.run_identity, family=offer.family, role=role,
                  trading_symbol=chosen.instrument.trading_symbol,
                  expiry=chosen.instrument.expiry.isoformat(),
                  instrument_sha256=_digest(_instrument_value(chosen.instrument)),
                  offer_sha256=offer.offer_sha256,
                  sponsor_authorization_identity=sponsor_authorization_identity,
                  recorded_at=recorded_at)
    unsigned = _digest({"schema": SCHEMA, **{
        key: value.value if isinstance(value, StrEnum) else value.isoformat()
        if isinstance(value, datetime) else value for key, value in values.items()
    }})
    return McxSponsorContractSelection(**values, integrity_sha256=unsigned)


class LocalMcxSponsorSelectionStore:
    """One immutable pre-analysis choice per run/family; no current pointer."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser()
        if not self.root.is_absolute():
            raise ValueError("MCX_SPONSOR_SELECTION_STORE_INVALID")
        self._lock = RLock()

    def _path(self, run_identity: str, family: McxFamily) -> Path:
        if not is_swing_analysis_run_id(run_identity) or type(family) is not McxFamily:
            raise ValueError("MCX_SPONSOR_SELECTION_PATH_INVALID")
        return self.root / run_identity / (family.value + ".json")

    def retain(self, selection: McxSponsorContractSelection) -> Path:
        if type(selection) is not McxSponsorContractSelection:
            raise ValueError("MCX_SPONSOR_SELECTION_INVALID")
        path = self._path(selection.run_identity, selection.family)
        payload = json.dumps({"schema": SCHEMA, "selection": {
            "run_identity": selection.run_identity, "family": selection.family.value,
            "role": selection.role.value, "trading_symbol": selection.trading_symbol,
            "expiry": selection.expiry, "instrument_sha256": selection.instrument_sha256,
            "offer_sha256": selection.offer_sha256,
            "sponsor_authorization_identity": selection.sponsor_authorization_identity,
            "recorded_at": selection.recorded_at.isoformat(),
            "integrity_sha256": selection.integrity_sha256,
        }}, sort_keys=True, separators=(",", ":")).encode()
        with self._lock:
            if path.exists():
                if path.is_symlink() or path.read_bytes() != payload:
                    raise ValueError("MCX_SPONSOR_SELECTION_IMMUTABLE")
                return path
            path.parent.mkdir(parents=True, exist_ok=True)
            if self.root.is_symlink() or path.parent.is_symlink():
                raise ValueError("MCX_SPONSOR_SELECTION_STORE_INVALID")
            temporary = path.parent / ("." + selection.family.value + "." + uuid4().hex + ".pending")
            try:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as handle:
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

    def load(self, run_identity: str, family: McxFamily) -> McxSponsorContractSelection:
        path = self._path(run_identity, family)
        if path.is_symlink():
            raise ValueError("MCX_SPONSOR_SELECTION_INTEGRITY_INVALID")
        try:
            raw = path.read_bytes()
            value = json.loads(raw)
            if value["schema"] != SCHEMA or raw != json.dumps(
                value, sort_keys=True, separators=(",", ":")
            ).encode():
                raise ValueError
            fields = value["selection"]
            selection = McxSponsorContractSelection(
                run_identity=fields["run_identity"], family=McxFamily(fields["family"]),
                role=McxSelectionRole(fields["role"]),
                trading_symbol=fields["trading_symbol"], expiry=fields["expiry"],
                instrument_sha256=fields["instrument_sha256"],
                offer_sha256=fields["offer_sha256"],
                sponsor_authorization_identity=fields["sponsor_authorization_identity"],
                recorded_at=datetime.fromisoformat(fields["recorded_at"]),
                integrity_sha256=fields["integrity_sha256"],
            )
            if path != self._path(selection.run_identity, selection.family):
                raise ValueError
            return selection
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise ValueError("MCX_SPONSOR_SELECTION_INTEGRITY_INVALID") from error


def selected_mcx_instrument_before_acquisition(
    store: LocalMcxSponsorSelectionStore, offer: McxContractOffer,
    current_master: tuple[InstrumentRecord, ...], *, acquired_at: datetime,
) -> InstrumentRecord:
    """Return only the exact recorded contract, before any candle request."""

    if (type(store) is not LocalMcxSponsorSelectionStore
            or type(offer) is not McxContractOffer
            or type(current_master) is not tuple or not _aware(acquired_at)):
        raise ValueError("MCX_CONTRACT_ACQUISITION_INPUT_INVALID")
    selection = store.load(offer.run_identity, offer.family)
    if (selection.offer_sha256 != offer.offer_sha256
            or selection.role not in offer.selectable()
            or selection.recorded_at >= acquired_at):
        raise ValueError("MCX_CONTRACT_SELECTION_STALE")
    chosen = offer.near if selection.role is McxSelectionRole.NEAR else offer.next_eligible
    if chosen is None or (chosen.reasons(acquired_at)
            if offer.selection_policy == "STRICT_VERIFIED_ENTRY"
            else chosen.v1_reasons(acquired_at)):
        raise ValueError("MCX_CONTRACT_SELECTION_INELIGIBLE")
    matches = tuple(item for item in current_master
                    if type(item) is InstrumentRecord
                    and item.trading_symbol == selection.trading_symbol
                    and item.expiry is not None
                    and item.expiry.isoformat() == selection.expiry
                    and _digest(_instrument_value(item)) == selection.instrument_sha256)
    if len(matches) != 1 or matches[0] != chosen.instrument:
        raise ValueError("MCX_CONTRACT_MASTER_CHANGED_OR_AMBIGUOUS")
    return matches[0]


def acquire_selected_mcx_evidence(
    store: LocalMcxSponsorSelectionStore, offer: McxContractOffer,
    current_master: tuple[InstrumentRecord, ...], *, acquired_at: datetime,
    acquire: Callable[[InstrumentRecord], _T],
) -> _T:
    if not callable(acquire):
        raise ValueError("MCX_CONTRACT_ACQUISITION_INPUT_INVALID")
    selected = selected_mcx_instrument_before_acquisition(
        store, offer, current_master, acquired_at=acquired_at,
    )
    return acquire(selected)


def require_mcx_choice_matches_handoff(
    selection: McxSponsorContractSelection, handoff: McxStep31PreparedHandoff,
) -> None:
    """A later expiry needs its own exact run, candles, Review, receipt and V2."""

    if (type(selection) is not McxSponsorContractSelection
            or type(handoff) is not McxStep31PreparedHandoff
            or selection.run_identity != handoff.bound.run_identity
            or selection.family is not handoff.bound.family
            or selection.trading_symbol != handoff.bound.derivative_symbol
            or selection.expiry != handoff.bound.derivative_expiry):
        raise ValueError("MCX_SELECTION_REVIEW_V2_CONTRACT_MISMATCH")


@dataclass(frozen=True, slots=True)
class McxProcessChoice:
    family: McxFamily
    offer: McxContractOffer
    store_root: Path
    selection_sha256: str


@dataclass(frozen=True, slots=True)
class McxAnalysisProcessHandoff:
    """Five recorded choices carried unchanged across the Swing worker boundary."""

    run_identity: str
    generation: int
    choices: tuple[McxProcessChoice, ...]
    integrity_sha256: str

    def __post_init__(self) -> None:
        if (
            not is_swing_analysis_run_id(self.run_identity)
            or type(self.generation) is not int or self.generation <= 0
            or type(self.choices) is not tuple or len(self.choices) != len(McxFamily)
            or any(type(item) is not McxProcessChoice for item in self.choices)
            or {item.family for item in self.choices} != set(McxFamily)
            or any(
                item.offer.run_identity != self.run_identity
                or item.offer.family is not item.family
                or not item.store_root.is_absolute()
                or not _hex(item.selection_sha256)
                for item in self.choices
            )
            or self.integrity_sha256 != self.digest()
        ):
            raise ValueError("MCX_PROCESS_HANDOFF_INVALID")

    def digest(self) -> str:
        return _digest({
            "schema": SCHEMA, "run_identity": self.run_identity,
            "generation": self.generation,
            "choices": [{
                "family": item.family.value,
                "offer_sha256": item.offer.offer_sha256,
                "store_root": str(item.store_root),
                "selection_sha256": item.selection_sha256,
            } for item in self.choices],
        })

    @classmethod
    def create(
        cls, run_identity: str, generation: int,
        offers: dict[McxFamily, McxContractOffer],
        store: LocalMcxSponsorSelectionStore,
    ) -> McxAnalysisProcessHandoff:
        if set(offers) != set(McxFamily):
            raise ValueError("MCX_PROCESS_HANDOFF_INCOMPLETE")
        choices = tuple(McxProcessChoice(
            family, offers[family], store.root,
            store.load(run_identity, family).integrity_sha256,
        ) for family in McxFamily)
        values = dict(run_identity=run_identity, generation=generation, choices=choices)
        unsigned = _digest({
            "schema": SCHEMA, "run_identity": run_identity,
            "generation": generation,
            "choices": [{
                "family": item.family.value,
                "offer_sha256": item.offer.offer_sha256,
                "store_root": str(item.store_root),
                "selection_sha256": item.selection_sha256,
            } for item in choices],
        })
        return cls(**values, integrity_sha256=unsigned)

    def analysis_choices(self) -> dict[
        McxFamily, tuple[McxContractOffer, LocalMcxSponsorSelectionStore]
    ]:
        """Parent and spawned child both recheck immutable selection bytes."""

        result = {}
        for item in self.choices:
            store = LocalMcxSponsorSelectionStore(item.store_root)
            selected = store.load(self.run_identity, item.family)
            if (selected.integrity_sha256 != item.selection_sha256
                    or selected.offer_sha256 != item.offer.offer_sha256):
                raise ValueError("MCX_PROCESS_HANDOFF_SELECTION_CHANGED")
            result[item.family] = item.offer, store
        return result
