#!/usr/bin/env python3
"""TE-09R isolated Theta operational entry point. Not a production launcher.

Genuine operation requires a subsequent Sponsor order (TE-09B). This tool does
not auto-admit charts, create Questions, import Answers or call any Provider.
Rehearsals use disposable substitutes and visible synthetic evidence only.
"""
from argparse import ArgumentParser
import json
import hashlib
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import subprocess
import sys
import tempfile

REPOSITORY = Path(__file__).resolve().parents[1]
REAL_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
GENUINE_ROOT = REPOSITORY / "output/theta-te09b-genuine-trial"
SPONSOR = REAL_HOME / "Documents/Project-KRONOS/KRONOS REVIEW PACK/Theta Earners"
PROTECTED_PORTS = {8947,8948,8968}
RETAINED_CHART_ROOT = Path('/private/var/folders/t6/y8wycddx2tv3swhcw_ccqjcw0000gn/T/kronos-test-theta-te06a-preview.3xtBtmab6C/disposable-theta')
PREVIEW_ROOT = Path('/private/tmp/kronos-theta-te07ux.rFN6fn/preview')


def policy(root, inbox, outbox, port, probe, original_paths=()):
    """Kernel deny boundary: only contained state and no-clobber outbox writes."""
    q = lambda p: json.dumps(str(p))
    protected = [REAL_HOME/'Library/Application Support/KRONOS',
        REAL_HOME/'Library/Application Support/Project-KRONOS', REAL_HOME/'Library/Keychains',
        REAL_HOME/'.ssh',REAL_HOME/'.aws',Path('/Applications/KRONOS.app'),
        RETAINED_CHART_ROOT,PREVIEW_ROOT]
    protected += [p/'.env' for p in (REPOSITORY,*REPOSITORY.parents)]
    denied = '\n'.join('(subpath '+q(p)+')' for p in protected)
    # Explicit exceptions are to the frozen Theta directories, not the entire
    # Review Pack. Answers remain read-only at the OS layer.
    review = REAL_HOME/'Documents/Project-KRONOS/KRONOS REVIEW PACK'
    # TE-09R2: macOS requires file-read-data to open a directory descriptor
    # even with O_DIRECTORY|O_NOFOLLOW. Metadata-only admits lstat but not the
    # unchanged directory() traversal. Admit exact ancestor nodes, never their
    # children/subpaths; the application still forbids discovery/foreign paths.
    review_ancestors = {p for leaf in (inbox,outbox) for p in leaf.parents
                        if p == review or review in p.parents}
    ancestor_reads = ('(allow file-read-metadata file-read-data '+
                      '\n'.join('(literal '+q(p)+')'
                                for p in sorted(review_ancestors,key=str))+')'
                      if review_ancestors else '')
    ancestors=set(root.parents)|set(outbox.parents)
    ancestor_creation='\n'.join('(literal '+q(p)+')' for p in sorted(ancestors,key=str))
    original_reads=''
    if original_paths:
        traverse=set(original_paths)|{parent for p in original_paths for parent in p.parents}
        original_reads='(allow file-read* '+ '\n'.join('(literal '+q(p)+')' for p in sorted(traverse,key=str))+')'
    return f'''(version 1)
(allow default)
(deny file* {denied})
(deny file* (require-all (subpath {q(review)})
    (require-not (subpath {q(inbox)})) (require-not (subpath {q(outbox)}))))
{ancestor_reads}
(deny file-write* (require-all (require-not (subpath {q(root)}))
    (require-not (subpath {q(outbox)}))))
; Existing no-follow directory traversal attempts mkdir on existing ancestors.
; Only that operation is admitted at those exact names, never child writes.
(allow file-write-create {ancestor_creation})
{original_reads}
(deny file-read-data file-write* (literal {q(probe)}))
(deny network*)
(allow network-inbound (local tcp "localhost:{port}"))
(allow network-outbound (remote tcp "localhost:{port}"))
(deny process-exec (literal "/usr/bin/security") (literal "/usr/bin/open")
    (literal "/bin/launchctl") (literal "/usr/bin/osascript"))
'''


