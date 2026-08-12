"""C-23 context package + provenance (ARK-REQ-0055).

Owner: engineering.agent. Concern: `agent_task_bounding_and_context`.

THE REQUIREMENT IS TWO CLAUSES AND BOTH ARE ENFORCED. `MS §Context Compiler`:
"ARKALI sends only relevant files, symbols, contracts, tests, ADRs, failures and
verified knowledge to a model. Context provenance is recorded." So a package may
carry only kinds the canonical document admits, and every item must say where it
came from. Neither is advisory: an item of an unlisted kind cannot be
constructed, and an item without provenance cannot be constructed.

PROVENANCE IS PER ITEM, NOT PER PACKAGE. A package-level "compiled from the
repository" note records nothing useful — the question a reader has is *which*
file, symbol or failure this particular claim came from. `origin` is therefore
required on each item, and blank is refused.

THE NO-SECRET BOUNDARY IS C-09's, REUSED AND NOT REIMPLEMENTED.
`control.policy.secret_reference.assert_no_raw_secret` is the canonical guard,
and its own docstring names the context package as one of the sinks raw values
must never reach. `engineering.agent` is layer rank 4 and `control.policy` is
rank 1, so the import is a legal downward edge and
`policy_callable_from_any_layer` permits the call besides. Copying its shape
regex here would create a second authority for what a secret looks like, and the
two would drift — exactly the defect `ARK-REQ-0052`'s consumer rule exists to
prevent, applied to secrets instead of provider concerns.

THE CONTEXT HASH IS THE INTERLOCK WITH C-14, NOT A LOCAL INVENTION. The accepted
Phase 6 `ArtifactProvenanceRecord` already carries a `context_hash` field, so an
artifact's provenance is meant to bind to the exact context its producer saw.
`context_hash` is computed here with `kernel.contracts.content_address`, the same
canonical addressing C-14 uses, over a deterministic rendering of the package.
Two packages with identical content therefore address identically and any change
to any item changes the address.

WHAT THIS CONTRACT IS NOT THE AUTHORITY FOR. It does not decide which kinds are
admissible — `context_kinds.py` parses that from the canonical document. It does
not decide whether a payload may be sent — that is `control.policy`'s. It does
not store an artifact, and it records no evidence: C-14 and C-15 own those, and a
package that wrote one would be a second evidence writer.
"""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from arkali.control.policy.secret_reference import assert_no_raw_secret
from arkali.engineering.agent.context_kinds import ContextKindAuthority, slug
from arkali.engineering.agent.errors import MalformedHarnessElement
from arkali.kernel.contracts.content_address import address_of

C23_SOURCE = "MS §Context Compiler (C-23)"

#: The sink name reported when the C-09 guard refuses, so a negative control can
#: assert WHICH boundary refused rather than that something somewhere raised.
CONTEXT_SINK = "context package (C-23)"

Declared = Annotated[str, Field(min_length=1)]


class ContextItem(BaseModel):
    """One piece of context, with the provenance that says where it came from."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    #: A kind the canonical document admits. Validated against the parsed
    #: authority by `ContextPackage`, which holds it; an item alone cannot know.
    kind: Declared
    #: What was sent - a path, a symbol name, a requirement id, a failure id.
    identifier: Declared
    #: Where it came from. `ARK-REQ-0055`'s second clause, per item.
    origin: Declared

    def rendering(self) -> tuple[str, str, str]:
        """The deterministic form the package hash is computed over."""
        return (slug(self.kind), self.identifier, self.origin)


class ContextPackage(BaseModel):
    """A compiled context package: only admissible kinds, all with provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    package_id: Declared
    #: The C-22 task this context was compiled for. C-22 carries the package
    #: identifier; this carries the task identifier. Neither embeds the other.
    task_id: Declared
    items: tuple[ContextItem, ...]

    @model_validator(mode="after")
    def _no_raw_secret_anywhere(self) -> ContextPackage:
        """Every string this package carries goes through the C-09 guard.

        Derived from the model rather than field-by-field, so a field added
        later is scanned the day it appears rather than when someone remembers.
        """
        for item in self.items:
            for value in item.rendering():
                assert_no_raw_secret(value, sink=CONTEXT_SINK)
        for value in (self.package_id, self.task_id):
            assert_no_raw_secret(value, sink=CONTEXT_SINK)
        return self

    def validate_kinds(self, authority: ContextKindAuthority) -> None:
        """Refuse any item whose kind the canonical document does not admit.

        Separate from construction because the vocabulary is parsed from a
        document and a model validator cannot reach a repository root without
        making every `ContextPackage` depend on one. The compiler calls this;
        `compiled` is the path that cannot forget to.
        """
        refused = tuple(
            item.kind for item in self.items if not authority.admits(item.kind)
        )
        if refused:
            raise MalformedHarnessElement(
                f"context kind(s) {sorted(set(refused))} are not admissible; "
                f"{authority.source} admits only {list(authority.kinds())}",
                source=C23_SOURCE,
            )

    @classmethod
    def compiled(
        cls,
        authority: ContextKindAuthority,
        *,
        package_id: str,
        task_id: str,
        items: tuple[ContextItem, ...],
    ) -> ContextPackage:
        """Build a package that has already been checked against the vocabulary.

        The only constructor a Context Compiler should use: it cannot produce a
        package carrying an inadmissible kind, because the check happens before
        the caller gets the object rather than after.
        """
        package = cls(package_id=package_id, task_id=task_id, items=items)
        package.validate_kinds(authority)
        return package

    @property
    def context_hash(self) -> str:
        """The canonical address of exactly this context.

        Deterministic and order-sensitive: the items are rendered in the order
        the compiler chose, because a different order is a different context to
        a model. `ArtifactProvenanceRecord.context_hash` binds to this value.
        """
        payload = json.dumps(
            {
                "package_id": self.package_id,
                "task_id": self.task_id,
                "items": [list(item.rendering()) for item in self.items],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return address_of(payload.encode("utf-8"))

    def kinds_present(self) -> tuple[str, ...]:
        """The distinct kinds carried, in first-appearance order."""
        seen: list[str] = []
        for item in self.items:
            identifier = slug(item.kind)
            if identifier not in seen:
                seen.append(identifier)
        return tuple(seen)
