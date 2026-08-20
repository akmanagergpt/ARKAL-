"""The canonical staged-generation stage vocabulary, parsed from its document.

Owner: `engineering.factory`. Internal generation-pipeline sequencing only —
this is not a `CONTRACT_INVENTORY.md` contract (verified: every existing
contract, C-01 through C-37, was added in one of three commits that all
predate Phase 16; no phase since has minted a new contract row, so this
staged-generation pipeline does not mint one either). Nothing outside
`engineering.factory` consumes this vocabulary.

WHY THIS IS PARSED, NOT A PYTHON LIST. Writing the stage order and each
stage's declared inputs into a second Python structure would let it drift
from `STAGED_GENERATION_STAGES.md` — the same F-0013 shape
`engineering.repair.failure_protocol.FailureProtocolVocabulary` already
exists to prevent for the (unrelated) root-cause pipeline. This module reads
that same neighbouring markdown file at call time instead.

FAILS CLOSED. An absent document, a stage with no declared `Inputs:` or
`Rule:` line, a non-sequential stage number, a duplicate stage name, or an
input naming anything other than a strictly-earlier stage all raise
`StageVocabularyError` rather than being guessed or silently dropped.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

from arkali.engineering.factory.errors import StageVocabularyError

#: Located next to this module, not under top-level `docs/` — it documents
#: this context's own internal sequencing, not a cross-context contract.
STAGE_VOCABULARY_RELPATH: Final[str] = (
    "backend/arkali/engineering/factory/STAGED_GENERATION_STAGES.md"
)

_STAGE_HEADING: Final[re.Pattern[str]] = re.compile(
    r"^###\s+(?P<number>\d+)\.\s+(?P<name>[a-z_]+)\s*$", re.M
)
_INPUTS_LINE: Final[re.Pattern[str]] = re.compile(
    r"^Inputs:\s*(?P<value>.+?)\s*$", re.M
)
_RULE_LINE: Final[re.Pattern[str]] = re.compile(r"^Rule:\s*(?P<value>.+)$", re.M | re.S)


class StageDeclaration:
    """One stage's declared position, its required prior-stage inputs and rule."""

    def __init__(self, order: int, name: str, inputs: tuple[str, ...], rule: str) -> None:
        self.order = order
        self.name = name
        self.inputs = inputs
        self.rule = rule


def _stage_blocks(text: str) -> list[re.Match[str]]:
    return list(_STAGE_HEADING.finditer(text))


def _parse_stage(text: str, start: int, end: int, source: str) -> StageDeclaration:
    heading = _STAGE_HEADING.match(text, start)
    assert heading is not None  # the caller only passes a heading match's span
    body = text[heading.end():end]

    inputs_match = _INPUTS_LINE.search(body)
    if inputs_match is None:
        raise StageVocabularyError(
            f"stage {heading.group('name')!r} declares no 'Inputs:' line",
            source=source,
        )
    raw_inputs = inputs_match.group("value").strip()
    inputs = () if raw_inputs.lower() == "none" else tuple(
        part.strip() for part in raw_inputs.split(",") if part.strip()
    )

    rule_match = _RULE_LINE.search(body)
    if rule_match is None or not rule_match.group("value").strip():
        raise StageVocabularyError(
            f"stage {heading.group('name')!r} declares no 'Rule:' text", source=source
        )
    rule = " ".join(rule_match.group("value").split())

    return StageDeclaration(
        order=int(heading.group("number")), name=heading.group("name"),
        inputs=inputs, rule=rule,
    )


class StageVocabulary:
    """The ordered, acyclic staged-generation stage list.

    Construct with `load`. `stages()` returns the declarations in document
    order, each already proven to depend only on strictly-earlier stages.
    """

    def __init__(self, stages: tuple[StageDeclaration, ...], source: str) -> None:
        self._stages = stages
        self.source = source

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> StageVocabulary:
        path = repo_root / STAGE_VOCABULARY_RELPATH
        if not path.is_file():
            raise StageVocabularyError(
                "the staged-generation stage vocabulary document is missing",
                source=str(path),
            )
        text = path.read_text(encoding="utf-8")
        headings = _stage_blocks(text)
        if len(headings) < 2:
            raise StageVocabularyError(
                f"the stage vocabulary declares {len(headings)} stage(s); a "
                "pipeline with nothing to sequence would pass vacuously",
                source=str(path),
            )

        declarations: list[StageDeclaration] = []
        for index, heading in enumerate(headings):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            declarations.append(_parse_stage(text, heading.start(), end, str(path)))

        names_seen: dict[str, int] = {}
        for expected_order, declaration in enumerate(declarations, start=1):
            if declaration.order != expected_order:
                raise StageVocabularyError(
                    f"stage {declaration.name!r} is numbered {declaration.order}; "
                    f"expected {expected_order} (stages must be declared in "
                    "sequential order, one place, no gaps)",
                    source=str(path),
                )
            if declaration.name in names_seen:
                raise StageVocabularyError(
                    f"stage name {declaration.name!r} is declared twice "
                    f"(stages {names_seen[declaration.name]} and {declaration.order})",
                    source=str(path),
                )
            for input_name in declaration.inputs:
                if input_name not in names_seen:
                    raise StageVocabularyError(
                        f"stage {declaration.name!r} declares input "
                        f"{input_name!r}, which is not a strictly-earlier "
                        "declared stage (inputs may never name themselves, a "
                        "later stage, or an undeclared name)",
                        source=str(path),
                    )
            names_seen[declaration.name] = declaration.order

        return cls(tuple(declarations), str(path))

    def stages(self) -> tuple[StageDeclaration, ...]:
        """Every stage, in document/execution order."""
        return self._stages

    def stage(self, name: str) -> StageDeclaration:
        for declaration in self._stages:
            if declaration.name == name:
                return declaration
        raise StageVocabularyError(
            f"no stage named {name!r} is declared", source=self.source
        )
