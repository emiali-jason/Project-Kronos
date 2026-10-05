"""Isolated explicit authority, provenance and advancing factual-clock checks."""
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from kronos.application.swing_research_authority import ResearchReleaseVerifier, import_official_actions
from kronos.application.swing_nse_equity_basis import NseEquityBasisStore, NseEquityActionReport
from kronos.application.swing_research_inbox import SwingResearchInbox
from tests.unit.application.test_swing_research_worker import _control
from tests.unit.application.test_swing_prospective_research_wo12 import _app, _calendar, _fetch
from tests.unit.swing.v1.test_prospective_research_wo12 import _origin, _milestone, _sessions

AT = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
CSV = b"SYMBOL,SERIES,PURPOSE,EX-DATE\n"


def actions():
    # A verified special-session close at 15:30 IST, not the removed 16:00 guess.
    calendar = SimpleNamespace(publication=lambda _: SimpleNamespace(
        coverage_start=date(2026, 9, 29), coverage_end=date(2026, 10, 1),
        source_boundary=AT-timedelta(days=2), trading_dates=(date(2026, 10, 1),),
        calendar_identity="ISOLATED-CALENDAR", publication_sha256="a"*64, calendar_version="1"),
        schedule=lambda *a, **k: SimpleNamespace(windows=(SimpleNamespace(
            window_open=AT-timedelta(hours=6), window_close=AT),)))
    fields = dict(symbol="RELIANCE", series="EQ", coverage_start="2026-09-29",
        coverage_end="2026-10-01", source_url="https://www.nseindia.com/companies-listing/corporate-filings-actions",
        source_sha256=sha256(CSV).hexdigest(), all_results_row_count=0,
        capture_identity="CAPTURE-ONE", captured_at=AT.isoformat(),
        attested_by="ISOLATED-SPONSOR", attested_at=AT.isoformat(),
        all_results=True, purpose_filter="ALL")
    return calendar, fields


def test_original_bytes_attestation_session_and_import_replay(tmp_path):
    calendar, fields = actions()
    store = NseEquityBasisStore(tmp_path/'basis')
    identity = import_official_actions(store, calendar, fields, CSV, received_at=AT+timedelta(seconds=2))
    before = (store.root/(identity+'.json')).read_bytes()
    assert import_official_actions(store, calendar, fields, CSV, received_at=AT+timedelta(days=1)) == identity
    assert (store.root/(identity+'.json')).read_bytes() == before
    value = json.loads(before)['material']
    import base64
    assert base64.b64decode(value['csv_base64']) == CSV
    assert value['attestation']['received_at'] == (AT+timedelta(seconds=2)).isoformat()
    assert store.basis('RELIANCE', 'EQ', date(2026,9,29),date(2026,10,1))[0] == 'VERIFIED_NO_ACTION'
    with pytest.raises(ValueError, match='CAPTURE_CONFLICT'):
        import_official_actions(store, calendar, {**fields, 'attested_by':'OTHER'}, CSV, received_at=AT)


@pytest.mark.parametrize('field,value', [('source_sha256','b'*64),('series','BE'),
    ('all_results',False),('purpose_filter','BONUS'),('all_results_row_count',1),
    ('attested_by',''),('captured_at',(AT-timedelta(seconds=1)).isoformat())])
def test_invalid_attestation_never_writes(tmp_path, field, value):
    calendar, fields = actions()
    store = NseEquityBasisStore(tmp_path/'basis')
    with pytest.raises(ValueError):
        import_official_actions(store, calendar, {**fields,field:value}, CSV, received_at=AT)
    assert not store.root.exists()


def test_legacy_boolean_and_missing_calendar_are_not_authority(tmp_path):
    calendar, fields = actions()
    store = NseEquityBasisStore(tmp_path/'basis')
    store.retain(NseEquityActionReport('RELIANCE','EQ',date(2026,9,29),date(2026,10,1),
                 AT, fields['source_url'], CSV,0,True))
    assert store.basis('RELIANCE','EQ',date(2026,9,29),date(2026,10,1)) == ('UNKNOWN',None)
    with pytest.raises(ValueError):
        import_official_actions(store, None, fields, CSV, received_at=AT)


