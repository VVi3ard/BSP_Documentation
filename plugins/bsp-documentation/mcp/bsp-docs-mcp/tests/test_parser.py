from bsp_docs_mcp.parser import parse_html


HTML = """
<h1 id="chapter">Глава</h1>
<p>Введение.</p>
<h2 id="files">Работа с файлами</h2>
<p>Рекомендуется использовать программный интерфейс.</p>
<pre><code>Файл = РаботаСФайлами.ПолучитьФайл();</code></pre>
<h3 id="legacy">Старый способ</h3>
<p>Не рекомендуется вызывать этот метод.</p>
"""


def test_parses_hierarchy_code_and_flags() -> None:
    chunks = parse_html(HTML, "3.1.11.155", max_chars=10_000)
    files = next(chunk for chunk in chunks if chunk.anchor == "files")
    legacy = next(chunk for chunk in chunks if chunk.anchor == "legacy")

    assert files.breadcrumb == ("Глава", "Работа с файлами")
    assert "РаботаСФайлами.ПолучитьФайл" in files.text
    assert files.has_recommendation is True
    assert files.has_warning is False
    assert legacy.breadcrumb == ("Глава", "Работа с файлами", "Старый способ")
    assert legacy.has_warning is True


def test_ids_are_deterministic_and_include_source_version() -> None:
    first = parse_html(HTML, "3.1.11.155")
    second = parse_html(HTML, "3_1_11_155")
    other = parse_html(HTML, "3.2.1.1")

    assert [item.id for item in first] == [item.id for item in second]
    assert first[0].id != other[0].id
    assert first[0].source_version == "3.1.11.155"


def test_splits_large_sections_without_losing_breadcrumb() -> None:
    html = '<h1 id="large">Большой раздел</h1>' + "".join(
        f"<p>Абзац {number}: " + ("текст " * 20) + "</p>" for number in range(12)
    )
    chunks = parse_html(html, "3.1.11.155", max_chars=300)

    assert len(chunks) > 1
    assert all(chunk.breadcrumb == ("Большой раздел",) for chunk in chunks)
    assert [chunk.part for chunk in chunks] == list(range(1, len(chunks) + 1))


def test_adds_filesystem_breadcrumb_without_duplicate_page_title() -> None:
    chunks = parse_html(
        '<h1>ПолучитьФайл</h1><p>Описание программного интерфейса.</p>',
        "3.1.11",
        source_path="Глава 4/Работа с файлами/Интерфейс/ПолучитьФайл.html",
        base_breadcrumb=("Глава 4", "Работа с файлами", "Интерфейс", "ПолучитьФайл"),
    )

    assert chunks[0].source_path.endswith("ПолучитьФайл.html")
    assert chunks[0].breadcrumb == (
        "Глава 4",
        "Работа с файлами",
        "Интерфейс",
        "ПолучитьФайл",
    )
    assert "Source: Глава 4/Работа с файлами" in chunks[0].embedding_text


def test_source_path_participates_in_stable_id() -> None:
    first = parse_html(HTML, "3.1.11", source_path="one/page.html")
    second = parse_html(HTML, "3.1.11", source_path="two/page.html")
    assert first[0].id != second[0].id
