"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Citation } from "@/lib/types";

interface StreamState {
  question: string;
  answer: string;
  citations: readonly Citation[];
  isStreaming: boolean;
  error: string | null;
}

const initialState: StreamState = {
  question: "",
  answer: "",
  citations: [],
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

  // Close the connection if the consumer unmounts mid-stream.
  useEffect(() => {
    return () => sourceRef.current?.close();
  }, []);

  const ask = useCallback((query: string, topK: number = 7): void => {
    const trimmed = query.trim();
    if (!trimmed) return;

    sourceRef.current?.close();
    setState({ ...initialState, question: trimmed, isStreaming: true });

    const params = new URLSearchParams({
      query: trimmed,
      top_k: String(topK),
    });
    const es = new EventSource(`/api/query/stream?${params.toString()}`);
    sourceRef.current = es;

    es.addEventListener("citations", (event: MessageEvent<string>) => {
      const next = parseCitations(event.data);
      setState((s) => ({ ...s, citations: next }));
    });

    es.addEventListener("delta", (event: MessageEvent<string>) => {
      setState((s) => ({ ...s, answer: s.answer + event.data }));
    });

    es.addEventListener("done", () => {
      es.close();
      setState((s) => ({ ...s, isStreaming: false }));
    });

    // EventSource fires 'error' both on transport failures and on normal
    // server close. We treat any error AFTER 'done' as benign (already closed
    // above); otherwise surface it.
    es.addEventListener("error", () => {
      const wasStreaming = es.readyState !== EventSource.CLOSED;
      es.close();
      setState((s) => ({
        ...s,
        isStreaming: false,
        error: wasStreaming && s.isStreaming ? "连接中断，请重试" : s.error,
      }));
    });
  }, []);

  const reset = useCallback((): void => {
    sourceRef.current?.close();
    setState(initialState);
  }, []);

  return { ...state, ask, reset };
}
