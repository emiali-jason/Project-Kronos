"""RUNTIME-01 startup-only source qualification; no runtime or evidence writes."""
from __future__ import annotations

import ctypes
from contextvars import ContextVar
from kronos.common.release_admission import inherited_budget, validation_output, validation_unresolved
import fnmatch
import glob
from hashlib import sha1
from hashlib import sha256
from dataclasses import replace
from pathlib import Path
import os
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import sys

CANONICAL = Path("/Applications/KRONOS.app")
EXECUTABLE = CANONICAL / "Contents/MacOS/KRONOS"
SOURCE_BRANCH = "maintenance/release-b-swing-ux"
SOURCE_REMOTE = "origin"
SOURCE_REF = "refs/heads/maintenance/release-b-swing-ux"
SOURCE_TRACKING_REF = "refs/remotes/origin/maintenance/release-b-swing-ux"
SOURCE_ORIGIN = "git@github.com:emiali-jason/Project-Kronos.git"


_SOURCE_BUDGET = ContextVar("kronos_source_validation_budget", default=None)


def _git(root, *args):
    budget = _SOURCE_BUDGET.get()
    if budget is None:budget = inherited_budget(60)
    return validation_output(["/usr/bin/git", *args], cwd=root, budget=budget,
        ceiling=20, phase="SOURCE_GIT").decode().strip()



def _destination_denied():
    raise ValueError("SOURCE_DESTINATION_NOT_AUTHORIZED")


def _invocation_environment():
    """Inspect only; never run a configured transport or credential command."""
    forbidden = {"GIT_CONFIG", "GIT_SSH", "GIT_SSH_COMMAND", "GIT_SSH_VARIANT",
        "GIT_PROXY_COMMAND", "GIT_EXEC_PATH", "GIT_DIR", "GIT_COMMON_DIR",
        "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_SHALLOW_FILE",
        "GIT_REPLACE_REF_BASE", "DEVELOPER_DIR"}
    if any(key in forbidden or key.startswith("GIT_CONFIG_") for key in os.environ):
        _destination_denied()
    if shutil.which("ssh") != "/usr/bin/ssh":
        _destination_denied()
    return tuple((key, os.environ.get(key)) for key in
        ("PATH", "HOME", "XDG_CONFIG_HOME", "SSH_AUTH_SOCK"))


