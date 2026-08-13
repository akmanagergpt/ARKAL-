"""Register-derived applicability and coverage over the C-16 graph."""

from __future__ import annotations

import pathlib
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from arkali.control.specification.register_parser import RequirementRegister
from arkali.control.specification.requirement_record import Classification


class _NodeView(Protocol):
    kind: str
    reference: str


class _EdgeView(Protocol):
    source: _NodeView
    target: _NodeView


class _GraphView(Protocol):
    nodes: tuple[_NodeView, ...]
    edges: tuple[_EdgeView, ...]
    paths: tuple[tuple[_NodeView, ...], ...]


class _Applicability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    requirement_id: str
    applicable: bool
    evaluated: bool
    rule: str | None


class _RequirementCoverage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    requirement_id: str
    applicable: bool
    passed: bool
    required_evidence: tuple[str, ...]
    present_evidence: tuple[str, ...]


class _Coverage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    requirements: tuple[_RequirementCoverage, ...]
    requirement_numerator: int
    requirement_denominator: int
    evidence_numerator: int
    evidence_denominator: int

    @property
    def requirement_fraction(self) -> tuple[int, int]:
        return self.requirement_numerator, self.requirement_denominator

    @property
    def evidence_fraction(self) -> tuple[int, int]:
        return self.evidence_numerator, self.evidence_denominator


_COMPARE = re.compile(
    r"^(?P<key>[a-z][a-z0-9_.<>-]*)\s*(?P<op>==|>=|>)\s*"
    r"(?P<value>true|false|\d+)$", re.I
)
_MEMBER = re.compile(
    r"^(?P<key>[a-z][a-z0-9_.<>-]*)\s+in\s+\{(?P<values>[^}]+)\}$", re.I
)


def _value(text: str) -> object:
    normal = text.strip()
    if normal.lower() in {"true", "false"}:
        return normal.lower() == "true"
    try:
        return Decimal(normal)
    except InvalidOperation:
        return normal


def _atom(expression: str, state: Mapping[str, object]) -> bool | None:
    member = _MEMBER.fullmatch(expression.strip())
    if member:
        key = member.group("key")
        if key not in state:
            return None
        choices = {_value(item) for item in member.group("values").split(",")}
        return state[key] in choices
    comparison = _COMPARE.fullmatch(expression.strip())
    if comparison is None or comparison.group("key") not in state:
        return None
    actual = state[comparison.group("key")]
    expected = _value(comparison.group("value"))
    if comparison.group("op") == "==":
        return actual == expected
    if isinstance(actual, bool) or not isinstance(actual, (int, float, Decimal)):
        return None
    numeric_actual = Decimal(str(actual))
    if not isinstance(expected, Decimal):
        return None
    if comparison.group("op") == ">=":
        return numeric_actual >= expected
    return numeric_actual > expected


def _dimension_rule(state: Mapping[str, object]) -> bool | None:
    dimensions = (
        state.get("hardware.probe.gpu_available"),
        state.get("hardware.probe.vram_available"),
    )
    providers = tuple(
        value for key, value in state.items()
        if re.fullmatch(r"provider\.registry\.[^.]+\.cost_reporting", key)
    )
    if not providers and all(value is None for value in dimensions):
        return None
    return any(value is True for value in (*dimensions, *providers))


def _fallback_rule(expressions: list[str], state: Mapping[str, object]) -> bool | None:
    first = _atom(expressions[0], state)
    second = _atom(expressions[1].replace(":", " =="), state)
    if first is True or second is True:
        return True
    if first is None or second is None:
        return None
    return False


def _reference_answers(
    rule: str, state: Mapping[str, object], register: RequirementRegister
) -> tuple[bool | None, ...]:
    answers: list[bool | None] = []
    for reference in re.findall(r"(ARK-REQ-\d{4}) applicable", rule):
        resolved = _applicability(register, reference, state)
        answers.append(resolved.applicable if resolved.evaluated else None)
    return tuple(answers)


def _evaluate_rule(
    rule: str, state: Mapping[str, object], register: RequirementRegister
) -> bool | None:
    if "all evaluate true" in rule:
        return True
    if "Per dimension:" in rule:
        return _dimension_rule(state)
    expressions = re.findall(r"`([^`]+)`", rule)
    if "outside this set" in rule and len(expressions) == 2:
        return _fallback_rule(expressions, state)
    clean = " AND ".join(expressions) if expressions else rule.strip()
    answers = tuple(
        _atom(part.strip(), state) for part in re.split(r"\s+AND\s+", clean)
    )
    answers += _reference_answers(rule, state, register)
    if any(answer is None for answer in answers):
        return None
    return all(answer is True for answer in answers)


def _applicability(
    register: RequirementRegister, requirement_id: str, state: Mapping[str, object]
) -> _Applicability:
    record = register.get(requirement_id)  # an unregistered claim fails here
    if record.classification is Classification.MANDATORY:
        return _Applicability(
            requirement_id=requirement_id, applicable=True, evaluated=True, rule=None
        )
    if record.classification is Classification.OPTIONAL:
        return _Applicability(
            requirement_id=requirement_id, applicable=False, evaluated=True, rule=None
        )
    rule = register.applicability_rule(requirement_id)
    answer = None if rule is None else _evaluate_rule(rule, state, register)
    return _Applicability(
        requirement_id=requirement_id,
        applicable=True if answer is None else answer,
        evaluated=answer is not None,
        rule=rule,
    )


def _passing_paths(graph: _GraphView) -> dict[str, frozenset[str]]:
    passed: dict[str, set[str]] = {}
    for path in graph.paths:
        by_kind = {node.kind: node.reference for node in path}
        if by_kind.get("Result") == "PASS":
            passed.setdefault(by_kind["Requirement"], set()).add(by_kind["Test"])
    return {key: frozenset(value) for key, value in passed.items()}


def _coverage(
    graph: _GraphView, repo_root: pathlib.Path, state: Mapping[str, object]
) -> _Coverage:
    register = RequirementRegister.load(pathlib.Path(repo_root))
    passing = _passing_paths(graph)
    rows: list[_RequirementCoverage] = []
    for requirement_id in register.all_ids():
        record = register.get(requirement_id)
        applicability = _applicability(register, requirement_id, state)
        if record.classification is Classification.OPTIONAL or not applicability.applicable:
            continue
        observed = passing.get(requirement_id, frozenset())
        present = tuple(kind for kind in record.required_evidence if kind in observed)
        rows.append(
            _RequirementCoverage(
                requirement_id=requirement_id,
                applicable=True,
                passed=requirement_id in passing,
                required_evidence=record.required_evidence,
                present_evidence=present,
            )
        )
    return _Coverage(
        requirements=tuple(rows),
        requirement_numerator=sum(row.passed for row in rows),
        requirement_denominator=len(rows),
        evidence_numerator=sum(len(row.present_evidence) for row in rows),
        evidence_denominator=sum(len(row.required_evidence) for row in rows),
    )


class _EvidenceCoverageAuthority:
    @staticmethod
    def applicability(
        repo_root: pathlib.Path,
        requirement_id: str,
        recorded_state: Mapping[str, object],
    ) -> _Applicability:
        return _applicability(
            RequirementRegister.load(pathlib.Path(repo_root)),
            requirement_id,
            recorded_state,
        )

    @staticmethod
    def compute(
        graph: _GraphView,
        repo_root: pathlib.Path,
        recorded_state: Mapping[str, object],
    ) -> _Coverage:
        return _coverage(graph, repo_root, recorded_state)


evidence_coverage = _EvidenceCoverageAuthority()
