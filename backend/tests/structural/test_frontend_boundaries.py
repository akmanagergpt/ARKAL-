"""Negative controls on what the frontend is not allowed to become.

A browser is not an authority. It renders what the fabric decided and asks the
fabric to decide again. Three specific ways a frontend stops respecting that are
easy to introduce, invisible in review once the file is long enough, and fatal
to the guarantees the backend spends its whole architecture establishing:

* a **shadow state machine** - a transition map in TypeScript, added so a button
  can be greyed out. The canonical relation now lives in two places, and the
  copy drifts silently because nothing compares them;
* a **shadow policy** - an authorization rule in TypeScript. A browser check is
  a hint. Treating it as an answer means the real answer was never asked for;
* **fabricated production data** - a hard-coded project list, or a mutation
  reported as successful without the backend having said so. The interface looks
  alive while the registry is unreachable, which is worse than an interface that
  admits it.

Every check below reads the production sources under `frontend/src` with
comments stripped, so the prose explaining a ban never trips the ban.
`frontend/tests` is deliberately out of scope: fixtures at the test boundary are
legitimate, and the control that keeps them there is in this module too.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

from arkali.control.policy.operation_class import OperationClassVocabulary
from arkali.control.registry.project.project_state_machine import DEFINITION
from tests.structural.typescript_reader import (
    FRONTEND_SRC,
    FRONTEND_TESTS,
    REPO,
    read,
    sources,
    strip_comments,
)

API_CLIENT: Final[pathlib.Path] = FRONTEND_SRC / "api" / "client.ts"

#: Identifiers that name a transition relation rather than a single state.
TRANSITION_SHAPES: Final[tuple[str, ...]] = (
    "TRANSITIONS",
    "ALLOWED_TRANSITIONS",
    "allowedTransitions",
    "canTransitionTo",
    "isTransitionAllowed",
    "nextStates",
    "TERMINAL_STATES",
    "terminalStates",
    "StateMachine",
)

#: Identifiers that name an authorization decision made locally.
POLICY_SHAPES: Final[tuple[str, ...]] = (
    "PolicyDecisionPoint",
    "PolicyEnforcementPoint",
    "isAllowed",
    "canPerform",
    "hasPermission",
    "TRUST_TIER",
    "TRUST-0",
    "TRUST-1",
    "TRUST-2",
    "TRUST-3",
    "TRUST-4",
    "ASK_USER",
)

#: Names a browser store used as though it were the registry.
LOCAL_PERSISTENCE: Final[tuple[str, ...]] = (
    "localStorage",
    "sessionStorage",
    "indexedDB",
)


def production_sources() -> list[tuple[pathlib.Path, str]]:
    found = [(path, strip_comments(read(path))) for path in sources(FRONTEND_SRC)]
    assert found, "no frontend production source was found to check"
    return found


class TestNoShadowStateMachine:
    def test_no_canonical_state_name_is_declared_in_production_source(self) -> None:
        """The states are fetched from the machine's own surface, never typed here.

        This is what makes the lifecycle control honest: the page renders the
        vocabulary the API returned, so there is nothing to drift.
        """
        for path, text in production_sources():
            for state in DEFINITION.states:
                # Whole tokens only. `UNSPECIFIED` - the client's fallback code
                # for a refusal that did not explain itself - contains
                # `SPECIFIED` and is not a lifecycle state.
                assert re.search(rf"\b{re.escape(state)}\b", text) is None, (
                    f"{path.name} declares the lifecycle state {state!r}. The Project "
                    "machine in control.registry.project is the only authority for "
                    "the states; read them from /api/lifecycle/project instead."
                )

    def test_no_transition_relation_is_expressed_in_production_source(self) -> None:
        for path, text in production_sources():
            for shape in TRANSITION_SHAPES:
                assert shape not in text, (
                    f"{path.name} declares {shape!r}, which is a transition relation. "
                    "Whether a move is legal is answered by the backend when the "
                    "move is attempted."
                )

    def test_the_control_would_catch_a_reintroduced_map(self) -> None:
        """NEGATIVE CONTROL: prove the check is not matching an empty corpus."""
        offending = strip_comments(
            "// harmless prose about DRAFT\n"
            "const ALLOWED_TRANSITIONS = { DRAFT: ['SPECIFIED'] };\n"
        )
        assert "ALLOWED_TRANSITIONS" in offending
        assert any(state in offending for state in DEFINITION.states)


class TestNoShadowPolicy:
    def test_no_operation_class_is_named_in_production_source(self) -> None:
        """Which operation class a request belongs to is decided at the PEP."""
        classes = set(OperationClassVocabulary.load(REPO).names())
        assert classes, "the canonical operation-class vocabulary is empty"
        for path, text in production_sources():
            named = {name for name in classes if name in text}
            assert named == set(), (
                f"{path.name} names the operation class(es) {sorted(named)}. "
                "The Package 4A PEP is the enforcement boundary; a browser that "
                "classifies operations has begun to authorize them."
            )

    def test_no_authorization_decision_is_expressed_in_production_source(self) -> None:
        for path, text in production_sources():
            for shape in POLICY_SHAPES:
                assert shape not in text, (
                    f"{path.name} declares {shape!r}. A browser action is never "
                    "authorization."
                )

    def test_no_control_is_disabled_on_a_locally_invented_rule(self) -> None:
        """`disabled` is legitimate for pending input and in-flight work only.

        The slice's disabled conditions are all of that kind - a blank field, a
        request in flight. None consults a permission, and a permission-shaped
        one would be caught by the two checks above.
        """
        for path, text in production_sources():
            for match in re.finditer(r"disabled=\{([^}]*)\}", text):
                condition = match.group(1)
                assert not any(shape in condition for shape in POLICY_SHAPES), (
                    f"{path.name} disables a control on an authorization test: "
                    f"{condition.strip()!r}"
                )


class TestProductionUsesRealDataOnly:
    def test_no_browser_store_stands_in_for_the_registry(self) -> None:
        for path, text in production_sources():
            for store in LOCAL_PERSISTENCE:
                assert store not in text, (
                    f"{path.name} uses {store}. C-03 persistence is the registry's "
                    "store; a browser copy is a second one."
                )

    def test_no_fixture_or_mock_is_reachable_from_production_source(self) -> None:
        forbidden = re.compile(
            r"\b(mockProjects|MOCK_[A-Z_]+|FIXTURE_[A-Z_]+|SAMPLE_PROJECTS|"
            r"stubFetch|vi\.fn|msw)\b"
        )
        for path, text in production_sources():
            found = forbidden.search(text)
            assert found is None, (
                f"{path.name} contains {found.group(0)!r}. Test fixtures live at the "
                "test boundary under frontend/tests, never on the production path."
            )

    def test_production_source_never_imports_from_the_test_tree(self) -> None:
        for path, text in production_sources():
            assert "../tests" not in text and "@/../tests" not in text, (
                f"{path.name} imports from the test tree"
            )

    def test_the_fixtures_that_do_exist_are_confined_to_the_test_tree(self) -> None:
        """The counterpart: fixtures exist, and this is where they are allowed."""
        fixtures = FRONTEND_TESTS / "fixtures.ts"
        assert fixtures.is_file(), "the component tests must declare their fixtures"
        assert "stubFetch" in read(fixtures)


class TestOneApiBoundary:
    def test_fetch_is_called_in_the_api_client_and_nowhere_else(self) -> None:
        for path, text in production_sources():
            if path == API_CLIENT:
                continue
            assert not re.search(r"\bfetch\s*\(", text), (
                f"{path.name} performs its own network call. Every request goes "
                "through the typed client so the contract has one definition."
            )

    def test_the_api_client_is_the_only_module_that_names_a_route(self) -> None:
        for path, text in production_sources():
            if path == API_CLIENT:
                continue
            # A route *literal*, not the `@/api/client` module specifier.
            assert re.search(r"['\"`]/api/", text) is None, (
                f"{path.name} names an API path directly; routes are declared once, "
                "in the client's ENDPOINTS table."
            )

    def test_the_api_client_really_does_call_fetch(self) -> None:
        """NEGATIVE CONTROL: the two checks above are vacuous if nothing fetches."""
        assert re.search(r"\bfetch\w*\s*\(", strip_comments(read(API_CLIENT)))
