"""Генерация references навыка из очищенных статей и таблицы article-methods.json.

Запуск:
    python build_references.py <article-methods.json> <каталог references> <статья.md>...

Текст статей не меняется. Добавляется только разметка: строка метода становится
заголовком `####`, под ним - строка сверки с текущей версией БСП.
Отдельно пишется catalog.md: одна строка на метод, разделы по убыванию популярности.
"""
import json
import re
import sys
from pathlib import Path

TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p",
                     "r", "s", "t", "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))
RE_METHOD = re.compile(r"^(\d+)\. ([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*)\. (.*)$")
RE_SECTION = re.compile(r"^###\s+(.+)$")
STATUS_TEXT = {
    "deprecated": "устарел или исключен из программного интерфейса в 3.1.11, не использовать",
    "not_found": "в программном интерфейсе БСП 3.1.11 не найден (метод другой библиотеки), не использовать",
    "ambiguous": "одноименные методы в нескольких модулях, модуль выбирать по документации",
}


def slug(text: str) -> str:
    s = "".join(TRANSLIT.get(ch, ch) for ch in text.lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def context_code(ctx: list[str]) -> str:
    server = "server" in ctx or "externalConnection" in ctx
    client = "clientManagedApplication" in ctx
    code = "КС" if server and client else "С" if server else "К" if client else "?"
    return code + ("+ВызовСервера" if "serverCall" in ctx else "")


def signature(it: dict) -> str:
    return f"{it['module']}.{it['name']}({', '.join(it.get('params', []))})"


def annotation(it: dict) -> str:
    if it["status"] == "ok":
        return f"> 3.1.11: есть, контекст {context_code(it['context'])}, вызовов в типовых: {it['calls']}"
    extra = f" {it['replacement']}" if it.get("replacement") else ""
    return f"> 3.1.11: **{STATUS_TEXT[it['status']]}.**{extra}"


def first_sentence(text: str) -> str:
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    return m.group(1) if m else text


def main() -> None:
    items = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    by_key = {(i["section"], i["name"]): i for i in items}
    sections: dict[str, list[str]] = {}
    order: list[str] = []
    for article in sys.argv[3:]:
        text = Path(article).read_text(encoding="utf-8")
        source = re.search(r"Источник: (\S+)", text).group(1)
        section = None
        for line in text.splitlines():
            m = RE_SECTION.match(line)
            if m:
                section = m.group(1).strip()
                if section not in sections:
                    order.append(section)
                    sections[section] = [f"# {section}", "", f"Источник: {source} (БСП 3.1.4, сверено с 3.1.11)", ""]
                continue
            if section is None:
                continue
            m = RE_METHOD.match(line)
            it = by_key.get((section, m.group(2))) if m else None
            if it:
                title = signature(it) if it["status"] == "ok" else it["name"]
                sections[section] += [f"## {title}", "", annotation(it), "", m.group(3)]
            else:
                sections[section].append(line)
    files = {}
    for section in order:
        name = f"{slug(section)}.md"
        files[section] = name
        body = re.sub(r"\n{3,}", "\n\n", "\n".join(sections[section])).strip() + "\n"
        (out_dir / name).write_text(body, encoding="utf-8")

    lines = ["# Каталог методов БСП из статей", "",
             "Одна строка на метод: `Модуль.Метод(параметры)`, контекст, число вызовов в 5 типовых "
             "конфигурациях, описание. Контекст: С - сервер, К - клиент, КС - клиент и сервер.",
             "Подробности и примеры - в файле раздела.", ""]
    for section in sorted(order, key=lambda s: -max([i["calls"] for i in items if i["section"] == s] or [0])):
        rows = sorted((i for i in items if i["section"] == section), key=lambda i: -i["calls"])
        if not rows:
            continue
        lines += [f"## {section}", "", f"Файл: `references/{files[section]}`", ""]
        for i in rows:
            if i["status"] == "ok":
                lines.append(f"- `{signature(i)}` {context_code(i['context'])} ({i['calls']}): {first_sentence(i['description'])}")
            else:
                lines.append(f"- ~~{i['name']}~~ ({i['calls']}): {STATUS_TEXT[i['status']]}.")
        lines.append("")
    (out_dir / "catalog.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"разделов: {len(files)}, catalog.md: {len(lines)} строк")


if __name__ == "__main__":
    main()
