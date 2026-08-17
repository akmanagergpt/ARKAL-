"""F-0034: acceptance is declared, never inferred from prose.

The predecessor decided a phase's acceptance with
`"ACCEPTED" in status_text.upper() and "NOT ACCEPTED" not in status_text.upper()`.
Two conjoined mistakes: the search ran over the whole free-text cell, and
acceptance came from the *absence* of a negation rather than from an affirmative
declaration. Writing "Prerequisites Phases 5 and 6 are accepted" on Phase 7's own
row therefore accepted Phase 7 - a fail-**open** in the acceptance path, since
`checker.check_prerequisites` reads the same property.

These controls are the reproduction fixtures, kept. Every synthetic case below
failed against the predecessor and passes now; the five marked `WAS_FALSE_ACCEPT`
are the ones that returned True when they must return False.

NOTHING HERE HARD-CODES WHICH PHASE IS ACCEPTED. That is the F-0029/F-0031
family - a control that names today's phase numbers expires the moment the build
moves. The live-row controls assert *properties* (every row parses; prose cannot
move a verdict; prerequisites of an accepted phase are accepted; exactly one
phase is unlocked and unaccepted), all of which stay true at every future phase.
"""

from __future__ import annotations

import pathlib

import pytest

from arkali.acceptance.governance_state import (
    DeclaredPhaseState,
    GovernanceState,
    PhaseStatus,
    parse_declared_state,
)
from arkali.kernel.contracts.errors import AuthoritativeSourceError

REPO = pathlib.Path(__file__).resolve().parents[3]

#: Sentences that must be inert. Each contains a token the predecessor matched.
INERT_PROSE = (
    " Prerequisites Phases 5 and 6 are accepted.",
    " Phase 6 was recorded MACHINE-ACCEPTED in PHASE_HISTORY.md.",
    " This cell mentions `PhaseStatus.is_accepted` by name.",
    " An earlier revision of this phase was NOT ACCEPTED.",
    " See the accepted ADRs and the accepted human-gate records.",
    " ← next work. The matrix Gate column is empty.",
)


def accepted(text: str) -> bool:
    return PhaseStatus.parse("X", "title", text).is_accepted


class TestProseCannotDecideAcceptance:
    """The five cases that were false accepts, plus their honest neighbours."""

    @pytest.mark.parametrize(
        "status_text",
        [
            # WAS_FALSE_ACCEPT - the wording that actually shipped and was
            # caught during Phase 6 post-acceptance recording.
            "**UNLOCKED — NOT_STARTED** ← next work. Both prerequisites, Phases 5 "
            "and 6, are accepted; the matrix Gate column is empty",
            # WAS_FALSE_ACCEPT - unrelated use of the word.
            "**UNLOCKED — NOT_STARTED**. Prerequisites Phases 5 and 6 are accepted",
            # WAS_FALSE_ACCEPT - quoted history.
            "**UNLOCKED — NOT_STARTED**. Phase 6 was recorded MACHINE-ACCEPTED",
            # WAS_FALSE_ACCEPT - naming the parser's own identifier.
            "**UNLOCKED — NOT_STARTED** ← next work. This cell deliberately avoids "
            "the word that `PhaseStatus.is_accepted` matches on",
            # WAS_FALSE_ACCEPT - the underscore spelling F-0029's note warned of.
            "**UNLOCKED — IN PROGRESS, NOT_ACCEPTED**",
            # Already correct, kept so the control covers the honest neighbours.
            "**UNLOCKED — NOT_STARTED**. This phase is not accepted",
            "**UNLOCKED — IN PROGRESS, NOT ACCEPTED**. Phase 5 is accepted",
            "**UNLOCKED — NOT_STARTED**",
            "**LOCKED**",
        ],
    )
    def test_a_non_accepting_row_is_never_accepted(self, status_text: str) -> None:
        assert accepted(status_text) is False

    @pytest.mark.parametrize(
        "status_text",
        [
            "**MACHINE-ACCEPTED**",
            "**MACHINE-ACCEPTED** (66 tests, 8 gates, mypy clean)",
            "**ACCEPTED**",
            "**ACCEPTED — HUMAN GATE 1 granted**",
        ],
    )
    def test_a_canonical_acceptance_is_accepted(self, status_text: str) -> None:
        assert accepted(status_text) is True

    def test_the_negation_alone_never_grants_acceptance(self) -> None:
        """Removing 'NOT ACCEPTED' from a row must not accept it.

        The predecessor's rule was `has ACCEPTED and not has NOT ACCEPTED`, so
        deleting the negation from any row containing the token flipped it to
        accepted. Acceptance now needs an affirmative head, so it does not.
        """
        row = "**UNLOCKED — IN PROGRESS, NOT ACCEPTED**"
        assert accepted(row) is False
        assert accepted(row.replace(" — IN PROGRESS, NOT ACCEPTED", "")) is False


