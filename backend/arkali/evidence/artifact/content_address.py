"""Artifact identity: content addressing for C-14 (ARK-REQ-0057).

Owner: `evidence.artifact` - AUTHORITY_MAP.yaml concern
`artifact_identity_and_provenance`. `ARCHITECTURE.md` section 3 row 11 names
this context the authority for "Artifact Fabric, content addressing,
provenance".

THE AUTHORITY IS HERE; THE MECHANISM IS IN THE KERNEL. The bytes-to-digest
primitive moved to `kernel.contracts.content_address` in Phase 6 Package 2,
because `evidence.audit` needs the same mechanism and the two contexts are
siblings that `allow_same_layer: false` forbids from importing each other. Only
rank 0 is reachable from both. This is the Phase 3 shape recorded in
`DECISION_LOG.md`: the mechanism is a kernel contract, the authority stays with
the context the authority map names.

WHAT REMAINED HERE, AND WHY IT IS THE AUTHORITY. The kernel primitive is total -
it returns values and decides nothing. This module decides:

  * that a malformed address is `InvalidArtifactIdentity`, a typed refusal in
    this context's taxonomy;
  * that an artifact's address is the canonical form and no other spelling is
    accepted;
  * where an artifact's bytes live (`relative_path`), which is storage layout
    and has nothing to do with hashing.

THE ADDRESS IS DERIVED, NEVER SUPPLIED. Every function takes bytes and returns
an address. There is no constructor that accepts a digest from a caller, because
an identity a caller can choose is an identity that can disagree with its
content - the single failure content addressing exists to prevent.

NO PERSISTENCE, NO POLICY, NO FILESYSTEM. This module is pure, which is what
lets the determinism controls test it directly rather than through a store.
"""

from __future__ import annotations

from typing import Final

from arkali.evidence.artifact.errors import InvalidArtifactIdentity
from arkali.kernel.contracts.content_address import (
    ADDRESS_LENGTH,
    ALGORITHM,
    address_of,
    digest_of,
    is_address,
    split,
)

__all__ = [
    "ADDRESS_LENGTH",
    "ALGORITHM",
    "address_of",
    "digest_of",
    "is_address",
    "matches",
    "parse",
    "relative_path",
]

#: Re-exported so this context's own modules read artifact identity from their
#: own authority rather than reaching past it to the primitive.
_ALGORITHM: Final[str] = ALGORITHM


def parse(address: str) -> tuple[str, str]:
    """Split a well-formed artifact address into `(algorithm, digest)`.

    Refuses anything that is not exactly canonical. Accepting a lenient spelling
    would let the same bytes be filed under two identities. This is where the
    kernel primitive's `None` becomes a typed refusal in this taxonomy.
    """
    parts = split(address)
    if parts is None:
        raise InvalidArtifactIdentity(
            f"{address!r} is not a canonical content address "
            f"('{ALGORITHM}:<64 lowercase hex digits>')"
        )
    return parts


def matches(payload: bytes, address: str) -> bool:
    """Whether `payload` really hashes to `address`.

    Parses first, so a malformed address is a typed refusal rather than a quiet
    False a caller might read as "different content".
    """
    parse(address)
    return address_of(payload) == address


def relative_path(address: str) -> str:
    """Where the bytes for `address` live, relative to the store root.

    Storage layout, not hashing - which is why it stayed in this context.
    Sharded on the first two digest characters so a directory does not grow to
    hold every artifact ever produced. The path is a pure function of the
    address, so the filesystem layout *is* the index: a blob cannot be misfiled
    and still be addressable.
    """
    _algorithm, digest = parse(address)
    return f"{ALGORITHM}/{digest[:2]}/{digest}"
