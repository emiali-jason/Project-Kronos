"""Actual C-main integration with an explicitly synthetic offline installation.

No production authority is issued by this fixture.  Only the canonical bundle
location, account-home lookup and signature/UI syscall leaves are substituted
in a disposable copy.  The actual C main, Darwin process identity, private
preparation selection, broker, native codecs, Python pinned imports and Browser
owners are kept.  Synthetic Git object metadata describes these exact copied
bytes; no candidate/canonical Git state is changed.
"""
from dataclasses import dataclass
from hashlib import sha256
import ast
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()


def _replace_function(source, name, body):
    tree=ast.parse(source)
    node=next(node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name==name)
    lines=source.splitlines(keepends=True)
    return "".join(lines[:node.body[0].lineno-1])+body+"".join(lines[node.end_lineno:])


def _replace_c_function(source,name,body):
    start=source.index("static int "+name+"(")
    opening=source.index("{",start)
    depth,index=1,opening+1
    while depth:
        if source[index]=="{":depth+=1
        elif source[index]=="}":depth-=1
        index+=1
    return source[:opening+1]+body+source[index-1:]


@dataclass
class NativeInstallation:
    home: Path
    repository: Path
    bundle: Path
    executable: Path
    substitutions: list
    port: int
    revision: str
    install_receipt: dict | None = None

    @property
    def estate(self):return self.home/"Library/Application Support/KRONOS/runtime"

    def environment(self, *, mode=None):
        environment={key:value for key,value in os.environ.items()
            if not key.startswith(("KRONOS_","KITE_","OPENAI_","TELEGRAM_"))}
        environment.update(HOME=str(self.home),PYTHONDONTWRITEBYTECODE="1",PYTHON_DOTENV_DISABLED="1",
            PYTHONNOUSERSITE="1")
        # Retain the harness's immutable manifest as diagnostic/isolation
        # context; it is never a recovery selector or product authority.
        environment["KRONOS_TEST_ISOLATION_MANIFEST"]=os.environ["KRONOS_TEST_ISOLATION_MANIFEST"]
        if mode:environment["KRONOS_LAUNCH_MODE"]=mode
        return environment

    def start_main(self,mode):
        return subprocess.Popen([str(self.executable)],env=self.environment(mode=mode),
            cwd=self.repository,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0)

    def trace(self,name,payload):
        target=self.home/(name+".json")
        raw=_canonical(payload);target.write_bytes(raw)
        retained=ROOT.parent/"native-integration-evidence"/sha256(str(self.home).encode()).hexdigest()[:16]
        retained.mkdir(parents=True,exist_ok=True)
        destination=retained/target.name
        with destination.open("xb") as stream:stream.write(raw)
        print("NATIVE_STAGE_TRACE",name,str(destination),sha256(raw).hexdigest())
        return destination


def _fixture_repository(repository):
    """Populate disposable Git objects; never a source publication command."""
    def git(*args,input=None):
        result=subprocess.run(["git",*args],cwd=repository,input=input,capture_output=True)
        assert result.returncode==0,result.stderr.decode()
        return result.stdout.strip().decode()
    git("init","--quiet","--initial-branch=develop")
    (repository/".gitignore").write_text(".venv/\n__pycache__/\n*.pyc\n")
    git("add",".")
    tree=git("write-tree")
    # A synthetic test object, constructed without git commit, hooks or publish.
    content=("tree "+tree+"\nauthor Synthetic Fixture <fixture@invalid> 1792713600 +0000\n"
        "committer Synthetic Fixture <fixture@invalid> 1792713600 +0000\n\n"
        "Synthetic isolated integration source; no production approval.\n").encode()
    revision=git("hash-object","-t","commit","-w","--stdin",input=content)
    (repository/".git/refs/heads/develop").write_text(revision+"\n")
    remote=repository/".git/refs/remotes/origin";remote.mkdir(parents=True)
    (remote/"develop").write_text(revision+"\n")
    git("config","remote.origin.url",str(repository/".git"))
    git("config","branch.develop.remote","origin")
    git("config","branch.develop.merge","refs/heads/develop")
    assert git("status","--porcelain=v1","--untracked-files=all")==""
    assert git("ls-remote","--exit-code","origin","refs/heads/develop").split()==[revision,"refs/heads/develop"]
    return revision


