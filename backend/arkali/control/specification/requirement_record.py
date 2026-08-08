"""C-04 requirement record model.

Owner: control.specification. The register is the SOLE coverage denominator
(MASTER_SPECIFICATION, Canonical Requirement Register). This module defines the
record shape only; the register file itself remains authoritative.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict


class Classification(str, enum.Enum):
    MANDATORY = "MANDATORY"
    CONDITIONAL = "CONDITIONAL"
    OPTIONAL = "OPTIONAL"


class RequirementRecord(BaseModel):
    """One ARK-REQ entry. Identifiers are immutable and never reused."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    req_id: str
    statement: str
    source: str
    classification: Classification
    owning_phase: str
    owning_component: str
    required_evidence: tuple[str, ...]

    @property
    def is_mandatory(self) -> bool:
        return self.classification is Classification.MANDATORY

    @property
    def counts_toward_coverage(self) -> bool:
        """OPTIONAL entries never contribute to mandatory coverage."""
        return self.classification in (
            Classification.MANDATORY,
            Classification.CONDITIONAL,
        )
