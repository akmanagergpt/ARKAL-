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

## Package 2 scope

Package 2 adds a read-only coverage projection. The requirement denominator,
classification, required evidence keys and conditional rules are loaded from
the canonical register on every call. MANDATORY requirements are always
applicable; an absent state value or rule expression that cannot be evaluated
remains APPLICABLE. An unknown requirement identifier is a refusal, never a
NOT_APPLICABLE classification.

Requirement coverage counts only a graph-reachable `PASS` result. Required
evidence coverage counts a register evidence key only when that exact key is a
Test node on a passing path. No producer name, filename, prose or weaker result
is interpreted as evidence. OPTIONAL and objectively false CONDITIONAL entries
are excluded; all other registered MANDATORY and CONDITIONAL entries remain in
the denominator. This projection records nothing, issues no capability or
release verdict and does not create the Proof-of-Engineering Passport.

## Package 3 scope

Package 3 adds the immutable Proof-of-Engineering Passport accounting view over
that projection. Its applicable nineteen-kind vocabulary is parsed from the
frozen Verification and Delivery Contract, while each concrete obligation is
the exact evidence key on an applicable Canonical Requirement Register entry.
Requirements are grouped by the register's owning component, which is the
capability boundary; no producer chooses its own obligations.

Every counted item retains the complete C-16 binding: requirement, contract,
artifact, test/evidence kind, content-addressed evidence record and honest
result. Only exact register keys on passing paths are present. Missing and
non-PASS evidence remain explicit, and completion is the number of requirements
whose evidence obligations are complete divided by the applicable register
denominator. This is evidence accounting only: it persists nothing and issues
no Acceptance Engine, phase, release or human-gate verdict.

## Package 5 scope

Package 5 adds the Acceptance Engine's per-capability verdict over the immutable
Passport. An implementation claim is evidence-derived: at least one passing,
fully bound C-16 path must exist. That fact remains strictly weaker than
`VERIFIED`, which requires every applicable obligation owned by the Canonical
Requirement Register to be present and passing. Missing mandatory evidence is
reported by exact requirement and evidence-key identity and always produces a
non-verified result.

The verdict cannot accept producer opinion, create evidence, waive an
obligation, or classify applicability. For every declared required HUMAN GATE
it calls the policy-owned Package 4 boundary and refuses unless the gate is
recorded. The result is a capability-verification projection only: it grants no
release, Stable mutation, promotion, phase acceptance, or human-gate authority.
