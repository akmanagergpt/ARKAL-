"""The structured change-plan/changeset schema a Managed Product
modification must produce before any file is ever touched (D-030 Ruling 7).

Pure value objects, no persistence and no cross-context import: the model
proposes a `ChangePlan`, `engineering.product_change`'s own orchestration
validates it against real repository facts (workspace containment,
preconditions, collisions) before ever calling `CandidateWorkspace.write`/
`.delete`/`.rename` -- this module owns none of that validation itself,
only the shape.

DOMAIN-GENERAL, BY CONSTRUCTION. Nothing here names a product domain
(student, payment, course, ...). `target_files`/`path`/`content` are
free-form strings the provider supplies and the orchestration layer
validates generically.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CHANGE_PLAN_SCHEMA_VERSION = "1.0.0"

OperationKind = Literal["create", "update", "delete", "rename"]


class ChangeOperation(BaseModel):
    """One file-level operation the plan proposes. `content` is required
    for `create`/`update`, ignored otherwise. `new_path` is required for
    `rename`, ignored otherwise -- enforced by the orchestration layer's
    own changeset validation, not by this schema, so an invalid shape is
    reported with the same real refusal path a missing precondition is."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: OperationKind
    path: str = Field(min_length=1)
    new_path: str | None = None
    content: str | None = None
    expected_content_sha256: str | None = None
    rationale: str = Field(min_length=1)


class ChangePlan(BaseModel):
    """The provider's own real, structured proposal for one modification
    request. Evidence, never lifecycle truth -- registered through
    `evidence.artifact.ArtifactStore` by the orchestration layer, never a
    dedicated `ChangePlanRegistry`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = CHANGE_PLAN_SCHEMA_VERSION
    request_text: str = Field(min_length=1)
    target_summary: str = Field(min_length=1)
    operations: tuple[ChangeOperation, ...] = Field(min_length=1)
