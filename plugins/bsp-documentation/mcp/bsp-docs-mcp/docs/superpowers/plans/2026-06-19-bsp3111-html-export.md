# BSP 3.1.11 Clean HTML Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export the authenticated `bsp3111doc` documentation into a resumable, validated, cleaned HTML tree under `bsp-docs-mcp/data/sources/3.1.11/`.

**Architecture:** A small JavaScript capture adapter runs inside the already authenticated in-app browser session, follows direct printable BSP source pages, and stores raw HTML plus downloaded image assets in a staging directory. A Python transformation pipeline uses BeautifulSoup to build the Russian-named directory tree, rewrite local links and assets, generate navigation and manifests, and validate the offline result without handling credentials or cookies.

**Tech Stack:** Node.js ESM and built-in `node:test`, in-app Browser `Tab`/`pageAssets` APIs, Python 3.11+, BeautifulSoup/lxml, pytest.

---

## File map

- `bsp-docs-mcp/tools/bsp_export/capture.mjs` — authenticated navigation, source URL discovery, raw capture, image bundling, and resume state.
- `bsp-docs-mcp/tools/bsp_export/urls.mjs` — pure BSP URL recognition and printable-source conversion.
- `bsp-docs-mcp/tools/bsp_export/run_capture.mjs` — narrow entry point imported from the browser session.
- `bsp-docs-mcp/tests_js/bsp_export_urls.test.mjs` — URL conversion tests independent of a live browser.
- `bsp-docs-mcp/src/bsp_docs_mcp/html_export.py` — path allocation, HTML cleanup, relative-link rewriting, and output generation.
- `bsp-docs-mcp/src/bsp_docs_mcp/html_validation.py` — offline link, anchor, resource, authentication-page, and UTF-8 checks.
- `bsp-docs-mcp/tests/test_html_export.py` — deterministic unit tests for paths, cleanup, navigation, links, and assets.
- `bsp-docs-mcp/tests/test_html_validation.py` — validator tests using temporary output trees.
- `bsp-docs-mcp/src/bsp_docs_mcp/cli.py` — `export-html` and `validate-html` commands for the transform phase.
- `bsp-docs-mcp/README.md` — capture, resume, transform, and validation instructions.
- `bsp-docs-mcp/data/sources/3.1.11/` — generated deliverable; not used for temporary capture state.

### Task 1: Pure BSP URL routing

**Files:**
- Create: `bsp-docs-mcp/tools/bsp_export/urls.mjs`
- Create: `bsp-docs-mcp/tests_js/bsp_export_urls.test.mjs`

- [ ] **Step 1: Write failing URL tests**

```js
import test from "node:test";
import assert from "node:assert/strict";
import { printableUrl, isBspSourceLink } from "../tools/bsp_export/urls.mjs";

test("converts a source navigation link to the direct printable page", () => {
  const input = "https://its.1c.ru/db/bsp3111doc/content/src/глава 4. программный интерфейс.htm_";
  assert.equal(
    printableUrl(input),
    "https://its.1c.ru/db/content/bsp3111doc/src/%D0%B3%D0%BB%D0%B0%D0%B2%D0%B0%204.%20%D0%BF%D1%80%D0%BE%D0%B3%D1%80%D0%B0%D0%BC%D0%BC%D0%BD%D1%8B%D0%B9%20%D0%B8%D0%BD%D1%82%D0%B5%D1%80%D1%84%D0%B5%D0%B9%D1%81.htm#_print",
  );
});

test("accepts only links inside bsp3111doc source content", () => {
  assert.equal(isBspSourceLink("/db/bsp3111doc/content/src/банки.htm_"), true);
  assert.equal(isBspSourceLink("/db/v8std/content/1/hdoc"), false);
  assert.equal(isBspSourceLink("javascript:"), false);
});
```

- [ ] **Step 2: Run the test and verify the expected failure**

Run: `node --test tests_js/bsp_export_urls.test.mjs`

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `urls.mjs`.

- [ ] **Step 3: Implement strict URL conversion**

