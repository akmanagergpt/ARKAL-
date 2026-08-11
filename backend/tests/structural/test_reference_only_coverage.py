"""ARK-REQ-0053 scope and derivation controls (Phase 9 Package 2).

The sibling module asks whether the rule detects the right SHAPES. This one asks
whether it covers the right SUBJECTS: every module a consumer has today and
every module it gains tomorrow, every context the canonical map declares
reference-only, and nothing the map does not.

ADR-0008 decomposition: the two halves together reached the 400 logical-line
budget, and the seam - detection versus coverage - is a real one. No GATE 8
exception was requested.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.gates.provider_source import (
    ProviderVocabulary,
    tokens,
)
from arkali.control.registry.provider.provider_authority import ProviderAuthority
from arkali.kernel.contracts.results import HonestState
from tests.structural.provider_consumer_harness import (
    REPO,
    SCANNER_MODULE,
    evaluate,
    materialise,
    place,
    summaries,
    widen_authority,
)


@pytest.fixture(scope="module")
def live_map() -> AuthorityMap:
    return AuthorityMap.load(REPO)


@pytest.fixture(scope="module")
def authority() -> ProviderAuthority:
    return ProviderAuthority.load(REPO)


@pytest.fixture(scope="module")
def vocabulary(live_map: AuthorityMap) -> ProviderVocabulary:
    return ProviderVocabulary(live_map.provider_authority)


class TestCoverageFollowsTheAuthorityMap:
    def test_a_newly_added_consumer_module_is_scanned(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap,
        authority: ProviderAuthority
    ) -> None:
        """Discovery is by walk, so tomorrow's module needs no edit here."""
        concern = authority.owned_concerns()[0]
        root = materialise(tmp_path, live_map)
        assert evaluate(root, live_map).state is HonestState.PASS
        result = place(
            root, live_map,
            f"class Late:\n    provider_{concern}: str = ''\n",
            name="added_later.py",
        )
        assert result.state is HonestState.FAIL
        assert any("added_later.py" in s for s in summaries(result))

    def test_a_consumer_added_to_the_map_is_enforced(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap,
        authority: ProviderAuthority
    ) -> None:
        """A context promoted to reference-only is covered without an edit."""
        declared = live_map.provider_authority["reference_only_consumers"]
        extra = next(
            name for name in sorted(live_map.contexts)
            if name not in declared and name != live_map.provider_authority["owner"]
        )
        widened = widen_authority(
            live_map, reference_only_consumers=[*declared, extra]
        )
        root = materialise(tmp_path, widened)
        concern = authority.owned_concerns()[0]
        target = root / widened.contexts[extra].module_root / "probe.py"
        target.write_text(f"class M:\n    provider_{concern}: str = ''\n", "utf-8")
        result = evaluate(root, widened)
        assert result.state is HonestState.FAIL
        # The path is the context's DECLARED module root, which need not mirror
        # its dotted name: `acceptance.engine` is rooted at `.../acceptance`.
        assert any(widened.contexts[extra].module_root in s for s in summaries(result))

    def test_a_consumer_removed_from_the_map_is_no_longer_scanned(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap,
        authority: ProviderAuthority
    ) -> None:
        """Scope follows the declaration in both directions, never a list here."""
        declared = list(live_map.provider_authority["reference_only_consumers"])
        dropped, remaining = declared[0], declared[1:]
        narrowed = widen_authority(live_map, reference_only_consumers=remaining)
        root = materialise(tmp_path, live_map)  # every declared root exists
        concern = authority.owned_concerns()[0]
        (root / live_map.contexts[dropped].module_root / "probe.py").write_text(
            f"class M:\n    provider_{concern}: str = ''\n", "utf-8"
        )
        assert evaluate(root, live_map).state is HonestState.FAIL
        assert evaluate(root, narrowed).state is HonestState.PASS

    def test_an_unknown_consumer_in_the_map_fails_closed(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap
    ) -> None:
        widened = widen_authority(live_map, reference_only_consumers=[
            *live_map.provider_authority["reference_only_consumers"],
            "context.that.does.not.exist",
        ])
        result = evaluate(materialise(tmp_path, widened), widened)
        assert result.state is HonestState.FAIL
        assert any("unknown reference-only consumer" in s for s in summaries(result))

    def test_an_empty_consumer_set_is_refused(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap
    ) -> None:
        """Scanning nothing is not a pass (ADR-0001)."""
        emptied = widen_authority(live_map, reference_only_consumers=[])
        result = evaluate(tmp_path, emptied)
        assert result.state is HonestState.FAIL
        assert any("vacuous" in s for s in summaries(result))

    def test_a_consumer_with_no_module_on_disk_fails_closed(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap
    ) -> None:
        result = evaluate(tmp_path, live_map)
        assert result.state is HonestState.FAIL
        assert any("no module on disk" in s for s in summaries(result))

    def test_permitting_copying_is_still_refused(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap
    ) -> None:
        """The declaration half is retained, not replaced by the source half."""
        permissive = widen_authority(live_map, copying_permitted=True)
        result = evaluate(materialise(tmp_path, permissive), permissive)
        assert result.state is HonestState.FAIL
        assert any("copying_permitted is true" in s for s in summaries(result))

    def test_the_owner_may_not_be_its_own_consumer(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap
    ) -> None:
        owner = live_map.provider_authority["owner"]
        confused = widen_authority(live_map, reference_only_consumers=[
            *live_map.provider_authority["reference_only_consumers"], owner,
        ])
        result = evaluate(materialise(tmp_path, confused), confused)
        assert result.state is HonestState.FAIL
        assert any("also listed as reference-only consumer" in s
                   for s in summaries(result))


