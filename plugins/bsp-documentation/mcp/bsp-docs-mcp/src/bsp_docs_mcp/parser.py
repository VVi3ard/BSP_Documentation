"""Convert the monolithic BSP HTML document into searchable sections."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from bs4 import BeautifulSoup, Tag

from .versions import BspVersion


_HEADING_RE = re.compile(r"^h([1-6])$")
_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_RECOMMEND_RE = re.compile(r"\bрекоменду(?:ется|емый|емая|емые|овано)\b", re.IGNORECASE)
_WARNING_RE = re.compile(
    r"\b(?:не\s+рекомендуется|устарел(?:а|о|и)?|не\s+следует|запрещается)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    id: str
    source_version: str
    anchor: str
    title: str
    breadcrumb: tuple[str, ...]
    text: str
    part: int
    has_recommendation: bool
    has_warning: bool
    source_path: str = ""

    @property
    def embedding_text(self) -> str:
        path = " > ".join(self.breadcrumb)
        source = f"\nSource: {self.source_path}" if self.source_path else ""
        return f"BSP {self.source_version}\nSection: {path}{source}\n\n{self.text}"


def _clean_text(value: str) -> str:
    lines = [_SPACE_RE.sub(" ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def _is_top_level_block(tag: Tag) -> bool:
    if tag.name not in {"p", "pre", "table", "li"}:
        return False
    return not any(
        isinstance(parent, Tag) and parent.name in {"p", "pre", "table", "li"}
        for parent in tag.parents
    )


def _split_blocks(blocks: list[str], max_chars: int) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    current_size = 0
    for block in blocks:
        separator = 2 if current else 0
        if current and current_size + separator + len(block) > max_chars:
            parts.append("\n\n".join(current))
            current = []
            current_size = 0
        if len(block) <= max_chars:
            current.append(block)
            current_size += (2 if current_size else 0) + len(block)
            continue
        for start in range(0, len(block), max_chars):
            fragment = block[start : start + max_chars].strip()
            if fragment:
                if current:
                    parts.append("\n\n".join(current))
                    current = []
                    current_size = 0
                parts.append(fragment)
    if current:
        parts.append("\n\n".join(current))
    return parts


def parse_html(
    html: str,
    source_version: str,
    *,
    max_chars: int = 8_000,
    source_path: str = "",
    base_breadcrumb: tuple[str, ...] = (),
) -> list[DocumentChunk]:
    """Parse UTF-8 BSP HTML into deterministic, non-overlapping chunks."""

    version = BspVersion.parse(source_version)
    soup = BeautifulSoup(html, "lxml")
    hierarchy: list[str] = []
    sections: list[tuple[str, str, tuple[str, ...], list[str]]] = []
    current: tuple[str, str, tuple[str, ...], list[str]] | None = None

    for element in soup.descendants:
        if not isinstance(element, Tag):
            continue
        heading_match = _HEADING_RE.match(element.name or "")
        if heading_match:
            level = int(heading_match.group(1))
            title = _clean_text(element.get_text(" ", strip=True))
            if not title:
                continue
            hierarchy = hierarchy[: level - 1]
            while len(hierarchy) < level - 1:
                hierarchy.append("")
            hierarchy.append(title)
            internal = tuple(part for part in hierarchy if part)
            breadcrumb = _merge_breadcrumbs(base_breadcrumb, internal)
            anchor = str(element.get("id") or f"section-{len(sections) + 1}")
            current = (anchor, title, breadcrumb, [])
            sections.append(current)
            continue
        if current is not None and _is_top_level_block(element):
            text = _clean_text(element.get_text("\n", strip=True))
            if text:
                current[3].append(text)

    chunks: list[DocumentChunk] = []
    for anchor, title, breadcrumb, blocks in sections:
        if not blocks:
            blocks = [title]
        for part_number, text in enumerate(_split_blocks(blocks, max_chars), start=1):
            digest_input = (
                f"{version.full}\0{source_path}\0{anchor}\0{part_number}\0{text}"
            ).encode("utf-8")
            chunk_id = hashlib.sha256(digest_input).hexdigest()[:24]
            chunks.append(
                DocumentChunk(
                    id=chunk_id,
                    source_version=version.full,
                    anchor=anchor,
                    title=title,
                    breadcrumb=breadcrumb,
                    text=text,
                    part=part_number,
                    has_recommendation=bool(_RECOMMEND_RE.search(text)),
                    has_warning=bool(_WARNING_RE.search(text)),
                    source_path=source_path,
                )
            )
    return chunks


def _merge_breadcrumbs(
    base: tuple[str, ...], internal: tuple[str, ...]
) -> tuple[str, ...]:
    merged = list(base)
    for part in internal:
        if merged and merged[-1].strip().casefold() == part.strip().casefold():
            continue
        merged.append(part)
    return tuple(merged)
