"""C-21 worker contract (class, limits, tier).

Owner: `execution.scheduler`.

WHAT THIS PACKAGE IS. Phase 8 Package 1 delivers the C-21 *declaration*: what a
worker states about itself, validated against the canonical vocabulary. It is an
INT contract, so there is no table, no migration and no ORM record - a worker
declaration is a value, and the set of them is held in memory by the context
that owns allocation.

WHAT THIS PACKAGE IS NOT. There is no admission decision here. Package 2 owns
`capability != NOT_CONFIGURED AND isolation satisfies tier AND budget available`,
and nothing in this module resolves a capability, composes an isolation backend,
tracks a budget or answers whether work may run. `require` returns what a worker
declared; it decides nothing. A structural control asserts the absence.

TIERS AND ISOLATION PROPERTIES ARE NOT REDECLARED HERE. `control.isolation` owns
the five TRUST tiers and the seven isolation properties, and this module asks it
rather than holding a copy - `execution.scheduler` is rank 3 and `control
.isolation` is rank 1, so the dependency runs strictly downward and needs no
sibling edge. The worker classes and the six declaration dimensions come from
`worker_vocabulary`, which parses them from the canonical document. This module
therefore declares no vocabulary of its own.

WHY THE DECLARED PROPERTIES ARE NOT CHECKED AGAINST THE TIER. A tier already
implies required properties, and a worker separately declares the properties it
requires; the canonical set lists both as distinct dimensions. Asking whether
the two *compose* is the isolation half of admission, which is Package 2. What
is checked here is only that each declared property exists in the canonical set
- the forged-capability check applied to the requiring side.

EVERY GOVERNED READ PASSES A PEP. The canonical vocabulary and the isolation
authority are re-read from their governed documents on every operation, under an
injected PEP with no default, using `READ_FILE` - the class `evidence.audit` and
`execution.durable` already use for governed reads. No new operation class is
invented, and `unmapped_action_resolution: DENY` means none could be. Re-reading
rather than caching is the same call-time-parsing rule the register, the
governance state and the isolation authority all follow.

HEARTBEAT INTERVAL IS A DECLARATION, NOT A MECHANISM. C-21's heartbeat interval
is what a worker states about itself. It is not C-19's persisted execution
heartbeat, its ownership record or its liveness sweep, and nothing here emits,
stores, expires or watches a heartbeat. `execution.durable` remains the sole
authority for that, and this context does not import it.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from typing import Final

from pydantic import BaseModel, ConfigDict

from arkali.control.isolation.isolation_contract import IsolationAuthority
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.execution.scheduler.errors import (
    DuplicateWorkerDeclaration,
    ForgedIsolationRequirement,
    InvalidWorkerDeclaration,
    UndeclaredWorkerClass,
)
from arkali.execution.scheduler.worker_vocabulary import WorkerVocabulary

#: The actor this context presents to the PDP.
ACTOR: Final[str] = "execution.scheduler"
TRUST_TIER: Final[str] = "TRUST-0"

#: Reading the governed worker declarations means reading the canonical
#: documents that define them. No new operation class is invented.
READ: Final[str] = "READ_FILE"

#: THE SINGLE BINDING SITE between canonical prose and code identifiers.
#:
#: The canonical set states the six dimensions as English in
#: `EXECUTION_AND_CAPABILITY.md` §4; Python needs identifiers. Something must
#: bind the two, and deriving identifiers by munging the prose would be worse
#: than stating the binding: `class` is a reserved word, `required TRUST tier`
#: has no mechanical spelling, and a munger silently maps a reworded dimension
#: onto the wrong field.
#:
#: So the binding is explicit, lives in exactly one place, and is reconciled
#: against the parsed canonical list in BOTH directions by a structural control.
#: A dimension added to, removed from or reworded in the canonical document
#: fails that control, and so does a model field that no canonical dimension
#: names. This is the opposite of a shadow model: the copy cannot drift quietly
#: because drift is exactly what is asserted against.
CANONICAL_DIMENSION_FIELDS: Final[dict[str, str]] = {
    "class": "worker_class",
    "concurrency limit": "concurrency_limit",
    "resource profile": "resource_profile",
    "required TRUST tier": "required_trust_tier",
    "required isolation properties": "required_isolation_properties",
    "heartbeat interval": "heartbeat_interval",
}


class WorkerDeclaration(BaseModel):
    """What one worker declares about itself. Exactly the six C-21 dimensions.

    Frozen, and `extra="forbid"`: a worker cannot smuggle a seventh dimension
    past the contract, which is what `ADDITIVE` compatibility means for the
    declaring side - the canonical set adds dimensions, workers do not.

    Shape is validated here; canonical membership is validated by
    `WorkerContract`, which is the side that holds the vocabulary.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    worker_class: str
    concurrency_limit: int
    resource_profile: str
    required_trust_tier: str
    required_isolation_properties: tuple[str, ...] = ()
    heartbeat_interval: dt.timedelta

    def validate_bounds(self) -> None:
        """Refuse a declaration whose values cannot mean anything.

        Bounds only. Whether the class, the tier and the properties are
        canonical is asked by `WorkerContract`, which holds the authorities.
        """
        if self.concurrency_limit < 1:
            raise InvalidWorkerDeclaration(
                f"concurrency limit {self.concurrency_limit} is not a limit; a "
                "worker admitting no work at all is not a worker"
            )
        if not self.resource_profile.strip():
            raise InvalidWorkerDeclaration(
                "resource profile is empty; the canonical set requires a worker "
                "to declare one"
            )
        if self.heartbeat_interval <= dt.timedelta(0):
            raise InvalidWorkerDeclaration(
                f"heartbeat interval {self.heartbeat_interval} is not positive; "
                "an interval that never elapses declares nothing"
            )
        duplicated = sorted(
            {
                name
                for name in self.required_isolation_properties
                if self.required_isolation_properties.count(name) > 1
            }
        )
        if duplicated:
            raise InvalidWorkerDeclaration(
                f"isolation properties repeated in one declaration: {duplicated}"
            )


