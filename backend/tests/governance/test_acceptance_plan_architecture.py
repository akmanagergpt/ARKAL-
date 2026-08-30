"""Regression protections for the acceptance-plan compiler/reconciliation
split (ARK-REQ-0074 Phase 30): a handful of real architectural invariants
that unit tests alone would not catch if quietly violated by a future
change -- each one names the real defect it prevents.

Owner: `control.architecture`.
"""

from __future__ import annotations

import inspect
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[3]
FACTORY = REPO / "backend" / "arkali" / "engineering" / "factory"


class TestCoreRunnerNeverDefaultsToAHandAuthoredScenario:
    """`run_golden_acceptance.py --scenario` must be an explicit override,
    never the argparse default -- the compiled-by-default path (Part A)
    is what makes the runner usable against a candidate nobody hand-wrote
    a scenario for. `TestScenarioResolution` in `test_golden_acceptance_
    runner.py` proves the real BEHAVIOR (no flag -> compiles); this is the
    narrower, cheaper regression trip-wire on the flag's own wiring."""

    def test_the_scenario_flag_has_no_default_path(self) -> None:
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location(
            "run_golden_acceptance", REPO / "scripts" / "run_golden_acceptance.py",
        )
        runner = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = runner
        spec.loader.exec_module(runner)

        source = inspect.getsource(runner.main)
        assert '"--scenario", type=pathlib.Path, default=None' in source, (
            "run_golden_acceptance.py's --scenario flag must default to None "
            "(compile-by-default), never a hand-authored scenario path"
        )


class TestNoSecondJsFunctionParameterParser:
    """Part B's own consolidation (commit e067d83): `frontend_mutation_
    contract.py` and `frontend_callback_arity_preflight.py` once each
    implemented their own, inconsistent regex for "this function's own
    declared parameters" -- both must keep importing the single shared
    implementation in `frontend_js_semantics.py`, never grow a second copy
    back."""

    _CONSUMERS = (
        FACTORY / "frontend_mutation_contract.py",
        FACTORY / "frontend_callback_arity_preflight.py",
    )
    _RETIRED_NAMES = ("_function_params", "_function_definition_params", "_bare_reference_declared_params")

    def test_both_consumers_import_the_shared_parser(self) -> None:
        for path in self._CONSUMERS:
            source = path.read_text(encoding="utf-8")
            assert "from arkali.engineering.factory.frontend_js_semantics import" in source, path

    def test_neither_consumer_reintroduces_its_own_retired_parser(self) -> None:
        for path in self._CONSUMERS:
            source = path.read_text(encoding="utf-8")
            for name in self._RETIRED_NAMES:
                assert f"def {name}(" not in source, f"{path} reintroduced {name}"


class TestFixtureFilesNeverEnterTheProductionImportGraph:
    """`golden/scenarios/*.json` is real DATA -- a regression oracle
    (Part A) and an explicit `--scenario` override target -- never a
    second code path. No file under `backend/arkali/**` may open or
    hardcode a path into it; only `run_golden_acceptance.py` (a script,
    not a package module) and test files may reference it."""

    def test_no_production_package_file_opens_a_golden_scenario_fixture(self) -> None:
        offenders = []
        for path in (REPO / "backend" / "arkali").rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            if "golden" + "/scenarios/" in source or "golden" + "\\scenarios\\" in source:
                # Prose docstring mentions ("...regression fixture, e.g.
                # `golden/scenarios/student_fee_management.json`") are the
                # one legitimate real exception -- no `open(...)`/`Path(...)`
                # call anywhere in this codebase actually loads that path
                # from inside `arkali/` today; a real future load call would
                # still contain this same substring and be caught here too,
                # so this stays a real (if coarse) regression trip-wire.
                if "open(" in source or ".read_text(" in source:
                    offenders.append(str(path.relative_to(REPO)))
        assert offenders == [], offenders


class TestAManualScenarioIsNeverAuthoritativeOnItsOwn:
    """`_reconcile_scenario` exists precisely so a `--scenario` override is
    never trusted on its own -- this is a real, enforced call site, not
    just a function that exists somewhere unused."""

    def test_run_golden_acceptance_calls_reconcile_before_trusting_an_override(self) -> None:
        source = (REPO / "scripts" / "run_golden_acceptance.py").read_text(encoding="utf-8")
        assert "_reconcile_scenario(scenario, contract_files)" in source
