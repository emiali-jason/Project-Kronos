"""Product-local immutable bytes and atomic selection, using KRONOS conventions."""

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import stat
from uuid import uuid4

from kronos.theta.contracts import PROSPECTIVE_VERSION, ThetaError, digest, encode, parse, require, stamp

DEFAULT_ROOT = Path.home() / "Library/Application Support/KRONOS/evidence/theta-v1"
REVIEW_ROOT = Path.home() / "Documents/Project-KRONOS/KRONOS REVIEW PACK/Theta Earners"
DEFAULT_OUTBOX = REVIEW_ROOT / "KRONOS QUESTIONS"
DEFAULT_INBOX = REVIEW_ROOT / "CHATGPT ANSWERS"
MAX_ARTIFACT_BYTES = 96 * 1024 * 1024


@contextmanager
def directory(path: Path, *, create=False):
    """Reject symlinks in every component; never follow untrusted intake paths."""
    require(isinstance(path, Path) and path.is_absolute() and path != Path("/"),
            "THETA_PATH_INVALID")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            require(component not in {".", ".."}, "THETA_PATH_INVALID")
            if create:
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            following = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        yield descriptor
    finally:
        os.close(descriptor)


def filename(name: str):
    require(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,180}", name) is not None
            and name not in {".", ".."}, "THETA_PATH_INVALID")


def read_at(fd: int, name: str, maximum=MAX_ARTIFACT_BYTES) -> bytes:
    filename(name)
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(descriptor, "rb") as stream:
        facts = os.fstat(stream.fileno())
        require(stat.S_ISREG(facts.st_mode) and facts.st_nlink == 1
                and 0 < facts.st_size <= maximum, "THETA_ARTIFACT_INVALID")
        payload = stream.read(maximum + 1)
        require(len(payload) == facts.st_size and len(payload) <= maximum,
                "THETA_ARTIFACT_INVALID")
        return payload


