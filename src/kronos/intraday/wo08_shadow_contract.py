"""WO08 Option A research-only contracts; approved Slice 02A R1 / ADR-0059.

Schemas preserve the reviewed payload shapes. No operational decision may
consume these identities. Provider revision/finality is never inferred.
"""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import math
import re

SCHEMA_JSON = '{"T0":{"$id":"urn:kronos:wo08:wo08_shadow_t0_sample:1.0.0","$schema":"https://json-schema.org/draft/2020-12/schema","additionalProperties":false,"description":"PROPOSED RESEARCH-ONLY contract; not commissioned. Integrity covers canonical payload excluding integrity_sha256. Cross-record lineage and temporal conditions require owning validators.","properties":{"analysis_boundary":{"format":"date-time","type":"string"},"analysis_operation_id":{"type":"string"},"authority":{"const":"RESEARCH_ONLY"},"binding_id":{"type":["string","null"]},"calendar_id":{"type":"string"},"calendar_version":{"type":"string"},"candle_refs":{"items":{"additionalProperties":false,"properties":{"candle_id":{"type":"string"},"completion":{"const":"COMPLETE"},"end":{"format":"date-time","type":"string"},"exchange_event_at":{"type":["string","null"]},"integrity":{"type":"string"},"kronos_acquired_at":{"type":["string","null"]},"kronos_published_at":{"type":["string","null"]},"oi":{"type":["number","null"]},"provider_observed_at":{"type":["string","null"]},"source_identity":{"type":"string"},"source_revision_id":{"type":["string","null"]},"start":{"format":"date-time","type":"string"},"timeframe":{"enum":["1D","1H","15M","5M"]}},"required":["timeframe","candle_id","integrity","start","end","completion","source_identity"],"type":"object"},"type":"array"},"candle_supplement_identity":{"type":["string","null"]},"candle_supplement_sha256":{"pattern":"^[0-9a-f]{64}$","type":["string","null"]},"completed_selection_id":{"type":"string"},"direction":{"enum":["LONG","SHORT","NON_DIRECTIONAL","CONFLICTING","UNKNOWN"]},"discovery_id":{"type":"string"},"exact_contract_id":{"type":["string","null"]},"exclusion_reasons":{"items":{"type":"string"},"type":"array"},"instrument_family":{"type":"string"},"integrity_sha256":{"pattern":"^[0-9a-f]{64}$","type":"string"},"machine_fact_ids":{"items":{"type":"string"},"type":"array"},"mapping_id":{"type":"string"},"market_family":{"enum":["NSE_EQUITY","NSE_INDEX","MCX_METALS","MCX_ENERGY"]},"mcx_binding_class":{"enum":["NOT_MCX","MCX_BINDING_VALID","MCX_BINDING_INVALID","MCX_BINDING_UNAVAILABLE"]},"native_decision_id":{"type":["string","null"]},"native_state":{"type":"string"},"operational_authority":{"const":false},"phase":{"enum":["OPENING","STRUCTURE","FIRST_CURRENT_SESSION_1H","CURRENT_SESSION_ESTABLISHED"]},"probables_member_id":{"type":"string"},"probables_run_id":{"type":"string"},"probables_state":{"enum":["LONG_PROBABLE","SHORT_PROBABLE","NOT_ADMITTED","UNAVAILABLE"]},"quality":{"enum":["COMPLETE","PARTIAL","INVALID","UNAVAILABLE"]},"research_published_at":{"format":"date-time","type":"string"},"run_id":{"type":"string"},"sample_id":{"type":"string"},"schema_identity":{"type":"string"},"schema_version":{"const":"1.0.0"},"session_id":{"type":"string"},"source_artifact_refs":{"items":{"additionalProperties":false,"properties":{"identity":{"type":"string"},"integrity_sha256":{"pattern":"^[0-9a-f]{64}$","type":"string"},"kind":{"type":"string"}},"required":["kind","identity","integrity_sha256"],"type":"object"},"type":"array"},"source_revision_status":{"enum":["VERIFIED","SOURCE_REVISION_PROVENANCE_UNAVAILABLE"]},"subject":{"type":"string"},"trading_authority":{"const":false}},"required":["schema_identity","schema_version","authority","operational_authority","trading_authority","integrity_sha256","sample_id","run_id","analysis_operation_id","analysis_boundary","research_published_at","subject","market_family","instrument_family","direction","probables_state","discovery_id","probables_run_id","probables_member_id","mapping_id","phase","session_id","calendar_id","calendar_version","completed_selection_id","native_decision_id","native_state","mcx_binding_class","exact_contract_id","binding_id","machine_fact_ids","candle_refs","source_revision_status","quality","exclusion_reasons","source_artifact_refs","candle_supplement_identity","candle_supplement_sha256"],"title":"WO08_SHADOW_T0_SAMPLE","type":"object"},"RUN":{"$id":"urn:kronos:wo08:wo08_shadow_run_manifest:1.0.0","$schema":"https://json-schema.org/draft/2020-12/schema","additionalProperties":false,"description":"PROPOSED RESEARCH-ONLY contract; not commissioned. Integrity covers canonical payload excluding integrity_sha256. Cross-record lineage and temporal conditions require owning validators.","properties":{"all_result_ids":{"items":{"type":"string"},"type":"array"},"analysis_boundary":{"format":"date-time","type":"string"},"analysis_operation_id":{"type":"string"},"authority":{"const":"RESEARCH_ONLY"},"capture_failures":{"items":{"type":"string"},"type":"array"},"excluded_result_reasons":{"additionalProperties":{"type":"string"},"type":"object"},"inclusion_probabilities":{"additionalProperties":{"exclusiveMinimum":0,"maximum":1,"type":"number"},"type":"object"},"integrity_sha256":{"pattern":"^[0-9a-f]{64}$","type":"string"},"manifest_id":{"type":"string"},"operational_authority":{"const":false},"population_total":{"minimum":0,"type":"integer"},"probables_run_id":{"type":"string"},"recorded_at":{"format":"date-time","type":"string"},"run_integrity":{"type":"string"},"sampling_policy_id":{"type":"string"},"sampling_seed":{"type":"string"},"schema_identity":{"type":"string"},"schema_version":{"const":"1.0.0"},"selected_sample_ids":{"items":{"type":"string"},"type":"array"},"trading_authority":{"const":false},"universe_identity":{"type":"string"}},"required":["schema_identity","schema_version","authority","operational_authority","trading_authority","integrity_sha256","manifest_id","analysis_operation_id","probables_run_id","analysis_boundary","run_integrity","universe_identity","population_total","all_result_ids","selected_sample_ids","excluded_result_reasons","sampling_policy_id","sampling_seed","inclusion_probabilities","capture_failures","recorded_at"],"title":"WO08_SHADOW_RUN_MANIFEST","type":"object"},"LINK":{"$id":"urn:kronos:wo08:wo08_shadow_sample_link:1.0.0","$schema":"https://json-schema.org/draft/2020-12/schema","additionalProperties":false,"description":"PROPOSED RESEARCH-ONLY contract; not commissioned. Integrity covers canonical payload excluding integrity_sha256. Cross-record lineage and temporal conditions require owning validators.","properties":{"authority":{"const":"RESEARCH_ONLY"},"cluster_key_subject_session":{"type":"string"},"integrity_sha256":{"pattern":"^[0-9a-f]{64}$","type":"string"},"link_created_at":{"format":"date-time","type":"string"},"link_id":{"type":"string"},"operational_authority":{"const":false},"outcome_ids":{"items":{"type":"string"},"type":"array"},"previous_sample_id":{"type":["string","null"]},"relationship":{"enum":["ORIGINAL","REASSESSMENT","IDEMPOTENT_DUPLICATE"]},"sample_id":{"type":"string"},"schema_identity":{"type":"string"},"schema_version":{"const":"1.0.0"},"t0_integrity":{"type":"string"},"trading_authority":{"const":false},"visual_reconciliation_ids":{"items":{"type":"string"},"type":"array"}},"required":["schema_identity","schema_version","authority","operational_authority","trading_authority","integrity_sha256","link_id","sample_id","t0_integrity","outcome_ids","visual_reconciliation_ids","previous_sample_id","cluster_key_subject_session","relationship","link_created_at"],"title":"WO08_SHADOW_SAMPLE_LINK","type":"object"},"OUTCOME":{"$id":"urn:kronos:wo08:wo08_shadow_forward_outcome:1.0.0","$schema":"https://json-schema.org/draft/2020-12/schema","additionalProperties":false,"description":"PROPOSED RESEARCH-ONLY contract; not commissioned. Integrity covers canonical payload excluding integrity_sha256. Cross-record lineage and temporal conditions require owning validators.","properties":{"authority":{"const":"RESEARCH_ONLY"},"captured_at":{"format":"date-time","type":"string"},"continuation_persistence":{"type":["number","null"]},"directional_return":{"type":["number","null"]},"exact_contract_id":{"type":["string","null"]},"first_adverse_at":{"type":["string","null"]},"first_favorable_at":{"type":["string","null"]},"horizon":{"enum":["NEXT_COMPLETED_5M","NEXT_15M","NEXT_30M","NEXT_60M","SESSION_REMAINDER"]},"integrity_sha256":{"pattern":"^[0-9a-f]{64}$","type":"string"},"mae":{"type":["number","null"]},"mfe":{"type":["number","null"]},"operational_authority":{"const":false},"ordered_5m_candle_ids":{"items":{"type":"string"},"type":"array"},"ordered_integrities":{"items":{"type":"string"},"type":"array"},"outcome_candle_supplement_identity":{"type":["string","null"]},"outcome_candle_supplement_sha256":{"pattern":"^[0-9a-f]{64}$","type":["string","null"]},"outcome_id":{"type":"string"},"quality":{"enum":["COMPLETE","PARTIAL","INVALID","UNAVAILABLE"]},"reason":{"type":["string","null"]},"sample_id":{"type":"string"},"schema_identity":{"type":"string"},"schema_version":{"const":"1.0.0"},"session_id":{"type":"string"},"source_acquisition_id":{"type":["string","null"]},"source_artifact_refs":{"items":{"additionalProperties":false,"properties":{"identity":{"type":"string"},"integrity_sha256":{"pattern":"^[0-9a-f]{64}$","type":"string"},"kind":{"type":"string"}},"required":["kind","identity","integrity_sha256"],"type":"object"},"type":"array"},"source_publication_id":{"type":["string","null"]},"source_revision_status":{"type":"string"},"state":{"enum":["COMPLETE_SAME_CONTRACT","PARTIAL_SESSION_END","PARTIAL_ROLL_BOUNDARY","PARTIAL_GAP","INVALID_FOR_NATIVE_OUTCOME","UNAVAILABLE"]},"structural_failure":{"type":["boolean","null"]},"subject":{"type":"string"},"t0_boundary":{"format":"date-time","type":"string"},"trading_authority":{"const":false}},"required":["schema_identity","schema_version","authority","operational_authority","trading_authority","integrity_sha256","outcome_id","sample_id","horizon","state","subject","session_id","exact_contract_id","t0_boundary","captured_at","source_acquisition_id","source_publication_id","source_revision_status","ordered_5m_candle_ids","ordered_integrities","directional_return","mfe","mae","first_favorable_at","first_adverse_at","continuation_persistence","structural_failure","reason","quality","source_artifact_refs","outcome_candle_supplement_identity","outcome_candle_supplement_sha256"],"title":"WO08_SHADOW_FORWARD_OUTCOME","type":"object"}}'
SCHEMAS = json.loads(SCHEMA_JSON)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return sha256(canonical(value)).hexdigest()


