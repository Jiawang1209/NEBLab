# Sprint 3 v0.3 — 引用 [N] 侧栏 Chunk 正文预览 设计文档

**项目**：NEBLab RAG — Web UI v0.3
**日期**：2026-05-19
**阶段**：v1 MVP / Sprint 3 UI 第三轮迭代
**状态**：待用户审阅

---

## 1. 背景与动机

v0.2（commit `9a8757c`）已交付：聊天 UI、流式答案、左侧 session 历史、右侧引用面板（折叠/展开、外链 OpenAlex）。

**当前痛点**：用户读到答案中的 `[3]`、想验证该论断是否真的有文献支撑时，只能：

1. 点 `[3]` → 滚到右侧第 3 张卡片
2. 看到卡片只有**标题** + OpenAlex 链接
3. 想确认 chunk 正文 → 必须点外链跳到 OpenAlex 网站 → 那里只显示摘要，不是被检索到的 chunk

整个链路断开了"被引用的 chunk 究竟说了什么"这个关键信号。**v0.3 把 chunk 正文带到侧栏卡片里**，用户在一次点击内就能完成"读答案 → 验证证据"闭环。

## 2. 范围

### 2.1 包含

- 后端：`Citation` schema 加 `chunk_text: str` 字段，沿 pipeline 传到 API 响应和 SSE 事件
- 前端：
  - `Citation` TypeScript 类型加 `chunk_text` 字段
  - SSE 流解析消费新字段
  - 引用面板每张卡片增加可折叠的 chunk 正文区块
  - 点击答案中 `[N]` 自动展开对应卡片的 chunk 正文（不再只是滚动）
- 测试：后端单测覆盖新字段的端到端传递

### 2.2 不包含（推迟到 v0.4+）

- 高亮 chunk 内 "支持该引用的具体句子"（需 LLM 额外一轮，跨越简单 UI 改动的范围）
- 答案导出 Markdown / PDF（v0.4 的候选）
- 多轮对话深化（已经有 v0.2 的 ChatSession 基础，但深化用户体验放到独立 sprint）
- 引用卡片的全屏 modal 视图
- 移动端响应式（当前布局是固定三栏；移动适配放到独立 sprint）
- chunk 正文的截断 + "展开全文" 二级状态——本 sprint 默认展开后全文显示，chunk_size=1000 下 chunk 实际 500-1200 字符可读

### 2.3 显式不破坏

- v0.2 引用面板的折叠/展开行为、外链 OpenAlex 行为
- `Citation` 已有字段（`number / doc_id / openalex_id / title`）不动；只**新增** `chunk_text`
- `chunk_text` 在前端类型上**可选**（`chunk_text?: string`），保证旧 API / 部分错误响应不会让前端崩
- 后端 `Citation.chunk_text` 必填，避免歧义；旧的客户端忽略未知字段，不影响兼容

## 3. 数据流设计

### 3.1 当前数据流

```
HybridRetriever
    │ List[Chunk]  (含 .text, .title, .doc_id, .openalex_id)
    ▼
AnswerGenerator.generate()
    │ 构造 Citation(number, doc_id, openalex_id, title)
    │ ← 丢弃了 chunk.text
    ▼
RAGResult.answer.citations: list[Citation]
    │
    ▼
api/routes/query.py
    │ CitationOut(number, doc_id, openalex_id, title)
    │
    ▼ SSE event "citations" / JSON response
前端 / SSE consumer
    │ Citation TS type
    ▼
CitationsPanel 渲染（只显示 title）
```

### 3.2 v0.3 数据流（变更点 ▲）

```
HybridRetriever  (不变)
    ▼
AnswerGenerator.generate()
    │ Citation(number, doc_id, openalex_id, title, ▲ chunk_text=c.text)
    ▼
RAGResult.answer.citations  (不变,只是新字段透传)
    ▼
api/routes/query.py
    │ CitationOut(number, doc_id, openalex_id, title, ▲ chunk_text)
    ▼ SSE event "citations" 包含 chunk_text
前端
    │ Citation TS type 增加 ▲ chunk_text?: string
    ▼
CitationsPanel 卡片增加 ▲ chunk text 折叠块 + chevron toggle
```

