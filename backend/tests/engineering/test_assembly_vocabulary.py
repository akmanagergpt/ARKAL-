"""Phase 12 Package 1: canonical C-25 vocabularies fail closed."""

from __future__ import annotations

import pathlib
from typing import Final

import pytest

from arkali.engineering.candidate.assembly_vocabulary import (
    MASTER_SPEC_RELPATH,
    AssemblyVocabulary,
)
from arkali.engineering.candidate.errors import (
    UnknownAssemblyCheckError,
    UnknownProductComponentError,
)
from arkali.kernel.contracts.error_base import AuthoritativeSourceError

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]


def write_spec(root: pathlib.Path, products: str, checks: str) -> pathlib.Path:
    target = root / MASTER_SPEC_RELPATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"### Product Plane\n{products}.\n\n"
        f"## Semantic Candidate Assembly\nCandidate assembly validates {checks}.\n",
        encoding="utf-8",
    )
    return root


class TestLiveCanonicalVocabulary:
    def test_product_plane_components_are_loaded_from_the_specification(self) -> None:
        vocabulary = AssemblyVocabulary.load(REPO)
        assert vocabulary.product_ids() == (
            "working_copies",
            "candidate_products",
            "stable_products",
            "imported_projects",
            "generated_products",
            "ai_native_child_products",
            "product_evolution_sdk",
            "arkali_candidate_core",
        )

    def test_every_semantic_consistency_pair_is_loaded(self) -> None:
        vocabulary = AssemblyVocabulary.load(REPO)
        assert vocabulary.check_ids() == (
            "api_to_frontend",
            "api_to_qa",
            "db_to_models",
            "models_to_frontend",
            "requirements_to_implementation",
            "entrypoint_to_startup",
            "routes_to_browser",
            "dependencies_to_locks",
        )

    @pytest.mark.parametrize("product_count,check_count", [(2, 2), (3, 5), (7, 11)])
    def test_counts_follow_the_document(
        self, tmp_path: pathlib.Path, product_count: int, check_count: int
    ) -> None:
        products = ", ".join(f"Product {i}" for i in range(product_count))
        checks = ", ".join(f"left{i}↔right{i}" for i in range(check_count))
        vocabulary = AssemblyVocabulary.load(
            write_spec(tmp_path / f"{product_count}-{check_count}", products, checks)
        )
        assert len(vocabulary.products()) == product_count
        assert len(vocabulary.checks()) == check_count


class TestVocabularyRefusals:
    def test_unknown_product_and_check_are_distinct_refusals(self) -> None:
        vocabulary = AssemblyVocabulary.load(REPO)
        with pytest.raises(UnknownProductComponentError):
            vocabulary.require_product("Wishful Product")
        with pytest.raises(UnknownAssemblyCheckError):
            vocabulary.require_check("vibes↔confidence")

    def test_every_live_entry_resolves(self) -> None:
        vocabulary = AssemblyVocabulary.load(REPO)
        resolved_products = tuple(
            vocabulary.require_product(value) for value in vocabulary.products()
        )
        resolved_checks = tuple(
            vocabulary.require_check(value) for value in vocabulary.checks()
        )
        assert resolved_products == vocabulary.product_ids()
        assert resolved_checks == vocabulary.check_ids()

    def test_missing_document_is_refused(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(AuthoritativeSourceError, match="not found"):
            AssemblyVocabulary.load(tmp_path)

    @pytest.mark.parametrize(
        "products,checks,message",
        [
            ("Only", "a↔b, c↔d", "too few"),
            ("A, B", "only↔one", "too few"),
            ("A, A", "a↔b, c↔d", "duplicate"),
            ("A, B", "a↔b, no-pair", "consistency pair"),
        ],
    )
    def test_malformed_or_vacuous_declarations_fail_closed(
        self, tmp_path: pathlib.Path, products: str, checks: str, message: str
    ) -> None:
        with pytest.raises(AuthoritativeSourceError, match=message):
            AssemblyVocabulary.load(write_spec(tmp_path, products, checks))
