"""Exact WO08/T0/outcome association inside the existing WO12 ledger.

This reader does no acquisition and never participates in live admission. It
uses the immutable 02A T0/T1+ store and stores compact associations, not candles.
"""
from datetime import datetime

from kronos.intraday.wo12_research_contract import record
from kronos.intraday.probables import ProbableState

LEGACY_SCHEMA = "WO12_WO08_ASSESSMENT_ASSOCIATION_V1"
SCHEMA = "WO12_WO08_ASSESSMENT_ASSOCIATION_V3"
ADMITTED = {ProbableState.LONG_PROBABLE, ProbableState.SHORT_PROBABLE}


def associate_assessments(*, assessments, shadow, probables, origins, readiness, futures, lifecycle, watch_store=None):
    if assessments is None:
        return ()
    manifests = () if shadow is None else tuple(shadow.load("RUN", p.stem)
        for p in sorted((shadow.root / "run").glob("*.json")))
    samples = tuple(shadow.load("T0", identity) for identity in sorted({identity
        for manifest in manifests for identity in manifest.data["selected_sample_ids"]}))
    outcomes = () if shadow is None else tuple(shadow.load("OUTCOME", p.stem)
        for p in sorted((shadow.root / "outcome").glob("*.json")))
    records = []
    retained = assessments.records()
    # Detached immutable payload projections are local to this research pass.
    # Avoid decoding the complete source graph for every history/method pair.
    data_by_identity = {item.identity: item.data for item in retained}
    by_result = {data_by_identity[item.identity]["probable_result_identity"]: item for item in retained}
    method_fields = ('methodology_identity', 'methodology_version', 'methodology_checksum')
    by_method = {}
    for item in retained:
        method = tuple(data_by_identity[item.identity][k] for k in method_fields)
        by_method.setdefault(method, set()).add(item.identity)
    watch_documents = watch_history = ()
    if watch_store is not None and any(data_by_identity[a.identity]['methodology_identity'] ==
            'KRONOS-INTRADAY-WO08-EXPERIMENTAL-PULLBACK-PAPER' for a in retained):
        from kronos.application.intraday_experimental_watch import ExperimentalWatchStore
        watch_owner = ExperimentalWatchStore(watch_store)
        watch_documents, watch_history = watch_owner.records(), watch_owner.watch_history()
    for assessment in retained:
        assessment.__post_init__()
        d = data_by_identity[assessment.identity]
        run = probables.load_run(d["run_identity"])
        result = probables.load_result(d["probable_result_identity"])
        if (result not in run.results or run.integrity_identity != d["run_integrity"]
                or result.integrity_identity != d["probable_result_integrity"]):
            raise ValueError("WO12_WO08_PROBABLES_BINDING_INVALID")
        matching = [sample for sample in samples
            if sample.data["probables_run_id"] == d["run_identity"]
            and sample.data["probables_member_id"] == d["probable_result_identity"]]
        for sample in matching:
            sd = sample.data
            if (sd["subject"] != d["subject"] or sd["session_id"] != d["session_identity"]
                    or datetime.fromisoformat(sd["analysis_boundary"]) != datetime.fromisoformat(d["analysis_boundary"])
                    or sd["native_decision_id"] != d["native_decision_identity"]
                    or sd["completed_selection_id"] != d["completed_evidence_identity"]
                    or sd["exact_contract_id"] != d["exact_mcx_contract_identity"]
                    or sd["binding_id"] != d["exact_mcx_roll_lineage"]):
                raise ValueError("WO12_WO08_T0_BINDING_INVALID")
        sample_ids = {sample.identity for sample in matching}
        later = [item for item in outcomes if item.data["sample_id"] in sample_ids]
        applicable = [origin for origin in origins
            if origin.data["canonical_subject_identity"] == d["subject"]
            and origin.data["market_session_identity"] == d["session_identity"]
            and datetime.fromisoformat(origin.data["origin_at"]) <= datetime.fromisoformat(d["analysis_boundary"])]
        origin = max(applicable, key=lambda item: (item.data["origin_at"], item.identity)) if applicable else None
        original = None if origin is None else by_result.get(origin.data["probable_result_identity"])
        # Only the exact original admission result can supply the original prediction.
        # A later reassessment is never substituted when that assessment is absent.
        original_prediction = None
        original_source = original_methodology = original_run_identity = None
        if original is not None:
            original.__post_init__()
            od = data_by_identity[original.identity]
            original_result = probables.load_result(od["probable_result_identity"])
            if original_result.state not in ADMITTED:
                raise ValueError("WO12_WO08_ORIGINAL_NOT_ADMITTED")
            original_prediction = dict(assessment_identity=original.identity,
                assessment_integrity=original.integrity, probable_result_identity=original_result.result_identity,
                probable_result_integrity=original_result.integrity_identity,
                direction=od["direction"], probables_state=original_result.state.value,
                probables_reasons=[reason.value for reason in original_result.reasons],
                criteria=od["criteria"], disposition=od["disposition"], hard_gate=od["hard_gate"],
                failure_stage=od["failure_stage"], failure_reason=od["failure_reason"],
                analysis_boundary=od["analysis_boundary"], created_at=od["created_at"])
            original_run_identity = od['run_identity']
            original_methodology = {k: od[k] for k in ('methodology_identity', 'methodology_version', 'methodology_checksum')}
            original_source = {k: od[k] for k in ('generation', 'discovery_identity', 'mapping_identity',
                'semantic_evidence_identity', 'semantic_evidence_integrity', 'completed_evidence_identity',
                'completed_evidence_integrity', 'native_decision_identity', 'native_decision_integrity',
                'exact_mcx_contract_identity', 'exact_mcx_roll_lineage', 'calendar_identity', 'calendar_version', 'trading_date')}
        history = tuple(item for values in readiness.values() for item in values
                        if getattr(item, "wo08_identity", None) == assessment.identity)
        episode_history = tuple(item for values in readiness.values() for item in values
            if origin is not None and item.canonical_subject_identity == d['subject']
            and item.session_identity == d['session_identity']
            and item.analysis_boundary >= datetime.fromisoformat(origin.data['origin_at'])
            and not any(o.data['canonical_subject_identity'] == d['subject']
                and o.data['market_session_identity'] == d['session_identity']
                and datetime.fromisoformat(origin.data['origin_at']) < datetime.fromisoformat(o.data['origin_at']) <= item.analysis_boundary
                for o in origins)
            and getattr(item, 'wo08_identity', None) in by_method[tuple(
                (original_methodology or d)[k] for k in method_fields)])
        entry = min(episode_history, key=lambda r: (r.created_at, r.readiness_identity)) if episode_history else None
        readiness_ids = {item.readiness_identity for item in history}
        downstream = [item for schema in ("WO10_OPPORTUNITY_V1", "WO10_CONSTRUCTION_UNAVAILABLE_V1",
                                          "WO10_SPONSOR_COMPARISON_V1")
                      for item in futures.records(schema) if item.data.get("readiness_identity") in readiness_ids]
        opportunity_ids = {item.identity for item in downstream if item.schema == "WO10_OPPORTUNITY_V1"}
        tracks = [item for item in lifecycle.restore()
                  if item.data["intake"]["opportunity_identity"] in opportunity_ids]
        experimental = d["methodology_identity"] == "KRONOS-INTRADAY-WO08-EXPERIMENTAL-PULLBACK-PAPER"
        experimental_history = {}
        if experimental:
            from kronos.application.intraday_experimental_watch import ExperimentalWatchStore, BINDING, HINT
            documents = watch_documents
            bindings = [v for v in documents if v["schema"] == BINDING
                        and v["assessment_identity"] == assessment.identity]
            binding_ids = {v["identity"] for v in bindings}
            watches = watch_history
            from kronos.intraday.wo09_readiness import artifact_bytes
            import json
            experimental_history = dict(
                experimental_authority="EXPERIMENTAL_PAPER_ONLY",
                predictive_usefulness="NOT_ESTABLISHED",
                experimental_measurement=d.get("experimental_measurement"),
                selective_watch_bindings=bindings,
                selective_watch_history=[json.loads(artifact_bytes(w)) for w in watches
                                         if w.watch_identity in {b["watch_identity"] for b in bindings}],
                advisory_wake_hints=[v for v in documents if v["schema"] == HINT
                                    and v["binding_identity"] in binding_ids],
                first_five_provenance=[item.first_five_document for item in history
                    if getattr(item, "first_five_document", None) is not None])
        records.append(record("WO12_WO08_EXPERIMENTAL_ASSOCIATION_V1" if experimental else SCHEMA,
            **experimental_history,
            research_authority="RESEARCH_ONLY_NO_TRADING_AUTHORITY", live_control_authority="NONE",
            assessment_identity=assessment.identity, assessment_integrity=assessment.integrity,
            methodology_identity=d["methodology_identity"], methodology_version=d["methodology_version"],
            methodology_checksum=d["methodology_checksum"], run_identity=d["run_identity"],
            probable_result_identity=d["probable_result_identity"], subject=d["subject"],
            probable_result_integrity=result.integrity_identity, probables_state=result.state.value,
            probables_direction=None if result.direction is None else result.direction.value,
            probables_reasons=[reason.value for reason in result.reasons],
            considered_at_assessment=result.state in ADMITTED,
            consideration_rule="FROZEN_LONG_OR_SHORT_PROBABLE_NO_READINESS_FILTER",
            wo09_record_state="RECORDED" if history else "MISSING",
            original_prediction_state="EXACT_ORIGINAL_ADMISSION_ASSESSMENT" if original_prediction else "ORIGINAL_PREDICTION_UNAVAILABLE",
            original_prediction=original_prediction,
            opportunity_origin_at=None if origin is None else origin.data['origin_at'],
            original_run_identity=original_run_identity, original_methodology=original_methodology,
            original_source=original_source,
            wo09_entry=None if entry is None else dict(identity=entry.readiness_identity,
                integrity=entry.integrity_identity, created_at=entry.created_at,
                currentness=entry.currentness.value, wo08_identity=entry.wo08_identity),
            eod_validation_state="SEPARATE_ADDITIVE_WO12_OUTCOME",
            eod_prediction_match="SEPARATE_RESULT_LOOKUP", eod_match_reason="ORIGINAL_ASSOCIATION_IS_NOT_AN_OUTCOME",
            market_family=d["market_family"], direction=d["direction"], session_identity=d["session_identity"],
            analysis_boundary=d["analysis_boundary"], assessment_created_at=d["created_at"],
            assessment_latency_seconds=(datetime.fromisoformat(d["created_at"])-datetime.fromisoformat(d["analysis_boundary"])).total_seconds(),
            disposition=d["disposition"], criteria=d["criteria"], hard_gate=d["hard_gate"],
            failure_stage=d["failure_stage"], failure_reason=d["failure_reason"],
            opportunity_identity=None if origin is None else origin.data["opportunity_identity"],
            opportunity_id=None if origin is None else origin.data["opportunity_id"],
            t0_state="EXACT_ORIGINAL_T0" if matching else "ORIGINAL_T0_UNAVAILABLE",
            t0_references=[dict(identity=item.identity, integrity=item.data["integrity_sha256"],
                supplement_identity=item.data["candle_supplement_identity"],
                supplement_integrity=item.data["candle_supplement_sha256"]) for item in matching],
            outcomes=[dict(identity=item.identity, integrity=item.data["integrity_sha256"],
                **{key:item.data[key] for key in ("sample_id", "horizon", "state", "quality", "captured_at",
                   "directional_return", "mfe", "mae", "structural_failure", "reason")}) for item in later],
            readiness_references=[dict(identity=item.readiness_identity, integrity=item.integrity_identity,
                state=item.readiness_state.value, count=item.satisfied_count,
                created_at=item.created_at, hard_gate=item.hard_gate.value,
                criteria=[dict(criterion_id=c.criterion_id.value, state=c.state.value,
                    reason_codes=list(c.reason_codes)) for c in item.criteria]) for item in history],
            downstream_references=[dict(identity=item.identity, integrity=item.integrity, schema=item.schema) for item in downstream],
            lifecycle_references=[dict(identity=item.identity, integrity=item.integrity,
                truth_class=item.data["truth_class"], state=item.data["state"]) for item in tracks],
            false_advance_classification="SEPARATE_TERMINAL_NONMATCH_BY_WO09_PROGRESSION_LEVEL"))
    return tuple(records)


