"""Index abstracts into Qdrant.

For v1: 1 abstract = 1 chunk = 1 vector point. Plan 2 will add multi-chunk
indexing for full text. Status ``FULLTEXT_INDEXED`` after the abstract is
indexed is intentional — for v1 the abstract IS the indexed unit.

Embeds ``title + "\\n\\n" + abstract`` rather than just abstract: title
adds semantic anchor terms (especially useful for short abstracts). Falls
back to title-only if abstract is missing (e.g. some IPCC reports in
OpenAlex).
"""

from sqlalchemy.orm import Session

from neblab_rag.db.models import IndexStatus
from neblab_rag.db.repositories import DocumentRepository
from neblab_rag.logging_config import get_logger
from neblab_rag.providers.embedding.base import EmbeddingProvider
from neblab_rag.vector import QdrantRepo, VectorPoint

log = get_logger(__name__)


class AbstractIndexer:
    def __init__(
        self,
        session: Session,
        embedder: EmbeddingProvider,
        qdrant: QdrantRepo,
    ):
        self._session = session
        self._repo = DocumentRepository(session)
        self._embedder = embedder
        self._qdrant = qdrant

    async def index_pending(self, *, batch_size: int = 32) -> int:
        self._qdrant.ensure_collection()
        pending = list(self._repo.list_documents_with_status(IndexStatus.METADATA_ONLY))

        total = 0
        for i in range(0, len(pending), batch_size):
            batch = pending[i : i + batch_size]
            texts = [f"{d.title}\n\n{d.abstract.text}" if d.abstract else d.title for d in batch]
            vectors = await self._embedder.embed(texts)

            points = [
                VectorPoint(
                    id=d.id,
                    vector=v,
                    payload={
                        "doc_id": d.id,
                        "openalex_id": d.openalex_id,
                        "title": d.title,
                        # Store the abstract in payload so retriever can hand it to
                        # the generator without a Postgres roundtrip. Sprint-0 corpus
                        # is small (~5k docs × ~1KB) — payload size is fine.
                        "abstract": d.abstract.text if d.abstract else "",
                        "year": d.year,
                        "topic": d.primary_topic,
                        "language": d.language,
                    },
                )
                for d, v in zip(batch, vectors, strict=True)
            ]
            self._qdrant.upsert_points(points)

            for d in batch:
                d.status = IndexStatus.FULLTEXT_INDEXED
                if d.abstract:
                    d.abstract.qdrant_point_id = str(d.id)

            total += len(batch)
            self._session.flush()
            log.info("index_progress", processed=total, total=len(pending))

        return total
