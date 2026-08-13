# C-16 — Evidence graph edge (`REQ→Contract→Artifact→Test→Evidence→Result`)

**Owner:** `acceptance.engine` · **Kind:** GRAPH · **Versioning:** semver
· **Compatibility:** STRICT · **Phase:** 13

This is a derived description of the Package 1 implementation. Canonical
documents and executable controls remain authoritative.

## Package 1 scope

The Evidence Graph is an immutable, read-only view derived from the intact C-15
audit chain. It creates no table and has no write operation. C-15 remains the
sole evidence store and integrity authority; C-14 remains the artifact identity
and provenance authority; the Canonical Requirement Register remains the sole
requirement denominator.

The six node kinds and their order are parsed from C-16's row in
`CONTRACT_INVENTORY.md` at call time. Each C-15 record must supply one complete
path: its registered requirement reference, contract reference, artifact
reference, test reference, own content-addressed evidence identity and canonical
honest result. Missing nodes, an empty or corrupt chain, an unknown requirement,
or an absent, malformed or vacuous C-16 declaration fail closed.

Nodes and adjacent edges are de-duplicated without losing their first-seen
order, and the graph is bound to the recomputed chain head. Superseded records
remain visible: selecting the result that counts is an acceptance decision and
is deliberately not smuggled into this foundation.

Package 1 computes no applicability, coverage or completion percentage, records
no Proof-of-Engineering Passport, and issues no acceptance or release verdict.
