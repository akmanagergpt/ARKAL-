from __future__ import annotations

import ast
import importlib.util
import json
import pathlib
import sys
from decimal import Decimal
from types import SimpleNamespace

import pytest

from arkali.engineering.candidate.errors import CandidateIntegrityError
from arkali.engineering.candidate.ledger import (
    ACCEPTANCE_RUNNING,
    ACCEPTED,
    CandidateLedger,
    FINAL_GATE_FAILED,
    GenerationProvenance,
    GENERATING,
    GOLDEN_REPAIR_PASS,
    GOLDEN_REPAIR_RUNNING,
    hash_text,
    STAGED_GENERATION_PASS,
    STAGE_FAILED,
)
from arkali.engineering.repair import golden_corpus as gc
from arkali.engineering.repair import golden_corpus_injectors as gi
from arkali.engineering.repair import golden_repair_runner as gr
from arkali.engineering.repair.contracts import RepairBudget, RepairFingerprint
from arkali.engineering.repair.errors import (
    RepairBudgetExceededError,
    RepeatedFailedStrategyError,
)

# ---------------------------------------------------------------------------
# A minimal, but structurally faithful, synthetic candidate -- the same real
# conventions STAGED_GENERATION_STAGES.md requires (backend/app.py with a
# module-level `app`, backend/db.py, backend/routes.json,
# backend/data_model.json, backend/requirements.txt), never golden-work-129's
# own real content: this proves the corpus is domain-independent (item 14)
# by construction, since it is exercised here against a completely different
# resource name ("items", not "students"/"courses"/"payments").
# ---------------------------------------------------------------------------

_APP_PY = '''\
from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3

app = Flask(__name__)
CORS(app)


def get_db_connection():
    conn = sqlite3.connect('items.db')
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/items', methods=['GET'])
def list_items():
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM items').fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route('/items', methods=['POST'])
def create_item():
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO items (name, extra) VALUES (?, ?)',
        (data['name'], data['extra']),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return jsonify({'id': new_id, 'name': data['name'], 'extra': data['extra']})


@app.route('/items/<int:id>', methods=['GET'])
def get_item(id):
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM items WHERE id = ?', (id,)).fetchone()
    conn.close()
    if row is None:
        return jsonify({'error': 'not found'}), 404
    return jsonify(dict(row))


@app.route('/items/<int:id>', methods=['PUT'])
def update_item(id):
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE items SET name = ?, extra = ? WHERE id = ?',
        (data['name'], data['extra'], id),
    )
    if cursor.rowcount == 0:
        return jsonify({'error': 'not found'}), 404
    conn.commit()
    conn.close()
    return jsonify({'id': id, 'name': data['name'], 'extra': data['extra']})


@app.route('/items/<int:id>', methods=['DELETE'])
def delete_item(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM items WHERE id = ?', (id,))
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'error': 'not found'}), 404
    conn.commit()
    conn.close()
    return jsonify({'result': 'deleted'})
'''

_DB_PY = """\
import sqlite3


def init_db():
    conn = sqlite3.connect('items.db')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            extra TEXT
        )
    ''')
    conn.commit()
    conn.close()
"""

_ROUTES_JSON = json.dumps([
    {"path": "/items", "method": "GET"},
    {"path": "/items", "method": "POST"},
    {"path": "/items/{id}", "method": "GET"},
    {"path": "/items/{id}", "method": "PUT"},
    {"path": "/items/{id}", "method": "DELETE"},
], indent=2)

_DATA_MODEL_JSON = json.dumps({
    "fields": {"items": {"id": "integer", "name": "string", "extra": "string"}},
})

_REQUIREMENTS_TXT = "flask==2.3.2\nflask_cors>=3.0\npytest==7.4.0\nWerkzeug<3\n"

_TESTS_APP_PY = "def test_items_placeholder():\n    assert True\n"


def _candidate_files() -> dict[str, str]:
    """A fresh, unbroken copy every test starts from -- callers must never
    share or mutate this module-level content directly."""
    return {
        "backend/app.py": _APP_PY,
        "backend/db.py": _DB_PY,
        "backend/routes.json": _ROUTES_JSON,
        "backend/data_model.json": _DATA_MODEL_JSON,
        "backend/requirements.txt": _REQUIREMENTS_TXT,
        "tests/test_app.py": _TESTS_APP_PY,
    }


