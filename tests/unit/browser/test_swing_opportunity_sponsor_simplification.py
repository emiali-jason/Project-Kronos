"""Presentation-only Slice 1; owning fixtures, no production evidence."""
from copy import deepcopy
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
import os

import pytest

from kronos.browser.views import _native_opportunity_card, render_opportunities
from kronos.swing.v1.analytical_promotion_v2 import create_record
from kronos.swing.v1.native_discovery import NativeDiscoveryStatus, NativeProductPath, Native1WState
from kronos.swing.v1.native_review import MCX_REFERENCE_MAPPINGS
from kronos.swing.v1.models import V1Direction
from tests.unit.application.test_swing_opportunities import _ready
from tests.unit.swing.v1.test_native_review import _evidence_run
from tests.unit.swing.v1.test_analytical_promotion_v2 import (
    source, criteria, nse, mcx, NOW,
)


class CardText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.disclosures = 0
        self.primary = []
        self.details = []

    def handle_starttag(self, tag, attrs):
        if tag == 'details':
            self.disclosures += 1

    def handle_endtag(self, tag):
        if tag == 'details':
            self.disclosures -= 1

    def handle_data(self, data):
        (self.details if self.disclosures else self.primary).append(data)


def fixture(*, symbol=None, market='NSE', complete=True, question=True,
            evidence='ACCEPTED', current=True, status=NativeDiscoveryStatus.PROBABLE, direction='LONG'):
    _, run, item = _evidence_run()
    if symbol is not None:
        item = replace(item, canonical_instrument=symbol,
                       product_path=NativeProductPath.NSE if market == 'NSE' else NativeProductPath.MCX,
                       weekly_state=item.weekly_state if market == 'NSE' else Native1WState.NOT_APPLICABLE)
    item = replace(item, status=status, direction=V1Direction(direction))
    row = dict(instrument=item.canonical_instrument, run_identity=item.run_identity,
               assessment_sha256=item.result_sha256, eligible=True,
               expected={'bound': True} if current else None,
               error=None if current else 'REVIEW_BINDING_STALE', complete=complete,
               question_ready=question, evidence=evidence, receipt_id='fixture-receipt')
    intake = dict(rows=(row,), packages=(), workspace=None, error=None)
    return run, item, intake


def promotion(item, *, market='NSE', count=5, unavailable=None, states=('OUTPERFORMING', 'OUTPERFORMING'), confirmation_options=None):
    s = source(market=market, instrument=item.canonical_instrument, direction=item.direction.value)
    s['native_run_identity'] = item.run_identity
    s['native_assessment_sha256'] = item.result_sha256
    confirmation = (mcx(**(confirmation_options or {})) if market == 'MCX' else
                    nse(states=states, direction=item.direction.value, **(confirmation_options or {})))
    if market == 'NSE' and confirmation['nse_binding']['payload'] is not None:
        payload = confirmation['nse_binding']['payload']
        payload['run_identity'], payload['canonical_instrument'] = item.run_identity, item.canonical_instrument
    elif market == 'MCX':
        name, venue, symbol = MCX_REFERENCE_MAPPINGS[item.canonical_instrument]
        confirmation['mcx_binding']['payload']['registered_mapping'] = dict(
            native_family=item.canonical_instrument, reference_name=name,
            reference_market=venue.value, reference_symbol=symbol)
        for binding in s['acceptance']['visual_bindings']:
            if binding['role'] == 'SUPPORTING_REFERENCE':
                binding['reference_market'], binding['reference_symbol'] = venue.value, symbol
    c = criteria(count, unavailable=unavailable)
    if unavailable == 3:
        c = tuple(replace(x, reason='NATIVE_1H_SETUP_QUALITY_UNAVAILABLE') if i == 3 else x
                  for i, x in enumerate(c))
    return create_record(source=s, criteria=c,
                         confirmation=confirmation, created_at=NOW)


def parts(markup):
    p = CardText(); p.feed(markup)
    assert p.disclosures == 0
    return ' '.join(p.primary), ' '.join(p.details)


