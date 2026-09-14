"""WO-04 prepared Swing contributions; WO-05 alone selects committed runs.

No runtime activation, latest selector, current pointer or downstream rebinding.
Legacy Native and MTF serialization remains owned by its existing producers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

from kronos.provider.contracts.instrument import InstrumentRecord
from kronos.swing.run_provenance import SwingAnalysisRunProvenance
from kronos.swing.v1 import native_discovery as native
from kronos.swing.v1.mtf_facts import FactualTimeframe, SameRunMtfFactSnapshot

SCHEMA = "KRONOS-SWING-OPPORTUNITY-CONTINUITY-V1"
MANUAL_REASONS = frozenset({"SOURCE_BINDING_UNAVAILABLE", "SOURCE_OR_CONTRACT_BREAK",
    "UNRESOLVED_CONTINUITY_BREAK", "ANALYTICAL_POLICY_CHANGED", "EXISTING_STRUCTURAL_INVALIDATION",
    "FOUR_HOUR_REUSE_CONTEXT_UNCERTAIN", "FOUR_HOUR_BOUNDARY_REGRESSION", "DIRECTION_CHANGED",
    "OPERATIVE_ANCHOR_CHANGED", "ANALYTICAL_ROOT_UNCERTAIN"})


class ContinuityDisposition(StrEnum):
    NOT_ADMITTED = "NOT_ADMITTED"
    ADMITTED = "ADMITTED"
    CONTINUING = "CONTINUING"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


def _json(value):
    if hasattr(value, "__dataclass_fields__"):
        return _json(asdict(value))
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError("SWING_CONTINUITY_TIMESTAMP_INVALID")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("SWING_CONTINUITY_NUMBER_INVALID")
    return value


def _bytes(value):
    return json.dumps(_json(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _digest(value):
    return sha256(_bytes(value)).hexdigest()


def _hash_valid(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


@dataclass(frozen=True)
class SourceBinding:
    canonical_instrument: str
    exchange: str
    provider: str
    segment: str
    trading_symbol: str
    instrument_type: str
    expiry: str | None

    def __post_init__(self):
        if (not self.canonical_instrument or self.exchange not in {"NSE", "MCX"}
                or not all((self.provider, self.segment, self.trading_symbol))
                or not isinstance(self.instrument_type, str)
                or (self.exchange == "MCX" and self.expiry is None)):
            raise ValueError("SWING_CONTINUITY_SOURCE_INVALID")
        if self.expiry is not None:
            from datetime import date
            if date.fromisoformat(self.expiry).isoformat() != self.expiry:
                raise ValueError("SWING_CONTINUITY_SOURCE_INVALID")

    @classmethod
    def from_instrument(cls, canonical_instrument, record: InstrumentRecord):
        if type(record) is not InstrumentRecord:
            raise ValueError("SWING_CONTINUITY_SOURCE_INVALID")
        return cls(canonical_instrument, record.exchange, record.provider, record.segment,
                   record.trading_symbol, record.instrument_type,
                   None if record.expiry is None else record.expiry.isoformat())


def _pivots(series):
    # Rolling window indices are positions, not factual pivot identity.
    return {"definition": series.definition_identity, "radius": series.radius,
            "highs": [(p.kind.value, p.timestamp, p.value) for p in series.swing_highs[-2:]],
            "lows": [(p.kind.value, p.timestamp, p.value) for p in series.swing_lows[-2:]]}


def timeframe_material(fact):
    return {"timeframe": fact.timeframe, "start": fact.source_timestamp,
            "end": fact.observation_boundary,
            "ohlcv": (fact.open, fact.high, fact.low, fact.close, fact.volume),
            "calendar": (fact.calendar_identity, fact.calendar_version, fact.session_identity,
                         fact.exchange_timezone),
            "provider": fact.source_provider_identity, "interval": fact.source_interval,
            "bucket": fact.bucket_class,
            "pivots": [_pivots(s) for s in sorted(fact.structural_measurements, key=lambda s: s.radius)],
            "sma": None if fact.moving_averages is None else
                   (fact.moving_averages.sma20, fact.moving_averages.sma50, fact.moving_averages.sma200),
            "volume": None if fact.volume_facts is None else fact.volume_facts.prior_20_mean}


def evidence_fingerprints(instrument, binding):
    facts = {tf.value: timeframe_material(instrument.fact(tf)) for tf in
             (FactualTimeframe.DAILY, FactualTimeframe.FOUR_HOUR, FactualTimeframe.ONE_HOUR)}
    weekly = instrument.nse_weekly_foundation
    if instrument.exchange == "NSE":
        facts["1W"] = None if weekly is None else {
            "availability": weekly.availability, "reason": weekly.unavailable_reason,
            "boundary": weekly.observation_boundary,
            "calendar": (weekly.calendar_identity, weekly.calendar_version,
                         weekly.calendar_publication_sha256),
            "provider": (weekly.provider, weekly.provider_exchange, weekly.provider_segment,
                         weekly.provider_trading_symbol, weekly.provider_instrument_type),
            "closes": [(bar.source_start, bar.observation_boundary, bar.close)
                       for bar in weekly.completed_weekly_bars[-201:]],
            "sma": (weekly.current_sma200, weekly.prior_sma200_5w,
                    weekly.latest_weekly_close, weekly.latest_close_relation, weekly.sma200_direction),
            "structure": None if weekly.radius_2_structure is None else
                         (weekly.radius_2_structure.high_relation, weekly.radius_2_structure.low_relation),
        }
    common = {"schema": SCHEMA, "subject": (instrument.exchange, instrument.canonical_instrument),
              "source": binding, "policy": (native.NATIVE_DISCOVERY_POLICY_ID,
                                           native.NATIVE_DISCOVERY_POLICY_VERSION)}
    return {name: _digest({**common, "fact": fact}) for name, fact in facts.items()}


@dataclass(frozen=True)
class FourHourConsumption:
    boundary: datetime
    fingerprint: str
    daily_fingerprint: str
    entering_state: native.Native4HState | None
    result_state: native.Native4HState
    anchor: native.NativeAnchor | None
    reasons: tuple[str, ...]
    daily_state: native.Native1DState
    direction: native.V1Direction


@dataclass(frozen=True)
class ContinuityRow:
    canonical_instrument: str
    source_binding: SourceBinding | None
    disposition: ContinuityDisposition
    reason: str | None
    opportunity_id: str | None
    origin_run: str | None
    origin_assessment: str | None
    first_admitted: datetime | None
    material_revision: str | None
    material_fingerprint: str
    latest_material_at: datetime
    last_analysis_checked: datetime
    no_material_change: bool
    consumptions: tuple[FourHourConsumption, ...]


@dataclass(frozen=True)
class PreparedContinuity:
    """Not an admission receipt. Candidate origins are inert until WO-05 commits."""
    native_run: native.NativeDiscoveryRun
    mtf_sha256: str
    rows: tuple[ContinuityRow, ...]
    integrity_sha256: str

    def validate(self):
        # Existing Native decoder enforces unchanged Native hashes and schema.
        native._run(native._json_value(asdict(self.native_run)))
        if (not _hash_valid(self.mtf_sha256) or len(self.rows) != 98
                or len({r.canonical_instrument for r in self.rows}) != 98
                or {r.canonical_instrument for r in self.rows} !=
                   {a.canonical_instrument for a in self.native_run.assessments}
                or _digest(_material(self)) != self.integrity_sha256):
            raise ValueError("SWING_CONTINUITY_INTEGRITY_INVALID")
        for row in self.rows:
            assessment = next(a for a in self.native_run.assessments
                              if a.canonical_instrument == row.canonical_instrument)
            if (not _hash_valid(row.material_fingerprint)
                    or row.last_analysis_checked < self.native_run.observed_at
                    or row.latest_material_at > row.last_analysis_checked
                    or type(row.disposition) is not ContinuityDisposition
                    or type(row.no_material_change) is not bool
                    or (row.source_binding is not None and
                        row.source_binding.canonical_instrument != row.canonical_instrument)):
                raise ValueError("SWING_CONTINUITY_ROW_INVALID")
            origin = (row.opportunity_id, row.origin_run, row.origin_assessment,
                      row.first_admitted, row.material_revision)
            if any(v is not None for v in origin):
                if (any(v is None for v in origin) or not _hash_valid(row.origin_assessment)
                        or not native.is_swing_analysis_run_id(row.origin_run)
                        or row.first_admitted > row.last_analysis_checked
                        or row.opportunity_id != _opportunity_id(row.origin_run, row.canonical_instrument,
                                                                 row.origin_assessment)):
                    raise ValueError("SWING_CONTINUITY_ORIGIN_INVALID")
            if row.disposition in {ContinuityDisposition.ADMITTED, ContinuityDisposition.CONTINUING}:
                if row.opportunity_id is None or row.source_binding is None:
                    raise ValueError("SWING_CONTINUITY_ORIGIN_INVALID")
            if row.disposition is ContinuityDisposition.ADMITTED and (
                    assessment.status is not native.NativeDiscoveryStatus.PROBABLE
                    or row.origin_run != self.native_run.run_identity
                    or row.origin_assessment != assessment.result_sha256):
                raise ValueError("SWING_CONTINUITY_ADMISSION_INVALID")
            if (row.disposition is ContinuityDisposition.MANUAL_REVIEW_REQUIRED) != (row.reason is not None):
                raise ValueError("SWING_CONTINUITY_DISPOSITION_INVALID")
            if row.reason is not None and row.reason not in MANUAL_REASONS:
                raise ValueError("SWING_CONTINUITY_DISPOSITION_INVALID")
            if row.material_revision is not None and (
                    not row.material_revision.startswith("SWMR-")
                    or not _hash_valid(row.material_revision[5:])
                    or (row.reason is None and row.material_revision != "SWMR-" + _digest({
                        "opportunity": row.opportunity_id, "material": row.material_fingerprint}))):
                raise ValueError("SWING_CONTINUITY_REVISION_INVALID")
            if len({m.fingerprint for m in row.consumptions}) != len(row.consumptions):
                raise ValueError("SWING_CONTINUITY_CONSUMPTION_INVALID")
            for memo in row.consumptions:
                if (not _hash_valid(memo.fingerprint) or not _hash_valid(memo.daily_fingerprint)
                        or memo.boundary > self.native_run.observed_at or not memo.reasons
                        or type(memo.result_state) is not native.Native4HState
                        or type(memo.daily_state) is not native.Native1DState
                        or (memo.entering_state is not None and type(memo.entering_state) is not native.Native4HState)
                        or type(memo.direction) is not native.V1Direction):
                    raise ValueError("SWING_CONTINUITY_CONSUMPTION_INVALID")
        return self


def _material(bundle):
    # Native timestamp spellings participate in its existing hashes: preserve them.
    return {"schema": SCHEMA, "native_run": native._json_value(asdict(bundle.native_run)),
            "mtf_sha256": bundle.mtf_sha256, "rows": bundle.rows}


def _opportunity_id(run, symbol, assessment):
    return "SWO-" + _digest({"origin_run": run, "instrument": symbol, "assessment": assessment})


@dataclass(frozen=True, init=False)
class CommittedContinuity:
    """Exact selected contribution supplied by the WO-05 publication owner.

    This verifier cannot select a current run or prove multi-file atomic commit.
    WO-05 must supply its committed digest; file existence is never sufficient.
    """
    contribution: PreparedContinuity
    successful_completed_at: datetime

    def __init__(self, *args, **kwargs):
        raise TypeError("USE_EXACT_COMMITTED_CONTINUITY_VERIFICATION")

    @classmethod
    def verify(cls, prepared, *, native_run, mtf_snapshot, provenance,
               committed_contribution_sha256):
        prepared.validate()
        if (type(provenance) is not SwingAnalysisRunProvenance
                or provenance.successful_completed_at is None
                or prepared.integrity_sha256 != committed_contribution_sha256
                or prepared.native_run != native_run
                or prepared.mtf_sha256 != _digest(mtf_snapshot)
                or provenance.run_id != native_run.run_identity
                or mtf_snapshot.run_identity != native_run.run_identity
                or native_run.observed_at != mtf_snapshot.observed_at
                or native_run.provider_source_identity != mtf_snapshot.provider_source_identity
                or any(r.last_analysis_checked != provenance.successful_completed_at for r in prepared.rows)):
            raise ValueError("SWING_CONTINUITY_COMMITTED_BINDING_INVALID")
        result = object.__new__(cls)
        object.__setattr__(result, "contribution", prepared)
        object.__setattr__(result, "successful_completed_at", provenance.successful_completed_at)
        return result


def prepare_continuity(snapshot: SameRunMtfFactSnapshot, source_bindings, *,
                       predecessor: CommittedContinuity | None = None, daily_control=None,
                       successful_completed_at: datetime | None = None,
                       adopted_predecessor=None):
    """Pure bundle preparation. No retained file is independently an admission."""
    if type(snapshot) is not SameRunMtfFactSnapshot or (
            predecessor is not None and type(predecessor) is not CommittedContinuity):
        raise ValueError("SWING_CONTINUITY_REQUEST_INVALID")
    prior = None if predecessor is None else predecessor.contribution.validate()
    if adopted_predecessor is not None:
        from kronos.swing.run_publication import CommittedRun
        if (type(adopted_predecessor) is not CommittedRun or prior is not None
                or adopted_predecessor.manifest["kind"] != "ADOPTED_EXISTING_CHECKPOINT"
                or adopted_predecessor.continuity is not None):
            raise ValueError("SWING_CONTINUITY_REQUEST_INVALID")
    checked_at = snapshot.observed_at if successful_completed_at is None else successful_completed_at
    if checked_at.utcoffset() is None or checked_at < snapshot.observed_at:
        raise ValueError("SWING_CONTINUITY_TIMESTAMP_INVALID")
    if prior is not None and snapshot.observed_at < prior.native_run.observed_at:
        raise ValueError("SWING_CONTINUITY_PREDECESSOR_ORDER_INVALID")
    if any(f.observation_boundary > snapshot.observed_at for i in snapshot.instruments for f in i.timeframes):
        raise ValueError("SWING_CONTINUITY_INCOMPLETE_EVIDENCE")
    if not isinstance(source_bindings, (tuple, list)) or any(type(b) is not SourceBinding for b in source_bindings):
        raise ValueError("SWING_CONTINUITY_SOURCE_INVALID")
    bindings = {b.canonical_instrument: b for b in source_bindings}
    if (len(bindings) != len(source_bindings)
            or set(bindings) - {i.canonical_instrument for i in snapshot.instruments}):
        raise ValueError("SWING_CONTINUITY_SOURCE_INVALID")
    rows = []

    def build(snap, instrument, previous, control):
        binding = bindings.get(instrument.canonical_instrument)
        old = None if prior is None else next(r for r in prior.rows
                                             if r.canonical_instrument == instrument.canonical_instrument)
        fps = evidence_fingerprints(instrument, binding)
        material = _digest(fps)
        same = old is not None and old.material_fingerprint == material
        reason = None
        if adopted_predecessor is not None and previous is not None and previous.status in {
                native.NativeDiscoveryStatus.PROBABLE, native.NativeDiscoveryStatus.FORMING_WATCH}:
            # No historical origins/revisions/unknown entering state are invented.
            reason = "ANALYTICAL_ROOT_UNCERTAIN"
        if binding is None or binding.exchange != instrument.exchange:
            reason = "SOURCE_BINDING_UNAVAILABLE"
        elif old is not None and old.source_binding != binding:
            reason = "SOURCE_OR_CONTRACT_BREAK"
        elif old is not None and old.disposition is ContinuityDisposition.MANUAL_REVIEW_REQUIRED:
            reason = "UNRESOLVED_CONTINUITY_BREAK"
        elif previous is not None and (previous.policy_identity, previous.policy_version) != (
                native.NATIVE_DISCOVERY_POLICY_ID, native.NATIVE_DISCOVERY_POLICY_VERSION):
            reason = "ANALYTICAL_POLICY_CHANGED"
        memos = list(() if old is None else old.consumptions)
        four = instrument.fact(FactualTimeframe.FOUR_HOUR)

        def resolve(daily, current_four, daily_state, direction, entering):
            nonlocal reason
            if adopted_predecessor is not None:
                old_four = adopted_predecessor.mtf.instrument(instrument.canonical_instrument).fact(FactualTimeframe.FOUR_HOUR)
                if current_four.observation_boundary <= old_four.observation_boundary:
                    # The legacy publication has no trustworthy consumption receipt.
                    # Preserve its original Native bytes at adoption; subsequent
                    # uncertain reuse is explicitly unavailable, never advanced.
                    reason = reason or "FOUR_HOUR_REUSE_CONTEXT_UNCERTAIN"
                    return (native.Native4HState.UNAVAILABLE, None,
                            ("SWING_CONTINUITY_REUSE_REQUIRES_MANUAL_REVIEW",))
            if memos and four.observation_boundary < max(m.boundary for m in memos):
                reason = reason or "FOUR_HOUR_BOUNDARY_REGRESSION"
                return (native.Native4HState.UNAVAILABLE, None,
                        ("SWING_CONTINUITY_REUSE_REQUIRES_MANUAL_REVIEW",))
            boundary_memos = [m for m in memos if m.boundary == four.observation_boundary]
            exact = next((m for m in boundary_memos if m.fingerprint == fps["4H"]), None)
            first = next(iter(boundary_memos), None)
            # A correction at the same boundary always starts before that boundary.
            start = entering if first is None else first.entering_state
            if (exact is not None and exact.daily_fingerprint == fps["1D"]
                    and exact.direction == direction and exact.daily_state == daily_state
                    and daily_state not in {native.Native1DState.NO_VALID_SWING_REGIME,
                                            native.Native1DState.UNAVAILABLE}):
                return exact.result_state, exact.anchor, exact.reasons
            result = native.classify_native_four_hour(daily, current_four, daily_state, direction, start)
            if exact is not None:
                if (daily_state in {native.Native1DState.NO_VALID_SWING_REGIME, native.Native1DState.UNAVAILABLE}
                        or result[0] is native.Native4HState.FAILED):
                    reason = reason or ("FOUR_HOUR_REUSE_CONTEXT_UNCERTAIN"
                        if daily_state is native.Native1DState.UNAVAILABLE
                        else "EXISTING_STRUCTURAL_INVALIDATION")
                    return result
                if (exact.direction != direction or exact.daily_state != daily_state
                        or (exact.daily_fingerprint != fps["1D"] and
                            (result[0], result[1]) != (exact.result_state, exact.anchor))):
                    reason = reason or "FOUR_HOUR_REUSE_CONTEXT_UNCERTAIN"
                    return (native.Native4HState.UNAVAILABLE, None,
                            ("SWING_CONTINUITY_REUSE_REQUIRES_MANUAL_REVIEW",))
                return exact.result_state, exact.anchor, exact.reasons
            memos.append(FourHourConsumption(four.observation_boundary, fps["4H"], fps["1D"],
                                            start, *result, daily_state, direction))
            return result

        assessment = native._discover_instrument(snap, instrument, previous, control,
                                                 four_hour_resolver=resolve)
        if same and previous is not None and reason is None:
            # Preserve analytical meaning while creating the normal new run-bound artifact.
            names = ("direction", "weekly_state", "daily_state", "four_hour_state", "one_hour_state",
                     "status", "context_kind", "opportunity_identity", "operative_anchor", "reason_codes")
            assessment = replace(assessment, **{name: getattr(previous, name) for name in names})
            assessment = replace(assessment, result_sha256=native._assessment_digest(assessment))
        if old is not None and previous is not None:
            if assessment.direction != previous.direction:
                reason = reason or "DIRECTION_CHANGED"
            elif assessment.operative_anchor != previous.operative_anchor:
                reason = reason or "OPERATIVE_ANCHOR_CHANGED"
            elif assessment.context_kind != previous.context_kind:
                reason = reason or "ANALYTICAL_ROOT_UNCERTAIN"
        if ("DAILY_RADIUS2_STRUCTURAL_FAILURE" in assessment.reason_codes
                or assessment.four_hour_state is native.Native4HState.FAILED
                or assessment.one_hour_state is native.Native1HState.FAILING):
            reason = reason or "EXISTING_STRUCTURAL_INVALIDATION"
        opportunity = None if old is None else old.opportunity_id
        origin_run = None if old is None else old.origin_run
        origin_assessment = None if old is None else old.origin_assessment
        first_admitted = None if old is None else old.first_admitted
        disposition = ContinuityDisposition.NOT_ADMITTED
        if reason is not None:
            disposition = ContinuityDisposition.MANUAL_REVIEW_REQUIRED
        elif opportunity is not None:
            disposition = ContinuityDisposition.CONTINUING
        elif assessment.status is native.NativeDiscoveryStatus.PROBABLE:
            disposition = ContinuityDisposition.ADMITTED
            origin_run, origin_assessment = snap.run_identity, assessment.result_sha256
            first_admitted = checked_at
            opportunity = _opportunity_id(origin_run, instrument.canonical_instrument, origin_assessment)
        revision = None if old is None else old.material_revision
        if opportunity is not None and reason is None:
            revision = "SWMR-" + _digest({"opportunity": opportunity, "material": material})
        rows.append(ContinuityRow(instrument.canonical_instrument, binding, disposition, reason,
                                 opportunity, origin_run, origin_assessment, first_admitted, revision,
                                 material, old.latest_material_at if same else max(
                                     f.observation_boundary for f in instrument.timeframes
                                     if instrument.exchange == "NSE" or f.timeframe is not FactualTimeframe.WEEKLY),
                                 checked_at, same, tuple(memos)))
        return assessment

    previous_run = (adopted_predecessor.native if adopted_predecessor is not None else
                    None if prior is None else prior.native_run)
    run = native.discover_native_mtf(snapshot, previous_run,
                                    daily_control, assessment_builder=build)
    result = PreparedContinuity(run, _digest(snapshot), tuple(rows), "")
    return replace(result, integrity_sha256=_digest(_material(result))).validate()


def _anchor(value):
    return None if value is None else native.NativeAnchor(native.NativeAnchorType(value["anchor_type"]),
                                                        value["price"], datetime.fromisoformat(value["source_boundary"]))


def stamp_completed_contribution(prepared, completed_at):
    """Publication owner supplies completion after the full analysis is built."""
    prepared.validate()
    if completed_at.utcoffset() is None or completed_at < prepared.native_run.observed_at:
        raise ValueError("SWING_CONTINUITY_TIMESTAMP_INVALID")
    rows = tuple(replace(row, last_analysis_checked=completed_at,
        first_admitted=(completed_at if row.origin_run == prepared.native_run.run_identity
                        else row.first_admitted)) for row in prepared.rows)
    result = replace(prepared, rows=rows, integrity_sha256="")
    return replace(result, integrity_sha256=_digest(_material(result))).validate()


def _row(value):
    if set(value) != {f.name for f in fields(ContinuityRow)}:
        raise ValueError("SWING_CONTINUITY_ROW_INVALID")
    value = dict(value)
    value["disposition"] = ContinuityDisposition(value["disposition"])
    value["source_binding"] = None if value["source_binding"] is None else SourceBinding(**value["source_binding"])
    for key in ("first_admitted", "latest_material_at", "last_analysis_checked"):
        value[key] = None if value[key] is None else datetime.fromisoformat(value[key])
    memos = []
    for m in value["consumptions"]:
        if set(m) != {f.name for f in fields(FourHourConsumption)}:
            raise ValueError("SWING_CONTINUITY_CONSUMPTION_INVALID")
        memos.append(FourHourConsumption(datetime.fromisoformat(m["boundary"]), m["fingerprint"],
            m["daily_fingerprint"], None if m["entering_state"] is None else native.Native4HState(m["entering_state"]),
            native.Native4HState(m["result_state"]), _anchor(m["anchor"]), tuple(m["reasons"]),
            native.Native1DState(m["daily_state"]), native.V1Direction(m["direction"])))
    value["consumptions"] = tuple(memos)
    return ContinuityRow(**value)


class ContinuityEvidenceStore:
    """Immutable Swing companion files. Deliberately no latest/current API."""
    def __init__(self, native_evidence_root: Path):
        if not Path(native_evidence_root).is_absolute() or Path(native_evidence_root) == Path("/"):
            raise ValueError("SWING_CONTINUITY_ROOT_INVALID")
        self.root = Path(native_evidence_root) / "opportunity-continuity"
        self._lock = RLock()

    def _path(self, run):
        if not native.is_swing_analysis_run_id(run):
            raise ValueError("SWING_ANALYSIS_RUN_IDENTITY_INVALID")
        return self.root / (run + ".json")

    def retain_prepared(self, bundle: PreparedContinuity):
        bundle.validate()
        path = self._path(bundle.native_run.run_identity)
        payload = _bytes({**_material(bundle), "integrity_sha256": bundle.integrity_sha256})
        with self._lock:
            if path.exists():
                if path.read_bytes() != payload:
                    raise ValueError("SWING_CONTINUITY_IMMUTABLE")
                return path
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            temp = path.with_name("." + uuid4().hex + ".tmp")
            try:
                fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, path)
            finally:
                temp.unlink(missing_ok=True)
        return path

    def load_prepared(self, run):
        try:
            payload = json.loads(self._path(run).read_bytes())
            if set(payload) != {"schema", "native_run", "mtf_sha256", "rows", "integrity_sha256"} or payload["schema"] != SCHEMA:
                raise ValueError
            result = PreparedContinuity(native._run(payload["native_run"]), payload["mtf_sha256"],
                                        tuple(_row(r) for r in payload["rows"]), payload["integrity_sha256"]).validate()
            if result.native_run.run_identity != run:
                raise ValueError
            return result
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise ValueError("SWING_CONTINUITY_RESTORATION_INVALID") from error
