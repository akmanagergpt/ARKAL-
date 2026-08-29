"""C-25 candidate workspace and semantic assembly failures (Phase 12)."""

from __future__ import annotations

from arkali.kernel.contracts.contract_violation_base import ContractViolation


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


class InvalidAssemblyReportError(CandidateContractError):
    """A C-25 report is incomplete, ambiguous, or not manifest-bound."""

    code = "ARK-ERR-0108"


class CandidateIdentityReuseError(CandidateContractError):
    """A `candidate_id` already has ledger history (`ledger.py`), even if
    its workspace directory was deleted; identities are never reused."""

    code = "ARK-ERR-0109"


class CandidateIntegrityError(CandidateContractError):
    """A candidate's live on-disk content no longer matches the manifest
    recorded at its last terminal state (`ledger.py`)."""

    code = "ARK-ERR-0110"


class UnknownLifecycleStateError(CandidateContractError):
    """A state outside `ledger.ALL_STATES` was recorded or requested."""

    code = "ARK-ERR-0111"


class CampaignBudgetExhaustedError(CandidateContractError):
    """A generation campaign (`campaign_budget.py`) has no headroom left on
    at least one declared budget dimension; a new candidate may not start
    without an explicit, human-confirmed override."""

    code = "ARK-ERR-0112"


class CampaignEscalatedError(CandidateContractError):
    """The same failure fingerprint recurred a third time within a
    generation campaign (`campaign_budget.py`); the campaign is escalated
    and refuses every further candidate, override or not."""

    code = "ARK-ERR-0113"


class InvalidLifecycleTransitionError(CandidateContractError):
    """A candidate lifecycle state (`ledger.py`) was recorded that its
    current latest state does not permit -- e.g. entering
    ACCEPTANCE_RUNNING from anything but STAGED_GENERATION_PASS, or
    recording anything at all after a true dead-end state."""

    code = "ARK-ERR-0114"


class CandidateAcceptanceInProgressError(CandidateContractError):
    """A second acceptance attempt was refused because one for this
    `candidate_id` is already starting or in progress (`ledger.py`
    `begin_acceptance`'s file lock)."""

    code = "ARK-ERR-0115"
