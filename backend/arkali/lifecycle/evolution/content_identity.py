"""Content-address re-export for `lifecycle.evolution` (ADR-0008 decomposition).

`campaign_declaration.py` and `campaign_ledger.py` each need
`kernel.contracts.content_address.address_of` for their own C-33 evidence
identity. One shared site in this context imports the kernel primitive;
mirrors `engineering.candidate.content_identity`, which exists for the
identical reason.
"""

from __future__ import annotations

from arkali.kernel.contracts.content_address import address_of, is_address

__all__ = ["address_of", "is_address"]
