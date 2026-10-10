"""WO-13 adapter of the shared notification centre, not a second product/store.

Durable compact source references are queued only after governed source writes.
One worker drains the queue; GET reads the centre's restored memory projection.
No acquisition, subscription, analytical decision or research publication lives here.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC
from hashlib import sha256
import json
import os
import re
import stat
import tempfile
from threading import RLock
from pathlib import Path
from kronos.common.maintenance_admission import MaintenanceAdmissionCoordinator
from kronos.common.maintenance import _valid_notification_checkpoint

from kronos.application import intraday_notification_sources as sources
from kronos.intraday.notification_policy import telegram_text, aware
from kronos.intraday.wo11_lifecycle import TERMINAL


class IntradayNotifications:
    KINDS = {"PROBABLES", "READINESS", "CURRENTNESS", "COMPARISON", "UNAVAILABLE", "TRACK"}

    def __init__(self, *, centre, research, wo09, futures, lifecycle, telegram=None,
                 background=True, expected_checkpoint=None):
        if (expected_checkpoint is not None
                and not _valid_notification_checkpoint(expected_checkpoint)):
            raise ValueError("WO13_EXPECTED_CHECKPOINT_INVALID")
        self.centre, self.research, self.wo09 = centre, research, wo09
        self.futures, self.lifecycle, self.telegram = futures, lifecycle, telegram
        self.root = centre._store.root / "intraday-source-references-v1"
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(max_workers=1,thread_name_prefix="kronos-notification") if background else None
        self._scheduled = False
        self._closed = False
        self._maintenance_admission: MaintenanceAdmissionCoordinator | None = None
        self.last_failure = None
        self._pending_reference_count = 0
        self._durability_unproven = False
        self._expected_checkpoint = (None if expected_checkpoint is None
                                     else dict(expected_checkpoint))
        self._origins = {}
        self._refresh_origins()
        self.owner_states = {}
        self.terminal_tracks = set()
        # Restore presentation only. No sources are reconstructed on GET.
        for track in lifecycle.restore():
            self._monitoring(track)

    def bind_maintenance_admission(self, admission: MaintenanceAdmissionCoordinator) -> None:
        with self._lock:
            if self._scheduled or self._maintenance_admission is not None:
                raise ValueError("WO13_MAINTENANCE_BINDING_CONFLICT")
            self._maintenance_admission = admission

    def _refresh_origins(self):
        for item in self.research.store.records("WO12_OPPORTUNITY_ORIGIN_V1"):
            d=item.data; key=(d["canonical_subject_identity"],d["market_session_identity"])
            self._origins.setdefault(key,{})[item.identity]=item

    def _origin(self, subject, session, at):
        values=[x for x in self._origins.get((subject,session),{}).values() if aware(x.data["origin_at"])<=aware(at)]
        if not values:raise ValueError("WO13_OPPORTUNITY_ORIGIN_NOT_RETAINED")
        return max(values,key=lambda x:(aware(x.data["origin_at"]),x.identity))

    def _readiness_origin(self, readiness):
        from kronos.intraday.wo09_machine_readiness import MachineReadinessRecord
        if type(readiness) is MachineReadinessRecord:
            readiness.__post_init__()
            # WO08 includes non-admitted population. Such unavailable records
            # have no opportunity origin and cannot create a notification.
            values = [x for x in self._origins.get((readiness.canonical_subject_identity,
                readiness.session_identity), {}).values()
                if aware(x.data["origin_at"]) <= aware(readiness.created_at)]
            if not values:
                return None
        return self._origin(readiness.canonical_subject_identity, readiness.session_identity, readiness.created_at)

    def bind(self, probables):
        checkpoint = self.checkpoint()
        if (self._expected_checkpoint is not None
                and checkpoint != self._expected_checkpoint):
            raise ValueError("WO13_NOTIFICATION_CHECKPOINT_MISMATCH")
        self._pending_reference_count = checkpoint["pending_count"]
        probables.opportunity_origin_listener=self.research.publish_admitted_origins
        for store in (probables,self.wo09,self.futures,self.lifecycle):
            store.notification_listener=self.enqueue
        self.probables=probables
        if checkpoint["pending_count"]:
            self._schedule()

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def checkpoint(self, *, certify_durable: bool = False) -> dict[str, object]:
        """Validate a durable replay set; pending does not mean active work."""
        with self._lock:
            if certify_durable and self._durability_unproven:
                raise ValueError("WO13_NOTIFICATION_DURABILITY_UNPROVEN")
            if not self.root.exists():
                if certify_durable:
                    self._fsync_directory(self.root.parent)
                return {"state": "EMPTY", "pending_count": 0,
                        "sha256": sha256(b"").hexdigest()}
            if self.root.is_symlink() or not self.root.is_dir():
                raise ValueError("WO13_NOTIFICATION_CHECKPOINT_INVALID")
            entries: list[bytes] = []
            pending_count = 0
            for path in sorted(self.root.iterdir()):
                if (path.suffix not in {".pending", ".done"}
                        or not re.fullmatch(r"[0-9a-f]{64}", path.stem)
                        or path.is_symlink()):
                    raise ValueError("WO13_NOTIFICATION_CHECKPOINT_INVALID")
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    info = os.fstat(fd)
                    if not stat.S_ISREG(info.st_mode) or info.st_size > 1024:
                        raise ValueError("WO13_NOTIFICATION_CHECKPOINT_INVALID")
                    with os.fdopen(fd, "rb", closefd=False) as handle:
                        raw = handle.read(1025)
                finally:
                    os.close(fd)
                try:
                    ref = json.loads(raw)
                    at = datetime.fromisoformat(ref["received_at"])
                    valid = (type(ref) is dict
                        and set(ref) == {"kind", "identity", "received_at"}
                        and ref["kind"] in self.KINDS
                        and type(ref["identity"]) is str
                        and 0 < len(ref["identity"]) <= 200
                        and at.tzinfo is not None and at.utcoffset() is not None
                        and sha256((ref["kind"] + ":" + ref["identity"]).encode()).hexdigest()
                            == path.stem
                        and raw == json.dumps(ref, sort_keys=True).encode())
                except (ValueError, TypeError, KeyError, AttributeError,
                        UnicodeDecodeError):
                    valid = False
                if not valid:
                    raise ValueError("WO13_NOTIFICATION_CHECKPOINT_INVALID")
                entries.append(path.name.encode() + b":" + sha256(raw).hexdigest().encode())
                pending_count += path.suffix == ".pending"
            digest = sha256(b"\n".join(entries)).hexdigest()
            if certify_durable:
                # This covers references written by the older direct-enqueue
                # path as well as current staged publications.
                self._fsync_directory(self.root)
                self._fsync_directory(self.root.parent)
            return {"state": "VALID_PENDING" if pending_count else "EMPTY",
                    "pending_count": pending_count, "sha256": digest}

    def enqueue(self, kind, identity):
        admission = self._maintenance_admission
        ticket = None if admission is None else admission.admit("NOTIFICATION")
        if admission is not None and ticket is None:
            raise ValueError("WO13_MAINTENANCE_FENCED")
        try:
            return self._enqueue_owned(kind, identity)
        finally:
            if ticket is not None:
                ticket.release()

    def _enqueue_owned(self, kind, identity):
        if kind not in self.KINDS or not isinstance(identity,str) or len(identity)>200:
            raise ValueError("WO13_SOURCE_REFERENCE_INVALID")
        with self._lock:
            created = not self.root.exists()
            self.root.mkdir(parents=True,exist_ok=True)
            if created:
                self._fsync_directory(self.root.parent)
            key=sha256((kind+":"+identity).encode()).hexdigest()
            path=self.root/(key+".pending")
            if (self.root/(key+".done")).exists() or path.exists():return
            payload={"kind":kind,"identity":identity,"received_at":datetime.now(UTC).isoformat()}
            fd, staged = tempfile.mkstemp(prefix=f".{key}.", suffix=".staged", dir=self.root)
            with os.fdopen(fd, "w") as f:
                json.dump(payload,f,sort_keys=True);f.flush()
                os.fsync(f.fileno())
            # A no-overwrite hard link publishes only complete, fsynced bytes.
            # An interrupted staged file remains invalid to checkpoint proof.
            os.link(staged, path, follow_symlinks=False)
            self._fsync_directory(self.root)
            os.unlink(staged)
            self._fsync_directory(self.root)
            self._pending_reference_count += 1
        self._schedule()

    def _schedule(self):
        if self._executor is not None:
            admission = self._maintenance_admission
            ticket = None if admission is None else admission.admit("NOTIFICATION")
            if admission is not None and ticket is None:
                return
            scheduled = False
            with self._lock:
                if not self._scheduled and not self._closed:
                    self._scheduled=True
                    try:
                        self._executor.submit(self._drain_owned, ticket)
                        scheduled = True
                    except RuntimeError:
                        self._scheduled = False
            if ticket is not None and not scheduled:
                ticket.release()

    def _drain_owned(self, ticket):
        try:
            if ticket is None:
                self.drain()
            else:
                with ticket.activate():
                    self.drain()
        finally:
            if ticket is not None:
                ticket.release()

    def drain(self):
        with self._lock:
            try:
                pending=sorted(((p,json.loads(p.read_text())) for p in self.root.glob("*.pending")),key=lambda x:(x[1]["received_at"],x[0].name))
                for path,ref in pending:
                    try:
                        self._consume(ref["kind"],ref["identity"])
                        path.rename(path.with_suffix(".done"))
                        try:
                            self._fsync_directory(self.root)
                        except OSError:
                            self._durability_unproven = True
                            raise
                        self._pending_reference_count -= 1
                        self.last_failure=None
                    except (ValueError,TypeError,KeyError,OSError,RuntimeError):
                        self.last_failure="WO13_SOURCE_OR_LINEAGE_UNAVAILABLE"
                        # Keep exact reference for a later source-driven attempt.
            finally:self._scheduled=False

    def _emit(self, detail):
        if detail is None:return
        detail=dict(detail,published_at=datetime.now(UTC).isoformat())
        item=self.centre.accept_intraday(detail)
        if item.dismissed or item.state.value!="LIVE" or item.telegram_delivery!="PENDING":return
        if self.telegram is None or not self.telegram.status().private_chat_configured or not self.telegram.status().delivery_enabled:
            return
        # Persist dispatch intent before transport: ambiguous process interruption
        # never causes an automatic duplicate message on restoration.
        self.centre.record_delivery(item.notification_identity,"ATTEMPTING")
        try:
            result=self.telegram.send(telegram_text(detail))
            state="SENT" if result.state.value=="SENT" else "FAILED"
        except Exception:state="FAILED"
        self.centre.record_delivery(item.notification_identity,state)

    def _consume(self, kind, identity):
        if kind=="PROBABLES":
            # The synchronous admitted-persistence origin producer has already
            # completed.  Notification delivery merely refreshes its compact
            # lookup and never becomes identity authority.
            self._refresh_origins()
            return
        if kind=="CURRENTNESS":
            pointer=self.wo09.load_pointer(identity)
            r=self.wo09.load_readiness(pointer.readiness_identity)
            origin=self._readiness_origin(r)
            if origin is None:return
            self.centre.expire_intraday(origin.data["opportunity_identity"],{"READY_FOUR","READY_FIVE"},at=pointer.updated_at)
            return
        if kind=="READINESS":
            r=self.wo09.load_readiness(identity)
            origin=self._readiness_origin(r)
            if origin is None:return
            d=sources.ready(origin,r)
            if r.satisfied_count!=4:
                self.centre.expire_intraday(origin.data["opportunity_identity"],{"READY_FOUR"},at=r.created_at)
            if r.satisfied_count!=5:
                self.centre.expire_intraday(origin.data["opportunity_identity"],{"READY_FIVE"},at=r.created_at)
            self._emit(d)
            return
        if kind in {"COMPARISON","UNAVAILABLE"}:
            c=self.futures.load(identity);d=c.data;r=self.wo09.load_readiness(d["readiness_identity"])
            origin=self._origin(d["subject"],r.session_identity,d["created_at"])
            if kind=="UNAVAILABLE":
                self._emit(sources.unavailable(origin,c,r.session_identity));return
            self.centre.expire_intraday(origin.data["opportunity_identity"],{"ACTION_REQUIRED"},at=aware(d["created_at"]))
            self._emit(sources.trade_candidate(origin,c,self.futures.load(d["expression_identity"]),
                self.futures.load(d["plan_identity"]),self.futures.load(d["advisory_identity"])))
            return
        current=self.lifecycle.load(identity);d=current.data;i=d["intake"]
        origin=self._origin(i["subject"],i["session_identity"],d["armed_at"])
        event=self.lifecycle.load(d["event_identity"]) if d["event_identity"] else None
        metric=self.lifecycle.load(d["metrics"]) if d["metrics"] else None
        gap=self.lifecycle.load(d["gaps"][-1]) if d["gaps"] else None
        self._monitoring(current)
        details=sources.track_events(origin,current,event=event,metrics=metric,gap_record=gap)
        for notice in details:self._emit(notice)
        if d["monitoring"]!="INTERRUPTED" or d["state"] in TERMINAL:
            self.centre.expire_intraday(origin.data["opportunity_identity"],{"MONITORING_INTERRUPTED"},at=aware(d["updated_at"]),track_identity=d["track_identity"])
        if d["state"] in TERMINAL:
            self.centre.expire_intraday(origin.data["opportunity_identity"],{"PAPER_ENTRY","OBSERVATION_ENTRY"},at=aware(d["updated_at"]),track_identity=d["track_identity"])

    def _monitoring(self, current):
        d=current.data;owner="INTRADAY-WO11-LIFECYCLE:"+d["track_identity"]
        terminal=d["state"] in TERMINAL
        if terminal:self.terminal_tracks.add(d["track_identity"])
        # AVAILABLE is an exact lifecycle observation, not REST connectedness.
        self.owner_states[owner]="NOT_REQUIRED" if terminal else {
            "AVAILABLE":"LIVE","INTERRUPTED":"INTERRUPTED","UNATTACHED":"IDLE"}.get(d["monitoring"],"UNAVAILABLE")

    def indicator(self, details):
        return sources.monitoring_indicator(details,self.owner_states,
            terminal=details.get("track_identity") in self.terminal_tracks)

    def close(self, *, wait=True):
        if self._executor is not None:self._executor.shutdown(wait=wait)
        with self._lock:
            self._closed = True

    def maintenance_status(self):
        with self._lock:
            return {"closed": self._closed, "scheduled": self._scheduled,
                    "pending_reference_count": self._pending_reference_count}
