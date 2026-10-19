"""Pure NSE local research input/result boundary. No stores, clocks or acquisition.

Source authenticity and currentness remain the canonical caller's responsibility.
A content hash detects change; it cannot authenticate a self-consistent forgery.
LOCAL-02 must independently obtain/recheck expected_source before publication.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
import math
import re

from kronos.swing.run_identity import is_swing_analysis_run_id
from kronos.swing.v1.mtf_facts import (
    CompletedTimeframeBar, FactualTimeframe, _completed_bar, _one_hour_atr,
)
from kronos.swing.v1.native_discovery import NativeDiscoveryStatus
from kronos.swing.v1.nse_technical_summary import build_nse_technical_summary

INPUT_CONTRACT = "KRONOS-SWING-NSE-LOCAL-INPUT-V1"
RESULT_CONTRACT = "KRONOS-SWING-NSE-LOCAL-RESULT-V1"
VERSION = "1.0"
TIMEFRAMES = ("1W", "1D", "4H", "1H")
MAX_INPUT_BYTES = 16 * 1024 * 1024


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value) -> str:
    return sha256(canonical(value)).hexdigest()


def require(ok, reason="NSE_LOCAL_INPUT_INVALID") -> None:
    if not ok:
        raise ValueError(reason)


def closed(value, keys) -> None:
    require(type(value) is dict and set(value) == set(keys))


def _decode(raw):
    require(type(raw) is str and len(raw.encode("utf-8")) <= MAX_INPUT_BYTES)
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, "NSE_LOCAL_DUPLICATE_KEY")
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: require(False))


@dataclass(frozen=True, slots=True)
class SourceBinding:
    """Expected exact source, obtained independently by the canonical caller."""
    input_sha256: str
    run_identity: str
    publication_sha256: str
    instrument: str
    assessment_sha256: str
    requirement_sha256: str
    provider_source_identity: str
    information_cutoff: str

    def __post_init__(self):
        for field in (self.input_sha256, self.publication_sha256,
                      self.assessment_sha256, self.requirement_sha256):
            _hash(field)
        require(type(self.run_identity) is str and is_swing_analysis_run_id(self.run_identity))
        _text(self.instrument)
        require(re.fullmatch(r"[A-Z0-9&._ -]{1,64}", self.instrument) is not None)
        require(type(self.provider_source_identity) is str and
                re.fullmatch(r"KITE-MTF-FACTS-[0-9a-f]{64}", self.provider_source_identity) is not None)
        _time(self.information_cutoff)


@dataclass(frozen=True, slots=True)
class LocalAnalysisInput:
    evidence_json: str
    identity: str

    def to_dict(self) -> dict:
        return _decode(self.evidence_json)

    def to_json(self) -> str:
        return canonical(dict(identity=self.identity, evidence=self.to_dict())).decode()

    @property
    def binding(self) -> SourceBinding:
        body = self.to_dict()
        fields = {k: body["binding"][k] for k in (
            "run_identity", "publication_sha256", "instrument", "assessment_sha256",
            "requirement_sha256", "provider_source_identity")}
        return SourceBinding(self.identity, **fields, information_cutoff=body["information_cutoff"])


@dataclass(frozen=True, slots=True)
class LocalAnalysisResult:
    payload_json: str
    identity: str

    def to_dict(self) -> dict:
        return _decode(self.payload_json)

    def to_json(self) -> str:
        return canonical(dict(identity=self.identity, result=self.to_dict())).decode()


def _time(value):
    from datetime import datetime
    require(type(value) is str)
    parsed = datetime.fromisoformat(value)
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None)
    return parsed


def _text(value):
    require(type(value) is str and bool(value.strip()) and value == value.strip()
            and len(value) <= 512 and not any(ord(c) < 32 for c in value))


def _hash(value):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None)


def _source_json(value):
    from dataclasses import asdict, is_dataclass
    from kronos.swing.v1.mtf_facts import _json_value
    return _json_value(asdict(value) if is_dataclass(value) else value)


def _source_fact(raw):
    # Restore through the existing MTF owner; round-trip equality rejects fields
    # its backwards-compatible reader would otherwise ignore or default.
    from kronos.swing.v1.mtf_facts import _timeframe
    fact = _timeframe(raw)
    require(canonical(raw) == canonical(_source_json(fact)))
    for value in (fact.calendar_identity, fact.calendar_version, fact.session_identity,
                  fact.source_provider_identity, *fact.provenance):
        _text(value)
    if fact.moving_averages is not None:
        fact.moving_averages.__post_init__()
    if fact.volume_facts is not None:
        fact.volume_facts.__post_init__()
    for measured in fact.structural_measurements:
        measured.__post_init__()
        for level in (*measured.swing_highs, *measured.swing_lows):
            level.__post_init__()
            require(level.timestamp <= fact.observation_boundary)
    return fact


def _source_thesis(raw, facts, binding, cutoff):
    from dataclasses import fields
    from kronos.swing.v1.native_discovery import (
        Native1WState, Native1DState, Native4HState, Native1HState,
        NativeProductPath, NativeContextKind, NativeOpportunityIdentity,
    )
    from kronos.swing.v1.models import V1Direction
    from kronos.swing.v1.native_review import NativeReviewThesis, _primitive, _timeframe_fact
    closed(raw, (f.name for f in fields(NativeReviewThesis)))
    values = dict(raw)
    for key, kind in (("direction", V1Direction), ("product_path", NativeProductPath),
                      ("context_kind", NativeContextKind), ("opportunity_identity", NativeOpportunityIdentity),
                      ("weekly_state", Native1WState), ("daily_state", Native1DState),
                      ("four_hour_state", Native4HState), ("one_hour_state", Native1HState)):
        require(type(values[key]) is str)
        values[key] = kind(values[key])
    values["operative_anchor_boundary"] = _time(raw["operative_anchor_boundary"])
    values["timeframe_facts"] = tuple(_timeframe_fact(fact) for fact in facts)
    for key in ("provider_provenance", "calendar_provenance"):
        require(type(raw[key]) is list and bool(raw[key]))
        for item in raw[key]: _text(item)
        values[key] = tuple(raw[key])
    thesis = NativeReviewThesis(**values)
    require(canonical(raw) == canonical(_primitive(thesis)))
    require(thesis.product_path is NativeProductPath.NSE
            and thesis.native_run_identity == binding["run_identity"]
            and thesis.native_assessment_sha256 == binding["assessment_sha256"]
            and thesis.canonical_instrument == binding["instrument"]
            and thesis.direction.value == binding["direction"]
            and thesis.operative_anchor_boundary <= cutoff)
    for item in (thesis.operative_anchor_identity, thesis.native_policy_identity, thesis.native_policy_version):
        _text(item)
    # Exactly the existing NSE requirement identity, without rerunning Native.
    require(sha256(json.dumps({"thesis": raw, "mcx_reference": None},
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            == binding["requirement_sha256"])
    return thesis


def _summary(binding, cutoff, facts, thesis, atr):
    from kronos.swing.v1.nse_technical_summary import _number, _relation
    frames = []
    contexts = (thesis.weekly_state, thesis.daily_state, thesis.four_hour_state, thesis.one_hour_state)
    from kronos.swing.v1.native_review import _timeframe_fact
    for fact, context in zip(facts, contexts):
        retained = _timeframe_fact(fact)
        values = {key: _number(getattr(retained, key)) for key in ("open", "high", "low", "close")}
        values["volume"] = _number(retained.volume, integer=True)
        comparisons = {}
        for period in (20, 50, 200):
            current, prior = getattr(retained, f"sma{period}"), getattr(retained, f"prior_sma{period}_5bars")
            values[f"sma{period}"] = None if current is None else _number(current)
            values[f"prior_sma{period}_5bars"] = None if prior is None else _number(prior)
            comparisons[f"close_sma{period}"] = _relation(values["close"], current,
                ("BELOW", "EQUAL", "ABOVE"), f"SMA{period}_UNAVAILABLE")
            comparisons[f"sma{period}_change"] = _relation(current, prior,
                ("FALLING", "UNCHANGED", "RISING"), f"SMA{period}_HISTORY_UNAVAILABLE")
        mean = retained.prior_20_volume_mean
        values["prior_20_volume_mean"] = None if mean is None else _number(mean)
        comparisons["volume_reference"] = _relation(values["volume"], mean,
            ("BELOW", "EQUAL", "ABOVE"), "VOLUME_REFERENCE_UNAVAILABLE")
        comparisons["candle_direction"] = _relation(values["close"], values["open"],
            ("DOWN", "UNCHANGED", "UP"), "CANDLE_UNAVAILABLE")
        frames.append(dict(timeframe=fact.timeframe.value, context=context.value,
            observed_boundary=fact.observation_boundary.isoformat(), source_timestamp=fact.source_timestamp.isoformat(),
            values=values, comparisons=comparisons, calendar_identity=fact.calendar_identity,
            calendar_version=fact.calendar_version, session_identity=fact.session_identity,
            provider_identity=fact.source_provider_identity, provenance=list(fact.provenance),
            visual={q:dict(state="UNKNOWN", reason="METHOD_NOT_APPROVED") for q in ("Q3", "Q5", "Q10")}))
    atr_view = dict(state="UNAVAILABLE", value=None, reason="ATR14_NOT_RETAINED")
    if atr is not None:
        atr_view = dict(state=atr.availability.value, value=atr.value, reason=atr.unavailable_reason,
            integrity_sha256=atr.integrity_sha256, analysis_boundary=atr.analysis_boundary.isoformat(),
            observed_boundary=atr.observation_boundary.isoformat(),
            source_timestamp=atr.source_market_data_boundary.isoformat(), provenance=list(atr.provenance))
    missing = sum(v["state"] == "UNAVAILABLE" for frame in frames for v in frame["comparisons"].values())
    return dict(schema="KRONOS-SWING-NSE-TECHNICAL-SUMMARY-V1", version="1.0",
        authority="FACTUAL_EXPLANATORY_ONLY", independence="NOT_ESTABLISHED", binding=binding,
        analysis_time=cutoff, coverage="PARTIAL" if missing or atr_view["state"] != "AVAILABLE" else "COMPLETE",
        frames=frames, atr=atr_view)


def _validate_body(body):
    closed(body, ("contract", "version", "binding", "information_cutoff",
                  "native_observed_at", "summary", "source_evidence"))
    require(body["contract"] == INPUT_CONTRACT and body["version"] == VERSION)
    binding = body["binding"]
    closed(binding, ("run_identity", "publication_sha256", "instrument", "direction",
                     "assessment_sha256", "requirement_sha256", "provider_source_identity"))
    SourceBinding(digest(body), **{k: v for k, v in binding.items() if k != "direction"},
                  information_cutoff=body["information_cutoff"])
    require(type(binding["direction"]) is str and binding["direction"] in ("LONG", "SHORT"))
    cutoff = _time(body["information_cutoff"])
    # Capture may follow market cutoff. It never expands the permitted information set.
    require(_time(body["native_observed_at"]) >= cutoff)
    source = body["source_evidence"]
    closed(source, ("thesis", "timeframes", "completed_series", "atr"))
    require(type(source["timeframes"]) is list and len(source["timeframes"]) == 4)
    facts = tuple(_source_fact(raw) for raw in source["timeframes"])
    require(tuple(f.timeframe.value for f in facts) == TIMEFRAMES)
    for fact in facts:
        require(fact.source_timestamp < fact.observation_boundary <= cutoff
                and fact.source_timestamp <= fact.source_market_data_boundary <= cutoff)
        require(fact.source_interval == ("DAY" if fact.timeframe.value in ("1W", "1D") else "60minute"))
        ma = fact.moving_averages
        if ma is not None:
            for period in (20, 50, 200):
                for prefix, minimum in (("sma", period), ("prior_sma", period + 5)):
                    name = f"{prefix}{period}" + ("_5bars" if prefix == "prior_sma" else "")
                    value = getattr(ma, name)
                    require(value is None or value >= 0 and ma.completed_count >= minimum)
        if fact.volume_facts is not None:
            require(fact.volume_facts.current == fact.volume)
        for series in fact.structural_measurements:
            for levels in (series.swing_highs, series.swing_lows):
                require(all(p.value > 0 and p.timestamp <= fact.observation_boundary for p in levels))
                require(all(a.timestamp < b.timestamp and a.candle_index < b.candle_index
                            for a, b in zip(levels, levels[1:])))
    thesis = _source_thesis(source["thesis"], facts, binding, cutoff)
    require(type(source["completed_series"]) is list and len(source["completed_series"]) == 4)
    history = {}
    for fact, row in zip(facts, source["completed_series"]):
        closed(row, ("timeframe", "bars"))
        require(row["timeframe"] == fact.timeframe.value and type(row["bars"]) is list
                and 1 <= len(row["bars"]) <= 10000)
        bars = tuple(_completed_bar(raw) for raw in row["bars"])
        for raw, bar in zip(row["bars"], bars):
            require(canonical(raw) == canonical(_source_json(bar)))
            require(bar.timeframe is fact.timeframe
                    and bar.source_timestamp <= bar.source_market_data_boundary <= cutoff
                    and bar.observation_boundary <= cutoff)
            for key in ("exchange_timezone", "source_interval", "source_provider_identity"):
                require(getattr(bar, key) == getattr(fact, key))
            for text in (bar.calendar_identity, bar.calendar_version, bar.session_identity, *bar.provenance):
                _text(text)
        require(all(a.observation_boundary < b.observation_boundary and a.source_timestamp < b.source_timestamp
                    for a, b in zip(bars, bars[1:])))
        require(bars[-1] == CompletedTimeframeBar.from_fact(fact))
        history[fact.timeframe.value] = bars
        # Consistency proof only: keep the owner facts, never replace or fill
        # them. Use the owner's exact arithmetic on a fully retained window.
        ma = fact.moving_averages
        if ma is not None:
            require(ma.completed_count >= len(bars))
            for period in (20, 50, 200):
                for name, offset in ((f"sma{period}", 0), (f"prior_sma{period}_5bars", 5)):
                    supplied = getattr(ma, name)
                    if supplied is not None and len(bars) >= period + offset:
                        window = bars[-period:] if not offset else bars[-period-offset:-offset]
                        require(supplied == math.fsum(bar.close for bar in window) / period)
        volume = fact.volume_facts
        if volume is not None and volume.prior_20_mean is not None and len(bars) >= 21:
            require(volume.prior_20_mean == math.fsum(bar.volume for bar in bars[-21:-1]) / 20)
    atr = None if source["atr"] is None else _one_hour_atr(source["atr"])
    if atr is not None:
        hourly = facts[-1]
        require(canonical(source["atr"]) == canonical(_source_json(atr)))
        require(atr.run_identity == binding["run_identity"] and atr.canonical_instrument == binding["instrument"]
                # The canonical owner may retain an earlier analytical/session
                # anchor than the completed 1H boundary. They are distinct clocks.
                and atr.analysis_boundary <= cutoff
                and atr.observation_boundary == hourly.observation_boundary
                and atr.source_market_data_boundary == hourly.source_market_data_boundary)
        for key in ("calendar_identity", "calendar_version", "session_identity", "source_provider_identity"):
            require(getattr(atr, key) == getattr(hourly, key))
        hourly_history = history["1H"]
        require(atr.completed_candle_count >= len(hourly_history))
        if atr.value is not None and len(hourly_history) >= 15:
            window = hourly_history[-15:]
            true_ranges = [max(bar.high - bar.low, abs(bar.high - prior.close),
                               abs(bar.low - prior.close)) for prior, bar in zip(window, window[1:])]
            require(atr.value == math.fsum(true_ranges) / 14)
    summary = _summary(binding, body["information_cutoff"], facts, thesis, atr)
    require(canonical(body["summary"]) == canonical(summary))
    return summary, facts, history, atr


def _source_references(body):
    """Resolve every methodology alias to an exact immutable input JSON pointer."""
    references = {}
    def add(alias, pointer, value, tf):
        references[alias] = dict(input_pointer=pointer, value=value, timeframe=tf)
    source = body["source_evidence"]
    for index, fact in enumerate(source["timeframes"]):
        tf = fact["timeframe"]
        prefix = f"/source_evidence/timeframes/{index}"
        for key in ("open", "high", "low", "close", "volume"):
            add(f"frames.{tf}.{key}", f"{prefix}/{key}", fact[key], tf)
        for period in (20, 50, 200):
            for key in (f"sma{period}", f"prior_sma{period}_5bars"):
                ma = fact["moving_averages"]
                # A missing optional owner record has an exact null address.
                pointer = f"{prefix}/moving_averages" + (f"/{key}" if ma is not None else "")
                add(f"frames.{tf}.{key}", pointer, None if ma is None else ma[key], tf)
        volume = fact["volume_facts"]
        add(f"frames.{tf}.prior_20_volume_mean", f"{prefix}/volume_facts" +
            ("/prior_20_mean" if volume is not None else ""),
            None if volume is None else volume["prior_20_mean"], tf)
        for series_index, series in enumerate(fact["structural_measurements"]):
            for alias, key in (("highs", "swing_highs"), ("lows", "swing_lows")):
                for pivot_index, pivot in enumerate(series[key]):
                    add(f"frames.{tf}.structure.radius_{series['radius']}.{alias}[{pivot_index}].value",
                        f"{prefix}/structural_measurements/{series_index}/{key}/{pivot_index}/value",
                        pivot["value"], tf)
        for bar_index, bar in enumerate(source["completed_series"][index]["bars"]):
            add(f"history.{tf}[{bar_index}].close",
                f"/source_evidence/completed_series/{index}/bars/{bar_index}/close", bar["close"], tf)
    atr = source["atr"]
    add("atr.1H.value", "/source_evidence/atr" + ("/value" if atr is not None else ""),
        None if atr is None else atr["value"], "1H")
    return references


def validate_input(value: LocalAnalysisInput) -> LocalAnalysisInput:
    """Strict structural/temporal/derivation validation, not source authentication."""
    try:
        require(type(value) is LocalAnalysisInput)
        _hash(value.identity)
        body = value.to_dict()
        require(value.identity == digest(body) and value.evidence_json == canonical(body).decode())
        _validate_body(body)
        return value
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError("NSE_LOCAL_INPUT_INVALID") from error


def decode_input(raw: str) -> LocalAnalysisInput:
    wrapper = _decode(raw)
    closed(wrapper, ("identity", "evidence"))
    return validate_input(LocalAnalysisInput(canonical(wrapper["evidence"]).decode(), wrapper["identity"]))


def build_local_input(requirement, native, facts, publication_sha256: str) -> LocalAnalysisInput:
    """Bind exact eligible owner records without rerunning discovery or acquisition.

    Callers must obtain these objects through existing owners and final-currentness
    fences. Their consistency and exact consumed bytes are retained; hashes alone
    never establish that an untrusted object is a published source.
    """
    summary = build_nse_technical_summary(requirement, native, facts, publication_sha256)
    native.__post_init__()
    facts.__post_init__()
    assessment = next(a for a in native.assessments if a.canonical_instrument == requirement.canonical_instrument)
    require(assessment.status is NativeDiscoveryStatus.PROBABLE)
    # Use the existing owner's pure eligibility check; do not change its decisions.
    from kronos.swing.v1.native_review import build_native_review_requirements, _primitive
    require(requirement in build_native_review_requirements(native, facts))
    instrument = facts.instrument(requirement.canonical_instrument)
    instrument.__post_init__()
    source = dict(thesis=_primitive(requirement.thesis),
        timeframes=[_source_json(f) for f in instrument.timeframes],
        completed_series=[dict(timeframe=f.timeframe.value,
            bars=[_source_json(CompletedTimeframeBar.from_fact(b))
                  if type(b) is not CompletedTimeframeBar else _source_json(b)
                  for b in instrument.completed_bars(f.timeframe)]) for f in instrument.timeframes],
        atr=_source_json(instrument.one_hour_atr))
    body = dict(contract=INPUT_CONTRACT, version=VERSION, binding=summary["binding"],
        information_cutoff=facts.observed_at.isoformat(), native_observed_at=native.observed_at.isoformat(),
        summary=summary, source_evidence=source)
    return validate_input(LocalAnalysisInput(canonical(body).decode(), digest(body)))


def analyze_local(value: LocalAnalysisInput, *, expected_source: SourceBinding) -> LocalAnalysisResult:
    """Deterministic research only. No clock, store, model, Provider or transport."""
    validate_input(value)
    require(type(expected_source) is SourceBinding, "NSE_LOCAL_EXPECTED_SOURCE_REQUIRED")
    expected_source.__post_init__()
    require(value.binding == expected_source, "NSE_LOCAL_SOURCE_STALE")
    body = value.to_dict()
    summary, facts, history, atr = _validate_body(body)
    from kronos.swing.v1.nse_local_methodology import METHOD_VERSION, method_parameters, derive_thesis
    thesis = derive_thesis(summary, facts, history, atr, body["binding"]["direction"])
    result = dict(contract=RESULT_CONTRACT, version=VERSION, method_version=METHOD_VERSION,
        parameter_sha256=digest(method_parameters()), binding=body["binding"], input_sha256=value.identity,
        information_cutoff=body["information_cutoff"], native_observed_at=body["native_observed_at"],
        summary=summary, thesis=thesis, source_references=_source_references(body),
        authority="RESEARCH_ONLY_NO_ADMISSION_OR_EXECUTION",
        visual={q: "UNKNOWN" for q in ("Q3", "Q5", "Q10")},
        currentness="SOURCE_MATCH_AT_CALL_NOT_LIVE_CERTIFICATION")
    return LocalAnalysisResult(canonical(result).decode(), digest(result))


def validate_result(result: LocalAnalysisResult, value: LocalAnalysisInput, *, expected_source: SourceBinding) -> LocalAnalysisResult:
    """Validate immutable replay by deriving the complete result again locally."""
    require(type(result) is LocalAnalysisResult, "NSE_LOCAL_RESULT_INVALID")
    expected = analyze_local(value, expected_source=expected_source)
    require(result == expected, "NSE_LOCAL_RESULT_INVALID")
    return result


def decode_result(raw: str, value: LocalAnalysisInput, *, expected_source: SourceBinding) -> LocalAnalysisResult:
    wrapper = _decode(raw)
    closed(wrapper, ("identity", "result"))
    return validate_result(LocalAnalysisResult(canonical(wrapper["result"]).decode(), wrapper["identity"]),
                           value, expected_source=expected_source)
