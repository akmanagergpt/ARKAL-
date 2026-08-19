"""C-31 suspicious-package review (ARK-REQ-0125).

Owner: `lifecycle.release` (Protected Core).

THREE REAL, LOCAL, DETERMINISTIC CHECKS - NO NETWORK CALL, NO EXTERNAL
REGISTRY, NO CREDENTIAL. `review_sbom` re-derives every finding from
`sbom.py`'s own real `SoftwareBillOfMaterials` on every call:

  1. UNPINNED DEPENDENCIES. `version_constraint == "*"` means the exact
     version that ships is decided at install time, by whatever the
     resolver finds - the textbook dependency-substitution risk this check
     exists to name (ARK-REQ-0124's own "deterministic manifests").

  2. KNOWN TYPOSQUAT NAMES. `_KNOWN_TYPOSQUATS` is a small, explicitly
     documented set of REAL, historically reported typosquat incidents -
     `crossenv` (npm, 2017, impersonating `cross-env`) and `colourama`
     (PyPI, impersonating `colorama`) - not a live threat-intel feed this
     repository has no way to query without a network call this phase's
     canonical scope forbids. Extending the set means adding a documented
     entry, never widening a pattern.

  3. NAME-CONFUSABLE PAIRS WITHIN ONE ECOSYSTEM. Two distinct dependency
     names in the same ecosystem with Levenshtein edit-distance <= 1 are
     flagged together - the general shape every specific typosquat in (2)
     is an instance of, catching a name this repository has never seen
     before rather than only ones already reported elsewhere.

A PASS (`findings == ()`) IS EARNED, NOT ASSUMED. This repository's own real
SBOM (Package 3) triggers none of the three checks today - proven directly
by this module's own test suite against the real manifests, not merely
asserted - and a synthetic negative control proves each check can genuinely
fire.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict

from arkali.lifecycle.release.sbom import SoftwareBillOfMaterials

#: (ecosystem, name) pairs with a real, documented typosquat history.
#: `crossenv` (npm, 2017): impersonated `cross-env`, exfiltrated environment
#: variables during install. `colourama` (PyPI): impersonated `colorama`
#: with a malicious clipboard-hijacking payload.
_KNOWN_TYPOSQUATS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("node", "crossenv"),
        ("python", "colourama"),
    }
)


def _levenshtein(a: str, b: str) -> int:
    """Classic edit distance, iterative, no external library."""
    if a == b:
        return 0
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            current[j] = min(
                previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost
            )
        previous = current
    return previous[-1]


class SuspiciousPackageFinding(BaseModel):
    """One real, named reason a dependency (or pair) was flagged."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dependency: str
    ecosystem: str
    reason: str


class SuspiciousPackageReview(BaseModel):
    """C-31/ARK-REQ-0125: the real, re-derived result of reviewing one SBOM."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reviewed_count: int
    findings: tuple[SuspiciousPackageFinding, ...]

    @property
    def clean(self) -> bool:
        return not self.findings


def _unpinned_findings(sbom: SoftwareBillOfMaterials) -> tuple[SuspiciousPackageFinding, ...]:
    return tuple(
        SuspiciousPackageFinding(
            dependency=entry.name,
            ecosystem=entry.ecosystem,
            reason="unpinned dependency (version_constraint is '*'); the "
            "exact version that ships is decided at install time",
        )
        for entry in sbom.entries
        if entry.version_constraint == "*"
    )


def _known_typosquat_findings(
    sbom: SoftwareBillOfMaterials,
) -> tuple[SuspiciousPackageFinding, ...]:
    return tuple(
        SuspiciousPackageFinding(
            dependency=entry.name,
            ecosystem=entry.ecosystem,
            reason=f"{entry.name!r} matches a documented typosquat incident "
            "in this ecosystem",
        )
        for entry in sbom.entries
        if (entry.ecosystem, entry.name) in _KNOWN_TYPOSQUATS
    )


def _confusable_pair_findings(
    sbom: SoftwareBillOfMaterials,
) -> tuple[SuspiciousPackageFinding, ...]:
    by_ecosystem: dict[str, list[str]] = {}
    for entry in sbom.entries:
        by_ecosystem.setdefault(entry.ecosystem, []).append(entry.name)
    findings: list[SuspiciousPackageFinding] = []
    for ecosystem, names in by_ecosystem.items():
        for i, first in enumerate(names):
            for second in names[i + 1 :]:
                if _levenshtein(first, second) <= 1:
                    findings.append(
                        SuspiciousPackageFinding(
                            dependency=f"{first} / {second}",
                            ecosystem=ecosystem,
                            reason=f"{first!r} and {second!r} are one edit "
                            "apart in the same ecosystem - a classic "
                            "typosquat shape",
                        )
                    )
    return tuple(findings)


def review_sbom(sbom: SoftwareBillOfMaterials) -> SuspiciousPackageReview:
    """The real, re-derived suspicious-package review of `sbom`.

    Never trusts a cached or prior result: every finding is recomputed from
    the SBOM handed to this call.
    """
    findings = (
        _unpinned_findings(sbom)
        + _known_typosquat_findings(sbom)
        + _confusable_pair_findings(sbom)
    )
    return SuspiciousPackageReview(
        reviewed_count=len(sbom.entries), findings=findings
    )


__all__ = [
    "SuspiciousPackageFinding",
    "SuspiciousPackageReview",
    "review_sbom",
]