def arguments(argv=None):
    p=ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('GENUINE_TRIAL','SYNTHETIC_REHEARSAL'),required=True)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--inbox',type=Path,required=True)
    p.add_argument('--outbox',type=Path,required=True)
    p.add_argument('--port',type=int,default=8970)
    p.add_argument('--child',action='store_true',help=__import__('argparse').SUPPRESS)
    p.add_argument('--denied-port',type=int,help=__import__('argparse').SUPPRESS)
    p.add_argument('--originals-manifest',type=Path)
    p.add_argument('--sponsor-confirmed-originals',action='store_true')
    return p.parse_args(argv)


def preflight(args):
    if sys.platform!='darwin' or not Path('/usr/bin/sandbox-exec').is_file():
        raise ValueError('THETA_TRIAL_KERNEL_ISOLATION_UNAVAILABLE')
    if args.port in PROTECTED_PORTS or not 1024<=args.port<=65535:
        raise ValueError('THETA_TRIAL_PORT_INVALID')
    for p in (args.root,args.inbox,args.outbox):
        if not p.is_absolute() or str(p)!=os.path.normpath(str(p)):
            raise ValueError('THETA_TRIAL_PATH_INVALID')
        # Do not follow even parent symlinks before constructing OS exceptions.
        cursor=Path('/')
        for part in p.parts[1:]:
            cursor=cursor/part
            if cursor.is_symlink(): raise ValueError('THETA_TRIAL_PATH_INVALID')
    if args.mode=='GENUINE_TRIAL':
        if (args.root,args.inbox,args.outbox)!=(GENUINE_ROOT,SPONSOR/'CHATGPT ANSWERS',SPONSOR/'KRONOS QUESTIONS') or args.port!=8970:
            raise ValueError('THETA_TRIAL_PATH_INVALID')
    else:
        temporary=Path(tempfile.gettempdir()).resolve() if not args.child else None
        if args.root==GENUINE_ROOT or (not args.child and not all(temporary in p.parents or Path('/private/tmp') in p.parents
                for p in (args.root,args.inbox,args.outbox))):
            raise ValueError('THETA_TRIAL_REHEARSAL_PATH_INVALID')
    for p in (args.inbox,args.outbox):
        info=p.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
            raise ValueError('THETA_TRIAL_PERMISSION_INVALID')
    if args.root.exists():
        info=args.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
            raise ValueError('THETA_TRIAL_PERMISSION_INVALID')
        names=set(os.listdir(args.root))
        if 'theta-operational.json' not in names and names-{'support'}:
            raise ValueError('THETA_TRIAL_FOREIGN_STORE')
        for relative in ('support','support/home','support/tmp'):
            p=args.root/relative
            if p.is_symlink(): raise ValueError('THETA_TRIAL_PATH_INVALID')


def safe_file(path,maximum):
    """Read only a bounded stable regular single-link file; no symlink parents."""
    path=Path(path)
    if not path.is_absolute() or path!=Path(os.path.normpath(str(path))):
        raise ValueError('THETA_TRIAL_ORIGINAL_INVALID')
    parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            next_fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            os.close(parent);parent=next_fd
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or not 0<before.st_size<=maximum:
                raise ValueError('THETA_TRIAL_ORIGINAL_INVALID')
            raw=stream.read(maximum+1);stream.seek(0);second=stream.read(maximum+1)
            after=os.fstat(stream.fileno());named=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
            fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_nlink')
            if raw!=second or len(raw)!=before.st_size or any(getattr(before,k)!=getattr(after,k) or getattr(before,k)!=getattr(named,k) for k in fields):
                raise ValueError('THETA_TRIAL_ORIGINAL_INVALID')
            return raw
    finally:os.close(parent)


