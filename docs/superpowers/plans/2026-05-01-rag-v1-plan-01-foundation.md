# Plan 1: 基建 + 摘要级 RAG

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 NEBLab RAG 项目基础设施，跑通**摘要级 RAG**（基于 OpenAlex 5000 条元数据 + 摘要），W1 末可演示"问→答→引用"完整闭环。

**Architecture:** Python (uv) + FastAPI 后端 + Provider Abstraction（LLM/Embedding/Reranker）+ PostgreSQL（元数据/全文）+ Qdrant Cloud（向量）+ OpenAI-compatible 远程 LLM/Embedding 端点。全云 API、零本地 GPU。Provider 抽象层让所有外部 AI 服务可热切换。

**Tech Stack:** uv, Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, Qdrant Cloud, pyalex（OpenAlex SDK）, pytest, ruff, pyright, structlog, docker-compose.

**Spec reference:** `docs/superpowers/specs/2026-05-01-rag-v1-design.md`

**Sprint:** Sprint 0 of v1（对应 W1）

---

## 前置假设（开始前必须满足）

- [ ] **miniforge 已安装**（提供 `mamba` 命令）：https://github.com/conda-forge/miniforge
- [ ] Docker + docker-compose 已安装（本地 Postgres）
- [ ] 你有以下访问权限：
  - DeepSeek API（OpenAI 兼容端点 + API key）
  - 内部 Qwen3 embedding/reranker 端点（OpenAI 兼容）
  - Qdrant Cloud（免费层即可）
- [ ] 已在 `.env.local` 中保存以上 endpoint URL + API key（**不要 commit**）

## 工具链约定

- **环境隔离**：miniforge / mamba（env 名 `NEBLab`）
- **依赖管理**：pyproject.toml（声明）+ uv（快速安装）
- **运行命令**：env 激活后**不需要** `uv run` 前缀，直接 `pytest` / `uvicorn` 等
- **添加新依赖**：编辑 `pyproject.toml` → 跑 `uv pip install -e ".[dev]"`

---

## 文件结构（本 Plan 末态）

```text
NEBLab/
├── pyproject.toml                       # uv 项目配置
├── uv.lock
├── .python-version
├── .env.example                         # 配置模板（commit）
├── .gitignore
├── docker-compose.yml                   # 本地 Postgres + Qdrant
├── Makefile                             # 常用命令
├── README.md
├── src/neblab_rag/
│   ├── __init__.py
│   ├── config.py                        # pydantic-settings
│   ├── logging_config.py                # structlog
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── llm/{__init__.py,base.py,deepseek.py}
│   │   ├── embedding/{__init__.py,base.py,qwen3.py}
│   │   └── reranker/{__init__.py,base.py,qwen3.py}
│   ├── db/
│   │   ├── __init__.py
│   │   ├── engine.py                    # SQLAlchemy engine + session
│   │   ├── models.py                    # Document, Abstract
│   │   └── repositories.py              # DocumentRepository
│   ├── corpus/
│   │   ├── __init__.py
│   │   ├── topics.py                    # 7 主题关键词
│   │   ├── openalex_client.py           # pyalex 包装
│   │   ├── ingestion.py                 # 元数据入库 service
│   │   └── cli.py                       # `neblab-ingest` 入口
│   ├── vector/
│   │   ├── __init__.py
│   │   └── qdrant_repo.py
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── indexer.py                   # 摘要 → 向量入库
│   │   ├── retriever.py                 # 检索
│   │   ├── generator.py                 # LLM 生成 + 引用标注
│   │   └── pipeline.py                  # 端到端组合
│   └── api/
│       ├── __init__.py
│       ├── main.py                      # FastAPI app
│       └── routes/
│           ├── __init__.py
│           ├── health.py
│           └── query.py                 # POST /query SSE
├── alembic.ini
├── alembic/{env.py, script.py.mako, versions/}
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── providers/
│   │   ├── corpus/
│   │   ├── db/
│   │   ├── rag/
│   │   └── vector/
│   └── integration/
│       ├── test_ingestion_e2e.py
│       └── test_query_e2e.py
└── .github/workflows/ci.yml
```

---

## Phase 0：仓库骨架（Tasks 1-5）

### Task 1: 写 `pyproject.toml` + 项目骨架

**Files:**
- Create: `pyproject.toml`, `.python-version`, `src/neblab_rag/__init__.py`, `tests/__init__.py`, `.gitignore`

- [ ] **Step 1: 写 `pyproject.toml`（声明所有依赖）**

```toml
[project]
name = "neblab-rag"
version = "0.1.0"
description = "RAG knowledge base for Northern Ecological Barrier Lab"
requires-python = ">=3.12,<3.13"
readme = "README.md"

dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
  "sqlalchemy>=2.0",
  "alembic>=1.14",
  "asyncpg>=0.30",
  "psycopg2-binary>=2.9",
  "httpx>=0.27",
  "qdrant-client>=1.12",
  "pyalex>=0.15",
  "structlog>=24.4",
  "python-dotenv>=1.0",
  "sse-starlette>=2.1",
  "tenacity>=9.0",
  "click>=8.1",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "pytest-cov>=6.0",
  "pytest-mock>=3.14",
  "ruff>=0.7",
  "pyright>=1.1.380",
  "pre-commit>=4.0",
  "ipython>=8.28",
]

[project.scripts]
neblab-ingest = "neblab_rag.corpus.cli:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/neblab_rag"]
```

- [ ] **Step 2: 写 `.python-version`**

```bash
echo "3.12" > .python-version
```

- [ ] **Step 3: 创建包骨架**

```bash
mkdir -p src/neblab_rag tests
touch src/neblab_rag/__init__.py tests/__init__.py
```

- [ ] **Step 4: 写 `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
venv/
.pytest_cache/
.coverage
.coverage.*
htmlcov/
.mypy_cache/
.ruff_cache/
.pyright/
*.egg-info/
build/
dist/

# uv
uv.lock

# Env
.env
.env.local
.env.*.local

# IDE
.vscode/
.idea/
*.swp
.DS_Store

# Project artifacts
data/
logs/
*.log
.claude/settings.local.json
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .python-version src/ tests/ .gitignore
git commit -m "chore: add pyproject.toml and project skeleton"
```

---

### Task 2: 创建 `NEBLab` mamba 环境

**Files:**
- Create: `environment.yml`

- [ ] **Step 1: 写 `environment.yml`**

```yaml
# environment.yml — bootstrap the NEBLab environment.
#
# Usage:
#   mamba env create -f environment.yml
#   mamba activate NEBLab
#
# To re-sync after pyproject.toml changes:
#   uv pip install -e ".[dev]"
name: NEBLab
channels:
  - conda-forge
dependencies:
  - python=3.12
  - pip
  - uv
  - pip:
      - -e .[dev]
```

- [ ] **Step 2: 创建环境**

```bash
mamba env create -f environment.yml
```

预期：mamba 安装 Python 3.12 + uv + 通过 `pip install -e .[dev]` 装上所有 pyproject.toml 中的依赖。

- [ ] **Step 3: 激活并验证**

```bash
mamba activate NEBLab
python --version
# Expected: Python 3.12.x

uv --version
# Expected: uv 0.x.x

python -c "import fastapi, sqlalchemy, qdrant_client, pyalex; print('OK')"
# Expected: OK
```

- [ ] **Step 4: Commit**

```bash
git add environment.yml
git commit -m "chore: add environment.yml for NEBLab mamba env"
```

> 之后所有命令默认在 `mamba activate NEBLab` 状态下执行。每次开新终端都要先 activate。

---

### Task 3: 配置 ruff + pyright

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 在 `pyproject.toml` 末尾追加配置**

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM", "RUF"]
ignore = ["E501"]  # line length handled by formatter

[tool.ruff.format]
quote-style = "double"

[tool.pyright]
include = ["src", "tests"]
pythonVersion = "3.12"
typeCheckingMode = "strict"
reportMissingTypeStubs = false

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-v --tb=short"
```

- [ ] **Step 2: 跑一次格式化看是否生效**

```bash
ruff check src/ tests/ || true
ruff format src/ tests/
pyright src/ || true   # 第一次跑允许有错
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: configure ruff + pyright"
```

---

### Task 4: 写 `.env.example`

**Files:**
- Create: `.env.example`

- [ ] **Step 1: 写 `.env.example`**

```bash
# === LLM (DeepSeek, OpenAI-compatible) ===
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxx
LLM_DEFAULT_MODEL=deepseek-v3.2
LLM_REASONING_MODEL=deepseek-r1:671b-64k
LLM_LIGHT_MODEL=deepseek-v4-flash

# === Embedding (Qwen3, OpenAI-compatible internal endpoint) ===
EMBEDDING_BASE_URL=http://your-internal-host/v1
EMBEDDING_API_KEY=sk-internal
EMBEDDING_MODEL=qwen3-embedding:8b
EMBEDDING_DIM=4096

# === Reranker (Qwen3) ===
RERANKER_BASE_URL=http://your-internal-host/v1
RERANKER_API_KEY=sk-internal
RERANKER_MODEL=qwen3-reranker:8b

# === Postgres ===
POSTGRES_DSN=postgresql+psycopg2://neblab:neblab@localhost:5432/neblab

# === Qdrant ===
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=neblab_abstracts

# === OpenAlex ===
OPENALEX_EMAIL=your-email@university.edu

# === Logging ===
LOG_LEVEL=INFO
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "chore: add env template"
```

---

### Task 5: 添加 GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

> 注意：CI 不用 mamba，直接用 uv（更快）。pyproject.toml 是单一事实源，所以两边都能装。

- [ ] **Step 1: 写 CI 配置**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Set Python version
        run: uv python install 3.12

      - name: Install project (with dev deps)
        run: uv pip install --system -e ".[dev]"

      - name: Lint
        run: ruff check src tests

      - name: Format check
        run: ruff format --check src tests

      - name: Type check
        run: pyright src

      - name: Test
        run: pytest -m "not integration" --cov=src/neblab_rag --cov-report=term-missing
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "chore: add GitHub Actions CI"
```

---

### Task 3: 配置 ruff + pyright

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 在 `pyproject.toml` 末尾追加配置**

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM", "RUF"]
ignore = ["E501"]  # line length handled by formatter

[tool.ruff.format]
quote-style = "double"

