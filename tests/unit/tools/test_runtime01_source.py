"""Fixed policy and local Git mechanics; remote advertisements are simulated.

No GitHub/SSH transport is qualified. Production literals are not weakened:
only test I/O uses a disposable HOME/config and a local bare publication.
"""
from dataclasses import replace
from pathlib import Path
import subprocess
import os
import pytest
from tools import runtime_source_gate as gate
from tests.unit.intraday.test_runtime_identity import _seed


@pytest.fixture
def ssh_configuration(tmp_path, monkeypatch):
    base = tmp_path / 'ssh'; base.mkdir()
    system, user = base / 'system', base / 'config'
    monkeypatch.setattr(gate, '_ssh_configuration_paths',
        lambda: ((system, base), (user, base)))
    return system, user


@pytest.fixture
def repository(tmp_path, monkeypatch, ssh_configuration):
    remote = tmp_path / 'remote.git'
    root = tmp_path / 'repo'; root.mkdir()
    fixture_home = tmp_path / 'git-home'; fixture_home.mkdir()
    fixture_environment = dict(os.environ, HOME=str(fixture_home),
        GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_GLOBAL=str(fixture_home / 'config'))
    def git(*args):
        return subprocess.check_output(['/usr/bin/git', *args], cwd=root,
            env=fixture_environment, stderr=subprocess.DEVNULL).decode().strip()
    git('init', '--bare', str(remote)); git('init', '-b', gate.SOURCE_BRANCH)
    git('config', 'user.email', 'isolated@example.invalid'); git('config', 'user.name', 'Isolated Test')
    (root / 'source.py').write_text('value = 1\n')
    git('add', '.'); git('commit', '-m', 'isolated baseline')
    git('remote', 'add', 'origin', str(remote))
    git('push', '--set-upstream', 'origin', gate.SOURCE_BRANCH)
    git('remote', 'set-url', 'origin', gate.SOURCE_ORIGIN)

    # Separate the production policy from test I/O. Every real subprocess below
    # uses fixture configuration; every ls-remote is intercepted before transport.
    calls = []
    def gate_git(path, *args):
        calls.append(args)
        if args[0] == 'ls-remote':
            revision = git('--git-dir=' + str(remote), 'rev-parse', gate.SOURCE_REF)
            return revision + '\t' + gate.SOURCE_REF
        return subprocess.check_output(['/usr/bin/git', *args], cwd=path,
            env=fixture_environment, stderr=subprocess.DEVNULL, timeout=20).decode().strip()
    monkeypatch.setattr(gate, '_git', gate_git)
    def publish():
        git('push', str(remote), gate.SOURCE_BRANCH)
        git('update-ref', gate.SOURCE_TRACKING_REF, git('rev-parse', 'HEAD'))
    git.publish = publish
    git.calls = calls
    git.gate_git = gate_git
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
    assert c.index('qualify_source(')<c.index('native_gate(')<c.index('start_backend(')
    restoration,normal=c.split('    pid_t backend_pid = 0;',1)
    restoration=restoration.split('    if(restoration) {',1)[1]
    assert restoration.index('native_validation("restoration-reserve"')<restoration.index('native_apply_proposal(')<restoration.index('start_backend(')
    assert normal.index('request_graceful_shutdown(')<normal.index('wait_for_backend_stop(')<normal.index('start_backend(')


def test_assume_unchanged_python_and_ignored_python_cannot_pass(repository):
    root,git=repository
    (root/'tools').mkdir();(root/'tools/source.py').write_text('value=1\n')
    (root/'.gitignore').write_text('tools/ignored.py\n')
    git('add','.');git('commit','-m','python snapshot');git.publish()
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


def test_exact_policy_and_simulated_advertisement(repository):
    root, git = repository
    assert gate.SOURCE_ORIGIN == 'git@github.com:emiali-jason/Project-Kronos.git'
    assert gate.SOURCE_BRANCH == 'maintenance/release-b-swing-ux'
    assert gate.SOURCE_REF == 'refs/heads/maintenance/release-b-swing-ux'
    assert gate.qualify_repository(root) == git('rev-parse', 'HEAD')
    assert [call for call in git.calls if call[0] == 'ls-remote'] == [
        ('ls-remote', '--exit-code', 'origin', gate.SOURCE_REF)]


