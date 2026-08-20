from __future__ import annotations

import pytest

from arkali.engineering.factory.errors import ProductSemanticPreflightError
from arkali.engineering.factory.product_preflight import inspect_product_files


def _complete() -> dict[str, str]:
    return {
        "backend/src/service.py": (
            "import sqlite3\n"
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
        "config/README.md": "run\n",
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
