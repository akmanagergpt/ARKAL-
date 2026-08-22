from __future__ import annotations

import pytest

from arkali.engineering.factory.errors import ProductSemanticPreflightError
from arkali.engineering.factory.product_preflight import inspect_product_files


def _complete() -> dict[str, str]:
    return {
        "backend/src/service.py": (
            "import sqlite3\n@app.route('/records')\n"
            "def connection(): return sqlite3.connect('data.db')\n"
            "def bootstrap():\n"
            "    connection().execute('CREATE TABLE IF NOT EXISTS records (id INTEGER)')\n"
            "bootstrap()\n"
        ),
        "tests/backend/test_service.py": (
            "from service import connection\n"
            "def test_connection():\n    assert connection() is not None\n"
        ),
        "frontend/src/App.js": "export default function App(){return null}\n",
        "frontend/public/index.html": '<div id="root"></div>\n',
        "frontend/package.json": '{"scripts":{"build":"echo ok"}}\n',
        "config/README.md": "run\n",
        "backend/requirements.txt": "pytest\n",
    }


def test_complete_self_consistent_product_passes() -> None:
    assert inspect_product_files(_complete()).passed


def test_unittest_assertion_methods_are_meaningful() -> None:
    files = {
        **_complete(),
        "tests/backend/test_service.py": (
            "import unittest\nfrom service import connection\n"
            "class TestService(unittest.TestCase):\n"
            "    def test_connection(self): self.assertIsNotNone(connection())\n"
        ),
    }
    assert inspect_product_files(files).passed


def test_declared_third_party_import_is_not_misclassified_as_local() -> None:
    files = {
        **_complete(),
        "backend/requirements.txt": "Flask==3.1.0\npytest>=8\n",
        "tests/backend/test_service.py": (
            "from flask import Flask\nfrom service import connection\n"
            "def test_connection(): assert Flask and connection()\n"
        ),
    }
    assert inspect_product_files(files).passed


def test_package_qualified_generated_module_import_resolves() -> None:
    files = {
        **_complete(),
        "tests/backend/test_service.py": (
            "from backend.src.service import connection\n"
            "def test_connection(): assert connection()\n"
        ),
    }
    assert inspect_product_files(files).passed


def test_stdlib_is_refused_as_an_installable_dependency() -> None:
    files = {**_complete(), "backend/requirements.txt": "sqlite3\npytest\n"}
    report = inspect_product_files(files)
    assert "stdlib_dependency" in {item.code for item in report.findings}


def test_react_scripts_requires_real_html_entry() -> None:
    files = {
        **_complete(),
        "frontend/package.json": '{"dependencies":{"react-scripts":"5"}}',
    }
    files.pop("frontend/public/index.html")
    report = inspect_product_files(files)
    assert "missing_frontend_entry" in {item.code for item in report.findings}


def test_manifest_names_cannot_stand_in_for_persistence_or_api_code() -> None:
    files = {
        **_complete(),
        "backend/src/service.py": "def create_app(): return object()\n",
        "backend/requirements.txt": "Flask\nSQLAlchemy\n",
    }
    codes = {item.code for item in inspect_product_files(files).findings}
    assert {"missing_persistence_code", "missing_api_routes"} <= codes


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (
            {
                "tests/backend/test_service.py": (
                    "from missing import thing\ndef test_x(): assert thing\n"
                )
            },
            "missing_local_module",
        ),
        (
            {
                "tests/backend/test_service.py": (
                    "from service import absent\ndef test_x(): assert absent\n"
                )
            },
            "missing_imported_symbols",
        ),
        (
            {
                "backend/src/service.py": (
                    "import sqlite3\ndef connection(): return sqlite3.connect('x.db')\n"
                )
            },
            "missing_schema_bootstrap",
        ),
        (
            {
                "tests/backend/test_service.py": (
                    "from service import connection\ndef test_x(): pass\n"
                )
            },
            "vacuous_tests",
        ),
    ],
)
def test_incomplete_model_products_fail_closed(
    mutation: dict[str, str],
    expected: str,
) -> None:
    files = {**_complete(), **mutation}
    report = inspect_product_files(files)
    assert expected in {item.code for item in report.findings}
    with pytest.raises(ProductSemanticPreflightError):
        report.require_pass()


def test_repair_cannot_remove_parent_symbols() -> None:
    original = _complete()
    repaired = {**original, "backend/src/service.py": "import sqlite3\n"}
    report = inspect_product_files(repaired, baseline=original)
    assert "removed_parent_symbols" in {item.code for item in report.findings}


def test_a_backend_module_importing_a_json_contract_file_is_refused() -> None:
    """golden-work-067 (real repository evidence, real qwen2.5-coder:14b,
    frozen): backend/db.py and backend/app.py both wrote
    `from backend.data_model import data_model` -- never used anywhere in
    either file -- against backend/data_model.json, a real schema
    *document*, not a Python module. The real, first pytest collection of
    this real candidate failed outright:
    `ModuleNotFoundError: No module named 'backend.data_model'`. Nothing
    before this checked whether a backend module's own import actually
    resolved -- ast.parse alone is blind to this, since the import is
    syntactically valid Python."""
    files = {
        "backend/data_model.json": '{"fields": {"students": {"id": "integer"}}}',
        "backend/db.py": (
            "import sqlite3\n"
            "from backend.data_model import data_model\n"
            "def init_db():\n"
            "    sqlite3.connect('database.db').execute("
            "'CREATE TABLE IF NOT EXISTS students (id INTEGER)')\n"
        ),
        "backend/app.py": (
            "import sqlite3\n"
            "from backend.db import init_db\n"
            "from backend.data_model import data_model\n"
            "app = object()\n"
            "@app.route('/students')\n"
            "def list_students(): return sqlite3.connect('database.db')\n"
            "init_db()\n"
        ),
    }
    report = inspect_product_files(files)
    paths_with_missing_local_module = {
        item.path for item in report.findings if item.code == "missing_local_module"
    }
    assert paths_with_missing_local_module == {"backend/db.py", "backend/app.py"}


def test_a_backend_module_importing_a_real_sibling_module_is_silent() -> None:
    files = {
        "backend/db.py": "import sqlite3\ndef init_db():\n    return sqlite3.connect('x.db')\n",
        "backend/app.py": (
            "from backend.db import init_db\napp = object()\n"
            "@app.route('/x')\ndef list_x(): return init_db()\n"
        ),
    }
    report = inspect_product_files(files)
    assert "missing_local_module" not in {item.code for item in report.findings}
