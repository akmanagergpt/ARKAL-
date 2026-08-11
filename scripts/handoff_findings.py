"""Finding-summary drift controls for ARKALI_HANDOFF.md.

Validation tool, not application source code.

WHY THIS EXISTS. F-0046 made the validator read the prose, but only for
GOVERNANCE-STATE narrative: which phase is current, what it declares, which
commit a revision was generated at, the interpreter, the execution surfaces.
F-0047 added the LIVE ARCHITECTURE summary. Neither touched the manifest's
FINDING summary, and the machine-readable `open_blocker_high` claim validates a
list of stopping findings - not the prose that summarises the recorded set. So
the current-state row saying "every finding through F-XXXX is closed" was an
author-maintained transcription with no mechanical backing, and it went stale
the moment the next finding was recorded, while the validator reported PASS.
The same transcribed-value family as F-0002, F-0011, F-0041 and F-0047 itself.

NO SHADOW MODEL. The finding set is parsed by `arkali.acceptance.findings`, from
the file `arkali.acceptance.governance_state` declares canonical, so this module
and the acceptance gate read one record through one parser. Nothing here names a
finding identifier, a severity, a count or a phase.

SCOPE IS THE LIVE SUMMARY ONLY. The commit ledger, the generation records and
the per-finding rows in the open-items section are records of individual
findings at particular commits. They are evidence and are never re-derived.

ADR-0008 decomposition: `check_handoff.py` is near its 400 logical-line budget
and this has a different subject and authority from the controls that remain
there. No GATE 8 exception was requested.
"""
from __future__ import annotations

import pathlib
import re
import sys
from typing import Any

from handoff_markdown import DriftReport, plain, section

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

#: The section carrying the live summary. Matched by ROLE, never by number.
CURRENT_STATE_HEADING = r"^##\s*\d+\.\s*Current verified state\s*$"
#: A finding identifier as every canonical record spells one.
_FINDING_ID = re.compile(r"F-\d{4}")
#: A statement that closes the recorded set at some identifier.
_THROUGH = re.compile(r"through\s+(F-\d{4})", re.IGNORECASE)
#: How far past the latest identifier its own status and severity may be written.
_STATUS_WINDOW = 80
#: The only two states a finding row may declare, as whole words.
_STATUS_TOKEN = re.compile(r"\b(OPEN|CLOSED)\b")


def finding_truth(repo: pathlib.Path) -> dict[str, Any]:
    """The recorded finding set, read through the canonical parser.

    The file is the one `governance_state` declares canonical, so a finding is
    never counted here that the acceptance gate would not see - and the reverse.
    `KNOWN_FAILURES.md` also carries finding-shaped rows, but it is a historical
    subset and is not the record any acceptance decision consults, so widening
    to it would invent a second authority.
    """
    from arkali.acceptance.findings import parse_findings, stopping_findings
    from arkali.acceptance.governance_state import OPEN_BLOCKERS

    text = (repo / OPEN_BLOCKERS).read_text(encoding="utf-8")
    found = parse_findings(text)
    latest = max(found, key=lambda f: f.identifier) if found else None
    return {
        "source": OPEN_BLOCKERS,
        "total": len(found),
        "latest_id": latest.identifier if latest else None,
        "latest_status": latest.status.value if latest else None,
        "latest_severity": latest.severity.upper() if latest else None,
        "open_ids": sorted(f.identifier for f in found if f.is_open),
        "stopping": sorted(stopping_findings(text)),
    }


