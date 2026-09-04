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
