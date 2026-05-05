"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import type { Citation } from "@/lib/types";

interface AnswerMarkdownProps {
  text: string;
  citations: readonly Citation[];
  isStreaming: boolean;
  /** Called when a citation chip is clicked. The page wires this to open
   * the right citations panel before the anchor scroll fires, otherwise
   * the target #cite-N node is unmounted and the jump silently no-ops. */
  onCitationClick?: (number: number) => void;
}

/**
 * Pre-process the answer before handing it to ReactMarkdown:
 *
 *  - `[N]` → `<sup data-cite="N">[N]</sup>` so we can render an inline
 *    citation chip via the `sup` component override.
 *  - `※` (Sprint 5c inference marker) → `<span data-marker="infer">※</span>`
 *    so the styling lives in CSS, not threaded through JSX.
 *
 * Both transforms operate on the raw markdown source. They embed inline
 * HTML, which `rehype-raw` then turns back into nodes the `components`
 * map can intercept. Without `rehype-raw` react-markdown would strip
 * the tags as a security default.
 */
function preprocess(text: string): string {
  return text
    .replace(/\[(\d+)\]/g, (_, n: string) => `<sup data-cite="${n}">[${n}]</sup>`)
    .replace(/※/g, '<span data-marker="infer">※</span>');
}

function buildComponents(
  byNumber: Map<number, Citation>,
  onCitationClick?: (number: number) => void,
): Components {
  return {
    p: ({ children }) => (
      <p className="my-3 leading-[1.85] text-foreground first:mt-0 last:mb-0">
        {children}
      </p>
    ),
    h1: ({ children }) => (
      <h1 className="mt-7 mb-3 text-xl font-semibold tracking-tight text-foreground first:mt-0">
        {children}
      </h1>
    ),
    h2: ({ children }) => (
      <h2 className="mt-7 mb-3 text-lg font-semibold tracking-tight text-foreground first:mt-0">
        {children}
      </h2>
    ),
    h3: ({ children }) => (
      <h3 className="mt-5 mb-2 text-base font-semibold text-foreground first:mt-0">
        {children}
      </h3>
    ),
    ul: ({ children }) => (
      <ul className="my-3 ml-1 space-y-1.5 [&>li]:relative [&>li]:pl-5 [&>li]:before:absolute [&>li]:before:left-0 [&>li]:before:top-[0.7em] [&>li]:before:size-1 [&>li]:before:rounded-full [&>li]:before:bg-foreground/40">
        {children}
      </ul>
    ),
    ol: ({ children }) => (
      <ol className="my-3 ml-6 list-decimal space-y-1.5 marker:text-muted-foreground">
        {children}
      </ol>
    ),
    li: ({ children }) => (
      <li className="leading-[1.85] text-foreground">{children}</li>
    ),
    blockquote: ({ children }) => (
      <blockquote className="my-4 border-l-2 border-border pl-4 text-muted-foreground italic">
        {children}
      </blockquote>
    ),
    code: ({ children, className }) => {
      const isBlock = typeof className === "string" && className.startsWith("language-");
      if (isBlock) {
        return (
          <pre className="my-4 overflow-x-auto rounded-lg bg-secondary p-4 text-[0.85rem] leading-6 text-foreground">
            <code>{children}</code>
          </pre>
        );
      }
      return (
        <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[0.85em] text-foreground">
          {children}
        </code>
      );
    },
    strong: ({ children }) => (
      <strong className="font-semibold text-foreground">{children}</strong>
    ),
    em: ({ children }) => <em className="italic">{children}</em>,
    a: ({ children, href }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-foreground decoration-foreground/30 underline underline-offset-4 hover:decoration-foreground"
      >
        {children}
      </a>
    ),
    table: ({ children }) => (
      <div className="my-4 overflow-x-auto">
        <table className="w-full border-collapse text-[0.9rem]">{children}</table>
      </div>
    ),
    thead: ({ children }) => (
      <thead className="border-b border-border">{children}</thead>
    ),
    th: ({ children }) => (
      <th className="px-3 py-2 text-left font-semibold text-foreground">{children}</th>
    ),
    td: ({ children }) => (
      <td className="border-b border-border px-3 py-2 text-foreground/90">{children}</td>
    ),
    hr: () => <hr className="my-6 border-border" />,
    sup: (props) => {
      // Citation chip — emitted by preprocess() above. Renders as an
      // inline anchor that scrolls to the matching footnote at the
      // bottom of the answer card.
      const dataCite = (props as { "data-cite"?: string })["data-cite"];
      if (!dataCite) return <sup>{props.children}</sup>;
      const num = Number(dataCite);
      const citation = byNumber.get(num);
      const title = citation?.title ?? "未找到对应文献";
      return (
        <a
          href={`#cite-${num}`}
          title={title}
          onClick={(e) => {
            if (!onCitationClick) return;
            e.preventDefault();
            onCitationClick(num);
            // Defer the scroll so the panel can mount the target node first.
            requestAnimationFrame(() => {
              document
                .getElementById(`cite-${num}`)
                ?.scrollIntoView({ behavior: "smooth", block: "center" });
            });
          }}
          className="mx-[1px] inline-block align-super text-[0.65em] font-medium tabular-nums text-foreground/70 underline-offset-2 hover:text-foreground hover:underline"
        >
          [{num}]
        </a>
      );
    },
    span: (props) => {
      const marker = (props as { "data-marker"?: string })["data-marker"];
      if (marker === "infer") {
        return (
          <span
            title="基于推理或类比，非文献直接结论"
            className="ml-1 align-super text-[0.65em] font-medium text-muted-foreground/70"
          >
            {props.children}
          </span>
        );
      }
      return <span {...props} />;
    },
  };
}

export function AnswerMarkdown({
  text,
  citations,
  isStreaming,
  onCitationClick,
}: AnswerMarkdownProps) {
  const byNumber = new Map<number, Citation>(
    citations.map((c) => [c.number, c]),
  );
  const components = buildComponents(byNumber, onCitationClick);
  const processed = preprocess(text);

  return (
    <div
      className={
        isStreaming && text.length > 0
          ? "[&>*:last-child]:after:ml-[2px] [&>*:last-child]:after:inline-block [&>*:last-child]:after:h-[1.05em] [&>*:last-child]:after:w-[2px] [&>*:last-child]:after:translate-y-[2px] [&>*:last-child]:after:bg-foreground/70 [&>*:last-child]:after:align-text-bottom [&>*:last-child]:after:content-[''] [&>*:last-child]:after:animate-pulse"
          : ""
      }
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={components}
      >
        {processed}
      </ReactMarkdown>
    </div>
  );
}
