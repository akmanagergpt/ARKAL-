"""Yerel hafıza aracı yalnızca türetilmiş, doğrulanabilir veri üretir."""

from __future__ import annotations

import importlib.util
import pathlib
from typing import Final

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
SCRIPT: Final[pathlib.Path] = REPO / "scripts" / "arkali_memory.py"

spec = importlib.util.spec_from_file_location("arkali_memory", SCRIPT)
assert spec is not None and spec.loader is not None
memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory)


def test_manifest_is_hash_only_and_sorted() -> None:
    manifest = memory.source_manifest()
    assert manifest == dict(sorted(manifest.items()))
    assert manifest
    assert all(len(digest) == 64 for digest in manifest.values())
    assert all(not path.startswith("docs/") for path in manifest)


def test_sensitive_path_components_are_excluded_from_memory() -> None:
    assert "secrets" in memory.SENSITIVE_PATH_PARTS
    assert "credentials" in memory.SENSITIVE_PATH_PARTS


def test_changed_distinguishes_added_changed_and_removed() -> None:
    assert memory._changed(
        {"same.py": "a", "old.py": "b", "edit.py": "c"},
        {"same.py": "a", "new.py": "d", "edit.py": "e"},
    ) == {"added": ["new.py"], "changed": ["edit.py"], "removed": ["old.py"]}


def test_impact_only_follows_verified_import_edges() -> None:
    edges = [
        {"origin": "arkali/a.py", "target": "arkali.changed", "source": "arkali/a.py"},
        {"origin": "arkali/b.py", "target": "arkali.a", "source": "arkali/b.py"},
        {"origin": "arkali/unrelated.py", "target": "requests", "source": "arkali/unrelated.py"},
    ]
    assert memory._impact_sources("arkali/changed.py", edges) == [
        "arkali/a.py",
        "arkali/b.py",
        "arkali/changed.py",
    ]


def test_continue_page_links_to_authorities_without_claiming_authority() -> None:
    page = memory.continue_markdown(
        {
            "refreshed_at": "2026-09-06T00:00:00+00:00",
            "source_count": 1,
            "built_kinds": ["symbol"],
            "not_built": ["route"],
            "changes": {"added": ["backend/arkali/new.py"], "changed": [], "removed": []},
        }
    )
    assert "otorite: none" in page
    assert "[[ARKALI_HANDOFF" in page
    assert "[[docs/build/OPEN_BLOCKERS" in page
    assert "`backend/arkali/new.py`" in page
    assert "DEVAM_SURECI" in page
    assert "KULLANIM_KILAVUZU" in page