def original_manifest(args):
    """Only image locators/hashes/media; no receipt/selection/Question import."""
    if args.originals_manifest is None:return {}
    if not args.sponsor_confirmed_originals or args.root/'support' not in args.originals_manifest.parents:
        raise ValueError('THETA_TRIAL_CHART_CONFIRMATION_REQUIRED')
    def unique(pairs):
        value={}
        for k,v in pairs:
            if k in value:raise ValueError('THETA_TRIAL_ORIGINAL_INVALID')
            value[k]=v
        return value
    value=json.loads(safe_file(args.originals_manifest,65536),object_pairs_hook=unique)
    roles={'GOLDM','SILVERM','COPPER','CRUDEOIL','NATURALGAS','GLOBAL_MACRO'}
    if not isinstance(value,dict) or set(value)!={'originals'} or not isinstance(value['originals'],dict) or set(value['originals'])!=roles:
        raise ValueError('THETA_TRIAL_ORIGINAL_INVALID')
    for item in value['originals'].values():
        if not isinstance(item,dict) or set(item)!={'path','sha256','media_type'} or not isinstance(item['path'],str) or not isinstance(item['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',item['sha256']) or item['media_type'] not in {'image/png','image/jpeg'}:
            raise ValueError('THETA_TRIAL_ORIGINAL_INVALID')
        path=Path(item['path'])
        if path.name!=item['sha256'] or path!=Path(os.path.normpath(str(path))):
            raise ValueError('THETA_TRIAL_ORIGINAL_INVALID')
        if args.mode=='GENUINE_TRIAL':
            if path.parent!=RETAINED_CHART_ROOT/'populated/evidence/blobs':raise ValueError('THETA_TRIAL_ORIGINAL_INVALID')
        elif args.root/'support' not in path.parents:raise ValueError('THETA_TRIAL_ORIGINAL_INVALID')
    return value['originals']


def handler(base, mode):
    from http import HTTPStatus
    from urllib.parse import urlsplit
    gets={'/theta-earners','/theta-earners/new-analysis','/theta-earners/detail',
        '/theta-earners/question-pack','/theta-earners/answer','/theta-earners/chart-preview',
        '/theta-earners/detail-chart','/assets/brand/kronos-brand-mark.png',
        '/assets/brand/kronos-sidebar-mark.png','/favicon.png'}
    posts={'/theta-earners/chart','/theta-earners/question','/theta-earners/import'}
    class ThetaOnly(base):
        def denied(self):
            self._text(HTTPStatus.FORBIDDEN,'Isolated Theta trial: operation not permitted.')
        def do_GET(self):
            if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':
                self.denied();return
            path=urlsplit(self.path).path
            if path=='/': self._redirect('/theta-earners');return
            if path not in gets: self.denied();return
            super().do_GET()
        def do_POST(self):
            if urlsplit(self.path).path not in posts: self.denied();return
            # Shared Host/Origin/body-size/maintenance/concurrency admission stays.
            super().do_POST()
        do_HEAD=denied
        do_PUT=denied
        do_PATCH=denied
        do_DELETE=denied
        do_OPTIONS=denied
    return ThetaOnly


def child(args):
    # This bootstrap is operational, not the test-only fixture bootstrap. The
    # OS probe must prove isolation before any KRONOS import/default constructor.
    probe=args.root/'support/kernel-denial-probe'
    info=probe.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o600:
        raise ValueError('THETA_TRIAL_KERNEL_PROTECTION_MISSING')
    try: probe.read_bytes()
    except PermissionError: pass
    else: raise ValueError('THETA_TRIAL_KERNEL_PROTECTION_MISSING')
    if args.denied_port is None: raise ValueError('THETA_TRIAL_KERNEL_PROTECTION_MISSING')
    with socket.socket() as client:
        try: client.connect(('127.0.0.1',args.denied_port))
        except PermissionError: pass
        else: raise ValueError('THETA_TRIAL_NETWORK_PROTECTION_MISSING')
    support=args.root/'support/home'
    Path.home=classmethod(lambda cls: cls(support))  # No HOME/environment reassignment.
    temporary=args.root/'support/tmp';temporary.mkdir(mode=0o700,exist_ok=True)
    tempfile.tempdir=str(temporary)
    sys.path.insert(0,str(REPOSITORY/'src'))
    from kronos.theta.operational import TrialPaths,compose,admit_originals
    from kronos.application.swing_opportunities import SwingOpportunitiesApplication
    from kronos.browser.product_routes import ProductBrowserRoutes
    from kronos.browser.theta_routes import ThetaBrowserRoutes
    from kronos.browser.server import create_browser_server
    from threading import Thread
    import signal
    app,metadata=compose(TrialPaths(args.root,args.inbox,args.outbox,args.mode))
    located=original_manifest(args)
    if located:
        from hashlib import sha256
        originals={}
        for role,item in located.items():
            raw=safe_file(Path(item['path']),16*1024*1024)
            if sha256(raw).hexdigest()!=item['sha256']:raise ValueError('THETA_TRIAL_ORIGINAL_INVALID')
            originals[role]={'payload':raw,'sha256':item['sha256'],'media_type':item['media_type']}
        admit_originals(app,originals,sponsor_confirmed=True)
    calls=[]
    def forbidden():
        calls.append('FORBIDDEN');raise RuntimeError('THETA_TRIAL_PROVIDER_FORBIDDEN')
    route=ThetaBrowserRoutes(app.workflow,sponsor_workflow=app)
    if args.mode=='SYNTHETIC_REHEARSAL':
        original=route._page
        def marked(snapshot,body,**options):
            return original(snapshot,'<p role="status"><strong>SYNTHETIC — NOT FOR GENUINE FORECASTING</strong> · TE-09R disposable rehearsal.</p>'+body,**options)
        route._page=marked
    server=create_browser_server(SwingOpportunitiesApplication(forbidden),port=args.port,
        product_routes=ProductBrowserRoutes((route,)))
    server.RequestHandlerClass=handler(server.RequestHandlerClass,args.mode)
    server.service_actions=lambda: None  # No unrelated product lifecycle pulse.
    print(json.dumps({'status':'READY','pid':os.getpid(),'port':server.server_port,
        'mode':args.mode,'qualification_mode':False,'target_count':10,
        'url':f'http://127.0.0.1:{server.server_port}/theta-earners'}),flush=True)
    def stop(*_): Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try: server.serve_forever(poll_interval=.25)
    finally:
        server.server_close()
        print(json.dumps({'status':'STOPPED','provider_calls':len(calls),'broker_operations':0,'astra_api_calls':0}),flush=True)
        if calls: raise RuntimeError('THETA_TRIAL_PROHIBITED_ACTIVITY')


def main(argv=None):
    args=arguments(argv);preflight(args)
    if args.child: child(args);return 0
    # No arbitrary existing root adoption. Operational compose also verifies its
    # immutable ownership before permitting any evidence access.
    args.root.mkdir(mode=0o700,parents=False,exist_ok=True)
    support=args.root/'support';support.mkdir(mode=0o700,exist_ok=True)
    (support/'home').mkdir(mode=0o700,exist_ok=True)
    (support/'tmp').mkdir(mode=0o700,exist_ok=True)
    probe=support/'kernel-denial-probe'
    if probe.is_symlink(): raise ValueError('THETA_TRIAL_PATH_INVALID')
    fd=os.open(probe,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600) if not probe.exists() else None
    if fd is not None: os.write(fd,b'THETA_TRIAL_KERNEL_PROBE\n');os.close(fd)
    located=original_manifest(args)
    raw=policy(args.root,args.inbox,args.outbox,args.port,probe,[Path(i['path']) for i in located.values()]).encode()
    policy_file=support/('operational-'+hashlib.sha256(raw).hexdigest()+'.sb')
    # Caller-controlled support file is not analytical authority; never follow it.
    if policy_file.exists():
        info=policy_file.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or policy_file.read_bytes()!=raw:
            raise ValueError('THETA_TRIAL_POLICY_CONFLICT')
    else:
        fd=os.open(policy_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream: stream.write(raw)
    # Only non-secret process basics; no credential/session environment copied.
    env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL','LC_CTYPE','TMPDIR','USER','LOGNAME'}}
    env.update(PYTHONPATH=str(REPOSITORY/'src'),PYTHON_DOTENV_DISABLED='1',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    env['TMPDIR']=str(support/'tmp')
    with socket.socket() as blocked:
        blocked.bind(('127.0.0.1',0));blocked.listen(1)
        command=['/usr/bin/sandbox-exec','-f',str(policy_file),sys.executable,'-I','-B',str(Path(__file__).resolve()),
            '--child','--mode',args.mode,'--root',str(args.root),'--inbox',str(args.inbox),
            '--outbox',str(args.outbox),'--port',str(args.port),'--denied-port',str(blocked.getsockname()[1])]
        if args.originals_manifest:command+=['--originals-manifest',str(args.originals_manifest),'--sponsor-confirmed-originals']
        return subprocess.call(command,cwd=REPOSITORY,env=env)


if __name__=='__main__':
    try: raise SystemExit(main())
    except (OSError,ValueError,KeyError) as failure:
        print('THETA_TRIAL_STARTUP_REJECTED:'+type(failure).__name__,file=sys.stderr);raise SystemExit(78)