[tool.pyright]
include = ["src", "tests"]
pythonVersion = "3.12"
typeCheckingMode = "strict"
reportMissingTypeStubs = false

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-v --tb=short"
```

- [ ] **Step 2: 跑一次格式化看是否生效**

```bash
ruff check src/ tests/ || true
ruff format src/ tests/
pyright src/ || true   # 第一次跑允许有错
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: configure ruff + pyright"
```

---

### Task 4: 编写 .gitignore + .env.example

**Files:**
- Create: `.gitignore`, `.env.example`

- [ ] **Step 1: 写 `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
venv/
.pytest_cache/
.coverage
.coverage.*
htmlcov/
.mypy_cache/
.ruff_cache/
.pyright/
*.egg-info/
build/
dist/

# Env
.env
.env.local
.env.*.local

# IDE
.vscode/
.idea/
*.swp
.DS_Store

# Project artifacts
data/
logs/
*.log
.claude/settings.local.json
```

- [ ] **Step 2: 写 `.env.example`**

```bash
# === LLM (DeepSeek, OpenAI-compatible) ===
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxx
LLM_DEFAULT_MODEL=deepseek-v3.2
LLM_REASONING_MODEL=deepseek-r1:671b-64k
LLM_LIGHT_MODEL=deepseek-v4-flash

# === Embedding (Qwen3, OpenAI-compatible internal endpoint) ===
EMBEDDING_BASE_URL=http://your-internal-host/v1
EMBEDDING_API_KEY=sk-internal
EMBEDDING_MODEL=qwen3-embedding:8b
EMBEDDING_DIM=4096

# === Reranker (Qwen3) ===
RERANKER_BASE_URL=http://your-internal-host/v1
RERANKER_API_KEY=sk-internal
RERANKER_MODEL=qwen3-reranker:8b

# === Postgres ===
POSTGRES_DSN=postgresql+psycopg2://neblab:neblab@localhost:5432/neblab

# === Qdrant ===
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=neblab_abstracts

# === OpenAlex ===
OPENALEX_EMAIL=your-email@university.edu

# === Logging ===
LOG_LEVEL=INFO
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore .env.example
git commit -m "chore: add gitignore and env template"
```

---

### Task 5: 添加 GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: 写 CI 配置**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Set Python version
        run: uv python install 3.12

      - name: Install dependencies
        run: uv pip install -e ".[dev]" --all-extras

      - name: Lint
        run: ruff check src tests

      - name: Format check
        run: ruff format --check src tests

      - name: Type check
        run: pyright src

      - name: Test
        run: pytest --cov=src/neblab_rag --cov-report=term-missing
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "chore: add GitHub Actions CI"
```

---

## Phase 1：配置 + 日志 + FastAPI 骨架（Tasks 6-9）

### Task 6: Settings 模块（pydantic-settings）

**Files:**
- Create: `src/neblab_rag/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_config.py
"""Test Settings configuration loading."""

import os
from unittest.mock import patch

from neblab_rag.config import Settings


def test_settings_loads_from_env_vars():
    env = {
        "LLM_BASE_URL": "https://example.com/v1",
        "LLM_API_KEY": "test-key",
        "LLM_DEFAULT_MODEL": "test-model",
        "EMBEDDING_BASE_URL": "https://example.com/v1",
        "EMBEDDING_API_KEY": "emb-key",
        "EMBEDDING_MODEL": "emb-model",
        "EMBEDDING_DIM": "1024",
        "RERANKER_BASE_URL": "https://example.com/v1",
        "RERANKER_API_KEY": "rr-key",
        "RERANKER_MODEL": "rr-model",
        "POSTGRES_DSN": "postgresql://x",
        "QDRANT_URL": "http://localhost:6333",
        "QDRANT_COLLECTION": "test",
        "OPENALEX_EMAIL": "a@b.com",
    }
    with patch.dict(os.environ, env, clear=True):
        s = Settings()
    assert s.llm.api_key == "test-key"
    assert s.embedding.dim == 1024
    assert s.qdrant.collection == "test"
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
pytest tests/unit/test_config.py -v
# Expected: ImportError / ModuleNotFoundError
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/config.py
"""Centralized configuration via pydantic-settings."""

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseModel):
    base_url: str
    api_key: str
    default_model: str
    reasoning_model: str = "deepseek-r1:671b-64k"
    light_model: str = "deepseek-v4-flash"


class EmbeddingSettings(BaseModel):
    base_url: str
    api_key: str
    model: str
    dim: int


class RerankerSettings(BaseModel):
    base_url: str
    api_key: str
    model: str


class QdrantSettings(BaseModel):
    url: str
    api_key: str = ""
    collection: str = "neblab_abstracts"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_nested_delimiter="__",
        env_prefix="",
        case_sensitive=False,
    )

    llm: LLMSettings = Field(default_factory=lambda: LLMSettings(
        base_url="", api_key="", default_model=""
    ))
    embedding: EmbeddingSettings = Field(default_factory=lambda: EmbeddingSettings(
        base_url="", api_key="", model="", dim=0
    ))
    reranker: RerankerSettings = Field(default_factory=lambda: RerankerSettings(
        base_url="", api_key="", model=""
    ))
    qdrant: QdrantSettings = Field(default_factory=lambda: QdrantSettings(url=""))

    postgres_dsn: str = ""
    openalex_email: str = ""
    log_level: str = "INFO"

    def __init__(self, **data):  # noqa: D401
        # Manually build nested settings from flat env keys (LLM_BASE_URL, etc.)
        import os
        flat = {**os.environ, **data}

        def _pick(prefix: str) -> dict[str, str]:
            return {
                k.removeprefix(prefix).lower(): v
                for k, v in flat.items()
                if k.startswith(prefix)
            }

        llm_kw = _pick("LLM_")
        emb_kw = _pick("EMBEDDING_")
        rr_kw = _pick("RERANKER_")
        qd_kw = _pick("QDRANT_")

        if llm_kw:
            data.setdefault("llm", LLMSettings(**llm_kw))
        if emb_kw:
            emb_kw["dim"] = int(emb_kw.get("dim", 0))
            data.setdefault("embedding", EmbeddingSettings(**emb_kw))
        if rr_kw:
            data.setdefault("reranker", RerankerSettings(**rr_kw))
        if qd_kw:
            data.setdefault("qdrant", QdrantSettings(**qd_kw))

        super().__init__(**data)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Singleton accessor."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
pytest tests/unit/test_config.py -v
# Expected: PASS
```

- [ ] **Step 5: Commit**

```bash
git add src/neblab_rag/config.py tests/unit/test_config.py
git commit -m "feat(config): add Settings module with nested LLM/Embedding/Reranker/Qdrant config"
```

---

### Task 7: 结构化日志（structlog）

**Files:**
- Create: `src/neblab_rag/logging_config.py`
- Test: `tests/unit/test_logging.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/test_logging.py
import logging

from neblab_rag.logging_config import configure_logging, get_logger


def test_get_logger_returns_bound_logger(caplog):
    configure_logging(level="DEBUG")
    log = get_logger("test")
    with caplog.at_level(logging.DEBUG):
        log.info("hello", key="value")
    assert "hello" in caplog.text
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
pytest tests/unit/test_logging.py -v
# Expected: ImportError
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/logging_config.py
"""Structured logging via structlog."""

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/unit/test_logging.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/neblab_rag/logging_config.py tests/unit/test_logging.py
git commit -m "feat(logging): add structlog configuration"
```

---

### Task 8: FastAPI app + /health 端点

**Files:**
- Create: `src/neblab_rag/api/main.py`, `src/neblab_rag/api/routes/__init__.py`, `src/neblab_rag/api/routes/health.py`
- Test: `tests/unit/api/test_health.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/api/test_health.py
from fastapi.testclient import TestClient

from neblab_rag.api.main import create_app


def test_health_endpoint_returns_ok():
    app = create_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/api/test_health.py -v
# Expected: ImportError
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/api/main.py
"""FastAPI application factory."""

from fastapi import FastAPI

from neblab_rag.api.routes import health
from neblab_rag.config import get_settings
from neblab_rag.logging_config import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level)

    app = FastAPI(
        title="NEBLab RAG API",
        version="0.1.0",
        description="北方生态屏障数字实验室 RAG 知识库",
    )
    app.include_router(health.router)
    return app


app = create_app()
```

```python
# src/neblab_rag/api/routes/__init__.py
```

```python
# src/neblab_rag/api/routes/health.py
"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/unit/api/test_health.py -v
```

- [ ] **Step 5: 启动 server 手动验证**

```bash
uvicorn neblab_rag.api.main:app --reload --port 8000 &
curl http://localhost:8000/health
# Expected: {"status":"ok"}
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add src/neblab_rag/api/ tests/unit/api/
git commit -m "feat(api): scaffold FastAPI app with /health endpoint"
```

---

### Task 9: docker-compose（Postgres + Qdrant 本地服务）

**Files:**
- Create: `docker-compose.yml`, `Makefile`

- [ ] **Step 1: 写 `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: neblab-postgres
    environment:
      POSTGRES_USER: neblab
      POSTGRES_PASSWORD: neblab
      POSTGRES_DB: neblab
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U neblab"]
      interval: 5s
      timeout: 5s
      retries: 5

  qdrant:
    image: qdrant/qdrant:latest
    container_name: neblab-qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  postgres_data:
  qdrant_data:
```

- [ ] **Step 2: 写 `Makefile`**

```makefile
.PHONY: up down logs ps test lint format typecheck migrate ingest dev

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

test:
	pytest

lint:
	ruff check src tests

format:
	ruff format src tests

typecheck:
	pyright src

migrate:
	alembic upgrade head

ingest:
	python -m neblab_rag.corpus.cli ingest

dev:
	uvicorn neblab_rag.api.main:app --reload --port 8000
```

- [ ] **Step 3: 启动并验证**

```bash
make up
sleep 5
docker ps | grep neblab    # 应看到 neblab-postgres 和 neblab-qdrant
curl http://localhost:6333  # Qdrant 应返回 JSON
make down
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml Makefile
git commit -m "chore: add docker-compose and Makefile for local dev"
```

---

## Phase 2：Provider 抽象（Tasks 10-15）

### Task 10: LLMProvider 接口 + 数据模型

**Files:**
- Create: `src/neblab_rag/providers/__init__.py`, `src/neblab_rag/providers/llm/__init__.py`, `src/neblab_rag/providers/llm/base.py`
- Test: `tests/unit/providers/llm/test_base.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/providers/llm/test_base.py
"""Test LLMProvider abstract interface contract."""

import pytest

from neblab_rag.providers.llm.base import (
    ChatMessage,
    ChatRequest,
    LLMProvider,
)


def test_chat_message_roles():
    m = ChatMessage(role="user", content="hi")
    assert m.role == "user"


def test_chat_request_default_temperature():
    req = ChatRequest(messages=[ChatMessage(role="user", content="hi")])
    assert req.temperature == 0.3


def test_llm_provider_is_abstract():
    with pytest.raises(TypeError):
        LLMProvider()  # type: ignore[abstract]
```

