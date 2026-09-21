"""WO-07 immutable intake contracts. No reconciliation or trading authority.

Receipt objects retain canonical bytes, not caller-owned mutable dictionaries.
Applicability is a pure projection and never updates historical acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, date
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import PurePosixPath
import re

RECEIPT_SCHEMA = "KRONOS-SWING-REVIEW-EVIDENCE-RECEIPT-V1"
RECEIPT_VERSION = "1.0"
RECEIPT_SCHEMA_V2 = "KRONOS-SWING-REVIEW-EVIDENCE-RECEIPT-V2"
RECEIPT_VERSION_V2 = "2.0"
RECEIPT_PREFIX = "SWING-REVIEW-RECEIPT-"
COMMIT_SCHEMA = "KRONOS-SWING-REVIEW-EVIDENCE-COMMIT-V1"
PROJECTION_SCHEMA = "KRONOS-SWING-REVIEW-EVIDENCE-PROJECTION-V1"
NSE_REQUEST_SCHEMA = "KRONOS-SWING-NSE-REVIEW-REQUEST-V1"
NSE_ANSWER_SCHEMA = "KRONOS-SWING-NSE-REVIEW-ANSWER-V1"
NSE_TRANSPORT_VERSION = "1.0"
NSE_REQUEST_SCHEMA_V2 = "KRONOS-SWING-NSE-REVIEW-REQUEST-V2"
NSE_ANSWER_SCHEMA_V2 = "KRONOS-SWING-NSE-REVIEW-ANSWER-V2"
NSE_TRANSPORT_VERSION_V2 = "2.0"
NSE_REQUEST_FIELDS = {
    "schema", "version", "request_identity", "request_sha256", "review_pack_identity",
    "review_pack_sha256", "native_run_identity", "committed_run_manifest_identity",
    "question_set_identity", "question_set_version", "answer_schema", "answer_version",
    "request_timestamp", "subjects",
}
NSE_REQUEST_SUBJECT_FIELDS = {"subject_reference", "canonical_instrument", "native_assessment_sha256",
    "chart_revision_sha256", "responses"}
NSE_REQUEST_RESPONSE_FIELDS = {"timeframe", "expected_chart_identity", "chart_revision_sha256",
    "machine_fact_integrity_sha256", "observation_boundary", "analysis_boundary"}
NSE_TIMEFRAMES = ("1W", "1D", "4H", "1H")


class ReviewEvidenceError(ValueError):
    def __init__(self, code: str, path: str = "$") -> None:
        super().__init__(code)
        self.code = code
        self.path = path


class ReviewEvidenceState(StrEnum):
    MISSING = "MISSING"
    ACCEPTED = "ACCEPTED"
    REPLACED = "REPLACED"
    STALE = "STALE"
    INVALID = "INVALID"


def require(condition: bool, code: str, path: str = "$") -> None:
    if not condition:
        raise ReviewEvidenceError(code, path)


def closed(value: object, keys: set[str], path: str = "$") -> dict:
    require(type(value) is dict, "REVIEW_FIELD_TYPE_INVALID", path)
    extra = set(value) - keys
    missing = keys - set(value)
    require(not extra, "REVIEW_UNKNOWN_FIELD", path + "." + str(sorted(extra)[0]) if extra else path)
    require(not missing, "REVIEW_REQUIRED_FIELD_MISSING", path + "." + str(sorted(missing)[0]) if missing else path)
    return value


def text(value: object, maximum: int = 256) -> bool:
    return type(value) is str and bool(value.strip()) and len(value) <= maximum


def digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise ReviewEvidenceError("REVIEW_SERIALIZATION_INVALID") from error


def strict_json(payload: bytes | str) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "REVIEW_DUPLICATE_KEY")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise ReviewEvidenceError("REVIEW_JSON_INVALID")

    try:
        value = json.loads(payload, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (json.JSONDecodeError, UnicodeError, TypeError) as error:
        raise ReviewEvidenceError("REVIEW_JSON_INVALID") from error
    require(type(value) is dict, "REVIEW_JSON_INVALID")
    return value


def timestamp(value: datetime) -> str:
    require(isinstance(value, datetime) and value.utcoffset() is not None,
            "REVIEW_TIMESTAMP_INVALID")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def valid_timestamp(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        return timestamp(datetime.fromisoformat(value)) == value
    except (ValueError, TypeError):
        return False


def relative_path(value: object) -> bool:
    if not text(value, 2048) or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return (not path.is_absolute() and value == path.as_posix()
            and all(part not in {".", ".."} for part in path.parts)
            and bool(path.parts))


NATIVE_BINDING_FIELDS = {
    "market", "analytical_run_identity", "committed_run_manifest_identity",
    "candidate_identity", "canonical_instrument", "native_assessment_sha256",
    "review_cycle_identity", "request_identity", "request_timestamp",
    "review_pack_identity", "review_pack_sha256",
}
CONTEXT_BINDING_FIELDS = {
    "trading_date", "slot", "context_cycle_identity", "request_identity",
    "request_timestamp", "question_pack_identity", "question_pack_sha256", "families",
}


@dataclass(frozen=True, slots=True)
class ReviewEvidenceBinding:
    scope: str
    _payload: bytes

    def __post_init__(self) -> None:
        require(type(self._payload) is bytes, "REVIEW_BINDING_INVALID")
        value = strict_json(self._payload)
        require(self.scope in {"NATIVE_REVIEW", "MCX_SUPPORTING_CONTEXT"}, "REVIEW_BINDING_INVALID")
        closed(value, NATIVE_BINDING_FIELDS if self.scope == "NATIVE_REVIEW" else CONTEXT_BINDING_FIELDS)
        for key, item in value.items():
            if key != "families":
                require(text(item), "REVIEW_BINDING_INVALID", "$." + key)
        require(valid_timestamp(value["request_timestamp"]), "REVIEW_TIMESTAMP_INVALID")
        if self.scope == "NATIVE_REVIEW":
            require(value["market"] in {"NSE", "MCX"}, "REVIEW_BINDING_INVALID")
            require(digest(value["native_assessment_sha256"]) and digest(value["review_pack_sha256"]),
                    "REVIEW_BINDING_INVALID")
        else:
            try:
                day = date.fromisoformat(value["trading_date"])
            except ValueError as error:
                raise ReviewEvidenceError("REVIEW_BINDING_INVALID") from error
            require(day.isoformat() == value["trading_date"] and value["slot"] in {"MORNING", "EVENING"}
                    and value["families"] == ["METALS", "ENERGY"]
                    and digest(value["question_pack_sha256"]), "REVIEW_BINDING_INVALID")
        require(canonical(value) == self._payload, "REVIEW_BINDING_INVALID")

    @classmethod
    def create(cls, scope: str, value: dict) -> ReviewEvidenceBinding:
        return cls(scope, canonical(value))

    @property
    def value(self) -> dict:
        return strict_json(self._payload)

    @property
    def lineage_key(self) -> tuple:
        value = self.value
        if self.scope == "NATIVE_REVIEW":
            return (self.scope, value["market"], value["analytical_run_identity"],
                    value["candidate_identity"], value["canonical_instrument"],
                    value["native_assessment_sha256"])
        return self.scope, value["trading_date"], value["slot"]


CONTRACT_FIELDS = {"role", "question_contract_identity", "question_contract_version",
                   "answer_contract_identity", "answer_contract_version",
                   "structured_evidence_schema", "structured_evidence_version"}
CHART_FIELDS = {"role", "subject_identity", "reference_market", "reference_symbol",
                "timeframe_or_panel_identity", "revision_identity", "sha256", "retained_relative_path"}
STRUCTURED_FIELDS = {"role", "subject_identity", "timeframe_or_family_identity",
                     "schema", "version", "sha256", "retained_relative_path"}
BODY_FIELDS = {"scope", "binding", "contracts", "chart_revisions", "answer",
               "structured_evidence", "accepted_at", "predecessor_receipt_id"}
COMPARISON_EVIDENCE_FIELDS = {"schema", "version", "native_candidate_reference", "pair_binding_sha256",
    "native_request_identity", "native_request_sha256", "reference_request_identity", "reference_request_sha256",
    "answer_identity", "answer_pdf_sha256", "sha256", "retained_relative_path"}


def _validate_body(body: dict, *, successor: bool = False) -> ReviewEvidenceBinding:
    closed(body, BODY_FIELDS | ({"comparison_evidence"} if successor else set()))
    binding = ReviewEvidenceBinding.create(body["scope"], body["binding"])
    require(valid_timestamp(body["accepted_at"]), "REVIEW_TIMESTAMP_INVALID")
    previous = body["predecessor_receipt_id"]
    require(previous is None or (type(previous) is str and previous.startswith(RECEIPT_PREFIX)
            and digest(previous[len(RECEIPT_PREFIX):])), "REVIEW_PREDECESSOR_INVALID")
    for name, fields in (("contracts", CONTRACT_FIELDS), ("chart_revisions", CHART_FIELDS),
                         ("structured_evidence", STRUCTURED_FIELDS)):
        values = body[name]
        require(type(values) is list and bool(values), "REVIEW_ACCEPTANCE_INCOMPLETE", "$." + name)
        require(len({canonical(item) for item in values}) == len(values), "REVIEW_DUPLICATE_ARTIFACT")
        for index, item in enumerate(values):
            path = f"$.{name}[{index}]"
            closed(item, fields, path)
            for key, value in item.items():
                if key in {"reference_market", "reference_symbol"} and value is None:
                    continue
                require(text(value, 2048 if key == "retained_relative_path" else 256),
                        "REVIEW_FIELD_TYPE_INVALID", path + "." + key)
            if name != "contracts":
                require(digest(item["sha256"]) and relative_path(item["retained_relative_path"]),
                        "REVIEW_ARTIFACT_REFERENCE_INVALID", path)
            if name == "chart_revisions":
                require((item["reference_market"] is None) == (item["reference_symbol"] is None),
                        "REVIEW_ARTIFACT_REFERENCE_INVALID", path)
    roles = {item["role"] for item in body["contracts"]}
    require(roles == {item["role"] for item in body["chart_revisions"]}
            == {item["role"] for item in body["structured_evidence"]}, "REVIEW_ACCEPTANCE_INCOMPLETE")
    answer = closed(body["answer"], {"answer_identity", "pdf_sha256", "byte_length", "retained_relative_path"})
    require(text(answer["answer_identity"]) and digest(answer["pdf_sha256"])
            and type(answer["byte_length"]) is int and answer["byte_length"] > 8
            and (not successor or answer["byte_length"] <= 128 * 1024 * 1024)
            and relative_path(answer["retained_relative_path"]), "REVIEW_ARTIFACT_REFERENCE_INVALID")
    if successor:
        comparison = body["comparison_evidence"]
        if binding.scope == "NATIVE_REVIEW" and binding.value["market"] == "MCX":
            closed(comparison, COMPARISON_EVIDENCE_FIELDS)
            require(comparison["schema"] == "KRONOS-SWING-MCX-PAIR-COMPARISON-EVIDENCE-V1"
                    and comparison["version"] == "1.0"
                    and comparison["native_candidate_reference"] == binding.value["candidate_identity"]
                    and all(text(comparison[key]) for key in ("native_request_identity", "reference_request_identity"))
                    and all(digest(comparison[key]) for key in ("pair_binding_sha256", "native_request_sha256",
                                                            "reference_request_sha256", "answer_pdf_sha256", "sha256"))
                    and relative_path(comparison["retained_relative_path"])
                    and comparison["answer_identity"] == answer["answer_identity"]
                    and comparison["answer_pdf_sha256"] == answer["pdf_sha256"],
                    "REVIEW_ARTIFACT_REFERENCE_INVALID")
        else:
            require(comparison is None, "REVIEW_ARTIFACT_REFERENCE_INVALID")
    return binding


@dataclass(frozen=True, slots=True)
class ReviewAcceptanceReceipt:
    _payload: bytes

    def __post_init__(self) -> None:
        require(type(self._payload) is bytes, "REVIEW_RECEIPT_INVALID")
        value = strict_json(self._payload)
        closed(value, {"schema", "version", "receipt_id", "body", "integrity_sha256"})
        successor = (value["schema"], value["version"]) == (RECEIPT_SCHEMA_V2, RECEIPT_VERSION_V2)
        require(successor or (value["schema"], value["version"]) ==
                (RECEIPT_SCHEMA, RECEIPT_VERSION), "REVIEW_CONTRACT_UNSUPPORTED")
        _validate_body(value["body"], successor=successor)
        require(value["receipt_id"] == RECEIPT_PREFIX + sha256(canonical(value["body"])).hexdigest(),
                "REVIEW_RECEIPT_INTEGRITY_INVALID")
        unsigned = {key: item for key, item in value.items() if key != "integrity_sha256"}
        require(value["integrity_sha256"] == sha256(canonical(unsigned)).hexdigest()
                and canonical(value) == self._payload, "REVIEW_RECEIPT_INTEGRITY_INVALID")

    @classmethod
    def create(cls, body: dict) -> ReviewAcceptanceReceipt:
        successor = "comparison_evidence" in body
        _validate_body(body, successor=successor)
        value = {"schema": RECEIPT_SCHEMA_V2 if successor else RECEIPT_SCHEMA,
                 "version": RECEIPT_VERSION_V2 if successor else RECEIPT_VERSION,
                 "receipt_id": RECEIPT_PREFIX + sha256(canonical(body)).hexdigest(), "body": body}
        value["integrity_sha256"] = sha256(canonical(value)).hexdigest()
        return cls(canonical(value))

    @property
    def value(self) -> dict:
        return strict_json(self._payload)

    @property
    def body(self) -> dict:
        return self.value["body"]

    @property
    def receipt_id(self) -> str:
        return self.value["receipt_id"]

    @property
    def binding(self) -> ReviewEvidenceBinding:
        body = self.body
        return ReviewEvidenceBinding.create(body["scope"], body["binding"])

    @property
    def payload(self) -> bytes:
        return self._payload


def project_review_evidence_state(receipt: ReviewAcceptanceReceipt | None,
                                  current: ReviewEvidenceBinding | None, *,
                                  committed_successor: ReviewAcceptanceReceipt | None = None,
                                  integrity_valid: bool = True) -> ReviewEvidenceState:
    """Caller supplies only committed, integrity-verified lineage; no store I/O."""
    if not integrity_valid:
        return ReviewEvidenceState.INVALID
    if receipt is None:
        return ReviewEvidenceState.MISSING
    if committed_successor is not None:
        require(committed_successor.body["predecessor_receipt_id"] == receipt.receipt_id
                and committed_successor.binding.lineage_key == receipt.binding.lineage_key,
                "REVIEW_PREDECESSOR_INVALID")
        return ReviewEvidenceState.REPLACED
    if receipt.binding != current:
        return ReviewEvidenceState.STALE
    return ReviewEvidenceState.ACCEPTED


PRECONDITION_FIELDS = {"expected_committed_run_manifest", "expected_run_identity",
    "expected_candidate_identity", "expected_review_cycle_identity", "expected_request_identity",
    "expected_revision_set_digest", "expected_acceptance_receipt_id", "mutation_identity"}


@dataclass(frozen=True, slots=True)
class ReviewMutationPrecondition:
    _payload: bytes

    def __post_init__(self) -> None:
        value = closed(strict_json(self._payload), PRECONDITION_FIELDS)
        require(all(item is None or text(item) for item in value.values())
                and text(value["mutation_identity"]) and canonical(value) == self._payload,
                "REVIEW_PRECONDITION_INVALID")

    @classmethod
    def create(cls, value: dict) -> ReviewMutationPrecondition:
        return cls(canonical(value))

    def validate(self, current: dict) -> None:
        value = strict_json(self._payload)
        expected = {key: item for key, item in value.items() if key != "mutation_identity"}
        require(expected == current, "REVIEW_BINDING_STALE")


def nse_pre_render_digest(mapping: dict) -> str:
    """Sponsor correction: exclude exactly self digest and post-render PDF digest.

    This is NOT the finalized mapping/PDF integrity authority. Publication must
    separately hash both exact artifacts and atomically bind them in a manifest.
    """
    closed(mapping, NSE_REQUEST_FIELDS)
    return sha256(canonical({key: value for key, value in mapping.items()
                             if key not in {"request_sha256", "review_pack_sha256"}})).hexdigest()


@dataclass(frozen=True, slots=True)
class NseReviewRequestMapping:
    """Prospective mapping only; no historical record is converted on read."""
    payload: bytes

    def __post_init__(self):
        require(type(self.payload) is bytes, "REVIEW_REQUEST_MISMATCH")
        value = closed(strict_json(self.payload), NSE_REQUEST_FIELDS)
        require(value["question_set_identity"] == "SWING-V1-VISUAL-QUESTION-SET-V3"
                and (value["schema"], value["version"], value["answer_schema"],
                     value["answer_version"], value["question_set_version"]) in {
                    (NSE_REQUEST_SCHEMA, NSE_TRANSPORT_VERSION, NSE_ANSWER_SCHEMA, NSE_TRANSPORT_VERSION, "3.1"),
                    (NSE_REQUEST_SCHEMA_V2, NSE_TRANSPORT_VERSION_V2, NSE_ANSWER_SCHEMA_V2,
                     NSE_TRANSPORT_VERSION_V2, "3.2"),
                }, "REVIEW_CONTRACT_UNSUPPORTED")
        for key in ("request_identity", "review_pack_identity", "native_run_identity", "committed_run_manifest_identity"):
            require(text(value[key]), "REVIEW_REQUEST_MISMATCH", "$." + key)
        require(valid_timestamp(value["request_timestamp"]), "REVIEW_TIMESTAMP_INVALID")
        require(digest(value["review_pack_sha256"]) and digest(value["request_sha256"])
                and nse_pre_render_digest(value) == value["request_sha256"], "REVIEW_REQUEST_MISMATCH")
        subjects = value["subjects"]
        require(type(subjects) is list and bool(subjects), "REVIEW_ACCEPTANCE_INCOMPLETE", "$.subjects")
        references, instruments = set(), set()
        for index, subject in enumerate(subjects):
            path = f"$.subjects[{index}]"
            closed(subject, NSE_REQUEST_SUBJECT_FIELDS, path)
            require(text(subject["subject_reference"]) and text(subject["canonical_instrument"])
                    and digest(subject["native_assessment_sha256"]) and digest(subject["chart_revision_sha256"]),
                    "REVIEW_REQUEST_MISMATCH", path)
            require(subject["subject_reference"] not in references and subject["canonical_instrument"] not in instruments,
                    "REVIEW_REQUEST_MISMATCH", path)
            references.add(subject["subject_reference"])
            instruments.add(subject["canonical_instrument"])
            responses = subject["responses"]
            require(type(responses) is list and len(responses) == 4, "REVIEW_REQUEST_MISMATCH", path + ".responses")
            for offset, (tf, response) in enumerate(zip(NSE_TIMEFRAMES, responses, strict=True)):
                rp = f"{path}.responses[{offset}]"
                closed(response, NSE_REQUEST_RESPONSE_FIELDS, rp)
                require(response["timeframe"] == tf and response["expected_chart_identity"] == subject["canonical_instrument"]
                        and response["chart_revision_sha256"] == subject["chart_revision_sha256"]
                        and digest(response["machine_fact_integrity_sha256"]), "REVIEW_REQUEST_MISMATCH", rp)
                for key in ("observation_boundary", "analysis_boundary"):
                    boundary = response[key]
                    try:
                        require(text(boundary) and datetime.fromisoformat(boundary).utcoffset() is not None,
                                "REVIEW_REQUEST_MISMATCH", rp + "." + key)
                    except ValueError as error:
                        raise ReviewEvidenceError("REVIEW_REQUEST_MISMATCH", rp + "." + key) from error
        require(canonical(value) == self.payload, "REVIEW_REQUEST_MISMATCH")

    @classmethod
    def create(cls, mapping: dict):
        """Finalize already rendered metadata without inventing IDs/timestamps."""
        value = dict(mapping)
        value["request_sha256"] = nse_pre_render_digest(value)
        return cls(canonical(value))

    @property
    def value(self) -> dict:
        return strict_json(self.payload)

    @property
    def request_reference(self) -> dict:
        value = self.value
        return {key: value[key] for key in ("request_identity", "request_sha256")}
