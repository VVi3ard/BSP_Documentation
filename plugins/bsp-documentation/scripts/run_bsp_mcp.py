"""Start the bundled BSP MCP from a private, user-writable Python environment."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MCP_ROOT = PLUGIN_ROOT / "mcp" / "bsp-docs-mcp"


def _runtime_root() -> Path:
    configured = os.getenv("BSP_DOCUMENTATION_RUNTIME_DIR")
    if configured:
        return Path(configured)
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "BSP_Documentation"
    return Path.home() / ".bsp_documentation"


def _venv_python(runtime_root: Path) -> Path:
    relative = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return runtime_root / "venv" / relative


def _ensure_runtime() -> Path:
    runtime_root = _runtime_root()
    python = _venv_python(runtime_root)
    if python.is_file():
        return python
    runtime_root.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "venv", str(runtime_root / "venv")], check=True)
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            str(MCP_ROOT),
        ],
        check=True,
    )
    return python


def main() -> None:
    python = _ensure_runtime()
    environment = os.environ.copy()
    environment["BSP_DOCS_DATA_DIR"] = str(PLUGIN_ROOT / "data")
    os.execve(
        str(python),
        [str(python), "-m", "bsp_docs_mcp", "serve"],
        environment,
    )


if __name__ == "__main__":
    main()
