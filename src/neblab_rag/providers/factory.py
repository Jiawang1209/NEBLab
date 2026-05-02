"""Provider factory wired to Settings.

This is the **only** place that imports concrete provider classes; the rest
of the codebase depends on the abstract interfaces (LLMProvider /
EmbeddingProvider / RerankerProvider). Swapping a vendor = changing one line
here, no other module is touched.
"""

from qdrant_client import QdrantClient

from neblab_rag.config import Settings, get_settings
from neblab_rag.providers.embedding import EmbeddingProvider, Qwen3EmbeddingProvider
from neblab_rag.providers.llm import LLMProvider
from neblab_rag.providers.llm.deepseek import DeepSeekProvider
from neblab_rag.providers.reranker import Qwen3RerankerProvider, RerankerProvider
from neblab_rag.vector import QdrantRepo


def build_llm_provider(settings: Settings | None = None) -> LLMProvider:
    s = (settings or get_settings()).llm
    return DeepSeekProvider(
        base_url=s.base_url,
        api_key=s.api_key,
        default_model=s.default_model,
    )


def build_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    s = (settings or get_settings()).embedding
    return Qwen3EmbeddingProvider(
        base_url=s.base_url,
        api_key=s.api_key,
        model=s.model,
        dim=s.dim,
    )


def build_reranker_provider(settings: Settings | None = None) -> RerankerProvider:
    s = (settings or get_settings()).reranker
    return Qwen3RerankerProvider(
        base_url=s.base_url,
        api_key=s.api_key,
        model=s.model,
    )


def build_qdrant_repo(settings: Settings | None = None) -> QdrantRepo:
    s = settings or get_settings()
    client = QdrantClient(
        url=s.qdrant.url,
        api_key=s.qdrant.api_key or None,
    )
    return QdrantRepo(client=client, collection=s.qdrant.collection, dim=s.embedding.dim)
