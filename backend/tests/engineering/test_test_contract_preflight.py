from __future__ import annotations

import ast

from arkali.engineering.factory.test_contract_preflight import (
    _lifecycle_findings,
    _undefined_call_findings,
)


def _findings(source: str, path: str = "tests/test_app.py") -> list:
    return _undefined_call_findings(path, ast.parse(source))


def test_flags_a_call_to_a_name_never_imported_or_defined() -> None:
    """golden-work-071 (real repository evidence, real qwen2.5-coder:14b,
    frozen): tests/test_app.py wrote `from backend.app import app,
    get_db_connection` and called `init_db()` in setUp() -- a real
    function, genuinely defined in backend/db.py, but never imported by
    this file under any name. Real pytest collection failed all 8 tests
    outright with NameError: name 'init_db' is not defined."""
    source = (
        "import unittest\n"
        "from backend.app import app, get_db_connection\n"
        "class TestApp(unittest.TestCase):\n"
        "    def setUp(self):\n"
        "        self.app = app.test_client()\n"
        "        init_db()\n"
    )
    findings = _findings(source)
    assert len(findings) == 1
    assert findings[0].code == "undefined_name_called"
    assert "init_db" in findings[0].detail


def test_is_silent_when_the_name_is_imported() -> None:
    source = (
        "from backend.db import init_db\n"
        "def test_x():\n    init_db()\n    assert True\n"
    )
    assert _findings(source) == []


def test_is_silent_when_the_name_is_defined_locally() -> None:
    source = "def init_db():\n    pass\ndef test_x():\n    init_db()\n    assert True\n"
    assert _findings(source) == []


def test_is_silent_for_builtins() -> None:
    source = "def test_x():\n    print(len([1, 2]))\n    assert True\n"
    assert _findings(source) == []


def test_is_silent_for_a_method_call_on_an_object() -> None:
    """Only bare-name calls (`foo()`) are checked -- `obj.foo()` is an
    attribute access this check does not attempt to resolve."""
    source = "def test_x():\n    response = object()\n    response.json()\n    assert True\n"
    assert _findings(source) == []


def test_is_silent_when_the_name_is_a_function_parameter() -> None:
    source = "def test_x(callback):\n    callback()\n    assert True\n"
    assert _findings(source) == []


def test_is_silent_when_the_name_is_assigned_before_use() -> None:
    source = "def helper(): pass\ndef test_x():\n    fn = helper\n    fn()\n    assert True\n"
    assert _findings(source) == []


def test_deduplicates_repeated_calls_to_the_same_undefined_name() -> None:
    source = (
        "def test_a():\n    ghost()\n    assert True\n"
        "def test_b():\n    ghost()\n    assert True\n"
    )
    findings = _findings(source)
    assert len(findings) == 1


def test_flags_mutating_sqlite_tests_that_share_persistent_rows() -> None:
    files = {
        "backend/app.py": "import sqlite3\n",
        "tests/test_app.py": (
            "import pytest\n"
            "@pytest.fixture\n"
            "def init_database():\n    init_db('app.db')\n"
            "def test_create(client, init_database):\n"
            "    client.post('/things', json={'name': 'x'})\n"
            "def test_list(client, init_database):\n"
            "    client.post('/things', json={'name': 'x'})\n"
            "    assert len(client.get('/things').json) == 1\n"
        ),
    }
    findings = _lifecycle_findings(files)
    assert [finding.code for finding in findings] == [
        "test_database_state_leaks_between_cases"
    ]


def test_accepts_mutating_sqlite_tests_with_per_test_temporary_database() -> None:
    files = {
        "backend/app.py": "import sqlite3\n",
        "tests/test_app.py": (
            "import pytest\n"
            "@pytest.fixture\n"
            "def database(tmp_path, monkeypatch):\n"
            "    monkeypatch.setattr(app, 'DB_PATH', tmp_path / 'app.db')\n"
            "def test_create(client, database):\n    client.post('/things')\n"
            "def test_delete(client, database):\n    client.delete('/things/1')\n"
        ),
    }
    assert _lifecycle_findings(files) == []


def test_accepts_read_only_sqlite_tests_without_database_reset() -> None:
    files = {
        "backend/app.py": "import sqlite3\n",
        "tests/test_app.py": (
            "def test_list(client):\n    assert client.get('/things').status_code == 200\n"
            "def test_get(client):\n    assert client.get('/things/1').status_code == 404\n"
        ),
    }
    assert _lifecycle_findings(files) == []