def _entry(defect_class: str, *, repairable: bool = True) -> gc.RepairCorpusEntry:
    return gc.RepairCorpusEntry(
        id=f"CORPUS-{defect_class}-001",
        defect_class=defect_class,
        title=defect_class,
        injection_target="source_module",
        injection_strategy="structural",
        expected_detection=("generated_backend_tests",),
        repairable=repairable,
        budget_profile="default",
        rationale="behavioral test fixture",
    )


def _all_entries() -> tuple[gc.RepairCorpusEntry, ...]:
    return tuple(_entry(cls) for cls in gc.DEFECT_CLASSES)


class TestEachInjectorDetectorPair:
    """Every real corpus class, proven individually: absent before its own
    injector runs, present after -- structural, on a resource name this
    corpus module has never seen (item 14: no domain-specific tokens)."""

    @pytest.mark.parametrize("defect_class", gc.DEFECT_CLASSES)
    def test_defect_is_absent_before_and_present_after_injection(
        self, defect_class: str,
    ) -> None:
        files = _candidate_files()
        detector = gi.DETECTORS[defect_class]
        injector = gi.INJECTORS[defect_class]
        assert detector(files) is False
        broken = injector(files)
        assert detector(broken) is True

    def test_no_defect_class_name_or_injector_source_names_a_resource(self) -> None:
        """A generic corpus must survive being pointed at a different
        product family -- proven here by targeting a family (\"items\")
        this module's own source code never mentions."""
        import inspect
        source = inspect.getsource(gc) + inspect.getsource(gi)
        for token in ("student", "course", "payment", "fee"):
            assert token not in source.lower()


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CORPUS_INSTANCE_PATH = REPO_ROOT / "golden" / "repair" / "golden_repair_corpus.json"


