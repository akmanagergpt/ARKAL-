"""Parser and typed model for the canonical authority map (C-05, C-06).

Owner: control.architecture (Protected Core).

NO SHADOW MODEL: this module holds no copy of the governed data. Layers,
contexts, concerns, budgets, gates, human gates and sibling edges are all parsed
from docs/canonical/AUTHORITY_MAP.yaml at call time. If that file changes, every
consumer changes with it.
"""

from __future__ import annotations

import pathlib
from typing import Any, Self

import yaml
from pydantic import BaseModel, ConfigDict

from arkali.kernel.contracts.errors import AuthoritativeSourceError

AUTHORITY_MAP_RELPATH = "docs/canonical/AUTHORITY_MAP.yaml"


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
    architecture_budgets: dict[str, Any]
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
            raise AuthoritativeSourceError(
                "authority map not found", source=str(path)
            )
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise AuthoritativeSourceError(
                f"authority map is not parseable YAML: {exc}", source=str(path)
            ) from exc
        if not isinstance(raw, dict):
            raise AuthoritativeSourceError(
                "authority map root is not a mapping", source=str(path)
            )
        return cls._from_raw(raw, path)

    @classmethod
    def _from_raw(cls, raw: dict[str, Any], path: pathlib.Path) -> Self:
        for key in ("layers", "contexts", "concerns", "architecture_budgets",
                    "architecture_gates", "human_gates"):
            if key not in raw:
                raise AuthoritativeSourceError(
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
            raise AuthoritativeSourceError(
                f"authority map is malformed: {exc}", source=str(path)
            ) from exc

        unknown = sorted({c.layer for c in contexts.values()} - set(ranks))
        if unknown:
            raise AuthoritativeSourceError(
                f"contexts reference undeclared layers: {unknown}", source=str(path)
            )
        return cls(
            source_path=str(path),
            layer_ranks=ranks,
            contexts=contexts,
            concerns=concerns,
            sibling_edges=edges,
            architecture_budgets=raw["architecture_budgets"],
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
            raise AuthoritativeSourceError(f"unknown context {context_name!r}")
        return self.layer_ranks[context.layer]

    def context_for_module(self, dotted: str) -> str | None:
        """Longest-prefix match from a dotted module path to its owning context."""
        best: str | None = None
        best_len = -1
        for name, ctx in self.contexts.items():
            prefix = ctx.module_root.replace("backend/", "").replace("/", ".")
            if (dotted == prefix or dotted.startswith(prefix + ".")) and len(prefix) > best_len:
                best, best_len = name, len(prefix)
        return best
