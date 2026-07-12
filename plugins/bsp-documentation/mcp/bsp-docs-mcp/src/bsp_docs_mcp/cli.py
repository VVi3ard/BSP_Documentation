"""Command line entry point for indexing and serving."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import Settings
from .crawler import crawl_its
from .embeddings import OpenRouterEmbedder
from .exporter import export_chapter_tree
from .indexer import build_index
from .navigation import build_api_navigation, navigation_path
from .server import run_server
from .versions import BspVersion


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bsp-docs-mcp")
    subcommands = parser.add_subparsers(dest="command", required=True)

    index = subcommands.add_parser("index", help="build a versioned BSP index")
    index.add_argument("--version", required=True, help="full BSP version")
    index_source = index.add_mutually_exclusive_group(required=True)
    index_source.add_argument("--source", type=Path, help="HTML corpus directory")
    index_source.add_argument("--html", type=Path, help="legacy single HTML path")

    inspect = subcommands.add_parser("inspect", help="parse HTML without embeddings")
    inspect.add_argument("--version", required=True)
    inspect_source = inspect.add_mutually_exclusive_group(required=True)
    inspect_source.add_argument("--source", type=Path, help="HTML corpus directory")
    inspect_source.add_argument("--html", type=Path, help="legacy single HTML path")

    export_html = subcommands.add_parser(
        "export-html", help="export cleaned chapter pages to a local tree"
    )
    export_html.add_argument("--html", required=True, type=Path)
    export_html.add_argument(
        "--output", required=True, type=Path, help="destination directory"
    )

    crawl = subcommands.add_parser("crawl-its", help="crawl ITS pages into manifest.json")
    crawl.add_argument("--start-url", required=True, help="start ITS source page")
    crawl.add_argument(
        "--output",
        required=True,
        type=Path,
        help="output directory for manifest.json and raw pages",
    )
    crawl.add_argument(
        "--cookies-json",
        type=Path,
        help="JSON file with cookies as an object or a list of {name, value}",
    )
    crawl.add_argument(
        "--cookie",
        action="append",
        help="inline cookie in NAME=VALUE format; can be repeated",
    )
    crawl.add_argument(
        "--header",
        action="append",
        help="extra HTTP header in NAME=VALUE format; can be repeated",
    )
    crawl.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    crawl.add_argument("--delay", type=float, default=0.0, help="delay between requests in seconds")
    crawl.add_argument("--max-pages", type=int, help="stop after N fetched pages")

    navigation = subcommands.add_parser(
        "build-navigation", help="build program-interface navigation JSON"
    )
    navigation.add_argument("--version", required=True, help="full BSP version")
    navigation.add_argument("--source", required=True, type=Path)
    navigation.add_argument("--output", type=Path)

    subcommands.add_parser("serve", help="start the STDIO MCP server")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "serve":
        run_server()
        return 0

    if args.command == "inspect":
        version = BspVersion.parse(args.version)
        from .indexer import _load_chunks

        source = args.source or args.html
        chunks, source_file_count = _load_chunks(source, version.full)
        print(
            f"Parsed {len(chunks)} chunks from {source_file_count} files "
            f"for BSP {version.full} "
            f"(index family {version.family})"
        )
        return 0

    if args.command == "export-html":
        pages = export_chapter_tree(args.html, args.output)
        print(f"Exported {len(pages)} pages into {args.output}")
        return 0

    if args.command == "crawl-its":
        result = crawl_its(
            start_url=args.start_url,
            output_dir=args.output,
            cookies_json=args.cookies_json,
            cookies=args.cookie,
            headers=args.header,
            timeout=args.timeout,
            delay_seconds=args.delay,
            max_pages=args.max_pages,
        )
        print(
            f"Crawled {result['pages']} pages "
            f"(fetched {result['fetched']}, skipped {result['skipped']}, errors {result['errors']}) "
            f"into {result['manifest']}"
        )
        return 0

    if args.command == "build-navigation":
        version = BspVersion.parse(args.version)
        settings = Settings.from_env()
        output = args.output or navigation_path(settings.data_dir, version.full)
        result = build_api_navigation(args.source, version.full, output)
        print(f"Wrote {len(result['sections'])} API sections into {output}")
        return 0

    version = BspVersion.parse(args.version)
    source = args.source or args.html
    settings = Settings.from_env()
    if not settings.openrouter_api_key:
        raise SystemExit("OPENROUTER_API_KEY is required to build the index")
    embedder = OpenRouterEmbedder(
        settings.openrouter_api_key,
        model=settings.embedding_model,
        base_url=settings.openrouter_base_url,
    )
    try:
        count = build_index(
            source,
            version.full,
            settings.index_path(version.family),
            embedder,
        )
        if source.is_dir():
            build_api_navigation(
                source,
                version.full,
                navigation_path(settings.data_dir, version.full),
            )
    finally:
        embedder.close()
    print(f"Indexed {count} chunks into {settings.index_path(version.family)}")
    return 0
