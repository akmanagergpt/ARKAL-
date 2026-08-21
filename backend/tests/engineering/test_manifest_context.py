from __future__ import annotations

from arkali.engineering.factory.manifest_context import (
    _frontend_import_targets,
    _manifest_context,
    _third_party_python_imports,
)


def test_third_party_python_imports_excludes_stdlib_and_local_roots() -> None:
    files = {
        "backend/app.py": (
            "import sqlite3\n"
            "from flask import Flask\n"
            "from flask_cors import CORS\n"
            "from backend.migrate import migrate\n"
        ),
    }
    assert _third_party_python_imports(files) == frozenset({"flask", "flask_cors"})


def test_third_party_python_imports_ignores_non_backend_files() -> None:
    files = {"tests/test_app.py": "import pytest\n"}
    assert _third_party_python_imports(files) == frozenset()


def test_third_party_python_imports_skips_unparseable_files_without_raising() -> None:
    files = {"backend/broken.py": "def f(:\n"}
    assert _third_party_python_imports(files) == frozenset()


def test_frontend_import_targets_excludes_relative_imports() -> None:
    files = {
        "frontend/src/App.js": (
            "import axios from 'axios';\n"
            "import './App.css';\n"
            "import Client from '../client';\n"
        ),
    }
    assert _frontend_import_targets(files) == frozenset({"axios"})


def test_frontend_import_targets_handles_require() -> None:
    files = {"frontend/src/config.js": "const cors = require('cors/lib/index');\n"}
    assert _frontend_import_targets(files) == frozenset({"cors"})


def test_manifest_context_keeps_only_the_three_paths_the_validator_reads() -> None:
    files = {
        "backend/app.py": "from flask import Flask\napp = Flask(__name__)\n",
        "backend/requirements.txt": "flask\n",
        "frontend/package.json": '{"name": "app"}\n',
        "frontend/src/App.js": "import axios from 'axios';\n",
        "tests/test_app.py": "import pytest\ndef test_x(): assert True\n",
    }
    reduced = _manifest_context(files)
    assert reduced["backend/requirements.txt"] == "flask\n"
    assert reduced["frontend/package.json"] == '{"name": "app"}\n'
    # No route/UI/test source bytes leak into the reduced context.
    assert "backend/app.py" not in reduced
    assert "frontend/src/App.js" not in reduced
    assert "tests/test_app.py" not in reduced
    assert "flask" in reduced["_extracted/backend_third_party_imports.txt"]
    assert "axios" in reduced["_extracted/frontend_import_targets.txt"]


def test_manifest_context_preserves_frontend_public_index_presence() -> None:
    files = {"frontend/public/index.html": "<div id='root'></div>\n"}
    reduced = _manifest_context(files)
    assert reduced["frontend/public/index.html"] == "<div id='root'></div>\n"


def test_manifest_context_on_empty_input_still_has_extraction_keys() -> None:
    reduced = _manifest_context({})
    assert reduced["_extracted/backend_third_party_imports.txt"] == ""
    assert reduced["_extracted/frontend_import_targets.txt"] == ""
    assert "backend/requirements.txt" not in reduced
