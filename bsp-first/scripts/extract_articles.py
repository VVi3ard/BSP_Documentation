"""Скачивание и очистка статей Инфостарта в Markdown без изменения смысла.

Запуск:
    pip install beautifulsoup4 lxml
    python extract_articles.py <каталог вывода> <id статьи>...
    python extract_articles.py sources 1398340 1411756

Что делается (детерминированно, без LLM):
- берется только тело статьи (div.detail-text), кодировка windows-1251;
- заголовки -> #, блоки кода -> ```bsl, списки и таблицы - в текст;
- отрезается рекламный хвост (последний блок ## после текста статьи);
- строки-названия разделов (в HTML не размечены) становятся заголовками ###.
"""
import re
import sys
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

SKIP_TAGS = {"script", "style", "img", "iframe", "button", "form", "noscript"}
AD_MARKERS = ("## ТОП-5 инструментов", "## INFOSTART TOOLKIT")


def walk(el, out: list[str]) -> None:
    for c in el.children:
        if isinstance(c, NavigableString):
            if str(c).strip():
                out.append(re.sub(r"\s+", " ", str(c)))
            continue
        n = c.name
        if n in SKIP_TAGS:
            continue
        if n in ("h1", "h2", "h3", "h4", "h5"):
            out.append("\n\n" + "#" * int(n[1]) + " " + c.get_text(" ", strip=True) + "\n\n")
        elif n == "pre" or "code" in (c.get("class") or []):
            txt = c.get_text() if n == "pre" else c.get_text("\n")
            out.append("\n```bsl\n" + txt.strip("\n") + "\n```\n")
        elif n == "br":
            out.append("\n")
        elif n in ("p", "div", "ul", "ol", "table", "tr", "blockquote"):
            out.append("\n")
            walk(c, out)
            out.append("\n")
        elif n == "li":
            out.append("\n- ")
            walk(c, out)
        elif n in ("td", "th"):
            walk(c, out)
            out.append(" | ")
        else:
            walk(c, out)


def mark_sections(md: str) -> str:
    lines, code = [], False
    for line in md.split("\n"):
        if line.startswith("```"):
            code = not code
        if not code and re.match(r"^ [А-ЯЁA-Z][^.]{2,50}$", line):
            line = "### " + line.strip()
        lines.append(line)
    return "\n".join(lines)


def convert(html: bytes, url: str) -> str:
    soup = BeautifulSoup(html.decode("cp1251", "replace"), "lxml")
    out = [f"# {soup.find('h1').get_text(' ', strip=True)}\n\nИсточник: {url}\n"]
    walk(soup.find(class_="detail-text"), out)
    md = "".join(out)
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    for marker in AD_MARKERS:
        i = md.find(marker)
        if i > 0:
            md = md[:i]
    md = re.sub(r"^#####.*Часть 2.*\n", "", md, flags=re.M)  # ссылка на вторую часть
    return mark_sections(md).rstrip() + "\n"


def main() -> None:
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    for article_id in sys.argv[2:]:
        url = f"https://infostart.ru/1c/articles/{article_id}/"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        md = convert(urllib.request.urlopen(req).read(), url)
        (out_dir / f"{article_id}.md").write_text(md, encoding="utf-8")
        print(f"{article_id}: {len(md)} знаков")


if __name__ == "__main__":
    main()
