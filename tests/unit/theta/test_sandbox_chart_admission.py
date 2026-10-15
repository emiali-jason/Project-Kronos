"""TE-01R scoped sandbox admission; synthetic evidence and no Provider access."""

from datetime import timedelta
from http.client import HTTPConnection
from io import BytesIO
import json
from pathlib import Path
import shutil

from PIL import Image, ImageDraw
import pytest

from kronos.theta.contracts import SUBJECTS, digest
from kronos.theta.store import ThetaStore
from kronos.theta.workflow import CHART_ROLES, ThetaWorkflow
from tests.unit.theta.test_chart_intake import image, inventory, path, receive, role
from tests.unit.theta.test_question_packs import composite, complete_answer
from tests.unit.theta.test_rehearsal import running
from tests.unit.theta.test_workflow import NOW, authority, place

REPOSITORY = Path(__file__).resolve().parents[3]
from tests.unit.theta import sandbox_admission_fixture as sandbox


@pytest.fixture(scope='module')
def seed(tmp_path_factory):
    directory = tmp_path_factory.mktemp('te01r-seed').resolve()
    workflow = ThetaWorkflow(ThetaStore(directory / 'evidence'), inbox=directory / 'answers',
        outbox=directory / 'questions', authority_provider=authority, clock=lambda: NOW,
        qualification_mode=True)
    workflow.inbox.mkdir()
    for subject in CHART_ROLES:
        receive(workflow, subject, payload=composite(subject))
    result = workflow.commission_questions(SUBJECTS)
    workflow.clock = lambda: NOW + timedelta(hours=3)
    for entry in result['states'].values():
        q = workflow.store.question(entry['question_id'])
        place(workflow, q['question_id'], complete_answer(workflow, q))
        workflow.import_answer(q['question_id'])
    assert all(r['status'] == 'ACCEPTED_EXTERNAL_EVIDENCE' for r in workflow.summary())
    return workflow


@pytest.fixture
def populated(seed, tmp_path):
    directory = tmp_path.resolve() / 'copy'
    shutil.copytree(seed.store.root.parent, directory)
    return ThetaWorkflow(ThetaStore(directory / 'evidence'), inbox=directory / 'answers',
        outbox=directory / 'questions', authority_provider=authority, clock=seed.clock,
        qualification_mode=True)


