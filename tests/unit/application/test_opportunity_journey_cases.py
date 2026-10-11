"""Representative typed retained-source reporting cases, separate from full Analysis rehearsal."""
from dataclasses import replace
from datetime import datetime,timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import json
from kronos.application.intraday_research import IntradayResearchApplication
from kronos.application.intraday_opportunity_journey import JOURNEY_COLUMNS,build_journey_rows
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.wo09_persistence import Wo09Store
from kronos.intraday.wo12_research_store import ResearchStore
from kronos.intraday.wo12_eod_validation import consideration,evaluate
from kronos.intraday.wo12_research_contract import digest
from tests.unit.intraday.test_wo08_experimental import experimental_fixture
from tests.unit.intraday.test_wo09_experimental import publish,origin_for
from tests.unit.intraday.test_native_pullback_policy import BARS
from tests.unit.application.test_intraday_research import _EmptyStore,_Lifecycle


def case(tmp_path,count,subject):
    kwargs={}
    if count in (1,2):
        kwargs.update(minutes=150,rows=list(BARS)+[(117,99,116),(118,110,117)],
            five_rows=[(108,102,106)]*28+[(115,110,113),(121,114,120) if count==1 else (119,115,117)],daily=(118,92,105))
    elif count in (3,4):
        kwargs['five_rows']=[(108,102,106)]*25+[(115,110,113),(117,114,116)]
        if count==3:kwargs['daily']=(118,92,105)
    source,facts,mapping,run,native,assessment=experimental_fixture(subject=subject,**kwargs)
    assert sum(c['state']=='SATISFIED' for c in assessment.data['criteria'])==count,assessment.data['criteria']
    probables=ProbablesV2Store(tmp_path/'probables');probables.retain_complete(run=run,mappings=(mapping,))
    from kronos.intraday.assessment_observation import create_missing_assessment_observations
    from tests.unit.intraday.test_assessment_observation import positive,proof_for,manifest
    original=create_missing_assessment_observations(run).observations[0]
    price=positive(original,proof_for(original,price=Decimal('100')))
    probables.load_assessment_observations=lambda _:manifest(run,(price,))
    at=datetime.fromisoformat(assessment.data['created_at'])
    origin=origin_for(assessment);wo09=Wo09Store(tmp_path/'wo09');r,requirements=publish(wo09,assessment,origin,at+timedelta(seconds=1))
    app=IntradayResearchApplication(probables=probables,wo09=wo09,futures=_EmptyStore(),lifecycle=_Lifecycle(),
        store=ResearchStore(tmp_path/'research'),publication_root=tmp_path/'Statistics',clock=lambda:at+timedelta(seconds=2),
        wo08=SimpleNamespace(records=lambda:(assessment,)))
    if count==4:
        from kronos.application.intraday_wo09 import IntradayWo09Application
        from kronos.application.intraday_experimental_watch import IntradayExperimentalWatchCoordinator
        from kronos.provider.contracts.instrument import InstrumentRecord
        watch=IntradayExperimentalWatchCoordinator(IntradayWo09Application(wo09),clock=app.clock,current_binding=lambda _:True)
        bindings=watch.synchronize(r,requirements,session_expires_at=at+timedelta(hours=1),
            instrument=InstrumentRecord('KITE','NSE','NSE',subject.removeprefix('NSE-EQ-'),subject,'EQ',None,Decimal('.05'),1))
        assert len(bindings)==1
    projection=app.project(ensure_origins=True)
    association,=app.store.records('WO12_WO08_EXPERIMENTAL_ASSOCIATION_V1')
    cohort=consideration(association,probables,facts.current_schedule)
    return app,projection,association,cohort,price,facts,r


def test_nonadvanced_watch_never_promoted_and_terminal_match_cases(tmp_path,request):
    from tests.unit.intraday.test_wo12_eod_validation import terminal,source_ref
    from kronos.browser.intraday_research import export_research_workbook,validate_research_workbook
    cases=[(1,'NSE-EQ-TCS','110','MATCHED'),(2,'NSE-EQ-INFY','90','NOT_MATCHED'),
        (3,'NSE-EQ-HDFCBANK','110','MATCHED'),(4,'NSE-EQ-RELIANCE',None,'NOT_EVALUABLE'),
        (5,'NSE-EQ-LUPIN','90','NOT_MATCHED')]
    all_rows=[];proof=[]
    for count,subject,close,expected in cases:
        app,template,association,cohort,price,facts,r=case(tmp_path/subject,count,subject)
        candle=None if close is None else terminal(facts.current_schedule,subject,close)
        end=facts.current_schedule.windows[-1].closes_at
        outcome=evaluate(cohort,assessment=price,schedule=facts.current_schedule,candle=candle,
            now=end,source=None if candle is None else source_ref(candle))
        assert outcome.data['prediction_match']==expected
        rows=build_journey_rows(cohorts=(cohort,),associations=(association,),readiness=app._readiness_history_by_result(),
            outcomes=(outcome,),futures=app.futures,lifecycle=app.lifecycle,tracks=(),pointer_currentness={cohort.identity:'CURRENT'},assessments=app.wo08)
        row=dict(zip(JOURNEY_COLUMNS,rows[0]));all_rows+=rows
        assert row['Initial Count']==count and row['EOD Match']==expected
        assert row['Assessment Price']==Decimal('100')
        assert row['Entry Met']==row['Target Met']==row['Stop Met']=='NOT_EVALUABLE'
        if count<4:assert row['First 4 of 5 At']=='NOT_ESTABLISHED'
        if count==4:
            assert row['Watch Eligible at 4']=='YES' and row['First 5 of 5 At']=='NOT_ESTABLISHED'
            assert row['First Wake Hint At']=='NOT_ESTABLISHED'
            assert row['Watch Started At']!='NOT_ESTABLISHED' and row['Wake Hint Count']==0
        if count==5:assert row['False Advance 5']=='YES'
        if count==1:assert row['False Advance 3']==row['False Advance 4']==row['False Advance 5']=='NOT_ADVANCED'
        proof.append(dict(subject=subject,assessment_identity=association.data['assessment_identity'],
            cohort_identity=cohort.identity,outcome_identity=outcome.identity,readiness_identity=r.readiness_identity,
            source_case='TYPED_SOURCE_VALID_ASSESSMENT_AND_TERMINAL_EVALUATOR_SEAM',row=row))
    projection=replace(template,projection_identity='WO12-RESEARCH-PROJECTION-'+digest(all_rows),
        opportunities=(),tracks=(),events=(),analysis=(),data_quality=(),journey=tuple(all_rows),
        metadata=(('scope','DISPOSABLE_TYPED_PROJECTION_SEAM_NOT_FULL_ANALYSIS_OR_PROVIDER_EVIDENCE'),
            ('same_interval','DEFERRED_OUTSIDE_V1'),('terminal_source','SYNTHETIC_TYPED_CANDLE_WITH_FIXTURE_PROVENANCE')))
    payload=export_research_workbook(projection);validate_research_workbook(payload,projection)
    from tests.unit.application.test_opportunity_journey import assert_journey_readback
    assert_journey_readback(payload,projection.journey)
    if request.config.option.xmlpath:
        out=Path(request.config.option.xmlpath).parent
        (out/'Opportunity_Journey_representative_cases.xlsx').write_bytes(payload)
        (out/'Opportunity_Journey_representative_cases.json').write_text(json.dumps(dict(cases=proof,sha256=sha256(payload).hexdigest()),default=str,indent=2))
