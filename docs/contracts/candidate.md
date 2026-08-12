# C-25 — Candidate manifest + assembly report

**Owner:** `engineering.candidate` · **Kind:** ART · **Versioning:** semver
· **Compatibility:** STRICT · **Phase:** 12

This is a derived description of the implemented contract. Canonical documents
and executable repository controls remain authoritative.

## Packages 2–4 scope

Package 2 delivers the candidate manifest and isolated-workspace foundation.
Package 3 delivers the immutable assembly report and executes every consistency
pair read from the canonical Semantic Candidate Assembly declaration. No
requirement is discharged until Phase 12 acceptance.

Package 4 enforces the separate Stable-path boundary from its owning contexts.
`control.policy.AgentAuthority` derives both the direct-mutation permission set
and prohibited actors from `AUTHORITY_MAP.yaml`: the live permission set is
empty, so every actor and mechanism is refused, including an unknown label;
`ROLLBACK_STABLE` remains a separate Recovery Supervisor operation rather than
a direct-write permission. `lifecycle.release.StableCandidatePath` derives the
required path from the same declaration and issues immutable receipts only for
one-stage progression. Each receipt carries the complete traversed prefix, so
skipping directly to an accepted or promotion stage is refused. This authority
validates progression only: it performs no stable write and does not decide
verification, acceptance, or rollback.

`WorkspaceAuthority.allocate` creates one exclusive directory per workspace and
copies the stable task snapshot into it. Reallocation is refused, all write paths
are confined below the assigned root, and stable input is opened only as a copy
source. Thus agents may change their own snapshot but cannot share a workspace
or write through this contract to the stable source.

`CandidateManifest` is frozen and STRICT-versioned at `1.0.0`. It records the
candidate, workspace, task and agent identities, a content-addressed task
snapshot, and one or more canonical Product Plane components with immutable
artifact references. Component names are validated through
`AssemblyVocabulary`, which reads the Master Specification at call time. Its
deterministic JSON rendering is itself content-addressed as `manifest_ref`.

The manifest deliberately contains no verification, acceptance, promotion or
stable-revision verdict.

`SemanticAssembler` requires exactly one injected evaluator for every canonical
pair and executes them in canonical order. Each evaluator independently reduces
its left and right domain views to content-addressed semantic fingerprints. A
pair is consistent only when those fingerprints match; the result and overall
summary are derived and cannot be asserted by a caller. Missing, duplicate,
unknown, invalid or errored evaluations refuse the whole report rather than
fabricating an empty or successful check.

`AssemblyReport` is frozen and STRICT-versioned at `1.0.0`, binds the candidate
identity to the immutable manifest address, records all pair observations, and
is itself deterministically content-addressed. `all_consistent` is an assembly
fact only. The report carries no verification, acceptance, promotion or stable
verdict; those remain separate authorities and later stages.
