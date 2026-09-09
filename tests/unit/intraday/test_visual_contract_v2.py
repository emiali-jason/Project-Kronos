"""WO-07C deterministic contract fixtures; no empirical Analyst claims."""
from dataclasses import asdict, replace
import json
import pytest
from kronos.intraday import visual_contract_v2 as v
from kronos.intraday.review import ObservationStatus as S, ReviewError
from kronos.intraday.review_answer import parse_answer_pack, answer_artifact_bytes as artifact_bytes, answer_artifact_from_bytes as artifact_from_bytes, _parse_answer
from kronos.intraday.review_v2 import create_question_pack_v2, artifact_bytes_v2, artifact_from_bytes_v2, bind_imported_visual_evidence_v2
from kronos.intraday.review_v2_transport import _answer_candidate
from .test_review_v2 import _application, _opening_inputs, _resolver, _answer
from .test_review import _png


def observation(question, status=S.OBSERVED, answer=None):
    present = status in (S.OBSERVED, S.PARTIAL)
    selected = answer or question.allowed_answers[0] if present else None
    return v.VisualObservationV2(question.question_id, status, selected,
        question.timeframe_scope if present else (), "Independent visible fixture basis." if present else None,
        "Incomplete or unavailable fixture evidence." if status is not S.OBSERVED else None,
        "A material condition outside the other dimensions." if selected == "MATERIAL_OBSERVATION" else None)


@pytest.mark.parametrize("question", v.NSE_QUESTIONS + v.MCX_QUESTIONS, ids=lambda q:q.question_id)
@pytest.mark.parametrize("status", tuple(S))
def test_every_question_status(question, status):
    item = observation(question, status)
    document = asdict(item); document["visible_timeframes"] = list(item.visible_timeframes)
    assert _parse_answer(document, v.VisualObservationV2) == item


@pytest.mark.parametrize("question,answer", [(q,a) for q in v.NSE_QUESTIONS + v.MCX_QUESTIONS for a in q.allowed_answers])
def test_every_frozen_semantic_enum(question, answer):
    assert observation(question, answer=answer).answer == answer


@pytest.mark.parametrize("question", v.NSE_QUESTIONS + v.MCX_QUESTIONS, ids=lambda q:q.question_id)
@pytest.mark.parametrize("change", [dict(visible_basis=None), dict(visible_timeframes=("2H",)), dict(answer="BUY"), dict(why_not_covered_elsewhere="Repeated vote")])
def test_invalid_observation_fields(question, change):
    with pytest.raises(ReviewError):
        replace(observation(question), **change)


def fixture_pack(tmp_path, *, version=v.VERSION):
    *_, mapping = _opening_inputs()
    run, app = _application(tmp_path, mapping)
    cycle = app.create_eligible_cycles(run)[0]
    chart = app.upload_chart(cycle.cycle_identity, media_type="image/png", payload=_png(77))
    pack = create_question_pack_v2(app.review_store.load_handoff(cycle.handoff_identity), cycle, chart,
        question_version=version, completed_selection=mapping.completed_evidence)
    return app, pack, chart


def nse_document(pack):
    document = _answer_candidate(pack)
    document.update(observed_visible_subject_identity="Reliance Industries Ltd", global_observation_status="OBSERVED")
    document["answers"] = [asdict(observation(q)) for q in pack.questions]
    return document


def test_nse_v2_exact_roundtrip_and_v1_immutable(tmp_path):
    app, modern, chart = fixture_pack(tmp_path)
    legacy = create_question_pack_v2(app.review_store.load_handoff(app.review_store.load_cycle(chart.review_cycle_identity).handoff_identity), app.review_store.load_cycle(chart.review_cycle_identity), chart)
    old = artifact_bytes_v2(legacy)
    assert modern.review_pack_identity != legacy.review_pack_identity
    assert (legacy.schema_version, legacy.question_set_version) == ("2.0.0", "1.0.0")
    assert (modern.schema_version, modern.question_set_version) == ("3.0.0", "2.0.0")
    assert modern.governed_levels and artifact_from_bytes_v2(artifact_bytes_v2(modern)) == modern
    answer = parse_answer_pack(json.dumps(nse_document(modern)).encode())
    assert artifact_from_bytes(artifact_bytes(answer)) == answer
    evidence = bind_imported_visual_evidence_v2(modern, answer, imported_at=chart.received_at, visual_identity_resolver=_resolver(modern.analysis_boundary))
    assert artifact_from_bytes_v2(artifact_bytes_v2(evidence)) == evidence
    for pack, payload in ((modern, _answer(legacy)), (legacy, answer)):
        with pytest.raises(ReviewError):
            bind_imported_visual_evidence_v2(pack, payload, imported_at=chart.received_at, visual_identity_resolver=_resolver(modern.analysis_boundary))
    assert artifact_from_bytes_v2(old) == legacy and artifact_bytes_v2(legacy) == old


