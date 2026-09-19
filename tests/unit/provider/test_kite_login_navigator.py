import pickle

import pytest

from kronos.provider.adapters.kite.navigation import (
    KiteBrowserRedirectNavigator,
    KiteLoginNavigator,
)
from kronos.provider.models.authentication import (
    BrowserOpenCategory,
    BrowserOpenRequest,
)


VALID_URL = "https://kite.zerodha.com/connect/login?api_key=ABC123&v=3"


class _Opener:
    def __init__(self, result: bool | BaseException) -> None:
        self.result = result
        self.urls: list[str] = []

    def __call__(self, url: str) -> bool:
        self.urls.append(url)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def test_approved_kite_url_opens_once() -> None:
    opener = _Opener(True)
    navigator = KiteLoginNavigator(opener=opener)

    result = navigator.open_official_login(BrowserOpenRequest(VALID_URL))

    assert result.category is BrowserOpenCategory.OPENED
    assert opener.urls == [VALID_URL]


def test_browser_decline_is_one_call_with_no_fallback() -> None:
    opener = _Opener(False)
    navigator = KiteLoginNavigator(opener=opener)

    first = navigator.open_official_login(BrowserOpenRequest(VALID_URL))

    assert first.category is BrowserOpenCategory.DECLINED
    assert opener.urls == [VALID_URL]


def test_browser_exception_is_sanitized_and_not_retried() -> None:
    opener = _Opener(RuntimeError("raw browser failure"))
    navigator = KiteLoginNavigator(opener=opener)

    result = navigator.open_official_login(BrowserOpenRequest(VALID_URL))

    assert result.category is BrowserOpenCategory.FAILED
    assert opener.urls == [VALID_URL]
    assert "raw" not in repr(result)


@pytest.mark.parametrize(
    "url",
    [
        "http://kite.zerodha.com/connect/login?api_key=ABC123&v=3",
        "https://evil.example/connect/login?api_key=ABC123&v=3",
        "https://kite.zerodha.com.evil.example/connect/login?api_key=ABC123&v=3",
        "https://KITE.ZERODHA.COM/connect/login?api_key=ABC123&v=3",
        "https://user@kite.zerodha.com/connect/login?api_key=ABC123&v=3",
        "https://kite.zerodha.com:8443/connect/login?api_key=ABC123&v=3",
        "https://kite.zerodha.com/other?api_key=ABC123&v=3",
        "https://kite.zerodha.com/connect/login?api_key=ABC123&v=3#fragment",
        "https://kite.zerodha.com/connect/login?v=3",
        "https://kite.zerodha.com/connect/login?api_key=&v=3",
        "https://kite.zerodha.com/connect/login?api_key=ABC123",
        "https://kite.zerodha.com/connect/login?api_key=ABC123&v=2",
        "https://kite.zerodha.com/connect/login?api_key=ABC123&v=3&extra=1",
        "https://kite.zerodha.com/connect/login?api_key=ABC123&api_key=DEF456&v=3",
        "https://kite.zerodha.com/connect/login?api_key=ABC-123&v=3",
        "https://kite.zerodha.com/connect/login?api_key=ABC123&v=3&broken",
    ],
)
def test_non_governed_login_urls_are_rejected_before_browser(url: str) -> None:
    opener = _Opener(True)

    result = KiteLoginNavigator(opener=opener).open_official_login(
        BrowserOpenRequest(url)
    )

    assert result.category is BrowserOpenCategory.FAILED
    assert opener.urls == []


def test_explicit_default_https_port_is_permitted() -> None:
    opener = _Opener(True)
    url = "https://kite.zerodha.com:443/connect/login?v=3&api_key=ABC123"

    result = KiteLoginNavigator(opener=opener).open_official_login(
        BrowserOpenRequest(url)
    )

    assert result.category is BrowserOpenCategory.OPENED
    assert opener.urls == [url]


def test_invalid_request_type_never_calls_browser() -> None:
    opener = _Opener(True)

    result = KiteLoginNavigator(opener=opener).open_official_login(  # type: ignore[arg-type]
        object()
    )

    assert result.category is BrowserOpenCategory.FAILED
    assert opener.urls == []


