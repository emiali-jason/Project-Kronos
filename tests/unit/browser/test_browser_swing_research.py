"""WO-12 Browser is observational until one explicit Sponsor POST."""
from types import SimpleNamespace

from tests.unit.browser.test_browser_server import _request, _running_server


def test_research_get_does_not_update_and_explicit_button_post_is_bounded():
    server, thread = _running_server()
    calls = []
    server.swing_research_control = SimpleNamespace(
        status=lambda: {"origins": 2, "milestones": 1,
                        "verified_months": ["2026_10"],
                        "commissioned_at": "2026-10-01T10:00:00+00:00",
                        "admission_capture": None, "v2_capture": None},
        submit_update=lambda identity, parent: calls.append(identity) or {
            "operation_identity": identity, "state": "QUEUED", "phase": "ADMITTED"},
    )
    try:
        for _ in range(3):
            status, _, body = _request(server, "GET", "/swing/research")
            assert status == 200
            assert "UPDATE SWING RESEARCH" in body
            assert "Verified months: 2026_10" in body
        assert calls == []
        identity = "a" * 32
        payload = ("operation_identity=" + identity).encode()
        status, headers, _ = _request(
            server, "POST", "/swing/research/update",
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Host": f"127.0.0.1:{server.server_port}",
                     "Origin": f"http://127.0.0.1:{server.server_port}"},
            body=payload)
        assert status == 303
        assert "operation=" + identity in headers["Location"]
        assert calls == [identity]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_authority_controls_are_authenticated_counted_and_never_get_actions(tmp_path):
    from kronos.browser.restart_control import BrowserBackendRestartControl
    from hashlib import sha256
    import base64, json
    server,thread=_running_server()
    control=BrowserBackendRestartControl.create(tmp_path/'fixture.control')
    server.restart_control=control
    calls=[]
    def commission(**kwargs):
        assert server.maintenance_admission.snapshot()['owners']['BROWSER_POST']==1
        calls.append(('commission',kwargs))
        return SimpleNamespace(identity='receipt',data={'commissioned_at':'2026-10-01T10:00:00+00:00'})
    def import_actions(fields,data):
        assert server.maintenance_admission.snapshot()['owners']['BROWSER_POST']==1
        calls.append(('import',fields,data)); return 'report'
    server.swing_research_control=SimpleNamespace(commission=commission,import_actions=import_actions,
        close=lambda:None)
    headers={'Host':f'127.0.0.1:{server.server_port}',
             'Origin':f'http://127.0.0.1:{server.server_port}', 'Content-Type':'application/json'}
    manifest=b'{}'
    payload=json.dumps(dict(release_identity='a'*40,source_manifest_sha256=sha256(manifest).hexdigest(),
                           manifest_base64=base64.b64encode(manifest).decode())).encode()
    try:
        for path in ('/control/swing-research/commission','/control/swing-research/corporate-actions/import'):
            assert _request(server,'GET',path)[0]==404
            assert _request(server,'POST',path,headers=headers,body=payload)[0]==403
        assert calls==[]
        headers.update({'X-Kronos-Backend-Pid':str(control.process_id),'X-Kronos-Restart-Token':control._token})
        assert _request(server,'POST','/control/swing-research/commission',headers=headers,body=payload)[0]==200
        assert len(calls)==1
        # Duplicate JSON keys and extra fields cannot enter the owner operation.
        for invalid in (b'{"release_identity":"x","release_identity":"y"}',payload[:-1]+b',"extra":1}'):
            assert _request(server,'POST','/control/swing-research/commission',headers=headers,body=invalid)[0]==409
        assert len(calls)==1
        imported=json.dumps(dict(attestation={'capture_identity':'one'},csv_base64=base64.b64encode(b'original').decode())).encode()
        assert _request(server,'POST','/control/swing-research/corporate-actions/import',headers=headers,body=imported)[0]==200
        assert calls[-1][2]==b'original'
        assert server.maintenance_admission.snapshot()['owners']=={}
        generation='f'*64
        assert server.maintenance_admission.claim(generation)
        assert _request(server,'POST','/control/swing-research/commission',headers=headers,body=payload)[0]==503
        assert len(calls)==2
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
