"""Negative controls for the handoff's LIVE finding summary (F-0047, completing).

F-0046 made the validator read the prose, but only for governance-state
narrative. F-0047's first pass added the live architecture summary and the
manifest's commit self-references. Neither reached the FINDING summary, and the
machine-readable `open_blocker_high` claim carries only the STOPPING set - so
recording a MEDIUM finding left §3 saying "every finding through F-XXXX is
closed" one identifier short, with the validator reporting PASS.

Two mutation subjects are needed, because the control reconciles a CLAIM in the
manifest against a RECORD in the repository:

  * manifest-side mutations run in memory, like every other control here;
  * record-side mutations must touch `OPEN_BLOCKERS.md`, because the truth is
    read from the file the acceptance gate reads. Those restore the original
    bytes and verify the sha256 in a `finally`, so a failing assertion can
    never leave the canonical record modified.

Every subject is DERIVED from `finding_truth`; no identifier, severity or count
is named here, so none of these controls can expire (F-0021).
"""

from __future__ import annotations

import ast
import hashlib
import re
import types
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.governance.handoff_harness import (
    HANDOFF,
    REPO,
    drift_names,
    load_module,
    load_validator,
    replace_once,
)

FINDINGS = REPO / "docs" / "build" / "OPEN_BLOCKERS.md"


@pytest.fixture(scope="module")
def validator() -> types.ModuleType:
    return load_validator()


@pytest.fixture(scope="module")
def handoff_text() -> str:
    return HANDOFF.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def findings_module() -> types.ModuleType:
    load_validator()  # puts scripts/ and backend/ on sys.path
    return load_module(REPO / "scripts" / "handoff_findings.py")


@pytest.fixture()
def truth(findings_module: types.ModuleType) -> dict:
    return findings_module.finding_truth(REPO)


def current_state_section(text: str) -> str:
    """The live current-state section, fetched through the validator's own helper."""
    markdown = load_module(REPO / "scripts" / "handoff_markdown.py")
    findings = load_module(REPO / "scripts" / "handoff_findings.py")
    body = markdown.section(text, findings.CURRENT_STATE_HEADING)
    assert body.strip(), "the current-state section could not be located"
    return body


@contextmanager
def record_mutated(replacement: str, original: str) -> Iterator[None]:
    """Rewrite the canonical finding record, then restore it byte for byte."""
    before = FINDINGS.read_bytes()
    digest = hashlib.sha256(before).hexdigest()
    text = before.decode("utf-8")
    assert original in text, f"expected {original!r} in the canonical record"
    try:
        FINDINGS.write_bytes(text.replace(original, replacement, 1).encode("utf-8"))
        yield
    finally:
        FINDINGS.write_bytes(before)
        assert hashlib.sha256(FINDINGS.read_bytes()).hexdigest() == digest, (
            "the canonical finding record was not restored"
        )


class TestFindingSummaryIsReconciled:
    """The live summary must agree with the canonical finding record."""

    def test_a_summary_that_stops_at_an_older_finding_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        """The exact drift: `through F-XXXX` left behind by the next finding."""
        latest = truth["latest_id"]
        previous = f"F-{int(latest.split('-')[1]) - 1:04d}"
        mutated = replace_once(
            handoff_text, f"through **{latest}**", f"through **{previous}**"
        )
        assert "every 'through F-xxxx' statement names the latest recorded finding" \
            in drift_names(validator, mutated)

    def test_a_summary_that_omits_the_latest_finding_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        """ANTI-VACUITY. Removing every mention must fail, not compare nothing."""
        section = current_state_section(handoff_text)
        assert truth["latest_id"] in section, "the fixture must start from a named latest"
        mutated = handoff_text.replace(
            section, section.replace(truth["latest_id"], "a finding")
        )
        assert "the live finding summary names the latest recorded finding" in \
            drift_names(validator, mutated)

    def test_a_fabricated_newer_finding_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        latest = truth["latest_id"]
        ahead = f"F-{int(latest.split('-')[1]) + 1:04d}"
        mutated = replace_once(
            handoff_text, f"through **{latest}**", f"through **{ahead}**"
        )
        assert "the live finding summary names no finding newer than the record" in \
            drift_names(validator, mutated)

    def test_a_contradicted_status_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        """The summary asserting the opposite of the recorded status."""
        latest, status = truth["latest_id"], truth["latest_status"]
        opposite = "OPEN" if status == "CLOSED" else "CLOSED"
        mutated = replace_once(
            handoff_text, f"**{latest}** — **{truth['latest_severity']}**, **{status}**",
            f"**{latest}** — **{truth['latest_severity']}**, **{opposite}**",
        )
        assert f"the live finding summary does not contradict {latest}'s declared status" \
            in drift_names(validator, mutated)

    def test_a_stale_severity_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        latest, severity = truth["latest_id"], truth["latest_severity"]
        wrong = "LOW" if severity != "LOW" else "HIGH"
        mutated = replace_once(
            handoff_text, f"**{latest}** — **{severity}**", f"**{latest}** — **{wrong}**"
        )
        assert f"the live finding summary states {latest}'s severity as {severity}" in \
            drift_names(validator, mutated)

    def test_a_wrong_blocker_high_pair_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        stopping = len(truth["stopping"])
        mutated = replace_once(
            handoff_text,
            f"| BLOCKER / HIGH | **{stopping} / {stopping}**",
            f"| BLOCKER / HIGH | **{stopping} / {stopping + 3}**",
        )
        assert "stated BLOCKER + HIGH total" in drift_names(validator, mutated)

    def test_a_removed_blocker_high_pair_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        """ANTI-VACUITY over the stopping-finding half."""
        stopping = len(truth["stopping"])
        mutated = replace_once(
            handoff_text,
            f"| BLOCKER / HIGH | **{stopping} / {stopping}**",
            "| BLOCKER / HIGH | none worth stating",
        )
        assert "the live summary still states the BLOCKER/HIGH pair" in \
            drift_names(validator, mutated)