def test_navigator_representation_and_serialization_are_redacted() -> None:
    navigator = KiteLoginNavigator(opener=_Opener(True))

    assert repr(navigator) == "<KiteLoginNavigator redacted>"
    assert str(navigator) == "<KiteLoginNavigator redacted>"
    assert "api_key" not in repr(navigator)
    with pytest.raises((TypeError, pickle.PicklingError)):
        pickle.dumps(navigator)


def test_browser_redirect_navigation_publishes_once_for_exact_generation(
    monkeypatch,
) -> None:
    from kronos.provider.adapters.kite import navigation as module
    from kronos.provider.services.provider_authentication import (
        ConnectionAttemptDeadline,
    )

    monkeypatch.setattr(
        module.webbrowser,
        "open_new_tab",
        lambda _url: (_ for _ in ()).throw(AssertionError("OS browser called")),
    )
    deadline = ConnectionAttemptDeadline(7, timeout_seconds=2)
    navigator = KiteBrowserRedirectNavigator()
    navigator.bind_attempt(deadline)

    assert navigator.open_official_login(
        BrowserOpenRequest(VALID_URL)
    ).category is BrowserOpenCategory.OPENED
    assert navigator.open_official_login(
        BrowserOpenRequest(VALID_URL)
    ).category is BrowserOpenCategory.FAILED
    assert navigator.take_redirect(8, timeout_seconds=0.01) is None
    assert navigator.take_redirect(7, timeout_seconds=1) == VALID_URL

    deadline.cancel()
    deadline.worker_finished()


def test_browser_redirect_navigation_rejects_invalid_url_and_wakes_on_terminal() -> None:
    from threading import Thread
    from kronos.provider.services.provider_authentication import (
        ConnectionAttemptDeadline,
    )

    deadline = ConnectionAttemptDeadline(9, timeout_seconds=2)
    navigator = KiteBrowserRedirectNavigator()
    navigator.bind_attempt(deadline)
    invalid = VALID_URL.replace("kite.zerodha.com", "evil.example")
    assert navigator.open_official_login(
        BrowserOpenRequest(invalid)
    ).category is BrowserOpenCategory.FAILED

    results = []
    waiter = Thread(
        target=lambda: results.append(
            navigator.take_redirect(9, timeout_seconds=1)
        )
    )
    waiter.start()
    deadline.cancel()
    waiter.join(1)

    assert not waiter.is_alive()
    assert results == [None]
    deadline.worker_finished()


def test_late_browser_redirect_invalidation_cannot_clear_fresh_generation() -> None:
    from kronos.provider.services.provider_authentication import (
        ConnectionAttemptDeadline,
    )

    first = ConnectionAttemptDeadline(1, timeout_seconds=2)
    second = ConnectionAttemptDeadline(2, timeout_seconds=2)
    navigator = KiteBrowserRedirectNavigator()
    navigator.bind_attempt(first)
    first.cancel()
    first.worker_finished()
    navigator.bind_attempt(second)
    assert navigator.open_official_login(
        BrowserOpenRequest(VALID_URL)
    ).category is BrowserOpenCategory.OPENED

    navigator._invalidate_attempt(first)

    assert navigator.take_redirect(2, timeout_seconds=1) == VALID_URL
    second.cancel()
    second.worker_finished()

# PF-02D decisive process tests use production spawn and child-side dependencies.
# These workers are importable by spawn; no real browser is ever called.
def _pf02d_browser_worker(sender, url, *, entered, release, mode):
    import time
    from kronos.provider.adapters.kite import navigation as module
    if mode == "resist":
        import signal
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    entered.set()
    if mode in {"partial", "oversized", "malformed", "exit"}:
        if mode == "partial":
            sender.sendall(b"\x00\x00")
            release.wait(5)
        elif mode == "oversized":
            sender.sendall(b"oversized")
        elif mode == "malformed":
            sender.sendall(b"X")
        sender.close()
        return
    def synthetic_opener(value):
        assert value == VALID_URL or value.endswith("api_key=redacted")
        if mode in {"blocked", "late", "resist"}:
            release.wait(5)
        if mode == "failure":
            raise RuntimeError("synthetic-private-launch-detail")
        return mode != "declined"
    module.webbrowser.open_new_tab = synthetic_opener
    module._browser_launch_worker(sender, url)
    if mode == "lingering":
        release.wait(5)


