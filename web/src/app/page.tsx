"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Sidebar } from "@/components/sidebar";
import { AnswerMarkdown } from "@/components/answer-markdown";
import { CitationsPanel } from "@/components/citations-panel";
import type { ChatTurn, Citation } from "@/lib/types";
import { useStreamQuery } from "@/hooks/use-stream-query";
import { loadHistory, saveHistory, newTurnId } from "@/lib/history";

const SAMPLE_QUESTIONS: readonly string[] = [
  "中国三北防护林对当地气温有什么影响？",
  "为什么过度放牧会加速荒漠化？",
  "What restoration strategies work in semi-arid China?",
  "帮我设计一个针对科尔沁沙地的防沙治沙方案",
];

function NebLogo() {
  return (
    <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-foreground text-[0.65rem] font-semibold tracking-tight text-background">
      NL
    </div>
  );
}

function TaskBadge({ taskType }: { taskType: ChatTurn["taskType"] }) {
  if (taskType !== "planning") return null;
  return (
    <span
      title="规划/方案类问题：允许从邻近案例迁移推理。※ 标记的为推理性内容；[N] 标记的为文献证据。"
      className="inline-flex items-center gap-1.5 rounded-full border border-border bg-accent/60 px-2 py-0.5 text-[0.7rem] font-medium tracking-wide text-foreground/70"
    >
      <span className="size-1.5 rounded-full bg-foreground/60" />
      规划模式
    </span>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-[0.95rem] leading-7 whitespace-pre-wrap text-foreground">
        {text}
      </div>
    </div>
  );
}

interface AssistantBubbleProps {
  taskType: ChatTurn["taskType"];
  answer: string;
  citations: readonly Citation[];
  isStreaming: boolean;
  error: string | null;
  onCitationClick: (n: number) => void;
}

function AssistantBubble({
  taskType,
  answer,
  citations,
  isStreaming,
  error,
  onCitationClick,
}: AssistantBubbleProps) {
  return (
    <div className="flex gap-3">
      <NebLogo />
      <div className="min-w-0 flex-1 space-y-2 pt-0.5">
        <div className="flex items-center gap-2">
          <span className="text-[0.85rem] font-medium text-foreground">
            NEBLab 助手
          </span>
          <TaskBadge taskType={taskType} />
        </div>
        {error ? (
          <p className="border-l-2 border-destructive bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {error}
          </p>
        ) : answer.length === 0 && isStreaming ? (
          <p className="text-sm text-muted-foreground italic">
            正在检索文献…
          </p>
        ) : (
          <AnswerMarkdown
            text={answer}
            citations={citations}
            isStreaming={isStreaming}
            onCitationClick={onCitationClick}
          />
        )}
      </div>
    </div>
  );
}

interface EmptyStateProps {
  onPick: (q: string) => void;
}

function EmptyState({ onPick }: EmptyStateProps) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 pb-12 text-center">
      <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
        北方生态屏障·研究助手
      </h1>
      <p className="mt-4 max-w-lg text-[0.95rem] leading-7 text-muted-foreground">
        基于 1810 篇 desertification / shelterbelt 中英文文献，
        每条回答都带 footnote 引用，可追溯到原文。
      </p>
      <div className="mt-10 grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
        {SAMPLE_QUESTIONS.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => onPick(q)}
            className="rounded-xl border border-border bg-card px-4 py-3 text-left text-[0.9rem] leading-6 text-foreground/80 transition-colors hover:border-foreground/30 hover:bg-accent hover:text-foreground"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

interface TurnViewProps {
  turn: ChatTurn;
  isStreaming: boolean;
  error: string | null;
  onCitationClick: (n: number) => void;
}

function TurnView({
  turn,
  isStreaming,
  error,
  onCitationClick,
}: TurnViewProps) {
  return (
    <div className="space-y-7">
      <UserBubble text={turn.question} />
      <AssistantBubble
        taskType={turn.taskType}
        answer={turn.answer}
        citations={turn.citations}
        isStreaming={isStreaming}
        error={error}
        onCitationClick={onCitationClick}
      />
    </div>
  );
}

