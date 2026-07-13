"""Runtime paths and environment configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    bsp_cache_root: Path
    openrouter_api_key: str | None
    openrouter_base_url: str
    embedding_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        codex_home = Path(
            os.getenv("CODEX_HOME", Path.home() / ".codex")
        )
        return cls(
            data_dir=Path(os.getenv("BSP_DOCS_DATA_DIR", PROJECT_ROOT / "data")),
            bsp_cache_root=Path(
                os.getenv("BSP_DOCUMENTATION_CACHE_DIR", codex_home / "bsp")
            ),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
            openrouter_base_url=os.getenv(
                "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
            ).rstrip("/"),
            embedding_model=os.getenv(
                "BSP_EMBEDDING_MODEL", "qwen/qwen3-embedding-8b"
            ),
        )

    def index_path(self, family: str) -> Path:
        return self.data_dir / "indexes" / family / "index.sqlite"
