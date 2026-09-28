"""Самопроверка правил хука.

Запуск:
    python check_antipatterns.py <antipatterns.json> <bsp-api-index.json> [<каталог src для замера>]

1. Каждое правило срабатывает на примере bad и не срабатывает на good.
2. Каждый метод из suggest (кроме «платформа:») есть в индексе актуального API.
3. С каталогом src: число срабатываний каждого правила по *.bsl - для калибровки шума.
Код возврата 1, если пункт 1 или 2 не выполнен.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

FLAGS = re.IGNORECASE | re.MULTILINE
RE_METHOD = re.compile(r"^\s*(?:Асинх\s+)?(?:Функция|Процедура)\s", FLAGS)
RE_DIRECTIVE = re.compile(r"^\s*&(НаКлиенте|НаСервере|НаСервереБезКонтекста|НаКлиентеНаСервереБезКонтекста"
                          r"|НаКлиентеНаСервере)\b", FLAGS)


def context_at(path: Path, text: str, pos: int) -> str:
    """client | server | both - где исполняется код в позиции pos.

    Образец для хука: директива метода важнее вида модуля; общий модуль
    определяется по суффиксу имени (соглашение БСП), модули объектов - сервер.
    """
    head = text[:pos]
    starts = list(RE_METHOD.finditer(head))
    if starts:
        before = head[:starts[-1].start()].rstrip().splitlines()[-1:] or [""]
        m = RE_DIRECTIVE.match(before[0])
        if m:
            d = m.group(1).lower()
            return "both" if "наклиентенасервере" in d else "client" if d == "наклиенте" else "server"
    parts = path.parts
    if "CommonModules" in parts:
        name = parts[parts.index("CommonModules") + 1]
        if name.endswith("КлиентСервер"):
            return "both"
        if name.endswith(("Клиент", "КлиентГлобальный")):
            return "client"
        return "server"
    if "CommandModule.bsl" in parts[-1]:
        return "client"
    return "server"


def applies(rule: dict, ctx: str) -> bool:
    return rule["context"] == "any" or ctx == "both" or rule["context"] == ctx


def main() -> None:
    rules = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["rules"]
    api = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    known = {f"{m['module']}.{m['name']}" for m in api}
    errors = []
    for r in rules:
        rx = re.compile(r["pattern"], FLAGS)
        if not rx.search(r["bad"]):
            errors.append(f"{r['id']}: не срабатывает на bad")
        if rx.search(r["good"]):
            errors.append(f"{r['id']}: срабатывает на good")
        for s in r["suggest"]:
            if not s.startswith("платформа:") and s not in known:
                errors.append(f"{r['id']}: {s} нет в актуальном API")
    print("\n".join(errors) or f"правил: {len(rules)}, ошибок нет")
    if len(sys.argv) > 3:
        hits: Counter = Counter()
        files: Counter = Counter()
        for p in Path(sys.argv[3]).rglob("*.bsl"):
            text = p.read_text(encoding="utf-8-sig", errors="replace")
            for r in rules:
                n = sum(applies(r, context_at(p, text, m.start()))
                        for m in re.finditer(r["pattern"], text, FLAGS))
                if n:
                    hits[r["id"]] += n
                    files[r["id"]] += 1
        for r in rules:
            print(f"{r['id']} {hits[r['id']]:6} совп. в {files[r['id']]:4} файлах  {r['title']}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
