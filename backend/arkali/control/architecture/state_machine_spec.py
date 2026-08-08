"""Parser for the canonical state-machine inventory (ARK-REQ-0043).

Owner: control.architecture (Protected Core) - the map assigns
`architecture_rules_and_budgets` here, and "the twelve critical entities use
validated state machines" is such a rule.

NO SHADOW MODEL (F-0013). The twelve executable definitions delivered in Phase 3
are the *implementation* authority for their own machines, but they are not
permitted to drift from the canonical specification. This module parses
docs/canonical/STATE_MACHINES.md at call time and holds no machine, state or
transition of its own, so the reconciliation test compares the executable
definitions against the document rather than against a second private copy.

This module deliberately does not import the twelve definition modules. They are
owned by contexts at equal or higher layer rank, and `allow_same_layer: false`
plus `allow_higher_layer: false` forbid that direction. Reconciliation is
performed by the test tier, which sits outside the context graph.

Normalisation rules, stated explicitly because they are interpretation:
  * a machine name is normalised to the authority map's key by removing spaces
    and "/" ("Backup/Restore" -> "BackupRestore");
  * `any` expands to every declared state; `any pre-X` to the states listed
    before X on the States line; `WAITING_*` to the states with that prefix;
  * wildcard expansion never yields a self-loop, since "any -> DISABLED" plainly
    does not assert "DISABLED -> DISABLED". Explicitly written pairs are kept
    exactly as written;
  * a state is terminal iff the parsed relation gives it no outgoing edge. This
    is derived, never declared twice.
"""

from __future__ import annotations

import pathlib
import re

from pydantic import BaseModel, ConfigDict

from arkali.kernel.contracts.errors import AuthoritativeSourceError

STATE_MACHINES_RELPATH = "docs/canonical/STATE_MACHINES.md"

_HEADER = re.compile(
    r"^###\s+(?P<index>\d+)\.\s+(?P<name>.+?)\s+[—-]\s+authority\s+`(?P<authority>[^`]+)`",
    re.M,
)
_STATES = re.compile(r"^States:\s*(?P<body>.+)$", re.M)
_TRANSITIONS = re.compile(r"^Transitions:\s*(?P<body>.+)$", re.M)
_FORBIDDEN = re.compile(r"^Forbidden:\s*(?P<body>.+)$", re.M)
_BACKTICKED = re.compile(r"`([^`]+)`")
_ARROW = re.compile(r"(→|↔)")


def normalise_machine_name(raw: str) -> str:
    """Canonical document name -> authority map key."""
    return raw.replace("/", "").replace(" ", "").strip()