@pytest.fixture
def native_installation(tmp_path):
    isolation=json.loads(Path(os.environ["KRONOS_TEST_ISOLATION_MANIFEST"]).read_text())
    port=isolation["allowed_ports"][0]
    assert port!=8947
    home=tmp_path/"synthetic-home";home.mkdir(mode=0o700)
    repository=home/"Documents/GitHub/Project-Kronos";repository.mkdir(parents=True)
    for directory in ("src","tools","data","assets","docs"):
        shutil.copytree(ROOT/directory,repository/directory,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    shutil.copyfile(ROOT/"pyproject.toml",repository/"pyproject.toml")
    # Package the disposable qualified copy with the strict source-pinner's
    # real owner-write-only policy. Do not change the candidate checkout modes.
    for path in repository.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    # The current harness interpreter is reused read-only; no environment install.
    (repository/".venv/bin").mkdir(parents=True)
    (repository/".venv/bin/python").symlink_to(sys.executable)
    environment_root=Path(sys.executable).parent.parent
    if (environment_root/"pyvenv.cfg").exists():
        shutil.copyfile(environment_root/"pyvenv.cfg",repository/".venv/pyvenv.cfg")
        (repository/".venv/lib").symlink_to(environment_root/"lib",target_is_directory=True)
    bundle=home/"Applications/KRONOS.app"
    executable=bundle/"Contents/MacOS/KRONOS";executable.parent.mkdir(parents=True)
    substitutions=[]
    def change(relative,transform,reason):
        path=repository/relative;before=path.read_text();after=transform(before)
        assert before!=after,relative
        path.write_text(after)
        substitutions.append(dict(path=relative,reason=reason,before=sha256(before.encode()).hexdigest(),after=sha256(after.encode()).hexdigest()))
    old="/Applications/KRONOS.app"
    # Signature qualification is an explicit synthetic fixture boundary.  No
    # security tool is invoked and no sandbox/security permission is changed.
    def python_leaves(source):
        source=source.replace(old,str(bundle)).replace(
            "Path(pwd.getpwuid(os.geteuid()).pw_dir)","Path("+json.dumps(str(home))+")")
        source=source.replace('["/usr/bin/codesign", "--verify", "--deep", "--strict",',
            '[sys.executable, "-c", "pass", "--synthetic-signature",')
        return source
    for relative in ("tools/runtime_source_gate.py","tools/failed_fenced_launcher.py","src/kronos/common/failed_fenced_startup.py"):
        def diagnostic_leaves(text,relative=relative):
            text=python_leaves(text)
            if relative=="tools/failed_fenced_launcher.py":
                text=text.replace('from __future__ import annotations\n',
                    'from __future__ import annotations\nimport faulthandler\nfaulthandler.dump_traceback_later(4,repeat=True)\n',1)
                text=text.replace('            run_native_recovery(context)\n',
                    '            try: run_native_recovery(context)\n            finally: print("FIXTURE_NATIVE_CALL_TIMINGS",__import__("json").dumps(getattr(context.registry.codec._exchange,"_fixture_call_times",{})),file=__import__("sys").stderr)\n',1)
                text=text.replace('    import struct\n    from kronos.common.failed_fenced_startup import NativeSemanticExchange',
                    '    import struct\n    if __import__("pathlib").Path('+repr(str(home/"fixture-native-guard-stall"))+').exists():__import__("time").sleep(16)\n    from kronos.common.failed_fenced_startup import NativeSemanticExchange',1)
            if relative=="src/kronos/common/failed_fenced_startup.py":
                text=text.replace('    def native_call(self, kind, payload):\n',
                    '    def native_call(self, kind, payload):\n        fixture_t=__import__("time").monotonic()\n        try: return self._fixture_native_call(kind,payload)\n        finally:\n            fixture_rows=getattr(self,"_fixture_call_times",{})\n            fixture_row=fixture_rows.setdefault(kind,[0,0.0]);fixture_row[0]+=1;fixture_row[1]+=__import__("time").monotonic()-fixture_t\n            self._fixture_call_times=fixture_rows\n    def _fixture_native_call(self, kind, payload):\n',1)
                before='    if observed != expected or any(dict(observed).get(name) != value for name, value in startup.loaded_modules):'
                assert text.count(before)==1
                text=text.replace(before,
                    '    print("FIXTURE_BOOTSTRAP_SET", __import__("json").dumps(dict(expected=expected,observed=observed,startup=startup.loaded_modules)),file=__import__("sys").stderr)\n'+before)
            return text
        change(relative,diagnostic_leaves,"Disposable native passwd/canonical location, synthetic signature subprocess leaf, helper diagnostic timer only")
    def early_account_fixture_leaf(text):
        # The child deny-only budget parser intentionally precedes all product
        # imports and cannot use the later runtime_source_gate fixture leaf.
        # Substitute the same native account observation in this disposable
        # source copy only; keep its parser, FD3, MAC and deadline checks exact.
        expression = "Path(pwd.getpwuid(os.geteuid()).pw_dir)"
        assert text.count(expression) == 1
        return text.replace(expression, "Path(" + json.dumps(str(home)) + ")", 1)
    change("tools/kronos_browser.py",early_account_fixture_leaf,
        "Exactly one early stdlib native account observation maps to the same disposable fixture home; no production parser or sandbox change")
    substitutions[-1]["source_occurrences"] = 1
    def package_fixture_leaves(text):
        text=text.replace("run('/usr/bin/codesign', '--verify',", "run('/usr/bin/true', '--verify',")
        # Observe the exact failed native predicate; never change its result.
        text=text.replace("                    raise PackageError('PACKAGE_RETAINED_CHANGED')\n            finally: os.close(reopened)",
            "                    print('FIXTURE_PACKAGE_CHAIN_CHANGED',__import__('json').dumps(dict(component=name,before=identity,retained=_descriptor_identity(os.fstat(child)),named=_descriptor_identity(os.fstat(reopened)))),file=__import__('sys').stderr)\n                    raise PackageError('PACKAGE_RETAINED_CHANGED')\n            finally: os.close(reopened)")
        return text
    change("tools/macos/package_launcher.py",package_fixture_leaves,
        "Synthetic signature syscall and diagnostic-only failed ancestor metadata; unchanged native manifest/path/mode/hash predicates")
    def server_fixture_diagnostics(text):
        before='            except (OSError, ValueError):\n                if claimed:'
        after="            except (OSError, ValueError) as fixture_error:\n                print('FIXTURE_ORIGINAL_POST_DENIAL',type(fixture_error).__name__,str(fixture_error)[:160],file=__import__('sys').stderr)\n                __import__('traceback').print_exception(type(fixture_error),fixture_error,fixture_error.__traceback__)\n                if claimed:"
        assert text.count(before)==1
        return text.replace(before,after,1)
    change("src/kronos/browser/server.py",server_fixture_diagnostics,
        "Diagnostic-only actual maintenance exception class/code; unchanged admission, authority, currentness and response predicates")

    def recovery_fixture_diagnostics(text):
        before='    def fail(self,error):\n        """Retain a bounded pre-seal failure; never write after the seal."""\n'
        after=before+"""        print('FIXTURE_RECOVERY_TRANSACTION_DENIAL',type(error).__name__,str(error),file=__import__('sys').stderr)
        fixture_tb=error.__traceback__
        while fixture_tb is not None:
            fixture_frame=fixture_tb.tb_frame
            if (fixture_frame.f_code.co_name=='verify_native_cleanup_result'
                    and fixture_frame.f_code.co_filename.endswith('/kronos/application/failed_fenced_owners.py')):
                fixture_payload=fixture_frame.f_locals.get('payload',{})
                fixture_detail={key:fixture_payload.get(key) for key in ('owner','action','resource','operation')}
                for fixture_key in ('retained','facts'):
                    fixture_values=fixture_frame.f_locals.get(fixture_key,{})
                    if type(fixture_values) is dict:
                        fixture_detail[fixture_key]={key:value for key,value in fixture_values.items()
                            if value is None or type(value) in (str,int,bool)}
                print('FIXTURE_EXACT_CLEANUP_FACTS_DENIAL',__import__('json').dumps(fixture_detail,sort_keys=True),file=__import__('sys').stderr)
            fixture_tb=fixture_tb.tb_next
        __import__('traceback').print_exception(type(error),error,error.__traceback__)
"""
        assert text.count(before)==1
        return text.replace(before,after,1)
    change("src/kronos/common/failed_fenced_recovery.py",recovery_fixture_diagnostics,
        "Diagnostic-only original recovery failure class/message/stack without locals; unchanged failure handling and authority validation")

    def owner_fixture_diagnostics(text):
        before='            except Exception:\n                # Native projection failures'
        after="            except Exception as fixture_error:\n                print('FIXTURE_NATIVE_CALLBACK_DENIAL',role,type(fixture_error).__name__,str(fixture_error)[:160],file=__import__('sys').stderr)\n                __import__('traceback').print_exception(type(fixture_error),fixture_error,fixture_error.__traceback__)\n                # Native projection failures"
        assert text.count(before)==1
        return text.replace(before,after,1)
    change("src/kronos/application/failed_fenced_owners.py",owner_fixture_diagnostics,
        "Diagnostic-only actual original callback exception trace; no callback replay or validation changes")
    def lifecycle_fixture_diagnostics(text):
        before='        except BaseException:\n            with self._work_lock:\n                self._rejected_work'
        after="        except BaseException as fixture_error:\n            print('FIXTURE_NATIVE_CALLER_DENIAL',type(fixture_error).__name__,str(fixture_error)[:160],file=__import__('sys').stderr)\n            __import__('traceback').print_exception(type(fixture_error),fixture_error,fixture_error.__traceback__)\n            with self._work_lock:\n                self._rejected_work"
        assert text.count(before)==1
        return text.replace(before,after,1)
    change("src/kronos/application/intraday_lifecycle.py",lifecycle_fixture_diagnostics,
        "Diagnostic-only exact original worker exception trace; no workflow, source or failure-handling changes")

    def browser_fixture_leaves(text):
        text=text.replace('default=8947','default='+str(port)).replace(
            'import argparse\n','import argparse\nimport faulthandler\nfaulthandler.dump_traceback_later(7,repeat=True)\n',1)
        for stage, before in (
            ('EARLY_BUDGET', '_RECOVERY_EARLY_BUDGET = _inherited_recovery_budget(os.environ)'),
            ('CAPTURE_ENTER', 'with StartupCapture(Path(__file__).resolve().parents[1], keep_sources_pinned=True,'),
            ('CAPTURE_RETURN', 'del _startup_capture'),
            ('PREPARATION_ENTER', '        authority, canonical_factory = load_child_preparation('),
            ('PREPARATION_RETURN', '        recovery_child = prepare_child_startup(authority, _STARTUP_EVIDENCE, os.environ)'),
            ('BOOTSTRAP_RETURN', '        if prepared_runtime is not None:\n            raise RecoveryStartupError("RECOVERY_CHILD_RUNTIME_FACTORY_SUBSTITUTION")'),
        ):
            assert text.count(before) == 1, before
            indent = before[:len(before)-len(before.lstrip())]
            marker = indent + "print('FIXTURE_CHILD_STAGE " + stage + "',__import__('time').clock_gettime_ns(__import__('time').CLOCK_MONOTONIC),file=__import__('sys').stderr)\n"
            text = text.replace(before, marker + before)
        # Hold the return of the actual replace syscall once, after native
        # pre-effect accounting and actual pointer replacement. Native fsync,
        # callback/caller completion and durable reference remain unchanged.
        hook="""
        if child_session is None and Path(%r).exists():
            import os as fixture_os,time as fixture_time
            fixture_native_replace=fixture_os.replace
            fixture_held=[False]
            def fixture_publication_return(source,destination,*a,**kw):
                result=fixture_native_replace(source,destination,*a,**kw)
                if not fixture_held[0] and '/prospective-v2-wo11-lifecycle/current/' in str(destination):
                    fixture_held[0]=True
                    Path(%r).write_text('ACTUAL_WO11_REPLACE_RETURN_HELD_AFTER_PRE_EFFECT')
                    fixture_stop=fixture_time.monotonic()+30
                    while not Path(%r).exists():
                        if fixture_time.monotonic()>=fixture_stop:
                            raise RuntimeError('SYNTHETIC_FIXTURE_HOLD_NOT_RELEASED')
                        fixture_time.sleep(.001)
                return result
            fixture_os.replace=fixture_publication_return
            fixture_admitted=server.intraday_lifecycle.request_pulse()
            Path(%r).write_text(__import__('json').dumps(dict(admitted=fixture_admitted,
                work=server.intraday_lifecycle.work_status(),last_failure=server.intraday_lifecycle.last_failure,
                store_root=str(server.intraday_lifecycle.store.root))))
            if not fixture_admitted:
                raise RuntimeError('SYNTHETIC_FIXTURE_NATIVE_CALLER_NOT_ADMITTED')
"""%(str(home/"fixture-native-wo11-enable"),str(home/"fixture-native-wo11-return-held"),str(home/"fixture-native-wo11-release"),str(home/"fixture-native-wo11-admission"))
        return text.replace('        url = f"http://127.0.0.1:{server.server_port}/swing/opportunities"',
            hook+'        url = f"http://127.0.0.1:{server.server_port}/swing/opportunities"',1)
    change("tools/kronos_browser.py",browser_fixture_leaves,
        "Harness ephemeral port; read-only trace timer; optional original-only native WO11 request and actual syscall-return barrier, no authority substitution")
    def native_leaves(source):
        source=source.replace(old,str(bundle)).replace("8947",str(port))
        source=source.replace('struct passwd *account=getpwuid(geteuid());',
            'struct passwd *account=getpwuid(geteuid()); struct passwd fixture_account; if(account){fixture_account=*account;fixture_account.pw_dir='+json.dumps(str(home))+';account=&fixture_account;}')
        # The canonical-parent probe has its own signature subprocess leaf.
        # Keep its actual subprocess/exit/deadline handling while substituting
        # only the forbidden production signing tool in this synthetic bundle.
        signature_leaf='char *arguments[]={"/usr/bin/codesign","--verify","--deep","--strict",'
        assert source.count(signature_leaf)==1
        source=source.replace(signature_leaf,
            'char *arguments[]={"/usr/bin/true","--verify","--deep","--strict",')
        source=_replace_c_function(source,"canonical_signature_valid","\n    /* Synthetic signature leaf only; actual package authority is not tested. */\n    return 1;\n")
        source=_replace_c_function(source,"open_workspace","\n    (void)workspace_script; return 0; /* No browser automation in this fixture. */\n")
        source=_replace_c_function(source,"show_alert",'\n    fprintf(stderr,"FIXTURE_ALERT:%s:%s\\n",title,message); return 1; /* No macOS UI in this fixture. */\n')
        # Preserve actual failing child/helper tracebacks in an isolated sink.
        # Protocol stdout/pipe framing, dispatch, process ownership are intact.
        sink=json.dumps(str(home/"actual-child-stderr.log"))
        source=source.replace('(void)dup2(devnull, STDERR_FILENO);',
            '{int fixture_log=open('+sink+',O_WRONLY|O_CREAT|O_APPEND,0600);if(fixture_log>=0){(void)dup2(fixture_log,STDERR_FILENO);close(fixture_log);}}')
        source=source.replace('int null=open("/dev/null",O_WRONLY);',
            'int null=open('+sink+',O_WRONLY|O_CREAT|O_APPEND,0600);')
        source=source.replace('int null=open("/dev/null",O_RDWR);if(null<0||dup2(null,0)!=0||dup2(null,1)!=1||dup2(null,2)!=2)_exit(92);if(null>3)close(null);',
            'int null=open("/dev/null",O_RDWR);if(null<0||dup2(null,0)!=0||dup2(null,1)!=1)_exit(92);if(null>3)close(null);int fixture_log=open('+sink+',O_WRONLY|O_CREAT|O_APPEND,0600);if(fixture_log<0||dup2(fixture_log,2)!=2)_exit(92);if(fixture_log>3)close(fixture_log);')
        source=source.replace('char *pinned_script = ffr3_ordinary_pin_script(repository,python,&native_startup);',
            'char *pinned_script = ffr3_ordinary_pin_script(repository,python,&native_startup); fprintf(stderr,"FIXTURE_NATIVE_PIN_BYTES=%zu\\n",pinned_script?strlen(pinned_script):0);')
        source=source.replace('char *plan=NULL,*plan_ref=NULL;if(!ffr3_open_static(p,&plan,&plan_ref))return NULL;',
            'char *plan=NULL,*plan_ref=NULL;if(!ffr3_open_static(p,&plan,&plan_ref)){fprintf(stderr,"FIXTURE_STATIC_OPEN_DENIED\\n");return NULL;}')
        source=source.replace('free(map);free(plan);free(plan_ref);if(!script)ffr3_release_preparation(p);return script;',
            'fprintf(stderr,"FIXTURE_STATIC_SCRIPT=%d\\n",script!=NULL); free(map);free(plan);free(plan_ref);if(!script)ffr3_release_preparation(p);return script;')
        source=source.replace('if(valid)s->child_process=strdup(process);',
            'fprintf(stderr,"FIXTURE_CHILD_IDENTITY valid=%d bytes=%zu present=%d now=%llu stop=%llu\\n",valid,bytes,identity!=NULL,ffr3_now_ns(),(unsigned long long)s->prepared->stop.tv_sec*1000000000ULL+(unsigned long long)s->prepared->stop.tv_nsec);if(valid)s->child_process=strdup(process);')
        # Non-authoritative isolated stage timing; no protocol/authority input.
        for before, after in (
            ('char *script=ffr3_product_script(s,repository);if(!script)return NULL;',
             'fprintf(stderr,"FIXTURE_R3_STAGE SCRIPT_ENTER %llu\\n",ffr3_now_ns());char *script=ffr3_product_script(s,repository);fprintf(stderr,"FIXTURE_R3_STAGE SCRIPT_RETURN %llu\\n",ffr3_now_ns());if(!script)return NULL;'),
            ('pid_t child=fork();s->product=child;',
             'fprintf(stderr,"FIXTURE_R3_STAGE FORK_ENTER %llu\\n",ffr3_now_ns());pid_t child=fork();fprintf(stderr,"FIXTURE_R3_STAGE FORK_RETURN %llu PID %ld\\n",ffr3_now_ns(),(long)child);s->product=child;'),
            ('if(!failed_fenced_child_descriptor(channel[0],channel[1])||setsid()<0)_exit(91);',
             'fprintf(stderr,"FIXTURE_R3_STAGE DESCRIPTORS_ENTER %llu\\n",ffr3_now_ns());if(!failed_fenced_child_descriptor(channel[0],channel[1])||setsid()<0)_exit(91);fprintf(stderr,"FIXTURE_R3_STAGE DESCRIPTORS_RETURN %llu\\n",ffr3_now_ns());'),
            ('execl(python,python,"-I","-B","-c",script,(char*)NULL);_exit(95);',
             'fprintf(stderr,"FIXTURE_R3_STAGE EXEC_ENTER %llu\\n",ffr3_now_ns());execl(python,python,"-I","-B","-c",script,(char*)NULL);_exit(95);'),
        ):
            assert source.count(before) == 1, before
            source = source.replace(before, after)
        return source
    change("tools/macos/kronos_launcher.c",native_leaves,
        "Disposable bundle/account home, synthetic signature and inert macOS UI syscall leaves; actual main unchanged")
    compiled=subprocess.run(["clang","-Wall","-Wextra","-Werror",str(repository/"tools/macos/kronos_launcher.c"),
        "-o",str(executable)],capture_output=True,text=True)
    assert compiled.returncode==0,compiled.stderr
    from tools.macos.package_launcher import RESOURCES
    for name in RESOURCES:
        destination=bundle/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/"tools/macos/KRONOS.app"/name,destination)
    signature=bundle/"Contents/_CodeSignature/CodeResources";signature.parent.mkdir()
    signature.write_bytes(b"SYNTHETIC CodeResources; not actual artifact signature qualification\n")
    for path in (bundle,*bundle.rglob("*")):
        path.chmod(0o755 if path.is_dir() or path==executable else 0o644)
    # Exercise the existing installer retention layout, not an invented rollback
    # location. Only its signature syscall leaf is synthetic; actual manifest,
    # copy, fsync, renamex_np swap and independent readbacks execute.
    from tools.macos import package_launcher
    candidate=home/"synthetic-unlaunched-candidate/KRONOS.app"
    candidate.parent.mkdir()
    shutil.copytree(bundle,candidate)
    (candidate/"Contents/_CodeSignature/CodeResources").write_bytes(b"SYNTHETIC successor CodeResources; not actual artifact qualification\n")
    old_id=package_launcher.identity(bundle);new_id=package_launcher.identity(candidate)
    original_run=package_launcher.run
    def verify_signature_leaf(*args,**kwargs):
        if args[:2]==('/usr/bin/codesign','--verify'):
            return subprocess.CompletedProcess(args,0,stdout=b'',stderr=b'SYNTHETIC SIGNATURE QUALIFICATION BOUNDARY')
        return original_run(*args,**kwargs)
    package_launcher.run=verify_signature_leaf
    try:
        receipt=package_launcher.install(candidate,bundle,rollback=home/"synthetic-explicit-rollback/KRONOS.app",
            candidate_identity=new_id,installed_identity=old_id)
    finally:package_launcher.run=original_run
    assert receipt["launched"] is False and package_launcher.identity(Path(receipt["exchanged_original"]))==old_id
    # Exact source-copy inventory accounts for every permitted substitution.
    changed={row["path"] for row in substitutions}
    for prefix in ("src","tools"):
        for original in (ROOT/prefix).rglob("*"):
            if not original.is_file() or "__pycache__" in original.parts or original.suffix==".pyc":continue
            relative=original.relative_to(ROOT).as_posix();copied=repository/relative
            if relative not in changed:assert copied.read_bytes()==original.read_bytes(),relative
    revision=_fixture_repository(repository)
    installation=NativeInstallation(home,repository,bundle,executable,substitutions,port,revision,receipt)
    installation.trace("fixture-boundaries",dict(synthetic=True,production_authority=False,
        source_revision=revision,source_substitutions=substitutions,executable_sha256=sha256(executable.read_bytes()).hexdigest(),port=port))
    return installation