def _config_file(path, snapshots, *, optional=False):
    """Read bounded regular configuration files, not keys or executable policy."""
    path = Path(path)
    if not os.path.lexists(path):
        if not optional:
            _destination_denied()
        snapshots.append((str(path), "ABSENT"))
        return None
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved,
        os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 262144:
            _destination_denied()
        raw = bytearray()
        while len(raw) <= 262144:
            part = os.read(descriptor, min(65536, 262145 - len(raw)))
            if not part:
                break
            raw.extend(part)
        after = os.fstat(descriptor)
        named = os.stat(resolved, follow_symlinks=False)
        fields = lambda value: (value.st_dev, value.st_ino, value.st_mode,
            value.st_uid, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if (len(raw) > 262144 or fields(before) != fields(after)
                or fields(after) != fields(named) or path.resolve(strict=True) != resolved):
            _destination_denied()
        snapshots.append((str(path), str(resolved), fields(after), sha256(raw).hexdigest()))
        return raw.decode("utf-8")
    finally:
        os.close(descriptor)


def _git_configuration(root, snapshots):
    # This builtin parses configuration/includes without invoking their commands.
    raw = _git(root, "config", "--includes", "--null", "--show-origin",
        "--show-scope", "--list")
    fields = raw.split("\0")
    if fields[-1:] == [""]:
        fields.pop()
    if len(fields) % 3:
        _destination_denied()
    values = {}
    for offset in range(0, len(fields), 3):
        scope, origin, item = fields[offset:offset + 3]
        key, separator, value = item.partition("\n")
        # Apple's installed vendor gitconfig can be labelled "unknown". Its
        # regular file and every effective setting are still inspected below;
        # command-line/stdin provenance never supplies policy authority.
        if (scope not in {"system", "global", "local", "worktree", "unknown"}
                or not origin.startswith("file:") or not separator):
            _destination_denied()
        config = Path(origin[5:])
        if not config.is_absolute():
            config = root / config
        _config_file(config, snapshots)
        key = key.lower()
        values.setdefault(key, []).append(value)
        if key.startswith("includeif."):
            # No conditional-selection interpreter is introduced by this profile.
            _destination_denied()
        if key == "include.path":
            if "%" in value or "\0" in value:
                _destination_denied()
            included = Path(value).expanduser()
            if not included.is_absolute():
                included = config.parent / included
            _config_file(included, snapshots)
        if ((key.startswith("url.") and key.endswith((".insteadof", ".pushinsteadof")))
                or key in {"core.sshcommand", "core.gitproxy", "ssh.variant",
                    "remote.origin.pushurl", "remote.origin.uploadpack", "remote.origin.vcs",
                    "remote.origin.proxy"}
                or (key == "core.fsmonitor" and value.lower() not in {"false", "no", "off", "0"})
                or (key.startswith("remote.") and not key.startswith("remote.origin."))):
            _destination_denied()
    if values.get("remote.origin.url") != [SOURCE_ORIGIN]:
        _destination_denied()
    if values.get("branch." + SOURCE_BRANCH + ".remote") != [SOURCE_REMOTE]:
        _destination_denied()
    if values.get("branch." + SOURCE_BRANCH + ".merge") != [SOURCE_REF]:
        _destination_denied()
    return tuple(sorted((key, tuple(value)) for key, value in values.items()))


def _ssh_user_home():
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def _ssh_configuration_paths():
    # OpenSSH's user directory comes from passwd, not a caller's HOME override.
    user_home = _ssh_user_home()
    return ((Path("/etc/ssh/ssh_config"), Path("/etc/ssh")),
            (user_home / ".ssh/config", user_home / ".ssh"))


def _host_matches(value, patterns, *, comma_separated=False):
    # Host takes whitespace-separated patterns; Match takes comma-separated
    # pattern lists. Reject Python-only bracket classes before any inactive
    # decision (including an earlier matching negation). OpenSSH uses * and ?.
    items = [item for pattern in patterns
             for item in (pattern.split(",") if comma_separated else [pattern])]
    if any("[" in item or "]" in item for item in items):
        _destination_denied()
    matched = False
    for item in items:
        negative = item.startswith("!")
        pattern = item[1:] if negative else item
        if fnmatch.fnmatchcase(value.lower(), pattern.lower()):
            if negative:
                return False
            matched = True
    return matched


def _ssh_configuration(snapshots):
    # These options preserve authentication/host-key behavior; no key is read.
    passive = set("identityfile identityagent identitiesonly certificatefile addkeystoagent "
        "usekeychain preferredauthentications passwordauthentication kbdinteractiveauthentication "
        "pubkeyauthentication hostbasedauthentication gssapiauthentication pkcs11provider "
        "securitykeyprovider hostkeyalgorithms pubkeyacceptedalgorithms casignaturealgorithms "
        "ciphers kexalgorithms macs compression connecttimeout connectionattempts "
        "serveraliveinterval serveralivecountmax sendenv setenv loglevel logverbose "
        "syslogfacility verifyhostkeydns checkhostip hashknownhosts globalknownhostsfile "
        "userknownhostsfile updatehostkeys stricthostkeychecking revokedhostkeys batchmode "
        "numberofpasswordprompts rekeylimit ipqos addressfamily bindaddress bindinterface "
        "escapechar requesttty tcpkeepalive visualhostkey forwardagent forwardx11 "
        "forwardx11trusted".split())
    local_user = pwd.getpwuid(os.getuid()).pw_name
    seen = set()

    def read(path, base, active=True, ancestors=()):
        if len(ancestors) >= 16 or len(seen) >= 64:
            _destination_denied()
        text = _config_file(path, snapshots, optional=True)
        if text is None:
            return active
        identity = Path(path).resolve()
        if identity in ancestors:
            _destination_denied()
        seen.add(identity)
        for line in text.splitlines():
            try:
                words = shlex.split(line, comments=True)
            except ValueError:
                _destination_denied()
            if not words:
                continue
            if "=" in words[0]:
                keyword, first = words[0].split("=", 1)
                words = [keyword] + ([first] if first else []) + words[1:]
            if words[1:2] == ["="]:
                words.pop(1)
            keyword, args = words[0].lower(), words[1:]
            if not args:
                _destination_denied()
            if keyword == "host":
                active = _host_matches("github.com", args)
            elif keyword == "match":
                if args == ["all"]:
                    active = True
                    continue
                active = True
                while args:
                    criterion = args.pop(0).lower()
                    if criterion not in {"host", "originalhost", "user", "localuser"} or not args:
                        _destination_denied()  # In particular: never evaluate Match exec.
                    subject = {"host": "github.com", "originalhost": "github.com",
                        "user": "git", "localuser": local_user}[criterion]
                    active = _host_matches(subject, [args.pop(0)], comma_separated=True) and active
            elif not active:
                continue
            elif keyword == "include":
                for pattern in args:
                    if "%" in pattern or "${" in pattern:
                        _destination_denied()
                    if pattern == "~" or pattern.startswith("~/"):
                        pattern = _ssh_user_home() / pattern[2:]
                    elif pattern.startswith("~"):
                        _destination_denied()  # Other-user expansion is unresolved.
                    pattern = Path(pattern)
                    if not pattern.is_absolute():
                        pattern = base / pattern
                    for child in sorted(glob.glob(str(pattern))):
                        active = read(Path(child), base, active, (*ancestors, identity))
            elif keyword in {"hostname", "user", "port", "hostkeyalias"}:
                if args != [{"hostname": "github.com", "user": "git",
                              "port": "22", "hostkeyalias": "github.com"}[keyword]]:
                    _destination_denied()
            elif keyword in {"proxycommand", "proxyjump", "controlpath"}:
                if args != ["none"]:
                    _destination_denied()
            elif keyword in {"permitlocalcommand", "forkafterauthentication", "controlmaster",
                             "controlpersist", "canonicalizehostname"}:
                if args not in (["no"], ["false"], ["0"]):
                    _destination_denied()
            elif keyword not in passive:
                _destination_denied()  # Unknown/command-bearing behavior is unresolved.
        return active

    for path, base in _ssh_configuration_paths():
        read(path, base)


def _destination_state(root):
    environment = _invocation_environment()
    snapshots = []
    configuration = _git_configuration(root, snapshots)
    _ssh_configuration(snapshots)
    if _invocation_environment() != environment:
        _destination_denied()
    return environment, configuration, tuple(sorted(set(snapshots), key=repr))


def _fixed_publication(root, revision):
    if (not re.fullmatch(r"[a-f0-9]{40}", revision)
            or _git(root, "branch", "--show-current") != SOURCE_BRANCH
            or _git(root, "rev-parse", "--symbolic-full-name", "@{upstream}") != SOURCE_TRACKING_REF
            or _git(root, "rev-parse", SOURCE_TRACKING_REF) != revision):
        raise ValueError("SOURCE_REVISION_NOT_AUTHORIZED")


def canonical_parent():
    """Kernel parent image plus strict bundle seal; no environment authority."""
    if sys.platform != "darwin":
        raise ValueError("CANONICAL_LAUNCHER_REQUIRED")
    try:
        buffer = ctypes.create_string_buffer(4096)
        library = ctypes.CDLL("/usr/lib/libproc.dylib")
        if (library.proc_pidpath(os.getppid(), buffer, len(buffer)) <= 0
                or Path(os.fsdecode(buffer.value)) != EXECUTABLE
                or EXECUTABLE.resolve() != EXECUTABLE):
            raise ValueError("CANONICAL_LAUNCHER_REQUIRED")
        validation_output(["/usr/bin/codesign", "--verify", "--deep", "--strict",
            "-R", '=identifier "com.project-kronos.browser-v1"', str(CANONICAL)],
            cwd=None, budget=_SOURCE_BUDGET.get() or inherited_budget(60),
            ceiling=10, phase="SOURCE_SIGNATURE")
    except (OSError, subprocess.SubprocessError):
        raise ValueError("CANONICAL_SIGNATURE_INVALID") from None


def _qualify_repository(root):
    """One fixed maintenance publication; no caller-selected release policy."""
    root = Path(root).resolve()
    def git(*args):
        budget = _SOURCE_BUDGET.get()
        if budget is not None:budget.check()
        result = _git(root, *args)
        if budget is not None:budget.check()
        return result
    try:
        _invocation_environment()
        if Path(git("rev-parse", "--show-toplevel")).resolve() != root:
            raise ValueError("SOURCE_PROOF_UNAVAILABLE")
        destination = _destination_state(root)
        if git("status", "--porcelain=v1", "--untracked-files=all"):
            raise ValueError("SOURCE_NOT_CLEAN")
        revision = git("rev-parse", "HEAD")
        _fixed_publication(root, revision)
        if _destination_state(root) != destination:
            _destination_denied()
        if git("ls-remote", "--exit-code", SOURCE_REMOTE, SOURCE_REF) != revision + "\t" + SOURCE_REF:
            raise ValueError("SOURCE_REVISION_NOT_AUTHORIZED")
        # Do not trust index stat caches, assume-unchanged or ignored Python files.
        tree = git("ls-tree", "-r", revision, "--", "src/kronos", "tools")
        blobs = {line.split("\t", 1)[1]: line.split("\t", 1)[0].split()[2]
                 for line in tree.splitlines()}
        seen = set()
        for prefix in ("src/kronos", "tools"):
            for path in (root / prefix).rglob("*.py"):
                if path.is_symlink() or not path.resolve().is_relative_to(root):
                    raise ValueError("SOURCE_NOT_CLEAN")
                seen.add(str(path.relative_to(root)))
                payload = path.read_bytes()
                actual = sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
                if blobs.get(str(path.relative_to(root))) != actual:
                    raise ValueError("SOURCE_NOT_CLEAN")
        if seen != {name for name in blobs if name.endswith(".py")}:
            raise ValueError("SOURCE_NOT_CLEAN")
        if git("rev-parse", "HEAD") != revision or git("status", "--porcelain=v1", "--untracked-files=all"):
            raise ValueError("SOURCE_NOT_CLEAN")
        _fixed_publication(root, revision)
        if _destination_state(root) != destination:
            _destination_denied()
        return revision
    except (OSError, subprocess.SubprocessError, IndexError, UnicodeError):
        raise ValueError("SOURCE_PROOF_UNAVAILABLE") from None


def _qualify_startup(root, evidence):
    canonical_parent()
    revision = qualify_repository(root)
    try:
        replace(evidence)
        if (evidence.source_revision != revision or evidence.source_state != "CLEAN_COMMIT"
                or evidence.process_id != os.getpid()
                or evidence.load_verification != "PINNED_STARTUP_IMPORTS"
                or not evidence.source_snapshot_digest):
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("SOURCE_PROOF_UNAVAILABLE") from None
    return revision


def _source_call(function, *args):
    existing = _SOURCE_BUDGET.get()
    budget = existing or inherited_budget(60)
    token = _SOURCE_BUDGET.set(budget)
    try:
        budget.check()
        result = function(*args)
        budget.check()
        return result
    finally:
        _SOURCE_BUDGET.reset(token)


def qualify_repository(root):
    return _source_call(_qualify_repository, root)


def qualify_startup(root, evidence):
    return _source_call(_qualify_startup, root, evidence)


if __name__ == "__main__":
    try:
        def source_main():
            canonical_parent()
            qualify_repository(Path(__file__).resolve().parents[1])
        _source_call(source_main)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(79 if validation_unresolved() else 1)
