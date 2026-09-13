"""WO-13 adapter of the shared notification centre, not a second product/store.

Durable compact source references are queued only after governed source writes.
One worker drains the queue; GET reads the centre's restored memory projection.
No acquisition, subscription, analytical decision or research publication lives here.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC
from hashlib import sha256
import json
from threading import RLock

from kronos.application import intraday_notification_sources as sources
from kronos.intraday.notification_policy import telegram_text, aware
from kronos.intraday.wo11_lifecycle import TERMINAL


class IntradayNotifications:
    KINDS = {"PROBABLES", "READINESS", "CURRENTNESS", "COMPARISON", "UNAVAILABLE", "TRACK"}

    def __init__(self, *, centre, research, wo09, futures, lifecycle, telegram=None, background=True):
        self.centre, self.research, self.wo09 = centre, research, wo09
        self.futures, self.lifecycle, self.telegram = futures, lifecycle, telegram
        self.root = centre._store.root / "intraday-source-references-v1"
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(max_workers=1,thread_name_prefix="kronos-notification") if background else None
        self._scheduled = False
        self.last_failure = None
        self._origins = {}
        self._refresh_origins()
        self.owner_states = {}
        self.terminal_tracks = set()
        # Restore presentation only. No sources are reconstructed on GET.
        for track in lifecycle.restore():
            self._monitoring(track)

    def _refresh_origins(self):
        for item in self.research.store.records("WO12_OPPORTUNITY_ORIGIN_V1"):
            d=item.data; key=(d["canonical_subject_identity"],d["market_session_identity"])
            self._origins.setdefault(key,{})[item.identity]=item

    def _origin(self, subject, session, at):
        values=[x for x in self._origins.get((subject,session),{}).values() if aware(x.data["origin_at"])<=aware(at)]
        if not values:raise ValueError("WO13_OPPORTUNITY_ORIGIN_NOT_RETAINED")
        return max(values,key=lambda x:(aware(x.data["origin_at"]),x.identity))

    def bind(self, probables):
        probables.opportunity_origin_listener=self.research.publish_admitted_origins
        for store in (probables,self.wo09,self.futures,self.lifecycle):
            store.notification_listener=self.enqueue
        self.probables=probables
        if self.root.exists() and any(self.root.glob("*.pending")):
            self._schedule()

    def enqueue(self, kind, identity):
        if kind not in self.KINDS or not isinstance(identity,str) or len(identity)>200:
            raise ValueError("WO13_SOURCE_REFERENCE_INVALID")
        with self._lock:
            self.root.mkdir(parents=True,exist_ok=True)
            key=sha256((kind+":"+identity).encode()).hexdigest()
            path=self.root/(key+".pending")
            if (self.root/(key+".done")).exists() or path.exists():return
            payload={"kind":kind,"identity":identity,"received_at":datetime.now(UTC).isoformat()}
            with path.open("x") as f:
                json.dump(payload,f,sort_keys=True);f.flush()
                import os
                os.fsync(f.fileno())
            path.chmod(0o600)
        self._schedule()

    def _schedule(self):
        if self._executor is not None:
            with self._lock:
                if not self._scheduled:
                    self._scheduled=True
                    self._executor.submit(self.drain)

    def drain(self):
        with self._lock:
            try:
                pending=sorted(((p,json.loads(p.read_text())) for p in self.root.glob("*.pending")),key=lambda x:(x[1]["received_at"],x[0].name))
                for path,ref in pending:
                    try:
                        self._consume(ref["kind"],ref["identity"])
                        path.rename(path.with_suffix(".done"))
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
            origin=self._origin(r.canonical_subject_identity,r.session_identity,r.created_at)
            self.centre.expire_intraday(origin.data["opportunity_identity"],{"READY_FOUR","READY_FIVE"},at=pointer.updated_at)
            return
        if kind=="READINESS":
            r=self.wo09.load_readiness(identity)
            origin=self._origin(r.canonical_subject_identity,r.session_identity,r.created_at)
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

    def close(self):
        if self._executor is not None:self._executor.shutdown(wait=True)
