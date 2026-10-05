"""Retained NSE equity corporate-action coverage for comparable price research.

This is a file-backed evidence consumer, not a downloader or adjustment-factor
engine. Only a complete, exact-symbol official report can verify that the
price interval is action-free. Any reported action or missing coverage withholds
the checkpoint; no factor is inferred from a purpose label.
"""
from __future__ import annotations

import csv
import base64
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo


_REQUIRED = {"SYMBOL", "SERIES", "PURPOSE", "EX-DATE"}
_IST = ZoneInfo("Asia/Kolkata")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode() + b"\n"


def _date(value: str) -> date:
    for pattern in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            pass
    raise ValueError("SWING_NSE_ACTION_DATE_INVALID")


@dataclass(frozen=True)
class NseEquityActionReport:
    symbol: str
    series: str
    coverage_start: date
    coverage_end: date
    retrieved_at: datetime
    source_url: str
    csv_bytes: bytes
    reported_rows: int
    complete_download: bool
    attestation: dict | None = None

    def __post_init__(self) -> None:
        parsed = urlsplit(self.source_url)
        if (not self.symbol or not self.symbol.isascii() or not self.symbol.replace("&", "").replace("-", "").isalnum()
                or self.series != "EQ" or self.coverage_start > self.coverage_end
                or self.retrieved_at.tzinfo is None
                or parsed.hostname not in {"www.nseindia.com", "nseindia.com"}
                or parsed.scheme != "https" or parsed.username is not None
                or parsed.password is not None or parsed.fragment or not self.csv_bytes
                or type(self.reported_rows) is not int or self.reported_rows < 0
                or self.complete_download is not True):
            raise ValueError("SWING_NSE_ACTION_REPORT_INVALID")
        self.rows()
        if self.attestation is not None:
            a = self.attestation
            expected = {"symbol": self.symbol, "series": self.series,
                        "coverage_start": self.coverage_start.isoformat(),
                        "coverage_end": self.coverage_end.isoformat(),
                        "source_url": self.source_url,
                        "source_sha256": sha256(self.csv_bytes).hexdigest(),
                        "all_results_row_count": self.reported_rows,
                        "captured_at": self.retrieved_at.isoformat(), "all_results": True,
                        "purpose_filter": "ALL",
                        "authority": "SPONSOR_OR_DATA_OWNER_COMPLETENESS_ATTESTATION_V1"}
            if (not isinstance(a, dict) or any(a.get(k) != v for k, v in expected.items())
                    or not a.get("attested_by") or not a.get("capture_identity")
                    or not a.get("calendar_identity") or not a.get("calendar_sha256")
                    or not a.get("attested_at") or not a.get("received_at")
                    or not self.retrieved_at <= datetime.fromisoformat(a["attested_at"])
                       <= datetime.fromisoformat(a["received_at"])):
                raise ValueError("SWING_NSE_ACTION_ATTESTATION_INVALID")

    def rows(self) -> tuple[tuple[str, str], ...]:
        try:
            text = self.csv_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError("SWING_NSE_ACTION_REPORT_INVALID") from error
        reader = csv.DictReader(StringIO(text))
        headers = [] if reader.fieldnames is None else [name.strip() for name in reader.fieldnames]
        if len(headers) != len(set(headers)) or not _REQUIRED.issubset(set(headers)):
            raise ValueError("SWING_NSE_ACTION_REPORT_COLUMNS_INVALID")
        reader.fieldnames = headers
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("SWING_NSE_ACTION_REPORT_COLUMNS_INVALID")
            row = {key: value.strip() for key, value in row.items()}
            if (row["SYMBOL"] != self.symbol or row["SERIES"] != self.series
                    or not row["PURPOSE"]):
                raise ValueError("SWING_NSE_ACTION_REPORT_SCOPE_INVALID")
            ex_date = _date(row["EX-DATE"])
            if not self.coverage_start <= ex_date <= self.coverage_end:
                raise ValueError("SWING_NSE_ACTION_REPORT_SCOPE_INVALID")
            rows.append((ex_date.isoformat(), row["PURPOSE"]))
        if len(rows) != self.reported_rows:
            raise ValueError("SWING_NSE_ACTION_REPORT_TRUNCATED")
        return tuple(sorted(rows))

    def material(self) -> dict:
        return {"symbol": self.symbol, "series": self.series,
                "coverage_start": self.coverage_start.isoformat(),
                "coverage_end": self.coverage_end.isoformat(),
                "retrieved_at": self.retrieved_at.isoformat(),
                "source_url": self.source_url,
                "source_sha256": sha256(self.csv_bytes).hexdigest(),
                "csv_base64": base64.b64encode(self.csv_bytes).decode("ascii"),
                "reported_rows": self.reported_rows,
                "complete_download": True, "rows": self.rows(),
                **({"attestation": self.attestation} if self.attestation is not None else {})}


class NseEquityBasisStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        if not self.root.is_absolute():
            raise ValueError("SWING_NSE_ACTION_STORE_INVALID")

    def retain(self, report: NseEquityActionReport) -> str:
        if type(report) is not NseEquityActionReport:
            raise ValueError("SWING_NSE_ACTION_REPORT_INVALID")
        material = report.material()
        identity = sha256(_canonical(material)).hexdigest()
        path = self.root / (identity + ".json")
        if self.root.is_symlink() or path.is_symlink():
            raise ValueError("SWING_NSE_ACTION_STORE_INVALID")
        self.root.mkdir(parents=True, exist_ok=True)
        payload = _canonical({"identity": identity, "material": material})
        if path.exists():
            if path.read_bytes() != payload:
                raise ValueError("SWING_NSE_ACTION_REPORT_CONFLICT")
            return identity
        temporary = self.root / ("." + uuid4().hex + ".pending")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError:
                if path.read_bytes() != payload:
                    raise ValueError("SWING_NSE_ACTION_REPORT_CONFLICT")
            directory = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
        return identity

    def basis(self, symbol: str, series: str, start: date, through: date,
              *, as_of: datetime | None = None) -> tuple[str, str | None]:
        if (series != "EQ" or start > through
                or as_of is not None and as_of.tzinfo is None):
            return "UNKNOWN", None
        candidates = []
        overlapping = []
        if not self.root.exists():
            return "UNKNOWN", None
        for path in sorted(self.root.glob("*.json")):
            if path.is_symlink():
                raise ValueError("SWING_NSE_ACTION_STORE_INVALID")
            value = json.loads(path.read_bytes())
            material = value["material"]
            if (sha256(_canonical(material)).hexdigest() != value["identity"]
                    or path.stem != value["identity"]
                    or sha256(base64.b64decode(material["csv_base64"], validate=True)).hexdigest()
                       != material["source_sha256"]):
                raise ValueError("SWING_NSE_ACTION_REPORT_INTEGRITY_INVALID")
            covered_from = date.fromisoformat(material["coverage_start"])
            covered_through = date.fromisoformat(material["coverage_end"])
            if (material["symbol"] == symbol and material["series"] == series
                    and (as_of is None or datetime.fromisoformat(material["retrieved_at"]) <= as_of)
                    and covered_from <= through and covered_through >= start):
                report = NseEquityActionReport(
                    symbol, series, covered_from, covered_through,
                    datetime.fromisoformat(material["retrieved_at"]),
                    material["source_url"],
                    base64.b64decode(material["csv_base64"], validate=True),
                    material["reported_rows"], material["complete_download"],
                    material.get("attestation"))
                if (report.attestation is None or as_of is not None
                        and datetime.fromisoformat(report.attestation["received_at"]) > as_of):
                    continue  # Historical caller booleans are not completeness authority.
                overlapping.append((covered_from, covered_through, report.rows()))
                if covered_from <= start and covered_through >= through:
                    candidates.append((value["identity"], report.rows()))
        if not candidates:
            return "UNKNOWN", None
        facts = {tuple(row for row in rows
                       if start <= date.fromisoformat(row[0]) <= through)
                 for _, rows in candidates}
        if len(facts) != 1:
            return "UNKNOWN", None
        selected = next(iter(facts))
        for covered_from, covered_through, rows in overlapping:
            begin, end = max(start, covered_from), min(through, covered_through)
            if tuple(row for row in rows if begin <= date.fromisoformat(row[0]) <= end) != tuple(
                    row for row in selected if begin <= date.fromisoformat(row[0]) <= end):
                return "UNKNOWN", None
        identity = sorted(item[0] for item in candidates)[-1]
        return ("AFFECTED" if selected else "VERIFIED_NO_ACTION", identity)
