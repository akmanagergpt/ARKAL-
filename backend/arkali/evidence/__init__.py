"""Layer grouping package: evidence (rank 2).

Not a bounded context. Contains only bounded-context subpackages.
A module may depend only on strictly lower layer ranks, plus the sibling
edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__layer__ = "evidence"
__layer_rank__ = 2
__is_bounded_context__ = False
