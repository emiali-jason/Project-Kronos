"""TE-05C deterministic assessment of exact accepted Theta V3 evidence.

This module is deliberately narrower than an analytical model.  It verifies
the documentary relationships named by ADR-0067, persists one immutable
KRONOS-owned record, and projects existing TE-04B currentness.  It never reads
an inbox, accepts caller-supplied JSON/policy, interprets prose or charts, or
changes the accepted forecast.
"""
from copy import deepcopy
from datetime import datetime
import re

from kronos.theta.combined_intake import CombinedAnswerIntake
from kronos.theta.contracts import ThetaError, digest, encode, require, stamp
from kronos.theta.contracts_v3 import validate_answer_v3, validate_question_v3
from kronos.theta.methodology import (
    ASSESSMENT_ID, ASSESSMENT_SHA256, RESEARCH_ID, RESEARCH_SHA256, VERSION,
    ThetaMethodologyPublication,
)
from kronos.theta.store import sealed, unseal

SCHEMA_ID = "KRONOS-THETA-ANALYTICAL-ASSESSMENT-V1"
SCHEMA_VERSION = "1.0.0"
STATES = ("DOCUMENTED", "LIMITED", "NOT_EVALUABLE")
CRITERIA = tuple("C" + str(number) for number in range(1, 10))
REFERENCE_KEYS = (
    "evidence_ids", "source_ids", "observation_ids", "relation_ids",
    "event_ids", "assumption_ids", "limitation_ids",
)
VERIFICATION_CLAIM = (
    "KRONOS verified the integrity and required documentary relationships of "
    "this assessment."
)
RESEARCH_DESCRIPTOR = {
    "identity": RESEARCH_ID, "version": VERSION, "sha256": RESEARCH_SHA256,
}
ASSESSMENT_DESCRIPTOR = {
    "identity": ASSESSMENT_ID, "version": VERSION, "sha256": ASSESSMENT_SHA256,
}


def _key(value):
    return digest(encode(value)) + ".json"


def _references(**values):
    result = {name: [] for name in REFERENCE_KEYS}
    for name, members in values.items():
        require(name in result, "THETA_ASSESSMENT_IMPLEMENTATION_INVALID")
        result[name] = sorted(set(members))
    return result


def _criterion(identity, result, reason_code, references=None, *, event_timing=None):
    require(identity in CRITERIA and result in STATES
            and re.fullmatch(r"THETA_ASSESSMENT_[A-Z0-9_]{1,100}", reason_code),
            "THETA_ASSESSMENT_IMPLEMENTATION_INVALID")
    value = {"criterion_id": identity, "result": result,
             "reason_code": reason_code,
             "references": _references() if references is None else references}
    if identity == "C7":
        value["event_timing"] = [] if event_timing is None else event_timing
    return value


def _not_evaluable(reason):
    return [_criterion(identity, "NOT_EVALUABLE", reason) for identity in CRITERIA]


def _aggregate(criteria):
    results = [item["result"] for item in criteria]
    if "NOT_EVALUABLE" in results:
        return "NOT_EVALUABLE"
    if "LIMITED" in results:
        return "LIMITED"
    require(results == ["DOCUMENTED"] * 9, "THETA_ASSESSMENT_INTEGRITY_INVALID")
    return "DOCUMENTED"


def _populations(answer):
    research = answer["research"]
    return {
        "sources": {v["source_id"]: v for v in research["sources"]},
        "observations": {v["observation_id"]: v for v in research["chart_observations"]},
        "evidence": {v["evidence_id"]: v for v in research["evidence_items"]},
        "relations": {v["relation_id"]: v for v in research["relationships"]},
        "events": {v["event_id"]: v for v in research["scheduled_events"]},
        "assumptions": {v["identity"]: v for v in research["assumptions"]},
        "limitations": {v["identity"]: v for v in research["limitations"]},
    }


