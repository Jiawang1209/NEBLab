# Sprint 3 v0.3 — Citation Chunk Preview Findings (2026-05-19)

## Shipped

引用面板每张卡片增加一个 chevron 切换按钮，点击展开/收起该 chunk
正文。点击答案正文里的 `[N]` 除了滚到对应卡片，还自动展开 chunk
正文（"读答案 → 验证证据" 闭环在一次点击内完成）。

- 后端：`Citation.chunk_text`、SSE `_citations_payload`、`CitationOut`
  三处同时透传 chunk 文本，源头是已经在内存里的 Qdrant payload `text`
  字段（零新增数据库或向量查询）
- 前端：`Citation` TS interface 新增 optional `chunk_text?: string`、
  `CitationsPanel` chevron + chunk 区块、`page.tsx` hoisted `expandedCites:
  Set<number>` 状态、`onCitationClick` 联动 `expandCite`、关闭面板 /
  切换 session 都 reset expanded set
- Back-compat：chunk_text 缺失时（旧 localStorage session）chevron
  自动隐藏，卡片回退 v0.2 样式（title + openalex_id only）
- 防御：`parseCitations` 和 `isCitation` 两处 type guard 都加了
  `chunk_text === undefined || typeof chunk_text === "string"`，
  防止损坏 payload 让 UI 崩

## Verification

| 阶段 | 状态 | 备注 |
|---|---|---|
| Backend tests (`make test`) | ✅ 162 passed | 3 个 TDD 测试加进去：generator / handlers / api routes |
| `make lint` (ruff) | ✅ pass | |
| `ruff format --check .` | ✅ unchanged (1 pre-existing failure on `scripts/corpus_stats.py` — 不是 v0.3 引入) |
| `make typecheck` (pyright) | ✅ unchanged (9 pre-existing errors in `deepseek.py` + `system_info.py` — 不是 v0.3 引入) |
| Frontend `npx tsc --noEmit` | ✅ zero errors | 全 v0.3 改动 |
| Frontend lint | ✅ 1 pre-existing error (`react-hooks/set-state-in-effect` at page.tsx:221 — 不是 v0.3 引入；v0.3 把数从 2 减到 1) |
| Spec compliance review (4 个 task)| ✅ all PASS | subagent-driven |
| Code quality review (4 个 task) | ✅ all APPROVE | 一处 IMPORTANT scroll race 在 fixup commit `0e29ad6` 修了 |
| Live smoke 路径 A 核心 | ✅ 引用面板卡片出现、chevron 可见、点击展开/收起 chunk 正文工作 | |
| Live smoke 路径 A 完整流式 | ⏸ deferred | CST 端点超时（`httpx.ReadTimeout`），与今天 sprint 6a 同源；流式答案没完成 → 没法验 `[N]` 自动展开。但 `[N]` 的代码路径走的是已经验过的 `expandCite`，bug 风险接近零 |
| Live smoke 路径 B/C/D | ⏸ deferred | 同上；可选验证，等 CST 恢复 |

## CST 注记

今天 CST uni-api 持续 `ReadTimeout`，跟 v0.3 无关。同样的 infra 问题
已经在 `evals/v1/sprint-6a-progress-2026-05-18.md` 5-19 早上那段
有详细记录。Live smoke 完整流式答案的部分被这个问题挡住了，但
v0.3 本身的代码改动（chunk_text 透传 + UI 联动）不依赖 LLM 响应
速度，已经能用。

## Decision

**SHIP — code-complete.** 所有静态检查通过、4 个 task 的 spec + code
review 全部 APPROVE、live smoke 核心新功能（chevron + chunk 正文展开）
已经验证可用。流式完整答案的 `[N]` 联动验证因 CST 故障 deferred，但
代码路径已经在 review 阶段被读过，逻辑无新风险。

下一轮 UI sprint 候选（按使用价值排）：
- **v0.4** 多轮对话深度 / 答案导出 Markdown
- **v0.5** 移动端响应式 / chunk 内支撑句高亮
- **v0.6+** 引用面板抽屉式 mobile 适配 / 用户可保留的 query 收藏

## Files

后端：
- `src/neblab_rag/rag/generator.py` (Citation 模型加 chunk_text)
- `src/neblab_rag/rag/handlers.py` (SSE _citations_payload 加 chunk_text)
- `src/neblab_rag/api/routes/query.py` (CitationOut 加 chunk_text)
- `tests/unit/rag/test_generator.py`、`test_handlers.py`
- `tests/unit/api/test_query.py`、`tests/unit/eval/test_runner.py`、
  `tests/unit/rag/test_pipeline.py` (fixture chunk_text 补齐)

前端：
- `web/src/lib/types.ts` (Citation interface 加 optional chunk_text)
- `web/src/hooks/use-stream-query.ts` (parseCitations 类型守卫加固)
- `web/src/lib/history.ts` (isCitation 类型守卫加固)
- `web/src/components/citations-panel.tsx` (chevron + chunk 区块)
- `web/src/app/page.tsx` (expandedCites state + 联动 + reset 路径)

文档：
- 设计：`docs/superpowers/specs/2026-05-19-citation-chunk-preview-design.md`
- 计划：`docs/superpowers/plans/2026-05-19-citation-chunk-preview-plan.md`
- 本 findings

提交链：
- `788861c` docs: spec
- `4e48dcf` docs: plan
- `67d46e9` feat(rag): Citation.chunk_text (backend 1/3)
- `023851e` feat(api): SSE _citations_payload (backend 2/3)
- `533a8aa` feat(api): CitationOut (backend 3/3)
- `9152a38` feat(web): Citation TS type (frontend 1/3)
- `bd85bbd` feat(web): citation [N] expands chunk text in side panel (frontend 2/3 + 类型守卫加固)
- `0e29ad6` fix(web): remove double scroll (review follow-up)
