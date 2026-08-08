"""C-02 correlation / causation envelope.

Owner: kernel.observability. Every governance action emits an envelope carrying
correlation and causation identifiers plus evidence links, so a result can be
traced back to the run that produced it (ARK-REQ-0014, ARK-REQ-0242).

Determinism: identifiers are supplied by the caller or derived from a seed. This
module never calls uuid4() or the clock implicitly, because governance output
must be reproducible byte-for-byte across identical runs.
"""

from __future__ import annotations

import hashlib
from typing import Self

from pydantic import BaseModel, ConfigDict, Field


def derive_id(*parts: str) -> str:
    """Deterministic identifier from stable inputs. Same inputs, same id."""
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:32]


class Envelope(BaseModel):
    """Correlation/causation envelope attached to every emitted record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    correlation_id: str
    causation_id: str | None = None
    context: str
    operation: str
    evidence_links: tuple[str, ...] = Field(default_factory=tuple)

    @classmethod
    def root(cls, context: str, operation: str, *, seed: str) -> Self:
        """Start a new correlation chain from a deterministic seed."""
        return cls(
            correlation_id=derive_id(context, operation, seed),
            causation_id=None,
            context=context,
            operation=operation,
        )

    def child(self, context: str, operation: str) -> Self:
        """Derive a caused envelope, preserving the correlation id."""
        return type(self)(
            correlation_id=self.correlation_id,
            causation_id=derive_id(self.correlation_id, context, operation),
            context=context,
            operation=operation,
        )

    def with_evidence(self, *links: str) -> Self:
        """Return a copy with additional evidence links, order preserved."""
        return self.model_copy(update={"evidence_links": self.evidence_links + links})
