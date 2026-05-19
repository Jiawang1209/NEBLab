"use client";

import { ChevronRight, BookOpen, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Citation } from "@/lib/types";

interface CitationsPanelProps {
  citations: readonly Citation[];
  open: boolean;
  onToggle: () => void;
  /** Sprint 3 v0.3: set of citation numbers whose chunk_text is
   * currently expanded in-card. Owned by the page so the [N] click
   * handler in the answer can also toggle entries here. */
  expandedCites: ReadonlySet<number>;
  onToggleExpand: (n: number) => void;
}

export function CitationsPanel({
  citations,
  open,
  onToggle,
  expandedCites,
  onToggleExpand,
}: CitationsPanelProps) {
  if (!open) {
    return (
      <aside className="flex w-11 shrink-0 flex-col items-center border-l border-border bg-sidebar py-3">
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onToggle}
          aria-label="展开引用面板"
          title="展开引用"
        >
          <BookOpen />
        </Button>
        {citations.length > 0 && (
          <span className="mt-2 rounded-full bg-foreground/10 px-1.5 py-0.5 text-[0.65rem] font-medium tabular-nums text-foreground/70">
            {citations.length}
          </span>
        )}
      </aside>
    );
  }

  return (
    <aside className="flex w-[320px] shrink-0 flex-col border-l border-border bg-sidebar">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <BookOpen className="size-3.5 text-muted-foreground" />
          <h3 className="text-[0.85rem] font-semibold text-foreground">
            引用 · {citations.length}
          </h3>
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onToggle}
          aria-label="折叠引用面板"
          title="折叠"
        >
          <ChevronRight />
        </Button>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {citations.length === 0 ? (
          <p className="py-8 text-center text-[0.75rem] text-muted-foreground">
            尚未检索文献
          </p>
        ) : (
          <ol className="space-y-3 text-[0.85rem] leading-6">
            {citations.map((c) => {
              const href = c.openalex_id
                ? `https://openalex.org/${c.openalex_id}`
                : null;
              const hasChunkText = !!c.chunk_text;
              const isExpanded = expandedCites.has(c.number);
              return (
                <li
                  key={c.number}
                  id={`cite-${c.number}`}
                  className="scroll-mt-4 rounded-md p-2 -mx-2 transition-colors target:bg-accent"
                >
                  <div className="flex gap-2.5">
                    <span className="w-5 shrink-0 text-right tabular-nums text-muted-foreground">
                      {c.number}
                    </span>
                    <span className="flex-1">
                      {href ? (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-foreground decoration-foreground/20 underline-offset-4 hover:underline"
                        >
                          {c.title}
                        </a>
                      ) : (
                        <span className="text-foreground">{c.title}</span>
                      )}
                      {c.openalex_id && (
                        <span className="mt-1 block font-mono text-[0.7rem] tracking-tight text-muted-foreground">
                          {c.openalex_id}
                        </span>
                      )}
                      {hasChunkText && (
                        <>
                          <button
                            type="button"
                            onClick={() => onToggleExpand(c.number)}
                            className="mt-2 flex items-center gap-1 text-[0.7rem] text-muted-foreground hover:text-foreground"
                            aria-expanded={isExpanded}
                            aria-controls={`cite-${c.number}-chunk`}
                          >
                            {isExpanded ? (
                              <ChevronUp className="size-3" />
                            ) : (
                              <ChevronDown className="size-3" />
                            )}
                            {isExpanded ? "隐藏 chunk 正文" : "显示 chunk 正文"}
                          </button>
                          {isExpanded && (
                            <div
                              id={`cite-${c.number}-chunk`}
                              className="mt-2 whitespace-pre-wrap border-t border-border/40 pt-2 text-[0.8rem] leading-6 text-muted-foreground"
                            >
                              {c.chunk_text}
                            </div>
                          )}
                        </>
                      )}
                    </span>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </aside>
  );
}
