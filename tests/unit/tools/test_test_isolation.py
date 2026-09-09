"""Kernel-backed qualification uses only controlled surrogate production data."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from kronos_test_isolation import IsolationError, check_path, state


def child(code, env=None):
    return subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,timeout=15)


def test_home_env_is_not_repurposed_but_defaults_are_private():
    current = state()
    assert os.environ.get('HOME') == current['original_home']
    assert str(Path.home()) == current['home']
    assert Path.home() != Path(current['original_home'])


@pytest.mark.parametrize('key', ['KRONOS_HOME','KRONOS_KITE_ACCESS_TOKEN','OPENAI_API_KEY','TELEGRAM_BOT_TOKEN'])
def test_inherited_production_like_environment_is_not_consumed(key):
    values={key:state()['surrogate'],'HOME':state()['original_home']}
    result=child("import os; from pathlib import Path; from kronos_test_isolation import state; "
                 f"assert {key!r} not in os.environ; assert str(Path.home())==state()['home']",values)
    assert result.returncode == 0, result.stderr


def test_all_default_store_constants_bind_before_composition():
    from kronos.swing.v1.native_review import NativeReviewEvidenceStore
    from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
    from kronos.intraday.review_mcx_paired_persistence import IntradayMcxPairedReviewStore
    from kronos.intraday.wo10_persistence import Wo10Store
    from kronos.application.swing_ux10 import Ux10NotificationStore
    from kronos.application.notification_centre import SponsorNotificationLifecycleStore
    from kronos.browser.restart_control import DEFAULT_BACKEND_CONTROL_PATH
    for value in (NativeReviewEvidenceStore().root, IntradayReviewV2Store().root,
                  IntradayMcxPairedReviewStore().root, Wo10Store().root,
                  Ux10NotificationStore().root, SponsorNotificationLifecycleStore().root,
                  DEFAULT_BACKEND_CONTROL_PATH):
        assert Path(state()['home']) in Path(value).parents


def test_review_answer_and_configuration_defaults_are_private():
    from kronos.configuration.pdf_visual_review import default_pdf_visual_review_directories
    from kronos.configuration.loader import provider_authentication_application_config_path
    from kronos.integrations.telegram import telegram_delivery_control_path
    for path in (*default_pdf_visual_review_directories(),provider_authentication_application_config_path(),telegram_delivery_control_path()):
        assert Path(state()['home']) in path.parents


def test_browser_omitting_root_and_restoration_remains_private():
    from tests.unit.browser.test_browser_server import _running_server
    server,thread = _running_server()
    try:
        assert Path(state()['home']) in server.native_review.evidence_root.parents
        server.restore_sponsor_operability()
        assert server.trade_window is not None
        assert server.ux10_notifications is not None
        assert server.notification_centre is not None
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
    assert not thread.is_alive()


@pytest.mark.parametrize('operation',['read','write','mkdir','list','resolve','bind','rename','unlink'])
def test_surrogate_production_access_fails_before_effect(operation,tmp_path):
    root=Path(state()['surrogate']);target=root/'record.json'
    with pytest.raises((PermissionError,IsolationError)):
        if operation=='read':target.read_bytes()
        elif operation=='write':target.write_text('forbidden')
        elif operation=='mkdir':(root/'new').mkdir()
        elif operation=='list':list(root.iterdir())
        elif operation=='resolve':target.resolve()
        elif operation=='bind':
            from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
            IntradayReviewV2Store(root)
        elif operation=='rename':target.rename(tmp_path/'stolen')
        else:target.unlink()


def test_symlink_cannot_bypass_kernel_guard(tmp_path):
    alias=tmp_path/'alias'
    alias.symlink_to(Path(state()['surrogate'])/'record.json')
    with pytest.raises(PermissionError):alias.read_bytes()


def test_descriptor_relative_access_cannot_bypass_kernel_guard():
    root=Path(state()['surrogate'])
    with pytest.raises(PermissionError):
        fd=os.open(root,os.O_RDONLY)
        try:os.open('record.json',os.O_RDONLY,dir_fd=fd)
        finally:os.close(fd)


def test_native_child_is_guarded_without_python_hooks():
    result=subprocess.run(['/bin/cat',str(Path(state()['surrogate'])/'record.json')],capture_output=True)
    assert result.returncode != 0 and not result.stdout


def test_explicit_empty_child_environment_still_bootstraps():
    result=child('from kronos_test_isolation import state; from pathlib import Path; assert str(Path.home()) == state()["home"]',{})
    assert result.returncode == 0, result.stderr


def test_child_ignoring_python_environment_still_cannot_read_production():
    code='from pathlib import Path\np=Path('+repr(str(Path(state()['surrogate'])/'record.json'))+')\ntry:p.read_bytes()\nexcept PermissionError:pass\nelse:raise RuntimeError("ESCAPED")'
    result=subprocess.run([sys.executable,'-I','-c',code],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr


def test_protected_loopback_probe_is_unreachable():
    with socket.socket() as client:
        with pytest.raises(PermissionError):client.connect(('127.0.0.1',state()['blocked_test_port']))


def test_live_shadow_store_explicit_surrogate_root_cannot_open():
    from kronos.intraday.live_shadow_persistence import ShadowStore
    with pytest.raises((PermissionError,IsolationError)):ShadowStore(Path(state()['surrogate']))


def test_pdf_transport_default_constructor_is_private():
    from kronos.intraday.review_pdf import IntradayReviewPdfTransport
    transport = IntradayReviewPdfTransport()
    assert Path(state()['home']) in transport.question_outbox.parents
    assert Path(state()['home']) in transport.answer_inbox.parents


def test_native_style_child_cannot_contact_protected_listener():
    code = "import socket; s=socket.socket(); s.connect(('127.0.0.1'," + str(state()['blocked_test_port']) + "))"
    result = subprocess.run([sys.executable, '-I', '-c', code], capture_output=True, text=True)
    assert result.returncode != 0 and 'PermissionError' in result.stderr


def test_plain_pytest_refuses_before_collection():
    repository = Path(__file__).resolve().parents[3]
    code = ("import os,sys; os.environ.pop('KRONOS_TEST_ISOLATION_MANIFEST', None); "
            + "sys.path.insert(0," + repr(str(repository)) + "); import pytest; "
            + "raise SystemExit(pytest.main(['--collect-only','-q',"
            + repr(str(repository/'tests/unit/tools/test_test_isolation.py')) + "]))")
    result = subprocess.run([sys.executable, '-I', '-c', code], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'KRONOS_TEST_ISOLATION_REQUIRED' in result.stderr


def test_readable_probe_cannot_forge_kernel_protection(tmp_path):
    root = tmp_path / 'kronos-test-forged'; root.mkdir()
    home = root / 'home'; home.mkdir()
    probe = root / 'probe'; probe.write_text('readable'); probe.chmod(0o600)
    manifest = root / 'isolation.json'
    manifest.write_text(json.dumps(dict(state(), root=str(root), home=str(home), probe=str(probe))))
    manifest.chmod(0o600)
    repository = Path(__file__).resolve().parents[3]
    code = ("import os,sys; sys.path.insert(0," + repr(str(repository)) + "); "
            + "os.environ['KRONOS_TEST_ISOLATION_MANIFEST']=" + repr(str(manifest)) + "; "
            + "from kronos_test_isolation import install; install(required=True)")
    result = subprocess.run([sys.executable, '-I', '-c', code], capture_output=True, text=True)
    assert result.returncode != 0 and 'KRONOS_TEST_KERNEL_PROTECTION_MISSING' in result.stderr
