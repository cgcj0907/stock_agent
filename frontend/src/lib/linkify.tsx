"use client";

import * as React from "react";

/** 匹配文本中的 http(s) 链接（含中文/括号等边界处理）。 */
const URL_RE = /(https?:\/\/[^\s<>"'）)\]】]+)/g;

const LINK_CLS =
  "break-all text-emerald-600 underline decoration-emerald-600/40 underline-offset-2 hover:text-emerald-700 hover:decoration-emerald-600 dark:text-emerald-400 dark:hover:text-emerald-300";

/**
 * 渲染一段文本，自动把其中的 http(s) 链接变成可点击的 <a>。
 * 没有链接时原样输出，避免无谓的 React 节点开销。
 */
export function LinkedText({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  const parts = text.split(URL_RE);
  const hasLink = parts.some((p) => /^https?:\/\//i.test(p));
  if (!hasLink) {
    return <span className={className}>{text}</span>;
  }
  return (
    <span className={className}>
      {parts.map((part, i) =>
        /^https?:\/\//i.test(part) ? (
          <a
            key={i}
            href={part}
            target="_blank"
            rel="noopener noreferrer"
            className={LINK_CLS}
          >
            {part}
          </a>
        ) : (
          <React.Fragment key={i}>{part}</React.Fragment>
        )
      )}
    </span>
  );
}
