"""STDIO MCP server exposing version-aware BSP documentation tools."""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .config import Settings
from .embeddings import OpenRouterEmbedder
from .navigation import discover_api_sections, get_api_section_map, load_api_navigation
from .search import SearchEngine
from .source_reader import read_source_document
from .storage import IndexDatabase
from .versions import BspVersion, detect_bsp_version as detect_version_file


MCP_INSTRUCTIONS = """Search documentation for the 1C Standard Subsystems Library (BSP/SSL).
Before searching, determine the project's BSP version from
src/Configuration/Configuration.distr: call detect_bsp_version, or locate
БиблиотекаСтандартныхПодсистем and use the nearest preceding quoted version.
Pass that version to every documentation lookup. Only major.minor compatibility
is significant: 3.1.11.155 uses the 3.1 index. Before writing new 1C/BSL code
that may use a standard BSP mechanism, call discover_bsp_api_sections with the
development task, then call get_bsp_api_section_map for the selected subsystem.
Search the selected API group with search_bsp mode="development", subsystem and
api_group. Use mode="override" for extension callbacks. Call get_bsp_section
for complete text before writing a BSP call.
For a practical implementation example, call get_bsp_demo_location and search
the returned bundled demo directory for the complete BSP method name.
Treat warning and recommendation flags as retrieval hints and verify conclusions
against the returned documentation text.
"""


def _compact_search_result(result: dict[str, object]) -> dict[str, object]:
    excerpt = str(result.get("excerpt", ""))
    compact: dict[str, object] = {
        "id": result["id"],
        "title": result["title"],
        "location": " > ".join(str(item) for item in result.get("breadcrumb", [])),
        "excerpt": excerpt[:600] + ("…" if len(excerpt) > 600 else ""),
    }
    if result.get("has_recommendation"):
        compact["has_recommendation"] = True
    if result.get("has_warning"):
        compact["has_warning"] = True
    return compact


class Runtime:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self._embedder: OpenRouterEmbedder | None = None
        self._engines: dict[str, SearchEngine] = {}

    def close(self) -> None:
        if self._embedder is not None:
            self._embedder.close()

    def _index_path(self, version: str) -> tuple[BspVersion, Path]:
        parsed = BspVersion.parse(version)
        path = self.settings.index_path(parsed.family)
        if not path.is_file():
            raise FileNotFoundError(
                f"No BSP documentation index for {parsed.family}; expected {path}"
            )
        return parsed, path

    def _get_embedder(self) -> OpenRouterEmbedder:
        if self._embedder is None:
            if not self.settings.openrouter_api_key:
                raise RuntimeError("OPENROUTER_API_KEY is required for semantic search")
            self._embedder = OpenRouterEmbedder(
                self.settings.openrouter_api_key,
                model=self.settings.embedding_model,
                base_url=self.settings.openrouter_base_url,
            )
        return self._embedder

    def search(
        self,
        version: str,
        query: str,
        limit: int = 8,
        mode: str = "all",
        subsystem: str | None = None,
        api_group: str | None = None,
    ) -> dict[str, object]:
        parsed, path = self._index_path(version)
        engine = self._engines.get(parsed.family)
        if engine is None:
            engine = SearchEngine(path, self._get_embedder())
            self._engines[parsed.family] = engine
        results = engine.search(
                query,
                limit=limit,
                mode=mode,
                subsystem=subsystem,
                api_group=api_group,
            )
        return {"results": [_compact_search_result(result) for result in results]}

    def list_api_sections(self, version: str) -> dict[str, object]:
        parsed, path = self._index_path(version)
        with IndexDatabase(path) as database:
            source_version = database.metadata().get("source_version")
        if not source_version:
            raise KeyError(f"Index metadata for BSP {parsed.family} lacks source_version")
        navigation = load_api_navigation(self.settings.data_dir, source_version)
        return {
            "sections": [
                {
                    "name": section.get("name", ""),
                    "description": section.get("description", ""),
                }
                for section in navigation.get("sections", [])
            ]
        }

    def discover_api_sections(
        self, version: str, query: str, limit: int = 5
    ) -> dict[str, object]:
        _, navigation = self._navigation(version)
        return {
            "results": discover_api_sections(navigation, query, limit),
        }

    def get_api_section_map(
        self, version: str, subsystem: str
    ) -> dict[str, object]:
        _, navigation = self._navigation(version)
        return {
            "subsystem": get_api_section_map(navigation, subsystem),
        }

    def get_demo_location(self, version: str) -> dict[str, object]:
        """Return the bundled EDT demo configuration compatible with a BSP release."""

        parsed, _ = self._index_path(version)
        release = ".".join(parsed.full.split(".")[:3])
        root = self.settings.data_dir / "demo"
        candidates = (
            sorted(
                (
                    path
                    for path in root.iterdir()
                    if path.is_dir()
                    and (
                        path.name == parsed.full
                        or path.name == release
                        or path.name.startswith(f"{release}.")
                    )
                ),
                key=lambda path: path.name,
                reverse=True,
            )
            if root.is_dir()
            else []
        )
        if not candidates:
            return {
                "requested_version": parsed.full,
                "available": False,
                "reason": f"No bundled demo configuration for BSP {release}",
            }
        demo = candidates[0]
        return {
            "requested_version": parsed.full,
            "demo_version": demo.name,
            "demo_root": str(demo),
            "source_format": "1c-edt",
            "available": True,
            "usage_hint": (
                "Search the full BSP symbol first. Read the enclosing BSL procedure, "
                "then follow callback procedures, commands and managed-form files."
            ),
        }

    def _navigation(
        self, version: str
    ) -> tuple[dict[str, object], dict[str, object]]:
        parsed, path = self._index_path(version)
        with IndexDatabase(path) as database:
            source_version = database.metadata().get("source_version")
        if not source_version:
            raise KeyError(f"Index metadata for BSP {parsed.family} lacks source_version")
        return (
            {
                "requested_version": parsed.full,
                "index_family": parsed.family,
                "index_source_version": source_version,
            },
            load_api_navigation(self.settings.data_dir, str(source_version)),
        )

    def get_section(self, version: str, section_id: str) -> dict[str, object]:
        _, path = self._index_path(version)
        with IndexDatabase(path) as database:
            section = database.get_section(section_id)
            if section is None:
                raise KeyError(
                    f"Section {section_id!r} does not exist in requested BSP documentation"
                )
        compact = {"title": section["title"], "text": section["text"]}
        if section.get("has_recommendation"):
            compact["has_recommendation"] = True
        if section.get("has_warning"):
            compact["has_warning"] = True
        return {"section": compact}

    def get_source_section(
        self, version: str, section_id: str, format: str = "markdown"
    ) -> dict[str, object]:
        parsed, path = self._index_path(version)
        with IndexDatabase(path) as database:
            section = database.get_section(section_id)
            if section is None:
                raise KeyError(
                    f"Section {section_id!r} does not exist in BSP {parsed.family}"
                )
            metadata = database.metadata()
        source_version = metadata.get("source_version")
        if not source_version:
            raise KeyError(f"Index metadata for BSP {parsed.family} lacks source_version")
        source_document = read_source_document(
            self.settings.data_dir,
            source_version,
            str(section["source_path"]),
            format=format,
        )
        return {
            "title": section["title"],
            "format": source_document["format"],
            "content": source_document["content"],
        }

    def list_versions(self) -> list[str]:
        root = self.settings.data_dir / "indexes"
        if not root.is_dir():
            return []
        return sorted(
            path.parent.name for path in root.glob("*/index.sqlite") if path.is_file()
        )