@pytest.mark.parametrize('market,symbol', [
    ('NSE', 'INFY'), ('MCX', 'GOLDM'), ('MCX', 'SILVERM'), ('MCX', 'COPPER'),
    ('MCX', 'CRUDEOIL'), ('MCX', 'NATURALGAS'),
])
def test_six_market_rows_keep_bound_status_and_detail(market, symbol):
    _, item, intake = fixture(symbol=symbol, market=market)
    record = promotion(item, market=market, count=3, unavailable=3)
    before = deepcopy(record.value)
    html = _native_opportunity_card(item, None, native_intake=intake, promotions_v2=(record,))
    primary, detail = parts(html)
    assert symbol in primary and item.direction.value in primary
    assert 'Current stage' in primary and 'KR-370 V2' in primary
    assert 'NOT EVALUABLE' in primary and 'BINDING CURRENT' in primary
    assert 'CHART READY' in primary and 'QUESTION PACK READY' in primary and 'ANSWER IMPORTED' in primary
    assert 'Pending requirements' in primary
    assert 'Methodology' not in primary and 'Phase' not in primary and 'Boundary' not in primary
    assert all(x in detail for x in ('Methodology', 'Phase', 'Boundary', 'K1', 'K2', 'K3', 'K4', 'K5'))
    assert '<details class="swing-opportunity-details">' in html
    assert '<details class="swing-opportunity-details" open' not in html
    assert record.value == before
    assert '<form' not in html
    if market == 'MCX':
        assert 'DOWNSTREAM — MCX STEP-31 NOT COMMISSIONED' in primary
        assert 'M1 mapping / coverage' in detail and 'M2 structural agreement' in detail
        assert 'NIFTY CONFIRMATION' not in html


@pytest.mark.parametrize('complete,question,evidence,labels', [
    (False, False, 'MISSING', ('CHART MISSING', 'QUESTION PACK NOT READY', 'ANSWER MISSING')),
    (True, False, 'MISSING', ('CHART READY', 'QUESTION PACK NOT READY', 'ANSWER MISSING')),
    (True, True, 'MISSING', ('CHART READY', 'QUESTION PACK READY', 'ANSWER MISSING')),
    (True, True, 'ACCEPTED', ('CHART READY', 'QUESTION PACK READY', 'ANSWER IMPORTED')),
    (True, True, 'STALE', ('CHART READY', 'QUESTION PACK READY', 'ANSWER STALE')),
    (True, True, 'INVALID', ('CHART READY', 'QUESTION PACK READY', 'ANSWER REJECTED')),
])
def test_intake_states_are_compact_but_not_promoted(complete, question, evidence, labels):
    _, item, intake = fixture(complete=complete, question=question, evidence=evidence)
    html = _native_opportunity_card(item, None, native_intake=intake)
    primary, _ = parts(html)
    assert all(label in primary for label in labels)
    assert 'KR-370 V2' not in primary and 'BUY NOW' not in html
    assert 'Current stage' in primary and 'Review' in primary


@pytest.mark.parametrize('count,unavailable,states,expected', [
    (5, None, ('OUTPERFORMING','OUTPERFORMING'), 'BUY NOW'),
    (4, None, ('OUTPERFORMING','OUTPERFORMING'), 'BUY READY'),
    (3, None, ('OUTPERFORMING','OUTPERFORMING'), 'HARD GATED'),
    (5, 3, ('OUTPERFORMING','OUTPERFORMING'), 'NOT EVALUABLE'),
    (5, None, ('UNDERPERFORMING','UNDERPERFORMING'), 'BUY READY'),
])
def test_v2_owning_outcomes_remain_exact(count, unavailable, states, expected):
    _, item, intake = fixture()
    record = promotion(item, count=count, unavailable=unavailable, states=states)
    html = _native_opportunity_card(item, None, native_intake=intake, promotions_v2=(record,))
    primary, detail = parts(html)
    assert expected in primary
    assert 'K1_1H_DIRECTIONAL_PROGRESSION' in detail and 'K5_NON_EXTENSION' in detail
    if states == ('UNDERPERFORMING','UNDERPERFORMING'):
        assert 'Confirmation · NSE 1D CONTRADICTORY' in primary
        assert 'Confirmation · NSE 4H CONTRADICTORY' in primary
    assert record.value['integrity_sha256'] not in html