class TestTheMechanismTranscribesNothing:
    def test_the_scanner_names_no_consumer_concern_or_context(
        self, authority: ProviderAuthority
    ) -> None:
        """A checker holding its own copy of the map would be the F-0013 defect
        applied to the very requirement it exists to enforce.

        The subject is EXECUTABLE code. Docstrings cite the canonical sources a
        module exists because of, which is provenance rather than logic.
        """
        tree = ast.parse(SCANNER_MODULE.read_text(encoding="utf-8"))
        docstrings = set()
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ) and body and isinstance(body[0], ast.Expr):
                docstrings.add(id(body[0].value))
        literals = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings
        ]
        forbidden = {
            *authority.owned_concerns(),
            *authority.reference_only_consumers(),
            authority.owner,
        }
        named = sorted(forbidden & set(literals))
        assert not named, f"the scanner transcribes canonical values: {named}"

    def test_the_provider_token_is_derived_from_the_owner(
        self, vocabulary: ProviderVocabulary, authority: ProviderAuthority
    ) -> None:
        assert vocabulary.provider_token == authority.owner.rsplit(".", 1)[-1]

    def test_the_concern_set_is_the_maps_concern_set(
        self, vocabulary: ProviderVocabulary, authority: ProviderAuthority
    ) -> None:
        assert set(vocabulary.concerns) == set(authority.owned_concerns())

    def test_forbidden_operations_come_from_declared_permissions(
        self, live_map: AuthorityMap, vocabulary: ProviderVocabulary
    ) -> None:
        """`copying_permitted: false` and `caching_permitted: false` are the
        source; flipping one to true removes it from the forbidden set."""
        assert vocabulary.forbidden_operations
        relaxed = ProviderVocabulary(
            {**live_map.provider_authority, "caching_permitted": True}
        )
        assert relaxed.forbidden_operations < vocabulary.forbidden_operations

    def test_an_unusable_declaration_fails_closed(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap
    ) -> None:
        """A map declaring no owned concern cannot silently permit everything."""
        hollow = widen_authority(live_map, fields_owned=[])
        result = evaluate(materialise(tmp_path, hollow), hollow)
        assert result.state is HonestState.FAIL
        assert any("no owner or no owned concern" in s for s in summaries(result))

    def test_tokenisation_splits_snake_and_camel_alike(self) -> None:
        assert tokens("provider_health") == tokens("ProviderHealth")
        assert "health" not in tokens("healthy")
