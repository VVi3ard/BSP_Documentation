from pathlib import Path
import json

from bsp_docs_mcp.crawler import FetchResult, ItsCrawler, discover_links, normalize_its_url


def test_normalize_its_url_supports_relative_and_legacy_links() -> None:
    source = "https://its.1c.ru/db/content/bsp3111doc/src/chapter.htm#_print"
    legacy = "/db/bsp3111doc/content/src/subsystem.htm_"

    assert normalize_its_url("subsystem.htm_", source) == (
        "https://its.1c.ru/db/content/bsp3111doc/src/subsystem.htm#_print"
    )
    assert normalize_its_url(legacy, source) == (
        "https://its.1c.ru/db/content/bsp3111doc/src/subsystem.htm#_print"
    )


def test_discover_links_keeps_only_allowed_its_pages() -> None:
    html = """
    <html><body>
      <a href="one.htm_">One</a>
      <a href="/db/content/bsp3111doc/src/two.htm_">Two</a>
      <a href="https://its.1c.ru/db/content/bsp3111doc/src/two.htm_">Two dup</a>
      <a href="https://example.com/outside">Outside</a>
      <a href="#local">Local</a>
    </body></html>
    """
    source = "https://its.1c.ru/db/content/bsp3111doc/src/root.htm#_print"
    allowed_root = "https://its.1c.ru/db/content/bsp3111doc/src/"

    assert discover_links(html, source, allowed_root) == [
        "https://its.1c.ru/db/content/bsp3111doc/src/one.htm#_print",
        "https://its.1c.ru/db/content/bsp3111doc/src/two.htm#_print",
    ]


def test_crawler_writes_manifest_and_resumes_without_refetch(tmp_path: Path) -> None:
    responses = {
        "https://its.1c.ru/db/content/bsp3111doc/src/root.htm#_print": (
            "<html><body><h1>Глава 1. Состав библиотеки</h1>"
            '<a href="child.htm_">Child</a></body></html>'
        ),
        "https://its.1c.ru/db/content/bsp3111doc/src/child.htm#_print": (
            "<html><body><h1>Child</h1><p>Done</p></body></html>"
        ),
    }
    calls: list[str] = []

    def fetch(url: str) -> FetchResult:
        calls.append(url)
        return FetchResult(status_code=200, content=responses[url].encode("utf-8"))

    output = tmp_path / "crawl"
    crawler = ItsCrawler(
        start_url="https://its.1c.ru/db/content/bsp3111doc/src/root.htm#_print",
        output_dir=output,
        fetch=fetch,
    )

    first = crawler.run()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert first["pages"] == 2
    assert calls == [
        "https://its.1c.ru/db/content/bsp3111doc/src/root.htm#_print",
        "https://its.1c.ru/db/content/bsp3111doc/src/child.htm#_print",
    ]
    assert manifest["pages"]["https://its.1c.ru/db/content/bsp3111doc/src/child.htm#_print"]["parent"] == (
        "https://its.1c.ru/db/content/bsp3111doc/src/root.htm#_print"
    )
    assert (output / "pages" / "0001.html").exists()
    assert (output / "pages" / "0002.html").exists()

    second = crawler.run()

    assert second["fetched"] == 0
    assert second["skipped"] >= 1
    assert calls == [
        "https://its.1c.ru/db/content/bsp3111doc/src/root.htm#_print",
        "https://its.1c.ru/db/content/bsp3111doc/src/child.htm#_print",
    ]
