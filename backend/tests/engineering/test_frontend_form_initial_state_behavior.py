"""Real, browser-driven proof (properties D/E/C/H) that the fix
`frontend_form_initial_state_preflight.py`'s own findings recommend --
destructure `initialData`, seed `useState(initialData || {})`, resync via
`useEffect(() => setFormData(initialData || {}), [initialData])` -- is
behaviorally sound, not just structurally present.

Runs `fixtures/form_initial_state_rehydration.mjs` as a real subprocess
(real Chromium via `@playwright/test`, the same real dependency and the
same subprocess-invocation convention
`test_golden_browser_journey_capability_coverage.py`'s own `_run_journey`
already established) -- never a static substring check. The static
"is `initialData` structurally consumed" checks (properties A/B/F/G) live
in `test_frontend_form_initial_state_preflight.py`, pure-Python and fast;
this file is the one place in this suite exercising real React runtime
semantics, kept separate because it is orders of magnitude slower.
"""

from __future__ import annotations

import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[3]
FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "form_initial_state_rehydration.mjs"


def test_the_recommended_fix_rehydrates_after_a_real_async_update_and_never_clobbers_a_real_user_edit() -> None:
    """Properties D (real async rehydration, not just a correct first
    render) and E (a real, unrelated parent re-render never clobbers a
    real user's own typed edit) -- both proven in real Chromium against
    the exact React source this module's own docstring transcribes
    unparaphrased from `_form_initial_data_ignored_findings`'s own finding
    `detail` text. Run over two structurally unrelated domains inside the
    one subprocess (student name/email, task title/due_date) -- properties
    C/H, the same no-hardcoding proof this pipeline's other cross-domain
    tests already require."""
    result = subprocess.run(
        ["node", str(FIXTURE)], cwd=REPO, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "all assertions passed" in result.stdout