class _PF02DSignal:
    # A killed child cannot acknowledge Condition.notify(); use a semaphore
    # signal so test teardown never waits for a dead Event waiter.
    def __init__(self, context):
        self._semaphore = context.Semaphore(0)

    def set(self):
        self._semaphore.release()

    def wait(self, timeout=None):
        if self._semaphore.acquire(timeout=timeout):
            self._semaphore.release()
            return True
        return False

    def is_set(self):
        return self.wait(0)


def _pf02d_process_fixture(monkeypatch, *, keychain=False, mode="opened", timeout=3.0):
    import functools
    import multiprocessing
    import threading
    from types import SimpleNamespace
    from kronos.provider.services.provider_authentication import ConnectionAttemptDeadline
    from kronos.provider.adapters.kite import navigation
    from kronos.configuration import apple_keychain
    context = multiprocessing.get_context("spawn")
    entered, release = _PF02DSignal(context), _PF02DSignal(context)
    records, connections = [], []
    original_process, original_pipe = context.Process, context.Pipe
    original_socket_pair = navigation._browser_socket_pair
    def process_factory(*args, **kwargs):
        process = original_process(*args, **kwargs)
        row = SimpleNamespace(process=process, exited=None, closed=False, original_close=process.close)
        records.append(row)
        return process
    original_close = multiprocessing.process.BaseProcess.close
    def observed_close(process):
        row = next((row for row in records if row.process is process), None)
        if row is not None:
            row.exited = (process.pid, process.exitcode, process.is_alive())
        original_close(process)
        if row is not None:
            row.closed = True
    monkeypatch.setattr(multiprocessing.process.BaseProcess, "close", observed_close)
    def pipe(*args, **kwargs):
        pair = original_pipe(*args, **kwargs)
        connections.extend(pair)
        return pair
    def browser_socket_pair():
        pair = original_socket_pair()
        connections.extend(pair)
        return pair
    monkeypatch.setattr(context, "Process", process_factory)
    if keychain:
        monkeypatch.setattr(context, "Pipe", pipe)
        from tests.unit.configuration.test_apple_keychain import _pf02d_keychain_worker
        monkeypatch.setattr(apple_keychain, "_security_framework_retrieval_worker", functools.partial(
            _pf02d_keychain_worker, entered=entered, release=release, mode=mode))
    else:
        monkeypatch.setattr(navigation, "_browser_socket_pair", browser_socket_pair)
        monkeypatch.setattr(navigation, "_browser_launch_worker", functools.partial(
            _pf02d_browser_worker, entered=entered, release=release, mode=mode))
    deadline = ConnectionAttemptDeadline(1, timeout_seconds=timeout)
    deadline.arm(lambda: None)
    return SimpleNamespace(context=context, entered=entered, release=release,
        records=records, connections=connections, deadline=deadline, threading=threading)


def _pf02d_assert_processes_released(case):
    import os
    assert case.records
    for row in case.records:
        assert row.closed and row.process._closed
        pid, exitcode, alive = row.exited
        assert pid is not None and exitcode is not None and alive is False
        # join has reaped the actual child, not just cleared a mock flag.
        with pytest.raises(ChildProcessError):
            os.waitpid(pid, os.WNOHANG)
    assert all(getattr(connection, "closed", getattr(connection, "_closed", False))
               for connection in case.connections)
    assert case.deadline.snapshot()["resources_pending"] is False
    print("PF02D_ACTUAL_EXIT", [row.exited for row in case.records],
          "ipc_closed", len(case.connections), "process_handles_closed", len(case.records))


def _pf02d_finish(case):
    case.release.set()
    case.deadline.cancel()
    for row in case.records:
        if not row.process._closed:
            row.process.join(1)
            if row.process.is_alive():
                row.process.kill()
                row.process.join(1)
            row.original_close()
    for connection in case.connections:
        connection.close()


