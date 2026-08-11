"""Source-level enforcement of ARK-REQ-0053 in the reference-only consumers.

Owner: control.architecture (Protected Core).

WHAT THE RULE IS. `MS §Provider and Agent separation`: "The Provider/Model
Registry is the sole canonical authority for provider identity, model identity,
provider configuration, health, availability, cost metadata and provider
fallback configuration. No other component may store, cache, mirror, default or
re-derive these values. All consumers resolve them from the Registry at query
time." `AUTHORITY_MAP.yaml` `provider_authority` is the machine-readable form of
exactly that, and ADR-0001 makes it the artifact the gates evaluate against.

WHY THIS EXISTS. Until now `ShadowRegistryGate` validated the DECLARATION -
owner, consumer set, copying and caching flags - and never read consumer source.
`docs/contracts/provider_record.md` §3 stated that gap rather than papering over
it. Nine real violations were proven to pass the untouched mechanism before this
module was written.

NO SHADOW MODEL, AND NO SECOND REGISTRY IN THE CHECKER. This module names no
consumer, no owned concern and no context. The consumer set, the owner, the
owned concerns and the forbidden operations are all derived from
`provider_authority` at call time, so adding a concern or a consumer to the
canonical map moves this control instead of expiring it.

STRUCTURE, NOT TEXT. Every subject is an AST binding construct - a class field,
an attribute assignment, a module-level name, a function name, a defaulted
parameter, a dict key or a string keyword argument. Comments, docstrings and
positional message strings are never subjects, so documentation and historical
evidence describing a previous state cannot trip it, and an ordinary word that
merely overlaps provider terminology cannot either: a name matches only when its
tokens carry the provider token AND every token of an owned concern.
"""

from __future__ import annotations

import ast
import pathlib
import re
from typing import Final

#: Identifier-shaped strings are the only string constants treated as names.
_IDENTIFIER_LIKE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")
#: CamelCase boundary, so `ProviderHealthCache` tokenises like `provider_health_cache`.
_CAMEL: Final[re.Pattern[str]] = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
#: A declaration key of the form `<operation>_permitted`.
_PERMISSION_KEY: Final[re.Pattern[str]] = re.compile(r"^(?P<stem>[a-z_]+)_permitted$")


def tokens(name: str) -> frozenset[str]:
    """Lower-cased word tokens of an identifier, snake and Camel alike."""
    spaced = _CAMEL.sub("_", name)
    return frozenset(part for part in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if part)


def _forms(stem: str) -> frozenset[str]:
    """A derived permission stem and the ordinary word forms it appears as.

    `copying_permitted` yields `copying` and `copy`; `caching_permitted` yields
    `caching`, `cach` and `cache`. This is morphological expansion of a stem read
    from the canonical map, not a hand-written vocabulary: a map that later
    declares `mirroring_permitted: false` is picked up with no edit here.
    """
    found = {stem}
    if stem.endswith("ying"):
        found.add(stem[:-4] + "y")
    elif stem.endswith("ing"):
        found.add(stem[:-3])
        found.add(stem[:-3] + "e")
    return frozenset(found)


class ProviderVocabulary:
    """Everything this control knows, derived from `provider_authority`."""

    def __init__(self, authority: dict[str, object]) -> None:
        owner = str(authority.get("owner", ""))
        #: The owner context's own final segment - `control.registry.provider`
        #: gives `provider`. Never transcribed; a renamed owner renames this.
        self.provider_token = owner.rsplit(".", 1)[-1] if owner else ""
        # Narrowed rather than asserted: a `fields_owned` that is not a sequence
        # yields no concern, which makes the vocabulary unusable and the gate
        # FAIL. A malformed declaration must never read as "nothing is owned".
        declared = authority.get("fields_owned")
        raw_concerns = declared if isinstance(declared, (list, tuple)) else ()
        self.concerns: dict[str, frozenset[str]] = {
            str(concern): tokens(str(concern)) for concern in raw_concerns
        }
        forbidden: set[str] = set()
        for key, value in authority.items():
            match = _PERMISSION_KEY.match(str(key))
            if match and value is False:
                forbidden |= _forms(match.group("stem"))
        self.forbidden_operations = frozenset(forbidden)
        #: The map calls these consumers `reference_only`, and ADR-0003 has the
        #: Capability Graph hold `provider_refs` resolved at query time. Holding
        #: a reference is therefore the permitted shape, and only that.
        self.reference_tokens = frozenset({"reference", "ref", "refs"})

    @property
    def usable(self) -> bool:
        return bool(self.provider_token and self.concerns)

    def concern_in(self, name: str) -> str | None:
        """The owned concern a name embeds, or None.

        Requires the provider token AND every token of the concern, so
        `worker_health` and `healthy` do not match while `provider_health` and
        `ProviderHealthCache` do.
        """
        found = tokens(name)
        if self.provider_token not in found:
            return None
        for concern, needed in self.concerns.items():
            if needed <= found:
                return concern
        return None

    def bare_concern(self, name: str) -> str | None:
        """A name that IS an owned concern, with no qualifier at all."""
        found = tokens(name)
        for concern, needed in self.concerns.items():
            if found == needed:
                return concern
        return None

    def operation_in(self, name: str) -> str | None:
        """A provider-qualified name carrying an operation the map forbids."""
        found = tokens(name)
        if self.provider_token not in found:
            return None
        hit = sorted(found & self.forbidden_operations)
        return hit[0] if hit else None

    def is_provider_shaped(self, name: str) -> bool:
        return self.provider_token in tokens(name)

    def is_reference_shaped(self, name: str) -> bool:
        return bool(tokens(name) & self.reference_tokens)


