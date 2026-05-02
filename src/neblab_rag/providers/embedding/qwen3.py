"""Qwen3 embedding provider via OpenAI-compatible /embeddings endpoint.

Provider-agnostic at the wire level; named ``Qwen3EmbeddingProvider`` because
qwen3-embedding:8b is the v1 default. Batches inputs internally so callers
can pass arbitrary list sizes.
"""

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from neblab_rag.providers.embedding.base import EmbeddingProvider


class Qwen3EmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dim: int,
        timeout: float = 60.0,
        batch_size: int = 32,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._dim = dim
        self._timeout = timeout
        self._batch_size = batch_size

    @property
    def dim(self) -> int:
        return self._dim

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url=f"{self._base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "input": batch},
            )
            resp.raise_for_status()
            data = resp.json()
        # Sort by index to maintain input order (server may return out-of-order).
        return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            out.extend(await self._embed_batch(batch))
        return out
