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

# The sibling modules are loaded by path, not as a package: this file is run as
# `scripts/check_handoff.py` and is also loaded by file location by the
# governance controls, so neither `scripts` nor `backend` is importable by name.
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))


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

    # Imported here rather than at module scope: `scripts/` reaches sys.path
    # above, after the import block this file's linting requires to be first.
    from handoff_architecture import check_architecture
    from handoff_findings import check_findings
    from handoff_transition import check_transition

    check_narrative(repo, handoff_text, report)
    check_architecture(repo, handoff_text, report)
    check_findings(repo, handoff_text, report)
    check_transition(repo, handoff_text, report)

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


#: The heading of the section that describes the phase currently being worked.
#: Matched by ROLE, not by number, so the section can be renumbered.
_CURRENT_PHASE_HEADING = re.compile(
    r"^##\s*\d+\.\s*Current phase contract\s*[-—–]\s*Phase\s*(\S+)\s*$", re.M
)
#: The single marker that says which commit a handoff revision was generated at.
_HEAD_MARKER = "HEAD at generation"
#: A commit id cited in the accepted-commit-history ledger.
_LEDGER_COMMIT = re.compile(r"^\|\s*\d+\s*\|\s*`([0-9a-f]{7,40})`\s*\|", re.M)
#: The row number of a ledger row, paired with the commit it cites.
_LEDGER_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*`([0-9a-f]{7,40})`\s*\|", re.M)
#: The identity section, which may name the commit this revision was generated at.
_IDENTITY_HEADING = r"^##\s*\d+\.\s*Project identity\s*$"
#: A commit id written inline in backticks.
_INLINE_SHA = re.compile(r"`([0-9a-f]{7,40})`")


