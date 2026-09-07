"""Bounded local/provider model output -> isolated multi-file candidate.

Owner: ``engineering.factory``. The model adapter and candidate workspace are
structural ports: their existing authorities execute inference and confine
filesystem writes. This module owns only the product-generation composition
and strict response validation required before any model bytes become files.
"""

from __future__ import annotations

import ast
import json
import pathlib
import platform
import sys
from collections.abc import Callable, Mapping
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
MANIFEST_NORMALIZATION_VERSION = "1.0.0"


def _require_runnable_manifests(paths: tuple[str, ...]) -> None:
    missing = REQUIRED_EXACT - set(paths)
    if missing:
        raise ValueError(f"generated product misses runnable manifests: {sorted(missing)}")
    backend_manifests = {"backend/requirements.txt", "backend/pyproject.toml"}
    if not backend_manifests.intersection(paths):
        raise ValueError("generated backend needs a dependency manifest")


def _normalise_requirements(files: dict[str, str]) -> dict[str, str]:
    """Undo a literal escaped-newline transport defect (the same real class
    `_normalise_python_transport` already fixes for `.py` files, F-0080;
    real evidence: `factory-goal-mtqt1uk9-qfs6bw` -- a real `requirements.
    txt` with three real declared packages collapsed onto ONE line by
    literal `\\n` sequences, so pip could never parse `flask_cors`/
    `pytest` as separate requirements at all, reported downstream as
    `undeclared_test_dependency`/`missing_local_module` even though both
    were genuinely declared, just unparseable) before removing only
    impossible stdlib package declarations; code is untouched. A real
    `requirements.txt` line never legitimately contains a literal
    backslash-escape sequence (unlike Python source, which can hold one
    inside a real string literal), so unescaping here needs none of
    `_normalise_python_transport`'s own parse-before/parse-after safety
    dance -- it is unconditionally safe."""
    path = "backend/requirements.txt"
    if path not in files:
        return files
    content = files[path]
    if "\\n" in content:
        content = content.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    retained: list[str] = []
    for line in content.splitlines():
        declared = line.split("#", 1)[0].strip()
        name = declared.split("[", 1)[0]
        for marker in ("==", ">=", "<=", "~=", "!=", ">", "<"):
            name = name.split(marker, 1)[0]
        if name.strip().replace("-", "_").lower() in sys.stdlib_module_names:
            continue
        retained.append(line)
    normalized = dict(files)
    normalized[path] = "\n".join(retained).rstrip() + "\n"
    return normalized


def _normalise_escaped_transport(
    files: dict[str, str], *, suffix: str,
    parse: Callable[[str], object], parse_error: type[Exception],
) -> dict[str, str]:
    """A real provider can double-escape an embedded newline as a literal
    `\\n` in its own raw JSON reply (F-0080, real evidence: a `.py` file
    collapsed onto one logical line this way, failing `ast.parse`).
    UNCONDITIONALLY SAFE for any file type with a real, mechanical parser:
    already-valid content is never touched (`parse(content)` succeeding
    is the only way this returns without change), and a repair candidate
    is only ever kept when it genuinely parses where the original did
    not -- a legitimate literal `\\n` inside an already-valid file (a
    real newline correctly escaped within a string literal) can never be
    corrupted, since that file already parses on the first attempt.
    Shared by `_normalise_python_transport` (`.py`/`ast.parse`) and
    `_normalise_json_transport` (`.json`/`json.loads`, F-0090) rather than
    duplicating the same parse-before/parse-after dance twice."""
    normalized = dict(files)
    for path, content in files.items():
        if not path.endswith(suffix) or "\\n" not in content:
            continue
        try:
            parse(content)
            continue
        except parse_error:
            candidate = content.replace("\\r\\n", "\n").replace("\\n", "\n")
            candidate = candidate.replace("\\t", "\t")
        try:
            parse(candidate)
        except parse_error:
            continue
        normalized[path] = candidate
    return normalized


def _normalise_python_transport(files: dict[str, str]) -> dict[str, str]:
    return _normalise_escaped_transport(files, suffix=".py", parse=ast.parse, parse_error=SyntaxError)


def _normalise_json_transport(files: dict[str, str]) -> dict[str, str]:
    """F-0090, real evidence `factory-goal-mtqz9w2b-cuqqqe`: the identical
    real transport-corruption class F-0080 already fixed for `.py` files
    and F-0087 already fixed for `backend/requirements.txt`, never yet
    extended to JSON artifacts -- a real, otherwise-correct
    `frontend/package.json` was written with every one of its own real
    newlines as a literal `\\n` escape sequence, so `npm install` failed
    outright with `npm error code EJSONPARSE`. Every `.json` file this
    pipeline ever writes gets the same treatment, not only
    `frontend/package.json` specifically -- `backend/routes.json`,
    `backend/data_model.json` and `product/ux_spec.json` are exactly as
    exposed to the same real provider transport defect, and a fix scoped
    to one candidate-specific filename would be exactly the kind of
    domain leakage this pipeline's own architecture forbids. Unlike
    `.py` source, JSON has no legitimate reason to contain a literal
    backslash-n OUTSIDE a string value, but a string value MAY
    legitimately contain one (e.g. a real multi-line description) --
    which is exactly why this reuses the parse-before/parse-after
    primitive rather than `_normalise_requirements`'s unconditional
    replace: a JSON file whose only "escape" is a real, valid one inside
    an already-parseable string already parses on the first attempt and
    is therefore never touched."""
    return _normalise_escaped_transport(
        files, suffix=".json", parse=json.loads, parse_error=json.JSONDecodeError,
    )