### 3.3 数据源选择

`chunk_text` 来自 `Chunk.text`——后者在 retrieval 完成时已经在内存里（Qdrant payload 的 `text` 字段，CLAUDE.md 第 3 节有约定）。**不增加任何数据库或 Qdrant 查询**。

注意：`AnswerGenerator` 内部已经在 prompt 拼装里用过 `c.text`（generator.py:155 `f"[{i}] {c.title}\n{c.text}\n"`），所以这条数据通路是验证过的。

## 4. UI 设计

### 4.1 引用面板卡片结构（变更前 → 变更后）

**v0.2**：
```
┌─ 卡片 ────────────────────────┐
│  1    Title of the document   │
│       openalex_id             │
└───────────────────────────────┘
```

**v0.3**：
```
┌─ 卡片 ───────────────────────────────┐
│  1    Title of the document          │
│       openalex_id                    │
│       ────────────────────────────── │
│       ⌄ 显示 chunk 正文              │  ← 默认折叠
└──────────────────────────────────────┘
```

展开后：
```
┌─ 卡片 ───────────────────────────────┐
│  1    Title of the document          │
│       openalex_id                    │
│       ────────────────────────────── │
│       ⌃ 隐藏 chunk 正文              │
│                                      │
│       "We observed that shelterbelt  │
│        mass transport reduced by     │
│        40-60% under heavy ground     │
│        cover..." (~500-1200 字符)    │
│                                      │
└──────────────────────────────────────┘
```

### 4.2 交互细节

| 操作 | v0.2 行为 | v0.3 行为 |
|---|---|---|
| 点击答案中 `[N]` | 引用面板展开（若折叠）→ 滚到第 N 张卡片 | 同 v0.2 + 该卡片的 chunk 正文自动展开 |
| 点击卡片自身（任意位置）的 ⌄/⌃ chevron | 无 | 切换该卡片 chunk 正文的展开/收起 |
| 同一卡片二次点击 [N] | 滚动至卡片 | 同 v0.2（chunk 正文保持展开状态） |
| 关闭引用面板 (右上 ⟩) | 引用面板折叠成窄条 | 同 v0.2；下次展开时所有 chunk 正文回到折叠状态（清空 expanded set） |

### 4.3 默认状态

- 新答案到达 → 所有 citation 卡片默认折叠（与 v0.2 一致）
- chunk text 区块默认**折叠**，避免侧栏被 7 张 1000 字 chunk 灌满
- 用户首次点 [N] → 滚动 + 展开该卡片的 chunk

### 4.4 视觉

- chunk 正文用 `text-muted-foreground` 配色、`text-[0.8rem] leading-6`、`max-h-none`（无截断）
- chevron 用 `lucide-react` 的 `ChevronDown` / `ChevronUp`（已经依赖）
- 卡片之间分隔线在 chunk 正文区块上方再加一条 `border-t border-border/40`
- 平台保持现有的暗色 sidebar / 卡片对比度

## 5. 实施清单

### 5.1 后端

1. **`src/neblab_rag/rag/generator.py`**
   - `Citation` 模型增加 `chunk_text: str`
   - 在 line 197-202 构造时增加 `chunk_text=c.text`

2. **`src/neblab_rag/api/routes/query.py`**
   - `CitationOut` 增加 `chunk_text: str`（不写默认值，要 fail-fast，避免后端漏掉数据时前端拿到 undefined）

3. **`tests/unit/rag/test_generator.py`** / **`tests/unit/api/test_query.py`**
   - 断言生成的 Citation / CitationOut 含非空 `chunk_text` 且等于源 chunk 的 text

4. **`tests/unit/rag/test_pipeline.py`** 端到端 fake 链路
   - 给 fake retriever 返 chunk(text="hello world") → 断言 result.answer.citations[0].chunk_text == "hello world"

### 5.2 前端

5. **`web/src/lib/types.ts`**
   - `Citation.chunk_text?: string`（可选，向后兼容）

