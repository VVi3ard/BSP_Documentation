"""Versioned navigation for the BSP program interface."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


PROGRAM_INTERFACE_ROOT = "Глава 4. Программный интерфейс"
NAVIGATION_FILE = "program-interface.json"
INTERFACE_KINDS = ("Интерфейс", "Переопределение")
MAIN_GROUP = "Основные процедуры и функции"
_WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")
_DISCOVERY_STOP_WORDS = {
    "другие",
    "других",
    "если",
    "записи",
    "запись",
    "наличие",
    "нужно",
    "отменить",
    "показать",
    "при",
    "проверить",
    "проверять",
    "реализовать",
    "сделать",
    "справочник",
    "справочника",
    "список",
    "чтобы",
}
_IGNORED_PURPOSE_LINES = {
    "Оглавление",
    "Синтаксис",
    "Параметры",
    "Возвращаемое значение",
    "Описание",
    "Пример",
}


def navigation_path(data_dir: Path, source_version: str) -> Path:
    return data_dir / "navigation" / source_version / NAVIGATION_FILE


def build_api_navigation(
    source_dir: str | Path, source_version: str, output_path: str | Path
) -> dict[str, object]:
    """Build deterministic API groups and method evidence from BSP HTML files."""

    source = Path(source_dir)
    root = source / PROGRAM_INTERFACE_ROOT
    if not root.is_dir() and source.name == PROGRAM_INTERFACE_ROOT:
        root = source
    if not root.is_dir():
        raise FileNotFoundError(f"BSP program interface directory does not exist: {root}")

    sections: list[dict[str, object]] = []
    for section_dir in sorted(
        (path for path in root.iterdir() if path.is_dir()),
        key=lambda path: path.name.casefold(),
    ):
        groups = _collect_groups(root, section_dir)
        sections.append(
            {
                "name": section_dir.name,
                "description": "",
                "keywords": [],
                "source_path": _relative_source_path(root, section_dir),
                "kinds": [
                    name for name in INTERFACE_KINDS if (section_dir / name).is_dir()
                ],
                "method_count": sum(int(group["method_count"]) for group in groups),
                "groups": groups,
            }
        )

    navigation: dict[str, object] = {
        "schema_version": 2,
        "source_version": source_version,
        "root": PROGRAM_INTERFACE_ROOT,
        "sections": sections,
    }
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(navigation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return navigation


def _collect_groups(root: Path, section_dir: Path) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    for interface_kind in INTERFACE_KINDS:
        kind_dir = section_dir / interface_kind
        if not kind_dir.is_dir():
            continue
        direct_methods = _method_files(kind_dir)
        if direct_methods:
            groups.append(
                _group_card(root, section_dir.name, interface_kind, MAIN_GROUP, kind_dir, direct_methods)
            )
        for group_dir in sorted(
            (path for path in kind_dir.iterdir() if path.is_dir()),
            key=lambda path: path.name.casefold(),
        ):
            methods = sorted(
                (
                    path
                    for path in group_dir.rglob("*.html")
                    if path.name.casefold() != "index.html"
                ),
                key=lambda path: path.as_posix().casefold(),
            )
            if methods:
                groups.append(
                    _group_card(
                        root,
                        section_dir.name,
                        interface_kind,
                        group_dir.name,
                        group_dir,
                        methods,
                    )
                )
    return groups


def _method_files(directory: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in directory.glob("*.html")
            if path.name.casefold() != "index.html"
        ),
        key=lambda path: path.name.casefold(),
    )


def _group_card(
    root: Path,
    subsystem: str,
    interface_kind: str,
    name: str,
    directory: Path,
    methods: list[Path],
) -> dict[str, object]:
    evidence = [_method_evidence(root, path) for path in methods]
    source_hash = hashlib.sha256(
        json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "id": f"{subsystem}|{interface_kind}|{name}",
        "name": name,
        "description": "",
        "keywords": [],
        "interface_kind": interface_kind,
        "source_prefix": _relative_source_path(root, directory),
        "method_count": len(methods),
        "methods": evidence,
        "evidence_methods": [],
        "confidence": "",
        "source_hash": source_hash,
    }


def _method_evidence(root: Path, path: Path) -> dict[str, str]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    heading = soup.find(["h1", "h2", "h3"])
    method = _clean(heading.get_text(" ", strip=True)) if heading else path.stem
    lines = [_clean(line) for line in soup.get_text("\n", strip=True).splitlines()]
    purpose = next(
        (
            line
            for line in lines
            if _is_meaningful_purpose(line, method)
        ),
        method,
    )
    return {
        "method": method,
        "purpose": purpose[:500],
        "source_path": _relative_source_path(root, path),
    }


def _is_meaningful_purpose(line: str, method: str) -> bool:
    if not line or line == method or line in _IGNORED_PURPOSE_LINES:
        return False
    if line.startswith(("Функция ", "Процедура ", "См. ", "Источник:")):
        return False
    if line.endswith("()") or ("(" in line and line.endswith(")")):
        return False
    return len(line) >= 12


def _relative_source_path(root: Path, path: Path) -> str:
    return f"{PROGRAM_INTERFACE_ROOT}/{path.relative_to(root).as_posix()}"


def _clean(value: str) -> str:
    return " ".join(value.split())


def load_api_navigation(data_dir: Path, source_version: str) -> dict[str, object]:
    path = navigation_path(data_dir, source_version)
    if not path.is_file():
        raise FileNotFoundError(
            f"BSP API navigation for {source_version} does not exist: {path}"
        )
    navigation = json.loads(path.read_text(encoding="utf-8"))
    if navigation.get("source_version") != source_version:
        raise ValueError(
            f"BSP API navigation version mismatch in {path}: "
            f"expected {source_version!r}"
        )
    return navigation


def discover_api_sections(
    navigation: dict[str, object], query: str, limit: int = 5
) -> list[dict[str, object]]:
    """Rank compact subsystem cards using names, descriptions and keywords."""

    if not query.strip():
        raise ValueError("Discovery query must not be empty")
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    query_tokens = _tokens(query) - _DISCOVERY_STOP_WORDS
    raw_sections = list(navigation.get("sections", []))
    documents = [_section_tokens(section) for section in raw_sections]
    token_weights = {
        token: 1.0
        + math.log(
            (len(documents) + 1)
            / (1 + sum(token in document for document in documents))
        )
        for token in query_tokens
    }
    ranked: list[tuple[float, str, dict[str, object]]] = []
    for raw_section in raw_sections:
        groups = list(raw_section.get("groups", []))
        name = str(raw_section.get("name", ""))
        score = _text_score(query_tokens, name, weight=5.0, token_weights=token_weights)
        score += _text_score(
            query_tokens,
            str(raw_section.get("description", "")),
            weight=3.0,
            token_weights=token_weights,
        )
        score += _text_score(
            query_tokens,
            " ".join(raw_section.get("keywords", [])),
            weight=2.5,
            token_weights=token_weights,
        )
        group_scores = [
            _text_score(
                query_tokens,
                str(group.get("name", "")),
                weight=3.0,
                token_weights=token_weights,
            )
            + _text_score(
                query_tokens,
                str(group.get("description", "")),
                weight=2.0,
                token_weights=token_weights,
            )
            + _text_score(
                query_tokens,
                " ".join(group.get("keywords", [])),
                weight=3.0,
                token_weights=token_weights,
            )
            for group in groups
        ]
        # A large subsystem must not outrank a focused one merely because many
        # unrelated groups each contain one generic query word.
        score += max(group_scores, default=0.0)
        if score > 0:
            section = {
                "name": name,
                "description": raw_section.get("description", ""),
            }
            ranked.append((score, name.casefold(), section))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [section for _, _, section in ranked[:limit]]


def get_api_section_map(
    navigation: dict[str, object], subsystem: str
) -> dict[str, object]:
    """Return one subsystem and its API groups without full method lists."""

    wanted = subsystem.strip().casefold()
    for raw_section in navigation.get("sections", []):
        if str(raw_section.get("name", "")).casefold() != wanted:
            continue
        return {
            "name": raw_section.get("name", ""),
            "description": raw_section.get("description", ""),
            "groups": [
                {
                    "name": group.get("name", ""),
                    "description": group.get("description", ""),
                    "interface_kind": group.get("interface_kind", ""),
                }
                for group in raw_section.get("groups", [])
            ],
        }
    raise KeyError(f"BSP API subsystem does not exist: {subsystem!r}")


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in _WORD_RE.findall(value) if len(token) > 2}


def _section_tokens(section: dict[str, Any]) -> set[str]:
    values = [
        str(section.get("name", "")),
        str(section.get("description", "")),
        " ".join(section.get("keywords", [])),
    ]
    for group in section.get("groups", []):
        values.extend(
            (
                str(group.get("name", "")),
                str(group.get("description", "")),
                " ".join(group.get("keywords", [])),
            )
        )
    return _tokens(" ".join(values))


def _text_score(
    query_tokens: set[str],
    value: str,
    *,
    weight: float,
    token_weights: dict[str, float],
) -> float:
    value_tokens = _tokens(value)
    if not value_tokens:
        return 0.0
    exact = sum(token_weights[token] for token in query_tokens & value_tokens)
    partial = sum(
        token_weights[query_token]
        for query_token in query_tokens - value_tokens
        if any(
            len(query_token) >= 5
            and len(value_token) >= 5
            and (query_token in value_token or value_token in query_token)
            for value_token in value_tokens
        )
    )
    return weight * (exact + partial * 0.5)
