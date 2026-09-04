from __future__ import annotations

import pathlib
import sys
import time

import pytest

from arkali.engineering.candidate import preview as preview_module
from arkali.engineering.candidate.preview import PreviewCancelled, PreviewRefused, _run


class _NeverExits:
    def poll(self):  # noqa: ANN201
        return None


def test_run_honours_a_real_cancel_request_well_before_the_process_would_finish_on_its_own() -> None:
    """The whole point of cooperative cancellation: a "Durdur" during a slow
    install/build must not wait for that subprocess to finish on its own."""
    started = time.monotonic()
    with pytest.raises(PreviewCancelled):
        _run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=pathlib.Path.cwd(), should_cancel=lambda: True,
        )
    elapsed = time.monotonic() - started
    # Bounded by `_CANCEL_POLL_SECONDS`, not by the 30s sleep it interrupted.
    assert elapsed < 10.0


def test_run_leaves_no_process_behind_after_a_cancel() -> None:
    """`_run` calls the real, already-proven `stop_process` on cancel -- this
    is a regression guard against that call being dropped, not a re-test of
    `stop_process` itself (covered in `test_candidate_runtime_process.py`)."""
    process_holder: list[object] = []
    real_popen = preview_module.subprocess.Popen

    def _capturing_popen(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        process = real_popen(*args, **kwargs)
        process_holder.append(process)
        return process

    original = preview_module.subprocess.Popen
    preview_module.subprocess.Popen = _capturing_popen  # type: ignore[assignment]
    try:
        with pytest.raises(PreviewCancelled):
            _run(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                cwd=pathlib.Path.cwd(), should_cancel=lambda: True,
            )
    finally:
        preview_module.subprocess.Popen = original  # type: ignore[assignment]

    # The captured list also includes `stop_process`'s own `taskkill` child
    # on Windows (`subprocess.run` shares the same, singleton `Popen`) --
    # the real assertion is about the FIRST process, the one `_run` started
    # and cancelled.
    assert len(process_holder) >= 1
    process = process_holder[0]
    process.wait(timeout=5)  # type: ignore[attr-defined]
    assert process.poll() is not None  # type: ignore[attr-defined]


def test_run_never_checks_cancellation_when_none_is_given() -> None:
    """A caller with no cancellation concept (the plain CLI) gets the exact
    old, unconditional behaviour -- nothing here is silently mandatory."""
    output = _run([sys.executable, "-c", "print('ok')"], cwd=pathlib.Path.cwd())
    assert "ok" in output


def test_run_still_times_out_on_its_own_bound_even_with_should_cancel_given() -> None:
    with pytest.raises(RuntimeError, match="timed out"):
        _run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=pathlib.Path.cwd(), should_cancel=lambda: False, timeout_seconds=1.0,
        )


def test_require_accepted_refuses_a_stage_failed_candidate(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        preview_module.CandidateLedger, "latest",
        lambda self, candidate_id: {"state": "STAGE_FAILED"},  # noqa: ARG005
    )
    with pytest.raises(PreviewRefused, match="STAGE_FAILED"):
        preview_module._require_accepted("golden-work-130")


def test_require_accepted_refuses_an_unknown_candidate(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        preview_module.CandidateLedger, "latest", lambda self, candidate_id: None,  # noqa: ARG005
    )
    with pytest.raises(PreviewRefused, match="None"):
        preview_module._require_accepted("golden-work-unknown")


def test_require_accepted_allows_a_real_accepted_candidate(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        preview_module.CandidateLedger, "latest",
        lambda self, candidate_id: {"state": "ACCEPTED"},  # noqa: ARG005
    )
    preview_module._require_accepted("golden-work-129")  # does not raise


# -- build cache: real filesystem operations over isolated tmp_path fixtures,
# -- never the real candidate source under var/factory/candidates/ --------


def _write_fake_candidate(root: pathlib.Path, *, requirement: str = "flask==2.3.2") -> None:
    (root / "backend").mkdir(parents=True)
    (root / "backend" / "requirements.txt").write_text(requirement, encoding="utf-8")
    (root / "backend" / "app.py").write_text("app = object()", encoding="utf-8")
    (root / "frontend").mkdir()
    (root / "frontend" / "package.json").write_text('{"name": "x"}', encoding="utf-8")


def test_cache_key_is_deterministic_for_identical_content(tmp_path: pathlib.Path) -> None:
    one = tmp_path / "one"
    two = tmp_path / "two"
    _write_fake_candidate(one)
    _write_fake_candidate(two)

    assert preview_module._cache_key_for(one) == preview_module._cache_key_for(two)


