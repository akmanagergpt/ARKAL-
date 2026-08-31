"""Negative controls for phase-transition residue in the handoff (F-0048).

When a phase moves from in-progress to ACCEPTED, the §12 refresh must complete
the transition in the LIVE prose as well as in the claim block. It did not: the
accepted phase's summary row kept its "packages N of M complete / none
discharged / cumulative stays X" tail, and the tail of NEXT EXACT ACTION kept
instructing the reader to derive the PREVIOUS phase's requirement rows, contract
and denominator - inside the live brief for the next phase.

Every existing control was scoped to the claim block or to the current-phase
section, so neither place was read. These controls read both.

Every subject is DERIVED - the accepted set and each phase's discharge from the
accepted traceability records, the current phase from `GovernanceState`, the
denominator from the register - so none of them names a phase, a requirement, a
count or a contract, and none can expire as the build advances (F-0021).
"""

from __future__ import annotations

import re
import types

import pytest

from tests.governance.handoff_harness import (
    HANDOFF,
    REPO,
    drift_names,
    load_module,
    load_validator,
    replace_once,
)


@pytest.fixture(scope="module")
def validator() -> types.ModuleType:
    return load_validator()


@pytest.fixture(scope="module")
def handoff_text() -> str:
    return HANDOFF.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def transition_module() -> types.ModuleType:
    load_validator()  # puts scripts/ and backend/ on sys.path
    return load_module(REPO / "scripts" / "handoff_transition.py")


@pytest.fixture(scope="module")
def truth(transition_module: types.ModuleType) -> dict:
    return transition_module.transition_truth(REPO)


def current_state_section(text: str, transition: types.ModuleType) -> str:
    """The live current-state section, fetched through the validator's own scope.

    Unscoped, `re.search` over the whole document finds §4/§11's historical
    "cumulative verified stays N" rows before it ever reaches §3's live one -
    the same scoping mistake F-0048 already fixed in the validator itself.
    """
    markdown = load_module(REPO / "scripts" / "handoff_markdown.py")
    body = markdown.section(text, transition.CURRENT_STATE_HEADING)
    assert body.strip(), "the current-state section could not be located"
    return body


def discharging_phase(truth: dict) -> tuple[str, tuple[str, ...]]:
    """An accepted phase whose record discharges something. Derived, not named."""
    found = sorted((p, ids) for p, ids in truth["discharged"].items() if ids)
    assert found, "no accepted phase discharges anything; controls would be vacuous"
    return found[-1]


def row_for(text: str, phase: str) -> str:
    row = next(
        (ln for ln in text.splitlines()
         if re.match(rf"^\|\s*Phase {re.escape(phase)}\s*\|", ln.strip())),
        None,
    )
    assert row is not None, f"the live summary has no row for phase {phase}"
    return row


class TestAnAcceptedPhaseRowMustCompleteItsTransition:
    def test_claiming_its_requirements_undischarged_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        phase, _ = discharging_phase(truth)
        row = row_for(handoff_text, phase)
        mutated = replace_once(
            handoff_text, row, row + " None is discharged yet."
        )
        assert any("does not claim its requirements undischarged" in d
                   for d in drift_names(validator, mutated))

    def test_describing_its_packages_as_incomplete_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        phase, _ = discharging_phase(truth)
        row = row_for(handoff_text, phase)
        mutated = replace_once(
            handoff_text, row, row + " Packages 1 and 2 of 4 are complete."
        )
        assert any("does not describe its packages as incomplete" in d
                   for d in drift_names(validator, mutated))

    def test_describing_an_accepted_phase_as_in_progress_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        phase, _ = discharging_phase(truth)
        row = row_for(handoff_text, phase)
        mutated = replace_once(handoff_text, row, row + " IN PROGRESS.")
        assert any("does not describe an accepted phase as in progress" in d
                   for d in drift_names(validator, mutated))

    def test_a_deleted_row_cannot_evade_reconciliation(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        """ANTI-VACUITY. The first draft was defeated by exactly this: removing
        the row removed the thing the controls would have judged."""
        phase, _ = discharging_phase(truth)
        row = row_for(handoff_text, phase)
        mutated = replace_once(handoff_text, row + "\n", "")
        assert any("carries a row for every phase that discharged anything" in d
                   for d in drift_names(validator, mutated))

    def test_a_cumulative_total_below_the_accepted_records_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict,
        transition_module: types.ModuleType,
    ) -> None:
        derivable = sum(len(ids) for ids in truth["discharged"].values())
        assert derivable > 0
        # Scoped to §3, exactly as `check_accepted_rows` reads it - not the
        # whole document, where a bare `re.search` would land on a historical
        # §4/§11 row instead of the live statement this control must mutate.
        section_text = current_state_section(handoff_text, transition_module)
        stated = re.search(
            r"cumulative verified\s+(?:stays|is|remains)\s+\*{0,2}(\d+)\*{0,2}",
            section_text, re.IGNORECASE,
        )
        assert stated is not None, "the live current-state section states no cumulative total"
        mutated = replace_once(handoff_text, stated.group(0),
                               f"cumulative verified stays {derivable - 1}")
        assert any("is not below the accepted records" in d
                   for d in drift_names(validator, mutated))