@pytest.mark.parametrize('key,value,duplicate', [
    ('remote', None, False), ('remote', 'other', False),
    ('remote', 'origin', True), ('merge', None, False),
    ('merge', 'refs/heads/develop', False), ('merge', gate.SOURCE_REF, True),
])
def test_upstream_configuration_exactly_once(repository, key, value, duplicate):
    root, git = repository
    name = 'branch.' + gate.SOURCE_BRANCH + '.' + key
    if value is None:
        git('config', '--unset-all', name)
    else:
        git('config', '--add' if duplicate else '--replace-all', name, value)
    with pytest.raises(ValueError, match='SOURCE_'):
        gate.qualify_repository(root)
    assert not any(call[0] == 'ls-remote' for call in git.calls)


@pytest.mark.parametrize('mode', ['wrong', 'duplicate', 'pushurl', 'other-remote'])
def test_origin_must_be_sole_approved_destination(repository, mode):
    root, git = repository
    if mode == 'wrong': git('remote', 'set-url', 'origin', 'git@github.com:other/repo.git')
    if mode == 'duplicate': git('config', '--add', 'remote.origin.url', gate.SOURCE_ORIGIN)
    if mode == 'pushurl': git('config', 'remote.origin.pushurl', gate.SOURCE_ORIGIN)
    if mode == 'other-remote': git('remote', 'add', 'other', gate.SOURCE_ORIGIN)
    with pytest.raises(ValueError, match='SOURCE_DESTINATION'):
        gate.qualify_repository(root)
    assert not any(call[0] == 'ls-remote' for call in git.calls)


@pytest.mark.parametrize('key,value', [
    ('url.ssh://redirect/.insteadOf', 'git@github.com:'),
    ('url.ssh://redirect/.pushInsteadOf', 'git@github.com:'),
    ('core.sshCommand', 'never-execute'), ('core.gitProxy', 'never-execute'),
    ('ssh.variant', 'plink'), ('remote.origin.uploadpack', 'never-execute'),
    ('remote.origin.vcs', 'never-execute'), ('core.fsmonitor', 'never-execute'),
])
def test_git_destination_or_command_override_denied(repository, key, value):
    root, git = repository
    git('config', key, value)
    with pytest.raises(ValueError, match='SOURCE_DESTINATION'):
        gate.qualify_repository(root)
    assert not any(call[0] in {'status', 'ls-remote'} for call in git.calls)


@pytest.mark.parametrize('key', [
    'GIT_CONFIG_SYSTEM', 'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_COUNT',
    'GIT_CONFIG_PARAMETERS', 'GIT_SSH', 'GIT_SSH_COMMAND', 'GIT_SSH_VARIANT',
    'GIT_PROXY_COMMAND', 'GIT_EXEC_PATH', 'GIT_DIR', 'GIT_WORK_TREE',
    'GIT_INDEX_FILE', 'GIT_NAMESPACE', 'DEVELOPER_DIR',
])
def test_actual_invocation_override_rejected_before_git(repository, monkeypatch, key):
    root, git = repository
    monkeypatch.setenv(key, 'unapproved')
    with pytest.raises(ValueError, match='SOURCE_DESTINATION'):
        gate.qualify_repository(root)
    assert git.calls == []


def test_unapproved_path_ssh_is_rejected(repository, monkeypatch):
    root, git = repository
    monkeypatch.setattr(gate.shutil, 'which', lambda name: '/fixture/other-ssh')
    with pytest.raises(ValueError, match='SOURCE_DESTINATION'):
        gate.qualify_repository(root)
    assert git.calls == []


