export interface Citation {
  number: number;
  doc_id: number;
  openalex_id: string | null;
  title: string;
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
