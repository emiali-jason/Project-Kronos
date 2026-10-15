"""TE01 / TE-RQ-001/002: exact identities and lossless external evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
import re

from kronos.instrument.active_derivative import ACTIVE_DERIVATIVE_FAMILY_MAPPINGS

SUBJECTS = ("GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS")
CANONICAL = {provider: canonical for _, canonical, provider in ACTIVE_DERIVATIVE_FAMILY_MAPPINGS}
TARGET = "OPTION_EXPIRY_UNDERLYING_SETTLEMENT_REFERENCE"
VERSION = "1.0.0"
PROSPECTIVE_VERSION = "2.0.0"
QUESTION_SCHEMA = "KRONOS-THETA-QUESTION-V1"
ANSWER_SCHEMA = "KRONOS-THETA-ANSWER-V1"
MAX_JSON_BYTES = 2 * 1024 * 1024
CLASSIFICATIONS = ("FACT", "RESEARCH_RESULT", "HYPOTHESIS")


class ThetaError(ValueError):
    """Controlled code only; never echo an external payload in error text."""


def require(condition: bool, code: str = "THETA_SCHEMA_INVALID") -> None:
    if not condition:
        raise ThetaError(code)


def text(value: object, maximum: int = 16000) -> bool:
    return type(value) is str and bool(value.strip()) and len(value) <= maximum


def stamp(value: object) -> datetime:
    require(type(value) is str and len(value) <= 64, "THETA_TIMESTAMP_INVALID")
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise ThetaError("THETA_TIMESTAMP_INVALID") from None
    require(result.tzinfo is not None and result.utcoffset() is not None,
            "THETA_TIMESTAMP_INVALID")
    return result


def decimal(value: object) -> Decimal:
    # Strings preserve the Analyst's exact decimal representation in the UX.
    require(type(value) is str and len(value) <= 128
            and re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value) is not None,
            "THETA_NUMERIC_INVALID")
    return Decimal(value)


def encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def parse(payload: bytes, *, maximum: int = MAX_JSON_BYTES) -> dict:
    require(type(payload) is bytes and 0 < len(payload) <= maximum)

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "THETA_DUPLICATE_KEY")
            result[key] = value
        return result

    def constant(_):
        raise ThetaError("THETA_NUMERIC_INVALID")

    try:
        result = json.loads(payload.decode("utf-8"), object_pairs_hook=pairs,
                            parse_constant=constant)
    except (UnicodeError, ValueError, RecursionError):
        raise ThetaError("THETA_SCHEMA_INVALID") from None
    require(type(result) is dict)
    return result


def keys(value: object, expected: set[str]) -> None:
    require(type(value) is dict and set(value) == expected)


@dataclass(frozen=True, slots=True)
class ExpiryTarget:
    """Consumed owner evidence, NOT a new DOMAIN-001 selection authority.

    The owner must establish next/second-next eligibility and exact exchange
    mapping. Date ordering and nonempty references are only structural checks.
    No provider token, nearest-contract inference or continuous series is used.
    """

    subject: str
    canonical_subject: str
    horizon: str
    option_expiry: str
    expires_at: str
    underlying_future: str
    futures_expiry: str
    settlement_reference: str
    authority_reference: str
    exchange_evidence_reference: str
    target: str = TARGET

    def __post_init__(self):
        require(self.subject in SUBJECTS and self.canonical_subject == CANONICAL[self.subject])
        require(self.horizon in {"E1", "E2"} and self.target == TARGET)
        try:
            expiry = date.fromisoformat(self.option_expiry)
            future = date.fromisoformat(self.futures_expiry)
        except (TypeError, ValueError):
            raise ThetaError("THETA_TARGET_INVALID") from None
        require(stamp(self.expires_at).date() == expiry and future >= expiry,
                "THETA_TARGET_INVALID")
        require(all(text(v, 1024) for v in (self.underlying_future,
            self.settlement_reference, self.authority_reference,
            self.exchange_evidence_reference)), "THETA_TARGET_AUTHORITY_UNAVAILABLE")


@dataclass(frozen=True, slots=True)
class AuthorityBundle:
    """Explicit dependency supplied only by a commissioned owner adapter.

    There is deliberately no Browser upload, file auto-enrolment, provider call
    or default fabricated bundle. References do not authenticate themselves.
    """

    targets: tuple[ExpiryTarget, ...]
    valid_from: str
    valid_through: str
    methodology_reference: str
    methodology_instructions: str

    def for_subjects(self, subjects: tuple[str, ...], at: datetime) -> list[dict]:
        require(type(self.targets) is tuple and all(type(t) is ExpiryTarget for t in self.targets),
                "THETA_TARGET_AUTHORITY_UNAVAILABLE")
        require(stamp(self.valid_from) <= at <= stamp(self.valid_through),
                "THETA_TARGET_AUTHORITY_STALE")
        require(text(self.methodology_reference, 1024) and text(self.methodology_instructions),
                "THETA_METHODOLOGY_UNAVAILABLE")
        result = []
        for subject in subjects:
            values = sorted((t for t in self.targets if t.subject == subject),
                            key=lambda t: t.horizon)
            require(len(values) == 2 and [t.horizon for t in values] == ["E1", "E2"],
                    "THETA_TARGET_AUTHORITY_UNAVAILABLE")
            require(date.fromisoformat(values[0].option_expiry)
                    < date.fromisoformat(values[1].option_expiry)
                    and all(at < stamp(t.expires_at) for t in values),
                    "THETA_TARGET_AUTHORITY_STALE")
            result.extend(asdict(t) for t in values)
        return result


INSTRUCTIONS = (
    "External Analyst only. Sponsor selects the Astra-Max / Ultra-class model and manually submits this pack. KRONOS does not call the Analyst.",
    "Analyse only independently visible chart evidence using the bound approved methodology. A Sponsor chart label is not independent visual identity proof. Disclose unreadable identity, omitted panels and forming evidence; do not invent indicators or trading rules.",
    "Research commodity-specific global trends: macro, supply/demand, inventories, currency, international commodity markets, seasonality where relevant, geopolitical and scheduled event risks. Distinguish observed facts, defined research results and unvalidated hypotheses.",
    "For each subject return E1 next applicable MCX option expiry and E2 second-next applicable expiry. Copy the exact bound target identities; never guess a future or substitute spot, continuous futures, COMEX/NYMEX or option premium. Disclose conflicting exchange evidence rather than resolving it silently.",
    "Give independent lower, upper and confidence_pct decimal strings for each expiry. Confidence is your stated terminal containment confidence only, NOT calibrated KRONOS probability, profitable selling, OTM, expected return or no-touch probability. No confidence labels or trading recommendations.",
    "Explain chart analysis, global research, supporting and opposing evidence, uncertainty and range reasoning. Supply sources with publication/access timestamps and source references. Preserve analysis T0 and information cutoff. Never use evidence beyond cutoff.",
    "Return EXACTLY one UTF-8 JSON Answer Pack conforming to answer-template.json. Do not return markdown fences, extra keys or null/missing forecasts. Preserve Question identity and chart hashes. Replace required null placeholders; published_at may remain null when unknown. A pack for a subset must include both horizons for every requested subject; it is not a complete five-subject assessment.",
    "If identity, mapping, settlement reference or required evidence is unresolved, do not fabricate an Answer. Report the gap to Sponsor outside the accepted Answer flow. KRONOS will not repair or reinterpret your output.",
)


def answer_template(question: dict) -> dict:
    prospective = question.get("schema_version") == PROSPECTIVE_VERSION
    return {
        "schema_identity": ANSWER_SCHEMA, "schema_version": PROSPECTIVE_VERSION if prospective else VERSION,
        "answer_id": None, "question_id": question["question_id"],
        "question_sha256": digest(encode(question)),
        "analyzed_at": None, "information_cutoff": question["information_cutoff"] if prospective else None,
        "analyst": {"identity": None, "model": None, "provenance": None},
        "forecasts": [{"target": target, "chart_sha256": next(
            c["sha256"] for c in question["charts"] if c["subject"] == target["subject"]),
            "lower": None, "upper": None, "confidence_pct": None,
            "analysis": {name: {"classification": None, "text": None} for name in
                ("chart_analysis", "global_research", "supporting_evidence", "opposing_evidence", "uncertainty", "reasoning")},
            "sources": [{"title": None, "url": None, "published_at": None,
                         "accessed_at": None, "evidence": None,
                         **({"available_at": None} if prospective else {})}]}
            for target in question["targets"]],
    }


def validate_answer(payload: bytes, question: dict, *, received_at: datetime) -> dict:
    version = question.get("schema_version", VERSION)
    require(version in {VERSION, PROSPECTIVE_VERSION})
    prospective = version == PROSPECTIVE_VERSION
    value = parse(payload)
    keys(value, {"schema_identity", "schema_version", "answer_id", "question_id",
                 "question_sha256", "analyzed_at", "information_cutoff", "analyst", "forecasts"})
    require(value["schema_identity"] == ANSWER_SCHEMA and value["schema_version"] == version)
    require(type(value["answer_id"]) is str
            and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value["answer_id"]) is not None)
    require(value["question_id"] == question["question_id"]
            and value["question_sha256"] == digest(encode(question)), "THETA_QUESTION_MISMATCH")
    origin, cutoff = stamp(value["analyzed_at"]), stamp(value["information_cutoff"])
    require(stamp(question["created_at"]) <= origin <= received_at and cutoff <= origin
            and cutoff >= max(stamp(c["information_cutoff"]) for c in question["charts"]),
            "THETA_TIMESTAMP_INVALID")
    if prospective:
        require(value["information_cutoff"] == question["information_cutoff"]
                and stamp(question["information_cutoff"]) == stamp(question["created_at"]),
                "THETA_TIMESTAMP_INVALID")
    keys(value["analyst"], {"identity", "model", "provenance"})
    require(all(text(v, 1024) for v in value["analyst"].values()))
    forecasts = value["forecasts"]
    require(type(forecasts) is list and len(forecasts) == len(question["targets"]),
            "THETA_ANSWER_INCOMPLETE")
    expected = {(t["subject"], t["horizon"]): t for t in question["targets"]}
    seen = set()
    for forecast in forecasts:
        keys(forecast, {"target", "chart_sha256", "lower", "upper", "confidence_pct", "analysis", "sources"})
        target = forecast["target"]
        require(type(target) is dict and type(target.get("subject")) is str
                and type(target.get("horizon")) is str, "THETA_TARGET_MISMATCH")
        identity = target["subject"], target["horizon"]
        require(identity not in seen and expected.get(identity) == target, "THETA_TARGET_MISMATCH")
        seen.add(identity)
        chart = next(c for c in question["charts"] if c["subject"] == target["subject"])
        require(forecast["chart_sha256"] == chart["sha256"], "THETA_CHART_MISMATCH")
        require(origin < stamp(target["expires_at"]) and received_at < stamp(target["expires_at"]),
                "THETA_ANSWER_EXPIRED")
        require(decimal(forecast["lower"]) <= decimal(forecast["upper"]), "THETA_RANGE_INVALID")
        require(Decimal(0) <= decimal(forecast["confidence_pct"]) <= Decimal(100),
                "THETA_CONFIDENCE_INVALID")
        keys(forecast["analysis"], {"chart_analysis", "global_research", "supporting_evidence",
                                   "opposing_evidence", "uncertainty", "reasoning"})
        for statement in forecast["analysis"].values():
            keys(statement, {"classification", "text"})
            require(statement["classification"] in CLASSIFICATIONS and text(statement["text"]))
        sources = forecast["sources"]
        require(type(sources) is list and 1 <= len(sources) <= 100)
        for source in sources:
            keys(source, {"title", "url", "published_at", "accessed_at", "evidence"}
                 | ({"available_at"} if prospective else set()))
            from urllib.parse import urlsplit
            require(all(text(source[k]) for k in ("title", "url", "evidence")))
            url = urlsplit(source["url"])
            require(url.scheme in {"https", "http"} and bool(url.netloc))
            if prospective:
                require(stamp(source["available_at"]) <= cutoff
                        and stamp(source["available_at"]) <= stamp(source["accessed_at"]) <= origin,
                        "THETA_SOURCE_TIME_INVALID")
            else:
                require(stamp(source["accessed_at"]) <= cutoff)
            require(source["published_at"] is None or stamp(source["published_at"]) <= cutoff)
    require(seen == set(expected), "THETA_ANSWER_INCOMPLETE")
    return value
