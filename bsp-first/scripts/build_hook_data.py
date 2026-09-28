"""Данные хука из полного индекса (build_bsp_api_index.py --full).

Запуск:
    python build_hook_data.py <api-full.json> <каталог hook/data> [<src поставки БСП>]

Пишет:
  bsp-deprecated.json - экспортные методы ПрограммныйИнтерфейс с пометкой «Устарела»
                        или из области УстаревшиеПроцедурыИФункции: call, note (замена);
  bsp-internal.json   - экспортные методы, которые прикладному коду вызывать нельзя:
                        модули *Служебный* и области СлужебныйПрограммныйИнтерфейс /
                        СлужебныеПроцедурыИФункции; call, region;
  bsp-objects.txt     - с третьим аргументом: объекты поставки БСП (<Тип>/<Имя>), в которых
                        хук молчит. Брать src чистой БСП нужной версии, не демо-конфигурации:
                        в демо есть объекты-примеры _Демо*, они отбрасываются.
"""
import json
import sys
from pathlib import Path


def main() -> None:
    api = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(sys.argv[2])
    api = [m for m in api if not m["module"].startswith("_Демо")]
    deprecated = [{"call": f"{m['module']}.{m['name']}", "note": m["summary"]} for m in api
                  if m["region"] == "ПрограммныйИнтерфейс" and m["deprecated"] and "Служебн" not in m["module"]]
    internal = [{"call": f"{m['module']}.{m['name']}", "region": m["region"]} for m in api
                if "Служебн" in m["module"] or m["region"] in ("СлужебныйПрограммныйИнтерфейс",
                                                                "СлужебныеПроцедурыИФункции")]
    for name, data in (("bsp-deprecated.json", deprecated), ("bsp-internal.json", internal)):
        (out / name).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"устаревших: {len(deprecated)}, служебных: {len(internal)}")
    if len(sys.argv) > 3:
        src = Path(sys.argv[3])
        objects = sorted(f"{kind.name}/{obj.name}" for kind in src.iterdir() if kind.is_dir()
                         for obj in kind.iterdir() if obj.is_dir() and not obj.name.startswith("_Демо"))
        (out / "bsp-objects.txt").write_text("\n".join(objects) + "\n", encoding="utf-8")
        print(f"объектов БСП: {len(objects)}")


if __name__ == "__main__":
    main()