```js
const ORIGIN = "https://its.1c.ru";
const SOURCE_PREFIX = "/db/bsp3111doc/content/src/";

export function isBspSourceLink(value) {
  const url = new URL(value, ORIGIN);
  return url.origin === ORIGIN && url.pathname.startsWith(SOURCE_PREFIX) && url.pathname.endsWith(".htm_");
}

export function printableUrl(value) {
  if (!isBspSourceLink(value)) throw new Error(`Not a bsp3111doc source link: ${value}`);
  const url = new URL(value, ORIGIN);
  const name = decodeURIComponent(url.pathname.slice(SOURCE_PREFIX.length, -1));
  return `${ORIGIN}/db/content/bsp3111doc/src/${encodeURIComponent(name).replaceAll("%2F", "/")}#_print`;
}

export const ROOT_PRINT_URL = `${ORIGIN}/db/content/bsp3111doc/src/index.htm#_print`;
```

- [ ] **Step 4: Run the focused test**

Run: `node --test tests_js/bsp_export_urls.test.mjs`

Expected: 2 tests PASS.

- [ ] **Step 5: Commit URL routing**

```powershell
git add bsp-docs-mcp/tools/bsp_export/urls.mjs bsp-docs-mcp/tests_js/bsp_export_urls.test.mjs
git commit -m "feat: add BSP source URL routing"
```

### Task 2: Authenticated, resumable raw capture

**Files:**
- Create: `bsp-docs-mcp/tools/bsp_export/capture.mjs`
- Create: `bsp-docs-mcp/tools/bsp_export/run_capture.mjs`

- [ ] **Step 1: Define the capture record and browser contract**

Implement the exported async function `captureDocumentation` with one object
argument containing `tab`, `stagingDir`, `startUrl`, `maxPages` (default
`Infinity`), and `delayMs` (default `150`). It returns the final capture
manifest. The manifest schema is `{schemaVersion, startUrl, pages}`, where each
page contains `sourceUrl`, `title`, `parentUrl`, `rawHtmlPath`, `links`,
`assets`, `status`, and `error`.

The function must accept the browser `tab` as a dependency; it must not read or persist credentials, cookies, local storage, or browser profile data.

- [ ] **Step 2: Add atomic UTF-8 JSON and file helpers**

```js
async function writeAtomic(path, value) {
  const temporary = `${path}.tmp`;
  await fs.writeFile(temporary, value, "utf8");
  await fs.rename(temporary, path);
}

async function writeJson(path, value) {
  await writeAtomic(path, `${JSON.stringify(value, null, 2)}\n`);
}
```

- [ ] **Step 3: Capture one direct page through a bounded DOM read**

After `await tab.goto(url)`, call one `tab.playwright.evaluate` that returns:

```js
() => ({
  title: document.title.replace(/\s*::.*$/, "").trim(),
  html: `<!doctype html>\n${document.documentElement.outerHTML}`,
  sourceLinks: Array.from(document.querySelectorAll(".index a[href]"), a => ({
    href: a.href,
    title: (a.textContent || "").trim(),
  })),
  restricted: /Доступ к данному материалу ограничен|Войти на сайт/.test(document.body.innerText),
})
```

Reject the page before writing it when `restricted` is true or the captured HTML has no `<h1`.

- [ ] **Step 4: Discover children and persist progress after every page**

Use a FIFO queue beginning with `ROOT_PRINT_URL`. Keep `queued` and `visited` sets keyed by printable URL. Only `.index` source links accepted by `isBspSourceLink` enter the queue. Store the discovery edge as `parentUrl`; if a page is linked from several parents, retain its first discovery parent and record other links only as cross-links.

Write raw pages under `bsp-docs-mcp/.tmp/bsp3111-capture/pages/<sha256>.html`. Update `capture-manifest.json` atomically after every success or error. On restart, skip records with `status: "ok"` whose raw file still exists and retry records with `status: "error"`.

- [ ] **Step 5: Bundle observed images without exporting authentication state**

For every captured page:

```js
const assets = await tab.capabilities.get("pageAssets");
const inventory = await assets.list();
const bundle = await assets.bundle({ inventoryId: inventory.id, kinds: ["image"] });
```

Copy successful files into `<stagingDir>/assets/<sha256-of-url><extension>`, deduplicated by absolute URL. Store `{url, path, contentType}` in the capture manifest. Record bundle failures on the page record. Do not bundle site stylesheets, scripts, fonts, or video.

- [ ] **Step 6: Add the browser-session entry point**

```js
import { captureDocumentation } from "./capture.mjs";
import { ROOT_PRINT_URL } from "./urls.mjs";

