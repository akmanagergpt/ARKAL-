"""Content addressing for C-14 (ARK-REQ-0057).

Owner: `evidence.artifact` - `ARCHITECTURE.md` section 3 row 11 names this
context the authority for "Artifact Fabric, content addressing, provenance".

THE ADDRESS IS DERIVED, NEVER SUPPLIED. Every function here takes bytes and
returns an address. There is no constructor that accepts a digest from a caller,
because an identity a caller can choose is an identity that can disagree with its
content - the single failure content addressing exists to prevent.

DETERMINISTIC AND TOTAL. The digest is taken over the raw bytes only. No
timestamp, filename, host fact or ordering participates, so identical bytes yield
an identical address in any process on any host. The empty byte string has an
address like any other.

NO PERSISTENCE, NO POLICY, NO FILESYSTEM. This module is pure. It is the piece
every other artifact module depends on, so keeping it free of I/O is what lets
the determinism control test it directly rather than through a store.
"""

from __future__ import annotations

import hashlib
import re
from typing import Final

from arkali.evidence.artifact.errors import InvalidArtifactIdentity

#: The algorithm this phase ships. Named once; the address carries it explicitly
#: so a future algorithm is a new prefix rather than a silent reinterpretation of
#: existing rows.
ALGORITHM: Final[str] = "sha256"

#: `<algorithm>:<lowercase hex digest>`. Anchored, lowercase-only and
#: length-exact, so a truncated or upper-cased digest is rejected rather than
#: stored as a second spelling of the same artifact.
ADDRESS_PATTERN: Final[re.Pattern[str]] = re.compile(r"^(?P<algorithm>sha256):(?P<digest>[0-9a-f]{64})$")


def digest_of(payload: bytes) -> str:
    """The lowercase hex digest of `payload`."""
    return hashlib.sha256(payload).hexdigest()


def address_of(payload: bytes) -> str:
    """The canonical content address of `payload`.

    The only way an `artifact_id` is ever produced.
    """
    return f"{ALGORITHM}:{digest_of(payload)}"


def parse(address: str) -> tuple[str, str]:
    """Split a well-formed address into `(algorithm, digest)`.

    Refuses anything that is not exactly canonical. Accepting a lenient spelling
    would let the same bytes be filed under two identities.
    """
    match = ADDRESS_PATTERN.match(address)
    if match is None:
        raise InvalidArtifactIdentity(
            f"{address!r} is not a canonical content address "
            f"('{ALGORITHM}:<64 lowercase hex digits>')"
        )
    return match.group("algorithm"), match.group("digest")


def is_address(candidate: str) -> bool:
    """Whether `candidate` is a canonical content address."""
    return ADDRESS_PATTERN.match(candidate) is not None


def matches(payload: bytes, address: str) -> bool:
    """Whether `payload` really hashes to `address`.

    Parses first, so a malformed address is a typed refusal rather than a
    quiet False that a caller might read as "different content".
    """
    parse(address)
    return address_of(payload) == address


def relative_path(address: str) -> str:
    """Where the bytes for `address` live, relative to the store root.

    Sharded on the first two digest characters so a directory does not grow to
    hold every artifact ever produced. The path is a pure function of the
    address, so the filesystem layout *is* the index: a blob cannot be misfiled
    and still be addressable.
    """
    _algorithm, digest = parse(address)
    return f"{ALGORITHM}/{digest[:2]}/{digest}"
