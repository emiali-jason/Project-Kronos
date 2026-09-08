"""WO-06E: deterministic isolated comparison, never live operations."""
import ast
from copy import deepcopy
from datetime import datetime, time
from decimal import Decimal, localcontext
from inspect import getsource
from itertools import product
from types import SimpleNamespace

import pytest

from kronos.intraday import cpr_counterfactual_research as research
from kronos.intraday.cpr_counterfactual_research import (
    CprResearchError, Decision, _decision, compare_population, counts, research_slice,
)
from kronos.application.intraday_cpr_research import analyze_retained, distribution
from kronos.intraday.probables_v2 import (
    _evaluate_member, create_probables_v2_methodology, SemanticDirection as Direction,
    IntradayAnalysisPhase as Phase,
)
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.population_measurement import MeasurementPopulation, longitudinal_population
from kronos.intraday.completed_evidence import EvidenceSessionRole
from kronos.intraday.contracts import IntradayTimeframe
from tests.unit.intraday.test_opening_admission_correction import opening_mapping, run_mapping
from tests.unit.intraday.test_probables_v2 import _narrow_from_daily, _later_mapping, CURRENT_DAY, IST


def population(**kwargs):
    version=kwargs.pop("version","2.2.0")
    method=create_probables_v2_methodology(version=version)
    mapping=opening_mapping(method,source_binding_version="1.1.0",**kwargs)
    return MeasurementPopulation(run_mapping(mapping,method),(mapping,),None)


def facts(pop):
    result={}
    for mapping in pop.mappings:
        daily,=mapping.completed_evidence.candles(IntradayTimeframe.DAILY,EvidenceSessionRole.PREVIOUS_SESSION_DAILY)
        fact=_narrow_from_daily(daily,mapping.market_session_identity,mapping.analysis_boundary)
        result[fact.fact_identity]=fact
    return result


def test_exact_transcription_only_two_gate_conditions_differ():
    original=ast.parse(getsource(_evaluate_member)).body[0]
    alternative=ast.parse(getsource(_decision)).body[0]
    class ExpectedEdits(ast.NodeTransformer):
        gates=0
        def visit_Name(self,node):
            if node.id=="_result":node.id="_decision_result"
            return node
        def visit_If(self,node):
            self.generic_visit(node)
            if ast.unparse(node.test)=="not semantic.narrow_cpr_qualified":
                self.gates+=1
                node.test=ast.BoolOp(op=ast.And(),values=[ast.Name(id="require_cpr",ctx=ast.Load()),node.test])
            return node
    transform=ExpectedEdits()
    expected=[transform.visit(node) for node in original.body]
    assert transform.gates==2
    assert [ast.dump(n) for n in expected]==[ast.dump(n) for n in alternative.body]


@pytest.mark.parametrize("version",["2.0.0","2.1.0","2.2.0"])
@pytest.mark.parametrize("direction",["LONG","SHORT"])
@pytest.mark.parametrize("narrow",[False,True])
@pytest.mark.parametrize("prior,five,nifty",list(product(["SUPPORTING","INFORMATIONAL","CONFLICTING"],repeat=3)))
def test_original_methodology_and_opening_truth_table(version,direction,narrow,prior,five,nifty):
    method=create_probables_v2_methodology(version=version)
    mapping=opening_mapping(method,direction=direction,narrow=narrow,prior=prior,five=five,nifty=nifty)
    before=repr(mapping)
    original=_evaluate_member(mapping)
    baseline=_decision(mapping,require_cpr=True)
    shadow=_decision(mapping,require_cpr=False)
    assert baseline==Decision(original.state,original.direction,original.reasons)
    expected=(prior!="CONFLICTING" and nifty!="CONFLICTING"
        and (five=="SUPPORTING" if version!="2.2.0" else ("CONFLICTING" not in (prior,five,nifty) and "SUPPORTING" in (prior,five,nifty))))
    assert shadow.admitted==expected
    assert baseline.admitted==(narrow and expected)
    assert shadow.direction==baseline.direction==Direction(direction)
    assert repr(mapping)==before
    if baseline.admitted:assert shadow==baseline