def release(tmp_path, path_name='src/owner.py'):
    root=tmp_path/'source'; root.mkdir()
    def git(*args):
        return subprocess.check_output(['git','-C',str(root),*args]).decode().strip()
    git('init'); git('config','user.email','isolated@example.invalid'); git('config','user.name','Isolated')
    path=root/path_name; path.parent.mkdir(parents=True); path.write_text('VALUE = 1\n')
    git('add','.'); git('commit','-m','isolated base'); base=git('rev-parse','HEAD')
    path.write_text('VALUE = 2\n'); git('add','.')
    manifest=json.dumps(dict(direct_base_commit=base,path_count=1,
        paths=[dict(path=path_name,candidate_sha256=sha256(path.read_bytes()).hexdigest())])).encode()
    digest=sha256(manifest).hexdigest()
    git('commit','-m','isolated release\n\nWO12-Source-Manifest-SHA256: '+digest)
    head=git('rev-parse','HEAD')
    return root, head, manifest, digest


def test_authentic_approved_34_path_release_includes_canonical_startup_tool(tmp_path):
    """Original signed manifest and real blobs, not an illustrative one-row release."""
    repository = Path(__file__).resolve().parents[3]
    original = (repository/'tests/fixtures/swing_research/approved_wo12_34_path_manifest.json').read_bytes()
    digest = 'aaa2267958e12dfa8b7bd25e2d803b19f55ed932f480bd2a4f67f8c89b2182bb'
    head = '35f9694bb2b1868f8e0f619b6f61551efcf3049e'
    assert sha256(original).hexdigest() == digest
    assert json.loads(original)['path_count'] == 34
    root = tmp_path/'authentic-release'
    subprocess.run(['git', 'clone', '--shared', '--no-checkout', str(repository), str(root)], check=True)
    subprocess.run(['git', '-C', str(root), 'checkout', '--detach', head], check=True)
    proof = ResearchReleaseVerifier(root, lambda: head).verify(head, original, digest)
    assert proof == dict(release_identity=head, source_manifest_sha256=digest,
                         verified_paths=34, base_commit=json.loads(original)['direct_base_commit'])
    revisions = iter((head, 'a'*40))
    with pytest.raises(ValueError, match='RELEASE_DRIFT'):
        ResearchReleaseVerifier(root, lambda: next(revisions)).verify(head, original, digest)


def test_exact_startup_tool_commissions_once_and_retains_bound_receipt(tmp_path):
    root, head, manifest, digest = release(tmp_path, 'tools/kronos_browser.py')
    control = _control(tmp_path, inbox=SwingResearchInbox(tmp_path/'inbox'))
    control.release_verifier = ResearchReleaseVerifier(root, lambda: head)
    control.application.committed_research_replay_history = lambda: ()
    try:
        receipt = control.commission(release_identity=head, source_manifest_sha256=digest,
                                     manifest_bytes=manifest)
        assert receipt.data['release_identity'] == head
        assert receipt.data['source_manifest_sha256'] == digest
        assert control.commission(release_identity=head, source_manifest_sha256=digest,
                                 manifest_bytes=manifest) == receipt
        assert control.research.store.records('COMMISSIONING') == (receipt,)
    finally:
        control.close()


@pytest.mark.parametrize('path_name', ['tools/owner.py', 'tools/kronos_browser.py.backup',
                                      'tools/nested/kronos_browser.py'])
def test_other_tools_paths_are_not_release_authority(tmp_path, path_name):
    root, head, manifest, digest = release(tmp_path, path_name)
    with pytest.raises(ValueError, match='RELEASE_PATH_INVALID'):
        ResearchReleaseVerifier(root, lambda: head).verify(head, manifest, digest)


@pytest.mark.parametrize('change', ['loaded', 'requested', 'manifest_hash', 'trailer',
                                   'scope', 'committed_hash', 'untracked', 'staged'])
