"""Индекс экспортного API общих модулей БСП из исходников EDT.

Запуск:
    python build_bsp_api_index.py <каталог src> <выход.json> [--full]

Без --full пишется компактный индекс для навыка и хука: только ПрограммныйИнтерфейс,
без устаревших, служебных, *Переопределяемый и *Локализация. С --full - все
экспортные методы (нужен extract_article_methods.py, чтобы распознавать устаревшие).

Каталог src - корень выгрузки EDT (содержит CommonModules). Годится и демо БСП,
и сама целевая конфигурация: тогда индекс точно совпадает с версией БСП проекта.

Для каждого экспортного метода общего модуля пишется:
module, name, kind (Функция/Процедура), params, region (верхняя область),
subregion (вложенные области), deprecated, context (флаги модуля), summary
(первая строка комментария-описания).
"""
import json
import re
import sys
from pathlib import Path

RE_REGION = re.compile(r"^\s*#Область\s+(\S+)", re.I)
RE_END_REGION = re.compile(r"^\s*#КонецОбласти", re.I)
RE_METHOD_START = re.compile(
    r"^\s*(?:Асинх\s+)?(Функция|Процедура)\s+([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*)\s*\(", re.I)
RE_SIGNATURE_TAIL = re.compile(r"\)\s*(Экспорт)?", re.I)
CONTEXT_FLAGS = ("server", "clientManagedApplication", "clientOrdinaryApplication",
                 "externalConnection", "serverCall", "privileged", "global")


def module_context(mdo: Path) -> list[str]:
    if not mdo.exists():
        return []
    text = mdo.read_text(encoding="utf-8", errors="replace")
    return [f for f in CONTEXT_FLAGS if re.search(rf"<{f}>true</{f}>", text)]


def comment_block(lines: list[str], idx: int) -> list[str]:
    out = []
    i = idx - 1
    while i >= 0 and lines[i].strip().startswith("//"):
        out.append(lines[i].strip()[2:].strip())
        i -= 1
    return list(reversed(out))


def parse_module(path: Path, module: str, context: list[str]) -> list[dict]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    stack: list[str] = []
    result = []
    for idx, line in enumerate(lines):
        m = RE_REGION.match(line)
        if m:
            stack.append(m.group(1))
            continue
        if RE_END_REGION.match(line):
            if stack:
                stack.pop()
            continue
        m = RE_METHOD_START.match(line)
        if not m:
            continue
        # Сигнатура может занимать несколько строк: копим до закрывающей скобки.
        signature, j = line[m.end():], idx
        while ")" not in signature and j + 1 < len(lines):
            j += 1
            signature += " " + lines[j].split("//")[0].strip()
        tail = RE_SIGNATURE_TAIL.search(signature)
        if not tail or not tail.group(1):
            continue
        params_text = signature[:tail.start()]
        comments = comment_block(lines, idx)
        summary = next((c for c in comments if c and not set(c) <= {"/", "-"}), "")
        deprecated = summary.lower().startswith("устарела") or any(
            r.lower().startswith("устаревш") for r in stack)
        params_text = re.sub(r'"[^"]*"', '""', params_text)  # запятые внутри строковых умолчаний
        params = [p.split("=")[0].replace("Знач ", "").strip()
                  for p in params_text.split(",") if p.strip()]
        result.append({
            "module": module,
            "name": m.group(2),
            "kind": m.group(1).capitalize(),
            "params": params,
            "region": stack[0] if stack else "",
            "subregion": "/".join(stack[1:]),
            "deprecated": deprecated,
            "context": context,
            "summary": summary,
        })
    return result


# Обработчики событий и точки локализации - не вызываемый программный интерфейс.
SKIP_MODULE_SUFFIXES = ("Переопределяемый", "ПереопределяемыйКлиент", "Локализация")


def compact(methods: list[dict]) -> list[dict]:
    """Только то, что прикладному коду разрешено вызывать: ПрограммныйИнтерфейс, не устаревшее."""
    return [m for m in methods
            if m["region"] == "ПрограммныйИнтерфейс" and not m["deprecated"]
            and "Служебн" not in m["module"]
            and not m["module"].endswith(SKIP_MODULE_SUFFIXES)
            and not m["module"].startswith("_Демо")  # примеры демо-конфигурации, не БСП
            and "Переопределяем" not in m["module"]]


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    full = "--full" in sys.argv
    methods = []
    for mod_dir in sorted((src / "CommonModules").iterdir()):
        bsl = mod_dir / "Module.bsl"
        if bsl.exists():
            methods += parse_module(bsl, mod_dir.name, module_context(mod_dir / f"{mod_dir.name}.mdo"))
    data = methods if full else compact(methods)
    # Одна запись на строку: grep по файлу выдает ровно один метод.
    out.write_text("[\n" + ",\n".join(json.dumps(m, ensure_ascii=False) for m in data) + "\n]\n", encoding="utf-8")
    public = [m for m in methods if m["region"] == "ПрограммныйИнтерфейс"]
    print(f"методов: {len(methods)}, в ПрограммныйИнтерфейс: {len(public)}, "
          f"устаревших: {sum(m['deprecated'] for m in methods)}, записано: {len(data)}")


if __name__ == "__main__":
    main()
