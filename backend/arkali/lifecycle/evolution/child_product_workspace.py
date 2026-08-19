"""C-36 child-product working-copy isolation, reused from Phase 12's
`engineering.candidate` unmodified (ARK-REQ-0132, ARK-REQ-0358).

Owner: `lifecycle.evolution`.

STRUCTURAL, NOT IMPORTED, COMPOSITION WITH THE WORKSPACE. `engineering.
candidate`'s own chain into `kernel.contracts` was already measured at
`max_orchestration_depth` 4 of 4 as of Phase 16 (`product_generation.py`'s
own `WorkspaceTarget`) and Phase 19 (`project_import/pipeline.py`'s own
`_WorkspaceTarget`/`_WorkspaceHandle`) - a static `lifecycle.evolution ->
engineering.candidate` import would extend that same chain to 5.
`_WorkspaceAllocator`/`_WorkspaceHandle` below are structural `Protocol`s
matching `WorkspaceAuthority.allocate`/`CandidateWorkspace`'s exact shape,
the identical pattern both of those phases already used for the identical
problem - so a real `WorkspaceAuthority` instance satisfies this module
without adding the edge the measured graph would see. Decomposition per
ADR-0008, not an exemption.

ISOLATION PER PRODUCT AND PER CAMPAIGN, NOT PER CALL. `_child_workspace_id`
derives a deterministic identifier from the exact `(product, campaign)`
pair, mirroring `child_product_campaign._child_campaign_id`'s own
traceability discipline - two campaigns for the same product, or the same
campaign requested twice, resolve to the same workspace identity rather
than silently allocating two disjoint ones `WorkspaceAuthority.allocate`
would then refuse as already-allocated.

WHAT "NEVER COPY ARKALI'S OWN CORE" MEANS HERE, AND WHAT IT DOES NOT.
`ARK-REQ-0358` forbids a generated child's own runtime from containing a
copy of ARKALI's core. This module never reaches ARKALI's own repository
root, source tree, or any path outside its caller-supplied
`stable_snapshot` argument - proven structurally
(`test_child_product_workspace.py`'s `TestNeverReachesArkaliOwnSource`):
no repository-root constant, no `__file__`-relative upward path, no
import of anything under `backend/arkali` beyond this context's own
Protocol-only reach. What this module cannot prove by itself is that some
*future* caller never passes ARKALI's own source tree as `stable_snapshot`
- that is an obligation of whichever package builds the real generation
entrypoint (out of this package's scope; tracked, not silently assumed).
"""

from __future__ import annotations

import pathlib
from typing import Protocol

from arkali.lifecycle.evolution.child_product_identity import ChildProductIdentity
from arkali.lifecycle.evolution.content_identity import address_of


class _WorkspaceHandle(Protocol):
    """Structural shape of an allocated workspace - matches
    `engineering.candidate.workspace.CandidateWorkspace`, unimported."""

    root: pathlib.Path
    snapshot: pathlib.Path


class _WorkspaceAllocator(Protocol):
    """Structural shape of
    `engineering.candidate.workspace.WorkspaceAuthority`, unimported. See
    the module docstring for why."""

    def allocate(
        self,
        *,
        workspace_id: str,
        task_id: str,
        agent_id: str,
        stable_snapshot: pathlib.Path,
    ) -> _WorkspaceHandle: ...


def _child_workspace_id(identity: ChildProductIdentity, *, campaign_id: str) -> str:
    """The deterministic workspace identifier for one product's one
    campaign - content-addressed over both, never a caller-chosen free
    string, so the same (product, campaign) pair always resolves to the
    same workspace identity."""
    payload = f"{identity.product_ref}:{campaign_id}".encode()
    return address_of(payload).replace("sha256:", "child-ws-")


def allocate_child_product_workspace(
    allocator: _WorkspaceAllocator,
    identity: ChildProductIdentity,
    *,
    campaign_id: str,
    stable_snapshot: pathlib.Path,
) -> _WorkspaceHandle:
    """ARK-REQ-0132: allocate one isolated working copy for a child
    product's campaign, through the real, unmodified Phase 12 authority -
    never a second workspace mechanism."""
    return allocator.allocate(
        workspace_id=_child_workspace_id(identity, campaign_id=campaign_id),
        task_id=identity.product_id,
        agent_id="lifecycle.evolution",
        stable_snapshot=stable_snapshot,
    )
