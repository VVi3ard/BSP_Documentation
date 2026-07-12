"""Export cleaned BSP documentation pages to a local HTML tree."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import quote, unquote, urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag


_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")
_INVALID_FS_CHARS_RE = re.compile(r'[<>:"/\\|?*]')
_CHAPTER_RE = re.compile(r"^h1$", re.IGNORECASE)
_TOP_LEVEL_RE = re.compile(r"^(?:Глава|Приложение)\s+\d+\.", re.IGNORECASE)
_TOP_LEVEL_TITLES = (
    "Глава 1. Состав библиотеки",
    "Глава 2. Инструкция по внедрению библиотеки",
    "Глава 3. Настройка и использование подсистем при разработке конфигурации",
    "Глава 4. Программный интерфейс",
    "Глава 5. Пользовательская документация",
    "Приложение 1. Формат файла сообщения обмена данными",
    "Приложение 2. Доступные параметры запуска приложения",
    "Приложение 3. Международная поставка без национальной специфики",
)
_SOURCE_PREFIXES = (
    "/db/bsp3111doc/content/src/",
    "/db/content/bsp3111doc/src/",
)
_MAX_RELATIVE_PATH = 180


@dataclass(frozen=True, slots=True)
class ExportedPage:
    title: str
    path: Path


def _clean_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()


def _slugify(value: str) -> str:
    value = _clean_text(value).replace("\u00a0", " ")
    value = _INVALID_FS_CHARS_RE.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value or "index"


def _bounded_name(value: str, limit: int = 100) -> str:
    name = _slugify(value)
    return name[:limit].rstrip(" .") or "index"


def _normalize_source_url(value: str, base: str = "https://its.1c.ru") -> str | None:
    parsed = urlparse(urljoin(base, value))
    path = unquote(parsed.path)
    tail = next(
        (path[len(prefix) :] for prefix in _SOURCE_PREFIXES if path.startswith(prefix)),
        None,
    )
    if tail is None:
        return None
    tail = tail.removesuffix("_")
    if not tail.lower().endswith(".htm"):
        return None
    return f"https://its.1c.ru/db/content/bsp3111doc/src/{quote(tail, safe='/')}#_print"


def _is_chapter_heading(tag: Tag) -> bool:
    return bool(tag.name and _CHAPTER_RE.fullmatch(tag.name))


def _iter_direct_siblings(start: Tag, stop: Tag | None) -> list[Tag | NavigableString]:
    nodes: list[Tag | NavigableString] = []
    for sibling in start.next_siblings:
        if sibling is stop:
            break
        nodes.append(sibling)
    return nodes


def _rewrite_href(href: str, local_links: dict[str, str]) -> str:
    parsed = urlparse(href)
    if parsed.scheme or parsed.netloc:
        return href
    decoded = unquote(href)
    if decoded.startswith("#"):
        return decoded
    base = decoded.split("#", 1)[0].split("?", 1)[0]
    mapped = local_links.get(base)
    if mapped is None:
        return href
    if "#" in decoded:
        return f"{mapped}#{decoded.split('#', 1)[1]}"
    return mapped


def _materialize_table_numbers(fragment: Tag) -> None:
    tables = ([fragment] if fragment.name == "table" else []) + fragment.find_all("table")
    for table in tables:
        number = 0
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            if not cells or cells[0].name != "td":
                continue
            marker = cells[0].select_one("ol.n > li")
            if marker is None or marker.get_text(strip=True):
                continue
            number += 1
            cell = cells[0]
            cell.clear()
            cell["class"] = [*cell.get("class", []), "row-number"]
            cell.string = str(number)


def _clean_fragment(fragment: Tag, local_links: dict[str, str]) -> None:
    filter_blocks = (
        [fragment] if "filter_place" in fragment.get("class", []) else []
    ) + fragment.select(".filter_place")
    for filter_block in filter_blocks:
        for form in filter_block.find_all("form"):
            form.decompose()
    _materialize_table_numbers(fragment)

    for node in list(fragment.find_all(True)):
        if node.name == "script":
            node.decompose()
            continue
        if node.name == "link":
            rel = " ".join(node.get("rel", []))
            href = node.get("href")
            if rel == "stylesheet" and href:
                node["href"] = _rewrite_href(href, local_links)
        for attr in ("href", "src"):
            if node.has_attr(attr):
                node[attr] = _rewrite_href(str(node[attr]), local_links)
        if node.name in {"div", "nav", "header", "footer", "aside"} and not node.get_text(strip=True):
            node.decompose()


def export_chapter_tree(source_html: str | Path, output_dir: str | Path) -> list[ExportedPage]:
    source = Path(source_html)
    soup = BeautifulSoup(source.read_text(encoding="utf-8"), "lxml")
    h1s = [tag for tag in soup.find_all("h1") if _is_chapter_heading(tag)]
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    local_links: dict[str, str] = {}
    pages: list[ExportedPage] = []
    for chapter in h1s:
        title = _clean_text(chapter.get_text(" ", strip=True))
        if not title:
            continue
        folder = output / _slugify(title)
        page_path = folder / "index.html"
        pages.append(ExportedPage(title=title, path=page_path))
        anchor = chapter.get("id")
        if anchor:
            local_links[str(anchor)] = str(page_path.relative_to(output)).replace("\\", "/")

    for index, chapter in enumerate(h1s):
        title = _clean_text(chapter.get_text(" ", strip=True))
        if not title:
            continue
        next_chapter = h1s[index + 1] if index + 1 < len(h1s) else None
        chapter_nodes = _iter_direct_siblings(chapter, next_chapter)
        chapter_soup = BeautifulSoup("", "lxml")
        html = chapter_soup.new_tag("html", lang="ru")
        head = chapter_soup.new_tag("head")
        meta = chapter_soup.new_tag("meta", charset="utf-8")
        viewport = chapter_soup.new_tag("meta", attrs={"name": "viewport", "content": "width=device-width, initial-scale=1"})
        title_tag = chapter_soup.new_tag("title")
        title_tag.string = title
        style = chapter_soup.new_tag("style")
        style.string = (
            ":root{color-scheme:light;--text:#1f2937;--muted:#5b6472;--border:#d7dde5;--bg:#fff;--link:#0b57d0}"
            "body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 'Segoe UI',Arial,sans-serif}"
            "main{max-width:960px;margin:0 auto;padding:32px 24px 48px}"
            "h1{margin:0 0 18px;font-size:2rem;line-height:1.2}"
            "h2,h3,h4,h5,h6{margin:1.3em 0 .5em;line-height:1.25}"
            "p,li{margin:0 0 18px}"
            "img{max-width:100%;height:auto}"
            "a{color:var(--link);text-decoration:none}a:hover{text-decoration:underline}"
            "table{border-collapse:collapse}td,th{border:1px solid var(--border);padding:.35rem .5rem;vertical-align:top}"
            ".row-number{text-align:right;white-space:nowrap}"
        )
        head.extend([meta, viewport, title_tag, style])
        body = chapter_soup.new_tag("body")
        main = chapter_soup.new_tag("main")
        main.append(BeautifulSoup(str(chapter), "lxml").find("h1"))
        for node in chapter_nodes:
            fragment = BeautifulSoup(str(node), "lxml")
            for child in fragment.body.contents if fragment.body else fragment.contents:
                if isinstance(child, NavigableString):
                    if not str(child).strip():
                        continue
                    main.append(chapter_soup.new_string(str(child)))
                    continue
                if isinstance(child, Tag):
                    _clean_fragment(child, local_links)
                    if child.name is not None:
                        main.append(child)
        body.append(main)
        html.extend([head, body])
        chapter_soup.append(html)

        page = pages[index]
        page.path.parent.mkdir(parents=True, exist_ok=True)
        page.path.write_text(str(chapter_soup), encoding="utf-8")

    return pages


def _source_index_children(raw_html: str, source_url: str, pages: dict[str, dict]) -> list[str]:
    soup = BeautifulSoup(raw_html, "lxml")
    children: list[str] = []
    for link in soup.select(".index a[href]"):
        child = _normalize_source_url(str(link.get("href", "")), source_url)
        if child and child != source_url and child in pages and child not in children:
            children.append(child)
    return children


def _crawl_paths(
    pages: dict[str, dict], crawl_root: Path
) -> tuple[dict[str, Path], dict[str, list[str]], list[str]]:
    children: dict[str, list[str]] = {}
    incoming: set[str] = set()
    for url, page in pages.items():
        raw_html = (crawl_root / page["file"]).read_text(encoding="utf-8-sig")
        page_children = _source_index_children(raw_html, url, pages)
        children[url] = page_children
        incoming.update(page_children)

    by_title = {page.get("title", ""): url for url, page in pages.items()}
    roots = [by_title[title] for title in _TOP_LEVEL_TITLES if title in by_title]
    if not roots:
        roots = sorted(
            (url for url in pages if url not in incoming),
            key=lambda url: (pages[url].get("title", "").casefold(), url),
        )

    result: dict[str, Path] = {}
    used_names: dict[Path, set[str]] = {}

    def unique_component(parent: Path, title: str, url: str, extension: str) -> str:
        parent_length = len(parent.as_posix()) + 1 if parent.parts else 0
        tail_length = len(extension) if extension else len("/index.html")
        available = max(24, _MAX_RELATIVE_PATH - parent_length - tail_length)
        full_name = _slugify(title)
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
        if len(full_name) > available:
            base = f"{full_name[: available - 9].rstrip(' .')}-{digest}"
        else:
            base = full_name
        candidate = f"{base}{extension}"
        used = used_names.setdefault(parent, set())
        if candidate.casefold() in used:
            shortened = base[: max(1, available - 9)].rstrip(" .")
            candidate = f"{shortened}-{digest}{extension}"
        used.add(candidate.casefold())
        return candidate

    def allocate(url: str, parent: Path, force_directory: bool = False) -> None:
        if url in result:
            return
        title = pages[url].get("title") or "Страница"
        as_directory = force_directory or bool(children[url])
        if as_directory:
            directory = parent / unique_component(parent, title, url, "")
            result[url] = directory / "index.html"
            for child in children[url]:
                allocate(child, directory)
            return
        result[url] = parent / unique_component(parent, title, url, ".html")

    for root in roots:
        allocate(root, Path(), force_directory=True)

    # A few pages are linked from chapter text rather than its .index block.
    # Keep them under their recorded parent instead of dropping information.
    pending = set(pages) - set(result)
    while pending:
        progressed = False
        for url in sorted(pending, key=lambda item: (pages[item].get("title", "").casefold(), item)):
            parent_url = pages[url].get("parent")
            if parent_url in result:
                parent_path = result[parent_url]
                parent_dir = parent_path.parent if parent_path.name == "index.html" else parent_path.parent
                allocate(url, parent_dir)
                pending.remove(url)
                progressed = True
                break
        if progressed:
            continue
        extras = Path("Дополнительные материалы")
        for url in sorted(pending, key=lambda item: (pages[item].get("title", "").casefold(), item)):
            allocate(url, extras)
        break

    return result, children, roots


def _rewrite_crawl_links(body: Tag, source_url: str, page_path: Path, page_paths: dict[str, Path]) -> None:
    for link in body.select("a[href]"):
        original = str(link.get("href", ""))
        target_url = _normalize_source_url(original, source_url)
        if target_url and target_url in page_paths:
            relative = os.path.relpath(page_paths[target_url], page_path.parent).replace("\\", "/")
            fragment = urlparse(original).fragment
            link["href"] = f"{relative}#{fragment}" if fragment else relative
        elif original and not original.startswith(("#", "mailto:", "javascript:")):
            link["href"] = urljoin(source_url, original)
    for media in body.select("img[src]"):
        media["src"] = urljoin(source_url, str(media.get("src", "")))


def _render_crawl_page(raw_html: str, source_url: str, title: str, page_path: Path, page_paths: dict[str, Path]) -> str:
    source = BeautifulSoup(raw_html, "lxml")
    body = source.body or source
    _clean_fragment(body, {})
    _rewrite_crawl_links(body, source_url, page_path, page_paths)

    document = BeautifulSoup("", "lxml")
    html = document.new_tag("html", lang="ru")
    head = document.new_tag("head")
    head.append(document.new_tag("meta", charset="utf-8"))
    head.append(document.new_tag("meta", attrs={"name": "viewport", "content": "width=device-width, initial-scale=1"}))
    title_tag = document.new_tag("title")
    title_tag.string = title
    head.append(title_tag)
    style = document.new_tag("style")
    style.string = (
        "body{margin:0;color:#1f2937;background:#fff;font:16px/1.55 'Segoe UI',Arial,sans-serif}"
        "main{max-width:1100px;margin:0 auto;padding:24px 28px 48px}"
        "nav{margin-bottom:24px;padding-bottom:12px;border-bottom:1px solid #d7dde5}"
        "a{color:#0b57d0}img{max-width:100%;height:auto}table{border-collapse:collapse;max-width:100%}"
        "td,th{border:1px solid #d7dde5;padding:.35rem .5rem;vertical-align:top}"
        "pre{overflow:auto;padding:12px;background:#f5f7fa}.row-number{text-align:right;white-space:nowrap}"
    )
    head.append(style)
    main = document.new_tag("main")
    nav = document.new_tag("nav")
    root_link = document.new_tag("a", href=os.path.relpath(Path("index.html"), page_path.parent).replace("\\", "/"))
    root_link.string = "Оглавление"
    nav.append(root_link)
    main.append(nav)
    for child in list(body.contents):
        main.append(child)
    page_body = document.new_tag("body")
    page_body.append(main)
    html.extend([head, page_body])
    document.append(html)
    return str(document)


def export_crawl_manifest(manifest_path: str | Path, output_dir: str | Path) -> dict:
    manifest_file = Path(manifest_path)
    crawl_root = manifest_file.parent
    raw_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    pages = {
        url: page
        for url, page in raw_manifest.get("pages", {}).items()
        if page.get("status") == "ok" and page.get("file")
    }
    page_paths, _children, roots = _crawl_paths(pages, crawl_root)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, str]] = []
    for url, page_path in page_paths.items():
        page = pages[url]
        title = page.get("title") or "Страница"
        raw_html = (crawl_root / page["file"]).read_text(encoding="utf-8-sig")
        rendered = _render_crawl_page(raw_html, url, title, page_path, page_paths)
        destination = output / page_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
        items.append({"sourceUrl": url, "title": title, "path": page_path.as_posix()})

    items.sort(key=lambda item: (item["title"].casefold(), item["sourceUrl"]))
    index = BeautifulSoup("<html lang='ru'><head><meta charset='utf-8'><title>БСП 3.1.11</title></head><body><main><h1>БСП 3.1.11</h1><ul></ul></main></body></html>", "lxml")
    listing = index.find("ul")
    assert listing is not None
    root_items = {url: item for url, item in ((item["sourceUrl"], item) for item in items)}
    for root_url in roots:
        item = root_items[root_url]
        row = index.new_tag("li")
        link = index.new_tag("a", href=item["path"])
        link.string = item["title"]
        row.append(link)
        listing.append(row)
    (output / "index.html").write_text(str(index), encoding="utf-8")
    result = {"schemaVersion": 1, "pages": len(items), "items": items}
    (output / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
