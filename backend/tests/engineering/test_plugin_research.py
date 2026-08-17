"""Research capability (ARK-REQ-0163): official sources first, never
mutates production.

Phase 21 Package 4.
"""

from __future__ import annotations

import itertools
import pathlib
from typing import Final

import pytest

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.engineering.plugin.research import (
    COMMUNITY,
    OFFICIAL,
    PolicyDecisionSource,
    ResearchResult,
    ResearchSource,
    attempt_fetch,
    research_task_ref,
    resolve_sources,
)

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]

OFFICIAL_A = ResearchSource(name="vendor-docs", kind=OFFICIAL, url="https://vendor.example/docs")
OFFICIAL_B = ResearchSource(name="spec", kind=OFFICIAL, url="https://spec.example/rfc")
COMMUNITY_A = ResearchSource(name="forum-post", kind=COMMUNITY, url="https://forum.example/x")
COMMUNITY_B = ResearchSource(name="blog", kind=COMMUNITY, url="https://blog.example/y")


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


class TestOfficialSourcesAreAlwaysTriedFirst:
    """Not Hypothesis (`hypothesis` is NOT_CONFIGURED on this host per
    `BUILD_STATE.md`) - an exhaustive sweep of every ordering of a small,
    representative source set instead, which is total for this input size
    rather than sampled."""

    ALL_SOURCES = (OFFICIAL_A, OFFICIAL_B, COMMUNITY_A, COMMUNITY_B)

    @pytest.mark.parametrize(
        "permutation", list(itertools.permutations(ALL_SOURCES))
    )
    def test_every_input_ordering_yields_official_first(
        self, permutation: tuple[ResearchSource, ...]
    ) -> None:
        resolved = resolve_sources(permutation)
        kinds = [s.kind for s in resolved]
        first_community = kinds.index(COMMUNITY) if COMMUNITY in kinds else len(kinds)
        assert all(k == OFFICIAL for k in kinds[:first_community])
        assert set(resolved) == set(permutation)

    def test_relative_order_within_each_kind_is_preserved(self) -> None:
        resolved = resolve_sources((COMMUNITY_B, OFFICIAL_B, COMMUNITY_A, OFFICIAL_A))
        assert resolved == (OFFICIAL_B, OFFICIAL_A, COMMUNITY_B, COMMUNITY_A)

    def test_all_official_stays_all_official(self) -> None:
        assert resolve_sources((OFFICIAL_A, OFFICIAL_B)) == (OFFICIAL_A, OFFICIAL_B)

    def test_all_community_stays_all_community(self) -> None:
        assert resolve_sources((COMMUNITY_A, COMMUNITY_B)) == (COMMUNITY_A, COMMUNITY_B)

    def test_empty_input_resolves_empty(self) -> None:
        assert resolve_sources(()) == ()

    def test_no_source_is_ever_dropped(self) -> None:
        resolved = resolve_sources(self.ALL_SOURCES)
        assert len(resolved) == len(self.ALL_SOURCES)
        assert set(resolved) == set(self.ALL_SOURCES)


class TestResultIsStructurallyReadOnly:
    def test_mutation_applied_defaults_false(self) -> None:
        result = ResearchResult(source=OFFICIAL_A, decision="AUTO")
        assert result.mutation_applied is False

    def test_mutation_applied_cannot_be_constructed_true(self) -> None:
        """A dataclass field typed `Literal[False]` is a static, not a
        runtime, guarantee - mypy refuses a `True` literal at the call site.
        The runtime proof is that no code path in this module ever passes
        anything but the field's own default."""
        import inspect

        import arkali.engineering.plugin.research as research_module

        assert "mutation_applied=True" not in inspect.getsource(research_module)

    def test_permitted_reflects_auto_only(self) -> None:
        assert ResearchResult(source=OFFICIAL_A, decision="AUTO").permitted is True
        assert ResearchResult(source=OFFICIAL_A, decision="ASK_USER").permitted is False
        assert ResearchResult(source=OFFICIAL_A, decision="DENY").permitted is False


class TestNoMutationAuthorityIsImported:
    def test_module_imports_no_persistence_or_write_path(self) -> None:
        """Checks real `import`/`from ... import` statements only - a
        docstring explaining why a forbidden module is absent must not
        itself trip this control."""
        from arkali.control.architecture.gates.structure_gates import (
            internal_imports,
        )

        path = REPO / "backend/arkali/engineering/plugin/research.py"
        imports = internal_imports(path)
        forbidden_prefixes = (
            "arkali.kernel.persistence", "arkali.lifecycle.release",
        )
        for name in imports:
            assert not name.startswith(forbidden_prefixes), name
        assert imports  # sanity: the module does import something real

    def test_no_http_transport_library_is_imported(self) -> None:
        import ast

        path = REPO / "backend/arkali/engineering/plugin/research.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_top_level_names = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert imported_top_level_names.isdisjoint({"requests", "httpx", "urllib"})


class TestRealPdpGovernsEveryFetch:
    """The real PDP, not a fixture: proves `NETWORK_EXTERNAL`'s "DENY in
    Local-Only" fixed rule (`SECURITY_ARCHITECTURE.md` §2) actually reaches
    research's own fetch attempts - the VDC names "research" explicitly
    among the paths whose Local-Only DENY evidence is required."""

    def test_pdp_structurally_satisfies_the_protocol(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        assert isinstance(pdp, PolicyDecisionSource)

    def test_local_only_denies_a_real_research_fetch(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        result = attempt_fetch(
            OFFICIAL_A, pdp, actor="engineering.plugin", trust_tier="TRUST-2",
            local_only=True,
        )
        assert result.decision == "DENY"
        assert result.permitted is False
        assert result.mutation_applied is False

    def test_local_only_disabled_does_not_force_deny(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        """Local-Only OFF must not itself force DENY - the fixed rule is
        conditional on the mode, not on the operation class alone.
        `SECURITY_ARCHITECTURE.md` §2: NETWORK_EXTERNAL at TRUST-0/1 is
        ASK_USER, not DENY, once Local-Only is off."""
        result = attempt_fetch(
            OFFICIAL_A, pdp, actor="engineering.plugin", trust_tier="TRUST-0",
            local_only=False,
        )
        assert result.decision == "ASK_USER"

    def test_every_source_kind_is_governed_identically_by_the_pdp(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        """`kind` (OFFICIAL/COMMUNITY) is this module's own classification,
        never a second security decision — the PDP decides purely from tier
        and Local-Only, the same as any other NETWORK_EXTERNAL caller."""
        official_result = attempt_fetch(
            OFFICIAL_A, pdp, actor="x", trust_tier="TRUST-2", local_only=True,
        )
        community_result = attempt_fetch(
            COMMUNITY_A, pdp, actor="x", trust_tier="TRUST-2", local_only=True,
        )
        assert official_result.decision == community_result.decision == "DENY"


class TestResearchTaskRefIsContentAddressed:
    def test_identical_tasks_share_a_ref(self) -> None:
        a = research_task_ref(task="license terms", sources=(OFFICIAL_A,))
        b = research_task_ref(task="license terms", sources=(OFFICIAL_A,))
        assert a == b

    def test_a_changed_source_set_changes_the_ref(self) -> None:
        a = research_task_ref(task="license terms", sources=(OFFICIAL_A,))
        b = research_task_ref(task="license terms", sources=(OFFICIAL_A, COMMUNITY_A))
        assert a != b

    def test_ref_is_a_canonical_content_address(self) -> None:
        from arkali.kernel.contracts.content_address import is_address

        assert is_address(research_task_ref(task="x", sources=()))
