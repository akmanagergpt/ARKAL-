from __future__ import annotations

from arkali.engineering.factory.route_response_preflight import (
    _missing_generated_id_findings,
    _raw_row_jsonify_findings,
)


def test_flags_a_create_route_that_never_references_lastrowid() -> None:
    """golden-work-052 and golden-work-053 (session evidence, frozen,
    byte-identical across two separate real qwen2.5-coder:14b runs): the
    real model's create_task handler returned the client-submitted body
    verbatim, never the row id SQLite actually assigned."""
    source = (
        "from flask import jsonify\n"
        "def create_task():\n"
        "    data = request.get_json()\n"
        "    cursor.execute('INSERT INTO tasks (title) VALUES (?)', (data['title'],))\n"
        "    conn.commit()\n"
        "    return jsonify(data), 201\n"
    )
    findings = _missing_generated_id_findings({"backend/app.py": source})
    assert len(findings) == 1
    assert findings[0].code == "missing_generated_id_in_create_response"
    assert "create_task" in findings[0].detail


def test_is_silent_when_lastrowid_is_referenced() -> None:
    source = (
        "from flask import jsonify\n"
        "def create_task():\n"
        "    cursor.execute('INSERT INTO tasks (title) VALUES (?)', (data['title'],))\n"
        "    conn.commit()\n"
        "    task_id = cursor.lastrowid\n"
        "    return jsonify({**data, 'id': task_id}), 201\n"
    )
    assert _missing_generated_id_findings({"backend/app.py": source}) == []


def test_is_silent_when_no_insert_is_present() -> None:
    source = "def get_tasks():\n    cursor.execute('SELECT * FROM tasks')\n    return jsonify(cursor.fetchall())\n"
    assert _missing_generated_id_findings({"backend/app.py": source}) == []


def test_is_silent_when_insert_exists_but_the_function_returns_no_json() -> None:
    """A schema-bootstrap or seed function that inserts rows without ever
    building a client-facing JSON response is not this defect class."""
    source = "def seed():\n    cursor.execute('INSERT INTO tasks (title) VALUES (?)', ('x',))\n    conn.commit()\n"
    assert _missing_generated_id_findings({"backend/app.py": source}) == []


def test_ignores_non_backend_files() -> None:
    source = "def create_task():\n    cursor.execute('INSERT INTO tasks (title) VALUES (?)')\n    return jsonify(data), 201\n"
    assert _missing_generated_id_findings({"frontend/src/App.js": source}) == []


def test_real_golden_work_053_evidence_is_flagged() -> None:
    """Real, frozen evidence — not a hand-constructed stand-in."""
    source = (
        "from flask import Flask, request, jsonify\n"
        "import sqlite3\n"
        "app = Flask(__name__)\n"
        "DB_NAME = 'tasks.db'\n"
        "@app.route('/tasks', methods=['POST'])\n"
        "def create_task():\n"
        "    data = request.get_json()\n"
        "    conn = sqlite3.connect(DB_NAME)\n"
        "    cursor = conn.cursor()\n"
        "    cursor.execute('INSERT INTO tasks (title, description, completed) VALUES (?, ?, ?)',\n"
        "                   (data['title'], data.get('description', ''), data.get('completed', False)))\n"
        "    conn.commit()\n"
        "    conn.close()\n"
        "    return jsonify(data), 201\n"
    )
    findings = _missing_generated_id_findings({"backend/app.py": source})
    assert [f.code for f in findings] == ["missing_generated_id_in_create_response"]


