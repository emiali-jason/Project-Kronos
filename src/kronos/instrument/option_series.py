"""TE-03A additive, exchange-qualified option-series facts (DOMAIN-001).

No Provider input, acquisition, active-futures selection or execution geometry.
Public futures identities reuse ADR-0017's exact canonical naming convention.
The checked-in candidate is NOT an approved publication merely by existing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from functools import wraps
from urllib.parse import urlparse

from kronos.instrument.active_derivative import ACTIVE_DERIVATIVE_FAMILY_MAPPINGS

OPTION_SERIES = "KRONOS-MCX-OPTION-SERIES-PUBLICATION-V1"
SETTLEMENT = "OPTION_EXPIRY_UNDERLYING_SETTLEMENT_REFERENCE"
FAMILIES = {family: (label, subject) for label, subject, family in ACTIVE_DERIVATIVE_FAMILY_MAPPINGS}
QUOTATION_UNITS = {"GOLDM": "INR per 10 grams", "SILVERM": "INR per kilogram",
                   "COPPER": "INR per kilogram", "CRUDEOIL": "INR per barrel",
                   "NATURALGAS": "INR per MMBtu"}
DEFAULT_OPTION_ROOT = Path(__file__).resolve().parents[3] / "data/instruments/mcx_option_series"


class OptionAuthorityError(ValueError):
    """Sanitized failure code, never source content or filesystem details."""


def check(condition, code="OPTION_AUTHORITY_INTEGRITY_INVALID"):
    if not condition:
        raise OptionAuthorityError(code)


def authority_boundary(function):
    """Malformed publications are unavailable, with no incidental exception text."""
    @wraps(function)
    def guarded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except OptionAuthorityError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            raise OptionAuthorityError("OPTION_AUTHORITY_INTEGRITY_INVALID") from None
    return guarded


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def aware(value):
    try:
        result = datetime.fromisoformat(value)
        check(result.tzinfo is not None and result.utcoffset() is not None)
        return result
    except (ValueError, TypeError):
        raise OptionAuthorityError("OPTION_AUTHORITY_TEMPORAL_INVALID") from None


def public_id(value):
    check(type(value) is str and re.fullmatch(r"[A-Z0-9][A-Z0-9_.:/+-]{0,255}", value)
          and not any(s in value for s in ("KITE", "PROVIDER", "BROKER", "TOKEN", "ACCOUNT")))
    return value


def read_exact(root: Path, relative: str, *, expected_sha256=None):
    """Read one explicit artifact; no scanning, mtime, symlink or path fallback."""
    check(root.is_absolute() and root == root.resolve(), "OPTION_AUTHORITY_PATH_INVALID")
    parts = relative.split("/")
    check(all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", p) and p not in {".", ".."}
              for p in parts), "OPTION_AUTHORITY_PATH_INVALID")
    handles = []
    try:
        # The caller supplies an explicit trusted repository root. Every child
        # is opened relative to its retained no-follow directory descriptor.
        handles.append(os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
        for part in parts[:-1]:
            handles.append(os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                   dir_fd=handles[-1]))
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=handles[-1])
        handles.append(fd)
        info = os.fstat(fd)
        check(stat.S_ISREG(info.st_mode), "OPTION_AUTHORITY_PATH_INVALID")
        size = info.st_size
        check(0 < size <= 20 * 1024 * 1024)
        with os.fdopen(os.dup(fd), "rb") as stream:
            payload = stream.read(size + 1)
        check(len(payload) == size)
        if expected_sha256 is not None:
            check(re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is not None
                  and sha256(payload).hexdigest() == expected_sha256,
                  "OPTION_AUTHORITY_SOURCE_INVALID")
        return payload
    except OSError:
        raise OptionAuthorityError("OPTION_AUTHORITY_ARTIFACT_UNAVAILABLE") from None
    finally:
        for fd in reversed(handles):
            os.close(fd)


def document(payload):
    def pairs(items):
        result = {}
        for key, value in items:
            check(key not in result)
            result[key] = value
        return result
    try:
        value = json.loads(payload, object_pairs_hook=pairs,
                           parse_constant=lambda _: check(False))
        check(type(value) is dict)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise OptionAuthorityError("OPTION_AUTHORITY_INTEGRITY_INVALID") from None


@dataclass(frozen=True)
class PublicationPin:
    identity: str
    version: str
    sha256: str
    filename: str

    def __post_init__(self):
        public_id(self.identity)
        check(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", self.version) is not None
              and re.fullmatch(r"[a-f0-9]{64}", self.sha256) is not None)

    @property
    def reference(self):
        return f"{self.identity}/{self.version}/SHA256:{self.sha256}"


@dataclass(frozen=True)
class OptionSeries:
    identity: str
    family: str
    canonical_subject: str
    series_kind: str
    expiry: date
    underlying_future: str
    futures_expiry: date
    quotation_unit: str
    settlement_reference: str
    source_ids: tuple[str, ...]
    source_locator: str


@dataclass(frozen=True)
class OptionSeriesPublication:
    pin: PublicationPin
    effective_from: datetime
    effective_through: datetime
    coverage_start: date
    coverage_end: date
    supersedes: str | None
    rows: tuple[OptionSeries, ...]
    source_provenance: tuple[str, ...]


@authority_boundary
def load_option_series(root=DEFAULT_OPTION_ROOT, *, pin: PublicationPin):
    raw = document(read_exact(root, pin.filename, expected_sha256=pin.sha256))
    check(set(raw) == {"schema_identity", "schema_version", "publication_identity",
                      "publication_version", "effective_from", "effective_through",
                      "coverage_start", "coverage_end", "supersedes", "sources", "series"})
    check(raw["schema_identity"] == OPTION_SERIES and raw["schema_version"] == "1.0.0"
          and raw["publication_identity"] == pin.identity and raw["publication_version"] == pin.version)
    start, end = date.fromisoformat(raw["coverage_start"]), date.fromisoformat(raw["coverage_end"])
    first, last = aware(raw["effective_from"]), aware(raw["effective_through"])
    check(start <= end and first <= last)
    source_ids, provenance = set(), []
    check(type(raw["sources"]) is list and 1 <= len(raw["sources"]) <= 100
          and type(raw["series"]) is list and 1 <= len(raw["series"]) <= 2000)
    for source in raw["sources"]:
        check(set(source) == {"identity", "official_uri", "reference", "published_on",
                             "retrieved_at", "filename", "sha256", "effective_scope"})
        identity = public_id(source["identity"])
        url = urlparse(source["official_uri"])
        check(identity not in source_ids and url.scheme == "https"
              and url.hostname in {"www.mcxindia.com", "classic.mcxindia.com"}
              and url.path.startswith("/docs/") and bool(source["reference"])
              and bool(source["effective_scope"]), "OPTION_AUTHORITY_SOURCE_INVALID")
        check(date.fromisoformat(source["published_on"]) <= aware(source["retrieved_at"]).date()
              and aware(source["retrieved_at"]) <= first, "OPTION_AUTHORITY_SOURCE_INVALID")
        payload = read_exact(root, source["filename"], expected_sha256=source["sha256"])
        check(payload.startswith(b"%PDF-"), "OPTION_AUTHORITY_SOURCE_INVALID")
        source_ids.add(identity)
        provenance.append(f"{identity}/SHA256:{source['sha256']}")
    check(bool(source_ids), "OPTION_AUTHORITY_SOURCE_INVALID")
    rows, identities, expiries = [], set(), set()
    for item in raw["series"]:
        check(set(item) == {"identity", "family", "canonical_subject", "series_kind", "expiry",
                            "underlying_future", "futures_expiry", "quotation_unit",
                            "settlement_reference", "source_ids", "source_locator"})
        family = item["family"]
        check(family in FAMILIES, "OPTION_AUTHORITY_FAMILY_UNAVAILABLE")
        label, subject = FAMILIES[family]
        expiry, future = date.fromisoformat(item["expiry"]), date.fromisoformat(item["futures_expiry"])
        identity = public_id(item["identity"])
        check(identity == f"MCX-OPT-SERIES-{family}-{item['series_kind']}-{expiry.isoformat()}")
        check(identity not in identities and (family, expiry) not in expiries,
              "OPTION_AUTHORITY_SERIES_AMBIGUOUS")
        check(item["canonical_subject"] == subject and item["series_kind"] in {"MONTHLY", "BI_MONTHLY"}
              and start <= expiry <= end and future >= expiry)
        check(item["underlying_future"] == f"MCX-FUT-{label}-{future.isoformat()}",
              "OPTION_AUTHORITY_UNDERLYING_INVALID")
        check(item["quotation_unit"] == QUOTATION_UNITS[family], "OPTION_AUTHORITY_UNIT_UNAVAILABLE")
        check(item["settlement_reference"] == SETTLEMENT,
              "OPTION_AUTHORITY_SETTLEMENT_UNAVAILABLE")
        check(bool(item["source_ids"]) and set(item["source_ids"]) <= source_ids
              and bool(item["source_locator"]), "OPTION_AUTHORITY_SOURCE_INVALID")
        rows.append(OptionSeries(identity, family, subject, item["series_kind"], expiry,
                                item["underlying_future"], future, item["quotation_unit"],
                                item["settlement_reference"], tuple(item["source_ids"]), item["source_locator"]))
        identities.add(identity); expiries.add((family, expiry))
    check(set(r.family for r in rows) == set(FAMILIES), "OPTION_AUTHORITY_COVERAGE_UNAVAILABLE")
    return OptionSeriesPublication(pin, first, last, start, end, raw["supersedes"],
                                   tuple(rows), tuple(provenance))
