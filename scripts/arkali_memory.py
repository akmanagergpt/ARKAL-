"""ARKALI'nin yerel, türetilmiş ikinci-beyin indeksi.

Bu araç kaynakları, kanonik belgeleri veya karar kayıtlarını değiştirmez. Mevcut
``engineering.codeintel`` Python grafik üreticisini kullanarak yalnızca
doğrulanabilir Python sembol/import/bağımlılık verisini ``var/memory`` altında
yeniden üretir. Çıktılar git-ignored, içerik-adresli ve otorite dışıdır.

Kullanım:
    python scripts/arkali_memory.py refresh
    python scripts/arkali_memory.py status
    python scripts/arkali_memory.py impact backend/arkali/example.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time
from collections import defaultdict, deque
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
STORE = REPO / "var" / "memory"
STATUS = STORE / "status.json"
MANIFEST = STORE / "source_manifest.json"
GRAPHS = STORE / "python_graphs.json"
OBSIDIAN_STATUS = REPO / "docs" / "hafiza" / ".generated" / "DURUM.md"
OBSIDIAN_CONTINUE = REPO / "docs" / "hafiza" / ".generated" / "DEVAM_ET.md"
# Bu araç içerik dışa aktarmasa da hassas konumları hiç taramamak tercih edilir.
# İsim karşılaştırması küçük harf ve yol bileşeni bazındadır; kural uzantı veya
# içerik tahminine dayanmaz.
SENSITIVE_PATH_PARTS = frozenset({"secrets", ".secrets", "credentials", "private"})


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sources() -> tuple[pathlib.Path, ...]:
    return tuple(
        path
        for path in sorted(BACKEND.rglob("*.py"))
        if not SENSITIVE_PATH_PARTS.intersection(
            part.lower() for part in path.relative_to(REPO).parts
        )
    )


def source_manifest() -> dict[str, str]:
    """Dosya kimlikleri; değişiklik karşılaştırması için yeterli, kaynak kopyası değil."""
    return {
        path.relative_to(REPO).as_posix(): _sha256(path)
        for path in _sources()
    }


def _read_previous_manifest() -> dict[str, str]:
    if not MANIFEST.is_file():
        return {}
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return raw.get("sources", {}) if isinstance(raw, dict) else {}


def _changed(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    return {
        "added": sorted(set(after) - set(before)),
        "changed": sorted(key for key in set(after) & set(before) if after[key] != before[key]),
        "removed": sorted(set(before) - set(after)),
    }


def _graph_payload() -> dict[str, Any]:
    # Bu araç yeni bir ayrıştırıcı değildir: C-24'ün mevcut üreticisini kullanır.
    sys.path.insert(0, str(BACKEND))
    from arkali.engineering.codeintel.graph_vocabulary import GraphVocabulary
    from arkali.engineering.codeintel.python_builder import PythonGraphBuilder

    builder = PythonGraphBuilder(GraphVocabulary.load(REPO), BACKEND)
    graphs: dict[str, Any] = {}
    for kind in builder.builds():
        graph = builder.build(kind)
        graphs[kind] = {
            "address": graph.address,
            "nodes": [node.model_dump() for node in graph.nodes()],
            "edges": [edge.model_dump() for edge in graph.edges()],
            "sources": list(graph.sources()),
        }
    return {
        "derived": True,
        "authority": "none; inspect source and canonical documents",
        "source_root": "backend",
        "built_kinds": list(builder.builds()),
        "not_built": list(builder.unbuilt()),
        "graphs": graphs,
    }


def _write_json(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(rendered, encoding="utf-8")


def _write_obsidian_status(status: dict[str, Any]) -> None:
    changes = status["changes"]
    lines = [
        "---",
        "türetilmiş: true",
        "otorite: none",
        "---",
        "# Yerel Hafıza Durumu",
        "",
        "> Bu sayfa otomatik üretilir; kaynak ya da karar kaydı değildir.",
        "",
        f"Son yenileme: `{status['refreshed_at']}`",
        f"İzlenen Python dosyası: **{status['source_count']}**",
        f"Grafik kapsamı: {', '.join(status['built_kinds'])}",
        f"Henüz kapsam dışı: {', '.join(status['not_built'])}",
        "",
        "## Son değişiklikler",
        "",
        f"- Eklenen: {len(changes['added'])}",
        f"- Değişen: {len(changes['changed'])}",
        f"- Silinen: {len(changes['removed'])}",
        "",
        "Etkilenen dosyaları görmek için `python scripts/arkali_memory.py impact <dosya>` kullanılır.",
    ]
    OBSIDIAN_STATUS.parent.mkdir(parents=True, exist_ok=True)
    OBSIDIAN_STATUS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def continue_markdown(status: dict[str, Any]) -> str:
    """Aylar sonraki dönüş için kısa, otoriteye bağlantılı başlangıç ekranı."""
    changes = status["changes"]
    changed_paths = changes["added"] + changes["changed"] + changes["removed"]
    listed = changed_paths[:20]
    change_lines = [f"- `{path}`" for path in listed] or ["- Son yenilemeden beri Python kaynak değişikliği yok."]
    if len(changed_paths) > len(listed):
        change_lines.append(f"- … ve {len(changed_paths) - len(listed)} dosya daha")
    return "\n".join(
        [
            "---",
            "türetilmiş: true",
            "otorite: none",
            "---",
            "# Devam Et",
            "",
            "> Bu sayfa otomatik üretilir. Yön vermez ve karar vermez; doğru otoriter kayda hızlıca ulaştırır.",
            "",
            f"Son yenileme: `{status['refreshed_at']}`",
            "",
            "## Güvenli başlangıç",
            "",
            "1. [[ARKALI_HANDOFF|Devir kaydını]] oku.",
            "2. [[docs/build/BUILD_STATE|Build durumunu]] ve [[docs/build/OPEN_BLOCKERS|açık bulguları]] doğrula.",
            "3. İnsan onayı gerektiren bir iş varsa [[docs/acceptance/HUMAN_GATE_RECORDS|kapı kayıtlarına]] bak.",
            "4. Kod değişikliği öncesinde güncel handoff kontrolünü çalıştır; sapma varsa önce onu görünür kıl.",
            "5. Etkilenen Python dosyalarını görmek için `python scripts/arkali_memory.py impact <dosya>` kullan.",
            "",
            "## Yerel hafıza kapsamı",
            "",
            f"- İzlenen Python dosyası: **{status['source_count']}**",
            f"- Doğrulanmış grafikler: {', '.join(status['built_kinds'])}",
            f"- Henüz otomatik analiz dışı: {', '.join(status['not_built'])}",
            "",
            "## Son Python kaynak değişiklikleri",
            "",
            *change_lines,
            "",
            "## Ana otoriteler",
            "",
            "- [[docs/canonical/REQUIREMENT_REGISTER|Gereksinimler]]",
            "- [[docs/build/DECISION_LOG|Kararlar]]",
            "- [[docs/adr/ADR_INDEX|Mimari kararlar]]",
            "- [[docs/acceptance/EVIDENCE_INDEX|Kanıt dizini]]",
            "",
            "## Gizlilik",
            "",
            "[[docs/hafiza/calisma_rehberleri/GIZLILIK|Gizli bilgi kurallarını]] uygula; sırları sohbete veya nota yazma.",
            "",
            "## Çalışma akışı",
            "",
            "[[docs/hafiza/calisma_rehberleri/DEVAM_SURECI|Geliştirmeye devam etme sürecini]] izle.",
            "[[docs/hafiza/calisma_rehberleri/KULLANIM_KILAVUZU|Kullanıcı kullanım kılavuzu]] burada.",
            "",
        ]
    )


def _write_continue_page(status: dict[str, Any]) -> None:
    OBSIDIAN_CONTINUE.parent.mkdir(parents=True, exist_ok=True)
    OBSIDIAN_CONTINUE.write_text(continue_markdown(status), encoding="utf-8")


def refresh() -> dict[str, Any]:
    before = _read_previous_manifest()
    current = source_manifest()
    payload = _graph_payload()
    changed = _changed(before, current)
    now = datetime.now(UTC).isoformat()
    status = {
        "derived": True,
        "authority": "none; source plus canonical documents win",
        "refreshed_at": now,
        "source_count": len(current),
        "built_kinds": payload["built_kinds"],
        "not_built": payload["not_built"],
        "changes": changed,
    }
    _write_json(MANIFEST, {"sources": current})
    _write_json(GRAPHS, payload)
    _write_json(STATUS, status)
    _write_obsidian_status(status)
    _write_continue_page(status)
    return status


def _normalise_source(value: str) -> str:
    candidate = pathlib.Path(value)
    if candidate.is_absolute():
        try:
            candidate = candidate.relative_to(BACKEND)
        except ValueError as exc:
            raise ValueError("dosya backend/ altında olmalıdır") from exc
    else:
        text = candidate.as_posix()
        if text.startswith("backend/"):
            candidate = pathlib.PurePosixPath(text).relative_to("backend")
    normalised = pathlib.PurePosixPath(candidate).as_posix()
    if not (BACKEND / normalised).is_file():
        raise ValueError(f"Python kaynak dosyası bulunamadı: {value}")
    return normalised


def _module_names(source: str) -> set[str]:
    parts = list(pathlib.PurePosixPath(source).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return {".".join(parts)} if parts else set()


def _impact_sources(source: str, edges: Iterable[dict[str, str]]) -> list[str]:
    """Değişen yerel modülü doğrudan/dolaylı içe aktaran kaynakları bulur."""
    module_names = _module_names(source)
    reverse: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        reverse[edge["target"]].add(edge["origin"])
    seen = {source}
    queue: deque[str] = deque(module_names)
    while queue:
        target = queue.popleft()
        for importer in reverse.get(target, set()):
            if importer not in seen:
                seen.add(importer)
                queue.extend(_module_names(importer))
    return sorted(seen)


def impact(path: str) -> dict[str, Any]:
    if not GRAPHS.is_file():
        raise RuntimeError("hafıza henüz üretilmemiş; önce refresh çalıştırın")
    source = _normalise_source(path)
    graphs = json.loads(GRAPHS.read_text(encoding="utf-8"))
    imports = graphs["graphs"]["import"]["edges"]
    return {
        "derived": True,
        "authority": "none; inspect source and tests before acting",
        "changed_source": source,
        "possibly_affected_sources": _impact_sources(source, imports),
    }


def watch(interval: float) -> int:
    """Kaynak karmalarını yoklayıp yalnızca değişiklikte yerel çıktıyı yeniler.

    Bilerek dosya izleme paketi, ağ çağrısı veya ARKALI çalışma-zamanı entegrasyonu
    kullanmaz. Bu, geliştirici makinesindeki Obsidian görünümünü güncel tutan
    isteğe bağlı bir yardımcıdır.
    """
    if interval <= 0:
        raise ValueError("izleme aralığı sıfırdan büyük olmalıdır")
    if not MANIFEST.is_file():
        refresh()
    known = _read_previous_manifest()
    print(f"İzleme başladı: {len(known)} Python dosyası, {interval:g} sn aralık")
    try:
        while True:
            time.sleep(interval)
            current = source_manifest()
            if current != known:
                status = refresh()
                known = current
                changes = status["changes"]
                print(
                    "Hafıza yenilendi: "
                    f"+{len(changes['added'])} "
                    f"~{len(changes['changed'])} "
                    f"-{len(changes['removed'])}"
                )
    except KeyboardInterrupt:
        print("İzleme durduruldu.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="command", required=True)
    command.add_parser("refresh")
    command.add_parser("status")
    impact_parser = command.add_parser("impact")
    impact_parser.add_argument("path")
    watch_parser = command.add_parser("watch")
    watch_parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    if args.command == "refresh":
        result = refresh()
    elif args.command == "status":
        if not STATUS.is_file():
            raise RuntimeError("hafıza henüz üretilmemiş; önce refresh çalıştırın")
        result = json.loads(STATUS.read_text(encoding="utf-8"))
    elif args.command == "watch":
        return watch(args.interval)
    else:
        result = impact(args.path)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
