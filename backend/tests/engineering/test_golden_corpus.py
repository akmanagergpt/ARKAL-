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


def _entry(
    defect_class: str, *, repairable: bool = True, injection_target: str = "source_module",
) -> gc.RepairCorpusEntry:
    return gc.RepairCorpusEntry(
        id=f"CORPUS-{defect_class}-001",
        defect_class=defect_class,
        title=defect_class,
        injection_target=injection_target,
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


class TestChangedFileCount:
    """`_changed_file_count` -- the real touched_files diff, proven directly
    (items A/B/C): golden-work-129-repair-1's real terminal state was
    FINAL_GATE_FAILED because the old code charged an attempt for every
    file in the returned mapping, not the files it actually changed."""

    def test_one_changed_file_out_of_a_full_returned_mapping_counts_as_one(self) -> None:
        """item A."""
        before = _candidate_files()
        after = {**before, "backend/app.py": "# changed\n"}
        assert gr._changed_file_count(before, after) == 1

    def test_an_unchanged_returned_mapping_counts_as_zero(self) -> None:
        """item B."""
        before = _candidate_files()
        after = dict(before)
        assert gr._changed_file_count(before, after) == 0

    def test_added_removed_and_changed_paths_are_all_counted(self) -> None:
        """item C."""
        before = {"a.txt": "1", "b.txt": "2", "c.txt": "3"}
        after = {"a.txt": "1", "b.txt": "CHANGED", "d.txt": "new"}
        # b.txt changed, c.txt removed, d.txt added -- a.txt untouched.
        assert gr._changed_file_count(before, after) == 3

    def test_a_failed_attempt_with_no_files_touches_nothing(self) -> None:
        before = _candidate_files()
        assert gr._changed_file_count(before, None) == 0


class TestBudgetAccountingFixes:
    """Behavioral proof of the touched_files/elapsed_seconds fix found by
    the real golden-work-129-repair-1 benchmark run (BENCHMARK_SEMANTICS_GAP):
    the old code counted the whole returned file-set size and a constant
    elapsed_seconds=1 per attempt, exhausting the declared touched_files
    budget after ~3 attempts regardless of what a real attempt actually
    changed, and never reflecting real wall-clock cost."""

    def test_a_small_real_touch_count_does_not_pre_empt_a_later_entry(self) -> None:
        """item D: two entries in two DIFFERENT files, each attempt
        changing only that one file (~ real cost 1, not ~17) -- a budget
        that would have been exhausted by the old whole-mapping-size
        accounting after 3-4 attempts now comfortably covers both entries
        resolving on their own first real attempt. Deliberately different
        files (app.py vs requirements.txt): restoring one must not
        accidentally resolve the other, which would collapse this test's
        own proof that entry 2 still gets its own real attempt."""
        files = _candidate_files()
        entries = (_entry(gc.CONTRACT_VIOLATION), _entry(gc.DEPENDENCY_LOCK_MISMATCH))
        restore_path = {
            gc.CONTRACT_VIOLATION: "backend/app.py",
            gc.DEPENDENCY_LOCK_MISMATCH: "backend/requirements.txt",
        }
        broken = gi.apply_corpus(files, entries)

        def restore_relevant_file(entry: gc.RepairCorpusEntry, current: dict[str, str]):
            path = restore_path[entry.defect_class]
            fixed = {**current, path: files[path]}
            return fixed, _fingerprint(strategy=f"restore-{entry.defect_class}")

        # A tight budget that the OLD (whole-mapping-size) accounting could
        # never have satisfied for two entries (2 attempts x ~6 files each
        # already exceeds it), but the real per-attempt cost here is 1 file.
        tight_budget = _budget(touched_files=4, attempts=5)
        result = gr.run_corpus_repair(
            entries, broken, tight_budget, restore_relevant_file, candidate_id="test-candidate-touch-1",
        )
        assert set(result.resolved) == {e.id for e in entries}
        assert result.escalated == ()
        # 1 real changed file per entry, each entry's own independent ledger.
        assert result.ledgers[entries[0].id].consumption.touched_files == 1
        assert result.ledgers[entries[1].id].consumption.touched_files == 1

    def test_a_real_touch_count_that_genuinely_exceeds_the_ceiling_still_escalates(self) -> None:
        """item E: a real, correctly-measured touched_files count that
        genuinely crosses the declared ceiling must still terminate the
        entry via RepairBudgetExceededError -- the fix corrects what is
        counted, not whether the ceiling is enforced."""
        files = _candidate_files()
        entry = _entry(gc.CONTRACT_VIOLATION, repairable=False)
        broken = {**files, "backend/app.py": gi.INJECTORS[gc.CONTRACT_VIOLATION](files)["backend/app.py"]}
        attempt_index = 0

        def touches_many_files(entry: gc.RepairCorpusEntry, current: dict[str, str]):
            nonlocal attempt_index
            attempt_index += 1
            # A real, distinct 3-file change every attempt (still failing
            # to resolve the defect) -- genuinely touches 3 files/attempt.
            fixed = {
                **current,
                "backend/db.py": current["backend/db.py"] + f"\n# attempt {attempt_index}",
                "backend/data_model.json": current["backend/data_model.json"] + " ",
                "backend/requirements.txt": current["backend/requirements.txt"] + f"# {attempt_index}\n",
            }
            return fixed, _fingerprint(strategy=f"strategy-{attempt_index}")

        result = gr.run_corpus_repair(
            (entry,), broken, _budget(touched_files=7, attempts=10), touches_many_files,
            candidate_id="test-candidate-touch-2",
        )
        assert result.escalated == (entry.id,)
        # 2 attempts x 3 files = 6 (within 7); the 3rd attempt's own 3 more
        # would bring it to 9 > 7, so RepairBudgetExceededError fires there.
        assert attempt_index == 3
        assert result.ledgers[entry.id].consumption.touched_files == 6

    def test_elapsed_seconds_reflects_a_real_measured_delta_not_a_constant(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """item F/G: a controlled fake monotonic clock proves the recorded
        elapsed_seconds is a real ceil'd wall-clock delta, deterministically,
        with no real sleep involved."""
        ticks = iter([100.0, 104.6])  # a single attempt spanning 4.6s
        monkeypatch.setattr(gr.time, "monotonic", lambda: next(ticks))
        files = _candidate_files()
        entry = _entry(gc.CONTRACT_VIOLATION)
        broken = {**files, "backend/app.py": gi.INJECTORS[gc.CONTRACT_VIOLATION](files)["backend/app.py"]}

        def resolves(entry: gc.RepairCorpusEntry, current: dict[str, str]):
            fixed = {**current, "backend/app.py": files["backend/app.py"]}
            return fixed, _fingerprint(strategy="resolve")

        result = gr.run_corpus_repair(
            (entry,), broken, _budget(), resolves, candidate_id="test-candidate-elapsed-1",
        )
        assert result.ledgers[entry.id].consumption.elapsed_seconds == 5  # ceil(4.6) == 5, never the old constant 1

    def test_elapsed_seconds_accumulates_across_multiple_real_attempts(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """item H: cumulative semantics across several attempts -- each
        attempt's own real delta is added to the running total, matching
        touched_files'/ai_calls' own already-cumulative RepairConsumption
        field semantics (docs/contracts/repair.md's six-dimensional
        budget), never reset or overwritten between attempts. A tight
        attempts=3 ceiling forces a real 4th attempt whose own delta must
        NOT be added (its recording is refused before assignment)."""
        # 4 attempts: deltas of 2.4s, 3.1s, 4.0s (all recorded), then a 4th
        # (1.0s) whose recording itself is refused by the attempts ceiling.
        ticks = iter([0.0, 2.4, 10.0, 13.1, 20.0, 24.0, 30.0, 31.0])
        monkeypatch.setattr(gr.time, "monotonic", lambda: next(ticks))
        files = _candidate_files()
        entry = _entry(gc.CONTRACT_VIOLATION, repairable=False)
        broken = {**files, "backend/app.py": gi.INJECTORS[gc.CONTRACT_VIOLATION](files)["backend/app.py"]}
        attempt_index = 0

        def never_fixes(entry: gc.RepairCorpusEntry, current: dict[str, str]):
            nonlocal attempt_index
            attempt_index += 1
            return None, _fingerprint(strategy=f"strategy-{attempt_index}")

        result = gr.run_corpus_repair(
            (entry,), broken, _budget(attempts=3), never_fixes,
            candidate_id="test-candidate-elapsed-2",
        )
        assert attempt_index == 4
        assert result.escalated == (entry.id,)
        # ceil(2.4)=3, ceil(3.1)=4, ceil(4.0)=4 -> cumulative 11; the 4th
        # attempt's own ceil(1.0)=1 is never added (its record() call was
        # refused by the attempts ceiling before assignment).
        assert result.ledgers[entry.id].consumption.elapsed_seconds == 11


# ---------------------------------------------------------------------------
# Surgical per-class undo patches for the REAL corpus's own 5 defects that
# share backend/app.py (contract_violation, state_machine_invalid_transition,
# permission_check_removal, persistence_not_committed, boundary_off_by_one) --
# a targeted string replace per class, never a full-file restore, so fixing
# one class's own defect can never silently resolve a sibling class still
# present in the same file (the exact collapse F-0057's own audit warned
# about). Safe specifically because each targets a disjoint substring of the
# fixture's own known content (verified by inspection, not assumed).
# ---------------------------------------------------------------------------

_SURGICAL_APP_PY_FIX: dict[str, Callable[[str], str]] = {
    gc.BOUNDARY_OFF_BY_ONE: lambda src: src.replace("<id>", "<int:id>"),
    gc.CONTRACT_VIOLATION: lambda src: src.replace(
        "jsonify({'id': new_id, 'name': data['name']})",
        "jsonify({'id': new_id, 'name': data['name'], 'extra': data['extra']})",
    ),
    gc.PERSISTENCE_NOT_COMMITTED: lambda src: src.replace(
        "    new_id = cursor.lastrowid",
        "    conn.commit()\n    new_id = cursor.lastrowid",
    ),
    gc.STATE_MACHINE_INVALID_TRANSITION: lambda src: src.replace(
        "(data['name'], data['extra'], id),\n    )\n    conn.commit()",
        "(data['name'], data['extra'], id),\n    )\n    if cursor.rowcount == 0:\n"
        "        return jsonify({'error': 'not found'}), 404\n    conn.commit()",
    ),
}
_SIMPLE_RESTORE_TARGET = {
    gc.API_FRONTEND_CONTRACT_DRIFT: "backend/routes.json",
    gc.DEPENDENCY_LOCK_MISMATCH: "backend/requirements.txt",
    gc.MIGRATION_MODEL_MISMATCH: "backend/db.py",
}


class TestRealCorpusFeasibilityWithPerEntryLedgers:
    """F-0057: the real committed corpus (golden/repair/golden_repair_corpus.
    json) run through the real golden-repair-standard-v1 numeric profile
    against the real run_corpus_repair -- the exact combination the F-0057
    audit proved mathematically infeasible under the old shared-ledger scope
    (at most 6 of 8 entries could ever record even one successful attempt),
    and proves feasible here under the fixed per-entry scope. The model call
    is a deterministic fake callback; no real Ollama is used."""

    def test_the_real_8_entry_corpus_is_processable_under_the_real_profile(self) -> None:
        entries = gc.load_corpus_instance(CORPUS_INSTANCE_PATH)
        pristine = _candidate_files()
        broken = gi.apply_corpus(pristine, entries)
        attempt_log: dict[str, list[str]] = {e.id: [] for e in entries}

        def attempt_repair(entry: gc.RepairCorpusEntry, current: dict[str, str]):
            attempt_log[entry.id].append(entry.defect_class)
            if entry.defect_class == gc.PERMISSION_CHECK_REMOVAL:
                # item C/L: the real declared-unrepairable entry -- never
                # resolves, the identical strategy every time -> a genuine
                # anti-loop ESCALATED on its own 2nd attempt.
                return None, _fingerprint(strategy="never-converges")
            if entry.defect_class == gc.API_FRONTEND_CONTRACT_DRIFT:
                # item D/F: deliberately exhausts its OWN full budget (never
                # resolves, a distinct strategy every attempt) -- proves
                # later entries are unaffected by this entry's own ceiling.
                return None, _fingerprint(strategy=f"drift-attempt-{len(attempt_log[entry.id])}")
            if entry.defect_class in _SURGICAL_APP_PY_FIX:
                fixed_app_py = _SURGICAL_APP_PY_FIX[entry.defect_class](current["backend/app.py"])
                fixed = {**current, "backend/app.py": fixed_app_py}
            else:
                path = _SIMPLE_RESTORE_TARGET[entry.defect_class]
                fixed = {**current, path: pristine[path]}
            return fixed, _fingerprint(strategy=f"restore-{entry.defect_class}")

        # The real declared numeric profile -- not loosened for this test.
        real_profile_budget = _budget(
            attempts=6, ai_calls=6, elapsed_seconds=3600, touched_files=64, regression_delta=0,
        )
        result = gr.run_corpus_repair(
            entries, broken, real_profile_budget, attempt_repair,
            candidate_id="test-real-corpus-feasibility",
        )

        # A: 8/8 entries each own a real, independent ledger.
        assert set(result.ledgers) == {e.id for e in entries}
        assert len(entries) == 8

        # E: the whole corpus is processed -- every entry reaches a real
        # verdict, none silently skipped, under the REAL 6/6 profile.
        assert set(result.resolved) | set(result.escalated) == {e.id for e in entries}

        # B: every one of the 7 repairable entries gets at least one real
        # attempt -- opportunity, not a guarantee of resolution (one of
        # them, drift_id below, is deliberately made to exhaust its own
        # budget instead, to prove F/D directly).
        repairable_ids = {e.id for e in entries if e.repairable}
        assert len(repairable_ids) == 7
        for entry_id in repairable_ids:
            assert len(attempt_log[entry_id]) >= 1

        # C/L: the real declared-unrepairable entry reached genuine
        # anti-loop ESCALATED in exactly 2 real calls -- never force-resolved,
        # never pre-empted by any other entry's own consumption.
        unrepairable = next(e for e in entries if not e.repairable)
        assert unrepairable.defect_class == gc.PERMISSION_CHECK_REMOVAL
        assert unrepairable.id in result.escalated
        assert len(attempt_log[unrepairable.id]) == 2

        # F: the entry deliberately made to exhaust its OWN ceiling
        # (repairable: true, but never resolved here) escalated via its own
        # budget alone (6 recorded, a 7th real attempt that exceeded the
        # ceiling) -- independent of the unrepairable entry's own separate
        # escalation, proving a real repairable entry can still genuinely
        # escalate on its own real, isolated consumption.
        drift_id = next(e.id for e in entries if e.defect_class == gc.API_FRONTEND_CONTRACT_DRIFT)
        assert drift_id in result.escalated
        assert len(attempt_log[drift_id]) == 7
        assert result.ledgers[drift_id].consumption.attempts == 6

        # D: every OTHER repairable entry -- several processed AFTER the
        # budget-exhausted entry -- genuinely resolved with its own single,
        # minimal attempt, proving the exhausted entry's full consumption
        # never reduced any later entry's own independent budget.
        resolved_repairable_ids = repairable_ids - {drift_id}
        assert set(result.resolved) == resolved_repairable_ids
        for entry in entries:
            if entry.id in resolved_repairable_ids:
                assert len(attempt_log[entry.id]) == 1
                assert result.ledgers[entry.id].consumption.attempts == 1

        # G: fingerprints never cross entries -- each entry's own ledger
        # carries only fingerprints this exact entry's own attempts produced.
        _own_strategy_prefix = {
            unrepairable.id: "never-converges",
            drift_id: "drift-attempt-",
        }
        for entry in entries:
            expected = _own_strategy_prefix.get(entry.id, f"restore-{entry.defect_class}")
            for fp in result.ledgers[entry.id].fingerprints:
                assert fp.strategy.startswith(expected)

        # H: touched_files/elapsed consumption never crosses entries -- the
        # exhausted entry's own high real cost is confined to its own
        # ledger; every quick-resolving entry's own ledger reflects only
        # its own tiny, independent, real cost.
        for entry in entries:
            if entry.id in resolved_repairable_ids:
                assert result.ledgers[entry.id].consumption.touched_files >= 1
                assert result.ledgers[entry.id].consumption.touched_files < 10


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


# F-0059: real production code now calls `inspect_gate(files, baseline=...)`
# -- a fake gate must accept the same real keyword, never just `files`.
_PASSING_GATE = lambda files, baseline=None: SimpleNamespace(passed=True, findings=())  # noqa: E731

# F-0059: `run_isolated_golden_repair` now requires a real `measure_regression`
# callable (the same DI seam `inspect_gate` already uses) -- this fixture
# default is an explicit, honest "no regression measured for this test", never
# a stand-in for the real dynamic pytest-based measurement `_measure_regression`
# (exercised directly and end-to-end by TestRegressionMeasurement below).
_NO_REGRESSION = lambda parent_files, child_files: (0, "measured")  # noqa: E731


def _run_repair(
    ledger: CandidateLedger, candidates_root: pathlib.Path, *, parent_id: str, child_id: str,
    attempt_repair=None, inspect_gate=_PASSING_GATE, budget: RepairBudget | None = None,
    entries: tuple[gc.RepairCorpusEntry, ...] | None = None,
    measure_regression=_NO_REGRESSION,
) -> rgr.GoldenRepairOutcome:
    if attempt_repair is None:
        def attempt_repair(entry: gc.RepairCorpusEntry, current: dict[str, str]):
            fixed = {**current, "backend/app.py": _candidate_files()["backend/app.py"]}
            return fixed, _fingerprint(strategy=f"restore-{entry.defect_class}")
    request = rgr.GoldenRepairRequest(
        parent_id=parent_id, child_id=child_id,
        entries=entries or (_entry(gc.CONTRACT_VIOLATION),),
        budget=budget or _budget(),
        attempt_repair=attempt_repair,
        provenance=_provenance(),
    )
    return rgr.run_isolated_golden_repair(
        ledger, candidates_root, request,
        inspect_gate=inspect_gate, measure_regression=measure_regression,
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


# ---------------------------------------------------------------------------
# F-0058/59/60/61 -- OPEN_BLOCKERS.md. `run_isolated_golden_repair`'s real
# promotion predicate, the real dynamic regression signal, the real
# structurally-relevant prompt context, and real per-target fingerprint
# evidence, each proven against the real production code in scripts/
# run_golden_repair.py -- never a re-derivation of it in test-only logic.
#
# Three independent-file defect classes are used throughout so a multi-entry
# scenario's own fake attempt_repair can resolve/fail one entry without ever
# touching another entry's own file (contract_violation -> backend/app.py,
# dependency_lock_mismatch -> backend/requirements.txt, migration_model_
# mismatch -> backend/db.py -- confirmed against golden_corpus_injectors.py's
# own real injector targets, not assumed).
# ---------------------------------------------------------------------------

_MATRIX_RESTORE_PATH = {
    gc.CONTRACT_VIOLATION: "backend/app.py",
    gc.DEPENDENCY_LOCK_MISMATCH: "backend/requirements.txt",
    gc.MIGRATION_MODEL_MISMATCH: "backend/db.py",
}


def _matrix_attempt_repair(resolve: frozenset[str]):
    """Resolves every entry whose defect_class is in `resolve` by restoring
    the exact real file that class's own injector targets (never a whole-
    candidate restore, so resolving one entry can never accidentally also
    fix another entry's own independent defect). Every other entry gets the
    identical fixed fingerprint strategy on every call -- the same real
    anti-loop mechanism TestRunCorpusRepairConvergence's own `never_fixes`
    already relies on -- so it reaches ESCALATED automatically, never via an
    operator-supplied flag."""

    def attempt_repair(entry: gc.RepairCorpusEntry, current: dict[str, str]):
        if entry.defect_class in resolve:
            path = _MATRIX_RESTORE_PATH[entry.defect_class]
            fixed = {**current, path: _candidate_files()[path]}
            return fixed, _fingerprint(strategy=f"restore-{entry.defect_class}")
        return None, _fingerprint(strategy=f"always-fails-{entry.defect_class}")

    return attempt_repair


def _matrix_entries(*specs: tuple[str, bool]) -> tuple[gc.RepairCorpusEntry, ...]:
    """`(defect_class, repairable)` pairs -> real corpus entries."""
    return tuple(_entry(cls, repairable=repairable) for cls, repairable in specs)


class TestPromotionMatrix:
    """F-0058: `GOLDEN_REPAIR_PASS` now means every repairable entry
    RESOLVED, every declared-unrepairable entry ESCALATED, no protected-path
    violation, zero measured regression, and the structural gate PASS --
    ALL of them, not just `not violations and gate_passed`. Any single
    failure routes to the existing `FINAL_GATE_FAILED` state."""

    def test_a_all_canonical_conditions_true_promotes(self, tmp_path: pathlib.Path) -> None:
        """item A: every repairable entry resolved, the unrepairable entry
        escalated, no violations, zero regression, gate PASS -> PASS."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")
        entries = _matrix_entries(
            (gc.CONTRACT_VIOLATION, True), (gc.DEPENDENCY_LOCK_MISMATCH, False),
        )
        outcome = _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
            entries=entries, attempt_repair=_matrix_attempt_repair(frozenset({gc.CONTRACT_VIOLATION})),
        )
        assert outcome.repair_result.resolved == (entries[0].id,)
        assert outcome.repair_result.escalated == (entries[1].id,)
        assert outcome.all_repairable_resolved is True
        assert outcome.unrepairable_escalated is True
        assert outcome.regression_count == 0
        assert outcome.state == GOLDEN_REPAIR_PASS
        assert ledger.classify("golden-work-child") == GOLDEN_REPAIR_PASS

    def test_b_partial_resolution_of_repairable_entries_fails(self, tmp_path: pathlib.Path) -> None:
        """item B: a generic proxy for golden-work-129-repair-2's own real
        "6/7 resolved" shape -- not every repairable entry reached RESOLVED
        -> FINAL_GATE_FAILED, never GOLDEN_REPAIR_PASS."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")
        entries = _matrix_entries(
            (gc.CONTRACT_VIOLATION, True), (gc.DEPENDENCY_LOCK_MISMATCH, False),
        )
        # Only the unrepairable entry's own target is "fixed" here -- the
        # repairable entry never resolves.
        outcome = _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
            entries=entries, attempt_repair=_matrix_attempt_repair(frozenset()),
        )
        assert outcome.all_repairable_resolved is False
        assert outcome.state == FINAL_GATE_FAILED
        assert ledger.classify("golden-work-child") == FINAL_GATE_FAILED

    def test_c_a_repairable_entry_reaching_escalated_fails(self, tmp_path: pathlib.Path) -> None:
        """item C: a repairable entry that itself reaches ESCALATED (rather
        than RESOLVED) must fail promotion, even though every OTHER
        predicate -- gate, regression, protected paths -- genuinely holds."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")
        entries = _matrix_entries((gc.CONTRACT_VIOLATION, True), (gc.MIGRATION_MODEL_MISMATCH, True))
        outcome = _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
            entries=entries, attempt_repair=_matrix_attempt_repair(frozenset({gc.CONTRACT_VIOLATION})),
        )
        assert entries[1].id in outcome.repair_result.escalated
        assert outcome.all_repairable_resolved is False
        assert outcome.state == FINAL_GATE_FAILED

    def test_d_an_unrepairable_entry_that_resolves_instead_of_escalating_fails(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """item D: a declared-unrepairable entry that the loop actually
        resolves (never ESCALATED at all) must still fail promotion -- the
        canonical predicate requires the DECLARED-unrepairable entry to be
        the one that is ESCALATED, not merely "something got resolved"."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")
        entries = _matrix_entries(
            (gc.CONTRACT_VIOLATION, True), (gc.DEPENDENCY_LOCK_MISMATCH, False),
        )
        # Both entries resolve this time -- including the declared-unrepairable one.
        outcome = _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
            entries=entries,
            attempt_repair=_matrix_attempt_repair(
                frozenset({gc.CONTRACT_VIOLATION, gc.DEPENDENCY_LOCK_MISMATCH})
            ),
        )
        assert entries[1].id in outcome.repair_result.resolved
        assert outcome.unrepairable_escalated is False
        assert outcome.state == FINAL_GATE_FAILED

    def test_e_a_measured_regression_fails_promotion(self, tmp_path: pathlib.Path) -> None:
        """item E: every other predicate genuinely holds; only the real
        dynamic regression measurement reports a non-zero delta -> FAIL."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")
        entries = _matrix_entries((gc.CONTRACT_VIOLATION, True),)
        outcome = _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
            entries=entries, attempt_repair=_matrix_attempt_repair(frozenset({gc.CONTRACT_VIOLATION})),
            measure_regression=lambda parent_files, child_files: (1, "measured"),
        )
        assert outcome.regression_count == 1
        assert outcome.regression_status == "measured"
        assert outcome.state == FINAL_GATE_FAILED

    def test_e2_an_unmeasurable_regression_fails_promotion(self, tmp_path: pathlib.Path) -> None:
        """F-0059-ENV item D: environment preparation failing to complete
        (e.g. a real venv/pip-install failure) must produce `status=
        "unavailable"`, never a value a caller could mistake for a real
        `0` -- and, critically, `run_isolated_golden_repair` must refuse
        promotion on it, exactly as it refuses a genuine positive delta,
        even though every OTHER predicate genuinely holds."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")
        entries = _matrix_entries((gc.CONTRACT_VIOLATION, True),)
        outcome = _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
            entries=entries, attempt_repair=_matrix_attempt_repair(frozenset({gc.CONTRACT_VIOLATION})),
            measure_regression=lambda parent_files, child_files: (None, "unavailable"),
        )
        assert outcome.regression_count is None
        assert outcome.regression_status == "unavailable"
        assert outcome.state == FINAL_GATE_FAILED
        with pytest.raises(CandidateIntegrityError):
            ledger.begin_acceptance("golden-work-child", outcome.workspace_root)

    def test_f_a_protected_test_mutation_fails_promotion(self, tmp_path: pathlib.Path) -> None:
        """item F: re-stated here (alongside TestNoTestWeakening above) as
        part of the one canonical promotion-matrix suite -- no-test-weakening
        remains a real, independent predicate under the new F-0058 logic."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")

        def weakens_tests(entry: gc.RepairCorpusEntry, current: dict[str, str]):
            fixed = {
                **current,
                "backend/app.py": _candidate_files()["backend/app.py"],
                "tests/test_app.py": "# weakened\n",
            }
            return fixed, _fingerprint(strategy="weaken-tests")

        outcome = _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
            attempt_repair=weakens_tests,
        )
        assert outcome.all_repairable_resolved is True
        assert outcome.state == FINAL_GATE_FAILED

    def test_g_a_structural_gate_failure_fails_promotion(self, tmp_path: pathlib.Path) -> None:
        """item G: every OTHER predicate genuinely holds; only the whole-
        product structural gate itself reports a real finding -> FAIL."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")
        failing_gate = lambda files, baseline=None: SimpleNamespace(  # noqa: E731
            passed=False,
            findings=(SimpleNamespace(code="STRUCT", path="backend/app.py", detail="synthetic finding"),),
        )
        outcome = _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
            inspect_gate=failing_gate,
        )
        assert outcome.all_repairable_resolved is True
        assert outcome.gate_passed is False
        assert outcome.state == FINAL_GATE_FAILED

    def test_h_full_pass_preserves_acceptance_eligibility(self, tmp_path: pathlib.Path) -> None:
        """item H: the normal fully-passing path still promotes AND the
        resulting GOLDEN_REPAIR_PASS child remains begin_acceptance-eligible
        (item 11's own real gate, unmodified)."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")
        entries = _matrix_entries(
            (gc.CONTRACT_VIOLATION, True), (gc.DEPENDENCY_LOCK_MISMATCH, False),
        )
        outcome = _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
            entries=entries, attempt_repair=_matrix_attempt_repair(frozenset({gc.CONTRACT_VIOLATION})),
        )
        assert outcome.state == GOLDEN_REPAIR_PASS
        ledger.begin_acceptance("golden-work-child", outcome.workspace_root)  # must not raise
        assert ledger.classify("golden-work-child") == ACCEPTANCE_RUNNING

    def test_a_child_that_must_not_get_golden_repair_pass_is_not_begin_acceptance_eligible(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """The negative half of item E/H: a child correctly refused
        promotion must never be begin_acceptance-eligible either."""
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")
        entries = _matrix_entries((gc.CONTRACT_VIOLATION, True),)
        outcome = _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
            entries=entries, attempt_repair=_matrix_attempt_repair(frozenset({gc.CONTRACT_VIOLATION})),
            measure_regression=lambda parent_files, child_files: (1, "measured"),
        )
        assert outcome.state == FINAL_GATE_FAILED
        with pytest.raises(CandidateIntegrityError):
            ledger.begin_acceptance("golden-work-child", outcome.workspace_root)

    def test_the_normal_staged_generation_promotion_predicate_is_unaffected(self) -> None:
        """CandidateLedger's own staged-generation logic is a completely
        separate authority from this run_isolated_golden_repair-local
        promotion predicate -- proven by the fact this predicate lives
        entirely in scripts/run_golden_repair.py, never inside
        CandidateLedger itself (grep confirms no F-0058 changes touched
        ledger.py)."""
        import inspect
        from arkali.engineering.candidate import ledger as ledger_module
        source = inspect.getsource(ledger_module)
        assert "all_repairable_resolved" not in source
        assert "regression_count" not in source


class TestF0058RegressionTest:
    """F-0058's own direct regression test (item 16): a GENERIC proxy for
    golden-work-129-repair-2's real shape (2 of 7 corpus entries resolved,
    the other 5 escalated, all 6 repairable entries present, structural gate
    PASS, no protected-path violation) -- never hardcoding repair-2's own
    exact fixture data, but reproducing the same structural shape: SOME
    repairable entries resolved, SOME repairable entries escalated,
    structural gate PASS -> must NOT promote to GOLDEN_REPAIR_PASS."""

    def test_some_repairable_resolved_some_repairable_escalated_never_promotes(
        self, tmp_path: pathlib.Path,
    ) -> None:
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")
        entries = _matrix_entries(
            (gc.CONTRACT_VIOLATION, True),
            (gc.DEPENDENCY_LOCK_MISMATCH, True),
            (gc.MIGRATION_MODEL_MISMATCH, True),
        )
        outcome = _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
            entries=entries, attempt_repair=_matrix_attempt_repair(frozenset({gc.CONTRACT_VIOLATION})),
        )
        assert outcome.repair_result.resolved == (entries[0].id,)
        assert set(outcome.repair_result.escalated) == {entries[1].id, entries[2].id}
        # No unrepairable entry exists in this scenario at all -- so
        # `unrepairable_escalated` is vacuously true, isolating exactly
        # F-0058's own real bug: the OLD code (`not violations and
        # gate_passed`) would have wrongly granted GOLDEN_REPAIR_PASS here,
        # exactly as it did for the real golden-work-129-repair-2 run.
        assert outcome.unrepairable_escalated is True
        assert outcome.all_repairable_resolved is False
        assert outcome.state == FINAL_GATE_FAILED
        assert ledger.classify("golden-work-child") == FINAL_GATE_FAILED


class TestStaticRegressionBaselineWiring:
    """F-0059 (static half): `run_isolated_golden_repair` must pass a real
    baseline into `inspect_gate` -- the missing `baseline=` keyword argument
    that made `inspect_product_files`'s own `_regression_findings` check
    permanently vacuous (`for path, original in (baseline or {}).items():`
    iterates zero times when `baseline` defaults to `None`)."""

    def test_a_real_parent_baseline_reaches_inspect_gate(self, tmp_path: pathlib.Path) -> None:
        ledger = CandidateLedger(tmp_path / "_ledger")
        candidates_root = tmp_path / "candidates"
        _accept_parent(ledger, candidates_root, "golden-work-parent")
        captured: dict[str, object] = {}

        def spy_inspect(files, *, baseline=None):
            captured["baseline"] = baseline
            return SimpleNamespace(passed=True, findings=())

        _run_repair(
            ledger, candidates_root, parent_id="golden-work-parent", child_id="golden-work-child",
            inspect_gate=spy_inspect,
        )
        assert captured["baseline"] == _candidate_files()
        assert captured["baseline"] is not None


#: A minimal, fast-installing real candidate for the real-environment
#: regression tests below -- deliberately NOT `_candidate_files()` (which
#: needs flask/flask_cors/Werkzeug, slow to install and irrelevant to what
#: these tests prove). Only `pytest` itself is declared, so a real `pip
#: install -r backend/requirements.txt` stays fast.
_REAL_ENV_APP_PY = "def add(a, b):\n    return a + b\n"
_REAL_ENV_TESTS_PY = "from backend.app import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
_REAL_ENV_REQUIREMENTS = "pytest==7.4.0\n"


def _real_env_files(**overrides: str) -> dict[str, str]:
    files = {
        "backend/app.py": _REAL_ENV_APP_PY,
        "backend/requirements.txt": _REAL_ENV_REQUIREMENTS,
        "tests/test_app.py": _REAL_ENV_TESTS_PY,
    }
    files.update(overrides)
    return files


class TestParentTestSuiteIdentity:
    """F-0059-ENV item 5/6: the child's own `tests/` must never become the
    oracle -- only the parent's own real accepted `tests/` bytes are ever
    the baseline suite, for both the baseline run and the child run."""

    def test_child_non_test_files_are_kept_as_the_childs_own(self) -> None:
        parent = _real_env_files()
        child = _real_env_files(**{"backend/app.py": "def add(a, b):\n    return a - b\n"})
        merged = rgr._with_parent_test_suite(child, parent)
        assert merged["backend/app.py"] == child["backend/app.py"]

    def test_child_test_files_are_forced_back_to_the_parents_own_bytes(self) -> None:
        parent = _real_env_files()
        child = _real_env_files(**{"tests/test_app.py": "def test_add():\n    assert True\n"})
        merged = rgr._with_parent_test_suite(child, parent)
        assert merged["tests/test_app.py"] == parent["tests/test_app.py"]
        assert merged["tests/test_app.py"] != child["tests/test_app.py"]

    def test_a_new_test_file_the_child_planted_never_enters_the_merged_suite(self) -> None:
        parent = _real_env_files()
        child = _real_env_files(**{"tests/test_planted.py": "def test_always_passes():\n    assert True\n"})
        merged = rgr._with_parent_test_suite(child, parent)
        assert "tests/test_planted.py" not in merged


class TestRegressionMeasurementNoLifecycleSideEffect:
    """F-0059-ENV item F: the real-environment regression mechanism must
    never touch CandidateLedger, WorkspaceAuthority or ArtifactStore --
    a bare subprocess sequence only, proven structurally rather than by
    trying to catch a side effect at runtime."""

    def test_the_real_environment_functions_never_reference_the_ledger_or_workspace(self) -> None:
        import inspect
        source = "".join(
            inspect.getsource(fn) for fn in (
                rgr._prepare_real_environment, rgr._run_pytest_probe_real_env,
                rgr._pytest_failure_and_error_count_real_env, rgr._measure_regression,
            )
        )
        for forbidden in ("CandidateLedger", "WorkspaceAuthority", "ArtifactStore", "begin_acceptance", "ACCEPTANCE_RUNNING"):
            assert forbidden not in source, f"{forbidden!r} must never appear in the regression-measurement path"


class TestExistingAcceptanceBehaviorUnchanged:
    """F-0059-ENV item G/7: reuse, never modify. `run_golden_acceptance.py`
    itself is untouched by this session (its own `_accept`/`main` own
    real lifecycle -- begin_acceptance, ACCEPTANCE_RUNNING, the browser
    journey -- are never invoked here); only its already-private, already
    lifecycle-free `_run` subprocess helper is reused."""

    def test_the_loader_reuses_the_real_run_golden_acceptance_module(self) -> None:
        acceptance = rgr._load_run_golden_acceptance()
        assert callable(acceptance._run)
        assert callable(acceptance._accept)
        assert callable(acceptance.main)

    def test_the_regression_path_never_calls_accept_or_main(self) -> None:
        import inspect
        source = "".join(
            inspect.getsource(fn) for fn in (
                rgr._prepare_real_environment, rgr._run_pytest_probe_real_env,
            )
        )
        assert "_accept(" not in source
        assert ".main(" not in source


class TestRegressionMeasurement:
    """F-0059-ENV (real-environment fix): the real, dynamic pre-existing-
    test-suite comparison `_measure_regression` performs, now executed in
    a real venv with the candidate's own real dependencies installed --
    reusing `run_golden_acceptance.py`'s own real venv/pip-install/pytest
    sequence, never ARKALI's own interpreter (which this repository's own
    real inference-feasibility preflight found lacks `flask`, making the
    OLD interpreter-based probe unable to produce a usable zero-regression
    fact for a Flask-based candidate family at all)."""

    def test_a_identical_parent_and_child_genuinely_pass_in_a_real_environment(self) -> None:
        """items A+B: the parent's own real accepted suite genuinely runs,
        genuinely passes, in a real prepared environment, and an unchanged
        child measures a real, non-synthetic zero."""
        files = _real_env_files()
        delta, status = rgr._measure_regression(files, files)
        assert status == "measured"
        assert delta == 0

    def test_c_a_child_that_really_breaks_the_parents_own_test_is_a_real_measured_regression(self) -> None:
        """item C: the child's own product code is genuinely broken; the
        PARENT's own unchanged test (never the child's) genuinely fails
        against it in a real environment."""
        parent = _real_env_files()
        broken_child = _real_env_files(**{"backend/app.py": "def add(a, b):\n    return a - b\n"})
        delta, status = rgr._measure_regression(parent, broken_child)
        assert status == "measured"
        assert delta == 1

    def test_d_environment_preparation_failure_is_reported_unavailable_never_zero(self, monkeypatch) -> None:
        """item D: environment preparation itself failing to complete must
        propagate `"unavailable"`, never a synthetic zero a caller could
        mistake for a real clean measurement."""
        monkeypatch.setattr(rgr, "_prepare_real_environment", lambda scratch, *, timeout_seconds: None)
        files = _real_env_files()
        delta, status = rgr._measure_regression(files, files)
        assert delta is None
        assert status == "unavailable"


class TestContextSelection:
    """F-0060: only the real, structurally-relevant file(s) for a defect's
    own declared `injection_target` enter the repair prompt -- never the
    whole candidate, and derived purely from the corpus's own generic
    `injection_target` vocabulary, never a domain-specific file name."""

    def test_a_single_file_defect_gets_only_its_own_file(self) -> None:
        files = _candidate_files()
        entry = _entry(gc.CONTRACT_VIOLATION, injection_target="source_module")
        context = rgr._context_files(entry, files)
        assert set(context) == {"backend/app.py"}

    def test_a_cross_file_defect_gets_both_sides_of_the_contract(self) -> None:
        files = _candidate_files()
        entry = _entry(gc.API_FRONTEND_CONTRACT_DRIFT, injection_target="route_contract")
        context = rgr._context_files(entry, files)
        assert set(context) == {"backend/app.py", "backend/routes.json"}

    def test_a_migration_defect_gets_both_real_schema_files(self) -> None:
        files = _candidate_files()
        entry = _entry(gc.MIGRATION_MODEL_MISMATCH, injection_target="migration")
        context = rgr._context_files(entry, files)
        assert set(context) == {"backend/db.py", "backend/data_model.json"}

    def test_unrelated_files_never_enter_the_context(self) -> None:
        files = _candidate_files()
        entry = _entry(gc.DEPENDENCY_LOCK_MISMATCH, injection_target="lockfile")
        context = rgr._context_files(entry, files)
        assert set(context) == {"backend/requirements.txt"}
        assert "backend/app.py" not in context
        assert "tests/test_app.py" not in context

    def test_an_unrecognised_injection_target_falls_back_to_the_whole_candidate(self) -> None:
        """Never silently sends nothing for a target this run's own static
        mapping does not recognise."""
        files = _candidate_files()
        entry = _entry(gc.BOUNDARY_OFF_BY_ONE, injection_target="a_future_target_category")
        context = rgr._context_files(entry, files)
        assert context == dict(files)


class _FakeOllamaAdapter:
    """A real DI seam replacement for `rgr.OllamaAdapter` -- never a live
    network call. Captures exactly what production code passed it, and
    returns a scripted, honest `InferenceResult`-shaped response."""

    last_constructed: dict[str, object] | None = None

    def __init__(self, *, json_mode: bool, max_output_tokens: int) -> None:
        self._max_output_tokens = max_output_tokens
        type(self).last_constructed = {"json_mode": json_mode, "max_output_tokens": max_output_tokens}

    def infer(self, model: str, prompt: str, *, timeout_seconds: float):
        type(self).last_infer = {"model": model, "prompt": prompt, "timeout_seconds": timeout_seconds}
        return SimpleNamespace(
            state=SimpleNamespace(value=self._state_value),
            output=self._output,
            detail=self._detail,
        )


def _fake_adapter_class(state_value: str, output: str = "", detail: str = "synthetic"):
    return type(
        "_ScriptedFakeOllamaAdapter", (_FakeOllamaAdapter,),
        {"_state_value": state_value, "_output": output, "_detail": detail},
    )


class TestOllamaContextWiring:
    """F-0060: `resolve_output_budget`/`DEFAULT_NUM_CTX` must really reach
    the `OllamaAdapter` construction this run's own attempt makes -- proven
    by intercepting the real DI seam `rgr.OllamaAdapter`, never by re-
    deriving the arithmetic in test-only code."""

    def test_the_real_safe_output_budget_reaches_the_adapter_constructor(
        self, monkeypatch,
    ) -> None:
        fake_cls = _fake_adapter_class(
            "PASS", json.dumps({"files": {"backend/app.py": _candidate_files()["backend/app.py"]}}),
        )
        monkeypatch.setattr(rgr, "OllamaAdapter", fake_cls)
        attempt_repair = rgr._make_attempt_repair("qwen2.5-coder:14b", 8192, 30.0)
        entry = _entry(gc.CONTRACT_VIOLATION, injection_target="source_module")
        files = _candidate_files()

        changed, fingerprint = attempt_repair(entry, files)

        constructed = fake_cls.last_constructed
        assert constructed is not None
        assert constructed["json_mode"] is True
        # The exact real invariant F-0060 requires: never a fixed
        # max_output_tokens that could silently exceed num_ctx once the
        # real estimated input is accounted for.
        expected_prompt = fake_cls.last_infer["prompt"]
        expected_budget = rgr.resolve_output_budget(
            expected_prompt, num_ctx=rgr.DEFAULT_NUM_CTX, desired_output_tokens=8192,
        )
        assert constructed["max_output_tokens"] == expected_budget
        assert constructed["max_output_tokens"] <= rgr.DEFAULT_NUM_CTX
        assert fake_cls.last_infer["model"] == "qwen2.5-coder:14b"
        assert changed is not None

    def test_an_infeasible_prompt_is_refused_before_any_network_call(self, monkeypatch) -> None:
        """F-0060's own safety half: `resolve_output_budget` raises rather
        than silently constructing an adapter with a doomed request. A tiny
        `DEFAULT_NUM_CTX` makes ANY real prompt infeasible, regardless of
        its own size -- proving the refusal is the real arithmetic, not a
        coincidence of this fixture's particular prompt length."""
        called = []
        monkeypatch.setattr(
            rgr, "OllamaAdapter",
            lambda **kwargs: called.append(kwargs) or _fake_adapter_class("PASS")(**kwargs),
        )
        monkeypatch.setattr(rgr, "DEFAULT_NUM_CTX", 10)
        attempt_repair = rgr._make_attempt_repair("qwen2.5-coder:14b", 8192, 30.0)
        entry = _entry(gc.CONTRACT_VIOLATION, injection_target="source_module")
        with pytest.raises(ValueError):
            attempt_repair(entry, _candidate_files())
        assert called == []