def _load_run_golden_repair():
    """`run_isolated_golden_repair`'s real lifecycle orchestration lives in
    scripts/run_golden_repair.py, not a gated backend/arkali library module
    (see golden_repair_runner.py's own module docstring for why: exercising
    engineering.repair -> engineering.candidate from inside the gated tree
    pushes the architecture's measured orchestration depth over budget).
    Loaded the same way any Python caller would run this real entry point --
    dynamically, by file path, exactly once per test session."""
    module_name = "scripts_run_golden_repair"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(
        module_name, REPO_ROOT / "scripts" / "run_golden_repair.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


rgr = _load_run_golden_repair()


class TestLoadCorpusInstance:
    """The real, versioned corpus data file (golden/repair/golden_repair_
    corpus.json), mirroring golden/scenarios/*.json's own real-data
    pattern -- loaded and validated here, not re-derived in code."""

    def test_the_real_corpus_instance_file_loads_and_covers_all_eight_classes(self) -> None:
        entries = gc.load_corpus_instance(CORPUS_INSTANCE_PATH)
        assert {e.defect_class for e in entries} == set(gc.DEFECT_CLASSES)

    def test_the_real_corpus_instance_declares_exactly_one_unrepairable_entry(self) -> None:
        entries = gc.load_corpus_instance(CORPUS_INSTANCE_PATH)
        unrepairable = [e for e in entries if not e.repairable]
        assert len(unrepairable) == 1

    def test_a_corpus_missing_a_required_class_is_refused(self, tmp_path: pathlib.Path) -> None:
        entries = gc.load_corpus_instance(CORPUS_INSTANCE_PATH)
        incomplete = [e.rendering() for e in entries[:-1]]
        import json as _json
        path = tmp_path / "incomplete.json"
        path.write_text(
            _json.dumps({"entries": [_json.loads(item) for item in incomplete]}), encoding="utf-8",
        )
        with pytest.raises(gc.CorpusInjectionError):
            gc.load_corpus_instance(path)

    def test_the_real_corpus_instance_hash_is_deterministic(self) -> None:
        entries = gc.load_corpus_instance(CORPUS_INSTANCE_PATH)
        assert gc.corpus_hash(entries) == gc.corpus_hash(gc.load_corpus_instance(CORPUS_INSTANCE_PATH))

    def test_the_real_corpus_instance_drives_correct_injection_on_a_synthetic_candidate(self) -> None:
        """The real, declared entries (not a hand-built test fixture) applied
        end to end against a candidate this corpus has never seen."""
        entries = gc.load_corpus_instance(CORPUS_INSTANCE_PATH)
        files = _candidate_files()
        broken = gi.apply_corpus(files, entries)
        present = gi.corpus_defects_present(broken, entries)
        assert all(present.values()), present


class TestInjectionNeverTouchesProtectedPaths:
    def test_no_injector_writes_a_tests_or_config_path(self) -> None:
        """Corpus definition Sec5.4: injection targets only the declared
        injection_target, never tests/ or config/ (item 6)."""
        files = _candidate_files()
        before_protected = {p: v for p, v in files.items() if p.startswith(("tests/", "config/"))}
        broken = gi.apply_corpus(files, _all_entries())
        after_protected = {p: v for p, v in broken.items() if p.startswith(("tests/", "config/"))}
        assert before_protected == after_protected


class TestParentFilesUnchangedAfterInjection:
    def test_apply_corpus_never_mutates_the_caller_supplied_mapping(self) -> None:
        """item 4 (corpus-module half): the caller's own files mapping must
        be byte-for-byte unchanged after apply_corpus -- only the returned
        copy carries the injected defects."""
        files = _candidate_files()
        original = dict(files)
        gi.apply_corpus(files, _all_entries())
        assert files == original


class TestCorpusHashDeterminism:
    def test_the_same_entries_hash_identically_across_calls(self) -> None:
        """item 5."""
        entries = _all_entries()
        assert gc.corpus_hash(entries) == gc.corpus_hash(entries)

    def test_hash_is_independent_of_declared_entry_order(self) -> None:
        entries = _all_entries()
        reversed_entries = tuple(reversed(entries))
        assert gc.corpus_hash(entries) == gc.corpus_hash(reversed_entries)

    def test_a_changed_entry_changes_the_hash(self) -> None:
        entries = _all_entries()
        mutated = entries[:-1] + (
            entries[-1].model_copy(update={"rationale": "a different rationale"}),
        )
        assert gc.corpus_hash(entries) != gc.corpus_hash(mutated)


class TestCombinedInjectionStaysStructurallyValid:
    def test_all_eight_defects_coexist_and_app_py_still_parses(self) -> None:
        files = _candidate_files()
        broken = gi.apply_corpus(files, _all_entries())
        ast.parse(broken["backend/app.py"])
        json.loads(broken["backend/routes.json"])
        present = gi.corpus_defects_present(broken, _all_entries())
        assert all(present.values()), present


def _fingerprint(**overrides: object) -> RepairFingerprint:
    values: dict[str, object] = {
        "failure_signature": "fixture-failure",
        "root_cause_class": "fixture-root-cause",
        "files": ("backend/app.py",),
        "strategy": "fixture-strategy",
        "provider_model": "test/fake-model",
        "outcome": "fixture-outcome",
    }
    values.update(overrides)
    return RepairFingerprint.model_validate(values)


def _budget(**overrides: object) -> RepairBudget:
    values: dict[str, object] = {
        "attempts": 5,
        "ai_calls": 5,
        "elapsed_seconds": 60,
        "cost": Decimal(0),
        "touched_files": 10,
        "regression_delta": 0,
    }
    values.update(overrides)
    return RepairBudget.model_validate(values)


class TestRunCorpusRepairConvergence:
    """The bounded, dependency-injected convergence loop -- no real model or
    workspace involved; `attempt_repair` is a fake callable, exactly the
    seam `golden_corpus.py` was designed with for this purpose."""

    def test_a_repairable_defect_reaches_a_resolved_outcome_within_budget(self) -> None:
        """item 7."""
        files = _candidate_files()
        entry = _entry(gc.CONTRACT_VIOLATION)
        broken = {**files, "backend/app.py": gi.INJECTORS[gc.CONTRACT_VIOLATION](files)["backend/app.py"]}

        def fake_attempt_repair(entry: gc.RepairCorpusEntry, current: dict[str, str]):
            # Simulates a real repair: restores the file the injector broke.
            fixed = {**current, "backend/app.py": files["backend/app.py"]}
            return fixed, _fingerprint(strategy="restore-contract-field")

        result = gr.run_corpus_repair(
            (entry,), broken, _budget(), fake_attempt_repair, candidate_id="test-candidate-1",
        )
        assert result.resolved == (entry.id,)
        assert result.escalated == ()
        assert gi.DETECTORS[gc.CONTRACT_VIOLATION](result.files) is False

    def test_a_deliberately_unrepairable_defect_reaches_automatic_escalated(self) -> None:
        """item 8: no --record-escalated flag, no operator flag anywhere in
        this call -- escalation is the loop's own real, structural response
        to a repeated failed strategy."""
        files = _candidate_files()
        entry = _entry(gc.CONTRACT_VIOLATION, repairable=False)
        broken = {**files, "backend/app.py": gi.INJECTORS[gc.CONTRACT_VIOLATION](files)["backend/app.py"]}

        def never_fixes(entry: gc.RepairCorpusEntry, current: dict[str, str]):
            # Simulates a model that always proposes the identical failing
            # strategy and never actually resolves the defect.
            return None, _fingerprint(strategy="always-fails")

        result = gr.run_corpus_repair(
            (entry,), broken, _budget(), never_fixes, candidate_id="test-candidate-2",
        )
        assert result.escalated == (entry.id,)
        assert result.resolved == ()
        assert gi.DETECTORS[gc.CONTRACT_VIOLATION](result.files) is True

    def test_a_repeated_failed_strategy_cannot_loop_indefinitely_in_one_run(self) -> None:
        """item 9: the fake attempt_repair is called a bounded, small number
        of times -- never runs away inside one call to run_corpus_repair."""
        files = _candidate_files()
        entry = _entry(gc.CONTRACT_VIOLATION, repairable=False)
        broken = {**files, "backend/app.py": gi.INJECTORS[gc.CONTRACT_VIOLATION](files)["backend/app.py"]}
        call_count = 0

        def never_fixes(entry: gc.RepairCorpusEntry, current: dict[str, str]):
            nonlocal call_count
            call_count += 1
            return None, _fingerprint(strategy="always-fails")

        result = gr.run_corpus_repair(
            (entry,), broken, _budget(attempts=1000), never_fixes, candidate_id="test-candidate-3",
        )
        # RepeatedFailedStrategyError fires on the second identical
        # fingerprint -- exactly two attempts, never a thousand.
        assert call_count == 2
        assert result.escalated == (entry.id,)

    def test_an_already_resolved_entry_needs_no_attempt_at_all(self) -> None:
        files = _candidate_files()
        entry = _entry(gc.CONTRACT_VIOLATION)
        calls: list[object] = []

        def should_never_be_called(entry: gc.RepairCorpusEntry, current: dict[str, str]):
            calls.append(entry)
            return None, _fingerprint()

        result = gr.run_corpus_repair(
            (entry,), files, _budget(), should_never_be_called, candidate_id="test-candidate-4",
        )
        assert calls == []
        assert result.resolved == (entry.id,)

    def test_an_exceeded_budget_dimension_also_escalates_automatically(self) -> None:
        files = _candidate_files()
        entry = _entry(gc.CONTRACT_VIOLATION, repairable=False)
        broken = {**files, "backend/app.py": gi.INJECTORS[gc.CONTRACT_VIOLATION](files)["backend/app.py"]}
        attempt_index = 0

        def distinct_failing_strategies(entry: gc.RepairCorpusEntry, current: dict[str, str]):
            nonlocal attempt_index
            attempt_index += 1
            # A different strategy each time defeats the anti-loop check
            # specifically, so the plain attempts ceiling is what fires.
            return None, _fingerprint(strategy=f"strategy-{attempt_index}")

        result = gr.run_corpus_repair(
            (entry,), broken, _budget(attempts=2), distinct_failing_strategies,
            candidate_id="test-candidate-5",
        )
        assert result.escalated == (entry.id,)
        assert attempt_index == 3  # 2 recorded normally, 3rd exceeds the ceiling


# ---------------------------------------------------------------------------
# run_isolated_golden_repair -- the real lifecycle wired against a real
# CandidateLedger/WorkspaceAuthority on tmp_path. No real model, no real
# workspace under var/factory/candidates: every parent/child directory below
# lives entirely under pytest's own tmp_path.
# ---------------------------------------------------------------------------


def _write_all(root: pathlib.Path, files: dict[str, str]) -> None:
    # write_bytes, never write_text: text-mode writes translate "\n" to the
    # platform newline (CRLF on Windows), which would silently disagree with
    # workspace.write's own raw-bytes write and make an untouched file look
    # "changed" to changed_protected_paths for a reason with nothing to do
    # with repair.
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


def _provenance(**overrides: object) -> GenerationProvenance:
    values: dict[str, object] = {
        "goal_hash": hash_text("golden repair test goal"),
        "source_commit": "abc123",
        "runtime": "test",
        "endpoint": "test://fixture",
        "model": "test/fake-model",
        "model_parameters": {},
        "pipeline_version": "test-fixture/1.0.0",
    }
    values.update(overrides)
    return GenerationProvenance(**values)  # type: ignore[arg-type]


def _accept_parent(
    ledger: CandidateLedger, candidates_root: pathlib.Path, parent_id: str,
) -> pathlib.Path:
    """Drives a real candidate through the real staged-generation lifecycle
    to ACCEPTED, using the same real transitions run_staged_generation.py
    and run_golden_acceptance.py together produce -- never a shortcut
    state -- so a test against it is a test against a genuine ACCEPTED
    parent, not a fabricated one."""
    root = candidates_root / parent_id
    root.mkdir(parents=True)
    _write_all(root, _candidate_files())
    ledger.allocate(parent_id, provenance=_provenance())
    ledger.record_state(parent_id, GENERATING, root)
    ledger.record_state(parent_id, STAGED_GENERATION_PASS, root)
    ledger.record_state(parent_id, ACCEPTANCE_RUNNING, root)
    ledger.record_state(parent_id, ACCEPTED, root)
    return root


_PASSING_GATE = lambda files: SimpleNamespace(passed=True, findings=())  # noqa: E731


def _run_repair(
    ledger: CandidateLedger, candidates_root: pathlib.Path, *, parent_id: str, child_id: str,
    attempt_repair=None, inspect_gate=_PASSING_GATE, budget: RepairBudget | None = None,
) -> rgr.GoldenRepairOutcome:
    if attempt_repair is None:
        def attempt_repair(entry: gc.RepairCorpusEntry, current: dict[str, str]):
            fixed = {**current, "backend/app.py": _candidate_files()["backend/app.py"]}
            return fixed, _fingerprint(strategy=f"restore-{entry.defect_class}")
    request = rgr.GoldenRepairRequest(
        parent_id=parent_id, child_id=child_id,
        entries=(_entry(gc.CONTRACT_VIOLATION),),
        budget=budget or _budget(),
        attempt_repair=attempt_repair,
        provenance=_provenance(),
    )
    return rgr.run_isolated_golden_repair(
        ledger, candidates_root, request, inspect_gate=inspect_gate,
    )


class TestParentEligibility:
    def test_a_non_accepted_parent_is_refused_before_any_workspace_mutation(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """item 1."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        root = candidates_root / "golden-work-parent"
        root.mkdir(parents=True)
        _write_all(root, _candidate_files())
        ledger.allocate("golden-work-parent", provenance=_provenance())
        ledger.record_state("golden-work-parent", GENERATING, root)
        ledger.record_state("golden-work-parent", STAGE_FAILED, root)

        called = []
        with pytest.raises(CandidateIntegrityError):
            _run_repair(
                ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
                attempt_repair=lambda entry, current: called.append(entry) or (None, _fingerprint()),
            )
        assert called == []
        assert not (candidates_root / "golden-work-child").exists()

    def test_an_accepted_parent_with_integrity_drift_is_refused(self, tmp_path: pathlib.Path) -> None:
        """item 2."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        root = _accept_parent(ledger, candidates_root, "golden-work-parent")
        (root / "backend" / "app.py").write_text("# tampered after acceptance\n", encoding="utf-8")

        with pytest.raises(CandidateIntegrityError):
            _run_repair(ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child")
        assert not (candidates_root / "golden-work-child").exists()


class TestIsolatedRepairChild:
    def test_an_intact_accepted_parent_gets_a_real_isolated_child_workspace(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """item 3."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")

        outcome = _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
        )
        assert outcome.state == GOLDEN_REPAIR_PASS
        assert outcome.workspace_root == candidates_root / "golden-work-child"
        assert outcome.workspace_root.is_dir()
        assert ledger.classify("golden-work-child") == GOLDEN_REPAIR_PASS

    def test_the_parent_directory_is_never_touched_by_a_repair_run(self, tmp_path: pathlib.Path) -> None:
        """item 13 (files half): parent bytes on disk are identical before
        and after a full repair run reaches GOLDEN_REPAIR_PASS."""
        from arkali.engineering.candidate.ledger import file_manifest

        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        parent_root = _accept_parent(ledger, candidates_root, "golden-work-parent")
        before = file_manifest(parent_root)

        _run_repair(ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child")

        after = file_manifest(parent_root)
        assert before == after


class TestNoTestWeakening:
    def test_a_repair_attempt_that_touches_a_protected_test_path_fails_validation(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """item 10: a misbehaving attempt_repair that also rewrites
        tests/test_app.py must never be allowed to reach GOLDEN_REPAIR_PASS,
        even though its own targeted defect really is fixed."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")

        def weakens_tests(entry: gc.RepairCorpusEntry, current: dict[str, str]):
            fixed = {
                **current,
                "backend/app.py": _candidate_files()["backend/app.py"],
                "tests/test_app.py": "# tests weakened during repair\n",
            }
            return fixed, _fingerprint(strategy="weaken-tests")

        outcome = _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
            attempt_repair=weakens_tests,
        )
        assert outcome.state == FINAL_GATE_FAILED
        assert outcome.protected_path_violations == ("tests/test_app.py",)
        assert ledger.classify("golden-work-child") == FINAL_GATE_FAILED


class TestRepairChildEntersExistingAcceptanceFlow:
    def test_a_golden_repair_pass_child_can_begin_the_existing_acceptance_gate(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """item 11: begin_acceptance (the real, unmodified gate
        run_golden_acceptance.py calls) accepts a GOLDEN_REPAIR_PASS child
        exactly as it already accepts a STAGED_GENERATION_PASS one."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")
        outcome = _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
        )
        assert outcome.state == GOLDEN_REPAIR_PASS

        ledger.begin_acceptance("golden-work-child", outcome.workspace_root)  # must not raise
        assert ledger.classify("golden-work-child") == ACCEPTANCE_RUNNING


class TestNormalLifecycleUnchanged:
    def test_a_normal_staged_generation_candidate_still_works_unmodified(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """item 12: a completely ordinary candidate, sharing the same
        ledger as a golden-repair child, reaches ACCEPTED through the
        identical real transitions it always has -- golden_corpus's own
        additions changed nothing about this path."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")
        _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
        )

        ordinary_root = candidates_root / "golden-work-ordinary"
        ordinary_root.mkdir(parents=True)
        _write_all(ordinary_root, _candidate_files())
        ledger.allocate("golden-work-ordinary", provenance=_provenance())
        ledger.record_state("golden-work-ordinary", GENERATING, ordinary_root)
        ledger.record_state("golden-work-ordinary", STAGED_GENERATION_PASS, ordinary_root)
        ledger.record_state("golden-work-ordinary", ACCEPTANCE_RUNNING, ordinary_root)
        ledger.record_state("golden-work-ordinary", ACCEPTED, ordinary_root)
        assert ledger.classify("golden-work-ordinary") == ACCEPTED


class TestRepairChildAcceptedNeverMutatesParent:
    def test_the_child_reaching_accepted_leaves_the_parents_own_history_unchanged(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """item 13 (ledger-history half)."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")
        parent_history_before = ledger.history("golden-work-parent")

        outcome = _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
        )
        ledger.begin_acceptance("golden-work-child", outcome.workspace_root)
        ledger.record_state("golden-work-child", ACCEPTED, outcome.workspace_root)

        assert ledger.classify("golden-work-child") == ACCEPTED
        assert ledger.classify("golden-work-parent") == ACCEPTED
        assert ledger.history("golden-work-parent") == parent_history_before


class TestChangedProtectedPaths:
    """The no-test-weakening comparison helper (ARK-REQ-0093 item 10)."""

    def test_identical_manifests_report_no_changed_protected_paths(self) -> None:
        manifest = {"tests/test_app.py": {"sha256": "abc", "byte_length": 10}}
        assert gc.changed_protected_paths(manifest, manifest) == ()

    def test_a_changed_test_file_hash_is_reported(self) -> None:
        parent = {"tests/test_app.py": {"sha256": "abc", "byte_length": 10}}
        child = {"tests/test_app.py": {"sha256": "different", "byte_length": 12}}
        assert gc.changed_protected_paths(parent, child) == ("tests/test_app.py",)

    def test_a_deleted_test_file_is_reported(self) -> None:
        parent = {"tests/test_app.py": {"sha256": "abc", "byte_length": 10}}
        child: dict[str, dict[str, object]] = {}
        assert gc.changed_protected_paths(parent, child) == ("tests/test_app.py",)

    def test_a_planted_new_test_file_is_reported(self) -> None:
        parent: dict[str, dict[str, object]] = {}
        child = {"tests/new_test.py": {"sha256": "abc", "byte_length": 10}}
        assert gc.changed_protected_paths(parent, child) == ("tests/new_test.py",)

    def test_a_changed_non_protected_file_is_not_reported(self) -> None:
        parent = {
            "tests/test_app.py": {"sha256": "abc", "byte_length": 10},
            "backend/app.py": {"sha256": "same", "byte_length": 5},
        }
        child = {
            "tests/test_app.py": {"sha256": "abc", "byte_length": 10},
            "backend/app.py": {"sha256": "changed", "byte_length": 6},
        }
        assert gc.changed_protected_paths(parent, child) == ()