def _source_linked(ids, source_ids, evidence):
    """Every cited claim is source-backed through a cited source, and vice versa."""
    if not ids or not source_ids:
        return False
    claims = [evidence[identity] for identity in ids]
    return (all(set(claim["source_ids"]) & set(source_ids) for claim in claims)
            and all(any(source in claim["source_ids"] for claim in claims)
                    for source in source_ids))


def _typed(relation, kind, identity=None):
    return [ref["identity"] for ref in relation["references"]
            if ref["kind"] == kind and (identity is None or ref["identity"] == identity)]


def _relevant_ref(context, horizon, material):
    return any((ref["kind"] == "FORECAST" and ref["identity"] == horizon)
               or (ref["kind"] == "EVIDENCE" and ref["identity"] in material)
               for ref in context["affected_references"])


def _evaluate(answer, question, horizon):
    research, forecast = answer["research"], answer["forecasts"][horizon]
    p = _populations(answer)
    evidence, observations = p["evidence"], p["observations"]
    material = set(forecast["material_evidence_ids"])
    material_sources = set(forecast["material_source_ids"])
    applicable_relations = [r for r in p["relations"].values() if horizon in r["horizons"]]

    c1_refs = _references(evidence_ids=material, source_ids=material_sources,
                          observation_ids=[o for e in material for o in evidence[e]["observation_ids"]],
                          assumption_ids=[a for e in material for a in evidence[e]["assumption_ids"]])
    c1_ok = (question["binding"]["methodology"] == RESEARCH_DESCRIPTOR
             and all(horizon in evidence[identity]["horizons"] for identity in material)
             and _source_linked(material, material_sources, evidence))
    c1 = _criterion("C1", "DOCUMENTED" if c1_ok else "LIMITED",
                    "THETA_ASSESSMENT_C1_LINKS_DOCUMENTED" if c1_ok
                    else "THETA_ASSESSMENT_C1_MATERIAL_CONNECTION_GAP", c1_refs)

    rationale = forecast["rationale"]
    rationale_ids, rationale_sources = set(rationale["evidence_ids"]), set(rationale["source_ids"])
    section_ids = {}
    sections_ok = True
    for name in ("commodity_research", "macro_fundamental_research"):
        section = research[name]
        ids = {identity for identity in section["evidence_ids"]
               if horizon in evidence[identity]["horizons"]}
        section_ids[name] = ids
        sections_ok = sections_ok and section["availability"] == "AVAILABLE" and bool(ids)
        sections_ok = sections_ok and all(bool(evidence[i]["source_ids"]) for i in ids)
        sections_ok = sections_ok and bool(ids & rationale_ids)
    c2_ok = (bool(rationale_ids) and rationale_ids.issubset(material)
             and _source_linked(rationale_ids, rationale_sources, evidence) and sections_ok)
    c2_refs = _references(evidence_ids=rationale_ids | section_ids["commodity_research"]
                          | section_ids["macro_fundamental_research"],
                          source_ids=rationale_sources | {s for i in rationale_ids for s in evidence[i]["source_ids"]})
    c2 = _criterion("C2", "DOCUMENTED" if c2_ok else "LIMITED",
                    "THETA_ASSESSMENT_C2_RATIONALE_DOCUMENTED" if c2_ok
                    else "THETA_ASSESSMENT_C2_RATIONALE_COVERAGE_GAP", c2_refs)

    def forecast_relations(kind):
        return [relation for relation in applicable_relations
                if relation["relationship_type"] == kind
                and _typed(relation, "FORECAST", horizon) and _typed(relation, "EVIDENCE")]

    support, opposition = forecast_relations("SUPPORT"), forecast_relations("OPPOSITION")
    counter = forecast["counterevidence"]
    opposition_evidence = {identity for relation in opposition for identity in _typed(relation, "EVIDENCE")}
    counter_ids, counter_sources = set(counter["evidence_ids"]), set(counter["source_ids"])
    c3_ok = (bool(support) and bool(opposition) and bool(counter_ids)
             and bool(counter_ids & opposition_evidence)
             and _source_linked(counter_ids, counter_sources, evidence))
    c3_refs = _references(evidence_ids={i for r in support + opposition for i in _typed(r, "EVIDENCE")}
                          | counter_ids, source_ids=counter_sources,
                          relation_ids=[r["relation_id"] for r in support + opposition])
    c3 = _criterion("C3", "DOCUMENTED" if c3_ok else "LIMITED",
                    "THETA_ASSESSMENT_C3_PERSPECTIVES_DOCUMENTED" if c3_ok
                    else "THETA_ASSESSMENT_C3_PERSPECTIVE_TREATMENT_GAP", c3_refs)

    assumption_ids, limitation_ids = set(forecast["assumption_ids"]), set(forecast["limitation_ids"])
    used_assumptions = {a for identity in material for a in evidence[identity]["assumption_ids"]}
    attached_limitations = {a for relation in applicable_relations for a in relation["limitation_ids"]}
    assumptions_ok = (bool(assumption_ids) and used_assumptions.issubset(assumption_ids)
                      and all(horizon in p["assumptions"][a]["horizons"]
                              and _relevant_ref(p["assumptions"][a], horizon, material)
                              for a in assumption_ids))
    limitations_ok = (bool(limitation_ids) and attached_limitations.issubset(limitation_ids)
                      and all(horizon in p["limitations"][a]["horizons"]
                              and _relevant_ref(p["limitations"][a], horizon, material)
                              for a in limitation_ids))
    c4_ok = assumptions_ok and limitations_ok
    c4_refs = _references(evidence_ids=material, relation_ids=[r["relation_id"] for r in applicable_relations
                                                               if r["limitation_ids"]],
                          assumption_ids=assumption_ids | used_assumptions,
                          limitation_ids=limitation_ids | attached_limitations)
    c4 = _criterion("C4", "DOCUMENTED" if c4_ok else "LIMITED",
                    "THETA_ASSESSMENT_C4_DECLARATIONS_DOCUMENTED" if c4_ok
                    else "THETA_ASSESSMENT_C4_DECLARATION_TREATMENT_GAP", c4_refs)

    source_ids = set(p["sources"])
    c5 = _criterion("C5", "DOCUMENTED", "THETA_ASSESSMENT_C5_ACCEPTED_CHRONOLOGY_DOCUMENTED",
                    _references(source_ids=source_ids))

    available = [o for o in observations.values()
                 if o["availability"] == "AVAILABLE" and horizon in o["horizons"]]
    refs = {o["observation_id"] for o in available if o["role"] == "REFERENCE"}
    mcx = {o["observation_id"] for o in available if o["role"] == "MCX"}
    reconciliation = research["reconciliation"]
    recon_ids = {identity for identity in reconciliation["evidence_ids"]
                 if horizon in evidence[identity]["horizons"]}
    recon_relations = []
    for relation in applicable_relations:
        if relation["relationship_type"] != "RECONCILIATION":
            continue
        obs_ids, evidence_ids = set(_typed(relation, "OBSERVATION")), set(_typed(relation, "EVIDENCE"))
        if obs_ids & refs and obs_ids & mcx and evidence_ids & recon_ids:
            if all(evidence[i]["source_ids"] for i in evidence_ids):
                recon_relations.append(relation)
    c6_ok = (bool(refs) and bool(mcx) and reconciliation["availability"] == "AVAILABLE"
             and bool(recon_ids) and all(evidence[i]["source_ids"] for i in recon_ids)
             and bool(recon_relations))
    c6_refs = _references(evidence_ids=recon_ids, observation_ids=refs | mcx,
                          relation_ids=[r["relation_id"] for r in recon_relations],
                          source_ids={s for i in recon_ids for s in evidence[i]["source_ids"]})
    c6 = _criterion("C6", "DOCUMENTED" if c6_ok else "LIMITED",
                    "THETA_ASSESSMENT_C6_RECONCILIATION_DOCUMENTED" if c6_ok
                    else "THETA_ASSESSMENT_C6_RECONCILIATION_GAP", c6_refs)

    applicable_events = [event for event in p["events"].values() if horizon in event["horizons"]]
    statement_ids = set(forecast["rationale"]["evidence_ids"]) | set(forecast["uncertainty"]["evidence_ids"]) \
                    | set(forecast["confidence_justification"]["evidence_ids"])
    event_ok = bool(applicable_events)
    timing = []
    event_evidence, event_sources = set(), set()
    expiry = stamp(forecast["target"]["expires_at"])
    for event in applicable_events:
        ids = set(event["evidence_ids"])
        event_evidence |= ids
        if event["schedule_source_id"] is not None:
            event_sources.add(event["schedule_source_id"])
        event_ok = event_ok and event["availability"] == "AVAILABLE" and bool(ids & statement_ids)
        if event["availability"] == "AVAILABLE":
            start, end = stamp(event["scheduled_window"]["start"]), stamp(event["scheduled_window"]["end"])
            position = "BEFORE_EXPIRY" if end < expiry else "AFTER_EXPIRY" if start > expiry else "ACROSS_EXPIRY"
            timing.append({"event_id": event["event_id"], "position": position})
    timing.sort(key=lambda item: item["event_id"])
    c7_refs = _references(evidence_ids=event_evidence, source_ids=event_sources,
                          event_ids=[event["event_id"] for event in applicable_events])
    c7 = _criterion("C7", "DOCUMENTED" if event_ok else "LIMITED",
                    "THETA_ASSESSMENT_C7_EVENTS_DOCUMENTED" if event_ok
                    else "THETA_ASSESSMENT_C7_EVENT_TREATMENT_GAP", c7_refs,
                    event_timing=timing)

    explanation_ids, explanation_sources = set(), set()
    c8_ok = True
    for name in ("confidence_justification", "path_risk"):
        statement = forecast[name]
        ids, sources = set(statement["evidence_ids"]), set(statement["source_ids"])
        explanation_ids |= ids
        explanation_sources |= sources
        c8_ok = c8_ok and _source_linked(ids, sources, evidence)
    c8 = _criterion("C8", "DOCUMENTED" if c8_ok else "LIMITED",
                    "THETA_ASSESSMENT_C8_EXPLANATIONS_DOCUMENTED" if c8_ok
                    else "THETA_ASSESSMENT_C8_EXPLANATION_LINK_GAP",
                    _references(evidence_ids=explanation_ids, source_ids=explanation_sources))

    contradictions = [relation for relation in applicable_relations
                      if relation["relationship_type"] == "UNRESOLVED_CONTRADICTION"]
    c9_ok = bool(applicable_relations) and not contradictions
    c9_refs = _references(evidence_ids={i for r in contradictions for i in _typed(r, "EVIDENCE")},
                          observation_ids={i for r in contradictions for i in _typed(r, "OBSERVATION")},
                          relation_ids=[r["relation_id"] for r in applicable_relations],
                          limitation_ids={i for r in contradictions for i in r["limitation_ids"]})
    c9 = _criterion("C9", "DOCUMENTED" if c9_ok else "LIMITED",
                    "THETA_ASSESSMENT_C9_NO_DECLARED_UNRESOLVED_CONTRADICTION" if c9_ok
                    else ("THETA_ASSESSMENT_C9_DECLARED_UNRESOLVED_CONTRADICTION"
                          if contradictions else "THETA_ASSESSMENT_C9_RELATIONSHIP_RECORD_GAP"), c9_refs)
    return [c1, c2, c3, c4, c5, c6, c7, c8, c9]


