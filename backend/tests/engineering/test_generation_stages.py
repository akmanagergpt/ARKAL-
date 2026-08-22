from __future__ import annotations

import pathlib

import pytest

from arkali.engineering.factory.errors import StageVocabularyError
from arkali.engineering.factory.generation_stages import StageVocabulary

REPO = pathlib.Path(__file__).resolve().parents[3]


def test_loads_the_real_document() -> None:
    vocabulary = StageVocabulary.load(REPO)
    stages = vocabulary.stages()
    assert [s.name for s in stages] == [
        "backend_contract", "backend_schema", "backend_implementation",
        "backend_cors_boundary", "backend_tests", "product_ux_spec",
        "frontend_client", "frontend_ui", "frontend_tests_config", "manifests",
    ]


def test_stages_are_ordered_one_through_n() -> None:
    stages = StageVocabulary.load(REPO).stages()
    assert [s.order for s in stages] == list(range(1, len(stages) + 1))


def test_every_input_is_a_strictly_earlier_stage() -> None:
    stages = StageVocabulary.load(REPO).stages()
    seen: list[str] = []
    for declaration in stages:
        for input_name in declaration.inputs:
            assert input_name in seen, (
                f"{declaration.name!r} declares input {input_name!r} which "
                "is not a strictly-earlier stage"
            )
            assert input_name != declaration.name
        seen.append(declaration.name)


def test_first_stage_declares_no_inputs() -> None:
    vocabulary = StageVocabulary.load(REPO)
    assert vocabulary.stage("backend_contract").inputs == ()


def test_manifests_stage_depends_on_every_prior_stage() -> None:
    vocabulary = StageVocabulary.load(REPO)
    manifests = vocabulary.stage("manifests")
    prior_names = {s.name for s in vocabulary.stages() if s.name != "manifests"}
    assert set(manifests.inputs) == prior_names


def test_unknown_stage_name_refuses() -> None:
    vocabulary = StageVocabulary.load(REPO)
    with pytest.raises(StageVocabularyError):
        vocabulary.stage("does_not_exist")


def test_missing_document_refuses(tmp_path: pathlib.Path) -> None:
    with pytest.raises(StageVocabularyError):
        StageVocabulary.load(tmp_path)


def test_non_sequential_numbering_refuses(tmp_path: pathlib.Path) -> None:
    doc = tmp_path / "backend/arkali/engineering/factory/STAGED_GENERATION_STAGES.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "### 1. first\nInputs: none\nRule: do the first thing.\n\n"
        "### 3. second\nInputs: first\nRule: do the second thing.\n",
        encoding="utf-8",
    )
    with pytest.raises(StageVocabularyError):
        StageVocabulary.load(tmp_path)


def test_forward_reference_refuses(tmp_path: pathlib.Path) -> None:
    doc = tmp_path / "backend/arkali/engineering/factory/STAGED_GENERATION_STAGES.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "### 1. first\nInputs: second\nRule: do the first thing.\n\n"
        "### 2. second\nInputs: none\nRule: do the second thing.\n",
        encoding="utf-8",
    )
    with pytest.raises(StageVocabularyError):
        StageVocabulary.load(tmp_path)


def test_self_referential_input_refuses(tmp_path: pathlib.Path) -> None:
    doc = tmp_path / "backend/arkali/engineering/factory/STAGED_GENERATION_STAGES.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "### 1. first\nInputs: none\nRule: do the first thing.\n\n"
        "### 2. second\nInputs: second\nRule: do the second thing.\n",
        encoding="utf-8",
    )
    with pytest.raises(StageVocabularyError):
        StageVocabulary.load(tmp_path)


def test_duplicate_stage_name_refuses(tmp_path: pathlib.Path) -> None:
    doc = tmp_path / "backend/arkali/engineering/factory/STAGED_GENERATION_STAGES.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        "### 1. first\nInputs: none\nRule: do the first thing.\n\n"
        "### 2. first\nInputs: none\nRule: do it again.\n",
        encoding="utf-8",
    )
    with pytest.raises(StageVocabularyError):
        StageVocabulary.load(tmp_path)


def test_missing_inputs_line_refuses(tmp_path: pathlib.Path) -> None:
    doc = tmp_path / "backend/arkali/engineering/factory/STAGED_GENERATION_STAGES.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("### 1. first\nRule: do the first thing.\n", encoding="utf-8")
    with pytest.raises(StageVocabularyError):
        StageVocabulary.load(tmp_path)


def test_single_stage_document_refuses(tmp_path: pathlib.Path) -> None:
    doc = tmp_path / "backend/arkali/engineering/factory/STAGED_GENERATION_STAGES.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("### 1. only\nInputs: none\nRule: the only stage.\n", encoding="utf-8")
    with pytest.raises(StageVocabularyError):
        StageVocabulary.load(tmp_path)
