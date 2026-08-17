"""ARK-REQ-0337 evidence for `migration_release_check.py`.

Owner: `acceptance.engine`.

`PhaseGateChecker` and every other `acceptance.engine` caller is constructed
with the outer *repository* root, never the backend root `migrations.py`'s
own `VERSIONS_DIR` is relative to. The check's first draft resolved the path
against the repo root directly, so it silently found no directory and
reported a vacuous "no migrations directory yet" PASS - `passed is True` for
a reason unrelated to the property it claims, the F-0017 shape. These tests
pin the fix: called with the real repo root, the check must report a real
analysed-revision count, and a synthetic repo layout with a destructive
revision must actually be found and block.
"""

from __future__ import annotations

import pathlib

from arkali.acceptance.migration_release_check import (
    BACKEND_RELPATH,
    _evaluate_migration_data_loss_risk,
)
from arkali.kernel.persistence.migrations import VERSIONS_DIR, declared_migrations

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"


def test_called_with_the_real_repo_root_it_finds_the_real_chain() -> None:
    """Reproduces the exact call shape `PhaseGateChecker(REPO)` uses."""
    chain = declared_migrations(BACKEND)
    passed, summary, detail = _evaluate_migration_data_loss_risk(REPO)
    assert passed is True
    assert "no migrations directory" not in summary
    assert str(len(chain)) in summary
    assert detail == ""


def test_called_with_the_backend_root_directly_is_refused_as_a_negative_control(
    tmp_path: pathlib.Path,
) -> None:
    """A caller that already holds the backend root (not the repo root) must
    not silently pass either: `repo_root / BACKEND_RELPATH / VERSIONS_DIR`
    resolves one level too deep and finds nothing, correctly reported."""
    passed, summary, _detail = _evaluate_migration_data_loss_risk(BACKEND)
    assert passed is True
    assert "no migrations directory" in summary


def test_a_flagged_synthetic_chain_is_found_and_blocks(
    tmp_path: pathlib.Path,
) -> None:
    versions = tmp_path / BACKEND_RELPATH / VERSIONS_DIR
    versions.mkdir(parents=True)
    (versions / "0001_destructive.py").write_text(
        'revision = "0001_destructive"\ndown_revision = None\n'
        'direction = "FORWARD"\n'
        "def upgrade() -> None:\n    op.drop_table('widget')\n",
        encoding="utf-8",
    )
    passed, summary, detail = _evaluate_migration_data_loss_risk(tmp_path)
    assert passed is False
    assert "blocks release" in summary
    assert "drop_table" in detail
