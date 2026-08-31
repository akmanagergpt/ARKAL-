"""Phase-transition residue controls for ARKALI_HANDOFF.md.

Validation tool, not application source code.

WHY THIS EXISTS. F-0046 made the validator read the prose, F-0047 bound the live
architecture and finding summaries to their mechanisms. Every one of those
controls is scoped either to the machine-readable claim block or to the
CURRENT-PHASE section. None of them reads the per-phase rows of the live state
summary, and none reads the body of NEXT EXACT ACTION beyond the claim that
names its phase.

So a phase moving from in-progress to ACCEPTED left residue in exactly the two
places nothing looked: its own summary row kept the old "packages N of M
complete / none discharged / cumulative stays X" tail underneath the new
acceptance sentence, and the tail of NEXT EXACT ACTION kept instructing the
reader to derive the PREVIOUS phase's requirement rows, contract and
denominator - inside what is now the live continuation brief for the next phase.
That is worse than stale prose: it points the next implementer back into an
accepted phase's scope.

NOTHING HERE NAMES A PHASE, A REQUIREMENT, A COUNT OR A CONTRACT. The accepted
set, the current work phase, each phase's discharge and the denominators are all
derived from `GovernanceState`, the accepted traceability records and the
register, so these controls follow the build instead of expiring with it.
"""
from __future__ import annotations

import pathlib
import re
import sys
from typing import Any

from handoff_markdown import DriftReport, plain, section

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

CURRENT_STATE_HEADING = r"^##\s*\d+\.\s*Current verified state\s*$"
#: The numeric prefix is OPTIONAL so this one pattern matches both the
#: handoff's own numbered section ("## 9. Next exact action") and
#: `docs/build/BUILD_STATE.md`'s unnumbered section of the same name
#: (F-0050: BUILD_STATE.md carries its own separate "Next exact action"
#: section, and nothing checked it -- it named Phase 14 for sixteen real
#: phases after the current phase moved on).
NEXT_ACTION_HEADING = r"^##\s*(?:\d+\.\s*)?Next exact action\s*$"
#: A requirement identifier as every canonical record spells one.
_REQ_ID = re.compile(r"ARK-REQ-\d{4}")
#: A contract identifier as CONTRACT_INVENTORY.md spells one.
_CONTRACT_ID = re.compile(r"\bC-\d{2}\b")
#: Phrases that assert nothing has been discharged yet.
_NONE_DISCHARGED = re.compile(
    r"(none is discharged|no requirement (is |has been )?discharged|"
    r"none of (them|its requirements) is discharged)", re.IGNORECASE
)
#: A claim that some packages of a total are complete.
_PARTIAL_PACKAGES = re.compile(
    r"packages?\s+[\w,\s]*?\bof\s+(\d+)\s+(?:are\s+)?complete", re.IGNORECASE
)
#: A cumulative total stated in the live summary.
_CUMULATIVE = re.compile(r"cumulative verified\s+(?:stays|is|remains)\s+(\d+)",
                         re.IGNORECASE)
#: The marker this repository's own documents already use (verbatim, in both
#: `ARKALI_HANDOFF.md` and `docs/build/BUILD_STATE.md`) to separate the live
#: guidance in a "Next exact action" section from the historical entries kept
#: below it for continuity. A brief is judged only up to the first one: an
#: older entry's own foreign requirement ids and phase numbers are real
#: history, not a residue the live brief is claiming as its own subject.
_SUPERSEDED_MARKER = re.compile(
    r"\(superseded guidance retained for continuity\)", re.IGNORECASE
)


def transition_truth(repo: pathlib.Path) -> dict[str, Any]:
    """Accepted phases, their discharge, the current phase and its denominator."""
    from arkali.acceptance.governance_state import GovernanceState
    from arkali.acceptance.requirement_claim import TraceabilityRecord
    from arkali.control.specification.register_parser import RequirementRegister

    state = GovernanceState.load(repo)
    register = RequirementRegister.load(repo)
    current = state.current_work_phase()
    accepted = sorted(p for p, s in state.phases.items() if s.is_accepted)
    discharged: dict[str, tuple[str, ...]] = {}
    for phase in accepted:
        if (repo / "docs/acceptance" / f"phase_{phase}_traceability.json").is_file():
            discharged[phase] = TraceabilityRecord.load(repo, phase).satisfied_ids()
    return {
        "current": current,
        "accepted": accepted,
        "discharged": discharged,
        "current_denominator": tuple(
            r.req_id for r in register.for_phase(current)
        ) if current else (),
        "foreign_ids": {
            req: phase
            for phase, ids in discharged.items()
            for req in ids
        },
    }