def _private_estate(installation):
    from kronos.common.failed_fenced_recovery import RecoveryStore, canonical_bytes
    installation.estate.mkdir(parents=True,mode=0o700)
    # Newly made ancestors are fixture-only, all authoritative leaves private.
    installation.estate.chmod(0o700)
    store=RecoveryStore(installation.estate)
    scope=dict(schema="KRONOS_FAILED_FENCED_GUARD_SCOPE_V1",version="1.0.0",
        service="synthetic-service",installation="synthetic-installation",policy="MANDATORY")
    store.provision(scope,sha256(canonical_bytes(scope)).hexdigest())
    return store


def _seed_synthetic_swing_original(installation):
    """Create a real governed fixture publication, never a production history."""
    from tests.unit.swing.test_run_publication import scenario,make_checkpoint
    from kronos.swing.v1.mtf_facts import MtfFactEvidenceStore
    from kronos.swing.v1.native_discovery import NativeDiscoveryEvidenceStore
    from kronos.swing.v1.relative_context import RelativeContextEvidenceStore,build_relative_context_run
    from kronos.swing.run_provenance import LocalSwingRunProvenanceStore
    from kronos.swing.run_publication import SwingRunPublication
    from kronos.swing.universe import SWING_PHASE1_UNIVERSE
    from kronos.swing.v1 import opportunity_continuity as continuity
    from tests.unit.swing.test_run_publication import provenance
    root=installation.home/"Library/Application Support/KRONOS/evidence/swing-v1"
    snapshot,bindings=scenario.__wrapped__()
    coordinator=SwingRunPublication(root/"run-publication-v1",mtf_store=MtfFactEvidenceStore(root/"current-governed-mtf"),
        native_store=NativeDiscoveryEvidenceStore(root/"native-discovery"),relative_store=RelativeContextEvidenceStore(root/"relative-context-v1"),
        provenance_store=LocalSwingRunProvenanceStore(root/"run-provenance"))
    native=continuity.prepare_continuity(snapshot,bindings).native_run
    for owner,value in ((coordinator.mtf_store,snapshot),(coordinator.native_store,native),
        (coordinator.relative_store,build_relative_context_run(snapshot,SWING_PHASE1_UNIVERSE)),(coordinator.provenance_store,provenance(snapshot))):
        owner.retain(value)
    references=coordinator._references(snapshot.run_identity,continuity=False)
    current=coordinator.adopt(snapshot.run_identity,{key:value for key,value in references.items() if key!="continuity"})
    installation.trace("synthetic-swing-original",dict(synthetic=True,market_data="TEST_FIXTURE_NOT_ACQUIRED",run=snapshot.run_identity,
        committed=str(current.reference)))
    return current



def _seed_synthetic_wo11_original(installation):
    """Existing governed experimental Native→WO12→WO09→WO10 owner fixture.

    All market requests here terminate in the existing in-memory test adapter.
    Its actual invocations are counted separately from zero external calls.
    No compatibility origin is invented for the distinct legacy WO10 identity.
    """
    from tests.unit.application.test_iwo_experimental_rehearsal import configured_experimental_runtime
    from tests.unit.application.test_intraday_discovery_operation import _request_at
    from kronos.application.intraday_discovery_operation import DiscoveryOperationState
    from kronos.application.intraday_lifecycle_intake import load_intake
    from kronos.intraday.wo11_lifecycle import arm
    from kronos.intraday.wo09_experimental import origin_from
    seed=installation.home/"synthetic-offline-experimental-native-source-graph"
    runtime,shared,clock,stage,calls=configured_experimental_runtime(seed,"LONG")
    try:
        stage[0]="SYNTHETIC_FIVE_OF_FIVE"
        result=runtime.discovery_v2_operation.execute(_request_at("SYNTHETIC-ORIGINAL-EXPERIMENTAL-NATIVE",clock[0]))
        assert result.state is DiscoveryOperationState.COMPLETE,str(result)
        candidates=[r for _,r in runtime.wo09_application.restore()
            if r.canonical_subject_identity=="NSE-EQ-LUPIN" and r.satisfied_count==5]
        assert len(candidates)==1
        readiness=candidates[0]
        handoff=runtime.wo09_application.create_handoff(readiness,created_at=clock[0])
        assert handoff.authority=="EXPERIMENTAL_PAPER_ONLY"
        comparison=runtime.futures_application.construct_current(handoff_identity=handoff.handoff_identity,
            request_identity="SYNTHETIC-EXACT-NSE-FUTURE")
        assert comparison.schema=="WO10_SPONSOR_COMPARISON_V1" and comparison.data["executability"]=="EXECUTABLE",comparison.data
        session=runtime.lifecycle_application.session_source(readiness.canonical_subject_identity,clock[0])
        selection=runtime.futures_application.select(comparison.identity,choice="SELECTED_FUTURE",lots=1,
            session=session,action_identity="SYNTHETIC-OFFLINE-SELECT")
        selected=next(item for item in runtime.futures_application.store.records("WO10_SELECTED_TRADE_HANDOFF_V1")
            if item.data["selection_identity"]==selection.identity)
        intake=load_intake(runtime.futures_application,selected.identity,session=session,
            now=clock[0],eligibility=runtime.futures_application.eligibility)
        transition=arm(intake,truth_class="PAPER_OBSERVATION",action_identity="synthetic-offline-original",action_at=clock[0])
        claim=next(item.data["claim"]for item in transition.evidence if item.schema=="WO11_AUTHORIZATION_V1")
        assert runtime.lifecycle_application.store.publish(transition,claim=claim,previous=None)==transition.current
        origin=origin_from(readiness.origin_document)
        assert runtime.research_store.load(origin.identity)==origin
        assert intake.data["experimental_opportunity_identity"]==origin.data["opportunity_identity"]
        # No active business/observer work of WO17 is used or enabled by setup.
        wo17=runtime.wo17_monitoring.work_status()
        assert wo17["owned_workers"]==0 and wo17["queued_items"]==0 and wo17["generation"] is None
        source=seed/"evidence"
        evidence=installation.home/"Library/Application Support/KRONOS/evidence/intraday-v1"
        shutil.copytree(source,evidence,dirs_exist_ok=True)
        assert all((evidence/path.relative_to(source)).read_bytes()==path.read_bytes()
                   for path in source.rglob("*") if path.is_file())
        from kronos.intraday.wo10_futures_contract import normalize
        adapter_calls=normalize(calls)
        installation.trace("synthetic-wo11-original",dict(synthetic=True,market_data="TEST_FIXTURE_NOT_ACQUIRED",
            original=transition.current.identity,claim=claim,original_state=transition.current.data["state"],
            native_intake=intake.identity,comparison=intake.data["comparison_identity"],
            source_profile="EXISTING_GOVERNED_EXPERIMENTAL_PAPER_ONLY",
            adapter_fixture="tests.unit.application.test_iwo_experimental_rehearsal.configured_experimental_runtime",
            in_memory_adapter_invocations=len(calls),in_memory_adapter_calls=adapter_calls,
            external_provider_calls=0,production_provider_calls=0,model_calls=0,actual_paper_execution=False,
            original_wo12_identity=origin.identity,original_opportunity_identity=origin.data["opportunity_identity"],
            origin_producer="EXISTING_NATIVE_PUBLICATION_LISTENER_RETAINED_ONLY",wo17_work=wo17))
        return transition.current
    finally:
        # Disposable fake Provider resources are setup only, never recovery
        # evidence and never a production connection or acquisition.
        shared.end_kronos_session()


