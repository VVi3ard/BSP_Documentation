import httpx
import numpy as np

from bsp_docs_mcp.embeddings import OpenRouterEmbedder


def test_openrouter_embedder_sends_model_and_instruction() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        requests.append(payload)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 2.0]},
                    {"index": 0, "embedding": [3.0, 0.0]},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    embedder = OpenRouterEmbedder("secret", client=client)
    vectors = embedder.embed_queries(["первый", "второй"])

    assert requests[0]["model"] == "qwen/qwen3-embedding-8b"
    assert requests[0]["input"][0].endswith("Query: первый")
    np.testing.assert_allclose(vectors, np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))


def test_document_embedding_has_no_query_instruction() -> None:
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        captured.extend(payload["input"])
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})

    embedder = OpenRouterEmbedder(
        "secret", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    embedder.embed_documents(["Раздел документации"])
    assert captured == ["Раздел документации"]

