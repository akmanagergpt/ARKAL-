"""Proof-of-Engineering Passport accounting over the C-16 projection.

This module records no evidence.  It preserves the identities already bound
into each C-16 path, groups register-owned obligations by capability (the
register's owning component), and derives the C-16 capability verdict from that
accounting.  Implementation evidence remains distinct from complete VERIFIED
evidence; neither producer opinion nor a file-presence claim can issue PASS.
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from arkali.acceptance.evidence_coverage import evidence_coverage
from arkali.acceptance.evidence_graph import evidence_graph
from arkali.control.policy.acceptance_boundary import AcceptanceBoundaryPolicy
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


class _CapabilityVerdict(BaseModel):
    """Evidence-derived result for one register-owned capability."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    capability: str
    implemented: bool
    verified: bool
    requirement_numerator: int
    requirement_denominator: int
    missing_requirements: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    required_human_gate: str | None

    @property
    def result(self) -> str:
        if self.verified:
            return "VERIFIED"
        if self.implemented:
            return "IMPLEMENTED_NOT_VERIFIED"
        return "NOT_VERIFIED"


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


def _capability_account(
    passport: _Passport, capability: str
) -> _CapabilityAccount:
    matches = tuple(
        account for account in passport.capabilities
        if account.capability == capability
    )
    if len(matches) != 1:
        raise evidence_graph.Refusal(
            f"capability {capability!r} has no unique applicable Passport account",
            source=REGISTER_RELPATH,
        )
    return matches[0]


def _reconcile_requirement(requirement: _RequirementAccount) -> None:
    derived_present = tuple(
        kind for kind in requirement.required_evidence
        if any(
            binding.result == "PASS" and binding.evidence_kind == kind
            for binding in requirement.bindings
        )
    )
    derived_missing = tuple(
        kind for kind in requirement.required_evidence
        if kind not in derived_present
    )
    if (
        requirement.present_evidence != derived_present
        or requirement.missing_evidence != derived_missing
    ):
        raise evidence_graph.Refusal(
            f"Passport account for {requirement.requirement_id} is not "
            "reconciled to its bound C-16 evidence",
            source="docs/contracts/evidence_graph.md Package 3",
        )


def _reconcile_account(
    account: _CapabilityAccount,
) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    if account.requirement_denominator == 0:
        raise evidence_graph.Refusal(
            f"capability {account.capability!r} has a vacuous Passport denominator",
            source=REGISTER_RELPATH,
        )
    for requirement in account.requirements:
        _reconcile_requirement(requirement)
    derived_numerator = sum(
        requirement.evidence_complete for requirement in account.requirements
    )
    if (
        account.requirement_denominator != len(account.requirements)
        or account.requirement_numerator != derived_numerator
    ):
        raise evidence_graph.Refusal(
            f"Passport totals for {account.capability!r} are not reconciled",
            source="docs/contracts/evidence_graph.md Package 3",
        )
    missing_requirements = tuple(
        requirement.requirement_id for requirement in account.requirements
        if not requirement.evidence_complete
    )
    missing_evidence = tuple(
        f"{requirement.requirement_id}:{kind}"
        for requirement in account.requirements
        for kind in requirement.missing_evidence
    )
    return derived_numerator, missing_requirements, missing_evidence


def _verdict(
    passport: _Passport,
    capability: str,
    repo_root: pathlib.Path,
    required_human_gate: str | None,
    recorded_human_gates: tuple[str, ...],
) -> _CapabilityVerdict:
    account = _capability_account(passport, capability)
    derived_numerator, missing_requirements, missing_evidence = (
        _reconcile_account(account)
    )

    # This call is mandatory even for an evidence-incomplete result: the
    # Acceptance Engine may report non-verification, but it may never turn a
    # machine result into a substitute for a required human decision.
    AcceptanceBoundaryPolicy.load(repo_root).assert_machine_gate_boundary(
        required_gate=required_human_gate,
        recorded_human_gates=recorded_human_gates,
    )
    # "Implemented" is itself evidence-derived: at least one passing, fully
    # bound C-16 path must exist.  It is intentionally insufficient for
    # VERIFIED, which requires every applicable register obligation.
    implemented = any(
        requirement.bindings for requirement in account.requirements
    )
    verified = not missing_evidence and derived_numerator == len(account.requirements)
    return _CapabilityVerdict(
        capability=capability,
        implemented=implemented,
        verified=verified,
        requirement_numerator=account.requirement_numerator,
        requirement_denominator=account.requirement_denominator,
        missing_requirements=missing_requirements,
        missing_evidence=missing_evidence,
        required_human_gate=required_human_gate,
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

    @staticmethod
    def verdict(
        passport: _Passport,
        capability: str,
        repo_root: pathlib.Path,
        required_human_gate: str | None = None,
        recorded_human_gates: tuple[str, ...] = (),
    ) -> _CapabilityVerdict:
        return _verdict(
            passport,
            capability,
            pathlib.Path(repo_root),
            required_human_gate,
            recorded_human_gates,
        )


evidence_passport = _EvidencePassportAuthority()
