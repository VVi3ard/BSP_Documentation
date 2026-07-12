from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.ps1"


def installer_text() -> str:
    assert INSTALLER.exists(), "install.ps1 must exist in the repository root"
    return INSTALLER.read_text(encoding="utf-8")


def test_installer_uses_repository_and_portable_default_path():
    text = installer_text()

    assert "$PSScriptRoot" in text
    assert "$env:USERPROFILE" in text
    assert ".codex\\mcp\\bsp-docs-mcp" in text
    assert "volos" not in text.lower()


def test_installer_requires_python_312_and_creates_virtual_environment():
    text = installer_text()

    assert re.search(r"\bpy(?:\.exe)?\s+-3\.12\s+--version\b", text)
    assert re.search(r"\bpy(?:\.exe)?\s+-3\.12\s+-m\s+venv\b", text)


def test_installer_copies_safely_and_installs_runtime_dependencies_only():
    text = installer_text()

    assert "robocopy" in text.lower()
    for excluded in (".git", ".venv", ".pytest_cache", "__pycache__", ".env"):
        assert excluded in text
    assert re.search(r"pip(?:\.exe)?['\"]?\s+-m\s+pip\s+install", text) is None
    assert "-m pip install" in text
    assert "-e" in text
    assert ".[dev]" not in text


def test_installer_does_not_accept_or_store_an_api_key():
    text = installer_text()
    param_block = re.search(r"param\s*\((.*?)\)\s*\n", text, re.DOTALL | re.IGNORECASE)

    assert param_block is not None
    assert "API_KEY" not in param_block.group(1).upper()
    assert "sk-or-v1-" not in text


def test_installer_verifies_bundled_index():
    text = installer_text()

    assert "data\\indexes\\3.1\\index.sqlite" in text
    assert "Test-Path" in text


def test_installer_parses_with_powershell_51_default_encoding():
    escaped_path = str(INSTALLER).replace("'", "''")
    command = (
        "$null = [scriptblock]::Create("
        f"(Get-Content -Raw -LiteralPath '{escaped_path}'))"
    )

    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode(errors="replace")