def test_cache_key_changes_when_source_content_changes(tmp_path: pathlib.Path) -> None:
    """The deterministic-miss requirement: a real content difference must
    produce a real, different key -- proven against an isolated fixture,
    never the real historical candidate source."""
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_fake_candidate(before)
    _write_fake_candidate(after)
    (after / "backend" / "app.py").write_text("app = object()  # changed", encoding="utf-8")

    assert preview_module._cache_key_for(before) != preview_module._cache_key_for(after)


def test_cache_key_changes_when_the_requirements_file_changes(tmp_path: pathlib.Path) -> None:
    """A dependency-manifest change is a build-input change, not merely a
    source-content change -- both must miss."""
    one = tmp_path / "one"
    two = tmp_path / "two"
    _write_fake_candidate(one, requirement="flask==2.3.2")
    _write_fake_candidate(two, requirement="flask==3.0.0")

    assert preview_module._cache_key_for(one) != preview_module._cache_key_for(two)


def test_cache_key_changes_with_the_schema_version(monkeypatch, tmp_path: pathlib.Path) -> None:  # noqa: ANN001
    """A build-recipe change this module makes, independent of any candidate's
    own content, must still invalidate every existing entry."""
    source = tmp_path / "source"
    _write_fake_candidate(source)

    monkeypatch.setattr(preview_module, "_CACHE_SCHEMA_VERSION", "1")
    key_v1 = preview_module._cache_key_for(source)
    monkeypatch.setattr(preview_module, "_CACHE_SCHEMA_VERSION", "2")
    key_v2 = preview_module._cache_key_for(source)

    assert key_v1 != key_v2


def _populate_fake_build_outputs(workspace_root: pathlib.Path, candidate: pathlib.Path) -> None:
    (workspace_root / ".venv" / "Scripts").mkdir(parents=True)
    (workspace_root / ".venv" / "Scripts" / "python.exe").write_bytes(b"fake-interpreter")
    frontend = candidate / "frontend"
    (frontend / "node_modules" / "some-package").mkdir(parents=True)
    (frontend / "node_modules" / "some-package" / "index.js").write_text("x", encoding="utf-8")
    (frontend / "build").mkdir()
    (frontend / "build" / "index.html").write_text("<html></html>", encoding="utf-8")


def test_populate_cache_cancelled_before_any_copy_leaves_no_temp_dir_and_no_entry(
    tmp_path: pathlib.Path, monkeypatch,  # noqa: ANN001
) -> None:
    monkeypatch.setattr(preview_module, "_BUILD_CACHE", tmp_path / "cache-root")
    cache_dir = tmp_path / "cache-root" / "key-a"
    workspace = tmp_path / "workspace"
    candidate = workspace / "snapshot"
    candidate.mkdir(parents=True)
    _populate_fake_build_outputs(workspace, candidate)

    preview_module._populate_cache(cache_dir, workspace, candidate, should_cancel=lambda: True)

    assert not cache_dir.exists()
    assert not list((tmp_path / "cache-root").glob(".tmp-*"))


def test_populate_cache_cancelled_between_copy_steps_leaves_no_partial_entry(
    tmp_path: pathlib.Path, monkeypatch,  # noqa: ANN001
) -> None:
    """The real bound cooperative cancellation gives: cancelling mid-way
    through the three real copies still never promotes a half-built
    entry -- exactly the "Durdur while runtime is up and population is
    still running" scenario this turn is required to prove."""
    monkeypatch.setattr(preview_module, "_BUILD_CACHE", tmp_path / "cache-root")
    cache_dir = tmp_path / "cache-root" / "key-a"
    workspace = tmp_path / "workspace"
    candidate = workspace / "snapshot"
    candidate.mkdir(parents=True)
    _populate_fake_build_outputs(workspace, candidate)

    calls = {"n": 0}

    def should_cancel() -> bool:
        calls["n"] += 1
        return calls["n"] >= 2  # false the first check (before venv copy), true after

    preview_module._populate_cache(cache_dir, workspace, candidate, should_cancel=should_cancel)

    assert not cache_dir.exists()
    assert not list((tmp_path / "cache-root").glob(".tmp-*"))
    assert calls["n"] >= 2  # the cooperative check really did run more than once


