"""Structured parsing of governance findings (F-0025).

Owner: acceptance.engine (Protected Core).

THE DEFECT THIS REPLACES. The predecessor decided a finding's state by
searching the whole row for the substring `CLOSED`. A finding whose description
merely mentioned closure - or quoted a field name ending in `_closed` - was
silently treated as resolved and vanished from `open_stopping_findings`. That is
a fail-**open** in the one control whose job is to stop progression, and it hid
F-0024 on the first attempt to record it.

THE RULE NOW. A finding's state comes only from its declared `Status` cell.
Free text may contain OPEN, CLOSED, BLOCKED, PASS, FAIL, HIGH or any other token
without effect. Nothing outside the status column can change a state.

FAIL CLOSED, NEVER SILENTLY. A row that cannot be parsed - unknown status,
missing status, missing id - is not skipped. It is returned as a malformed
finding that stops progression, so an unreadable row is louder than an open one
rather than quieter. A table that declares a Severity column but no Status
column is itself malformed, which closes the gap where a findings table could
avoid parsing altogether by omitting a header.
"""

from __future__ import annotations

import enum
import re

from pydantic import BaseModel, ConfigDict

#: A markdown table row, split on unescaped pipes.
_ROW = re.compile(r"^\|(?P<body>.*)\|\s*$")
#: A markdown alignment separator. It must contain at least one dash: an
#: all-empty row (`| | | |`) matches the character class but is a data row, and
#: treating it as a separator silently drops it - the exact class of defect
#: F-0025 was about.
_SEPARATOR = re.compile(r"^(?=.*-)[\s:|-]+$")


class FindingStatus(str, enum.Enum):
    """The only states a finding row may declare."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    #: Not declarable. Produced when a row cannot be read.
    MALFORMED = "MALFORMED"


#: Severities that stop acceptance. Read from the canonical Severity taxonomy by
#: the caller; named here only as the set this module compares against.
STOPPING_SEVERITIES = frozenset({"BLOCKER", "HIGH"})


class Finding(BaseModel):
    """One governance finding, as declared by its own row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identifier: str
    severity: str
    status: FindingStatus
    detail: str = ""
    source_line: int = 0

    @property
    def is_open(self) -> bool:
        return self.status is FindingStatus.OPEN

    @property
    def stops_acceptance(self) -> bool:
        """A malformed row always stops. An open row stops on severity."""
        if self.status is FindingStatus.MALFORMED:
            return True
        return self.is_open and self.severity.upper() in STOPPING_SEVERITIES

    def render(self) -> str:
        return f"{self.identifier} [{self.severity}] {self.status.value}"


def _cells(line: str) -> list[str]:
    match = _ROW.match(line.strip())
    if match is None:
        return []
    return [c.strip() for c in match.group("body").split("|")]


def _clean(cell: str) -> str:
    """Strip markdown emphasis and strike-through so a status reads plainly."""
    return cell.replace("*", "").replace("~", "").replace("`", "").strip()


def _status_of(raw: str) -> FindingStatus:
    text = _clean(raw).upper()
    if text == "OPEN":
        return FindingStatus.OPEN
    if text == "CLOSED":
        return FindingStatus.CLOSED
    return FindingStatus.MALFORMED


class FindingTable:
    """One markdown table that declares findings."""

    def __init__(self, header: list[str], rows: list[tuple[int, list[str]]]) -> None:
        self.header = [_clean(c).upper() for c in header]
        self.rows = rows

    @property
    def declares_severity(self) -> bool:
        return "SEVERITY" in self.header

    @property
    def declares_status(self) -> bool:
        return "STATUS" in self.header

    @property
    def declares_id(self) -> bool:
        return "ID" in self.header

    @property
    def is_finding_table(self) -> bool:
        """A table is a findings table if it declares an id and a severity.

        Status is deliberately NOT part of this test. A findings table that
        omits Status must be detected as malformed, not silently ignored.
        """
        return self.declares_id and self.declares_severity

    def parse(self) -> list[Finding]:
        found: list[Finding] = []
        for line_no, cells in self.rows:
            found.append(self._parse_row(line_no, cells))
        return found

    def _parse_row(self, line_no: int, cells: list[str]) -> Finding:
        identifier = self._value(cells, "ID")
        severity = self._value(cells, "SEVERITY")
        if not self.declares_status:
            return Finding(
                identifier=identifier or f"row-{line_no}",
                severity=severity,
                status=FindingStatus.MALFORMED,
                detail="findings table declares no Status column",
                source_line=line_no,
            )
        status = _status_of(self._value(cells, "STATUS"))
        if not identifier:
            return Finding(
                identifier=f"row-{line_no}",
                severity=severity,
                status=FindingStatus.MALFORMED,
                detail="finding row declares no identifier",
                source_line=line_no,
            )
        return Finding(
            identifier=identifier,
            severity=severity,
            status=status,
            detail="" if status is not FindingStatus.MALFORMED
            else f"unreadable status {self._value(cells, 'STATUS')!r}",
            source_line=line_no,
        )

    def _value(self, cells: list[str], column: str) -> str:
        if column not in self.header:
            return ""
        index = self.header.index(column)
        return _clean(cells[index]) if index < len(cells) else ""


def _collect_tables(text: str) -> list[FindingTable]:
    tables: list[FindingTable] = []
    header: list[str] | None = None
    rows: list[tuple[int, list[str]]] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        cells = _cells(line)
        if not cells:
            if header is not None:
                tables.append(FindingTable(header, rows))
            header, rows = None, []
            continue
        if header is None:
            header, rows = cells, []
            continue
        if _SEPARATOR.match("|".join(cells)):
            continue
        rows.append((line_no, cells))
    if header is not None:
        tables.append(FindingTable(header, rows))
    return tables


def parse_findings(text: str) -> tuple[Finding, ...]:
    """Every finding declared by every findings table in the document."""
    found: list[Finding] = []
    for table in _collect_tables(text):
        if not table.is_finding_table:
            continue
        found.extend(table.parse())
    return tuple(found)


def stopping_findings(text: str) -> tuple[str, ...]:
    """Identifiers of findings that stop acceptance. Malformed rows always stop."""
    return tuple(
        sorted({f.identifier for f in parse_findings(text) if f.stops_acceptance})
    )
