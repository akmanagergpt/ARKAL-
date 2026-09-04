"""Promote one Managed Product change proposal, for Product Detail's
"Kabul Et" (D-030 V1).

Owner: `surfaces.command`.

REJECT NEEDS NO BRIDGE OF ITS OWN. "Vazgeç" leaves the SAME `cancel_
requested` checkpoint `POST /jobs/{job_id}/cancel` already does — the
`managed_product.change` worker's own poll loop (`scripts/run_product_
change_worker.py`) watches for it exactly as the preview worker already
watches for a real "Durdur", stops the live review preview, discards the
proposal's workspace, and transitions the job to CANCELLED. Reject is
therefore just that same generic route, exposed under a domain-specific
path for a clean audit trail — no new mechanism, no code in this module.

WHY `engineering.product_change` IS NEVER IMPORTED HERE. A direct import
was tried and measured real: orchestration depth 5 of a 4 ceiling
(`surfaces.command -> engineering.product_change -> evidence.artifact ->
control.policy -> kernel.contracts`), `kernel.contracts.contract_
violation_base` fan-in pushed to 16 of 15, and a module touching 4
contexts against a 3-context-per-module ceiling. `_ChangePromoter` is a
structural `Protocol` instead -- the same "composition root supplies the
real verb, this context only holds its shape" discipline `_PreviewBridgeWiring`
already established, one level further: there, only DATA collaborators
(`ArtifactBlobStore`, a ledger) crossed the boundary; here, the WHOLE
promote VERB does, as an injected callable, because reconstructing
`PreparedModification` needs `engineering.product_change`'s own real
types (`ChangePlan`, `VerificationResult`) that this module may not
import either.

WHY THE ROUTE CALLS IT IN-REQUEST, NOT THROUGH A DURABLE JOB. Promotion
is fast: an archive of already-materialized bytes, one content-addressed
`ArtifactStore.register`, one `ProjectRegistry` row — no provider call,
no install/build. `ARK-REQ-0027` ("no long AI work in HTTP requests") is
about exactly the slow work already confined to the durable job.

WHAT CROSSES THE BOUNDARY. The route reads the job's own real, durable
`ready_for_review` checkpoint through `JobStore` (already legal --
`execution.durable` is an ordinary, already-used collaborator of this
context) and hands the whole payload, unread and untransformed, to the
injected `_ChangePromoter`. Nothing here parses or trusts any field of
it beyond passing it through; `engineering.product_change`'s own
promotion logic (composed by the script) does every real check.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable

from arkali.kernel.contracts.error_root import ArkaliError


class _NoReadyChangeError(ArkaliError):
    """No job checkpoint named `ready_for_review` exists for this job --
    either it never got that far, or it already reached a terminal state
    this route was never meant to act on again."""

    code = "ARK-ERR-0170"


class _ChangeVerificationFailedError(ArkaliError):
    """The injected promoter reports the proposal's own real verification
    did not pass -- translated from `engineering.product_change.errors.
    VerificationFailedError`, which this context may not import; see the
    module docstring."""

    code = "ARK-ERR-0171"


class _ChangeStaleBaseError(ArkaliError):
    """The injected promoter reports the project's real current revision
    moved on since this proposal was prepared -- translated from
    `engineering.product_change.errors.StaleBaseRevisionError`."""

    code = "ARK-ERR-0172"


class _ChangeNotAuthorizedError(ArkaliError):
    """The injected promoter reports no matching `HUMAN_GATE_3` grant --
    translated from `engineering.product_change.errors.
    PromotionNotAuthorizedError`."""

    code = "ARK-ERR-0173"


@runtime_checkable
class _CheckpointSource(Protocol):
    """Structural shape of the one real `JobStore` read this module needs."""

    def checkpoints(self, job_id: str) -> tuple[object, ...]: ...


@runtime_checkable
class _ChangePromoter(Protocol):
    """The real promote verb, composed entirely by the script (`run_
    command_center.py`) -- see the module docstring for why this is a
    `Protocol`, never a direct `engineering.product_change` import.
    `ready` is the `ready_for_review` checkpoint's own payload, passed
    through unread."""

    def promote(self, project_id: str, ready: Mapping[str, object]) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class _ProductChangeWiring:
    """Everything the composition root must supply. `promoter.promote` is
    a fully self-contained closure (own session management, exactly as
    the durable-job worker's own `_checkpoint`/`_finish` are) -- no
    session dependency needed here, unlike `_PreviewBridgeWiring`'s
    `artifact_session_scope`."""

    promoter: _ChangePromoter


def _latest_ready_checkpoint(store: _CheckpointSource, job_id: str) -> Mapping[str, object]:
    for row in reversed(store.checkpoints(job_id)):
        if row.payload.get("phase") == "ready_for_review":  # type: ignore[attr-defined]
            return row.payload  # type: ignore[attr-defined]
    raise _NoReadyChangeError(f"job {job_id!r} has no ready_for_review checkpoint")


def _promote_ready_change(
    project_id: str, job_id: str, *, store: _CheckpointSource, wiring: _ProductChangeWiring,
) -> Mapping[str, object]:
    """Resolve the job's own real `ready_for_review` checkpoint and hand it
    to the injected promoter unchanged. Returns whatever plain, JSON-safe
    result the promoter itself returns (the new revision's identity)."""
    ready = _latest_ready_checkpoint(store, job_id)
    return wiring.promoter.promote(project_id, ready)