def test_populate_cache_with_should_cancel_always_false_completes_normally(
    tmp_path: pathlib.Path, monkeypatch,  # noqa: ANN001
) -> None:
    """A caller with real cancellation support (the worker) whose user
    never actually cancels must still get a real, complete cache entry --
    the cooperative checks must never themselves cause a false cancel."""
    monkeypatch.setattr(preview_module, "_BUILD_CACHE", tmp_path / "cache-root")
    cache_dir = tmp_path / "cache-root" / "key-a"
    workspace = tmp_path / "workspace"
    candidate = workspace / "snapshot"
    candidate.mkdir(parents=True)
    _populate_fake_build_outputs(workspace, candidate)

    preview_module._populate_cache(cache_dir, workspace, candidate, should_cancel=lambda: False)

    assert cache_dir.is_dir()
    assert (cache_dir / preview_module._CACHE_VENV_DIR / "Scripts" / "python.exe").read_bytes() == b"fake-interpreter"


def test_populate_cache_runs_correctly_on_a_background_thread(
    tmp_path: pathlib.Path, monkeypatch,  # noqa: ANN001
) -> None:
    """`run_preview` starts this on a `threading.Thread` -- proves the
    function itself has no hidden main-thread-only assumption."""
    import threading

    monkeypatch.setattr(preview_module, "_BUILD_CACHE", tmp_path / "cache-root")
    cache_dir = tmp_path / "cache-root" / "key-a"
    workspace = tmp_path / "workspace"
    candidate = workspace / "snapshot"
    candidate.mkdir(parents=True)
    _populate_fake_build_outputs(workspace, candidate)

    thread = threading.Thread(
        target=preview_module._populate_cache,
        args=(cache_dir, workspace, candidate), kwargs={"should_cancel": None}, daemon=True,
    )
    thread.start()
    thread.join(timeout=10.0)

    assert not thread.is_alive()
    assert cache_dir.is_dir()


def test_restore_from_cache_is_false_for_a_key_that_was_never_populated(tmp_path: pathlib.Path) -> None:
    cache_dir = tmp_path / "cache" / "sha256_does-not-exist"
    workspace_root = tmp_path / "workspace"
    candidate = tmp_path / "workspace" / "snapshot"
    candidate.mkdir(parents=True)

    assert preview_module._restore_from_cache(cache_dir, workspace_root, candidate) is False
    assert not (workspace_root / ".venv").exists()


def test_populate_then_restore_round_trips_real_bytes(tmp_path: pathlib.Path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(preview_module, "_BUILD_CACHE", tmp_path / "cache-root")
    cache_dir = tmp_path / "cache-root" / "key-a"

    build_workspace = tmp_path / "build-workspace"
    build_candidate = build_workspace / "snapshot"
    build_candidate.mkdir(parents=True)
    _populate_fake_build_outputs(build_workspace, build_candidate)

    preview_module._populate_cache(cache_dir, build_workspace, build_candidate)

    assert cache_dir.is_dir()
    assert not list((tmp_path / "cache-root").glob(".tmp-*"))  # no leftover temp directory

    restore_workspace = tmp_path / "restore-workspace"
    restore_candidate = restore_workspace / "snapshot"
    restore_candidate.mkdir(parents=True)

    hit = preview_module._restore_from_cache(cache_dir, restore_workspace, restore_candidate)

    assert hit is True
    assert (restore_workspace / ".venv" / "Scripts" / "python.exe").read_bytes() == b"fake-interpreter"
    assert (restore_candidate / "frontend" / "build" / "index.html").read_text(encoding="utf-8") == "<html></html>"
    assert (restore_candidate / "frontend" / "node_modules" / "some-package" / "index.js").is_file()


def test_populate_cache_discards_its_own_temp_copy_when_another_populate_already_won(
    tmp_path: pathlib.Path, monkeypatch,  # noqa: ANN001
) -> None:
    """Two previews racing on the identical content identity must not
    error -- content-addressed entries are interchangeable by construction,
    so the loser's own temp directory is simply discarded."""
    monkeypatch.setattr(preview_module, "_BUILD_CACHE", tmp_path / "cache-root")
    cache_dir = tmp_path / "cache-root" / "key-a"
    cache_dir.mkdir(parents=True)
    (cache_dir / "already-here.txt").write_text("first writer won", encoding="utf-8")

    workspace = tmp_path / "workspace"
    candidate = workspace / "snapshot"
    candidate.mkdir(parents=True)
    _populate_fake_build_outputs(workspace, candidate)

    preview_module._populate_cache(cache_dir, workspace, candidate)  # must not raise

    # The pre-existing (first writer's) content is untouched.
    assert (cache_dir / "already-here.txt").read_text(encoding="utf-8") == "first writer won"
    assert not (cache_dir / preview_module._CACHE_VENV_DIR).exists()
    assert not list(cache_dir.parent.glob(".tmp-*"))  # this writer's own temp dir was cleaned up
