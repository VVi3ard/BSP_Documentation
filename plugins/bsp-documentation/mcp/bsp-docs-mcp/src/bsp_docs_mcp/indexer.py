"""Build an atomic major/minor BSP documentation index."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import os
import tempfile

from .corpus import discover_html_pages
from .embeddings import Embedder
from .parser import parse_html
from .storage import IndexDatabase
from .versions import BspVersion


def build_index(
    html_path: str | Path,
    source_version: str,
    target_path: str | Path,
    embedder: Embedder,
) -> int:
    version = BspVersion.parse(source_version)
    source = Path(html_path)
    chunks, source_file_count = _load_chunks(source, version.full)
    vectors = embedder.embed_documents([chunk.embedding_text for chunk in chunks])

    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="index-", suffix=".sqlite", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    try:
        metadata = {
            "family": version.family,
            "source_version": version.full,
            "source_file": source.name,
            "source_file_count": str(source_file_count),
            "model": embedder.model,
            "chunk_count": str(len(chunks)),
            "built_at": datetime.now(timezone.utc).isoformat(),
        }
        with IndexDatabase.create(temporary, metadata) as database:
            database.add_chunks(chunks, vectors)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return len(chunks)


def _load_chunks(source: Path, source_version: str):
    if source.is_file():
        html = source.read_text(encoding="utf-8")
        return parse_html(html, source_version, source_path=source.name), 1

    pages = discover_html_pages(source)
    chunks = []
    for page in pages:
        chunks.extend(
            parse_html(
                page.path.read_text(encoding="utf-8"),
                source_version,
                source_path=page.source_path,
                base_breadcrumb=page.breadcrumb,
            )
        )
    return chunks, len(pages)
