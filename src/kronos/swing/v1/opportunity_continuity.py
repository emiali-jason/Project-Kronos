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
class CausalPivotReference:
    timeframe: str
    radius: int
    kind: str
    value: float
    centre: datetime
    confirmation: datetime | None


@dataclass(frozen=True)
class QualificationEvidence:
    """WO-06 references only; the exact Native/MTF owners retain the payloads."""
    run: str
    assessment: str
    mtf: str
    observed_at: datetime
    policy: tuple[str, str]
    boundaries: tuple[tuple[str, datetime], ...]
    fingerprints: tuple[tuple[str, str], ...]
    candles: tuple[tuple[str, str], ...]
    history: tuple[tuple[str, int, str], ...]
    pivots: tuple[CausalPivotReference, ...]
    anchor: native.NativeAnchor | None
    gaps: tuple[str, ...]


@dataclass(frozen=True)
class QualificationOrigin:
    opportunity: str
    material_revision: str
    evidence: QualificationEvidence
    boundary: datetime | None
    first_detected: datetime
    attribution: str


@dataclass(frozen=True)
class QualificationCorrection:
    """Same-boundary WO-04 material correction, not a replacement detection."""
    previous_run: str
    previous_assessment: str
    evidence: QualificationEvidence
    timeframes: tuple[str, ...]
    support: str


@dataclass(frozen=True)
class QualificationRecord:
    origin: QualificationOrigin | None
    current: QualificationEvidence
    validity: str
    reason: str | None
    corrections: tuple[QualificationCorrection, ...]


def _candle_fingerprint(bar):
    # Acquisition boundaries/provenance remain in exact MTF references, not in
    # the equality test for an unchanged historical completed candle.
    return _digest({"start": getattr(bar, "source_timestamp", getattr(bar, "source_start", None)),
        **{key: getattr(bar, key, None) for key in ("observation_boundary", "open", "high", "low",
            "close", "volume", "calendar_identity", "calendar_version", "session_identity",
            "trading_week_identity", "exchange_timezone", "source_interval", "source_provider_identity", "bucket_class")}})


def _causal_evidence(snapshot, instrument, assessment, fps, mtf_sha):
    """Reference the radii already consumed by Native; never classify or replay.

    Pivot indices are relative to measurement windows, so resolve centres by
    exact timestamp/value in retained bars, then locate the right-hand bar.
    Absence is an evidence gap, never an inferred confirmation timestamp.
    """
    boundaries, candles, history, refs, gaps = [], [], [], [], []
    for tf, radii in ((FactualTimeframe.DAILY, (2, 1)),
                      (FactualTimeframe.FOUR_HOUR, (1, 2)),
                      (FactualTimeframe.ONE_HOUR, (1,))):
        fact = instrument.fact(tf)
        bars = instrument.completed_bars(tf)
        boundaries.append((tf.value, fact.observation_boundary))
        candles.append((tf.value, _candle_fingerprint(bars[-1])))
        history.append((tf.value, len(bars), _digest(tuple(_candle_fingerprint(b) for b in bars))))
        # Daily radius 1 participates only in the existing reversal branch.
        if tf is FactualTimeframe.DAILY and assessment.context_kind is not native.NativeContextKind.REVERSAL:
            radii = (2,)
        for radius in radii:
            series = native._pivot_series(fact, radius)
            pivots = (*series.swing_highs[-2:], *series.swing_lows[-2:])
            if len(pivots) < 4:
                gaps.append(tf.value + "_CAUSAL_PIVOTS_UNAVAILABLE")
            for pivot in pivots:
                refs.append(_pivot_reference(tf.value, radius, pivot, bars, fact.observation_boundary))
    if instrument.exchange == "NSE":
        weekly = instrument.nse_weekly_foundation
        if weekly is None or not weekly.completed_weekly_bars or weekly.observation_boundary is None:
            gaps.append("1W_CAUSAL_EVIDENCE_UNAVAILABLE")
        else:
            boundaries.append(("1W", weekly.observation_boundary))
            candles.append(("1W", _candle_fingerprint(weekly.completed_weekly_bars[-1])))
            history.append(("1W", len(weekly.completed_weekly_bars),
                _digest(tuple(_candle_fingerprint(b) for b in weekly.completed_weekly_bars))))
            structure = weekly.radius_2_structure
            # Native explicitly permits NONE/incomplete Weekly structure. Only
            # reference a directional relation actually available to its rules;
            # do not turn a factual absence into a new Weekly eligibility gate.
            if structure is not None and structure.high_relation is not None and structure.low_relation is not None:
                for pivot in (structure.preceding_high, structure.latest_high,
                              structure.preceding_low, structure.latest_low):
                    if pivot is not None:
                        refs.append(_pivot_reference("1W", 2, pivot,
                            weekly.completed_weekly_bars, weekly.observation_boundary))
    gaps.extend(p.timeframe + "_PIVOT_CONFIRMATION_UNAVAILABLE" for p in refs if p.confirmation is None)
    if assessment.operative_anchor is None:
        gaps.append("OPERATIVE_ANCHOR_UNAVAILABLE")
    return QualificationEvidence(snapshot.run_identity, assessment.result_sha256, mtf_sha,
        snapshot.observed_at, (assessment.policy_identity, assessment.policy_version),
        tuple(boundaries), tuple(sorted(fps.items())), tuple(candles), tuple(history), tuple(refs),
        assessment.operative_anchor, tuple(sorted(set(gaps))))


