"""Explicit WO-12 maintenance operations; no acquisition or startup mutation."""
from __future__ import annotations

from datetime import datetime, date, time, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from zoneinfo import ZoneInfo

from kronos.application.swing_nse_equity_basis import NseEquityActionReport

IST = ZoneInfo("Asia/Kolkata")
MAX_IMPORT_BYTES = 1024 * 1024


class ResearchReleaseVerifier:
    """Compare the process's startup identity, Git blobs and actual source bytes."""
    def __init__(self, source_root: Path, loaded_revision):
        self.root = Path(source_root)
        self.loaded_revision = loaded_revision

    def verify(self, release: str, manifest_bytes: bytes, expected_hash: str) -> dict:
        if (re.fullmatch(r"[a-f0-9]{40}", release) is None
                or re.fullmatch(r"[a-f0-9]{64}", expected_hash) is None
                or not 0 < len(manifest_bytes) <= MAX_IMPORT_BYTES
                or sha256(manifest_bytes).hexdigest() != expected_hash):
            raise ValueError("SWING_RESEARCH_RELEASE_INVALID")
        def git(*args):
            return subprocess.check_output(["git", "-C", str(self.root), *args],
                                           timeout=5, stderr=subprocess.DEVNULL,
                                           env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        try:
            loaded = self.loaded_revision()
            if (loaded != release or git("rev-parse", "HEAD").decode().strip() != release
                    or git("status", "--porcelain", "--untracked-files=all")):
                raise ValueError("SWING_RESEARCH_RELEASE_DRIFT")
            # The published release attests the reviewed manifest identity.
            # A caller cannot substitute differently serialized or unreviewed
            # manifest bytes merely because the source rows happen to match.
            trailers = [line.removeprefix("WO12-Source-Manifest-SHA256: ")
                        for line in git("show", "-s", "--format=%B", release).decode().splitlines()
                        if line.startswith("WO12-Source-Manifest-SHA256: ")]
            if trailers != [expected_hash]:
                raise ValueError("SWING_RESEARCH_RELEASE_MANIFEST_UNATTESTED")
            manifest = json.loads(manifest_bytes)
            base = manifest["direct_base_commit"]
            if re.fullmatch(r"[a-f0-9]{40}", base) is None:
                raise ValueError("SWING_RESEARCH_RELEASE_INVALID")
            entries = manifest["paths"]
            paths = [entry["path"] for entry in entries]
            if (not paths or len(paths) > 256 or len(paths) != len(set(paths))
                    or manifest["path_count"] != len(paths)):
                raise ValueError("SWING_RESEARCH_RELEASE_INVALID")
            changed = set(git("diff", "--name-only", base, release).decode().splitlines())
            if changed != set(paths):
                raise ValueError("SWING_RESEARCH_RELEASE_SCOPE_INVALID")
            for entry in entries:
                path = PurePosixPath(entry["path"])
                if (path.is_absolute() or ".." in path.parts or str(path) != entry["path"]
                        or (path.parts[0] not in {"src", "tests", "docs"}
                            and str(path) != "tools/kronos_browser.py")):
                    raise ValueError("SWING_RESEARCH_RELEASE_PATH_INVALID")
                local = self.root / path
                if any(parent.is_symlink() for parent in (local, *local.parents)):
                    raise ValueError("SWING_RESEARCH_RELEASE_PATH_INVALID")
                blob = git("show", release + ":" + str(path))
                if (sha256(blob).hexdigest() != entry["candidate_sha256"]
                        or local.read_bytes() != blob):
                    raise ValueError("SWING_RESEARCH_RELEASE_BYTES_INVALID")
            # Recheck after all I/O, before returning any authority.
            if self.loaded_revision() != loaded or git("rev-parse", "HEAD").decode().strip() != release:
                raise ValueError("SWING_RESEARCH_RELEASE_DRIFT")
            return {"release_identity": release, "source_manifest_sha256": expected_hash,
                    "verified_paths": len(paths), "base_commit": base}
        except (OSError, subprocess.SubprocessError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("SWING_RESEARCH_RELEASE_UNAVAILABLE") from error


def import_official_actions(store, calendar, fields: dict, csv_bytes: bytes,
                            *, received_at: datetime) -> str:
    """Retain original bytes with attributable completeness, not exchange certification."""
    expected = {"symbol", "series", "coverage_start", "coverage_end", "source_url",
                "source_sha256", "all_results_row_count", "capture_identity", "captured_at",
                "attested_by", "attested_at", "all_results", "purpose_filter"}
    if (type(fields) is not dict or set(fields) != expected
            or not 0 < len(csv_bytes) <= MAX_IMPORT_BYTES
            or fields["source_sha256"] != sha256(csv_bytes).hexdigest()
            or fields["all_results"] is not True or fields["purpose_filter"] != "ALL"
            or not isinstance(fields["attested_by"], str)
            or not 0 < len(fields["attested_by"].strip()) <= 120
            or not isinstance(fields["capture_identity"], str)
            or re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", fields["capture_identity"]) is None
            or fields["series"] != "EQ"):
        raise ValueError("SWING_NSE_ACTION_ATTESTATION_INVALID")
    start, end = date.fromisoformat(fields["coverage_start"]), date.fromisoformat(fields["coverage_end"])
    captured, attested = datetime.fromisoformat(fields["captured_at"]), datetime.fromisoformat(fields["attested_at"])
    if (any(value.tzinfo is None for value in (captured, attested, received_at))
            or not captured <= attested <= received_at or start > end or calendar is None):
        raise ValueError("SWING_NSE_ACTION_ATTESTATION_INVALID")
    # Same capture replay preserves the original import receipt time.
    if store.root.exists():
        for path in store.root.glob("*.json"):
            if path.is_symlink():
                raise ValueError("SWING_NSE_ACTION_STORE_INVALID")
            value = json.loads(path.read_bytes())
            material = value["material"]
            prior = material.get("attestation", {})
            if prior.get("capture_identity") == fields["capture_identity"]:
                if (sha256(json.dumps(material, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=False).encode() + b"\n").hexdigest() != value["identity"]
                        or path.stem != value["identity"]
                        or any(prior.get(key) != item for key, item in fields.items())):
                    raise ValueError("SWING_NSE_ACTION_CAPTURE_CONFLICT")
                return value["identity"]
    publication = calendar.publication("NSE")
    if (publication.coverage_start > start or publication.coverage_end < end
            or publication.source_boundary > captured):
        raise ValueError("SWING_NSE_ACTION_COVERAGE_UNAVAILABLE")
    # Completed governed sessions, including special sessions; never a normal-close guess.
    sessions = []
    for day in sorted(publication.trading_dates):
        if start <= day <= end:
            schedule = calendar.schedule("NSE", day, observed_at=captured)
            if schedule is None or not schedule.windows:
                raise ValueError("SWING_NSE_ACTION_COVERAGE_UNAVAILABLE")
            windows = schedule.windows
            sessions.append({"date": day.isoformat(),
                             "windows": [(w.window_open.isoformat(), w.window_close.isoformat()) for w in windows]})
            if any(w.window_close > captured for w in windows):
                raise ValueError("SWING_NSE_ACTION_COVERAGE_INCOMPLETE")
    if end not in publication.trading_dates and captured < datetime.combine(end + timedelta(days=1), time.min, IST):
        raise ValueError("SWING_NSE_ACTION_COVERAGE_INCOMPLETE")
    if captured.astimezone(IST).date() < end:
        raise ValueError("SWING_NSE_ACTION_COVERAGE_INCOMPLETE")
    attestation = {**fields, "received_at": received_at.isoformat(),
                   "calendar_identity": publication.calendar_identity,
                   "calendar_sha256": publication.publication_sha256,
                   "calendar_version": publication.calendar_version,
                   "calendar_source_boundary": publication.source_boundary.isoformat(),
                   "sessions": sessions,
                   "authority": "SPONSOR_OR_DATA_OWNER_COMPLETENESS_ATTESTATION_V1"}
    report = NseEquityActionReport(fields["symbol"], fields["series"], start, end,
                                  captured, fields["source_url"], csv_bytes,
                                  fields["all_results_row_count"], True, attestation)
    return store.retain(report)
