# Доступность навыка и MCP

## Что доступно

- Навык `bsp-documentation:bsp-development` загружен из установленного плагина версии `0.1.0`.
- `codex plugin list` показывает установленный и включенный плагин.
- `codex mcp list` показывает включенный сервер `bsp_documentation` с запуском `scripts/run_bsp_mcp.py`.
- В исходниках сервера объявлены необходимые инструменты: `detect_bsp_version`, `discover_bsp_api_sections`, `get_bsp_api_section_map`, `search_bsp`, `get_bsp_section`, `get_bsp_demo_location`.

## Что недоступно агенту

Проверка текущего набора callable tools по именам BSP вернула пустой список:

```text
[]
```

Тот же результат получил read-only субагент. Поэтому штатно вызвать BSP MCP из этого прогона нельзя.

## Вывод

Навык и регистрация сервера видимы, но capability MCP не попала в инструментальный контекст задачи. Это отдельная проблема от качества карт и поиска.