- [ ] **Step 2: 跑测试，确认失败**

```bash
pytest tests/unit/providers/llm/test_base.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/providers/__init__.py
```

```python
# src/neblab_rag/providers/llm/__init__.py
from neblab_rag.providers.llm.base import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    LLMProvider,
    StreamChunk,
)

__all__ = [
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "LLMProvider",
    "StreamChunk",
]
```

```python
# src/neblab_rag/providers/llm/base.py
"""LLMProvider abstract interface."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None  # None = use provider default
    temperature: float = 0.3
    max_tokens: int = 2048
    stop: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    content: str
    model: str
    finish_reason: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class StreamChunk(BaseModel):
    delta: str
    finish_reason: str | None = None


class LLMProvider(ABC):
    """Abstract LLM provider. Implementations wrap a specific vendor API."""

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse: ...

    @abstractmethod
    def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]: ...
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/unit/providers/llm/test_base.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/neblab_rag/providers/ tests/unit/providers/
git commit -m "feat(providers/llm): define LLMProvider abstract interface"
```

---

### Task 11: DeepSeekProvider 实现

**Files:**
- Create: `src/neblab_rag/providers/llm/deepseek.py`
- Test: `tests/unit/providers/llm/test_deepseek.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/providers/llm/test_deepseek.py
"""Test DeepSeekProvider with mocked HTTP."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neblab_rag.providers.llm.base import ChatMessage, ChatRequest
from neblab_rag.providers.llm.deepseek import DeepSeekProvider


@pytest.fixture
def provider() -> DeepSeekProvider:
    return DeepSeekProvider(
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        default_model="deepseek-v3.2",
    )


@pytest.mark.asyncio
async def test_chat_calls_correct_endpoint(provider: DeepSeekProvider):
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "id": "x",
        "model": "deepseek-v3.2",
        "choices": [{
            "message": {"role": "assistant", "content": "hi"},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3},
    }
    fake_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)) as mock_post:
        resp = await provider.chat(ChatRequest(
            messages=[ChatMessage(role="user", content="hi")]
        ))

    assert resp.content == "hi"
    assert resp.model == "deepseek-v3.2"
    assert resp.prompt_tokens == 5
    assert mock_post.call_args.kwargs["url"] == "https://api.example.com/v1/chat/completions"
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/providers/llm/test_deepseek.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/providers/llm/deepseek.py
"""DeepSeek LLM provider (OpenAI-compatible)."""

import json
from collections.abc import AsyncIterator

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from neblab_rag.providers.llm.base import (
    ChatRequest,
    ChatResponse,
    LLMProvider,
    StreamChunk,
)


class DeepSeekProvider(LLMProvider):
    """OpenAI-compatible client for DeepSeek API.

    Works with any OpenAI-compatible endpoint (DeepSeek, Qwen, Spark, etc.)
    by configuring base_url + default_model. We name it DeepSeek because
    that's our v1 default.
    """

    def __init__(self, base_url: str, api_key: str, default_model: str, timeout: float = 60.0):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, request: ChatRequest, *, stream: bool) -> dict:
        return {
            "model": request.model or self._default_model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stop": request.stop or None,
            "stream": stream,
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def chat(self, request: ChatRequest) -> ChatResponse:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url=f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(request, stream=False),
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})
        return ChatResponse(
            content=choice["message"]["content"],
            model=data["model"],
            finish_reason=choice.get("finish_reason", "stop"),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:  # type: ignore[override]
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                method="POST",
                url=f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(request, stream=True),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    payload = line.removeprefix("data: ")
                    if payload == "[DONE]":
                        break
                    obj = json.loads(payload)
                    choice = obj["choices"][0]
                    delta = choice.get("delta", {}).get("content", "")
                    yield StreamChunk(
                        delta=delta,
                        finish_reason=choice.get("finish_reason"),
                    )
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/unit/providers/llm/test_deepseek.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/neblab_rag/providers/llm/deepseek.py tests/unit/providers/llm/test_deepseek.py
git commit -m "feat(providers/llm): implement DeepSeekProvider with retry + streaming"
```

---

### Task 12: EmbeddingProvider 接口 + Qwen3 实现

**Files:**
- Create: `src/neblab_rag/providers/embedding/__init__.py`, `base.py`, `qwen3.py`
- Test: `tests/unit/providers/embedding/test_qwen3.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/providers/embedding/test_qwen3.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neblab_rag.providers.embedding.qwen3 import Qwen3EmbeddingProvider


@pytest.fixture
def provider():
    return Qwen3EmbeddingProvider(
        base_url="https://example.com/v1",
        api_key="key",
        model="qwen3-embedding:8b",
        dim=4096,
    )


@pytest.mark.asyncio
async def test_embed_returns_correct_shape(provider):
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "data": [
            {"embedding": [0.1] * 4096, "index": 0},
            {"embedding": [0.2] * 4096, "index": 1},
        ],
        "model": "qwen3-embedding:8b",
    }
    fake_response.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
        vectors = await provider.embed(["a", "b"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 4096


def test_dim_property(provider):
    assert provider.dim == 4096
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/providers/embedding/test_qwen3.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/providers/embedding/__init__.py
from neblab_rag.providers.embedding.base import EmbeddingProvider
from neblab_rag.providers.embedding.qwen3 import Qwen3EmbeddingProvider

__all__ = ["EmbeddingProvider", "Qwen3EmbeddingProvider"]
```

```python
# src/neblab_rag/providers/embedding/base.py
from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Abstract embedding provider."""

    @property
    @abstractmethod
    def dim(self) -> int: ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
```

```python
# src/neblab_rag/providers/embedding/qwen3.py
"""Qwen3 embedding provider via OpenAI-compatible /embeddings endpoint."""

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from neblab_rag.providers.embedding.base import EmbeddingProvider


class Qwen3EmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dim: int,
        timeout: float = 60.0,
        batch_size: int = 32,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._dim = dim
        self._timeout = timeout
        self._batch_size = batch_size

    @property
    def dim(self) -> int:
        return self._dim

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url=f"{self._base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "input": batch},
            )
            resp.raise_for_status()
            data = resp.json()
        # Sort by index to maintain input order
        return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            out.extend(await self._embed_batch(batch))
        return out
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/unit/providers/embedding/ -v
```

- [ ] **Step 5: Commit**

```bash
git add src/neblab_rag/providers/embedding/ tests/unit/providers/embedding/
git commit -m "feat(providers/embedding): add Qwen3EmbeddingProvider with batching"
```

---

### Task 13: RerankerProvider 接口 + Qwen3 实现

**Files:**
- Create: `src/neblab_rag/providers/reranker/{__init__.py,base.py,qwen3.py}`
- Test: `tests/unit/providers/reranker/test_qwen3.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/providers/reranker/test_qwen3.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neblab_rag.providers.reranker.qwen3 import Qwen3RerankerProvider


@pytest.mark.asyncio
async def test_rerank_returns_sorted_indices_with_scores():
    provider = Qwen3RerankerProvider(
        base_url="https://example.com/v1",
        api_key="key",
        model="qwen3-reranker:8b",
    )
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "results": [
            {"index": 0, "relevance_score": 0.4},
            {"index": 1, "relevance_score": 0.9},
            {"index": 2, "relevance_score": 0.7},
        ],
    }
    fake_response.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
        ranked = await provider.rerank(query="x", documents=["a", "b", "c"], top_k=2)
    assert [r.index for r in ranked] == [1, 2]
    assert ranked[0].score == 0.9
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/providers/reranker/test_qwen3.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/providers/reranker/__init__.py
from neblab_rag.providers.reranker.base import RerankResult, RerankerProvider
from neblab_rag.providers.reranker.qwen3 import Qwen3RerankerProvider

__all__ = ["RerankResult", "RerankerProvider", "Qwen3RerankerProvider"]
```

```python
# src/neblab_rag/providers/reranker/base.py
from abc import ABC, abstractmethod

from pydantic import BaseModel


class RerankResult(BaseModel):
    index: int
    score: float


class RerankerProvider(ABC):
    @abstractmethod
    async def rerank(
        self, query: str, documents: list[str], top_k: int
    ) -> list[RerankResult]: ...
```

```python
# src/neblab_rag/providers/reranker/qwen3.py
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from neblab_rag.providers.reranker.base import RerankerProvider, RerankResult


class Qwen3RerankerProvider(RerankerProvider):
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 60.0):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def rerank(
        self, query: str, documents: list[str], top_k: int
    ) -> list[RerankResult]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url=f"{self._base_url}/rerank",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "query": query,
                    "documents": documents,
                    "top_n": top_k,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        results = [
            RerankResult(index=r["index"], score=r["relevance_score"])
            for r in data["results"]
        ]
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
```

- [ ] **Step 4: 跑测试**

```bash
pytest tests/unit/providers/reranker/ -v
```

- [ ] **Step 5: Commit**

```bash
git add src/neblab_rag/providers/reranker/ tests/unit/providers/reranker/
git commit -m "feat(providers/reranker): add Qwen3RerankerProvider"
```

---

### Task 14: Provider 工厂 + DI 容器

**Files:**
- Create: `src/neblab_rag/providers/factory.py`
- Test: `tests/unit/providers/test_factory.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/providers/test_factory.py
import os
from unittest.mock import patch

import pytest

from neblab_rag.providers.factory import (
    build_embedding_provider,
    build_llm_provider,
    build_reranker_provider,
)


@pytest.fixture
def env():
    return {
        "LLM_BASE_URL": "https://example.com/v1",
        "LLM_API_KEY": "k",
        "LLM_DEFAULT_MODEL": "deepseek-v3.2",
        "EMBEDDING_BASE_URL": "https://example.com/v1",
        "EMBEDDING_API_KEY": "k",
        "EMBEDDING_MODEL": "qwen3-embedding:8b",
        "EMBEDDING_DIM": "4096",
        "RERANKER_BASE_URL": "https://example.com/v1",
        "RERANKER_API_KEY": "k",
        "RERANKER_MODEL": "qwen3-reranker:8b",
        "QDRANT_URL": "http://localhost:6333",
        "OPENALEX_EMAIL": "a@b.com",
    }


def test_build_llm_provider(env):
    with patch.dict(os.environ, env, clear=True):
        provider = build_llm_provider()
    from neblab_rag.providers.llm.deepseek import DeepSeekProvider
    assert isinstance(provider, DeepSeekProvider)


def test_build_embedding_provider(env):
    with patch.dict(os.environ, env, clear=True):
        provider = build_embedding_provider()
    assert provider.dim == 4096


def test_build_reranker_provider(env):
    with patch.dict(os.environ, env, clear=True):
        provider = build_reranker_provider()
    assert provider is not None
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/providers/test_factory.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/providers/factory.py
"""Provider factory wired to Settings.

This is the only place that knows about concrete provider classes;
the rest of the codebase depends only on abstract interfaces.
"""

from neblab_rag.config import Settings, get_settings
from neblab_rag.providers.embedding import EmbeddingProvider, Qwen3EmbeddingProvider
from neblab_rag.providers.llm import LLMProvider
from neblab_rag.providers.llm.deepseek import DeepSeekProvider
from neblab_rag.providers.reranker import Qwen3RerankerProvider, RerankerProvider


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
```

