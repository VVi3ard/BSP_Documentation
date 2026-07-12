"""Discovery rules for the multifile BSP documentation corpus."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class HtmlPage:
    path: Path
    source_path: str
    breadcrumb: tuple[str, ...]


def discover_html_pages(root: str | Path) -> list[HtmlPage]:
    """Select leaf HTML pages and standalone index pages under *root*."""

    corpus_root = Path(root)
    if not corpus_root.is_dir():
        raise FileNotFoundError(f"BSP documentation directory does not exist: {corpus_root}")
    html_files = sorted(
        (path for path in corpus_root.rglob("*") if path.is_file() and path.suffix.lower() == ".html"),
        key=lambda path: path.relative_to(corpus_root).as_posix().casefold(),
    )
    if not html_files:
        raise ValueError(f"No HTML files found in BSP documentation directory: {corpus_root}")

    directories_with_descendants: set[Path] = set()
    for html_file in html_files:
        for parent in html_file.parents:
            if parent == corpus_root.parent:
                break
            if parent == html_file.parent and html_file.name.casefold() == "index.html":
                continue
            directories_with_descendants.add(parent)

    pages: list[HtmlPage] = []
    for path in html_files:
        if (
            path.name.casefold() == "index.html"
            and path.parent in directories_with_descendants
        ):
            continue
        relative = path.relative_to(corpus_root)
        pages.append(
            HtmlPage(
                path=path,
                source_path=relative.as_posix(),
                breadcrumb=tuple(relative.parts[:-1]),
            )
        )
    return pages
