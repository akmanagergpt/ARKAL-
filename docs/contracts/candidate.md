# C-25 — Candidate manifest + assembly report

**Owner:** `engineering.candidate` · **Kind:** ART · **Versioning:** semver
· **Compatibility:** STRICT · **Phase:** 12

This is a derived description of the implemented contract. Canonical documents
and executable repository controls remain authoritative.

## Package 2 scope

Package 2 delivers the candidate manifest and isolated-workspace foundation.
It does not deliver the assembly report or execute the eight semantic checks.
No requirement is discharged until Phase 12 acceptance.

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
stable-revision verdict. Semantic assembly belongs to the next package;
acceptance and promotion remain separate authorities and stages.
