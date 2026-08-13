"""Proof-of-Engineering Passport accounting over the C-16 projection.

This module records no evidence and issues no acceptance verdict.  It preserves
the identities already bound into each C-16 path and groups register-owned
obligations by capability (the register's owning component).
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from arkali.acceptance.evidence_coverage import evidence_coverage
from arkali.acceptance.evidence_graph import evidence_graph
from arkali.control.specification.register_parser import RequirementRegister

VDC_RELPATH = "docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md"
REGISTER_RELPATH = "docs/canonical/REQUIREMENT_REGISTER.md"

_PASSPORT = re.compile(
    r"^## Proof-of-Engineering Passport\s*$\s*"
    r"Every critical capability records applicable:\s*(?P<kinds>[^.]+)\.",
    re.M,
)
_KEYS = re.compile(r"^Evidence keys:\s*(?P<keys>.+)$", re.M)
_KEY = re.compile(r"`([a-z][a-z0-9]*)`(?:=[^·]+)?")


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


class _CoverageRow(Protocol):
    requirement_id: str
    required_evidence: tuple[str, ...]
    present_evidence: tuple[str, ...]


class _EvidenceBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    requirement_id: str
    evidence_kind: str
    contract_id: str
    artifact_id: str
    test_id: str
    evidence_id: str
    result: str


class _RequirementAccount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    requirement_id: str
    required_evidence: tuple[str, ...]
    present_evidence: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    bindings: tuple[_EvidenceBinding, ...]

    @property
    def evidence_complete(self) -> bool:
        return not self.missing_evidence


class _CapabilityAccount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    capability: str
    requirements: tuple[_RequirementAccount, ...]
    required_evidence: tuple[str, ...]
    requirement_numerator: int
    requirement_denominator: int


class _Passport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    applicable_evidence_vocabulary: tuple[str, ...]
    capabilities: tuple[_CapabilityAccount, ...]
    requirement_numerator: int
    requirement_denominator: int

    @property
    def completion_fraction(self) -> tuple[int, int]:
        return self.requirement_numerator, self.requirement_denominator


def _read(path: pathlib.Path, description: str) -> str:
    if not path.is_file():
        raise evidence_graph.Refusal(f"{description} not found", source=str(path))
    return path.read_text(encoding="utf-8")


def _vocabulary(repo_root: pathlib.Path) -> tuple[str, ...]:
    path = repo_root / VDC_RELPATH
    match = _PASSPORT.search(_read(path, "verification contract"))
    if match is None:
        raise evidence_graph.Refusal(
            "Proof-of-Engineering Passport vocabulary is absent or unparseable",
            source=str(path),
        )
    kinds = tuple(item.strip() for item in match.group("kinds").split(","))
    if not kinds or any(not item for item in kinds) or len(set(kinds)) != len(kinds):
        raise evidence_graph.Refusal(
            f"Passport evidence vocabulary is vacuous or malformed: {kinds!r}",
            source=str(path),
        )
    return kinds


def _registered_keys(repo_root: pathlib.Path) -> frozenset[str]:
    path = repo_root / REGISTER_RELPATH
    match = _KEYS.search(_read(path, "requirement register"))
    keys = frozenset(_KEY.findall(match.group("keys"))) if match else frozenset()
    if not keys:
        raise evidence_graph.Refusal(
            "register evidence-key declaration is absent or unparseable",
            source=str(path),
        )
    return keys


def _bindings(graph: _GraphView) -> dict[str, tuple[_EvidenceBinding, ...]]:
    grouped: dict[str, list[_EvidenceBinding]] = {}
    for path in graph.paths:
        nodes = {node.kind: node.reference for node in path}
        binding = _EvidenceBinding(
            requirement_id=nodes["Requirement"],
            evidence_kind=nodes["Test"],
            contract_id=nodes["Contract"],
            artifact_id=nodes["Artifact"],
            test_id=nodes["Test"],
            evidence_id=nodes["Evidence"],
            result=nodes["Result"],
        )
        grouped.setdefault(binding.requirement_id, []).append(binding)
    return {key: tuple(value) for key, value in grouped.items()}


def _account(
    row: _CoverageRow, register: RequirementRegister,
    allowed_keys: frozenset[str], bindings: dict[str, tuple[_EvidenceBinding, ...]],
) -> tuple[str, _RequirementAccount]:
    requirement_id = row.requirement_id
    required = row.required_evidence
    present = row.present_evidence
    unknown = set(required) - allowed_keys
    if unknown:
        raise evidence_graph.Refusal(
            f"requirement {requirement_id} uses undeclared evidence keys "
            f"{sorted(unknown)}",
            source=register.source_path,
        )
    passing = tuple(
        binding for binding in bindings.get(requirement_id, ())
        if binding.result == "PASS" and binding.evidence_kind in required
    )
    return register.get(requirement_id).owning_component, _RequirementAccount(
        requirement_id=requirement_id,
        required_evidence=required,
        present_evidence=present,
        missing_evidence=tuple(kind for kind in required if kind not in present),
        bindings=passing,
    )


def _build(
    graph: _GraphView, repo_root: pathlib.Path, state: Mapping[str, object]
) -> _Passport:
    root = pathlib.Path(repo_root)
    register = RequirementRegister.load(root)
    allowed_keys = _registered_keys(root)
    coverage = evidence_coverage.compute(graph, root, state)
    by_requirement = _bindings(graph)
    accounts: dict[str, list[_RequirementAccount]] = {}
    for row in coverage.requirements:
        capability, account = _account(row, register, allowed_keys, by_requirement)
        accounts.setdefault(capability, []).append(account)

    capabilities = tuple(
        _CapabilityAccount(
            capability=capability,
            requirements=tuple(requirements),
            required_evidence=tuple(dict.fromkeys(
                kind for requirement in requirements
                for kind in requirement.required_evidence
            )),
            requirement_numerator=sum(
                requirement.evidence_complete for requirement in requirements
            ),
            requirement_denominator=len(requirements),
        )
        for capability, requirements in sorted(accounts.items())
    )
    return _Passport(
        applicable_evidence_vocabulary=_vocabulary(root),
        capabilities=capabilities,
        requirement_numerator=sum(
            capability.requirement_numerator for capability in capabilities
        ),
        requirement_denominator=sum(
            capability.requirement_denominator for capability in capabilities
        ),
    )


class _EvidencePassportAuthority:
    @staticmethod
    def vocabulary(repo_root: pathlib.Path) -> tuple[str, ...]:
        return _vocabulary(pathlib.Path(repo_root))

    @staticmethod
    def build(
        graph: _GraphView,
        repo_root: pathlib.Path,
        recorded_state: Mapping[str, object],
    ) -> _Passport:
        return _build(graph, repo_root, recorded_state)


evidence_passport = _EvidencePassportAuthority()