def check_transition(repo: pathlib.Path, text: str, report: DriftReport) -> None:
    """The live summary and the live brief must have completed the transition."""
    truth = transition_truth(repo)
    summary = plain(section(text, CURRENT_STATE_HEADING))
    report.assert_true(
        "a current verified-state section exists for the transition controls",
        bool(summary.strip()),
    )
    if summary.strip():
        check_accepted_rows(summary, truth, report)
    check_next_action(repo, text, truth, report)

    # F-0050: the identical control, re-applied to BUILD_STATE.md's own
    # "Next exact action" section -- not a second mechanism, the same
    # derivation and the same function, called a second time against a
    # second document that makes the identical continuation claim.
    build_state = repo / "docs" / "build" / "BUILD_STATE.md"
    if build_state.is_file():
        check_next_action(
            repo, build_state.read_text(encoding="utf-8"), truth, report,
            label="BUILD_STATE.md: ",
        )


def _row_for(summary: str, phase: str) -> str | None:
    """The live summary row describing one phase, or None."""
    for line in summary.splitlines():
        if re.match(rf"^\|\s*Phase {re.escape(phase)}\s*\|", line.strip()):
            return line
    return None


def check_accepted_rows(
    summary: str, truth: dict[str, Any], report: DriftReport
) -> None:
    """An accepted phase's row may not still read as an in-progress one."""
    # ANTI-VACUITY. Every phase whose accepted record discharges something must
    # HAVE a row here, or the reconciliation below could be evaded simply by
    # deleting the row it would have judged - which is how the first draft of
    # this control was defeated by its own mutation battery.
    absent = sorted(
        phase for phase, ids in truth["discharged"].items()
        if ids and _row_for(summary, phase) is None
    )
    report.assert_true(
        "the live summary carries a row for every phase that discharged anything",
        not absent,
        f"phases {absent} discharge requirements but have no live row to reconcile",
    )

    checked = 0
    for phase, ids in sorted(truth["discharged"].items()):
        row = _row_for(summary, phase)
        if row is None:
            continue
        checked += 1
        if ids:
            report.assert_true(
                f"the phase {phase} row does not claim its requirements undischarged",
                not _NONE_DISCHARGED.search(row),
                f"{len(ids)} requirements are SATISFIED in its accepted record",
            )
        report.assert_true(
            f"the phase {phase} row does not describe its packages as incomplete",
            not _PARTIAL_PACKAGES.search(row),
            "the phase is accepted, so no package of it remains outstanding",
        )
        report.assert_true(
            f"the phase {phase} row does not describe an accepted phase as in progress",
            "IN PROGRESS" not in row.upper(),
        )
    report.assert_true(
        "the live summary carries a row for at least one accepted phase",
        checked > 0,
        "no accepted phase row was found, so nothing was reconciled",
    )

    # A live cumulative total must agree with the accepted records it sums.
    derivable = sum(len(ids) for ids in truth["discharged"].values())
    stated = [int(m.group(1)) for m in _CUMULATIVE.finditer(summary)]
    for value in stated:
        report.assert_true(
            f"the live cumulative total {value} is not below the accepted records",
            value >= derivable,
            f"accepted traceability records already account for {derivable}",
        )


def check_next_action(
    repo: pathlib.Path, text: str, truth: dict[str, Any], report: DriftReport,
    *, label: str = "",
) -> None:
    """The WHOLE brief must target the current phase, not just its opening.

    `label` distinguishes which document's own "Next exact action" section a
    finding is about when this same function is applied to more than one
    (F-0050: `docs/build/BUILD_STATE.md` carries a second such section,
    separate from the handoff's). The default `""` reproduces the exact
    original, unlabelled messages this function always reported for the
    handoff, so the handoff's own call site is unaffected.
    """
    body = section(text, NEXT_ACTION_HEADING)
    marker = _SUPERSEDED_MARKER.search(body)
    if marker is not None:
        body = body[: marker.start()]
    report.assert_true(
        f"{label}a next-exact-action section exists", bool(body.strip())
    )
    current = truth["current"]
    if not body.strip() or current is None:
        return

    report.assert_true(
        f"{label}the next-exact-action section names the current work phase",
        re.search(rf"\bPhase {re.escape(current)}\b", body) is not None,
        f"the live brief never names phase {current}",
    )

    # Requirement ids offered as live continuation subjects must be the current
    # phase's. An id already discharged by an accepted phase is residue.
    denominator = set(truth["current_denominator"])
    named = set(_REQ_ID.findall(body))
    stale = sorted(
        req for req in named
        if req in truth["foreign_ids"] and req not in denominator
    )
    report.assert_true(
        f"{label}the live brief presents no discharged requirement as a continuation subject",
        not stale,
        f"{stale} were discharged by accepted phase(s) "
        f"{sorted({truth['foreign_ids'][r] for r in stale})}",
    )

    # The brief must state its denominator.  Without anti-vacuity, deleting the
    # claim also deletes the only value this reconciliation can judge.
    stated = re.search(
        r"denominator\s*[-—–:]*\s*(\w+)\s+requirements?", body, re.IGNORECASE
    )
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "zero": 0}
    report.assert_true(
        f"{label}the live brief states a denominator",
        stated is not None,
        f"phase {current} has {len(denominator)} registered requirements",
    )
    if stated:
        token = stated.group(1).lower()
        value = words.get(token, int(token) if token.isdigit() else None)
        if value is not None:
            report.check(
                f"{label}the live brief states the current phase's denominator",
                value, len(denominator),
            )
