"""Structural controls on the C-14 / C-15 authority split.

`VERIFICATION_ARCHITECTURE.md` section 2.2 rule 7 gives `evidence.audit` the
chain and says no other context may write or amend an evidence record.
`ARCHITECTURE.md` section 3 gives `evidence.artifact` artifact identity and
provenance. The two sit in the same layer, so the dependency gate cannot tell
them apart - a duplicate authority here would be invisible to every gate the
repository runs. These controls are what make the split checkable:

* only `evidence.audit` writes the chain;
* only `evidence.artifact` mints artifact identity;
* neither becomes the other;
* the public authority has no amend/overwrite/delete escape;
* no stored flag substitutes for recomputing integrity.

Read from the deployed source with `ast`, so prose cannot satisfy a check.
"""

from __future__ import annotations

import ast
import pathlib
import re
from typing import Final

from arkali.evidence.audit.chain import AuditChain
from arkali.evidence.audit.integrity import DIGESTED_FIELDS
from arkali.evidence.audit.records import AuditRecord

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PACKAGE: Final[pathlib.Path] = REPO / "backend" / "arkali"
AUDIT: Final[pathlib.Path] = PACKAGE / "evidence" / "audit"
ARTIFACT: Final[pathlib.Path] = PACKAGE / "evidence" / "artifact"
CONTRACT_DOC: Final[pathlib.Path] = REPO / "docs" / "contracts" / "audit_record.md"

#: Names that would mean the chain had stopped being append-only.
MUTATION_NAMES: Final[tuple[str, ...]] = (
    "update", "amend", "overwrite", "replace", "delete", "purge", "rewrite",
    "edit", "truncate", "prune",
)


def modules(root: pathlib.Path) -> list[pathlib.Path]:
    found = sorted(p for p in root.rglob("*.py") if p.name != "__init__.py")
    assert found, f"no module under {root}; this control would be vacuous"
    return found


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """Source with docstrings and comments removed."""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                text = text.replace(doc, "")
    return re.sub(r"#[^\n]*", "", text)


def called(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


class TestEvidenceAuditIsTheSoleChainWriter:
    def test_no_other_context_constructs_an_evidence_record(self) -> None:
        """NEGATIVE CONTROL: scanned over the whole package, not one directory."""
        offenders = []
        for module in modules(PACKAGE):
            if AUDIT in module.parents:
                continue
            body = code_only(read(module))
            if "AuditRecord(" in body:
                offenders.append(module.relative_to(REPO).as_posix())
        assert offenders == [], (
            f"{offenders} construct an evidence record. VERIFICATION_ARCHITECTURE "
            "section 2.2 rule 7 gives the chain to evidence.audit alone."
        )

    def test_no_other_context_imports_the_chain_table(self) -> None:
        offenders = []
        for module in modules(PACKAGE):
            if AUDIT in module.parents:
                continue
            tree = ast.parse(read(module))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module == "arkali.evidence.audit.records"
                ):
                    offenders.append(module.relative_to(REPO).as_posix())
        assert offenders == [], (
            f"{offenders} import the evidence record table directly; callers use "
            "the append API, which is the only governed write path"
        )

    def test_the_audit_context_really_does_write(self) -> None:
        """Otherwise the two checks above are vacuous."""
        assert "AuditRecord(" in code_only(read(AUDIT / "chain.py"))

    def test_evidence_artifact_never_writes_the_chain(self) -> None:
        """The sharpest case: the sibling context, invisible to the layer gate."""
        for module in modules(ARTIFACT):
            body = code_only(read(module))
            assert "AuditRecord" not in body
            assert "arkali.evidence.audit" not in body