class TestFingerprintTargetAccuracy:
    """F-0061: root-cause and fingerprint evidence must be grounded in the
    entry's own real resolved context, never a hardcoded `backend/app.py`
    for every defect class."""

    def test_two_different_defect_targets_get_different_fingerprint_files(self, monkeypatch) -> None:
        files = _candidate_files()
        monkeypatch.setattr(
            rgr, "OllamaAdapter",
            _fake_adapter_class("PASS", json.dumps({"files": {"backend/app.py": files["backend/app.py"]}})),
        )
        attempt_repair = rgr._make_attempt_repair("fake-model", 8192, 30.0)
        source_entry = _entry(gc.CONTRACT_VIOLATION, injection_target="source_module")
        _, source_fp = attempt_repair(source_entry, files)
        assert source_fp.files == ("backend/app.py",)

        monkeypatch.setattr(
            rgr, "OllamaAdapter",
            _fake_adapter_class(
                "PASS", json.dumps({"files": {"backend/requirements.txt": files["backend/requirements.txt"]}}),
            ),
        )
        lockfile_entry = _entry(gc.DEPENDENCY_LOCK_MISMATCH, injection_target="lockfile")
        _, lockfile_fp = attempt_repair(lockfile_entry, files)
        assert lockfile_fp.files == ("backend/requirements.txt",)
        assert lockfile_fp.files != source_fp.files
        # F-0061: the Python-AST analyzer is never mis-applied to a
        # non-Python/non-entrypoint target -- the existing generic fallback
        # vocabulary is used instead, never an invented class.
        assert lockfile_fp.root_cause_class == "unclassified_runtime_failure"

    def test_a_rejected_attempt_still_points_at_the_correct_target(self, monkeypatch) -> None:
        files = _candidate_files()
        monkeypatch.setattr(rgr, "OllamaAdapter", _fake_adapter_class("EXTERNAL_UNAVAILABLE"))
        attempt_repair = rgr._make_attempt_repair("fake-model", 8192, 30.0)
        lockfile_entry = _entry(gc.DEPENDENCY_LOCK_MISMATCH, injection_target="lockfile")

        changed, fingerprint = attempt_repair(lockfile_entry, files)

        assert changed is None
        assert fingerprint.files == ("backend/requirements.txt",)
        assert fingerprint.outcome.startswith("rejected:")

    def test_anti_loop_strategy_identity_is_unaffected_by_the_target_fix(self, monkeypatch) -> None:
        """F-0056/anti-loop identity depends only on `strategy` staying a
        deterministic function of `entry.defect_class` -- unchanged by
        F-0061's own real-target fix."""
        files = _candidate_files()
        monkeypatch.setattr(rgr, "OllamaAdapter", _fake_adapter_class("EXTERNAL_UNAVAILABLE"))
        attempt_repair = rgr._make_attempt_repair("fake-model", 8192, 30.0)
        entry = _entry(gc.MIGRATION_MODEL_MISMATCH, injection_target="migration")

        _, fp1 = attempt_repair(entry, files)
        _, fp2 = attempt_repair(entry, files)

        assert fp1.strategy == fp2.strategy == f"model_repair_{gc.MIGRATION_MODEL_MISMATCH}"


