#!/usr/bin/env python3
"""Run repository tests with an inherited OS production-store denial boundary.

macOS qualification entry point. Other platforms fail closed until an equally
strong kernel isolation backend is qualified. No production application imports.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import socket
import tempfile

REPOSITORY = Path(__file__).resolve().parents[1]
MARKER = 'KRONOS_TEST_ISOLATION_MANIFEST'


def protected_roots(environment):
    homes = {Path.home(), Path(pwd.getpwuid(os.getuid()).pw_dir)}
    if environment.get('HOME'):
        homes.add(Path(environment['HOME']))
    roots = {Path('/Applications/KRONOS.app')}
    for home in homes:
        roots.update((home / 'Library/Application Support/KRONOS',
                      home / 'Library/Application Support/Project-KRONOS',
                      home / 'Documents/Project-KRONOS/KRONOS REVIEW PACK'))
    if environment.get('KRONOS_HOME'):
        roots.add(Path(environment['KRONOS_HOME']))
    roots.update(parent / '.env' for parent in (REPOSITORY, *REPOSITORY.parents))
    return sorted({str(path.resolve()) for path in roots})


def profile(roots, probe, allowed_ports):
    literals = '\n'.join('(subpath ' + json.dumps(root) + ')' for root in roots)
    ports = '\n'.join(f'(remote tcp "localhost:{port}")' for port in allowed_ports)
    return f'''(version 1)
(allow default)
(deny file* {literals})
(deny file-read-data file-write* (literal {json.dumps(str(probe))}))
(deny network*)
(allow network-inbound (local tcp "localhost:*"))
(allow network-outbound {ports})
(deny process-exec (literal "/usr/bin/security") (literal "/usr/bin/open") (literal "/bin/launchctl") (literal "/usr/bin/osascript"))
'''


def main(arguments=None):
    if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').is_file():
        raise SystemExit('KRONOS_TEST_KERNEL_ISOLATION_UNAVAILABLE')
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if not arguments:
        arguments = ['tests']
    original = dict(os.environ)
    roots = protected_roots(original)
    with tempfile.TemporaryDirectory(prefix='kronos-test-') as directory, socket.socket() as network_probe:
        network_probe.bind(('127.0.0.1',0)); network_probe.listen(1)
        blocked_port = network_probe.getsockname()[1]
        reservations = [socket.socket() for _ in range(64)]
        for reservation in reservations:
            reservation.bind(('127.0.0.1', 0))
        allowed_ports = [reservation.getsockname()[1] for reservation in reservations]
        if 8947 in allowed_ports:
            raise SystemExit('KRONOS_TEST_PRODUCTION_PORT_FORBIDDEN')
        root = Path(directory).resolve()
        home = root / 'home'; home.mkdir(mode=0o700)
        protected = root / 'protected'; protected.mkdir(mode=0o700)
        # Controlled surrogate production tree used by negative tests. Its
        # children are denied at the same kernel layer as real product roots.
        (protected / 'record.json').write_text('{"fixture":"DO_NOT_READ"}\n')
        probe = root / 'kernel-denial-probe'
        probe.write_text('KRONOS_TEST_PROBE\n'); probe.chmod(0o600)
        roots.append(str(protected))
        bootstrap = REPOSITORY / 'tools/testing/bootstrap'
        pythonpath = os.pathsep.join(map(str,(bootstrap,REPOSITORY,REPOSITORY/'src',REPOSITORY/'tests/unit')))
        manifest = root / 'isolation.json'
        manifest.write_text(json.dumps({'version':1,'root':str(root),'home':str(home),
            'probe':str(probe),'protected':roots,'surrogate':str(protected),
            'original_home':original.get('HOME'),'pythonpath':pythonpath,'blocked_test_port':blocked_port,'allowed_ports':allowed_ports}))
        manifest.chmod(0o600)
        policy = root / 'isolation.sb'; policy.write_text(profile(roots,probe,allowed_ports))
        environment = {key:value for key,value in original.items()
            if not key.startswith(('KRONOS_', 'KITE_', 'OPENAI_', 'TELEGRAM_'))}
        environment.update({MARKER:str(manifest),'PYTHONPATH':pythonpath,
            'PYTHON_DOTENV_DISABLED':'1','PYTHONNOUSERSITE':'1',
            'PYTHONDONTWRITEBYTECODE':'1'})
        # stdout/stderr and explicit JUnit output remain caller-owned; all
        # product defaults and pytest working files are disposable.
        command=['/usr/bin/sandbox-exec','-f',str(policy),sys.executable,'-m','pytest',*arguments]
        for reservation in reservations:
            reservation.close()
        completed = subprocess.run(command,cwd=REPOSITORY,env=environment)
        if tuple(protected.iterdir()) != (protected / 'record.json',) or (protected / 'record.json').read_text() != '{"fixture":"DO_NOT_READ"}\n':
            raise SystemExit('KRONOS_TEST_SURROGATE_MUTATED')
        return completed.returncode


if __name__ == '__main__':
    raise SystemExit(main())
