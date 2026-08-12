"""Canonical Stable-to-candidate stage boundary (ARK-REQ-0023/0025).

This authority validates progression; it performs no filesystem mutation and
does not decide verification or acceptance. The governed path is parsed from
``AUTHORITY_MAP.yaml`` so release code cannot carry a shadow lifecycle.
"""

from __future__ import annotations

import pathlib
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from arkali.kernel.contracts.error_base import ArkaliError

AUTHORITY_MAP_RELPATH = "docs/canonical/AUTHORITY_MAP.yaml"


class StablePathError(ArkaliError):
    """The canonical stable-candidate path is malformed or was bypassed."""

    code = "ARK-ERR-0098"


class StageReceipt(BaseModel):
    """Immutable proof that one candidate reached one canonical stage."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    candidate_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    traversed: tuple[str, ...]


class StableCandidatePath:
    """Advance a candidate only one authority-declared stage at a time."""

    def __init__(self, stages: tuple[str, ...], source: str) -> None:
        if len(stages) < 2 or len(set(stages)) != len(stages):
            raise StablePathError("stable mutation path must be non-vacuous and unique")
        self._stages = stages
        self.source = source

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> StableCandidatePath:
        path = repo_root / AUTHORITY_MAP_RELPATH
        if not path.is_file():
            raise StablePathError(f"authority map not found: {path}")
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        declared = ((raw or {}).get("stable_mutation") or {}).get("required_path")
        stages = tuple(
            str(stage).strip().lower() for stage in (declared or ()) if str(stage).strip()
        )
        if not stages:
            raise StablePathError("stable_mutation.required_path is absent or empty")
        return cls(stages, str(path))

    def stages(self) -> tuple[str, ...]:
        return self._stages

    def begin_candidate(self, *, candidate_id: str) -> StageReceipt:
        """Move off Stable only into the immediately following candidate stage."""
        return StageReceipt(
            candidate_id=candidate_id,
            stage=self._stages[1],
            traversed=self._stages[:2],
        )

    def advance(self, receipt: StageReceipt, *, to_stage: str) -> StageReceipt:
        """Refuse skipped, reversed, repeated, unknown, or cross-candidate stages."""
        target = to_stage.strip().lower()
        try:
            current_index = self._stages.index(receipt.stage)
            target_index = self._stages.index(target)
        except ValueError as error:
            raise StablePathError("stage is not in the canonical required path") from error
        if receipt.traversed != self._stages[: current_index + 1]:
            raise StablePathError("stage receipt does not prove the complete canonical prefix")
        if target_index != current_index + 1:
            raise StablePathError(
                f"cannot advance from {receipt.stage!r} to {target!r}; "
                "every canonical stage is required"
            )
        return StageReceipt(
            candidate_id=receipt.candidate_id,
            stage=target,
            traversed=(*receipt.traversed, target),
        )

    def promotion_receipt(self, accepted: StageReceipt) -> StageReceipt:
        """Issue a promotion-stage receipt only from its immediate predecessor."""
        return self.advance(accepted, to_stage=self._stages[-1])
