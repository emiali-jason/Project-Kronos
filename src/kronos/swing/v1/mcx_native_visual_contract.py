"""Independent WO-07 MCX visual extraction contract.

Sponsor-approved annex V1. No Readiness, promotion, reconciliation or trading
authority. In particular, reference Q5 is orientation-only; narrative is not
interpreted by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math

from kronos.swing.v1.native_review import MCX_REFERENCE_MAPPINGS
from kronos.swing.v1.review_evidence_binding import (
    ReviewEvidenceError, canonical, closed, digest, strict_json, text, valid_timestamp,
)

VERSION = "1.0"
NATIVE_ROLE = "NATIVE_MCX"
REFERENCE_ROLE = "SUPPORTING_REFERENCE"
NATIVE_QUESTIONS = "KRONOS-SWING-MCX-NATIVE-VISUAL-QUESTIONS-V1"
REFERENCE_QUESTIONS = "KRONOS-SWING-MCX-REFERENCE-VISUAL-QUESTIONS-V1"
NATIVE_ANSWER = "KRONOS-SWING-MCX-NATIVE-VISUAL-ANSWER-V1"
REFERENCE_ANSWER = "KRONOS-SWING-MCX-REFERENCE-VISUAL-ANSWER-V1"
NATIVE_EVIDENCE = "KRONOS-SWING-MCX-NATIVE-VISUAL-EVIDENCE-V1"
REFERENCE_EVIDENCE = "KRONOS-SWING-MCX-REFERENCE-VISUAL-EVIDENCE-V1"
NATIVE_TIMEFRAMES = ("1D", "4H", "1H")
# Independently governed by the reference annex, not inferred from symmetry.
REFERENCE_TIMEFRAMES = ("1D", "4H", "1H")
NATIVE_REQUEST_SCHEMA = "KRONOS-SWING-MCX-NATIVE-REVIEW-REQUEST-V1"
REFERENCE_REQUEST_SCHEMA = "KRONOS-SWING-MCX-REFERENCE-REVIEW-REQUEST-V1"
REQUEST_COMMIT_SCHEMA = "KRONOS-SWING-MCX-REVIEW-REQUEST-COMMIT-V1"
RETAINED_REQUEST_FIELDS = {"schema", "version", "request_bundle_identity", "request_identity",
    "request_sha256", "review_pack_identity", "review_pack_sha256", "native_run_identity",
    "committed_run_manifest_identity", "review_cycle_identity", "question_contract_identity",
    "question_contract_version", "answer_contract_identity", "answer_contract_version",
    "request_timestamp", "subjects"}
RETAINED_NATIVE_SUBJECT_FIELDS = {"subject_reference", "native_candidate_reference", "canonical_instrument",
    "native_assessment_sha256", "supplied_native_direction", "responses"}
RETAINED_REFERENCE_SUBJECT_FIELDS = {"subject_reference", "native_candidate_reference", "native_canonical_instrument",
    "native_assessment_sha256", "reference_subject_identity", "reference_market", "reference_symbol",
    "supplied_native_direction", "responses"}
RETAINED_REFERENCE_RESPONSE_FIELDS = {"timeframe", "expected_chart_identity", "chart_revision_identity",
    "chart_revision_sha256"}
RETAINED_NATIVE_RESPONSE_FIELDS = RETAINED_REFERENCE_RESPONSE_FIELDS | {
    "native_machine_fact_integrity_sha256", "governed_reference_period",
    "governed_reference_basis_availability", "observation_boundary", "analysis_boundary"}


def mcx_pre_render_digest(mapping: dict) -> str:
    """Independent approved preimage; final artifact integrity belongs to the commit."""
    closed(mapping, RETAINED_REQUEST_FIELDS)
    _check(mapping["schema"] in (NATIVE_REQUEST_SCHEMA, REFERENCE_REQUEST_SCHEMA),
           "MCX_CONTRACT_MISMATCH", "$.schema")
    return sha256(canonical({key: value for key, value in mapping.items()
                             if key not in {"request_sha256", "review_pack_sha256"}})).hexdigest()


def _validate_retained_mapping(payload: bytes, *, native: bool) -> None:
    _check(type(payload) is bytes, "MCX_REQUEST_MISMATCH", "$")
    value = closed(strict_json(payload), RETAINED_REQUEST_FIELDS)
    _check(value["schema"] == (NATIVE_REQUEST_SCHEMA if native else REFERENCE_REQUEST_SCHEMA)
           and value["question_contract_identity"] == (NATIVE_QUESTIONS if native else REFERENCE_QUESTIONS)
           and value["answer_contract_identity"] == (NATIVE_ANSWER if native else REFERENCE_ANSWER)
           and all(type(value[key]) is str and value[key] == VERSION for key in
                   ("version", "question_contract_version", "answer_contract_version")),
           "MCX_CONTRACT_MISMATCH", "$")
    for key in ("request_bundle_identity", "request_identity", "review_pack_identity", "native_run_identity",
                "committed_run_manifest_identity", "review_cycle_identity"):
        _check(text(value[key]), "MCX_REQUEST_MISMATCH", "$." + key)
    _check(valid_timestamp(value["request_timestamp"]), "MCX_REQUEST_MISMATCH", "$.request_timestamp")
    _check(digest(value["review_pack_sha256"]) and value["request_sha256"] == mcx_pre_render_digest(value)
           and canonical(value) == payload, "MCX_REQUEST_MISMATCH", "$")
    subjects = _array(value["subjects"], "$.subjects")
    references, candidates, instruments = set(), set(), set()
    for index, subject in enumerate(subjects):
        path = f"$.subjects[{index}]"
        closed(subject, RETAINED_NATIVE_SUBJECT_FIELDS if native else RETAINED_REFERENCE_SUBJECT_FIELDS, path)
        for field in ("subject_reference", "native_candidate_reference"):
            _check(text(subject[field]), "MCX_REQUEST_MISMATCH", path + "." + field)
        instrument = subject["canonical_instrument" if native else "native_canonical_instrument"]
        _check(text(instrument) and instrument in MCX_REFERENCE_MAPPINGS, "MCX_IDENTITY_MISMATCH", path)
        _check(subject["subject_reference"] not in references
               and subject["native_candidate_reference"] not in candidates and instrument not in instruments,
               "MCX_POPULATION_MISMATCH", path)
        references.add(subject["subject_reference"])
        candidates.add(subject["native_candidate_reference"])
        instruments.add(instrument)
        _check(digest(subject["native_assessment_sha256"]), "MCX_REQUEST_MISMATCH", path)
        _enum(subject["supplied_native_direction"], ("LONG", "SHORT"), path + ".supplied_native_direction")
        if not native:
            _check((subject["reference_subject_identity"], subject["reference_market"], subject["reference_symbol"])
                   == MCX_REFERENCE_MAPPINGS[instrument], "MCX_IDENTITY_MISMATCH", path)
        responses = _array(subject["responses"], path + ".responses", 3)
        frames = NATIVE_TIMEFRAMES if native else REFERENCE_TIMEFRAMES
        for offset, (tf, response) in enumerate(zip(frames, responses, strict=True)):
            rp = f"{path}.responses[{offset}]"
            closed(response, RETAINED_NATIVE_RESPONSE_FIELDS if native else RETAINED_REFERENCE_RESPONSE_FIELDS, rp)
            _check(response["timeframe"] == tf, "MCX_TIMEFRAME_MISMATCH", rp + ".timeframe")
            _check(response["expected_chart_identity"] == (instrument if native else subject["reference_symbol"]),
                   "MCX_IDENTITY_MISMATCH", rp + ".expected_chart_identity")
            _check(text(response["chart_revision_identity"]) and digest(response["chart_revision_sha256"]),
                   "MCX_CHART_REVISION_MISMATCH", rp)
            if native:
                _check(digest(response["native_machine_fact_integrity_sha256"]), "MCX_REQUEST_MISMATCH", rp)
                _check(response["governed_reference_period"] == ("PREVIOUS_WEEK" if tf == "1H" else "PREVIOUS_MONTH")
                       and response["governed_reference_basis_availability"] in ("AVAILABLE", "UNAVAILABLE"),
                       "MCX_REFERENCE_BASIS_INVALID", rp)
                for field in ("observation_boundary", "analysis_boundary"):
                    _check(text(response[field]), "MCX_REQUEST_MISMATCH", rp + "." + field)


@dataclass(frozen=True, slots=True)
class McxNativeReviewRequestMapping:
    payload: bytes

    def __post_init__(self):
        _validate_retained_mapping(self.payload, native=True)

    @classmethod
    def create(cls, value: dict):
        return cls(canonical({**value, "request_sha256": mcx_pre_render_digest(value)}))

    @property
    def value(self):
        return strict_json(self.payload)


@dataclass(frozen=True, slots=True)
class McxReferenceReviewRequestMapping:
    payload: bytes

    def __post_init__(self):
        _validate_retained_mapping(self.payload, native=False)

    @classmethod
    def create(cls, value: dict):
        return cls(canonical({**value, "request_sha256": mcx_pre_render_digest(value)}))

    @property
    def value(self):
        return strict_json(self.payload)


def validate_mcx_request_pair(native: McxNativeReviewRequestMapping,
                              reference: McxReferenceReviewRequestMapping) -> None:
    _check(type(native) is McxNativeReviewRequestMapping and type(reference) is McxReferenceReviewRequestMapping,
           "MCX_CONTRACT_MISMATCH", "$")
    left, right = native.value, reference.value
    for field in ("request_bundle_identity", "review_cycle_identity", "review_pack_identity", "review_pack_sha256",
                  "native_run_identity", "committed_run_manifest_identity", "request_timestamp"):
        _check(left[field] == right[field], "MCX_REQUEST_MISMATCH", "$." + field)
    _check(left["request_identity"] != right["request_identity"], "MCX_REQUEST_MISMATCH", "$.request_identity")
    _check(len(left["subjects"]) == len(right["subjects"]), "MCX_POPULATION_MISMATCH", "$.subjects")
    for index, (n, r) in enumerate(zip(left["subjects"], right["subjects"], strict=True)):
        path = f"$.subjects[{index}]"
        for field in ("native_candidate_reference", "native_assessment_sha256", "supplied_native_direction"):
            _check(n[field] == r[field], "MCX_REQUEST_MISMATCH", path + "." + field)
        _check(n["canonical_instrument"] == r["native_canonical_instrument"], "MCX_IDENTITY_MISMATCH", path)


def mcx_question_pack_from_mappings(native: McxNativeReviewRequestMapping,
                                    reference: McxReferenceReviewRequestMapping) -> McxNativeVisualRequest:
    """Projection of trusted mappings; never copies native bar facts into reference provenance."""
    validate_mcx_request_pair(native, reference)
    packs = []
    for mapping, role in ((native.value, NATIVE_ROLE), (reference.value, REFERENCE_ROLE)):
        is_native = role == NATIVE_ROLE
        subjects = []
        for subject in mapping["subjects"]:
            subjects.append({"subject_reference": subject["subject_reference"],
                "native_candidate_reference": subject["native_candidate_reference"], "role": role,
                "subject_identity": subject["canonical_instrument"] if is_native else subject["reference_subject_identity"],
                "market": "MCX" if is_native else subject["reference_market"],
                "reference_symbol": None if is_native else subject["reference_symbol"],
                "supplied_native_direction": subject["supplied_native_direction"],
                "machine_inventory_disclosure": "NOT_SUPPLIED" if is_native else "NOT_GOVERNED",
                "charts": [{**{key: response[key] for key in RETAINED_REFERENCE_RESPONSE_FIELDS},
                    "expected_market": "MCX" if is_native else subject["reference_market"],
                    "reference_period": response["governed_reference_period"] if is_native else None,
                    "reference_basis_availability": response["governed_reference_basis_availability"] if is_native else "NOT_APPLICABLE"}
                    for response in subject["responses"]]})
        packs.append({"schema": NATIVE_QUESTIONS if is_native else REFERENCE_QUESTIONS, "version": VERSION,
            "request_reference": {key: mapping[key] for key in ("request_identity", "request_sha256")},
            "subjects": subjects, "questions": question_definitions(role)})
    return McxNativeVisualRequest.create({**packs[0], "supporting_reference_pack": packs[1]})


def mcx_structured_evidence(answer_payload: bytes, native: McxNativeReviewRequestMapping,
                            reference: McxReferenceReviewRequestMapping, answer_pdf_sha256: str) -> tuple[bytes, ...]:
    """Annex section 22, after strict whole-pair validation; no downstream evaluation."""
    _check(digest(answer_pdf_sha256), "MCX_REQUEST_MISMATCH", "$.answer_pdf_sha256")
    answer = validate_mcx_answer(answer_payload, mcx_question_pack_from_mappings(native, reference))
    results = []
    for mapping, answered, role in ((native.value, answer, NATIVE_ROLE),
            (reference.value, answer["supporting_reference_answer"], REFERENCE_ROLE)):
        is_native = role == NATIVE_ROLE
        for subject, raw in zip(mapping["subjects"], answered["subjects"], strict=True):
            for chart, response in zip(subject["responses"], raw["responses"], strict=True):
                binding = {key: mapping[key] for key in ("committed_run_manifest_identity", "native_run_identity",
                    "review_cycle_identity", "request_identity", "request_sha256", "request_timestamp")}
                binding.update({key: subject[key] for key in ("native_assessment_sha256", "native_candidate_reference", "subject_reference")})
                binding.update(native_canonical_instrument=subject["canonical_instrument"] if is_native else subject["native_canonical_instrument"],
                    role=role, subject_identity=raw["subject_identity"], market=raw["market"], reference_symbol=raw["reference_symbol"],
                    chart_revision_identity=chart["chart_revision_identity"], chart_revision_sha256=chart["chart_revision_sha256"],
                    timeframe=chart["timeframe"], native_machine_fact_binding=chart["native_machine_fact_integrity_sha256"] if is_native else None)
                evidence = {"schema": NATIVE_EVIDENCE if is_native else REFERENCE_EVIDENCE, "version": VERSION,
                    "binding": binding, "answer_identity": answered["answer_identity"], "answer_pdf_sha256": answer_pdf_sha256,
                    "response": response, "provenance": {"provider_identity": "SPONSOR_MEDIATED_PDF",
                        **{key: mapping[key] for key in ("question_contract_identity", "question_contract_version",
                                                       "answer_contract_identity", "answer_contract_version")}}}
                evidence["integrity_sha256"] = sha256(canonical(evidence)).hexdigest()
                results.append(canonical(evidence))
    return tuple(results)


STATUSES = ("OBSERVED", "NOT_VISIBLE", "NOT_APPLICABLE", "PARTIAL", "UNAVAILABLE", "INVALID")
PRESENCE = ("PRESENT", "NOT_PRESENT", "NOT_IDENTIFIABLE")
PRICE_RELATIONSHIP = ("ABOVE", "INSIDE", "BELOW", "NOT_OBSERVABLE")
INTERACTION = ("HOLD", "RECLAIM", "REJECTION", "BREAK", "NONE", "NOT_OBSERVABLE")
REFERENCE_RELATIONSHIP = ("ABOVE_REFERENCE_RANGE", "INSIDE_REFERENCE_RANGE", "BELOW_REFERENCE_RANGE",
    "INTERACTING_WITH_REFERENCE_HIGH", "INTERACTING_WITH_REFERENCE_LOW", "NOT_OBSERVABLE")
QUALITY = ("CLEAN_DIRECTIONAL", "HEALTHY_CONSOLIDATION", "HEALTHY_COMPRESSION", "ORDERLY_PULLBACK",
    "MESSY_CHOPPY", "CONFLICTING", "NOT_OBSERVABLE")
CLUSTERING = ("CLUSTERED", "NOT_CLUSTERED", "PARTIAL_COMPONENT_IDENTITY", "NOT_OBSERVABLE")
NATIVE_COMPONENTS = ("CPR", "GOVERNED_REFERENCE_HIGH", "GOVERNED_REFERENCE_LOW", "SMA20", "SMA50",
    "SMA200", "STRUCTURAL_PIVOT", "OPERATIVE_ANCHOR", "RANGE_BOUNDARY", "BREAK_BOUNDARY",
    "UNIDENTIFIED_PLOTTED_STRUCTURE")
REFERENCE_COMPONENTS = ("CPR", "SMA20", "SMA50", "SMA200", "STRUCTURAL_PIVOT", "RANGE_BOUNDARY",
    "BREAK_BOUNDARY", "UNIDENTIFIED_PLOTTED_STRUCTURE")
PROVENANCE_FIELDS = frozenset({"provider_identity", "native_run_identity", "native_assessment_sha256",
    "native_canonical_instrument", "request_timestamp", "analysis_boundary", "observation_boundary",
    "machine_fact_integrity_sha256", "source_provenance", "acceptance_timestamp", "receipt_id",
    "committed_run_manifest_identity"})
AUTHORITY_FIELDS = frozenset({"authority", "readiness", "promotion", "direction", "entry", "stop",
    "target", "risk", "execution_contract", "broker_instrument", "supplied_native_direction"})
REQUEST_REFERENCE_FIELDS = {"request_identity", "request_sha256"}
CHART_FIELDS = {"timeframe", "chart_revision_identity", "chart_revision_sha256", "expected_chart_identity",
    "expected_market", "reference_period", "reference_basis_availability"}
QUESTION_SUBJECT_FIELDS = {"subject_reference", "native_candidate_reference", "role", "subject_identity",
    "market", "reference_symbol", "supplied_native_direction", "machine_inventory_disclosure", "charts"}
ANSWER_SUBJECT_FIELDS = {"subject_reference", "native_candidate_reference", "role", "subject_identity",
    "observed_chart_identity", "market", "reference_symbol", "responses"}
RESPONSE_FIELDS = {"model_identity", "question_set_identity", "question_set_version", "role", "timeframe",
    "chart_identity", "chart_revision_sha256", "observations"}
OBSERVATION_FIELDS = {"question_id", "timeframe", "observation_status", "visible_basis",
    "confidence_in_extraction", "ambiguity_reason", "source_chart_identity", "source_chart_revision",
    "why_not_covered_elsewhere", "not_applicable_reason", "result"}
RESULT_FIELDS = (
    {"observed_identity", "observed_market", "observed_timeframe", "readability"},
    {"presence", "price_relationship", "interaction"},
    {"finding", "machine_coverage_comparison", "point_price", "zone_low", "zone_high"},
    {"reference_period", "presence", "relationship", "interaction"},
    {"setup_quality", "finding"}, {"finding", "point_price", "zone_low", "zone_high"},
    {"finding"}, {"finding"}, {"clustering", "components"}, {"finding", "machine_coverage_comparison"},
)


def _check(condition: bool, code: str, path: str) -> None:
    if not condition:
        raise ReviewEvidenceError(code, path)


def _closed(value: object, fields: set[str], path: str) -> dict:
    _check(type(value) is dict, "MCX_FIELD_TYPE_INVALID", path)
    extra = set(value) - fields
    for names, code in ((PROVENANCE_FIELDS, "MCX_PROVENANCE_FORBIDDEN"),
                        (AUTHORITY_FIELDS, "MCX_AUTHORITY_FIELD_FORBIDDEN")):
        found = sorted(extra & names)
        _check(not found, code, path + "." + found[0] if found else path)
    _check(not extra, "MCX_UNKNOWN_FIELD", path + "." + sorted(extra)[0] if extra else path)
    missing = fields - set(value)
    _check(not missing, "MCX_REQUIRED_FIELD_MISSING", path + "." + sorted(missing)[0] if missing else path)
    return value


def parse_mcx_json(payload: bytes | str) -> dict:
    try:
        return strict_json(payload)
    except ReviewEvidenceError as error:
        code = "MCX_DUPLICATE_KEY" if error.code == "REVIEW_DUPLICATE_KEY" else "MCX_JSON_INVALID"
        raise ReviewEvidenceError(code, error.path) from error


def _enum(value: object, values: tuple, path: str) -> None:
    _check(type(value) is str and value in values, "MCX_ENUM_INVALID", path)


def _array(value: object, path: str, count: int | None = None) -> list:
    _check(type(value) is list and (bool(value) if count is None else len(value) == count),
           "MCX_FIELD_TYPE_INVALID", path)
    return value


def _request_reference(value: object, path: str) -> dict:
    value = _closed(value, REQUEST_REFERENCE_FIELDS, path)
    _check(text(value["request_identity"]) and digest(value["request_sha256"]), "MCX_REQUEST_MISMATCH", path)
    return value


def question_definitions(role: str) -> list[dict]:
    _enum(role, (NATIVE_ROLE, REFERENCE_ROLE), "$.role")
    texts = NATIVE_QUESTION_TEXTS if role == NATIVE_ROLE else REFERENCE_QUESTION_TEXTS
    frames = NATIVE_TIMEFRAMES if role == NATIVE_ROLE else REFERENCE_TIMEFRAMES
    return [{"question_id": question, "text": wording, "applicable_timeframes": list(frames),
             "result_schema": f"Q{index + 1}Result"}
            for index, (question, wording) in enumerate(zip(QUESTION_IDS, texts, strict=True))]


def _validate_question_pack(pack: dict, role: str, associated: list | None = None) -> None:
    fields = {"schema", "version", "request_reference", "subjects", "questions"}
    if role == NATIVE_ROLE:
        fields.add("supporting_reference_pack")
    _closed(pack, fields, "$")
    _check(pack["schema"] == (NATIVE_QUESTIONS if role == NATIVE_ROLE else REFERENCE_QUESTIONS)
           and type(pack["version"]) is str and pack["version"] == VERSION, "MCX_CONTRACT_MISMATCH", "$")
    _request_reference(pack["request_reference"], "$.request_reference")
    _check(pack["questions"] == question_definitions(role), "MCX_CONTRACT_MISMATCH", "$.questions")
    subjects = _array(pack["subjects"], "$.subjects")
    for index, subject in enumerate(subjects):
        path = f"$.subjects[{index}]"
        _closed(subject, QUESTION_SUBJECT_FIELDS, path)
        for field in ("subject_reference", "native_candidate_reference", "subject_identity"):
            _check(text(subject[field]), "MCX_FIELD_TYPE_INVALID", path + "." + field)
    _check(len({item.get("subject_reference") for item in subjects if type(item) is dict}) == len(subjects),
           "MCX_POPULATION_MISMATCH", "$.subjects")
    _check(len({item.get("native_candidate_reference") for item in subjects if type(item) is dict}) == len(subjects),
           "MCX_POPULATION_MISMATCH", "$.subjects")
    if associated is not None:
        _check(len(subjects) == len(associated), "MCX_POPULATION_MISMATCH", "$.subjects")
    for index, subject in enumerate(subjects):
        path = f"$.subjects[{index}]"
        _closed(subject, QUESTION_SUBJECT_FIELDS, path)
        for field in ("subject_reference", "native_candidate_reference", "subject_identity"):
            _check(text(subject[field]), "MCX_FIELD_TYPE_INVALID", path + "." + field)
        _check(subject["role"] == role, "MCX_ROLE_MISMATCH", path + ".role")
        _enum(subject["supplied_native_direction"], ("LONG", "SHORT"), path + ".supplied_native_direction")
        if role == NATIVE_ROLE:
            _check(subject["subject_identity"] in MCX_REFERENCE_MAPPINGS and subject["market"] == "MCX"
                   and subject["reference_symbol"] is None and subject["machine_inventory_disclosure"] == "NOT_SUPPLIED",
                   "MCX_IDENTITY_MISMATCH", path)
            expected_identity = subject["subject_identity"]
        else:
            native = associated[index]
            mapped_subject, mapped_market, mapped_symbol = MCX_REFERENCE_MAPPINGS[native["subject_identity"]]
            _check(subject["native_candidate_reference"] == native["native_candidate_reference"]
                   and subject["supplied_native_direction"] == native["supplied_native_direction"], "MCX_REQUEST_MISMATCH", path)
            _check(subject["subject_identity"] == mapped_subject, "MCX_IDENTITY_MISMATCH", path + ".subject_identity")
            _check(subject["market"] == mapped_market, "MCX_REFERENCE_MARKET_MISMATCH", path + ".market")
            _check(subject["reference_symbol"] == mapped_symbol, "MCX_REFERENCE_SYMBOL_MISMATCH", path + ".reference_symbol")
            _check(subject["machine_inventory_disclosure"] == "NOT_GOVERNED", "MCX_MACHINE_COVERAGE_INVALID", path)
            expected_identity = mapped_symbol
        charts = _array(subject["charts"], path + ".charts", 3)
        for tf, chart in zip(NATIVE_TIMEFRAMES if role == NATIVE_ROLE else REFERENCE_TIMEFRAMES, charts, strict=True):
            _closed(chart, CHART_FIELDS, path + ".charts")
            _check(chart["timeframe"] == tf, "MCX_TIMEFRAME_MISMATCH", path + ".charts")
            _check(text(chart["chart_revision_identity"]) and digest(chart["chart_revision_sha256"]),
                   "MCX_CHART_REVISION_MISMATCH", path + ".charts")
            _check(chart["expected_chart_identity"] == expected_identity and chart["expected_market"] == subject["market"],
                   "MCX_IDENTITY_MISMATCH", path + ".charts")
            period = ("PREVIOUS_WEEK" if tf == "1H" else "PREVIOUS_MONTH") if role == NATIVE_ROLE else None
            availability = ("AVAILABLE", "UNAVAILABLE") if role == NATIVE_ROLE else ("NOT_APPLICABLE",)
            _check(chart["reference_period"] == period and chart["reference_basis_availability"] in availability,
                   "MCX_REFERENCE_BASIS_INVALID", path + ".charts")
    if role == NATIVE_ROLE:
        _validate_question_pack(pack["supporting_reference_pack"], REFERENCE_ROLE, subjects)
        reference = pack["supporting_reference_pack"]
        _check(pack["request_reference"]["request_identity"] != reference["request_reference"]["request_identity"],
               "MCX_REQUEST_MISMATCH", "$.supporting_reference_pack.request_reference")


@dataclass(frozen=True, slots=True)
class McxNativeVisualRequest:
    """Complete retained pair; foreign/native correspondence is validated here."""
    payload: bytes

    def __post_init__(self):
        value = parse_mcx_json(self.payload)
        _validate_question_pack(value, NATIVE_ROLE)
        _check(type(self.payload) is bytes and canonical(value) == self.payload, "MCX_CONTRACT_MISMATCH", "$")

    @classmethod
    def create(cls, value: dict):
        return cls(canonical(value))

    @property
    def value(self):
        return parse_mcx_json(self.payload)


def _validate_observation(observation: dict, index: int, role: str, chart: dict, path: str) -> None:
    _closed(observation, OBSERVATION_FIELDS, path)
    _check(observation["question_id"] == QUESTION_IDS[index], "MCX_QUESTION_ORDER_INVALID", path + ".question_id")
    result = _closed(observation["result"], RESULT_FIELDS[index], path + ".result")
    _check(observation["timeframe"] == chart["timeframe"], "MCX_TIMEFRAME_MISMATCH", path + ".timeframe")
    _check(observation["source_chart_identity"] == chart["expected_chart_identity"], "MCX_IDENTITY_MISMATCH", path + ".source_chart_identity")
    _check(observation["source_chart_revision"] == chart["chart_revision_sha256"], "MCX_CHART_REVISION_MISMATCH", path + ".source_chart_revision")
    status = observation["observation_status"]
    _enum(status, STATUSES, path + ".observation_status")
    for name, maximum in (("visible_basis", 512), ("confidence_in_extraction", 64)):
        _check(text(observation[name], maximum), "MCX_FIELD_TYPE_INVALID", path + "." + name)
    ambiguity = observation["ambiguity_reason"]
    _check(type(ambiguity) is str and len(ambiguity) <= 512
           and (status not in {"PARTIAL", "UNAVAILABLE", "INVALID"} or bool(ambiguity.strip())),
           "MCX_AVAILABILITY_INVALID", path + ".ambiguity_reason")
    reference_q4 = role == REFERENCE_ROLE and index == 3
    _check((status == "NOT_APPLICABLE") == reference_q4
           and observation["not_applicable_reason"] == ("REFERENCE_PERIOD_NOT_GOVERNED" if reference_q4 else None),
           "MCX_NOT_APPLICABLE_INVALID", path + ".not_applicable_reason")
    why = observation["why_not_covered_elsewhere"]
    _check((why is None) if index != 9 or result.get("finding") == "NONE" else text(why, 512),
           "MCX_Q10_INVALID", path + ".why_not_covered_elsewhere")
    if "finding" in result:
        _check(text(result["finding"], 512), "MCX_FIELD_TYPE_INVALID", path + ".result.finding")
    if index == 0:
        _enum(result["readability"], ("READABLE", "PARTIAL", "UNREADABLE"), path + ".result.readability")
        _check(result["readability"] != "UNREADABLE"
               and all(result[key] is not None for key in ("observed_identity", "observed_market", "observed_timeframe")),
               "MCX_IDENTITY_UNAVAILABLE", path + ".result")
        _check(result["observed_identity"] == chart["expected_chart_identity"], "MCX_IDENTITY_MISMATCH", path + ".result.observed_identity")
        _check(result["observed_market"] == chart["expected_market"], "MCX_IDENTITY_MISMATCH", path + ".result.observed_market")
        _check(result["observed_timeframe"] == chart["timeframe"], "MCX_TIMEFRAME_MISMATCH", path + ".result.observed_timeframe")
    elif index in (1, 3):
        if reference_q4:
            _check(all(value is None for value in result.values()), "MCX_REFERENCE_BASIS_INVALID", path + ".result")
        else:
            relation = "price_relationship" if index == 1 else "relationship"
            _enum(result["presence"], PRESENCE, path + ".result.presence")
            _enum(result[relation], PRICE_RELATIONSHIP if index == 1 else REFERENCE_RELATIONSHIP, path + ".result." + relation)
            _enum(result["interaction"], INTERACTION, path + ".result.interaction")
            _check(result["presence"] == "PRESENT" or (result[relation] == "NOT_OBSERVABLE" and result["interaction"] == "NOT_OBSERVABLE"),
                   "MCX_Q2_INVALID" if index == 1 else "MCX_REFERENCE_BASIS_INVALID", path + ".result")
            if index == 3:
                _check(result["reference_period"] == chart["reference_period"], "MCX_REFERENCE_BASIS_INVALID", path + ".result.reference_period")
                _check(chart["reference_basis_availability"] != "UNAVAILABLE" or
                       (status == "UNAVAILABLE" and result["presence"] == "NOT_IDENTIFIABLE"
                        and result[relation] == "NOT_OBSERVABLE" and result["interaction"] == "NOT_OBSERVABLE"),
                       "MCX_REFERENCE_BASIS_INVALID", path + ".result")
    elif index == 4:
        _enum(result["setup_quality"], QUALITY, path + ".result.setup_quality")
    elif index == 7:
        _check(status not in {"NOT_VISIBLE", "UNAVAILABLE"} or result["finding"] == "NONE", "MCX_AVAILABILITY_INVALID", path + ".result.finding")
    elif index == 8:
        _enum(result["clustering"], CLUSTERING, path + ".result.clustering")
        components = result["components"]
        allowed = NATIVE_COMPONENTS if role == NATIVE_ROLE else REFERENCE_COMPONENTS
        _check(type(components) is list and all(type(c) is str and c in allowed for c in components), "MCX_COMPONENT_ROLE_INVALID", path + ".result.components")
        _check(components == [c for c in allowed if c in components], "MCX_Q9_INVALID", path + ".result.components")
        identifiable = [c for c in components if c != "UNIDENTIFIED_PLOTTED_STRUCTURE"]
        state = result["clustering"]
        _check((state != "CLUSTERED" or len(identifiable) >= 2)
               and (state not in {"NOT_CLUSTERED", "NOT_OBSERVABLE"} or not components)
               and (state != "PARTIAL_COMPONENT_IDENTITY" or "UNIDENTIFIED_PLOTTED_STRUCTURE" in components),
               "MCX_Q9_INVALID", path + ".result")
    if index in (2, 9):
        _check(result["machine_coverage_comparison"] == ("COMPARISON_UNAVAILABLE" if role == NATIVE_ROLE else "NOT_APPLICABLE"),
               "MCX_MACHINE_COVERAGE_INVALID", path + ".result.machine_coverage_comparison")
    if index in (2, 5):
        point, low, high = (result[key] for key in ("point_price", "zone_low", "zone_high"))
        def number(value):
            return type(value) in (int, float) and (type(value) is int or math.isfinite(value)) and value >= 0
        valid = ((point is low is high is None) or (number(point) and low is high is None)
                 or (point is None and number(low) and number(high) and low <= high))
        _check(valid and ((result["finding"] != "NONE" and status not in {"NOT_VISIBLE", "UNAVAILABLE", "INVALID"})
                         or point is low is high is None), "MCX_LEVEL_INVALID", path + ".result")


def _validate_answer(answer: dict, request: dict, role: str, path: str) -> None:
    fields = {"schema", "version", "request_reference", "answer_identity", "subjects"}
    if role == NATIVE_ROLE:
        fields.add("supporting_reference_answer")
    _closed(answer, fields, path)
    _check(answer["schema"] == (NATIVE_ANSWER if role == NATIVE_ROLE else REFERENCE_ANSWER)
           and type(answer["version"]) is str and answer["version"] == VERSION, "MCX_CONTRACT_MISMATCH", path)
    _request_reference(answer["request_reference"], path + ".request_reference")
    _check(answer["request_reference"] == request["request_reference"], "MCX_REQUEST_MISMATCH", path + ".request_reference")
    _check(text(answer["answer_identity"]), "MCX_FIELD_TYPE_INVALID", path + ".answer_identity")
    subjects = _array(answer["subjects"], path + ".subjects")
    _check(len(subjects) == len(request["subjects"]), "MCX_POPULATION_MISMATCH", path + ".subjects")
    for index, (subject, expected) in enumerate(zip(subjects, request["subjects"], strict=True)):
        sp = f"{path}.subjects[{index}]"
        _closed(subject, ANSWER_SUBJECT_FIELDS, sp)
        _check(subject["role"] == role, "MCX_ROLE_MISMATCH", sp + ".role")
        for key in ("subject_reference", "native_candidate_reference", "subject_identity", "market", "reference_symbol"):
            code = {"market": "MCX_REFERENCE_MARKET_MISMATCH", "reference_symbol": "MCX_REFERENCE_SYMBOL_MISMATCH"}.get(key, "MCX_IDENTITY_MISMATCH")
            _check(subject[key] == expected[key], code, sp + "." + key)
        _check(subject["observed_chart_identity"] == expected["charts"][0]["expected_chart_identity"], "MCX_IDENTITY_MISMATCH", sp + ".observed_chart_identity")
        responses = subject["responses"]
        _check(type(responses) is list and len(responses) == 3, "MCX_TIMEFRAME_MISMATCH", sp + ".responses")
        for ri, (response, chart) in enumerate(zip(responses, expected["charts"], strict=True)):
            rp = f"{sp}.responses[{ri}]"
            _closed(response, RESPONSE_FIELDS, rp)
            _check(text(response["model_identity"], 128), "MCX_FIELD_TYPE_INVALID", rp + ".model_identity")
            _check(response["question_set_identity"] == request["schema"] and response["question_set_version"] == VERSION,
                   "MCX_CONTRACT_MISMATCH", rp)
            _check(response["role"] == role, "MCX_ROLE_MISMATCH", rp + ".role")
            _check(response["timeframe"] == chart["timeframe"], "MCX_TIMEFRAME_MISMATCH", rp + ".timeframe")
            _check(response["chart_identity"] == chart["expected_chart_identity"], "MCX_IDENTITY_MISMATCH", rp + ".chart_identity")
            _check(response["chart_revision_sha256"] == chart["chart_revision_sha256"], "MCX_CHART_REVISION_MISMATCH", rp + ".chart_revision_sha256")
            observations = response["observations"]
            _check(type(observations) is list and len(observations) == 10, "MCX_QUESTION_COUNT_INVALID", rp + ".observations")
            for qi, observation in enumerate(observations):
                _validate_observation(observation, qi, role, chart, f"{rp}.observations[{qi}]")
    if role == NATIVE_ROLE:
        _check(answer["supporting_reference_answer"] is not None, "MCX_REFERENCE_REQUIRED", path + ".supporting_reference_answer")
        _validate_answer(answer["supporting_reference_answer"], request["supporting_reference_pack"], REFERENCE_ROLE, path + ".supporting_reference_answer")


def _answer_shape(answer: dict, role: str, path: str) -> None:
    """Complete closed-object pass precedes any request/identity comparison."""
    fields = {"schema", "version", "request_reference", "answer_identity", "subjects"}
    if role == NATIVE_ROLE:
        fields.add("supporting_reference_answer")
    _closed(answer, fields, path)
    _check(answer["schema"] == (NATIVE_ANSWER if role == NATIVE_ROLE else REFERENCE_ANSWER)
           and type(answer["version"]) is str and answer["version"] == VERSION, "MCX_CONTRACT_MISMATCH", path)
    _closed(answer["request_reference"], REQUEST_REFERENCE_FIELDS, path + ".request_reference")
    subjects = _array(answer["subjects"], path + ".subjects")
    for si, subject in enumerate(subjects):
        sp = f"{path}.subjects[{si}]"
        _closed(subject, ANSWER_SUBJECT_FIELDS, sp)
        _check(type(subject["responses"]) is list, "MCX_FIELD_TYPE_INVALID", sp + ".responses")
        for ri, response in enumerate(subject["responses"]):
            rp = f"{sp}.responses[{ri}]"
            _closed(response, RESPONSE_FIELDS, rp)
            _check(type(response["observations"]) is list, "MCX_FIELD_TYPE_INVALID", rp + ".observations")
            for qi, obs in enumerate(response["observations"]):
                op = f"{rp}.observations[{qi}]"
                _closed(obs, OBSERVATION_FIELDS, op)
                # Shape is selected by the declared question, never by position
                # before the later exact count/order check.
                _check(type(obs["question_id"]) is str and obs["question_id"] in QUESTION_IDS,
                       "MCX_QUESTION_ORDER_INVALID", op + ".question_id")
                _closed(obs["result"], RESULT_FIELDS[QUESTION_IDS.index(obs["question_id"])], op + ".result")
    if role == NATIVE_ROLE and answer["supporting_reference_answer"] is not None:
        _answer_shape(answer["supporting_reference_answer"], REFERENCE_ROLE, path + ".supporting_reference_answer")


def validate_mcx_answer(payload: bytes | str, request: McxNativeVisualRequest) -> dict:
    """Pure validation. Returns independently reported values, never repaired ones."""
    _check(type(request) is McxNativeVisualRequest, "MCX_REQUEST_MISMATCH", "$")
    answer = parse_mcx_json(payload)
    _answer_shape(answer, NATIVE_ROLE, "$")
    _validate_answer(answer, request.value, NATIVE_ROLE, "$")
    return answer
QUESTION_IDS = (
    "VISUAL_CHART_VALIDATION", "CPR_VISUAL_RELATIONSHIP",
    "VISUAL_SUPPORT_RESISTANCE_GAP", "GOVERNED_REFERENCE_VISUAL_CONTEXT",
    "PRICE_ACTION_QUALITY", "VISUAL_OBSTACLE_EVIDENCE",
    "MATURITY_AND_CHASE_CONTEXT", "PINE_VISIBLE_EVIDENCE",
    "VISUAL_COMPONENT_CLUSTERING", "VISUAL_FACTS_NOT_CAPTURED_BY_KRONOS",
)
NATIVE_QUESTION_TEXTS = (
    "Independently read the native MCX chart identity, market and timeframe, and report chart readability. Bind this observation to the exact supplied native chart revision. Do not substitute a COMEX/NYMEX subject or infer an executable futures contract.",
    "Report whether CPR is independently identifiable on this native MCX chart, the visible price relationship to it, and any visible interaction. Do not transcribe, calculate or infer CP, BC or TC.",
    "Report material support or resistance independently visible on this native MCX chart. The deterministic machine inventory is not supplied to the Chart Analyst: mark machine_coverage_comparison as COMPARISON_UNAVAILABLE and do not claim that a reported structure is absent from KRONOS. Report a price or zone only when independently readable; otherwise leave all level fields null. NONE is valid.",
    "Using only the exact native chart revision and governed reference-period declaration in this request, report the visible relationship to the previous-month structure on 1D/4H or previous-week structure on 1H. Do not substitute PDH/PDL, transcribe reference levels, use another revision, or compare MCX prices with COMEX/NYMEX prices. If the governed basis is unavailable, report UNAVAILABLE.",
    "Classify the visible price-action quality on this native MCX chart relative to the supplied Native direction, using only the permitted setup_quality values, and state the visible basis. Do not originate or change direction or state a Readiness, promotion or trading consequence.",
    "Report factual obstacles independently visible on this native MCX chart. A readable point or zone may be reported in this chart’s own price units. Do not create Entry, Stop, Target, risk or execution geometry. NONE is valid.",
    "Describe only the visible maturity, extension or chase context of this native MCX chart. Do not calculate a threshold, extension score or trading consequence. NONE is valid.",
    "Transcribe only independently readable evidence displayed by the Pine panel on this native MCX chart. Attribute it as displayed content, not a KRONOS decision. If no Pine panel is visible, report NOT_VISIBLE with finding NONE; if present but unreadable, report UNAVAILABLE with finding NONE.",
    "Report whether at least two identifiable structures plotted on this native MCX chart visibly cluster near active price, using only the permitted native component identities. Do not include reference-market components, create a numerical zone or assign a score.",
    "Report only a clear material native-chart fact not covered by Q1–Q9. Use finding NONE when there is no such fact. For a non-NONE finding, explain specifically why Q1–Q9 do not cover it. Mark machine_coverage_comparison as COMPARISON_UNAVAILABLE; do not claim absence from an undisclosed machine inventory or provide an analytical consequence or recommendation.",
)
REFERENCE_QUESTION_TEXTS = (
    "Independently read the mapped COMEX/NYMEX chart symbol, market and timeframe, and report readability. Bind this observation to the exact supplied reference chart revision. The reference subject is not the native MCX candidate and is not an MCX executable contract.",
    "Report only independently identifiable CPR plotted on this COMEX/NYMEX reference chart, its visible price relationship and visible interaction. This is visual supporting evidence only: do not calculate or transcribe CP, BC or TC, or treat these as MCX levels.",
    "Report material support or resistance independently visible on this reference chart. No governed KRONOS COMEX/NYMEX machine inventory is provided by this contract: mark machine_coverage_comparison as NOT_APPLICABLE. A readable point or zone remains in the reference chart’s own price units and must not be converted to an MCX price. NONE is valid.",
    "No governed COMEX/NYMEX previous-week/month machine-reference period is commissioned by this contract. Return NOT_APPLICABLE with reason REFERENCE_PERIOD_NOT_GOVERNED and null reference-period, presence, relationship and interaction fields. Do not substitute MCX references, PDH/PDL or another chart.",
    "Describe this reference chart’s visible price-action quality relative to the supplied Native direction as an orientation comparison only, using the permitted setup_quality values. Do not originate or change the Native direction, infer MCX price alignment, or produce Readiness, promotion or trading consequences.",
    "Report factual obstacles independently visible on this reference chart. Any readable point or zone is reference-market evidence only and must remain bound to this reference symbol and revision. Do not derive MCX Entry, Stop, Target or execution geometry. NONE is valid.",
    "Describe only visible maturity, extension or chase context on this reference chart. Do not transfer a price distance or threshold to MCX and do not state a trading consequence. NONE is valid.",
    "Transcribe only independently readable Pine-panel content on this reference chart, explicitly as displayed supporting evidence. If no Pine panel is visible, report NOT_VISIBLE with finding NONE; if present but unreadable, report UNAVAILABLE with finding NONE. Do not convert a displayed label into KRONOS authority.",
    "Report whether identifiable structures plotted on this reference chart visibly cluster near its active price, using only the permitted reference component identities. Do not include native MCX operative anchors or governed native reference levels, create a numerical zone or assign a score.",
    "Report only a clear material reference-chart fact not covered by reference Q1–Q9. Use finding NONE when there is no such fact. For a non-NONE finding, explain why those questions do not cover it. Mark machine_coverage_comparison as NOT_APPLICABLE. Do not provide an MCX analytical consequence, recommendation or assertion about nonexistent reference-market machine evidence.",
)
