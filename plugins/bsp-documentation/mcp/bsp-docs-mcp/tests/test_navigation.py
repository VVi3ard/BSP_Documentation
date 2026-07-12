from pathlib import Path

from bsp_docs_mcp.navigation import build_api_navigation, load_api_navigation


def test_builds_and_loads_program_interface_navigation(tmp_path: Path) -> None:
    root = tmp_path / "sources" / "Глава 4. Программный интерфейс"
    (root / "Загрузка данных из файла" / "Интерфейс").mkdir(parents=True)
    (root / "Загрузка данных из файла" / "Интерфейс" / "Загрузить.html").write_text(
        "<h1>Загрузить</h1>", encoding="utf-8"
    )
    (root / "Печать" / "Переопределение").mkdir(parents=True)

    data_dir = tmp_path / "data"
    output = data_dir / "navigation" / "3.1.11" / "program-interface.json"
    result = build_api_navigation(tmp_path / "sources", "3.1.11", output)

    assert [section["name"] for section in result["sections"]] == [
        "Загрузка данных из файла",
        "Печать",
    ]
    assert result["sections"][0]["kinds"] == ["Интерфейс"]
    assert result["sections"][0]["method_count"] == 1
    assert load_api_navigation(data_dir, "3.1.11") == result
