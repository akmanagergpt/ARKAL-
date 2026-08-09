"""The T10 harness must stay real, or its evidence is worthless.

WHY THIS CONTROL EXISTS. `VERIFICATION_ARCHITECTURE.md` 1.1 puts T10 at
execution level L2 with no substitution permitted, and its substitution policy
is explicit: a tier from T5 upward that substitutes a database, a provider or a
product produces NOT_CONFIGURED, never PASS. A browser journey is the easiest
evidence in the repository to hollow out — intercept the routes, answer them
from a canned body, and every assertion still passes against nothing. The suite
would stay green while proving only that Playwright can read a fixture.

WHAT IS ASSERTED. That the launcher serves the real application over a real file
database, that the journey runs against the production build rather than a
substitute, that no request is intercepted in the browser, and that the negative
path asserts a refusal code the backend actually emits — read from the live
error taxonomy, not transcribed here.
"""

from __future__ import annotations

import ast
import pathlib
import re
from typing import Final

from arkali.control.registry.project.errors import DuplicateIdentity
from arkali.kernel.contracts.state_machine_errors import ForbiddenTransition
from tests.structural.typescript_reader import FRONTEND, REPO, read, strip_comments

LAUNCHER: Final[pathlib.Path] = REPO / "scripts" / "run_command_center.py"
PW_CONFIG: Final[pathlib.Path] = FRONTEND / "playwright.config.ts"
JOURNEY: Final[pathlib.Path] = (
    FRONTEND / "tests" / "e2e" / "project-registry.spec.ts"
)

#: Ways a browser test stops talking to the backend without looking like it.
INTERCEPTION: Final[tuple[str, ...]] = (
    "page.route(",
    "context.route(",
    "routeFromHAR",
    "fulfill(",
    "setContent(",
    "addInitScript(",
)


def launcher_tree() -> ast.Module:
    return ast.parse(LAUNCHER.read_text(encoding="utf-8"))


def called(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


class TestTheLauncherServesTheRealApplication:
    def test_it_builds_no_application_of_its_own(self) -> None:
        tree = launcher_tree()
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert "arkali.surfaces.command.app" in imported, (
            "the E2E launcher does not import the real Command Center factory"
        )
        assert "create_app" in called(tree)
        assert "FastAPI" not in called(tree), (
            "the launcher constructs an application of its own; the journey would "
            "then be exercising a second surface, not the one that ships."
        )

    def test_it_uses_the_real_engine_and_the_real_migration_chain(self) -> None:
        tree = launcher_tree()
        names = called(tree)
        assert "create_persistence_engine" in names
        assert "sqlite_url" in names
        assert "upgrade" in names, (
            "the schema is not built by the real Alembic chain"
        )
        assert "create_engine" not in names

    def test_it_cannot_serve_an_in_memory_database(self) -> None:
        """NEGATIVE CONTROL: an in-memory database unearns every persistence claim.

        Nothing survives a reload in `:memory:`, so the journey's whole
        persistence argument would collapse while still reporting PASS.
        """
        source = LAUNCHER.read_text(encoding="utf-8")
        assert ":memory:" not in source
        assert "mkdir" in source, "the launcher does not create a real file location"

    def test_it_binds_loopback_by_default(self) -> None:
        assert '"127.0.0.1"' in LAUNCHER.read_text(encoding="utf-8")


class TestTheJourneyRunsAgainstTheRealStack:
    def test_the_config_starts_the_real_api_and_the_production_build(self) -> None:
        config = strip_comments(read(PW_CONFIG))
        assert "run_command_center.py" in config, (
            "the journey does not start the real backend"
        )
        assert "vite preview" in config, (
            "the journey does not run against the production build"
        )
        assert "vite build" in config

    def test_the_run_starts_from_an_empty_registry(self) -> None:
        """Otherwise a stale row could satisfy the persistence assertions."""
        assert "--fresh" in strip_comments(read(PW_CONFIG))
        assert "--fresh" in LAUNCHER.read_text(encoding="utf-8")

    def test_the_journey_intercepts_no_request(self) -> None:
        """NEGATIVE CONTROL: the T10 substitution ban, enforced not trusted."""
        journey = strip_comments(read(JOURNEY))
        for form in INTERCEPTION:
            assert form not in journey, (
                f"the browser journey uses {form!r}, which replaces the backend. "
                "VERIFICATION_ARCHITECTURE 1.1 makes a substituting T10 run "
                "NOT_CONFIGURED, never PASS."
            )

    def test_the_journey_really_drives_a_browser(self) -> None:
        journey = strip_comments(read(JOURNEY))
        assert "@playwright/test" in journey
        assert "page.goto(" in journey
        assert "page.reload()" in journey, (
            "nothing in the journey proves state survives a reload"
        )
        assert "browser.newContext()" in journey, (
            "nothing in the journey proves state survives a fresh browser profile"
        )

    def test_the_journey_covers_the_required_chain(self) -> None:
        """Create, read, revision, transition, reload, verify - all of it."""
        journey = strip_comments(read(JOURNEY))
        for step in (
            "register project",
            "record revision",
            "request transition",
            "localStorage",
        ):
            assert step in journey, f"the journey never exercises {step!r}"

    def test_the_negative_path_asserts_a_code_the_backend_really_emits(self) -> None:
        """The refusal codes are read from the live taxonomy, never transcribed.

        If a domain error's code changed, this control fails and the journey's
        assertion is exposed as stale - rather than the journey quietly checking
        for a string nothing produces any more.
        """
        journey = strip_comments(read(JOURNEY))
        forbidden = str(ForbiddenTransition("probe").code)
        duplicate = str(DuplicateIdentity("probe").code)
        assert re.search(rf"\b{re.escape(forbidden)}\b", journey), (
            f"the journey does not assert the real forbidden-transition code "
            f"{forbidden!r}"
        )
        assert re.search(rf"\b{re.escape(duplicate)}\b", journey), (
            f"the journey does not assert the real duplicate-identity code "
            f"{duplicate!r}"
        )

    def test_the_negative_path_proves_the_state_did_not_move(self) -> None:
        journey = strip_comments(read(JOURNEY))
        assert "not.toContainText" in journey, (
            "the journey never asserts that a refused transition left the "
            "displayed state unchanged"
        )