def write_at(fd: int, name: str, payload: bytes, *, replace=False):
    """No partial-file publication; immutable conflict fails, identical is idempotent."""
    filename(name)
    require(type(payload) is bytes and 0 < len(payload) <= MAX_ARTIFACT_BYTES)
    temporary = "." + uuid4().hex + ".tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=fd)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
        else:
            try:
                os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
            except FileExistsError:
                require(read_at(fd, name) == payload, "THETA_IMMUTABLE_CONFLICT")
        os.fsync(fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError:
            pass


def sealed(value: dict) -> bytes:
    return encode({"value": value, "sha256": digest(encode(value))})


def unseal(payload: bytes) -> dict:
    document = parse(payload)
    require(set(document) == {"value", "sha256"} and type(document["value"]) is dict
            and document["sha256"] == digest(encode(document["value"])),
            "THETA_INTEGRITY_INVALID")
    return document["value"]


class ThetaStore:
    def __init__(self, root=DEFAULT_ROOT):
        require(isinstance(root, Path) and root.is_absolute() and len(root.parts) >= 3,
                "THETA_PATH_INVALID")
        self.root = root

    @contextmanager
    def transaction(self):
        # Cross-process serialization includes reads, publication and restart.
        with directory(self.root, create=True) as root:
            lock = os.open(".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=root)
            try:
                require(stat.S_ISREG(os.fstat(lock).st_mode), "THETA_PATH_INVALID")
                fcntl.flock(lock, fcntl.LOCK_EX)
                yield
            finally:
                os.close(lock)

    def retain(self, family: str, name: str, payload: bytes):
        filename(family)
        with directory(self.root / family, create=True) as fd:
            write_at(fd, name, payload)

    def load(self, family: str, name: str) -> bytes:
        filename(family)
        with directory(self.root / family) as fd:
            return read_at(fd, name)

    def blob(self, payload: bytes) -> str:
        identity = digest(payload)
        self.retain("blobs", identity, payload)
        return identity

    def load_blob(self, identity: str) -> bytes:
        require(type(identity) is str and re.fullmatch(r"[0-9a-f]{64}", identity) is not None,
                "THETA_INTEGRITY_INVALID")
        value = self.load("blobs", identity)
        require(digest(value) == identity, "THETA_INTEGRITY_INVALID")
        return value

    def current(self) -> dict:
        with directory(self.root, create=True) as fd:
            try:
                payload = read_at(fd, "current.json")
                result = unseal(payload)
            except FileNotFoundError:
                if "selection-history" in os.listdir(fd):
                    with directory(self.root / "selection-history") as history:
                        require(not os.listdir(history), "THETA_INTEGRITY_INVALID")
                return {"schema": "KRONOS-THETA-SELECTION-V1", "subjects": {}}
        require(result.get("schema") == "KRONOS-THETA-SELECTION-V1"
                and type(result.get("subjects")) is dict, "THETA_INTEGRITY_INVALID")
        require(self.load("selection-history", digest(payload) + ".json") == payload,
                "THETA_INTEGRITY_INVALID")
        return result

    def select(self, value: dict):
        payload = sealed(value)
        self.retain("selection-history", digest(payload) + ".json", payload)
        with directory(self.root) as fd:
            write_at(fd, "current.json", payload, replace=True)

    def question(self, identity: str) -> dict:
        require(type(identity) is str and re.fullmatch(r"TEQ-[0-9a-f]{64}", identity) is not None)
        value = unseal(self.load("questions", identity + ".json"))
        core = {k: v for k, v in value.items() if k != "question_id"}
        require(value.get("question_id") == identity and identity == "TEQ-" + digest(encode(core)),
                "THETA_INTEGRITY_INVALID")
        charts = value["charts"] + ([value["macro_chart"]] if value.get("schema_version")==PROSPECTIVE_VERSION else [])
        for chart in charts:
            self.load_blob(chart["sha256"])
            require(self.chart("TEC-" + digest(encode(chart))) == chart,
                    "THETA_INTEGRITY_INVALID")
        if value.get("schema_version")==PROSPECTIVE_VERSION:
            require(len(value["subjects"])==1 and len(value["charts"])==1
                    and value["information_cutoff"]==value["created_at"],"THETA_INTEGRITY_INVALID")
            cutoff=stamp(value["information_cutoff"])
            require(all(stamp(chart["information_cutoff"])<=cutoff for chart in charts),
                    "THETA_INTEGRITY_INVALID")
            cycle=unseal(self.load("cycles",value["cycle_id"]+".json"))
            require(value["cycle_id"]=="TAC-"+digest(encode(cycle)),"THETA_INTEGRITY_INVALID")
            require([b["subject"] for b in value["chart_bindings"]]==[value["subjects"][0],"GLOBAL_MACRO"],"THETA_INTEGRITY_INVALID")
            for binding,chart in zip(value["chart_bindings"],charts):
                revision=unseal(self.load("chart-revisions",binding["revision_id"]+".json"))
                require(binding["revision_id"]=="TCR-"+digest(encode(revision))
                        and binding["cycle_id"]==revision["cycle_id"]==value["cycle_id"]
                        and binding["chart_id"]==revision["chart_id"]=="TEC-"+digest(encode(chart))
                        and binding["sha256"]==revision["sha256"]==chart["sha256"]
                        and revision["subject"]==(None if binding["subject"]=="GLOBAL_MACRO" else binding["subject"]),
                        "THETA_INTEGRITY_INVALID")
        return value

    def chart(self, identity: str) -> dict:
        require(type(identity) is str and re.fullmatch(r"TEC-[0-9a-f]{64}", identity) is not None)
        chart = unseal(self.load("charts", identity + ".json"))
        require(identity == "TEC-" + digest(encode(chart)), "THETA_INTEGRITY_INVALID")
        self.load_blob(chart["sha256"])
        return chart
