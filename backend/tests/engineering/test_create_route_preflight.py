from __future__ import annotations

from arkali.engineering.factory.create_route_preflight import _missing_generated_id_findings


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