class ThetaAssessmentEngine:
    """Explicit TE-05C application operation over accepted evidence only."""

    def __init__(self, intake, publication=None):
        require(type(intake) is CombinedAnswerIntake,
                "THETA_ASSESSMENT_CONFIGURATION_INVALID")
        publication = ThetaMethodologyPublication() if publication is None else publication
        require(type(publication) is ThetaMethodologyPublication,
                "THETA_ASSESSMENT_CONFIGURATION_INVALID")
        self.intake, self.store, self.publication = intake, intake.store, publication

    @staticmethod
    def _identity(receipt):
        return "TAS-" + digest(encode([SCHEMA_ID, SCHEMA_VERSION, receipt["answer_id"],
                                      receipt["acceptance_id"], ASSESSMENT_DESCRIPTOR]))

    def _load_question_answer(self, receipt_id):
        evidence = self.intake.accepted_evidence(receipt_id)
        receipt = evidence["receipt"]
        question = validate_question_v3(self.intake._get("questions", receipt["question_id"] + ".json"))
        answer = validate_answer_v3(evidence["child_raw"], question,
                                    received_at=stamp(receipt["accepted_at"]))
        require(receipt["question_sha256"] == digest(encode(question))
                and receipt["raw_child_sha256"] == digest(evidence["child_raw"])
                and receipt["canonical_child_sha256"] == digest(encode(answer))
                and receipt["binding"] == question["binding"] == answer["binding"]
                and receipt["answer_id"] == answer["answer_id"],
                "THETA_ASSESSMENT_ACCEPTED_GRAPH_INVALID")
        return evidence, receipt, question, answer

    def _resolve(self, answer_id):
        require(type(answer_id) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,99}", answer_id),
                "THETA_ASSESSMENT_ANSWER_ID_INVALID")
        claim = self.intake._get("answer-identities", _key(answer_id))
        require(set(claim) == {"receipt_id"}, "THETA_ASSESSMENT_ACCEPTED_GRAPH_INVALID")
        result = self._load_question_answer(claim["receipt_id"])
        require(result[1]["answer_id"] == answer_id, "THETA_ASSESSMENT_ACCEPTED_GRAPH_INVALID")
        return result

    def _policy(self, question):
        admitted = self.publication.assessment_policy(stamp(question["information_cutoff"]))
        require(admitted["descriptor"] == ASSESSMENT_DESCRIPTOR
                and admitted["policy"]["identity"] == ASSESSMENT_ID
                and admitted["policy"]["version"] == VERSION
                and question["binding"]["methodology"] == RESEARCH_DESCRIPTOR,
                "THETA_ASSESSMENT_POLICY_BINDING_INVALID")
        return admitted

    def _record(self, receipt, question, answer, assessed_at, *, admission_reason=None):
        identity = self._identity(receipt)
        if admission_reason is None:
            horizons = {}
            for horizon in ("E1", "E2"):
                criteria = _evaluate(answer, question, horizon)
                horizons[horizon] = {"result": _aggregate(criteria), "criteria": criteria}
            admission = "ADMITTED"
        else:
            horizons = {h: {"result": "NOT_EVALUABLE", "criteria": _not_evaluable(admission_reason)}
                        for h in ("E1", "E2")}
            admission = "NOT_EVALUABLE"
        return {
            "schema_identity": SCHEMA_ID, "schema_version": SCHEMA_VERSION,
            "assessment_id": identity, "assessed_at": assessed_at.isoformat(),
            "assessment_admission": admission, "subject": receipt["subject"],
            "accepted_answer": {
                "answer_id": receipt["answer_id"], "acceptance_receipt_id": receipt["acceptance_id"],
                "answer_package_id": receipt["answer_package_id"], "question_id": receipt["question_id"],
                "question_sha256": receipt["question_sha256"],
                "raw_package_sha256": receipt["raw_package_sha256"],
                "canonical_package_sha256": receipt["canonical_package_sha256"],
                "raw_child_sha256": receipt["raw_child_sha256"],
                "canonical_child_sha256": receipt["canonical_child_sha256"],
            },
            "information_cutoff": question["information_cutoff"],
            "binding": deepcopy(question["binding"]),
            "targets": deepcopy(question["targets"]),
            "research_methodology": deepcopy(question["binding"]["methodology"]),
            "assessment_methodology": deepcopy(ASSESSMENT_DESCRIPTOR),
            "verification_claim": VERIFICATION_CLAIM if admission == "ADMITTED" else None,
            "horizons": horizons,
        }

    def _validate_record(self, value, receipt=None, question=None):
        expected_keys = {"schema_identity", "schema_version", "assessment_id", "assessed_at",
                         "assessment_admission", "subject", "accepted_answer", "information_cutoff",
                         "binding", "targets", "research_methodology", "assessment_methodology",
                         "verification_claim", "horizons"}
        require(type(value) is dict and set(value) == expected_keys
                and value["schema_identity"] == SCHEMA_ID and value["schema_version"] == SCHEMA_VERSION
                and value["assessment_admission"] in {"ADMITTED", "NOT_EVALUABLE"}
                and value["assessment_methodology"] == ASSESSMENT_DESCRIPTOR
                and value["verification_claim"] == (VERIFICATION_CLAIM
                    if value["assessment_admission"] == "ADMITTED" else None)
                and set(value["horizons"]) == {"E1", "E2"},
                "THETA_ASSESSMENT_INTEGRITY_INVALID")
        stamp(value["assessed_at"]); stamp(value["information_cutoff"])
        accepted = value["accepted_answer"]
        require(type(accepted) is dict and set(accepted) == {
            "answer_id", "acceptance_receipt_id", "answer_package_id", "question_id", "question_sha256",
            "raw_package_sha256", "canonical_package_sha256", "raw_child_sha256", "canonical_child_sha256"},
            "THETA_ASSESSMENT_INTEGRITY_INVALID")
        expected_id = "TAS-" + digest(encode([SCHEMA_ID, SCHEMA_VERSION, accepted["answer_id"],
                                               accepted["acceptance_receipt_id"], ASSESSMENT_DESCRIPTOR]))
        require(value["assessment_id"] == expected_id, "THETA_ASSESSMENT_INTEGRITY_INVALID")
        for horizon, result in value["horizons"].items():
            require(type(result) is dict and set(result) == {"result", "criteria"}
                    and result["result"] in STATES and type(result["criteria"]) is list
                    and [item.get("criterion_id") for item in result["criteria"]] == list(CRITERIA)
                    and result["result"] == _aggregate(result["criteria"]),
                    "THETA_ASSESSMENT_INTEGRITY_INVALID")
            for item in result["criteria"]:
                required = {"criterion_id", "result", "reason_code", "references"}
                if item["criterion_id"] == "C7":
                    required.add("event_timing")
                require(set(item) == required and item["result"] in STATES
                        and re.fullmatch(r"THETA_ASSESSMENT_[A-Z0-9_]{1,100}", item["reason_code"])
                        and type(item["references"]) is dict
                        and set(item["references"]) == set(REFERENCE_KEYS)
                        and all(type(ids) is list and ids == sorted(set(ids))
                                and all(type(i) is str for i in ids)
                                for ids in item["references"].values()),
                        "THETA_ASSESSMENT_INTEGRITY_INVALID")
                if item["criterion_id"] == "C7":
                    require(type(item["event_timing"]) is list
                            and all(type(t) is dict and set(t) == {"event_id", "position"}
                                    and t["position"] in {"BEFORE_EXPIRY", "ACROSS_EXPIRY", "AFTER_EXPIRY"}
                                    for t in item["event_timing"]),
                            "THETA_ASSESSMENT_INTEGRITY_INVALID")
        require((value["assessment_admission"] == "NOT_EVALUABLE")
                == all(value["horizons"][h]["result"] == "NOT_EVALUABLE" for h in ("E1", "E2")),
                "THETA_ASSESSMENT_INTEGRITY_INVALID")
        if receipt is not None and question is not None:
            require(value["assessment_id"] == self._identity(receipt)
                    and value["subject"] == receipt["subject"]
                    and value["accepted_answer"] == self._record_lineage(receipt)
                    and value["information_cutoff"] == question["information_cutoff"]
                    and value["binding"] == question["binding"]
                    and value["targets"] == question["targets"]
                    and value["research_methodology"] == question["binding"]["methodology"],
                    "THETA_ASSESSMENT_INTEGRITY_INVALID")
        return value

    @staticmethod
    def _record_lineage(receipt):
        return {
            "answer_id": receipt["answer_id"], "acceptance_receipt_id": receipt["acceptance_id"],
            "answer_package_id": receipt["answer_package_id"], "question_id": receipt["question_id"],
            "question_sha256": receipt["question_sha256"],
            "raw_package_sha256": receipt["raw_package_sha256"],
            "canonical_package_sha256": receipt["canonical_package_sha256"],
            "raw_child_sha256": receipt["raw_child_sha256"],
            "canonical_child_sha256": receipt["canonical_child_sha256"],
        }

    def _currentness(self, receipt):
        restored = self.intake.restore_import(receipt["attempt_id"])
        row = restored["children"][receipt["subject"]]
        require(row["receipt_id"] == receipt["acceptance_id"],
                "THETA_ASSESSMENT_ACCEPTED_GRAPH_INVALID")
        return row["currentness"]

    def _projection(self, record, receipt, disposition):
        return {"assessment": deepcopy(record), "currentness": self._currentness(receipt),
                "disposition": disposition}

    def _unavailable(self, reason):
        require(re.fullmatch(r"THETA_ASSESSMENT_[A-Z0-9_]{1,100}", reason),
                "THETA_ASSESSMENT_IMPLEMENTATION_INVALID")
        criteria = _not_evaluable(reason)
        return {"assessment": None, "currentness": "UNAVAILABLE", "disposition": "NOT_EVALUABLE",
                "horizons": {h: {"result": "NOT_EVALUABLE", "criteria": deepcopy(criteria)}
                             for h in ("E1", "E2")}, "reason_code": reason}

    def assess_accepted_theta_answer(self, accepted_answer_id):
        """Assess by accepted Answer identity; caller cannot supply evidence/policy."""
        try:
            _, receipt, question, answer = self._resolve(accepted_answer_id)
            identity = self._identity(receipt)
            created = False
            with self.store.transaction():
                try:
                    existing = unseal(self.store.load("v3-assessments", identity + ".json"))
                except FileNotFoundError:
                    existing = None
                if existing is not None:
                    self._validate_record(existing, receipt, question)
                else:
                    try:
                        self._policy(question)
                    except (ThetaError, OSError, KeyError, TypeError, ValueError):
                        reason = "THETA_ASSESSMENT_POLICY_NOT_ADMITTED"
                    else:
                        reason = None
                    now = self.intake.workflow.now()
                    require(type(now) is datetime and now.tzinfo is not None and now.utcoffset() is not None
                            and now >= stamp(receipt["accepted_at"]),
                            "THETA_ASSESSMENT_TIMESTAMP_INVALID")
                    existing = self._record(receipt, question, answer, now, admission_reason=reason)
                    self._validate_record(existing, receipt, question)
                    self.store.retain("v3-assessments", identity + ".json", sealed(existing))
                    retained = unseal(self.store.load("v3-assessments", identity + ".json"))
                    self._validate_record(retained, receipt, question)
                    require(retained == existing, "THETA_ASSESSMENT_INTEGRITY_INVALID")
                    created = True
            return self._projection(existing, receipt, "CREATED" if created else "REPLAY")
        except (OSError, KeyError, TypeError, ValueError) as error:
            if isinstance(error, ThetaError) and str(error) == "THETA_IMMUTABLE_CONFLICT":
                raise
            return self._unavailable("THETA_ASSESSMENT_ACCEPTED_GRAPH_NOT_ADMITTED")

    def restore_assessment(self, assessment_id):
        """Restore exact retained results/currentness without rerunning C1-C9."""
        require(type(assessment_id) is str and re.fullmatch(r"TAS-[0-9a-f]{64}", assessment_id),
                "THETA_ASSESSMENT_IDENTITY_INVALID")
        try:
            with self.store.transaction():
                record = unseal(self.store.load("v3-assessments", assessment_id + ".json"))
                self._validate_record(record)
            receipt_id = record["accepted_answer"]["acceptance_receipt_id"]
            _, receipt, question, _ = self._load_question_answer(receipt_id)
            self._validate_record(record, receipt, question)
            return self._projection(record, receipt, "RESTORED")
        except (OSError, KeyError, TypeError, ValueError):
            raise ThetaError("THETA_ASSESSMENT_RESTORE_INVALID") from None