class TestFailClosed:
    """Unreadable or self-contradictory state is refused, never defaulted."""

    @pytest.mark.parametrize(
        "status_text",
        [
            "",
            "   ",
            "tbd",
            "**PENDING**",
            "**PROBABLY ACCEPTED**",
            "**MACHINE-ACCEPTED — NOT ACCEPTED**",
            "**LOCKED — ACCEPTED**",
            "**NOT_STARTED — MACHINE-ACCEPTED**",
        ],
    )
    def test_malformed_or_contradictory_state_is_refused(
        self, status_text: str
    ) -> None:
        with pytest.raises(AuthoritativeSourceError):
            parse_declared_state(status_text, "X")

    def test_a_refusal_names_the_authoritative_source(self) -> None:
        with pytest.raises(AuthoritativeSourceError) as raised:
            parse_declared_state("**PENDING**", "9")
        assert "BUILD_STATE.md" in str(raised.value)

    def test_an_unreadable_row_stops_the_whole_load(self, tmp_path) -> None:  # noqa: ANN001
        """A malformed cell must break the checker, not be quietly skipped."""
        docs = tmp_path / "docs" / "build"
        docs.mkdir(parents=True)
        source = (REPO / "docs/build/BUILD_STATE.md").read_text(encoding="utf-8")
        broken = source.replace(
            "| 1 | Repository Bootstrap | **MACHINE-ACCEPTED**",
            "| 1 | Repository Bootstrap | **PROBABLY FINE**",
            1,
        )
        assert broken != source, "fixture anchor no longer matches BUILD_STATE.md"
        (docs / "BUILD_STATE.md").write_text(broken, encoding="utf-8")
        for relative in ("docs/acceptance/HUMAN_GATE_RECORDS.md",
                         "docs/build/OPEN_BLOCKERS.md",
                         "docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md"):
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text((REPO / relative).read_text(encoding="utf-8"),
                              encoding="utf-8")
        with pytest.raises(AuthoritativeSourceError):
            GovernanceState.load(tmp_path)


class TestDeclaredStateVocabulary:
    def test_only_affirmative_states_grant_acceptance(self) -> None:
        granting = {s for s in DeclaredPhaseState if s.grants_acceptance}
        assert granting == {
            DeclaredPhaseState.ACCEPTED, DeclaredPhaseState.MACHINE_ACCEPTED
        }

    def test_unlocked_is_not_read_as_locked(self) -> None:
        """`"LOCKED" in "UNLOCKED"` is why this property existed and lied."""
        unlocked = PhaseStatus.parse("X", "t", "**UNLOCKED — NOT_STARTED**")
        assert unlocked.is_unlocked is True
        assert unlocked.is_locked is False
        locked = PhaseStatus.parse("X", "t", "**LOCKED**")
        assert locked.is_locked is True
        assert locked.is_unlocked is False

    def test_an_accepted_phase_is_not_reported_unlocked(self) -> None:
        assert PhaseStatus.parse("X", "t", "**MACHINE-ACCEPTED**").is_unlocked is False


@pytest.fixture(scope="module")
def state() -> GovernanceState:
    return GovernanceState.load(REPO)


