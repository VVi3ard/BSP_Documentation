# Получение `manifest.json` и сырых HTML через `crawl_its.py`

`crawl_its.py` — это первый этап выгрузки ИТС. Он не использует LLM. Скрипт:

- открывает стартовую страницу ИТС по обычному HTTP;
- обходит внутренние HTML-страницы того же раздела;
- сохраняет сырые страницы в `pages/*.html`;
- пишет `manifest.json`;
- поддерживает повторный запуск без повторной загрузки уже сохраненных страниц.

Именно этот `manifest.json` потом использует [exporter.py](/C:/Users/volos/.codex/mcp/bsp-docs-mcp/src/bsp_docs_mcp/exporter.py).

## Что нужно для работы

- доступ к ИТС из браузера или уже известные cookies;
- Python-окружение проекта;
- стартовая ссылка вида:
  - `https://its.1c.ru/db/content/bsp3111doc/src/...htm#_print`
  - или старый вариант `https://its.1c.ru/db/bsp3111doc/content/src/...htm_`

Если ИТС требует авторизацию, скрипту нужно передать cookies. Самый простой путь — экспортировать их в JSON.

## Формат cookies JSON

Поддерживаются два варианта.

Объект:

```json
{
  "ITSUser": "value",
  "JSESSIONID": "value"
}
```

Или массив:

```json
[
  {"name": "ITSUser", "value": "value"},
  {"name": "JSESSIONID", "value": "value"}
]
```

## Быстрый запуск

Из корня репозитория:

```powershell
.\.venv\Scripts\python.exe .\crawl_its.py `
  --start-url "https://its.1c.ru/db/content/bsp3111doc/src/%D0%B3%D0%BB%D0%B0%D0%B2%D0%B0%204.%20%D0%BF%D1%80%D0%BE%D0%B3%D1%80%D0%B0%D0%BC%D0%BC%D0%BD%D1%8B%D0%B9%20%D0%B8%D0%BD%D1%82%D0%B5%D1%80%D1%84%D0%B5%D0%B9%D1%81.htm#_print" `
  --output ".\.tmp\bsp3111-crawl" `
  --cookies-json ".\cookies.json" `
  --delay 0.2
```

Результат:

```text
.tmp\bsp3111-crawl\
  manifest.json
  pages\
    0001.html
    0002.html
    ...
```

## Повторный запуск

Если `manifest.json` уже существует, скрипт:

- не скачивает заново страницы со статусом `ok`, если соответствующий файл еще на месте;
- продолжает обход по уже найденным дочерним ссылкам;
- докачивает недостающие страницы;
- повторяет только страницы с ошибками.

То есть для продолжения достаточно повторно вызвать ту же команду.

## Параметры

- `--start-url` — стартовая страница ИТС.
- `--output` — каталог, где будут лежать `manifest.json` и `pages/`.
- `--cookies-json` — JSON-файл с cookies.
- `--cookie NAME=VALUE` — cookie прямо в командной строке; можно повторять.
- `--header NAME=VALUE` — дополнительный HTTP-заголовок; можно повторять.
- `--timeout` — таймаут HTTP-запроса в секундах, по умолчанию `30`.
- `--delay` — задержка между запросами, по умолчанию `0`.
- `--max-pages` — ограничение на число новых скачанных страниц за запуск.

## Структура `manifest.json`

Файл содержит:

- `startUrl` — исходная точка обхода;
- `allowedRoot` — ограничение области обхода;
- `pages` — словарь страниц по URL.

Для каждой страницы обычно есть:

- `status` — `ok` или `error`;
- `title` — заголовок страницы;
- `file` — относительный путь к сырому HTML;
- `parent` — родительская страница, если известна;
- `children` — найденные дочерние ссылки;
- `fetchedAt` / `lastTriedAt`.

## Как связать с `exporter.py`

После завершения crawl:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -c @'
from pathlib import Path
from bsp_docs_mcp.exporter import export_crawl_manifest

manifest = Path(r".tmp\bsp3111-crawl\manifest.json")
output = Path(r"data\sources\3.1.11")
result = export_crawl_manifest(manifest, output)
print(f"Exported {result['pages']} pages into {output}")
'@
```

## Что важно понимать

- Скрипт работает обычным Python и HTTP, токены LLM на обход страниц не тратятся.
- Скрипт не удаляет сырые HTML.
- Скрипт ограничивает обход текущим разделом ИТС и сохраняет только HTML-страницы документации.
