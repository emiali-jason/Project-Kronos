"""Synthetic retained-source presentation; no production or Provider evidence."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

import pytest

from kronos.browser.views import (
    render_opportunities, _analysis_status_time, _analysis_status_duration,
)
from tests.unit.browser.test_swing_local_analysis import (
    _admission_rig, _serving, _post, _admit_successor, _request, _inventory,
    _ADMISSION_WARNING,
)
from tests.unit.application.test_swing_opportunities import _ready
from tests.unit.swing.v1.test_nse_local_analysis import _case


class _Summary(HTMLParser):
    def __init__(self):
        super().__init__(); self.active = False; self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag == 'aside' and dict(attrs).get('class') == 'swing-analysis-execution':self.active = True
    def handle_endtag(self, tag):
        if tag == 'aside':self.active = False
    def handle_data(self, data):
        if self.active:self.parts.append(data)


def _source():
    _, native, _ = _case()
    start = native.observed_at + timedelta(minutes=2)
    end = start + timedelta(seconds=107)
    snapshot = replace(_ready(), swing_analysis_run_identity=native.run_identity,
        run_created_at=start, completed_at=end, observation_boundary=native.observed_at)
    publication = dict(control=dict(current_manifest={'sha256':'a'*64}, latest_attempt=dict(
        run_id=native.run_identity, state='SUCCEEDED', accepted_at=start.isoformat(),
        completed_at=end.isoformat(), predecessor_manifest=None, failure_reason=None)))
    return snapshot, native, publication


def _texts(snapshot, native, publication):
    html = render_opportunities(snapshot, native, publication_status=publication)
    parser = _Summary(); parser.feed(html)
    latest, successful = ' '.join(parser.parts).split('Latest successful analysis')
    return html, latest, successful


def test_success_uses_bound_native_assessments_and_actual_attempt_timestamps():
    snapshot, native, pub = _source()
    html, latest, success = _texts(snapshot, native, pub)
    assert 'Success · 1m 47s · 98 analysed' in latest
    assert _analysis_status_time(snapshot.observation_boundary) in latest
    assert _analysis_status_time(snapshot.completed_at) in latest
    assert native.run_identity in latest and native.run_identity in success
    assert 'LAST SUCCESSFUL ANALYSIS' in html
    assert 'Retained attempt timing' in latest


@pytest.mark.parametrize('state', ['FAILED', 'RUNNING', 'INTERRUPTED'])
def test_new_attempt_never_borrows_old_success_boundary_or_count(state):
    snapshot, native, pub = _source()
    attempt = pub['control']['latest_attempt']
    attempt.update(run_id='SWING-RUN-'+'C'*32, state=state,
        accepted_at=(snapshot.completed_at+timedelta(hours=1)).isoformat(),
        completed_at=None if state == 'RUNNING' else (snapshot.completed_at+timedelta(hours=1,seconds=107)).isoformat())
    _, latest, success = _texts(snapshot, native, pub)
    assert {'FAILED':'Failed','RUNNING':'Running','INTERRUPTED':'Interrupted'}[state] in latest
    assert '98 analysed' not in latest and '98 analysed' in success
    assert 'Boundary ·  Unavailable' in latest
    assert native.run_identity not in latest and native.run_identity in success
    if state == 'RUNNING':
        assert 'Completed ·  Unavailable' in latest
        assert 'Running · Unavailable · Unavailable' in latest
    else:assert '1m 47s' in latest


@pytest.mark.parametrize('missing', ['completion','started','boundary','native','run_binding','control'])
def test_missing_source_fields_remain_unavailable(missing):
    snapshot, native, pub = _source()
    if missing == 'completion':pub['control']['latest_attempt']['completed_at'] = None
    elif missing == 'started':pub['control']['latest_attempt']['accepted_at'] = None
    elif missing == 'boundary':snapshot = replace(snapshot, observation_boundary=None)
    elif missing == 'native':native = None
    elif missing == 'run_binding':snapshot = replace(snapshot, swing_analysis_run_identity='SWING-RUN-'+'D'*32)
    else:pub = {'control':None}
    _, latest, _ = _texts(snapshot, native, pub)
    assert 'Unavailable' in latest
    if missing in {'completion','started','control'}:assert '1m 47s' not in latest
    if missing in {'native','run_binding','control'}:assert '98 analysed' not in latest


@pytest.mark.parametrize('start,end,expected', [
    ('2026-10-16T09:12:13+00:00','2026-10-16T09:14:00+00:00','1m 47s'),
    ('2026-10-16T09:12:13+00:00','2026-10-16T14:44:00+05:30','1m 47s'),
    ('2026-10-16T09:12:13+00:00','2026-10-16T09:12:13.499999+00:00','0s'),
    ('2026-10-16T09:12:13+00:00','2026-10-16T09:12:13.500000+00:00','1s'),
    ('2026-10-16T09:12:13+00:00','2026-10-16T09:12:12+00:00','Unavailable'),
    (None,'2026-10-16T09:14:00+00:00','Unavailable'),
    ('2026-10-16T09:12:13',None,'Unavailable'),
])
def test_duration_is_exact_retained_timestamp_delta(start, end, expected):
    assert _analysis_status_duration(start, end) == expected


@pytest.mark.parametrize('value,expected', [
    ('2026-10-16T09:12:00+00:00','16 OCT 2026 14:42 IST'),
    ('2026-10-16T14:44:00+05:30','16 OCT 2026 14:44 IST'),
    ('2026-10-16T09:12:00','Unavailable'),(None,'Unavailable'),('invalid','Unavailable'),
])
def test_ist_format_matches_existing_display(value, expected):
    assert _analysis_status_time(value) == expected


def test_summary_does_not_use_configured_universe_for_analysed_count():
    snapshot, _, pub = _source()
    assert snapshot.universe_count == 98
    _, latest, _ = _texts(snapshot, None, pub)
    assert '98 analysed' not in latest


def test_status_summary_is_additive_and_preserves_existing_page_markup(monkeypatch):
    from kronos.browser import views
    snapshot, native, pub = _source()
    summary = views._swing_analysis_execution_summary(snapshot, native, pub)
    enhanced = render_opportunities(snapshot, native, publication_status=pub)
    monkeypatch.setattr(views, '_swing_analysis_execution_summary', lambda *a:'')
    original = render_opportunities(snapshot, native, publication_status=pub)
    assert enhanced.count(summary) == 1
    assert enhanced.replace(summary, '', 1) == original


@pytest.mark.parametrize('state', ['failed', 'unavailable'])
def test_capture_other_retained_states_for_responsive_verification(request, state):
    snapshot, native, pub = _source()
    if state == 'failed':
        pub['control']['latest_attempt'].update(run_id='SWING-RUN-'+'E'*32,
            state='FAILED', accepted_at=(snapshot.completed_at+timedelta(minutes=1)).isoformat(),
            completed_at=(snapshot.completed_at+timedelta(minutes=2)).isoformat())
    else:pub, native = {'control':None}, None
    html, latest, _ = _texts(snapshot, native, pub)
    assert 'Unavailable' in latest
    output = Path(request.config.getoption('xmlpath')).parent
    (output/('SYNTHETIC-'+state+'.html')).write_text(html)


@pytest.mark.parametrize('admitted', [False, True])
def test_real_browser_get_reuses_projection_without_writes_or_acquisition(tmp_path, monkeypatch, request, admitted):
    from kronos.application import swing_local_analysis as local_module
    rig = _admission_rig(tmp_path)
    with _serving(rig) as server:
        assert _post(server, rig)[0] == 303
        before = _inventory(rig.research.store.root)
        intake_before = _inventory(rig.intake.store.root)
        if admitted:_admit_successor(rig)
        def forbidden(*a, **k):pytest.fail('Status GET acquired, evaluated, scanned or wrote')
        monkeypatch.setattr(rig.application, 'run_analysis', forbidden)
        monkeypatch.setattr(rig.application, 'authenticated_read_only_capability', forbidden)
        monkeypatch.setattr(rig.research.store, 'records', forbidden)
        monkeypatch.setattr(rig.research.store, 'retain', forbidden)
        monkeypatch.setattr(local_module, 'analyze_local', forbidden)
        status, _, html = _request(server, 'GET', '/swing/opportunities')
        assert status == 200 and 'Latest retained analysis attempt' in html
        if admitted:
            assert _ADMISSION_WARNING in html
            assert 'Running · Unavailable · Unavailable' in html
            assert 'Immutable original identity and timestamps' not in html
        else:assert 'Success' in html and 'Independent local analysis' in html
        assert _inventory(rig.research.store.root) == before
        assert _inventory(rig.intake.store.root) == intake_before
        output = Path(request.config.getoption('xmlpath')).parent
        (output/('SYNTHETIC-running.html' if admitted else 'SYNTHETIC-success.html')).write_text(html)
