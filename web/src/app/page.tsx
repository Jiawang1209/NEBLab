"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { Citation } from "@/lib/types";
import { useStreamQuery } from "@/hooks/use-stream-query";

const CITATION_PATTERN = /\[(\d+)\]/g;

interface CitationChipProps {
  number: number;
  citation: Citation | undefined;
}

function CitationChip({ number, citation }: CitationChipProps) {
  const title = citation?.title ?? "未找到对应文献";
  return (
    <span
      title={title}
      className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded bg-primary/10 px-1.5 align-baseline text-[0.7rem] font-medium text-primary tabular-nums"
    >
      {number}
    </span>
  );
}

interface AnswerProps {
  text: string;
  citations: readonly Citation[];
}

function Answer({ text, citations }: AnswerProps) {
  const byNumber = new Map<number, Citation>(
    citations.map((c) => [c.number, c]),
  );

  const parts: Array<string | { num: number }> = [];
  let cursor = 0;
  for (const match of text.matchAll(CITATION_PATTERN)) {
    const start = match.index ?? 0;
    if (start > cursor) parts.push(text.slice(cursor, start));
    parts.push({ num: Number(match[1]) });
    cursor = start + match[0].length;
  }
  if (cursor < text.length) parts.push(text.slice(cursor));

  return (
    <div className="whitespace-pre-wrap text-base leading-7">
      {parts.map((part, i) =>
        typeof part === "string" ? (
          <span key={`t-${i}`}>{part}</span>
        ) : (
          <CitationChip
            key={`c-${i}-${part.num}`}
            number={part.num}
            citation={byNumber.get(part.num)}
          />
        ),
      )}
    </div>
  );
}

interface CitationListProps {
  citations: readonly Citation[];
}

function CitationList({ citations }: CitationListProps) {
  if (citations.length === 0) return null;
  return (
    <section className="mt-10 border-t border-border pt-6">
      <h2 className="mb-3 text-xs font-medium tracking-widest text-muted-foreground uppercase">
        引用 · {citations.length}
      </h2>
      <ol className="space-y-2 text-sm">
        {citations.map((c) => {
          const href = c.openalex_id
            ? `https://openalex.org/${c.openalex_id}`
            : null;
          return (
            <li key={c.number} className="flex gap-3 leading-6">
              <span className="w-6 shrink-0 text-right tabular-nums text-muted-foreground">
                [{c.number}]
              </span>
              {href ? (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-foreground underline-offset-4 hover:underline"
                >
                  {c.title}
                </a>
              ) : (
                <span className="text-foreground">{c.title}</span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export default function Home() {
  const [input, setInput] = useState("");
  const { question, answer, citations, isStreaming, error, ask } =
    useStreamQuery();

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    if (isStreaming) return;
    const trimmed = input.trim();
    if (!trimmed) return;
    ask(trimmed);
    setInput("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>): void {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      e.currentTarget.form?.requestSubmit();
    }
  }

  const showResult = question.length > 0;

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-6 py-12 sm:py-16">
      <header className="mb-12">
        <p className="text-xs font-medium tracking-[0.2em] text-muted-foreground uppercase">
          NEBLab · 知识库 v1
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          北方生态屏障·研究助手
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground">
          基于 1810 篇 desertification / shelterbelt 中英文文献，回答带引用、可追溯。
          引用准确率（86 题 eval）：63.9%。
        </p>
      </header>

      <section className="flex-1">
        {showResult ? (
          <article className="space-y-6">
            <div className="text-sm text-muted-foreground">您的提问</div>
            <p className="text-lg font-medium leading-8 text-foreground">
              {question}
            </p>
            <div className="text-sm text-muted-foreground">回答</div>
            {error ? (
              <p className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {error}
              </p>
            ) : (
              <Answer text={answer} citations={citations} />
            )}
            {isStreaming && (
              <p className="text-xs text-muted-foreground">正在生成回答…</p>
            )}
            <CitationList citations={citations} />
          </article>
        ) : (
          <div className="rounded-lg border border-dashed border-border p-8 text-sm leading-7 text-muted-foreground">
            <p className="font-medium text-foreground">建议的提问方式</p>
            <ul className="mt-3 list-disc space-y-1 pl-5">
              <li>问一个具体问题：「中国三北防护林对当地气温有什么影响？」</li>
              <li>问机制：「为什么过度放牧会加速荒漠化？」</li>
              <li>对比：「干旱区和半干旱区的恢复策略有何不同？」</li>
            </ul>
            <p className="mt-4 text-xs">
              中文与英文均可。系统会把中文问题翻译成英文检索文献，再用中文回答。
            </p>
          </div>
        )}
      </section>

      <form
        onSubmit={handleSubmit}
        className="mt-8 sticky bottom-6 flex gap-2 rounded-2xl border border-border bg-background p-2 shadow-sm focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50"
      >
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="问点什么…（Enter 发送，Shift+Enter 换行）"
          rows={2}
          className="resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
          disabled={isStreaming}
        />
        <Button
          type="submit"
          size="lg"
          disabled={isStreaming || input.trim().length === 0}
          className="self-end"
        >
          {isStreaming ? "生成中" : "发送"}
        </Button>
      </form>
    </main>
  );
}