export async function runCapture(tab, workspaceRoot) {
  return captureDocumentation({
    tab,
    startUrl: ROOT_PRINT_URL,
    stagingDir: `${workspaceRoot}/bsp-docs-mcp/.tmp/bsp3111-capture`,
  });
}
```

- [ ] **Step 7: Run a three-page browser smoke capture**

Import `runCapture` from the browser session and call `captureDocumentation` with `maxPages: 3`. Expected: three UTF-8 raw HTML files, a valid manifest, no restricted-access marker, and at least one discovered child queued.

- [ ] **Step 8: Commit capture support**

```powershell
git add bsp-docs-mcp/tools/bsp_export/capture.mjs bsp-docs-mcp/tools/bsp_export/run_capture.mjs
git commit -m "feat: capture authenticated BSP documentation"
```

### Task 3: Deterministic Russian directory allocation

**Files:**
- Create: `bsp-docs-mcp/src/bsp_docs_mcp/html_export.py`
- Create: `bsp-docs-mcp/tests/test_html_export.py`

- [ ] **Step 1: Write failing path-allocation tests**

```python
from bsp_docs_mcp.html_export import safe_name, allocate_paths


def test_safe_name_preserves_cyrillic_and_removes_windows_characters() -> None:
    assert safe_name('Работа с файлами: интерфейс? ') == 'Работа с файлами_ интерфейс_'


def test_allocate_paths_follows_parent_hierarchy_and_disambiguates() -> None:
    pages = [
        {"sourceUrl": "root", "title": "Документация", "parentUrl": None},
        {"sourceUrl": "a", "title": "Глава", "parentUrl": "root"},
        {"sourceUrl": "b", "title": "Интерфейс", "parentUrl": "a"},
        {"sourceUrl": "c", "title": "Интерфейс", "parentUrl": "a"},
    ]
    paths = allocate_paths(pages)
    assert paths["b"].as_posix() == "Глава/Интерфейс/index.html"
    assert paths["c"].as_posix().startswith("Глава/Интерфейс-")
```

- [ ] **Step 2: Verify the tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_html_export.py -q`

Expected: collection error for missing `bsp_docs_mcp.html_export`.

- [ ] **Step 3: Implement `safe_name` and `allocate_paths`**

Use `re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).rstrip(' .')`. Reserve Windows device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`) by suffixing `_`. Resolve sibling collisions case-insensitively with `-<first-eight-hex-of-sha256-source-url>`. Detect missing parents and cycles with explicit `ValueError` messages.

- [ ] **Step 4: Run the focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_html_export.py -q`

Expected: path tests PASS.

- [ ] **Step 5: Commit path allocation**

```powershell
git add bsp-docs-mcp/src/bsp_docs_mcp/html_export.py bsp-docs-mcp/tests/test_html_export.py
git commit -m "feat: allocate BSP export directories"
```

### Task 4: Clean HTML generation and local link rewriting

**Files:**
- Modify: `bsp-docs-mcp/src/bsp_docs_mcp/html_export.py`
- Modify: `bsp-docs-mcp/tests/test_html_export.py`

- [ ] **Step 1: Add failing cleanup and rewriting tests**

Create fixtures containing `script`, `.index`, a local BSP source link with a fragment, an external `/db/v8std` link, an image, table, `pre`, and warning paragraph. Assert that `render_page` removes scripts and source `.index`, preserves semantic content, converts the internal link to a relative `index.html#anchor`, keeps the external URL absolute, rewrites the image to the root `assets/` path, and includes links to the parent and root indexes.