- [ ] **Step 4: 跑测试 + 提交**

```bash
pytest tests/unit/providers/test_factory.py -v
git add src/neblab_rag/providers/factory.py tests/unit/providers/test_factory.py
git commit -m "feat(providers): add factory wired to Settings"
```

---

## Phase 3：数据库层（Tasks 15-18）

### Task 15: SQLAlchemy 模型 — Document + Abstract

**Files:**
- Create: `src/neblab_rag/db/__init__.py`, `engine.py`, `models.py`
- Test: `tests/unit/db/test_models.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/db/test_models.py
from datetime import UTC, datetime

from neblab_rag.db.models import AbstractRecord, Document, IndexStatus


def test_document_default_status():
    doc = Document(
        openalex_id="W123",
        title="Test",
        primary_topic="desertification",
    )
    assert doc.status == IndexStatus.METADATA_ONLY


def test_abstract_record_required_fields():
    rec = AbstractRecord(
        document_id=1,
        text="abstract text",
        language="en",
    )
    assert rec.text == "abstract text"
    assert rec.language == "en"
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/db/test_models.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/db/__init__.py
from neblab_rag.db.engine import get_engine, get_session
from neblab_rag.db.models import AbstractRecord, Base, Document, IndexStatus

__all__ = [
    "AbstractRecord",
    "Base",
    "Document",
    "IndexStatus",
    "get_engine",
    "get_session",
]
```

```python
# src/neblab_rag/db/engine.py
"""SQLAlchemy engine + session factory."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from neblab_rag.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(
        get_settings().postgres_dsn,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


@contextmanager
def get_session() -> Iterator[Session]:
    sm = sessionmaker(bind=get_engine(), expire_on_commit=False)
    session = sm()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

```python
# src/neblab_rag/db/models.py
"""SQLAlchemy ORM models."""

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class IndexStatus(str, enum.Enum):
    METADATA_ONLY = "metadata_only"
    FULLTEXT_PENDING = "fulltext_pending"
    FULLTEXT_INDEXED = "fulltext_indexed"
    FAILED = "failed"


class Document(Base):
    """One row per unique document (paper)."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    openalex_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    venue: Mapped[str | None] = mapped_column(String(500))
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    primary_topic: Mapped[str] = mapped_column(String(100), index=True)
    extra_topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    language: Mapped[str | None] = mapped_column(String(10))
    is_oa: Mapped[bool] = mapped_column(default=False)
    cited_by_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[IndexStatus] = mapped_column(
        Enum(IndexStatus), default=IndexStatus.METADATA_ONLY
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    abstract: Mapped["AbstractRecord | None"] = relationship(
        back_populates="document", cascade="all, delete-orphan", uselist=False
    )


class AbstractRecord(Base):
    """Abstract text per document. Stored separately to keep documents row small."""

    __tablename__ = "abstracts"
    __table_args__ = (UniqueConstraint("document_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10))
    qdrant_point_id: Mapped[str | None] = mapped_column(String(50))

    document: Mapped[Document] = relationship(back_populates="abstract")
```

- [ ] **Step 4: 跑测试 + commit**

```bash
pytest tests/unit/db/test_models.py -v
git add src/neblab_rag/db/ tests/unit/db/
git commit -m "feat(db): define Document and AbstractRecord ORM models"
```

---

### Task 16: Alembic 初始化 + 首版 migration

**Files:**
- Create: `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_initial.py`

- [ ] **Step 1: 初始化 Alembic**

```bash
alembic init -t async alembic
```

(注：使用 `-t async` 模板，但我们用同步 engine 也兼容。)

- [ ] **Step 2: 改 `alembic/env.py`**

```python
# alembic/env.py
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from neblab_rag.config import get_settings
from neblab_rag.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().postgres_dsn)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: 启动 Postgres + 生成首版 migration**

```bash
make up
sleep 3
alembic revision --autogenerate -m "initial: documents and abstracts"
```

- [ ] **Step 4: 应用 migration + 验证**

```bash
alembic upgrade head
docker exec -it neblab-postgres psql -U neblab -d neblab -c "\dt"
# Expected: alembic_version, abstracts, documents
```

- [ ] **Step 5: Commit**

```bash
git add alembic.ini alembic/
git commit -m "feat(db): initial alembic migration for documents + abstracts"
```

---

### Task 17: DocumentRepository

**Files:**
- Create: `src/neblab_rag/db/repositories.py`
- Test: `tests/unit/db/test_repositories.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/db/test_repositories.py
"""Repository unit tests using SQLite in-memory."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from neblab_rag.db.models import Base, IndexStatus
from neblab_rag.db.repositories import DocumentRepository


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine)
    s = sm()
    yield s
    s.close()


def test_upsert_inserts_new_document(session):
    repo = DocumentRepository(session)
    doc = repo.upsert_metadata(
        openalex_id="W1",
        title="hello",
        primary_topic="desertification",
        authors=["A"],
        year=2020,
        language="en",
        is_oa=True,
        cited_by_count=5,
        venue="Nature",
        extra_topics=["land-degradation"],
        doi=None,
        abstract_text="Some abstract about sand.",
        abstract_language="en",
    )
    session.commit()
    assert doc.id is not None
    assert doc.abstract is not None


def test_upsert_updates_existing_document(session):
    repo = DocumentRepository(session)
    repo.upsert_metadata(
        openalex_id="W1", title="v1", primary_topic="t", authors=[], year=None,
        language=None, is_oa=False, cited_by_count=0, venue=None, extra_topics=[],
        doi=None, abstract_text="a1", abstract_language="en",
    )
    session.commit()
    doc = repo.upsert_metadata(
        openalex_id="W1", title="v2", primary_topic="t", authors=[], year=None,
        language=None, is_oa=False, cited_by_count=0, venue=None, extra_topics=[],
        doi=None, abstract_text="a2", abstract_language="en",
    )
    session.commit()
    assert doc.title == "v2"
    assert doc.abstract is not None
    assert doc.abstract.text == "a2"


def test_list_pending_metadata_returns_only_metadata_only(session):
    repo = DocumentRepository(session)
    repo.upsert_metadata(
        openalex_id="W1", title="t", primary_topic="t", authors=[], year=None,
        language=None, is_oa=False, cited_by_count=0, venue=None, extra_topics=[],
        doi=None, abstract_text="a", abstract_language="en",
    )
    session.commit()
    docs = repo.list_documents_with_status(IndexStatus.METADATA_ONLY)
    assert len(docs) == 1
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/db/test_repositories.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/db/repositories.py
"""Repository pattern for Document/Abstract."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from neblab_rag.db.models import AbstractRecord, Document, IndexStatus


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
            self._session.flush()
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

    def mark_qdrant_point(self, document_id: int, point_id: str) -> None:
        doc = self._session.get(Document, document_id)
        if doc and doc.abstract:
            doc.abstract.qdrant_point_id = point_id
```

- [ ] **Step 4: 跑测试 + commit**

```bash
pytest tests/unit/db/test_repositories.py -v
git add src/neblab_rag/db/repositories.py tests/unit/db/test_repositories.py
git commit -m "feat(db): add DocumentRepository with upsert + status query"
```

---

## Phase 4：OpenAlex 采集（Tasks 18-21）

### Task 18: 7 主题关键词配置

**Files:**
- Create: `src/neblab_rag/corpus/__init__.py`, `topics.py`
- Test: `tests/unit/corpus/test_topics.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/corpus/test_topics.py
from neblab_rag.corpus.topics import TOPICS, TopicConfig


def test_seven_topics_defined():
    assert len(TOPICS) == 7


def test_each_topic_has_keywords_in_both_languages():
    for t in TOPICS:
        assert t.zh_keywords, f"{t.id} missing zh"
        assert t.en_keywords, f"{t.id} missing en"


def test_topic_quotas_sum_to_2500():
    assert sum(t.fulltext_quota for t in TOPICS) == 2500
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/corpus/test_topics.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/corpus/__init__.py
```

```python
# src/neblab_rag/corpus/topics.py
"""Seven research topics with keyword sets and full-text quotas.

