import type { ChatSession, ChatTurn, Citation } from "@/lib/types";

const STORAGE_KEY = "neblab.sessions.v2";
const MAX_SESSIONS = 100;

function isCitation(value: unknown): value is Citation {
  if (typeof value !== "object" || value === null) return false;
  const c = value as Record<string, unknown>;
  return (
    typeof c.number === "number" &&
    typeof c.doc_id === "number" &&
    typeof c.title === "string" &&
    (c.openalex_id === null || typeof c.openalex_id === "string") &&
    (c.chunk_text === undefined || typeof c.chunk_text === "string")
  );
}

function isChatTurn(value: unknown): value is ChatTurn {
  if (typeof value !== "object" || value === null) return false;
  const t = value as Record<string, unknown>;
  return (
    typeof t.id === "string" &&
    typeof t.question === "string" &&
    typeof t.answer === "string" &&
    typeof t.createdAt === "number" &&
    Array.isArray(t.citations) &&
    t.citations.every(isCitation)
  );
}

function isChatSession(value: unknown): value is ChatSession {
  if (typeof value !== "object" || value === null) return false;
  const s = value as Record<string, unknown>;
  return (
    typeof s.id === "string" &&
    typeof s.createdAt === "number" &&
    typeof s.updatedAt === "number" &&
    Array.isArray(s.turns) &&
    s.turns.every(isChatTurn)
  );
}

export function loadSessions(): ChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isChatSession);
  } catch {
    return [];
  }
}

export function saveSessions(sessions: readonly ChatSession[]): void {
  if (typeof window === "undefined") return;
  try {
    const trimmed = sessions.slice(0, MAX_SESSIONS);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // localStorage may be full or disabled — degrade silently.
  }
}

export function newSessionId(): string {
  return `sess_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

export function newTurnId(): string {
  return `turn_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

/** Sidebar label for a session — use the first user question, truncated. */
export function sessionLabel(session: ChatSession, max: number = 50): string {
  const first = session.turns[0]?.question ?? "(空对话)";
  if (first.length <= max) return first;
  return first.slice(0, max - 1) + "…";
}
