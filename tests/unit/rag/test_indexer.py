from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from neblab_rag.db.models import Base, Document, IndexStatus
from neblab_rag.db.repositories import DocumentRepository
from neblab_rag.rag.indexer import AbstractIndexer


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine)
    s = sm()
    yield s
    s.close()


@pytest.mark.asyncio
async def test_index_pending_calls_embed_and_upsert(session):
    repo = DocumentRepository(session)
    repo.upsert_metadata(
        openalex_id="W1",
        doi=None,
        title="t",
        authors=[],
        venue=None,
        year=2020,
        primary_topic="desertification",
        extra_topics=[],
        language="en",
        is_oa=True,
        cited_by_count=0,
        abstract_text="some abstract",
        abstract_language="en",
    )
    session.commit()

    fake_embed = MagicMock()
    fake_embed.dim = 4
    fake_embed.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]])
    fake_qdrant = MagicMock()

    indexer = AbstractIndexer(session=session, embedder=fake_embed, qdrant=fake_qdrant)
    n = await indexer.index_pending(batch_size=10)
    session.commit()

    assert n == 1
    fake_embed.embed.assert_awaited_once()
    fake_qdrant.upsert_points.assert_called_once()

    docs = session.query(Document).all()
    assert docs[0].status == IndexStatus.FULLTEXT_INDEXED