@pytest.mark.parametrize("hour,fifteen",list(product(list(Direction),repeat=2)))
@pytest.mark.parametrize("phase",[Phase.STRUCTURE,Phase.FIRST_CURRENT_SESSION_1H,Phase.CURRENT_SESSION_ESTABLISHED])
@pytest.mark.parametrize("narrow",[False,True])
def test_later_phase_direction_and_other_blockers(hour,fifteen,phase,narrow):
    # Decision-only truth table; public comparison separately requires full
    # immutable governed artifacts and rejects absent/corrupt source evidence.
    features={"1H_REGIME":SimpleNamespace(direction=hour),"15M_STRUCTURE":SimpleNamespace(direction=fifteen)}
    mapping=SimpleNamespace(semantic_evidence=SimpleNamespace(narrow_cpr_qualified=narrow,fact=features.__getitem__),
        completed_evidence=SimpleNamespace(market_identity="NSE"),phase=phase)
    baseline=_decision(mapping,require_cpr=True);shadow=_decision(mapping,require_cpr=False)
    expected=hour==fifteen and hour in (Direction.LONG,Direction.SHORT)
    assert shadow.admitted==expected
    assert baseline.admitted==(narrow and expected)
    if shadow.admitted:assert shadow.direction==hour==fifteen


@pytest.mark.parametrize("subject",["NSE-EQ-RELIANCE","NSE-INDEX-NIFTY","NSE-INDEX-BANKNIFTY"])
@pytest.mark.parametrize("direction",["LONG","SHORT"])
@pytest.mark.parametrize("narrow",[False,True])
def test_bound_comparison_preserves_subject_phase_history_and_prices(subject,direction,narrow):
    pop=population(subject=subject,direction=direction,narrow=narrow)
    before=pop.encode()
    rows=compare_population(pop,facts(pop));row,=rows
    assert row["eligible"] and row["subject"]==subject and row["direction"]==direction
    assert row["phase"]=="OPENING" and row["methodology"]=="2.2.0"
    assert counts(rows)["additional"]==int(not narrow)
    assert counts(rows)["sole_cpr"]==int(not narrow)
    assert counts(rows)["removed"]==0
    assert pop.encode()==before
    assert all(o.assessment_price is None and o.assessment_time is None for o in pop.observations)


def test_sole_cpr_vs_multiple_blockers_and_no_version_upgrade():
    sole=population(narrow=False)
    multiple=population(narrow=False,prior="CONFLICTING")
    historical=population(narrow=False,version="2.1.0")
    rows=[compare_population(p,facts(p))[0] for p in (sole,multiple,historical)]
    assert counts(rows)["sole_cpr"]==1
    assert counts(rows)["cpr_plus_other"]==2
    assert rows[2]["counterfactual"]["reasons"]==["OPENING_5M_NOT_SUPPORTING"]


@pytest.mark.parametrize("phase_args",[(2,0),(4,1),(8,2)])
def test_real_later_mapping_baseline_and_source_binding(phase_args):
    m=_later_mapping(*phase_args,boundary=datetime.combine(CURRENT_DAY,time(13),IST))
    p=MeasurementPopulation(run_mapping(m,create_probables_v2_methodology()),(m,),None)
    row,=compare_population(p,facts(p))
    assert row["eligible"] and row["baseline"]==row["counterfactual"]


@pytest.mark.parametrize("failure",["missing","foreign","tampered","formula"])
def test_missing_foreign_corrupt_source_is_not_silently_eligible(failure):
    from kronos.intraday.qualification import _narrow_cpr_payload, _identity
    p=population();source=facts(p);key=next(iter(source))
    if failure=="missing":source={}
    if failure=="foreign":source={key:next(iter(facts(population(subject="NSE-EQ-FOREIGN")).values()))}
    if failure=="tampered":
        source=deepcopy(source);object.__setattr__(source[key],"pivot",Decimal("999"))
    if failure=="formula":
        fact=deepcopy(source[key]);object.__setattr__(fact,"pivot",Decimal("999"))
        payload=_narrow_cpr_payload(fact)
        object.__setattr__(fact,"fact_identity",_identity("INTRADAY-NARROW-CPR-FACT-",payload))
        object.__setattr__(fact,"integrity_identity",_identity("INTEGRITY-NARROW-CPR-",payload))
        fact.__post_init__()
        # Direct formula check is independent of the later semantic identity gate.
        with pytest.raises(CprResearchError,match="CPR_FORMULA_NOT_REPRODUCED"):
            research._validate_cpr(p.mappings[0],fact)
        return
    rows=compare_population(p,source)
    assert len(rows)==1 and not rows[0]["eligible"]
    assert rows[0]["exclusion_reason"] and rows[0]["counterfactual"] is None
    with pytest.raises(CprResearchError):research_slice(p,rows,counterfactual=True)