@pytest.mark.parametrize('change', ['run','assessment','unavailable'])
def test_stale_or_wrong_intake_never_establishes_currentness(change):
    _, item, intake = fixture()
    row = intake['rows'][0]
    if change == 'run': row['run_identity'] = 'OTHER-RUN'
    elif change == 'assessment': row['assessment_sha256'] = 'f'*64
    else: row['expected'] = None
    primary, _ = parts(_native_opportunity_card(item, None, native_intake=intake))
    assert 'BINDING CURRENT' not in primary and 'BINDING UNAVAILABLE' in primary
    assert 'Review workspace unavailable' in primary


@pytest.mark.parametrize('status', list(NativeDiscoveryStatus))
def test_discovery_population_and_authority_do_not_expand(status):
    run, item, intake = fixture(status=status)
    run = replace(run, assessments=tuple(item if x.canonical_instrument == item.canonical_instrument else
        replace(x, status=NativeDiscoveryStatus.NO_CURRENT_OPPORTUNITY) for x in run.assessments), result_sha256='f'*64)
    html = render_opportunities(_ready(), run, native_intake=intake)
    assert html.count('<article class="opportunity native-opportunity">') == (1 if status is NativeDiscoveryStatus.PROBABLE else 0)
    if status is not NativeDiscoveryStatus.PROBABLE:
        assert 'No Native Probables' in html


def test_long_identifiers_and_accessible_scoped_disclosure():
    _, item, intake = fixture(symbol='SYMBOL-'+'X'*160)
    card = _native_opportunity_card(item, None, native_intake=intake)
    primary, detail = parts(card)
    assert item.canonical_instrument in primary and item.run_identity in detail
    assert item.result_sha256 in detail
    assert '<summary>WHY BLOCKED / ANALYSIS DETAILS</summary>' in card
    assert '<summary tabindex="-1"' not in card and 'role="button"' not in card
    page = render_opportunities(_ready())
    assert '.native-opportunity .swing-opportunity-details>summary:focus-visible' in page
    assert 'outline:2px solid var(--blue)' in page and 'overflow-wrap:anywhere' in page
    assert '@media(max-width:760px){.native-opportunity .swing-sponsor-summary' in page


@pytest.mark.parametrize('direction', ['LONG','SHORT'])
@pytest.mark.parametrize('market,symbol', [('NSE','INFY'),('MCX','GOLDM'),('MCX','SILVERM'),
    ('MCX','COPPER'),('MCX','CRUDEOIL'),('MCX','NATURALGAS')])
def test_directions_and_eligible_intake_do_not_create_v2(market,symbol,direction):
    _, item, intake = fixture(symbol=symbol,market=market,direction=direction,
                              complete=False,question=False,evidence='MISSING')
    primary,_ = parts(_native_opportunity_card(item,None,native_intake=intake))
    assert symbol in primary and direction in primary
    assert 'CHART MISSING' in primary and 'ANSWER MISSING' in primary
    assert 'BUY NOW' not in primary and 'SELL NOW' not in primary and 'KR-370 V2' not in primary


@pytest.mark.parametrize('direction,comparison', [('LONG','above'),('SHORT','below')])
def test_existing_governed_numeric_blockers_are_visible_before_details(tmp_path,direction,comparison):
    from types import SimpleNamespace
    from kronos.browser.swing_v3_presentation import present_v2_promotion
    from kronos.swing.v1.analytical_promotion_v2 import V2CriterionExplanation, V2ReadinessExplanation
    from kronos.validation.kr370 import Kr370CriterionState
    _, item, intake = fixture(direction=direction)
    s=source(direction=direction)
    s['native_run_identity'],s['native_assessment_sha256']=item.run_identity,item.result_sha256
    c=criteria(5,unavailable=1)
    c=tuple(replace(x,state=Kr370CriterionState.UNSATISFIED,
                    reason='COMPLETED_1H_CLOSE_NOT_ACCEPTED_BEYOND_CPR') if i==1 else x
            for i,x in enumerate(c))
    confirmation=nse(direction=direction)
    confirmation['nse_binding']['payload']['run_identity']=item.run_identity
    confirmation['nse_binding']['payload']['canonical_instrument']=item.canonical_instrument
    record=create_record(source=s,criteria=c,confirmation=confirmation,created_at=NOW)
    explanations=tuple(V2CriterionExplanation(x.identity.value,x.state.value,x.reason,
        'governed observed state','governed required state',
        (('Completed close',1025.90,'PRICE'),('CPR threshold',1021.20,'PRICE'),
         ('Gap to condition',4.70,'PRICE')) if i==1 else (), '1H',NOW,'next completed 1H')
        for i,x in enumerate(c))
    explanation=V2ReadinessExplanation(item.run_identity,item.canonical_instrument,
        item.result_sha256,record.value['promotion_state'],record.value['evaluation_disposition'],
        explanations,record.value['confirmation']['state'],())
    view=present_v2_promotion(record,explanation=explanation)
    visual=SimpleNamespace(run_identity=item.run_identity,canonical_instrument=item.canonical_instrument,
        native_assessment_sha256=item.result_sha256,kr370_v2=view,kr370=None,sponsor_status=view.disposition)
    primary,detail=parts(_native_opportunity_card(item,None,visual_v3=(visual,),native_intake=intake,
                                               promotions_v2=(record,)))
    assert f'completed 1H close {comparison} ₹1,021.20' in primary
    assert 'Last close ₹1,025.90' in primary and '₹4.70' in primary
    assert 'Completed close' in detail and 'CPR threshold' in detail


