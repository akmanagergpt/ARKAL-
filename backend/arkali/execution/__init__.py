"""Layer grouping package: execution (rank 3).

Not a bounded context. Contains only bounded-context subpackages.
A module may depend only on strictly lower layer ranks, plus the sibling
edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__layer__ = "execution"
__layer_rank__ = 3
__is_bounded_context__ = False
