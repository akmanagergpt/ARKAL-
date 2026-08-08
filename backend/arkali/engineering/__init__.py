"""Layer grouping package: engineering (rank 4).

Not a bounded context. Contains only bounded-context subpackages.
A module may depend only on strictly lower layer ranks, plus the sibling
edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__layer__ = "engineering"
__layer_rank__ = 4
__is_bounded_context__ = False
