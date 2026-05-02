# NEBLab RAG — 北方生态屏障数字实验室知识库

> Sprint 0 状态：✅ 摘要级 RAG 全链路跑通（OpenAlex 采集 → Qdrant 向量库 → DeepSeek 生成带引用的答案）

NEBLab 是中国国家级生态/防沙治沙研究项目（北方生态屏障数字实验室）的母项目，本仓库实现其中的 **RAG 知识库子系统 v1**。

---

## 快速开始

```bash
# 1. 克隆 + 安装依赖
git clone <repo> && cd NEBLab
mamba env create -f environment.yml   # 一次性
mamba activate NEBLab
uv pip install -e ".[dev]"

# 2. 配置环境变量（拷贝示例 → 填入真实 endpoint / API key）
cp .env.example .env.local
$EDITOR .env.local

# 3. 起本地 Postgres（Qdrant 走云，无需本地起）
make pg-start
make migrate

# 4. 一键端到端冒烟（采集 50 篇 → 入向量库 → 起 API → POST /query）
bash scripts/smoke_run.sh
```

或者按部就班分步跑：

```bash
# 拉摘要语料（最大 5000，主题 desertification，英文）
neblab-ingest ingest --topic desertification --language en --max 500

# 把 status=METADATA_ONLY 的摘要 embed + upsert 到 Qdrant
python -c "
import asyncio
from neblab_rag.db.engine import get_session
from neblab_rag.providers.factory import build_embedding_provider, build_qdrant_repo
from neblab_rag.rag.indexer import AbstractIndexer

async def main():
    with get_session() as s:
        idx = AbstractIndexer(session=s, embedder=build_embedding_provider(), qdrant=build_qdrant_repo())
        print(await idx.index_pending(batch_size=32))

asyncio.run(main())
"

# 起 API
make dev

# 同步问答
curl -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"What are the main mechanisms of desertification in northern China?"}'

# 流式问答（SSE：先收 citations，再连续收 delta，最后 done）
curl -N "http://localhost:8000/query/stream?query=desertification%20mechanism"
```

---

## 架构（Sprint 0：摘要级 RAG）

```
浏览器 → POST /query → FastAPI
                          ↓
                       RAGPipeline
                          ↓
            ┌───────── HybridRetriever ─────────┐
            ↓                ↓                  ↓
   EmbeddingProvider   QdrantRepo        RerankerProvider
   (Qwen3 4096-d)      (cosine 30→top_k) (Qwen3 cross-encoder)
                          ↓
                    AnswerGenerator
                          ↓
                    LLMProvider (DeepSeek-V3.2)
                          ↓
                  GeneratedAnswer + Citations [N]
                          ↓
                  CitationValidator（[N] 是否在 chunk 范围）
```

**Provider 层是单一切换点**：换 vendor 只改 `src/neblab_rag/providers/factory.py` 一处，业务代码全靠抽象接口（`LLMProvider` / `EmbeddingProvider` / `RerankerProvider`）。

**摘要 = 一个 chunk = 一个向量**（Sprint 0 不分块，整段摘要直接 embed）。Plan 2 会引入多块切分支持全文。

---

## 数据流

```
OpenAlex API → DocumentRepository.upsert (Postgres)
                                        ↓
                              status=METADATA_ONLY
                                        ↓
                              AbstractIndexer (Qwen3 emb + Qdrant upsert)
                                        ↓
                             status=FULLTEXT_INDEXED
                                        ↓
                              HybridRetriever 可见
```

| 存储 | 内容 |
|---|---|
| Postgres `documents` | OpenAlex 元数据 + 本地状态（IndexStatus enum） |
| Postgres `abstracts` | 摘要纯文本 + 对应 Qdrant point id |
| Qdrant Cloud `neblab_abstracts` | 4096-d cosine 向量，payload = {doc_id, openalex_id, title, year, topic, language} |

---

## 开发命令

| 命令 | 作用 |
|------|------|
| `make pg-start` / `pg-stop` / `pg-status` | 本地 Postgres 生命周期（Homebrew 服务） |
| `make migrate` | Alembic upgrade head |
| `make ingest` | OpenAlex 采集 CLI（`neblab-ingest` 同义） |
| `make dev` | uvicorn `--factory --reload :8000` |
| `make test` | 跑全部单元测试 |
| `make lint` | ruff check |
| `make format` | ruff format |
| `make typecheck` | pyright |

跑集成测试（需 .env.local 真 endpoint + 至少 1 篇文档已 ingest+index）：

```bash
pytest tests/integration -m integration
```

---

## 文档

- 设计文档：`docs/superpowers/specs/2026-05-01-rag-v1-design.md`
- Plan 1（本仓库的实施 Plan，基建 + 摘要 RAG）：`docs/superpowers/plans/2026-05-01-rag-v1-plan-01-foundation.md`
- 后续 Plan（多块全文 / 评测 / 多模态）：`docs/superpowers/plans/`

## License

TBD
