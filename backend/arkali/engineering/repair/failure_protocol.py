"""The canonical failure-protocol stage vocabulary, parsed from both documents.

Owner: engineering.repair. Concern: `root_cause_and_convergence`.

WHAT THIS EXISTS TO PREVENT. `ARK-REQ-0086` requires the root-cause pipeline to
be "followed end to end" and cites `MS §Root-Cause`; `ARK-REQ-0238` requires the
failure protocol to be "followed" and cites `BP §Failure protocol`. Writing
either stage list into a Python tuple would put a governed value in a second
place — defect class F-0013 — so neither list appears in this module. Both are
parsed at call time, exactly as `harness_elements.py` parses the eight harness
elements from the same two documents.

TWO DOCUMENTS DECLARE IT, AND NEITHER MAY BE PREFERRED. `Reproduce->Observe->
Evidence->Hypotheses->Experiment->Root Cause->Minimal Repair->Targeted
Acceptance->Regression` (MS, 9 stages) and `Reproduce->Evidence->Classify->
Hypotheses->Experiment->Root Cause->Minimal Change->Candidate->Targeted Tests->
Regression->Accept/Reject` (BP, 11 stages) are reconciled with the identical
algorithm `harness_elements.py` established for this exact shape of problem:
positions must agree in COUNT, and at each position one name must be a
word-wise abbreviation of the other. A disagreement in either fails closed
rather than being resolved by an invented mapping.

THIS RECONCILIATION CURRENTLY REFUSES, AND THAT REFUSAL IS THE HONEST RESULT.
Unlike the harness elements — where the two declarations differ only by
abbreviation at matching positions — MS declares 9 stages and BP declares 11.
`Reproduce`, `Hypotheses`, `Experiment`, `Root Cause` and `Regression` are
identical in both; the rest diverge in a way that is not reducible to
abbreviation (`Observe`/`Evidence` versus `Evidence`/`Classify` share no common
root at either position, and BP names `Candidate` and `Accept/Reject` as
explicit stages MS does not separately name at all). Inventing a semantic
bridge between `Observe` and `Classify` here would be exactly the alias-table
defect (F-0013 wearing a different hat) `harness_elements.py`'s own docstring
warns against: a resolution not actually derivable from either document's
text. This module therefore raises rather than guesses, matching the D-023
precedent (Phase 9 Package 3 stopped at Stage 1 and reported an ambiguity
rather than inventing a resolution) — `docs/build/DECISION_LOG.md` records the
resulting decision and its scope.

FAILS CLOSED, AND ANTI-VACUITY IS EXPLICIT. An absent section, a section with
no arrow-chain, or a chain carrying fewer than two stages is refused. A
pipeline vocabulary with nothing in it would let "followed end to end" pass
vacuously by having no stage to skip (F-0016, F-0017).

THIS MODULE DESCRIBES; IT DOES NOT ENFORCE. Nothing here tracks a repair
attempt's progress through any stage, and no pipeline orchestrator exists yet.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

from arkali.kernel.contracts.error_base import AuthoritativeSourceError

#: Where each declaration lives. File LOCATIONS only — the stages themselves
#: are read out of the documents, never written here.
MASTER_SPEC_RELPATH: Final[str] = "docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md"
BUILD_PROTOCOL_RELPATH: Final[str] = "docs/CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md"

#: The section each document declares its pipeline under. Unnumbered headings,
#: at any level, bounded to the next heading so a later section's sentence
#: cannot be mistaken for the declaration.
_MS_SECTION: Final[re.Pattern[str]] = re.compile(
    r"^#+\s*Root-Cause and Convergence Engine\s*$(?P<body>.*?)(?=^#+\s|\Z)",
    re.M | re.S,
)
_BP_SECTION: Final[re.Pattern[str]] = re.compile(
    r"^#+\s*Failure protocol\s*$(?P<body>.*?)(?=^#+\s|\Z)", re.M | re.S
)

#: The declaration itself: a run of stage names joined by the canonical arrow
#: (U+2192), the same character `ARKALI_HANDOFF.md` uses for an orchestration
#: path. One arrow is the floor — a chain with none would not be a sequence.
_CHAIN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<line>[^\n→]+(?:→[^\n→]+)+)\.?\s*$", re.M
)

_MINIMUM_STAGES: Final[int] = 2


def _words(name: str) -> tuple[str, ...]:
    return tuple(part for part in re.split(r"\W+", name.lower()) if part)


def _refines(shorter: str, longer: str) -> bool:
    """Whether `longer` is the unabbreviated form of `shorter`.

    Identical in shape to `harness_elements._refines`: word-wise, derived from
    the two spellings themselves rather than from a table.
    """
    left, right = _words(shorter), _words(longer)
    if not left or len(left) > len(right):
        return False
    return all(
        full.startswith(part) for part, full in zip(left, right, strict=False)
    )


def _chain_in(text: str, section: re.Pattern[str], what: str, source: str) -> tuple[str, ...]:
    matched = section.search(text)
    if matched is None:
        raise AuthoritativeSourceError(
            f"no {what} section; refusing to invent the pipeline stages",
            source=source,
        )
    found = _CHAIN.search(matched.group("body"))
    if found is None:
        raise AuthoritativeSourceError(
            f"the {what} section declares no stage chain", source=source
        )
    stages = tuple(
        part.strip().rstrip(".").strip() for part in found.group("line").split("→")
    )
    if len(stages) < _MINIMUM_STAGES:
        raise AuthoritativeSourceError(
            f"the {what} stage chain carries {len(stages)} stage(s); a "
            "pipeline with nothing to skip would pass vacuously",
            source=source,
        )
    return stages


class FailureProtocolVocabulary:
    """Both canonical pipeline declarations, and their reconciliation attempt.

    Construct with `load`. `stages()` succeeds only when the two documents
    reconcile under the harness-element algorithm; when they do not, the
    documents themselves — via `ms_stages()` and `bp_stages()` — remain
    readable so a caller can see exactly what each one declares.
    """

    def __init__(
        self, ms_stages: tuple[str, ...], bp_stages: tuple[str, ...], sources: tuple[str, str]
    ) -> None:
        self._ms_stages = ms_stages
        self._bp_stages = bp_stages
        self.sources = sources

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> FailureProtocolVocabulary:
        ms_path = repo_root / MASTER_SPEC_RELPATH
        bp_path = repo_root / BUILD_PROTOCOL_RELPATH
        for path in (ms_path, bp_path):
            if not path.is_file():
                raise AuthoritativeSourceError(
                    "canonical failure-protocol document not found", source=str(path)
                )
        ms_stages = _chain_in(
            ms_path.read_text(encoding="utf-8"),
            _MS_SECTION,
            "MS Root-Cause and Convergence Engine",
            str(ms_path),
        )
        bp_stages = _chain_in(
            bp_path.read_text(encoding="utf-8"),
            _BP_SECTION,
            "BP Failure protocol",
            str(bp_path),
        )
        return cls(ms_stages, bp_stages, (str(ms_path), str(bp_path)))

    def ms_stages(self) -> tuple[str, ...]:
        """MS §Root-Cause's declared stage chain, exactly as written."""
        return self._ms_stages

    def bp_stages(self) -> tuple[str, ...]:
        """BP §Failure protocol's declared stage chain, exactly as written."""
        return self._bp_stages

    def stages(self) -> tuple[str, ...]:
        """One reconciled stage list, or a refusal. Never a preference.

        Identical algorithm to `HarnessElementAuthority._reconcile`: the two
        declarations must agree in count, and at each position one name must
        be a word-wise abbreviation of the other.
        """
        ms, bp = self._ms_stages, self._bp_stages
        if len(ms) != len(bp):
            raise AuthoritativeSourceError(
                f"MS declares {len(ms)} root-cause stages and BP declares "
                f"{len(bp)} failure-protocol stages; they must agree before "
                "any pipeline can be judged followed end to end "
                f"(MS: {list(ms)}; BP: {list(bp)})",
                source=" + ".join(self.sources),
            )
        agreed: list[str] = []
        for index, (left, right) in enumerate(zip(ms, bp, strict=True)):
            if _refines(right, left):
                agreed.append(left)
            elif _refines(left, right):
                agreed.append(right)
            else:
                raise AuthoritativeSourceError(
                    f"pipeline stage {index} is declared {left!r} (MS) and "
                    f"{right!r} (BP); neither is an abbreviation of the "
                    "other, so the canonical documents disagree and no "
                    "stage list can be derived",
                    source=" + ".join(self.sources),
                )
        return tuple(agreed)
