"""Exercise the compiled C preflight/POST using an isolated fake HTTP peer."""
from pathlib import Path
import os
import socket
import subprocess
from threading import Thread

import pytest


@pytest.mark.parametrize('supported',[False,True])
def test_launcher_protocol_preflight_never_stops_a_legacy_backend(tmp_path,supported):
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(2)
    listener.settimeout(5);port=listener.getsockname()[1]
    requests=[];errors=[]
    def peer():
        try:
            for index in range(2 if supported else 1):
                conn,_=listener.accept()
                with conn:
                    data=b''
                    while b'\r\n\r\n' not in data:data+=conn.recv(4096)
                    requests.append(data.decode())
                    body=(b'{"maintenance":{"protocol":"KRONOS_MAINTENANCE_HANDOFF_V1"}}'
                        if supported and index==0 else b'{"service":"KRONOS_BROWSER_V1"}')
                    status=b'200 OK'
                    if index==1:body=b'{"status":"STOPPING"}';status=b'202 Accepted'
                    conn.sendall(b'HTTP/1.0 '+status+b'\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body)
        except Exception as error:errors.append(error)
        finally:listener.close()
    root=Path(__file__).resolve().parents[3]
    source=(root/'tools/macos/kronos_launcher.c').read_text()
    # Redirect the compiled function's socket exclusively to this fake peer.
    source=source.replace('htons(8947)',f'htons({port})').replace('int main(void) {','int unused_application_main(void) {')
    source+=f'\nint main(void) {{ return request_graceful_shutdown({os.getpid()}, "'+('a'*64)+'", "'+('b'*64)+f'") == {1 if supported else 0} ? 0 : 1; }}\n'
    unit=tmp_path/'launcher-test.c';unit.write_text(source);binary=tmp_path/'launcher-test'
    subprocess.run(['clang','-Wall','-Wextra','-Werror',str(unit),'-o',str(binary)],check=True,capture_output=True)
    thread=Thread(target=peer);thread.start()
    try:subprocess.run([str(binary)],check=True,timeout=5,capture_output=True)
    finally:thread.join(6);listener.close()
    assert not thread.is_alive() and not errors
    assert requests[0].startswith('GET /status ')
    if supported:
        assert requests[1].startswith('POST /control/shutdown ')
        assert 'X-Kronos-Maintenance-Generation: '+('b'*64) in requests[1]
    else:assert len(requests)==1