@pytest.mark.parametrize("mode,category", [
    ("opened", BrowserOpenCategory.OPENED),
    ("declined", BrowserOpenCategory.DECLINED),
    ("failure", BrowserOpenCategory.FAILED),
    ("oversized", BrowserOpenCategory.FAILED),
    ("malformed", BrowserOpenCategory.FAILED),
    ("exit", BrowserOpenCategory.FAILED),
    ("lingering", BrowserOpenCategory.FAILED),
])
def test_pf02d_spawn_browser_result_requires_exit(monkeypatch, mode, category):
    case = _pf02d_process_fixture(monkeypatch, mode=mode)
    navigator = KiteLoginNavigator()
    navigator.bind_attempt(case.deadline)
    try:
        result = navigator.open_official_login(BrowserOpenRequest(VALID_URL))
        assert result.category is category
        assert case.entered.is_set()
        assert len(case.records) == 1
        _pf02d_assert_processes_released(case)
    finally:
        _pf02d_finish(case)


@pytest.mark.parametrize("mode", ["blocked", "partial", "resist"])
@pytest.mark.parametrize("terminal", ["cancel", "deadline"])
def test_pf02d_spawn_browser_stall_is_terminated(monkeypatch, mode, terminal):
    import time
    case = _pf02d_process_fixture(monkeypatch, mode=mode)
    navigator = KiteLoginNavigator()
    navigator.bind_attempt(case.deadline)
    results = []
    thread = case.threading.Thread(target=lambda: results.append(navigator.open_official_login(BrowserOpenRequest(VALID_URL))))
    try:
        thread.start()
        assert case.entered.wait(2)
        started = time.perf_counter()
        if terminal == "cancel":
            case.deadline.cancel()
        else:
            case.deadline.shorten(0.08)
        thread.join(1.5)
        elapsed = time.perf_counter() - started
        assert not thread.is_alive()
        assert results[0].category is BrowserOpenCategory.FAILED
        _pf02d_assert_processes_released(case)
        if mode == "resist":
            import signal
            assert case.records[0].exited[1] == -signal.SIGKILL
        print("PF02D_BROWSER_STOP", mode, terminal, round(elapsed, 4))
    finally:
        _pf02d_finish(case)
        thread.join(2)


def test_pf02d_browser_late_success_is_rejected(monkeypatch):
    case = _pf02d_process_fixture(monkeypatch, mode="late")
    navigator = KiteLoginNavigator()
    navigator.bind_attempt(case.deadline)
    results = []
    thread = case.threading.Thread(target=lambda: results.append(navigator.open_official_login(BrowserOpenRequest(VALID_URL))))
    try:
        thread.start()
        assert case.entered.wait(2)
        case.deadline.cancel()
        case.release.set()
        thread.join(1.5)
        assert not thread.is_alive()
        assert results[0].category is BrowserOpenCategory.FAILED
        _pf02d_assert_processes_released(case)
    finally:
        _pf02d_finish(case)
        thread.join(2)


def test_pf02d_browser_failed_cleanup_retains_actual_child_and_fence(monkeypatch):
    import multiprocessing
    case = _pf02d_process_fixture(monkeypatch, mode="blocked")
    navigator = KiteLoginNavigator()
    navigator.bind_attempt(case.deadline)
    results = []
    thread = case.threading.Thread(target=lambda: results.append(navigator.open_official_login(BrowserOpenRequest(VALID_URL))))
    try:
        thread.start()
        assert case.entered.wait(2)
        process = case.records[0].process
        terminate, kill = process.terminate, process.kill
        process.terminate = process.kill = lambda: None  # fault only; real child remains alive
        case.deadline.cancel()
        thread.join(1.5)
        assert not thread.is_alive() and process.is_alive()
        assert navigator._owner.local_cleanup_state == "FAILED"
        case.deadline.worker_finished()
        assert not case.deadline.retry_ready
        assert navigator.open_official_login(BrowserOpenRequest(VALID_URL)).category is BrowserOpenCategory.FAILED
        assert len(case.records) == 1
        process.terminate, process.kill = terminate, kill
        case.release.set()
        process.join(1)
        assert not process.is_alive()
        assert navigator._owner.local_cleanup_state == "FAILED"
        assert not case.deadline.retry_ready
    finally:
        if case.records and "terminate" in locals():
            case.records[0].process.terminate, case.records[0].process.kill = terminate, kill
        _pf02d_finish(case)
        thread.join(2)


