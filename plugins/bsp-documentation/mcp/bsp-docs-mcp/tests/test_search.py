from pathlib import Path

import numpy as np

from bsp_docs_mcp.parser import DocumentChunk
from bsp_docs_mcp.search import SearchEngine
from bsp_docs_mcp.storage import IndexDatabase


class FakeEmbedder:
    model = "fake-model"

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        assert texts
        return np.asarray([[1.0, 0.0]], dtype=np.float32)


def chunk(
    chunk_id: str, title: str, text: str, source_path: str = ""
) -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        source_version="3.1.11.155",
        anchor=chunk_id,
        title=title,
        breadcrumb=("БСП", title),
        text=text,
        part=1,
        has_recommendation="Рекомендуется" in text,
        has_warning=False,
        source_path=source_path,
    )


def create_index(path: Path) -> None:
    chunks = [
        chunk("semantic", "Работа с файлами", "Получение данных из хранилища"),
        chunk("lexical", "Файловые операции", "Точное редкое имя метода"),
        chunk("other", "Пользователи", "Учетные записи"),
    ]
    vectors = np.asarray([[1.0, 0.0], [0.7, 0.7], [0.0, 1.0]], dtype=np.float32)
    with IndexDatabase.create(
        path,
        {"family": "3.1", "source_version": "3.1.11.155", "model": "fake-model"},
    ) as database:
        database.add_chunks(chunks, vectors)


def test_hybrid_search_combines_dense_and_lexical_results(tmp_path: Path) -> None:
    path = tmp_path / "index.sqlite"
    create_index(path)
    engine = SearchEngine(path, FakeEmbedder())

    results = engine.search("точное редкое имя", limit=2)

    assert {result["id"] for result in results} == {"semantic", "lexical"}
    assert all(result["source_version"] == "3.1.11.155" for result in results)
    assert all("score" in result for result in results)


def test_search_caches_query_embedding(tmp_path: Path) -> None:
    path = tmp_path / "index.sqlite"
    create_index(path)
    engine = SearchEngine(path, FakeEmbedder())
    engine.search("получить файл")

    with IndexDatabase(path) as database:
        assert database.get_cached_query("fake-model\nполучить файл") is not None


def test_rejects_index_built_with_another_model(tmp_path: Path) -> None:
    path = tmp_path / "index.sqlite"
    with IndexDatabase.create(
        path, {"family": "3.1", "source_version": "3.1.1.1", "model": "other"}
    ):
        pass
    try:
        SearchEngine(path, FakeEmbedder())
    except ValueError as error:
        assert "other" in str(error)
    else:
        raise AssertionError("Expected model mismatch")


def test_development_mode_filters_before_hybrid_ranking(tmp_path: Path) -> None:
    path = tmp_path / "index.sqlite"
    chunks = [
        chunk(
            "api",
            "ЗагрузитьДанные",
            "Загрузка данных из файла",
            "Глава 4. Программный интерфейс/Загрузка данных из файла/Интерфейс/ЗагрузитьДанные.html",
        ),
        chunk(
            "override",
            "ПриЗагрузке",
            "Переопределение загрузки",
            "Глава 4. Программный интерфейс/Загрузка данных из файла/Переопределение/ПриЗагрузке.html",
        ),
        chunk(
            "manual",
            "Загрузка данных",
            "Пользовательская инструкция",
            "Глава 5. Пользовательская документация/Загрузка данных.html",
        ),
    ]
    vectors = np.asarray([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    with IndexDatabase.create(
        path,
        {"family": "3.1", "source_version": "3.1.11", "model": "fake-model"},
    ) as database:
        database.add_chunks(chunks, vectors)
    engine = SearchEngine(path, FakeEmbedder())

    development = engine.search(
        "загрузка данных",
        mode="development",
        subsystem="Загрузка данных из файла",
    )
    override = engine.search(
        "загрузка данных",
        mode="override",
        subsystem="Загрузка данных из файла",
    )

    assert [result["id"] for result in development] == ["api"]
    assert [result["id"] for result in override] == ["override"]