export default function Home() {
  const [history, setHistory] = useState<ChatTurn[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [citationsOpen, setCitationsOpen] = useState<boolean>(true);
  const persistedRef = useRef<boolean>(false);
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);

  const {
    question,
    answer,
    citations,
    taskType,
    isStreaming,
    error,
    ask,
    reset,
  } = useStreamQuery();

  // Hydrate history once on mount.
  useEffect(() => {
    setHistory(loadHistory());
  }, []);

  // Persist a completed turn exactly once per stream.
  useEffect(() => {
    if (isStreaming || answer.length === 0 || persistedRef.current) return;
    persistedRef.current = true;
    const turn: ChatTurn = {
      id: pendingId ?? newTurnId(),
      question,
      answer,
      citations: [...citations],
      taskType,
      createdAt: Date.now(),
    };
    setHistory((prev) => {
      const next = [turn, ...prev];
      saveHistory(next);
      return next;
    });
    setActiveId(turn.id);
  }, [isStreaming, answer, citations, taskType, question, pendingId]);

  // Keep the latest assistant content in view while streaming.
  useEffect(() => {
    if (!isStreaming) return;
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [answer, isStreaming]);

  const activeTurn = useMemo<ChatTurn | null>(() => {
    if (pendingId !== null && question) {
      return {
        id: pendingId,
        question,
        answer,
        citations: [...citations],
        taskType,
        createdAt: Date.now(),
      };
    }
    if (activeId) {
      return history.find((t) => t.id === activeId) ?? null;
    }
    return null;
  }, [pendingId, activeId, question, answer, citations, taskType, history]);

  function startNewQuery(q: string): void {
    persistedRef.current = false;
    setActiveId(null);
    setPendingId(newTurnId());
    ask(q);
    setInput("");
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    if (isStreaming) return;
    const trimmed = input.trim();
    if (!trimmed) return;
    startNewQuery(trimmed);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>): void {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      e.currentTarget.form?.requestSubmit();
    }
  }

  function handleNewChat(): void {
    // Don't gate on isStreaming — clicking "新对话" mid-stream should
    // abort and reset (reset() closes the EventSource).
    persistedRef.current = false;
    setActiveId(null);
    setPendingId(null);
    reset();
    setInput("");
  }

  function handleSelect(id: string): void {
    // Same: switching to a history item mid-stream aborts the stream.
    persistedRef.current = false;
    setActiveId(id);
    setPendingId(null);
    reset();
  }

  function handleDelete(id: string): void {
    setHistory((prev) => {
      const next = prev.filter((t) => t.id !== id);
      saveHistory(next);
      return next;
    });
    if (activeId === id) {
      setActiveId(null);
      reset();
    }
  }

  const showEmpty = activeTurn === null;
  const sendDisabled = isStreaming || input.trim().length === 0;
  const activeCitations: readonly Citation[] = activeTurn?.citations ?? [];

  function handleCitationClick(_n: number): void {
    if (!citationsOpen) setCitationsOpen(true);
  }

  return (
    <div className="flex h-screen w-full">
      <Sidebar
        turns={history}
        activeId={activeId}
        onSelect={handleSelect}
        onNewChat={handleNewChat}
        onDelete={handleDelete}
      />

      <main className="relative flex flex-1 flex-col overflow-hidden">
        <div className="flex flex-1 flex-col overflow-y-auto">
          {showEmpty ? (
            <EmptyState onPick={startNewQuery} />
          ) : (
            <div className="mx-auto w-full max-w-3xl px-6 pt-10 pb-48 sm:px-10">
              {activeTurn && (
                <TurnView
                  turn={activeTurn}
                  isStreaming={isStreaming && pendingId !== null}
                  error={error}
                  onCitationClick={handleCitationClick}
                />
              )}
              <div ref={scrollAnchorRef} />
            </div>
          )}
        </div>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-center bg-gradient-to-t from-background via-background/80 to-transparent pt-8 pb-6">
          <form
            onSubmit={handleSubmit}
            className="pointer-events-auto mx-6 w-full max-w-3xl"
          >
            <div className="relative rounded-2xl border border-border bg-card shadow-[0_2px_24px_-12px_rgba(0,0,0,0.12)] focus-within:border-foreground/30">
              <Textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="问点什么…  Enter 发送, Shift+Enter 换行"
                rows={1}
                className="min-h-[56px] resize-none border-0 bg-transparent px-5 py-4 pr-14 text-[0.95rem] leading-6 shadow-none focus-visible:ring-0"
                disabled={isStreaming}
              />
              <Button
                type="submit"
                size="icon"
                variant="default"
                disabled={sendDisabled}
                className="absolute right-2.5 bottom-2.5 size-9 rounded-lg"
                aria-label="发送"
              >
                <ArrowUp className="size-4" />
              </Button>
            </div>
            <p className="mt-2 px-2 text-center text-[0.7rem] text-muted-foreground">
              回答可能不准确。引用准确率 63.9%（86 题 eval, judge=DeepSeek）。
            </p>
          </form>
        </div>
      </main>

      <CitationsPanel
        citations={activeCitations}
        open={citationsOpen}
        onToggle={() => setCitationsOpen((v) => !v)}
      />
    </div>
  );
}
