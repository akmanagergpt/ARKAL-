"""Every third-party import an entrypoint script makes must be declared (F-0042).

WHAT THIS CATCHES, STATED PLAINLY. `scripts/run_command_center.py` is the real
runtime entrypoint and the T10 browser-evidence harness. It imported `uvicorn`
directly while no manifest declared it anywhere, so a canonical install produced
an entrypoint that raised `ModuleNotFoundError` on start, and the accepted
Phase 5 e2e evidence — `EV-0048`, "a real uvicorn-served surfaces.command
process" — was reproducible only on a machine that happened to have uvicorn.
Nothing compared the imports against the manifest, which is why it survived
three phases.

EVERY SUBJECT IS DERIVED. The script set, their imports, the standard library,
the import-name to distribution-name mapping and the declared requirement names
all come from the live repository and the live environment. No list here is
transcribed, so a script added later, or an import added to an existing script,
is covered without editing this control - the F-0032 lesson.

THIS CHECKS DECLARATION, NOT WHICH GROUP. Whether a dependency belongs in
`dependencies` or in an optional-extra is a policy question the manifest owns.
What this asserts is the property that failed: that it is declared *somewhere*,
so a canonical install can reproduce the entrypoint.

FAILS CLOSED. An import whose distribution cannot be resolved is reported, not
skipped: an unresolvable name is an unanswered question, and treating it as
satisfied would be the vacuous pass this control exists to prevent.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
import tomllib
from importlib.metadata import packages_distributions
from typing import Final

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS: Final[pathlib.Path] = REPO / "scripts"
MANIFEST: Final[pathlib.Path] = REPO / "backend" / "pyproject.toml"

#: The distribution this repository builds. Its own modules are not third party.
FIRST_PARTY: Final[str] = "arkali"

#: PEP 503 name normalisation, so `PyYAML`, `pyyaml` and `py-yaml` compare equal.
_SEPARATORS: Final[re.Pattern[str]] = re.compile(r"[-_.]+")


def _normalise(name: str) -> str:
    return _SEPARATORS.sub("-", name).lower()


def _script_modules() -> list[pathlib.Path]:
    found = sorted(SCRIPTS.glob("*.py"))
    assert found, "no script found; this control would be vacuous"
    return found


def _sibling_module_names() -> set[str]:
    """Scripts import each other by bare name; those are files, not packages."""
    return {path.stem for path in _script_modules()}


def _third_party_imports(path: pathlib.Path) -> set[str]:
    """Top-level import names that are neither stdlib, first-party nor sibling."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tops: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            tops |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            tops.add(node.module.split(".")[0])
    return {
        name
        for name in tops
        if name not in sys.stdlib_module_names
        and name != FIRST_PARTY
        and name not in _sibling_module_names()
    }


def _declared_requirements() -> set[str]:
    """Every distribution named by the manifest, in any dependency group."""
    manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    project = manifest["project"]
    specifiers: list[str] = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        specifiers.extend(extra)
    # A requirement string is `name` followed by any extras, marker or specifier.
    return {
        _normalise(re.split(r"[<>=!~\[; ]", specifier, maxsplit=1)[0])
        for specifier in specifiers
        if specifier.strip()
    }


def _distributions_for(import_name: str) -> set[str]:
    return {_normalise(dist) for dist in packages_distributions().get(import_name, [])}


class TestEntrypointDependenciesAreDeclared:
    """A canonical install must be able to run what the repository ships."""

    def test_every_third_party_script_import_is_declared_in_the_manifest(
        self,
    ) -> None:
        declared = _declared_requirements()
        assert declared, "the manifest declares no dependency at all"

        checked = 0
        undeclared: list[str] = []
        unresolved: list[str] = []
        for path in _script_modules():
            for import_name in sorted(_third_party_imports(path)):
                checked += 1
                distributions = _distributions_for(import_name)
                if not distributions:
                    unresolved.append(f"{path.name} -> {import_name}")
                    continue
                if not (distributions & declared):
                    undeclared.append(
                        f"{path.name} imports {import_name!r} "
                        f"(distribution {sorted(distributions)}), which "
                        f"backend/pyproject.toml does not declare"
                    )

        assert not unresolved, (
            "these imports resolve to no installed distribution, so whether they "
            f"are declared cannot be answered: {unresolved}"
        )
        assert not undeclared, (
            "an entrypoint script imports something a canonical install would not "
            f"provide: {undeclared}"
        )
        assert checked >= 3, (
            f"only {checked} third-party script imports were checked; this "
            "control would be weaker than the defect it closes"
        )

    def test_the_test_clients_http_backend_is_declared(self) -> None:
        """Closes F-0043, the transitive half of the same defect.

        `fastapi.testclient.TestClient` is used by four test modules, and
        `starlette.testclient` binds an HTTP backend that starlette declares
        under its own `full` extra rather than as a hard requirement. The
        manifest declared none, so on a canonical install the import raised and
        pytest could not COLLECT the suite - a stricter failure than F-0042's,
        because no evidence tier could run at all.

        Derived, not named: the live starlette is asked which backend it
        actually bound, and the manifest must declare that. If starlette changes
        backend again, this control follows it instead of going stale.

        Imported inside the test on purpose. At module scope an unimportable
        client would break collection of this control too, and the one thing it
        must never do is disappear exactly when it is needed.
        """
        import starlette.testclient as testclient

        backend = testclient.httpx.__name__
        distributions = _distributions_for(backend)
        assert distributions, (
            f"starlette.testclient bound {backend!r}, which resolves to no "
            "installed distribution"
        )
        assert distributions & _declared_requirements(), (
            f"the test client binds {backend!r} (distribution "
            f"{sorted(distributions)}) but the manifest does not declare it; on a "
            "canonical install pytest could not collect the suite"
        )

    def test_the_runtime_entrypoints_server_is_declared(self) -> None:
        """The specific regression F-0042 closed, kept executable.

        Derived rather than named: whatever server the launcher imports must be
        declared. Renaming the server does not silence this.
        """
        launcher = SCRIPTS / "run_command_center.py"
        assert launcher.is_file(), "the Command Center launcher is missing"
        imports = _third_party_imports(launcher)
        assert imports, "the launcher imports nothing third-party; control vacuous"
        declared = _declared_requirements()
        for import_name in sorted(imports):
            distributions = _distributions_for(import_name)
            assert distributions & declared, (
                f"the runtime entrypoint imports {import_name!r} but the manifest "
                "does not declare it; a canonical install could not start it"
            )