def _normalise_frontend_entry(files: dict[str, str]) -> dict[str, str]:
    package = files.get("frontend/package.json", "")
    entry = "frontend/public/index.html"
    if "react-scripts" not in package or entry in files:
        return files
    normalized = dict(files)
    normalized[entry] = (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Generated Product</title></head><body>"
        '<noscript>JavaScript is required.</noscript><div id="root"></div>'
        "</body></html>\n"
    )
    return normalized


def _require_executable_product(files: tuple[GeneratedFile, ...]) -> None:
    persistence_markers = ("sqlite3", "sqlalchemy", "sqlite://")
    has_persistence = any(
        item.path.endswith(".py")
        and item.path.startswith("backend/")
        and any(marker in item.content.lower() for marker in persistence_markers)
        for item in files
    )
    if not has_persistence:
        raise ValueError("generated backend needs executable persistence code")
    source_suffixes = {".js", ".jsx", ".ts", ".tsx"}
    has_frontend = any(
        item.path.startswith("frontend/src/")
        and pathlib.PurePosixPath(item.path).suffix in source_suffixes
        for item in files
    )
    if not has_frontend:
        raise ValueError("generated frontend needs executable source")


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
        _require_executable_product(self.files)
        if sum(len(item.content.encode("utf-8")) for item in self.files) > MAX_TOTAL_BYTES:
            raise ValueError("generated product exceeds the aggregate byte bound")
        return self


class ModelProductResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    blueprint_id: str
    runtime: str
    model_id: str
    files: tuple[str, ...]
    attempts_used: int = Field(ge=1)


def _prompt(blueprint: RequirementBlueprint, prior_failure: str | None = None) -> str:
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
                    "never list Python standard-library modules as installable dependencies",
                    "declare compatible transitive dependency bounds for pinned frameworks",
                    "frontend/package.json with runnable build and start scripts",
                    "frontend/public/index.html when the selected frontend toolchain requires it",
                    "tests must import modules and symbols that the generated backend exposes",
                    "tests must define every non-builtin fixture they consume",
                    "tests must enter application lifecycle contexts required by startup hooks",
                    "test-only third-party imports must be declared in a dependency manifest",
                    "SQLite selection requires executable schema bootstrap or migrations",
                    "framework-bound schema bootstrap must run inside its required app context",
                    "do not use APIs removed by the selected framework version",
                    "backend manifests must expose an executable server entrypoint",
                    "frontend must exercise every generated mutation workflow exposed by the backend",
                    "separate frontend and backend origins require an explicit narrow CORS policy",
                ],
            },
            "blueprint_id": blueprint.blueprint_id,
            "target_runtime": {"python": platform.python_version()},
            "goal": blueprint.goal.goal_text,
            "derived_requirements": requirements,
            "prior_attempt_failure": prior_failure,
            "convergence_rule": (
                "When prior_attempt_failure is present, correct that exact structural "
                "defect while retaining every other output requirement."
            ),
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
        raise ModelGenerationError(
            f"model response violates the multi-file contract: {error}"
        ) from error
    file_map = _normalise_frontend_entry(
        _normalise_json_transport(
            _normalise_python_transport(
                _normalise_requirements({item.path: item.content for item in envelope.files})
            )
        )
    )
    try:
        inspect_product_files(file_map, baseline=baseline).require_pass()
    except ProductSemanticPreflightError as error:
        raise ModelGenerationError(f"model response fails semantic preflight: {error}") from error
    for path, content in file_map.items():
        workspace.write(path, content.encode("utf-8"))
    return tuple(file_map)


def generate_model_product(
    blueprint: RequirementBlueprint,
    model: ModelSource,
    model_id: str,
    workspace: WorkspaceTarget,
    *,
    timeout_seconds: float = 300.0,
) -> ModelProductResult:
    return generate_model_product_bounded(
        blueprint,
        model,
        model_id,
        workspace,
        timeout_seconds=timeout_seconds,
        max_attempts=1,
    )


def generate_model_product_bounded(
    blueprint: RequirementBlueprint,
    model: ModelSource,
    model_id: str,
    workspace: WorkspaceTarget,
    *,
    timeout_seconds: float = 300.0,
    max_attempts: int = 2,
) -> ModelProductResult:
    if not blueprint.is_fully_resolved:
        raise ModelGenerationError("model generation refuses an unresolved blueprint")
    if max_attempts < 1 or max_attempts > 4:
        raise ModelGenerationError("generation attempt budget must be between 1 and 4")
    failure: str | None = None
    for attempt in range(1, max_attempts + 1):
        outcome = model.infer(
            model_id, _prompt(blueprint, failure), timeout_seconds=timeout_seconds
        )
        if outcome.state is not HonestState.PASS or not outcome.output.strip():
            failure = f"real model inference did not pass: {outcome.state.value}: {outcome.detail}"
            continue
        try:
            files = write_model_product_output(outcome.output, workspace)
        except ModelGenerationError as error:
            failure = str(error)
            continue
        return ModelProductResult(
            blueprint_id=blueprint.blueprint_id,
            runtime=outcome.runtime,
            model_id=outcome.model_id,
            files=files,
            attempts_used=attempt,
        )
    raise ModelGenerationError(
        f"generation budget exhausted after {max_attempts} attempts: {failure}"
    )


__all__ = [
    "ModelProductResult",
    "generate_model_product",
    "generate_model_product_bounded",
    "write_model_product_output",
]
