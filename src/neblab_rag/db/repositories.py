"""Repository pattern for Document / Abstract / Chunk.

Repositories own the SQL queries; service code (corpus.ingestion, RAG
indexer) talks to repositories instead of constructing Selects inline.
This keeps the query surface area small and testable in isolation.
"""

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from neblab_rag.db.models import AbstractRecord, Chunk, Document, IndexStatus
from neblab_rag.rag.chunker import Chunk as ChunkText


class DocumentRepository:
    def __init__(self, session: Session):
        self._session = session

    def upsert_metadata(
        self,
        *,
        openalex_id: str | None,
        doi: str | None,
        title: str,
        authors: list[str],
        venue: str | None,
        year: int | None,
        primary_topic: str,
        extra_topics: list[str],
        language: str | None,
        is_oa: bool,
        cited_by_count: int,
        abstract_text: str | None,
        abstract_language: str | None,
    ) -> Document:
        """Insert or update a Document by openalex_id (preferred) or doi.

        If ``abstract_text`` is provided, also creates/updates the related
        AbstractRecord. Caller is responsible for ``session.commit()``.
        """
        existing: Document | None = None
        if openalex_id:
            stmt = select(Document).where(Document.openalex_id == openalex_id)
            existing = self._session.execute(stmt).scalar_one_or_none()
        if existing is None and doi:
            stmt = select(Document).where(Document.doi == doi)
            existing = self._session.execute(stmt).scalar_one_or_none()

        if existing is None:
            doc = Document(
                openalex_id=openalex_id,
                doi=doi,
                title=title,
                authors=authors,
                venue=venue,
                year=year,
                primary_topic=primary_topic,
                extra_topics=extra_topics,
                language=language,
                is_oa=is_oa,
                cited_by_count=cited_by_count,
            )
            self._session.add(doc)
            self._session.flush()  # populate doc.id for the abstract FK below
        else:
            existing.title = title
            existing.authors = authors
            existing.venue = venue
            existing.year = year
            existing.primary_topic = primary_topic
            existing.extra_topics = extra_topics
            existing.language = language
            existing.is_oa = is_oa
            existing.cited_by_count = cited_by_count
            doc = existing

        if abstract_text:
            if doc.abstract is None:
                doc.abstract = AbstractRecord(
                    document_id=doc.id,
                    text=abstract_text,
                    language=abstract_language or "und",
                )
            else:
                doc.abstract.text = abstract_text
                doc.abstract.language = abstract_language or doc.abstract.language

        return doc

    def list_documents_with_status(
        self, status: IndexStatus, *, limit: int | None = None
    ) -> Sequence[Document]:
        stmt = select(Document).where(Document.status == status)
        if limit:
            stmt = stmt.limit(limit)
        return self._session.execute(stmt).scalars().all()


class ChunkRepository:
    """Persists Chunk rows. Replace-on-write keeps re-indexing idempotent."""

    def __init__(self, session: Session):
        self._session = session

    def replace_for_document(self, document_id: int, chunks: list[ChunkText]) -> list[Chunk]:
        """Delete all existing chunks for ``document_id`` and insert ``chunks``.

        Used when re-indexing a document: chunk count or boundaries may have
        changed, so we drop the old set rather than try to merge. Caller is
        responsible for ``session.commit()``.
        """
        self._session.execute(delete(Chunk).where(Chunk.document_id == document_id))
        rows = [
            Chunk(
                document_id=document_id,
                chunk_index=i,
                text=c.text,
                start_offset=c.start,
                end_offset=c.end,
            )
            for i, c in enumerate(chunks)
        ]
        self._session.add_all(rows)
        self._session.flush()  # populate row.id (used as Qdrant point id)
        return rows
