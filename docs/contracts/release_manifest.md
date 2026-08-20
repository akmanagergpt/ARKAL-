# Release Manifest + SBOM — derived contract (C-31, Phase 26)

**Owner:** `lifecycle.release` (Protected Core — Release Authority, SBOM,
suspicious-package review, HUMAN_GATE_7 wiring — all six packages), one
field owned by `evidence.artifact` (`ARK-REQ-0015`'s Git-linked
revisions/content hashes, reused unmodified via C-14)
**Kind:** ART (a library composition producing real content-addressed
artifacts; no HTTP route — no Phase 26 requirement is owned by any
`surfaces.*` context)
**Confinement:** STRICT (per `CONTRACT_INVENTORY.md`'s own row)
**Identity:** content-addressed (`ReleaseCandidate.release_id`, and every
C-14 artifact this contract registers — provenance, SBOM, suspicious-package
review, final manifest — each its own real `sha256:` address)
**Version:** 1.0.0

This document records the executable Phase 26 contract derived from
`REQUIREMENT_REGISTER.md` (`ARK-REQ-0007`, `ARK-REQ-0015`, `ARK-REQ-0124`,
`ARK-REQ-0125`, `ARK-REQ-0350`, `ARK-REQ-0369`),
`docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md` sections "Product Plane",
"Frozen technology direction" and "Supply-Chain Security",
`docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md` sections
"Provenance" and "Final delivery", `docs/canonical/AUTHORITY_MAP.yaml`'s
`lifecycle.release` declaration (Protected Core), and
`docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md` row 26 (no human gate
precondition for phase acceptance; the state machine's own `RELEASED`
transition is separately guarded by `HUMAN_GATE_7`). It does not replace
those authorities.

## 0. Scope of this revision

Six atomic packages plus this candidate freeze, no new state machine minted
(`STATE_MACHINES.md` stays at twelve — `Release` was already declared since
an early phase, reused as-is, its first real production caller) and no
second release, artifact, evidence, or human-gate authority created (D-017's
own explicit rule):

1. `release_manifest.py` — `ReleaseAuthority`, the first real composer of
   the unmodified `Release` machine and the unmodified `StableRevisionPointer`
   (read-only). `ReleaseCandidate` is content-addressed over
   `(core_revision_id, declared_at)`, never caller-supplied.
2. `release_provenance.py` — registers a release candidate's own declaration
   as a real C-14 artifact via a structural `ArtifactRegistrar` Protocol
   (avoiding a real, measured `max_orchestration_depth` violation), every
   VDC §Provenance field populated, re-verified after write.
3. `sbom.py` — a real, deterministic dependency inventory parsed from
   `backend/pyproject.toml`/`frontend/package.json`, no network call.
4. `suspicious_package_review.py` — three real, local, deterministic checks
   (unpinned dependencies, documented typosquat names, name-confusable
   pairs), no external registry.
5. `release_composition.py` + `release_gate.py` — the final manifest
   artifact (real parent edges to provenance/SBOM/review) and the real
   `HUMAN_GATE_7` singleton wiring that closes "bypassed acceptance"/
   "bypassed release policy".
6. `test_release_supply_chain_adversarial.py` — negative/adversarial proofs
   for the named supply-chain risks (artifact tampering, digest mismatch,
   stale/forged candidate, wrong provenance, dependency substitution,
   release replay, secret leakage, direct Stable mutation, wrong
   target/environment, unsigned/unverified package, rollback to unverified
   revision, package/version identity collision).
7. `test_release_journey.py` — the composed VDC journey, this contract
   document, the C-17 report and traceability record (candidate frozen).

## 1. Real-time dependency inventory

`SoftwareBillOfMaterials` (`sbom.py`): `entries: tuple[DependencyEntry, ...]`,
each `{ecosystem, name, version_constraint}`, sorted by `(ecosystem, name)`
for determinism. Parsed live from this repository's own two real,
canonical manifests — `backend/pyproject.toml`'s `[project.dependencies]`
(via `tomllib`, Python 3.13 standard library) and `frontend/package.json`'s
`"dependencies"` — every call, never cached. `devDependencies` are
deliberately excluded (build/dev tooling, a separate VDC §Final delivery
line item). `ARK-REQ-0369` (CONDITIONAL) is genuinely applicable —
`ecosystem.sbom_supported` is true for both Python and Node on this real
repository — and genuinely `PASS`, not `NOT_APPLICABLE` by default.

## 2. Suspicious-package review

`SuspiciousPackageReview` (`suspicious_package_review.py`):
`{reviewed_count, findings: tuple[SuspiciousPackageFinding, ...]}`, real,
local, deterministic, re-derived on every call:

1. **Unpinned dependencies** — `version_constraint == "*"`.
2. **Known typosquat names** — a small, explicitly documented set of real
   historical incidents (`crossenv`/npm 2017 impersonating `cross-env`,
   `colourama`/PyPI impersonating `colorama`), never a live threat-intel
   query.
3. **Name-confusable pairs** — Levenshtein edit-distance ≤ 1 between two
   distinct names in the same ecosystem.

This repository's own real SBOM earns a genuine, re-derived `clean == True`
result — proven directly by `test_suspicious_package_review.py`, not
assumed — and a synthetic negative control proves each check can fire.

## 3. Release Authority and the real `Release` machine

`ReleaseAuthority.declare_release_candidate` (`release_manifest.py`)
composes `release_state_machine.build()` (unmodified, `docs/canonical/
STATE_MACHINES.md` §7: `DRAFT → BUILT → VERIFIED → SIGNED_READY → RELEASED`,
alternate terminal `WITHDRAWN`) and `StableRevisionPointer.current()`
(unmodified, Phase 22B), refusing before constructing anything if no Stable
Core revision exists yet — the literal mechanism behind `ARK-REQ-0007`
("Stable definitions take effect from first Release-Authority
designation"): a "Stable Product revision" (MS's own distinct term from
"Stable Core revision") has no meaning until this Release Authority's first
real `DRAFT` declaration exists, and that declaration can only ever
reference an already-designated Stable Core revision.
`ReleaseAuthority.assert_still_stable` re-asks the pointer directly on every
call, defending against a stale or tampered candidate naming a revision
this repository's own history has since disowned.

`DRAFT → RELEASED`/`BUILT → RELEASED`/`VERIFIED → RELEASED` are not
declared transitions — only `SIGNED_READY → RELEASED` is — so no
intermediate stage can be skipped, structurally (`test_release_supply_
chain_adversarial.py::TestUnsignedOrUnverifiedPackageCannotReachReleased`).

## 4. Real C-14 provenance, composition, and evidence completeness

`register_release_provenance` (`release_provenance.py`) registers one
artifact per release candidate — `producer_agent`, `provider_model`
("none" — packaging is fully deterministic, no AI provider is contacted),
`task_id`, `specification_version` ("C-31"), `context_hash` (the packaged
core revision) — through the real, unmodified C-14 `ArtifactStore`
(Phase 6), reached via a structural `ArtifactRegistrar` Protocol rather than
a direct import (a real, measured `max_orchestration_depth` violation: the
pre-existing `lifecycle.evolution → lifecycle.release` edge would have
extended through `evidence.artifact → control.policy → kernel.contracts` to
five hops).

`compose_release_manifest` (`release_composition.py`) then registers the
SBOM and the suspicious-package review as their own real C-14 artifacts, and
a final manifest artifact whose `parents` cite all three — the point in
this pipeline where a genuine derivation exists to record, proven by
`ArtifactStore.register`'s own foreign-key check on `parents` at write time.
`verify_evidence_complete` re-checks all four artifacts on every call —
never a stored flag; a real tamper test
(`test_release_composition.py::test_verify_evidence_complete_is_false_
after_real_tampering`) proves it can genuinely flip to `False`.

## 5. `HUMAN_GATE_7` — a real, unscoped singleton, not invented

`authorize_release` (`release_gate.py`) supplies the two facts
`release_state_machine.release_guard` requires for `SIGNED_READY →
RELEASED`. A genuine canonical-discovery correction happened mid-package:
an early draft built a scoped `(gate, operation_class, target, revision)`
grant lookup mirroring `HUMAN_GATE_2`/`HUMAN_GATE_3`'s own mechanism, before
re-reading `CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md`'s own Canonical
HUMAN GATES list closely enough to see that Gate 7 ("Final Production
Release") is textually the same shape as Gate 1 ("PHASE 0 canonical
architecture acceptance") — and
`acceptance.human_gate_authorization.SINGLETON_GATES` already declares both
`{HUMAN_GATE_1, HUMAN_GATE_7}` as one-time, unscoped project events,
answered by "a legacy, gate-ID-only record", not a repeatable category. The
scoped design was discarded before shipping. The real mechanism composes
`GovernanceState.accepted_human_gates` — the identical simple membership
check Gate 1 already uses — through a `HumanGate7Source` structural
Protocol (`lifecycle.release` has no depth headroom for a direct
`acceptance.engine` import). `evidence_complete` still comes from real
artifact re-verification (§4).

Mechanically re-verified against this real repository:
`GATE_7 not in GovernanceState.load(REPO).accepted_human_gates` — `HUMAN_
GATE_7` has never been recorded here, so the real, unmodified guard
genuinely refuses `RELEASED` today
(`test_release_journey.py::test_the_full_journey_from_core_promotion_to_a_
real_gate_refusal`), and genuinely permits it once a real, temporary
`HUMAN_GATE_RECORDS.md` grants it
(`test_release_journey.py::test_released_is_reachable_once_a_genuine_
gate_7_grant_exists`) — never against the live, accepted `docs/` tree.

## 6. Supply-chain negative/adversarial proofs

`test_release_supply_chain_adversarial.py` proves, against real running
infrastructure, every risk this phase's own acceptance brief names:
artifact tampering / digest mismatch (a tampered blob fails
`ArtifactStore.verify`), stale/forged release candidate
(`assert_still_stable` refuses a never-promoted revision), wrong provenance
(`context_hash` always matches the real core revision), dependency
substitution / build-artifact-source mismatch (a substituted manifest
immediately changes the SBOM), release replay (three replayed declarations
register exactly one artifact), secret leakage (a secret-shaped field is
refused by the existing C-09 `assert_no_raw_secret` path before persisting),
direct Stable mutation (AST proof: only `stable_pointer.py` ever calls
`.promote`/`.rollback_to`), wrong target/environment (AST proof: no release
function accepts a deployment-target parameter), unsigned/unverified
package (§3), rollback to unverified revision (the unmodified pointer still
refuses it), package/version identity collision (two different core
revisions never share a `release_id`).

## 7. What is explicitly not claimed

- **No live goal-to-product pipeline.** DEF-009 remains open, permanently
  tracked. This phase strengthens only the acceptance → release → packaging
  → deployment-preparation end of the chain the discovery brief named — not
  the goal → blueprint → routing → local-AI → candidate → product end.
- **No real deployment.** No installer is built, no target environment is
  selected, no artifact is transferred anywhere — proven structurally, not
  merely by omission (§6's wrong-target/environment AST proof). Deployment
  execution is Phase 29's own obligation (`check_phase_graph.py`: "Installer
  phase can integrate the Recovery Supervisor").
- **No real code signing.** VDC's own wording is "signing-ready", not
  "signed" — no signing credential exists in this canonical scope, and none
  is fabricated. `SIGNED_READY` is a real state-machine stage name, not a
  claim that a cryptographic signature was produced.
- **No live external SBOM/vulnerability-database query.** The suspicious-
  package review is local and deterministic by design (§2); it does not,
  and canonically may not, contact a network service.
- **No second release, artifact, evidence, or human-gate authority.** Every
  mechanism this contract composes — `Release`, `StableRevisionPointer`,
  `ArtifactStore`, `GovernanceState.accepted_human_gates` — is the real,
  pre-existing one, reused unmodified (D-017; §§3–5 above).
- **No frontend increment.** No Phase 26 requirement is owned by any
  `surfaces.*` context; C-31's own delivery type is `ART`, not an HTTP
  contract — the identical reasoning the Phase 7 durable-job enqueue
  surface and Phase 25's own Computer-Use execution boundaries already
  recorded for the same shape of decision.