Quotas come from the spec §3.2 (Plan B / 2500 fulltext target).
"""

from pydantic import BaseModel, Field


class TopicConfig(BaseModel):
    id: str
    label_zh: str
    label_en: str
    priority: str  # "must" or "want"
    fulltext_quota: int
    fulltext_zh: int
    fulltext_en: int
    zh_keywords: list[str] = Field(default_factory=list)
    en_keywords: list[str] = Field(default_factory=list)


TOPICS: list[TopicConfig] = [
    TopicConfig(
        id="desertification",
        label_zh="荒漠化监测/机理（含防沙治沙总论）",
        label_en="Desertification monitoring & mechanisms",
        priority="must",
        fulltext_quota=550,
        fulltext_zh=300,
        fulltext_en=250,
        zh_keywords=["荒漠化", "沙漠化", "沙化", "防沙", "治沙"],
        en_keywords=["desertification", "land degradation", "sand control", "sand stabilization"],
    ),
    TopicConfig(
        id="shelterbelt",
        label_zh="三北防护林/农田防护林",
        label_en="Shelterbelt forests",
        priority="must",
        fulltext_quota=500,
        fulltext_zh=350,
        fulltext_en=150,
        zh_keywords=["三北防护林", "农田防护林", "防护林体系", "三北工程"],
        en_keywords=["shelterbelt", "windbreak", "Three-North", "protective forest"],
    ),
    TopicConfig(
        id="horqin_otindag",
        label_zh="科尔沁/浑善达克沙地",
        label_en="Horqin & Otindag sandlands",
        priority="must",
        fulltext_quota=450,
        fulltext_zh=380,
        fulltext_en=70,
        zh_keywords=["科尔沁沙地", "浑善达克沙地", "奥都格沙地", "内蒙古东部沙地"],
        en_keywords=["Horqin", "Hunshandake", "Otindag", "Inner Mongolia sandland"],
    ),
    TopicConfig(
        id="lidar_uav",
        label_zh="无人机/LiDAR 植被遥感",
        label_en="UAV & LiDAR vegetation remote sensing",
        priority="want",
        fulltext_quota=300,
        fulltext_zh=100,
        fulltext_en=200,
        zh_keywords=["无人机", "激光雷达", "LiDAR", "UAV"],
        en_keywords=["UAV", "LiDAR", "drone", "airborne laser scanning"],
    ),
    TopicConfig(
        id="forest_grass",
        label_zh="林草生态系统结构与功能",
        label_en="Forest-grassland ecosystem structure & function",
        priority="want",
        fulltext_quota=250,
        fulltext_zh=150,
        fulltext_en=100,
        zh_keywords=["林草生态", "林分结构", "乔灌草", "草原生态"],
        en_keywords=["forest grassland", "stand structure", "tree shrub grass"],
    ),
    TopicConfig(
        id="soil_water_dryland",
        label_zh="水土保持/草地退化/干旱区生态",
        label_en="Soil-water conservation, grassland degradation, dryland ecology",
        priority="want",
        fulltext_quota=250,
        fulltext_zh=150,
        fulltext_en=100,
        zh_keywords=["水土保持", "草地退化", "干旱区", "退化草地"],
        en_keywords=["soil and water conservation", "grassland degradation", "drylands", "arid ecology"],
    ),
    TopicConfig(
        id="multi_system_coupling",
        label_zh="山水林田湖草沙系统耦合",
        label_en="Mountain-river-forest-farmland-lake-grassland-sand multi-system coupling",
        priority="want",
        fulltext_quota=200,
        fulltext_zh=180,
        fulltext_en=20,
        zh_keywords=["山水林田湖草沙", "多系统耦合", "生态系统耦合"],
        en_keywords=["mountain river forest farmland lake grassland sand", "ecosystem coupling China"],
    ),
]


TOPIC_BY_ID: dict[str, TopicConfig] = {t.id: t for t in TOPICS}
```

- [ ] **Step 4: 跑测试 + commit**

```bash
pytest tests/unit/corpus/test_topics.py -v
git add src/neblab_rag/corpus/ tests/unit/corpus/
git commit -m "feat(corpus): define 7 research topics with keywords and quotas"
```

---

### Task 19: OpenAlex 客户端封装

**Files:**
- Create: `src/neblab_rag/corpus/openalex_client.py`
- Test: `tests/unit/corpus/test_openalex_client.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/corpus/test_openalex_client.py
from unittest.mock import MagicMock, patch

from neblab_rag.corpus.openalex_client import OpenAlexClient


def test_search_by_keywords_uses_pyalex():
    fake_works = MagicMock()
    fake_works.search.return_value = fake_works
    fake_works.filter.return_value = fake_works
    fake_works.paginate.return_value = iter([
        [
            {
                "id": "https://openalex.org/W1",
                "doi": "10.1/x",
                "title": "Sand control study",
                "publication_year": 2020,
                "language": "en",
                "open_access": {"is_oa": True},
                "cited_by_count": 7,
                "abstract_inverted_index": {"sand": [0], "study": [1]},
                "authorships": [{"author": {"display_name": "Alice"}}],
                "primary_location": {"source": {"display_name": "Nature"}},
            }
        ]
    ])

    with patch("neblab_rag.corpus.openalex_client.Works", return_value=fake_works):
        client = OpenAlexClient(email="a@b.com")
        results = list(client.search_by_keywords(
            keywords=["desertification"],
            language="en",
            max_results=10,
        ))

    assert len(results) == 1
    assert results[0].openalex_id == "W1"
    assert results[0].title == "Sand control study"
    assert results[0].abstract == "sand study"
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/corpus/test_openalex_client.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/corpus/openalex_client.py
"""Thin wrapper over pyalex with our DTO."""

from collections.abc import Iterator

import pyalex
from pydantic import BaseModel
from pyalex import Works


class OpenAlexRecord(BaseModel):
    openalex_id: str
    doi: str | None
    title: str
    authors: list[str]
    venue: str | None
    year: int | None
    language: str | None
    is_oa: bool
    cited_by_count: int
    abstract: str | None


def _restore_abstract(inverted: dict[str, list[int]] | None) -> str | None:
    if not inverted:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


class OpenAlexClient:
    def __init__(self, email: str):
        pyalex.config.email = email

    def search_by_keywords(
        self,
        *,
        keywords: list[str],
        language: str | None = None,
        max_results: int = 1000,
        per_page: int = 100,
    ) -> Iterator[OpenAlexRecord]:
        query = " OR ".join(f'"{k}"' for k in keywords)
        works = Works().search(query)
        if language:
            works = works.filter(language=language)

        count = 0
        for page in works.paginate(per_page=per_page, n_max=max_results):
            for w in page:
                if count >= max_results:
                    return
                yield OpenAlexRecord(
                    openalex_id=w["id"].rsplit("/", 1)[-1],
                    doi=(w.get("doi") or "").removeprefix("https://doi.org/") or None,
                    title=w.get("title") or "",
                    authors=[
                        a["author"]["display_name"]
                        for a in w.get("authorships", [])
                        if a.get("author", {}).get("display_name")
                    ],
                    venue=(w.get("primary_location") or {}).get("source", {}).get("display_name"),
                    year=w.get("publication_year"),
                    language=w.get("language"),
                    is_oa=(w.get("open_access") or {}).get("is_oa", False),
                    cited_by_count=w.get("cited_by_count", 0),
                    abstract=_restore_abstract(w.get("abstract_inverted_index")),
                )
                count += 1
```

- [ ] **Step 4: 跑测试 + commit**

```bash
pytest tests/unit/corpus/test_openalex_client.py -v
git add src/neblab_rag/corpus/openalex_client.py tests/unit/corpus/test_openalex_client.py
git commit -m "feat(corpus): add OpenAlex client wrapper with abstract reconstruction"
```

---

### Task 20: Ingestion service（OpenAlex → DB）

**Files:**
- Create: `src/neblab_rag/corpus/ingestion.py`
- Test: `tests/unit/corpus/test_ingestion.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/corpus/test_ingestion.py
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from neblab_rag.corpus.ingestion import IngestionService
from neblab_rag.corpus.openalex_client import OpenAlexRecord
from neblab_rag.corpus.topics import TOPIC_BY_ID
from neblab_rag.db.models import Base, Document


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sm = sessionmaker(bind=engine)
    s = sm()
    yield s
    s.close()


def test_ingest_topic_inserts_records(session):
    fake_client = MagicMock()
    fake_client.search_by_keywords.return_value = iter([
        OpenAlexRecord(
            openalex_id="W1", doi="10.1/x", title="A", authors=["X"],
            venue="V", year=2020, language="en", is_oa=True, cited_by_count=5,
            abstract="abs",
        ),
        OpenAlexRecord(
            openalex_id="W2", doi=None, title="B", authors=[],
            venue=None, year=2021, language="en", is_oa=False, cited_by_count=1,
            abstract=None,
        ),
    ])

    service = IngestionService(client=fake_client, session=session)
    n = service.ingest_topic(TOPIC_BY_ID["desertification"], language="en", max_results=2)
    session.commit()

    assert n == 2
    docs = session.query(Document).all()
    assert len(docs) == 2
    assert {d.openalex_id for d in docs} == {"W1", "W2"}
    assert docs[0].abstract is not None or docs[1].abstract is not None  # at least one has abstract
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/corpus/test_ingestion.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/corpus/ingestion.py
"""Ingest OpenAlex records into the documents table."""

from sqlalchemy.orm import Session

from neblab_rag.corpus.openalex_client import OpenAlexClient
from neblab_rag.corpus.topics import TopicConfig
from neblab_rag.db.repositories import DocumentRepository
from neblab_rag.logging_config import get_logger

log = get_logger(__name__)


class IngestionService:
    def __init__(self, client: OpenAlexClient, session: Session):
        self._client = client
        self._repo = DocumentRepository(session)
        self._session = session

    def ingest_topic(
        self,
        topic: TopicConfig,
        *,
        language: str,
        max_results: int,
    ) -> int:
        keywords = topic.zh_keywords if language == "zh" else topic.en_keywords
        log.info("ingest_start", topic=topic.id, language=language, max=max_results)

        count = 0
        for rec in self._client.search_by_keywords(
            keywords=keywords,
            language=language,
            max_results=max_results,
        ):
            self._repo.upsert_metadata(
                openalex_id=rec.openalex_id,
                doi=rec.doi,
                title=rec.title,
                authors=rec.authors,
                venue=rec.venue,
                year=rec.year,
                primary_topic=topic.id,
                extra_topics=[],
                language=rec.language,
                is_oa=rec.is_oa,
                cited_by_count=rec.cited_by_count,
                abstract_text=rec.abstract,
                abstract_language=rec.language,
            )
            count += 1
            if count % 100 == 0:
                self._session.flush()
                log.info("ingest_progress", topic=topic.id, count=count)

        log.info("ingest_done", topic=topic.id, language=language, count=count)
        return count
```

- [ ] **Step 4: 跑测试 + commit**

```bash
pytest tests/unit/corpus/test_ingestion.py -v
git add src/neblab_rag/corpus/ingestion.py tests/unit/corpus/test_ingestion.py
git commit -m "feat(corpus): add IngestionService for OpenAlex → DB pipeline"
```

---

### Task 21: CLI 入口 `neblab-ingest`

**Files:**
- Create: `src/neblab_rag/corpus/cli.py`
- Modify: `pyproject.toml`（添加 entry point）

- [ ] **Step 1: 写 CLI**

```python
# src/neblab_rag/corpus/cli.py
"""CLI entrypoint for corpus ingestion.

Usage:
    python -m neblab_rag.corpus.cli ingest --max 200 --language en
    python -m neblab_rag.corpus.cli ingest --topic desertification --language zh
