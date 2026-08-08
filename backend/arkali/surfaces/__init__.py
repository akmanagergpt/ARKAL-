"""Layer grouping package: surfaces (rank 6).

Not a bounded context. Contains only bounded-context subpackages.
A module may depend only on strictly lower layer ranks, plus the sibling
edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__layer__ = "surfaces"
__layer_rank__ = 6
__is_bounded_context__ = False
