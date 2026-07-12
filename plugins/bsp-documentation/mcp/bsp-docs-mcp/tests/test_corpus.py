from pathlib import Path

from bsp_docs_mcp.corpus import discover_html_pages


def write(path: Path, text: str = "<h1>Page</h1><p>Text</p>") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_discovers_pages_and_skips_aggregate_index(tmp_path: Path) -> None:
    write(tmp_path / "Глава 1" / "index.html")
    write(tmp_path / "Глава 2" / "index.html")
    write(tmp_path / "Глава 2" / "Раздел" / "Метод.html")
    write(tmp_path / "Глава 3" / "Страница.html")

    pages = discover_html_pages(tmp_path)

    assert [page.source_path for page in pages] == [
        "Глава 1/index.html",
        "Глава 2/Раздел/Метод.html",
        "Глава 3/Страница.html",
    ]
    assert pages[0].breadcrumb == ("Глава 1",)
    assert pages[1].breadcrumb == ("Глава 2", "Раздел")


def test_discovery_is_case_insensitive_for_html_and_index(tmp_path: Path) -> None:
    write(tmp_path / "Chapter" / "INDEX.HTML")
    pages = discover_html_pages(tmp_path)
    assert [page.source_path for page in pages] == ["Chapter/INDEX.HTML"]


def test_rejects_missing_or_empty_corpus(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    try:
        discover_html_pages(missing)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Expected missing corpus error")

    try:
        discover_html_pages(tmp_path)
    except ValueError as error:
        assert "HTML" in str(error)
    else:
        raise AssertionError("Expected empty corpus error")