class TestRecordSideMutationsAreDetected:
    """Mutating the RECORD rather than the claim must fail the same way."""

    def test_a_newly_recorded_finding_makes_the_summary_stale(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        """The live defect, reproduced from the other direction: recording a
        finding the summary does not name must stop the run."""
        latest = truth["latest_id"]
        successor = f"F-{int(latest.split('-')[1]) + 1:04d}"
        row = (
            f"| {successor} | **A probe finding, never committed.** | MEDIUM | CLOSED "
            f"| control.architecture | probe |\n"
        )
        anchor = next(
            line for line in FINDINGS.read_text(encoding="utf-8").splitlines()
            if line.startswith(f"| {latest} |")
        )
        with record_mutated(anchor + "\n" + row.rstrip("\n"), anchor):
            names = drift_names(validator, handoff_text)
        assert "the live finding summary names the latest recorded finding" in names

    def test_a_reopened_finding_contradicts_a_closed_summary(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        """If the record says OPEN, a summary saying CLOSED must be refused.

        The mutation is anchored to the LATEST finding's own row. Replacing the
        first `| MEDIUM | CLOSED |` in the file would reopen whichever finding
        happens to be written first, leave the latest closed, and prove nothing.
        """
        latest, severity = truth["latest_id"], truth["latest_severity"]
        row = next(
            line for line in FINDINGS.read_text(encoding="utf-8").splitlines()
            if line.startswith(f"| {latest} |")
        )
        cells = f"| {severity} | CLOSED |"
        assert cells in row, "the latest finding's row does not declare a status"
        with record_mutated(row.replace(cells, f"| {severity} | OPEN |", 1), row):
            names = drift_names(validator, handoff_text)
        assert f"the live finding summary states {latest} as OPEN" in names
        assert f"the live finding summary does not contradict {latest}'s declared status" \
            in names

    def test_the_canonical_record_is_restored_after_every_mutation(self) -> None:
        """The guard itself is proven, so a failure cannot leave the record dirty."""
        before = FINDINGS.read_bytes()
        with pytest.raises(AssertionError):
            with record_mutated("| MEDIUM | OPEN |", "| MEDIUM | CLOSED |"):
                raise AssertionError("simulated control failure")
        assert FINDINGS.read_bytes() == before


class TestFindingTruthComesFromTheCanonicalRecord:
    def test_truth_is_read_from_the_file_the_gate_reads(
        self, findings_module: types.ModuleType, truth: dict
    ) -> None:
        from arkali.acceptance.governance_state import OPEN_BLOCKERS

        assert truth["source"] == OPEN_BLOCKERS

    def test_the_latest_identifier_is_the_maximum_recorded(self, truth: dict) -> None:
        assert truth["latest_id"] is not None
        assert truth["total"] > 1, "one finding cannot prove a maximum"

    def test_the_stopping_set_agrees_with_governance_state(self, truth: dict) -> None:
        from arkali.acceptance.governance_state import GovernanceState

        assert truth["stopping"] == sorted(
            GovernanceState.load(REPO).open_stopping_findings
        )

    def test_no_finding_identifier_is_hard_coded_in_the_controls(self) -> None:
        """The F-0021 rule, asserted against the module's own source.

        The subject is EXECUTABLE code, not prose. Docstrings and comments cite
        the findings a module exists because of - that is provenance every
        module here carries, and banning it would delete the reason the code is
        shaped the way it is. What must not exist is a finding identifier the
        logic depends on.
        """
        source = (REPO / "scripts" / "handoff_findings.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        # Identified by POSITION, not by value: `ast.get_docstring` returns the
        # cleaned text while the node holds the raw literal, so comparing the
        # two never matches and every docstring would count as logic.
        docstrings = set()
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ) and body and isinstance(body[0], ast.Expr):
                docstrings.add(id(body[0].value))
        literals = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings
            and re.search(r"F-\d{4}", node.value)
        ]
        assert not literals, f"the controls name findings in logic: {literals}"


