"""Bounded local/provider model output -> isolated multi-file candidate.

Owner: ``engineering.factory``. The model adapter and candidate workspace are
structural ports: their existing authorities execute inference and confine
filesystem writes. This module owns only the product-generation composition
and strict response validation required before any model bytes become files.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from arkali.control.specification.blueprint_contracts import RequirementBlueprint
from arkali.engineering.factory.errors import ModelGenerationError, ProductSemanticPreflightError
from arkali.engineering.factory.product_preflight import inspect_product_files
from arkali.kernel.contracts.honest_state import HonestState

MAX_FILES = 64
MAX_FILE_BYTES = 262_144
MAX_TOTAL_BYTES = 2_000_000
REQUIRED_ROOTS = frozenset({"backend", "frontend", "tests", "config"})
REQUIRED_EXACT = frozenset({"frontend/package.json", "config/README.md"})


def _require_runnable_manifests(paths: tuple[str, ...]) -> None:
    missing = REQUIRED_EXACT - set(paths)
    if missing:
        raise ValueError(f"generated product misses runnable manifests: {sorted(missing)}")
    backend_manifests = {"backend/requirements.txt", "backend/pyproject.toml"}
    if not backend_manifests.intersection(paths):
        raise ValueError("generated backend needs a dependency manifest")


class InferenceOutcome(Protocol):
    runtime: str
    model_id: str
    state: HonestState
    detail: str
    output: str


class ModelSource(Protocol):
    def infer(
        self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0
    ) -> InferenceOutcome: ...


class WorkspaceTarget(Protocol):
    def write(self, relative: str, payload: bytes) -> pathlib.Path: ...


class GeneratedFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=MAX_FILE_BYTES)

    @model_validator(mode="after")
    def _safe_relative_text_file(self) -> GeneratedFile:
        candidate = pathlib.PurePosixPath(self.path)
        if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
            raise ValueError("generated paths must be relative and confined")
        if "\\" in self.path or candidate.as_posix() != self.path:
            raise ValueError("generated paths must use canonical POSIX separators")
        if "\x00" in self.content:
            raise ValueError("generated files must be text")
        if len(self.content.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError("generated file exceeds the byte bound")
        return self


class ModelProductEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    files: tuple[GeneratedFile, ...] = Field(min_length=1, max_length=MAX_FILES)

    @field_validator("files", mode="before")
    @classmethod
    def _normalise_path_map(cls, value: object) -> object:
        """Accept the other lossless JSON spelling of the same file set.

        A mapping grants no extra path/content semantics: every entry is still
        passed through ``GeneratedFile`` and the identical aggregate checks.
        """
        if isinstance(value, dict):
            return [{"path": path, "content": content} for path, content in value.items()]
        return value

    @model_validator(mode="after")
    def _complete_and_bounded(self) -> ModelProductEnvelope:
        paths = tuple(item.path for item in self.files)
        if len(set(paths)) != len(paths):
            raise ValueError("generated paths must be unique")
        roots = {pathlib.PurePosixPath(path).parts[0] for path in paths}
        missing = REQUIRED_ROOTS - roots
        if missing:
            raise ValueError(f"generated product misses required roots: {sorted(missing)}")
        _require_runnable_manifests(paths)
        persistence_markers = ("sqlite3", "sqlalchemy", "sqlite://", "database")
        if not any(
            "database" in item.path.lower()
            or "migration" in item.path.lower()
            or any(marker in item.content.lower() for marker in persistence_markers)
            for item in self.files
        ):
            raise ValueError("generated product needs a persistence/database artifact")
        if sum(len(item.content.encode("utf-8")) for item in self.files) > MAX_TOTAL_BYTES:
            raise ValueError("generated product exceeds the aggregate byte bound")
        return self


class ModelProductResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    blueprint_id: str
    runtime: str
    model_id: str
    files: tuple[str, ...]


def _prompt(blueprint: RequirementBlueprint) -> str:
    requirements = [item.model_dump(mode="json") for item in blueprint.requirements]
    return json.dumps(
        {
            "role": "You are the implementation worker in a bounded software factory.",
            "task": (
                "Generate a runnable professional multi-file application from the requirements."
            ),
            "output_contract": {
                "format": "one JSON object only; no markdown or commentary",
                "schema": {"files": [{"path": "relative/posix/path", "content": "complete text"}]},
                "required_roots": sorted(REQUIRED_ROOTS),
                "completeness_rule": (
                    "The response is invalid unless it includes at least one complete file "
                    "under every required root: backend/, frontend/, tests/, and config/. "
                    "The config root must include config/README.md with exact startup steps."
                ),
                "json_encoding_rule": (
                    "Every file content is a JSON string. Escape newlines as \\n and all "
                    "other control characters according to RFC 8259; never emit literal control "
                    "characters inside a string."
                ),
                "requirements": [
                    "real backend API",
                    "real frontend",
                    "persistent SQLite database",
                    "automated tests",
                    "configuration and documented startup path",
                    "loading, empty and error states; no fake data or embedded secrets",
                    "backend/requirements.txt or backend/pyproject.toml",
                    "frontend/package.json with runnable build and start scripts",
                    "tests must import modules and symbols that the generated backend exposes",
                    "SQLite selection requires executable schema bootstrap or migrations",
                ],
            },
            "blueprint_id": blueprint.blueprint_id,
            "goal": blueprint.goal.goal_text,
            "derived_requirements": requirements,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _json_payload(output: str) -> str:
    stripped = output.strip()
    try:
        parsed = json.loads(stripped)
    except (ValueError, json.JSONDecodeError):
        parsed = None
    if isinstance(parsed, dict):
        return stripped
    if stripped.startswith("```json\n") and stripped.endswith("\n```"):
        body = stripped[len("```json\n") : -len("\n```")]
        if "```" in body:
            raise ModelGenerationError("model response contains multiple fenced blocks")
        return body
    if "```" in stripped:
        raise ModelGenerationError("model response contains an incomplete or annotated fence")
    return stripped


def write_model_product_output(
    output: str,
    workspace: WorkspaceTarget,
    *,
    baseline: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Validate and write model bytes; shared by generation and repair roots."""
    try:
        envelope = ModelProductEnvelope.model_validate_json(_json_payload(output))
    except (ValueError, json.JSONDecodeError) as error:
        raise ModelGenerationError("model response violates the multi-file contract") from error
    file_map = {item.path: item.content for item in envelope.files}
    try:
        inspect_product_files(file_map, baseline=baseline).require_pass()
    except ProductSemanticPreflightError as error:
        raise ModelGenerationError("model response fails semantic preflight") from error
    for item in envelope.files:
        workspace.write(item.path, item.content.encode("utf-8"))
    return tuple(item.path for item in envelope.files)


def generate_model_product(
    blueprint: RequirementBlueprint,
    model: ModelSource,
    model_id: str,
    workspace: WorkspaceTarget,
    *,
    timeout_seconds: float = 300.0,
) -> ModelProductResult:
    if not blueprint.is_fully_resolved:
        raise ModelGenerationError("model generation refuses an unresolved blueprint")
    outcome = model.infer(model_id, _prompt(blueprint), timeout_seconds=timeout_seconds)
    if outcome.state is not HonestState.PASS or not outcome.output.strip():
        raise ModelGenerationError(
            f"real model inference did not pass: {outcome.state.value}: {outcome.detail}"
        )
    files = write_model_product_output(outcome.output, workspace)
    return ModelProductResult(
        blueprint_id=blueprint.blueprint_id,
        runtime=outcome.runtime,
        model_id=outcome.model_id,
        files=files,
    )


__all__ = ["ModelProductResult", "generate_model_product", "write_model_product_output"]