def _line(process,seconds=5):
    assert select.select([process.stdout],[],[],seconds)[0],"Actual C did not report inert staging identity"
    raw=process.stdout.readline()
    assert raw,process.stderr.read().decode()
    return json.loads(raw)


def _native_declaration(installation):
    """Derive static declarations by composing the real copied native code.

    This is a qualification snapshot, not evidence that a future P/S has loaded
    it. Their eventual SOURCE proofs must separately bind their own startup.
    """
    program=r'''
import sys,json,os
from dataclasses import asdict
from pathlib import Path
sys.path[:0]=[str(Path.cwd()/"src"),str(Path.cwd())]
from kronos.intraday.runtime_identity import StartupCapture,LauncherConfiguration,canonical
with StartupCapture(Path.cwd(),keep_sources_pinned=True) as captured:
 from kronos.application.intraday_runtime import create_intraday_runtime
 from kronos.application.intraday_wo08_shadow import compose_wo08_shadow
 from kronos.provider.runtime import SharedAuthenticatedProviderRuntime
 from kronos.browser.intraday_probables_v2_control import IntradayProbablesV2OperationalControl
 startup=captured.finish()
shared=SharedAuthenticatedProviderRuntime(lambda:(_ for _ in ()).throw(AssertionError('NO_PROVIDER')),provider_identity='KITE')
root=Path.home()/"Library/Application Support/KRONOS/evidence/intraday-v1"
runtime=create_intraday_runtime(shared,evidence_root=root,startup_evidence=startup,wo08_shadow_factory=lambda:compose_wo08_shadow(root))
control=IntradayProbablesV2OperationalControl(runtime.discovery_v2_operation,runtime.probables_v2_application,
 runtime.refresh_v2_provenance_store,startup_evidence=startup,launcher_configuration=LauncherConfiguration(int(sys.argv[1]),False))
assert startup.source_state=='CLEAN_COMMIT' and startup.load_verification=='PINNED_STARTUP_IMPORTS'
from kronos.application.intraday_live_shadow import IntradayLiveShadowService
from kronos.intraday.live_shadow_persistence import ShadowStore
from datetime import datetime,timezone
shadow=IntradayLiveShadowService(store=ShadowStore(root),clock=lambda:datetime.now(timezone.utc))
shadow.bind_runtime(control._runtime_manifest)
shadow.accept_runtime(expected_revision=startup.source_revision,request_identity='SYNTHETIC_OFFLINE_ACCEPTANCE_NOT_PRODUCTION')
epoch=shadow._epochs.chain()[0];window,acceptance=shadow._epochs.bound(epoch)
print(json.dumps({'manifest':asdict(control._runtime_manifest),'native_window':window.payload.hex(),'native_epoch':epoch,'modules':[(name,__import__('hashlib').sha256(row[1]).hexdigest()) for name,row in sorted(captured._sources.items())]},default=lambda value:value.isoformat(),sort_keys=True,separators=(',',':')))
'''
    result=subprocess.run([sys.executable,"-I","-B","-c",program,str(installation.port)],
        cwd=installation.repository,env=installation.environment(),capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)


