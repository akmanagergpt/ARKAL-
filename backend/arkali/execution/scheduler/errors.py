"""C-21 worker contract error types.

Owner: `execution.scheduler`.

WHY THESE ARE NOT IN `kernel.contracts.errors`. The same reason the C-12, C-14,
C-15 and C-19 taxonomies are not: `arkali.kernel.contracts.errors` sits at its
fan-in budget, and ADR-0008 makes decomposition the answer to a budget rather
than an exception. The shared base stays in the kernel; the concrete types live
with the context that raises them.

THIS CONTEXT ADDS NO EDGE TO `errors.py`. Its fan-in was at the budget (15)
before Phase 8, so a sixteenth importer would have breached it. The abstract base
layer now lives in `kernel.contracts.error_base` and is imported from there;
`errors.py` re-exports the same names for every earlier caller. One import site
for the whole context, which is the rule `acceptance.engine` already follows.

Each failure mode is a distinct type so a negative control can assert the
*reason* something was refused. A control asserting only that an exception was
raised would pass for an unrelated reason - the F-0017 defect.

NO TIER OR ISOLATION ERRORS HERE. An unknown TRUST tier is refused by
`control.isolation`, which owns the tier vocabulary, and its `TrustTierViolation`
propagates unchanged. Re-raising it as a scheduler error would make this context
look like a second tier authority, which it is not - the same rule
`execution.durable` follows for the canonical `Job` machine's rejections.

Codes are allocated from 0081 upward; 0070-0080 belong to `execution.durable`.
"""

from __future__ import annotations

from arkali.kernel.contracts.error_base import (
    AuthoritativeSourceError,
    ContractViolation,
)


class CanonicalWorkerSourceError(AuthoritativeSourceError):
    """The canonical worker section is absent, unparseable or empty.

    Distinct from every declaration failure below: this says the *authority*
    could not be read, not that a worker declared something wrong. A negative
    control must be able to tell a broken document from a broken declaration.
    """

    code = "ARK-ERR-0086"


class UnknownWorkerClass(ContractViolation):
    """A declaration names a worker class the canonical set does not define.

    Refused rather than admitted as an extension point. The seven classes are
    governed data in `EXECUTION_AND_CAPABILITY.md` §4; a worker that could name
    its own class would be a second vocabulary.
    """

    code = "ARK-ERR-0081"


class InvalidWorkerDeclaration(ContractViolation):
    """A declared C-21 dimension is absent, empty or outside its bounds.

    Covers the concurrency limit, the resource profile and the heartbeat
    interval. A declaration is refused whole: C-21 has six dimensions and a
    partial declaration is not a worker contract.
    """

    code = "ARK-ERR-0082"


class ForgedIsolationRequirement(ContractViolation):
    """A declaration requires an isolation property the canonical set does not
    define.

    The forged-capability check applied to the requiring side. `control
    .isolation` already refuses a *backend* that claims an undefined property;
    a worker that could require an undefined one would make its requirement
    unsatisfiable by construction while looking stricter than the canonical set.
    """

    code = "ARK-ERR-0083"


class DuplicateWorkerDeclaration(ContractViolation):
    """A worker class already has a declaration.

    Declaration is not idempotent by silence. C-21 keys a declaration by its
    canonical class, so a second declaration for the same class would make the
    read non-deterministic - it would answer with whichever arrived last.
    """

    code = "ARK-ERR-0084"


class UndeclaredWorkerClass(ContractViolation):
    """An operation needs a worker class's declaration and none was declared.

    Fails CLOSED rather than returning a default profile. An absent declaration
    is an unanswered question, and answering it with a synthesised default would
    grant limits and a tier that nobody declared.
    """

    code = "ARK-ERR-0085"
