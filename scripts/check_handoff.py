#!/usr/bin/env python3
"""Handoff drift validator for ARKALI GENESIS v2.

Validation tool, not application source code.

ARKALI_HANDOFF.md is an INDEX, never an authority. This validator derives the
current truth from the repository (Git plus the accepted governance artifacts)
and compares it against the claims the handoff declares. Any disagreement is
HANDOFF_DRIFT and the run FAILS CLOSED.

NO SHADOW MODEL: nothing governed is hard-coded here. HEAD, branch, phase state,
requirement counts, human gates, ADR states and finding counts are all read from
authoritative sources at run time. Only parsing logic lives in this file.

This validator never repairs an authoritative repository file.

Exit 0 = handoff agrees with repository truth. Exit 1 = HANDOFF_DRIFT.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys
from typing import Any

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "ARKALI_HANDOFF.md"
SESSION_PROMPT = ROOT / "ARKALI_NEW_SESSION_PROMPT.txt"
SCHEMA_VERSION = "ARKALI-HANDOFF-V1"

sys.path.insert(0, str(ROOT / "backend"))


def git(*args: str, repo: pathlib.Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo or ROOT, capture_output=True, text=True
    )
    return result.stdout.strip()


def parse_claims(text: str) -> dict[str, Any]:
    """Extract the machine-readable claim block from the handoff."""
    match = re.search(r"```yaml\s+# ARKALI-HANDOFF-CLAIMS\s+(.*?)```", text, re.S)
    if not match:
        raise ValueError("handoff contains no ARKALI-HANDOFF-CLAIMS yaml block")
    parsed = yaml.safe_load(match.group(1))
    if not isinstance(parsed, dict):
        raise ValueError("claim block is not a mapping")
    return parsed


def derive_truth(repo: pathlib.Path) -> dict[str, Any]:
    """Current truth, read from Git and the accepted governance artifacts."""
    from arkali.acceptance.governance_state import GovernanceState
    from arkali.control.specification.register_parser import RequirementRegister

    register = RequirementRegister.load(repo)
    state = GovernanceState.load(repo)
    counts = register.classification_counts()

    adr_text = (repo / "docs/adr/ADR_INDEX.md").read_text(encoding="utf-8")
    accepted_phases = sorted(
        pid for pid, status in state.phases.items() if status.is_accepted
    )
    # The current work phase: declared UNLOCKED and not yet accepted.
    #
    # Defect F-0029. The predecessor additionally required NOT_STARTED, so the
    # derivation recognised only the two states that existed while every phase
    # was delivered in a single commit: not started, or accepted. Phase 5 is the
    # first phase delivered in atomic packages, and the moment BUILD_STATE
    # truthfully said "IN PROGRESS, NOT ACCEPTED" the phase became invisible
    # here and the manifest's next-action claim drifted against nothing.
    # Seventh instance of a rule that only understood the states existing when
    # it was written (F-0008, F-0013, F-0016, F-0019, F-0022, F-0027).
    #
    # Acceptance is still read from `PhaseStatus.is_accepted`, so this is not a
    # second acceptance model, and exactly one such phase is still required.
    #
    # Defect F-0034. This module used to restate the rule as
    # `"UNLOCKED" in status_text.upper()`, the same prose-substring test that
    # let unrelated commentary decide acceptance - a row merely *mentioning*
    # that some phase was unlocked would have matched, and two matches collapse
    # the answer to None. The derivation now belongs to `GovernanceState` and is
    # called, not reimplemented, so there is one rule and one place to correct.
    return {
        "head": git("rev-parse", "HEAD", repo=repo),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD", repo=repo),
        "working_tree_clean": git("status", "--porcelain", "-uall", repo=repo) == "",
        "requirements_total": len(register),
        "requirements_mandatory": counts["MANDATORY"],
        "requirements_conditional": counts["CONDITIONAL"],
        "requirements_optional": counts["OPTIONAL"],
        "accepted_phases": accepted_phases,
        "unlocked_phase": state.current_work_phase(),
        "accepted_human_gates": sorted(state.accepted_human_gates),
        "adr_accepted": adr_text.count("| ACCEPTED |"),
        "adr_proposed": adr_text.count("| PROPOSED |"),
        "open_blocker_high": list(state.open_stopping_findings),
    }


class Report:
    def __init__(self) -> None:
        self.drift: list[str] = []

    def check(self, name: str, claimed: Any, actual: Any) -> None:
        ok = claimed == actual
        print(f"{'PASS ' if ok else 'DRIFT'} {name}")
        if not ok:
            print(f"        claimed={claimed!r}")
            print(f"        actual ={actual!r}")
            self.drift.append(name)

    def assert_true(self, name: str, condition: bool, detail: str = "") -> None:
        print(f"{'PASS ' if condition else 'DRIFT'} {name}"
              + (f"  -- {detail}" if detail and not condition else ""))
        if not condition:
            self.drift.append(name)


#: Artifacts whose change invalidates a handoff. Paths only; contents are read
#: from the repository, never mirrored here.
GOVERNED_PATHS: tuple[str, ...] = (
    "docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md",
    "docs/CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md",
    "docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md",
    "docs/ARKALI_GENESIS_V2_START_COMMAND.txt",
    "docs/canonical/",
    "docs/adr/",
    "docs/acceptance/HUMAN_GATE_RECORDS.md",
    "docs/build/BUILD_STATE.md",
    "docs/build/PHASE_HISTORY.md",
    "docs/build/OPEN_BLOCKERS.md",
)


def check_head(report: Report, repo: pathlib.Path, claimed: str, actual: str) -> None:
    """HEAD must match, or differ only by commits that changed nothing governed.

    A manifest that records HEAD cannot be committed at that HEAD: committing it
    advances HEAD by one. Rather than weaken the check, the claimed commit is
    accepted only when it is an ancestor of the current HEAD AND no governed
    artifact changed in between. Any governance change since generation is
    HANDOFF_DRIFT.
    """
    if claimed == actual:
        report.assert_true("HEAD matches exactly", True)
        return
    is_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", claimed, actual],
        cwd=repo, capture_output=True, text=True,
    ).returncode == 0
    if not is_ancestor:
        report.assert_true(
            "HEAD is current or a governed-clean ancestor", False,
            f"claimed {claimed[:12]} is not an ancestor of {actual[:12]}",
        )
        return
    changed = git("diff", "--name-only", f"{claimed}..{actual}", "--",
                  *GOVERNED_PATHS, repo=repo)
    touched = [line for line in changed.splitlines() if line.strip()]
    report.assert_true(
        "HEAD is current or a governed-clean ancestor", not touched,
        f"governed artifacts changed since {claimed[:12]}: {touched}",
    )



def validate(repo: pathlib.Path, handoff_text: str,
             session_prompt: pathlib.Path | None = None) -> Report:
    report = Report()
    claims = parse_claims(handoff_text)
    truth = derive_truth(repo)

    report.check("schema version", claims.get("schema_version"), SCHEMA_VERSION)
    check_head(report, repo, str(claims.get("head", "")), truth["head"])
    report.check("branch", claims.get("branch"), truth["branch"])
    report.check("working-tree clean claim",
                 bool(claims.get("working_tree_clean")), truth["working_tree_clean"])
    report.check("requirements total",
                 claims.get("requirements_total"), truth["requirements_total"])
    report.check("requirements MANDATORY",
                 claims.get("requirements_mandatory"), truth["requirements_mandatory"])
    report.check("requirements CONDITIONAL",
                 claims.get("requirements_conditional"),
                 truth["requirements_conditional"])
    report.check("requirements OPTIONAL",
                 claims.get("requirements_optional"), truth["requirements_optional"])
    report.check("accepted phases",
                 sorted(claims.get("accepted_phases", [])), truth["accepted_phases"])
    report.check("unlocked phase",
                 claims.get("unlocked_phase"), truth["unlocked_phase"])
    report.check("accepted human gates",
                 sorted(claims.get("accepted_human_gates", [])),
                 truth["accepted_human_gates"])
    report.check("ADR accepted count",
                 claims.get("adr_accepted"), truth["adr_accepted"])
    report.check("ADR proposed count",
                 claims.get("adr_proposed"), truth["adr_proposed"])
    report.check("open BLOCKER/HIGH",
                 list(claims.get("open_blocker_high", [])), truth["open_blocker_high"])

    # cumulative verified requirements must equal the sum of per-phase closures
    verified = claims.get("verified_by_phase", {}) or {}
    report.check("cumulative verified requirements",
                 claims.get("cumulative_verified"),
                 sum(int(v) for v in verified.values()))

    # every indexed authoritative source must exist
    missing = [p for p in claims.get("authoritative_sources", [])
               if not (repo / p).is_file()]
    report.assert_true("all authoritative sources exist", not missing, str(missing))

    # NEXT EXACT ACTION must name the unlocked phase and not a locked one
    next_phase = str(claims.get("next_exact_action_phase", ""))
    report.check("NEXT EXACT ACTION targets the unlocked phase",
                 next_phase, truth["unlocked_phase"])

    # the session prompt must exist and must not leak secrets
    prompt = session_prompt if session_prompt is not None else SESSION_PROMPT
    report.assert_true("new-session prompt present", prompt.is_file())
    if prompt.is_file():
        body = prompt.read_text(encoding="utf-8")
        leaked = re.search(
            r"(?i)(api[_-]?key|password|secret\s*[:=]|BEGIN [A-Z ]*PRIVATE KEY|@gmail\.)",
            body,
        )
        report.assert_true("new-session prompt carries no secret or personal data",
                           leaked is None, leaked.group(0) if leaked else "")
    return report


def main() -> int:
    if not HANDOFF.is_file():
        print(f"DRIFT  handoff manifest missing at {HANDOFF}")
        print("\nRESULT: HANDOFF_DRIFT")
        return 1
    try:
        report = validate(ROOT, HANDOFF.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - reported, never converted to PASS
        print(f"DRIFT  handoff could not be validated: {exc!r}")
        print("\nRESULT: HANDOFF_DRIFT")
        return 1
    print()
    if report.drift:
        print(f"RESULT: HANDOFF_DRIFT ({len(report.drift)}) -> {report.drift}")
        print("Repository authority wins. Continuation must stop.")
        return 1
    print("RESULT: PASS - handoff agrees with repository truth")
    return 0


if __name__ == "__main__":
    sys.exit(main())