6. **`web/src/hooks/use-stream-query.ts`**
   - SSE 事件 `citations` 的 parser 把 `chunk_text` 透传

7. **`web/src/components/citations-panel.tsx`**
   - 卡片增加 `expandedCites: Set<number>` 状态
   - 每张卡片底部增加 chevron + 可展开 chunk 区
   - 接受 `expandedCites` 和 `onToggleExpand` props
   - 关闭面板时清空 `expandedCites`

8. **`web/src/app/page.tsx`**
   - 把 `expandedCites: Set<number>` 状态提升到 page 级（因为答案区的 [N] 点击也要影响它）
   - `onCitationClick(n)` 处理器除了 scroll，还把 n 加入 expandedCites
   - 切换 session 时 reset expandedCites（与 session 状态绑定，避免跨 session 串味）
   - 引用面板的 `onToggle`（关闭面板）也 reset expandedCites（与 §4.2 表格"关闭引用面板"一致）
   - 旧 session 持久化里的 citations 可能没有 `chunk_text`——前端类型已 optional，UI 在 chunk_text 缺失时**完全隐藏 chevron 和 chunk 区块**（卡片回退到 v0.2 样式）

### 5.3 验证

9. `make test` 全通过
10. `make lint && make typecheck` 通过
11. `make dev` + `cd web && npm run dev`，手动核验：
    - 提一个简单查询（"为什么过度放牧加速荒漠化"），等流式答案完成
    - 点答案里的 `[2]` → 侧栏展开第 2 张卡片，且 chunk 正文展开可见
    - 点该卡片 chevron 收起，再点 [2] → 又展开
    - 关闭引用面板再打开 → 所有 chunk 回到折叠
    - 切换历史 session → 引用刷新、expanded set 清空

## 6. 风险与回滚

| 风险 | 缓解 |
|---|---|
| chunk_text 包含特殊字符（换行/Markdown/HTML）破坏侧栏布局 | 用 `<pre>` 或保留换行的纯文本渲染，不走 Markdown 渲染器；CSS `whitespace-pre-wrap` |
| 7 张 chunk 全展开后侧栏过长 | 默认折叠 + 用户主动展开是核心设计——不主动全展开 |
| Next.js 16 的 server/client 边界 | 引用面板已经是 `"use client"`；新 state 都在客户端组件 |
| 测试中的 fake retriever 不返回 chunk text 字段 | 测试 fake 必须 explicit set `text="..."`；fix 测试 fixture |
| SSE 流大小膨胀（每个 chunk +1KB） | 7 × 1KB = 7KB 单次 SSE event，CDN/浏览器都 OK；不优化 |

回滚：单文件级。后端 / 前端两个 PR 都是纯增量字段。后端先 merge，前端跟上；如前端找到 bug 可单独 revert 前端。

## 7. 文件清单

| 文件 | 改动 |
|---|---|
| `src/neblab_rag/rag/generator.py` | `Citation` +1 字段，构造 +1 参数 |
| `src/neblab_rag/api/routes/query.py` | `CitationOut` +1 字段 |
| `tests/unit/rag/test_generator.py` | 加断言 |
| `tests/unit/api/test_query.py` | 加 chunk_text 流出测试 |
| `tests/unit/rag/test_pipeline.py` | 端到端断言 |
| `web/src/lib/types.ts` | `Citation.chunk_text?` |
| `web/src/hooks/use-stream-query.ts` | parser 透传 |
| `web/src/components/citations-panel.tsx` | chevron + chunk 区块 + expanded state |
| `web/src/app/page.tsx` | expandedCites 状态 + onCitationClick 联动 |

## 8. 不在本文档范围

下一轮 UI sprint 候选（按使用价值排）：
- **v0.4** 多轮对话深度 / 答案导出 Markdown
- **v0.5** 移动端响应式 / chunk 内支撑句高亮
- **v0.6+** 离线缓存 / 用户可保留的 query 收藏

---

**状态**：等待用户审阅本文档；通过后调用 writing-plans skill 形成执行计划。
