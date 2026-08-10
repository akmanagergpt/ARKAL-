"""Bounded context: execution.scheduler (layer execution, rank 3).

Canonical authority for:
  - resource_allocation

Protected Core: no.
Implementation phase: 8.

Phase 8 Package 1 delivers the C-21 worker contract: `worker_vocabulary` parses
the canonical worker classes and declaration dimensions, and `worker_contract`
validates and holds worker declarations under an injected PEP. C-21 is INT, so
this context maps no record and owns no table.

No admission decision exists yet - that is Package 2. Allocation state, queues,
priority and fairness are not implemented and are not claimed.

Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml. No sibling edge
exists between this context and `execution.durable`, in either direction.
"""

__context__ = "execution.scheduler"
__layer__ = "execution"
__layer_rank__ = 3
__protected_core__ = False
__all__: list[str] = []
