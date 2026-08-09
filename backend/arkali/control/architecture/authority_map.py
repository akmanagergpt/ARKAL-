"""Parser and typed model for the canonical authority map (C-05, C-06).

Owner: control.architecture (Protected Core).

NO SHADOW MODEL: this module holds no copy of the governed data. Layers,
contexts, concerns, budgets, gates, human gates and sibling edges are all parsed
from docs/canonical/AUTHORITY_MAP.yaml at call time. If that file changes, every
consumer changes with it.
"""

from __future__ import annotations

import pathlib
from typing import Any, Final, Self

import yaml
from pydantic import BaseModel, ConfigDict

from arkali.control.architecture.refusal import refuse

AUTHORITY_MAP_RELPATH = "docs/canonical/AUTHORITY_MAP.yaml"

#: `dependency_rules` key suffixes that declare an exception to the layer
#: direction rule (ARCHITECTURE.md section 4 rules 5 and 6). The SUBJECT is the
#: part before the suffix and is resolved against the map at call time, so an
#: exemption is added or removed by editing AUTHORITY_MAP.yaml and never here
#: (F-0028). Keys not ending in one of these are not exemptions.
_EXEMPTION_SUFFIXES: Final[tuple[str, ...]] = (
    "_callable_from_any_layer",
    "_write_from_any_layer",
)


class BoundedContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    layer: str
    protected_core: bool
    module_root: str


