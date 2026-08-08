"""Parser for the canonical requirement register (C-04 consumer).

Owner: control.specification.

NO SHADOW MODEL: the requirement denominator is never hard-coded. Every entry is
parsed from docs/canonical/REQUIREMENT_REGISTER.md at call time, so the register
alone decides what exists and how it is classified.
"""

from __future__ import annotations

import pathlib
import re
from collections import Counter

from arkali.control.specification.requirement_record import (
    Classification,
    RequirementRecord,
)
from arkali.kernel.contracts.errors import AuthoritativeSourceError

REGISTER_RELPATH = "docs/canonical/REQUIREMENT_REGISTER.md"

_ROW = re.compile(
    r"^\|\s*(ARK-REQ-\d{4})\s*\|(?P<statement>[^|]*)\|(?P<source>[^|]*)\|"
    r"\s*(?P<cls>MANDATORY|CONDITIONAL|OPTIONAL)\s*\|"
    r"(?P<phase>[^|]*)\|(?P<owner>[^|]*)\|(?P<evidence>[^|]*)\|",
    re.M,
)
_APPENDIX_RULE = re.compile(r"^\|\s*(ARK-REQ-\d{4})\s*\|(?P<rule>[^|]*)\|", re.M)


class RequirementRegister:
    """Parsed register. Construct with `load`; never populated by hand."""

    def __init__(
        self,
        records: dict[str, RequirementRecord],
        applicability_rules: dict[str, str],
        source_path: str,
    ) -> None:
        self._records = records
        self._rules = applicability_rules
        self.source_path = source_path

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> RequirementRegister:
        path = repo_root / REGISTER_RELPATH
        if not path.is_file():
            raise AuthoritativeSourceError("register not found", source=str(path))
        text = path.read_text(encoding="utf-8")

        records: dict[str, RequirementRecord] = {}
        for match in _ROW.finditer(text):
            req_id = match.group(1)
            if req_id in records:
                raise AuthoritativeSourceError(
                    f"duplicate requirement id {req_id}", source=str(path)
                )
            evidence = tuple(
                token.strip()
                for token in match.group("evidence").split(",")
                if token.strip()
            )
            records[req_id] = RequirementRecord(
                req_id=req_id,
                statement=match.group("statement").strip(),
                source=match.group("source").strip(),
                classification=Classification(match.group("cls")),
                owning_phase=match.group("phase").strip(),
                owning_component=match.group("owner").strip(),
                required_evidence=evidence,
            )
        if not records:
            raise AuthoritativeSourceError(
                "register parsed to zero requirements", source=str(path)
            )

        rules: dict[str, str] = {}
        if "## Appendix A" in text:
            appendix = text.split("## Appendix A")[1].split("\n## ")[0]
            for match in _APPENDIX_RULE.finditer(appendix):
                rules[match.group(1)] = match.group("rule").strip()
        return cls(records, rules, str(path))

    def __len__(self) -> int:
        return len(self._records)

    def all_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._records))

    def get(self, req_id: str) -> RequirementRecord:
        record = self._records.get(req_id)
        if record is None:
            raise AuthoritativeSourceError(
                f"unknown requirement {req_id}", source=self.source_path
            )
        return record

    def for_phase(self, phase: str) -> tuple[RequirementRecord, ...]:
        return tuple(
            r for r in sorted(self._records.values(), key=lambda x: x.req_id)
            if r.owning_phase == phase
        )

    def mandatory_ids(self) -> tuple[str, ...]:
        return tuple(
            r.req_id for r in sorted(self._records.values(), key=lambda x: x.req_id)
            if r.is_mandatory
        )

    def classification_counts(self) -> dict[str, int]:
        counter = Counter(r.classification.value for r in self._records.values())
        return {k: counter.get(k, 0) for k in ("MANDATORY", "CONDITIONAL", "OPTIONAL")}

    def applicability_rule(self, req_id: str) -> str | None:
        return self._rules.get(req_id)

    def conditional_without_rule(self) -> tuple[str, ...]:
        """CONDITIONAL entries lacking an objective rule. Must always be empty."""
        return tuple(
            sorted(
                r.req_id
                for r in self._records.values()
                if r.classification is Classification.CONDITIONAL
                and r.req_id not in self._rules
            )
        )
