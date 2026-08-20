from __future__ import annotations

from arkali.engineering.repair.product_root_cause import analyze_python_product_failure


def test_real_defect_shape_is_classified_from_sources_not_assumed() -> None:
    backend = "import sqlite3\napp = object()\ndef get_db_connection(): pass\n"
    test = "from app import app, db, Work\n"
    result = analyze_python_product_failure(
        "backend/src/main.py", backend, test,
        "ModuleNotFoundError: No module named 'app'",
    )
    assert result.root_cause_classes == (
        "assembly_import_path_defect",
        "generated_test_backend_contract_drift",
        "schema_runtime_mismatch",
    )
    assert result.missing_exports == ("Work", "db")
    assert result.failure_signature.startswith("sha256:")


def test_matching_contract_and_schema_are_not_misclassified() -> None:
    result = analyze_python_product_failure(
        "backend/app.py",
        "app = object()\ndb = object()\nclass Work: pass\nSQL='CREATE TABLE works'\n",
        "from app import app, db, Work\n", "other failure",
    )
    assert result.root_cause_classes == ("unclassified_runtime_failure",)
    assert result.missing_exports == ()