def _qualified_bootstrap_declaration(installation, source):
    """Offline exact entry/verifier closure; never rewrite a forked plan.

    Import the real entry without invoking main, followed by the fixed intent
    verifier adapters. The actual child must independently execute exactly this
    prequalified set and byte identities under the unchanged runtime guard.
    """
    program=r'''
import sys,json,hashlib
from pathlib import Path
sys.path[:0]=[str(Path.cwd()/"src"),str(Path.cwd())]
from tools import kronos_browser
from tools import failed_fenced_launcher,runtime_source_gate
from kronos.common import failed_fenced_startup,failed_fenced_compatibility
from kronos.intraday import failed_fenced_native_evidence,books_factual_contract
from kronos.intraday import live_shadow_acceptance
rows={}
for module in tuple(sys.modules.values()):
 spec=getattr(module,"__spec__",None);name=getattr(spec,"name",None)
 if type(name) is not str or not(name in {"kronos","tools"} or name.startswith(("kronos.","tools."))):continue
 path=getattr(module,"__file__",None)
 if path is None:continue
 payload=getattr(getattr(spec,"loader",None),"payload",None)
 if payload is None:payload=Path(path).read_bytes()
 rows[name]=hashlib.sha256(payload).hexdigest()
print(json.dumps(sorted(rows.items()),separators=(",",":")))
'''
    result=subprocess.run([sys.executable,"-I","-B","-c",program],cwd=installation.repository,
        env=installation.environment(),capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    rows=json.loads(result.stdout)
    assert all(dict(source).get(name)==digest for name,digest in rows)
    return rows


def _normative_blob(name):
    raw=(ROOT/"docs/architecture/interfaces/KRONOS-FAILED-FENCED-RECOVERY-V1.md").read_bytes()
    import re
    match=re.search(rb'<<<KRONOS_NORMATIVE_FILE name='+re.escape(name.encode())+rb' bytes=([0-9]+)[^\n]*\n',raw)
    if match is None:
        # Frozen rendering puts sha256 before bytes; fields remain source data.
        start=raw.index(b'<<<KRONOS_NORMATIVE_FILE name='+name.encode()+b' ')
        end=raw.index(b'\n',start);header=raw[start:end]
        count=int(re.search(rb'bytes=([0-9]+)',header)[1]);return raw[end+1:end+1+count]
    return raw[match.end():match.end()+int(match[1])]


def _static_preparation(installation,store):
    """Explicit synthetic offline reviews, real fixed publisher and root schemas."""
    from kronos.browser.failed_fenced_control import RecoveryBrowserBinding
    from kronos.common.failed_fenced_recovery import (RecoveryCodec,RecoveryBudget,PreparationAnchors,
        blob_ref,publish_reviewed_preparation,SCOPE_HASH,APPENDIX_HASH,ROOT_SCHEMA)
    from tools.runtime_source_gate import native_boot_id
    declaration=_native_declaration(installation)
    retained={}
    def retain(identity,raw):
        ref=blob_ref(identity,raw);prior=retained.get(ref["hash"])
        if prior is not None:assert prior[1]==raw
        else:retained[ref["hash"]]=(ref,raw)
        return ref
    source=retain("synthetic-source-inventory",_canonical(declaration["modules"]))
    native=retain("synthetic-native-declaration",_canonical(declaration["manifest"]))
    retain("native-compatibility-window",bytes.fromhex(declaration["native_window"]))
    configuration=retain("synthetic-launcher-configuration",_canonical(dict(browser_port=installation.port,open_browser=False)))
    executable=retain("synthetic-native-executable",installation.executable.read_bytes())
    from tools.macos.package_launcher import manifest,canonical
    package=retain("synthetic-package",canonical(manifest(installation.bundle)))
    retain("native-installed-CodeResources",(installation.bundle/"Contents/_CodeSignature/CodeResources").read_bytes())
    rollback_path=Path(installation.install_receipt["exchanged_original"])
    rollback_package=retain("synthetic-retained-rollback-package",canonical(manifest(rollback_path)))
    retain("native-retained-rollback-CodeResources",(rollback_path/"Contents/_CodeSignature/CodeResources").read_bytes())
    assert rollback_package["hash"]!=package["hash"]
    interface=retain("frozen-r3-interface",(ROOT/"docs/architecture/interfaces/KRONOS-FAILED-FENCED-RECOVERY-V1.md").read_bytes())
    scope_raw=_normative_blob("SUPPORTED-OWNER-AND-OBLIGATION-SCOPE.md")
    assert sha256(scope_raw).hexdigest()==SCOPE_HASH
    scope=retain("FAILED_FENCED_INITIAL_OWNER_SCOPE_V1",scope_raw)
    appendix_raw=_normative_blob("CLOSED-AUTHORITY-AND-EXTERNAL-PROOFS.md")
    assert sha256(appendix_raw).hexdigest()==APPENDIX_HASH
    appendix=retain("synthetic-frozen-appendix",appendix_raw)
    qualification=retain("synthetic-offline-qualification",b"SYNTHETIC isolated engineering fixture; not production artifact qualification")
    decisions={authority:retain("synthetic-decision-"+authority.lower(),("SYNTHETIC OFFLINE "+authority+" fixture review; no production authority").encode())
        for authority in ("CA","PCP","SPONSOR","EA-SWING","EA-INTRADAY")}
    clock_report=retain("synthetic-clock-report",b"SYNTHETIC clock-equivalence review boundary; real monotonic values and boot observed")
    platform=retain("synthetic-platform",b"Darwin CLOCK_MONOTONIC fixture qualification")
    boot=native_boot_id()
    clock_payload=dict(identity="synthetic-clock",approval="clock-pcp",platform=platform,boot_id=boot,
        c_clock="clock_gettime:CLOCK_MONOTONIC",python_clock="time.clock_gettime_ns:CLOCK_MONOTONIC",
        unit="NANOSECONDS",report=clock_report,equivalent=True,nondecreasing=True,sleep_behavior_equal=True)
    clock_root=retain(clock_payload["identity"],_canonical(dict(schema=ROOT_SCHEMA,kind="CLOCK_QUALIFICATION",payload=clock_payload)))
    clock=dict(type="CLOCK_MONOTONIC",boot_id=boot,qualification=dict(clock_root,authority="PCP",
        contract="KRONOS-FAILED-FENCED-ROOT-PROOF:1.0.0:CLOCK_QUALIFICATION"))
    sentinel=retain("synthetic-guard-sentinel",(store.root/"guard-scope.json").read_bytes())
    backend=retain("synthetic-backend-entry",(installation.repository/"tools/kronos_browser.py").read_bytes())
    provision=retain("synthetic-provisioning",_canonical(dict(schema="KRONOS-FAILED-FENCED-GUARD-PROVISIONING/1.0.0",
        identity="synthetic-provisioning",service="synthetic-service",installation="synthetic-installation",
        launcher=executable,backend=backend,source=source,sentinel=sentinel,lock_scope="synthetic-service",
        before_first_capable_start=True,fsync_verified=True,readback_verified=True)))
    guard_payload=dict(identity="synthetic-guard-applicability",approval="guard-ca",service="synthetic-service",
        launcher=executable,backend=backend,source=source,classification="MANDATORY",sentinel=sentinel,provisioning=provision)
    guard_root=retain(guard_payload["identity"],_canonical(dict(schema=ROOT_SCHEMA,kind="GUARD_APPLICABILITY",payload=guard_payload)))
    plan=dict(schema="KRONOS-FAILED-FENCED-BOOTSTRAP-PLAN/1.0.0",identity="synthetic-complete-pin-plan",source_inventory=source,
        qualification=qualification,modules=[dict(name=name,digest=digest) for name,digest in _qualified_bootstrap_declaration(installation,declaration["modules"])])
    bootstrap=retain(plan["identity"],_canonical(plan))
    restoration_payload=dict(identity="synthetic-restoration-plan",approval="artifact-ca",service="synthetic-service",
        revision=installation.revision,source_inventory=source,configuration=configuration,
        owners=[dict(owner=owner,contract="synthetic-restoration-"+owner,validator=qualification,applicability=qualification)
            for owner in ("LOCAL_ANALYSIS","MCX","NATIVE","RESEARCH","SWING_ANALYSIS","TRADE_WINDOW","WO08","WO11","WO17")])
    restoration=retain(restoration_payload["identity"],_canonical(dict(schema=ROOT_SCHEMA,kind="RESTORATION_PLAN",payload=restoration_payload)))
    rows=[]
    def row(identity,authority,purpose,binding,artifact=None):
        if purpose=="ARTIFACT" and artifact is None:
            # Distinct synthetic review decisions bind the installed and
            # rollback artifacts independently. A shared qualification report
            # is not a unique decision for either exact artifact row.
            artifact=retain("synthetic-"+identity+"-decision",_canonical(dict(
                synthetic=True,production_authority=False,identity=identity,
                authority=authority,purpose=purpose,bindings=binding)))
        rows.append(dict(identity=identity,authority=authority,purpose=purpose,bindings=binding,
            artifact=artifact or qualification,attribution=decisions[authority]))
    for authority in ("CA","PCP"):
        row("clock-"+authority.lower(),authority,"CLOCK",dict(kind="CLOCK",root=clock_root,report=clock_report,boot_id=boot),clock_root)
        row("guard-"+authority.lower(),authority,"GUARD",dict(kind="GUARD",service="synthetic-service",installation="synthetic-installation",
            classification="MANDATORY",launcher=executable,backend=backend,source_inventory=source,sentinel=sentinel,provisioning=provision),guard_root)
        row("tail-"+authority.lower(),authority,"TAIL",dict(kind="TAIL",source_inventory=source,entry=RecoveryBrowserBinding.TAIL_ENTRY,callgraph=qualification,
            qualification=qualification,cleanup_actions=[],allowed=["CONTROL_RESPONSE","CLOSE_DESCRIPTORS","PROCESS_EXIT"]))
    row("artifact-ca","CA","ARTIFACT",dict(kind="ARTIFACT",revision=installation.revision,source_inventory=source,
        capability_manifest=native,executable=executable,package=package,configuration=configuration,bootstrap_plan=bootstrap,qualification=qualification))
    row("rollback-artifact-ca","CA","ARTIFACT",dict(kind="ARTIFACT",revision=installation.revision,source_inventory=source,
        capability_manifest=native,executable=executable,package=rollback_package,configuration=configuration,bootstrap_plan=bootstrap,qualification=qualification))
    row("architecture-ca","CA","ARCHITECTURE",dict(kind="ARCHITECTURE",interface=interface,scope=scope,appendix=appendix,contract=interface,adr=qualification))
    for authority in ("CA","PCP","EA-SWING","EA-INTRADAY"):
        row("owner-scope-"+authority.lower(),authority,"OWNER_SCOPE",dict(kind="OWNER_SCOPE",interface=interface,scope=scope,owner=authority,
            implementation=source,qualification=qualification),decisions[authority])
    catalogue=dict(schema="KRONOS-RECOVERY-APPROVAL-CATALOGUE/1.0.0",identity="synthetic-static-catalogue",service="synthetic-service",
        package_manifest=package,interface=interface,scope=scope,appendix=appendix,rows=sorted(rows,key=lambda item:item["identity"]))
    catalogue_raw=_canonical(catalogue);catalogue_ref=blob_ref(catalogue["identity"],catalogue_raw)
    import ctypes
    from tools.failed_fenced_launcher import _ProcBSDInfo
    info=_ProcBSDInfo();library=ctypes.CDLL("/usr/lib/libproc.dylib",use_errno=True)
    assert library.proc_pidinfo(os.getpid(),3,0,ctypes.byref(info),ctypes.sizeof(info))==ctypes.sizeof(info)
    assert info.pid==os.getpid()
    static=dict(pid=str(os.getpid()),kernel_birth=dict(seconds=str(info.start_seconds),microseconds=str(info.start_microseconds)),
        runtime=sha256(Path(sys.executable).resolve().read_bytes()).hexdigest())
    lineage=dict(predecessor=static,generation="0"*64)
    private=("KRONOS_BROWSER_BACKEND_CONTROL_V1\n"+str(os.getpid())+"\n"+"b"*64+"\n").encode()
    # Static installation roots grant no predecessor custody. No P exists yet.
    record=dict(schema="KRONOS-FAILED-FENCED-CONTROL-PREPARATION/1.0.0",identity="synthetic-static-preparation",mode="ORIGINAL",
        service="synthetic-service",installation="synthetic-installation",controller=static,lineage=lineage,attempt="synthetic-static",
        control_hash=sha256(private).hexdigest(),catalogue=catalogue_ref,original_preparation=None,
        launcher_source=source,launcher_package=package,clock=clock,prepared_ns=str(time.clock_gettime_ns(time.CLOCK_MONOTONIC)))
    record_raw=_canonical(record);record_ref=blob_ref(record["identity"],record_raw)
    selector={key:record[key] for key in ("mode","service","installation","lineage","attempt")}
    pin=dict(schema="KRONOS-FAILED-FENCED-PREPARATION-PIN/1.0.0",**selector,preparation=record_ref,catalogue=catalogue_ref)
    pin_raw=_canonical(pin);pin_ref=blob_ref("synthetic-static-pin",pin_raw)
    approval=dict(schema="KRONOS-FAILED-FENCED-PREPARATION-APPROVAL/1.0.0",pin=pin_ref,preparation=record_ref,
        attributions=[dict(authority=authority,decision=decisions[authority]) for authority in ("CA","PCP")])
    approval_raw=_canonical(approval)
    anchors=PreparationAnchors(pin_ref,blob_ref("synthetic-static-approval",approval_raw),catalogue_ref,tuple(decisions.values()))
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    prepared=publish_reviewed_preparation(store,pin_raw=pin_raw,approval_raw=approval_raw,preparation_raw=record_raw,
        catalogue_raw=catalogue_raw,anchors=anchors,retained=tuple(retained.values()),budget=RecoveryBudget(clock,now,now+15_000_000_000))
    return dict(prepared=prepared,catalogue=catalogue,clock=clock,source=source,package=package,restoration=restoration,
        target_declaration=declaration,decisions=decisions,retained=retained,scope=scope,bootstrap=bootstrap,rollback_package=rollback_package,synthetic_static_control=private)



def _proofs(store,kind,process=None):
    result=[]
    for path in sorted((store.root/"blobs").glob("*.blob")):
        try:value=json.loads(path.read_bytes())
        except (ValueError,UnicodeError):continue
        if (type(value) is dict and value.get("kind")==kind
                and (process is None or value["payload"].get("process")==process)):
            raw=path.read_bytes()
            assert sha256(raw).hexdigest()==path.stem
            result.append((value,raw))
    return result


def _publish_operation(installation,store,state,controller,*,mode,lineage,attempt,binding,
                       original=None):
    """Synthetic offline decisions, actual immutable source-owned publisher.

    The actual C identity is observed before this exact permission is frozen.
    No reader/codec or native operational predicate is replaced by this helper.
    """
    from kronos.common.failed_fenced_recovery import (PreparationAnchors,RecoveryBudget,
        blob_ref,publish_reviewed_preparation)
    from copy import deepcopy
    retained=dict(state["retained"])
    def retain(identity,raw):
        ref=blob_ref(identity,raw)
        retained[ref["hash"]]=(ref,raw)
        return ref
    purpose="ORIGINAL_OPERATION" if mode=="ORIGINAL" else "RECOVERY_OPERATION"
    rows=deepcopy(state["catalogue"]["rows"])
    assert not any(row["purpose"]==purpose for row in rows)
    rows.append(dict(identity="synthetic-"+attempt+"-sponsor",authority="SPONSOR",purpose=purpose,
        artifact=state["decisions"]["SPONSOR"],attribution=state["decisions"]["SPONSOR"],bindings=binding))
    catalogue=deepcopy(state["catalogue"])
    catalogue.update(identity="synthetic-"+attempt+"-catalogue",rows=sorted(rows,key=lambda row:row["identity"]))
    catalogue_raw=_canonical(catalogue);catalogue_ref=blob_ref(catalogue["identity"],catalogue_raw)
    control=(installation.estate/"browser-backend-v1.control").read_bytes()
    assert str(lineage["predecessor"]["pid"]).encode()==control.splitlines()[1]
    record=dict(schema="KRONOS-FAILED-FENCED-CONTROL-PREPARATION/1.0.0",
        identity="synthetic-"+attempt+"-preparation",mode=mode,service="synthetic-service",
        installation="synthetic-installation",controller=controller,lineage=lineage,attempt=attempt,
        control_hash=sha256(control).hexdigest(),catalogue=catalogue_ref,
        original_preparation=None if original is None else original.pin["preparation"],
        launcher_source=state["source"],launcher_package=state["package"],clock=state["clock"],
        prepared_ns=str(time.clock_gettime_ns(time.CLOCK_MONOTONIC)))
    record_raw=_canonical(record);record_ref=blob_ref(record["identity"],record_raw)
    selector={key:record[key] for key in ("mode","service","installation","lineage","attempt")}
    pin=dict(schema="KRONOS-FAILED-FENCED-PREPARATION-PIN/1.0.0",**selector,
        preparation=record_ref,catalogue=catalogue_ref)
    pin_raw=_canonical(pin);pin_ref=blob_ref("synthetic-"+attempt+"-pin",pin_raw)
    approval=dict(schema="KRONOS-FAILED-FENCED-PREPARATION-APPROVAL/1.0.0",pin=pin_ref,
        preparation=record_ref,attributions=[dict(authority=authority,decision=state["decisions"][authority])
            for authority in (("CA","PCP") if mode=="ORIGINAL" else ("CA","PCP","SPONSOR"))])
    approval_raw=_canonical(approval)
    anchors=PreparationAnchors(pin_ref,blob_ref("synthetic-"+attempt+"-approval",approval_raw),
        catalogue_ref,tuple(state["decisions"].values()))
    now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    return publish_reviewed_preparation(store,pin_raw=pin_raw,approval_raw=approval_raw,
        preparation_raw=record_raw,catalogue_raw=catalogue_raw,anchors=anchors,
        retained=tuple(retained.values()),budget=RecoveryBudget(state["clock"],now,now+15_000_000_000))

def test_actual_c_main_rejects_unapproved_preparation_without_helper_or_child(native_installation):
    """Actual main/loaded executable/kernel identity; no synthetic protocol MAC."""
    installation=native_installation;store=_private_estate(installation)
    (store.root/"service.lock").write_bytes(b"");(store.root/"service.lock").chmod(0o600)
    before={str(p.relative_to(store.root)):p.read_bytes() for p in store.root.rglob("*") if p.is_file()}
    process=installation.start_main("FAILED_FENCED_PREPARATION")
    identity=_line(process)
    assert identity["pid"]==str(process.pid)
    assert identity["runtime"]==sha256(installation.executable.read_bytes()).hexdigest()
    # A filesystem event wakes the exact main; it grants nothing and a partial
    # fixed preparation must deny rather than create a helper or a child.
    (store.root/"preparation"/("0"*64+".pin")).write_bytes(b"{}")
    (store.root/"preparation"/("0"*64+".pin")).chmod(0o600)
    stdout,stderr=process.communicate(timeout=20)
    assert process.returncode==1,(stdout,stderr)
    assert list((store.root/"slots").iterdir())==list((store.root/"guards").iterdir())==[]
    assert list((store.root/"records").iterdir())==list((store.root/"blobs").iterdir())==[]
    assert {key:(store.root/key).read_bytes() for key in before}==before
    installation.trace("actual-main-unapproved-denial",dict(process=identity,exit=process.returncode,
        stdout=stdout.decode(),stderr=stderr.decode(),child_records=0,helper_proofs=0))


def test_actual_native_static_preparation_has_only_independently_bound_installation_roots(native_installation):
    from kronos.common.failed_fenced_recovery import RecoveryCodec,EvidenceRegistry
    installation=native_installation;store=_private_estate(installation)
    state=_static_preparation(installation,store)
    prepared=state["prepared"]
    codec=RecoveryCodec(state["synthetic_static_control"],state["clock"])
    registry=EvidenceRegistry(codec,store,prepared)
    assert registry.verify(state["clock"]["qualification"],"CLOCK_QUALIFICATION")["payload"]["equivalent"]
    raw=store.read_blob(prepared.rows["guard-ca"]["artifact"])
    guard=registry.verify(registry.proof_evidence(raw),"GUARD_APPLICABILITY")["payload"]
    assert guard["classification"]=="MANDATORY"
    assert not any(row["purpose"] in {"ORIGINAL_OPERATION","RECOVERY_OPERATION"} for row in prepared.rows.values())
    assert list((store.root/"slots").iterdir())==list((store.root/"guards").iterdir())==[]
    assert list((store.root/"records").iterdir())==[]
    installation.trace("static-only-installation",dict(synthetic=True,source=state["source"],
        package=state["package"],preparation=prepared.pin["preparation"],operations=0))


def test_actual_main_cold_start_uses_prepared_pinned_browser_factory(native_installation):
    """Cold P entry only; cleanup here is fixture teardown, not an R3 closure."""
    import signal
    installation=native_installation;store=_private_estate(installation)
    state=_static_preparation(installation,store)
    _seed_synthetic_swing_original(installation)
    process=installation.start_main(None);backend_pid=None
    control=installation.estate/"browser-backend-v1.control"
    try:
        stop=time.monotonic()+45
        while time.monotonic()<stop:
            if control.exists():
                backend_pid=int(control.read_bytes().splitlines()[1])
            if backend_pid is not None:
                facts=[]
                for path in (store.root/"blobs").glob("*.blob"):
                    try:value=json.loads(path.read_bytes())
                    except (ValueError,UnicodeError):continue
                    if type(value) is dict and value.get("kind")=="ENDPOINT_CONFIGURATION":facts.append(value)
                if facts:break
            if process.poll() is not None:break
            time.sleep(.01)
        log=installation.home/"actual-child-stderr.log"
        diagnostics=log.read_text() if log.exists() else "NO_CHILD_TRACE"
        assert backend_pid is not None,diagnostics
        assert len(facts)==1,diagnostics
        endpoint=facts[0]
        assert endpoint["payload"]["port"]==str(installation.port)
        assert endpoint["payload"]["process"]["pid"]==str(backend_pid)
        assert endpoint["role"]=="PREDECESSOR"
        assert process.wait(timeout=125)==0,diagnostics
        installation.trace("actual-cold-p-factory",dict(controller_pid=process.pid,predecessor_pid=backend_pid,
            endpoint=endpoint,source_inventory=state["source"],control_sha256=sha256(control.read_bytes()).hexdigest(),
            synthetic_signature=True,actual_operational_recovery=False))
    finally:
        # Never leave a disposable server running after an isolated assertion.
        # A test using this cleanup cannot claim governed executor termination.
        if process.poll() is None:process.terminate()
        outer_stdout,outer_stderr=process.communicate(timeout=10)
        installation.trace("actual-cold-controller-result",dict(controller_pid=process.pid,exit=process.returncode,
            stdout=outer_stdout.decode(),stderr=outer_stderr.decode(),helper_child_trace=(
                (installation.home/"actual-child-stderr.log").read_text() if (installation.home/"actual-child-stderr.log").exists() else None)))
        if outer_stdout or outer_stderr:
            print("ACTUAL_C_MAIN_STDOUT",outer_stdout.decode())
            print("ACTUAL_C_MAIN_STDERR",outer_stderr.decode())
        if backend_pid is not None:
            try:os.kill(backend_pid,signal.SIGTERM)
            except ProcessLookupError:pass

def _wait_native_factory(installation,store,controller,*,held=False):
    control=installation.estate/"browser-backend-v1.control"
    until=time.monotonic()+45
    while time.monotonic()<until:
        endpoints=_proofs(store,"ENDPOINT_CONFIGURATION")
        if control.exists() and len(endpoints)==1:
            pid=int(control.read_bytes().splitlines()[1])
            if not held or (installation.home/"fixture-native-wo11-return-held").exists():
                assert endpoints[0][0]["payload"]["process"]["pid"]==str(pid)
                assert controller.wait(timeout=125)==0
                return endpoints[0][0]["payload"]["process"]
        if controller.poll() is not None and controller.returncode!=0:break
        time.sleep(.005)
    diagnostics=installation.home/"actual-child-stderr.log"
    from http.client import HTTPConnection
    endpoint_snapshot=None
    if endpoints:
        connection=HTTPConnection("127.0.0.1",installation.port,timeout=1)
        try:
            connection.request("GET","/runtime/status",headers={"Connection":"close"})
            response=connection.getresponse();raw=response.read(1024*1024+1)
            endpoint_snapshot=dict(status=response.status,bytes=len(raw),body=raw.decode(errors="replace"))
        except (OSError,TimeoutError) as error:endpoint_snapshot=dict(error=type(error).__name__,reason=str(error))
        finally:connection.close()
    owner_files={}
    lifecycle=installation.home/"Library/Application Support/KRONOS/evidence/intraday-v1/prospective-v2-wo11-lifecycle"
    for file in lifecycle.rglob("*.json"):
        if len(owner_files)>=20:break
        owner_files[str(file.relative_to(lifecycle))]=file.read_text()
    installation.trace("actual-cold-pending-stage",dict(controller_pid=controller.pid,controller_exit=controller.poll(),
        control_exists=control.exists(),control_pid=None if not control.exists() else control.read_bytes().splitlines()[1].decode(),
        endpoint_count=len(endpoints),held_requested=held,held_marker=(installation.home/"fixture-native-wo11-return-held").exists(),
        admission_marker=(installation.home/"fixture-native-wo11-admission").read_text() if (installation.home/"fixture-native-wo11-admission").exists() else None,
        actual_read_only_fixture_runtime=endpoint_snapshot,native_wo11_files=owner_files))
    raise AssertionError(diagnostics.read_text() if diagnostics.exists() else "NO_CHILD_TRACE")


def _fixture_put(state,identity,raw):
    from kronos.common.failed_fenced_recovery import blob_ref
    ref=blob_ref(identity,raw);state["retained"][ref["hash"]]=(ref,raw);return ref


def _native_records(store,codec,kind):
    result=[]
    fixed={"CHILD_INTENT":"child-intent","CONSUMPTION":"consumption"}
    if kind == "ACK":
        assert not list((store.root/"records").glob("ACK-*.json"))
        for observation,_ in _native_records(store,codec,"OBSERVATION"):
            raw=bytes.fromhex(observation["payload"]["ack_bytes"])
            value=codec.decode(raw,"ACK")
            assert {"kind":"ACK","hash":sha256(raw).hexdigest()}==observation["payload"]["ack"]
            result.append((value,raw))
        return result
    paths=sorted((store.root/"slots").glob("*/"+fixed[kind])) if kind in fixed else sorted((store.root/"records").glob(kind+"-*.json"))
    for path in paths:
        raw=path.read_bytes();value=codec.decode(raw,kind)
        if kind not in fixed:assert path.name==kind+"-"+sha256(raw).hexdigest()+".json"
        else:assert path.parent.name==value["payload"]["slot"]
        result.append((value,raw))
    return result


def _trace_native_protocol(installation,store,codec,phase):
    """Retain bounded synthetic protocol metadata before disposable teardown.

    Only closed record/proof envelopes are selected. Native data blobs, raw
    controls/custody and tokens are never copied. The two embedded protocol
    byte fields are reduced to their digest/size; their complete original
    envelope digest remains available without exporting those bytes.
    """
    from kronos.common.failed_fenced_recovery import EXTERNAL_SCHEMA,ROOT_SCHEMA,MAX_RECORD
    from kronos.common import failed_fenced_schema as closed
    # Successor composition creates its own future-operation custody. Decode
    # each generation under its actual retained control, never the wrong key.
    from kronos.common.failed_fenced_recovery import RecoveryCodec
    codecs={codec.key_id:codec}
    control=installation.estate/"browser-backend-v1.control"
    if control.exists():
        current=RecoveryCodec(control.read_bytes(),codec.clock)
        codecs[current.key_id]=current
    rows=[];observed_bytes=0
    fixed={"guard":"GUARD","claim":"CLAIM","child-intent":"CHILD_INTENT",
        "child-identity":"CHILD_IDENTITY","consumption":"CONSUMPTION"}
    for namespace,pattern in (("records","*.json"),("blobs","*.blob"),("guards","*/guard"),("slots","*/*")):
        paths=sorted((store.root/namespace).glob(pattern))
        if namespace=="slots":
            paths=[path for path in paths if path.name in fixed]
            paths+=sorted((store.root/namespace).glob("*/bootstrap/*.bootstrap.json"))
        assert len(paths)<=4096,"Synthetic protocol diagnostic file bound"
        for path in paths:
            size=path.stat().st_size
            if not 0<size<=MAX_RECORD:continue
            observed_bytes+=size
            assert observed_bytes<=64*1024*1024,"Synthetic protocol diagnostic byte bound"
            raw=path.read_bytes()
            if not raw.startswith(b"{"):continue
            try:value=json.loads(raw)
            except (ValueError,UnicodeError):continue
            if type(value) is not dict:continue
            kind=value.get("kind")
            selected=codec if value.get("schema")==ROOT_SCHEMA else codecs.get(value.get("key_id"))
            if namespace=="records" or path.name in fixed:
                if kind not in closed.RECORD_SCHEMAS:continue
                assert selected is not None
                value=selected.decode(raw,kind)
                if namespace=="records":assert path.name==kind+"-"+sha256(raw).hexdigest()+".json"
                else:assert fixed[path.name]==kind and len(path.parent.name)==64
            else:
                if value.get("schema") not in {EXTERNAL_SCHEMA,ROOT_SCHEMA} or kind not in closed.PROOF_SCHEMAS:continue
                assert selected is not None
                value=selected.decode_proof(raw,kind)
                assert path.name.split(".")[0]==sha256(raw).hexdigest()
            omitted={}
            for field in ("authority_bytes","ack_bytes"):
                if field in value["payload"]:
                    embedded=bytes.fromhex(value["payload"].pop(field))
                    omitted[field]=dict(bytes=len(embedded),sha256=sha256(embedded).hexdigest())
            rows.append(dict(namespace=namespace,file=str(path.relative_to(store.root/namespace)),sha256=sha256(raw).hexdigest(),
                bytes=len(raw),authenticated_original=(selected is codec),authenticated_generation=True,envelope=value,
                omitted_embedded_protocol_bytes=omitted,
                envelope_bytes_complete=not omitted))
    return installation.trace("actual-native-protocol-"+phase,dict(
        synthetic_installation=True,production_authority=False,
        observed_ns=str(time.clock_gettime_ns(time.CLOCK_MONOTONIC)),
        excluded="raw control, raw custody, tokens, opaque native blobs, embedded protocol byte fields",
        envelopes=rows))


def _actual_journal_heads(store,codec):
    from kronos.common.failed_fenced_recovery import blob_ref
    rows=[]
    for kind in ("OBLIGATION","CLEANUP"):
        records=_native_records(store,codec,kind)
        prior={row[0]["payload"]["previous"]["hash"] for row in records if row[0]["payload"]["previous"] is not None}
        for value,raw in records:
            if sha256(raw).hexdigest() not in prior:
                rows.append(blob_ref("fixture-observed-"+kind.lower()+"-"+sha256(raw).hexdigest(),raw))
    return sorted(rows,key=lambda row:row["identity"])


def test_actual_c_original_failed_fenced_recovery_has_one_consumed_child_and_ready(native_installation):
    """Synthetic qualification decisions, actual complete native process path."""
    import signal
    from kronos.common.failed_fenced_recovery import RecoveryCodec,blob_ref,slot_key
    installation=native_installation;store=_private_estate(installation)
    state=_static_preparation(installation,store)
    _seed_synthetic_swing_original(installation)
    original_track=_seed_synthetic_wo11_original(installation)
    (installation.home/"fixture-native-wo11-enable").write_text("SYNTHETIC_ACTUAL_CALLER_RETURN_BARRIER")
    evidence=installation.home/"Library/Application Support/KRONOS/evidence"
    originals={str(path.relative_to(evidence)):path.read_bytes() for path in evidence.rglob("*.json")
        if "records" in path.parts or "/runs/" in str(path)}
    controllers=[];owned_pids=set()
    try:
        cold=installation.start_main(None);controllers.append(cold)
        predecessor=_wait_native_factory(installation,store,cold,held=True);owned_pids.add(int(predecessor["pid"]))
        control_path=installation.estate/"browser-backend-v1.control"
        private=control_path.read_bytes();codec=RecoveryCodec(private,state["clock"])
        source_value,source_raw=_proofs(store,"SOURCE",predecessor)[0]
        capability_value,capability_raw=_proofs(store,"CAPABILITY",predecessor)[0]
        source_ref=blob_ref(source_value["payload"]["identity"],source_raw)
        capability_ref=blob_ref(capability_value["payload"]["identity"],capability_raw)
        assert codec.decode_proof(source_raw,"SOURCE")["payload"]["process"]==predecessor
        original_c=installation.start_main("FAILED_FENCED_PREPARATION");controllers.append(original_c)
        original_controller=_line(original_c);prior_facts=_line(original_c)
        assert original_controller["pid"]==str(original_c.pid) and prior_facts=={"retained_facts":None}
        generation=sha256(b"SYNTHETIC_ACTUAL_ORIGINAL_GENERATION").hexdigest()
        lineage=dict(predecessor=predecessor,generation=generation)
        now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        permission=_fixture_put(state,"synthetic-exact-ordinary-permission",
            _canonical(dict(synthetic=True,purpose="ONE_ACTUAL_ORIGINAL_ONLY",controller=original_controller,
                predecessor=predecessor,generation=generation,external_provider_calls=0,
                production_provider_calls=0,model_calls=0)))
        original_binding=dict(kind="ORIGINAL_OPERATION",service="synthetic-service",controller=original_controller,
            predecessor=predecessor,generation=generation,attempt="synthetic-original-operation",operation_kind="ORDINARY",
            control=sha256(private).hexdigest(),source=source_ref,package=state["package"],permission=permission,
            clock=state["clock"],valid_from_ns=str(now),valid_until_ns=str(now+60_000_000_000))
        original_preparation=_publish_operation(installation,store,state,original_controller,mode="ORIGINAL",
            lineage=lineage,attempt=original_binding["attempt"],binding=original_binding)
        until=time.monotonic()+14
        terminal_rows=[]
        while time.monotonic()<until:
            terminal_rows=_native_records(store,codec,"TERMINAL")
            if terminal_rows:break
            if original_c.poll() is not None:break
            time.sleep(.001)
        if not terminal_rows:
            from http.client import HTTPConnection
            connection=HTTPConnection("127.0.0.1",installation.port,timeout=1)
            try:
                connection.request("GET","/runtime/status",headers={"Connection":"close"})
                response=connection.getresponse();raw=response.read(1024*1024+1)
                observation=dict(status=response.status,bytes=len(raw),body=raw.decode(errors="replace"))
            except (OSError,TimeoutError) as error:observation=dict(error=type(error).__name__,reason=str(error))
            finally:connection.close()
            records=[]
            for path in sorted((store.root/"records").glob("*.json")):
                raw=path.read_bytes();value=json.loads(raw)
                records.append(dict(file=path.name,sha256=sha256(raw).hexdigest(),kind=value.get("kind"),payload=value.get("payload")))
            installation.trace("actual-original-preterminal-denial",dict(original_controller=original_controller,
                process_exit=original_c.poll(),actual_fixture_runtime=observation,retained_native_records=records))
        assert len(terminal_rows)==1,"Real original did not publish its timed-out terminal"
        terminal,terminal_raw=terminal_rows[0]
        assert terminal["payload"]["lineage"]==lineage and terminal["payload"]["first_failure"]=="TIMEOUT"
        assert int(terminal["payload"]["failed_ns"])>=int(terminal["payload"]["original_deadline_ns"])
        original_rows=_native_records(store,codec,"ORIGINAL")
        assert len(original_rows)==1
        original_limits=original_rows[0][0]["payload"]["original_limits"]
        assert int(original_limits["stop_deadline_ns"])-int(original_limits["origin_ns"])==15_000_000_000
        assert int(terminal["payload"]["original_deadline_ns"])-int(original_limits["origin_ns"])==10_000_000_000
        installation.trace("actual-original-terminal",dict(terminal=terminal,
            terminal_sha256=sha256(terminal_raw).hexdigest(),original_limits=original_limits,
            observed_ns=str(time.clock_gettime_ns(time.CLOCK_MONOTONIC)),predecessor=predecessor,
            original_controller=original_controller,actual_original_return_still_held=True))
        # Release only the original syscall return; actual fsync/callback,
        # reference retention and enclosing-caller/observer completion follow.
        (installation.home/"fixture-native-wo11-release").write_text("RELEASE_ACTUAL_ORIGINAL_RETURN")
        original_exit=original_c.wait(timeout=5)
        original_records=[]
        for path in sorted((store.root/"records").glob("*.json")):
            raw=path.read_bytes();value=json.loads(raw)
            original_records.append(dict(file=path.name,sha256=sha256(raw).hexdigest(),kind=value.get("kind"),payload=value.get("payload")))
        installation.trace("actual-original-controller-return",dict(controller=original_controller,
            exit=original_exit,observed_ns=str(time.clock_gettime_ns(time.CLOCK_MONOTONIC)),
            retained_native_records=original_records))
        assert original_exit==0
        executor_rows=_native_records(store,codec,"EXECUTOR")
        # Native C completion precedes the separately counted original P
        # observer's final publication. Observe that asynchronous fact only
        # within the same original absolute stop; elapsed time is not proof.
        while not any(value["payload"]["state"]=="TERMINATED" for value,_ in executor_rows):
            if time.clock_gettime_ns(time.CLOCK_MONOTONIC)>=int(original_limits["stop_deadline_ns"]):break
            time.sleep(.001)
            executor_rows=_native_records(store,codec,"EXECUTOR")
        installation.trace("actual-original-executor-observation",dict(
            observed_ns=str(time.clock_gettime_ns(time.CLOCK_MONOTONIC)),original_limits=original_limits,
            executors=[value for value,_ in executor_rows]))
        assert any(value["payload"]["state"]=="TERMINATED" for value,_ in executor_rows)
        _trace_native_protocol(installation,store,codec,"original-return")
        original_authorities=_proofs(store,"ORIGINAL_AUTHORITY")
        assert len(original_authorities)==1
        original_authority=codec.decode_proof(original_authorities[0][1],"ORIGINAL_AUTHORITY")["payload"]
        original_controllers=_proofs(store,"ORIGINAL_CONTROLLER")
        assert len(original_controllers)==1
        original_snapshot={str(path.relative_to(store.root)):path.read_bytes() for path in store.root.rglob("*") if path.is_file()}
        recovery_c=installation.start_main("FAILED_FENCED_PREPARATION");controllers.append(recovery_c)
        recovery_controller=_line(recovery_c);staged=_line(recovery_c,10)["retained_facts"]
        assert recovery_controller["pid"]==str(recovery_c.pid) and set(staged)=={
            "target","installed_package","rollback_package","compatibility"}
        for kind,key in (("TARGET_ARTIFACT","target"),("PACKAGE","installed_package"),("PACKAGE","rollback_package"),("COMPATIBILITY","compatibility")):
            value=codec.decode_proof(store.read_blob(staged[key]),kind)
            assert value["issuer"]==recovery_controller
        terminal_ref=blob_ref("actual-original-terminal",terminal_raw)
        diagnosis=_fixture_put(state,"synthetic-exact-recovery-diagnosis",_canonical(dict(synthetic=True,
            terminal=terminal_ref,reason="ACTUAL_COUNTED_WO11_RETURN_DRAIN_TIMEOUT",original_preserved=True)))
        now=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        binding=dict(kind="RECOVERY_OPERATION",service="synthetic-service",controller=recovery_controller,
            lineage=lineage,slot=slot_key(lineage),transaction="synthetic-one-recovery",original_preparation=original_preparation.pin["preparation"],
            original_reservation=original_authority["reservation"],terminal=terminal_ref,
            journal_heads=_actual_journal_heads(store,codec),predecessor_source=source_ref,predecessor_capability=capability_ref,
            target=staged["target"],installed_package=staged["installed_package"],rollback_package=staged["rollback_package"],
            compatibility=staged["compatibility"],diagnosis=diagnosis,interface=state["catalogue"]["interface"],scope=state["scope"],
            clock=state["clock"],valid_from_ns=str(now),valid_until_ns=str(now+60_000_000_000))
        _publish_operation(installation,store,state,recovery_controller,mode="RECOVERY",lineage=lineage,
            attempt=binding["transaction"],binding=binding,original=original_preparation)
        recovery_exit=recovery_c.wait(timeout=125)
        recovery_records=[]
        for path in sorted((store.root/"records").glob("*.json")):
            raw=path.read_bytes();value=json.loads(raw)
            recovery_records.append(dict(file=path.name,sha256=sha256(raw).hexdigest(),kind=value.get("kind"),payload=value.get("payload")))
        installation.trace("actual-recovery-controller-return",dict(controller=recovery_controller,
            exit=recovery_exit,observed_ns=str(time.clock_gettime_ns(time.CLOCK_MONOTONIC)),
            retained_native_records=recovery_records))
        _trace_native_protocol(installation,store,codec,"recovery-return")
        assert recovery_exit==0
        ready_rows=_native_records(store,codec,"READY_RECEIPT")
        assert len(ready_rows)==1
        ready,ready_raw=ready_rows[0]
        child=ready["payload"]["runtime"];owned_pids.add(int(child["pid"]))
        assert child!=predecessor and ready["role"]=="LAUNCHER"
        started=_native_records(store,codec,"CHILD_STARTED")
        assert len(started)==1
        assert int(ready["payload"]["ready_ns"])<=int(started[0][0]["payload"]["ready_deadline_ns"])
        assert int(started[0][0]["payload"]["ready_deadline_ns"])-int(started[0][0]["payload"]["fork_enter_ns"])==120_000_000_000
        assert int(ready["payload"]["ready_ns"])>=int(started[0][0]["payload"]["fork_enter_ns"])
        exits=_native_records(store,codec,"EXIT_PROOF")
        assert len(exits)==1
        exit_payload=exits[0][0]["payload"]
        assert exit_payload["predecessor"]==predecessor
        for field,kind,result in (("process_evidence","PROCESS_EXIT","EXITED"),("listener_evidence","LISTENER_ABSENT","ABSENT")):
            observation=codec.decode_proof(store.read_blob(exit_payload[field]),"PLATFORM_OBSERVATION")
            assert observation["payload"]["subject"]==predecessor
            assert observation["payload"]["kind"]==kind and observation["payload"]["result"]==result
            assert observation["payload"]["observer"]==recovery_controller
        assert int(exit_payload["limits"]["stop_deadline_ns"])-int(exit_payload["limits"]["origin_ns"])==15_000_000_000
        assert not _native_records(store,codec,"FAILURE")
        assert len(_native_records(store,codec,"CHILD_INTENT"))==len(_native_records(store,codec,"CHILD_STARTED"))==1
        assert len(_native_records(store,codec,"CONSUMPTION"))==1
        assert len(_native_records(store,codec,"SEAL"))==len(_native_records(store,codec,"ACK"))==1
        assert all((evidence/relative).read_bytes()==raw for relative,raw in originals.items())
        assert all((store.root/relative).read_bytes()==raw for relative,raw in original_snapshot.items())
        from tools.macos.package_launcher import identity
        assert identity(installation.bundle)==state["package"]["hash"]
        assert identity(Path(installation.install_receipt["exchanged_original"]))==state["rollback_package"]["hash"]
        assert original_track.identity in " ".join(str(path) for path in evidence.rglob("*.json"))
        installation.trace("actual-native-full-roundtrip",dict(synthetic_offline_decisions=True,production_authority=False,
            original_controller=original_controller,predecessor=predecessor,recovery_controller=recovery_controller,
            child=child,terminal=terminal_ref,ready=blob_ref("actual-ready-receipt",ready_raw),
            original_evidence_preserved=len(originals),original_recovery_records_preserved=len(original_snapshot),
            child_intents=1,child_starts=1,consumptions=1,ready_receipts=1,
            external_provider_calls=0,production_provider_calls=0,model_calls=0,
            synthetic_adapter_invocations="Recorded separately in synthetic-wo11-original.json"))
    finally:
        # Disposal is outside the recorded engineering proof; no teardown below
        # can supply a required original/recovery/child lifecycle receipt.
        for process in controllers:
            if process.poll() is None:process.terminate()
            out,err=process.communicate(timeout=10)
            if out or err:
                print("ACTUAL_NATIVE_CONTROLLER",process.pid,"EXIT",process.returncode,
                    "STDOUT",out.decode(),"STDERR",err.decode())
        control=installation.estate/"browser-backend-v1.control"
        if control.exists():owned_pids.add(int(control.read_bytes().splitlines()[1]))
        for pid in owned_pids:
            try:os.kill(pid,signal.SIGTERM)
            except ProcessLookupError:pass
        diagnostics=installation.home/"actual-child-stderr.log"
        if diagnostics.exists():
            installation.trace("actual-native-helper-child-trace",dict(synthetic_boundary=True,stderr=diagnostics.read_text()))
            print("ACTUAL_NATIVE_CHILD_HELPER_TRACE",diagnostics.read_text())



def test_actual_c_guard_deadline_rejection_never_launches_a_product(native_installation):
    """Late helper data cannot extend the actual fixed 15-second guard budget."""
    installation=native_installation;store=_private_estate(installation)
    _static_preparation(installation,store);_seed_synthetic_swing_original(installation)
    (installation.home/"fixture-native-guard-stall").write_text("SYNTHETIC_NATIVE_HELPER_DELAY_16_SECONDS")
    process=installation.start_main(None)
    started=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    try:
        out,err=process.communicate(timeout=40)
        finished=time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        assert process.returncode==1
        assert not (installation.estate/"browser-backend-v1.control").exists()
        assert not _proofs(store,"SOURCE") and not _proofs(store,"ENDPOINT_CONFIGURATION")
        assert not list((store.root/"records").iterdir())
        assert not list((store.root/"slots").iterdir())
        assert not list((store.root/"guards").iterdir())
        assert not list((store.root/"custody").iterdir())
        log=installation.home/"actual-child-stderr.log"
        diagnostic=log.read_text() if log.exists() else ""
        assert "TIMEOUT" in diagnostic or "BUDGET" in diagnostic or "EXPIRED" in diagnostic
        installation.trace("actual-c-guard-deadline-denial",dict(synthetic_fixture_stall_seconds=16,
            actual_monotonic_started_ns=str(started),actual_monotonic_finished_ns=str(finished),
            unchanged_internal_budget_seconds=15,exit=process.returncode,stdout=out.decode(),stderr=err.decode(),
            helper_trace=diagnostic,product_source_proofs=0,product_endpoints=0,product_child_intents=0,
            products_started=0,custody_publications=0))
    finally:
        if process.poll() is None:process.terminate();process.communicate(timeout=10)
