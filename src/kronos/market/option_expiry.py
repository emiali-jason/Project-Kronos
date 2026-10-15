"""TE-03A DOMAIN-008 option-specific endpoints; never FUT cutoff substitution.

An explicit option publication binds the Instrument roster and base calendar.
Expiry rules are mechanical exchange specification facts, not Theta heuristics.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import stat
from zipfile import BadZipFile, LargeZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile
from zoneinfo import ZoneInfo
from zlib import error as DecompressionError

from kronos.instrument.option_series import (
    OptionAuthorityError, OptionSeries, OptionSeriesPublication, PublicationPin,
    aware, authority_boundary, check, document, read_exact)
from kronos.market.calendar import MarketCalendarPublisher

OPTION_EXPIRY = "KRONOS-MCX-OPTION-EXPIRY-PUBLICATION-V1"
DEFAULT_EXPIRY_ROOT = Path(__file__).resolve().parents[3] / "data/market_calendars/mcx_option_expiries"


def read_dst_source(root, source):
    """Resolve the same pinned original from raw or exact-member transport.

    PLC-03C changes distribution only, not the source identity or its bytes.
    Legacy raw layouts remain supported. An existing invalid/inaccessible raw
    artifact is never masked by the package. No extraction or filesystem write
    occurs; neither a container name nor its presence supplies source authority.
    """
    try:
        return read_exact(root, source["filename"], expected_sha256=source["sha256"])
    except OptionAuthorityError as error:
        if str(error) != "OPTION_AUTHORITY_ARTIFACT_UNAVAILABLE":
            raise
        try:
            (root / source["filename"]).lstat()
        except FileNotFoundError:
            pass
        except OSError:
            raise error from None
        else:
            raise error from None
    check(source["filename"] == "sources/nist-dst-2026.html",
          "OPTION_AUTHORITY_SOURCE_INVALID")
    payload = read_exact(root, "sources/nist-dst-2026.zip")
    limit = 20 * 1024 * 1024  # Same bound as the existing exact-artifact reader.
    try:
        with ZipFile(BytesIO(payload)) as package:
            members = package.infolist()
            check(len(members) == 1, "OPTION_AUTHORITY_SOURCE_INVALID")
            member = members[0]
            check(member.filename == "nist-dst-2026.html"
                  and not member.is_dir() and not member.flag_bits & 1
                  and stat.S_IFMT(member.external_attr >> 16) in {0, stat.S_IFREG}
                  and member.compress_type in {ZIP_STORED, ZIP_DEFLATED}
                  and 0 < member.file_size <= limit,
                  "OPTION_AUTHORITY_SOURCE_INVALID")
            with package.open(member) as stream:
                original = stream.read(limit + 1)
            check(len(original) == member.file_size
                  and sha256(original).hexdigest() == source["sha256"],
                  "OPTION_AUTHORITY_SOURCE_INVALID")
            return original
    except (BadZipFile, LargeZipFile, RuntimeError, NotImplementedError,
            EOFError, DecompressionError):
        raise OptionAuthorityError("OPTION_AUTHORITY_SOURCE_INVALID") from None


def business_days(calendar, start, end):
    check(calendar.coverage_start <= start <= end <= calendar.coverage_end,
          "OPTION_AUTHORITY_CALENDAR_UNAVAILABLE")
    return tuple(d for d in sorted(calendar.trading_dates) if start <= d <= end
                 and "MUHURAT" not in calendar.trading_dates[d].session_type.upper())


def expiry_date(calendar, *, rule, future, contract_month):
    """Apply only the rule expressly bound by the owner option publication."""
    if rule in {"TWO_BUSINESS_DAYS_BEFORE_FUTURE", "THREE_BEFORE_THREE_DAY_TENDER"}:
        # Tender's first day is FUT-2 trading days; three prior is FUT-5.
        count = 2 if rule == "TWO_BUSINESS_DAYS_BEFORE_FUTURE" else 5
        days = business_days(calendar, max(calendar.coverage_start, future-timedelta(days=45)), future)
        check(len(days) > count and days[-1] == future, "OPTION_AUTHORITY_CALENDAR_UNAVAILABLE")
        return days[-1-count]
    check(rule == "FOURTH_LAST_BUSINESS_DAY_MONTHLY", "OPTION_AUTHORITY_RULE_UNAVAILABLE")
    start = contract_month.replace(day=1)
    end = (date(start.year+1, 1, 1) if start.month == 12
           else date(start.year, start.month+1, 1))-timedelta(days=1)
    days = business_days(calendar, start, end)
    check(len(days) >= 5, "OPTION_AUTHORITY_CALENDAR_UNAVAILABLE")
    result = days[-4]
    # The specification says Friday OR the day before a holiday. Weekends are
    # non-business days; the Friday rule independently produces the same shift.
    if result.weekday() == 4 or result+timedelta(days=1) not in calendar.trading_dates:
        result = days[days.index(result)-1]
    return result


@dataclass(frozen=True)
class OptionEndpoint:
    series_identity: str
    expiry: date
    opens_at: datetime
    expires_at: datetime
    session_identity: str
    option_publication_reference: str
    base_calendar_reference: str
    source_provenance: tuple[str, ...]


@dataclass(frozen=True)
class OptionExpiryPublication:
    pin: PublicationPin
    instrument_reference: str
    base_calendar_reference: str
    effective_from: datetime
    effective_through: datetime
    coverage_start: date
    coverage_end: date
    supersedes: str | None
    endpoints: tuple[OptionEndpoint, ...]


@authority_boundary
def load_option_expiries(*, instrument: OptionSeriesPublication, pin: PublicationPin,
                         root=DEFAULT_EXPIRY_ROOT, calendar_publisher=None):
    raw = document(read_exact(root, pin.filename, expected_sha256=pin.sha256))
    check(set(raw) == {"schema_identity", "schema_version", "publication_identity", "publication_version",
                      "instrument_reference", "base_calendar_reference", "effective_from", "effective_through",
                      "coverage_start", "coverage_end", "supersedes", "rules", "session_periods", "supporting_source"})
    check(raw["schema_identity"] == OPTION_EXPIRY and raw["schema_version"] == "1.0.0"
          and raw["publication_identity"] == pin.identity and raw["publication_version"] == pin.version)
    check(raw["instrument_reference"] == instrument.pin.reference, "OPTION_AUTHORITY_OWNER_CONFLICT")
    publisher = calendar_publisher or MarketCalendarPublisher()
    calendar = publisher.publication("MCX")
    reference = f"{calendar.calendar_identity}/{calendar.calendar_version}/SHA256:{calendar.publication_sha256}"
    check(raw["base_calendar_reference"] == reference, "OPTION_AUTHORITY_CALENDAR_STALE")
    start, end = date.fromisoformat(raw["coverage_start"]), date.fromisoformat(raw["coverage_end"])
    first, last = aware(raw["effective_from"]), aware(raw["effective_through"])
    check(calendar.coverage_start <= start <= end <= calendar.coverage_end
          and instrument.coverage_start <= start <= end <= instrument.coverage_end,
          "OPTION_AUTHORITY_COVERAGE_UNAVAILABLE")
    check(instrument.effective_from <= first <= last <= instrument.effective_through
          and calendar.source_boundary <= first)
    # NIST supplies the already-published US-DST dates, not MCX authority.
    # MCX option specifications supply the conditional 23:30/23:55 rule.
    # This additive publication uses base-calendar DATE availability only;
    # it neither changes that calendar's clocks nor claims equivalence with it.
    source = raw["supporting_source"]
    check(set(source) == {"identity", "official_uri", "updated_on", "retrieved_at", "filename", "sha256"}
          and source["identity"] == "NIST-US-DST-2026"
          and source["official_uri"] == "https://www.nist.gov/pml/time-and-frequency-division/popular-links/daylight-saving-time-dst"
          and date.fromisoformat(source["updated_on"]) <= aware(source["retrieved_at"]).date()
          and aware(source["retrieved_at"]) <= first, "OPTION_AUTHORITY_SOURCE_INVALID")
    support = read_dst_source(root, source)
    check(b"November 1" in support and b"2026" in support, "OPTION_AUTHORITY_SOURCE_INVALID")
    periods = []
    for period in raw["session_periods"]:
        check(set(period) == {"start", "end", "normal_open", "normal_close", "source_identity"})
        begin, finish = date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
        opening, closing = time.fromisoformat(period["normal_open"]), time.fromisoformat(period["normal_close"])
        check(start <= begin <= finish <= end and opening == time(9)
              and closing in {time(23,30),time(23,55)} and period["source_identity"] == source["identity"])
        periods.append((begin,finish,opening,closing))
    check(periods and periods[0][0] == start and periods[-1][1] == end
          and all(a[1]+timedelta(days=1) == b[0] for a,b in zip(periods,periods[1:])))
    rules = {}
    for item in raw["rules"]:
        check(set(item) == {"family", "series_kind", "expiry_rule", "session_rule", "source_ids"})
        key = item["family"], item["series_kind"]
        check(key not in rules and item["session_rule"] == "OPTION_SPEC_NORMAL_MCX_SESSION")
        check(bool(item["source_ids"]) and set(item["source_ids"]) <= set(
            p.split("/SHA256:")[0] for p in instrument.source_provenance), "OPTION_AUTHORITY_SOURCE_INVALID")
        rules[key] = item
    endpoints = []
    zone = ZoneInfo("Asia/Kolkata")
    for series in instrument.rows:
        if not start <= series.expiry <= end:
            continue
        rule = rules.get((series.family, series.series_kind))
        check(rule is not None, "OPTION_AUTHORITY_RULE_UNAVAILABLE")
        # GOLDM's source table explicitly supplies dates. All other initial
        # dates are DERIVED from the bound exchange rule and governed calendar.
        if rule["expiry_rule"] != "EXPLICIT_EXCHANGE_DATE":
            expected = expiry_date(calendar, rule=rule["expiry_rule"], future=series.futures_expiry,
                                   contract_month=series.expiry)
            check(expected == series.expiry, "OPTION_AUTHORITY_OWNER_CONFLICT")
        check(series.expiry in calendar.trading_dates, "OPTION_AUTHORITY_CALENDAR_UNAVAILABLE")
        session = calendar.trading_dates[series.expiry]
        check(len(session.windows) == 1 and session.windows[0].window_open.hour == 9
              and session.windows[0].window_close.hour == 23
              and session.windows[0].window_close.minute in {30,55},
              "OPTION_AUTHORITY_SESSION_UNAVAILABLE")
        window = session.windows[0]
        applicable = [p for p in periods if p[0] <= series.expiry <= p[1]]
        check(len(applicable) == 1, "OPTION_AUTHORITY_SESSION_UNAVAILABLE")
        period = applicable[0]
        check(window.window_open == period[2], "OPTION_AUTHORITY_SESSION_UNAVAILABLE")
        endpoints.append(OptionEndpoint(series.identity, series.expiry,
            datetime.combine(series.expiry, period[2], zone),
            datetime.combine(series.expiry, period[3], zone),
            f"{pin.identity}/{pin.version}/{series.identity}/OPTION_SESSION", pin.reference,
            reference, tuple(p for p in instrument.source_provenance
                if p.split("/SHA256:")[0] in set(series.source_ids) | set(rule["source_ids"]))
                + (f"{source['identity']}/SHA256:{source['sha256']}",)))
    return OptionExpiryPublication(pin, instrument.pin.reference, reference, first, last,
                                    start, end, raw["supersedes"], tuple(endpoints))
