"""Non-authoritative MCX official-source check and immutable staging.

This module deliberately cannot publish or activate Instrument/Market authority.
Construction is dormant.  S3.03 must bind activation to the real READY and
custody-release receipts and may only display the status produced here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from hashlib import sha256
from html.parser import HTMLParser
import json
import http.client
import os
from pathlib import Path
import re
import stat
import ssl
import time
from threading import Event, Lock, Thread, current_thread
from typing import Callable
from urllib.parse import unquote, urljoin, urlparse

from kronos.common.release_admission import ValidationBudget, monotonic_ns


FAMILIES = ("GOLDM", "SILVERM", "COPPER", "CRUDEOIL", "NATURALGAS")
PRODUCT_PAGES = {
    "GOLDM": "https://www.mcxindia.com/products/bullion/gold",
    "SILVERM": "https://www.mcxindia.com/en/products/bullion/Silver",
    "COPPER": "https://www.mcxindia.com/products/metals/copper",
    "CRUDEOIL": "https://www.mcxindia.com/products/energy/crude-oil",
    "NATURALGAS": "https://www.mcxindia.com/products/energy/natural-gas",
}
CIRCULARS_PAGE = "https://www.mcxindia.com/circulars/all-circulars"
ALLOWED_HOSTS = frozenset({"www.mcxindia.com", "classic.mcxindia.com"})
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 3
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 15
MAX_CHECK_REQUESTS = 64
MAX_CHECK_DOCUMENTS = 48
MAX_CHECK_BYTES = 100 * 1024 * 1024
MAX_CHECK_DURATION_SECONDS = 45.0
MAX_CIRCULAR_PAGES = 10
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class OfficialCheckError(ValueError):
    """Sanitized checker failure; source content never enters diagnostics."""


class CheckerState(str, Enum):
    CURRENT = "CURRENT"
    UPDATE_AVAILABLE = "UPDATE AVAILABLE"
    AWAITING_REVIEW = "AWAITING REVIEW"
    FAILED = "FAILED"


class CheckFrequency(str, Enum):
    DAILY = "DAILY"
    EVERY_THREE_DAYS = "EVERY THREE DAYS"
    WEEKLY = "WEEKLY"

    @property
    def interval_seconds(self) -> int:
        return {self.DAILY: 86400, self.EVERY_THREE_DAYS: 259200,
                self.WEEKLY: 604800}[self]


@dataclass(frozen=True)
class OfficialHttpResponse:
    requested_url: str
    final_url: str
    status: int
    media_type: str
    body: bytes
    redirects: tuple[str, ...] = ()
    complete: bool = True
    circular_from: int | None = None
    circular_through: int | None = None
    page_number: int | None = None
    page_count: int | None = None
    page_item_count: int | None = None
    next_page_url: str | None = None
    location: str | None = None


@dataclass(frozen=True)
class CheckLimits:
    max_requests: int = MAX_CHECK_REQUESTS
    max_documents: int = MAX_CHECK_DOCUMENTS
    max_bytes: int = MAX_CHECK_BYTES
    max_duration_seconds: float = MAX_CHECK_DURATION_SECONDS
    max_circular_pages: int = MAX_CIRCULAR_PAGES

    def validate(self) -> None:
        if (type(self.max_requests) is not int or not 1 <= self.max_requests <= 256
                or type(self.max_documents) is not int or not 1 <= self.max_documents <= 128
                or type(self.max_bytes) is not int
                or not MAX_PAGE_BYTES <= self.max_bytes <= 512 * 1024 * 1024
                or type(self.max_duration_seconds) not in {int, float}
                or not 0 < float(self.max_duration_seconds) <= 300
                or type(self.max_circular_pages) is not int
                or not 1 <= self.max_circular_pages <= 50):
            raise OfficialCheckError("MCX_CHECK_LIMITS_INVALID")


@dataclass
class _CheckScope:
    started: float
    requests: int = 0
    documents: int = 0
    bytes: int = 0
    responses: list[dict[str, object]] = field(default_factory=list)


class OfficialHttpsTransport:
    """One HTTPS exchange per call. The engine owns redirects and total limits."""

    def __call__(self, url: str, *, connect_timeout_seconds: float, read_timeout_seconds: float,
                 max_bytes: int, max_redirects: int,
                 whole_check_remaining_seconds: float = MAX_CHECK_DURATION_SECONDS) -> OfficialHttpResponse:
        _safe_url(url, document=urlparse(url).path.lower().endswith('.pdf'))
        parsed = urlparse(url)
        connection = http.client.HTTPSConnection(
            parsed.hostname, timeout=connect_timeout_seconds, context=ssl.create_default_context())
        deadline = time.monotonic() + whole_check_remaining_seconds
        def remaining():
            value = deadline - time.monotonic()
            if value <= 0:
                raise OfficialCheckError('MCX_CHECK_DEADLINE_EXPIRED')
            return min(read_timeout_seconds, value)
        try:
            connection.connect()
            connection.sock.settimeout(remaining())
            connection.request('GET', parsed.path + ('?' + parsed.query if parsed.query else ''),
                               headers={'User-Agent': 'KRONOS-MCX-Official-Check/1.0',
                                        'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            chunks, size = [], 0
            while True:
                if connection.sock is not None:
                    connection.sock.settimeout(remaining())
                else:
                    remaining()
                chunk = (response.read1(min(65536, max_bytes + 1 - size))
                         if hasattr(response, 'read1') else response.read(max_bytes + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk); size += len(chunk)
                if size > max_bytes:
                    raise OfficialCheckError('MCX_CHECK_SIZE_INVALID')
                if not hasattr(response, 'read1'):
                    break  # Disclosed finite in-memory transport fixture only.
            body = b''.join(chunks)
            remaining()
            if len(body) > max_bytes:
                raise OfficialCheckError('MCX_CHECK_SIZE_INVALID')
            result = OfficialHttpResponse(url, url, response.status,
                response.getheader('Content-Type', ''), body,
                location=response.getheader('Location'))
            # The observed Sitefinity circular page uses client-side table
            # pagination with href="#". Its response does not establish a
            # complete circular range or an auditable next request. Fail closed.
            if parsed.path == urlparse(CIRCULARS_PAGE).path:
                return OfficialHttpResponse(**{**result.__dict__, 'complete': False})
            return result
        except (OSError, http.client.HTTPException) as error:
            raise OfficialCheckError('MCX_CHECK_TRANSPORT_UNAVAILABLE') from error
        finally:
            connection.close()


@dataclass(frozen=True)
class ActivationEvidence:
    """Exact integration receipts; never a caller-supplied readiness boolean."""

    startup_generation: str
    ready_receipt: bytes
    ready_receipt_sha256: str
    custody_release_receipt: bytes
    custody_release_receipt_sha256: str

    def validate(self) -> None:
        if (_SHA256.fullmatch(self.startup_generation) is None
                or type(self.ready_receipt) is not bytes or not self.ready_receipt
                or type(self.custody_release_receipt) is not bytes or not self.custody_release_receipt
                or sha256(self.ready_receipt).hexdigest() != self.ready_receipt_sha256
                or sha256(self.custody_release_receipt).hexdigest()
                != self.custody_release_receipt_sha256):
            raise OfficialCheckError("MCX_CHECK_ACTIVATION_EVIDENCE_INVALID")


@dataclass(frozen=True)
class StagedAuthorityCandidate:
    instrument_root: Path
    market_root: Path
    current_filename: str = "current.json"
    review: object | None = None


@dataclass(frozen=True)
class ValidatedAuthorityCandidate:
    instrument_reference: str
    market_reference: str
    current_sha256: str
    staged_object_sha256: tuple[str, ...]


@dataclass(frozen=True)
class CheckOutcome:
    state: str
    receipt_sha256: str | None
    failure: str | None


@dataclass(frozen=True)
class CleanupOutcome:
    state: str
    owned_workers: int
    unfinished_durable_writes: int
    durable_write_ownership: str
    budget_deadline_ns: int
    entered_operations: int = 0
    worker_thread_identity: int | None = None
    worker_termination: str = "NOT_OBSERVED"


class _Links(HTMLParser):
    _VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img",
                       "input", "link", "meta", "param", "source", "track", "wbr"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._href: str | None = None
        self._text: list[str] = []
        self.links: list[tuple[str, str, str | None]] = []
        self._sections: list[tuple[str, str | None]] = []
        self._detached_family: str | None = None

    @staticmethod
    def _section(attrs) -> str | None:
        values = " ".join(value for key, value in attrs
                          if key.lower() in {"id", "class"} and value).lower()
        compact = re.sub(r"[^a-z0-9]", "", values)
        if any(name in compact for name in ('crudeoilminisection', 'naturalgasminisection',
                'silver100section', 'silvermicrosection', 'goldtensection',
                'goldpetalsection', 'goldguineasection', 'goldsection', 'silversection')):
            return 'OUT_OF_SCOPE'
        aliases = {
            "GOLDM": ("goldmini", "goldm"),
            "SILVERM": ("silvermini", "silverm"),
            "COPPER": ("copper",),
            "CRUDEOIL": ("crudeoil",),
            "NATURALGAS": ("naturalgas",),
        }
        matches = [family for family, terms in aliases.items()
                   if any(term in compact for term in terms)]
        return matches[0] if len(matches) == 1 else None

    def handle_starttag(self, tag, attrs):
        normalized = tag.lower()
        attributes = dict(attrs)
        if normalized == 'section' and attributes.get('id', '').endswith('section'):
            self._detached_family = self._section(attrs)
        inherited = self._sections[-1][1] if self._sections else None
        section = self._section(attrs) or inherited
        # Observed Sitefinity contract accordions are sibling content blocks,
        # labelled by the preceding product section and item-link/item-title IDs.
        # Carry the family only to those exact contract links, never arbitrary
        # later Documents/sidebar PDFs.
        if normalized == 'a' and attributes.get('id', '').startswith('item-link-'):
            section = self._detached_family
        if normalized not in self._VOID:
            self._sections.append((normalized, section))
        if normalized == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        normalized = tag.lower()
        if normalized == "a" and self._href is not None:
            section = self._sections[-1][1] if self._sections else None
            self.links.append((self._href, " ".join(self._text), section))
            self._href = None
            self._text = []
        for index in range(len(self._sections) - 1, -1, -1):
            if self._sections[index][0] == normalized:
                del self._sections[index:]
                break

    def handle_startendtag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href is not None:
                section = self._sections[-1][1] if self._sections else None
                self.links.append((href, "", section))


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _aware(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise OfficialCheckError("MCX_CHECK_TIME_INVALID")
    return value


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _safe_url(url: str, *, document: bool = False) -> None:
    parsed = urlparse(url)
    decoded_path = unquote(parsed.path)
    safe_segments = (".." not in decoded_path.split("/") and "\\" not in decoded_path
                     and "//" not in decoded_path)
    if document:
        valid_query = (not parsed.query
                       or re.fullmatch(r"sfvrsn=[A-Za-z0-9_-]+", parsed.query) is not None)
        valid_path = parsed.path.startswith("/docs/") and valid_query and safe_segments
    else:
        circular = (parsed.path == urlparse(CIRCULARS_PAGE).path
                    and (not parsed.query or re.fullmatch(r"page=[1-9][0-9]*", parsed.query)))
        valid_path = url in set(PRODUCT_PAGES.values()) or circular
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.port not in {None, 443}
            or parsed.username is not None or parsed.password is not None
            or parsed.fragment or not safe_segments or not valid_path):
        raise OfficialCheckError("MCX_CHECK_URL_DENIED")


def _circular_page_number(url: str) -> int | None:
    try:
        _safe_url(url, document=False)
    except OfficialCheckError:
        return None
    parsed = urlparse(url)
    if parsed.path != urlparse(CIRCULARS_PAGE).path:
        return None
    if not parsed.query:
        return 1
    match = re.fullmatch(r"page=([1-9][0-9]*)", parsed.query)
    return None if match is None else int(match.group(1))


def _validate_response(response: OfficialHttpResponse, *, expected_url: str,
                       document: bool) -> bytes:
    if type(response) is not OfficialHttpResponse:
        raise OfficialCheckError("MCX_CHECK_TRANSPORT_INVALID")
    if response.requested_url != expected_url:
        raise OfficialCheckError("MCX_CHECK_RESPONSE_MISMATCH")
    _safe_url(response.requested_url, document=document)
    _safe_url(response.final_url, document=document)
    if len(response.redirects) > MAX_REDIRECTS:
        raise OfficialCheckError("MCX_CHECK_REDIRECT_INVALID")
    for value in response.redirects:
        _safe_url(value, document=document)
    if response.status != 200 or not response.complete or type(response.body) is not bytes:
        raise OfficialCheckError("MCX_CHECK_SOURCE_INCOMPLETE")
    media = response.media_type.split(";", 1)[0].strip().lower()
    limit = MAX_DOCUMENT_BYTES if document else MAX_PAGE_BYTES
    if not 0 < len(response.body) <= limit:
        raise OfficialCheckError("MCX_CHECK_SIZE_INVALID")
    if document:
        if media != "application/pdf":
            raise OfficialCheckError("MCX_CHECK_MEDIA_TYPE_INVALID")
        if not response.body.startswith(b"%PDF-") or not response.body.rstrip().endswith(b"%%EOF"):
            raise OfficialCheckError("MCX_CHECK_PDF_INVALID")
    elif media not in {"text/html", "application/xhtml+xml"}:
        raise OfficialCheckError("MCX_CHECK_MEDIA_TYPE_INVALID")
    return response.body


def _family_terms(family: str) -> tuple[str, ...]:
    return {
        "GOLDM": ("gold mini", "goldm"),
        "SILVERM": ("silver mini", "silverm"),
        "COPPER": ("copper",),
        "CRUDEOIL": ("crude oil", "crudeoil"),
        "NATURALGAS": ("natural gas", "naturalgas"),
    }[family]


def _market_wide_title(value: str) -> bool:
    normalized = " ".join(value.lower().replace("-", " ").split())
    subjects = ("launch calendar", "contract launch", "expiry calendar",
                "trading calendar", "trading hours", "trading session",
                "session timing", "special session", "holiday calendar")
    qualifiers = ("calendar", "launch", "trading", "session", "holiday",
                  "timing", "amendment")
    return any(subject in normalized for subject in subjects) or (
        "amendment" in normalized and any(term in normalized for term in qualifiers[:-1]))


class McxOfficialCheckEngine:
    """One dormant, single-flight, non-authoritative MCX check owner."""

    def __init__(self, store_root: Path, *, transport: Callable[..., OfficialHttpResponse],
                 authority_provider: Callable[[], object],
                 candidate_supplier: Callable[[dict[str, object]], StagedAuthorityCandidate | None]
                 | None = None,
                 frequency: CheckFrequency = CheckFrequency.DAILY,
                 utc_clock: Callable[[], datetime] | None = None,
                 monotonic_clock: Callable[[], float] | None = None,
                 background_runner: Callable[[Callable[[], None]], Thread] | None = None,
                 check_limits: CheckLimits | None = None,
                 replace: Callable[[str | os.PathLike, str | os.PathLike], None] = os.replace) -> None:
        if not isinstance(store_root, Path) or not store_root.is_absolute() or ".." in store_root.parts:
            raise OfficialCheckError("MCX_CHECK_STORE_PATH_INVALID")
        if type(frequency) is not CheckFrequency:
            raise OfficialCheckError("MCX_CHECK_FREQUENCY_INVALID")
        self._limits = check_limits or CheckLimits()
        if type(self._limits) is not CheckLimits:
            raise OfficialCheckError("MCX_CHECK_LIMITS_INVALID")
        self._limits.validate()
        self.store_root = store_root
        self.transport = transport
        self.authority_provider = authority_provider
        self.candidate_supplier = candidate_supplier
        self.frequency = frequency
        self.automatic_check_enabled = True
        self._utc_clock = utc_clock or (lambda: datetime.now(timezone.utc))
        if monotonic_clock is None:
            import time
            monotonic_clock = time.monotonic
        self._monotonic_clock = monotonic_clock
        self._runner = background_runner or self._thread_runner
        self._replace = replace
        self._lock = Lock()
        self._worker_done = Event()
        self._worker_done.set()
        self._active = False
        self._activation_failed = False
        self._draining = False
        self._closed = False
        self._worker_generation = 0
        self._owned_workers = 0
        self._worker_running = False
        self._worker_callback_complete = False
        self._worker_handle: Thread | None = None
        self._worker_identity: int | None = None
        self._worker_launch_uncertain = False
        self._worker_termination = "NOT_OBSERVED"
        self._operations = 0
        self._operations_done = Event()
        self._operations_done.set()
        self._next_due: float | None = None
        self._last_attempt: datetime | None = None
        self._last_attempt_monotonic: float | None = None
        self._last_success: datetime | None = None
        self._last_state: str | None = None
        self._last_failure: str | None = None
        self._last_receipt: str | None = None
        self._durable_writes = 0
        self._write_ownership_unknown = False
        self._maintenance = None
        self._activation_evidence_sha256: str | None = None
        self._canonical_custody = None
        self._cleanup_outcome: CleanupOutcome | None = None

    def bind_canonical_custody(self, custody) -> None:
        from kronos.common.release_admission import AdmissionCustody
        if type(custody) is not AdmissionCustody:
            raise OfficialCheckError('MCX_CHECK_CUSTODY_INVALID')
        custody.check()
        with self._lock:
            if self._active or self._canonical_custody is not None:
                raise OfficialCheckError('MCX_CHECK_ACTIVATION_CONFLICT')
            self._canonical_custody = custody

    def activate_from_canonical(self, server, custody) -> None:
        try:
            digest = self._canonical_activation_digest(server, custody)
            custody.budget.check()
            self._activate_transition(digest)
            custody.budget.check()
        except BaseException:
            with self._lock:
                self._activation_failed = True
            raise

    def _canonical_activation_digest(self, server, custody) -> str:
        """Observe the same actual close-only release and durable READY record."""
        from kronos.common.release_admission import AdmissionCustody
        import errno
        if (type(custody) is not AdmissionCustody or custody is not self._canonical_custody
                or not custody.released or custody.cleanup_started or custody.cleanup_complete
                or getattr(server, 'mcx_official_check', None) is not self
                or server._domain_closed or server.socket.fileno() < 0):
            raise OfficialCheckError('MCX_CHECK_CUSTODY_RELEASE_UNPROVED')
        try:
            os.fstat(custody.descriptor)
        except OSError as error:
            if error.errno != errno.EBADF:
                raise
        else:
            raise OfficialCheckError('MCX_CHECK_CUSTODY_RELEASE_UNPROVED')
        governance = server.connection_governance
        state = governance.maintenance_status()
        if (state.get('startup') != 'READY' or state.get('active') is not False
                or state.get('failure') is not None or governance.shutting_down):
            raise OfficialCheckError('MCX_CHECK_READY_UNPROVED')
        process = governance.process
        path = governance.store.root / 'maintenance' / (process.runtime_identity + '-startup.json')
        raw = path.read_bytes()
        receipt = json.loads(raw)
        if (receipt.get('schema') != 'RUNTIME_STARTUP_MAINTENANCE_EXIT_V1'
                or receipt.get('runtime_identity') != process.runtime_identity
                or receipt.get('maintenance_identity') != governance.maintenance_identity
                or receipt.get('trigger') != 'VERIFIED_CANONICAL_STARTUP'
                or not receipt.get('at')):
            raise OfficialCheckError('MCX_CHECK_READY_UNPROVED')
        return sha256(_canonical({
            'ready_receipt_sha256': sha256(raw).hexdigest(),
            'runtime_identity': process.runtime_identity,
            'custody_descriptor': custody.descriptor,
            'custody_released': custody.released,
            'original_deadline_ns': custody.budget.deadline_ns,
        })).hexdigest()

    def cleanup_complete(self) -> bool:
        with self._lock:
            return self._cleanup_outcome is not None and self._cleanup_outcome.state == 'CLOSED'

    @staticmethod
    def _thread_runner(callback: Callable[[], None]) -> Thread:
        handle = Thread(target=callback, name="kronos-mcx-official-check", daemon=True)
        handle.start()
        return handle

    def _reserve_operation(self, *, activation: bool = False) -> None:
        with self._lock:
            unavailable = self._draining or self._closed or self._activation_failed
            if activation:
                unavailable = unavailable or self._active or self._operations
            else:
                unavailable = unavailable or not self._active
            if unavailable:
                raise OfficialCheckError("MCX_CHECK_ACTIVATION_CONFLICT" if activation
                                         else "MCX_CHECK_NOT_AVAILABLE")
            self._operations += 1
            self._operations_done.clear()

    def _release_operation(self) -> None:
        with self._lock:
            self._operations -= 1
            if self._operations == 0:
                self._operations_done.set()

    def _reap_worker(self) -> None:
        with self._lock:
            handle = self._worker_handle
        if handle is None or handle is current_thread() or handle.ident is None:
            return
        handle.join(0)
        if handle.is_alive():
            return
        with self._lock:
            if self._worker_handle is handle:
                self._worker_identity = handle.ident
                self._worker_handle = None
                self._owned_workers = 0
                self._worker_launch_uncertain = False
                self._worker_termination = "OBSERVED"
                self._worker_done.set()

    def bind_maintenance_admission(self, admission) -> None:
        with self._lock:
            if self._active or self._maintenance is not None:
                raise OfficialCheckError("MCX_CHECK_MAINTENANCE_BINDING_CONFLICT")
            self._maintenance = admission

    def _ensure_store(self) -> None:
        current = Path(self.store_root.anchor)
        for part in self.store_root.parts[1:]:
            current /= part
            if current.exists():
                info = current.lstat()
                if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                    raise OfficialCheckError("MCX_CHECK_STORE_PATH_INVALID")
            else:
                current.mkdir(mode=0o700)
            info = current.lstat()
            if current == self.store_root:
                if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                    raise OfficialCheckError("MCX_CHECK_STORE_PERMISSION_INVALID")
        for name in ("objects", "receipts"):
            path = self.store_root / name
            path.mkdir(mode=0o700, exist_ok=True)
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise OfficialCheckError("MCX_CHECK_STORE_PATH_INVALID")
            os.chmod(path, 0o700)
        for path in self.store_root.glob(".*.tmp"):
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                raise OfficialCheckError("MCX_CHECK_RECOVERY_UNRESOLVED")
            path.unlink()
        self._fsync_directory(self.store_root)

    def _recover_documents(self) -> None:
        """Recover only already-durable local state; never infer a check result."""
        config = self.store_root / "configuration.json"
        if config.exists():
            value = self._read_local_document(config)
            if (set(value) != {"schema", "frequency", "automatic_check_enabled"}
                    or value["schema"] != "KRONOS-MCX-OFFICIAL-CHECK-CONFIG-V1"
                    or type(value["automatic_check_enabled"]) is not bool):
                raise OfficialCheckError("MCX_CHECK_CONFIGURATION_INVALID")
            try:
                self.frequency = CheckFrequency(value["frequency"])
                self.automatic_check_enabled = value['automatic_check_enabled']
            except (TypeError, ValueError):
                raise OfficialCheckError("MCX_CHECK_CONFIGURATION_INVALID") from None
        status = self.store_root / "status.json"
        if status.exists():
            value = self._read_local_document(status)
            if value.get("schema") != "KRONOS-MCX-OFFICIAL-CHECK-STATUS-V1":
                raise OfficialCheckError("MCX_CHECK_STATUS_INVALID")
            state = value.get("checker_state")
            if state not in {item.value for item in CheckerState}:
                raise OfficialCheckError("MCX_CHECK_STATUS_INVALID")
            try:
                attempt = (None if value.get("last_attempt") is None else
                           _aware(datetime.fromisoformat(value["last_attempt"])))
                success = (None if value.get("last_successful_check") is None else
                           _aware(datetime.fromisoformat(value["last_successful_check"])))
            except (TypeError, ValueError):
                raise OfficialCheckError("MCX_CHECK_STATUS_INVALID") from None
            receipt = value.get("last_receipt_sha256")
            if receipt is not None and _SHA256.fullmatch(receipt) is None:
                raise OfficialCheckError("MCX_CHECK_STATUS_INVALID")
            with self._lock:
                self._last_state = state
                self._last_attempt = attempt
                self._last_success = success
                self._last_failure = value.get("failure")
                self._last_receipt = receipt

    @staticmethod
    def _read_local_document(path: Path) -> dict[str, object]:
        try:
            value = json.loads(McxOfficialCheckEngine._read_private_file(
                path, max_bytes=2 * 1024 * 1024))
            if type(value) is not dict:
                raise OfficialCheckError("MCX_CHECK_LOCAL_STATE_INVALID")
            return value
        except (OSError, ValueError, TypeError, UnicodeError):
            raise OfficialCheckError("MCX_CHECK_LOCAL_STATE_INVALID") from None

    @staticmethod
    def _read_private_file(path: Path, *, max_bytes: int) -> bytes:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                before = os.fstat(fd)
                if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                        or stat.S_IMODE(before.st_mode) != 0o600
                        or not 0 < before.st_size <= max_bytes):
                    raise OfficialCheckError("MCX_CHECK_LOCAL_STATE_INVALID")
                chunks, remaining = [], before.st_size
                while remaining:
                    chunk = os.read(fd, min(remaining, 1024 * 1024))
                    if not chunk:
                        raise OfficialCheckError("MCX_CHECK_LOCAL_STATE_INVALID")
                    chunks.append(chunk); remaining -= len(chunk)
                if os.read(fd, 1):
                    raise OfficialCheckError("MCX_CHECK_LOCAL_STATE_INVALID")
                after = os.fstat(fd)
                stable = (before.st_dev, before.st_ino, before.st_size,
                          before.st_mtime_ns, before.st_ctime_ns)
                observed = (after.st_dev, after.st_ino, after.st_size,
                            after.st_mtime_ns, after.st_ctime_ns)
                if stable != observed:
                    raise OfficialCheckError("MCX_CHECK_LOCAL_STATE_CHANGED")
                return b"".join(chunks)
            finally:
                os.close(fd)
        except OfficialCheckError:
            raise
        except OSError:
            raise OfficialCheckError("MCX_CHECK_LOCAL_STATE_INVALID") from None

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _begin_write(self) -> None:
        with self._lock:
            self._durable_writes += 1

    def _finish_write(self, *, resolved: bool) -> None:
        with self._lock:
            self._durable_writes -= 1
            if not resolved:
                self._write_ownership_unknown = True

    @staticmethod
    def _write_exact(fd: int, payload: bytes) -> None:
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if type(written) is not int or written <= 0 or written > len(payload) - offset:
                raise OfficialCheckError("MCX_CHECK_DURABLE_WRITE_UNRESOLVED")
            offset += written

    def _atomic_document(self, name: str, value: object) -> str:
        payload = _canonical(value) + b"\n"
        digest = sha256(payload).hexdigest()
        temp = self.store_root / f".{name}.{digest}.tmp"
        final = self.store_root / name
        self._begin_write()
        resolved = False
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                self._write_exact(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
            if self._read_private_file(temp, max_bytes=2 * 1024 * 1024) != payload:
                raise OfficialCheckError("MCX_CHECK_DURABLE_WRITE_UNRESOLVED")
            self._replace(temp, final)
            self._fsync_directory(self.store_root)
            if self._read_private_file(final, max_bytes=2 * 1024 * 1024) != payload:
                raise OfficialCheckError("MCX_CHECK_DURABLE_WRITE_UNRESOLVED")
            resolved = True
            return digest
        except OSError as error:
            raise OfficialCheckError("MCX_CHECK_DURABLE_WRITE_UNRESOLVED") from error
        finally:
            self._finish_write(resolved=resolved)

    def _object(self, payload: bytes) -> str:
        digest = sha256(payload).hexdigest()
        path = self.store_root / "objects" / digest
        self._begin_write()
        resolved = False
        try:
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                if self._read_private_file(path, max_bytes=MAX_DOCUMENT_BYTES) != payload:
                    raise OfficialCheckError("MCX_CHECK_OBJECT_CONFLICT")
                resolved = True
                return digest
            try:
                self._write_exact(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
            self._fsync_directory(path.parent)
            if self._read_private_file(path, max_bytes=MAX_DOCUMENT_BYTES) != payload:
                raise OfficialCheckError("MCX_CHECK_DURABLE_WRITE_UNRESOLVED")
            resolved = True
            return digest
        except OSError as error:
            raise OfficialCheckError("MCX_CHECK_DURABLE_WRITE_UNRESOLVED") from error
        finally:
            self._finish_write(resolved=resolved)

    def _immutable_receipt(self, value: dict[str, object]) -> str:
        payload = _canonical(value) + b"\n"
        digest = sha256(payload).hexdigest()
        path = self.store_root / "receipts" / f"{digest}.json"
        self._begin_write()
        resolved = False
        try:
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                if self._read_private_file(path, max_bytes=2 * 1024 * 1024) != payload:
                    raise OfficialCheckError("MCX_CHECK_RECEIPT_CONFLICT")
                resolved = True
                return digest
            try:
                self._write_exact(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
            self._fsync_directory(path.parent)
            if self._read_private_file(path, max_bytes=2 * 1024 * 1024) != payload:
                raise OfficialCheckError("MCX_CHECK_DURABLE_WRITE_UNRESOLVED")
            resolved = True
            return digest
        except OSError as error:
            raise OfficialCheckError("MCX_CHECK_DURABLE_WRITE_UNRESOLVED") from error
        finally:
            self._finish_write(resolved=resolved)

    def activate(self, evidence: ActivationEvidence) -> None:
        if type(evidence) is not ActivationEvidence:
            raise OfficialCheckError("MCX_CHECK_ACTIVATION_EVIDENCE_INVALID")
        evidence.validate()
        self._activate_transition(sha256(_canonical({
            'startup_generation': evidence.startup_generation,
            'ready_receipt_sha256': evidence.ready_receipt_sha256,
            'custody_release_receipt_sha256': evidence.custody_release_receipt_sha256,
        })).hexdigest())

    def _activate_transition(self, evidence_digest: str) -> None:
        self._reserve_operation(activation=True)
        try:
            self._ensure_store()
            self._recover_documents()
            self._atomic_document("configuration.json", {
                "schema": "KRONOS-MCX-OFFICIAL-CHECK-CONFIG-V1",
                "frequency": self.frequency.value,
                "automatic_check_enabled": self.automatic_check_enabled,
            })
            next_due = self._due_from_history(self.frequency)
            with self._lock:
                if self._draining or self._closed:
                    raise OfficialCheckError("MCX_CHECK_ACTIVATION_CANCELLED")
                self._active = True
                self._next_due = next_due
                self._activation_evidence_sha256 = evidence_digest
        except BaseException:
            with self._lock:
                self._activation_failed = True
            raise
        finally:
            self._release_operation()

    def set_frequency(self, frequency: CheckFrequency) -> None:
        self.configure(automatic_check_enabled=self.automatic_check_enabled, frequency=frequency)

    def _due_from_history(self, frequency: CheckFrequency) -> float:
        current = self._monotonic_clock()
        if self._last_attempt is None:
            return current
        due = self._last_attempt + timedelta(seconds=frequency.interval_seconds)
        return current + max(0.0, (due - _aware(self._utc_clock())).total_seconds())

    def configure(self, *, automatic_check_enabled: bool,
                  frequency: CheckFrequency) -> None:
        if type(frequency) is not CheckFrequency:
            raise OfficialCheckError("MCX_CHECK_FREQUENCY_INVALID")
        if type(automatic_check_enabled) is not bool:
            raise OfficialCheckError('MCX_CHECK_CONFIGURATION_INVALID')
        self._reserve_operation()
        try:
            next_due = self._due_from_history(frequency)
            self._atomic_document("configuration.json", {
                "schema": "KRONOS-MCX-OFFICIAL-CHECK-CONFIG-V1",
                "frequency": frequency.value,
                "automatic_check_enabled": automatic_check_enabled,
            })
            with self._lock:
                if self._draining or self._closed:
                    raise OfficialCheckError("MCX_CHECK_CONFIGURATION_CANCELLED")
                self.frequency = frequency
                self.automatic_check_enabled = automatic_check_enabled
                self._next_due = next_due
        finally:
            self._release_operation()

    def check_now(self) -> str:
        with self._lock:
            if not self._active or self._draining or self._closed or self._activation_failed:
                return "DENIED"
        return self._schedule(manual=True, observed=self._monotonic_clock())

    def trigger_scheduled(self, *, observed: float | None = None) -> str:
        with self._lock:
            if not self._active or self._draining or self._closed or self._activation_failed:
                return "DENIED"
            if not self.automatic_check_enabled:
                return 'DISABLED'
        return self._schedule(manual=False,
                              observed=self._monotonic_clock() if observed is None else observed)

    def _schedule(self, *, manual: bool, observed: float) -> str:
        self._reap_worker()
        ticket = None
        with self._lock:
            if not self._active or self._draining or self._closed or self._activation_failed:
                return "DENIED"
            if self._owned_workers:
                return "PENDING"
            if not manual and (self._next_due is None or observed < self._next_due):
                return "NOT_DUE"
        if self._maintenance is not None:
            ticket = self._maintenance.admit_root("HOUSEKEEPING")
            if ticket is None:
                return "DENIED"
        with self._lock:
            if self._owned_workers or self._draining or self._closed:
                if ticket is not None:
                    ticket.release()
                return "PENDING" if self._owned_workers else "DENIED"
            self._worker_generation += 1
            generation = self._worker_generation
            self._owned_workers = 1
            self._worker_running = False
            self._worker_callback_complete = False
            self._worker_handle = None
            self._worker_identity = None
            self._worker_launch_uncertain = True
            self._worker_termination = "NOT_OBSERVED"
            self._worker_done.clear()
        try:
            handle = self._runner(lambda: self._worker(generation, ticket))
            if type(handle) is not Thread or handle.ident is None:
                raise OfficialCheckError("MCX_CHECK_WORKER_HANDLE_INVALID")
            with self._lock:
                if self._worker_generation == generation:
                    self._worker_handle = handle
                    self._worker_identity = handle.ident
                    self._worker_launch_uncertain = False
        except BaseException:
            with self._lock:
                self._activation_failed = True
                self._last_failure = "MCX_CHECK_WORKER_START_FAILED"
            raise
        return "SCHEDULED"

    def _worker(self, generation: int, ticket) -> None:
        try:
            with self._lock:
                cancelled = (self._worker_generation != generation
                             or self._activation_failed or self._draining or self._closed)
            if not cancelled:
                if ticket is None:
                    self._worker_owned(generation)
                else:
                    with ticket.activate():
                        self._worker_owned(generation)
        finally:
            if ticket is not None:
                ticket.release()
            with self._lock:
                if self._worker_generation == generation:
                    self._worker_running = False
                    self._worker_callback_complete = True

    def _worker_owned(self, generation: int) -> None:
        with self._lock:
            if (self._worker_generation != generation or self._activation_failed
                    or self._draining or self._closed):
                return
            self._worker_running = True
        outcome = self._perform_check()
        with self._lock:
            self._last_state = outcome.state
            self._last_failure = outcome.failure
            if outcome.receipt_sha256 is not None:
                self._last_receipt = outcome.receipt_sha256
            self._next_due = (self._last_attempt_monotonic + self.frequency.interval_seconds
                              if self._last_attempt_monotonic is not None else self._monotonic_clock())

    def _check_scope(self, scope: _CheckScope) -> None:
        if (scope.requests > self._limits.max_requests
                or scope.documents > self._limits.max_documents
                or scope.bytes > self._limits.max_bytes):
            raise OfficialCheckError("MCX_CHECK_LIMIT_EXHAUSTED")
        if (self._monotonic_clock() - scope.started
                >= float(self._limits.max_duration_seconds)):
            raise OfficialCheckError("MCX_CHECK_DEADLINE_EXPIRED")

    def _fetch(self, url: str, *, document: bool,
               scope: _CheckScope | None = None, _redirects: tuple[str, ...] = ()) -> OfficialHttpResponse:
        _safe_url(url, document=document)
        if scope is not None:
            scope.requests += 1
            if document:
                scope.documents += 1
            self._check_scope(scope)
        try:
            remaining = (float(self._limits.max_duration_seconds)
                if scope is None else max(0.001, float(self._limits.max_duration_seconds)
                    - (self._monotonic_clock() - scope.started)))
            response = self.transport(
                url, connect_timeout_seconds=min(CONNECT_TIMEOUT_SECONDS, remaining),
                read_timeout_seconds=min(READ_TIMEOUT_SECONDS, remaining),
                max_bytes=MAX_DOCUMENT_BYTES if document else MAX_PAGE_BYTES,
                max_redirects=MAX_REDIRECTS,
                whole_check_remaining_seconds=remaining,
            )
        except OfficialCheckError:
            raise
        except Exception as error:
            raise OfficialCheckError("MCX_CHECK_TRANSPORT_FAILED") from error
        if type(response) is not OfficialHttpResponse:
            raise OfficialCheckError("MCX_CHECK_TRANSPORT_INVALID")
        if scope is not None:
            if type(response.body) is not bytes:
                raise OfficialCheckError("MCX_CHECK_TRANSPORT_INVALID")
            scope.bytes += len(response.body)
            if type(self.transport) is OfficialHttpsTransport:
                retained = self._object(response.body) if response.body else None
                scope.responses.append(self._observation('HTTPS_RESPONSE', response,
                    response.body, retained_object_sha256=retained))
            self._check_scope(scope)
        if response.status in {301, 302, 303, 307, 308}:
            if (not response.location or len(_redirects) >= MAX_REDIRECTS
                    or response.requested_url != url or response.final_url != url):
                raise OfficialCheckError('MCX_CHECK_REDIRECT_INVALID')
            following = urljoin(url, response.location)
            _safe_url(following, document=document)
            if not document and urlparse(url).path == urlparse(CIRCULARS_PAGE).path:
                if _circular_page_number(following) != _circular_page_number(url):
                    raise OfficialCheckError('MCX_CHECK_PAGINATION_INVALID')
            final = self._fetch(following, document=document, scope=scope,
                                _redirects=_redirects + (following,))
            return OfficialHttpResponse(**{**final.__dict__, 'requested_url': url,
                'redirects': (following,) + final.redirects})
        return response

    @staticmethod
    def _observation(kind: str, response: OfficialHttpResponse, body: bytes,
                     **extra) -> dict[str, object]:
        return {
            "kind": kind,
            "requested_url": response.requested_url,
            "final_url": response.final_url,
            "redirects": list(response.redirects),
            "status": response.status,
            "media_type": response.media_type,
            "size": len(body),
            "sha256": sha256(body).hexdigest(),
            **extra,
        }

    def _discover(self, scope: _CheckScope
                  ) -> tuple[dict[str, dict[str, str]], tuple[int, int],
                             list[dict[str, object]]]:
        documents: dict[str, dict[str, str]] = {family: {} for family in FAMILIES}
        observations: list[dict[str, object]] = []
        for family, url in PRODUCT_PAGES.items():
            response = self._fetch(url, document=False, scope=scope)
            body = _validate_response(response, expected_url=url, document=False)
            parser = _Links(); parser.feed(body.decode("utf-8"))
            link_audit = []
            for href, text, section in parser.links:
                candidate = urljoin(response.final_url, href)
                try:
                    _safe_url(candidate, document=True)
                except OfficialCheckError:
                    continue
                haystack = f"{text} {candidate}".lower().replace("-", " ")
                accepted = (section == family or
                            (section is None and any(term in haystack
                                                     for term in _family_terms(family))))
                if urlparse(candidate).path.lower().endswith(".pdf") and accepted:
                    documents[family][candidate] = "FAMILY_PRODUCT_CANDIDATE"
                link_audit.append({"source_href": href, "resolved_url": candidate,
                                   "text_sha256": sha256(text.encode()).hexdigest(),
                                   "section_family": section, "accepted": accepted})
            if not documents[family]:
                raise OfficialCheckError("MCX_CHECK_PRODUCT_SOURCE_INCOMPLETE")
            retained = self._object(body)
            observations.append(self._observation(
                "PRODUCT_PAGE", response, body, family=family, links=link_audit,
                retained_object_sha256=retained,
                evidence_role="DISCOVERY_PAGE"))

        page_url = CIRCULARS_PAGE
        page_count: int | None = None
        intervals: list[tuple[int, int]] = []
        seen_pages = set()
        relevant = 0
        page_number = 1
        while True:
            if page_number > self._limits.max_circular_pages or page_url in seen_pages:
                raise OfficialCheckError("MCX_CHECK_LIMIT_EXHAUSTED")
            seen_pages.add(page_url)
            response = self._fetch(page_url, document=False, scope=scope)
            body = _validate_response(response, expected_url=page_url, document=False)
            if (_circular_page_number(response.final_url) != page_number
                    or any(_circular_page_number(value) != page_number
                           for value in response.redirects)):
                raise OfficialCheckError("MCX_CHECK_PAGINATION_INVALID")
            parser = _Links(); parser.feed(body.decode("utf-8"))
            if (type(response.page_number) is not int
                    or type(response.page_count) is not int
                    or type(response.page_item_count) is not int
                    or response.page_number != page_number
                    or response.page_count < 1
                    or response.page_count > self._limits.max_circular_pages
                    or response.page_item_count != len(parser.links)):
                raise OfficialCheckError("MCX_CHECK_PAGINATION_INCOMPLETE")
            if page_count is None:
                page_count = response.page_count
            elif response.page_count != page_count:
                raise OfficialCheckError("MCX_CHECK_PAGINATION_INCOMPLETE")
            if (type(response.circular_from) is not int
                    or type(response.circular_through) is not int
                    or response.circular_from < 0
                    or response.circular_through < response.circular_from):
                raise OfficialCheckError("MCX_CHECK_CIRCULAR_RANGE_INCOMPLETE")
            intervals.append((response.circular_from, response.circular_through))
            link_audit = []
            for href, text, section in parser.links:
                candidate = urljoin(response.final_url, href)
                try:
                    _safe_url(candidate, document=True)
                except OfficialCheckError:
                    continue
                if not urlparse(candidate).path.lower().endswith(".pdf"):
                    continue
                haystack = f"{text} {candidate}".lower().replace("-", " ")
                families = [family for family in FAMILIES
                            if any(term in haystack for term in _family_terms(family))]
                classification = "FAMILY_CIRCULAR_CANDIDATE"
                if _market_wide_title(haystack):
                    families = list(FAMILIES)
                    classification = "MARKET_WIDE_GOVERNING_CANDIDATE"
                for family in families:
                    documents[family][candidate] = classification
                    relevant += 1
                link_audit.append({"source_href": href, "resolved_url": candidate,
                                   "text_sha256": sha256(text.encode()).hexdigest(),
                                   "families": families,
                                   "classification": classification if families else None})
            retained = self._object(body)
            observations.append(self._observation(
                "CIRCULAR_INDEX_PAGE", response, body, page_number=page_number,
                page_count=page_count, page_item_count=response.page_item_count,
                circular_from=response.circular_from,
                circular_through=response.circular_through,
                next_page_url=response.next_page_url, links=link_audit,
                retained_object_sha256=retained,
                evidence_role="DISCOVERY_PAGE"))
            if page_number == page_count:
                if response.next_page_url is not None:
                    raise OfficialCheckError("MCX_CHECK_PAGINATION_INCOMPLETE")
                break
            if type(response.next_page_url) is not str:
                raise OfficialCheckError("MCX_CHECK_PAGINATION_INCOMPLETE")
            if _circular_page_number(response.next_page_url) != page_number + 1:
                raise OfficialCheckError("MCX_CHECK_PAGINATION_INVALID")
            page_url = response.next_page_url
            page_number += 1
        if not relevant:
            raise OfficialCheckError("MCX_CHECK_CIRCULAR_SOURCE_INCOMPLETE")
        covered = sorted(intervals)
        for previous, following in zip(covered, covered[1:]):
            if following[0] > previous[1] + 1:
                raise OfficialCheckError("MCX_CHECK_CIRCULAR_RANGE_INCOMPLETE")
        unique_documents = {url for values in documents.values() for url in values}
        if len(unique_documents) > self._limits.max_documents:
            raise OfficialCheckError("MCX_CHECK_LIMIT_EXHAUSTED")
        return documents, (covered[0][0], max(value[1] for value in covered)), observations

    def _active_hashes(self, authority) -> set[str]:
        result = set()
        for value in authority.instrument.source_provenance:
            if "/SHA256:" not in value:
                raise OfficialCheckError("MCX_CHECK_ACTIVE_AUTHORITY_INVALID")
            digest = value.rsplit("/SHA256:", 1)[1]
            if _SHA256.fullmatch(digest) is None:
                raise OfficialCheckError("MCX_CHECK_ACTIVE_AUTHORITY_INVALID")
            result.add(digest)
        return result

    def _validate_candidate(self, receipt: dict[str, object], staged: tuple[str, ...], active
                            ) -> ValidatedAuthorityCandidate | None:
        if self.candidate_supplier is None:
            return None
        candidate = self.candidate_supplier(receipt)
        if candidate is None:
            return None
        if type(candidate) is not StagedAuthorityCandidate:
            raise OfficialCheckError("MCX_CHECK_CANDIDATE_INVALID")
        from kronos.theta.target_authority import OwnerOptionAuthority
        owner = OwnerOptionAuthority(
            instrument_root=candidate.instrument_root,
            market_root=candidate.market_root,
            current_filename=candidate.current_filename,
            review=candidate.review,
        )
        candidate_hashes = {value.rsplit("/SHA256:", 1)[1]
                            for value in owner.instrument.source_provenance}
        if not candidate_hashes or not candidate_hashes <= set(staged):
            raise OfficialCheckError("MCX_CHECK_CANDIDATE_EVIDENCE_MISSING")
        if (owner.instrument.pin.reference == active.instrument.pin.reference
                and owner.market.pin.reference == active.market.pin.reference
                and owner.current_sha256 == active.current_sha256):
            return None
        return ValidatedAuthorityCandidate(owner.instrument.pin.reference,
                                           owner.market.pin.reference,
                                           owner.current_sha256, staged)

    def _perform_check(self) -> CheckOutcome:
        observed = _aware(self._utc_clock())
        scope = _CheckScope(self._monotonic_clock())
        attempt_receipt_digest: str | None = None
        with self._lock:
            self._last_attempt = observed
            self._last_attempt_monotonic = scope.started
        try:
            authority = self.authority_provider()
            active = self._active_hashes(authority)
            comparison_authority = {
                "instrument_reference": authority.instrument.pin.reference,
                "market_reference": authority.market.pin.reference,
                "current_sha256": authority.current_sha256,
            }
            documents, circular_range, observations = self._discover(scope)
            staged: list[str] = []
            document_records: list[dict[str, object]] = []
            selected: dict[str, dict[str, object]] = {}
            for family, family_documents in documents.items():
                for url, classification in family_documents.items():
                    item = selected.setdefault(url, {"families": set(),
                                                     "classifications": set()})
                    item["families"].add(family)
                    item["classifications"].add(classification)
            for url in sorted(selected):
                response = self._fetch(url, document=True, scope=scope)
                payload = _validate_response(response, expected_url=url, document=True)
                digest = self._object(payload)
                staged.append(digest)
                classifications = selected[url]["classifications"]
                classification = ("MARKET_WIDE_GOVERNING_CANDIDATE"
                                  if "MARKET_WIDE_GOVERNING_CANDIDATE" in classifications
                                  else sorted(classifications)[0])
                document_records.append({
                    "families": sorted(selected[url]["families"]),
                    "source_url": url,
                    "requested_url": response.requested_url,
                    "final_url": response.final_url,
                    "redirects": list(response.redirects),
                    "sha256": digest,
                    "size": len(payload),
                    "classification": classification,
                })
            unique_staged = tuple(sorted(set(staged)))
            self._check_scope(scope)
            receipt = {
                "schema": "KRONOS-MCX-OFFICIAL-CHECK-RECEIPT-V1",
                "retrieved_at": observed.isoformat(),
                "circular_from": circular_range[0],
                "circular_through": circular_range[1],
                "scan_complete": True,
                "observations": observations,
                "documents": document_records,
                "comparison_authority": comparison_authority,
                "discovery_inputs": {
                    "product_pages": dict(PRODUCT_PAGES),
                    "circulars_page": CIRCULARS_PAGE,
                    "limits": asdict(self._limits),
                    "observed_requests": scope.requests,
                    "observed_documents": scope.documents,
                    "observed_bytes": scope.bytes,
                },
                "semantic_mapping_approved": False,
            }
            candidate = self._validate_candidate(receipt, unique_staged, authority)
            self._check_scope(scope)
            changed = any(digest not in active for digest in unique_staged)
            if candidate is not None:
                receipt["validated_candidate"] = asdict(candidate)
                state = CheckerState.AWAITING_REVIEW.value
            else:
                state = (CheckerState.UPDATE_AVAILABLE.value if changed
                         else CheckerState.CURRENT.value)
            receipt["state"] = state
            digest = self._immutable_receipt(receipt)
            attempt_receipt_digest = digest
            self._check_scope(scope)
            self._atomic_document("status.json", {
                "schema": "KRONOS-MCX-OFFICIAL-CHECK-STATUS-V1",
                "checker_state": state,
                "last_attempt": observed.isoformat(),
                "last_successful_check": observed.isoformat(),
                "last_receipt_sha256": digest,
                "active_authority": self._coverage(authority, observed),
            })
            self._check_scope(scope)
            with self._lock:
                self._last_success = observed
            return CheckOutcome(state, digest, None)
        except Exception as error:
            code = str(error) if type(error) is OfficialCheckError else "MCX_CHECK_FAILED"
            try:
                if scope.responses:
                    failure_receipt = self._immutable_receipt({
                        'schema': 'KRONOS-MCX-OFFICIAL-CHECK-FAILED-V1',
                        'retrieved_at': observed.isoformat(), 'failure': code,
                        'scan_complete': False, 'responses': scope.responses,
                        'limits': asdict(self._limits),
                        'observed_requests': scope.requests, 'observed_bytes': scope.bytes,
                    })
                else:
                    failure_receipt = None
                failure_status = {
                    "schema": "KRONOS-MCX-OFFICIAL-CHECK-STATUS-V1",
                    "checker_state": CheckerState.FAILED.value,
                    "last_attempt": observed.isoformat(),
                    "last_successful_check": _iso(self._last_success),
                    "last_receipt_sha256": self._last_receipt,
                    "failure": code,
                }
                if attempt_receipt_digest is not None:
                    failure_status["attempt_receipt_sha256"] = attempt_receipt_digest
                if failure_receipt is not None:
                    failure_status['failure_receipt_sha256'] = failure_receipt
                self._atomic_document("status.json", failure_status)
            except Exception:
                code = "MCX_CHECK_DURABLE_WRITE_UNRESOLVED"
            return CheckOutcome(CheckerState.FAILED.value, None, code)

    @staticmethod
    def _coverage(authority, at: datetime) -> dict[str, object]:
        endpoints = {item.series_identity: item for item in authority.market.endpoints}
        families: dict[str, object] = {}
        losses: list[tuple[datetime, str]] = []
        for family in FAMILIES:
            complete = sorted(((row, endpoints[row.identity]) for row in authority.instrument.rows
                               if row.family == family and row.identity in endpoints),
                              key=lambda item: item[1].expires_at)
            eligible = [(row, endpoint) for row, endpoint in complete
                        if authority.first <= at <= authority.last and at < endpoint.expires_at]
            targets = eligible[:2]
            governing = authority.last
            roster_loss = (eligible[-2][1].expires_at if len(eligible) >= 2 else at)
            loss = min(roster_loss, governing)
            losses.append((loss, family))
            remaining = loss - at
            if remaining <= timedelta(0):
                warning = "UNAVAILABLE"
            elif remaining <= timedelta(days=7):
                warning = "7 DAYS"
            elif remaining <= timedelta(days=14):
                warning = "14 DAYS"
            elif remaining <= timedelta(days=30):
                warning = "30 DAYS"
            else:
                warning = "NONE"
            families[family] = {
                "authority_health": "USABLE" if len(targets) == 2 else "UNAVAILABLE",
                "e1": None if len(targets) < 1 else targets[0][0].identity,
                "e2": None if len(targets) < 2 else targets[1][0].identity,
                "complete_approved_roster_count": len(complete),
                "eligible_count": len(eligible),
                "coverage_loss_at": loss.isoformat(),
                "warning": warning,
            }
        earliest, family = min(losses)
        return {
            "instrument_reference": authority.instrument.pin.reference,
            "market_reference": authority.market.pin.reference,
            "current_sha256": authority.current_sha256,
            "families": families,
            "earliest_shared_coverage_loss": {
                "family": family, "at": earliest.isoformat()},
        }

    def settings_status(self) -> dict[str, object]:
        """Read-only Settings projection; no check, persistence or transport."""
        status = self.status_document()
        try:
            coverage = self.coverage()
        except (ValueError, OSError, TypeError, KeyError):
            coverage = {'families': {}, 'failure': 'ACTIVE_AUTHORITY_UNAVAILABLE'}
        return {**{key: status[key] for key in (
            'lifecycle_state', 'checker_state', 'last_attempt', 'last_successful_check',
            'last_failure', 'frequency', 'automatic_check_enabled', 'next_scheduled_check')},
            'coverage': coverage}

    def coverage(self, at: datetime | None = None) -> dict[str, object]:
        return self._coverage(self.authority_provider(), _aware(at or self._utc_clock()))

    def retained_discovery_pages(self, receipt_sha256: str) -> tuple[bytes, ...]:
        """Read exact discovery inputs without any network refetch."""
        if type(receipt_sha256) is not str or _SHA256.fullmatch(receipt_sha256) is None:
            raise OfficialCheckError("MCX_CHECK_DISCOVERY_EVIDENCE_INVALID")
        try:
            receipt_bytes = self._read_private_file(
                self.store_root / "receipts" / f"{receipt_sha256}.json",
                max_bytes=2 * 1024 * 1024)
            if sha256(receipt_bytes).hexdigest() != receipt_sha256:
                raise OfficialCheckError("MCX_CHECK_DISCOVERY_EVIDENCE_INVALID")
            receipt = json.loads(receipt_bytes)
            observations = receipt.get("observations")
            if (receipt.get("schema") != "KRONOS-MCX-OFFICIAL-CHECK-RECEIPT-V1"
                    or type(observations) is not list or not observations):
                raise OfficialCheckError("MCX_CHECK_DISCOVERY_EVIDENCE_INVALID")
            result = []
            for observation in observations:
                if (type(observation) is not dict
                        or observation.get("kind") not in {
                            "PRODUCT_PAGE", "CIRCULAR_INDEX_PAGE"}
                        or observation.get("evidence_role") != "DISCOVERY_PAGE"):
                    raise OfficialCheckError("MCX_CHECK_DISCOVERY_EVIDENCE_INVALID")
                digest = observation.get("retained_object_sha256")
                if (type(digest) is not str or _SHA256.fullmatch(digest) is None
                        or observation.get("sha256") != digest):
                    raise OfficialCheckError("MCX_CHECK_DISCOVERY_EVIDENCE_INVALID")
                payload = self._read_private_file(
                    self.store_root / "objects" / digest, max_bytes=MAX_PAGE_BYTES)
                if sha256(payload).hexdigest() != digest:
                    raise OfficialCheckError("MCX_CHECK_DISCOVERY_EVIDENCE_INVALID")
                result.append(payload)
            return tuple(result)
        except OfficialCheckError as error:
            if str(error) == "MCX_CHECK_DISCOVERY_EVIDENCE_INVALID":
                raise
            raise OfficialCheckError("MCX_CHECK_DISCOVERY_EVIDENCE_INVALID") from error
        except (OSError, ValueError, TypeError, UnicodeError) as error:
            raise OfficialCheckError("MCX_CHECK_DISCOVERY_EVIDENCE_INVALID") from error

    def status_document(self) -> dict[str, object]:
        self._reap_worker()
        with self._lock:
            if self._closed:
                lifecycle = ("STOPPED" if not self._owned_workers and not self._durable_writes
                             and not self._operations else "CLOSE_PENDING")
            elif self._draining:
                lifecycle = "DRAINING"
            elif self._activation_failed:
                lifecycle = "ACTIVATION_FAILED"
            elif not self._active:
                lifecycle = "DORMANT"
            elif self._worker_running:
                lifecycle = "RUNNING"
            elif self._owned_workers:
                lifecycle = "SCHEDULED"
            else:
                lifecycle = "IDLE"
            return {
                "lifecycle_state": lifecycle,
                "checker_state": self._last_state,
                "last_attempt": _iso(self._last_attempt),
                "last_successful_check": _iso(self._last_success),
                "last_failure": self._last_failure,
                "last_receipt_sha256": self._last_receipt,
                "frequency": self.frequency.value,
                "automatic_check_enabled": self.automatic_check_enabled,
                "next_scheduled_check": (_iso(self._last_attempt + timedelta(
                    seconds=self.frequency.interval_seconds))
                    if self.automatic_check_enabled and self._last_attempt else None),
                "next_check_monotonic": self._next_due,
                "owned_workers": self._owned_workers,
                "worker_generation": self._worker_generation,
                "worker_thread_identity": self._worker_identity,
                "worker_callback_complete": self._worker_callback_complete,
                "worker_launch_ownership": ("UNKNOWN" if self._worker_launch_uncertain
                                            else "KNOWN"),
                "worker_termination": self._worker_termination,
                "entered_operations": self._operations,
                "unfinished_durable_writes": self._durable_writes,
                "durable_write_ownership": ("UNKNOWN" if self._write_ownership_unknown else "KNOWN"),
                "activation_evidence_sha256": self._activation_evidence_sha256,
            }

    def drain(self) -> None:
        with self._lock:
            self._draining = True

    def close(self, budget: ValidationBudget) -> CleanupOutcome:
        # Bootstrap reconciles the pinned admission module after this import.
        # Resolve its current exact class without accepting an unrelated budget.
        from kronos.common.release_admission import ValidationBudget as CurrentValidationBudget
        if type(budget) is not CurrentValidationBudget:
            raise OfficialCheckError("MCX_CHECK_CLEANUP_BUDGET_INVALID")
        self.drain()
        expired = False
        try:
            budget.check()
            remaining = max(0.0, (budget.deadline_ns - monotonic_ns()) / 1_000_000_000)
            self._operations_done.wait(remaining)
            budget.check()
        except ValueError:
            expired = True
        with self._lock:
            handle = self._worker_handle
        if not expired and handle is not None and handle is not current_thread():
            remaining = max(0.0, (budget.deadline_ns - monotonic_ns()) / 1_000_000_000)
            try:
                handle.join(remaining)
            except RuntimeError:
                with self._lock:
                    self._worker_launch_uncertain = True
            observed = monotonic_ns()
            if handle.ident is not None and not handle.is_alive() and observed < budget.deadline_ns:
                with self._lock:
                    if self._worker_handle is handle:
                        self._worker_identity = handle.ident
                        self._worker_handle = None
                        self._owned_workers = 0
                        self._worker_launch_uncertain = False
                        self._worker_termination = "OBSERVED_WITHIN_DEADLINE"
                        self._worker_done.set()
            elif observed >= budget.deadline_ns:
                expired = True
                with self._lock:
                    self._worker_termination = "NOT_OBSERVED_WITHIN_DEADLINE"
        with self._lock:
            preliminary_unresolved = bool(
                expired or self._owned_workers or self._durable_writes
                or self._write_ownership_unknown or self._operations
                or self._worker_launch_uncertain)
            if not preliminary_unresolved:
                try:
                    budget.check()
                except ValueError:
                    expired = True
            self._closed = True
            unresolved = bool(expired or self._owned_workers or self._durable_writes
                              or self._write_ownership_unknown or self._operations
                              or self._worker_launch_uncertain)
            self._cleanup_outcome = CleanupOutcome("UNRESOLVED" if unresolved else "CLOSED",
                                  self._owned_workers, self._durable_writes,
                                  "UNKNOWN" if self._write_ownership_unknown else "KNOWN",
                                  budget.deadline_ns, self._operations,
                                  self._worker_identity, self._worker_termination)
            return self._cleanup_outcome