@pytest.mark.parametrize('text', [
    'Host github.com\n HostName other.invalid\n',
    'Host github.com\n Port 443\n', 'Host github.com\n User other\n',
    'ProxyCommand never-execute\n', 'ProxyJump other.invalid\n',
    'LocalCommand never-execute\n', 'KnownHostsCommand never-execute\n',
    'RemoteCommand never-execute\n', 'CanonicalizeHostname yes\n',
    'ControlPath /fixture/master\n', 'ControlMaster auto\n',
    'Match final\n IdentityFile fixture\n', 'UnknownFutureOption yes\n',
])
def test_applicable_ssh_overrides_or_unresolved_selection_denied(repository, ssh_configuration, text):
    root, git = repository
    ssh_configuration[1].write_text(text)
    with pytest.raises(ValueError, match='SOURCE_DESTINATION'):
        gate.qualify_repository(root)
    assert not any(call[0] == 'ls-remote' for call in git.calls)


def test_match_exec_is_inspected_without_execution(repository, ssh_configuration, tmp_path):
    root, git = repository
    sentinel = tmp_path / 'must-not-exist'
    ssh_configuration[1].write_text('Match exec "touch ' + str(sentinel) + '"\n HostName other\n')
    with pytest.raises(ValueError, match='SOURCE_DESTINATION'):
        gate.qualify_repository(root)
    assert not sentinel.exists()
    assert not any(call[0] == 'ls-remote' for call in git.calls)


def test_resolved_ssh_includes_preserve_normal_authentication(repository, ssh_configuration):
    root, git = repository
    system, user = ssh_configuration
    include = user.parent / 'auth.conf'
    include.write_text('IdentityFile ~/.ssh/disposable-reference-only\nStrictHostKeyChecking yes\n'
                       'UserKnownHostsFile ~/.ssh/disposable-reference-only\n')
    system.write_text('Host *\n SendEnv LANG LC_*\n')
    user.write_text('Host unrelated.invalid\n ProxyCommand never-execute\n'
                    'Host github.com\n HostName github.com\n User git\n Port 22\n'
                    ' Include auth.conf\nMatch host github.com user git\n BatchMode yes\n')
    assert gate.qualify_repository(root) == git('rev-parse', 'HEAD')
    assert not (user.parent / 'disposable-reference-only').exists()


@pytest.mark.parametrize('mode', ['cycle', 'directory', 'invalid', 'unresolved-token'])
def test_ssh_include_denies_unresolved_configuration(repository, ssh_configuration, mode):
    root, _ = repository
    user = ssh_configuration[1]
    value = {'cycle': 'Include config\n', 'directory': 'Include .\n',
             'invalid': 'Host "unterminated\n', 'unresolved-token': 'Include %d/fixture\n'}[mode]
    user.write_text(value)
    with pytest.raises(ValueError): gate.qualify_repository(root)


@pytest.mark.parametrize('mode', ['resolved', 'missing', 'conditional'])
def test_git_include_selection_is_bounded(repository, tmp_path, mode):
    root, git = repository
    include = tmp_path / 'included.gitconfig'
    if mode != 'missing': include.write_text('[user]\n signingkey = unused-fixture-reference\n')
    key = 'includeIf.onbranch:' + gate.SOURCE_BRANCH + '.path' if mode == 'conditional' else 'include.path'
    git('config', key, str(include))
    if mode == 'resolved': assert gate.qualify_repository(root) == git('rev-parse', 'HEAD')
    else:
        with pytest.raises(ValueError, match='SOURCE_DESTINATION'): gate.qualify_repository(root)


@pytest.mark.parametrize('mode', ['missing', 'stale', 'wrong-fetch-mapping'])
def test_tracking_revision_and_mapping_are_authoritative(repository, mode):
    root, git = repository
    if mode == 'missing': git('update-ref', '-d', gate.SOURCE_TRACKING_REF)
    if mode == 'stale': git('commit', '--allow-empty', '-m', 'unpublished fixture')
    if mode == 'wrong-fetch-mapping':
        git('config', 'remote.origin.fetch', '+refs/heads/*:refs/remotes/other/*')
    with pytest.raises(ValueError, match='SOURCE_'): gate.qualify_repository(root)
    assert not any(call[0] == 'ls-remote' for call in git.calls)


@pytest.mark.parametrize('mode', ['empty', 'wrong-revision', 'wrong-ref', 'duplicate', 'extra',
                                  'split-line', 'space-delimited', 'unreachable'])
