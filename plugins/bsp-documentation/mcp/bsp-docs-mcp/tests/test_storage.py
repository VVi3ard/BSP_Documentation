from pathlib import Path

import numpy as np

from bsp_docs_mcp.parser import DocumentChunk
from bsp_docs_mcp.storage import IndexDatabase


def make_chunk(chunk_id: str, title: str, text: str) -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        source_version="3.1.11.155",
        anchor=chunk_id,
        title=title,
        breadcrumb=("Глава", title),
        text=text,
        part=1,
        has_recommendation="Рекомендуется" in text,
        has_warning=False,
        source_path=f"Глава 4/{chunk_id}.html",
    )


def test_round_trip_sections_vectors_fts_and_metadata(tmp_path: Path) -> None:
    path = tmp_path / "index.sqlite"
    chunks = [
        make_chunk("files", "Работа с файлами", "Рекомендуется получить присоединенный файл"),
        make_chunk("users", "Пользователи", "Настройка учетных записей пользователей"),
    ]
    vectors = np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)

    with IndexDatabase.create(path, {"family": "3.1", "model": "test"}) as database:
        database.add_chunks(chunks, vectors)

    with IndexDatabase(path) as database:
        assert database.metadata()["family"] == "3.1"
        assert database.get_section("files")["title"] == "Работа с файлами"
        assert database.get_section("files")["source_path"] == "Глава 4/files.html"
        ids, loaded = database.all_vectors()
        assert ids == ["files", "users"]
        np.testing.assert_allclose(loaded, vectors)
        assert database.fts_candidates("присоединенный файл", 5)[0][0] == "files"
        assert database.section_ids() == ["files", "users"]


def test_query_embedding_cache(tmp_path: Path) -> None:
    path = tmp_path / "index.sqlite"
    with IndexDatabase.create(path, {"family": "3.1"}) as database:
        assert database.get_cached_query("ключ") is None
        database.cache_query("ключ", np.asarray([0.5, 0.25], dtype=np.float32))
        np.testing.assert_allclose(database.get_cached_query("ключ"), [0.5, 0.25])
