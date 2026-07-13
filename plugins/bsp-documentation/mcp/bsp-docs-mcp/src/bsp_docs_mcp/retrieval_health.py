"""Canary checks for detecting incompatible embedding-space changes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from time import monotonic

import numpy as np

from .embeddings import Embedder
from .search import SearchEngine


@dataclass(frozen=True, slots=True)
class RetrievalCanary:
    query: str
    expected_section_id: str
    mode: str = "development"
    subsystem: str | None = None
    api_group: str | None = None
    top_k: int = 8


CANARIES = (
    RetrievalCanary(
        query="Как скопировать прикрепленные файлы с одного объекта на другой?",
        subsystem="Работа с файлами",
        expected_section_id="adf28762b4f340639ca71f95",
    ),
    RetrievalCanary(
        query="Как проверить, включено ли хранение истории изменений объекта?",
        subsystem="Версионирование объектов",
        expected_section_id="274774382978a64d61573053",
    ),
    RetrievalCanary(
        query="Как определить, требуется ли обновление структуры информационной базы?",
        subsystem="Обновление версии ИБ",
        expected_section_id="3b5057dd328c48e2d975ca1d",
    ),
    RetrievalCanary(
        query="Как узнать, актуален ли индекс глобального поиска?",
        subsystem="Полнотекстовый поиск",
        expected_section_id="cefa3d1ca6a76eb05f8c1c1d",
    ),
    RetrievalCanary(
        query="Как расширить набор возможных прав для настройки доступа к объектам?",
        mode="override",
        subsystem="Управление доступом",
        expected_section_id="bfbb5ba7a70506ded44201cd",
    ),
)


class RetrievalHealthCheck:
    """Run fresh canary embeddings once per index/model/TTL interval."""

    def __init__(self, ttl_seconds: float = 24 * 60 * 60) -> None:
        self.ttl_seconds = ttl_seconds
        self._lock = Lock()
        self._fingerprint: tuple[object, ...] | None = None
        self._checked_at: float | None = None

    def ensure_valid(
        self,
        index_path: Path,
        engine: SearchEngine,
        embedder: Embedder,
        user_query: str,
    ) -> np.ndarray | None:
        """Return a freshly batched user vector when a health check was required."""

        fingerprint = self._index_fingerprint(index_path, engine)
        now = monotonic()
        if not self._is_due(fingerprint, now):
            return None

        with self._lock:
            now = monotonic()
            if not self._is_due(fingerprint, now):
                return None

            texts = [canary.query for canary in CANARIES] + [user_query]
            vectors = embedder.embed_queries(texts)
            failures: list[str] = []
            for canary, vector in zip(CANARIES, vectors[:-1], strict=True):
                results = engine.search(
                    canary.query,
                    limit=canary.top_k,
                    mode=canary.mode,
                    subsystem=canary.subsystem,
                    api_group=canary.api_group,
                    query_vector=vector,
                )
                result_ids = [str(result["id"]) for result in results]
                if canary.expected_section_id not in result_ids:
                    failures.append(
                        f"{canary.expected_section_id} not in top-{canary.top_k} "
                        f"for {canary.query!r}"
                    )

            if failures:
                raise RuntimeError(
                    "BSP embedding retrieval health check failed; the provider model "
                    "may no longer match the shipped index. Rebuild the index or restore "
                    "the compatible embedding model. Failures: "
                    + "; ".join(failures)
                )

            self._fingerprint = fingerprint
            self._checked_at = now
            return vectors[-1]

    def _is_due(self, fingerprint: tuple[object, ...], now: float) -> bool:
        return (
            self._fingerprint != fingerprint
            or self._checked_at is None
            or now - self._checked_at >= self.ttl_seconds
        )

    @staticmethod
    def _index_fingerprint(
        index_path: Path, engine: SearchEngine
    ) -> tuple[object, ...]:
        metadata = engine.metadata
        return (
            str(index_path.resolve()),
            engine.embedder.model,
            metadata.get("model"),
            metadata.get("source_version"),
            metadata.get("chunk_count"),
            metadata.get("built_at"),
        )