class WorkerContract:
    """The C-21 declaration authority for `execution.scheduler`.

    One declaration per canonical worker class. Keying by class is what the
    canonical dimensions permit: C-21 states what a worker declares, and
    identity is not one of the six. A fleet of many workers per class is not
    C-21 and is not built here.
    """

    def __init__(self, repo_root: pathlib.Path, pep: PolicyEnforcementPoint) -> None:
        self._root = repo_root
        self._pep = pep
        self._declared: dict[str, WorkerDeclaration] = {}

    def _authorities(self) -> tuple[WorkerVocabulary, IsolationAuthority]:
        """Take a real policy decision, then read the governed documents.

        The decision comes first, so a DENY prevents the read rather than
        annotating it. Nothing is cached between calls: the canonical documents
        are the authority at the moment they are asked.
        """
        self._pep.require_auto(
            PolicyRequest(operation_class=READ, trust_tier=TRUST_TIER, actor=ACTOR)
        )
        return (
            WorkerVocabulary.load(self._root),
            IsolationAuthority.load(self._root),
        )

    def canonical_classes(self) -> tuple[str, ...]:
        """The canonical worker classes, read live under a policy decision."""
        vocabulary, _ = self._authorities()
        return vocabulary.classes()

    def declare(self, declaration: WorkerDeclaration) -> WorkerDeclaration:
        """Validate one declaration against canonical authority and record it."""
        vocabulary, isolation = self._authorities()
        declaration.validate_bounds()
        vocabulary.require_class(declaration.worker_class)
        # An unknown tier raises `control.isolation`'s own TrustTierViolation,
        # unchanged: that context owns the tier vocabulary, not this one.
        isolation.required_properties(declaration.required_trust_tier)
        canonical = set(isolation.properties)
        forged = sorted(set(declaration.required_isolation_properties) - canonical)
        if forged:
            raise ForgedIsolationRequirement(
                f"worker class {declaration.worker_class!r} requires isolation "
                f"properties the canonical set does not define: {forged}",
                source=isolation.source_path,
            )
        if declaration.worker_class in self._declared:
            raise DuplicateWorkerDeclaration(
                f"worker class {declaration.worker_class!r} is already declared; "
                "a second declaration would make the read non-deterministic"
            )
        self._declared[declaration.worker_class] = declaration
        return declaration

    def require(self, worker_class: str) -> WorkerDeclaration:
        """The declaration for one canonical class, or a refusal.

        Fails closed on an undeclared class. Returning a synthesised default
        would grant limits and a tier nobody declared.
        """
        vocabulary, _ = self._authorities()
        vocabulary.require_class(worker_class)
        found = self._declared.get(worker_class)
        if found is None:
            raise UndeclaredWorkerClass(
                f"worker class {worker_class!r} is canonical but nothing has "
                "declared a C-21 contract for it"
            )
        return found

    def declared_classes(self) -> tuple[str, ...]:
        """Which classes this instance holds a declaration for.

        Deliberately ungoverned: it reads this object's own memory and opens no
        canonical document, so guarding it under `READ_FILE` would claim an
        enforcement that performs no governed operation.
        """
        return tuple(sorted(self._declared))
