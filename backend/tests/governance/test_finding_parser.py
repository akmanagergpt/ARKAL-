"""Negative controls for the structured finding parser (closes F-0025).

The predecessor decided a finding's state by searching the whole row for the
substring `CLOSED`. F-0024 could not be recorded because its description quoted
a field name ending in `_closed`, so the finding silently vanished from
`open_stopping_findings` and the gate kept passing.

The twelve controls the ruling requires each have a test below. All fixtures are
in-memory markdown; no repository file is written. The defect class is fixed, not
the single instance: no test here mentions F-0024 as a special case.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from arkali.acceptance.findings import (
    FindingStatus,
    parse_findings,
    stopping_findings,
)

REPO = pathlib.Path(__file__).resolve().parents[3]

HEADER = "| ID | Finding | Severity | Status | Owner |\n|---|---|---|---|---|\n"


def table(*rows: str) -> str:
    return HEADER + "".join(rows)


def row(identifier: str, detail: str, severity: str, status: str) -> str:
    return f"| {identifier} | {detail} | {severity} | {status} | owner |\n"


class TestFreeTextCannotChangeState:
    def test_1_open_finding_whose_description_says_closed_stays_open(self) -> None:
        text = table(row("F-1", "the closure was CLOSED last week", "HIGH", "OPEN"))
        found = parse_findings(text)
        assert found[0].status is FindingStatus.OPEN
        assert found[0].stops_acceptance

    def test_2_open_finding_containing_ark_req_ids_closed_stays_open(self) -> None:
        """The exact wording that hid F-0024."""
        text = table(
            row("F-2", "listed in `ark_req_ids_closed` wrongly", "HIGH", "OPEN")
        )
        assert parse_findings(text)[0].status is FindingStatus.OPEN
        assert stopping_findings(text) == ("F-2",)

    def test_3_closed_finding_with_a_normal_description_is_closed(self) -> None:
        text = table(row("F-3", "an ordinary description", "HIGH", "CLOSED"))
        assert parse_findings(text)[0].status is FindingStatus.CLOSED
        assert stopping_findings(text) == ()

    @pytest.mark.parametrize(
        "noise",
        ["OPEN", "CLOSED", "BLOCKED", "PASS", "FAIL", "HIGH", "BLOCKER", "resolved"],
    )
    def test_4_status_tokens_in_unrelated_text_cannot_alter_state(
        self, noise: str
    ) -> None:
        text = table(row("F-4", f"mentions {noise} in passing", "LOW", "CLOSED"))
        assert parse_findings(text)[0].status is FindingStatus.CLOSED
        assert stopping_findings(text) == ()

    @pytest.mark.parametrize("written", ["open", "Open", "OPEN", " open "])
    def test_11_status_is_case_insensitive_but_only_in_its_own_cell(
        self, written: str
    ) -> None:
        text = table(row("F-11", "closed closed closed", "HIGH", written))
        assert parse_findings(text)[0].status is FindingStatus.OPEN

    def test_11b_owner_column_text_cannot_control_status(self) -> None:
        text = (
            "| ID | Finding | Severity | Status | Owner |\n"
            "|---|---|---|---|---|\n"
            "| F-11b | detail | HIGH | OPEN | team-CLOSED |\n"
        )
        assert stopping_findings(text) == ("F-11b",)


class TestMalformedRowsFailClosed:
    def test_5_missing_status_field_fails_closed(self) -> None:
        """A findings table that declares Severity but no Status is malformed."""
        text = (
            "| ID | Finding | Severity | Owner |\n"
            "|---|---|---|---|\n"
            "| F-5 | detail | HIGH | owner |\n"
        )
        found = parse_findings(text)
        assert found[0].status is FindingStatus.MALFORMED
        assert found[0].stops_acceptance
        assert stopping_findings(text) == ("F-5",)

    def test_6_malformed_row_fails_closed(self) -> None:
        text = table("| | | | | |\n")
        found = parse_findings(text)
        assert found[0].status is FindingStatus.MALFORMED
        assert found[0].stops_acceptance

    @pytest.mark.parametrize("unknown", ["RESOLVED", "WONTFIX", "", "MAYBE", "-"])
    def test_7_unknown_status_fails_closed(self, unknown: str) -> None:
        text = table(row("F-7", "detail", "HIGH", unknown))
        found = parse_findings(text)
        assert found[0].status is FindingStatus.MALFORMED
        assert found[0].stops_acceptance

    def test_12_parser_never_silently_drops_an_unparseable_finding(self) -> None:
        """Every data row in a findings table produces exactly one Finding."""
        text = table(
            row("F-a", "fine", "HIGH", "OPEN"),
            "| | broken | | |\n",
            row("F-c", "fine", "LOW", "CLOSED"),
            row("F-d", "bad status", "HIGH", "PROBABLY"),
        )
        found = parse_findings(text)
        assert len(found) == 4, "a row disappeared"
        assert sum(1 for f in found if f.stops_acceptance) == 3


class TestSeverityGovernsBlocking:
    def test_8_open_high_finding_blocks_progression(self) -> None:
        assert stopping_findings(table(row("F-8", "d", "HIGH", "OPEN"))) == ("F-8",)

    def test_9_open_blocker_finding_blocks_progression(self) -> None:
        assert stopping_findings(table(row("F-9", "d", "BLOCKER", "OPEN"))) == ("F-9",)

    def test_10_closed_high_finding_does_not_block_because_its_text_says_high(
        self,
    ) -> None:
        text = table(row("F-10", "this was a HIGH severity BLOCKER", "HIGH", "CLOSED"))
        assert stopping_findings(text) == ()

    @pytest.mark.parametrize("severity", ["MEDIUM", "LOW", "INFORMATIONAL"])
    def test_open_non_stopping_severities_do_not_block(self, severity: str) -> None:
        assert stopping_findings(table(row("F-x", "d", severity, "OPEN"))) == ()


class TestNonFindingTablesAreNotMisread:
    def test_a_table_without_an_id_column_is_not_a_findings_table(self) -> None:
        text = (
            "| Item | Deferred to | Reason |\n"
            "|---|---|---|\n"
            "| corpus | Phase 30 | needs a Golden Product |\n"
        )
        assert parse_findings(text) == ()

    def test_a_deferred_items_table_is_not_read_as_findings(self) -> None:
        """It declares no Severity, so it is not a findings table."""
        text = (
            "| ID | Item | Deferred to | Reason |\n"
            "|---|---|---|---|\n"
            "| DEF-004 | corpus | Phase 30 | needs a Golden Product |\n"
        )
        assert parse_findings(text) == ()


class TestLiveDocumentIsStructured:
    def test_the_live_blockers_document_parses(self) -> None:
        text = (REPO / "docs/build/OPEN_BLOCKERS.md").read_text(encoding="utf-8")
        found = parse_findings(text)
        assert found, "the live document declares no findings; control is vacuous"
        assert all(f.status is not FindingStatus.MALFORMED for f in found), [
            f.render() for f in found if f.status is FindingStatus.MALFORMED
        ]

    def test_every_live_finding_declares_an_identifier_and_severity(self) -> None:
        text = (REPO / "docs/build/OPEN_BLOCKERS.md").read_text(encoding="utf-8")
        for finding in parse_findings(text):
            assert finding.identifier.strip()
            assert finding.severity.strip()

    def test_no_declared_finding_row_is_invisible_to_the_parser(self) -> None:
        """F-0035. A row the document declares must reach `parse_findings`.

        `_collect_tables` ends a table at a blank line and reads the next row as
        a header, so a blank line inside a findings table turns a data row into
        a header of prose - `declares_id` is then false and the whole fragment
        is skipped. Four such blank lines had accumulated in the live document
        and hid F-0027 through F-0034 from `stopping_findings`. Every hidden row
        was CLOSED, so nothing was falsely passed, but the first OPEN HIGH
        written into the natural place was silently ignored.

        The subject is derived from the document, not listed: any line that
        looks like a finding row must appear in the parsed set. That keeps
        working as findings are added, and fails the moment layout hides one.
        """
        text = (REPO / "docs/build/OPEN_BLOCKERS.md").read_text(encoding="utf-8")
        declared = {
            line.split("|")[1].strip().replace("*", "")
            for line in text.splitlines()
            if re.match(r"^\|\s*(?:F-\d{4}|EXT-\d{3})\s*\|", line)
        }
        assert declared, "no finding rows found; this control would be vacuous"
        parsed = {f.identifier for f in parse_findings(text)}
        assert declared - parsed == set(), (
            "these rows are declared in OPEN_BLOCKERS.md but invisible to the "
            f"acceptance gate: {sorted(declared - parsed)}"
        )