"""

import click

from neblab_rag.config import get_settings
from neblab_rag.corpus.ingestion import IngestionService
from neblab_rag.corpus.openalex_client import OpenAlexClient
from neblab_rag.corpus.topics import TOPIC_BY_ID, TOPICS
from neblab_rag.db.engine import get_session
from neblab_rag.logging_config import configure_logging, get_logger

log = get_logger(__name__)


@click.group()
def cli() -> None:
    """NEBLab corpus operations."""
    configure_logging(get_settings().log_level)


@cli.command("ingest")
@click.option("--topic", "topic_id", default=None, help="Topic id; default: all topics")
@click.option(
    "--language", default="en",
    type=click.Choice(["en", "zh"]),
    help="Language to ingest",
)
@click.option("--max", "max_results", default=500, type=int)
def ingest(topic_id: str | None, language: str, max_results: int) -> None:
    """Ingest OpenAlex metadata for topic(s)."""
    settings = get_settings()
    client = OpenAlexClient(email=settings.openalex_email)

    topics = [TOPIC_BY_ID[topic_id]] if topic_id else TOPICS

    total = 0
    with get_session() as session:
        service = IngestionService(client=client, session=session)
        for t in topics:
            n = service.ingest_topic(t, language=language, max_results=max_results)
            total += n
    log.info("ingest_total", count=total)
    click.echo(f"Ingested {total} documents")


if __name__ == "__main__":
    cli()
```

- [ ] **Step 2: pyproject.toml 添加 console script**

在 `[project]` 节追加：

```toml
[project.scripts]
neblab-ingest = "neblab_rag.corpus.cli:cli"
```

- [ ] **Step 3: 重新 sync + 验证 CLI 帮助**

```bash
uv pip install -e ".[dev]"
neblab-ingest --help
# Expected: 看到 ingest 子命令帮助
```

- [ ] **Step 4: Commit**

```bash
git add src/neblab_rag/corpus/cli.py pyproject.toml uv.lock
git commit -m "feat(corpus): add CLI entrypoint for ingestion"
```

---

## Phase 5：向量层（Tasks 22-23）

### Task 22: Qdrant Repository

**Files:**
- Create: `src/neblab_rag/vector/__init__.py`, `qdrant_repo.py`
- Test: `tests/unit/vector/test_qdrant_repo.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/vector/test_qdrant_repo.py
from unittest.mock import MagicMock

import pytest

from neblab_rag.vector.qdrant_repo import QdrantRepo, VectorPoint


@pytest.fixture
def mock_client():
    return MagicMock()


def test_ensure_collection_creates_if_missing(mock_client):
    mock_client.collection_exists.return_value = False
    repo = QdrantRepo(client=mock_client, collection="test", dim=4)
    repo.ensure_collection()
    mock_client.create_collection.assert_called_once()


def test_upsert_points_passes_correct_payload(mock_client):
    repo = QdrantRepo(client=mock_client, collection="test", dim=4)
    repo.upsert_points([
        VectorPoint(id="1", vector=[0.1, 0.2, 0.3, 0.4], payload={"doc_id": 1}),
    ])
    mock_client.upsert.assert_called_once()
    args = mock_client.upsert.call_args.kwargs
    assert args["collection_name"] == "test"


def test_search_returns_top_hits(mock_client):
    mock_hit = MagicMock()
    mock_hit.id = "p1"
    mock_hit.score = 0.9
    mock_hit.payload = {"doc_id": 1}
    mock_client.query_points.return_value.points = [mock_hit]

    repo = QdrantRepo(client=mock_client, collection="test", dim=4)
    hits = repo.search(query_vector=[0.1, 0.2, 0.3, 0.4], top_k=5)
    assert len(hits) == 1
    assert hits[0].score == 0.9
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/vector/test_qdrant_repo.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/vector/__init__.py
from neblab_rag.vector.qdrant_repo import QdrantRepo, SearchHit, VectorPoint

__all__ = ["QdrantRepo", "SearchHit", "VectorPoint"]
```

```python
# src/neblab_rag/vector/qdrant_repo.py
"""Qdrant access layer."""

from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


class VectorPoint(BaseModel):
    id: str
    vector: list[float]
    payload: dict


class SearchHit(BaseModel):
    id: str
    score: float
    payload: dict


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
            points=[
                PointStruct(id=p.id, vector=p.vector, payload=p.payload)
                for p in points
            ],
        )

    def search(self, query_vector: list[float], top_k: int = 10) -> list[SearchHit]:
        response = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=top_k,
            with_payload=True,
        )
        return [
            SearchHit(id=str(h.id), score=h.score, payload=h.payload or {})
            for h in response.points
        ]
```

- [ ] **Step 4: 跑测试 + commit**

```bash
pytest tests/unit/vector/test_qdrant_repo.py -v
git add src/neblab_rag/vector/ tests/unit/vector/
git commit -m "feat(vector): add Qdrant repository with collection lifecycle"
```

---

### Task 23: Qdrant 工厂

**Files:**
- Modify: `src/neblab_rag/providers/factory.py`

- [ ] **Step 1: 添加 `build_qdrant_repo`**

在 `factory.py` 末尾追加：

```python
from qdrant_client import QdrantClient

from neblab_rag.vector import QdrantRepo


def build_qdrant_repo(settings: Settings | None = None) -> QdrantRepo:
    s = settings or get_settings()
    client = QdrantClient(
        url=s.qdrant.url,
        api_key=s.qdrant.api_key or None,
    )
    return QdrantRepo(client=client, collection=s.qdrant.collection, dim=s.embedding.dim)
```

- [ ] **Step 2: 写测试**

```python
# tests/unit/providers/test_factory.py 末尾追加
def test_build_qdrant_repo_uses_settings(env):
    with patch.dict(os.environ, env, clear=True):
        repo = build_qdrant_repo()
    assert repo is not None
```

并在 import 行添加 `build_qdrant_repo`。

- [ ] **Step 3: 跑测试 + commit**

```bash
pytest tests/unit/providers/test_factory.py -v
git add src/neblab_rag/providers/factory.py tests/unit/providers/test_factory.py
git commit -m "feat(providers): add Qdrant repo factory"
```

---

## Phase 6：摘要级 RAG（Tasks 24-29）

### Task 24: Indexer — 摘要 → 向量入库

**Files:**
- Create: `src/neblab_rag/rag/__init__.py`, `src/neblab_rag/rag/indexer.py`
- Test: `tests/unit/rag/test_indexer.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/rag/test_indexer.py
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
        openalex_id="W1", doi=None, title="t", authors=[], venue=None,
        year=2020, primary_topic="desertification", extra_topics=[],
        language="en", is_oa=True, cited_by_count=0,
        abstract_text="some abstract", abstract_language="en",
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
    assert docs[0].status == IndexStatus.FULLTEXT_INDEXED  # we treat abstract-indexed as enough for v1
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/rag/test_indexer.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/rag/__init__.py
```

```python
# src/neblab_rag/rag/indexer.py
"""Index abstracts into Qdrant.

For v1: 1 abstract = 1 chunk = 1 vector point.
Plan 2 will add multi-chunk indexing for full text.
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
        pending = list(self._repo.list_documents_with_status(
            IndexStatus.METADATA_ONLY
        ))

        total = 0
        for i in range(0, len(pending), batch_size):
            batch = pending[i : i + batch_size]
            texts = [
                f"{d.title}\n\n{d.abstract.text}" if d.abstract else d.title
                for d in batch
            ]
            vectors = await self._embedder.embed(texts)

            points = [
                VectorPoint(
                    id=str(d.id),
                    vector=v,
                    payload={
                        "doc_id": d.id,
                        "openalex_id": d.openalex_id,
                        "title": d.title,
                        "year": d.year,
                        "topic": d.primary_topic,
                        "language": d.language,
                    },
                )
                for d, v in zip(batch, vectors, strict=True)
            ]
            self._qdrant.upsert_points(points)

            for d in batch:
                d.status = IndexStatus.FULLTEXT_INDEXED  # v1: abstract-only counts as indexed
                if d.abstract:
                    d.abstract.qdrant_point_id = str(d.id)

            total += len(batch)
            self._session.flush()
            log.info("index_progress", processed=total, total=len(pending))

        return total
```

- [ ] **Step 4: 跑测试 + commit**

```bash
pytest tests/unit/rag/test_indexer.py -v
git add src/neblab_rag/rag/ tests/unit/rag/
git commit -m "feat(rag): add abstract-level indexer (1 abstract = 1 vector)"
```

---

### Task 25: Retriever — 检索 + 重排

**Files:**
- Create: `src/neblab_rag/rag/retriever.py`
- Test: `tests/unit/rag/test_retriever.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/rag/test_retriever.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from neblab_rag.providers.reranker.base import RerankResult
from neblab_rag.rag.retriever import HybridRetriever, RetrievedChunk
from neblab_rag.vector import SearchHit


@pytest.mark.asyncio
async def test_retrieve_calls_embed_then_search_then_rerank():
    embed = MagicMock()
    embed.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3, 0.4]])

    qdrant = MagicMock()
    qdrant.search.return_value = [
        SearchHit(id="1", score=0.7, payload={"doc_id": 1, "title": "A", "openalex_id": "W1"}),
        SearchHit(id="2", score=0.6, payload={"doc_id": 2, "title": "B", "openalex_id": "W2"}),
        SearchHit(id="3", score=0.5, payload={"doc_id": 3, "title": "C", "openalex_id": "W3"}),
    ]

    rr = MagicMock()
    rr.rerank = AsyncMock(return_value=[
        RerankResult(index=2, score=0.95),
        RerankResult(index=0, score=0.8),
    ])

    retriever = HybridRetriever(embedder=embed, qdrant=qdrant, reranker=rr)
    chunks = await retriever.retrieve(query="sand control", top_k=2, candidate_k=3)

    assert len(chunks) == 2
    assert chunks[0].title == "C"  # reranker put index 2 first
    assert chunks[1].title == "A"
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/rag/test_retriever.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/rag/retriever.py
"""Retrieve + rerank pipeline."""

from pydantic import BaseModel

from neblab_rag.providers.embedding.base import EmbeddingProvider
from neblab_rag.providers.reranker.base import RerankerProvider
from neblab_rag.vector import QdrantRepo


class RetrievedChunk(BaseModel):
    doc_id: int
    openalex_id: str | None
    title: str
    text: str
    score: float


class HybridRetriever:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        qdrant: QdrantRepo,
        reranker: RerankerProvider,
    ):
        self._embedder = embedder
        self._qdrant = qdrant
        self._reranker = reranker

    async def retrieve(
        self, *, query: str, top_k: int = 5, candidate_k: int = 30
    ) -> list[RetrievedChunk]:
        # 1. Embed query
        [query_vec] = await self._embedder.embed([query])

        # 2. Vector search → candidates
        hits = self._qdrant.search(query_vec, top_k=candidate_k)
        if not hits:
            return []

        # 3. Rerank candidates
        candidate_texts = [h.payload.get("title", "") for h in hits]
        rerank_results = await self._reranker.rerank(
            query=query, documents=candidate_texts, top_k=top_k
        )

        # 4. Build output
        out: list[RetrievedChunk] = []
        for r in rerank_results:
            h = hits[r.index]
            out.append(RetrievedChunk(
                doc_id=h.payload.get("doc_id", -1),
                openalex_id=h.payload.get("openalex_id"),
                title=h.payload.get("title", ""),
                text=h.payload.get("title", ""),  # for v1, abstract is in DB; payload has title only
                score=r.score,
            ))
        return out
