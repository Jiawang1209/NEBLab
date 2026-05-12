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
import type { ApiMessage, ChatSession, ChatTurn, Citation } from "@/lib/types";
import { useStreamQuery } from "@/hooks/use-stream-query";
import {
  loadSessions,
  newSessionId,
  newTurnId,
  saveSessions,
} from "@/lib/history";

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
      <p className="mt-2 text-[0.8rem] text-muted-foreground">
        现已支持多轮对话 — 可以追问、展开、对比。
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
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [pendingTurnId, setPendingTurnId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [citationsOpen, setCitationsOpen] = useState<boolean>(true);
  const persistedRef = useRef<boolean>(false);
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);

  const {
    answer,
    citations,
    taskType,
    isStreaming,
    error,
    ask,
    reset,
  } = useStreamQuery();

  // Hydrate sessions once on mount.
  useEffect(() => {
    setSessions(loadSessions());
  }, []);

  // Persist a completed turn back into its session. Fires once when
  // the stream ends with content; the persistedRef prevents a re-fire
  // when the page re-renders for any other reason.
  useEffect(() => {
    if (isStreaming || answer.length === 0) return;
    if (!pendingTurnId || !activeSessionId) return;
    if (persistedRef.current) return;
    persistedRef.current = true;

    setSessions((prev) => {
      const next = prev.map((s) => {
        if (s.id !== activeSessionId) return s;
        const turns = s.turns.map((t) =>
          t.id === pendingTurnId
            ? {
                ...t,
                answer,
                citations: [...citations],
                taskType,
              }
            : t,
        );
        return { ...s, turns, updatedAt: Date.now() };
      });
      saveSessions(next);
      return next;
    });
    setPendingTurnId(null);
  }, [isStreaming, answer, citations, taskType, pendingTurnId, activeSessionId]);

  // Auto-scroll while streaming.
  useEffect(() => {
    if (!isStreaming) return;
    scrollAnchorRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [answer, isStreaming]);

  const activeSession = useMemo<ChatSession | null>(
    () => sessions.find((s) => s.id === activeSessionId) ?? null,
    [sessions, activeSessionId],
  );

  /**
   * The "effective" last turn — what the citations panel binds to.
   * If the last turn is the one being streamed, overlay live state
   * (answer / citations / taskType) so the panel stays in sync.
   */
  const effectiveLastTurn = useMemo<ChatTurn | null>(() => {
    if (!activeSession || activeSession.turns.length === 0) return null;
    const last = activeSession.turns[activeSession.turns.length - 1];
    if (last.id === pendingTurnId) {
      return {
        ...last,
        answer,
        citations: [...citations],
        taskType,
      };
    }
    return last;
  }, [activeSession, pendingTurnId, answer, citations, taskType]);

  function startNewQuery(question: string): void {
    const trimmed = question.trim();
    if (!trimmed || isStreaming) return;

    persistedRef.current = false;
    const turnId = newTurnId();
    setPendingTurnId(turnId);

    const newTurn: ChatTurn = {
      id: turnId,
      question: trimmed,
      answer: "",
      citations: [],
      taskType: "qa",
      createdAt: Date.now(),
    };

    let messages: ApiMessage[] = [];

    if (activeSession === null) {
      // First turn of a brand-new session.
      const session: ChatSession = {
        id: newSessionId(),
        turns: [newTurn],
        createdAt: Date.now(),
        updatedAt: Date.now(),
      };
      setSessions((prev) => {
        const next = [session, ...prev];
        saveSessions(next);
        return next;
      });
      setActiveSessionId(session.id);
      messages = [{ role: "user", content: trimmed }];
    } else {
      // Follow-up — fold the prior turns into the message list.
      messages = activeSession.turns.flatMap((t) => [
        { role: "user", content: t.question } satisfies ApiMessage,
        { role: "assistant", content: t.answer } satisfies ApiMessage,
      ]);
      messages.push({ role: "user", content: trimmed });

      setSessions((prev) => {
        const next = prev.map((s) =>
          s.id === activeSession.id
            ? { ...s, turns: [...s.turns, newTurn], updatedAt: Date.now() }
            : s,
        );
        saveSessions(next);
        return next;
      });
    }

    void ask(messages);
    setInput("");
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    startNewQuery(input);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>): void {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      e.currentTarget.form?.requestSubmit();
    }
  }

  function handleNewChat(): void {
    // Aborts any in-flight stream + clears pending state.
    persistedRef.current = false;
    setPendingTurnId(null);
    setActiveSessionId(null);
    reset();
    setInput("");
  }

  function handleSelectSession(id: string): void {
    persistedRef.current = false;
    setPendingTurnId(null);
    setActiveSessionId(id);
    reset();
  }

  function handleDeleteSession(id: string): void {
    setSessions((prev) => {
      const next = prev.filter((s) => s.id !== id);
      saveSessions(next);
      return next;
    });
    if (activeSessionId === id) {
      setActiveSessionId(null);
      setPendingTurnId(null);
      reset();
    }
  }

  function handleCitationClick(_n: number): void {
    if (!citationsOpen) setCitationsOpen(true);
  }

  const showEmpty = activeSession === null || activeSession.turns.length === 0;
  const sendDisabled = isStreaming || input.trim().length === 0;
  const activeCitations: readonly Citation[] = effectiveLastTurn?.citations ?? [];

  return (
    <div className="flex h-screen w-full">
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelect={handleSelectSession}
        onNewChat={handleNewChat}
        onDelete={handleDeleteSession}
      />

      <main className="relative flex flex-1 flex-col overflow-hidden">
        <div className="flex flex-1 flex-col overflow-y-auto">
          {showEmpty ? (
            <EmptyState onPick={startNewQuery} />
          ) : (
            <div className="mx-auto w-full max-w-3xl space-y-12 px-6 pt-10 pb-48 sm:px-10">
              {activeSession?.turns.map((turn) => {
                const isPending = pendingTurnId === turn.id;
                const renderTurn: ChatTurn = isPending
                  ? {
                      ...turn,
                      answer,
                      citations: [...citations],
                      taskType,
                    }
                  : turn;
                return (
                  <TurnView
                    key={turn.id}
                    turn={renderTurn}
                    isStreaming={isPending && isStreaming}
                    error={isPending ? error : null}
                    onCitationClick={handleCitationClick}
                  />
                );
              })}
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
                placeholder={
                  activeSession
                    ? "继续追问…  Enter 发送, Shift+Enter 换行"
                    : "问点什么…  Enter 发送, Shift+Enter 换行"
                }
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
