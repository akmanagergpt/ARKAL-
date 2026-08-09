"""C-19 job-type contract registry: the `ARK-REQ-0060` applicability data.

Owner: `execution.durable`. Phase 7 Atomic Package 3.

WHY THIS EXISTS AT ALL. `ARK-REQ-0060` is CONDITIONAL and its Appendix A rule is
`job_type.supports_pause == true` "in the job-type contract registry". Governing
rule 7 of `REQUIREMENT_REGISTER.md` resolves an unwaived *unevaluable* rule to
APPLICABLE, so declining to build the registry did not avoid the requirement -
it only left the rule unanswerable. This module makes the rule mechanically
evaluable; it does not make the requirement go away, and no waiver is claimed.

THIS IS THE ONLY PLACE THE QUESTION IS ANSWERED. Pause capability is read from
the persisted row and from nowhere else - not from a request body, not from the
caller's identity, not from a UI affordance, and not inferred from the job's
current lifecycle state. A second answer would be a second applicability
authority, which is exactly what `MS §Constitution 1` forbids.

IT FAILS CLOSED. An unregistered job type raises `UnknownJobType` rather than
returning `False`. The distinction matters: `False` is a declaration that pause
is unsupported, while an absent row is an unanswered question, and a service
that silently converts the second into the first has decided something nobody
declared.

DECLARATION IS WRITE-ONCE. Re-declaring a registered type is refused rather than
overwriting it, so a job admitted while its type supported pause cannot have
that capability changed underneath it by a later registration. Canonical
authority declares no versioning or mutation semantics for this registry, so
none is invented: the smallest behaviour that satisfies the rule is the whole of
it.

WHAT THIS IS NOT. Not a scheduler registry, not a worker registry, not a
provider registry, not a plugin registry and not the Capability Graph. It holds
one durability capability per job type. Worker classes, concurrency limits,
resource profiles and TRUST tiers are the C-21 declaration at **Phase 8** and
appear nowhere here.

TRANSACTION BOUNDARIES BELONG TO THE CALLER, and every operation passes the
injected PEP - the same two operation classes the rest of C-19 uses.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.execution.durable.errors import (
    DuplicateJobType,
    InvalidJobIdentity,
    UnknownJobType,
)
from arkali.execution.durable.job_store import (
    ACTOR,
    READ,
    TRUST_TIER,
    WRITE,
    Clock,
)
from arkali.execution.durable.records import JobTypeRecord, utc_now


class JobTypeRegistry:
    """The declared job types and their durability capabilities, over one session."""

    def __init__(
        self,
        session: Session,
        pep: PolicyEnforcementPoint,
        clock: Clock = utc_now,
    ) -> None:
        self._session = session
        self._pep = pep
        self._clock = clock

    def _guard(self, operation: str) -> None:
        self._pep.require_auto(
            PolicyRequest(
                operation_class=operation, trust_tier=TRUST_TIER, actor=ACTOR
            )
        )

    # -- reads ---------------------------------------------------------------

    def get(self, job_type: str) -> JobTypeRecord | None:
        self._guard(READ)
        return self._session.execute(
            select(JobTypeRecord).where(JobTypeRecord.job_type == job_type)
        ).scalar_one_or_none()

    def require(self, job_type: str) -> JobTypeRecord:
        """The declaration for a job type, or a refusal.

        The fail-closed edge: an absent declaration is an unanswered question
        and is raised as one, never converted into a capability answer.
        """
        found = self.get(job_type)
        if found is None:
            raise UnknownJobType(
                f"job type {job_type!r} is not declared in the job-type "
                "registry, so its durability capabilities are unknown"
            )
        return found

    def supports_pause(self, job_type: str) -> bool:
        """The `ARK-REQ-0060` applicability answer, read from persisted data."""
        return bool(self.require(job_type).supports_pause)

    def declared(self) -> tuple[JobTypeRecord, ...]:
        """Every declared job type, by identity."""
        self._guard(READ)
        rows = self._session.execute(
            select(JobTypeRecord).order_by(JobTypeRecord.job_type)
        ).scalars()
        return tuple(rows)

    # -- writes --------------------------------------------------------------

    def declare(self, job_type: str, *, supports_pause: bool) -> JobTypeRecord:
        """Declare a job type once.

        `supports_pause` is keyword-only and has no default: a registration
        that did not state the answer would be the guess this registry exists
        to remove. A repeat is refused rather than overwritten, so a job in
        flight keeps the capability its type was declared with.
        """
        if not job_type.strip():
            raise InvalidJobIdentity("a job type declaration needs a non-empty type")
        if self.get(job_type) is not None:
            raise DuplicateJobType(
                f"job type {job_type!r} is already declared; a second "
                "declaration would change the capability a job in flight was "
                "admitted under"
            )
        self._guard(WRITE)
        record = JobTypeRecord(
            job_type=job_type,
            supports_pause=supports_pause,
            registered_at=self._clock(),
        )
        self._session.add(record)
        self._session.flush()
        return record
