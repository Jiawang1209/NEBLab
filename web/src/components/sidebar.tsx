"use client";

import { Plus, MessageSquare, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ChatSession } from "@/lib/types";
import { sessionLabel } from "@/lib/history";

interface SidebarProps {
  sessions: readonly ChatSession[];
  activeSessionId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onDelete: (id: string) => void;
}

interface Group {
  label: string;
  sessions: readonly ChatSession[];
}

function groupByDay(sessions: readonly ChatSession[]): Group[] {
  const now = Date.now();
  const startOfToday = new Date(now).setHours(0, 0, 0, 0);
  const startOfYesterday = startOfToday - 24 * 60 * 60 * 1000;
  const startOfWeek = startOfToday - 7 * 24 * 60 * 60 * 1000;

  const today: ChatSession[] = [];
  const yesterday: ChatSession[] = [];
  const earlierWeek: ChatSession[] = [];
  const older: ChatSession[] = [];

  // Sort by updatedAt desc so newest first within each bucket.
  const sorted = [...sessions].sort((a, b) => b.updatedAt - a.updatedAt);
  for (const s of sorted) {
    if (s.updatedAt >= startOfToday) today.push(s);
    else if (s.updatedAt >= startOfYesterday) yesterday.push(s);
    else if (s.updatedAt >= startOfWeek) earlierWeek.push(s);
    else older.push(s);
  }

  return [
    { label: "今天", sessions: today },
    { label: "昨天", sessions: yesterday },
    { label: "本周", sessions: earlierWeek },
    { label: "更早", sessions: older },
  ].filter((g) => g.sessions.length > 0);
}

export function Sidebar({
  sessions,
  activeSessionId,
  onSelect,
  onNewChat,
  onDelete,
}: SidebarProps) {
  const groups = groupByDay(sessions);

  return (
    <aside className="flex h-screen w-[260px] shrink-0 flex-col border-r border-border bg-sidebar">
      <div className="px-4 pt-5 pb-3">
        <div className="flex items-center gap-2 px-2">
          <div className="size-7 rounded-md bg-foreground text-[0.7rem] font-semibold tracking-tight text-background flex items-center justify-center">
            NL
          </div>
          <div className="leading-tight">
            <div className="text-[0.85rem] font-semibold text-foreground">
              NEBLab
            </div>
            <div className="text-[0.7rem] text-muted-foreground">知识助手</div>
          </div>
        </div>
      </div>

      <div className="px-3 pb-2">
        <Button
          onClick={onNewChat}
          variant="outline"
          size="sm"
          className="w-full justify-start font-normal"
        >
          <Plus />
          新对话
        </Button>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 pb-4">
        {groups.length === 0 ? (
          <p className="px-3 py-6 text-center text-[0.75rem] text-muted-foreground">
            没有历史对话
          </p>
        ) : (
          groups.map((g) => (
            <div key={g.label} className="mt-3 first:mt-1">
              <p className="px-3 pt-2 pb-1 text-[0.65rem] font-medium tracking-wider text-muted-foreground/80 uppercase">
                {g.label}
              </p>
              <ul className="space-y-0.5">
                {g.sessions.map((s) => {
                  const turnCount = s.turns.length;
                  return (
                    <li key={s.id}>
                      <button
                        type="button"
                        onClick={() => onSelect(s.id)}
                        className={cn(
                          "group/turn flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[0.85rem] leading-5 transition-colors",
                          activeSessionId === s.id
                            ? "bg-accent text-foreground"
                            : "text-foreground/80 hover:bg-accent/60",
                        )}
                      >
                        <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" />
                        <span className="flex-1 truncate">
                          {sessionLabel(s)}
                        </span>
                        {turnCount > 1 && (
                          <span className="shrink-0 rounded bg-foreground/10 px-1.5 py-0.5 text-[0.65rem] font-medium tabular-nums text-muted-foreground">
                            {turnCount}
                          </span>
                        )}
                        <span
                          role="button"
                          tabIndex={0}
                          onClick={(e) => {
                            e.stopPropagation();
                            onDelete(s.id);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              e.stopPropagation();
                              onDelete(s.id);
                            }
                          }}
                          className="hidden size-5 shrink-0 items-center justify-center rounded text-muted-foreground hover:bg-destructive/10 hover:text-destructive group-hover/turn:flex"
                          aria-label="删除"
                        >
                          <Trash2 className="size-3" />
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))
        )}
      </nav>

      <div className="border-t border-border px-4 py-3 text-[0.7rem] text-muted-foreground">
        v1 · 1810 篇文献 · 引用准确率 63.9%
      </div>
    </aside>
  );
}