```

- [ ] **Step 4: 跑测试 + commit**

```bash
pytest tests/unit/rag/test_retriever.py -v
git add src/neblab_rag/rag/retriever.py tests/unit/rag/test_retriever.py
git commit -m "feat(rag): add hybrid retriever with embedding search + reranker"
```

---

### Task 26: Generator — LLM 生成 + 引用标注

**Files:**
- Create: `src/neblab_rag/rag/generator.py`
- Test: `tests/unit/rag/test_generator.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/rag/test_generator.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from neblab_rag.providers.llm.base import ChatResponse
from neblab_rag.rag.generator import AnswerGenerator
from neblab_rag.rag.retriever import RetrievedChunk


@pytest.mark.asyncio
async def test_generate_builds_prompt_with_citations():
    chunks = [
        RetrievedChunk(doc_id=1, openalex_id="W1", title="A", text="content of A", score=0.9),
        RetrievedChunk(doc_id=2, openalex_id="W2", title="B", text="content of B", score=0.8),
    ]
    llm = MagicMock()
    llm.chat = AsyncMock(return_value=ChatResponse(
        content="Per [1] and [2], sand control involves shelterbelts.",
        model="m", finish_reason="stop", prompt_tokens=10, completion_tokens=20,
    ))

    gen = AnswerGenerator(llm=llm)
    answer = await gen.generate(query="What is sand control?", chunks=chunks)

    assert "[1]" in answer.content
    assert len(answer.citations) == 2
    assert answer.citations[0].number == 1
    assert answer.citations[0].title == "A"
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/rag/test_generator.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/rag/generator.py
"""LLM-driven answer generation with inline citations."""

from collections.abc import AsyncIterator

from pydantic import BaseModel

from neblab_rag.providers.llm.base import ChatMessage, ChatRequest, LLMProvider
from neblab_rag.rag.retriever import RetrievedChunk


class Citation(BaseModel):
    number: int
    doc_id: int
    openalex_id: str | None
    title: str


class GeneratedAnswer(BaseModel):
    content: str
    citations: list[Citation]


SYSTEM_PROMPT = """你是北方生态屏障数字实验室的科研助手。
基于下面提供的文献片段回答用户的问题。

规则：
1. 必须用提供的文献片段中的信息作答，不要编造。
2. 在每个论断后用 [N] 标注引用来源（N 是片段编号）。
3. 如果文献片段不足以回答问题，明确说"文献中暂未找到相关结论"。
4. 学术风格，简洁专业，不要使用感叹号或营销式语言。
5. 中文问中文答，英文问英文答。
"""


def _format_chunks(chunks: list[RetrievedChunk]) -> str:
    lines = []
    for i, c in enumerate(chunks, 1):
        lines.append(f"[{i}] {c.title}\n{c.text}\n")
    return "\n".join(lines)


class AnswerGenerator:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def _build_messages(self, query: str, chunks: list[RetrievedChunk]) -> list[ChatMessage]:
        return [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=f"文献片段：\n\n{_format_chunks(chunks)}\n\n问题：{query}",
            ),
        ]

    def _citations(self, chunks: list[RetrievedChunk]) -> list[Citation]:
        return [
            Citation(
                number=i,
                doc_id=c.doc_id,
                openalex_id=c.openalex_id,
                title=c.title,
            )
            for i, c in enumerate(chunks, 1)
        ]

    async def generate(
        self, *, query: str, chunks: list[RetrievedChunk]
    ) -> GeneratedAnswer:
        if not chunks:
            return GeneratedAnswer(
                content="文献库中暂未找到相关结论。",
                citations=[],
            )
        resp = await self._llm.chat(ChatRequest(messages=self._build_messages(query, chunks)))
        return GeneratedAnswer(content=resp.content, citations=self._citations(chunks))

    async def stream(
        self, *, query: str, chunks: list[RetrievedChunk]
    ) -> AsyncIterator[str]:
        if not chunks:
            yield "文献库中暂未找到相关结论。"
            return
        async for chunk in self._llm.stream(
            ChatRequest(messages=self._build_messages(query, chunks))
        ):
            if chunk.delta:
                yield chunk.delta
```

- [ ] **Step 4: 跑测试 + commit**

```bash
pytest tests/unit/rag/test_generator.py -v
git add src/neblab_rag/rag/generator.py tests/unit/rag/test_generator.py
git commit -m "feat(rag): add answer generator with citation annotation"
```

---

### Task 27: 引用校验

**Files:**
- Create: `src/neblab_rag/rag/citation.py`
- Test: `tests/unit/rag/test_citation.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/rag/test_citation.py
from neblab_rag.rag.citation import find_citation_numbers, validate_citations


def test_find_citation_numbers_extracts_all():
    text = "Per [1] and also [2], plus [1] again. [10] is also valid."
    assert find_citation_numbers(text) == {1, 2, 10}


def test_validate_citations_passes_when_all_referenced_exist():
    text = "Per [1] and [2]"
    assert validate_citations(text, num_chunks=3).is_valid is True


def test_validate_citations_fails_when_referencing_nonexistent_chunk():
    text = "Per [5]"
    result = validate_citations(text, num_chunks=3)
    assert result.is_valid is False
    assert 5 in result.invalid_numbers
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/rag/test_citation.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/rag/citation.py
"""Citation parsing and validation."""

import re

from pydantic import BaseModel

CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def find_citation_numbers(text: str) -> set[int]:
    return {int(m) for m in CITATION_PATTERN.findall(text)}


class CitationValidation(BaseModel):
    is_valid: bool
    referenced_numbers: set[int]
    invalid_numbers: set[int]


def validate_citations(text: str, num_chunks: int) -> CitationValidation:
    referenced = find_citation_numbers(text)
    valid_range = set(range(1, num_chunks + 1))
    invalid = referenced - valid_range
    return CitationValidation(
        is_valid=not invalid,
        referenced_numbers=referenced,
        invalid_numbers=invalid,
    )
```

- [ ] **Step 4: 跑测试 + commit**

```bash
pytest tests/unit/rag/test_citation.py -v
git add src/neblab_rag/rag/citation.py tests/unit/rag/test_citation.py
git commit -m "feat(rag): add citation parsing and validation"
```

---

### Task 28: Pipeline — 端到端组合

**Files:**
- Create: `src/neblab_rag/rag/pipeline.py`
- Test: `tests/unit/rag/test_pipeline.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/rag/test_pipeline.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from neblab_rag.rag.generator import Citation, GeneratedAnswer
from neblab_rag.rag.pipeline import RAGPipeline
from neblab_rag.rag.retriever import RetrievedChunk


@pytest.mark.asyncio
async def test_answer_orchestrates_retriever_and_generator():
    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=[
        RetrievedChunk(doc_id=1, openalex_id="W1", title="t", text="x", score=0.9),
    ])
    generator = MagicMock()
    generator.generate = AsyncMock(return_value=GeneratedAnswer(
        content="Per [1].",
        citations=[Citation(number=1, doc_id=1, openalex_id="W1", title="t")],
    ))

    pipeline = RAGPipeline(retriever=retriever, generator=generator)
    result = await pipeline.answer(query="x")
    assert result.answer.content == "Per [1]."
    assert result.citation_validation.is_valid is True
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/rag/test_pipeline.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/rag/pipeline.py
"""End-to-end RAG pipeline: query → retrieve → generate → validate."""

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

    async def answer(self, *, query: str, top_k: int = 5) -> RAGResult:
        chunks = await self._retriever.retrieve(query=query, top_k=top_k)
        answer = await self._generator.generate(query=query, chunks=chunks)
        validation = validate_citations(answer.content, num_chunks=len(chunks))
        return RAGResult(
            query=query, chunks=chunks, answer=answer, citation_validation=validation
        )
```

- [ ] **Step 4: 跑测试 + commit**

```bash
pytest tests/unit/rag/test_pipeline.py -v
git add src/neblab_rag/rag/pipeline.py tests/unit/rag/test_pipeline.py
git commit -m "feat(rag): add end-to-end RAG pipeline"
```

---

### Task 29: SSE /query 端点

**Files:**
- Create: `src/neblab_rag/api/routes/query.py`
- Modify: `src/neblab_rag/api/main.py`
- Test: `tests/unit/api/test_query.py`

- [ ] **Step 1: 写测试**

```python
# tests/unit/api/test_query.py
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from neblab_rag.api.main import create_app
from neblab_rag.api.routes.query import get_pipeline
from neblab_rag.rag.generator import Citation, GeneratedAnswer
from neblab_rag.rag.pipeline import RAGResult
from neblab_rag.rag.retriever import RetrievedChunk


def test_query_returns_answer_and_citations():
    fake_pipeline = MagicMock()
    fake_pipeline.answer = AsyncMock(return_value=RAGResult(
        query="What is sand control?",
        chunks=[
            RetrievedChunk(doc_id=1, openalex_id="W1", title="A", text="x", score=0.9),
        ],
        answer=GeneratedAnswer(
            content="Per [1].",
            citations=[Citation(number=1, doc_id=1, openalex_id="W1", title="A")],
        ),
        citation_validation=type("V", (), {  # quick mock
            "is_valid": True,
            "referenced_numbers": {1},
            "invalid_numbers": set(),
            "model_dump": lambda self: {"is_valid": True, "referenced_numbers": [1], "invalid_numbers": []},
        })(),
    ))

    app = create_app()
    app.dependency_overrides[get_pipeline] = lambda: fake_pipeline

    client = TestClient(app)
    response = client.post("/query", json={"query": "What is sand control?"})
    assert response.status_code == 200
    data = response.json()
    assert "Per [1]" in data["answer"]
    assert data["citations"][0]["title"] == "A"
```

- [ ] **Step 2: 跑测试**

```bash
pytest tests/unit/api/test_query.py -v
```

- [ ] **Step 3: 写实现**

```python
# src/neblab_rag/api/routes/query.py
"""POST /query and GET /query/stream endpoints."""

from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from neblab_rag.providers.factory import (
    build_embedding_provider,
    build_llm_provider,
    build_qdrant_repo,
    build_reranker_provider,
)
from neblab_rag.rag.generator import AnswerGenerator
from neblab_rag.rag.pipeline import RAGPipeline
from neblab_rag.rag.retriever import HybridRetriever

router = APIRouter(tags=["rag"])


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class CitationOut(BaseModel):
    number: int
    doc_id: int
    openalex_id: str | None
    title: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    citation_valid: bool


@lru_cache(maxsize=1)
def _build_pipeline() -> RAGPipeline:
    retriever = HybridRetriever(
        embedder=build_embedding_provider(),
        qdrant=build_qdrant_repo(),
        reranker=build_reranker_provider(),
    )
    generator = AnswerGenerator(llm=build_llm_provider())
    return RAGPipeline(retriever=retriever, generator=generator)


