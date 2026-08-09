"""Structural controls on C-14 (ARK-REQ-0057, ARK-REQ-0012, ADR-0006).

Four ways the artifact plane could quietly stop being what it claims:

* a **shadow identity authority** - an artifact id produced anywhere except from
  the bytes. Identity a caller can choose is identity that can disagree with
  content, which is the single failure content addressing exists to prevent;
* a **shadow audit chain** built inside `evidence.artifact`.
  `VERIFICATION_ARCHITECTURE.md` section 2.2 rule 7 gives the chain to
  `evidence.audit`, which is Protected Core and is Package 2. A chain grown here
  would be a second authority that no gate would notice, because both live in the
  same layer;
* a **second persistence authority** - an engine, a driver or engine-specific SQL
  in a context that ADR-0006 confines to `kernel.persistence`;
* a **Stable mutation path** - naming `WRITE_STABLE_FILE` or `ROLLBACK_STABLE`
  from a context that writes files.

Every check reads the deployed source with `ast` or with comments stripped, so
the prose explaining a ban never trips the ban.
"""

from __future__ import annotations

import ast
import pathlib
import re
from typing import Final

import pytest

from arkali.evidence.artifact import content_address
from arkali.evidence.artifact.records import (
    ArtifactParentEdge,
    ArtifactProvenanceRecord,
    ArtifactRecord,
)

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
CONTEXT: Final[pathlib.Path] = REPO / "backend" / "arkali" / "evidence" / "artifact"
CONTRACT_DOC: Final[pathlib.Path] = REPO / "docs" / "contracts" / "artifact.md"

#: Canonical metadata named by MS section Artifact Fabric and VDC section
#: Provenance. Both lists are identical; this is that list, and the reconciliation
#: below proves every item has a home.
CANONICAL_METADATA: Final[tuple[str, ...]] = (
    "content hash", "producer agent", "provider/model", "task ID",
    "specification version", "context hash", "parent artifacts",
    "normalization", "tests", "evidence", "timestamps",
)


def modules() -> list[pathlib.Path]:
    found = sorted(p for p in CONTEXT.rglob("*.py") if p.name != "__init__.py")
    assert found, "no artifact module was found; this control would be vacuous"
    return found


