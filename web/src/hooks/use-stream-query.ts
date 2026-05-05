"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Citation, TaskType } from "@/lib/types";

interface StreamState {
  question: string;
  answer: string;
  citations: readonly Citation[];
  taskType: TaskType;
  isStreaming: boolean;
  error: string | null;
}

const initialState: StreamState = {
  question: "",
  answer: "",
  citations: [],
  taskType: "qa",
  isStreaming: false,
  error: null,
};

function parseCitations(raw: string): readonly Citation[] {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (c: unknown): c is Citation =>
        typeof c === "object" &&
        c !== null &&
        typeof (c as { number?: unknown }).number === "number" &&
        typeof (c as { doc_id?: unknown }).doc_id === "number" &&
        typeof (c as { title?: unknown }).title === "string",
    );
  } catch {
    return [];
  }
}

export function useStreamQuery() {
  const [state, setState] = useState<StreamState>(initialState);
  const sourceRef = useRef<EventSource | null>(null);
  // Tracks whether the server signalled normal completion. EventSource fires
  // an `error` event on every disconnect — including the normal close after
  // `done` — so we use this flag to distinguish benign close from real failure.
  const completedRef = useRef<boolean>(false);
  // Set when the consumer aborts the stream voluntarily (reset / new chat).
  // The follow-on `error` event from the manual close should not surface as
  // a connection-failed message.
  const abortedRef = useRef<boolean>(false);

  // Close the connection if the consumer unmounts mid-stream.
  useEffect(() => {
    return () => sourceRef.current?.close();
  }, []);

  const ask = useCallback((query: string, topK: number = 7): void => {
    const trimmed = query.trim();
    if (!trimmed) return;

    sourceRef.current?.close();
    completedRef.current = false;
    abortedRef.current = false;
    setState({ ...initialState, question: trimmed, isStreaming: true });

    const params = new URLSearchParams({
      query: trimmed,
      top_k: String(topK),
    });
    // Next.js dev's rewrite proxy buffers SSE chunks, so we hit FastAPI
    // directly. Backend has CORS allowlist for localhost:3000.
    const apiBase =
      process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
    const es = new EventSource(`${apiBase}/query/stream?${params.toString()}`);
    sourceRef.current = es;

    es.addEventListener("task_type", (event: MessageEvent<string>) => {
      const value = event.data === "planning" ? "planning" : "qa";
      setState((s) => ({ ...s, taskType: value }));
    });

    es.addEventListener("citations", (event: MessageEvent<string>) => {
      const next = parseCitations(event.data);
      setState((s) => ({ ...s, citations: next }));
    });

    es.addEventListener("delta", (event: MessageEvent<string>) => {
      setState((s) => ({ ...s, answer: s.answer + event.data }));
    });

    es.addEventListener("done", () => {
      completedRef.current = true;
      es.close();
      setState((s) => ({ ...s, isStreaming: false }));
    });

    es.addEventListener("error", () => {
      // benign closes: server signalled `done`, or consumer aborted via reset()
      if (completedRef.current || abortedRef.current) return;
      es.close();
      setState((s) => ({
        ...s,
        isStreaming: false,
        error: s.error ?? "连接后端失败：请确认 FastAPI (`make dev`) 是否在 :8000 运行",
      }));
    });
  }, []);

  const reset = useCallback((): void => {
    abortedRef.current = true;
    sourceRef.current?.close();
    completedRef.current = false;
    setState(initialState);
  }, []);

  return { ...state, ask, reset };
}
