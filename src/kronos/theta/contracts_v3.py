"""Sponsor-authorized TE-04A contract slice, with no intake/persistence/runtime.

Public Question authority descriptors are CONSUMED assertions, not a new TE-03
producer. This module cannot commission an owner, select a chart, accept an
Answer, assess its quality or publish Outlook. V1/V2 modules remain unchanged.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date, datetime
import re
from urllib.parse import urlsplit, parse_qsl

from kronos.theta.contracts import CANONICAL, SUBJECTS, decimal, digest, encode, stamp
from kronos.theta.json_evidence import JsonRepresentation, parse_representations
from kronos.theta.schema_v3 import (
    ANSWER, ANSWER_SCHEMA, BATCH, BATCH_SCHEMA, BATCH_VERSION, COMBINED_SCHEMA,
    COMBINED_VERSION, ID, MAX_CHILD_BYTES, MAX_COMBINED_BYTES, QUESTION,
    QUESTION_SCHEMA, RESEARCH_SECTIONS, V3, V3Error, blank, check, obj,
    schema_document, string, validate_shape,
)


def _public_identity(value):
    # These are exchange/KRONOS public identities, not provider implementation IDs.
    validate_shape(value, ID)
    check(re.search(r"(?:^|[_.:-])(?:KITE|PROVIDER|BROKER|ACCOUNT|TOKEN|SESSION|POSITION|ORDER|HOLDING)(?:$|[_.:-])",
                    value, re.IGNORECASE) is None, "PROVIDER_NEUTRAL")


def _binding(binding):
    for field in ("canonical_subject", "cycle_id"):
        _public_identity(binding[field])
    check(binding["canonical_subject"] == CANONICAL[binding["subject"]], "BINDING")
    for key, subject in (("commodity_chart", binding["subject"]), ("macro_chart", "GLOBAL_MACRO")):
        chart = binding[key]
        check(chart["subject"] == subject and chart["cycle_id"] == binding["cycle_id"], "BINDING")
        for name in ("cycle_id", "chart_id", "revision_id"):
            _public_identity(chart[name])
    for key in ("methodology", "target_authority"):
        _public_identity(binding[key]["identity"])


def validate_question_v3(question):
    validate_shape(question, QUESTION)
    check(len(encode(question)) <= MAX_CHILD_BYTES, "SIZE")
    core = {k: v for k, v in question.items() if k != "question_id"}
    check(question["question_id"] == "TEQ-" + digest(encode(core)), "BINDING")
    _binding(question["binding"])
    check(question["created_at"] == question["information_cutoff"], "BINDING")
    t0 = stamp(question["information_cutoff"])
    check(t0 <= stamp(question["authority_valid_through"]), "CHRONOLOGY")
    for horizon, target in question["targets"].items():
        check(target["subject"] == question["binding"]["subject"]
              and target["canonical_subject"] == question["binding"]["canonical_subject"]
              and target["horizon"] == horizon, "BINDING")
        check(stamp(target["expires_at"]).date() == date.fromisoformat(target["option_expiry"])
              and date.fromisoformat(target["futures_expiry"]) >= date.fromisoformat(target["option_expiry"])
              and t0 < stamp(target["expires_at"]), "CHRONOLOGY")
        for key in ("underlying_future", "settlement_reference", "authority_reference", "exchange_evidence_reference"):
            _public_identity(target[key])
    check(stamp(question["targets"]["E1"]["expires_at"]) < stamp(question["targets"]["E2"]["expires_at"]), "BINDING")
    if not question["synthetic"]:
        # TE-05B genuine admission exposed the required boolean field's name
        # matching this marker itself. Exclude only that schema field; retain
        # the existing synthetic-evidence prohibition everywhere else.
        check("SYNTHETIC" not in encode({k: v for k, v in question.items()
                                       if k != "synthetic"}).decode().upper(), "BINDING")
    return deepcopy(question)


def make_question_v3(*, binding, targets, created_at, authority_valid_through,
                     methodology_instructions, synthetic=False):
    """Pure contract construction from explicitly supplied public owner inputs.

    No conversion of historical Questions; structural validity cannot establish
    commissioned authority or genuine forecasting permission.
    """
    core = {"schema_identity": QUESTION_SCHEMA, "schema_version": V3,
            "binding": deepcopy(binding), "targets": deepcopy(targets),
            "created_at": created_at, "information_cutoff": created_at,
            "authority_valid_through": authority_valid_through,
            "methodology_instructions": methodology_instructions, "synthetic": synthetic}
    return validate_question_v3({**core, "question_id": "TEQ-" + digest(encode(core))})


def make_question_batch_v3(questions):
    check(type(questions) is dict and set(questions) == set(SUBJECTS), "BINDING")
    retained = {s: validate_question_v3(questions[s]) for s in SUBJECTS}
    first = retained[SUBJECTS[0]]
    core = {"schema_identity": BATCH_SCHEMA, "schema_version": BATCH_VERSION,
            "cycle_id": first["binding"]["cycle_id"], "subjects": list(SUBJECTS),
            "questions": {s: {"question_id": q["question_id"], "question_sha256": digest(encode(q))}
                          for s, q in retained.items()},
            "macro_chart": first["binding"]["macro_chart"],
            "synthetic": first["synthetic"], "complete": True}
    batch = {**core, "batch_id": "TEB-" + digest(encode(core))}
    validate_question_batch_v3(batch, retained)
    return batch


def validate_question_batch_v3(batch, questions):
    validate_shape(batch, BATCH)
    core = {k: v for k, v in batch.items() if k != "batch_id"}
    check(batch["batch_id"] == "TEB-" + digest(encode(core)), "BINDING")
    check(type(questions) is dict and set(questions) == set(SUBJECTS), "BINDING")
    for subject in SUBJECTS:
        q = validate_question_v3(questions[subject])
        check(q["binding"]["subject"] == subject and q["binding"]["cycle_id"] == batch["cycle_id"]
              and q["binding"]["macro_chart"] == batch["macro_chart"]
              and q["synthetic"] == batch["synthetic"]
              and batch["questions"][subject] == {"question_id": q["question_id"],
                                                    "question_sha256": digest(encode(q))}, "BINDING")
    return deepcopy(batch)


def answer_schema_v3(question):
    q = validate_question_v3(question)
    definition = deepcopy(ANSWER)
    p = definition["properties"]
    for key, value in (("question_id", q["question_id"]), ("question_sha256", digest(encode(q))),
                       ("binding", q["binding"]), ("information_cutoff", q["information_cutoff"])):
        p[key] = {"const": deepcopy(value)}
    for horizon in ("E1", "E2"):
        p["forecasts"]["properties"][horizon]["properties"]["target"] = {"const": deepcopy(q["targets"][horizon])}
    return schema_document(definition)


def _envelope(batch, children):
    return obj({"schema_identity": string(64, const=COMBINED_SCHEMA),
                "schema_version": string(16, const=COMBINED_VERSION),
                "answer_package_id": ID, "cycle_id": {"const": batch["cycle_id"]},
                "question_batch_id": {"const": batch["batch_id"]},
                "question_batch_sha256": {"const": digest(encode(batch))},
                "answers": obj(children)})


def combined_answer_schema(batch, questions):
    validate_question_batch_v3(batch, questions)
    return schema_document(_envelope(batch, {s: answer_schema_v3(questions[s]) for s in SUBJECTS}))


def combined_answer_template(batch, questions):
    return blank(combined_answer_schema(batch, questions))


def _refs(values, population, horizon=None):
    check(all(v in population for v in values), "REFERENCE")
    if horizon is not None:
        check(all("horizons" not in population[v] or horizon in population[v]["horizons"] for v in values), "REFERENCE")


def _typed_refs(values, graph, horizons):
    for ref in values:
        population = graph[ref["kind"]]
        _refs([ref["identity"]], population)
        if ref["kind"] != "FORECAST":
            check(set(horizons).issubset(population[ref["identity"]]["horizons"]), "REFERENCE")
        else:
            check(ref["identity"] in horizons, "REFERENCE")


def _source_url(value):
    if value is None:
        return
    try:
        parts = urlsplit(value)
        hostname = parts.hostname
    except ValueError:
        raise V3Error("THETA_V3_PROVIDER_NEUTRAL") from None
    check(parts.scheme in {"http", "https"} and bool(hostname)
          and parts.username is None and parts.password is None, "PROVIDER_NEUTRAL")
    import ipaddress
    check(hostname.lower() != "localhost", "PROVIDER_NEUTRAL")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    check(address is None or address.is_global, "PROVIDER_NEUTRAL")
    check(not any(k.lower() in {"api_key", "api_secret", "access_token", "request_token", "session_token"}
                  for k, _ in parse_qsl(parts.query)), "PROVIDER_NEUTRAL")


def _graph(answer, question):
    research = answer["research"]
    categories = (("sources", "source_id"), ("chart_observations", "observation_id"),
                  ("evidence_items", "evidence_id"), ("relationships", "relation_id"),
                  ("scheduled_events", "event_id"), ("assumptions", "identity"), ("limitations", "identity"))
    seen = set()
    populations = {}
    for name, field in categories:
        values = {}
        for member in research[name]:
            identity = member[field]
            check(identity not in seen and identity not in {"E1", "E2"}, "DUPLICATE_IDENTITY")
            seen.add(identity)
            values[identity] = member
        populations[name] = values
    sources, observations, evidence, assumptions, limitations = (populations[k] for k in
        ("sources", "chart_observations", "evidence_items", "assumptions", "limitations"))
    graph = {"EVIDENCE": evidence, "OBSERVATION": observations, "FORECAST": answer["forecasts"]}
    cutoff = stamp(question["information_cutoff"])
    analyzed = stamp(answer["analyzed_at"])
    for source in sources.values():
        check(source["url"] is not None or source["reference"] is not None, "REFERENCE")
        _source_url(source["url"])
        if source["reference"] is not None:
            _public_identity(source["reference"])
        if source["archive_version_locator"] is not None:
            locator = source["archive_version_locator"]
            if "://" in locator:
                _source_url(locator)
            else:
                _public_identity(locator)
        check(stamp(source["available_at"]) <= cutoff
              and stamp(source["available_at"]) <= stamp(source["accessed_at"]) <= analyzed
              and (source["published_at"] is None or stamp(source["published_at"]) <= cutoff), "CHRONOLOGY")
        lineage = source["lineage"]
        check((lineage["status"] == "UNKNOWN" and lineage["original_information_id"] is None
               and not lineage["derivative_source_ids"])
              or (lineage["status"] == "KNOWN" and lineage["original_information_id"] is not None), "LINEAGE")
        _refs(lineage["derivative_source_ids"], sources)
        if lineage["original_information_id"] is not None:
            _public_identity(lineage["original_information_id"])
        _refs(source["linked_evidence_ids"], evidence)
    visited = set()

    def lineage_visit(identity, active):
        check(identity not in active, "LINEAGE")
        if identity not in visited:
            for parent in sources[identity]["lineage"]["derivative_source_ids"]:
                lineage_visit(parent, {*active, identity})
            visited.add(identity)
    for identity in sources:
        lineage_visit(identity, set())
    for observation in observations.values():
        role = observation["role"]
        expected = question["binding"]["macro_chart" if role == "MACRO" else "commodity_chart"]
        check(observation["chart_reference"] == expected, "BINDING")
        available = observation["availability"] == "AVAILABLE"
        check((available and observation["observation_text"] is not None
               and observation["classification"] is not None and observation["displayed_instrument"] is not None
               and observation["timeframe"] is not None and observation["unavailable_reason"] is None)
              or (not available and observation["observation_text"] is None
                  and observation["classification"] is None and observation["unavailable_reason"] is not None
                  ), "AVAILABILITY")
        check(observation["visible_as_of"] is None or stamp(observation["visible_as_of"]) <= cutoff, "CHRONOLOGY")
    for claim in evidence.values():
        check(bool(claim["source_ids"] or claim["observation_ids"]), "REFERENCE")
        _refs(claim["source_ids"], sources)
        _refs(claim["observation_ids"], observations)
        _refs(claim["assumption_ids"], assumptions)
        for ref in (*claim["observation_ids"], *claim["assumption_ids"]):
            member = observations.get(ref, assumptions.get(ref))
            check(set(claim["horizons"]).issubset(member["horizons"]), "REFERENCE")
    for source in sources.values():
        expected = {e["evidence_id"] for e in evidence.values() if source["source_id"] in e["source_ids"]}
        check(set(source["linked_evidence_ids"]) == expected, "REFERENCE")
    for name in RESEARCH_SECTIONS:
        _refs(research[name]["evidence_ids"], evidence)
    for relation in populations["relationships"].values():
        _typed_refs(relation["references"], graph, relation["horizons"])
        _refs(relation["limitation_ids"], limitations)
        if relation["relationship_type"] == "UNRESOLVED_CONTRADICTION":
            check(relation["unresolved_limitation"] is not None, "AVAILABILITY")
    for name in ("assumptions", "limitations"):
        for context in populations[name].values():
            _refs(context["supporting_evidence_ids"], evidence)
            _typed_refs(context["affected_references"], graph, context["horizons"])
    for event in populations["scheduled_events"].values():
        _refs(event["evidence_ids"], evidence)
        if event["availability"] == "AVAILABLE":
            check(event["scheduled_window"] is not None and event["schedule_source_id"] in sources
                  and event["schedule_known_at"] is not None and event["possible_impact"] is not None, "AVAILABILITY")
            check(stamp(sources[event["schedule_source_id"]]["available_at"])
                  <= stamp(event["schedule_known_at"]) <= cutoff, "CHRONOLOGY")
            check(stamp(event["scheduled_window"]["start"]) <= stamp(event["scheduled_window"]["end"]), "CHRONOLOGY")
        else:
            check(all(event[k] is None for k in
                      ("scheduled_window", "schedule_source_id", "schedule_known_at", "possible_impact")), "AVAILABILITY")
    for horizon, forecast in answer["forecasts"].items():
        _refs(forecast["material_evidence_ids"], evidence, horizon)
        _refs(forecast["material_source_ids"], sources)
        _refs(forecast["assumption_ids"], assumptions, horizon)
        _refs(forecast["limitation_ids"], limitations, horizon)
        for key in ("rationale", "counterevidence", "uncertainty", "path_risk", "confidence_justification"):
            _refs(forecast[key]["evidence_ids"], evidence, horizon)
            _refs(forecast[key]["source_ids"], sources)


def _validate_child(value, question, received_at, *, raw_size):
    check(raw_size <= MAX_CHILD_BYTES, "SIZE")
    # Binding is checked separately so wrong hashes/targets have typed failures.
    validate_shape(value, ANSWER)
    check(value["question_id"] == question["question_id"]
          and value["question_sha256"] == digest(encode(question))
          and value["binding"] == question["binding"]
          and value["information_cutoff"] == question["information_cutoff"], "BINDING")
    analyzed = stamp(value["analyzed_at"])
    check(stamp(question["created_at"]) <= analyzed <= received_at
          and received_at <= stamp(question["authority_valid_through"]), "CHRONOLOGY")
    for horizon, forecast in value["forecasts"].items():
        check(forecast["target"] == question["targets"][horizon], "BINDING")
        check(analyzed < stamp(forecast["target"]["expires_at"])
              and received_at < stamp(forecast["target"]["expires_at"]), "CHRONOLOGY")
        check(decimal(forecast["lower"]) < decimal(forecast["upper"])
              and decimal("0") <= decimal(forecast["confidence_pct"]) <= decimal("100"), "RANGE")
    _graph(value, question)
    return deepcopy(value)


def validate_answer_v3(payload, question, *, received_at):
    q = validate_question_v3(question)
    check(type(received_at) is datetime and received_at.utcoffset() is not None, "CHRONOLOGY")
    value, _ = parse_representations(payload, maximum=MAX_CHILD_BYTES)
    return _validate_child(value, q, received_at, raw_size=len(payload))


@dataclass(frozen=True, slots=True)
class ChildValidation:
    subject: str
    answer: dict | None
    failure_code: str | None
    representation: JsonRepresentation


@dataclass(frozen=True, slots=True)
class CombinedValidation:
    answer_package_id: str
    raw_sha256: str
    canonical_sha256: str
    children: tuple[ChildValidation, ...]

    @property
    def complete(self):
        return all(child.failure_code is None for child in self.children)


def validate_combined_answer(payload, *, batch, questions, received_at):
    validate_question_batch_v3(batch, questions)
    check(type(received_at) is datetime and received_at.utcoffset() is not None, "CHRONOLOGY")
    value, spans = parse_representations(payload, maximum=MAX_COMBINED_BYTES)
    # Wrapper failures are global; child structural/semantic failures are local.
    validate_shape(value, _envelope(batch, {s: {} for s in SUBJECTS}))
    children = []
    for subject in SUBJECTS:
        representation = spans[subject]
        try:
            answer = _validate_child(value["answers"][subject], questions[subject], received_at,
                                     raw_size=len(representation.raw_bytes))
            children.append(ChildValidation(subject, answer, None, representation))
        except V3Error as error:
            children.append(ChildValidation(subject, None, str(error), representation))
    ids = Counter(child.answer["answer_id"] for child in children if child.answer is not None)
    children = tuple(replace(c, answer=None, failure_code="THETA_V3_IDENTITY_CONFLICT")
                     if c.answer is not None and ids[c.answer["answer_id"]] > 1 else c for c in children)
    return CombinedValidation(value["answer_package_id"], digest(payload), digest(encode(value)), children)


def replay_disposition(*, original_identity, original_raw_sha256, candidate_identity, candidate_raw_sha256):
    """Pure comparison only; no acceptance/selection side effect in TE-04A."""
    from kronos.theta.schema_v3 import HASH
    for identity in (original_identity, candidate_identity):
        validate_shape(identity, ID)
    for sha in (original_raw_sha256, candidate_raw_sha256):
        validate_shape(sha, HASH)
    if original_identity != candidate_identity:
        return "NEW_IDENTITY"
    check(original_raw_sha256 == candidate_raw_sha256, "IDENTITY_CONFLICT")
    return "IDENTICAL_REPLAY"