def source_of(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def strip_comments(text: str) -> str:
    """Remove docstrings and comments so prose cannot satisfy or trip a check."""
    tree = ast.parse(text)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    for doc in docstrings:
        text = text.replace(doc, "")
    return re.sub(r"#[^\n]*", "", text)


def called_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


class TestIdentityHasOneAuthority:
    def test_only_content_address_computes_a_digest(self) -> None:
        """NEGATIVE CONTROL: no second hashing site may exist in this context."""
        for module in modules():
            if module.name == "content_address.py":
                continue
            body = strip_comments(source_of(module))
            for forbidden in ("hashlib", "sha256(", "md5(", "blake2", "sha1("):
                assert forbidden not in body, (
                    f"{module.name} computes a digest of its own; "
                    "content_address.py is the only identity authority"
                )

    def test_the_address_helper_really_hashes(self) -> None:
        """Otherwise the check above is vacuous."""
        assert "hashlib" in source_of(CONTEXT / "content_address.py")

    def test_no_module_accepts_an_artifact_id_argument(self) -> None:
        """Identity is derived. A parameter named for it would be a way in."""
        for module in modules():
            tree = ast.parse(source_of(module))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                if node.name in {"__init__", "path_for", "contains", "get",
                                 "require", "provenance_of", "parents_of",
                                 "verify", "content_of", "assert_derived_identity",
                                 "_refuse", "resolve", "provenance_ref_of",
                                 "parse", "is_address", "matches", "relative_path",
                                 "address_of", "digest_of"}:
                    continue
                supplied = {a.arg for a in node.args.args} | {
                    a.arg for a in node.args.kwonlyargs
                }
                assert "artifact_id" not in supplied, (
                    f"{module.name}::{node.name} accepts an artifact_id; identity "
                    "must be computed from bytes, never supplied"
                )

    def test_registration_derives_the_address_from_the_payload(self) -> None:
        store = ast.parse(source_of(CONTEXT / "store.py"))
        register = next(
            n for n in ast.walk(store)
            if isinstance(n, ast.FunctionDef) and n.name == "register"
        )
        assert "put" in called_names(register), (
            "register does not obtain the address from the blob store, so the "
            "identity it records may not be the identity of the bytes"
        )


class TestNoShadowAuditChain:
    def test_this_context_builds_no_audit_chain(self) -> None:
        """C-15 belongs to `evidence.audit` (Protected Core), and is Package 2."""
        forbidden = re.compile(
            r"\b(AuditRecord|AuditChain|audit_chain|append_audit|chain_head|"
            r"previous_hash|prev_hash|merkle)\b"
        )
        for module in modules():
            found = forbidden.search(strip_comments(source_of(module)))
            assert found is None, (
                f"{module.name} contains {found.group(0)!r}, which is an audit "
                "chain construct. evidence.audit owns the chain "
                "(VERIFICATION_ARCHITECTURE section 2.2 rule 7)."
            )

    def test_this_context_does_not_import_evidence_audit(self) -> None:
        for module in modules():
            tree = ast.parse(source_of(module))
            imported = {
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module is not None
            }
            assert not any(m.startswith("arkali.evidence.audit") for m in imported), (
                f"{module.name} imports evidence.audit, which is not built yet"
            )

    def test_evidence_is_stored_as_references_only(self) -> None:
        """The provenance column holds ids, not records."""
        column = ArtifactProvenanceRecord.__table__.columns["evidence"]
        assert column.type.__class__.__name__ == "JSON"


class TestNoSecondPersistenceAuthority:
    def test_no_engine_driver_or_raw_sql_in_this_context(self) -> None:
        """ADR-0006 / ARK-REQ-0012, asserted on the deployed source."""
        banned_calls = {
            "create_engine", "create_async_engine", "sessionmaker",
            "async_sessionmaker", "declarative_base", "text", "exec_driver_sql",
        }
        banned_imports = {"sqlite3", "psycopg", "psycopg2", "asyncpg"}
        for module in modules():
            tree = ast.parse(source_of(module))
            offending = called_names(tree) & banned_calls
            assert offending == set(), (
                f"{module.name} calls {sorted(offending)}; the engine is built "
                "only by kernel.persistence"
            )
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name.split(".")[0] not in banned_imports
                if isinstance(node, ast.ImportFrom) and node.module:
                    root = node.module.split(".")[0]
                    assert root not in banned_imports
                    assert not node.module.startswith("sqlalchemy.dialects")

    def test_the_declarative_base_comes_from_kernel_persistence(self) -> None:
        for record in (ArtifactRecord, ArtifactProvenanceRecord, ArtifactParentEdge):
            bases = {base.__name__ for base in record.__mro__}
            assert "PersistenceBase" in bases, (
                f"{record.__name__} does not use the kernel declarative base"
            )

    def test_column_types_stay_engine_neutral(self) -> None:
        """PostgreSQL-readiness is the abstraction, not a claim of operation."""
        permitted = {"String", "Integer", "DateTime", "JSON"}
        for record in (ArtifactRecord, ArtifactProvenanceRecord, ArtifactParentEdge):
            for column in record.__table__.columns:
                assert column.type.__class__.__name__ in permitted, (
                    f"{record.__tablename__}.{column.name} uses "
                    f"{column.type.__class__.__name__}, which is not in the "
                    "engine-neutral set"
                )


class TestNoStableMutationPath:
    def test_no_stable_operation_class_is_named(self) -> None:
        """This context writes files, so naming one would be a mutation path.

        SUBSTRING, NOT EXACT MATCH. The first version of this control compared
        whole string constants, so a docstring *containing* a class name passed
        it - and one did. Structure check 11 scans the raw source and caught what
        this missed, which is the right outcome for a repository validator and
        the wrong outcome for the control written specifically to guard this
        context. It now reads the source the same way the validator does, and
        the class names are derived from the authority map rather than listed,
        so the ban follows the canonical set.
        """
        from arkali.control.policy.operation_class import OperationClassVocabulary

        vocabulary = OperationClassVocabulary.load(REPO)
        declared = [
            name
            for name in vocabulary.names()
            if vocabulary.get(name).fixed in ("DENY", "RECOVERY_SUPERVISOR_ONLY")
        ]
        assert declared, "no stable-mutation class is declared; the check is vacuous"
        for module in modules():
            body = source_of(module)
            for name in declared:
                assert name not in body, (
                    f"{module.name} names the stable-mutation class {name!r} and "
                    "is capable of writing; structure check 11 treats that "
                    "combination as a Stable mutation path"
                )

    def test_the_only_write_class_requested_is_the_workspace_one(self) -> None:
        blob = strip_comments(source_of(CONTEXT / "blob_store.py"))
        assert "WRITE_WORKSPACE_FILE" in blob
        assert "READ_FILE" in blob

    def test_every_filesystem_write_passes_the_guard(self) -> None:
        """NEGATIVE CONTROL: an unguarded write would be a policy bypass."""
        tree = ast.parse(source_of(CONTEXT / "blob_store.py"))
        writers = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and {"write_bytes", "mkdir", "replace"} & called_names(node)
        ]
        assert writers, "the control is vacuous if nothing writes"
        for node in writers:
            assert "_guard" in called_names(node), (
                f"blob_store::{node.name} writes without a policy decision"
            )

    def test_nothing_deletes_a_stored_artifact(self) -> None:
        """An artifact store that can delete is not append-only."""
        for module in modules():
            names = called_names(ast.parse(source_of(module)))
            for destructive in ("unlink", "rmtree", "remove", "rmdir"):
                assert destructive not in names, (
                    f"{module.name} can delete stored content"
                )


