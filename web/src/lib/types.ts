export interface Citation {
  number: number;
  doc_id: number;
  openalex_id: string | null;
  title: string;
}

export type TaskType = "qa" | "planning";

export interface ChatTurn {
  id: string;
  question: string;
  answer: string;
  citations: Citation[];
  taskType: TaskType;
  createdAt: number;
}