def test_direct_remote_advertisement_cannot_be_substituted(repository, monkeypatch, mode):
    root, git = repository
    revision = git('rev-parse', 'HEAD')
    def runner(path, *args):
        if args[0] == 'ls-remote':
            if mode == 'unreachable': raise subprocess.CalledProcessError(128, args)
            good = revision + '\t' + gate.SOURCE_REF
            return {'empty': '', 'wrong-revision': 'f'*40 + '\t' + gate.SOURCE_REF,
                    'wrong-ref': revision + '\trefs/heads/develop',
                    'duplicate': good + '\n' + good, 'extra': good + '\nextra',
                    'split-line': revision + '\n' + gate.SOURCE_REF,
                    'space-delimited': revision + ' ' + gate.SOURCE_REF}[mode]
        return git.gate_git(path, *args)
    monkeypatch.setattr(gate, '_git', runner)
    with pytest.raises(ValueError, match='SOURCE_'): gate.qualify_repository(root)


@pytest.mark.parametrize('mutation', ['source', 'destination', 'branch'])
def test_final_currentness_rechecks_reject_during_validation_change(repository, monkeypatch,
        ssh_configuration, mutation):
    root, git = repository
    def runner(path, *args):
        result = git.gate_git(path, *args)
        if args[0] == 'ls-remote':
            if mutation == 'source': (root / 'source.py').write_text('changed\n')
            if mutation == 'destination': ssh_configuration[1].write_text('ProxyCommand never-execute\n')
            if mutation == 'branch': git('branch', '-m', 'other')
        return result
    monkeypatch.setattr(gate, '_git', runner)
    with pytest.raises(ValueError, match='SOURCE_'): gate.qualify_repository(root)


def test_no_develop_or_environment_policy_fallback(repository, monkeypatch):
    root, git = repository
    git('checkout', '-b', 'develop')
    monkeypatch.setenv('KRONOS_SOURCE_BRANCH', 'develop')
    with pytest.raises(ValueError, match='SOURCE_'): gate.qualify_repository(root)
    assert not any(call[0] == 'ls-remote' for call in git.calls)


def test_symlink_and_missing_tracked_python_are_rejected(repository):
    root, git = repository
    tools = root / 'tools'; tools.mkdir()
    source = tools / 'owned.py'; source.write_text('fact = 1\n')
    git('add', '.'); git('commit', '-m', 'owned Python'); git.publish()
    source.unlink(); source.symlink_to(root / 'source.py')
    with pytest.raises(ValueError, match='SOURCE_NOT_CLEAN'): gate.qualify_repository(root)
    source.unlink()
    with pytest.raises(ValueError, match='SOURCE_NOT_CLEAN'): gate.qualify_repository(root)


def test_real_git_configuration_records_are_supported(repository):
    root, git = repository
    try:
        state = gate._git_configuration(root, [])
    except ValueError as error:
        records = git.gate_git(root, 'config', '--includes', '--null', '--show-origin',
                               '--show-scope', '--list').split('\0')
        pytest.fail(f'Isolated Git configuration record format rejected: {records!r}; {error}')
    assert ('remote.origin.url', (gate.SOURCE_ORIGIN,)) in state


@pytest.mark.parametrize('field,value', [('scope', 'command'), ('origin', 'command line:')])
def test_nonfile_or_command_configuration_provenance_cannot_supply_policy(repository, monkeypatch,
        field, value):
    root, git = repository
    def runner(path, *args):
        raw = git.gate_git(path, *args)
        if args[0] == 'config':
            fields = raw.split('\0')
            fields[0 if field == 'scope' else 1] = value
            return '\0'.join(fields)
        return raw
    monkeypatch.setattr(gate, '_git', runner)
    with pytest.raises(ValueError, match='SOURCE_DESTINATION'):
        gate.qualify_repository(root)
    assert not any(call[0] == 'ls-remote' for call in git.calls)