class ConcernOwnership(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    concern: str
    owner: str
    enforced_by: str | None = None


class SiblingEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    target: str
    reason: str


class AuthorityMap(BaseModel):
    """Typed view of the authoritative map. Constructed only by `load`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_path: str
    layer_ranks: dict[str, int]
    contexts: dict[str, BoundedContext]
    concerns: tuple[ConcernOwnership, ...]
    sibling_edges: tuple[SiblingEdge, ...]
    #: Declared dependency direction rules. Parsed rather than assumed: the
    #: gate that enforces direction reads this, so the canonical declaration
    #: and the executable rule cannot diverge (F-0028).
    dependency_rules: dict[str, Any]
    architecture_budgets: dict[str, Any]
    #: Measurement formulas for the budgets above (ERR-003). Data, not code:
    #: the gate reads it and no validator holds a private copy.
    architecture_budget_measurement: dict[str, Any]
    architecture_gates: tuple[dict[str, Any], ...]
    human_gates: dict[str, str]
    lifecycle_authorities: dict[str, str]
    state_machine_authorities: dict[str, str]
    provider_authority: dict[str, Any]
    identifier_only_checker_is_sufficient: bool

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> Self:
        path = repo_root / AUTHORITY_MAP_RELPATH
        if not path.is_file():
            raise refuse(
                "authority map not found", source=str(path)
            )
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise refuse(
                f"authority map is not parseable YAML: {exc}", source=str(path)
            ) from exc
        if not isinstance(raw, dict):
            raise refuse(
                "authority map root is not a mapping", source=str(path)
            )
        return cls._from_raw(raw, path)

    @classmethod
    def _from_raw(cls, raw: dict[str, Any], path: pathlib.Path) -> Self:
        for key in ("layers", "contexts", "concerns", "architecture_budgets",
                    "architecture_gates", "human_gates"):
            if key not in raw:
                raise refuse(
                    f"authority map missing required section {key!r}", source=str(path)
                )
        try:
            ranks = {layer["name"]: int(layer["rank"]) for layer in raw["layers"]}
            contexts = {
                name: BoundedContext(name=name, **meta)
                for name, meta in raw["contexts"].items()
            }
            concerns = tuple(ConcernOwnership(**c) for c in raw["concerns"])
            edges = tuple(
                SiblingEdge(source=e["from"], target=e["to"], reason=e["reason"])
                for e in raw.get("allowed_sibling_edges", [])
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise refuse(
                f"authority map is malformed: {exc}", source=str(path)
            ) from exc

        unknown = sorted({c.layer for c in contexts.values()} - set(ranks))
        if unknown:
            raise refuse(
                f"contexts reference undeclared layers: {unknown}", source=str(path)
            )
        return cls(
            source_path=str(path),
            layer_ranks=ranks,
            contexts=contexts,
            concerns=concerns,
            sibling_edges=edges,
            dependency_rules=raw.get("dependency_rules", {}),
            architecture_budgets=raw["architecture_budgets"],
            architecture_budget_measurement=raw.get(
                "architecture_budget_measurement", {}
            ),
            architecture_gates=tuple(raw["architecture_gates"]),
            human_gates=raw["human_gates"],
            lifecycle_authorities=raw.get("lifecycle_authorities", {}),
            state_machine_authorities=raw.get("state_machine_authorities", {}),
            provider_authority=raw.get("provider_authority", {}),
            identifier_only_checker_is_sufficient=bool(
                raw.get("identifier_only_checker_is_sufficient", False)
            ),
        )

    def rank_of(self, context_name: str) -> int:
        context = self.contexts.get(context_name)
        if context is None:
            raise refuse(f"unknown context {context_name!r}")
        return self.layer_ranks[context.layer]

    @staticmethod
    def _exemption_subject(key: str) -> str | None:
        """The subject of a cross-layer exemption key, or None if not one."""
        for suffix in _EXEMPTION_SUFFIXES:
            if key.endswith(suffix):
                return key[: -len(suffix)]
        return None

    def _contexts_for_subject(self, subject: str) -> set[str]:
        """Resolve an exemption subject to contexts.

        Namespace first, then context final segment, then layer name. Order is
        load-bearing: `evidence` must resolve to the `evidence.*` contexts and
        NOT to `acceptance.engine`, which merely shares the `evidence` layer.
        ARCHITECTURE.md section 4 rule 5 grants the write exception to
        `evidence.*` by name; rule 6 names `control.policy`.
        """
        namespace = {n for n in self.contexts
                     if n == subject or n.startswith(subject + ".")}
        if namespace:
            return namespace
        segment = {n for n in self.contexts if n.rsplit(".", 1)[-1] == subject}
        if segment:
            return segment
        return {n for n, c in self.contexts.items() if c.layer == subject}

    def cross_layer_exempt_contexts(self) -> frozenset[str]:
        """Contexts reachable from any layer, derived from `dependency_rules`.

        An enabled rule whose subject resolves to nothing raises rather than
        silently granting or silently dropping the exemption.
        """
        exempt: set[str] = set()
        for key, enabled in self.dependency_rules.items():
            subject = self._exemption_subject(key)
            if subject is None or not enabled:
                continue
            resolved = self._contexts_for_subject(subject)
            if not resolved:
                raise refuse(
                    f"dependency rule {key!r} is enabled but its subject "
                    f"{subject!r} matches no context, namespace or layer",
                    source=self.source_path,
                )
            exempt |= resolved
        return frozenset(exempt)

    def edge_permitted(self, source: str, target: str) -> bool:
        """Whether an import edge `source -> target` is allowed.

        Every clause reads `dependency_rules`; none is assumed. The defaults
        below are the strict reading, so a map that omits a rule cannot widen
        the architecture by omission.
        """
        if target in self.cross_layer_exempt_contexts():
            return True
        if (source, target) in {(e.source, e.target) for e in self.sibling_edges}:
            return True
        rules = self.dependency_rules
        source_rank, target_rank = self.rank_of(source), self.rank_of(target)
        if target_rank < source_rank:
            return bool(rules.get("allow_lower_layer", False))
        if target_rank == source_rank:
            return bool(rules.get("allow_same_layer", False))
        return bool(rules.get("allow_higher_layer", False))

    def context_for_module(self, dotted: str) -> str | None:
        """Longest-prefix match from a dotted module path to its owning context."""
        best: str | None = None
        best_len = -1
        for name, ctx in self.contexts.items():
            prefix = ctx.module_root.replace("backend/", "").replace("/", ".")
            if (dotted == prefix or dotted.startswith(prefix + ".")) and len(prefix) > best_len:
                best, best_len = name, len(prefix)
        return best
