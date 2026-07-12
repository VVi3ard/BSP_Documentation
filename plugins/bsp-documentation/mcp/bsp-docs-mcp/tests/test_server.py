from pathlib import Path

import pytest

from bsp_docs_mcp.config import Settings
from bsp_docs_mcp.server import Runtime
from bsp_docs_mcp.storage import IndexDatabase


def _create_index(tmp_path: Path, *, section_id: str = "section-1") -> Path:
    index_path = tmp_path / "indexes" / "3.1" / "index.sqlite"
    with IndexDatabase.create(
        index_path,
        {
            "family": "3.1",
            "source_version": "3.1.11",
            "model": "test",
            "chunk_count": "1",
        },
    ) as database:
        database.connection.execute(
            """INSERT INTO sections
               (id, source_version, anchor, source_path, title, breadcrumb, text, part,
                has_recommendation, has_warning, embedding, embedding_dim)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                section_id,
                "3.1.11",
                "target",
                "chapter/page.html",
                "Target",
                '["Chapter", "Target"]',
                "Normalized text from index",
                1,
                0,
                0,
                b"\x00\x00\x80?",
                1,
            ),
        )
        database.connection.execute(
            "INSERT INTO sections_fts(id, title, breadcrumb, text) VALUES (?, ?, ?, ?)",
            (section_id, "Target", "Chapter > Target", "Normalized text from index"),
        )
        database.connection.commit()
    return index_path


def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        openrouter_api_key=None,
        openrouter_base_url="https://example.invalid",
        embedding_model="test",
    )


def test_runtime_requires_existing_version_index(tmp_path: Path) -> None:
    runtime = Runtime(settings(tmp_path))
    with pytest.raises(FileNotFoundError, match="3.1"):
        runtime.get_section("3.1.11.155", "missing")


def test_list_versions_reads_index_directories(tmp_path: Path) -> None:
    (tmp_path / "indexes" / "3.1").mkdir(parents=True)
    (tmp_path / "indexes" / "3.1" / "index.sqlite").touch()
    (tmp_path / "indexes" / "3.2").mkdir(parents=True)
    (tmp_path / "indexes" / "3.2" / "index.sqlite").touch()
    runtime = Runtime(settings(tmp_path))
    assert runtime.list_versions() == ["3.1", "3.2"]


def test_list_api_sections_reads_versioned_navigation(tmp_path: Path) -> None:
    _create_index(tmp_path)
    navigation_dir = tmp_path / "navigation" / "3.1.11"
    navigation_dir.mkdir(parents=True)
    (navigation_dir / "program-interface.json").write_text(
        '{"schema_version":1,"source_version":"3.1.11","root":"Глава 4. Программный интерфейс","sections":[{"name":"Загрузка данных из файла","source_path":"Глава 4. Программный интерфейс/Загрузка данных из файла","kinds":["Интерфейс"],"method_count":1}]}',
        encoding="utf-8",
    )

    result = Runtime(settings(tmp_path)).list_api_sections("3.1.11.155")

    assert result["index_source_version"] == "3.1.11"
    assert result["sections"][0]["name"] == "Загрузка данных из файла"


def test_get_source_section_reads_markdown_from_sources(tmp_path: Path) -> None:
    _create_index(tmp_path)
    source_dir = tmp_path / "sources" / "3.1.11" / "chapter"
    source_dir.mkdir(parents=True)
    (source_dir / "page.html").write_text(
        "<h1>Target</h1><p><strong>Original</strong> source page.</p>",
        encoding="utf-8",
    )

    runtime = Runtime(settings(tmp_path))
    result = runtime.get_source_section("3.1.11.155", "section-1")

    assert result["section"]["text"] == "Normalized text from index"
    assert result["source_document"]["format"] == "markdown"
    assert "# Target" in result["source_document"]["content"]
    assert "**Original** source page." in result["source_document"]["content"]


def test_get_source_section_supports_html_format(tmp_path: Path) -> None:
    _create_index(tmp_path)
    source_dir = tmp_path / "sources" / "3.1.11" / "chapter"
    source_dir.mkdir(parents=True)
    html = "<h1>Target</h1><p>Original source page.</p>"
    (source_dir / "page.html").write_text(html, encoding="utf-8")

    runtime = Runtime(settings(tmp_path))
    result = runtime.get_source_section("3.1.11.155", "section-1", format="html")

    assert result["source_document"] == {
        "format": "html",
        "content": html,
        "path": "chapter/page.html",
    }


def test_get_source_section_rejects_unknown_format(tmp_path: Path) -> None:
    _create_index(tmp_path)
    source_dir = tmp_path / "sources" / "3.1.11" / "chapter"
    source_dir.mkdir(parents=True)
    (source_dir / "page.html").write_text("<p>Original source page.</p>", encoding="utf-8")

    runtime = Runtime(settings(tmp_path))
    with pytest.raises(ValueError, match="format"):
        runtime.get_source_section("3.1.11.155", "section-1", format="xml")


def test_detect_bsp_version_falls_back_to_legacy_file_name(tmp_path: Path) -> None:
    root = tmp_path / "project"
    primary_dir = root / "Configuration" / "src" / "Configuration"
    primary_dir.mkdir(parents=True)
    (primary_dir / "Configuration.distr").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<distributionSupport:DistributionSupport xmlns:distributionSupport="http://g5.1c.ru/v8/dt/distribution/model" version="6" updateAvailable="true">
  <parentConfigurationInfos configRelease="3.1.12.200" configName="БиблиотекаСтандартныхПодсистем"/>
</distributionSupport:DistributionSupport>
""",
        encoding="utf-8",
    )

    legacy_dir = root / "Configuration" / "src" / "Configuration"
    (legacy_dir / "ParentConfigurations.bin").write_text(
        '{6,0,"3.1.11.155","БиблиотекаСтандартныхПодсистем"}',
        encoding="utf-8",
    )

    from bsp_docs_mcp.server import detect_bsp_version

    result = detect_bsp_version(str(root))

    assert result["full_version"] == "3.1.12.200"
    assert result["index_family"] == "3.1"


def test_detect_bsp_version_uses_legacy_file_when_distribution_support_is_missing(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    legacy_dir = root / "Configuration" / "src" / "Configuration"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "ParentConfigurations.bin").write_text(
        '{6,0,"3.1.11.155","БиблиотекаСтандартныхПодсистем"}',
        encoding="utf-8",
    )

    from bsp_docs_mcp.server import detect_bsp_version

    result = detect_bsp_version(str(root))

    assert result["full_version"] == "3.1.11.155"
    assert result["index_family"] == "3.1"
