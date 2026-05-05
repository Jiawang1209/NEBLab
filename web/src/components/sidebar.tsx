"use client";

import { Plus, MessageSquare, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ChatTurn } from "@/lib/types";

interface SidebarProps {
  turns: readonly ChatTurn[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onDelete: (id: string) => void;
}

interface Group {
  label: string;
  turns: readonly ChatTurn[];
}

function groupByDay(turns: readonly ChatTurn[]): Group[] {
  const now = Date.now();
  const startOfToday = new Date(now).setHours(0, 0, 0, 0);
  const startOfYesterday = startOfToday - 24 * 60 * 60 * 1000;
  const startOfWeek = startOfToday - 7 * 24 * 60 * 60 * 1000;

  const today: ChatTurn[] = [];
  const yesterday: ChatTurn[] = [];
  const earlierWeek: ChatTurn[] = [];
  const older: ChatTurn[] = [];

  for (const turn of turns) {
    if (turn.createdAt >= startOfToday) today.push(turn);
    else if (turn.createdAt >= startOfYesterday) yesterday.push(turn);
    else if (turn.createdAt >= startOfWeek) earlierWeek.push(turn);
    else older.push(turn);
  }

  return [
    { label: "今天", turns: today },
    { label: "昨天", turns: yesterday },
    { label: "本周", turns: earlierWeek },
    { label: "更早", turns: older },
  ].filter((g) => g.turns.length > 0);
}

export function Sidebar({
  turns,
  activeId,
  onSelect,
  onNewChat,
  onDelete,
}: SidebarProps) {
  const groups = groupByDay(turns);

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
            没有历史记录
          </p>
        ) : (
          groups.map((g) => (
            <div key={g.label} className="mt-3 first:mt-1">
              <p className="px-3 pt-2 pb-1 text-[0.65rem] font-medium tracking-wider text-muted-foreground/80 uppercase">
                {g.label}
              </p>
              <ul className="space-y-0.5">
                {g.turns.map((t) => (
                  <li key={t.id}>
                    <button
                      type="button"
                      onClick={() => onSelect(t.id)}
                      className={cn(
                        "group/turn flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[0.85rem] leading-5 transition-colors",
                        activeId === t.id
                          ? "bg-accent text-foreground"
                          : "text-foreground/80 hover:bg-accent/60",
                      )}
                    >
                      <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" />
                      <span className="flex-1 truncate">{t.question}</span>
                      <span
                        role="button"
                        tabIndex={0}
                        onClick={(e) => {
                          e.stopPropagation();
                          onDelete(t.id);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            e.stopPropagation();
                            onDelete(t.id);
                          }
                        }}
                        className="hidden size-5 shrink-0 items-center justify-center rounded text-muted-foreground hover:bg-destructive/10 hover:text-destructive group-hover/turn:flex"
                        aria-label="删除"
                      >
                        <Trash2 className="size-3" />
                      </span>
                    </button>
                  </li>
                ))}
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
