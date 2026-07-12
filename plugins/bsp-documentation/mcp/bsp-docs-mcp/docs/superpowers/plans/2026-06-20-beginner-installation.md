# Beginner Windows Installation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a beginner-safe Windows and Codex installation flow with an automated installer, complete manual fallback, verification, and troubleshooting.

**Architecture:** A root-level PowerShell installer copies the checked-out repository into the current user's global Codex MCP directory, creates a Python 3.12 virtual environment, and installs runtime dependencies. README presents the automated path first, then an explicit manual equivalent, while keeping API-key storage and Codex configuration as transparent user-controlled steps.

**Tech Stack:** Windows PowerShell 5.1, Python 3.12 `venv`/`pip`, Codex `config.toml`, pytest.

---

### Task 1: Testable PowerShell installer

**Files:**
- Create: `install.ps1`
- Create: `tests/test_installer.py`

- [ ] **Step 1: Write failing structural tests**

Add pytest checks that require `install.ps1` to use `$PSScriptRoot`, default to `%USERPROFILE%\.codex\mcp\bsp-docs-mcp`, validate `py -3.12`, install the package without `[dev]`, exclude secrets and development directories, and never accept an API key parameter.

- [ ] **Step 2: Run the installer tests and verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_installer.py -q`

Expected: failure because `install.ps1` does not exist.

- [ ] **Step 3: Implement `install.ps1`**

The script must expose only an optional `InstallDir` parameter:

```powershell
param(
    [string]$InstallDir = (Join-Path $env:USERPROFILE ".codex\mcp\bsp-docs-mcp")
)
```

It must verify Python 3.12, copy from `$PSScriptRoot` with `robocopy` while excluding `.git`, `.venv`, caches, logs, `.env`, and build artifacts, create the target virtual environment, run `pip install -e $InstallDir`, verify the bundled SQLite index, and print the next configuration steps without reading or writing the API key.

- [ ] **Step 4: Run focused tests and parser validation**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_installer.py -q
$null = [scriptblock]::Create((Get-Content -Raw -Encoding UTF8 .\install.ps1))
```

Expected: pytest passes and PowerShell reports no parser exception.

- [ ] **Step 5: Commit installer work**

```powershell
git add install.ps1 tests/test_installer.py
git commit -m "feat: add Windows installer"
```

### Task 2: Rewrite README for first-time users

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the installation flow**

Organize README in this order: purpose, bundled contents, prerequisites, download, quick installation, manual installation, API key, Codex configuration, verification, MCP tools, OpenRouter usage, reindexing/model changes, troubleshooting, developer tests.

- [ ] **Step 2: Make every command location explicit**

Before each PowerShell block, state whether it runs in the downloaded repository, installed MCP directory, or any PowerShell window. Include both GitHub ZIP and `git clone` download paths. Explain that `[dev]` is only for contributors.

- [ ] **Step 3: Preserve technical requirements**

Document the bundled `data/indexes/3.1/index.sqlite`, `qwen/qwen3-embedding-8b`, `env_vars = ["OPENROUTER_API_KEY"]`, relative project paths, token usage, required reindex after model changes, and version detection from `Configuration.distr`.

- [ ] **Step 4: Run README consistency checks**

Use an automated text check to confirm required headings, portable `%USERPROFILE%` paths, installer command, API-key explanation, bundled-index statement, model name, troubleshooting, and absence of a real `sk-or-v1-` key.

- [ ] **Step 5: Commit documentation**

```powershell
git add README.md
git commit -m "docs: add beginner Windows installation guide"
```

### Task 3: End-to-end verification and publication

**Files:**
- Verify: `install.ps1`
- Verify: `README.md`
- Verify: all tests under `tests/`

- [ ] **Step 1: Run the full automated test suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: all tests pass.

- [ ] **Step 2: Compile the Python package**

Run: `.\.venv\Scripts\python.exe -m compileall -q src`

Expected: exit code 0 and no errors.

- [ ] **Step 3: Test installation into an isolated temporary directory**

Invoke `install.ps1 -InstallDir <temporary-directory>`, verify `<temporary-directory>\.venv\Scripts\python.exe`, import `bsp_docs_mcp`, and verify `data\indexes\3.1\index.sqlite`. Remove the temporary installation after verification.

- [ ] **Step 4: Inspect repository state and commits**

Confirm only intended files changed, no `.env`, API keys, virtual environments, or temporary files are tracked, and the current branch is ahead of `origin/main` by the expected commits.

- [ ] **Step 5: Push to origin**

Run: `git push origin main`

Expected: `main` is updated successfully on GitHub.