class TestTheWholeBriefMustTargetTheCurrentPhase:
    def test_a_discharged_requirement_offered_as_a_subject_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        """The exact residue: the previous phase's ids left in the live brief."""
        _, ids = discharging_phase(truth)
        stale = next(r for r in ids if r not in truth["current_denominator"])
        marker = "## 9. Next exact action"
        assert marker in handoff_text
        mutated = replace_once(
            handoff_text, marker, f"{marker}\n\nFirst derive the rows for {stale}."
        )
        assert any("presents no discharged requirement as a continuation subject" in d
                   for d in drift_names(validator, mutated))

    def test_a_brief_that_never_names_the_current_phase_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        current = truth["current"]
        assert current is not None
        head, _, tail = handoff_text.partition("## 9. Next exact action")
        mutated = head + "## 9. Next exact action" + re.sub(
            rf"\bPhase {re.escape(current)}\b", "the next phase", tail
        )
        assert "the next-exact-action section names the current work phase" in \
            drift_names(validator, mutated)

    def test_a_wrong_denominator_in_the_brief_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict
    ) -> None:
        stated = re.search(
            r"denominator\s*[-—–:]*\s*(\w+)\s+requirements?", handoff_text, re.I
        )
        assert stated is not None, "the live brief states no denominator"
        # A numeral the control can read, and deliberately not the real size.
        wrong = "nine" if len(truth["current_denominator"]) != 9 else "two"
        mutated = replace_once(
            handoff_text, stated.group(0),
            stated.group(0).replace(stated.group(1), wrong)
        )
        assert any("states the current phase's denominator" in d
                   for d in drift_names(validator, mutated))


class TestBuildStateCarriesItsOwnNextExactAction:
    """F-0050 (`docs/build/OPEN_BLOCKERS.md`): `docs/build/BUILD_STATE.md`
    carries its own, separate "Next exact action" section -- unnumbered,
    unlike the handoff's "## 9. Next exact action" -- and nothing checked
    it. It named `Phase 14` for sixteen real phases after the current work
    phase moved on, with nothing to catch it: every existing control here
    was scoped to the handoff alone. Same derivation, same function
    (`check_next_action`, generalised with a `label` so two documents'
    findings are told apart), applied a second time -- not a second
    mechanism, and nothing here names a phase or a requirement id.
    """

    def test_the_real_build_state_names_the_current_work_phase(
        self, validator: types.ModuleType, handoff_text: str, truth: dict,
    ) -> None:
        """The real, current document -- proves the live fix, not a mock."""
        current = truth["current"]
        assert current is not None
        drift = drift_names(validator, handoff_text)
        assert not any(d.startswith("BUILD_STATE.md: ") for d in drift), drift

    def test_a_build_state_brief_naming_a_stale_phase_is_detected(
        self, validator: types.ModuleType, transition_module: types.ModuleType,
        truth: dict,
    ) -> None:
        """Reproduces the exact real defect found: BUILD_STATE.md's own
        unnumbered heading, naming a phase that is not the current one."""
        current = truth["current"]
        assert current is not None
        stale_phase = "14" if current != "14" else "13"
        synthetic = (
            "## Next exact action\n\n"
            f"**Begin Phase {stale_phase} -- stale by construction for this test.**\n"
        )
        report = validator.Report()
        transition_module.check_next_action(
            REPO, synthetic, truth, report, label="BUILD_STATE.md: ",
        )
        assert any(
            d == "BUILD_STATE.md: the next-exact-action section names the "
                 "current work phase"
            for d in report.drift
        ), report.drift

    def test_a_build_state_brief_naming_the_current_phase_is_not_flagged(
        self, validator: types.ModuleType, transition_module: types.ModuleType,
        truth: dict,
    ) -> None:
        """ANTI-VACUITY: the same shape, naming the real current phase and a
        real denominator, must NOT be flagged -- proves the control above
        fires on the mismatch, not on the document merely existing."""
        current = truth["current"]
        assert current is not None
        synthetic = (
            "## Next exact action\n\n"
            f"**Continue Phase {current}.** denominator: "
            f"{len(truth['current_denominator'])} requirements, all MANDATORY.\n"
        )
        report = validator.Report()
        transition_module.check_next_action(
            REPO, synthetic, truth, report, label="BUILD_STATE.md: ",
        )
        assert report.drift == [], report.drift


class TestTheControlsAreDerived:
    def test_the_module_names_no_phase_requirement_or_contract(
        self, truth: dict
    ) -> None:
        source = (REPO / "scripts" / "handoff_transition.py").read_text("utf-8")
        code = "\n".join(
            ln for ln in source.splitlines()
            if not ln.strip().startswith("#")
        )
        _, _, body = code.partition('"""')
        _, _, body = body.partition('"""')  # drop the module docstring
        assert not re.search(r"ARK-REQ-\d{4}", body), "a requirement id is hard-coded"
        for phase in truth["accepted"]:
            assert f'"{phase}"' not in body, f"phase {phase} is hard-coded"

    def test_truth_follows_the_repository(self, truth: dict) -> None:
        assert truth["current"] is not None
        assert truth["accepted"], "no accepted phase was derived"
        assert truth["discharged"], "no accepted discharge was derived"


