"""Which authority owns each C-13 reference, parsed from the canonical schema.

Owner: control.capability.

WHAT ACTIVATION NEEDS FIRST. `EXECUTION_AND_CAPABILITY.md` §1 states the rule
this phase exists to make real: "`can_perform(capability_id)` resolves every
`*_ref` at query time against its owning authority." Resolving a reference
requires knowing which authority owns it, and that binding is declared in the
canonical node schema itself - each reference field carries a `# -> <context>`
annotation naming its owner. This module reads that block.

NO SHADOW MODEL. The field names, the target kinds and the owning contexts are
all parsed from the canonical document at call time. None of them appears in this
module, so adding a reference field to the canonical schema moves this binding
instead of expiring it, and a renamed authority renames itself here. Writing the
table out would be defect class F-0013 applied to the very rule ARK-REQ-0047
states.

WHY THE DOCUMENT AND NOT A LOCAL DECLARATION. `control.capability` is layer rank
1 and every authority it references - `control.policy`, `control.specification`,
`control.registry.provider`, `control.isolation` - is also rank 1.
`allow_same_layer: false` forbids the import, and `ARCHITECTURE.md` §4 rule 3
makes interface inversion the answer. So this context may never *reach* those
authorities; it may only know their names, and it learns them from the canonical
schema rather than from an import it is not allowed to make.

FAILS CLOSED. An absent block, a block declaring no field, a schema with no
external reference at all, a schema with no graph-internal reference at all, or
an annotation naming a context `AUTHORITY_MAP.yaml` does not declare are each
refused. A binding table with nothing in it would let every later resolution
report "nothing to resolve" and pass vacuously (F-0016, F-0017).
"""

from __future__ import annotations

import pathlib
import re
from typing import Any, Final

import yaml
from pydantic import BaseModel, ConfigDict

from arkali.kernel.contracts.error_base import AuthoritativeSourceError

SCHEMA_RELPATH: Final[str] = "docs/canonical/EXECUTION_AND_CAPABILITY.md"
AUTHORITY_MAP_RELPATH: Final[str] = "docs/canonical/AUTHORITY_MAP.yaml"

#: The canonical node schema block. The same block `test_capability_schema.py`
#: already reconciles `CapabilityNode` against, read here for its annotations.
_BLOCK: Final[re.Pattern[str]] = re.compile(
    r"```yaml\s*\ncapability_node:\s*\n(?P<body>.*?)```", re.S
)

#: One declared field: `  <field>: <type>` with an optional `# -> <context>`.
#: The arrow is what distinguishes a reference into another authority from an
#: ordinary attribute; `id: str  # stable capability identifier` has a comment
#: and no arrow, and is therefore not a reference.
_FIELD: Final[re.Pattern[str]] = re.compile(
    r"^\s{2}(?P<field>\w+):\s*(?P<kind>[^#\n]*?)\s*"
    r"(?:#\s*(?:->\s*(?P<authority>[A-Za-z][\w.]*))?[^\n]*)?$",
    re.M,
)

#: A reference whose target is another capability is resolved by the graph
#: itself, so its owner is not annotated. The target kind is what identifies it.
_GRAPH_INTERNAL_KIND: Final[str] = "capability_id"


class ReferenceBinding(BaseModel):
    """One C-13 reference field and the authority that resolves it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The `CapabilityNode` field the canonical block declares.
    field: str
    #: The identifier kind the field holds, e.g. `policy_rule_id`.
    target_kind: str
    #: The owning context, or empty when the graph resolves it itself.
    authority: str = ""

    @property
    def is_external(self) -> bool:
        """Whether resolution requires an authority outside this context."""
        return bool(self.authority)


def _strip_container(kind: str) -> str:
    """`[policy_rule_id]` and `probe_id` both name one target kind."""
    return kind.strip().strip("[]").strip()


class CapabilityReferenceAuthority:
    """The canonical reference -> authority binding. Construct with `load`."""

    def __init__(
        self, bindings: tuple[ReferenceBinding, ...], source_path: str
    ) -> None:
        self._bindings = bindings
        self.source_path = source_path

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> CapabilityReferenceAuthority:
        path = repo_root / SCHEMA_RELPATH
        if not path.is_file():
            raise AuthoritativeSourceError(
                "capability schema document not found", source=str(path)
            )
        block = _BLOCK.search(path.read_text(encoding="utf-8"))
        if block is None:
            raise AuthoritativeSourceError(
                "the canonical capability_node schema block is absent; refusing "
                "to invent the reference bindings",
                source=str(path),
            )
        bindings = cls._parse(block.group("body"))
        if not bindings:
            raise AuthoritativeSourceError(
                "the canonical capability_node block declares no field",
                source=str(path),
            )
        instance = cls(bindings, str(path))
        instance._validate(repo_root, str(path))
        return instance

    @staticmethod
    def _parse(body: str) -> tuple[ReferenceBinding, ...]:
        found: list[ReferenceBinding] = []
        for match in _FIELD.finditer(body):
            kind = _strip_container(match.group("kind"))
            authority = (match.group("authority") or "").strip()
            if not authority and kind != _GRAPH_INTERNAL_KIND:
                continue
            found.append(
                ReferenceBinding(
                    field=match.group("field"), target_kind=kind, authority=authority
                )
            )
        return tuple(found)

    def _validate(self, repo_root: pathlib.Path, source: str) -> None:
        """Anti-vacuity and closed failure, before any caller sees a binding."""
        if not self.external():
            raise AuthoritativeSourceError(
                "the canonical schema declares no external reference; a "
                "resolution rule with no subject would pass vacuously",
                source=source,
            )
        if not self.graph_internal():
            raise AuthoritativeSourceError(
                "the canonical schema declares no capability-to-capability "
                "reference; the graph would have nothing of its own to resolve",
                source=source,
            )
        declared = self._declared_contexts(repo_root)
        unknown = sorted(
            b.authority for b in self.external() if b.authority not in declared
        )
        if unknown:
            raise AuthoritativeSourceError(
                f"the capability schema names authorities {unknown} that the "
                "authority map does not declare as bounded contexts",
                source=source,
            )

    @staticmethod
    def _declared_contexts(repo_root: pathlib.Path) -> frozenset[str]:
        path = repo_root / AUTHORITY_MAP_RELPATH
        if not path.is_file():
            raise AuthoritativeSourceError("authority map not found", source=str(path))
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        contexts = raw.get("contexts") if isinstance(raw, dict) else None
        if not isinstance(contexts, dict) or not contexts:
            raise AuthoritativeSourceError(
                "the authority map declares no bounded context", source=str(path)
            )
        return frozenset(str(name) for name in contexts)

    def bindings(self) -> tuple[ReferenceBinding, ...]:
        """Every reference field the canonical schema declares, in its order."""
        return self._bindings

    def external(self) -> tuple[ReferenceBinding, ...]:
        """References an authority outside `control.capability` must resolve."""
        return tuple(b for b in self._bindings if b.is_external)

    def graph_internal(self) -> tuple[ReferenceBinding, ...]:
        """References the graph resolves against its own node set."""
        return tuple(b for b in self._bindings if not b.is_external)

    def authorities(self) -> tuple[str, ...]:
        """The distinct external authorities, in canonical declaration order."""
        seen: list[str] = []
        for binding in self.external():
            if binding.authority not in seen:
                seen.append(binding.authority)
        return tuple(seen)

    def binding_for(self, field: str) -> ReferenceBinding:
        for binding in self._bindings:
            if binding.field == field:
                return binding
        raise AuthoritativeSourceError(
            f"the canonical schema declares no reference field {field!r}",
            source=self.source_path,
        )