def request(server, method, address, payload=b'', media='image/png',
            origin='EXACT', host='EXACT', declared_length=None):
    authority = '127.0.0.1:' + str(server.server_port)
    headers = {'Host': authority if host == 'EXACT' else host, 'Content-Type': media}
    if origin is not None:
        headers['Origin'] = 'http://' + authority if origin == 'EXACT' else origin
    if declared_length is not None:
        headers['Content-Length'] = str(declared_length)
    connection = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
    try:
        connection.request(method, address, body=payload, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def scoped(server):
    server.RequestHandlerClass = sandbox.chart_intake_handler(server.RequestHandlerClass)
    server.service_actions = lambda: None


@pytest.mark.parametrize('subject', CHART_ROLES)
@pytest.mark.parametrize('format,media', [('PNG', 'image/png'), ('JPEG', 'image/jpeg')])
def test_scoped_http_replacement_exact_bytes_role_local_question_stale_restart(populated, subject, format, media):
    before = populated.chart_workspace()
    retained = inventory(populated)
    old = role(populated, subject)
    questions = {r['subject']: r['question_id'] for r in populated.summary()}
    payload = image(format, color='blue')
    with running(populated) as server:
        scoped(server)
        status, body = request(server, 'POST', path(old), payload, media)
        assert status == 200 and json.loads(body)['outcome'] == 'CHART_RECEIVED'
        current = role(populated, subject)
        assert current['revision_id'] != old['revision_id']
        assert current['chart']['sha256'] == digest(payload) != old['chart']['sha256']
        assert current['intake']['previous_revision_id'] == old['revision_id']
        assert current['intake']['byte_length'] == len(payload)
        assert current['intake']['media_type'] == media
        assert populated.chart_bytes(old['chart']['sha256']) == composite(subject)
        assert populated.preview_chart(subject=subject, cycle_id=current['cycle_id'],
            revision_id=current['revision_id']) == (media, payload)
        assert [c for c in populated.chart_workspace()['cards'] if c['subject'] != subject] == [
            c for c in before['cards'] if c['subject'] != subject]
        rows = populated.summary()
        affected = SUBJECTS if subject == 'GLOBAL_MACRO' else (subject,)
        assert all(r['status'] != 'ACCEPTED_EXTERNAL_EVIDENCE' for r in rows if r['subject'] in affected)
        assert all(r['question_id'] == questions[r['subject']] and r['status'] == 'ACCEPTED_EXTERNAL_EVIDENCE'
            for r in rows if r['subject'] not in affected)
        assert request(server, 'POST', path(old), payload, media)[0] == 409
        assert request(server, 'GET', path(old, 'chart-preview'))[0] == 409
    assert all(inventory(populated)[p] == content for p, content in retained.items() if p != 'current.json')
    restored = ThetaWorkflow(ThetaStore(populated.store.root), inbox=populated.inbox,
        outbox=populated.outbox, authority_provider=authority, clock=populated.clock, qualification_mode=True)
    assert restored.chart_workspace() == populated.chart_workspace()
    assert restored.summary() == populated.summary()


@pytest.mark.parametrize('origin,host', [('http://foreign.invalid', 'EXACT'),
    (None, 'EXACT'), ('http://localhost:8948', 'EXACT'), ('EXACT', 'foreign.invalid')])
def test_scoped_origin_and_host_fail_closed(populated, origin, host):
    before = inventory(populated)
    with running(populated) as server:
        scoped(server)
        assert request(server, 'POST', path(role(populated, 'COPPER')), image(),
            origin=origin, host=host)[0] == 403
    assert inventory(populated) == before


@pytest.mark.parametrize('method,address', [('POST', '/theta-earners/question'),
    ('POST', '/theta-earners/import'), ('POST', '/intraday/analysis'),
    ('POST', '/swing/analysis'), ('POST', '/control/shutdown'),
    ('POST', '/theta-earners/chart/'), ('POST', '/theta-earners/%63hart'),
    ('POST', '/theta-earners/../chart'), ('PUT', '/theta-earners/chart'),
    ('PATCH', '/theta-earners/chart'), ('DELETE', '/theta-earners/chart')])
def test_scoped_other_mutations_blocked(populated, method, address):
    before = inventory(populated)
    with running(populated) as server:
        scoped(server)
        assert request(server, method, address, b'SYNTHETIC_INVALID')[0] == 405
    assert inventory(populated) == before


@pytest.mark.parametrize('payload,media', [(b'text', 'image/png'), (image(), 'image/jpeg'),
    (b'\x89PNG\r\n\x1a\ntruncated', 'image/png'), (image(), 'image/webp'), (b'', 'image/png')])
def test_scoped_invalid_input_preserves_selection(populated, payload, media):
    before = inventory(populated)
    with running(populated) as server:
        scoped(server)
        assert request(server, 'POST', path(role(populated, 'GLOBAL_MACRO')), payload, media)[0] == 409
    assert inventory(populated) == before


def test_scoped_retains_shared_admission_and_body_bound(populated):
    before = inventory(populated)
    with running(populated) as server:
        scoped(server)
        address = path(role(populated, 'COPPER'))
        assert request(server, 'POST', address, b'x', declared_length=26 * 1024 * 1024)[0] == 413
        original = server.admit_sponsor_work
        server.admit_sponsor_work = lambda: False
        assert request(server, 'POST', address, image())[0] == 503
        server.admit_sponsor_work = original
    assert inventory(populated) == before


def test_synthetic_browser_assets_and_retained_baseline(populated, tmp_path):
    """Emit exact, visibly synthetic source images for real keyboard/file tests."""
    # PLC-01 qualification is self-contained. Never inspect the protected 8948
    # store or depend on prior operational output to satisfy this regression.
    output = tmp_path / 'synthetic-assets'
    output.mkdir()
    manifest = {}
    for subject in CHART_ROLES:
        canvas = Image.open(BytesIO(composite(subject))).convert('RGB')
        ImageDraw.Draw(canvas).text((40, 12), 'TE-01R REPLACEMENT / SYNTHETIC / ' + subject,
            fill='#B40030')
        for format, extension, media in [('PNG', 'png', 'image/png'), ('JPEG', 'jpg', 'image/jpeg')]:
            stream = BytesIO()
            canvas.save(stream, format=format)
            binary = stream.getvalue()
            filename = 'SYNTHETIC_TE01R_' + subject + '.' + extension
            (output / filename).write_bytes(binary)
            manifest[filename] = {'sha256': digest(binary), 'bytes': len(binary), 'media_type': media}
    (output / 'synthetic-assets.json').write_text(json.dumps(manifest, indent=2) + '\n')
    assert len(manifest) == 12
    # This observation is read-only. Never seed or change the retained store here.
    directory = populated.store.root.parent
    workflow = ThetaWorkflow(ThetaStore(directory / 'evidence'), inbox=directory / 'answers',
        outbox=directory / 'questions', clock=lambda: NOW + timedelta(hours=3), qualification_mode=True)
    report = {'workspace': workflow.chart_workspace(), 'summary': workflow.summary(),
        'inventory': {p: digest(data) for p, data in inventory(workflow).items()}}
    target = output / 'retained-before-repair.json'
    if not target.exists():  # Preserve the first observed baseline across test reruns.
        target.write_text(json.dumps(report, indent=2) + '\n')
    assert len(report['workspace']['cards']) == 6
