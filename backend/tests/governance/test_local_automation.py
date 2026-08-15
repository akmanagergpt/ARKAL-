"""Controls for the local Codex/Qwen single-writer automation wrapper."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = ROOT / "scripts" / "automation" / "arkali_automation.py"
SPEC = importlib.util.spec_from_file_location("arkali_automation", MODULE)
assert SPEC and SPEC.loader
automation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = automation
SPEC.loader.exec_module(automation)


def test_external_and_credential_commands_are_refused() -> None:
    for command in (
        ["git", "push"], ["gh", "pr", "create"], ["curl", "https://example.test"],
        ["tool", "--api-key", "secret"], ["deploy", "production"],
    ):
        with pytest.raises(automation.AutomationError):
            automation.reject_forbidden(command)


def test_qwen_failure_is_advisory_not_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        automation, "run",
        lambda *_args, **_kwargs: automation.CommandResult(("ollama",), 1, "", "offline"),
    )
    advice = automation.qwen_advice("classify", ["ollama", "run", "qwen2.5-coder:14b"], 1)
    assert "NOT_CONFIGURED" in advice
    assert "COMPLETE" not in advice


def test_human_gate_stops_before_qwen_or_codex(tmp_path: pathlib.Path) -> None:
    packet = automation.Packet("gate", "work", (), (), human_gate=True)
    state = automation.execute_packet(
        packet, qwen_command=["ollama"], codex_command=["codex"], retries=0,
        backoff_seconds=0, qwen_timeout=1, journal=tmp_path / "journal",
    )
    assert state == "HUMAN_GATE_REQUIRED"


def test_single_writer_lock_refuses_a_second_writer(tmp_path: pathlib.Path) -> None:
    lock_path = tmp_path / "writer.lock"
    with automation.SingleWriter(lock_path):
        with pytest.raises(automation.AutomationError, match="another repository writer"):
            with automation.SingleWriter(lock_path):
                pass


def test_packet_commands_are_argv_not_shell_text() -> None:
    packet = automation.Packet.from_dict(
        {"id": "p1", "prompt": "bounded work", "tests": [["python", "-V"]],
         "full_regressions": [], "gate": None}
    )
    assert packet.tests == (("python", "-V"),)
    with pytest.raises(automation.AutomationError):
        automation.Packet.from_dict(
            {"id": "p2", "prompt": "work", "tests": ["python -V"],
             "full_regressions": []}
        )


def test_safe_environment_keeps_runtime_but_not_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", "/home/worker")
    monkeypatch.setenv("VIRTUAL_ENV", "/home/worker/.venv")
    monkeypatch.setenv("PYTHONPATH", "/repo/backend")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    environment = automation._safe_environment()
    assert environment["HOME"] == "/home/worker"
    assert environment["VIRTUAL_ENV"] == "/home/worker/.venv"
    assert environment["PYTHONPATH"] == "/repo/backend"
    assert "ANTHROPIC_API_KEY" not in environment


def test_local_paths_are_repository_relative_and_protected() -> None:
    assert automation._local_path("backend/tests/test_safe.py") == "backend/tests/test_safe.py"
    for path in ("../outside", "/etc/passwd", ".git/config", ".env", "config/.env.local"):
        with pytest.raises(automation.AutomationError):
            automation._local_path(path)


def test_quota_failure_uses_bounded_local_writer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path,
) -> None:
    calls: list[str] = []

    def fake_run(argv: object, **_kwargs: object) -> automation.CommandResult:
        rendered = tuple(argv)  # type: ignore[arg-type]
        if rendered[0] == "codex":
            return automation.CommandResult(rendered, 1, "usage limit", "")
        if rendered[0] == "aider":
            calls.extend(rendered)
            return automation.CommandResult(rendered, 0, "done", "")
        return automation.CommandResult(rendered, 0, "", "")

    monkeypatch.setattr(automation, "run", fake_run)
    monkeypatch.setattr(automation, "qwen_advice", lambda *_args: "{}")
    packet = automation.Packet(
        "p", "bounded", (), (), local_editable_paths=("docs/contracts/repair.md",)
    )
    state = automation.execute_packet(
        packet, qwen_command=["advisor"], codex_command=["codex"], retries=0,
        backoff_seconds=0, qwen_timeout=1, journal=tmp_path / "journal",
        local_writer_command=["aider"],
    )
    assert state == "COMPLETE"
    assert str(automation.REPO / "docs/contracts/repair.md") in calls
