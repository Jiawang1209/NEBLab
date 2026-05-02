"""End-to-end RAG pipeline: query → retrieve → generate → validate.

Stateless coordinator. The retriever and generator are injected so the
API layer can build them once at startup (their underlying providers
hold HTTP/qdrant clients that should be reused).
"""

from pydantic import BaseModel

from neblab_rag.rag.citation import CitationValidation, validate_citations
from neblab_rag.rag.generator import AnswerGenerator, GeneratedAnswer
from neblab_rag.rag.retriever import HybridRetriever, RetrievedChunk


class RAGResult(BaseModel):
    query: str
    chunks: list[RetrievedChunk]
    answer: GeneratedAnswer
    citation_validation: CitationValidation


class RAGPipeline:
    def __init__(self, retriever: HybridRetriever, generator: AnswerGenerator):
        self._retriever = retriever
        self._generator = generator

    @property
    def retriever(self) -> HybridRetriever:
        return self._retriever

    @property
    def generator(self) -> AnswerGenerator:
        return self._generator

    async def answer(self, *, query: str, top_k: int = 5) -> RAGResult:
        chunks = await self._retriever.retrieve(query=query, top_k=top_k)
        answer = await self._generator.generate(query=query, chunks=chunks)
        validation = validate_citations(answer.content, num_chunks=len(chunks))
        return RAGResult(
            query=query,
            chunks=chunks,
            answer=answer,
            citation_validation=validation,
        )