def _pivot_reference(tf, radius, pivot, bars, boundary):
    matches = [n for n, bar in enumerate(bars)
               if getattr(bar, "source_timestamp", getattr(bar, "source_start", None)) == pivot.timestamp
               and getattr(bar, "high" if pivot.kind.value == "HIGH" else "low") == pivot.value]
    confirmation = None
    if len(matches) == 1:
        n = matches[0]
        if n >= radius and n + radius < len(bars):
            window = bars[n - radius:n + radius + 1]
            if (all(b.observation_boundary <= boundary for b in window)
                    and all(a.observation_boundary <= getattr(b, "source_timestamp", getattr(b, "source_start", None))
                            for a, b in zip(window, window[1:]))):
                confirmation = bars[n + radius].observation_boundary
    return CausalPivotReference(tf, radius, pivot.kind.value, pivot.value, pivot.timestamp, confirmation)


def _qualification_boundary(current, old, previous, instrument):
    """Prove only one adjacent, retained, completed transition; no replay.

    An initial snapshot, a skipped bar, newly downloaded older history, multiple
    changed dependencies, or a correction cannot establish an earlier event.
    """
    if (current.gaps or old is None or old.qualification is None or previous is None
            or old.reason is not None or old.qualification.current.gaps
            or previous.status not in {native.NativeDiscoveryStatus.FORMING_WATCH,
                                       native.NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY}):
        return None
    prior = old.qualification.current
    changed = [tf for tf, digest in current.fingerprints if dict(prior.fingerprints).get(tf) != digest]
    if len(changed) != 1 or current.policy != prior.policy:
        return None
    tf = changed[0]
    bars = (instrument.nse_weekly_foundation.completed_weekly_bars if tf == "1W"
            else instrument.completed_bars(FactualTimeframe(tf)))
    boundary = dict(current.boundaries)[tf]
    retained_history = next((count, digest) for name, count, digest in prior.history if name == tf)
    if (len(bars) < 2 or _candle_fingerprint(bars[-2]) != dict(prior.candles).get(tf)
            or retained_history != (len(bars) - 1, _digest(tuple(_candle_fingerprint(b) for b in bars[:-1])))
            or bars[-2].observation_boundary != getattr(bars[-1], "source_timestamp", getattr(bars[-1], "source_start", None))
            or not old.last_analysis_checked < boundary <= current.observed_at
            or boundary != max(b for _, b in current.boundaries)
            or any(p.confirmation is None or p.confirmation > boundary for p in current.pivots)):
        return None
    return boundary