def moment(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise ValueError("WO08_TIMESTAMP_INVALID") from None


def _schema(value, rule):
    # Complete subset used by the four reviewed schemas, without a new dependency.
    types = rule.get("type", [])
    types = [types] if isinstance(types, str) else types
    match = {"object": type(value) is dict, "array": type(value) is list,
             "string": type(value) is str, "null": value is None,
             "integer": type(value) is int,
             "number": type(value) in (int, float) and math.isfinite(value),
             "boolean": type(value) is bool}
    if types and not any(match[t] for t in types):
        raise ValueError("WO08_SCHEMA_TYPE_INVALID")
    if "const" in rule and (type(value) is not type(rule["const"]) or value != rule["const"]):
        raise ValueError("WO08_AUTHORITY_INVALID")
    if "enum" in rule and value not in rule["enum"]:
        raise ValueError("WO08_SCHEMA_VALUE_INVALID")
    if type(value) is dict:
        if not set(rule.get("required", [])) <= set(value):
            raise ValueError("WO08_SCHEMA_FIELDS_INVALID")
        props = rule.get("properties", {})
        extra = rule.get("additionalProperties", True)
        if extra is False and set(value) - set(props):
            raise ValueError("WO08_SCHEMA_FIELDS_INVALID")
        for k, v in value.items():
            if type(k) is not str:
                raise ValueError("WO08_SCHEMA_FIELDS_INVALID")
            if k in props:
                _schema(v, props[k])
            elif type(extra) is dict:
                _schema(v, extra)
    if type(value) is list and "items" in rule:
        for v in value:
            _schema(v, rule["items"])
    if type(value) is str:
        if not value or value != value.strip():
            raise ValueError("WO08_SCHEMA_VALUE_INVALID")
        if "pattern" in rule and re.fullmatch(rule["pattern"], value) is None:
            raise ValueError("WO08_SCHEMA_VALUE_INVALID")
        if rule.get("format") == "date-time":
            moment(value)
    if type(value) in (int, float):
        for name, valid in (("minimum", lambda n: value >= n),
                            ("exclusiveMinimum", lambda n: value > n),
                            ("maximum", lambda n: value <= n)):
            if name in rule and not valid(rule[name]):
                raise ValueError("WO08_SCHEMA_VALUE_INVALID")


def validate(kind, data):
    if kind not in SCHEMAS:
        raise ValueError("WO08_RECORD_KIND_INVALID")
    _schema(data, SCHEMAS[kind])
    if data["schema_identity"] != SCHEMAS[kind]["title"]:
        raise ValueError("WO08_SCHEMA_IDENTITY_INVALID")
    core = {k: v for k, v in data.items() if k != "integrity_sha256"}
    if data["integrity_sha256"] != digest(core):
        raise ValueError("WO08_INTEGRITY_INVALID")
    if kind == "T0":
        boundary = moment(data["analysis_boundary"])
        if data['direction'] in {'CONFLICTING', 'UNKNOWN', 'NON_DIRECTIONAL'} and data['native_state'] == 'PULLBACK':
            raise ValueError('WO08_NEGATIVE_EVIDENCE_PROMOTION')
        if moment(data["research_published_at"]) < boundary:
            raise ValueError("WO08_PUBLICATION_BEFORE_BOUNDARY")
        for c in data["candle_refs"]:
            if (moment(c["start"]) >= moment(c["end"]) or moment(c["end"]) > boundary
                    or c["completion"] != "COMPLETE"):
                raise ValueError("WO08_T0_LOOKAHEAD")
        mcx = data["market_family"].startswith("MCX_")
        if (mcx != data["subject"].startswith("MCX-")
                or mcx == (data["mcx_binding_class"] == "NOT_MCX")):
            raise ValueError("WO08_MCX_CLASS_INVALID")
        if data["mcx_binding_class"] == "MCX_BINDING_VALID":
            if not data["binding_id"] or not data["exact_contract_id"]:
                raise ValueError("WO08_MCX_BINDING_REQUIRED")
        elif mcx and (data["quality"] == "COMPLETE" or data['native_state']=='PULLBACK'):
            raise ValueError("WO08_MCX_NEGATIVE_ONLY")
        if data['quality'] == 'COMPLETE' and (not data['candle_refs'] or not data['source_artifact_refs']):
            raise ValueError('WO08_COMPLETE_EVIDENCE_REQUIRED')
        if not mcx and any(data[k] is not None for k in ("binding_id", "exact_contract_id")):
            raise ValueError("WO08_MCX_CLASS_INVALID")
        if data["source_revision_status"] != "SOURCE_REVISION_PROVENANCE_UNAVAILABLE":
            if not data["candle_refs"] or any(not c.get("source_revision_id") for c in data["candle_refs"]):
                raise ValueError("WO08_REVISION_PROVENANCE_UNAVAILABLE")
    elif kind == "RUN":
        ids = data["all_result_ids"]
        chosen = data["selected_sample_ids"]
        if (data["population_total"] != 98 or len(ids) != 98 or len(set(ids)) != 98
                or len(set(chosen)) != len(chosen)
                or set(data["excluded_result_reasons"]) - set(ids)
                or set(data["inclusion_probabilities"]) != set(ids)):
            raise ValueError("WO08_POPULATION_INVALID")
        if moment(data["recorded_at"]) < moment(data["analysis_boundary"]):
            raise ValueError("WO08_PUBLICATION_BEFORE_BOUNDARY")
    elif kind == "LINK":
        if (data['relationship'] == 'ORIGINAL') != (data['previous_sample_id'] is None):
            raise ValueError('WO08_LINK_LINEAGE_INVALID')
    elif kind == "OUTCOME":
        if data["source_revision_status"] != "SOURCE_REVISION_PROVENANCE_UNAVAILABLE":
            raise ValueError("WO08_REVISION_PROVENANCE_UNAVAILABLE")
        if moment(data["captured_at"]) <= moment(data["t0_boundary"]):
            raise ValueError("WO08_OUTCOME_NOT_LATER")
        if len(data["ordered_5m_candle_ids"]) != len(data["ordered_integrities"]):
            raise ValueError("WO08_OUTCOME_LINEAGE_INVALID")
        if data["state"] == "COMPLETE_SAME_CONTRACT" and (
                data["quality"] != "COMPLETE" or not data["ordered_5m_candle_ids"]
                or not data["outcome_candle_supplement_sha256"]):
            raise ValueError("WO08_OUTCOME_EVIDENCE_REQUIRED")
        if data["state"] != "COMPLETE_SAME_CONTRACT" and any(data[k] is not None for k in (
                "directional_return", "mfe", "mae", "first_favorable_at", "first_adverse_at",
                "continuation_persistence", "structural_failure")):
            raise ValueError("WO08_PARTIAL_OUTCOME_METRICS_INVALID")


@dataclass(frozen=True, slots=True)
class ResearchRecord:
    kind: str
    payload: bytes

    def __post_init__(self):
        if type(self.payload) is not bytes:
            raise ValueError("WO08_RECORD_NOT_FROZEN")
        value = json.loads(self.payload)
        validate(self.kind, value)
        if canonical(value) != self.payload:
            raise ValueError("WO08_RECORD_NOT_CANONICAL")

    @property
    def data(self):
        return json.loads(self.payload)

    @property
    def identity(self):
        key = {"T0": "sample_id", "RUN": "manifest_id", "LINK": "link_id", "OUTCOME": "outcome_id"}[self.kind]
        return self.data[key]


def record(kind, **values):
    fixed = dict(schema_identity=SCHEMAS[kind]['title'], schema_version='1.0.0',
                 authority='RESEARCH_ONLY', operational_authority=False, trading_authority=False)
    if any(k in values and (type(values[k]) is not type(v) or values[k] != v) for k,v in fixed.items()):
        raise ValueError('WO08_AUTHORITY_INVALID')
    values.update(schema_identity=SCHEMAS[kind]["title"], schema_version="1.0.0",
                  authority="RESEARCH_ONLY", operational_authority=False, trading_authority=False)
    values["integrity_sha256"] = digest(values)
    return ResearchRecord(kind, canonical(values))


@dataclass(frozen=True, slots=True)
class Wo08ShadowHandoff:
    manifest: ResearchRecord
    samples: tuple[ResearchRecord, ...]
    supplements: tuple[bytes, ...]
    newly_published: bool

    def __post_init__(self):
        if (type(self.manifest) is not ResearchRecord or self.manifest.kind != "RUN"
                or type(self.samples) is not tuple or type(self.supplements) is not tuple
                or type(self.newly_published) is not bool or len(self.samples) > 98
                or len(self.supplements) != len(self.samples)):
            raise ValueError("WO08_HANDOFF_INVALID")
        self.manifest.__post_init__()
        m = self.manifest.data
        if [s.identity for s in self.samples] != m["selected_sample_ids"]:
            raise ValueError("WO08_HANDOFF_LINEAGE_INVALID")
        result_ids = []
        for sample, supplement in zip(self.samples, self.supplements):
            if type(sample) is not ResearchRecord or sample.kind != "T0" or type(supplement) is not bytes:
                raise ValueError("WO08_HANDOFF_NOT_FROZEN")
            sample.__post_init__()
            s = sample.data
            validate_t0_supplement(sample, supplement)
            rr = json.loads(supplement)['run_reference']
            if rr['integrity'] != m['run_integrity'] or rr['universe'] != m['universe_identity']:
                raise ValueError('WO08_HANDOFF_LINEAGE_INVALID')
            if any(s[k] != m[k] for k in ("analysis_operation_id", "probables_run_id", "analysis_boundary")):
                raise ValueError("WO08_HANDOFF_LINEAGE_INVALID")
            if s["run_id"] != m["manifest_id"]:
                raise ValueError("WO08_HANDOFF_LINEAGE_INVALID")
            result_ids.append(s["probables_member_id"])
        if (len(set(result_ids)) != len(result_ids)
                or set(result_ids) & set(m['excluded_result_reasons'])
                or set(result_ids) | set(m['excluded_result_reasons']) != set(m['all_result_ids'])
                or len({s.data['subject'] for s in self.samples}) != len(self.samples)):
            raise ValueError("WO08_HANDOFF_POPULATION_INVALID")

    def encoded(self):
        return canonical(dict(manifest=self.manifest.data, samples=[s.data for s in self.samples],
                              supplements=[json.loads(s) for s in self.supplements],
                              newly_published=self.newly_published))


def validate_t0_supplement(sample, payload):
    """Owning typed validation at capture AND exact-ID recovery.

    Replay references retain unavailable acquisition/revision provenance; a
    self-consistent hash is never sufficient to substitute another member.
    """
    from kronos.intraday.probables_v2_persistence import _from_wire, _to_wire
    from kronos.intraday.probables_v2 import (DiscoveryProbablesEvidenceV2,
        ProbableMemberResultV2, _mapped_result_lineage_valid)
    from kronos.intraday.native_structural_selection import create_native_selection
    from kronos.intraday.discovery import NativeDiscoveryMachineFactBundle
    from kronos.intraday.assessment_observation import AdmissionAssessment
    s = sample.data
    if type(payload) is not bytes or sha256(payload).hexdigest() != s['candle_supplement_sha256']:
        raise ValueError('WO08_SUPPLEMENT_INTEGRITY_INVALID')
    raw = json.loads(payload)
    keys = {'run_reference', 'result', 'mapping', 'facts_reference', 'assessments',
            'native', 'discovery_reference', 'bundles'}
    if type(raw) is not dict or set(raw) != keys or canonical(raw) != payload:
        raise ValueError('WO08_SUPPLEMENT_INVALID')
    r, m = _from_wire(raw['result']), _from_wire(raw['mapping'])
    if type(r) is not ProbableMemberResultV2 or type(m) is not DiscoveryProbablesEvidenceV2:
        raise ValueError('WO08_SUPPLEMENT_LINEAGE_INVALID')
    r.__post_init__(); m.__post_init__(); m.completed_evidence.__post_init__()
    if not _mapped_result_lineage_valid(r, m):
        raise ValueError('WO08_SUPPLEMENT_LINEAGE_INVALID')
    expected = dict(subject=r.canonical_subject_identity, probables_member_id=r.result_identity,
        discovery_id=r.source_discovery_run_identity, mapping_id=m.mapping_identity,
        phase=r.phase.value, session_id=r.market_session_identity,
        completed_selection_id=r.completed_evidence_selection_identity,
        analysis_boundary=r.analysis_boundary.isoformat(), probables_state=r.state.value,
        direction='UNKNOWN' if r.direction is None or str(r.direction)=='UNAVAILABLE' else str(r.direction),
        calendar_id=m.completed_evidence.calendar_identity, calendar_version=m.completed_evidence.calendar_version)
    if any(s[k] != v for k,v in expected.items()):
        raise ValueError('WO08_SUPPLEMENT_LINEAGE_INVALID')
    rr = raw['run_reference']
    if (type(rr) is not dict or set(rr) != {'identity','integrity','universe','reconciliation'}
            or rr['identity'] != s['probables_run_id']
            or type(raw['discovery_reference']) is not dict
            or set(raw['discovery_reference']) != {'identity','session'}
            or raw['discovery_reference']['identity'] != s['discovery_id']
            or not isinstance(raw['discovery_reference']['session'], str)):
        raise ValueError('WO08_SUPPLEMENT_LINEAGE_INVALID')
    refs = {v['kind']: v for v in s['source_artifact_refs']}
    if (refs.get('PROBABLES_RESULT') != dict(kind='PROBABLES_RESULT', identity=r.result_identity,
            integrity_sha256=sha256(canonical(_to_wire(r))).hexdigest())
            or 'PROBABLES_REPLAY_ENVELOPE' not in refs):
        raise ValueError('WO08_SUPPLEMENT_LINEAGE_INVALID')
    f = raw['facts_reference']
    if f is None:
        if s['machine_fact_ids'] or s['quality']=='COMPLETE':
            raise ValueError('WO08_SUPPLEMENT_LINEAGE_INVALID')
    elif (type(f) is not dict or set(f) != {'identity','replay_envelope'}
            or s['machine_fact_ids'] != [f['identity']] or f['identity'] not in m.provenance
            or f['replay_envelope'] != refs['PROBABLES_REPLAY_ENVELOPE']['identity']):
        raise ValueError('WO08_SUPPLEMENT_LINEAGE_INVALID')
    if type(raw['native']) is not dict:
        raise ValueError('WO08_SUPPLEMENT_LINEAGE_INVALID')
    n = create_native_selection(**raw['native'])
    d = n.data
    expected_native = dict(subject=s['subject'], analysis_cycle=s['probables_run_id'],
        probable_result_identity=r.result_identity, session=s['session_id'],
        completed_evidence_identity=s['completed_selection_id'], machine_identity=r.semantic_evidence_identity,
        machine_integrity=m.semantic_evidence.integrity_identity,
        direction='UNAVAILABLE' if r.direction is None else str(r.direction))
    if (n.identity != s['native_decision_id'] or d['result'] != s['native_state']
            or moment(d['analysis_boundary']) != r.analysis_boundary
            or any(d[k] != v for k,v in expected_native.items())
            or d['exact_contract'] != s['exact_contract_id'] or d['roll_lineage'] != s['binding_id']):
        raise ValueError('WO08_SUPPLEMENT_LINEAGE_INVALID')
    if s['market_family'].startswith('MCX_'):
        binding_class = ('MCX_BINDING_INVALID' if 'MCX_CONTRACT_BINDING_INVALID' in d['reasons']
            else 'MCX_BINDING_VALID' if d['exact_contract'] and d['roll_lineage'] else 'MCX_BINDING_UNAVAILABLE')
        if s['mcx_binding_class'] != binding_class or 'MCX_POSITIVE_METHOD_RESEARCH_NOT_COMMISSIONED' not in s['exclusion_reasons']:
            raise ValueError('WO08_MCX_NEGATIVE_ONLY')
    expected_candles = []
    for selected in m.completed_evidence.selected_candles:
        selected.__post_init__(); c = selected.candle; c.__post_init__()
        expected_candles.append(dict(timeframe=c.timeframe.value, candle_id=c.candle_identity,
            integrity=c.integrity_identity, start=c.candle_start.isoformat(), end=c.candle_end.isoformat(),
            completion=c.completion_state, source_identity=c.provider_source_identity,
            kronos_acquired_at=None, provider_observed_at=None, source_revision_id=None,
            kronos_published_at=None, oi=None))
    if s['candle_refs'] != expected_candles:
        raise ValueError('WO08_SUPPLEMENT_CANDLE_LINEAGE_INVALID')
    if type(raw['bundles']) is not list or type(raw['assessments']) is not list:
        raise ValueError('WO08_SUPPLEMENT_LINEAGE_INVALID')
    for value in raw['bundles']:
        bundle = _from_wire(value)
        if type(bundle) is not NativeDiscoveryMachineFactBundle:
            raise ValueError('WO08_SUPPLEMENT_LINEAGE_INVALID')
        bundle.__post_init__()
        if (bundle.canonical_identity != s['subject'] or bundle.market_session_identity != raw['discovery_reference']['session']
                or bundle.observation_boundary != r.analysis_boundary
                or bundle.universe_identity != rr['universe'] or bundle.reconciliation_identity != rr['reconciliation']):
            raise ValueError('WO08_SUPPLEMENT_LINEAGE_INVALID')
    for value in raw['assessments']:
        a = _from_wire(value)
        if type(a) is not AdmissionAssessment:
            raise ValueError('WO08_SUPPLEMENT_LINEAGE_INVALID')
        a.__post_init__()
        if (a.run_identity != s['probables_run_id'] or a.admission_identity != r.result_identity
                or a.canonical_subject_identity != s['subject'] or a.market_session_identity != s['session_id']
                or a.analysis_boundary != r.analysis_boundary or a.source_mapping_identity != m.mapping_identity):
            raise ValueError('WO08_SUPPLEMENT_LINEAGE_INVALID')
    return r, m, n


def outcome_for(t0, **values):
    t0.__post_init__()
    s = t0.data
    for k, v in dict(sample_id=t0.identity, subject=s["subject"], session_id=s["session_id"],
                     exact_contract_id=s["exact_contract_id"], t0_boundary=s["analysis_boundary"]).items():
        if k in values and values[k] != v:
            raise ValueError("WO08_OUTCOME_LINEAGE_INVALID")
        values[k] = v
    if (s['mcx_binding_class'] in {'MCX_BINDING_INVALID', 'MCX_BINDING_UNAVAILABLE'}
            or 'MCX_POSITIVE_METHOD_RESEARCH_NOT_COMMISSIONED' in s['exclusion_reasons']) and values['state'] == 'COMPLETE_SAME_CONTRACT':
        raise ValueError("WO08_MCX_NEGATIVE_ONLY")
    return record("OUTCOME", **values)


def validate_outcome_supplement(t0, outcome, payload, *, t0_supplement=None):
    """Verify existing governed later candles; never acquire or infer them."""
    from kronos.intraday.probables_v2_persistence import _from_wire
    from kronos.intraday.historical_semantic import GovernedHistoricalCandlePayload
    s, o = t0.data, outcome.data
    if type(payload) is not bytes or sha256(payload).hexdigest() != o['outcome_candle_supplement_sha256']:
        raise ValueError('WO08_OUTCOME_SUPPLEMENT_INVALID')
    raw = json.loads(payload)
    if type(raw) is not dict or set(raw) != {'candles'} or canonical(raw) != payload:
        raise ValueError('WO08_OUTCOME_SUPPLEMENT_INVALID')
    candles = tuple(_from_wire(x) for x in raw['candles'])
    boundary, captured = moment(s['analysis_boundary']), moment(o['captured_at'])
    previous = None
    for c in candles:
        if type(c) is not GovernedHistoricalCandlePayload:
            raise ValueError('WO08_OUTCOME_SUPPLEMENT_INVALID')
        c.__post_init__()
        if (c.canonical_subject_identity != s['subject'] or c.market_session_identity != s['session_id']
                or c.timeframe.value != '5M' or c.completion_state != 'COMPLETE'
                or c.candle_start < boundary or c.candle_end > captured
                or previous is not None and c.candle_start != previous):
            raise ValueError('WO08_OUTCOME_TEMPORAL_LINEAGE_INVALID')
        previous = c.candle_end
    if ([c.candle_identity for c in candles] != o['ordered_5m_candle_ids']
            or [c.integrity_identity for c in candles] != o['ordered_integrities']):
        raise ValueError('WO08_OUTCOME_LINEAGE_INVALID')
    lengths = {'NEXT_COMPLETED_5M':1, 'NEXT_15M':3, 'NEXT_30M':6, 'NEXT_60M':12}
    if o['horizon'] in lengths:
        from datetime import timedelta
        if (len(candles) != lengths[o['horizon']] or not candles
                or candles[0].candle_start >= boundary+timedelta(minutes=5)
                or any(c.candle_end-c.candle_start != timedelta(minutes=5) for c in candles)):
            raise ValueError('WO08_OUTCOME_HORIZON_INCOMPLETE')
    else:
        # Option A does not commission a session-remainder completeness producer.
        # Retained later candles cannot invent missing horizon/session authority.
        raise ValueError('WO08_OUTCOME_HORIZON_AUTHORITY_UNAVAILABLE')
    for k in ('first_favorable_at', 'first_adverse_at'):
        if o[k] is not None and not boundary < moment(o[k]) <= captured:
            raise ValueError('WO08_OUTCOME_NOT_LATER')
    return candles