def research_metrics(associations):
    audit = [item.data for item in associations]
    # Admission is frozen at consideration, independent of later readiness/outcome.
    values = [d for d in audit if d.get("considered_at_assessment") is True]
    def positive(assessment, criterion):
        from kronos.intraday.wo08_experimental import METHODOLOGY, VERSION, CHECKSUM
        experimental = (assessment.get('methodology_identity'), assessment.get('methodology_version'),
                        assessment.get('methodology_checksum')) == (METHODOLOGY, VERSION, CHECKSUM)
        return criterion['state'] == ('SATISFIED' if experimental else 'DETERMINISTICALLY_ESTABLISHED')
    count = len(values)
    opportunities = {d["opportunity_identity"] for d in values if d["opportunity_identity"] is not None}
    unbound = sum(d["opportunity_identity"] is None for d in values)
    unavailable = sum(any(c["state"] in {"UNAVAILABLE", "NOT_COMMISSIONED", "NOT_ESTABLISHED"}
                          for c in d["criteria"]) for d in values)
    covered = sum(bool(d["outcomes"]) for d in values)
    result = [
        ("WO08 population audit assessment count", len(audit), None, len(audit), "Scanned-population association audit only; not a validation denominator"),
        ("WO08 considered assessment count", count, count, count, "Frozen admitted Long/Short Probables assessments; includes unavailable/nonadvancing readiness and repeated assessments"),
        ("WO08 considered opportunity count", len(opportunities), len(opportunities), len(opportunities), "Distinct retained opportunity origins; reassessments never create another opportunity"),
        ("WO08 considered assessments missing origin", unbound, count, unbound / count if count else None, "Missing origin remains visible; no retrospective origin is invented"),
        ("WO08 considered assessments missing WO09", sum(d["wo09_record_state"] == "MISSING" for d in values), count,
         sum(d["wo09_record_state"] == "MISSING" for d in values) / count if count else None, "Included in considered assessment denominator despite missing readiness publication"),
        ("WO08 unavailable criterion rate", unavailable, count, unavailable / count if count else None,
         "Among considered assessments including repeats; at least one unavailable/uncommissioned criterion; absence is not negative"),
        ("WO08 outcome coverage", covered, count, covered / count if count else None,
         "Among considered assessments including repeats; exact 02A T0 with retained outcome; partial outcomes remain labelled"),
        ("WO08 average publication latency seconds", sum(d["assessment_latency_seconds"] for d in values), count,
         sum(d["assessment_latency_seconds"] for d in values) / count if count else None,
         "Assessment publication minus exact original Analysis boundary; no acquisition is performed"),
        ("WO08 fully established coverage", sum(all(positive(d, c) for c in d["criteria"]) for d in values),
         count, sum(all(positive(d, c) for c in d["criteria"]) for d in values) / count if count else None,
         "Among considered assessments including repeats; all five propositions established; unavailable remains in denominator"),
    ]
    for market in ("NSE", "MCX"):
        for direction in ("LONG", "SHORT", None, "UNAVAILABLE"):
            group = [d for d in values if d["market_family"] == market and d["direction"] == direction]
            if group:
                result.append((f"WO08 {market} {direction or 'UNKNOWN'} assessments", len(group), count,
                    len(group) / count if count else None, "Exact retained market/direction strata"))
    for criterion in ("I1", "I2", "I3", "I4", "I5"):
        established = sum(positive(d, next(c for c in d["criteria"] if c["criterion_id"] == criterion)) for d in values)
        result.append((f"WO08 {criterion} established rate", established, count,
            established / count if count else None, "Among considered assessments including repeats; criterion contribution with no fabricated positive score"))
    strata = {}
    for assessment in values:
        for outcome in assessment["outcomes"]:
            if outcome["state"] != "COMPLETE_SAME_CONTRACT":
                continue
            key = (assessment["methodology_identity"], assessment["methodology_version"],
                   assessment["methodology_checksum"], assessment["market_family"],
                   assessment["direction"], outcome["horizon"])
            strata.setdefault(key, []).append(outcome)
    for key, outcomes in sorted(strata.items(), key=lambda item: str(item[0])):
        for metric in ("directional_return", "mfe", "mae"):
            observed = [item[metric] for item in outcomes if item[metric] is not None]
            result.append(("WO08 " + " / ".join(str(k) for k in key) + " average " + metric,
                sum(observed), len(observed), sum(observed)/len(observed) if observed else None,
                "Exact complete same-contract 02A outcomes only; partial and unavailable excluded"))
    return tuple(result)
