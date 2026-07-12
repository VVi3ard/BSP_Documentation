"""Hybrid exact-vector and FTS5 retrieval."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .embeddings import Embedder
from .storage import IndexDatabase


class SearchEngine:
    def __init__(self, index_path: str | __import__("pathlib").Path, embedder: Embedder) -> None:
        self.index_path = index_path
        self.embedder = embedder
        with IndexDatabase(index_path) as database:
            metadata = database.metadata()
            expected_model = metadata.get("model")
            if expected_model and expected_model != embedder.model:
                raise ValueError(
                    f"Index uses embedding model {expected_model!r}, "
                    f"but runtime is configured for {embedder.model!r}"
                )
            self.metadata = metadata
            self._ids, self._vectors = database.all_vectors()

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        mode: str = "all",
        subsystem: str | None = None,
        api_group: str | None = None,
    ) -> list[dict[str, object]]:
        query = query.strip()
        if not query:
            raise ValueError("Search query must not be empty")
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        cache_key = f"{self.embedder.model}\n{query}"
        with IndexDatabase(self.index_path) as database:
            query_vector = database.get_cached_query(cache_key)
            if query_vector is None:
                query_vector = self.embedder.embed_queries([query])[0]
                database.cache_query(cache_key, query_vector)
            pool = max(limit * 5, 50)
            lexical = [
                item[0]
                for item in database.fts_candidates(
                    query,
                    pool,
                    mode=mode,
                    subsystem=subsystem,
                    api_group=api_group,
                )
            ]
            allowed_ids = (
                None
                if mode == "all" and not subsystem and not api_group
                else set(
                    database.section_ids(
                        mode=mode, subsystem=subsystem, api_group=api_group
                    )
                )
            )
            dense = self._dense_candidates(
                query_vector, pool, allowed_ids=allowed_ids
            )
            ranked = _reciprocal_rank_fusion((dense, lexical))[:limit]
            sections = database.get_sections([section_id for section_id, _ in ranked])

        results: list[dict[str, object]] = []
        for section_id, score in ranked:
            section = sections.get(section_id)
            if section is None:
                continue
            text = str(section["text"])
            section["excerpt"] = text[:1_500] + ("…" if len(text) > 1_500 else "")
            section.pop("text", None)
            section["score"] = round(score, 8)
            results.append(section)
        return results

    def _dense_candidates(
        self,
        query_vector: np.ndarray,
        limit: int,
        *,
        allowed_ids: set[str] | None = None,
    ) -> list[str]:
        if allowed_ids is None:
            candidate_ids = self._ids
            candidate_vectors = self._vectors
        else:
            indexes = [
                index
                for index, section_id in enumerate(self._ids)
                if section_id in allowed_ids
            ]
            candidate_ids = [self._ids[index] for index in indexes]
            candidate_vectors = self._vectors[indexes]
        if candidate_vectors.size == 0:
            return []
        if candidate_vectors.shape[1] != query_vector.size:
            raise ValueError("Query embedding dimension differs from index dimension")
        scores = candidate_vectors @ query_vector
        order = np.argsort(-scores)[:limit]
        return [candidate_ids[int(index)] for index in order]


def _reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], *, constant: int = 60
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, section_id in enumerate(ranking, start=1):
            scores[section_id] = scores.get(section_id, 0.0) + 1.0 / (constant + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
