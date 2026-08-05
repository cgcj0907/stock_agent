"use client";

import * as React from "react";
import { ExternalLink } from "lucide-react";
import { stockSourceLinks } from "@/lib/stock-links";
import { cn } from "@/lib/utils";

/**
 * 可点击的数据来源链接（东方财富 / 新浪财经 / 巨潮资讯）。
 * 代码不合法时返回 null。
 */
export function SourceLinks({
  code,
  className,
}: {
  code: string;
  className?: string;
}) {
  const links = stockSourceLinks(code);
  if (links.length === 0) return null;
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]",
        className
      )}
    >
      <span className="text-muted-foreground">数据来源：</span>
      {links.map((l, i) => (
        <React.Fragment key={l.label}>
          {i > 0 && <span className="text-muted-foreground/40">·</span>}
          <a
            href={l.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-0.5 text-emerald-600 underline decoration-emerald-600/40 underline-offset-2 hover:text-emerald-700 hover:decoration-emerald-600 dark:text-emerald-400 dark:hover:text-emerald-300"
          >
            {l.label}
            <ExternalLink className="size-2.5" />
          </a>
        </React.Fragment>
      ))}
    </div>
  );
}
