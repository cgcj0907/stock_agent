"use client";

import * as React from "react";
import { ChevronDown } from "lucide-react";

/**
 * 可折叠区块：默认折叠「次要细节」（参数/校准、深度风险分析等），
 * 让长卡首屏只保留结论 + 关键数字 + 风险，减少瀑布流列高失衡。
 */
export function Collapsible({
  title,
  defaultOpen = false,
  children,
}: {
  title: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div className="flex flex-col gap-1.5 border-t border-border/40 pt-2.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 rounded-md px-1 py-0.5 text-left transition-colors hover:bg-muted"
      >
        <span className="flex min-w-0 items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-primary/70">
          {title}
        </span>
        <ChevronDown
          className={`size-3.5 shrink-0 text-muted-foreground transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>
      {open && <div className="flex flex-col gap-2">{children}</div>}
    </div>
  );
}
