"""Qdrant access layer.

Wraps qdrant-client with our DTOs (VectorPoint, SearchHit) so the rest of
the codebase doesn't import qdrant types directly. Collection lifecycle
(``ensure_collection``) is idempotent so callers can run it on every boot.
"""

from typing import Any

from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


class VectorPoint(BaseModel):
    id: str
    vector: list[float]
    payload: dict[str, Any]


class SearchHit(BaseModel):
    id: str
    score: float
    payload: dict[str, Any]


class QdrantRepo:
    def __init__(self, client: QdrantClient, collection: str, dim: int):
        self._client = client
        self._collection = collection
        self._dim = dim

    def ensure_collection(self) -> None:
        if not self._client.collection_exists(self._collection):
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
            )

    def upsert_points(self, points: list[VectorPoint]) -> None:
        self._client.upsert(
            collection_name=self._collection,
            points=[PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in points],
        )

    def search(self, query_vector: list[float], top_k: int = 10) -> list[SearchHit]:
        response = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=top_k,
            with_payload=True,
        )
        return [
            SearchHit(id=str(h.id), score=h.score, payload=h.payload or {}) for h in response.points
        ]