_NOT_CONTRADICTED = (
    "the current-phase section is not contradicted by ledger rows or the "
    "live summary"
)


def _inject_after_current_phase_heading(
    text: str, validator: types.ModuleType, marker: str,
) -> str:
    """Force `marker` into the current-phase section's own body, regardless
    of what that section's real prose currently says.

    F-0050. The two controls below used to append their contradiction only
    to the INDEPENDENT source (the live-summary row or the ledger) and rely
    on the current-phase section ALREADY containing "NOT STARTED" / "no
    package exists" wording of its own for the other half of the production
    check's AND. That assumption holds only while a phase's own section is
    still honestly reporting no progress - it silently breaks the moment a
    phase's whole candidate and gate run land before its first handoff
    refresh (exactly Phase 20's real history: the live section jumps
    straight to "candidate complete, gate run, AWAITING_HUMAN_GATE" and
    never once states NOT STARTED), leaving the control permanently unable
    to construct its own precondition and therefore never exercised. Forcing
    the claim in directly - unconditionally, independent of whatever stage
    the real phase happens to be at - is what keeps the mutation a live
    behavioural probe under every lifecycle stage from NOT STARTED through
    ACCEPTED, rather than a bet on the current phase's own honest wording.
    """
    heading = validator._CURRENT_PHASE_HEADING.search(text)
    assert heading is not None, "no current-phase heading to inject after"
    assert marker not in text, "marker already present; mutation would be vacuous"
    injected = text[: heading.end()] + f"\n\n{marker}\n" + text[heading.end():]
    assert marker in injected, "injection did not land"
    return injected


class TestCurrentPhaseSectionIsNotContradictedByItsOwnEvidence:
    """The exact defect this class exists to catch: BUILD_STATE.md's phase-
    status row for the current work phase never advanced past UNLOCKED / NOT
    STARTED across three committed packages, and §8 mirrored that stale cell -
    so the pre-existing "declared state agrees with itself" check passed while
    both sides were wrong. These controls cross-check the current-phase
    section against two INDEPENDENT repository-derived sources instead: the
    accepted-commit-history ledger and the live "Current verified state"
    summary. Nothing here names a phase, a package count or a contract id."""

    def test_the_live_current_phase_section_is_not_contradicted(
        self, validator: types.ModuleType, handoff_text: str,
    ) -> None:
        """The real answer, over the real document."""
        assert _NOT_CONTRADICTED not in drift_names(validator, handoff_text)

    def test_a_not_started_claim_against_ledger_evidence_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict,
    ) -> None:
        """A current-phase section that claims NOT STARTED must be caught the
        moment an INDEPENDENT source — here, the live summary's own row for
        that phase — asserts progress. The NOT STARTED claim is forced into
        the section directly (see `_inject_after_current_phase_heading`)
        rather than assumed present in the section's real prose, so this
        control stays meaningful regardless of which lifecycle stage the
        real current phase's own honest wording happens to be at.
        """
        current = truth["current"]
        # ANTI-VACUITY: the real, unmutated document is not already flagged,
        # so the assertion below proves something about the mutation below,
        # not a pre-existing condition.
        assert _NOT_CONTRADICTED not in drift_names(validator, handoff_text)

        injected = _inject_after_current_phase_heading(
            handoff_text, validator, "STATUS-PROBE: NOT STARTED.",
        )

        row = row_for(handoff_text, current)
        # The production check reads "IN PROGRESS" from WITHIN the row's own
        # cell (bounded by its closing "|"), not from trailing text appended
        # past it - so the mutation must land before that last "|".
        mutated_row = row[: row.rfind("|")] + "IN PROGRESS |"
        assert mutated_row != row, "the live-summary row mutation is a no-op"
        combined = replace_once(injected, row, mutated_row)

        assert _NOT_CONTRADICTED in drift_names(validator, combined)

    def test_a_no_package_exists_claim_against_ledger_evidence_is_detected(
        self, validator: types.ModuleType, handoff_text: str, truth: dict,
    ) -> None:
        """Same contradiction, proven through the OTHER independent source:
        the accepted-commit-history ledger naming the current phase. See
        `test_a_not_started_claim_against_ledger_evidence_is_detected` and
        `_inject_after_current_phase_heading` for why the current-phase
        section's own "no package exists" claim is forced in directly rather
        than assumed present."""
        current = truth["current"]
        assert _NOT_CONTRADICTED not in drift_names(validator, handoff_text)

        injected = _inject_after_current_phase_heading(
            handoff_text, validator,
            "STATUS-PROBE: no package exists for this phase.",
        )

        anchor = "← HEAD at generation"
        assert anchor in handoff_text, "expected the handoff to render the HEAD marker"
        mutated_anchor = f"PHASE {current} package landed {anchor}"
        combined = replace_once(injected, anchor, mutated_anchor)

        assert _NOT_CONTRADICTED in drift_names(validator, combined)
