"""WO-07 content-addressed request publication; reads never recover or write.

The application takes its existing WO-05 publication lock before this store's
stable intake lock. No store method acquires WO-05 in the inverse order.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import fcntl
import os
from pathlib import Path
import stat
import tempfile

from pypdf import PdfReader

from kronos.swing.v1.mcx_native_visual_contract import (
    McxNativeReviewRequestMapping, McxReferenceReviewRequestMapping,
    REQUEST_COMMIT_SCHEMA, validate_mcx_request_pair, mcx_question_pack_from_mappings,
    validate_mcx_answer,
)
from kronos.swing.v1.review_evidence_binding import (
    COMMIT_SCHEMA, NseReviewRequestMapping, ReviewAcceptanceReceipt, ReviewEvidenceError, canonical, closed, digest,
    relative_path, require, strict_json, text, valid_timestamp,
)

NSE_PUBLICATION_SCHEMA = "KRONOS-SWING-NSE-REVIEW-PUBLICATION-V1"
NSE_PUBLICATION_VERSION = "1.0"
PUBLICATION_PREFIX = "SWING-REVIEW-REQUEST-PUBLICATION-"
PUBLICATION_FIELDS = {"schema", "version", "publication_identity", "request_identity", "request_sha256",
    "request_mapping_artifact", "question_pdf_artifact", "review_pack_identity", "question_set_identity",
    "question_set_version", "answer_schema", "answer_version", "publication_timestamp",
    "predecessor_publication_identity", "integrity_sha256"}
ACCEPTANCE_PREFIX = "SWING-REVIEW-EVIDENCE-COMMIT-"
ACCEPTANCE_FIELDS = {"schema", "version", "commit_identity", "package_key", "receipts",
    "request_publication_identity", "predecessor_commit_identity", "committed_at", "integrity_sha256"}
ATTEMPT_SCHEMA = "KRONOS-SWING-REVIEW-DOWNSTREAM-ATTEMPT-V1"
ATTEMPT_PREFIX = "SWING-REVIEW-DOWNSTREAM-ATTEMPT-"
ATTEMPT_FIELDS = {"schema", "version", "attempt_identity", "receipt_id", "commit_identity",
    "consumer_contract_identity", "consumer_contract_version", "state", "recorded_at",
    "predecessor_attempt_identity", "reason_code", "output_identities", "integrity_sha256"}
MCX_PUBLICATION_FIELDS = {"schema", "version", "publication_identity", "request_bundle_identity",
    "review_cycle_identity", "review_pack_identity", "native_request_identity", "native_request_sha256",
    "native_mapping_relative_path", "native_mapping_artifact_sha256", "reference_request_identity",
    "reference_request_sha256", "reference_mapping_relative_path", "reference_mapping_artifact_sha256",
    "question_pdf_relative_path", "question_pdf_sha256", "native_question_contract_identity",
    "native_question_contract_version", "native_answer_contract_identity", "native_answer_contract_version",
    "reference_question_contract_identity", "reference_question_contract_version",
    "reference_answer_contract_identity", "reference_answer_contract_version", "published_at",
    "predecessor_publication_identity", "integrity_sha256"}

# Ordering sentinel only: the existing stable filesystem lock remains authority.
_INTAKE_HELD = ContextVar("swing_review_intake_held", default=False)
_READ_SETS = ContextVar("swing_review_preparation_reads", default=())


def record_prepared_read(path, payload):
    """Record exact inputs, including absent controls, without refreshing a readset."""
    for reads in _READ_SETS.get():
        path = Path(path).absolute()
        if path in reads and reads[path] != payload:
            raise ReviewEvidenceError("REVIEW_BINDING_STALE")
        reads[path] = payload


@contextmanager
def capture_prepared_reads():
    require(not _INTAKE_HELD.get(), "REVIEW_PUBLICATION_LOCK_ORDER_INVALID")
    reads = {}
    token = _READ_SETS.set((*_READ_SETS.get(), reads))
    try:
        yield reads
    finally:
        _READ_SETS.reset(token)


@dataclass(frozen=True, slots=True)
class PreparedReadFence:
    """In-memory admission proof, not a new persisted contract or authority.

    All parsing is performed by the owning loaders before this tuple is frozen.
    Checking it only reads the exact previously selected paths and compares bytes.
    """

    entries: tuple

    def check(self):
        for path, expected in self.entries:
            try:
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(descriptor, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise ReviewEvidenceError("REVIEW_BINDING_STALE")
                    actual = stream.read()
            except FileNotFoundError:
                actual = None
            except OSError as error:
                raise ReviewEvidenceError("REVIEW_BINDING_STALE") from error
            if actual != expected:
                raise ReviewEvidenceError("REVIEW_BINDING_STALE")

    def with_published(self, *entries):
        """Only the exact bytes this operation publishes may replace its readset."""
        values = dict(self.entries)
        values.update(entries)
        return PreparedReadFence(tuple(values.items()))


def _acceptance_path(identity):
    require(type(identity) is str and identity.startswith(ACCEPTANCE_PREFIX)
            and digest(identity[len(ACCEPTANCE_PREFIX):]), "REVIEW_PUBLICATION_CONFLICT")
    return "acceptance-commits/" + identity + ".json"


def _package_key(receipts):
    require(type(receipts) is tuple and bool(receipts)
            and all(type(receipt) is ReviewAcceptanceReceipt for receipt in receipts), "REVIEW_ACCEPTANCE_INCOMPLETE")
    scopes = {receipt.body["scope"] for receipt in receipts}
    require(len(scopes) == 1, "REVIEW_ACCEPTANCE_INCOMPLETE")
    def scope(receipt):
        binding = receipt.binding.value
        if receipt.binding.scope == "NATIVE_REVIEW":
            # A new explicit Question Pack is a successor within this run and
            # market, not an unrelated acceptance pointer. The exact pack stays
            # immutable in every receipt and request publication.
            return ("NATIVE_REVIEW", binding["market"], binding["analytical_run_identity"])
        return ("MCX_SUPPORTING_CONTEXT", binding["trading_date"], binding["slot"])
    keys = {scope(receipt) for receipt in receipts}
    require(len(keys) == 1, "REVIEW_ACCEPTANCE_INCOMPLETE")
    require(len({receipt.binding.lineage_key for receipt in receipts}) == len(receipts), "REVIEW_DUPLICATE_ARTIFACT")
    return _hash(canonical(list(next(iter(keys)))))


@dataclass(frozen=True, slots=True)
class ReviewAcceptanceCommit:
    payload: bytes
    receipts: tuple[ReviewAcceptanceReceipt, ...]

    def __post_init__(self):
        value = closed(strict_json(self.payload), ACCEPTANCE_FIELDS)
        require(value["schema"] == COMMIT_SCHEMA and value["version"] == "1.0", "REVIEW_CONTRACT_UNSUPPORTED")
        unsigned = {key: item for key, item in value.items() if key != "integrity_sha256"}
        body = {key: item for key, item in unsigned.items() if key != "commit_identity"}
        require(value["commit_identity"] == ACCEPTANCE_PREFIX + _hash(canonical(body))
                and value["integrity_sha256"] == _hash(canonical(unsigned))
                and canonical(value) == self.payload, "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        require(value["package_key"] == _package_key(self.receipts) and valid_timestamp(value["committed_at"]), "REVIEW_PUBLICATION_CONFLICT")
        require(value["receipts"] == [{"receipt_identity": item.receipt_id,
                    "relative_path": "receipts/" + item.receipt_id + ".json", "sha256": _hash(item.payload)}
                    for item in self.receipts], "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        if value["predecessor_commit_identity"] is not None:
            _acceptance_path(value["predecessor_commit_identity"])
        require(text(value["request_publication_identity"]), "REVIEW_REQUEST_MISMATCH")

    @property
    def value(self):
        return strict_json(self.payload)

    @property
    def identity(self):
        return self.value["commit_identity"]


def _hash(payload: bytes) -> str:
    return sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ReviewDownstreamAttempt:
    """Immutable handoff event; neither its state nor its outputs alter acceptance."""

    payload: bytes

    def __post_init__(self):
        value = closed(strict_json(self.payload), ATTEMPT_FIELDS)
        require(value["schema"] == ATTEMPT_SCHEMA and value["version"] == "1.0",
                "REVIEW_CONTRACT_UNSUPPORTED")
        unsigned = {key: item for key, item in value.items() if key != "integrity_sha256"}
        body = {key: item for key, item in unsigned.items() if key != "attempt_identity"}
        require(value["attempt_identity"] == ATTEMPT_PREFIX + _hash(canonical(body))
                and value["integrity_sha256"] == _hash(canonical(unsigned))
                and canonical(value) == self.payload, "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        require(all(text(value[key]) for key in ("receipt_id", "consumer_contract_identity",
                    "consumer_contract_version")) and valid_timestamp(value["recorded_at"]),
                "REVIEW_REQUEST_MISMATCH")
        _acceptance_path(value["commit_identity"])
        if value["predecessor_attempt_identity"] is not None:
            _attempt_path(value["predecessor_attempt_identity"])
        reasons = {"RUNNING": None, "SUCCEEDED": None,
                   "FAILED": "REVIEW_DOWNSTREAM_PROCESSING_FAILED",
                   "UNSUPPORTED_CONTRACT": "REVIEW_DOWNSTREAM_CONTRACT_UNSUPPORTED"}
        require(value["state"] in reasons and value["reason_code"] == reasons[value["state"]],
                "REVIEW_CONTRACT_UNSUPPORTED")
        outputs = value["output_identities"]
        require(type(outputs) is list and all(text(item) for item in outputs)
                and len(outputs) == len(set(outputs)), "REVIEW_REQUEST_MISMATCH")
        require(bool(outputs) if value["state"] == "SUCCEEDED" else not outputs,
                "REVIEW_ACCEPTANCE_INCOMPLETE")

    @property
    def value(self):
        return strict_json(self.payload)

    @property
    def identity(self):
        return self.value["attempt_identity"]


def _attempt_path(identity):
    require(type(identity) is str and identity.startswith(ATTEMPT_PREFIX)
            and digest(identity[len(ATTEMPT_PREFIX):]), "REVIEW_PUBLICATION_CONFLICT")
    return "downstream-attempts/" + identity + ".json"


def _identity(unsigned: dict) -> str:
    return PUBLICATION_PREFIX + _hash(canonical({key: value for key, value in unsigned.items()
                                               if key != "publication_identity"}))


def _publication_path(identity: str) -> str:
    require(type(identity) is str and identity.startswith(PUBLICATION_PREFIX)
            and digest(identity[len(PUBLICATION_PREFIX):]), "REVIEW_PUBLICATION_CONFLICT")
    return "request-publications/" + identity + ".json"


def _verify_pdf(payload: bytes, mapping: NseReviewRequestMapping) -> None:
    require(type(payload) is bytes and 8 < len(payload) <= 128 * 1024 * 1024
            and payload.startswith(b"%PDF-"), "REVIEW_ARTIFACT_DIGEST_MISMATCH")
    value = mapping.value
    require(_hash(payload) == value["review_pack_sha256"], "REVIEW_ARTIFACT_DIGEST_MISMATCH")
    try:
        pdf = PdfReader(BytesIO(payload), strict=True)
        require(not pdf.is_encrypted, "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        content = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as error:
        raise ReviewEvidenceError("REVIEW_ARTIFACT_DIGEST_MISMATCH") from error
    # Values must be extractable exact echoes. Never insert/repair a missing
    # digest, regenerate the PDF or select a different artifact during a read.
    for key in ("request_identity", "request_sha256", "review_pack_identity", "answer_schema"):
        require(value[key] in content, "REVIEW_REQUEST_MISMATCH", "$.question_pdf." + key)


@dataclass(frozen=True, slots=True)
class NseRequestPublication:
    payload: bytes
    mapping: NseReviewRequestMapping

    def __post_init__(self):
        value = closed(strict_json(self.payload), PUBLICATION_FIELDS)
        require(value["schema"] == NSE_PUBLICATION_SCHEMA and value["version"] == NSE_PUBLICATION_VERSION,
                "REVIEW_CONTRACT_UNSUPPORTED")
        require(valid_timestamp(value["publication_timestamp"]), "REVIEW_TIMESTAMP_INVALID")
        previous = value["predecessor_publication_identity"]
        if previous is not None:
            _publication_path(previous)
        unsigned = {key: item for key, item in value.items() if key != "integrity_sha256"}
        require(value["publication_identity"] == _identity(unsigned)
                and value["integrity_sha256"] == _hash(canonical(unsigned))
                and canonical(value) == self.payload, "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        for field in ("request_mapping_artifact", "question_pdf_artifact"):
            artifact = closed(value[field], {"relative_path", "sha256"}, "$." + field)
            require(relative_path(artifact["relative_path"]) and digest(artifact["sha256"]), "REVIEW_ARTIFACT_REFERENCE_INVALID")
        mapping = self.mapping.value
        for field in ("request_identity", "request_sha256", "review_pack_identity", "question_set_identity",
                      "question_set_version", "answer_schema", "answer_version"):
            require(value[field] == mapping[field], "REVIEW_REQUEST_MISMATCH", "$." + field)
        require(value["request_mapping_artifact"]["sha256"] == _hash(self.mapping.payload)
                and value["question_pdf_artifact"]["sha256"] == mapping["review_pack_sha256"], "REVIEW_ARTIFACT_DIGEST_MISMATCH")

    @property
    def value(self):
        return strict_json(self.payload)

    @property
    def identity(self):
        return self.value["publication_identity"]


def _verify_mcx_pdf(payload, native, reference):
    validate_mcx_request_pair(native, reference)
    require(type(payload) is bytes and 8 < len(payload) <= 128 * 1024 * 1024
            and payload.startswith(b"%PDF-") and _hash(payload) == native.value["review_pack_sha256"],
            "REVIEW_ARTIFACT_DIGEST_MISMATCH")
    try:
        reader = PdfReader(BytesIO(payload), strict=True)
        require(not reader.is_encrypted, "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        content = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as error:
        raise ReviewEvidenceError("REVIEW_ARTIFACT_DIGEST_MISMATCH") from error
    for mapping in (native.value, reference.value):
        for field in ("question_contract_identity", "question_contract_version", "answer_contract_identity",
                      "answer_contract_version", "request_identity", "request_sha256", "review_pack_identity",
                      "request_bundle_identity", "review_cycle_identity"):
            require(mapping[field] in content, "REVIEW_REQUEST_MISMATCH", "$.question_pdf." + field)
        for subject in mapping["subjects"]:
            for field in ("subject_reference", "native_candidate_reference"):
                require(subject[field] in content, "REVIEW_REQUEST_MISMATCH", "$.question_pdf.subjects")
            for response in subject["responses"]:
                for field in ("timeframe", "expected_chart_identity", "chart_revision_identity", "chart_revision_sha256"):
                    require(response[field] in content, "REVIEW_REQUEST_MISMATCH", "$.question_pdf.charts")


@dataclass(frozen=True, slots=True)
class McxRequestPublication:
    payload: bytes
    native: McxNativeReviewRequestMapping
    reference: McxReferenceReviewRequestMapping

    def __post_init__(self):
        validate_mcx_request_pair(self.native, self.reference)
        value = closed(strict_json(self.payload), MCX_PUBLICATION_FIELDS)
        require(value["schema"] == REQUEST_COMMIT_SCHEMA and value["version"] == "1.0",
                "REVIEW_CONTRACT_UNSUPPORTED")
        unsigned = {key: item for key, item in value.items() if key != "integrity_sha256"}
        require(value["publication_identity"] == _identity(unsigned)
                and value["integrity_sha256"] == _hash(canonical(unsigned))
                and canonical(value) == self.payload, "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        require(valid_timestamp(value["published_at"]), "REVIEW_TIMESTAMP_INVALID")
        if value["predecessor_publication_identity"] is not None:
            _publication_path(value["predecessor_publication_identity"])
        for field in ("request_bundle_identity", "review_cycle_identity", "review_pack_identity"):
            require(value[field] == self.native.value[field], "REVIEW_REQUEST_MISMATCH", "$." + field)
        for prefix, mapping in (("native", self.native), ("reference", self.reference)):
            for field in ("request_identity", "request_sha256", "question_contract_identity", "question_contract_version",
                          "answer_contract_identity", "answer_contract_version"):
                require(value[prefix + "_" + field] == mapping.value[field], "REVIEW_REQUEST_MISMATCH")
            require(relative_path(value[prefix + "_mapping_relative_path"])
                    and value[prefix + "_mapping_artifact_sha256"] == _hash(mapping.payload),
                    "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        require(relative_path(value["question_pdf_relative_path"])
                and value["question_pdf_sha256"] == self.native.value["review_pack_sha256"],
                "REVIEW_ARTIFACT_DIGEST_MISMATCH")

    @property
    def value(self):
        return strict_json(self.payload)

    @property
    def identity(self):
        return self.value["publication_identity"]


class ReviewEvidenceStore:
    """A configured local evidence root. Construction and all loads are pure."""

    def __init__(self, evidence_root: Path, *, fault=None):
        self.root = Path(evidence_root).absolute() / "review-evidence-v1"
        self._fault = fault or (lambda phase: None)

    def _path(self, relative: str) -> Path:
        require(relative_path(relative), "REVIEW_ARTIFACT_REFERENCE_INVALID")
        path = self.root / relative
        # Reject symlink components, including the configured root itself.
        for part in (self.root, *path.relative_to(self.root).parents):
            candidate = part if part.is_absolute() else self.root / part
            require(not candidate.is_symlink(), "REVIEW_ARTIFACT_REFERENCE_INVALID")
        require(not path.is_symlink(), "REVIEW_ARTIFACT_REFERENCE_INVALID")
        return path

    def _read(self, relative: str) -> bytes:
        path = self._path(relative)
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as stream:
                require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "REVIEW_ARTIFACT_REFERENCE_INVALID")
                payload = stream.read()
                record_prepared_read(path, payload)
                return payload
        except OSError as error:
            raise ReviewEvidenceError("REVIEW_ARTIFACT_UNAVAILABLE", relative) from error

    @staticmethod
    def _fsync_directory(path: Path):
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @contextmanager
    def intake_lock(self):
        """Stable inode for all store instances/processes; never replaced/deleted."""
        require(not _INTAKE_HELD.get(), "REVIEW_PUBLICATION_LOCK_ORDER_INVALID")
        require(not self.root.is_symlink(), "REVIEW_ARTIFACT_REFERENCE_INVALID")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path("intake.lock")
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        token = None
        try:
            require(stat.S_ISREG(os.fstat(descriptor).st_mode), "REVIEW_ARTIFACT_REFERENCE_INVALID")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            token = _INTAKE_HELD.set(True)
            yield
        finally:
            if token is not None:
                _INTAKE_HELD.reset(token)
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @contextmanager
    def publication_commit_guard(self, publication_guard, recheck):
        """WO05 guard -> WO07 intake; callers prepare inputs before entry.

        No raw lock escapes. The caller validates the complete expected-state
        envelope before entry; recheck compares only its prepared byte/primitive
        fence after both owners' locks are held. No downstream work belongs here.
        """
        require(not _INTAKE_HELD.get(), "REVIEW_PUBLICATION_LOCK_ORDER_INVALID")
        require(callable(publication_guard) and callable(recheck), "REVIEW_REQUEST_MISMATCH")
        with publication_guard() as snapshot:
            with self.intake_lock():
                recheck(snapshot)
                yield snapshot

    @contextmanager
    def _commit_context(self, publication_guard, guarded_recheck):
        require(not _INTAKE_HELD.get(), "REVIEW_PUBLICATION_LOCK_ORDER_INVALID")
        if publication_guard is None:
            require(guarded_recheck is None, "REVIEW_REQUEST_MISMATCH")
            with self.intake_lock():
                yield None
        else:
            with self.publication_commit_guard(publication_guard, guarded_recheck) as snapshot:
                yield snapshot

    def _optional_read(self, relative):
        path = self._path(relative)
        if path.exists():
            return self._read(relative)
        record_prepared_read(path, None)
        return None

    def _immutable(self, relative: str, payload: bytes):
        path = self._path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            require(self._read(relative) == payload, "REVIEW_PUBLICATION_CONFLICT", relative)
            return
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".prepared-", delete=False) as stream:
            pending = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            try:
                os.link(pending, path)
            except FileExistsError:
                require(self._read(relative) == payload, "REVIEW_PUBLICATION_CONFLICT", relative)
            self._fsync_directory(path.parent)
        finally:
            pending.unlink(missing_ok=True)

    def _preflight_immutable(self, artifacts):
        """Check every prepared destination before retaining the first artifact."""
        for relative, payload in artifacts:
            if self._path(relative).exists() and self._read(relative) != payload:
                raise ReviewEvidenceError("REVIEW_PUBLICATION_CONFLICT", relative)

    def load_request(self, identity: str) -> NseRequestPublication:
        payload = self._read(_publication_path(identity))
        raw = closed(strict_json(payload), PUBLICATION_FIELDS)
        artifact = closed(raw["request_mapping_artifact"], {"relative_path", "sha256"})
        mapping_payload = self._read(artifact["relative_path"])
        require(_hash(mapping_payload) == artifact["sha256"], "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        publication = NseRequestPublication(payload, NseReviewRequestMapping(mapping_payload))
        require(publication.identity == identity, "REVIEW_PUBLICATION_CONFLICT")
        pdf = self._read(publication.value["question_pdf_artifact"]["relative_path"])
        _verify_pdf(pdf, publication.mapping)
        return publication

    def load_current_request(self) -> NseRequestPublication | None:
        payload = self._optional_read("current-request.json")
        if payload is None:
            return None
        raw = closed(strict_json(payload), {"schema", "version", "publication_identity", "integrity_sha256"})
        require(raw["schema"] == NSE_PUBLICATION_SCHEMA and raw["version"] == NSE_PUBLICATION_VERSION,
                "REVIEW_CONTRACT_UNSUPPORTED")
        require(raw["integrity_sha256"] == _hash(canonical({key: value for key, value in raw.items() if key != "integrity_sha256"})),
                "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        return self.load_request(raw["publication_identity"])

    def native_chart_selection(self, binding):
        """Prospective chart staging only; never a receipt or analytical fact.

        NSE roles retain separate pointers. MCX roles resolve through one shared
        composite pointer. Tombstones retain their predecessors so removal or
        re-paste cannot make an old tab current.
        Historical composite/DAILY carriers are intentionally not consulted.
        """
        closed(binding, {"run_identity", "candidate_identity", "instrument", "market", "role"})
        require(all(type(value) is str and value for value in binding.values())
                and binding["market"] in {"NSE", "MCX"}
                and binding["role"] in ({"NATIVE_NSE"} if binding["market"] == "NSE"
                    else {"NATIVE_MCX", "SUPPORTING_REFERENCE"}), "REVIEW_REQUEST_MISMATCH")
        if binding["market"] == "MCX":
            common = {key: binding[key] for key in
                      ("run_identity", "candidate_identity", "instrument", "market")}
            shared_path = "current-mcx-composite-" + _hash(canonical(common)) + ".json"
            shared_payload = self._optional_read(shared_path)
            if shared_payload is not None:
                pointer = closed(strict_json(shared_payload), {"NATIVE_MCX", "SUPPORTING_REFERENCE"})
                selections = {}
                for role in ("NATIVE_MCX", "SUPPORTING_REFERENCE"):
                    role_binding = {**common, "role": role}
                    selections[role] = self._load_native_chart_selection(
                        role_binding, pointer[role])
                native, reference = selections["NATIVE_MCX"], selections["SUPPORTING_REFERENCE"]
                require((native["image"] is None) == (reference["image"] is None),
                        "REVIEW_PUBLICATION_CONFLICT")
                if native["image"] is not None:
                    require(native["image"] == reference["image"],
                            "REVIEW_PUBLICATION_CONFLICT")
                return selections[binding["role"]]
        path = "current-chart-" + _hash(canonical(binding)) + ".json"
        payload = self._optional_read(path)
        if payload is None:
            return None
        pointer = closed(strict_json(payload), {"selection_sha256"})
        return self._load_native_chart_selection(binding, pointer["selection_sha256"])

    def _load_native_chart_selection(self, binding, selection_sha256):
        current, seen, selected = selection_sha256, set(), None
        while current is not None:
            require(digest(current) and current not in seen, "REVIEW_PUBLICATION_CONFLICT")
            seen.add(current)
            raw = self._read("chart-selections/" + current + ".json")
            require(_hash(raw) == current, "REVIEW_ARTIFACT_DIGEST_MISMATCH")
            value = closed(strict_json(raw), {"schema", "version", "binding", "predecessor", "image", "selected_at"})
            require(value["schema"] == "KRONOS-SWING-REVIEW-CHART-SELECTION-V1"
                    and value["version"] == "1.0" and value["binding"] == binding
                    and canonical(value) == raw and valid_timestamp(value["selected_at"]), "REVIEW_REQUEST_MISMATCH")
            if value["image"] is not None:
                image = closed(value["image"], {"sha256", "content_type"})
                require(digest(image["sha256"]) and image["content_type"] in {"image/png", "image/jpeg", "image/webp"},
                        "REVIEW_REQUEST_MISMATCH")
                require(_hash(self._read("chart-images/" + image["sha256"])) == image["sha256"],
                        "REVIEW_ARTIFACT_DIGEST_MISMATCH")
            if selected is None:
                selected = {**value, "selection_sha256": current}
            current = value["predecessor"]
        return selected

    def select_mcx_composite(self, bindings, image, content_type, *, selected_at,
                             expected_selections, publication_guard, recheck):
        """Publish both MCX logical roles through one atomic composite pointer."""
        roles = ("NATIVE_MCX", "SUPPORTING_REFERENCE")
        require(type(bindings) is dict and set(bindings) == set(roles)
                and type(expected_selections) is dict and set(expected_selections) == set(roles),
                "REVIEW_REQUEST_MISMATCH")
        common = {key: bindings[roles[0]][key] for key in
                  ("run_identity", "candidate_identity", "instrument", "market")}
        require(common["market"] == "MCX"
                and all(bindings[role] == {**common, "role": role} for role in roles),
                "REVIEW_REQUEST_MISMATCH")
        require(valid_timestamp(selected_at), "REVIEW_TIMESTAMP_INVALID")
        if image is not None:
            from kronos.swing.v1.evidence_store import _CONTENT_TYPES, _MAX_CHART_BYTES
            suffix, magic = _CONTENT_TYPES.get(content_type, (None, None))
            require(type(image) is bytes and 0 < len(image) <= _MAX_CHART_BYTES
                    and suffix is not None and image.startswith(magic)
                    and (content_type != "image/webp" or image[8:12] == b"WEBP"),
                    "REVIEW_ACCEPTANCE_INCOMPLETE")
        with capture_prepared_reads() as reads:
            previous = {role: self.native_chart_selection(bindings[role]) for role in roles}
            require(all((None if previous[role] is None else previous[role]["selection_sha256"])
                        == expected_selections[role] for role in roles), "REVIEW_BINDING_STALE")
        fence = PreparedReadFence(tuple(reads.items()))
        image_hash = None if image is None else _hash(image)
        image_record = None if image is None else dict(sha256=image_hash, content_type=content_type)
        # An exact replay is observationally idempotent. It neither creates a
        # new revision identity nor advances either logical role.
        if all(previous[role] is not None and previous[role]["image"] == image_record for role in roles):
            with self.publication_commit_guard(publication_guard, recheck):
                fence.check()
                recheck(None)
            return previous
        selections, artifacts = {}, []
        for role in roles:
            value = dict(schema="KRONOS-SWING-REVIEW-CHART-SELECTION-V1", version="1.0",
                binding=bindings[role], predecessor=expected_selections[role], selected_at=selected_at,
                image=image_record)
            raw = canonical(value)
            selected_hash = _hash(raw)
            selections[role] = {**value, "selection_sha256": selected_hash}
            artifacts.append(("chart-selections/" + selected_hash + ".json", raw))
        if image is not None:
            artifacts.insert(0, ("chart-images/" + image_hash, image))
        pointer_path = "current-mcx-composite-" + _hash(canonical(common)) + ".json"
        pointer_bytes = canonical({role: selections[role]["selection_sha256"] for role in roles})
        with self.publication_commit_guard(publication_guard, recheck):
            fence.check()
            self._preflight_immutable(tuple(artifacts))
            for relative, payload in artifacts:
                self._immutable(relative, payload)
            self._fault("after_mcx_composite_selection_retention")
            recheck(None)
            self._fault("before_mcx_composite_pointer_replace")
            self._replace_pointer(pointer_bytes, pointer_path)
        return {role: self.native_chart_selection(bindings[role]) for role in roles}

    def select_native_chart(self, binding, image, content_type, *, selected_at,
                            expected_selection, publication_guard, recheck):
        """One explicit paste/replace/remove under WO05 -> WO07; no reads write."""
        require(valid_timestamp(selected_at), "REVIEW_TIMESTAMP_INVALID")
        if image is not None:
            from kronos.swing.v1.evidence_store import _CONTENT_TYPES, _MAX_CHART_BYTES
            suffix, magic = _CONTENT_TYPES.get(content_type, (None, None))
            require(type(image) is bytes and 0 < len(image) <= _MAX_CHART_BYTES
                    and suffix is not None and image.startswith(magic)
                    and (content_type != "image/webp" or image[8:12] == b"WEBP"), "REVIEW_ACCEPTANCE_INCOMPLETE")
        with capture_prepared_reads() as reads:
            previous = self.native_chart_selection(binding)
            require((None if previous is None else previous["selection_sha256"]) == expected_selection,
                    "REVIEW_BINDING_STALE")
        fence = PreparedReadFence(tuple(reads.items()))
        image_hash = None if image is None else _hash(image)
        value = dict(schema="KRONOS-SWING-REVIEW-CHART-SELECTION-V1", version="1.0",
            binding=binding, predecessor=expected_selection, selected_at=selected_at,
            image=None if image is None else dict(sha256=image_hash, content_type=content_type))
        raw = canonical(value)
        selected_hash = _hash(raw)
        pointer_bytes = canonical({"selection_sha256": selected_hash})
        pointer_path = "current-chart-" + _hash(canonical(binding)) + ".json"
        selection_path = "chart-selections/" + selected_hash + ".json"
        with self.publication_commit_guard(publication_guard, recheck):
            fence.check()
            self._preflight_immutable(((selection_path, raw),) if image is None else
                                      (("chart-images/" + image_hash, image), (selection_path, raw)))
            if image is not None:
                self._immutable("chart-images/" + image_hash, image)
            self._immutable(selection_path, raw)
            recheck(None)
            self._replace_pointer(pointer_bytes, pointer_path)
        return self.native_chart_selection(binding)

    def native_chart_bytes(self, selection):
        require(selection is not None and selection["image"] is not None, "REVIEW_ACCEPTANCE_INCOMPLETE")
        payload = self._read("chart-images/" + selection["image"]["sha256"])
        require(_hash(payload) == selection["image"]["sha256"], "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        return payload

    def _replace_pointer(self, payload, relative="current-request.json"):
        path = self._path(relative)
        with tempfile.NamedTemporaryFile(dir=self.root, prefix=".prepared-pointer-", delete=False) as stream:
            pending = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            self._fault("before_pointer_replace")
            os.replace(pending, path)
            self._fsync_directory(self.root)
            self._fault("after_pointer_replace")
        finally:
            pending.unlink(missing_ok=True)

    def publish_nse_request(self, mapping: NseReviewRequestMapping, pdf: bytes, *,
                            publication_timestamp: str, expected_predecessor: str | None,
                            recheck, publication_guard=None, guarded_recheck=None) -> NseRequestPublication:
        require(not _INTAKE_HELD.get(), "REVIEW_PUBLICATION_LOCK_ORDER_INVALID")
        require(type(mapping) is NseReviewRequestMapping and callable(recheck), "REVIEW_REQUEST_MISMATCH")
        require(valid_timestamp(publication_timestamp), "REVIEW_TIMESTAMP_INVALID")
        _verify_pdf(pdf, mapping)
        recheck(mapping)  # admission; caller compares complete authoritative state
        predecessor_bytes = self._optional_read("current-request.json")
        current = self.load_current_request()
        value = mapping.value
        replay = current is not None and current.mapping.value["request_identity"] == value["request_identity"]
        if replay:
            require(current.mapping.payload == mapping.payload, "REVIEW_ANSWER_IDENTITY_CONFLICT")
            require(expected_predecessor in {current.identity, current.value["predecessor_publication_identity"]}, "REVIEW_BINDING_STALE")
        else:
            require((current.identity if current is not None else None) == expected_predecessor, "REVIEW_BINDING_STALE")
            retained = current
            seen = set()
            while retained is not None:
                require(retained.identity not in seen, "REVIEW_PUBLICATION_CONFLICT")
                seen.add(retained.identity)
                require(retained.mapping.value["request_identity"] != value["request_identity"], "REVIEW_ANSWER_IDENTITY_CONFLICT")
                previous = retained.value["predecessor_publication_identity"]
                retained = self.load_request(previous) if previous is not None else None
        pdf_path = "question-pdfs/" + _hash(pdf) + ".pdf"
        mapping_path = "request-mappings/" + _hash(mapping.payload) + ".json"
        manifest = {"schema": NSE_PUBLICATION_SCHEMA, "version": NSE_PUBLICATION_VERSION,
            **{key: value[key] for key in ("request_identity", "request_sha256", "review_pack_identity",
               "question_set_identity", "question_set_version", "answer_schema", "answer_version")},
            "request_mapping_artifact": {"relative_path": mapping_path, "sha256": _hash(mapping.payload)},
            "question_pdf_artifact": {"relative_path": pdf_path, "sha256": _hash(pdf)},
            "publication_timestamp": publication_timestamp, "predecessor_publication_identity": expected_predecessor}
        manifest["publication_identity"] = _identity(manifest)
        manifest["integrity_sha256"] = _hash(canonical(manifest))
        publication = NseRequestPublication(canonical(manifest), mapping)
        pointer = {"schema": NSE_PUBLICATION_SCHEMA, "version": NSE_PUBLICATION_VERSION,
                   "publication_identity": publication.identity}
        pointer["integrity_sha256"] = _hash(canonical(pointer))
        pointer_bytes = canonical(pointer)
        publication_path = _publication_path(publication.identity)
        with self._commit_context(publication_guard, guarded_recheck) as snapshot:
            require(self._optional_read("current-request.json") == predecessor_bytes, "REVIEW_BINDING_STALE")
            recheck(mapping)
            if replay:
                return current
            self._preflight_immutable(((pdf_path, pdf), (mapping_path, mapping.payload),
                                      (publication_path, publication.payload)))
            self._fault("before_retention")
            self._immutable(pdf_path, pdf)
            self._fault("after_pdf_retention")
            self._immutable(mapping_path, mapping.payload)
            self._fault("after_mapping_retention")
            self._immutable(publication_path, publication.payload)
            self._fault("after_manifest_retention")
            recheck(mapping)  # final fenced authority check before visibility
            if guarded_recheck is not None:
                guarded_recheck(snapshot)
            self._replace_pointer(pointer_bytes)
            self._fault("before_acknowledgement")
            return publication

    def recover_request(self) -> NseRequestPublication | None:
        """Explicit boundary: verify committed graph, never promote loose files.

        Residue may remain safely unreferenced. No evidence is deleted and no
        alternate publication is inferred when the committed graph is invalid.
        """
        with capture_prepared_reads() as reads:
            current = self.load_current_request()
        fence = PreparedReadFence(tuple(reads.items()))
        with self.intake_lock():
            fence.check()
        return current

    def load_mcx_request(self, identity: str) -> McxRequestPublication:
        payload = self._read(_publication_path(identity))
        raw = closed(strict_json(payload), MCX_PUBLICATION_FIELDS)
        mappings = []
        for prefix, model in (("native", McxNativeReviewRequestMapping), ("reference", McxReferenceReviewRequestMapping)):
            data = self._read(raw[prefix + "_mapping_relative_path"])
            require(_hash(data) == raw[prefix + "_mapping_artifact_sha256"], "REVIEW_ARTIFACT_DIGEST_MISMATCH")
            mappings.append(model(data))
        result = McxRequestPublication(payload, *mappings)
        require(result.identity == identity, "REVIEW_PUBLICATION_CONFLICT")
        _verify_mcx_pdf(self._read(result.value["question_pdf_relative_path"]), *mappings)
        return result

    def load_current_mcx_request(self) -> McxRequestPublication | None:
        payload = self._optional_read("current-mcx-request.json")
        if payload is None:
            return None
        value = closed(strict_json(payload), {"schema", "version", "publication_identity", "integrity_sha256"})
        require(value["schema"] == REQUEST_COMMIT_SCHEMA and value["version"] == "1.0", "REVIEW_CONTRACT_UNSUPPORTED")
        require(value["integrity_sha256"] == _hash(canonical({key: item for key, item in value.items()
                                                            if key != "integrity_sha256"})), "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        return self.load_mcx_request(value["publication_identity"])

    def publish_mcx_request(self, native, reference, pdf, *, publication_timestamp,
                            expected_predecessor, recheck, publication_guard=None, guarded_recheck=None):
        require(not _INTAKE_HELD.get(), "REVIEW_PUBLICATION_LOCK_ORDER_INVALID")
        require(callable(recheck) and valid_timestamp(publication_timestamp), "REVIEW_REQUEST_MISMATCH")
        _verify_mcx_pdf(pdf, native, reference)
        recheck(native, reference)
        predecessor_bytes = self._optional_read("current-mcx-request.json")
        current = self.load_current_mcx_request()
        n, r = native.value, reference.value
        replay = current is not None and current.native.value["request_bundle_identity"] == n["request_bundle_identity"]
        if replay:
            require(current.native.payload == native.payload and current.reference.payload == reference.payload,
                    "REVIEW_ANSWER_IDENTITY_CONFLICT")
            require(expected_predecessor in {current.identity, current.value["predecessor_publication_identity"]},
                    "REVIEW_BINDING_STALE")
        else:
            require((current.identity if current is not None else None) == expected_predecessor, "REVIEW_BINDING_STALE")
            retained, seen = current, set()
            while retained is not None:
                require(retained.identity not in seen, "REVIEW_PUBLICATION_CONFLICT")
                seen.add(retained.identity)
                old_ids = {retained.native.value["request_identity"], retained.reference.value["request_identity"]}
                require(not old_ids & {n["request_identity"], r["request_identity"]}
                        and retained.native.value["request_bundle_identity"] != n["request_bundle_identity"],
                        "REVIEW_ANSWER_IDENTITY_CONFLICT")
                previous = retained.value["predecessor_publication_identity"]
                retained = self.load_mcx_request(previous) if previous is not None else None
        manifest = {"schema": REQUEST_COMMIT_SCHEMA, "version": "1.0",
            **{key: n[key] for key in ("request_bundle_identity", "review_cycle_identity", "review_pack_identity")},
            "question_pdf_relative_path": "question-pdfs/" + _hash(pdf) + ".pdf",
            "question_pdf_sha256": _hash(pdf), "published_at": publication_timestamp,
            "predecessor_publication_identity": expected_predecessor}
        for prefix, mapping in (("native", native), ("reference", reference)):
            manifest.update({prefix + "_" + key: mapping.value[key] for key in ("request_identity", "request_sha256",
                "question_contract_identity", "question_contract_version", "answer_contract_identity", "answer_contract_version")})
            manifest[prefix + "_mapping_relative_path"] = "request-mappings/" + _hash(mapping.payload) + ".json"
            manifest[prefix + "_mapping_artifact_sha256"] = _hash(mapping.payload)
        manifest["publication_identity"] = _identity(manifest)
        manifest["integrity_sha256"] = _hash(canonical(manifest))
        result = McxRequestPublication(canonical(manifest), native, reference)
        pointer = {"schema": REQUEST_COMMIT_SCHEMA, "version": "1.0", "publication_identity": result.identity}
        pointer["integrity_sha256"] = _hash(canonical(pointer))
        pointer_bytes = canonical(pointer)
        publication_path = _publication_path(result.identity)
        with self._commit_context(publication_guard, guarded_recheck) as snapshot:
            require(self._optional_read("current-mcx-request.json") == predecessor_bytes, "REVIEW_BINDING_STALE")
            recheck(native, reference)
            if replay:
                return current
            self._preflight_immutable(((manifest["question_pdf_relative_path"], pdf),
                (manifest["native_mapping_relative_path"], native.payload),
                (manifest["reference_mapping_relative_path"], reference.payload),
                (publication_path, result.payload)))
            self._fault("before_retention")
            self._immutable(manifest["question_pdf_relative_path"], pdf)
            self._fault("after_pdf_retention")
            self._immutable(manifest["native_mapping_relative_path"], native.payload)
            self._fault("after_native_mapping_retention")
            self._immutable(manifest["reference_mapping_relative_path"], reference.payload)
            self._fault("after_reference_mapping_retention")
            self._immutable(publication_path, result.payload)
            self._fault("after_manifest_retention")
            recheck(native, reference)
            if guarded_recheck is not None:
                guarded_recheck(snapshot)
            self._replace_pointer(pointer_bytes, "current-mcx-request.json")
            self._fault("before_acknowledgement")
        return result

    def recover_mcx_request(self):
        with capture_prepared_reads() as reads:
            current = self.load_current_mcx_request()
        fence = PreparedReadFence(tuple(reads.items()))
        with self.intake_lock():
            fence.check()
        return current

    def validate_mcx_answer_for_publication(self, payload: bytes, publication_identity: str):
        """Resolve BOTH echoes through ONE committed graph, never independent latest scans."""
        current = self.load_current_mcx_request()
        require(current is not None and current.identity == publication_identity, "REVIEW_BINDING_STALE")
        return validate_mcx_answer(payload, mcx_question_pack_from_mappings(current.native, current.reference))

    def _receipt_artifacts(self, receipt):
        body = receipt.body
        artifacts = [(body["answer"]["retained_relative_path"], body["answer"]["pdf_sha256"])]
        artifacts.extend((item["retained_relative_path"], item["sha256"])
                         for name in ("chart_revisions", "structured_evidence") for item in body[name])
        return artifacts

    def _verify_complete_receipt(self, receipt, read=None):
        read = self._read if read is None else read
        body = receipt.body
        binding = receipt.binding.value
        if receipt.binding.scope == "NATIVE_REVIEW":
            expected = {("NATIVE_NSE", tf) for tf in ("1W", "1D", "4H", "1H")} if binding["market"] == "NSE" else {
                (role, tf) for role in ("NATIVE_MCX", "SUPPORTING_REFERENCE") for tf in ("1D", "4H", "1H")}
            for name, tf_key in (("chart_revisions", "timeframe_or_panel_identity"), ("structured_evidence", "timeframe_or_family_identity")):
                actual = [(item["role"], item[tf_key]) for item in body[name]]
                require(len(actual) == len(expected) and set(actual) == expected, "REVIEW_ACCEPTANCE_INCOMPLETE")
        else:
            require({item["timeframe_or_family_identity"] for item in body["structured_evidence"]} == {"METALS", "ENERGY"}
                    and len(body["structured_evidence"]) == 2, "REVIEW_ACCEPTANCE_INCOMPLETE")
            require({item["timeframe_or_panel_identity"] for item in body["chart_revisions"]} == {"METALS", "ENERGY"}
                    and len(body["chart_revisions"]) == 2, "REVIEW_ACCEPTANCE_INCOMPLETE")
        for path, expected_hash in self._receipt_artifacts(receipt):
            require(_hash(read(path)) == expected_hash, "REVIEW_ARTIFACT_DIGEST_MISMATCH", path)
        pdf = read(body["answer"]["retained_relative_path"])
        require(pdf.startswith(b"%PDF-") and len(pdf) == body["answer"]["byte_length"]
                and len(pdf) <= 128 * 1024 * 1024, "REVIEW_ARTIFACT_DIGEST_MISMATCH")

    def load_acceptance(self, identity: str) -> ReviewAcceptanceCommit:
        payload = self._read(_acceptance_path(identity))
        value = closed(strict_json(payload), ACCEPTANCE_FIELDS)
        require(type(value["receipts"]) is list and bool(value["receipts"]), "REVIEW_ACCEPTANCE_INCOMPLETE")
        receipts = []
        for artifact in value["receipts"]:
            closed(artifact, {"receipt_identity", "relative_path", "sha256"})
            raw = self._read(artifact["relative_path"])
            require(_hash(raw) == artifact["sha256"], "REVIEW_ARTIFACT_DIGEST_MISMATCH")
            receipt = ReviewAcceptanceReceipt(raw)
            require(receipt.receipt_id == artifact["receipt_identity"], "REVIEW_ARTIFACT_DIGEST_MISMATCH")
            self._verify_complete_receipt(receipt)
            receipts.append(receipt)
        commit = ReviewAcceptanceCommit(payload, tuple(receipts))
        require(commit.identity == identity, "REVIEW_PUBLICATION_CONFLICT")
        return commit

    def load_current_acceptance(self, package_key: str) -> ReviewAcceptanceCommit | None:
        require(digest(package_key), "REVIEW_PUBLICATION_CONFLICT")
        relative = "acceptance-current/" + package_key + ".json"
        payload = self._optional_read(relative)
        if payload is None:
            return None
        value = closed(strict_json(payload), {"commit_identity", "integrity_sha256"})
        require(value["integrity_sha256"] == _hash(canonical({"commit_identity": value["commit_identity"]})), "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        commit = self.load_acceptance(value["commit_identity"])
        require(commit.value["package_key"] == package_key, "REVIEW_PUBLICATION_CONFLICT")
        return commit

    def acceptance_history(self, package_key: str) -> tuple[ReviewAcceptanceCommit, ...]:
        """Pure exact-pointer ancestry, newest first; never promote loose residue."""
        current = self.load_current_acceptance(package_key)
        chain, seen = [], set()
        while current is not None:
            require(current.identity not in seen and current.value["package_key"] == package_key,
                    "REVIEW_PREDECESSOR_INVALID")
            seen.add(current.identity)
            chain.append(current)
            previous_id = current.value["predecessor_commit_identity"]
            previous = None if previous_id is None else self.load_acceptance(previous_id)
            current = previous
        prior = {}
        for commit in reversed(chain):
            for receipt in commit.receipts:
                predecessor = prior.get(receipt.binding.lineage_key)
                require(receipt.body["predecessor_receipt_id"] == (
                    None if predecessor is None else predecessor.receipt_id
                ), "REVIEW_PREDECESSOR_INVALID")
                prior[receipt.binding.lineage_key] = receipt
        return tuple(chain)

    def context_acceptance_history(self, trading_date, slot):
        key = _hash(canonical(["MCX_SUPPORTING_CONTEXT", trading_date.isoformat(), slot.value]))
        chain = self.acceptance_history(key)
        for commit in chain:
            require(len(commit.receipts) == 1 and commit.receipts[0].binding.scope == "MCX_SUPPORTING_CONTEXT",
                    "REVIEW_ACCEPTANCE_INCOMPLETE")
            binding = commit.receipts[0].binding.value
            require(binding["trading_date"] == trading_date.isoformat() and binding["slot"] == slot.value,
                    "REVIEW_BINDING_STALE")
        return chain

    def native_acceptance_history(self, market, run_identity):
        require(market in {"NSE", "MCX"} and text(run_identity), "REVIEW_BINDING_STALE")
        return self.acceptance_history(_hash(canonical(["NATIVE_REVIEW", market, run_identity])))

    def resolve_committed_receipt(self, commit_identity, receipt_identity, *, current=False):
        """An immutable receipt file alone is never downstream authority."""
        commit = self.load_acceptance(commit_identity)
        chain = self.acceptance_history(commit.value["package_key"])
        require(bool(chain) and any(item.identity == commit_identity for item in chain),
                "REVIEW_ACCEPTANCE_INCOMPLETE")
        if current:
            require(chain[0].identity == commit_identity, "REVIEW_BINDING_STALE")
        matches = [item for item in commit.receipts if item.receipt_id == receipt_identity]
        require(len(matches) == 1, "REVIEW_ACCEPTANCE_INCOMPLETE")
        return matches[0]

    def structured_evidence_for(self, commit_identity, receipt_identity):
        receipt = self.resolve_committed_receipt(commit_identity, receipt_identity)
        return tuple(self._read(item["retained_relative_path"])
                     for item in receipt.body["structured_evidence"])

    @staticmethod
    def _attempt_pointer(receipt_identity, consumer_identity, consumer_version):
        require(all(text(item) for item in (receipt_identity, consumer_identity, consumer_version)),
                "REVIEW_REQUEST_MISMATCH")
        key = _hash(canonical([receipt_identity, consumer_identity, consumer_version]))
        return "downstream-current/" + key + ".json"

    def downstream_attempts(self, commit_identity, receipt_identity, consumer_identity, consumer_version):
        """Pure pointer ancestry; never infer completion from an unselected event."""
        self.resolve_committed_receipt(commit_identity, receipt_identity)
        path = self._attempt_pointer(receipt_identity, consumer_identity, consumer_version)
        pointer = self._optional_read(path)
        if pointer is None:
            return ()
        value = closed(strict_json(pointer), {"attempt_identity", "integrity_sha256"})
        require(value["integrity_sha256"] == _hash(canonical({"attempt_identity": value["attempt_identity"]})),
                "REVIEW_ARTIFACT_DIGEST_MISMATCH")
        identity, seen, result = value["attempt_identity"], set(), []
        while identity is not None:
            require(identity not in seen, "REVIEW_PREDECESSOR_INVALID")
            seen.add(identity)
            attempt = ReviewDownstreamAttempt(self._read(_attempt_path(identity)))
            event = attempt.value
            require(attempt.identity == identity and (event["commit_identity"], event["receipt_id"],
                    event["consumer_contract_identity"], event["consumer_contract_version"]) ==
                    (commit_identity, receipt_identity, consumer_identity, consumer_version),
                    "REVIEW_REQUEST_MISMATCH")
            result.append(attempt)
            identity = event["predecessor_attempt_identity"]
        chronological = tuple(reversed(result))
        for index, attempt in enumerate(chronological):
            state = attempt.value["state"]
            prior = None if index == 0 else chronological[index - 1].value["state"]
            require((state == "RUNNING" and prior in {None, "RUNNING", "FAILED"})
                    or (state in {"FAILED", "SUCCEEDED"} and prior == "RUNNING")
                    or (state == "UNSUPPORTED_CONTRACT" and prior is None),
                    "REVIEW_PREDECESSOR_INVALID")
        return tuple(result)

    def _prepare_attempt(self, commit_identity, receipt, consumer_identity, consumer_version,
                         state, recorded_at, previous, outputs=()):
        require(not _INTAKE_HELD.get(), "REVIEW_PUBLICATION_LOCK_ORDER_INVALID")
        require(valid_timestamp(recorded_at), "REVIEW_TIMESTAMP_INVALID")
        value = {"schema": ATTEMPT_SCHEMA, "version": "1.0", "receipt_id": receipt.receipt_id,
            "commit_identity": commit_identity, "consumer_contract_identity": consumer_identity,
            "consumer_contract_version": consumer_version, "state": state, "recorded_at": recorded_at,
            "predecessor_attempt_identity": None if previous is None else previous.identity,
            "reason_code": {"FAILED": "REVIEW_DOWNSTREAM_PROCESSING_FAILED",
                "UNSUPPORTED_CONTRACT": "REVIEW_DOWNSTREAM_CONTRACT_UNSUPPORTED"}.get(state),
            "output_identities": list(outputs)}
        value["attempt_identity"] = ATTEMPT_PREFIX + _hash(canonical(value))
        value["integrity_sha256"] = _hash(canonical(value))
        attempt = ReviewDownstreamAttempt(canonical(value))
        pointer = {"attempt_identity": attempt.identity}
        pointer["integrity_sha256"] = _hash(canonical(pointer))
        path = self._attempt_pointer(receipt.receipt_id, consumer_identity, consumer_version)
        return attempt, _attempt_path(attempt.identity), path, canonical(pointer)

    def _publish_attempt_locked(self, prepared):
        require(_INTAKE_HELD.get(), "REVIEW_PUBLICATION_LOCK_ORDER_INVALID")
        attempt, artifact_path, path, pointer_bytes = prepared
        self._immutable(artifact_path, attempt.payload)
        self._fault("after_downstream_attempt_retention")
        self._path(path).parent.mkdir(parents=True, exist_ok=True)
        self._replace_pointer(pointer_bytes, path)
        self._fsync_directory(self._path(path).parent)
        return attempt

    def handoff_committed(self, commit_identity, receipt_identity, *, consumer_identity,
                          consumer_version, clock, publication_guard, recheck, restore, consume):
        """Prepare, admit, execute unlocked, then fence exact completion.

        An advisory, nonblocking lease on the already retained immutable receipt
        excludes concurrent consumers without a new file or persisted schema.
        It is acquired only under WO05 -> WO07 and never waited on. A process
        crash releases it; explicit recovery still restores exact output first.
        Publication locks are never retained across downstream execution.
        """
        require(not _INTAKE_HELD.get(), "REVIEW_PUBLICATION_LOCK_ORDER_INVALID")
        require(all(callable(fn) for fn in (clock, publication_guard, recheck, restore, consume)),
                "REVIEW_REQUEST_MISMATCH")
        with capture_prepared_reads() as reads:
            receipt = self.resolve_committed_receipt(commit_identity, receipt_identity, current=True)
            require(receipt.binding.scope == "NATIVE_REVIEW", "REVIEW_CONTRACT_UNSUPPORTED")
            attempts = self.downstream_attempts(commit_identity, receipt_identity, consumer_identity, consumer_version)
            previous = attempts[0] if attempts else None
            market = receipt.binding.value["market"]
            prior_state = None if previous is None else previous.value["state"]
            prior_outputs = None if previous is None else previous.value["output_identities"]
            # Production owners supply a preparation function that performs all
            # request/chart/history validation now and returns a byte-only fence.
            prepare = getattr(recheck, "prepare", None)
            guarded_check = prepare(receipt) if prepare is not None else recheck
        fence = PreparedReadFence(tuple(reads.items()))
        if market == "MCX":
            require(prior_state in {None, "UNSUPPORTED_CONTRACT"}, "REVIEW_CONTRACT_UNSUPPORTED")
        prepared = None if prior_state in {"SUCCEEDED", "UNSUPPORTED_CONTRACT"} else self._prepare_attempt(
            commit_identity, receipt, consumer_identity, consumer_version,
            "UNSUPPORTED_CONTRACT" if market == "MCX" else "RUNNING", clock(), previous)
        receipt_path = self._path("receipts/" + receipt_identity + ".json")
        descriptor = os.open(receipt_path, os.O_RDONLY | os.O_NOFOLLOW)
        leased = False
        try:
            with publication_guard() as snapshot:
                with self.intake_lock():
                    fence.check()
                    guarded_check(snapshot, receipt)
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        leased = True
                    except BlockingIOError as error:
                        raise ReviewEvidenceError("REVIEW_PUBLICATION_CONFLICT") from error
                    # The immutable guard snapshot is retained, not reparsed or
                    # replaced by a newer current-run observation on completion.
                    admitted_snapshot = (snapshot.control, snapshot.manifest) if hasattr(snapshot, "control") else snapshot
                    if prepared is not None:
                        self._publish_attempt_locked(prepared)
            if market == "MCX":
                return previous if prepared is None else prepared[0]
            if prior_state == "SUCCEEDED":
                outputs = restore(receipt)
                require(outputs is not None and list(outputs) == prior_outputs,
                        "REVIEW_ARTIFACT_DIGEST_MISMATCH")
                with publication_guard() as snapshot:
                    with self.intake_lock():
                        fence.check()
                        guarded_check(snapshot, receipt)
                        current_snapshot = (snapshot.control, snapshot.manifest) if hasattr(snapshot, "control") else snapshot
                        require(current_snapshot == admitted_snapshot, "REVIEW_BINDING_STALE")
                return previous
            admission, artifact_path, pointer_path, pointer_bytes = prepared
            completion_fence = fence.with_published(
                (self._path(pointer_path), pointer_bytes), (self._path(artifact_path), admission.payload))
            try:
                self._fault("before_downstream_dispatch")
                outputs = restore(receipt)
                if outputs is None:
                    outputs = consume(receipt)
                require(type(outputs) is tuple and bool(outputs) and all(text(item) for item in outputs)
                        and len(outputs) == len(set(outputs)), "REVIEW_ACCEPTANCE_INCOMPLETE")
                state = "SUCCEEDED"
            except (OSError, TypeError, ValueError):
                outputs, state = (), "FAILED"
            # Crash after output retention intentionally leaves RUNNING. An
            # explicit retry must restore exact output before repeating work.
            self._fault("after_downstream_output")
            completion = self._prepare_attempt(commit_identity, receipt, consumer_identity, consumer_version,
                state, clock(), admission, outputs)
            with publication_guard() as snapshot:
                with self.intake_lock():
                    completion_fence.check()
                    guarded_check(snapshot, receipt)
                    current_snapshot = (snapshot.control, snapshot.manifest) if hasattr(snapshot, "control") else snapshot
                    require(current_snapshot == admitted_snapshot, "REVIEW_BINDING_STALE")
                    return self._publish_attempt_locked(completion)
        finally:
            if leased:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def context_records(self, trading_date, slot):
        """Decode only whole committed packages into the unchanged context type."""
        return tuple(record for _, records in self.context_package_history(trading_date, slot)
                     for record in records)

    def context_package_history(self, trading_date, slot):
        """Resolve the pointer once; all decoded families share that ancestry."""
        from kronos.swing.v1.mcx_supporting_context import (
            MCX_CONTEXT_CONTRACT_ID, MCX_CONTEXT_CONTRACT_VERSION,
            _record_from_dict,
        )

        values = []
        for commit in reversed(self.context_acceptance_history(trading_date, slot)):
            receipt = commit.receipts[0]
            binding = receipt.binding.value
            records = []
            for artifact in receipt.body["structured_evidence"]:
                require(artifact["schema"] == MCX_CONTEXT_CONTRACT_ID
                        and artifact["version"] == MCX_CONTEXT_CONTRACT_VERSION,
                        "REVIEW_CONTRACT_UNSUPPORTED")
                record = _record_from_dict(strict_json(self._read(artifact["retained_relative_path"])))
                require(record.trading_date == trading_date and record.slot == slot
                        and record.family.value == artifact["timeframe_or_family_identity"]
                        and record.question_pack_identity == binding["question_pack_identity"]
                        and record.answer_pack_identity == receipt.body["answer"]["answer_identity"],
                        "REVIEW_REQUEST_MISMATCH")
                records.append(record)
            require(tuple(item.family.value for item in records) == ("METALS", "ENERGY"),
                    "REVIEW_ACCEPTANCE_INCOMPLETE")
            values.append((commit, tuple(records)))
        return tuple(values)

    def publish_acceptance(self, receipts: tuple[ReviewAcceptanceReceipt, ...], artifacts: dict[str, bytes], *,
                           request_publication_identity: str, expected_predecessor: str | None,
                           committed_at: str, recheck, publication_guard=None, guarded_recheck=None) -> ReviewAcceptanceCommit:
        """Commit one already-validated complete package, never individual frames.

        recheck must resolve the committed request publication and full current
        binding; it runs before retention and immediately before visibility.
        Downstream work is deliberately absent from this transaction.
        """
        require(not _INTAKE_HELD.get(), "REVIEW_PUBLICATION_LOCK_ORDER_INVALID")
        key = _package_key(receipts)
        require(callable(recheck) and text(request_publication_identity) and valid_timestamp(committed_at), "REVIEW_REQUEST_MISMATCH")
        required = {}
        for receipt in receipts:
            for path, checksum in self._receipt_artifacts(receipt):
                require(path not in required or required[path] == checksum, "REVIEW_PUBLICATION_CONFLICT")
                required[path] = checksum
        require(type(artifacts) is dict and set(artifacts) == set(required), "REVIEW_ACCEPTANCE_INCOMPLETE")
        for path, checksum in required.items():
            require(type(artifacts[path]) is bytes and _hash(artifacts[path]) == checksum, "REVIEW_ARTIFACT_DIGEST_MISMATCH", path)
        for receipt in receipts:
            self._verify_complete_receipt(receipt, artifacts.__getitem__)
        recheck(receipts, request_publication_identity)
        pointer_path = "acceptance-current/" + key + ".json"
        predecessor_bytes = self._optional_read(pointer_path)
        current = self.load_current_acceptance(key)
        replay = False
        if current is not None:
            original = {item.body["answer"]["answer_identity"] for item in current.receipts}
            submitted = {item.body["answer"]["answer_identity"] for item in receipts}
            replay = bool(original & submitted)
            if replay:
                def replay_body(item):
                    return {field: value for field, value in item.body.items() if field != "accepted_at"}
                require([replay_body(item) for item in receipts] == [replay_body(item) for item in current.receipts]
                        and request_publication_identity == current.value["request_publication_identity"], "REVIEW_ANSWER_IDENTITY_CONFLICT")
                require(expected_predecessor in {current.identity, current.value["predecessor_commit_identity"]}, "REVIEW_BINDING_STALE")
        if not replay:
            require((current.identity if current else None) == expected_predecessor, "REVIEW_BINDING_STALE")
            history = self.acceptance_history(key)
            prior = {item.binding.lineage_key: item for commit in reversed(history) for item in commit.receipts}
            historical_answers = {item.body["answer"]["answer_identity"] for commit in history for item in commit.receipts}
            require(not historical_answers & {item.body["answer"]["answer_identity"] for item in receipts},
                    "REVIEW_ANSWER_IDENTITY_CONFLICT")
            for receipt in receipts:
                predecessor = prior.get(receipt.binding.lineage_key)
                require(receipt.body["predecessor_receipt_id"] == (predecessor.receipt_id if predecessor else None), "REVIEW_PREDECESSOR_INVALID")
        manifest = {"schema": COMMIT_SCHEMA, "version": "1.0", "package_key": key,
            "receipts": [{"receipt_identity": item.receipt_id, "relative_path": "receipts/" + item.receipt_id + ".json",
                          "sha256": _hash(item.payload)} for item in receipts],
            "request_publication_identity": request_publication_identity,
            "predecessor_commit_identity": expected_predecessor, "committed_at": committed_at}
        manifest["commit_identity"] = ACCEPTANCE_PREFIX + _hash(canonical(manifest))
        manifest["integrity_sha256"] = _hash(canonical(manifest))
        commit = ReviewAcceptanceCommit(canonical(manifest), receipts)
        receipt_objects = tuple(("receipts/" + receipt.receipt_id + ".json", receipt.payload) for receipt in receipts)
        commit_path = _acceptance_path(commit.identity)
        pointer = {"commit_identity": commit.identity}
        pointer["integrity_sha256"] = _hash(canonical(pointer))
        pointer_bytes = canonical(pointer)
        with self._commit_context(publication_guard, guarded_recheck) as snapshot:
            require(self._optional_read(pointer_path) == predecessor_bytes, "REVIEW_BINDING_STALE")
            recheck(receipts, request_publication_identity)
            if replay:
                return current
            self._preflight_immutable((*artifacts.items(), *receipt_objects, (commit_path, commit.payload)))
            self._fault("before_acceptance_retention")
            for index, (path, payload) in enumerate(artifacts.items()):
                self._immutable(path, payload)
                self._fault(f"after_acceptance_artifact_{index}")
            for index, (path, payload) in enumerate(receipt_objects):
                self._immutable(path, payload)
                self._fault(f"after_acceptance_receipt_{index}")
            self._immutable(commit_path, commit.payload)
            self._fault("after_acceptance_manifest")
            recheck(receipts, request_publication_identity)
            if guarded_recheck is not None:
                guarded_recheck(snapshot)
            target = self._path(pointer_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".prepared-pointer-", delete=False) as stream:
                pending = Path(stream.name)
                stream.write(pointer_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                self._fault("before_acceptance_pointer")
                os.replace(pending, target)
                self._fsync_directory(target.parent)
                self._fault("after_acceptance_pointer")
            finally:
                pending.unlink(missing_ok=True)
            self._fault("before_acceptance_acknowledgement")
            return commit
