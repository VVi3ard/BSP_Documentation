"""Прототип правила «новый метод похож на метод БСП» и замер на существующем коде.

Запуск:
    python similar_names_probe.py <bsp-api-index.json> <article-methods.json> <каталог src> [порог] [--popular]

Алгоритм (тот же описан в hook/HOOK-SPEC.md, часть D):
1. Имя разбивается на слова по заглавным буквам: ЗначениеРеквизитаОбъекта -> значение, реквизита, объекта.
2. Каждое слово сводится к основе: первые 5 букв (грубый стемминг без словарей).
   Стоп-основы (получ, устан, вычис, запол, выпол, данны, парам, значе ...) не считаются.
   Имена обработчиков событий (При..., Перед..., После..., Обработка..., Подключаемый_...)
   не проверяются и не предлагаются.
3. Похожесть = |общие основы| / |основы нового имени|; нужно >= 2 общих значимых основ.
4. Кандидаты БСП: только ПрограммныйИнтерфейс; популярные методы из статей идут первыми.
"""
import json
import re
import sys
from pathlib import Path

RE_DECL = re.compile(r"^\s*(?:Асинх\s+)?(?:Функция|Процедура)\s+([А-Яа-яЁёA-Za-z_]\w*)\s*\(", re.M | re.I)
STOP = {"получ", "устан", "вычис", "запол", "выпол", "данны", "парам", "значе", "обраб", "прове",
        "новый", "новая", "новое", "текущ", "серве", "клиен", "форма", "формы", "форме", "коман",
        "объек", "докум", "справ", "регис", "строк", "табли", "запис", "table", "get", "set"}
# Обработчики событий и подключаемые команды: имя задано платформой или БСП, это не велосипед.
RE_HANDLER = re.compile(r"^(?:При|Перед|После|Обработка|Подключаемый_|Начало|Окончание)[А-ЯЁA-Z_]")


def stems(name: str) -> set[str]:
    words = re.findall(r"[А-ЯЁA-Z][а-яёa-z0-9]*", name)
    return {w.lower()[:5] for w in words if len(w) >= 3} - STOP


def main() -> None:
    api = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    calls = {f"{i['module']}.{i['name']}": i["calls"]
             for i in json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")) if i["status"] == "ok"}
    src = Path(sys.argv[3])
    args = [a for a in sys.argv[4:] if not a.startswith("--")]
    threshold = float(args[0]) if args else 0.67
    index = [(f"{m['module']}.{m['name']}", stems(m["name"])) for m in api
             if not RE_HANDLER.match(m["name"])]
    if "--popular" in sys.argv:  # кандидаты только из каталога статей
        index = [x for x in index if x[0] in calls]
    total = hits = 0
    samples = []
    for p in src.rglob("*.bsl"):
        for name in RE_DECL.findall(p.read_text(encoding="utf-8-sig", errors="replace")):
            s = stems(name)
            if RE_HANDLER.match(name) or len(s) < 2:
                continue
            total += 1
            best = []
            for full, st in index:
                common = s & st
                if len(common) >= 2 and len(common) / len(s) >= threshold:
                    best.append((len(common) / len(s), calls.get(full, 0), full))
            if best:
                hits += 1
                best.sort(reverse=True)
                samples.append((name, [b[2] for b in best[:3]]))
    print(f"порог {threshold}: имен {total}, с подсказкой {hits} ({hits / max(total, 1):.1%})")
    for name, cands in samples[:25]:
        print(f"  {name} -> {', '.join(cands)}")


if __name__ == "__main__":
    main()