class TestEvidenceAuditMintsNoArtifactIdentity:
    def test_it_computes_no_digest_of_artifact_content(self) -> None:
        """C-14 is the identity authority; this context references, never derives."""
        for module in modules(AUDIT):
            body = code_only(read(module))
            for forbidden in ("hashlib", "sha256(", "md5(", "blake2"):
                assert forbidden not in body, (
                    f"{module.name} computes a digest of its own content; artifact "
                    "identity belongs to evidence.artifact"
                )

    def test_it_reuses_the_shared_kernel_primitive(self) -> None:
        """One address shape exists in the repository, and no sibling edge.

        Package 2's first shape imported `evidence.artifact.content_address`,
        which is a same-layer edge surviving only on the
        `evidence_write_from_any_layer` exemption - an exemption about writes,
        not about reading a sibling's module. The mechanism moved to rank 0
        instead, which both evidence contexts may reach legally.
        """
        tree = ast.parse(read(AUDIT / "integrity.py"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert "arkali.kernel.contracts.content_address" in imported
        assert not any(m.startswith("arkali.evidence.artifact") for m in imported)

    def test_no_module_in_this_context_imports_its_sibling(self) -> None:
        """NEGATIVE CONTROL: allow_same_layer is false and stays false."""
        for module in modules(AUDIT):
            tree = ast.parse(read(module))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert not node.module.startswith("arkali.evidence.artifact"), (
                        f"{module.name} imports evidence.artifact; the two are "
                        "siblings in the evidence layer and neither may import "
                        "the other"
                    )

    def test_the_artifact_reference_is_enforced_by_the_schema(self) -> None:
        """Linkage is the persisted foreign key, not an import of the sibling."""
        column = AuditRecord.__table__.columns["artifact_id"]
        assert {fk.target_fullname for fk in column.foreign_keys} == {
            "artifact.artifact_id"
        }
        assert "IntegrityError" in read(AUDIT / "chain.py"), (
            "the append path does not translate the schema's refusal into a "
            "typed domain error"
        )

    def test_it_stores_a_reference_not_a_copy_of_artifact_metadata(self) -> None:
        columns = {c.name for c in AuditRecord.__table__.columns}
        for copied in ("digest", "hash_algorithm", "byte_size", "normalization",
                       "producer_agent", "provider_model", "context_hash"):
            assert copied not in columns, (
                f"{copied!r} duplicates C-14 metadata into the audit chain"
            )
        assert "artifact_id" in columns

    def test_the_artifact_reference_is_a_real_foreign_key(self) -> None:
        column = AuditRecord.__table__.columns["artifact_id"]
        targets = {fk.target_fullname for fk in column.foreign_keys}
        assert targets == {"artifact.artifact_id"}


class TestAppendOnlySurface:
    def test_the_public_api_has_no_mutation_escape(self) -> None:
        public = {name for name in dir(AuditChain) if not name.startswith("_")}
        for forbidden in MUTATION_NAMES:
            assert not any(forbidden in name for name in public), (
                f"AuditChain exposes a {forbidden!r}-shaped method"
            )

    def test_no_module_in_the_context_calls_a_delete(self) -> None:
        """NEGATIVE CONTROL: a chain you can delete from is not a chain."""
        for module in modules(AUDIT):
            names = called(ast.parse(read(module)))
            for destructive in ("delete", "drop", "truncate", "execute_delete"):
                assert destructive not in names, (
                    f"{module.name} can remove an evidence record"
                )

    def test_both_immutability_guards_are_registered(self) -> None:
        source = read(AUDIT / "records.py")
        assert '"before_update"' in source
        assert '"before_delete"' in source


class TestIntegrityIsNeverTrusted:
    def test_no_stored_verification_flag_exists(self) -> None:
        columns = {c.name for c in AuditRecord.__table__.columns}
        for flag in ("integrity_verified", "verified", "is_valid", "checksum_ok",
                     "trusted", "validated"):
            assert flag not in columns

    def test_every_persisted_field_enters_the_digest(self) -> None:
        """A field outside the digest could be altered without detection."""
        columns = {c.name for c in AuditRecord.__table__.columns}
        outside = columns - set(DIGESTED_FIELDS) - {"record_hash"}
        assert outside == set(), (
            f"{sorted(outside)} are stored but not covered by the integrity "
            "digest, so they could be altered without detection"
        )

    def test_the_digest_covers_the_predecessor(self) -> None:
        assert "previous_hash" in DIGESTED_FIELDS
        assert "sequence" in DIGESTED_FIELDS


class TestNoStableMutationPathAndNoSecondPersistence:
    def test_no_stable_operation_class_is_named(self) -> None:
        from arkali.control.policy.operation_class import OperationClassVocabulary

        vocabulary = OperationClassVocabulary.load(REPO)
        declared = [
            name for name in vocabulary.names()
            if vocabulary.get(name).fixed in ("DENY", "RECOVERY_SUPERVISOR_ONLY")
        ]
        assert declared, "no stable-mutation class declared; the check is vacuous"
        for module in modules(AUDIT):
            body = read(module)
            for name in declared:
                assert name not in body, f"{module.name} names {name!r}"

    def test_no_engine_driver_or_raw_sql_in_this_context(self) -> None:
        banned = {"create_engine", "sessionmaker", "declarative_base", "text",
                  "exec_driver_sql"}
        for module in modules(AUDIT):
            tree = ast.parse(read(module))
            assert called(tree) & banned == set(), f"{module.name} builds an engine"
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert not node.module.startswith("sqlalchemy.dialects")
                    assert node.module.split(".")[0] != "sqlite3"

    def test_column_types_stay_engine_neutral(self) -> None:
        permitted = {"String", "Integer", "DateTime"}
        for column in AuditRecord.__table__.columns:
            assert column.type.__class__.__name__ in permitted


class TestContractAndSchemaAgree:
    def test_the_contract_document_exists_and_names_the_owner(self) -> None:
        assert CONTRACT_DOC.is_file()
        text = read(CONTRACT_DOC)
        assert "C-15" in text
        assert "`evidence.audit`" in text
        assert "Protected Core" in text

    def test_every_mapped_column_is_documented(self) -> None:
        text = read(CONTRACT_DOC)
        for column in AuditRecord.__table__.columns:
            assert f"`{column.name}`" in text, (
                f"audit_record.{column.name} is mapped but undocumented"
            )

    def test_the_document_states_what_the_contract_does_not_own(self) -> None:
        text = read(CONTRACT_DOC)
        assert "Phase 13" in text
        assert "C-14" in text
