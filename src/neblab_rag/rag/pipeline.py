"""End-to-end RAG pipeline: query → (rewrite) → retrieve → generate → validate.

Stateless coordinator. The retriever and generator are injected so the
API layer can build them once at startup (their underlying providers
hold HTTP/qdrant clients that should be reused).

Optional ``query_rewriter`` was added in Sprint 4 after the baseline showed
Chinese questions retrieved unrelated docs from the English corpus. When
present, the rewritten query goes to the retriever (better corpus match)
while the original query goes to the generator (so the answer comes back
in the user's language). When absent, behavior is identical to Sprint 0.
"""

from pydantic import BaseModel

from neblab_rag.rag.citation import CitationValidation, validate_citations
from neblab_rag.rag.generator import AnswerGenerator, GeneratedAnswer
from neblab_rag.rag.query_rewriter import QueryRewriter, RewrittenQuery
from neblab_rag.rag.retriever import HybridRetriever, RetrievedChunk


class RAGResult(BaseModel):
    query: str
    chunks: list[RetrievedChunk]
    answer: GeneratedAnswer
    citation_validation: CitationValidation
    # Optional — only set when QueryRewriter actually changed the query
    rewritten_query: str | None = None


class RAGPipeline:
    def __init__(
        self,
        retriever: HybridRetriever,
        generator: AnswerGenerator,
        *,
        query_rewriter: QueryRewriter | None = None,
    ):
        self._retriever = retriever
        self._generator = generator
        self._rewriter = query_rewriter

    @property
    def retriever(self) -> HybridRetriever:
        return self._retriever

    @property
    def generator(self) -> AnswerGenerator:
        return self._generator

    async def answer(self, *, query: str, top_k: int = 5) -> RAGResult:
        rewritten = await self._maybe_rewrite(query)
        chunks = await self._retriever.retrieve(query=rewritten.rewritten, top_k=top_k)
        answer = await self._generator.generate(query=rewritten.original, chunks=chunks)
        validation = validate_citations(answer.content, num_chunks=len(chunks))
        return RAGResult(
            query=query,
            rewritten_query=rewritten.rewritten if rewritten.was_rewritten else None,
            chunks=chunks,
            answer=answer,
            citation_validation=validation,
        )

    async def _maybe_rewrite(self, query: str) -> RewrittenQuery:
        if self._rewriter is None:
            return RewrittenQuery(original=query, rewritten=query, was_rewritten=False)
        return await self._rewriter.rewrite(query)
