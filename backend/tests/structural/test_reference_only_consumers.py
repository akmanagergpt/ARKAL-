"""ARK-REQ-0053 source-level enforcement (Phase 9 Package 2).

`MS §Provider and Agent separation`: no component may store, cache, mirror,
default or re-derive provider identity, model identity, configuration, health,
availability, cost metadata or fallback; all consumers resolve them from the
Registry at query time.

Until Package 2 the `shadow_registry` gate validated only the DECLARATION, and
nine real violations were proven to pass it untouched. These controls prove the
gate now detects each one, and — the half that matters more — that it still
permits the shapes a reference-only consumer legitimately has.

EVERY SUBJECT IS DERIVED. No consumer name, concern name or context is written
here: the consumer set and the owned concerns come from `AUTHORITY_MAP.yaml`
through `ProviderAuthority`, so adding a consumer or a concern to the canonical
map moves these controls instead of expiring them (F-0021, F-0032).

ISOLATION. Gate-level controls materialise every declared consumer root inside
`tmp_path` and run the REAL `ShadowRegistryGate` against it, so detection is
proven end to end rather than against the scanner in isolation — the F-0017/
F-0040 lesson that exercising a helper never proves its caller consults it. The
repository tree is never written.
"""

from __future__ import annotations

import pathlib

import pytest

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.registry.provider.provider_authority import ProviderAuthority
from arkali.kernel.contracts.results import HonestState
from tests.structural.provider_consumer_harness import (
    REPO,
    evaluate,
    materialise,
    place,
    summaries,
)


@pytest.fixture(scope="module")
def live_map() -> AuthorityMap:
    return AuthorityMap.load(REPO)


@pytest.fixture(scope="module")
def authority() -> ProviderAuthority:
    return ProviderAuthority.load(REPO)


class TestTheLiveRepositoryObeysTheRule:
    def test_the_live_gate_passes_and_scans_real_modules(
        self, live_map: AuthorityMap
    ) -> None:
        result = evaluate(REPO, live_map)
        assert result.state is HonestState.PASS, summaries(result)
        scanned = int("".join(c for c in result.summary.split("scanned")[0]
                             if c.isdigit()))
        assert scanned > 0, "a PASS over zero modules would be vacuous"

    def test_an_empty_tree_fails_closed(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap
    ) -> None:
        """A consumer whose declared root is not on disk cannot be enforced."""
        result = evaluate(tmp_path, live_map)
        assert result.state is HonestState.FAIL
        assert any("no module on disk" in s for s in summaries(result))