@pytest.mark.parametrize("mutation", ["schema", "version", "question_set", "order", "duplicate", "missing", "unknown", "score", "old_enum"])
def test_nse_v2_rejects_masquerade_and_malformed(tmp_path, mutation):
    _, pack, _ = fixture_pack(tmp_path)
    d = nse_document(pack)
    if mutation == "schema": d["schema_identity"] = "KRONOS-INTRADAY-CHART-ANALYST-ANSWER-PACK-V1"
    elif mutation == "version": d["schema_version"] = "1.0.0"
    elif mutation == "question_set": d["question_set_identity"] = "KRONOS-INTRADAY-CHART-ANALYST-QUESTION-SET-V1"
    elif mutation == "order": d["answers"].reverse()
    elif mutation == "duplicate": d["answers"][-1] = d["answers"][0]
    elif mutation == "missing": d["answers"].pop()
    elif mutation == "unknown": d["answers"][0]["extra"] = True
    elif mutation == "score": d["score"] = 90
    else: d["answers"][1]["answer"] = "SUPPORTIVE"
    with pytest.raises(ReviewError): parse_answer_pack(json.dumps(d).encode())


def test_exact_question_order_and_no_redundant_questions():
    assert tuple(q.question_id for q in v.NSE_QUESTIONS) == tuple(f"Q{i}" for i in range(1,11))
    assert tuple(q.question_id for q in v.MCX_QUESTIONS) == tuple(f"{f}{i}" for f in "RMX" for i in range(1,6))
    assert {t for q in v.MCX_QUESTIONS for t in q.timeframe_scope} == {"1D","4H","15M","5M"}
    assert all("RSI" not in q.wording and "Railway" not in q.wording for q in v.MCX_QUESTIONS)


def test_missing_governed_level_has_no_substantive_fallback(tmp_path):
    app, p, chart = fixture_pack(tmp_path)
    cycle = app.review_store.load_cycle(chart.review_cycle_identity)
    p = create_question_pack_v2(app.review_store.load_handoff(cycle.handoff_identity),cycle,chart,question_version=v.VERSION)
    d = nse_document(p)
    with pytest.raises(ReviewError):
        bind_imported_visual_evidence_v2(p,parse_answer_pack(json.dumps(d).encode()),imported_at=chart.received_at,visual_identity_resolver=_resolver(p.analysis_boundary))
    for item in d["answers"]:
        if item["question_id"] in {"Q6","Q9"}: item["answer"] = "NOT_OBSERVABLE"
    assert bind_imported_visual_evidence_v2(p,parse_answer_pack(json.dumps(d).encode()),imported_at=chart.received_at,visual_identity_resolver=_resolver(p.analysis_boundary))


def test_question_optional_content_does_not_invalidate_other_dimensions(tmp_path):
    from .test_review_v2_individual_inbox import _fixture, _cycles
    from .chart_input_fixtures import fixture_receipt
    _, app = _fixture(tmp_path, ("BDL",))
    c = _cycles(app)["BDL"].cycle_identity
    chart = app.upload_chart(c,media_type="image/png",payload=_png(12))
    receipt = fixture_receipt(app, chart)
    v.require_question_content((observation(v.NSE_QUESTIONS[0]),), receipt.panels)
    with pytest.raises(ReviewError): v.require_question_content((observation(v.NSE_QUESTIONS[5]),), receipt.panels)
    v.require_question_content((observation(v.NSE_QUESTIONS[5], answer="NOT_OBSERVABLE"),), receipt.panels)
    from kronos.intraday.validation import FactObservability
    panels=tuple(replace(p,content=p.content+(("factual_levels",FactObservability.EXACT),)) for p in receipt.panels)
    v.require_question_content((observation(v.NSE_QUESTIONS[5]),), panels)


@pytest.mark.parametrize("index,expected", ((2, 'e7cfce529da19742bc557d05d3fb09f79b28ddfa1212d81c57d4d721074421e6'), (3, '85fd6f9d0577028b6990ec35a9da81d9e8c6a66b8eb87e25f36d750bbbecc374'), (4, 'f4c240c030d1d0a287d9b77adb7039384c87f1a78635216e463afe10cb3faf6e'), (5, 'cc83b7c6bd3c3decbed84192450342ac6a29b4c2b559dc42e89d47a5bb887dde')))
def test_historical_workflow_bytes_match_published_baseline(index,expected):
    # Frozen from unmodified published 2ce47b2 using the same governed fixture.
    from hashlib import sha256
    from .test_wo10_contracts import _v2_lineage
    value=_v2_lineage()[index]
    assert sha256(artifact_bytes_v2(value)).hexdigest()==expected