def test_flags_a_raw_fetchone_tuple_passed_straight_to_jsonify() -> None:
    """golden-work-056 (session evidence, frozen): a real qwen2.5-coder:14b
    get_task handler called cursor.fetchone() and passed that exact tuple
    straight to jsonify() — a real Flask+sqlite3 footgun (a bare tuple
    serializes as a JSON array, not a keyed object) — while its own
    generated test asserted response['id'] and got a real TypeError."""
    source = (
        "def get_task(id):\n"
        "    cursor = conn.cursor()\n"
        "    cursor.execute('SELECT * FROM tasks WHERE id = ?', (id,))\n"
        "    task = cursor.fetchone()\n"
        "    return jsonify(task)\n"
    )
    findings = _raw_row_jsonify_findings({"backend/app.py": source})
    assert len(findings) == 1
    assert findings[0].code == "raw_sqlite_row_passed_to_jsonify"
    assert "get_task" in findings[0].detail


def test_flags_dict_conversion_without_row_factory() -> None:
    """golden-work-057 (session evidence, frozen): a real qwen2.5-coder:14b
    wrapped raw fetchone()/fetchall() rows in dict(row) — a real fix for
    the golden-work-056 gap — but never set conn.row_factory =
    sqlite3.Row, so dict() on a plain tuple itself raised a real
    TypeError and every affected route returned HTTP 500. dict(...)
    alone must not be treated as proof of correctness."""
    source = (
        "def get_task(id):\n"
        "    cursor = conn.cursor()\n"
        "    task = cursor.fetchone()\n"
        "    return jsonify(dict(task))\n"
    )
    findings = _raw_row_jsonify_findings({"backend/app.py": source})
    assert len(findings) == 1
    assert findings[0].code == "raw_sqlite_row_passed_to_jsonify"


def test_flags_a_fetchall_comprehension_wrapped_in_dict_without_row_factory() -> None:
    """Real, frozen golden-work-057 evidence: [dict(row) for row in tasks]
    where tasks = cursor.fetchall(), with no row_factory anywhere."""
    source = (
        "def get_tasks():\n"
        "    cursor = conn.cursor()\n"
        "    tasks = cursor.fetchall()\n"
        "    return jsonify([dict(row) for row in tasks])\n"
    )
    findings = _raw_row_jsonify_findings({"backend/app.py": source})
    assert [f.code for f in findings] == ["raw_sqlite_row_passed_to_jsonify"]


def test_raw_row_check_is_silent_when_row_factory_is_used() -> None:
    source = (
        "def get_task(id):\n"
        "    conn.row_factory = sqlite3.Row\n"
        "    cursor = conn.cursor()\n"
        "    task = cursor.fetchone()\n"
        "    return jsonify(dict(task))\n"
    )
    assert _raw_row_jsonify_findings({"backend/app.py": source}) == []


def test_raw_row_check_is_silent_when_manually_converted_to_a_dict() -> None:
    source = (
        "def get_task(id):\n"
        "    cursor = conn.cursor()\n"
        "    task = cursor.fetchone()\n"
        "    return jsonify({'id': task[0], 'title': task[1]})\n"
    )
    assert _raw_row_jsonify_findings({"backend/app.py": source}) == []


def test_raw_row_check_is_silent_when_fetchone_result_is_unused() -> None:
    source = "def get_tasks():\n    cursor.execute('SELECT * FROM tasks')\n    return jsonify(cursor.fetchall())\n"
    assert _raw_row_jsonify_findings({"backend/app.py": source}) == []


def test_raw_row_check_catches_the_real_golden_work_056_evidence() -> None:
    """Real, frozen evidence — not a hand-constructed stand-in."""
    source = (
        "@app.route('/tasks/<int:id>', methods=['GET'])\n"
        "def get_task(id):\n"
        "    conn = sqlite3.connect(DB_NAME)\n"
        "    cursor = conn.cursor()\n"
        "    cursor.execute('SELECT * FROM tasks WHERE id = ?', (id,))\n"
        "    task = cursor.fetchone()\n"
        "    conn.close()\n"
        "    if task is None:\n"
        "        return jsonify({'error': 'Task not found'}), 404\n"
        "    return jsonify(task)\n"
    )
    findings = _raw_row_jsonify_findings({"backend/app.py": source})
    assert [f.code for f in findings] == ["raw_sqlite_row_passed_to_jsonify"]
