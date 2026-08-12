"""C-23: only relevant context, and provenance recorded (ARK-REQ-0055).

Phase 10 Package 2. `MS §Context Compiler` is two clauses and both are under
test here: a package may carry only the kinds the canonical document enumerates,
and every item must record where it came from. The no-secret assertion that
`CONTRACT_INVENTORY.md` row 23 names as this contract's verification is tested
against the REAL C-09 guard, not a local copy.
"""

from __future__ import annotations

import pathlib
from typing import Any, Final

import pytest
from pydantic import ValidationError

from arkali.control.policy.policy_errors import RawSecretLeak
from arkali.engineering.agent.context_kinds import ContextKindAuthority
from arkali.engineering.agent.context_package import (
    CONTEXT_SINK,
    ContextItem,
    ContextPackage,
)
from arkali.engineering.agent.errors import MalformedHarnessElement
from arkali.kernel.contracts.content_address import is_address

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
#: A real raw-secret shape the C-09 guard recognises. Not a secret.
FAKE_KEY: Final[str] = "sk-" + "A1b2C3d4E5f6G7h8"


@pytest.fixture(scope="module")
def authority() -> ContextKindAuthority:
    return ContextKindAuthority.load(REPO)


def item(**overrides: Any) -> ContextItem:
    fields: dict[str, Any] = {
        "kind": "files",
        "identifier": "backend/arkali/engineering/agent/harness_task.py",
        "origin": "repository revision 4766dc2",
    }
    fields.update(overrides)
    return ContextItem(**fields)


def package(authority: ContextKindAuthority, *items: ContextItem) -> ContextPackage:
    return ContextPackage.compiled(
        authority,
        package_id="ctx-7f3a",
        task_id="task-91",
        items=items or (item(),),
    )


class TestOnlyRelevantKindsMayBeSent:
    def test_every_canonical_kind_is_admitted(
        self, authority: ContextKindAuthority
    ) -> None:
        """Derived from the document, so a new kind is admitted the day it lands."""
        built = package(authority, *(item(kind=name) for name in authority.kinds()))
        assert len(built.items) == len(authority)
        assert built.kinds_present() == authority.identifiers()

    def test_an_inadmissible_kind_is_refused(
        self, authority: ContextKindAuthority
    ) -> None:
        with pytest.raises(MalformedHarnessElement, match="not admissible"):
            package(authority, item(kind="slack messages"))

    def test_the_refusal_names_what_is_admitted(
        self, authority: ContextKindAuthority
    ) -> None:
        """A refusal a reader cannot act on is barely a refusal."""
        with pytest.raises(MalformedHarnessElement) as raised:
            package(authority, item(kind="gossip"))
        assert authority.kinds()[0] in str(raised.value)

    def test_one_bad_item_refuses_the_whole_package(
        self, authority: ContextKindAuthority
    ) -> None:
        with pytest.raises(MalformedHarnessElement):
            package(authority, item(), item(kind="rumours"), item(kind="tests"))

    def test_the_compiled_constructor_cannot_forget_to_check(
        self, authority: ContextKindAuthority
    ) -> None:
        """`compiled` is the path a Context Compiler uses; it always validates."""
        raw = ContextPackage(
            package_id="p", task_id="t", items=(item(kind="anything"),)
        )
        with pytest.raises(MalformedHarnessElement):
            raw.validate_kinds(authority)
        with pytest.raises(MalformedHarnessElement):
            ContextPackage.compiled(
                authority, package_id="p", task_id="t",
                items=(item(kind="anything"),),
            )


class TestProvenanceIsRecordedPerItem:
    def test_an_item_without_origin_cannot_be_constructed(self) -> None:
        with pytest.raises(ValidationError, match="origin"):
            ContextItem(kind="files", identifier="x.py")  # type: ignore[call-arg]

    def test_a_blank_origin_is_refused(self) -> None:
        """A package-level shrug is not provenance."""
        with pytest.raises(ValidationError):
            item(origin="   ")

    def test_provenance_survives_on_every_item(
        self, authority: ContextKindAuthority
    ) -> None:
        built = package(
            authority,
            item(identifier="a.py", origin="revision aaa"),
            item(kind="tests", identifier="test_a.py", origin="revision bbb"),
        )
        assert [i.origin for i in built.items] == ["revision aaa", "revision bbb"]

    def test_an_item_is_immutable(self) -> None:
        with pytest.raises(ValidationError):
            item().origin = "somewhere else"


class TestTheNoSecretAssertion:
    """CONTRACT_INVENTORY.md row 23 names this as C-23's verification."""

    @pytest.mark.parametrize("field", ["identifier", "origin"])
    def test_a_raw_secret_in_any_item_field_is_refused(
        self, authority: ContextKindAuthority, field: str
    ) -> None:
        with pytest.raises(RawSecretLeak):
            package(authority, item(**{field: FAKE_KEY}))

    def test_a_raw_secret_in_a_package_field_is_refused(
        self, authority: ContextKindAuthority
    ) -> None:
        with pytest.raises(RawSecretLeak):
            ContextPackage.compiled(
                authority, package_id=FAKE_KEY, task_id="t", items=(item(),)
            )

    def test_the_refusal_names_this_sink(
        self, authority: ContextKindAuthority
    ) -> None:
        """So a control can assert WHICH boundary refused (F-0017)."""
        with pytest.raises(RawSecretLeak, match="context package"):
            package(authority, item(origin=FAKE_KEY))
        assert "C-23" in CONTEXT_SINK

    def test_the_guard_is_the_c09_one_and_not_a_local_copy(self) -> None:
        """A second shape authority would drift from the first.

        Reads the shipping source: this context must call the canonical guard
        and must not carry its own raw-secret pattern.
        """
        owner = REPO / "backend/arkali/engineering/agent"
        bodies = {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(owner.rglob("*.py"))
        }
        assert any("assert_no_raw_secret" in text for text in bodies.values())
        offenders = [
            name for name, text in bodies.items()
            if "BEGIN " in text or "AKIA" in text
        ]
        assert not offenders, f"raw-secret pattern copied here: {offenders}"


class TestTheContextHashBindsToC14:
    def test_it_is_a_canonical_content_address(
        self, authority: ContextKindAuthority
    ) -> None:
        assert is_address(package(authority).context_hash)

    def test_identical_content_addresses_identically(
        self, authority: ContextKindAuthority
    ) -> None:
        assert package(authority).context_hash == package(authority).context_hash

    @pytest.mark.parametrize(
        "change", [{"identifier": "other.py"}, {"origin": "revision zzz"},
                   {"kind": "symbols"}]
    )
    def test_any_change_to_any_item_changes_the_address(
        self, authority: ContextKindAuthority, change: dict[str, Any]
    ) -> None:
        assert (
            package(authority).context_hash
            != package(authority, item(**change)).context_hash
        )

    def test_order_is_part_of_the_context(
        self, authority: ContextKindAuthority
    ) -> None:
        """A different order is a different context to a model."""
        first, second = item(identifier="a.py"), item(identifier="b.py")
        assert (
            package(authority, first, second).context_hash
            != package(authority, second, first).context_hash
        )