def check_narrative(repo: pathlib.Path, text: str, report: Report) -> None:
    """Derived checks over the PROSE, not only the machine-readable claims.

    WHY THIS EXISTS (F-0046). Every check above reads the `ARKALI-HANDOFF-CLAIMS`
    block. Nothing read the document around it, so a refresh that updated the
    YAML and whichever prose the author happened to remember still reported
    `PASS` - and the handoff simultaneously said Phase 8 was accepted at the top
    and "IN PROGRESS, NOT ACCEPTED" in its own current-phase section, carried two
    `HEAD at generation` markers naming different commits, and described the
    canonical interpreter as absent while running on it.

    NOTHING HERE NAMES A PHASE, A VERSION OR A COMMIT. Every subject is derived
    from `GovernanceState`, the register, `pyproject.toml`, the filesystem and
    git, so these controls follow the repository instead of expiring with it.
    """
    from arkali.acceptance.governance_state import GovernanceState
    from handoff_markdown import section as _section

    state = GovernanceState.load(repo)
    current = state.current_work_phase()

    recorded = str(parse_claims(text).get("head", ""))

    # -- exactly one generation marker, naming the recorded head ---------------
    #
    # Defect F-0047. The marker was only COUNTED, while §11 stated that a
    # derived control also asserts it "names that same commit". It did not, and
    # the marker was left on an older ledger row by a later refresh - so the
    # manifest overstated its own validator. Counting and naming are now both
    # asserted.
    markers = [line for line in text.splitlines() if _HEAD_MARKER in line]
    report.assert_true(
        "exactly one HEAD-at-generation marker",
        len(markers) == 1,
        f"found {len(markers)}",
    )
    marked = [c for line in markers for c in _LEDGER_COMMIT.findall(line)]
    report.assert_true(
        "the HEAD-at-generation marker names the recorded head",
        len(marked) == 1 and bool(recorded) and recorded.startswith(marked[0]),
        f"marker names {marked}; recorded head is {recorded[:10]}",
    )

    # -- the ledger must be a set, in order, and must reach the recorded head --
    ledger = _section(text, r"^##\s*\d+\.\s*Accepted commit history\s*$")
    cited = _LEDGER_COMMIT.findall(ledger)
    numbered = [int(n) for n, _ in _LEDGER_ROW.findall(ledger)]
    report.assert_true(
        "the accepted-commit history is in ledger order",
        numbered == sorted(numbered),
        f"out of order at {[n for i, n in enumerate(numbered) if i and n < numbered[i - 1]]}",
    )
    duplicated = sorted({c for c in cited if cited.count(c) > 1})
    report.assert_true(
        "no commit is cited twice in the accepted-commit history",
        not duplicated,
        str(duplicated),
    )
    # The ledger must reach the commit the handoff was GENERATED at, not the
    # live HEAD: a §12 refresh commit cannot cite its own sha, which is the same
    # reason `check_head` accepts a governed-clean ancestor.
    reachable = any(recorded.startswith(c) for c in cited if c)
    report.assert_true(
        "the accepted-commit history reaches the recorded head",
        reachable or not cited,
        f"recorded head {recorded[:10]} is absent from {len(cited)} ledger rows",
    )

    # -- the identity section may not carry a second, stale commit ------------
    #
    # Defect F-0047. §11's sha transcription was removed by F-0046 precisely
    # because a hand-copied commit rots, but the identity table kept one and it
    # was twelve commits stale. A commit named there must be the recorded head;
    # naming none is compliant, which is how F-0046 left §11.
    identity = _section(text, _IDENTITY_HEADING)
    strays = [s for s in _INLINE_SHA.findall(identity) if not recorded.startswith(s)]
    report.assert_true(
        "the identity section names no commit other than the recorded head",
        not strays,
        f"{strays} disagree with the recorded head {recorded[:10]}",
    )

    # -- the current-phase section must describe the phase actually current ----
    heading = _CURRENT_PHASE_HEADING.search(text)
    report.assert_true(
        "a current-phase contract section exists", heading is not None
    )
    if heading is not None and current is not None:
        report.check(
            "the current-phase section names the current work phase",
            heading.group(1), current,
        )
        body = _section(text, _CURRENT_PHASE_HEADING.pattern)
        declared = state.phase(current).declared_state.value
        report.assert_true(
            "the current-phase section states that phase's declared state",
            declared.replace("_", " ") in body.replace("_", " ").upper()
            or declared in body,
            f"expected {declared!r} in the section body",
        )

    # -- an accepted phase may not be described as unaccepted ------------------
    if heading is not None:
        body = _section(text, _CURRENT_PHASE_HEADING.pattern).upper()
        accepted = {p for p, s in state.phases.items() if s.is_accepted}
        contradicted = sorted(
            p for p in accepted if re.search(rf"PHASE {re.escape(p)}\b[^.]{{0,80}}NOT ACCEPTED", body)
        )
        report.assert_true(
            "no accepted phase is described as unaccepted in the current section",
            not contradicted,
            str(contradicted),
        )

    # -- the current phase may not claim no progress against its own evidence --
    #
    # WHY THIS EXISTS. The declared-state check above only confirms the
    # current-phase section agrees with BUILD_STATE.md's OWN status cell for
    # that phase - if the cell itself never advanced past UNLOCKED / NOT
    # STARTED while packages landed and were documented elsewhere in this same
    # manifest, both sides "agree" while both are stale (exactly what happened
    # after Phase 14 Package 3: BUILD_STATE.md's phase-status row and this
    # section both still said NOT STARTED while §4 and §3 both documented three
    # committed packages). This control cross-checks against a THIRD,
    # independent, repository-derived source: the accepted-commit-history
    # ledger, whose rows already name their phase by the `PHASE <n> ...`
    # convention used for every phase in this repository, and the live
    # "Current verified state" summary's own per-phase row. Neither the current
    # phase number nor any package name is hard-coded; `current` is derived
    # from `GovernanceState`, exactly as the checks above it are.
    if heading is not None and current is not None:
        ledger_text = _section(text, r"^##\s*\d+\.\s*Accepted commit history\s*$")
        live_summary = _section(text, r"^##\s*\d+\.\s*Current verified state\s*$")
        section_body = _section(text, _CURRENT_PHASE_HEADING.pattern)
        has_ledger_rows = bool(
            re.search(rf"PHASE\s+{re.escape(current)}\b", ledger_text, re.I)
        )
        phase_row = re.search(
            rf"^\|\s*Phase\s*{re.escape(current)}\s*\|(?P<cell>[^\n]*)\|",
            live_summary, re.M,
        )
        live_says_in_progress = bool(
            phase_row and re.search(r"\bIN\s+PROGRESS\b", phase_row.group("cell"), re.I)
        )
        claims_not_started = bool(re.search(r"\bNOT[ _-]STARTED\b", section_body, re.I))
        claims_no_package = bool(re.search(
            r"\bno\b[^.\n]{0,40}\bpackage\b[^.\n]{0,30}\bexists?\b",
            section_body, re.I,
        ))
        report.assert_true(
            "the current-phase section is not contradicted by ledger rows or "
            "the live summary",
            not (
                (has_ledger_rows or live_says_in_progress)
                and (claims_not_started or claims_no_package)
            ),
            f"phase {current}: ledger_rows={has_ledger_rows} "
            f"live_in_progress={live_says_in_progress} "
            f"claims_not_started={claims_not_started} "
            f"claims_no_package={claims_no_package}",
        )

    # -- the canonical interpreter must not be reported absent while satisfied -
    required = _required_python(repo)
    running = ".".join(str(p) for p in sys.version_info[:2])
    environment = _section(text, r"^##\s*\d+\.\s*Current environment\s*$").upper()
    satisfied = _at_least(running, required) if required else False
    stale_absent = bool(
        required
        and satisfied
        and re.search(
            rf"PYTHON {re.escape(required)}[^|]*\|\s*ABSENT", environment
        )
    )
    report.assert_true(
        "the environment section does not report the canonical interpreter absent",
        not stale_absent,
        f"requires-python >= {required}; running {running}",
    )

    # -- an execution surface that exists may not be reported as non-existent --
    surfaces_root = repo / "backend" / "arkali" / "surfaces"
    built = [
        p for p in surfaces_root.rglob("*.py") if p.name != "__init__.py"
    ] if surfaces_root.is_dir() else []
    denies = re.search(r"(?i)no execution surface exists", text) is not None
    report.assert_true(
        "no claim that execution surfaces are absent while one is built",
        not (built and denies),
        f"{len(built)} surface modules exist",
    )


def _required_python(repo: pathlib.Path) -> str:
    """The floor `backend/pyproject.toml` declares. Never transcribed here."""
    manifest = repo / "backend" / "pyproject.toml"
    if not manifest.is_file():
        return ""
    found = re.search(
        r'requires-python\s*=\s*"[^0-9]*([0-9]+\.[0-9]+)', manifest.read_text(encoding="utf-8")
    )
    return found.group(1) if found else ""


def _at_least(running: str, required: str) -> bool:
    def parts(value: str) -> tuple[int, ...]:
        return tuple(int(p) for p in value.split(".") if p.isdigit())
    return parts(running) >= parts(required)


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
