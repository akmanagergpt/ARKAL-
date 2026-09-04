from __future__ import annotations

import socket
import subprocess

import pytest

from arkali.engineering.candidate import runtime_process


class _FakeResponse:
    def close(self) -> None:
        return None


class _RunningProcess:
    """Never exits on its own -- exercises the real HTTP polling path."""

    pid = 1234

    def poll(self):  # noqa: ANN201
        return None


class _DeadProcess:
    """Already exited before anyone waited on it -- the real early-exit path."""

    pid = 5678
    returncode = 1

    def poll(self):  # noqa: ANN201
        return self.returncode


def test_wait_http_returns_once_the_url_answers(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(runtime_process.urllib.request, "urlopen", lambda *a, **k: _FakeResponse())
    runtime_process.wait_http("http://127.0.0.1:1/health", _RunningProcess())


def test_wait_http_raises_when_the_owned_process_exits_early() -> None:
    with pytest.raises(RuntimeError, match="exited early"):
        runtime_process.wait_http("http://127.0.0.1:1/health", _DeadProcess(), timeout=1.0)


def test_wait_http_times_out_rather_than_hanging_forever(monkeypatch) -> None:  # noqa: ANN001
    def _always_refuses(*_args, **_kwargs):  # noqa: ANN202
        raise OSError("refused")

    monkeypatch.setattr(runtime_process.urllib.request, "urlopen", _always_refuses)
    with pytest.raises(RuntimeError, match="timed out"):
        runtime_process.wait_http("http://127.0.0.1:1/health", _RunningProcess(), timeout=0.3)


def test_wait_tcp_returns_once_a_plain_tcp_listener_accepts_a_connection() -> None:
    """The whole reason `wait_tcp` exists: a real listener needs no HTTP
    route at all to count as ready, unlike `wait_http`."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        port = listener.getsockname()[1]
        runtime_process.wait_tcp(port, _RunningProcess(), timeout=2.0)
    finally:
        listener.close()


def test_wait_tcp_raises_when_the_owned_process_exits_early() -> None:
    with pytest.raises(RuntimeError, match="exited early"):
        runtime_process.wait_tcp(1, _DeadProcess(), timeout=1.0)


def test_wait_tcp_times_out_rather_than_hanging_forever() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    with pytest.raises(RuntimeError, match="timed out"):
        runtime_process.wait_tcp(port, _RunningProcess(), timeout=0.3)


def test_stop_process_is_a_no_op_for_none() -> None:
    runtime_process.stop_process(None)


def test_stop_process_is_a_no_op_for_an_already_exited_process() -> None:
    runtime_process.stop_process(_DeadProcess())


def test_stop_process_scopes_windows_termination_to_the_owned_pid(monkeypatch) -> None:  # noqa: ANN001
    commands: list[list[str]] = []
    monkeypatch.setattr(runtime_process, "os", type("Os", (), {"name": "nt"}))
    monkeypatch.setattr(
        runtime_process.subprocess, "run",
        lambda command, **kwargs: commands.append(command),
    )

    class _Process:
        pid = 9999

        def poll(self):  # noqa: ANN201
            return None

        def wait(self, timeout: float) -> int:
            assert timeout == 10
            return 0

    runtime_process.stop_process(_Process())
    assert commands == [["taskkill", "/PID", "9999", "/T", "/F"]]


def test_stop_process_terminates_on_posix(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(runtime_process, "os", type("Os", (), {"name": "posix"}))

    class _Process:
        pid = 2222
        terminated = False

        def poll(self):  # noqa: ANN201
            return None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: float) -> int:
            assert timeout == 10
            return 0

    process = _Process()
    runtime_process.stop_process(process)
    assert process.terminated


def test_port_is_free_reports_a_real_bound_port_as_taken() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        port = listener.getsockname()[1]
        assert runtime_process.port_is_free(port) is False
    finally:
        listener.close()


def test_port_accepts_connections_is_true_for_a_real_listener() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        port = listener.getsockname()[1]
        assert runtime_process.port_accepts_connections(port) is True
    finally:
        listener.close()


def test_port_accepts_connections_is_false_when_nothing_listens() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    assert runtime_process.port_accepts_connections(port) is False