class TestPromptFairness:
    """F-0064: the real repair prompt `_make_attempt_repair` sends must carry
    only observable, candidate-derived evidence -- never corpus-authored
    evaluator metadata (what was injected, what it's called, why the
    evaluator expects a given outcome, which category the evaluator
    assigned). A real information-leak audit found `defect_title`/
    `defect_rationale` sent verbatim for all 8 real corpus entries -- one
    entry's own rationale even named internal benchmark mechanics
    (`RepeatedFailedStrategyError`) and stated outright that it was "the
    mandatory unrepairable entry". Tests the REAL constructed payload
    object (parsed JSON), not substring matching alone, per the explicit
    instruction that produced this fix."""

    def _capture_prompt(self, entry: gc.RepairCorpusEntry, monkeypatch, files=None):
        files = files if files is not None else _candidate_files()
        fake_cls = _fake_adapter_class(
            "PASS", json.dumps({"files": {"backend/app.py": files["backend/app.py"]}}),
        )
        monkeypatch.setattr(rgr, "OllamaAdapter", fake_cls)
        attempt_repair = rgr._make_attempt_repair("fake-model", 8192, 30.0)
        attempt_repair(entry, files)
        prompt_text = fake_cls.last_infer["prompt"]
        return prompt_text, json.loads(prompt_text)

    def test_a_prompt_omits_corpus_title(self, monkeypatch) -> None:
        entry = _entry(gc.PERMISSION_CHECK_REMOVAL).model_copy(
            update={"title": "UNIQUE_TITLE_MARKER_XYZ"}
        )
        prompt_text, payload = self._capture_prompt(entry, monkeypatch)
        assert "UNIQUE_TITLE_MARKER_XYZ" not in prompt_text
        assert "defect_title" not in payload

    def test_b_prompt_omits_corpus_rationale(self, monkeypatch) -> None:
        entry = _entry(gc.PERMISSION_CHECK_REMOVAL).model_copy(
            update={"rationale": "UNIQUE_RATIONALE_MARKER_XYZ"}
        )
        prompt_text, payload = self._capture_prompt(entry, monkeypatch)
        assert "UNIQUE_RATIONALE_MARKER_XYZ" not in prompt_text
        assert "defect_rationale" not in payload

    def test_c_prompt_omits_repairable_flag(self, monkeypatch) -> None:
        entry = _entry(gc.PERMISSION_CHECK_REMOVAL, repairable=False)
        prompt_text, payload = self._capture_prompt(entry, monkeypatch)
        assert "repairable" not in payload
        assert "repairable" not in prompt_text.lower()
        import inspect
        source = inspect.getsource(rgr._make_attempt_repair) + inspect.getsource(rgr._analyze_repair_target)
        assert "entry.repairable" not in source

    def test_d_prompt_construction_never_reads_injection_strategy(self) -> None:
        import inspect
        source = inspect.getsource(rgr._make_attempt_repair) + inspect.getsource(rgr._analyze_repair_target)
        assert "injection_strategy" not in source

    def test_e_prompt_construction_never_reads_expected_detection(self) -> None:
        import inspect
        source = inspect.getsource(rgr._make_attempt_repair) + inspect.getsource(rgr._analyze_repair_target)
        assert "expected_detection" not in source

    def test_f_prompt_omits_defect_class_and_injection_target(self, monkeypatch) -> None:
        entry = _entry(gc.PERMISSION_CHECK_REMOVAL, injection_target="source_module")
        prompt_text, payload = self._capture_prompt(entry, monkeypatch)
        assert "defect_class" not in payload
        assert "injection_target" not in payload
        assert "permission_check_removal" not in prompt_text

    def test_g_legitimate_current_files_present(self, monkeypatch) -> None:
        entry = _entry(gc.CONTRACT_VIOLATION, injection_target="source_module")
        prompt_text, payload = self._capture_prompt(entry, monkeypatch)
        assert "current_files" in payload
        assert "backend/app.py" in payload["current_files"]

    def test_h_legitimate_real_failure_output_present(self, monkeypatch) -> None:
        entry = _entry(gc.CONTRACT_VIOLATION, injection_target="source_module")
        prompt_text, payload = self._capture_prompt(entry, monkeypatch)
        assert "real_test_probe_output" in payload
        assert isinstance(payload["real_test_probe_output"], str)
        assert payload["real_test_probe_output"]

    def test_i_root_cause_evidence_contains_only_candidate_derived_facts(self, monkeypatch) -> None:
        entry = _entry(gc.PERMISSION_CHECK_REMOVAL).model_copy(
            update={"title": "MARK_TITLE_XYZ", "rationale": "MARK_RATIONALE_XYZ"}
        )
        prompt_text, payload = self._capture_prompt(entry, monkeypatch)
        rce_text = json.dumps(payload["root_cause_evidence"])
        assert "MARK_TITLE_XYZ" not in rce_text
        assert "MARK_RATIONALE_XYZ" not in rce_text

    def test_i2_empty_probe_never_falls_back_to_corpus_text(self, monkeypatch) -> None:
        """F-0064's own second leak vector: `_analyze_repair_target` used to
        fall back to `entry.title` when the real probe captured no text.
        Proven directly against the real function, bypassing the probe, for
        both branches (backend/app.py in context, and the non-Python
        fallback branch)."""
        import hashlib

        entry = _entry(gc.PERMISSION_CHECK_REMOVAL).model_copy(
            update={"title": "MARK_TITLE_XYZ", "rationale": "MARK_RATIONALE_XYZ"}
        )
        app_context = {"backend/app.py": _candidate_files()["backend/app.py"]}
        app_cause = rgr._analyze_repair_target(entry, app_context, "")
        app_cause_text = json.dumps(app_cause.model_dump(mode="json"))
        assert "MARK_TITLE_XYZ" not in app_cause_text
        assert "MARK_RATIONALE_XYZ" not in app_cause_text

        non_python_entry = _entry(gc.DEPENDENCY_LOCK_MISMATCH, injection_target="lockfile").model_copy(
            update={"title": "MARK_TITLE_XYZ", "rationale": "MARK_RATIONALE_XYZ"}
        )
        lockfile_context = {"backend/requirements.txt": "flask==2.3.2\n"}
        fallback_cause = rgr._analyze_repair_target(non_python_entry, lockfile_context, "")
        expected_signature = hashlib.sha256(rgr._NO_CAPTURED_FAILURE_TEXT.encode("utf-8")).hexdigest()
        assert fallback_cause.failure_signature == f"sha256:{expected_signature}"

    def test_j_corpus_metadata_still_recoverable_from_corpus_entry(self) -> None:
        """Evaluator-side: title/rationale/repairable/injection_strategy all
        remain real fields on the corpus entry itself and in the real
        corpus file -- removing them from the prompt loses no evidence,
        only stops it from reaching the repair agent."""
        entry = _entry(gc.PERMISSION_CHECK_REMOVAL, repairable=False)
        assert entry.title
        assert entry.rationale
        assert entry.repairable is False
        assert entry.injection_strategy
