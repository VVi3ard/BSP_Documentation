"""Разбор очищенных статей в таблицу методов и сверка с индексом API БСП.

Запуск:
    python extract_article_methods.py <api-index.json> <выход.json> <статья.md>...

Формат статьи: разделы - заголовки `###`, метод - строка
`<число вызовов>. <ИмяМетода>. <Описание>`, дальше до следующего метода - пояснения и
блоки ```bsl```. Модуль берется из примеров (`Модуль.ИмяМетода(`); если в примерах
его нет - из индекса, где метод найден в области ПрограммныйИнтерфейс.

status:
  ok          - найден в ПрограммныйИнтерфейс, не устарел;
  deprecated  - в текущей версии помечен «Устарела» (см. replacement);
  ambiguous   - одноименные методы в нескольких модулях, модуль в статье не указан;
  not_found   - в ПрограммныйИнтерфейс текущей версии нет.
"""
import json
import re
import sys
from pathlib import Path

RE_METHOD = re.compile(r"^(\d+)\. ([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*)\. (.*)$")
RE_SECTION = re.compile(r"^###\s+(.+)$")
# Ручное разрешение неоднозначностей: имя метода -> модуль (сверено по документации).
MODULE_OVERRIDES = {
    "ЗагрузитьФайл": "ФайловаяСистемаКлиент",  # ФайлыОбластейДанных - библиотека БТС
}


def parse_article(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    title = text.splitlines()[0].lstrip("# ").strip()
    items, section, current = [], "", None
    for line in text.splitlines():
        if line.startswith("```"):
            pass
        m = RE_SECTION.match(line)
        if m:
            section = m.group(1).strip()
            current = None
            continue
        m = RE_METHOD.match(line)
        if m:
            current = {"article": title, "section": section, "calls": int(m.group(1)),
                       "name": m.group(2), "description": m.group(3).strip(), "body": []}
            items.append(current)
            continue
        if current is not None:
            current["body"].append(line)
    return items


def resolve(item: dict, by_name: dict) -> None:
    body = "\n".join(item.pop("body"))
    item["example_modules"] = sorted(set(re.findall(rf"(\w+)\.{item['name']}\s*\(", body)))
    cands = [c for c in by_name.get(item["name"], []) if c["region"] == "ПрограммныйИнтерфейс"
             and "Служебн" not in c["module"]]
    if item["name"] in MODULE_OVERRIDES:
        cands = [c for c in cands if c["module"] == MODULE_OVERRIDES[item["name"]]]
    elif item["example_modules"]:
        preferred = [c for c in cands if c["module"] in item["example_modules"]]
        cands = preferred or cands
    item["candidates"] = [c["module"] for c in cands]
    live = [c for c in cands if not c["deprecated"]]
    if not cands:
        item["status"], item["module"] = "not_found", ""
    elif not live:
        item["status"], item["module"] = "deprecated", cands[0]["module"]
        item["replacement"] = cands[0]["summary"]
        # Тот же метод мог остаться в программном интерфейсе другого модуля.
        alive = [c["module"] for c in by_name.get(item["name"], []) if c["region"] == "ПрограммныйИнтерфейс"
                 and not c["deprecated"] and "Служебн" not in c["module"]]
        if alive:
            item["replacement"] += " Актуальный вызов: " + ", ".join(f"{m}.{item['name']}" for m in alive) + "."
    elif len({c["module"] for c in live}) > 1 and not item["example_modules"]:
        item["status"], item["module"] = "ambiguous", live[0]["module"]
    else:
        item["status"], item["module"] = "ok", live[0]["module"]
    if item["status"] in ("ok", "ambiguous"):
        c = live[0]
        item.update(params=c["params"], context=c["context"], subregion=c["subregion"],
                    summary_3_1_11=c["summary"])


def main() -> None:
    api = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    by_name: dict[str, list] = {}
    for m in api:
        by_name.setdefault(m["name"], []).append(m)
    items = []
    for p in sys.argv[3:]:
        items += parse_article(Path(p))
    for it in items:
        resolve(it, by_name)
    Path(sys.argv[2]).write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(len(items), Counter(i["status"] for i in items))


if __name__ == "__main__":
    main()
