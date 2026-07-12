"""Read original BSP source pages as HTML or Markdown."""

from __future__ import annotations

from pathlib import Path

from markdownify import markdownify as html_to_markdown


def read_source_document(
    data_dir: str | Path,
    source_version: str,
    source_path: str,
    *,
    format: str = "markdown",
) -> dict[str, str]:
    normalized_format = format.strip().lower()
    if normalized_format not in {"markdown", "html"}:
        raise ValueError("format must be either 'markdown' or 'html'")

    path = Path(data_dir) / "sources" / source_version / Path(source_path)
    if not path.is_file():
        raise FileNotFoundError(f"BSP source page does not exist: {path}")

    html = path.read_text(encoding="utf-8")
    if normalized_format == "html":
        return {
            "format": "html",
            "content": html,
            "path": source_path,
        }

    markdown = html_to_markdown(
        html,
        heading_style="ATX",
        bullets="-",
        strong_em_symbol="*",
    ).strip()
    return {
        "format": "markdown",
        "content": markdown,
        "path": source_path,
    }
