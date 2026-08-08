"""Layer grouping package: lifecycle (rank 5).

Not a bounded context. Contains only bounded-context subpackages.
A module may depend only on strictly lower layer ranks, plus the sibling
edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__layer__ = "lifecycle"
__layer_rank__ = 5
__is_bounded_context__ = False