def test_export_offline_rendering_fixture(tmp_path):
    # Explicit caller-owned output only; product roots remain kernel-denied.
    target = os.environ.get('SWING_UX_FIXTURE_OUTPUT')
    if not target:
        return
    from kronos.browser.swing_v3_presentation import present_v2_promotion
    _, item, intake = fixture(symbol='INFY')
    record = promotion(item, count=3, unavailable=3, states=('UNDERPERFORMING','UNDERPERFORMING'))
    html = _native_opportunity_card(item, None, native_intake=intake, promotions_v2=(record,))
    _, run, _ = _evidence_run()
    # Use the actual page CSS and shell with this isolated truthful card.
    page = render_opportunities(_ready(), run)
    first = page.index('<article class="opportunity native-opportunity">')
    last = page.index('</article>',first)+len('</article>')
    page = page[:first]+html+page[last:]
    p=Path(target); p.parent.mkdir(parents=True,exist_ok=True);p.write_text(page)
    _,long_item,long_intake=fixture(symbol='SYMBOL-'+'X'*160,current=False,complete=False,
                                  question=False,evidence='MISSING')
    long_card=_native_opportunity_card(long_item,None,native_intake=long_intake)
    (p.parent/'long-unavailable-fixture.html').write_text(page[:first]+long_card+page[first+len(html):])

    # The actual legacy Intraday page producer consumes the same shared CSS.
    from kronos.application.intraday_discovery import IntradayDiscoveryApplication
    from kronos.application.intraday_probables import IntradayProbablesApplication
    from kronos.browser.intraday_routes import IntradayBrowserRoutes
    from kronos.browser.product_routes import BrowserGetRequest
    from kronos.intraday.probables import FactualSourceKind
    from kronos.intraday.probables_persistence import ProbablesStore
    from tests.unit.browser.test_product_route_isolation import _snapshot
    from tests.unit.intraday.test_discovery_runtime import BOUNDARY,_publications,_service
    from tests.unit.intraday.test_probables import SESSION,_member
    service,provider,store,_=_service(tmp_path/'discovery')
    universe,reconciliation=_publications()
    probables=IntradayProbablesApplication(store=ProbablesStore((tmp_path/'probables').resolve()))
    app=IntradayDiscoveryApplication(universe=universe,reconciliation=reconciliation,
                                    store=store,service=service,probables=probables)
    discovery=app.run_discovery(BOUNDARY)
    member=next(x for x in discovery.results if x.canonical_identity=='RELIANCE')
    evidence=replace(_member(boundary=BOUNDARY.observation_boundary),
        universe_member_identity=member.universe_member_identity,source_run_identity=discovery.run_identity,
        source_member_identity=member.persistence_identity)
    probables.refresh_analysis(source_kind=FactualSourceKind.NATIVE_DISCOVERY,
        source_run_identity=discovery.run_identity,universe_identity=universe.publication_identity,
        universe_version=universe.publication_version,reconciliation_identity=reconciliation.publication_identity,
        reconciliation_version=reconciliation.publication_version,market_session_identity=SESSION,
        observation_boundary=BOUNDARY.observation_boundary,member_evidence=(evidence,),
        unavailable_members=(),provenance=('SYNTHETIC-TEST-FIXTURE',))
    before=tuple(provider.labels)
    response=IntradayBrowserRoutes(app).handle_get(BrowserGetRequest('/intraday',{}),_snapshot)
    assert response.status.value==200
    assert tuple(provider.labels)==before
    assert 'opportunity native-opportunity intraday-probable' in response.body
    (p.parent/'intraday-fixture.html').write_text(response.body)


