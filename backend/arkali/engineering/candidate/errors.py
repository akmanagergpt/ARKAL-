"""C-25 candidate workspace and semantic assembly failures (Phase 12)."""

from __future__ import annotations

from arkali.kernel.contracts.error_base import ContractViolation


class CandidateContractError(ContractViolation):
    """Base for failures owned by ``engineering.candidate``."""

    code = "ARK-ERR-0103"


class UnknownProductComponentError(CandidateContractError):
    """A component outside the canonical Product Plane was requested."""

    code = "ARK-ERR-0104"


class UnknownAssemblyCheckError(CandidateContractError):
    """A consistency pair outside canonical Semantic Assembly was requested."""

    code = "ARK-ERR-0105"


class WorkspaceIsolationError(CandidateContractError):
    """A workspace identity or path would cross an isolation boundary."""

    code = "ARK-ERR-0106"


class InvalidCandidateManifestError(CandidateContractError):
    """A C-25 manifest is incomplete, ambiguous, or not canonically addressed."""

    code = "ARK-ERR-0107"
