"""RUNTIME-01 shared startup completion and inert Browser authority projection."""
from __future__ import annotations

import re
import json
from hashlib import sha256

SCHEMA = "KRONOS-RUNTIME-STATE/1.0.0"
POLICY = {"identity": "KRONOS-RUNTIME-01", "version": "1.0.0",
    "source": "CLEAN_PUBLISHED_DEVELOP_PINNED_CANONICAL_PARENT",
    "restoration": "EXACT_OR_EXISTING_EXACT_COMPATIBILITY_ONLY",
    "maintenance_exit": "VERIFIED_STARTUP_NO_AUTHENTICATION",
    "monitoring": "INERT_FACTUAL_PROJECTION_NO_GAP_RECONSTRUCTION"}
POLICY_CHECKSUM = sha256(json.dumps(POLICY, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def complete_startup(server, shadow):
    governance = server.connection_governance
    failure = None
    try:
        # Snapshot retained owner evidence once, not on status/page reads.
        server.startup_monitoring_owners = [
            {"owner_identity": p.track.track_identity,
             "product": "SWING_PAPER_OBSERVATION",
             "track_state": p.track_state.value,
             "monitoring_state": p.monitoring_state.value,
             "monitoring_reason": p.monitoring_reason,
             "last_factual_observation_at": (None if p.last_factual_observation_at is None
                                             else p.last_factual_observation_at.isoformat())}
            for p in server.trade_window.paper_observation_projections()]
        status = shadow.status()
        if status["failure"] or (status["window"] is not None and not status["runtime_accepted"]):
            failure = "ACCEPTANCE_RESTORATION_NOT_ESTABLISHED"
        elif server.visual_v3_live.restoration_error is not None:
            failure = "SWING_RESTORATION_NOT_ESTABLISHED"
        elif server.provider_runtime.read_only_status()["capability_state"] != "ABSENT":
            failure = "UNEXPECTED_STARTUP_PROVIDER_CAPABILITY"
        elif server.swing_monitoring_hub.active_session_count:
            failure = "UNEXPECTED_STARTUP_TRANSPORT"
        # Persisted owners stay suspended without a new authenticated capability.
        # Existing explicit-connect restorer owns resubscription and gap evidence.
        server.monitoring_restoration_state = "DEFERRED_PROVIDER_DISCONNECTED"
    except (ValueError, OSError, TypeError, KeyError, AttributeError):
        failure = "RUNTIME_RESTORATION_PROOF_UNAVAILABLE"
    try:
        governance.complete_startup(failure)
    except (ValueError, OSError):
        governance.complete_startup("STARTUP_COMPLETION_RECORD_UNAVAILABLE")


def status_document(server):
    governance = server.connection_governance
    provider_runtime = getattr(server, "provider_runtime", None)
    provider_status = ({"capability_state": "NOT_EXPOSED", "operation_authority": "NONE"}
                       if provider_runtime is None else provider_runtime.read_only_status())
    connection_attempt = getattr(server.application, "connection_attempt_status", None)
    restoration_status = getattr(
        server.application, "sponsor_operability_restoration_status", None
    )
    restoration = (
        dict(restoration_status()) if callable(restoration_status) else {
            "state": "NOT_EXPOSED",
            "connection_generation": None,
            "failure": "",
            "work_owned": False,
            "owned_work_count": 0,
            "cleanup_state": "COMPLETE",
        }
    )
    return {"schema": SCHEMA, "policy": POLICY, "policy_checksum": POLICY_CHECKSUM,
        "process": None if governance is None else {
            "pid": governance.process.pid,
            "revision": governance.process.loaded_revision,
            "source_state": governance.process.source_state},
        "maintenance": None if governance is None else governance.maintenance_status(),
        "rest_authentication": server.application.snapshot().provider_state.value,
        "connection_attempt": connection_attempt() if callable(connection_attempt) else None,
        "rest_capability": provider_status["capability_state"],
        "provider_runtime": provider_status,
        "restoration_readiness": {
            "state": restoration["state"],
            "ready": restoration["state"] == "SUCCEEDED",
            "connection_generation": restoration["connection_generation"],
            "failure": restoration["failure"],
            "work_owned": restoration["work_owned"],
            "cleanup_state": restoration["cleanup_state"],
        },
        "browser_requests": server.request_capacity_status(),
        "monitoring": server.swing_monitoring_hub.status_document(),
        "owner_restoration": getattr(server, "monitoring_restoration_state", "NOT_ASSESSED"),
        "startup_retained_owner_evidence": getattr(server, "startup_monitoring_owners", []),
        "retained_owner_scope": "STARTUP_SNAPSHOT_NOT_CURRENT_LIFECYCLE_PROJECTION"}


def decorate_html(body, governance):
    if governance is None:
        return body
    for surface in ("HEADER", "SETTINGS"):
        marker = f'data-provider-control="{surface}"'
        body = body.replace(marker + ">", marker + '><input type="hidden" name="action_reference" value="'
                            + governance.action_reference(surface) + '">')
    state = governance.maintenance_status()
    control = ('<aside id="kronos-maintenance" role="status"' + ('' if state['active'] else ' hidden')
        + '><p>Controlled maintenance is active.</p><form method="post" action="/control/maintenance/exit">'
        + '<input type="hidden" name="action_reference" value="' + governance.action_reference("MAINTENANCE_EXIT")
        + '"><button type="submit">' + ('END MAINTENANCE' if state['active'] else '') + '</button></form></aside>')
    body = re.sub(r"<body\b[^>]*>", lambda m: m.group(0) + control, body, count=1)
    script = """<script>
window.applyKronosRuntimeState=function(s){const m=s.maintenance;if(!m)return;
const n=document.getElementById('kronos-maintenance');if(!n)return;
n.hidden=!m.active;n.querySelector('button').textContent=m.active?['END','MAINTENANCE'].join(' '):'';};
async function refreshKronosRuntimeState(){try{const r=await fetch('/runtime/status',{cache:'no-store'});
if(r.ok)window.applyKronosRuntimeState(await r.json());}catch(_e){}}
window.addEventListener('pageshow',refreshKronosRuntimeState);
window.addEventListener('focus',refreshKronosRuntimeState);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshKronosRuntimeState();});
</script>"""
    return body.replace('</body>', script + '</body>')