def test_ssh_tilde_include_uses_account_home_not_generic_home(repository, ssh_configuration,
        tmp_path, monkeypatch):
    root, git = repository
    account_home = tmp_path / 'account-home'; account_home.mkdir()
    (account_home / 'guard.conf').write_text('ProxyCommand never-execute\n')
    decoy = tmp_path / 'decoy.conf'; decoy.write_text('BatchMode yes\n')
    ssh_configuration[1].write_text('Include ~/guard.conf\n')
    monkeypatch.setattr(gate, '_ssh_user_home', lambda: account_home)
    # Model a divergent generic HOME expansion without changing HOME itself.
    monkeypatch.setattr(Path, 'expanduser', lambda self: decoy)
    with pytest.raises(ValueError, match='SOURCE_DESTINATION'):
        gate.qualify_repository(root)
    assert not any(call[0] == 'ls-remote' for call in git.calls)


def test_destination_changed_before_transport_is_rejected(repository, ssh_configuration, monkeypatch):
    root, git = repository
    changed = False
    def runner(path, *args):
        nonlocal changed
        result = git.gate_git(path, *args)
        if args == ('rev-parse', gate.SOURCE_TRACKING_REF) and not changed:
            changed = True
            ssh_configuration[1].write_text('ProxyJump other.invalid\n')
        return result
    monkeypatch.setattr(gate, '_git', runner)
    with pytest.raises(ValueError, match='SOURCE_DESTINATION'):
        gate.qualify_repository(root)
    assert not any(call[0] == 'ls-remote' for call in git.calls)


def test_wrong_repository_root_is_rejected(repository, monkeypatch, tmp_path):
    root, git = repository
    def runner(path, *args):
        if args == ('rev-parse', '--show-toplevel'): return str(tmp_path)
        return git.gate_git(path, *args)
    monkeypatch.setattr(gate, '_git', runner)
    with pytest.raises(ValueError, match='SOURCE_PROOF_UNAVAILABLE'):
        gate.qualify_repository(root)
    assert not any(call[0] == 'ls-remote' for call in git.calls)


@pytest.mark.parametrize('scope,value', [('hostname', 'evil.invalid'), ('port', '443')])
def test_system_ssh_include_cannot_redirect_transport(repository, ssh_configuration, scope, value):
    root, git = repository
    system, _ = ssh_configuration
    include = system.parent / 'system-include.conf'
    include.write_text('Host *\n' + scope + ' ' + value + '\n')
    system.write_text('Include system-include.conf\n')
    with pytest.raises(ValueError, match='SOURCE_DESTINATION'):
        gate.qualify_repository(root)
    assert not any(call[0] == 'ls-remote' for call in git.calls)


# CA findings 2.1-F01/F02: parser denial must precede any transport.
def test_host_bracket_negation_cannot_conceal_active_command(repository, ssh_configuration,
        tmp_path):
    root, git = repository
    sentinel = tmp_path / 'configured-command-must-not-run'
    ssh_configuration[1].write_text('Host * ![g]ithub.com\n ProxyCommand touch '
                                    + str(sentinel) + '\n')
    with pytest.raises(ValueError, match='SOURCE_DESTINATION_NOT_AUTHORIZED'):
        gate.qualify_repository(root)
    assert not sentinel.exists()
    assert not any(call[0] == 'ls-remote' for call in git.calls)


def test_environment_include_cannot_conceal_command(repository, ssh_configuration,
        tmp_path, monkeypatch):
    root, git = repository
    include_home = tmp_path / 'expanded-include'; include_home.mkdir()
    sentinel = tmp_path / 'include-command-must-not-run'
    (include_home / 'override.conf').write_text('Host github.com\n ProxyCommand touch '
                                               + str(sentinel) + '\n')
    monkeypatch.setenv('KRONOS_TEST_SSH_INCLUDE', str(include_home))
    ssh_configuration[1].write_text('Include ${KRONOS_TEST_SSH_INCLUDE}/override.conf\n')
    with pytest.raises(ValueError, match='SOURCE_DESTINATION_NOT_AUTHORIZED'):
        gate.qualify_repository(root)
    assert not sentinel.exists()
    assert not any(call[0] == 'ls-remote' for call in git.calls)


