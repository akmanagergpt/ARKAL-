"""ARK-REQ-0337: known data-loss risk blocks release.

Owner: `acceptance.engine` (Protected Core).

Split from `checker.py` so that module's own touched-context budget (3) is not
spent reaching `kernel.persistence` - the same ADR-0008 decomposition
`external_result_check.py` already established for a different check.

RE-DERIVED, NEVER CLAIMED. The shipping migration chain is analysed fresh on
every call through `kernel.persistence.migration_impact` - Phase 20's own
impact analyser, the same one `lifecycle.recovery`'s Apply-time Impact step
drives. A phase report cannot assert this check away; C6 already applies the
identical discipline to discharge claims.
"""

from __future__ import annotations

import pathlib

from arkali.kernel.persistence.migration_impact import analyze_chain
from arkali.kernel.persistence.migrations import VERSIONS_DIR

#: `VERSIONS_DIR` is declared relative to the backend root (`migrations.py`'s
#: own docstring), but every `acceptance.engine` caller - `PhaseGateChecker`
#: included - is constructed with the outer *repository* root. Without this,
#: the check silently resolves to a path that never exists and reports a
#: vacuous "no migrations directory yet" PASS instead of analysing anything -
#: caught by running the real `PhaseGateChecker` end to end, not by a unit
#: test that (like this module's own first draft) also assumed backend-root.
BACKEND_RELPATH = "backend"


def _evaluate_migration_data_loss_risk(repo_root: pathlib.Path) -> tuple[bool, str, str]:
    """(passed, summary, detail) for the DATA_LOSS_RISK check.

    `passed=True` with `NOT_APPLICABLE`-shaped prose when no migrations
    directory exists yet is legitimate: a repository state predating any
    migration carries no risk to detect, the same reasoning `check_human_gate`
    applies to a phase carrying no gate.
    """
    versions = repo_root / BACKEND_RELPATH / VERSIONS_DIR
    if not versions.is_dir():
        return True, "no migrations directory exists yet", ""
    reports = analyze_chain(versions)
    flagged = [r.render() for r in reports if r.data_loss_risk]
    if flagged:
        return (
            False,
            "known data-loss risk in the shipping migration chain blocks release",
            f"revisions={flagged}",
        )
    return (
        True,
        f"{len(reports)} declared revision(s) carry no known data-loss risk",
        "",
    )