- [ ] **Step 2: Verify the focused test fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_html_export.py::test_render_page_cleans_and_rewrites -q`

Expected: FAIL because `render_page` is not defined.

- [ ] **Step 3: Implement the transformation interfaces**

Define the immutable `ExportContext` dataclass with `output_root: Path`,
`page_paths: dict[str, Path]`, and `asset_paths: dict[str, Path]`. Implement
`render_page(raw_html: str, page: dict, context: ExportContext) -> str` and
`export_capture(capture_manifest: Path, output_root: Path) -> dict`.

`render_page` must parse with `BeautifulSoup(raw_html, "lxml")`, remove all `script`, `style`, `.index`, tracking and site-navigation elements, and build a new UTF-8 HTML document containing only the article body. Rewrite links by converting recognized source URLs through the manifest lookup and `os.path.relpath`; preserve fragments. Convert same-origin non-BSP links and all outside-document links to absolute HTTPS URLs. Rewrite known asset URLs to relative local paths and leave missing assets recorded as errors rather than silently deleting their elements.

- [ ] **Step 4: Add shared offline CSS and local navigation**

Generate `assets/documentation.css` with readable typography, bounded content width, responsive tables, monospace `pre/code`, visible note/warning blocks, and print rules. Every page references this file relatively and contains `Оглавление` plus `Вверх` when it has a parent.

- [ ] **Step 5: Generate the root table of contents and manifests**

`export_capture` writes each page through a temporary sibling and atomic replace, creates a nested root `index.html`, and writes:

```json
{
  "schemaVersion": 1,
  "source": "https://its.1c.ru/db/bsp3111doc",
  "version": "3.1.11",
  "pages": [{"sourceUrl": "https://its.1c.ru/db/content/bsp3111doc/src/index.htm#_print", "title": "Библиотека стандартных подсистем 3.1.11. Документация", "path": "index.html", "parentUrl": null}],
  "assets": [{"sourceUrl": "https://its.1c.ru/db/content/bsp3111doc/src/image001.png", "path": "assets/35ec90f2.png"}]
}
```

Write `export-errors.json` even when empty, using `{ "errors": [] }`.

- [ ] **Step 6: Run transformation tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_html_export.py -q`

Expected: all HTML export tests PASS.

- [ ] **Step 7: Commit clean HTML generation**

```powershell
git add bsp-docs-mcp/src/bsp_docs_mcp/html_export.py bsp-docs-mcp/tests/test_html_export.py
git commit -m "feat: generate cleaned offline BSP HTML"
```

### Task 5: Offline validation

**Files:**
- Create: `bsp-docs-mcp/src/bsp_docs_mcp/html_validation.py`
- Create: `bsp-docs-mcp/tests/test_html_validation.py`

- [ ] **Step 1: Write failing validator tests**

```python
from bsp_docs_mcp.html_validation import validate_export


def test_validator_reports_missing_file_anchor_and_auth_page(tmp_path) -> None:
    (tmp_path / "index.html").write_text(
        '<a href="missing/index.html">x</a><a href="#absent">y</a>'
        '<p>Доступ к данному материалу ограничен</p>', encoding="utf-8"
    )
    errors = validate_export(tmp_path)
    assert {item.code for item in errors} == {"missing-file", "missing-anchor", "restricted-page"}
```

- [ ] **Step 2: Verify the test fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_html_validation.py -q`

Expected: collection error for missing module.

- [ ] **Step 3: Implement deterministic validation**

Define the immutable `ValidationError` dataclass with string fields `code`,
`page`, `target`, and `message`. Implement
`validate_export(root: Path) -> list[ValidationError]`.

Walk every `*.html` in sorted order. Decode strictly as UTF-8. Check local `href` files and fragments, `src` files, duplicate manifest paths, authentication/restriction text, and the presence of every manifest page. Ignore `http:`, `https:`, `mailto:`, and `javascript:` targets. Return errors in stable `(page, code, target)` order.

- [ ] **Step 4: Run validator tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_html_validation.py -q`

