from pathlib import Path

import numpy as np

from bsp_docs_mcp.indexer import build_index
from bsp_docs_mcp.storage import IndexDatabase


class FakeEmbedder:
    model = "fake-model"

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.tile(np.asarray([[1.0, 0.0]], dtype=np.float32), (len(texts), 1))


def test_build_index_records_full_version_and_replaces_old_file(tmp_path: Path) -> None:
    html = tmp_path / "Документация.html"
    html.write_text(
        '<h1 id="root">БСП</h1><p>Рекомендуется использовать метод.</p>',
        encoding="utf-8",
    )
    target = tmp_path / "indexes" / "3.1" / "index.sqlite"
    target.parent.mkdir(parents=True)
    target.write_text("old incomplete index", encoding="utf-8")

    count = build_index(html, "3_1_11_155", target, FakeEmbedder())

    assert count == 1
    with IndexDatabase(target) as database:
        metadata = database.metadata()
        assert metadata["family"] == "3.1"
        assert metadata["source_version"] == "3.1.11.155"
        assert metadata["model"] == "fake-model"
        assert database.get_section(database.all_vectors()[0][0]) is not None


def test_build_index_from_multifile_directory(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "Глава 4" / "Интерфейс").mkdir(parents=True)
    (source / "Глава 4" / "index.html").write_text(
        "<h1>Aggregate duplicate</h1><p>Do not index</p>", encoding="utf-8"
    )
    (source / "Глава 4" / "Интерфейс" / "ПолучитьФайл.html").write_text(
        "<h1>ПолучитьФайл</h1><p>Возвращает присоединенный файл.</p>",
        encoding="utf-8",
    )
    target = tmp_path / "index.sqlite"

    count = build_index(source, "3.1.11", target, FakeEmbedder())

    assert count == 1
    with IndexDatabase(target) as database:
        metadata = database.metadata()
        assert metadata["source_version"] == "3.1.11"
        assert metadata["source_file_count"] == "1"
        section_id = database.all_vectors()[0][0]
        section = database.get_section(section_id)
        assert section["source_path"].endswith("ПолучитьФайл.html")
        assert section["breadcrumb"] == ["Глава 4", "Интерфейс", "ПолучитьФайл"]