def test_unavailable_context_is_preserved_before_cpr():
    p=population(narrow=False,missing="NIFTY")
    row,=compare_population(p,{})
    assert not row["eligible"] and row["baseline"]["state"]=="UNAVAILABLE"
    assert row["baseline"]==row["counterfactual"]
    assert counts([row])["raw"]==1
    assert counts([row])["additional"]==0


def test_held_mcx_remains_unavailable():
    m=SimpleNamespace(completed_evidence=SimpleNamespace(market_identity="MCX"),
        canonical_subject_identity="MCX-SUBJECT-NATGAS",semantic_evidence=None)
    assert _decision(m,require_cpr=True)==_decision(m,require_cpr=False)
    assert _decision(m,require_cpr=False).state.value=="UNAVAILABLE"


def test_evaluator_advancement_requires_review(monkeypatch):
    monkeypatch.setattr(research,"REVIEWED_EVALUATOR_SHA256","not-reviewed")
    with pytest.raises(CprResearchError,match="EVALUATOR_REVIEW_REQUIRED"):
        compare_population(population(),{})


def test_baseline_mismatch_is_reported_not_reinterpreted(monkeypatch):
    actual=research._decision
    def wrong(mapping,*,require_cpr):
        from dataclasses import replace
        return replace(actual(mapping,require_cpr=require_cpr),direction=Direction.SHORT)
    monkeypatch.setattr(research,"_decision",wrong)
    p=population();row,=compare_population(p,facts(p))
    assert not row["eligible"] and row["exclusion_reason"]=="HISTORICAL_BASELINE_NOT_REPRODUCED"


def test_dependence_projection_preserves_raw_population_and_rejects_partial():
    p=population(narrow=False);before=p.encode();rows=compare_population(p,facts(p))
    s=research_slice(p,rows,counterfactual=True)
    transitions=longitudinal_population([s,s])
    assert len(transitions)==1 and transitions[0].states==("NEW_ADMISSION",)
    assert transitions[0].observation_identity.startswith("WO06E-RESEARCH-OBSERVATION-")
    assert p.encode()==before and p.denominators["admitted"]==0
    for invalid in [[],[rows[0],rows[0]],[dict(rows[0],subject="FOREIGN")]]:
        with pytest.raises(CprResearchError):research_slice(p,invalid,counterfactual=True)


def test_read_only_adapter_missing_envelope_preserves_files(tmp_path):
    p=population();store=ProbablesV2Store(tmp_path)
    store.retain_complete(run=p.run,mappings=p.mappings)
    before={str(f):f.read_bytes() for f in tmp_path.rglob('*') if f.is_file()}
    result=analyze_retained(tmp_path)
    assert result["counts"]["raw"]==1 and result["counts"]["eligible"]==0
    assert result["exclusions"]=={"CPR_FACT_NOT_RETAINED":1}
    assert result["dependencies"]["errors"]
    assert {str(f):f.read_bytes() for f in tmp_path.rglob('*') if f.is_file()}==before


def test_distribution_empty_singleton_and_exact_interpolation():
    assert distribution([])["median"] is None
    assert distribution(["2"])["q1"]=="2"
    result=distribution(["0","10","20","30"])
    assert result["q1"]=="7.50" and result["median"]=="15.0" and result["q3"]=="22.50"
    with localcontext() as context:
        context.prec=3
        assert distribution(["0","10","20","30"])==result