Expected: all validator tests PASS.

- [ ] **Step 5: Commit validation**

```powershell
git add bsp-docs-mcp/src/bsp_docs_mcp/html_validation.py bsp-docs-mcp/tests/test_html_validation.py
git commit -m "feat: validate offline BSP export"
```

### Task 6: CLI integration and operator documentation

**Files:**
- Modify: `bsp-docs-mcp/src/bsp_docs_mcp/cli.py`
- Modify: `bsp-docs-mcp/README.md`
- Modify: `.gitignore`

- [ ] **Step 1: Add CLI parser tests for transform and validation commands**

Add tests that call `main(["export-html", "--capture", capture_path, "--output", output_path])` and `main(["validate-html", "--root", output_path])`. Assert return code `0` for a valid fixture and `1` when validation finds a broken local link.

- [ ] **Step 2: Add CLI subcommands**

```python
export_html = subcommands.add_parser("export-html")
export_html.add_argument("--capture", required=True, type=Path)
export_html.add_argument("--output", required=True, type=Path)

validate_html = subcommands.add_parser("validate-html")
validate_html.add_argument("--root", required=True, type=Path)
```

`export-html` calls `export_capture` and then `validate_export`; `validate-html` prints one line per validation error. Both return `1` when errors exist.

- [ ] **Step 3: Keep staging data ignored and the deliverable trackable**

Add only `bsp-docs-mcp/.tmp/` to `.gitignore` if not already present. Do not ignore `bsp-docs-mcp/data/sources/3.1.11/`.

- [ ] **Step 4: Document exact operating commands**

Document: authenticate in the in-app browser; run/import `run_capture.mjs` against the selected tab; resume with the same staging path; transform with:

```powershell
.\.venv\Scripts\python.exe -m bsp_docs_mcp export-html `
  --capture ".\.tmp\bsp3111-capture\capture-manifest.json" `
  --output ".\data\sources\3.1.11"
```

and validate with:

```powershell
.\.venv\Scripts\python.exe -m bsp_docs_mcp validate-html `
  --root ".\data\sources\3.1.11"
```

- [ ] **Step 5: Run focused and full verification**

Run:

```powershell
node --test tests_js/*.test.mjs
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src
```

Expected: all Node and Python tests pass; compileall exits `0`.

- [ ] **Step 6: Commit CLI and documentation**

```powershell
git add .gitignore bsp-docs-mcp/src/bsp_docs_mcp/cli.py bsp-docs-mcp/README.md
git commit -m "docs: add BSP HTML export workflow"
```

### Task 7: Full authenticated export and acceptance checks

**Files:**
- Generate: `bsp-docs-mcp/data/sources/3.1.11/**`

- [ ] **Step 1: Run the full capture from the authenticated browser**

Call `runCapture(tab, "D:/Documents/Настройка ИИ")`. Keep the in-app browser session open. Expected: the queue drains, every manifest page has `status: "ok"`, and no page contains an access restriction marker.

- [ ] **Step 2: Transform the capture**

Run the documented `export-html` command. Expected: exit code `0`, generated Russian-named directories, root `index.html`, `manifest.json`, `export-errors.json`, and `assets/`.

- [ ] **Step 3: Validate all local references**

Run the documented `validate-html` command. Expected: exit code `0` and `0 validation errors`.

- [ ] **Step 4: Perform representative content checks**

Verify one ordinary article, one table-heavy page, one code/API page, and one page with images. Confirm Cyrillic names display correctly, tables and code remain readable, images resolve locally, and parent/root navigation works.

- [ ] **Step 5: Record export counts and commit the deliverable**

Record page and asset counts in `README.md`, stage only `bsp-docs-mcp/data/sources/3.1.11/` plus the count update, and commit:

```powershell
git add bsp-docs-mcp/data/sources/3.1.11 bsp-docs-mcp/README.md
git commit -m "data: add BSP 3.1.11 offline documentation"
```
