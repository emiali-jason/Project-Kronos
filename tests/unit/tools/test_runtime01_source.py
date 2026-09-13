"""Source gates exercised with isolated local git publication, never live runtime."""
from dataclasses import replace
from pathlib import Path
import subprocess
import os
import pytest
from tools import runtime_source_gate as gate
from tests.unit.intraday.test_runtime_identity import _seed


@pytest.fixture
def repository(tmp_path):
    remote = tmp_path / 'remote.git'
    root = tmp_path / 'repo'; root.mkdir()
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.DEVNULL).decode().strip()
    git('init', '--bare', str(remote)); git('init', '-b', 'develop')
    git('config', 'user.email', 'isolated@example.invalid'); git('config', 'user.name', 'Isolated Test')
    (root / 'source.py').write_text('value = 1\n')
    git('add', '.'); git('commit', '-m', 'isolated baseline')
    git('remote', 'add', 'origin', str(remote)); git('push', 'origin', 'develop')
    return root, git


def test_clean_published_source_accepted(repository):
    root, git = repository
    assert gate.qualify_repository(root) == git('rev-parse', 'HEAD')


@pytest.mark.parametrize('mutation', ['dirty', 'staged', 'untracked', 'unpublished', 'branch', 'remote'])
def test_source_failures_prevent_activation(repository, mutation):
    root, git = repository
    if mutation in {'dirty','staged','unpublished'}:
        (root / 'source.py').write_text('value = 2\n')
    if mutation in {'staged','unpublished'}: git('add', 'source.py')
    if mutation == 'unpublished': git('commit', '-m', 'not published')
    if mutation == 'untracked': (root / 'untracked.py').write_text('extra')
    if mutation == 'branch': git('checkout', '-b', 'other')
    if mutation == 'remote': git('remote', 'remove', 'origin')
    with pytest.raises(ValueError, match='SOURCE_'):
        gate.qualify_repository(root)


def test_missing_source_proof(tmp_path):
    with pytest.raises(ValueError, match='SOURCE_PROOF_UNAVAILABLE'): gate.qualify_repository(tmp_path)


def test_direct_python_has_no_canonical_parent_authority():
    with pytest.raises(ValueError, match='CANONICAL_'): gate.canonical_parent()


@pytest.mark.parametrize('fault', ['dirty','revision','pid','proof'])
def test_pinned_proof_must_match_publication(repository, monkeypatch, fault):
    root, git = repository
    monkeypatch.setattr(gate, 'canonical_parent', lambda: None)
    args = dict(source_revision=git('rev-parse','HEAD'))
    if fault == 'dirty': args['source_state']='DIRTY_WORKTREE'
    if fault == 'revision': args['source_revision']='f'*40
    if fault == 'pid': args['process_id']=os.getpid()+1000
    if fault == 'proof': args['source_snapshot_digest']=None
    with pytest.raises(ValueError): gate.qualify_startup(root, _seed(**args))


def test_clean_pinned_proof_accepted(repository, monkeypatch):
    root, git = repository
    monkeypatch.setattr(gate, 'canonical_parent', lambda: None)
    revision=git('rev-parse','HEAD')
    assert gate.qualify_startup(root, _seed(source_revision=revision)) == revision


def test_gate_precedes_runtime_mutations():
    root=Path(__file__).resolve().parents[3]
    source=(root/'tools/kronos_browser.py').read_text()
    main=source[source.index('def main('):]
    assert main.index('qualify_startup(')<main.index('consume_startup_context(')<main.index('BrowserBackendRestartControl.create(')
    c=(root/'tools/macos/kronos_launcher.c').read_text().split('int main(void) {')[1]
    assert c.index('qualify_source(')<c.index('request_graceful_shutdown(')<c.index('start_backend(')


def test_assume_unchanged_python_and_ignored_python_cannot_pass(repository):
    root,git=repository
    (root/'tools').mkdir();(root/'tools/source.py').write_text('value=1\n')
    (root/'.gitignore').write_text('tools/ignored.py\n')
    git('add','.');git('commit','-m','python snapshot');git('push','origin','develop')
    git('update-index','--assume-unchanged','tools/source.py')
    (root/'tools/source.py').write_text('value=2\n')
    assert git('status','--porcelain')==''
    with pytest.raises(ValueError,match='SOURCE_NOT_CLEAN'):gate.qualify_repository(root)
    (root/'tools/source.py').unlink()
    assert git('status','--porcelain')==''
    with pytest.raises(ValueError,match='SOURCE_NOT_CLEAN'):gate.qualify_repository(root)
    (root/'tools/source.py').write_text('value=1\n')
    (root/'tools/ignored.py').write_text('hidden=True\n')
    with pytest.raises(ValueError,match='SOURCE_NOT_CLEAN'):gate.qualify_repository(root)


def test_kernel_parent_and_signature_on_isolated_canonical_bundle(tmp_path):
    import json,plistlib
    app=tmp_path/'Applications/KRONOS.app';exe=app/'Contents/MacOS/KRONOS';exe.parent.mkdir(parents=True)
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier='com.project-kronos.browser-v1',
        CFBundleExecutable='KRONOS',CFBundleName='KRONOS',CFBundlePackageType='APPL')))
    # Test-only constants in a child process. No production environment bypass.
    code=('from pathlib import Path;from tools import runtime_source_gate as g;'
          +'g.CANONICAL=Path('+repr(str(app))+');g.EXECUTABLE=Path('+repr(str(exe))+');g.canonical_parent()')
    import sys
    c=tmp_path/'parent.c'
    c.write_text('#include <unistd.h>\n#include <sys/wait.h>\nint main(void){int s;pid_t p=fork();'
        +'if(p==0){execl('+json.dumps(sys.executable)+',"python","-B","-c",'+json.dumps(code)+', (char*)0);_exit(9);}'
        +'if(waitpid(p,&s,0)!=p)return 8;return WIFEXITED(s)?WEXITSTATUS(s):7;}\n')
    subprocess.run(['clang','-Wall','-Wextra','-Werror',str(c),'-o',str(exe)],check=True,capture_output=True)
    subprocess.run(['codesign','--force','--sign','-','--timestamp=none',str(app)],check=True,capture_output=True)
    assert subprocess.run([str(exe)],capture_output=True).returncode==0
    with (app/'Contents/Info.plist').open('ab') as f:f.write(b'changed')
    assert subprocess.run([str(exe)],capture_output=True).returncode!=0
