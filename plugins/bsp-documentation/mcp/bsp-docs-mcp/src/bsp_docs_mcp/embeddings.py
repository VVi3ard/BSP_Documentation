"""Embedding provider abstraction and OpenRouter implementation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import httpx
import numpy as np
import numpy.typing as npt


QUERY_INSTRUCTION = (
    "Given a Russian-language query about the 1C Standard Subsystems Library, "
    "retrieve documentation sections describing the recommended API, "
    "implementation method, restrictions, and relevant code examples."
)


class EmbeddingError(RuntimeError):
    """Raised when an embedding provider returns an unusable response."""


class Embedder(Protocol):
    model: str

    def embed_documents(self, texts: Sequence[str]) -> npt.NDArray[np.float32]: ...

    def embed_queries(self, texts: Sequence[str]) -> npt.NDArray[np.float32]: ...


class OpenRouterEmbedder:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "qwen/qwen3-embedding-8b",
        base_url: str = "https://openrouter.ai/api/v1",
        batch_size: int = 32,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required")
        self.model = model
        self.batch_size = batch_size
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=120)
        self._url = f"{base_url.rstrip('/')}/embeddings"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": "BSP Documentation MCP",
        }

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def embed_documents(self, texts: Sequence[str]) -> npt.NDArray[np.float32]:
        return self._embed(list(texts))

    def embed_queries(self, texts: Sequence[str]) -> npt.NDArray[np.float32]:
        prepared = [f"Instruct: {QUERY_INSTRUCTION}\nQuery: {text}" for text in texts]
        return self._embed(prepared)

    def _embed(self, texts: list[str]) -> npt.NDArray[np.float32]:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        batches: list[npt.NDArray[np.float32]] = []
        for start in range(0, len(texts), self.batch_size):
            response: httpx.Response | None = None
            try:
                response = self._client.post(
                    self._url,
                    headers=self._headers,
                    json={
                        "model": self.model,
                        "input": texts[start : start + self.batch_size],
                        "encoding_format": "float",
                    },
                )
                response.raise_for_status()
                data = response.json()["data"]
                ordered = sorted(data, key=lambda item: item["index"])
                vectors = np.asarray(
                    [item["embedding"] for item in ordered], dtype=np.float32
                )
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                details = response.text[:500] if response is not None else str(error)
                raise EmbeddingError(
                    f"OpenRouter embedding request failed: {details}"
                ) from error
            if vectors.ndim != 2 or len(vectors) != len(
                texts[start : start + self.batch_size]
            ):
                raise EmbeddingError("OpenRouter returned an unexpected vector count")
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            if np.any(norms == 0):
                raise EmbeddingError("OpenRouter returned a zero embedding")
            batches.append(vectors / norms)
        return np.concatenate(batches).astype(np.float32, copy=False)