class MachineSpec(BaseModel):
    """One machine exactly as the canonical inventory declares it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    machine: str
    document_name: str
    authority: str
    states: tuple[str, ...]
    transitions: tuple[tuple[str, str], ...]
    forbidden: tuple[tuple[str, str], ...]

    @property
    def transition_set(self) -> frozenset[tuple[str, str]]:
        return frozenset(self.transitions)

    @property
    def forbidden_set(self) -> frozenset[tuple[str, str]]:
        return frozenset(self.forbidden)

    @property
    def terminal_states(self) -> tuple[str, ...]:
        """Derived: a state with no outgoing edge in the declared relation."""
        with_exit = {src for src, _ in self.transitions}
        return tuple(s for s in self.states if s not in with_exit)


def _expand(token: str, states: tuple[str, ...]) -> tuple[list[str], bool]:
    """Resolve one node token to concrete states. Returns (states, is_wildcard)."""
    text = token.replace("**", "").replace("`", "").strip()
    if text.startswith("{") and text.endswith("}"):
        return [part.strip() for part in text[1:-1].split(",") if part.strip()], False
    if text == "any":
        return list(states), True
    if text.startswith("any pre-"):
        pivot = text[len("any pre-"):].strip()
        if pivot not in states:
            raise AuthoritativeSourceError(
                f"'any pre-{pivot}' names an undeclared state",
                source=STATE_MACHINES_RELPATH,
            )
        return list(states[: states.index(pivot)]), True
    if text.endswith("*"):
        prefix = text[:-1]
        return [s for s in states if s.startswith(prefix)], True
    return [text], False


def _pairs(segment: str, states: tuple[str, ...]) -> list[tuple[str, str]]:
    """Expand one `A→B↔C` chain into concrete ordered pairs."""
    parts = [p for p in _ARROW.split(segment) if p.strip()]
    if len(parts) < 3:
        return []
    nodes: list[tuple[list[str], bool]] = []
    operators: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 0:
            nodes.append(_expand(part, states))
        else:
            operators.append(part.strip())
    found: list[tuple[str, str]] = []
    for position, operator in enumerate(operators):
        left, left_wild = nodes[position]
        right, right_wild = nodes[position + 1]
        wildcard = left_wild or right_wild
        for src in left:
            for dst in right:
                if wildcard and src == dst:
                    continue
                found.append((src, dst))
                if operator == "↔":
                    found.append((dst, src))
    return found


def _split_top_level(body: str, separator: str) -> list[str]:
    """Split on a separator that is not inside `{...}`."""
    out: list[str] = []
    depth = 0
    current: list[str] = []
    for char in body:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        if char == separator and depth == 0:
            out.append("".join(current))
            current = []
            continue
        current.append(char)
    out.append("".join(current))
    return [part.strip() for part in out if part.strip()]


def _parse_block(match: re.Match[str], block: str) -> MachineSpec:
    document_name = match.group("name").strip()
    states_match = _STATES.search(block)
    transitions_match = _TRANSITIONS.search(block)
    if states_match is None or transitions_match is None:
        raise AuthoritativeSourceError(
            f"machine {document_name!r} lacks a States or Transitions line",
            source=STATE_MACHINES_RELPATH,
        )
    states = tuple(_BACKTICKED.findall(states_match.group("body")))
    if not states:
        raise AuthoritativeSourceError(
            f"machine {document_name!r} declares no states",
            source=STATE_MACHINES_RELPATH,
        )
    transitions: list[tuple[str, str]] = []
    for segment in _split_top_level(transitions_match.group("body"), ";"):
        transitions.extend(_pairs(segment, states))

    forbidden: list[tuple[str, str]] = []
    forbidden_match = _FORBIDDEN.search(block)
    if forbidden_match is not None:
        for segment in _split_top_level(forbidden_match.group("body"), ","):
            forbidden.extend(_pairs(segment, states))

    unknown = sorted(
        {s for pair in transitions + forbidden for s in pair} - set(states)
    )
    if unknown:
        raise AuthoritativeSourceError(
            f"machine {document_name!r} references undeclared states {unknown}",
            source=STATE_MACHINES_RELPATH,
        )
    return MachineSpec(
        machine=normalise_machine_name(document_name),
        document_name=document_name,
        authority=match.group("authority").strip(),
        states=states,
        transitions=tuple(dict.fromkeys(transitions)),
        forbidden=tuple(dict.fromkeys(forbidden)),
    )


class StateMachineInventory:
    """Every machine declared by the canonical inventory. Construct with `load`."""

    def __init__(self, machines: dict[str, MachineSpec], source_path: str) -> None:
        self.machines = machines
        self.source_path = source_path

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> StateMachineInventory:
        path = repo_root / STATE_MACHINES_RELPATH
        if not path.is_file():
            raise AuthoritativeSourceError(
                "state machine inventory not found", source=str(path)
            )
        text = path.read_text(encoding="utf-8")
        headers = list(_HEADER.finditer(text))
        if not headers:
            raise AuthoritativeSourceError(
                "no machine declarations parsed", source=str(path)
            )
        machines: dict[str, MachineSpec] = {}
        for position, match in enumerate(headers):
            end = (
                headers[position + 1].start()
                if position + 1 < len(headers)
                else len(text)
            )
            spec = _parse_block(match, text[match.start():end])
            if spec.machine in machines:
                raise AuthoritativeSourceError(
                    f"duplicate machine {spec.machine!r}", source=str(path)
                )
            machines[spec.machine] = spec
        return cls(machines, str(path))

    def __len__(self) -> int:
        return len(self.machines)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self.machines))

    def get(self, machine: str) -> MachineSpec:
        spec = self.machines.get(machine)
        if spec is None:
            raise AuthoritativeSourceError(
                f"unknown machine {machine!r}", source=self.source_path
            )
        return spec