def _prepare_qualification(snapshot, instrument, assessment, fps, row, old, previous, mtf_sha):
    current = _causal_evidence(snapshot, instrument, assessment, fps, mtf_sha)
    retained = None if old is None else old.qualification
    origin = None if retained is None else retained.origin
    reason = row.reason
    if current.gaps:
        reason = reason or "QUALIFICATION_CAUSAL_EVIDENCE_UNAVAILABLE"
    if row.opportunity_id is not None and row.origin_run == snapshot.run_identity:
        boundary = _qualification_boundary(current, old, previous, instrument)
        origin = QualificationOrigin(row.opportunity_id, row.material_revision, current,
            boundary, row.first_admitted, "EXACT_COMMITTED_PREDECESSOR_TRANSITION" if boundary is not None
            else "FIRST_RETAINED_DETECTION_EARLIER_QUALIFICATION_NOT_ESTABLISHED")
    elif row.opportunity_id is not None and origin is None:
        # Read old companions without migrating or backfilling their history.
        reason = reason or "QUALIFICATION_HISTORY_UNAVAILABLE"
    validity = ("MANUAL_REVIEW_REQUIRED" if reason else "VALID" if
                assessment.status is native.NativeDiscoveryStatus.PROBABLE else "NOT_CURRENTLY_QUALIFIED")
    corrections = () if retained is None else retained.corrections
    if retained is not None and origin is not None:
        prior = retained.current
        corrected = tuple(tf for tf, digest in current.fingerprints
            if dict(prior.fingerprints).get(tf) != digest
            and dict(prior.boundaries).get(tf) == dict(current.boundaries).get(tf))
        if corrected:
            support = ("UNRESOLVED" if reason else "SUPPORTED" if validity == "VALID" else "NOT_SUPPORTED")
            corrections += (QualificationCorrection(prior.run, prior.assessment, current, corrected, support),)
    return QualificationRecord(origin, current, validity, reason, corrections)


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
    qualification: QualificationRecord | None = None


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
            _validate_qualification(row, assessment, self)
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
            "mtf_sha256": bundle.mtf_sha256, "rows": tuple(_row_material(r) for r in bundle.rows)}


def _row_material(row):
    value = asdict(row)
    if row.qualification is None:
        # Preserve historical WO-04 bytes and integrity hashes exactly.
        del value["qualification"]
    return value


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
    mtf_sha = _digest(snapshot)

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
        row = ContinuityRow(instrument.canonical_instrument, binding, disposition, reason,
                                 opportunity, origin_run, origin_assessment, first_admitted, revision,
                                 material, old.latest_material_at if same else max(
                                     f.observation_boundary for f in instrument.timeframes
                                     if instrument.exchange == "NSE" or f.timeframe is not FactualTimeframe.WEEKLY),
                                 checked_at, same, tuple(memos))
        rows.append(replace(row, qualification=_prepare_qualification(
            snap, instrument, assessment, fps, row, old, previous, mtf_sha)))
        return assessment

    previous_run = (adopted_predecessor.native if adopted_predecessor is not None else
                    None if prior is None else prior.native_run)
    run = native.discover_native_mtf(snapshot, previous_run,
                                    daily_control, assessment_builder=build)
    result = PreparedContinuity(run, mtf_sha, tuple(rows), "")
    return replace(result, integrity_sha256=_digest(_material(result))).validate()


def _anchor(value):
    return None if value is None else native.NativeAnchor(native.NativeAnchorType(value["anchor_type"]),
                                                        value["price"], datetime.fromisoformat(value["source_boundary"]))


def _shape(value, cls):
    if type(value) is not dict or set(value) != {f.name for f in fields(cls)}:
        raise ValueError("SWING_QUALIFICATION_SHAPE_INVALID")
    return dict(value)


