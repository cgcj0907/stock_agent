"use client";

import * as React from "react";
import { ChevronDown } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * 判断一段文本是否含 Markdown 语法（## 标题 / **加粗** / - 或 1. 列表），
 * 用于把 LLM 输出等 md 文本转成可折叠的富文本渲染。
 */
export function isMarkdownText(text: string): boolean {
  if (!text || typeof text !== "string") return false;
  return (
    text.includes("**") ||
    text.includes("##") ||
    /(^|\n)\s*[-*] /.test(text) ||
    /(^|\n)\s*\d+\. /.test(text)
  );
}

/**
 * 可折叠的 Markdown 渲染块：默认折叠成一行摘要，展开后渲染完整 Markdown
 * （不出现原始 ## / ** 符号）。
 */
export function MarkdownValue({
  text,
  label,
  defaultOpen = false,
}: {
  text: string;
  label?: string;
  defaultOpen?: boolean;
}) {
  return (
    <details
      open={defaultOpen}
      className="group overflow-hidden rounded-lg border bg-card"
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground [&::-webkit-details-marker]:hidden">
        <span className="truncate">{label ?? "Markdown 详情"}</span>
        <ChevronDown className="size-3.5 shrink-0 transition-transform group-open:rotate-180" />
      </summary>
      <div className="prose prose-sm max-w-none border-t px-3 py-2.5 text-xs leading-5 dark:prose-invert prose-headings:mb-1.5 prose-headings:mt-2.5 prose-headings:text-[13px] prose-p:my-1.5 prose-li:my-0.5 prose-strong:font-semibold prose-a:text-emerald-600 prose-a:no-underline hover:prose-a:underline">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>
    </details>
  );
}
