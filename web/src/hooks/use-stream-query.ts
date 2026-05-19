"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiMessage, Citation, TaskType } from "@/lib/types";

interface StreamState {
  answer: string;
  citations: readonly Citation[];
  taskType: TaskType;
  isStreaming: boolean;
  error: string | null;
}

const initialState: StreamState = {
  answer: "",
  citations: [],
  taskType: "qa",
  isStreaming: false,
  error: null,
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

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
        typeof (c as { title?: unknown }).title === "string" &&
        ((c as { chunk_text?: unknown }).chunk_text === undefined ||
          typeof (c as { chunk_text?: unknown }).chunk_text === "string"),
    );
  } catch {
    return [];
  }
}

interface SSEEvent {
  event: string;
  data: string;
}

/**
 * SSE frames are separated by blank lines. Within a frame, ``event:``
 * and ``data:`` lines describe the event. We need a manual parser
 * because EventSource doesn't support POST — and Sprint 5e's multi-turn
 * payload is too large for a query string.
 */
async function* parseSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<SSEEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        if (buffer.trim()) yield* drainFrame(buffer);
        return;
      }
      buffer += decoder.decode(value, { stream: true });
      let cut = findFrameEnd(buffer);
      while (cut !== -1) {
        const frame = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        yield* drainFrame(frame);
        cut = findFrameEnd(buffer);
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function findFrameEnd(buffer: string): number {
  // SSE allows \n\n or \r\n\r\n; check both.
  const a = buffer.indexOf("\n\n");
  const b = buffer.indexOf("\r\n\r\n");
  if (a === -1) return b;
  if (b === -1) return a;
  return Math.min(a, b);
}

function* drainFrame(frame: string): Generator<SSEEvent> {
  let event = "message";
  const dataLines: string[] = [];
  for (const rawLine of frame.split(/\r?\n/)) {
    if (!rawLine || rawLine.startsWith(":")) continue; // comment
    const colon = rawLine.indexOf(":");
    if (colon === -1) continue;
    const field = rawLine.slice(0, colon);
    const valStart = rawLine[colon + 1] === " " ? colon + 2 : colon + 1;
    const value = rawLine.slice(valStart);
    if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }
  if (dataLines.length || event !== "message") {
    yield { event, data: dataLines.join("\n") };
  }
}

export function useStreamQuery() {
  const [state, setState] = useState<StreamState>(initialState);
  const abortRef = useRef<AbortController | null>(null);

  // Abort an in-flight stream when the component unmounts.
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const ask = useCallback(async (messages: ApiMessage[]): Promise<void> => {
    if (!messages.length) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setState({ ...initialState, isStreaming: true });

    try {
      const resp = await fetch(`${API_BASE}/query/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({ messages, top_k: 7 }),
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) {
        setState((s) => ({
          ...s,
          isStreaming: false,
          error: `后端返回 ${resp.status}`,
        }));
        return;
      }

      for await (const ev of parseSSE(resp.body)) {
        if (controller.signal.aborted) return;
        if (ev.event === "task_type") {
          const value: TaskType =
            ev.data === "planning"
              ? "planning"
              : ev.data === "meta"
                ? "meta"
                : "qa";
          setState((s) => ({ ...s, taskType: value }));
        } else if (ev.event === "citations") {
          const next = parseCitations(ev.data);
          setState((s) => ({ ...s, citations: next }));
        } else if (ev.event === "delta") {
          setState((s) => ({ ...s, answer: s.answer + ev.data }));
        } else if (ev.event === "done") {
          setState((s) => ({ ...s, isStreaming: false }));
        }
      }
    } catch (err: unknown) {
      // AbortError is expected when reset() / new chat fires mid-stream.
      const name = (err as { name?: string }).name;
      if (name === "AbortError") return;
      setState((s) => ({
        ...s,
        isStreaming: false,
        error:
          s.error ??
          "连接后端失败：请确认 FastAPI (`make dev`) 是否在 :8000 运行",
      }));
    }
  }, []);

  const reset = useCallback((): void => {
    abortRef.current?.abort();
    abortRef.current = null;
    setState(initialState);
  }, []);

  return { ...state, ask, reset };
}