class TestContractAndSchemaAgree:
    def test_the_contract_document_exists_and_names_this_phase(self) -> None:
        assert CONTRACT_DOC.is_file()
        text = CONTRACT_DOC.read_text(encoding="utf-8")
        assert "C-14" in text
        assert "`evidence.artifact`" in text

    @pytest.mark.parametrize("item", CANONICAL_METADATA)
    def test_every_canonical_metadata_item_is_mapped(self, item: str) -> None:
        """MS Artifact Fabric and VDC Provenance name eleven items; all must land."""
        assert item in CONTRACT_DOC.read_text(encoding="utf-8"), (
            f"the contract document does not say where {item!r} is stored"
        )

    def test_the_documented_columns_are_the_mapped_columns(self) -> None:
        """A column added without documenting it fails here, and vice versa."""
        text = CONTRACT_DOC.read_text(encoding="utf-8")
        for record in (ArtifactRecord, ArtifactProvenanceRecord, ArtifactParentEdge):
            for column in record.__table__.columns:
                assert f"`{column.name}`" in text, (
                    f"{record.__tablename__}.{column.name} is mapped but not "
                    "documented in docs/contracts/artifact.md"
                )

    def test_the_address_column_holds_exactly_one_address(self) -> None:
        length = ArtifactRecord.__table__.columns["artifact_id"].type.length
        assert length == len(content_address.address_of(b""))

    def test_the_c12_reference_column_is_wide_enough(self) -> None:
        """Why C-12 needed no change: a 71-character address fits String(200)."""
        from arkali.control.registry.project.records import ProjectRevisionRecord

        column = ProjectRevisionRecord.__table__.columns["provenance_ref"]
        assert column.type.length >= len(content_address.address_of(b""))


class TestDependencyDirection:
    def test_the_project_registry_does_not_import_the_artifact_context(self) -> None:
        """NEGATIVE CONTROL: rank 1 may never import rank 2.

        Asserted over the whole registry context, not just one module, because a
        single new import anywhere in it would invert the dependency.
        """
        registry = REPO / "backend" / "arkali" / "control" / "registry"
        checked = 0
        for module in sorted(registry.rglob("*.py")):
            checked += 1
            tree = ast.parse(module.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                module_name = (
                    node.module if isinstance(node, ast.ImportFrom) and node.module
                    else ""
                )
                assert not module_name.startswith("arkali.evidence"), (
                    f"{module.name} imports evidence.*; control is layer rank 1 "
                    "and evidence is rank 2"
                )
        assert checked, "the control is vacuous if no registry module was read"

    def test_the_artifact_context_reads_the_registry_and_not_the_reverse(self) -> None:
        link = ast.parse(source_of(CONTEXT / "revision_link.py"))
        imported = {
            node.module
            for node in ast.walk(link)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert "arkali.control.registry.project.records" in imported

    def test_the_registry_edge_is_confined_to_one_module(self) -> None:
        """Keeps `store.py` inside max_contexts_touched_by_module (ADR-0008)."""
        importers = []
        for module in modules():
            tree = ast.parse(source_of(module))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and node.module.startswith("arkali.control.registry")
                ):
                    importers.append(module.name)
        assert importers == ["revision_link.py"], (
            f"the registry edge has spread to {sorted(set(importers))}"
        )
