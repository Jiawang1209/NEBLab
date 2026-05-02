"""Shared pytest fixtures.

This file is loaded automatically before any test module is imported.
The session-scoped fixture below sets dummy env vars so ``Settings()``
construction never fails during unit tests, regardless of what is in
the developer's ``.env.local``.
"""

import os

import pytest

_DUMMY_ENV: dict[str, str] = {
    "LLM_BASE_URL": "https://test.invalid/v1",
    "LLM_API_KEY": "test",
    "LLM_DEFAULT_MODEL": "test-model",
    "EMBEDDING_BASE_URL": "https://test.invalid/v1",
    "EMBEDDING_API_KEY": "test",
    "EMBEDDING_MODEL": "test-emb",
    "EMBEDDING_DIM": "1024",
    "RERANKER_BASE_URL": "https://test.invalid/v1",
    "RERANKER_API_KEY": "test",
    "RERANKER_MODEL": "test-rr",
    "QDRANT_URL": "https://test.invalid:6333",
    "QDRANT_API_KEY": "test",
    "QDRANT_COLLECTION": "test_collection",
    "POSTGRES_DSN": "postgresql+psycopg2://test@localhost:5432/test",
    "OPENALEX_EMAIL": "test@example.com",
    "LOG_LEVEL": "DEBUG",
}


# Set defaults at import time (before any test module imports application
# code). Individual tests can still override via monkeypatch / patch.dict.
for _key, _value in _DUMMY_ENV.items():
    os.environ.setdefault(_key, _value)


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Clear get_settings() lru_cache between tests so config changes take effect."""
    from neblab_rag.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
