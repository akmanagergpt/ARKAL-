"""Content-address primitive: bytes to a canonical digest string.

Owner: `kernel.contracts` — `ARCHITECTURE.md` section 3 row 3, "shared schema
primitives, error taxonomy".

WHY THE MECHANISM LIVES IN THE KERNEL AND THE AUTHORITY DOES NOT. Two contexts
need to hash bytes: `evidence.artifact`, which owns
`artifact_identity_and_provenance`, and `evidence.audit`, which owns
`audit_chain_and_evidence_integrity`. Both sit in the `evidence` layer and
`allow_same_layer: false`, so neither may import the other. Only rank 0 is
reachable from every authority.

This is exactly the Phase 3 shape, recorded in `DECISION_LOG.md`: the twelve
state machines are owned by ten contexts, so the *machine* primitive is a kernel
contract while every *machine* stays owned by the context the authority map
names. The same applies here — this module is a hashing mechanism and decides
nothing about identity. `evidence.artifact` remains the sole authority for what
an artifact's identity is and how it is registered; `evidence.audit` remains the
sole authority for the evidence chain. Neither concern moves.

TOTAL, NOT RAISING. Every function returns a value; none raises. That is
deliberate twice over. A primitive that refuses has begun deciding, and the
decision of what a malformed identity *means* belongs to the context that owns
the identity - `evidence.artifact` turns `split() is None` into
`InvalidArtifactIdentity`. It also means this module imports nothing, so it adds
no edge to `kernel.contracts.errors`, whose fan-in budget is 15 and which
ADR-0008 says to answer by decomposing rather than excepting.

ONE HASHING SITE. `hashlib` is used here and nowhere else in the repository, and
controls in both evidence contexts assert that.
"""

from __future__ import annotations

import hashlib
import re
from typing import Final

#: The algorithm the build ships. Carried explicitly in every address, so a
#: future algorithm is a new prefix rather than a silent reinterpretation of
#: existing values.
ALGORITHM: Final[str] = "sha256"

#: `<algorithm>:<lowercase hex digest>`. Anchored, lowercase-only and
#: length-exact, so a truncated or upper-cased digest is not a second spelling
#: of the same content.
ADDRESS_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"^(?P<algorithm>{ALGORITHM}):(?P<digest>[0-9a-f]{{64}})$"
)

#: Length of a canonical address: `sha256:` plus 64 hex characters.
ADDRESS_LENGTH: Final[int] = len(ALGORITHM) + 1 + 64


def digest_of(payload: bytes) -> str:
    """The lowercase hex digest of `payload`."""
    return hashlib.sha256(payload).hexdigest()


def address_of(payload: bytes) -> str:
    """The canonical content address of `payload`.

    Deterministic and total: the digest is taken over the raw bytes only, so
    identical bytes yield an identical address in any process on any host, and
    the empty byte string has an address like any other.
    """
    return f"{ALGORITHM}:{digest_of(payload)}"


def split(address: str) -> tuple[str, str] | None:
    """`(algorithm, digest)` for a canonical address, or None if malformed.

    Returns rather than raises: what a malformed identity means is the owning
    context's decision, not this primitive's.
    """
    match = ADDRESS_PATTERN.match(address)
    if match is None:
        return None
    return match.group("algorithm"), match.group("digest")


def is_address(candidate: str) -> bool:
    """Whether `candidate` is a canonical content address."""
    return ADDRESS_PATTERN.match(candidate) is not None


def matches(payload: bytes, address: str) -> bool:
    """Whether `payload` really hashes to `address`.

    A malformed address is False here - it cannot be the address of anything.
    A caller that needs to distinguish "malformed" from "different content"
    calls `split` first and types the refusal itself.
    """
    return is_address(address) and address_of(payload) == address