class TestLiveRowsKeepTheirMeaning:
    """Properties of the real BUILD_STATE rows. No phase number is named."""

    def test_every_live_row_parses_into_the_canonical_vocabulary(
        self, state: GovernanceState
    ) -> None:
        assert state.phases, "no phase rows parsed"
        for phase_id, status in state.phases.items():
            assert isinstance(status.declared_state, DeclaredPhaseState), phase_id

    @pytest.mark.parametrize("sentence", INERT_PROSE)
    def test_appending_prose_to_any_live_row_changes_nothing(
        self, state: GovernanceState, sentence: str
    ) -> None:
        """The property the defect violated, asserted against real rows."""
        for phase_id, status in state.phases.items():
            extended = PhaseStatus.parse(
                phase_id, status.title, status.status_text + sentence
            )
            assert extended.declared_state is status.declared_state, phase_id
            assert extended.is_accepted is status.is_accepted, phase_id

    def test_truncating_prose_from_any_live_row_changes_nothing(
        self, state: GovernanceState
    ) -> None:
        """Only the declared head carries meaning, so the tail is removable."""
        for phase_id, status in state.phases.items():
            head, marker, _ = status.status_text.partition("**")
            if not marker:
                continue
            declared, closing, _ = status.status_text[len(head) + 2:].partition("**")
            assert closing, phase_id
            trimmed = PhaseStatus.parse(phase_id, status.title, f"**{declared}**")
            assert trimmed.is_accepted is status.is_accepted, phase_id

    def test_exactly_one_phase_is_unlocked_and_unaccepted(
        self, state: GovernanceState
    ) -> None:
        """The invariant `check_handoff` derives the current work phase from."""
        current = [
            pid for pid, s in state.phases.items()
            if s.is_unlocked and not s.is_accepted
        ]
        assert len(current) == 1, current

    def test_the_current_work_phase_derivation_is_owned_by_one_place(
        self, state: GovernanceState
    ) -> None:
        current = state.current_work_phase()
        unlocked = [
            pid for pid, s in state.phases.items()
            if s.is_unlocked and not s.is_accepted
        ]
        assert current == unlocked[0]

    def test_an_ambiguous_answer_is_reported_as_none_not_guessed(self) -> None:
        """Two unlocked phases must not resolve to whichever sorts first."""
        rows = {
            "6": PhaseStatus.parse("6", "t", "**UNLOCKED — NOT_STARTED**"),
            "7": PhaseStatus.parse("7", "t", "**UNLOCKED — NOT_STARTED**"),
        }
        ambiguous = GovernanceState(
            rows, {}, {"7": "HUMAN_GATE_2"}, frozenset(), (), pathlib.Path(".")
        )
        assert ambiguous.current_work_phase() is None

    def test_every_prerequisite_of_an_accepted_phase_is_accepted(
        self, state: GovernanceState
    ) -> None:
        """An independent oracle: the dependency matrix, not the status cells.

        If the parser ever over-accepted a phase whose prerequisites are not
        themselves accepted, this fails without naming any phase.
        """
        checked = 0
        for phase_id, status in state.phases.items():
            if not status.is_accepted or phase_id not in state.prerequisites:
                continue
            for dependency in state.prerequisites_of(phase_id):
                if dependency not in state.phases:
                    continue
                checked += 1
                assert state.phase(dependency).is_accepted, (
                    f"{phase_id} is accepted but its prerequisite "
                    f"{dependency} is not"
                )
        assert checked >= 3, "the invariant evaluated too few real edges"


class TestNoConsumerRestatesTheRule:
    """F-0034's real lesson: one rule, one place.

    The parser can be perfect and the defect still return, because any consumer
    may search `status_text` for a state token instead of asking. `check_handoff`
    did exactly that. This asserts that no module outside the owning one
    classifies a phase by looking for a state token in the prose.
    """

    #: Every module that reads governance state, plus the validator scripts.
    SUBJECTS = (
        *sorted((REPO / "backend/arkali").rglob("*.py")),
        *sorted((REPO / "scripts").glob("*.py")),
    )
    OWNER = REPO / "backend/arkali/acceptance/governance_state.py"
    #: Tokens whose presence in prose must never decide a phase's state.
    STATE_TOKENS = ("ACCEPTED", "UNLOCKED", "LOCKED", "NOT_STARTED")

    def test_the_subject_set_is_not_empty(self) -> None:
        assert len(self.SUBJECTS) > 50, "the sweep found suspiciously few modules"
        assert self.OWNER in self.SUBJECTS

    def test_no_module_outside_the_owner_tests_status_text_for_a_state(
        self,
    ) -> None:
        offenders: list[str] = []
        for path in self.SUBJECTS:
            if path == self.OWNER:
                continue
            source = path.read_text(encoding="utf-8")
            for line_no, line in enumerate(source.splitlines(), 1):
                code = line.split("#", 1)[0]
                if "status_text" not in code:
                    continue
                if any(token in code for token in self.STATE_TOKENS):
                    offenders.append(
                        f"{path.relative_to(REPO)}:{line_no}: {line.strip()}"
                    )
        assert offenders == [], (
            "a consumer is classifying a phase by searching its prose instead "
            f"of reading the declared state: {offenders}"
        )

    def test_the_owner_really_does_classify(self) -> None:
        """Not vacuous: the rule exists, it is just confined to one module."""
        source = self.OWNER.read_text(encoding="utf-8")
        assert "_STATE_SPELLINGS" in source
        assert "grants_acceptance" in source
