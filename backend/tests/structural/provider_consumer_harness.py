"""Shared fixtures for the ARK-REQ-0053 consumer controls. NOT a test module.

Follows the `durable_harness.py` / `plane_harness.py` precedent: real shared
infrastructure that several test modules import and pytest collects from none,
because `python_files = ["test_*.py"]`.

Every helper derives its subject from `AUTHORITY_MAP.yaml` at call time. No
consumer, concern or context is named here, so a canonical change moves the
controls that use it instead of leaving them stale.
"""

from __future__ import annotations

import pathlib
from typing import Final

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.gates.authority_gates import ShadowRegistryGate
from arkali.control.architecture.gates.base import GateContext
from arkali.kernel.contracts.results import CheckResult

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
SCANNER_MODULE: Final[pathlib.Path] = (
    REPO / "backend/arkali/control/architecture/gates/provider_source.py"
)


def mutate(amap: AuthorityMap, **changes: object) -> AuthorityMap:
    """In-memory mutation only. The repository file is never touched."""
    data = amap.model_dump()
    data.update(changes)
    return AuthorityMap.model_validate(data)


def widen_authority(amap: AuthorityMap, **changes: object) -> AuthorityMap:
    """The same, for the `provider_authority` section specifically."""
    return mutate(amap, provider_authority={**amap.provider_authority, **changes})


def consumer_roots(amap: AuthorityMap) -> dict[str, str]:
    """Declared consumer -> declared module root, derived at call time."""
    found = {
        name: amap.contexts[name].module_root
        for name in amap.provider_authority["reference_only_consumers"]
        if name in amap.contexts
    }
    assert found, "no reference-only consumer resolves; the controls would be vacuous"
    return found


def materialise(root: pathlib.Path, amap: AuthorityMap) -> pathlib.Path:
    """A minimal tree carrying every declared consumer, and nothing else."""
    for module_root in consumer_roots(amap).values():
        target = root / module_root
        target.mkdir(parents=True, exist_ok=True)
        (target / "__init__.py").write_text("", encoding="utf-8")
    return root


def evaluate(root: pathlib.Path, amap: AuthorityMap) -> CheckResult:
    """The REAL gate, so detection is proven end to end (F-0017, F-0040)."""
    return ShadowRegistryGate().evaluate(GateContext(root, amap))


def place(
    root: pathlib.Path, amap: AuthorityMap, source: str, name: str = "probe.py"
) -> CheckResult:
    """Write one module into the FIRST declared consumer and run the gate."""
    first = next(iter(consumer_roots(amap).values()))
    (root / first / name).write_text(source, encoding="utf-8")
    return evaluate(root, amap)


def summaries(result: CheckResult) -> list[str]:
    return [finding.summary for finding in result.findings]