def test_startup_tool_exception_preserves_release_identity_and_scope_checks(tmp_path, change):
    root, head, manifest, digest = release(tmp_path, 'tools/kronos_browser.py')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args]).decode().strip()
    loaded = head
    error = 'RELEASE_DRIFT'
    if change == 'loaded':
        loaded = 'a'*40
    elif change == 'requested':
        head = 'a'*40
    elif change == 'manifest_hash':
        digest = 'a'*64; error = 'RELEASE_INVALID'
    elif change == 'trailer':
        git('commit', '--amend', '-m', 'isolated missing trailer')
        head = loaded = git('rev-parse', 'HEAD'); error = 'MANIFEST_UNATTESTED'
    elif change in {'scope', 'committed_hash'}:
        value = json.loads(manifest)
        if change == 'scope':
            value['paths'][0]['path'] = 'src/foreign.py'; error = 'SCOPE_INVALID'
        else:
            value['paths'][0]['candidate_sha256'] = 'a'*64; error = 'BYTES_INVALID'
        manifest = json.dumps(value).encode(); digest = sha256(manifest).hexdigest()
        git('commit', '--amend', '-m', 'isolated changed manifest\n\nWO12-Source-Manifest-SHA256: '+digest)
        head = loaded = git('rev-parse', 'HEAD')
    elif change == 'untracked':
        (root/'unexpected').write_text('unexpected')
    else:
        (root/'tools/kronos_browser.py').write_text('CHANGED = True\n')
        git('add', '.')
    with pytest.raises(ValueError, match=error):
        ResearchReleaseVerifier(root, lambda: loaded).verify(head, manifest, digest)


@pytest.mark.parametrize('bad_path', ['/tools/kronos_browser.py',
    'tools/../tools/kronos_browser.py', 'tools//kronos_browser.py'])
def test_startup_tool_exception_rejects_absolute_traversal_and_noncanonical_paths(tmp_path, monkeypatch, bad_path):
    root, head, manifest, digest = release(tmp_path, 'tools/kronos_browser.py')
    value = json.loads(manifest); value['paths'][0]['path'] = bad_path
    manifest = json.dumps(value).encode(); digest = sha256(manifest).hexdigest()
    subprocess.run(['git', '-C', str(root), 'commit', '--amend', '-m',
                    'isolated malformed path\n\nWO12-Source-Manifest-SHA256: '+digest], check=True)
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD']).decode().strip()
    original = subprocess.check_output
    # Scope is checked independently above. Reach path validation with an
    # adversarial scope response; no malformed path is read or admitted.
    def observed(command, **kwargs):
        if command[3:5] == ['diff', '--name-only']:
            return (bad_path+'\n').encode()
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, 'check_output', observed)
    with pytest.raises(ValueError, match='PATH_INVALID'):
        ResearchReleaseVerifier(root, lambda: head).verify(head, manifest, digest)


@pytest.mark.parametrize('symlink', ['file', 'parent'])
def test_exact_startup_tool_rejects_symlink_and_disk_substitution(tmp_path, monkeypatch, symlink):
    root, head, manifest, digest = release(tmp_path, 'tools/kronos_browser.py')
    outside = tmp_path/'outside'; outside.mkdir()
    data = root/'tools/kronos_browser.py'
    (outside/'kronos_browser.py').write_bytes(data.read_bytes())
    data.unlink()
    if symlink == 'file':
        data.symlink_to(outside/'kronos_browser.py')
    else:
        (root/'tools').rmdir(); (root/'tools').symlink_to(outside, target_is_directory=True)
    original = subprocess.check_output
    def clean_observation(command, **kwargs):
        if command[3:4] == ['status']:
            return b''
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, 'check_output', clean_observation)
    with pytest.raises(ValueError, match='PATH_INVALID'):
        ResearchReleaseVerifier(root, lambda: head).verify(head, manifest, digest)


def test_startup_tool_rejects_disk_change_after_clean_status_observation(tmp_path, monkeypatch):
    root, head, manifest, digest = release(tmp_path, 'tools/kronos_browser.py')
    original = subprocess.check_output
    def changed_after_status(command, **kwargs):
        result = original(command, **kwargs)
        if command[3:4] == ['status']:
            (root/'tools/kronos_browser.py').write_text('CHANGED_AFTER_OBSERVATION = True\n')
        return result
    monkeypatch.setattr(subprocess, 'check_output', changed_after_status)
    with pytest.raises(ValueError, match='BYTES_INVALID'):
        ResearchReleaseVerifier(root, lambda: head).verify(head, manifest, digest)


