export interface Citation {
  number: number;
  doc_id: number;
  openalex_id: string | null;
  title: string;
  /** Sprint 3 v0.3: full chunk text for inline preview. Optional so
   * legacy sessions persisted in localStorage before v0.3 (which
   * carry only title) degrade to the v0.2 card layout without errors. */
  chunk_text?: string;
}

export type TaskType = "qa" | "planning" | "meta";

export type Role = "user" | "assistant";

export interface ChatTurn {
  id: string;
  question: string;
  answer: string;
  citations: Citation[];
  taskType: TaskType;
  createdAt: number;
}

/** Sprint 5e: a multi-turn conversation. The sidebar lists Sessions
 * (labelled by the first user message); selecting one loads all of its
 * turns into the main view. New questions append to the active session
 * and are sent to the backend along with the full prior history. */
export interface ChatSession {
  id: string;
  turns: ChatTurn[];
  createdAt: number;
  updatedAt: number;
}

export interface ApiMessage {
  role: Role;
  content: string;
}
