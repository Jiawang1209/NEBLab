# pyright: reportArgumentType=false
"""Qdrant access layer.

Wraps qdrant-client with our DTOs (VectorPoint, SearchHit) so the rest of
the codebase doesn't import qdrant types directly. Collection lifecycle
(``ensure_collection``) is idempotent so callers can run it on every boot.

Point IDs: Qdrant accepts either an unsigned integer or a UUID string.
We use the document's Postgres primary key (sequential int) directly —
``int`` here is the contract, not ``str``. Sending a stringified int like
``"3"`` is rejected at runtime ("3 is not a valid point ID"); the strict
type prevents that class of bug.
"""

from typing import Any

from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


class VectorPoint(BaseModel):
    id: int
    vector: list[float]
    payload: dict[str, Any]


class SearchHit(BaseModel):
    # Qdrant returns whatever was upserted: int for our docs, but we keep
    # the union so a future caller upserting UUIDs (e.g. multi-chunk in
    # Plan 2) doesn't have to widen this contract again.
    id: int | str
    score: float
    payload: dict[str, Any]


# Sprint 1: full-text indexing produces 100s-1000s of chunks per doc;
# a single upsert of 4096-d × N vectors will time out against Qdrant Cloud.
# Empirically 100 × 4096-d still hangs at the default qdrant-client timeout;
# 50 fits comfortably even with 60s timeout. Tune via constructor arg if
# Qdrant Cloud tier changes the throughput envelope.
DEFAULT_UPSERT_BATCH_SIZE = 50


class QdrantRepo:
    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        dim: int,
        *,
        upsert_batch_size: int = DEFAULT_UPSERT_BATCH_SIZE,
    ):
        self._client = client
        self._collection = collection
        self._dim = dim
        self._upsert_batch_size = upsert_batch_size

    def ensure_collection(self) -> None:
        if not self._client.collection_exists(self._collection):
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
            )

    def upsert_points(self, points: list[VectorPoint]) -> None:
        for i in range(0, len(points), self._upsert_batch_size):
            batch = points[i : i + self._upsert_batch_size]
            self._client.upsert(
                collection_name=self._collection,
                points=[PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in batch],
            )

    def search(self, query_vector: list[float], top_k: int = 10) -> list[SearchHit]:
        response = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=top_k,
            with_payload=True,
        )
        return [SearchHit(id=h.id, score=h.score, payload=h.payload or {}) for h in response.points]