def check_findings(repo: pathlib.Path, text: str, report: DriftReport) -> None:
    """The live finding summary must reconcile with the canonical records."""
    body = plain(section(text, CURRENT_STATE_HEADING))
    report.assert_true(
        "a current verified-state section exists for the finding summary",
        bool(body.strip()),
    )
    if not body.strip():
        return
    truth = finding_truth(repo)
    latest = truth["latest_id"]
    report.assert_true(
        "the canonical finding record declares at least one finding",
        latest is not None,
        f"{truth['source']} parsed {truth['total']} findings",
    )
    if latest is None:
        return

    named = _FINDING_ID.findall(body)

    # -- the summary must reach the newest recorded finding --------------------
    #
    # This is the control the stale "every finding through F-XXXX is closed" row
    # needed: a summary that stops at the previous identifier does not name the
    # current one, and neither does a summary that omits findings entirely.
    report.assert_true(
        "the live finding summary names the latest recorded finding",
        latest in named,
        f"{truth['source']} records {latest}; the summary names {sorted(set(named))}",
    )

    # -- and may not close the set at an older identifier ----------------------
    stale = sorted({m for m in _THROUGH.findall(body) if m != latest})
    report.assert_true(
        "every 'through F-xxxx' statement names the latest recorded finding",
        not stale,
        f"{stale} closes the set short of {latest}",
    )

    # -- nor invent one that does not exist yet --------------------------------
    ahead = sorted({m for m in named if m > latest})
    report.assert_true(
        "the live finding summary names no finding newer than the record",
        not ahead,
        f"{ahead} are not recorded in {truth['source']}",
    )

    check_latest_shape(body, truth, report)
    check_stopping(body, truth, report)


def check_latest_shape(body: str, truth: dict[str, Any], report: DriftReport) -> None:
    """The latest finding's declared severity and status must be stated as recorded.

    Each mention is read through a BOUNDED WINDOW rather than the whole section,
    because the section discusses other findings and a search over all of it
    would match somebody else's status. EVERY mention is considered, not the
    first: the latest identifier legitimately appears in more than one row - the
    architecture summary cites the finding that repaired it - and anchoring on
    whichever came first would report on an incidental mention.
    """
    latest = truth["latest_id"]
    status, severity = truth["latest_status"], truth["latest_severity"]

    # A mention declares a status only through the token NEAREST to it. Testing
    # for the bare word anywhere in the window would read ordinary prose as an
    # assertion - "0 are open" says nothing about this finding's own state, and
    # the file name `OPEN_BLOCKERS.md` says nothing at all.
    declared: list[tuple[str, str]] = []
    for mention in re.finditer(re.escape(latest), body):
        window = body[mention.end(): mention.end() + _STATUS_WINDOW].upper()
        token = _STATUS_TOKEN.search(window)
        if token:
            declared.append((token.group(1), window))

    declaring = [w for token, w in declared if token == status]
    contradicting = [w for token, w in declared if token != status]

    report.assert_true(
        f"the live finding summary states {latest} as {status}",
        bool(declaring),
        f"the record declares {status}; no mention of {latest} states it",
    )
    report.assert_true(
        f"the live finding summary does not contradict {latest}'s declared status",
        not contradicting,
        f"the record declares {status}; the summary asserts otherwise beside {latest}",
    )
    if declaring:
        report.assert_true(
            f"the live finding summary states {latest}'s severity as {severity}",
            severity in declaring[0],
            f"the record declares {severity}; the summary says {declaring[0].strip()!r}",
        )


def check_stopping(body: str, truth: dict[str, Any], report: DriftReport) -> None:
    """The stated BLOCKER/HIGH pair must equal the live stopping-finding count.

    The MEDIUM and LOW totals are deliberately NOT checked: the manifest states
    that it does not mirror them, because a number written there would be a
    transcription that re-rots on the next finding (F-0002, F-0011). A control
    that demanded one would be arguing with a decision the manifest already
    made, and would create the very defect this module exists to prevent.
    """
    stated = re.search(r"BLOCKER\s*/\s*HIGH\s*\|\s*(\d+)\s*/\s*(\d+)", body, re.IGNORECASE)
    report.assert_true(
        "the live summary still states the BLOCKER/HIGH pair",
        stated is not None,
        "the claim was reworded or removed, so nothing was compared",
    )
    if stated is None:
        return
    live = len(truth["stopping"])
    report.check(
        "stated BLOCKER + HIGH total",
        int(stated.group(1)) + int(stated.group(2)),
        live,
    )
    # Every finding that stops acceptance must be visible in the live summary,
    # so a stopping finding can never be recorded and then not mentioned.
    missing = sorted(f for f in truth["stopping"] if f not in body)
    report.assert_true(
        "every stopping finding is named in the live summary",
        not missing,
        f"{missing} stop acceptance but are not named",
    )
