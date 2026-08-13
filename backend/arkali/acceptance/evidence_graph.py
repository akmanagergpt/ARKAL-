"""C-16 read-only Evidence Graph foundation.

Owner: ``acceptance.engine`` (Protected Core).

The graph is a derived view over C-15.  It stores nothing and never constructs
an audit row: ``evidence.audit`` remains the sole evidence writer and integrity
authority.  The path vocabulary is parsed from C-16's canonical inventory row
at call time, while requirement identity remains owned by the canonical
requirement register.

This package deliberately computes no coverage and issues no verdict.  Those
operations require applicability and passport accounting that are not part of
this foundation.
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import Iterable
from typing import Final, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict

from arkali.control.specification.register_parser import RequirementRegister
from arkali.kernel.contracts.error_base import AuthoritativeSourceError, ContractViolation

INVENTORY_RELPATH: Final[str] = "docs/canonical/CONTRACT_INVENTORY.md"
MASTER_RELPATH: Final[str] = "docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md"
CONTRACT_ID: Final[str] = "C-16"

_ROW = re.compile(
    r"^\|\s*C-16\s*\|\s*Evidence graph edge\s*\(`REQ→…→Result`\)\s*\|"
    r"\s*`acceptance\.engine`\s*\|.*\|\s*GRAPH\s*\|.*\|\s*STRICT\s*\|",
    re.M,
)
_PATH = re.compile(r"Evidence Graph links (?P<path>Requirement→[^.]+→Result)\.")


class _EvidenceGraphRefusal(ContractViolation):
    """C-16 cannot derive a complete graph from the supplied authority."""

    code = "ARK-ERR-0105"


class _EvidenceNode(BaseModel):
    """One typed node; identity is always a reference to an owning authority."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    reference: str


class _EvidenceEdge(BaseModel):
    """One adjacent directed edge in the canonical C-16 path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: _EvidenceNode
    target: _EvidenceNode


_T = TypeVar("_T", _EvidenceNode, _EvidenceEdge)


class _EvidenceGraph(BaseModel):
    """Immutable derived graph, bound to the verified C-15 chain head."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: str = CONTRACT_ID
    chain_head: str
    nodes: tuple[_EvidenceNode, ...]
    edges: tuple[_EvidenceEdge, ...]


class _ChainVerificationView(Protocol):
    """The integrity result C-15 exposes, without importing a sibling context."""

    verified: bool
    head: str | None

    @property
    def is_empty(self) -> bool: ...

    def render(self) -> str: ...


class _EvidenceRecordView(Protocol):
    """Only C-15 references C-16 reads to construct its derived view."""

    requirement_id: str
    contract_id: str | None
    artifact_id: str
    test_id: str | None
    record_hash: str
    result: str


class _EvidenceChainReader(Protocol):
    """Injected read port; C-15 remains the implementation and write authority."""

    def verify(self) -> _ChainVerificationView: ...

    def records(self) -> tuple[_EvidenceRecordView, ...]: ...


def _canonical_path(repo_root: pathlib.Path) -> tuple[str, ...]:
    """Read C-16's node order from the canonical contract inventory."""
    path = pathlib.Path(repo_root) / INVENTORY_RELPATH
    if not path.is_file():
        raise AuthoritativeSourceError("contract inventory not found", source=str(path))
    if _ROW.search(path.read_text(encoding="utf-8")) is None:
        raise AuthoritativeSourceError(
            "C-16 STRICT GRAPH declaration is absent or unparseable", source=str(path)
        )
    master = pathlib.Path(repo_root) / MASTER_RELPATH
    if not master.is_file():
        raise AuthoritativeSourceError("master specification not found", source=str(master))
    match = _PATH.search(master.read_text(encoding="utf-8"))
    if match is None:
        raise AuthoritativeSourceError(
            "canonical Evidence Graph path is absent or unparseable", source=str(master)
        )
    kinds = tuple(part.strip() for part in match.group("path").split("→"))
    if len(kinds) != 6 or any(not kind for kind in kinds) or len(set(kinds)) != 6:
        raise AuthoritativeSourceError(
            f"C-16 graph path is vacuous or malformed: {kinds!r}", source=str(path)
        )
    return kinds


def _record_nodes(
    record: _EvidenceRecordView, kinds: tuple[str, ...]
) -> tuple[_EvidenceNode, ...]:
    references = (
        record.requirement_id,
        record.contract_id,
        record.artifact_id,
        record.test_id,
        record.record_hash,
        record.result,
    )
    missing = [kinds[index] for index, value in enumerate(references) if not value]
    if missing:
        raise _EvidenceGraphRefusal(
            f"evidence record {record.record_hash!r} cannot form the complete "
            f"C-16 path; missing nodes: {missing}",
            source="docs/canonical/CONTRACT_INVENTORY.md C-16",
        )
    return tuple(
        _EvidenceNode(kind=kind, reference=str(reference))
        for kind, reference in zip(kinds, references, strict=True)
    )


def _unique(values: Iterable[_T]) -> tuple[_T, ...]:
    return tuple(dict.fromkeys(values))


def _derive_evidence_graph(
    chain: _EvidenceChainReader, repo_root: pathlib.Path
) -> _EvidenceGraph:
    """Derive C-16 from an intact, non-empty C-15 chain.

    Superseded records remain present because C-15 history is append-only.  A
    later package may determine which result counts; this foundation does not
    silently make that acceptance decision.
    """
    verification = chain.verify()
    if not verification.verified:
        raise _EvidenceGraphRefusal(
            f"the C-15 chain is corrupt: {verification.render()}",
            source="docs/contracts/audit_record.md section 5",
        )
    if verification.is_empty or verification.head is None:
        raise _EvidenceGraphRefusal(
            "an empty evidence chain cannot produce a C-16 graph",
            source="docs/canonical/VERIFICATION_ARCHITECTURE.md section 2",
        )

    register = RequirementRegister.load(pathlib.Path(repo_root))
    registered = frozenset(register.all_ids())
    kinds = _canonical_path(pathlib.Path(repo_root))
    node_stream: list[_EvidenceNode] = []
    edge_stream: list[_EvidenceEdge] = []
    for record in chain.records():
        if record.requirement_id not in registered:
            raise _EvidenceGraphRefusal(
                f"evidence names unregistered requirement {record.requirement_id!r}",
                source=register.source_path,
            )
        path_nodes = _record_nodes(record, kinds)
        node_stream.extend(path_nodes)
        edge_stream.extend(
            _EvidenceEdge(source=left, target=right)
            for left, right in zip(path_nodes, path_nodes[1:], strict=False)
        )
    return _EvidenceGraph(
        chain_head=verification.head,
        nodes=_unique(node_stream),
        edges=_unique(edge_stream),
    )


class _EvidenceGraphAuthority:
    """The single C-16 Package 1 entry point; state-free and read-only."""

    Refusal = _EvidenceGraphRefusal

    @staticmethod
    def canonical_path(repo_root: pathlib.Path) -> tuple[str, ...]:
        return _canonical_path(repo_root)

    @staticmethod
    def derive(chain: _EvidenceChainReader, repo_root: pathlib.Path) -> _EvidenceGraph:
        return _derive_evidence_graph(chain, repo_root)


# A service object rather than nine unrelated public symbols. The acceptance
# context was already at its ratified public-surface ceiling; C-16 adds one
# cohesive authority without widening that measured surface.
evidence_graph = _EvidenceGraphAuthority()
