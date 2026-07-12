# BSP Documentation MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an MCP server that searches versioned BSP HTML documentation using OpenRouter Qwen3 embeddings and SQLite FTS5, with every documentation lookup scoped to the BSP major/minor version.

**Architecture:** Store original documentation under its full release version and build one SQLite index per compatible major/minor family. Parse the HTML into stable hierarchical sections, store text and vectors in SQLite, combine exact cosine similarity with FTS5 BM25 through reciprocal-rank fusion, and expose version-aware MCP tools over STDIO.

**Tech Stack:** Python 3.11+, MCP Python SDK/FastMCP, BeautifulSoup/lxml, SQLite FTS5, NumPy, HTTPX, pytest.

---

### Task 1: Project skeleton and version rules

**Files:**
- Create: `bsp-docs-mcp/pyproject.toml`
- Create: `bsp-docs-mcp/src/bsp_docs_mcp/versions.py`
- Create: `bsp-docs-mcp/tests/test_versions.py`

- [ ] Add packaging, runtime dependencies, console entry points, and pytest configuration.
- [ ] Test normalization of dotted/underscored full versions to the `major.minor` family.
- [ ] Test extraction of the nearest quoted version preceding `БиблиотекаСтандартныхПодсистем` in `Configuration.distr` content.
- [ ] Implement strict version parsing and clear errors for absent BSP metadata.
- [ ] Run `pytest tests/test_versions.py -q`; expect all tests to pass.

### Task 2: Structured HTML ingestion

**Files:**
- Create: `bsp-docs-mcp/src/bsp_docs_mcp/parser.py`
- Create: `bsp-docs-mcp/tests/test_parser.py`
- Copy: source BSP HTML to `bsp-docs-mcp/data/sources/3.1.11.155/Документация.html`

- [ ] Test heading breadcrumbs, anchors, code preservation, recommendation flags, and deterministic chunk IDs.
- [ ] Implement flat, non-overlapping heading chunks with hierarchical breadcrumbs and bounded subchunks.
- [ ] Copy the UTF-8 HTML without modifying the installed 1C template.
- [ ] Run `pytest tests/test_parser.py -q`; expect all tests to pass.

### Task 3: Versioned SQLite index and OpenRouter embeddings

**Files:**
- Create: `bsp-docs-mcp/src/bsp_docs_mcp/config.py`
- Create: `bsp-docs-mcp/src/bsp_docs_mcp/embeddings.py`
- Create: `bsp-docs-mcp/src/bsp_docs_mcp/storage.py`
- Create: `bsp-docs-mcp/src/bsp_docs_mcp/indexer.py`
- Create: `bsp-docs-mcp/tests/test_storage.py`
- Create: `bsp-docs-mcp/tests/test_embeddings.py`

- [ ] Test OpenRouter request/response handling without making a network request.
- [ ] Test SQLite schema, FTS5 candidates, vector persistence, source/model metadata, and query cache.
- [ ] Implement batched `qwen/qwen3-embedding-8b` requests using `OPENROUTER_API_KEY`.
- [ ] Implement atomic index replacement under `data/indexes/<major.minor>/index.sqlite`.
- [ ] Run the focused storage and embedding tests; expect all tests to pass.

### Task 4: Hybrid retrieval

**Files:**
- Create: `bsp-docs-mcp/src/bsp_docs_mcp/search.py`
- Create: `bsp-docs-mcp/tests/test_search.py`

- [ ] Test exact vector ranking, BM25 ranking, reciprocal-rank fusion, version isolation, and missing-version errors.
- [ ] Implement normalized exact cosine similarity over all vectors and BM25 candidate retrieval.
- [ ] Return concise excerpts, hierarchy, source version, recommendation flags, and HTML anchors.
- [ ] Run `pytest tests/test_search.py -q`; expect all tests to pass.

### Task 5: MCP tools and CLI

**Files:**
- Create: `bsp-docs-mcp/src/bsp_docs_mcp/server.py`
- Create: `bsp-docs-mcp/src/bsp_docs_mcp/cli.py`
- Create: `bsp-docs-mcp/src/bsp_docs_mcp/__init__.py`
- Create: `bsp-docs-mcp/src/bsp_docs_mcp/__main__.py`
- Create: `bsp-docs-mcp/tests/test_server.py`

- [ ] Test tool functions with a temporary index and fake embedder.
- [ ] Expose `search_bsp`, `get_bsp_section`, `detect_bsp_version`, and `list_bsp_versions`.
- [ ] Require `version` for all documentation lookup tools and normalize full versions to major/minor.
- [ ] Add MCP initialization instructions describing `src/Configuration/Configuration.distr` detection.
- [ ] Add CLI commands for indexing and STDIO serving.
- [ ] Run `pytest tests/test_server.py -q`; expect all tests to pass.

### Task 6: Documentation and full verification

**Files:**
- Create: `bsp-docs-mcp/README.md`
- Create: `bsp-docs-mcp/.env.example`
- Modify: `.gitignore`

- [ ] Document environment setup, OpenRouter funding/key configuration, index construction, Codex MCP configuration, tool contracts, and version behavior.
- [ ] Ensure secrets and generated indexes are ignored while the copied source HTML remains tracked.
- [ ] Run `python -m compileall src`; expect success.
- [ ] Run `pytest -q`; expect all tests to pass.
- [ ] Run CLI help and a parser smoke test against the copied BSP HTML; expect successful output and nonzero chunks.
