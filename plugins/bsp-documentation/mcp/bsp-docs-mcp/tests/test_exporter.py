from pathlib import Path

import json

from bsp_docs_mcp.exporter import export_chapter_tree, export_crawl_manifest


HTML = """
<html><body>
<h1 id="root">Глава 1. Состав библиотеки</h1>
<p>Вступление <a href="#local">внутренняя ссылка</a>.</p>
<p><a href="https://its.1c.ru/db/bsp3111doc/content/2/hdoc">Следующая глава</a></p>
<h2 id="local">Локальный раздел</h2>
<p>Текст.</p>
<h1 id="second">Глава 2. Инструкция по внедрению библиотеки</h1>
<p>Продолжение.</p>
</body></html>
"""


def test_exports_clean_chapter_tree_with_russian_names(tmp_path: Path) -> None:
    source = tmp_path / "Документация.html"
    source.write_text(HTML, encoding="utf-8")

    pages = export_chapter_tree(source, tmp_path / "3.1.11")

    assert [page.title for page in pages] == [
        "Глава 1. Состав библиотеки",
        "Глава 2. Инструкция по внедрению библиотеки",
    ]
    assert pages[0].path == tmp_path / "3.1.11" / "Глава 1. Состав библиотеки" / "index.html"
    assert pages[1].path == tmp_path / "3.1.11" / "Глава 2. Инструкция по внедрению библиотеки" / "index.html"

    first = pages[0].path.read_text(encoding="utf-8")
    assert "<script" not in first
    assert "Глава 1. Состав библиотеки" in first
    assert 'href="#local"' in first
    assert 'href="https://its.1c.ru/db/bsp3111doc/content/2/hdoc"' in first
    assert "html/html" not in first
    assert ".155" not in str(pages[0].path)


def test_removes_subsystem_filters_and_materializes_table_numbers(tmp_path: Path) -> None:
    source = tmp_path / "Документация.html"
    source.write_text(
        """
        <html><body>
        <h1>Глава 1. Состав библиотеки</h1>
        <div class="filter_place">
          <form><div class="selectBoxName">Фильтр подсистем</div></form>
          <section class="filtered_tab">
            <table>
              <tr><th>№</th><th>Подсистема</th></tr>
              <tr><td><ol class="n"><li></li></ol></td><td>Первая</td></tr>
              <tr><td><ol class="n"><li></li></ol></td><td>Вторая</td></tr>
              <tr><td><ol class="n"><li></li></ol></td><td>Третья</td></tr>
            </table>
          </section>
        </div>
        </body></html>
        """,
        encoding="utf-8",
    )

    [page] = export_chapter_tree(source, tmp_path / "3.1.11")
    exported = page.path.read_text(encoding="utf-8")

    assert "Фильтр подсистем" not in exported
    assert '<td class="row-number">1</td>' in exported
    assert '<td class="row-number">2</td>' in exported
    assert '<td class="row-number">3</td>' in exported
    assert '<ol class="n">' not in exported


def test_exports_crawl_with_unique_paths_and_local_links(tmp_path: Path) -> None:
    crawl = tmp_path / "crawl"
    pages_dir = crawl / "pages"
    pages_dir.mkdir(parents=True)
    first_url = "https://its.1c.ru/db/content/bsp3111doc/src/first.htm#_print"
    second_url = "https://its.1c.ru/db/content/bsp3111doc/src/second.htm#_print"
    (pages_dir / "first.html").write_text(
        '<html><body><h1>Интерфейс</h1><a href="second.htm_">Далее</a></body></html>',
        encoding="utf-8",
    )
    (pages_dir / "second.html").write_text(
        '<html><body><h1>Интерфейс</h1><p>Вторая статья</p></body></html>',
        encoding="utf-8",
    )
    (crawl / "manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "pages": {
                    first_url: {"status": "ok", "title": "Интерфейс", "file": "pages/first.html"},
                    second_url: {"status": "ok", "title": "Интерфейс", "file": "pages/second.html"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = export_crawl_manifest(crawl / "manifest.json", tmp_path / "output")

    assert result["pages"] == 2
    paths = [Path(item["path"]) for item in result["items"]]
    assert len(set(paths)) == 2
    first = (tmp_path / "output" / paths[0]).read_text(encoding="utf-8")
    assert "https://its.1c.ru/db/content/bsp3111doc/src/second.htm_" not in first
    assert "Далее" in first


def test_exports_crawl_using_source_index_hierarchy(tmp_path: Path) -> None:
    crawl = tmp_path / "crawl"
    pages_dir = crawl / "pages"
    pages_dir.mkdir(parents=True)
    urls = {
        "chapter": "https://its.1c.ru/db/content/bsp3111doc/src/chapter.htm#_print",
        "subsystem": "https://its.1c.ru/db/content/bsp3111doc/src/subsystem.htm#_print",
        "interface": "https://its.1c.ru/db/content/bsp3111doc/src/interface.htm#_print",
        "method": "https://its.1c.ru/db/content/bsp3111doc/src/method.htm#_print",
    }
    fixtures = {
        "chapter": (
            "Глава 4. Программный интерфейс",
            '<div class="index"><a href="subsystem.htm_">Адресный классификатор</a></div>',
        ),
        "subsystem": (
            "Адресный классификатор",
            '<div class="index"><a href="interface.htm_">Интерфейс</a></div>',
        ),
        "interface": (
            "Интерфейс",
            '<div class="index"><a href="method.htm_">АдресныйКлассификаторЗагружен</a></div>',
        ),
        "method": ("АдресныйКлассификаторЗагружен", "<p>Описание метода</p>"),
    }
    manifest_pages = {}
    for key, (title, content) in fixtures.items():
        file_name = f"{key}.html"
        (pages_dir / file_name).write_text(
            f"<html><body><h1>{title}</h1>{content}</body></html>",
            encoding="utf-8",
        )
        manifest_pages[urls[key]] = {
            "status": "ok",
            "title": title,
            "file": f"pages/{file_name}",
        }
    (crawl / "manifest.json").write_text(
        json.dumps({"schemaVersion": 1, "pages": manifest_pages}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = export_crawl_manifest(crawl / "manifest.json", tmp_path / "output")

    paths = {item["title"]: item["path"] for item in result["items"]}
    base = "Глава 4. Программный интерфейс/Адресный классификатор/Интерфейс"
    assert paths["Глава 4. Программный интерфейс"] == "Глава 4. Программный интерфейс/index.html"
    assert paths["Адресный классификатор"] == "Глава 4. Программный интерфейс/Адресный классификатор/index.html"
    assert paths["Интерфейс"] == f"{base}/index.html"
    assert paths["АдресныйКлассификаторЗагружен"] == f"{base}/АдресныйКлассификаторЗагружен.html"
