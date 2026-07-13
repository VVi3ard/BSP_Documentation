# Архитектура

## Граница plugin

Репозиторий является Codex marketplace с одним устанавливаемым plugin:

```text
.agents/plugins/marketplace.json
└── plugins/bsp-documentation/
    ├── .codex-plugin/plugin.json
    ├── .mcp.json
    ├── skills/bsp-development/
    ├── mcp/bsp-docs-mcp/
    ├── data/
    │   ├── indexes/
    │   ├── navigation/
    │   ├── sources/
    │   └── demo/
    └── scripts/run_bsp_mcp.py
```

`plugin.json` регистрирует skill, а `.mcp.json` — bundled stdio MCP-сервер.

## Данные

Корень plugin владеет всеми read-only данными БСП. Совместимые версии документации, индекса, навигации и демо записаны в `data/manifest.json`.

Runner передаёт этот каталог через `BSP_DOCS_DATA_DIR`; MCP не зависит от абсолютного пути установки.

## Runtime-окружение

`scripts/run_bsp_mcp.py` при первом старте создаёт отдельное виртуальное окружение. По умолчанию оно находится в `%LOCALAPPDATA%\BSP_Documentation\venv`; для изменения используйте `BSP_DOCUMENTATION_RUNTIME_DIR`.

Поставляемые индекс и исходники демо не меняются. Зависимости и временные данные находятся вне установленного plugin.

`.mcp.json` передаёт в stdio-процесс только `OPENROUTER_API_KEY`; секрет хранится в пользовательском окружении, а не в plugin. После установки или ротации ключа Codex требуется перезапустить.

SQLite-индекс хранит идентификатор embedding-модели в таблице metadata. При создании `SearchEngine` runtime сравнивает его с `embedder.model` точным строковым сравнением, а перед dense search отдельно проверяет размерность query vector. Поставляемый индекс использует `qwen/qwen3-embedding-8b`. Другой provider endpoint или модель с тем же размером вектора не считаются совместимыми. Изменение модели — операция сборки данных: нужно полностью пересоздать индекс и поставить его вместе с согласованной конфигурацией.

## Доступ к демо

`get_bsp_demo_location(version)` возвращает реальный каталог bundled EDT-конфигурации подходящего релиза. Агент выполняет поиск по нему сам, сохраняя полный контекст кода и UI, а не получает заранее построенные карточки примеров.
