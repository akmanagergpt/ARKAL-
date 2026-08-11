"""Negative controls for the manifest's own commit references (F-0047).

The manifest names the commit it was generated at in three places: the `head:`
claim, the identity section, and one `HEAD at generation` marker on a row of the
accepted-commit ledger. Only the first was ever compared with anything.

The marker was COUNTED but not BOUND, while the integrity section asserted that
"a derived control" also checked it "names that same commit" - so the manifest
overstated its own validator, and a later refresh left the marker on an older
row with nothing noticing. The identity section carried a commit twelve commits
stale for the same reason, and the ledger rows had been written out of order.

Each control mutates an IN-MEMORY copy of the manifest text. No repository state
is modified, and every subject is derived from the document and from git.

ADR-0008 decomposition: `test_handoff_drift.py` reached its 400 logical-line
budget. This is F-0047's second half - self-reference rather than architecture
metrics - and it is a real seam, not a slice taken to fit. No GATE 8 exception
was requested.
"""

from __future__ import annotations

import subprocess
import types

import pytest

from tests.governance.handoff_harness import (
    HANDOFF,
    REPO,
    drift_names,
    load_validator,
    replace_once,
)


@pytest.fixture(scope="module")
def validator() -> types.ModuleType:
    return load_validator()


@pytest.fixture(scope="module")
def handoff_text() -> str:
    return HANDOFF.read_text(encoding="utf-8")


def first_parent_commit() -> str:
    """The root commit: guaranteed to exist and guaranteed not to be the head."""
    return subprocess.run(
        ["git", "rev-list", "--max-parents=0", "HEAD"],
        cwd=REPO, capture_output=True, text=True,
    ).stdout.strip().splitlines()[0]


class TestManifestSelfReferenceIsBound:
    """The manifest's own commit references must all name one commit."""

    def test_a_marker_on_the_wrong_ledger_row_is_detected(
        self, validator: types.ModuleType, handoff_text: str
    ) -> None:
        recorded = validator.parse_claims(handoff_text)["head"]
        marker = next(
            line for line in handoff_text.splitlines()
            if validator._HEAD_MARKER in line
        )
        elsewhere = next(
            line for line in handoff_text.splitlines()
            if (cited := validator._LEDGER_COMMIT.findall(line))
            and not recorded.startswith(cited[0])
        )
        moved = replace_once(
            handoff_text, marker, marker.replace(f" ← {validator._HEAD_MARKER}", "")
        )
        assert validator._HEAD_MARKER not in moved, "the marker was not removed"
        moved = replace_once(
            moved,
            elsewhere,
            elsewhere.rstrip().removesuffix("|") + f"← {validator._HEAD_MARKER} |",
        )
        assert moved.count(validator._HEAD_MARKER) == 1, "the mutation is malformed"
        assert "the HEAD-at-generation marker names the recorded head" in drift_names(
            validator, moved
        )

    def test_a_ledger_written_out_of_order_is_detected(
        self, validator: types.ModuleType, handoff_text: str
    ) -> None:
        assert len(validator._LEDGER_ROW.findall(handoff_text)) > 2, (
            "the ledger is too short to reorder"
        )
        lines = handoff_text.splitlines()
        rows = [i for i, line in enumerate(lines)
                if validator._LEDGER_ROW.findall(line)]
        first, last = rows[0], rows[-1]
        swapped = "\n".join(
            lines[:first] + [lines[last]] + lines[first:last] + lines[last + 1:]
        )
        numbers = [int(n) for n, _ in validator._LEDGER_ROW.findall(swapped)]
        assert numbers != sorted(numbers), "the mutation did not disorder the ledger"
        assert "the accepted-commit history is in ledger order" in drift_names(
            validator, swapped
        )

    def test_a_stale_commit_in_the_identity_section_is_detected(
        self, validator: types.ModuleType, handoff_text: str
    ) -> None:
        recorded = validator.parse_claims(handoff_text)["head"]
        baseline = first_parent_commit()
        assert not recorded.startswith(baseline[:7]), (
            "the mutation must name a commit that is not the recorded head"
        )
        mutated = replace_once(handoff_text, f"`{recorded}`", f"`{baseline}`")
        assert "the identity section names no commit other than the recorded head" in \
            drift_names(validator, mutated)

    def test_naming_no_commit_at_all_is_compliant(
        self, validator: types.ModuleType, handoff_text: str
    ) -> None:
        """Absence is the compliant state - it is how F-0046 left the integrity
        section. Presence is what must agree."""
        recorded = validator.parse_claims(handoff_text)["head"]
        mutated = replace_once(handoff_text, f"`{recorded}`", "see the §12 block")
        assert "the identity section names no commit other than the recorded head" \
            not in drift_names(validator, mutated)
