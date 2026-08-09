"""Content-addressed blob storage for C-14.

Owner: `evidence.artifact`.

THE LAYOUT IS THE INDEX. A blob lives at a path derived purely from its address
(`content_address.relative_path`), so there is no lookup table to fall out of
step with the filesystem and a misfiled blob is not addressable at all.

EVERY WRITE IS GOVERNED. `evidence.artifact` is layer rank 2 and `control.policy`
is rank 1, and `policy_callable_from_any_layer` makes the edge legal, so the PEP
call sits here at the point where the filesystem is actually touched rather than
being delegated upward to a surface that may not exist. Reads request
`READ_FILE`, writes request `WRITE_WORKSPACE_FILE`.

WORKSPACE ONLY. The two stable-mutation operation classes are never requested
and are deliberately not named anywhere in this module - structure check 11
treats a module that both names one and can write as a Stable mutation path, and
it is right to: this module writes files. Both classes are DENY for every actor
in any case; not requesting them is the point, and not naming them is how that
stays checkable.

WRITES ARE IDEMPOTENT AND NEVER OVERWRITE. If the bytes are already stored, the
address proves they are the same bytes and the write is skipped. There is no
code path that replaces an existing blob, so a stored artifact cannot be quietly
changed under its own identity.

NO DELETION. An artifact store that can delete is not append-only. Nothing here
removes a blob, and Package 1 ships no garbage collection.
"""

from __future__ import annotations

import pathlib
from typing import Final

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.evidence.artifact import content_address
from arkali.evidence.artifact.errors import (
    ArtifactContentMismatch,
    UnknownArtifact,
)

#: The actor this context presents to the PDP.
ACTOR: Final[str] = "evidence.artifact"
TRUST_TIER: Final[str] = "TRUST-0"
SURFACE: Final[str] = "evidence.artifact.blob_store"

READ: Final[str] = "READ_FILE"
WRITE: Final[str] = "WRITE_WORKSPACE_FILE"


class ArtifactBlobStore:
    """Bytes on disk, addressed by their own hash.

    The PEP is injected. There is no default that would let a caller obtain a
    store which writes without a policy decision.
    """

    def __init__(self, root: pathlib.Path, pep: PolicyEnforcementPoint) -> None:
        self._root = pathlib.Path(root)
        self._pep = pep

    @property
    def root(self) -> pathlib.Path:
        return self._root

    def _guard(self, operation: str) -> None:
        self._pep.require_auto(
            PolicyRequest(
                operation_class=operation, trust_tier=TRUST_TIER, actor=ACTOR
            )
        )

    def path_for(self, address: str) -> pathlib.Path:
        """Where `address` lives. Pure; performs no I/O and needs no decision."""
        return self._root / content_address.relative_path(address)

    def contains(self, address: str) -> bool:
        return self.path_for(address).is_file()

    def put(self, payload: bytes) -> str:
        """Store `payload` and return its address.

        The address is computed here from the bytes, so a caller cannot file
        content under an identity of its choosing.
        """
        address = content_address.address_of(payload)
        target = self.path_for(address)
        if target.is_file():
            # Same address means same bytes. Nothing to do, and deliberately no
            # overwrite branch exists.
            return address
        self._guard(WRITE)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary sibling and move into place, so a partial write
        # can never appear at an address that claims to hold complete content.
        staging = target.with_name(f"{target.name}.partial")
        staging.write_bytes(payload)
        staging.replace(target)
        return address

    def get(self, address: str) -> bytes:
        """The stored bytes for `address`, verified before they are returned.

        Verification is not optional on the read path: handing back bytes that
        no longer match their address would silently launder a corrupted blob
        into every downstream consumer.
        """
        self._guard(READ)
        target = self.path_for(address)
        if not target.is_file():
            raise UnknownArtifact(f"no stored content for {address!r}")
        payload = target.read_bytes()
        if not content_address.matches(payload, address):
            raise ArtifactContentMismatch(
                f"stored content for {address!r} hashes to "
                f"{content_address.address_of(payload)!r}; the bytes and the "
                "address disagree and neither is corrected automatically",
                source="docs/contracts/artifact.md section 2",
            )
        return payload

    def verify(self, address: str) -> bool:
        """Whether the stored bytes still hash to `address`.

        Returns False on mismatch rather than raising, so a caller can audit a
        whole store without the first bad blob ending the sweep.
        """
        self._guard(READ)
        target = self.path_for(address)
        if not target.is_file():
            raise UnknownArtifact(f"no stored content for {address!r}")
        return content_address.matches(target.read_bytes(), address)