class ConsumerScan(ast.NodeVisitor):
    """Collects ARK-REQ-0053 violations in one reference-only consumer module."""

    def __init__(self, vocabulary: ProviderVocabulary, where: str) -> None:
        self.vocabulary = vocabulary
        self.where = where
        self.violations: list[str] = []
        self._class_stack: list[str] = []

    # -- reporting ------------------------------------------------------------

    def _flag(self, line: int, what: str) -> None:
        self.violations.append(f"{self.where}:{line}: {what}")

    def _check_name(self, name: str, line: int, kind: str) -> None:
        concern = self.vocabulary.concern_in(name)
        if concern:
            self._flag(
                line,
                f"{kind} {name!r} holds the provider-owned concern {concern!r}; "
                "ARK-REQ-0053 forbids storing, caching, mirroring, defaulting or "
                "re-deriving it outside the registry",
            )
            return
        operation = self.vocabulary.operation_in(name)
        if operation:
            self._flag(
                line,
                f"{kind} {name!r} performs {operation!r} on provider data, which "
                "the authority map declares not permitted",
            )
            return
        if self._class_stack and self.vocabulary.is_provider_shaped(
            self._class_stack[-1]
        ):
            bare = self.vocabulary.bare_concern(name)
            if bare:
                self._flag(
                    line,
                    f"{kind} {name!r} in provider-shaped class "
                    f"{self._class_stack[-1]!r} mirrors the owned concern {bare!r}",
                )

    # -- binding constructs ---------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._check_name(node.name, node.lineno, "class")
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._check_name(node.name, node.lineno, "function")
        args = node.args
        defaulted = list(zip(args.args[len(args.args) - len(args.defaults):],
                             args.defaults, strict=False))
        defaulted += [
            (a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=False)
            if d is not None
        ]
        for arg, _default in defaulted:
            self._check_name(arg.arg, arg.lineno, "defaulted parameter")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._target(node.target)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._target(target)
        self.generic_visit(node)

    def _target(self, target: ast.expr) -> None:
        if isinstance(target, ast.Name):
            self._check_name(target.id, target.lineno, "binding")
        elif isinstance(target, ast.Attribute):
            self._check_name(target.attr, target.lineno, "attribute")
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._target(element)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key in node.keys:
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and _IDENTIFIER_LIKE.match(key.value)
            ):
                self._check_name(key.value, key.lineno, "dict key")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # `Field(alias="provider_health")` renames a field without renaming the
        # concern. Only identifier-shaped keyword values are subjects, so a
        # sentence in `description=` is prose and not an alias.
        for keyword in node.keywords:
            value = keyword.value
            if (
                isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and _IDENTIFIER_LIKE.match(value.value)
            ):
                self._check_name(value.value, value.lineno, "aliased name")
        self.generic_visit(node)


def retained_values(
    vocabulary: ProviderVocabulary, tree: ast.AST, where: str
) -> list[str]:
    """Provider values kept beyond the call that obtained them.

    A LOCAL is how a consumer legitimately uses a query result and is not a
    subject: `record = registry.resolve(ref)` inside a function stores nothing.
    Assigning that value to `self.<attr>` or to a module-level name is storage,
    and storage is what ARK-REQ-0053 forbids. Names carrying a reference token
    are exempt in both positions, because holding a reference is precisely what
    a reference-only consumer may do (ADR-0003, `provider_record.md` §2.3).
    """
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        sources = sorted(
            {
                name.id
                for name in ast.walk(node.value)
                if isinstance(name, ast.Name)
                and vocabulary.is_provider_shaped(name.id)
                and not vocabulary.is_reference_shaped(name.id)
            }
            if node.value is not None
            else set()
        )
        if not sources:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            kept = _retaining_target(vocabulary, target)
            if kept:
                found.append(
                    f"{where}:{node.lineno}: {kept} retains provider value(s) "
                    f"{sources}; a reference-only consumer resolves from the "
                    "registry at query time and keeps no copy"
                )
    return found


def _retaining_target(vocabulary: ProviderVocabulary, target: ast.expr) -> str | None:
    """The name of a target that outlives the call, or None for a local."""
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        if target.value.id == "self" and not vocabulary.is_reference_shaped(
            target.attr
        ):
            return f"attribute 'self.{target.attr}'"
    return None


def module_paths(root: pathlib.Path) -> list[pathlib.Path]:
    """Every Python module under a consumer's declared root, scanned fresh.

    Discovery is by walk rather than by list, so a module added to a consumer
    tomorrow is covered without editing anything.
    """
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def scan_module(
    vocabulary: ProviderVocabulary, path: pathlib.Path, where: str
) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    scan = ConsumerScan(vocabulary, where)
    scan.visit(tree)
    return scan.violations + retained_values(vocabulary, tree, where)