def test_startup_tool_rechecks_git_head_after_blob_reads(tmp_path, monkeypatch):
    root, head, manifest, digest = release(tmp_path, 'tools/kronos_browser.py')
    original = subprocess.check_output
    def advanced_after_blob(command, **kwargs):
        result = original(command, **kwargs)
        if command[3:] == ['show', head+':tools/kronos_browser.py']:
            original(['git', '-C', str(root), 'commit', '--amend', '-m',
                      'isolated concurrent release\n\nWO12-Source-Manifest-SHA256: '+digest])
        return result
    monkeypatch.setattr(subprocess, 'check_output', advanced_after_blob)
    with pytest.raises(ValueError, match='RELEASE_DRIFT'):
        ResearchReleaseVerifier(root, lambda: head).verify(head, manifest, digest)


def test_real_release_verifier_rejects_loaded_identity_scope_and_bytes_drift(tmp_path):
    root, head, manifest, digest=release(tmp_path)
    verifier=ResearchReleaseVerifier(root,lambda:head)
    assert verifier.verify(head,manifest,digest)['verified_paths']==1
    with pytest.raises(ValueError): ResearchReleaseVerifier(root,lambda:'a'*40).verify(head,manifest,digest)
    with pytest.raises(ValueError): verifier.verify(head,manifest,'a'*64)
    (root/'src/owner.py').write_text('VALUE = 3\n')
    with pytest.raises(ValueError): verifier.verify(head,manifest,digest)


@pytest.mark.parametrize('nonempty', ['inbox','unknown','candle','population','clean'])
def test_commission_once_empty_population_inbox_restart_and_replay(tmp_path, nonempty):
    root, head, manifest, digest=release(tmp_path)
    inbox=SwingResearchInbox(tmp_path/'inbox')
    control=_control(tmp_path,inbox=inbox)
    control.release_verifier=ResearchReleaseVerifier(root,lambda:head)
    control.application.committed_research_replay_history=lambda:()
    if nonempty=='inbox': inbox.retain('OWNER','one',{})
    if nonempty=='unknown': control.research.store.root.mkdir(); (control.research.store.root/'unknown').write_text('x')
    if nonempty in {'candle','population'}:
        from kronos.swing.v1.prospective_research import record
        control.research.store.retain(record('CANDLE' if nonempty=='candle' else 'ORIGIN', fixture='x'))
    try:
        if nonempty!='clean':
            with pytest.raises(ValueError, match='NOT_EMPTY'):
                control.commission(release_identity=head,source_manifest_sha256=digest,manifest_bytes=manifest)
            assert control.research.store.records('COMMISSIONING')==()
        else:
            receipt=control.commission(release_identity=head,source_manifest_sha256=digest,manifest_bytes=manifest)
            contents={str(p): (p.read_bytes(),p.stat().st_mtime_ns) for p in tmp_path.rglob('*') if p.is_file()}
            assert control.commission(release_identity=head,source_manifest_sha256=digest,manifest_bytes=manifest)==receipt
            assert contents=={str(p): (p.read_bytes(),p.stat().st_mtime_ns) for p in tmp_path.rglob('*') if p.is_file()}
            control.close(); control=_control(tmp_path,inbox=inbox)
            control.release_verifier=ResearchReleaseVerifier(root,lambda:head)
            assert control.commission(release_identity=head,source_manifest_sha256=digest,manifest_bytes=manifest)==receipt
    finally: control.close()


