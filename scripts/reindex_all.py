"""Reindex every METADATA_ONLY doc in Postgres into Qdrant."""

import asyncio

from neblab_rag.db.engine import get_session
from neblab_rag.providers.factory import build_embedding_provider, build_qdrant_repo
from neblab_rag.rag.indexer import ChunkIndexer


async def main() -> None:
    embedder = build_embedding_provider()
    qdrant = build_qdrant_repo()
    with get_session() as session:
        indexer = ChunkIndexer(session=session, embedder=embedder, qdrant=qdrant)
        n = await indexer.index_pending()
    print(f"indexed_docs={n}")


if __name__ == "__main__":
    asyncio.run(main())
