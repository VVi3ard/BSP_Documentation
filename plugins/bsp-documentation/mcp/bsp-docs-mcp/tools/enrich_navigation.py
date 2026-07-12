"""Enrich a deterministic BSP API navigation map through local Codex CLI."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


GROUP_PROMPT = """Ты создаешь компактные навигационные карточки программного интерфейса БСП.
Для каждой входной группы верни ровно одну карточку с тем же id.
Каждый элемент methods имеет формат [имя метода, назначение]. Используй только эти данные.
description: одно предложение на русском языке, 20-180 символов, назначение группы без перечисления методов.
keywords: 3-7 естественных формулировок задачи разработчика.
evidence_methods: 1-8 переданных методов, прямо подтверждающих описание.
confidence: high для однородной группы, medium для нескольких близких направлений, low для неоднородной группы.
Не выдумывай возможности. Верни только JSON по схеме.
"""

SECTION_PROMPT = """Ты создаешь верхний уровень навигации программного интерфейса БСП.
Для каждой подсистемы верни ровно одну карточку с тем же name.
Используй только названия и уже проверенные карточки групп.
description: одно предложение на русском языке, 20-180 символов, назначение подсистемы.
keywords: 3-7 естественных формулировок задачи разработчика.
Не перечисляй группы и не выдумывай возможности. Верни только JSON по схеме.
"""


def _schema(key: str, count: int, *, section: bool = False) -> dict[str, Any]:
    identity = "name" if section else "id"
    properties: dict[str, Any] = {
        identity: {"type": "string"},
        "description": {"type": "string", "minLength": 20, "maxLength": 180},
        "keywords": {
            "type": "array",
            "minItems": 3,
            "maxItems": 7,
            "items": {"type": "string", "minLength": 2, "maxLength": 60},
        },
    }
    required = [identity, "description", "keywords"]
    if not section:
        properties.update(
            {
                "evidence_methods": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 8,
                    "items": {"type": "string"},
                },
                "confidence": {"enum": ["high", "medium", "low"]},
            }
        )
        required.extend(("evidence_methods", "confidence"))
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": [key],
        "additionalProperties": False,
        "properties": {
            key: {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "required": required,
                    "additionalProperties": False,
                    "properties": properties,
                },
            }
        },
    }


def _batches(items: list[dict[str, Any]], max_items: int, max_chars: int) -> list[list[dict[str, Any]]]:
    result: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    size = 0
    for item in items:
        item_size = len(json.dumps(item, ensure_ascii=False))
        if current and (len(current) >= max_items or size + item_size > max_chars):
            result.append(current)
            current, size = [], 0
        current.append(item)
        size += item_size
    if current:
        result.append(current)
    return result


def _run_codex(
    prompt: str,
    payload: dict[str, Any],
    schema: dict[str, Any],
    output: Path,
    model: str,
    effort: str,
) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_file():
        return json.loads(output.read_text(encoding="utf-8"))
    request_base = output.with_suffix("")
    input_path = request_base.with_suffix(".input.json")
    stdin_path = request_base.with_suffix(".stdin.txt")
    schema_copy_path = request_base.with_suffix(".schema.json")
    input_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    stdin_text = prompt + "\n\n" + json.dumps(payload, ensure_ascii=False) + "\n"
    input_path.write_text(input_text, encoding="utf-8")
    stdin_path.write_text(stdin_text, encoding="utf-8")
    schema_copy_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
        json.dump(schema, handle, ensure_ascii=False, indent=2)
        schema_path = Path(handle.name)
    try:
        command = [
            "codex", "exec", "--ephemeral", "--ignore-rules", "--sandbox", "read-only",
            "-m", model, "-c", f'model_reasoning_effort="{effort}"',
            "--output-schema", str(schema_path), "--output-last-message", str(output), "-",
        ]
        completed = subprocess.run(command, input=stdin_text.encode("utf-8"), check=False)
        if completed.returncode:
            raise RuntimeError(f"Codex enrichment failed with exit code {completed.returncode}")
        return json.loads(output.read_text(encoding="utf-8"))
    finally:
        schema_path.unlink(missing_ok=True)


def _validate_group(source: dict[str, Any], card: dict[str, Any]) -> None:
    methods = {method["method"] for method in source["methods"]}
    unknown = set(card["evidence_methods"]) - methods
    if unknown:
        raise ValueError(f"Unknown evidence methods for {source['id']}: {sorted(unknown)}")


def _compact_group_batch(
    batch: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    compact: list[dict[str, Any]] = []
    sources: dict[str, dict[str, Any]] = {}
    for number, source in enumerate(batch, start=1):
        short_id = f"g{number:02d}"
        sources[short_id] = source
        compact.append(
            {
                "id": short_id,
                "subsystem": source["subsystem"],
                "kind": source["interface_kind"],
                "name": source["group"],
                "methods": [
                    [method["method"], method["purpose"]]
                    for method in source["methods"]
                ],
            }
        )
    return compact, sources


def export_group_requests(source_path: Path, work_dir: Path) -> int:
    """Save the exact group payload and stdin text without invoking a model."""

    navigation = json.loads(source_path.read_text(encoding="utf-8"))
    groups = [group for section in navigation["sections"] for group in section["groups"]]
    inputs = [
        {
            "id": group["id"],
            "subsystem": group["id"].split("|", 1)[0],
            "interface_kind": group["interface_kind"],
            "group": group["name"],
            "method_count": group["method_count"],
            "methods": group["methods"],
        }
        for group in groups
    ]
    batches = _batches(inputs, max_items=20, max_chars=75_000)
    work_dir.mkdir(parents=True, exist_ok=True)
    for number, batch in enumerate(batches, start=1):
        base = work_dir / f"groups-{number:03d}"
        compact, _ = _compact_group_batch(batch)
        payload = {"groups": compact}
        base.with_suffix(".input.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        base.with_suffix(".stdin.txt").write_text(
            GROUP_PROMPT + "\n\n" + json.dumps(payload, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        base.with_suffix(".schema.json").write_text(
            json.dumps(_schema("cards", len(batch)), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return len(batches)


def enrich(source_path: Path, output_path: Path, work_dir: Path, model: str, effort: str) -> None:
    navigation = json.loads(source_path.read_text(encoding="utf-8"))
    groups = [group for section in navigation["sections"] for group in section["groups"]]
    group_inputs = [
        {
            "id": group["id"],
            "subsystem": group["id"].split("|", 1)[0],
            "interface_kind": group["interface_kind"],
            "group": group["name"],
            "method_count": group["method_count"],
            "methods": group["methods"],
        }
        for group in groups
    ]
    cards: dict[str, dict[str, Any]] = {}
    group_batches = _batches(group_inputs, max_items=20, max_chars=75_000)
    for number, batch in enumerate(group_batches, start=1):
        print(f"Group batch {number}/{len(group_batches)}: {len(batch)} groups", flush=True)
        compact_batch, sources_by_short_id = _compact_group_batch(batch)
        result = _run_codex(
            GROUP_PROMPT,
            {"groups": compact_batch},
            _schema("cards", len(batch)),
            work_dir / f"groups-{number:03d}.json",
            model,
            effort,
        )
        by_id = {item["id"]: item for item in batch}
        for card in result["cards"]:
            card_id = card["id"]
            source = sources_by_short_id.get(card_id) or by_id.get(card_id)
            if source is None:
                raise ValueError(f"Unexpected group id: {card['id']}")
            _validate_group(source, card)
            cards[source["id"]] = card
    expected_ids = {group["id"] for group in groups}
    if set(cards) != expected_ids:
        raise ValueError(f"Missing group cards: {sorted(expected_ids - set(cards))}")
    for group in groups:
        card = cards[group["id"]]
        for field in ("description", "keywords", "evidence_methods", "confidence"):
            group[field] = card[field]

    section_inputs = [
        {
            "name": section["name"],
            "groups": [
                {
                    "name": group["name"],
                    "description": group["description"],
                    "keywords": group["keywords"],
                }
                for group in section["groups"]
            ],
        }
        for section in navigation["sections"]
    ]
    section_cards: dict[str, dict[str, Any]] = {}
    section_batches = _batches(section_inputs, max_items=25, max_chars=60_000)
    for number, batch in enumerate(section_batches, start=1):
        print(f"Section batch {number}/{len(section_batches)}: {len(batch)} sections", flush=True)
        result = _run_codex(
            SECTION_PROMPT,
            {"sections": batch},
            _schema("sections", len(batch), section=True),
            work_dir / f"sections-{number:03d}.json",
            model,
            effort,
        )
        for card in result["sections"]:
            section_cards[card["name"]] = card
    expected_names = {section["name"] for section in navigation["sections"]}
    if set(section_cards) != expected_names:
        raise ValueError(f"Missing section cards: {sorted(expected_names - set(section_cards))}")
    for section in navigation["sections"]:
        card = section_cards[section["name"]]
        section["description"] = card["description"]
        section["keywords"] = card["keywords"]

    navigation["enrichment"] = {"model": model, "reasoning_effort": effort}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(navigation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(groups)} groups and {len(section_inputs)} sections to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--export-group-requests-only", action="store_true")
    args = parser.parse_args()
    if args.export_group_requests_only:
        count = export_group_requests(args.source, args.work_dir)
        print(f"Wrote {count} group request batches to {args.work_dir}")
        return
    enrich(args.source, args.output, args.work_dir, args.model, args.effort)


if __name__ == "__main__":
    main()