@pytest.mark.parametrize('market', ['NSE','GOLDM','SILVERM','COPPER','CRUDEOIL','NATURALGAS'])
def test_fixed_cutoff_actual_publication_completion_and_replay_times(tmp_path, market):
    app=_app(tmp_path)
    source=_origin(market,identity='TIME-'+market,expiry=None if market=='NSE' else date(2026,10,20))
    app.capture_admitted(source,_milestone(source,4))
    cutoff=_sessions(market)[0].closes_at+timedelta(minutes=2)
    now=[cutoff]
    app.clock=lambda:now[0]
    def fetch(contract,session):
        from dataclasses import replace
        now[0]+=timedelta(seconds=7)
        return replace(_fetch(contract,session),retrieved_at=now[0])
    def fault(stage):
        if stage=='after_replace':now[0]+=timedelta(seconds=3)
    app.fault_hook=fault
    result=app.update(operation_identity='CLOCK',sessions={market:_calendar(market)},
                      fetch_missing=fetch,as_of=cutoff)
    assert result.outcome=='PUBLISHED'
    candle=app.store.records('CANDLE')[0]
    receipt=app.store.records('RECEIPT')[0]
    update=app.store.records('UPDATE')[0]
    assert candle.data['retrieved_at']==(cutoff+timedelta(seconds=7)).isoformat()
    assert receipt.data['published_at']==(cutoff+timedelta(seconds=10)).isoformat()
    assert receipt.data['generated_at']==(cutoff+timedelta(seconds=7)).isoformat()
    assert receipt.data['analytical_cutoff']==cutoff.isoformat()
    assert update.data['analytical_cutoff']==cutoff.isoformat()
    assert update.data['completed_at']==now[0].isoformat()
    now[0]+=timedelta(days=1)
    app.update(operation_identity='CLOCK',sessions={},fetch_missing=None,as_of=now[0])
    assert app.store.records('RECEIPT')==(receipt,)
    assert app.store.records('UPDATE')==(update,)


def test_original_nse_header_whitespace_normalization_does_not_rewrite_bytes(tmp_path):
    calendar, fields=actions()
    data=b'"SYMBOL \n","SERIES \n","PURPOSE \n","EX-DATE \n"\n'
    fields['source_sha256']=sha256(data).hexdigest()
    store=NseEquityBasisStore(tmp_path/'basis')
    identity=import_official_actions(store,calendar,fields,data,received_at=AT)
    import base64
    assert base64.b64decode(json.loads((store.root/(identity+'.json')).read_bytes())['material']['csv_base64'])==data


def test_incomplete_calendar_and_later_import_are_explicit_unavailable(tmp_path):
    calendar,fields=actions()
    store=NseEquityBasisStore(tmp_path/'basis')
    fields['coverage_end']='2026-10-02'
    with pytest.raises(ValueError,match='COVERAGE'):
        import_official_actions(store,calendar,fields,CSV,received_at=AT)
    assert not store.root.exists()
    fields['coverage_end']='2026-10-01'
    import_official_actions(store,calendar,fields,CSV,received_at=AT+timedelta(seconds=2))
    assert store.basis('RELIANCE','EQ',date(2026,9,29),date(2026,10,1),as_of=AT)==('UNKNOWN',None)


def test_commission_recovers_receipt_without_replacing_its_original_time(tmp_path, monkeypatch):
    root,head,manifest,digest=release(tmp_path)
    control=_control(tmp_path,inbox=SwingResearchInbox(tmp_path/'inbox'))
    control.release_verifier=ResearchReleaseVerifier(root,lambda:head)
    control.application.committed_research_replay_history=lambda:()
    publish=control.research.store.publish_pointer
    monkeypatch.setattr(control.research.store,'publish_pointer',lambda *args: (_ for _ in ()).throw(OSError('interrupted pointer')))
    try:
        with pytest.raises(OSError):
            control.commission(release_identity=head,source_manifest_sha256=digest,manifest_bytes=manifest)
        (original,)=control.research.store.records('COMMISSIONING')
        monkeypatch.setattr(control.research.store,'publish_pointer',publish)
        control.clock=lambda:AT+timedelta(days=2)
        assert control.commission(release_identity=head,source_manifest_sha256=digest,manifest_bytes=manifest)==original
        assert control.research.store.records('COMMISSIONING')==(original,)
    finally:control.close()