def _qualification_evidence(value):
    v = _shape(value, QualificationEvidence)
    v["observed_at"] = datetime.fromisoformat(v["observed_at"])
    v["policy"] = tuple(v["policy"])
    v["boundaries"] = tuple((tf, datetime.fromisoformat(t)) for tf, t in v["boundaries"])
    for key in ("fingerprints", "candles"):
        v[key] = tuple(tuple(pair) for pair in v[key])
    v["history"] = tuple(tuple(item) for item in v["history"])
    refs = []
    for p in v["pivots"]:
        p = _shape(p, CausalPivotReference)
        p["centre"] = datetime.fromisoformat(p["centre"])
        p["confirmation"] = None if p["confirmation"] is None else datetime.fromisoformat(p["confirmation"])
        refs.append(CausalPivotReference(**p))
    v["pivots"] = tuple(refs)
    v["anchor"] = _anchor(v["anchor"])
    v["gaps"] = tuple(v["gaps"])
    return QualificationEvidence(**v)


def _qualification_record(value):
    v = _shape(value, QualificationRecord)
    v["current"] = _qualification_evidence(v["current"])
    if v["origin"] is not None:
        origin = _shape(v["origin"], QualificationOrigin)
        origin["evidence"] = _qualification_evidence(origin["evidence"])
        origin["first_detected"] = datetime.fromisoformat(origin["first_detected"])
        origin["boundary"] = None if origin["boundary"] is None else datetime.fromisoformat(origin["boundary"])
        v["origin"] = QualificationOrigin(**origin)
    corrections = []
    for item in v["corrections"]:
        item = _shape(item, QualificationCorrection)
        item["evidence"] = _qualification_evidence(item["evidence"])
        item["timeframes"] = tuple(item["timeframes"])
        corrections.append(QualificationCorrection(**item))
    v["corrections"] = tuple(corrections)
    return QualificationRecord(**v)


