"""ARK-REQ-0009 architecture control: the canonical frontend stack is real.

THE REQUIREMENT. `REQUIREMENT_REGISTER.md` row ARK-REQ-0009 — "Frontend stack:
React, TypeScript, Vite, Tailwind", sourced to `MS §Frozen tech`, owned by
`surfaces.command`, verified by **arch**. So it owes an architecture control,
not merely a build that happened to succeed.

THE STACK IS PARSED, NOT LISTED. The four technologies are read from the Master
Specification's "Frontend:" line at call time. Writing them here would create a
second copy of a canonical decision, and if governance ever changed the frozen
direction this control would keep verifying the old one.

DECLARED IS NOT USED. A dependency in `package.json` proves an intention. Each
technology is therefore required to be resolved in the tracked lockfile **and**
to be doing work in the source tree: React rendering a real root, TypeScript
under `strict`, Vite owning the build, Tailwind's directives compiled with its
content globs actually covering the source. Any one of those can be removed
without the others noticing, and each removal fails here.

WHAT THIS CONTROL CANNOT SEE. Whether the toolchain is installed and runs. That
is execution evidence, and it lives in the phase report's recorded commands
(`npm ci`, `tsc --noEmit`, `vitest run`, `vite build`, `playwright test`). This
module deliberately reads only tracked files, so it gives the same answer on a
fresh clone as it does here.
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Final

import pytest

from tests.structural.typescript_reader import FRONTEND, FRONTEND_SRC, REPO, read

MASTER_SPEC: Final[pathlib.Path] = (
    REPO / "docs" / "ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md"
)
PACKAGE_JSON: Final[pathlib.Path] = FRONTEND / "package.json"
LOCKFILE: Final[pathlib.Path] = FRONTEND / "package-lock.json"

#: The canonical name each declared technology carries on npm.
NPM_NAME: Final[dict[str, str]] = {
    "react": "react",
    "typescript": "typescript",
    "vite": "vite",
    "tailwind css": "tailwindcss",
}


def canonical_frontend_stack() -> tuple[str, ...]:
    """The technologies MS §Frozen technology direction names for the frontend."""
    text = MASTER_SPEC.read_text(encoding="utf-8")
    match = re.search(r"^Frontend:\s*(?P<items>[^\n]+?)\.\s*$", text, re.M)
    assert match is not None, (
        "the Master Specification declares no 'Frontend:' line; the canonical "
        "stack cannot be resolved and this control must not report PASS"
    )
    declared = tuple(item.strip().lower() for item in match.group("items").split(","))
    assert len(declared) >= 4, f"unexpected frozen frontend direction: {declared}"
    return declared


@pytest.fixture(scope="module")
def stack() -> tuple[str, ...]:
    return canonical_frontend_stack()


@pytest.fixture(scope="module")
def manifest() -> dict[str, object]:
    return dict(json.loads(read(PACKAGE_JSON)))


@pytest.fixture(scope="module")
def declared_versions(manifest: dict[str, object]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for section in ("dependencies", "devDependencies"):
        merged.update(dict(manifest.get(section, {})))  # type: ignore[arg-type]
    return merged


class TestTheCanonicalStackIsDeclaredAndLocked:
    def test_the_control_reads_the_canonical_four(self, stack: tuple[str, ...]) -> None:
        assert set(NPM_NAME) <= set(stack), (
            f"the frozen frontend direction is {stack}, which this control does "
            "not know how to verify in full; it must be extended rather than "
            "silently passing on the part it recognises"
        )

    def test_every_declared_technology_is_a_real_dependency(
        self, stack: tuple[str, ...], declared_versions: dict[str, str]
    ) -> None:
        for technology in stack:
            package = NPM_NAME.get(technology)
            if package is None:
                continue
            assert package in declared_versions, (
                f"{technology} is canonical but {package!r} is not a frontend "
                "dependency"
            )

    def test_every_declared_technology_is_resolved_in_the_lockfile(
        self, stack: tuple[str, ...]
    ) -> None:
        """A declaration is an intention; a lock entry is a resolved artifact.

        `INSTALL_DEPENDENCY` is LOCKFILE_BOUND, so a technology present only in
        `package.json` was never actually resolved by npm.
        """
        packages = dict(json.loads(read(LOCKFILE))["packages"])
        for technology in stack:
            package = NPM_NAME.get(technology)
            if package is None:
                continue
            key = f"node_modules/{package}"
            assert key in packages, f"{package!r} is not resolved in the lockfile"
            assert packages[key].get("version"), f"{package!r} has no locked version"


class TestEveryTechnologyIsActuallyDoingWork:
    def test_react_renders_a_real_root(self) -> None:
        entry = FRONTEND_SRC / "main.tsx"
        assert entry.is_file(), "there is no React entry point"
        source = read(entry)
        assert "react-dom/client" in source
        assert "createRoot(" in source
        components = [
            path
            for path in FRONTEND_SRC.rglob("*.tsx")
            if "return (" in read(path) or "=> (" in read(path)
        ]
        assert components, "no React component renders anything"

    def test_typescript_is_strict_and_owns_the_source(self) -> None:
        config = read(FRONTEND / "tsconfig.json")
        assert '"strict": true' in config, (
            "TypeScript is present but not strict, which is the property that "
            "makes it a stack choice rather than a file extension"
        )
        sources = list(FRONTEND_SRC.rglob("*.ts")) + list(FRONTEND_SRC.rglob("*.tsx"))
        assert len(sources) >= 5
        assert not list(FRONTEND_SRC.rglob("*.jsx")), (
            "untyped JSX sources exist alongside the TypeScript ones"
        )

    def test_vite_owns_the_build(self, manifest: dict[str, object]) -> None:
        config = FRONTEND / "vite.config.ts"
        assert config.is_file()
        assert "defineConfig" in read(config)
        scripts = dict(manifest.get("scripts", {}))  # type: ignore[arg-type]
        assert "vite build" in scripts.get("build", ""), (
            "the build script does not run Vite, so Vite is not the bundler"
        )

    def test_tailwind_is_compiled_over_the_real_source(self) -> None:
        config = read(FRONTEND / "tailwind.config.ts")
        assert "content:" in config
        assert "./src/" in config, (
            "Tailwind's content globs do not cover the source tree, so its "
            "classes would be purged and the styling would be inert"
        )
        stylesheet = read(FRONTEND_SRC / "index.css")
        for directive in ("@tailwind base", "@tailwind components", "@tailwind utilities"):
            assert directive in stylesheet, f"{directive} is missing"
        postcss = read(FRONTEND / "postcss.config.js")
        assert "tailwindcss" in postcss, "Tailwind is not in the PostCSS pipeline"

    def test_the_stylesheet_is_actually_imported_by_the_application(self) -> None:
        """NEGATIVE CONTROL: an unimported stylesheet compiles to nothing used."""
        assert "index.css" in read(FRONTEND_SRC / "main.tsx")


class TestPlaywrightIsTheDeclaredE2ETool:
    def test_the_master_spec_names_playwright_and_the_repository_uses_it(
        self, declared_versions: dict[str, str]
    ) -> None:
        """`MS §Frozen tech` puts "Playwright E2E" in the testing direction.

        T10 is the tier that discharges the `e2e` column for ARK-REQ-0178 and
        ARK-REQ-0229, so the tool is not interchangeable.
        """
        spec = MASTER_SPEC.read_text(encoding="utf-8")
        assert re.search(r"^Testing:.*Playwright", spec, re.M | re.I), (
            "the Master Specification no longer names Playwright; this control "
            "must be re-derived rather than assumed"
        )
        assert "@playwright/test" in declared_versions
        assert (FRONTEND / "playwright.config.ts").is_file()