def test_canonical_release_verifier_is_installed_but_gets_never_commission(tmp_path):
    from tests.unit.browser.test_browser_server import _running_server, _request
    server,thread=_running_server()
    assert type(server.swing_research_control.release_verifier) is ResearchReleaseVerifier
    from kronos_test_isolation import state
    assert server.swing_research_control.research.store.root.is_relative_to(Path(state()["home"]))
    assert server.swing_research_control.capture.inbox.root.is_relative_to(Path(state()["home"]))
    calls=[]
    server.swing_research_control.release_verifier.verify=lambda *a: calls.append(a)
    try:
        assert _request(server,'GET','/swing/research')[0]==200
        assert server.swing_research_control.status()['commissioned_at'] is None
        assert calls==[]
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


@pytest.mark.parametrize('owner', ['application','intake','native_review','trade_window','mcx_control'])
def test_capture_failure_blocks_first_commissioning_without_receipt(tmp_path,owner):
    root,head,manifest,digest=release(tmp_path)
    control=_control(tmp_path,inbox=SwingResearchInbox(tmp_path/'inbox'))
    control.release_verifier=ResearchReleaseVerifier(root,lambda:head)
    control.application.committed_research_replay_history=lambda:()
    if owner=='application':control.application.research_capture_status=lambda:'CAPTURE_REPLAY_REQUIRED'
    else:setattr(control,owner,SimpleNamespace(research_capture_failure='CAPTURE_REPLAY_REQUIRED'))
    try:
        with pytest.raises(ValueError,match='CAPTURE_HEALTH'):
            control.commission(release_identity=head,source_manifest_sha256=digest,manifest_bytes=manifest)
        assert control.research.store.records('COMMISSIONING')==()
    finally:control.close()


def test_accepted_commissioning_remains_counted_through_final_receipt(tmp_path):
    from threading import Event, Thread
    from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
    root,head,manifest,digest=release(tmp_path)
    control=_control(tmp_path,inbox=SwingResearchInbox(tmp_path/'inbox'))
    verifier=ResearchReleaseVerifier(root,lambda:head)
    entered,finish=Event(),Event()
    def verify(*args):
        entered.set();assert finish.wait(5)
        return verifier.verify(*args)
    control.release_verifier=SimpleNamespace(verify=verify)
    control.application.committed_research_replay_history=lambda:()
    coordinator=MaintenanceAdmissionCoordinator();ticket=coordinator.admit('BROWSER_POST')
    receipts=[]
    def work():
        try:
            with ticket.activate():
                receipts.append(control.commission(release_identity=head,source_manifest_sha256=digest,manifest_bytes=manifest))
        finally:ticket.release()
    thread=Thread(target=work);thread.start()
    assert entered.wait(3)
    generation='c'*64;assert coordinator.claim(generation);coordinator.draining(generation)
    assert coordinator.snapshot()['owners']=={'BROWSER_POST':1}
    waiter=[];drain=Thread(target=lambda:waiter.append(coordinator.wait_for_zero(generation,5)));drain.start()
    assert drain.is_alive();finish.set();thread.join(5);drain.join(5)
    try:
        assert not thread.is_alive() and waiter==[True]
        assert receipts==list(control.research.store.records('COMMISSIONING'))
        assert len(receipts)==1
    finally:control.close()


def test_caller_cannot_substitute_unattested_manifest_serialization(tmp_path):
    root,head,manifest,digest=release(tmp_path)
    changed=manifest+b'\n'
    with pytest.raises(ValueError,match='MANIFEST_UNATTESTED'):
        ResearchReleaseVerifier(root,lambda:head).verify(head,changed,sha256(changed).hexdigest())