@pytest.mark.parametrize('selector', [
    'Host [g]ithub.com', 'Host * ![g]ithub.com', 'Host unrelated.invalid [g]ithub.com',
    'Host * !github.com [g]ithub.com',
    'Match host [g]ithub.com', 'Match host *,![g]ithub.com',
    'Match originalhost *,![g]ithub.com', 'Match user [g]it',
    'Match localuser *,![u]nrelated',
])
def test_unsupported_ssh_bracket_patterns_denied_before_inactive_classification(
        repository, ssh_configuration, selector):
    root, git = repository
    ssh_configuration[1].write_text(selector + '\n ProxyCommand never-execute\n')
    with pytest.raises(ValueError, match='SOURCE_DESTINATION_NOT_AUTHORIZED'):
        gate.qualify_repository(root)
    assert not any(call[0] == 'ls-remote' for call in git.calls)


@pytest.mark.parametrize('selector,active', [
    ('Host github.com,other.invalid', False),
    ('Match host github.com,other.invalid', True),
    ('Host * !github.com', False), ('Match host *,!github.com', False),
    ('Host * !other.invalid', True), ('Match host *,!other.invalid', True),
    ('Host g?thub.*', True), ('Match host g?thub.*', True),
    ('Host * !!github.com', True), ('Match host *,!!github.com', True),
])
def test_host_and_match_pattern_list_grammars_are_distinct(repository,
        ssh_configuration, selector, active):
    root, git = repository
    ssh_configuration[1].write_text(selector + '\n ProxyCommand never-execute\n')
    if active:
        with pytest.raises(ValueError, match='SOURCE_DESTINATION_NOT_AUTHORIZED'):
            gate.qualify_repository(root)
        assert not any(call[0] == 'ls-remote' for call in git.calls)
    else:
        assert gate.qualify_repository(root) == git('rev-parse', 'HEAD')
        assert len([call for call in git.calls if call[0] == 'ls-remote']) == 1


@pytest.mark.parametrize('include', [
    '${KRONOS_TEST_SSH_INCLUDE}/override.conf',
    'prefix/${KRONOS_TEST_SSH_INCLUDE}/override.conf',
    '${KRONOS_TEST_SSH_INCLUDE',
    'auth.conf ${KRONOS_TEST_SSH_INCLUDE}/override.conf',
])
def test_unresolved_ssh_include_environment_syntax_is_denied_before_glob(
        repository, ssh_configuration, monkeypatch, include):
    root, git = repository
    ssh_configuration[1].write_text('Host github.com\n Include ' + include + '\n')
    (ssh_configuration[1].parent / 'auth.conf').write_text('BatchMode yes\n')
    def forbidden_glob(pattern):
        assert '${' not in pattern, 'unresolved environment syntax reached glob'
        return []
    monkeypatch.setattr(gate.glob, 'glob', forbidden_glob)
    with pytest.raises(ValueError, match='SOURCE_DESTINATION_NOT_AUTHORIZED'):
        gate.qualify_repository(root)
    assert not any(call[0] == 'ls-remote' for call in git.calls)


def test_source_budget_is_shared_across_existing_git_seam(repository,monkeypatch):
    root,git=repository
    budgets=[]
    real=git.gate_git
    def runner(path,*args):
        budget=gate._SOURCE_BUDGET.get();assert budget is not None
        budgets.append(budget.deadline_ns)
        return real(path,*args)
    monkeypatch.setattr(gate,'_git',runner)
    assert gate.qualify_repository(root)==git('rev-parse','HEAD')
    assert budgets and len(set(budgets))==1


def test_source_budget_late_result_never_reaches_transport(repository,monkeypatch):
    root,git=repository
    real=git.gate_git
    def runner(path,*args):
        result=real(path,*args)
        if args==('rev-parse','HEAD'):gate._SOURCE_BUDGET.get().failed=True
        return result
    monkeypatch.setattr(gate,'_git',runner)
    # _git must enforce the shared boundary even with a fixture adapter.
    with pytest.raises(ValueError):gate.qualify_repository(root)