def test_pf02d_spawn_browser_repeated_cycles_do_not_accumulate(monkeypatch):
    import multiprocessing
    import os
    from kronos.provider.services.provider_authentication import ConnectionAttemptDeadline
    case = _pf02d_process_fixture(monkeypatch)
    navigator = KiteLoginNavigator()
    before_children = {child.pid for child in multiprocessing.active_children()}
    try:
        for index in range(7):
            deadline = ConnectionAttemptDeadline(index + 1, timeout_seconds=3)
            navigator.bind_attempt(deadline)
            assert navigator.open_official_login(BrowserOpenRequest(VALID_URL)).category is BrowserOpenCategory.OPENED
            deadline.finish(); deadline.worker_finished()
            assert deadline.retry_ready
            if index == 0:
                descriptors = len(os.listdir('/dev/fd'))
        assert len(os.listdir('/dev/fd')) <= descriptors
        assert {child.pid for child in multiprocessing.active_children()} == before_children
        _pf02d_assert_processes_released(case)
    finally:
        _pf02d_finish(case)


@pytest.mark.parametrize('keychain', [False, True])
def test_pf02d_spawn_startup_keeps_custody_after_terminalization(monkeypatch, keychain):
    import multiprocessing
    import threading
    from kronos.configuration import apple_keychain
    case = _pf02d_process_fixture(monkeypatch, keychain=keychain, mode='opened')
    entered, release = threading.Event(), threading.Event()
    real_start = multiprocessing.process.BaseProcess.start
    def held_start(process):
        entered.set()
        assert release.wait(2)
        real_start(process)
    monkeypatch.setattr(multiprocessing.process.BaseProcess, 'start', held_start)
    results = []
    navigator = KiteLoginNavigator(); navigator.bind_attempt(case.deadline)
    def run():
        try:
            if keychain:
                from tests.unit.configuration.test_apple_keychain import _pf02d_request
                results.append(apple_keychain.run_security_framework_subprocess(_pf02d_request(), deadline=case.deadline))
            else:
                results.append(navigator.open_official_login(BrowserOpenRequest(VALID_URL)).category)
        except TimeoutError:
            results.append('TIMED_OUT')
    thread = threading.Thread(target=run)
    try:
        thread.start()
        assert entered.wait(1)
        case.deadline.cancel()
        assert thread.is_alive() and case.records[0].process.pid is None
        assert case.deadline.snapshot()['resources_pending']
        case.deadline.worker_finished()
        assert not case.deadline.retry_ready
        release.set(); thread.join(2)
        assert not thread.is_alive()
        assert results == (['TIMED_OUT'] if keychain else [BrowserOpenCategory.FAILED])
        _pf02d_assert_processes_released(case)
        assert case.deadline.retry_ready
    finally:
        release.set(); thread.join(2)
        _pf02d_finish(case)


@pytest.mark.parametrize('keychain', [False, True])
def test_pf02d_ipc_close_failure_is_retained_after_actual_child_exit(monkeypatch, keychain):
    from kronos.configuration import apple_keychain
    from kronos.provider.adapters.kite import navigation
    case = _pf02d_process_fixture(monkeypatch, keychain=keychain, mode='blocked')
    navigator = KiteLoginNavigator(); navigator.bind_attempt(case.deadline)
    results = []
    def run():
        try:
            if keychain:
                from tests.unit.configuration.test_apple_keychain import _pf02d_request
                results.append(apple_keychain.run_security_framework_subprocess(_pf02d_request(), deadline=case.deadline))
            else:
                results.append(navigator.open_official_login(BrowserOpenRequest(VALID_URL)).category)
        except apple_keychain.AppleKeychainCredentialError:
            results.append('FAILED')
    thread = case.threading.Thread(target=run)
    owner = None
    try:
        thread.start()
        assert case.entered.wait(2)
        receiver = case.connections[0]
        original_close = receiver.close
        if keychain:
            def fail_close():
                raise OSError('synthetic close fault')
            receiver.close = fail_close
        else:
            original_owned_close = navigation._close_browser_connection
            def fail_close(connection):
                if connection is receiver:
                    raise OSError('synthetic close fault')
                original_owned_close(connection)
            monkeypatch.setattr(navigation, '_close_browser_connection', fail_close)
        case.release.set(); thread.join(2)
        assert not thread.is_alive()
        assert results == (['FAILED'] if keychain else [BrowserOpenCategory.FAILED])
        row = case.records[0]
        assert row.closed and row.exited[1:] == (0, False)
        assert not getattr(receiver, "closed", getattr(receiver, "_closed", False))
        owner = apple_keychain._retrieval_owners[0] if keychain else navigator._owner
        assert owner.local_cleanup_state == 'FAILED'
        case.deadline.cancel(); case.deadline.worker_finished()
        assert not case.deadline.retry_ready
        if keychain:
            receiver.close = original_close
        receiver.close()
        assert owner.local_cleanup_state == 'FAILED' and not case.deadline.retry_ready
    finally:
        case.release.set(); thread.join(2)
        if keychain and 'original_close' in locals():
            receiver.close = original_close
        _pf02d_finish(case)
        if owner in apple_keychain._retrieval_owners:
            apple_keychain._retrieval_owners.remove(owner)