def _validate_qualification(row, assessment, bundle):
    q = row.qualification
    if q is None:
        return  # Legacy contract, no invented origin or migration.
    error = "SWING_QUALIFICATION_BINDING_INVALID"
    if (type(q) is not QualificationRecord
            or q.validity not in {"VALID", "NOT_CURRENTLY_QUALIFIED", "MANUAL_REVIEW_REQUIRED"}
            or (q.validity == "MANUAL_REVIEW_REQUIRED") != (q.reason is not None)
            or q.current.run != bundle.native_run.run_identity
            or q.current.assessment != assessment.result_sha256
            or q.current.mtf != bundle.mtf_sha256
            or q.current.observed_at != bundle.native_run.observed_at
            or q.current.anchor != assessment.operative_anchor
            or (q.validity == "VALID" and assessment.status is not native.NativeDiscoveryStatus.PROBABLE)
            or ((q.current.gaps or row.reason) and q.validity != "MANUAL_REVIEW_REQUIRED")):
        raise ValueError(error)
    expected_tf = {"1D", "4H", "1H"}
    if assessment.weekly_state is not native.Native1WState.NOT_APPLICABLE:
        expected_tf.add("1W")
    evidence = [q.current]
    if q.origin is not None:
        o = q.origin
        evidence.append(o.evidence)
        if (o.opportunity != row.opportunity_id or o.evidence.run != row.origin_run
                or o.evidence.assessment != row.origin_assessment or o.first_detected != row.first_admitted
                or o.first_detected < o.evidence.observed_at or o.first_detected > row.last_analysis_checked
                or not o.material_revision.startswith("SWMR-") or not _hash_valid(o.material_revision[5:])
                or (o.boundary is None) != (o.attribution == "FIRST_RETAINED_DETECTION_EARLIER_QUALIFICATION_NOT_ESTABLISHED")
                or o.attribution not in {"FIRST_RETAINED_DETECTION_EARLIER_QUALIFICATION_NOT_ESTABLISHED",
                                         "EXACT_COMMITTED_PREDECESSOR_TRANSITION"}
                or (o.boundary is not None and (o.evidence.gaps or o.boundary > o.evidence.observed_at
                    or o.boundary != max(t for _, t in o.evidence.boundaries)
                    or any(p.confirmation is None or p.confirmation > o.boundary for p in o.evidence.pivots)))):
            raise ValueError(error)
        if row.origin_run == bundle.native_run.run_identity and (
                o.evidence != q.current or assessment.status is not native.NativeDiscoveryStatus.PROBABLE):
            raise ValueError(error)
    elif row.opportunity_id is not None and q.validity != "MANUAL_REVIEW_REQUIRED":
        raise ValueError(error)
    if len({item.evidence.run for item in q.corrections}) != len(q.corrections):
        raise ValueError(error)
    for item in q.corrections:
        evidence.append(item.evidence)
        if (q.origin is None or not native.is_swing_analysis_run_id(item.previous_run)
                or not _hash_valid(item.previous_assessment) or not item.timeframes
                or not set(item.timeframes) <= {"1D", "4H", "1H", "1W"}
                or item.support not in {"SUPPORTED", "NOT_SUPPORTED", "UNRESOLVED"}
                or item.evidence.observed_at > q.current.observed_at):
            raise ValueError(error)
    for e in evidence:
        if (not native.is_swing_analysis_run_id(e.run)
                or not _hash_valid(e.assessment) or not _hash_valid(e.mtf)
                or len(e.policy) != 2 or not all(isinstance(p, str) for p in e.policy)
                or e.observed_at.utcoffset() is None
                or len(dict(e.boundaries)) != len(e.boundaries)
                or not {"1D", "4H", "1H"} <= set(dict(e.boundaries)) <= {"1D", "4H", "1H", "1W"}
                or any(t.utcoffset() is None or t > e.observed_at for _, t in e.boundaries)
                or set(dict(e.candles)) != set(dict(e.boundaries))
                or {tf for tf, _, _ in e.history} != set(dict(e.boundaries))
                or len(e.history) != len(e.boundaries)
                or any(type(count) is not int or count < 1 or not _hash_valid(digest) for _, count, digest in e.history)
                or set(dict(e.fingerprints)) != expected_tf
                or any(not _hash_valid(h) for _, h in (*e.candles, *e.fingerprints))):
            raise ValueError(error)
        for p in e.pivots:
            if (p.timeframe not in dict(e.boundaries) or p.radius not in {1, 2}
                    or p.kind not in {"HIGH", "LOW"} or not math.isfinite(p.value)
                    or p.centre.utcoffset() is None
                    or (p.confirmation is not None and (p.confirmation.utcoffset() is None
                        or not p.centre < p.confirmation <= dict(e.boundaries)[p.timeframe]))
                    or (p.confirmation is None and p.timeframe + "_PIVOT_CONFIRMATION_UNAVAILABLE" not in e.gaps)):
                raise ValueError(error)


def stamp_completed_contribution(prepared, completed_at):
    """Publication owner supplies completion after the full analysis is built."""
    prepared.validate()
    if completed_at.utcoffset() is None or completed_at < prepared.native_run.observed_at:
        raise ValueError("SWING_CONTINUITY_TIMESTAMP_INVALID")
    rows = []
    for row in prepared.rows:
        qualification = row.qualification
        if qualification is not None and qualification.origin is not None and row.origin_run == prepared.native_run.run_identity:
            qualification = replace(qualification, origin=replace(qualification.origin, first_detected=completed_at))
        rows.append(replace(row, last_analysis_checked=completed_at, qualification=qualification,
            first_admitted=(completed_at if row.origin_run == prepared.native_run.run_identity else row.first_admitted)))
    result = replace(prepared, rows=tuple(rows), integrity_sha256="")
    return replace(result, integrity_sha256=_digest(_material(result))).validate()


def _row(value):
    names = {f.name for f in fields(ContinuityRow)}
    if set(value) not in (names, names - {"qualification"}):
        raise ValueError("SWING_CONTINUITY_ROW_INVALID")
    value = dict(value)
    if "qualification" in value:
        value["qualification"] = _qualification_record(value["qualification"])
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
