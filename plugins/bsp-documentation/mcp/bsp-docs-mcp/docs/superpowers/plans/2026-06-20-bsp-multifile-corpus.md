# BSP Multifile Corpus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild BSP 3.1 search from the complete versioned HTML tree while avoiding duplicate chapter indexes.

**Architecture:** Add a corpus discovery layer that selects leaf pages and standalone index pages, enrich parsed chunks with filesystem hierarchy and source paths, then rebuild the existing SQLite/embedding index atomically. Preserve the existing MCP contracts and major/minor version routing.

**Tech Stack:** Python 3.12, BeautifulSoup/lxml, SQLite FTS5, NumPy, OpenRouter embeddings, pytest.

---

### Task 1: Corpus discovery

**Files:**
- Create: `bsp-docs-mcp/src/bsp_docs_mcp/corpus.py`
- Create: `bsp-docs-mcp/tests/test_corpus.py`

- [ ] Test recursive discovery with ordinary pages, standalone `index.html`, and duplicate aggregate `index.html`.
- [ ] Implement deterministic selection and relative filesystem breadcrumbs.
- [ ] Run `pytest tests/test_corpus.py -q` and require success.

### Task 2: Page-aware parsing

**Files:**
- Modify: `bsp-docs-mcp/src/bsp_docs_mcp/parser.py`
- Modify: `bsp-docs-mcp/tests/test_parser.py`

- [ ] Add failing tests for `source_path` and deduplicated filesystem/internal breadcrumbs.
- [ ] Extend stable IDs and embedding text with source metadata.
- [ ] Run parser tests and require success.

### Task 3: Directory indexing and storage

**Files:**
- Modify: `bsp-docs-mcp/src/bsp_docs_mcp/storage.py`
- Modify: `bsp-docs-mcp/src/bsp_docs_mcp/indexer.py`
- Modify: `bsp-docs-mcp/src/bsp_docs_mcp/cli.py`
- Modify: `bsp-docs-mcp/tests/test_storage.py`
- Modify: `bsp-docs-mcp/tests/test_indexer.py`

- [ ] Add failing tests for source path persistence and directory index builds.
- [ ] Extend schema and build embeddings for the selected corpus.
- [ ] Support `--source` while retaining `--html` compatibility.
- [ ] Run focused tests and require success.

### Task 4: Rebuild and acceptance verification

**Files:**
- Modify: `bsp-docs-mcp/README.md`
- Replace generated: `bsp-docs-mcp/data/indexes/3.1/index.sqlite`

- [ ] Document the new source tree and indexing command.
- [ ] Run all tests and compileall.
- [ ] Inspect the real corpus and record selected/skipped counts.
- [ ] Rebuild version 3.1 using source version 3.1.11.
- [ ] Run the required semantic query and verify a program-interface page is in the top three.