class TestForbiddenShapesAreDetected:
    """The nine violations proven to pass the untouched mechanism."""

    def test_a_mirrored_owned_field_is_detected(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap,
        authority: ProviderAuthority
    ) -> None:
        concern = authority.owned_concerns()[0]
        root = materialise(tmp_path, live_map)
        result = place(
            root, live_map,
            "class Mirror:\n"
            f"    provider_{concern}: str = ''\n",
        )
        assert result.state is HonestState.FAIL
        assert any(concern in s for s in summaries(result))

    def test_every_owned_concern_is_detected_when_mirrored(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap,
        authority: ProviderAuthority
    ) -> None:
        """No concern may be covered by accident; each is proven individually."""
        for index, concern in enumerate(authority.owned_concerns()):
            root = materialise(tmp_path / f"c{index}", live_map)
            result = place(
                root, live_map, f"class M:\n    provider_{concern}: str = ''\n"
            )
            assert result.state is HonestState.FAIL, f"{concern} was not detected"
            assert any(concern in s for s in summaries(result))

    def test_an_aliased_field_is_detected(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap,
        authority: ProviderAuthority
    ) -> None:
        concern = authority.owned_concerns()[0]
        root = materialise(tmp_path, live_map)
        result = place(
            root, live_map,
            "from pydantic import BaseModel, Field\n\n\n"
            "class Aliased(BaseModel):\n"
            f'    hp: str = Field(alias="provider_{concern}")\n',
        )
        assert result.state is HonestState.FAIL
        assert any("aliased name" in s for s in summaries(result))

    def test_a_local_default_is_detected(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap,
        authority: ProviderAuthority
    ) -> None:
        concern = authority.owned_concerns()[0]
        root = materialise(tmp_path, live_map)
        result = place(
            root, live_map,
            f'def pick(provider_{concern}: str = "GUESS") -> str:\n'
            f"    return provider_{concern}\n",
        )
        assert result.state is HonestState.FAIL
        assert any("defaulted parameter" in s for s in summaries(result))

    def test_a_locally_derived_value_is_detected(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap,
        authority: ProviderAuthority
    ) -> None:
        concern = authority.owned_concerns()[0]
        root = materialise(tmp_path, live_map)
        result = place(
            root, live_map,
            f"def compute_provider_{concern}(latency: float) -> str:\n"
            '    return "AVAILABLE"\n',
        )
        assert result.state is HonestState.FAIL
        assert any("function" in s for s in summaries(result))

    def test_a_cached_registry_response_is_detected(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap
    ) -> None:
        """A provider value kept on `self` outlives the query that produced it."""
        root = materialise(tmp_path, live_map)
        result = place(
            root, live_map,
            "class Cache:\n"
            "    def __init__(self, provider_record: object) -> None:\n"
            "        self._kept = provider_record\n",
        )
        assert result.state is HonestState.FAIL
        assert any("retains provider value" in s for s in summaries(result))

    def test_a_second_lookup_table_is_detected(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap,
        authority: ProviderAuthority
    ) -> None:
        concern = authority.owned_concerns()[0]
        root = materialise(tmp_path, live_map)
        result = place(
            root, live_map,
            f'TABLE = {{"provider_{concern}": 1}}\n',
        )
        assert result.state is HonestState.FAIL
        assert any("dict key" in s for s in summaries(result))

    def test_a_second_registry_cache_is_detected(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap
    ) -> None:
        """The forbidden operation is derived from the map's own permissions."""
        root = materialise(tmp_path, live_map)
        result = place(
            root, live_map,
            "class ProviderRegistryCache:\n"
            "    def __init__(self) -> None:\n"
            "        self.provider_cache = {}\n",
        )
        assert result.state is HonestState.FAIL
        assert any("not permitted" in s for s in summaries(result))

    def test_a_bare_concern_inside_a_provider_class_is_detected(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap,
        authority: ProviderAuthority
    ) -> None:
        """Dropping the qualifier does not drop the concern."""
        concern = authority.owned_concerns()[0]
        root = materialise(tmp_path, live_map)
        result = place(
            root, live_map, f"class ProviderState:\n    {concern}: str = ''\n"
        )
        assert result.state is HonestState.FAIL
        assert any("mirrors the owned concern" in s for s in summaries(result))


class TestPermittedShapesStillPass:
    """The half that decides whether the control is usable."""

    def test_an_opaque_provider_reference_is_permitted(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap
    ) -> None:
        """ADR-0003: the Capability Graph holds `provider_refs` and resolves
        them at query time. Holding a reference is the permitted shape."""
        root = materialise(tmp_path, live_map)
        result = place(
            root, live_map,
            "class Node:\n"
            "    provider_refs: tuple[str, ...] = ()\n\n"
            "    def __init__(self, provider_ref: str) -> None:\n"
            "        self.provider_ref = provider_ref\n",
        )
        assert result.state is HonestState.PASS, summaries(result)

    def test_resolving_from_the_registry_in_a_local_is_permitted(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap,
        authority: ProviderAuthority
    ) -> None:
        """A local is how a consumer uses a query result; it stores nothing."""
        concern = authority.owned_concerns()[0]
        root = materialise(tmp_path, live_map)
        result = place(
            root, live_map,
            "def use(registry, provider_ref: str) -> str:\n"
            "    record = registry.resolve(provider_ref)\n"
            f"    return record.{concern}\n",
        )
        assert result.state is HonestState.PASS, summaries(result)

    def test_ordinary_words_overlapping_provider_terms_are_permitted(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap,
        authority: ProviderAuthority
    ) -> None:
        """A concern token without the provider token is somebody else's word."""
        concerns = authority.owned_concerns()
        body = "".join(f"    worker_{c}: str = ''\n" for c in concerns)
        root = materialise(tmp_path, live_map)
        result = place(root, live_map, "class Worker:\n" + body)
        assert result.state is HonestState.PASS, summaries(result)

    def test_prose_mentioning_a_concern_is_not_a_subject(
        self, tmp_path: pathlib.Path, live_map: AuthorityMap,
        authority: ProviderAuthority
    ) -> None:
        """Documentation describing a previous state must never trip the gate."""
        concern = authority.owned_concerns()[0]
        root = materialise(tmp_path, live_map)
        result = place(
            root, live_map,
            f'"""Once this module cached provider_{concern}; it no longer does."""\n'
            f"# provider_{concern} was mirrored here before Package 2\n"
            f'MESSAGE = "provider {concern} is owned by the registry"\n'
            f'def report(text: str = "provider {concern} unavailable") -> str:\n'
            "    return text\n",
        )
        assert result.state is HonestState.PASS, summaries(result)
