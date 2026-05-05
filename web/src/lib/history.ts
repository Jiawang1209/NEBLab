import type { ChatTurn, Citation } from "@/lib/types";

const STORAGE_KEY = "neblab.history.v1";
const MAX_TURNS = 100;

function isCitation(value: unknown): value is Citation {
  if (typeof value !== "object" || value === null) return false;
  const c = value as Record<string, unknown>;
  return (
    typeof c.number === "number" &&
    typeof c.doc_id === "number" &&
    typeof c.title === "string" &&
    (c.openalex_id === null || typeof c.openalex_id === "string")
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

export function loadHistory(): ChatTurn[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isChatTurn);
  } catch {
    return [];
  }
}

export function saveHistory(turns: readonly ChatTurn[]): void {
  if (typeof window === "undefined") return;
  try {
    const trimmed = turns.slice(0, MAX_TURNS);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // localStorage may be full or disabled — degrade silently.
  }
}

export function newTurnId(): string {
  return `turn_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}