@pytest.mark.parametrize("update_fails", [False, True])
def test_action_import_cannot_change_an_admitted_update_basis(tmp_path, monkeypatch, update_fails):
    from threading import Event, Thread
    calendar, fields = actions()
    control = _control(tmp_path)
    control.calendar = calendar
    control.equity_basis = NseEquityBasisStore(tmp_path / "actions")
    control.clock = lambda: AT
    control.intake = SimpleNamespace(retained_research_promotions=lambda: ())
    control.application.committed_research_replay_history = lambda: ()
    monkeypatch.setattr(control.capture, "commissioned_at", lambda: AT)
    monkeypatch.setattr(control.capture, "replay_retained", lambda *a, **k: None)
    entered, finish = Event(), Event()
    observations, errors = [], []
    def evaluate(**kwargs):
        for phase in ("before", "after"):
            observations.append(control.equity_basis.basis("RELIANCE", "EQ",
                date(2026, 9, 29), date(2026, 10, 1), as_of=AT))
            if phase == "before":
                entered.set()
                assert finish.wait(5)
        if update_fails:
            raise OSError("isolated acquisition failure")
        return "COMPLETE"
    monkeypatch.setattr(control.research, "update", evaluate)
    def run():
        try: control.update("a" * 32)
        except OSError as error: errors.append(str(error))
    worker = Thread(target=run)
    worker.start()
    try:
        assert entered.wait(3)
        with pytest.raises(ValueError, match="AUTHORITY_BUSY"):
            control.import_actions(fields, CSV)
        assert not control.equity_basis.root.exists()
    finally:
        finish.set(); worker.join(5)
        control.close()
    assert not worker.is_alive()
    assert observations == [("UNKNOWN", None), ("UNKNOWN", None)]
    assert bool(errors) is update_fails
    identity = control.import_actions(fields, CSV)
    assert control.equity_basis.basis("RELIANCE", "EQ", date(2026,9,29),
        date(2026,10,1), as_of=AT) == ("VERIFIED_NO_ACTION", identity)


def test_admitted_import_finishes_before_update_evaluation_and_both_owners_drain(tmp_path, monkeypatch):
    from threading import Event, Thread
    from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
    import kronos.application.swing_research_authority as authority
    from tests.unit.application.test_swing_research_worker import _result
    calendar, fields = actions()
    control = _control(tmp_path)
    control.calendar = calendar
    control.equity_basis = NseEquityBasisStore(tmp_path / "actions")
    control.clock = lambda: AT
    control.intake = SimpleNamespace(retained_research_promotions=lambda: (), research_capture_failure=None)
    control.application.committed_research_replay_history = lambda: ()
    monkeypatch.setattr(control.capture, "commissioned_at", lambda: AT)
    monkeypatch.setattr(control.capture, "replay_retained", lambda *a, **k: None)
    admitted, finish, evaluated = Event(), Event(), Event()
    receipts, observations, errors, drained = [], [], [], []
    waiter = None
    original = authority.import_official_actions
    def delayed_import(*a, **k):
        admitted.set()
        assert finish.wait(5)
        return original(*a, **k)
    monkeypatch.setattr(authority, "import_official_actions", delayed_import)
    def evaluate(**kwargs):
        observations.append(control.equity_basis.basis("RELIANCE", "EQ",
            date(2026,9,29), date(2026,10,1), as_of=AT))
        evaluated.set()
        return _result("b" * 32)
    monkeypatch.setattr(control.research, "update", evaluate)
    coordinator = MaintenanceAdmissionCoordinator()
    import_ticket = coordinator.admit("BROWSER_POST")
    def import_now():
        try:
            with import_ticket.activate(): receipts.append(control.import_actions(fields, CSV))
        except Exception as error: errors.append(str(error))
        finally: import_ticket.release()
    importer = Thread(target=import_now)
    importer.start()
    parent = coordinator.admit("BROWSER_POST")
    try:
        assert admitted.wait(3)
        assert control.submit_update("b" * 32, parent)["state"] == "QUEUED"
        parent.release()
        assert not evaluated.wait(0.1)
        generation = "e" * 64
        assert coordinator.claim(generation)
        coordinator.draining(generation)
        assert coordinator.snapshot()["owners"] == {"BROWSER_POST":1,"SWING_RESEARCH":1}
        waiter = Thread(target=lambda: drained.append(coordinator.wait_for_zero(generation, 5)))
        waiter.start()
        assert waiter.is_alive()
    finally:
        finish.set(); importer.join(5); control.close()
        if waiter is not None: waiter.join(5)
        if not parent._released: parent.release()
    assert not importer.is_alive() and not errors
    assert len(receipts) == 1
    assert observations == [("VERIFIED_NO_ACTION", receipts[0])]
    assert control.status()["operation"]["state"] == "COMPLETED"
    assert drained == [True]