@pytest.mark.parametrize('keychain', [False, True])
def test_pf02d_start_exception_without_child_handle_is_not_exit_proof(monkeypatch, keychain):
    import multiprocessing
    from kronos.configuration import apple_keychain
    case = _pf02d_process_fixture(monkeypatch, keychain=keychain)
    navigator = KiteLoginNavigator(); navigator.bind_attempt(case.deadline)
    def fail_start(process):
        raise OSError('synthetic startup uncertainty')
    monkeypatch.setattr(multiprocessing.process.BaseProcess, 'start', fail_start)
    owner = None
    try:
        if keychain:
            from tests.unit.configuration.test_apple_keychain import _pf02d_request
            with pytest.raises(apple_keychain.AppleKeychainCredentialError):
                apple_keychain.run_security_framework_subprocess(_pf02d_request(), deadline=case.deadline)
            owner = apple_keychain._retrieval_owners[0]
        else:
            assert navigator.open_official_login(BrowserOpenRequest(VALID_URL)).category is BrowserOpenCategory.FAILED
            owner = navigator._owner
        assert owner.start_attempted and not owner.start_returned
        assert owner.local_cleanup_state == 'FAILED'
        assert case.records[0].exited == (None, None, False)
        assert case.records[0].closed and all(
            getattr(c, "closed", getattr(c, "_closed", False)) for c in case.connections)
        case.deadline.cancel(); case.deadline.worker_finished()
        assert not case.deadline.retry_ready
    finally:
        _pf02d_finish(case)
        if owner in apple_keychain._retrieval_owners:
            apple_keychain._retrieval_owners.remove(owner)


def test_pf02d_browser_launch_material_is_absent_from_actual_spawn_argv(monkeypatch, capsys):
    import multiprocessing.util
    case = _pf02d_process_fixture(monkeypatch, mode='blocked')
    commands = []
    real_spawn = multiprocessing.util.spawnv_passfds
    def observed_spawn(path, arguments, passfds):
        commands.append(tuple(arguments))
        return real_spawn(path, arguments, passfds)
    monkeypatch.setattr(multiprocessing.util, 'spawnv_passfds', observed_spawn)
    navigator = KiteLoginNavigator(); navigator.bind_attempt(case.deadline)
    results = []
    thread = case.threading.Thread(target=lambda: results.append(navigator.open_official_login(BrowserOpenRequest(VALID_URL))))
    try:
        thread.start()
        assert case.entered.wait(2)
        assert case.records[0].process.is_alive()
        assert len(commands) == 1
        command = repr(commands[0])
        assert 'spawn_main' in command and 'api_key' not in command and 'ABC123' not in command
        case.deadline.cancel(); thread.join(2)
        assert not thread.is_alive() and results[0].category is BrowserOpenCategory.FAILED
        assert 'ABC123' not in capsys.readouterr().out
        _pf02d_assert_processes_released(case)
    finally:
        case.release.set(); thread.join(2)
        _pf02d_finish(case)
