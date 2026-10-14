"""Slice 4 presentation consumes immutable Reports projections, never owners."""
from dataclasses import replace
from html import unescape
import json
import re
import pytest
from kronos.browser.reports import (ReportsQuery, ReportProduct, ReportView, _coverage,
                                   export_reports_csv, export_reports_json, export_reports_xlsx)
from kronos.browser.views import render_reports
from kronos.swing.v1.native_sponsor_decision import SponsorTradeChoice
from kronos.swing.v1.mcx_contract_profile import McxFamily
from tests.unit.application.test_swing_opportunities import _ready
from tests.unit.browser.test_swing_reports_wo16 import history, project, NOW
from tests.unit.browser.test_wo14_mcx_journal_integration import fixture


def rendered(projection):
    return render_reports(_ready(), projection)


def raw_coverage(html):
    block = re.search(r'<details class="reports-coverage-audit"><summary>VIEW GOVERNED COVERAGE DETAILS</summary><pre>(.*?)</pre></details>', html, re.S)
    assert block is not None
    return unescape(block[1])


def test_retained_three_two_shape_discloses_missing_without_inventing_trades(tmp_path):
    window, native, _ = history(tmp_path, tuple(SponsorTradeChoice))
    p = project(window, native); h = rendered(p)
    assert 'Filtered records: <strong>3</strong>' in h
    assert 'V1 source records · before filters</dt><dd>3' in h
    assert 'V2 source records · before filters</dt><dd>2' in h
    assert 'Missing V2 relationships · filtered</dt><dd>1' in h
    assert 'WARNING: 1 filtered historical record(s) have no V2 relationship' in h
    assert 'does not certify operational readiness' in h
    assert '<span>Paper</span><strong>0' in h and '<span>Live</span><strong>0' in h
    assert '<span>Gross P/L</span><strong>UNAVAILABLE' in h
    assert 'Costs and net P/L are UNKNOWN' in h
    assert raw_coverage(h) == json.dumps(_coverage(p), sort_keys=True, indent=2)


@pytest.mark.parametrize('family', list(McxFamily))
@pytest.mark.parametrize('mixed', [False, True])
def test_all_families_and_mixed_population_preserve_exact_records_and_exports(tmp_path, family, mixed):
    window, native, _ = history(tmp_path/'history', choices=(SponsorTradeChoice.PAPER,) if mixed else ())
    control, position, instrument, plan = fixture(tmp_path/'mcx', family, active=True)
    p = project(window, native, control)
    before = (export_reports_csv(p), export_reports_json(p), export_reports_xlsx(p, generated_at=NOW))
    h = rendered(p)
    assert family.value + '</dt><dd>1' in h and plan.contract_symbol in h
    assert 'MCX · family-resolved</dt><dd>1' in h
    assert ('NSE</dt><dd>1' if mixed else 'NSE</dt><dd>0') in h
    assert raw_coverage(h) == json.dumps(_coverage(p), sort_keys=True, indent=2)
    assert before == (export_reports_csv(p), export_reports_json(p), export_reports_xlsx(p, generated_at=NOW))
    assert p.records[0].pnl is None


def test_generic_historical_mcx_remains_unresolved_and_never_allocated(tmp_path):
    window, native, _ = history(tmp_path); p = project(window, native)
    # Labelled projection fixture; actual retained source reproduced separately.
    row = replace(p.records[0], market='UNRESOLVED', contract_family='UNRESOLVED', instrument='MCX')
    p = replace(p, records=(row,), page_records=(row,)); h = rendered(p)
    assert 'Historical MCX · UNRESOLVED</dt><dd>1' in h
    assert 'MCX family and exact future UNRESOLVED' in h
    for family in McxFamily: assert family.value + '</dt><dd>0' in h
    assert 'No family-resolved MCX records in this filtered population' in h
    assert raw_coverage(h) == json.dumps(_coverage(p), sort_keys=True, indent=2)


