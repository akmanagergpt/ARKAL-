"""Admission condition (c): resource budget must be available.

Owner: `execution.scheduler`.

WHAT §4 REQUIRES, AND NOTHING MORE. "Resource budget is available." The canonical
set gives Phase 8 no worker pool, no capacity ledger, no reservation service, no
machine discovery and no autoscaling, so none is built. What exists here is a
pure function of two values: the C-21 declaration, and an availability snapshot
the caller supplies.

AVAILABILITY IS AN INPUT, NOT A UNIVERSE THIS CONTEXT OWNS. `ResourceAvailability`
is a frozen value passed in per evaluation. There is no long-lived mutable
resource state, no module-level pool and no persistence, so two evaluations
cannot interfere and nothing here can drift from reality between calls. Who
counts the in-flight work is the caller's business; deciding whether the number
fits the declared limit is this module's.

EVALUATING DOES NOT CONSUME. §4 describes a *test* for admission. Nothing here
reserves, decrements, claims or records anything: `evaluate` is referentially
transparent, and calling it twice with the same inputs returns the same answer
and leaves the snapshot unchanged. Turning the test into an allocation would make
admission-checking itself a scheduling side effect, which is not Phase 8 work and
would be unfixable at Package 3.

FAIL CLOSED ON AN IMPOSSIBLE SNAPSHOT. A negative in-flight count is not a
generous zero: it is an input that cannot be true, and answering it would be
guessing at what the caller meant.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from arkali.execution.scheduler.errors import InvalidResourceAvailability


class ResourceAvailability(BaseModel):
    """What the caller reports is free, at one instant. Immutable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: How many workers of the declared class are already occupied.
    in_flight: int
    #: The resource profiles the caller reports it can currently supply. C-21
    #: has no canonical profile vocabulary, so membership is the only question
    #: that can honestly be asked of a profile name.
    available_profiles: tuple[str, ...] = ()

    def validate_bounds(self) -> None:
        if self.in_flight < 0:
            raise InvalidResourceAvailability(
                f"in-flight count {self.in_flight} is negative; an impossible "
                "snapshot is refused rather than read as spare capacity"
            )


class ResourceAssessment(BaseModel):
    """Whether the declared budget fits the reported availability."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    satisfied: bool
    reason: str


class ResourceAdmission:
    """The pure §4 budget test. Holds no state at all."""

    def evaluate(
        self,
        concurrency_limit: int,
        resource_profile: str,
        availability: ResourceAvailability,
    ) -> ResourceAssessment:
        """Deterministic, side-effect free, and consumes nothing."""
        availability.validate_bounds()
        if availability.in_flight >= concurrency_limit:
            return ResourceAssessment(
                satisfied=False,
                reason=(
                    f"concurrency limit {concurrency_limit} is reached: "
                    f"{availability.in_flight} already in flight"
                ),
            )
        if resource_profile not in availability.available_profiles:
            return ResourceAssessment(
                satisfied=False,
                reason=(
                    f"resource profile {resource_profile!r} is not among the "
                    f"available profiles {list(availability.available_profiles)}"
                ),
            )
        return ResourceAssessment(
            satisfied=True,
            reason=(
                f"{availability.in_flight} of {concurrency_limit} in flight and "
                f"profile {resource_profile!r} is available"
            ),
        )