@pytest.mark.parametrize('market,symbol', [('NSE','INFY'),('MCX','GOLDM'),
    ('MCX','SILVERM'),('MCX','COPPER'),('MCX','CRUDEOIL'),('MCX','NATURALGAS')])
@pytest.mark.parametrize('count', [4,5])
def test_established_confirmation_is_evidence_not_a_pending_blocker(market,symbol,count):
    _,item,intake=fixture(symbol=symbol,market=market)
    record=promotion(item,market=market,count=count)
    before=deepcopy(record.value)
    assert record.value['confirmation']['state']=='ESTABLISHED'
    primary,detail=parts(_native_opportunity_card(item,None,native_intake=intake,promotions_v2=(record,)))
    reason='NSE BOTH HORIZONS SUPPORTIVE' if market=='NSE' else 'MCX REFERENCE CONFIRMED'
    assert reason not in primary
    assert reason in detail
    assert 'Confirmation ·' not in primary
    if count==4:
        assert 'E03 MATERIALLY EXTENDED' in primary
    else:
        assert 'Pending requirements' not in primary
    assert record.value==before
    if market=='MCX':
        assert 'DOWNSTREAM — MCX STEP-31 NOT COMMISSIONED' in primary


@pytest.mark.parametrize('market,options,states,reason', [
    ('NSE',{},('UNDERPERFORMING','UNDERPERFORMING'),'NSE 1D CONTRADICTORY'),
    ('NSE',{},('UNAVAILABLE','OUTPERFORMING'),'NSE 1D UNAVAILABLE'),
    ('NSE',{'validity':'MISSING'},('OUTPERFORMING','OUTPERFORMING'),'NSE CONTEXT MISSING'),
    ('MCX',{'m1':'UNDETERMINED'},('OUTPERFORMING','OUTPERFORMING'),'MCX MAPPING NOT MATCHED'),
    ('MCX',{'status':('UNAVAILABLE',)*3},('OUTPERFORMING','OUTPERFORMING'),'MCX COMPARISON UNAVAILABLE'),
])
def test_governed_withheld_or_unavailable_confirmation_remains_pending(market,options,states,reason):
    _,item,intake=fixture(symbol='INFY' if market=='NSE' else 'GOLDM',market=market)
    record=promotion(item,market=market,confirmation_options=options,states=states)
    before=deepcopy(record.value)
    assert record.value['confirmation']['state']=='WITHHELD'
    primary,detail=parts(_native_opportunity_card(item,None,native_intake=intake,promotions_v2=(record,)))
    assert 'Pending requirements' in primary
    assert 'Confirmation · '+reason in primary
    assert reason in detail
    assert record.value==before


def test_asset_class_exemption_is_not_a_pending_confirmation_blocker():
    from tests.unit.swing.v1.test_analytical_promotion_v2 import index
    _,item,intake=fixture(symbol='NIFTY')
    s=source(asset_class='NSE_INDEX',instrument=item.canonical_instrument)
    s['native_run_identity'],s['native_assessment_sha256']=item.run_identity,item.result_sha256
    record=create_record(source=s,criteria=criteria(4),confirmation=index(),created_at=NOW)
    primary,detail=parts(_native_opportunity_card(item,None,native_intake=intake,promotions_v2=(record,)))
    assert 'NOT REQUIRED BY ASSET CLASS' not in primary
    assert 'NOT REQUIRED BY ASSET CLASS' in detail
    assert 'E03 MATERIALLY EXTENDED' in primary


def test_new_narrow_action_rule_is_swing_contained():
    page=render_opportunities(_ready())
    rule='.native-opportunity .native-opportunity-actions .button{white-space:normal;overflow-wrap:anywhere}'
    assert '.swing-card-list '+rule in page
    assert page.count(rule)==1