runtime = Runtime()
mcp = FastMCP("BSP Documentation", instructions=MCP_INSTRUCTIONS)


@mcp.tool()
def search_bsp(
    version: str,
    query: str,
    limit: int = 8,
    mode: str = "all",
    subsystem: str | None = None,
    api_group: str | None = None,
) -> dict[str, object]:
    """Search BSP docs; use development/override modes for program interfaces."""

    return runtime.search(version, query, limit, mode, subsystem, api_group)


@mcp.tool()
def list_bsp_api_sections(version: str) -> dict[str, object]:
    """List version-specific BSP program-interface subsystems before coding."""

    return runtime.list_api_sections(version)


@mcp.tool()
def discover_bsp_api_sections(
    version: str, query: str, limit: int = 5
) -> dict[str, object]:
    """Find BSP program-interface subsystems relevant to a development task."""

    return runtime.discover_api_sections(version, query, limit)


@mcp.tool()
def get_bsp_api_section_map(version: str, subsystem: str) -> dict[str, object]:
    """Return compact API groups for one BSP program-interface subsystem."""

    return runtime.get_api_section_map(version, subsystem)


@mcp.tool()
def get_bsp_demo_location(version: str) -> dict[str, object]:
    """Return the bundled BSP demo directory for agent-driven source search."""

    return runtime.get_demo_location(version)


@mcp.tool()
def get_bsp_section(version: str, section_id: str) -> dict[str, object]:
    """Return complete text for one result from the requested BSP version."""

    return runtime.get_section(version, section_id)


@mcp.tool()
def get_bsp_source_section(
    version: str, section_id: str, format: str = "markdown"
) -> dict[str, object]:
    """Return the original source page for one result as Markdown or HTML."""

    return runtime.get_source_section(version, section_id, format)


def _find_bsp_source_file(project_path: str | Path) -> Path:
    root = Path(project_path)
    if root.is_file():
        return root

    primary = root / "Configuration" / "src" / "Configuration" / "Configuration.distr"
    if primary.is_file():
        return primary

    fallback = root / "Configuration" / "src" / "Configuration" / "ParentConfigurations.bin"
    if fallback.is_file():
        return fallback

    for candidate in root.rglob("Configuration.distr"):
        if candidate.is_file():
            return candidate

    for candidate in root.rglob("ParentConfigurations.bin"):
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        f"Could not find Configuration.distr or ParentConfigurations.bin under {root}"
    )


@mcp.tool()
def detect_bsp_version(
    project_path: str = ".",
) -> dict[str, str]:
    """Detect BSP version from the project root."""

    version = detect_version_file(_find_bsp_source_file(project_path))
    return {"full_version": version.full, "index_family": version.family}


@mcp.tool()
def list_bsp_versions() -> dict[str, list[str]]:
    """List installed BSP major/minor documentation indexes."""

    return {"versions": runtime.list_versions()}


def run_server() -> None:
    try:
        mcp.run(transport="stdio")
    finally:
        runtime.close()