def test_filters_do_not_mislabel_retained_source_counts(tmp_path):
    window, native, _ = history(tmp_path, tuple(SponsorTradeChoice))
    p = project(window, native, query=ReportsQuery(view=ReportView.PAPER))
    assert p.records == (); h = rendered(p)
    assert 'Filtered records: <strong>0</strong> · VALID_EMPTY' in h
    assert 'V1 source records · before filters</dt><dd>3' in h
    assert 'V2 source records · before filters</dt><dd>2' in h
    assert 'Missing V2 relationships · filtered</dt><dd>0' in h
    assert 'WARNING:' not in h


@pytest.mark.parametrize('state', ['OWNER_NOT_INSTALLED', 'UNAVAILABLE', 'UNKNOWN'])
def test_unavailable_authority_is_visible_and_not_counted_as_valid_empty(tmp_path, state):
    window, native, _ = history(tmp_path, choices=()); p = project(window, native)
    p = replace(p, coverage=(('V1', state, 0), ('MCX_PLANS', state, 0))); h = rendered(p)
    assert 'V1 source records · before filters</dt><dd>' + state + ' — count UNAVAILABLE' in h
    assert 'V2 source records · before filters</dt><dd>UNAVAILABLE' in h
    assert 'MCX plans: ' + state in h
    assert raw_coverage(h) == json.dumps(_coverage(p), sort_keys=True, indent=2)


def test_valid_empty_sources_and_complete_relationships_have_no_false_warning(tmp_path):
    window, native, _ = history(tmp_path, choices=()); p = project(window, native); h = rendered(p)
    assert 'Step-33 history: VALID_EMPTY' in h
    assert 'MCX plans: OWNER_NOT_INSTALLED' in h and 'MCX positions: OWNER_NOT_INSTALLED' in h
    assert 'VALID_EMPTY' in h and 'WARNING:' not in h
    window, native, _ = history(tmp_path/'complete', choices=(SponsorTradeChoice.PAPER,))
    h = rendered(project(window, native))
    assert 'Missing V2 relationships · filtered</dt><dd>0' in h and 'WARNING:' not in h


def test_installed_valid_empty_mcx_sources_remain_explicit(tmp_path):
    window, native, _ = history(tmp_path/'history', choices=())
    control, position, instrument, plan = fixture(tmp_path/'mcx', McxFamily.CRUDEOIL)
    from kronos.swing.v1.native_active_trade_lifecycle import ActiveTradeLifecycleService, LocalActiveTradeLifecycleStore
    from kronos.swing.v1.mcx_trade_plan import LocalMcxTradePlanStore
    control.lifecycle = ActiveTradeLifecycleService(LocalActiveTradeLifecycleStore(tmp_path/'empty-lifecycle'))
    control.plans = LocalMcxTradePlanStore(tmp_path/'empty-plans')
    h = rendered(project(window, native, control))
    assert 'MCX plans: VALID_EMPTY' in h and 'MCX positions: VALID_EMPTY' in h


def test_long_identifiers_and_disclosure_are_escaped_and_locally_scoped(tmp_path):
    window, native, _ = history(tmp_path); p = project(window, native)
    p = replace(p, coverage=p.coverage + (('LONG-<' + 'x'*400, 'UNAVAILABLE', 0),)); h = rendered(p)
    assert 'LONG-&lt;' in h and 'LONG-<' not in h
    assert '<details class="reports-coverage-audit" open' not in h
    assert '.reports-coverage summary:focus-visible' in h
    assert '.reports-coverage .reports-coverage-grid' in h
    assert raw_coverage(h) == json.dumps(_coverage(p), sort_keys=True, indent=2)


def test_intraday_renderer_has_no_swing_coverage_markup_or_new_styles(tmp_path):
    window, native, _ = history(tmp_path, choices=()); p = project(window, native)
    p = replace(p, query=ReportsQuery(product=ReportProduct.INTRADAY)); h = rendered(p)
    assert 'reports-coverage-grid' not in h and 'VIEW GOVERNED COVERAGE DETAILS' not in h
    assert 'Factual one-lot model records' in h