def get_pipeline() -> RAGPipeline:
    return _build_pipeline()


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, pipeline: RAGPipeline = Depends(get_pipeline)):
    result = await pipeline.answer(query=req.query, top_k=req.top_k)
    return QueryResponse(
        answer=result.answer.content,
        citations=[CitationOut(**c.model_dump()) for c in result.answer.citations],
        citation_valid=result.citation_validation.is_valid,
    )


@router.get("/query/stream")
async def stream(query: str, pipeline: RAGPipeline = Depends(get_pipeline)):
    """SSE streaming endpoint."""
    chunks = await pipeline._retriever.retrieve(query=query, top_k=5)

    async def event_generator() -> AsyncIterator[dict]:
        # First emit the citation list
        citations_payload = [
            {"number": i + 1, "title": c.title, "openalex_id": c.openalex_id, "doc_id": c.doc_id}
            for i, c in enumerate(chunks)
        ]
        yield {"event": "citations", "data": str(citations_payload)}

        # Then stream the answer
        async for delta in pipeline._generator.stream(query=query, chunks=chunks):
            yield {"event": "delta", "data": delta}
        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())
```

修改 `src/neblab_rag/api/main.py` —— 在 `app.include_router(health.router)` 后追加：

```python
from neblab_rag.api.routes import query as query_routes
app.include_router(query_routes.router)
```

- [ ] **Step 4: 跑测试 + commit**

```bash
pytest tests/unit/api/test_query.py -v
git add src/neblab_rag/api/ tests/unit/api/
git commit -m "feat(api): add /query (sync) and /query/stream (SSE) endpoints"
```

---

## Phase 7：端到端冒烟测试 + 文档（Tasks 30-32）

### Task 30: 集成冒烟脚本

**Files:**
- Create: `scripts/smoke_run.sh`

- [ ] **Step 1: 写脚本**

```bash
#!/usr/bin/env bash
# scripts/smoke_run.sh
set -euo pipefail

echo "==> Starting docker-compose services"
make up
sleep 5

echo "==> Running migrations"
make migrate

echo "==> Ingesting 50 docs from desertification topic (English)"
neblab-ingest ingest --topic desertification --language en --max 50

echo "==> Indexing pending abstracts"
python -c "
import asyncio
from neblab_rag.db.engine import get_session
from neblab_rag.providers.factory import build_embedding_provider, build_qdrant_repo
from neblab_rag.rag.indexer import AbstractIndexer

async def main():
    with get_session() as session:
        indexer = AbstractIndexer(
            session=session,
            embedder=build_embedding_provider(),
            qdrant=build_qdrant_repo(),
        )
        n = await indexer.index_pending(batch_size=16)
        print(f'Indexed {n} abstracts')

asyncio.run(main())
"

echo "==> Starting API server in background"
uvicorn neblab_rag.api.main:app --port 8000 &
SERVER_PID=$!
trap "kill $SERVER_PID" EXIT
sleep 3

echo "==> Hitting /query"
curl -s -X POST http://localhost:8000/query \
    -H 'Content-Type: application/json' \
    -d '{"query":"What are the main mechanisms of desertification in northern China?"}' \
    | python -m json.tool

echo "==> SUCCESS"
```

- [ ] **Step 2: 给执行权限 + commit**

```bash
chmod +x scripts/smoke_run.sh
git add scripts/smoke_run.sh
git commit -m "chore: add smoke-test script"
```

---

### Task 31: 集成测试（带 docker 服务）

**Files:**
- Create: `tests/integration/test_query_e2e.py`, `tests/conftest.py`

- [ ] **Step 1: 写 conftest.py**

```python
# tests/conftest.py
"""Shared test fixtures."""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def test_env(monkeypatch_session):
    """Ensure unit tests don't accidentally hit real services."""
    monkeypatch_session.setenv("LLM_BASE_URL", "https://invalid.test")
    monkeypatch_session.setenv("LLM_API_KEY", "test")
    monkeypatch_session.setenv("LLM_DEFAULT_MODEL", "test-model")


@pytest.fixture(scope="session")
def monkeypatch_session():
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()
```

- [ ] **Step 2: 写集成测试（标 `@pytest.mark.integration`，CI 默认不跑）**

```python
# tests/integration/test_query_e2e.py
"""End-to-end tests requiring real docker services + real API keys.

Skipped by default. Run with: `pytest tests/integration -v -m integration`
"""

import os

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not os.getenv("LLM_API_KEY") or os.getenv("LLM_API_KEY") == "test",
    reason="real LLM API key required",
)
def test_full_pipeline_runs():
    """Smoke test: assumes services up and at least 1 doc ingested+indexed."""
    from fastapi.testclient import TestClient

    from neblab_rag.api.main import create_app

    app = create_app()
    with TestClient(app) as client:
        resp = client.post("/query", json={"query": "desertification mechanism"})
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert isinstance(data["citations"], list)
```

并在 `pyproject.toml` 的 `[tool.pytest.ini_options]` 追加：

```toml
markers = [
    "integration: tests that require docker services and real API keys",
]
```

并在 ci.yml 中改为 `pytest -m "not integration"`。

- [ ] **Step 3: Commit**

```bash
git add tests/ pyproject.toml .github/workflows/ci.yml
git commit -m "test: add integration test scaffold (skipped by default)"
```

---

### Task 32: README 更新

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 写 README**

```markdown
# NEBLab RAG — 北方生态屏障数字实验室知识库

> Sprint 0 状态：✅ 摘要级 RAG 跑通

## 快速开始

```bash
# 1. 克隆 + 安装
git clone <repo> && cd NEBLab
uv pip install -e ".[dev]"

# 2. 配置环境变量（拷贝 .env.example → .env.local，填入实际值）
cp .env.example .env.local
$EDITOR .env.local

# 3. 启动本地服务（Postgres + Qdrant）
make up
make migrate

# 4. 拉取摘要语料（默认 500 条荒漠化主题英文论文）
neblab-ingest ingest --topic desertification --language en --max 500

# 5. 把摘要建入向量库
python -c "
import asyncio
from neblab_rag.db.engine import get_session
from neblab_rag.providers.factory import build_embedding_provider, build_qdrant_repo
from neblab_rag.rag.indexer import AbstractIndexer

async def main():
    with get_session() as s:
        idx = AbstractIndexer(s, build_embedding_provider(), build_qdrant_repo())
        print(await idx.index_pending(batch_size=32))

asyncio.run(main())
"

# 6. 启动 API
make dev

# 7. 问一下试试
curl -X POST http://localhost:8000/query \
    -H 'Content-Type: application/json' \
    -d '{"query":"What are the main mechanisms of desertification?"}'
```

## 架构（Sprint 0）

```
浏览器 → POST /query → FastAPI
                          ↓
                       RAGPipeline
                          ↓
            ┌───────── HybridRetriever ─────────┐
            ↓                ↓                  ↓
   EmbeddingProvider   QdrantRepo        RerankerProvider
   (qwen3-emb)         (vector search)   (qwen3-rerank)
                          ↓
                    AnswerGenerator
                          ↓
                    LLMProvider (DeepSeek)
                          ↓
                  GeneratedAnswer + Citations
```

## 开发命令

| 命令 | 作用 |
|------|------|
| `make up` | 启动 Postgres + Qdrant |
| `make down` | 停止 |
| `make migrate` | 跑 Alembic migration |
| `make test` | 跑单元测试 |
| `make lint` | ruff 检查 |
| `make format` | ruff 格式化 |
| `make typecheck` | pyright |
| `make dev` | 启动 dev server |

## 文档

- 设计：`docs/superpowers/specs/2026-05-01-rag-v1-design.md`
- Plan 1（本 Plan，基建+摘要 RAG）：`docs/superpowers/plans/2026-05-01-rag-v1-plan-01-foundation.md`
- 后续 Plan：见 `docs/superpowers/plans/`

## License

TBD
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: write README for Sprint 0"
```

---

## Phase 8：交付验收（Tasks 33-34）

### Task 33: 端到端真机演示

- [ ] **Step 1: 配置 `.env.local`**（你需要填入真实 API key）

- [ ] **Step 2: 跑冒烟脚本**

```bash
bash scripts/smoke_run.sh
```

预期：脚本无错误结束，最后看到 `==> SUCCESS` 和 JSON 形式的回答（含 citations 数组）。

- [ ] **Step 3: 手动测试若干个查询**

```bash
make dev &
sleep 3

# 中文问
curl -s -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"科尔沁沙地植被恢复有哪些主流方法？"}' | python -m json.tool

# 英文问
curl -s -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"What are common LiDAR methods for forest structure measurement?"}' | python -m json.tool
```

- [ ] **Step 4: 检查回答**

  - 是否每个论断后都有 `[N]` 引用？
  - `citations` 数组的 `title` 是否真的相关？
  - 是否有"瞎编"的论文（不在 citations 里的引用编号）？

如有问题：调整 `SYSTEM_PROMPT`，重测。

---

### Task 34: 关闭 Sprint 0

- [ ] **Step 1: 全测试通过**

```bash
make lint
make format
make typecheck
make test
```

- [ ] **Step 2: 推送到 origin**

```bash
git push -u origin main
```

- [ ] **Step 3: 在 GitHub 创建 release tag**

```bash
git tag -a v0.1.0-sprint0 -m "Sprint 0: foundation + abstract-level RAG"
git push origin v0.1.0-sprint0
```

- [ ] **Step 4: 在 spec 文档里勾选 Sprint 0 完成**

修改 `docs/superpowers/specs/2026-05-01-rag-v1-design.md` §8，把 `Sprint 0：基建` 标 ✅。

```bash
git add docs/
git commit -m "docs: mark Sprint 0 complete"
git push
```

---

## 完成标准

执行完所有 34 个任务后，满足以下条件即视为 Plan 1 完成：

- [ ] `make test` 全绿（所有单元测试通过）
- [ ] `make lint` `make typecheck` 全绿
- [ ] `bash scripts/smoke_run.sh` 成功跑完
- [ ] `POST /query` 能在 < 10 秒返回带引用的回答
- [ ] 数据库里有 ≥ 50 条 documents，对应 abstracts 都有 `qdrant_point_id`
- [ ] Qdrant 集合 `neblab_abstracts` 中有对应数量的向量
- [ ] CI on `main` 全绿
- [ ] README 里的"快速开始"对一个新克隆者完全可重复

完成后，**进入 Plan 2（全文采集 pipeline）和 Plan 3（核心 RAG + UI）并行开发阶段**。
