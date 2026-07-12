"""ITS HTML crawler that builds a local manifest for exporter.py."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Callable
from urllib.parse import quote, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, UnicodeDammit


_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
_SOURCE_PREFIXES = (
    "/db/bsp3111doc/content/src/",
    "/db/content/bsp3111doc/src/",
)


@dataclass(frozen=True, slots=True)
class FetchResult:
    status_code: int
    content: bytes
    content_type: str | None = None
    final_url: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_its_url(value: str, base_url: str = "https://its.1c.ru") -> str | None:
    parsed = urlparse(urljoin(base_url, value))
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


def _source_root(url: str) -> str:
    normalized = normalize_its_url(url, url)
    if normalized is None:
        raise ValueError(f"Unsupported ITS documentation URL: {url}")
    parsed = urlparse(normalized)
    marker = "/src/"
    prefix, _, _tail = parsed.path.partition(marker)
    if not prefix:
        raise ValueError(f"Unable to determine ITS source root from URL: {url}")
    return f"{parsed.scheme}://{parsed.netloc}{prefix}{marker}"


def _decode_html(content: bytes) -> str:
    decoded = UnicodeDammit(content, is_html=True)
    if decoded.unicode_markup is None:
        return content.decode("utf-8", errors="replace")
    return decoded.unicode_markup


def extract_title(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "lxml")
    heading = soup.find("h1")
    if heading is not None:
        title = heading.get_text(" ", strip=True)
        if title:
            return title
    if soup.title is not None:
        title = soup.title.get_text(" ", strip=True)
        if title:
            return title
    return "Страница"


def discover_links(raw_html: str, source_url: str, allowed_root: str) -> list[str]:
    soup = BeautifulSoup(raw_html, "lxml")
    links: list[str] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        normalized = normalize_its_url(str(anchor.get("href", "")), source_url)
        if normalized is None or normalized == source_url:
            continue
        if not normalized.startswith(allowed_root):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        links.append(normalized)
    return links


def _load_cookie_jar(cookies_json: str | Path | None) -> dict[str, str]:
    if not cookies_json:
        return {}
    raw = json.loads(Path(cookies_json).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    if isinstance(raw, list):
        result: dict[str, str] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            value = item.get("value")
            if name:
                result[str(name)] = "" if value is None else str(value)
        return result
    raise ValueError("cookies JSON must be an object or a list of {name, value}")


def _parse_name_value(items: list[str] | None, option: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"{option} must be in NAME=VALUE format: {item}")
        name, value = item.split("=", 1)
        name = name.strip()
        if not name:
            raise ValueError(f"{option} contains an empty name: {item}")
        result[name] = value
    return result


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _next_page_file(manifest_pages: dict[str, dict], pages_dir: Path) -> str:
    highest = 0
    for page in manifest_pages.values():
        file_name = page.get("file")
        if not isinstance(file_name, str):
            continue
        stem = Path(file_name).stem
        if stem.isdigit():
            highest = max(highest, int(stem))
    highest += 1
    candidate = pages_dir / f"{highest:04d}.html"
    while candidate.exists():
        highest += 1
        candidate = pages_dir / f"{highest:04d}.html"
    return candidate.name


class ItsCrawler:
    def __init__(
        self,
        *,
        start_url: str,
        output_dir: str | Path,
        delay_seconds: float = 0.0,
        max_pages: int | None = None,
        fetch: Callable[[str], FetchResult] | None = None,
    ) -> None:
        self.start_url = normalize_its_url(start_url, start_url)
        if self.start_url is None:
            raise ValueError(f"Unsupported ITS documentation URL: {start_url}")
        self.output_dir = Path(output_dir)
        self.delay_seconds = max(0.0, delay_seconds)
        self.max_pages = max_pages
        self.fetch = fetch
        self.allowed_root = _source_root(self.start_url)
        self.pages_dir = self.output_dir / "pages"
        self.manifest_path = self.output_dir / "manifest.json"

    def _load_manifest(self) -> dict:
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return {
            "schemaVersion": 1,
            "createdAt": _utc_now(),
            "updatedAt": _utc_now(),
            "startUrl": self.start_url,
            "allowedRoot": self.allowed_root,
            "pages": {},
        }

    def _save_manifest(self, manifest: dict) -> None:
        manifest["updatedAt"] = _utc_now()
        _atomic_write_json(self.manifest_path, manifest)

    def _fetch(self, url: str) -> FetchResult:
        if self.fetch is None:
            raise RuntimeError("fetch function is not configured")
        return self.fetch(url)

    def run(self) -> dict:
        manifest = self._load_manifest()
        manifest["startUrl"] = self.start_url
        manifest["allowedRoot"] = self.allowed_root
        pages: dict[str, dict] = manifest.setdefault("pages", {})
        self.pages_dir.mkdir(parents=True, exist_ok=True)

        queue: deque[str] = deque([self.start_url])
        queued = {self.start_url}
        fetched = 0
        skipped = 0
        errors = 0

        while queue:
            if self.max_pages is not None and fetched >= self.max_pages:
                break
            url = queue.popleft()
            queued.discard(url)
            entry = pages.setdefault(url, {"discoveredAt": _utc_now()})
            file_name = entry.get("file")
            file_path = self.output_dir / file_name if isinstance(file_name, str) else None

            if entry.get("status") == "ok" and file_path is not None and file_path.exists():
                skipped += 1
                for child in entry.get("children", []):
                    if child not in queued:
                        queue.append(child)
                        queued.add(child)
                continue

            result = self._fetch(url)
            if result.status_code != 200:
                entry.update(
                    {
                        "status": "error",
                        "error": f"HTTP {result.status_code}",
                        "lastTriedAt": _utc_now(),
                    }
                )
                errors += 1
                self._save_manifest(manifest)
                continue

            final_url = normalize_its_url(result.final_url or url, result.final_url or url) or url
            raw_html = _decode_html(result.content)
            title = extract_title(raw_html)
            children = discover_links(raw_html, final_url, self.allowed_root)
            if not file_name:
                file_name = f"pages/{_next_page_file(pages, self.pages_dir)}"
            destination = self.output_dir / file_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(raw_html, encoding="utf-8")

            entry.update(
                {
                    "status": "ok",
                    "title": title,
                    "file": file_name,
                    "url": final_url,
                    "contentType": result.content_type or "text/html",
                    "children": children,
                    "fetchedAt": _utc_now(),
                    "error": None,
                }
            )
            fetched += 1
            for child in children:
                child_entry = pages.setdefault(child, {"discoveredAt": _utc_now()})
                child_entry.setdefault("parent", final_url)
                if child not in queued:
                    queue.append(child)
                    queued.add(child)
            self._save_manifest(manifest)
            if self.delay_seconds:
                time.sleep(self.delay_seconds)

        return {
            "pages": sum(1 for page in pages.values() if page.get("status") == "ok"),
            "errors": errors,
            "fetched": fetched,
            "skipped": skipped,
            "manifest": str(self.manifest_path),
        }


def crawl_its(
    *,
    start_url: str,
    output_dir: str | Path,
    cookies_json: str | Path | None = None,
    cookies: list[str] | None = None,
    headers: list[str] | None = None,
    timeout: float = 30.0,
    delay_seconds: float = 0.0,
    max_pages: int | None = None,
    user_agent: str = _DEFAULT_USER_AGENT,
) -> dict:
    cookie_jar = _load_cookie_jar(cookies_json)
    cookie_jar.update(_parse_name_value(cookies, "--cookie"))
    request_headers = {"User-Agent": user_agent}
    request_headers.update(_parse_name_value(headers, "--header"))

    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers=request_headers,
        cookies=cookie_jar,
    ) as client:
        def fetch(url: str) -> FetchResult:
            response = client.get(url)
            return FetchResult(
                status_code=response.status_code,
                content=response.content,
                content_type=response.headers.get("content-type"),
                final_url=str(response.url),
            )

        crawler = ItsCrawler(
            start_url=start_url,
            output_dir=output_dir,
            delay_seconds=delay_seconds,
            max_pages=max_pages,
            fetch=fetch,
        )
        return crawler.run()
