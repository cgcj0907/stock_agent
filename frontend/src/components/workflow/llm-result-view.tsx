"use client";

import * as React from "react";
import { ExternalLink } from "lucide-react";
import { ValueView } from "@/components/workflow/value-view";
import { tryParseJson } from "@/lib/json";
import { fieldLabel } from "@/lib/labels";

/** 参考文章：形如 {title?, url?} 或纯 URL 字符串。 */
function ReferenceLinks({ value }: { value: unknown }) {
  const items = Array.isArray(value) ? value : [value];
  const links = items
    .map((item) => {
      if (typeof item === "string" && /^https?:\/\//i.test(item.trim())) {
        return { title: item.trim(), url: item.trim() };
      }
      if (item && typeof item === "object" && !Array.isArray(item)) {
        const rec = item as Record<string, unknown>;
        const url = String(rec.url ?? rec.link ?? rec.href ?? "").trim();
        if (/^https?:\/\//i.test(url)) {
          return { title: String(rec.title ?? rec.name ?? url), url };
        }
      }
      return null;
    })
    .filter((x): x is { title: string; url: string } => x !== null);

  if (links.length === 0) return <ValueView value={value} />;
  return (
    <ul className="flex flex-col gap-1">
      {links.map((l, i) => (
        <li key={i} className="flex items-start gap-1.5">
          <ExternalLink className="mt-0.5 size-3 shrink-0 text-muted-foreground" />
          <a
            href={l.url}
            target="_blank"
            rel="noopener noreferrer"
            className="min-w-0 break-all text-emerald-600 underline decoration-emerald-600/40 underline-offset-2 hover:text-emerald-700 hover:decoration-emerald-600 dark:text-emerald-400 dark:hover:text-emerald-300"
          >
            {l.title}
          </a>
        </li>
      ))}
    </ul>
  );
}

/**
 * 把 LLM 结构化输出（dict 或 JSON 文本）渲染成「字段名 + 值」的整齐列表；
 * references 字段特殊渲染为可点击的参考文章链接。
 * 非对象 / 解析失败时回退到 ValueView 原样展示。
 */
export function LlmResultView({ value }: { value: unknown }) {
  let data: Record<string, unknown> | null = null;
  if (value && typeof value === "object" && !Array.isArray(value)) {
    data = value as Record<string, unknown>;
  } else if (typeof value === "string") {
    const parsed = tryParseJson(value);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      data = parsed as Record<string, unknown>;
    }
  }

  if (!data || Object.keys(data).length === 0) {
    return <ValueView value={value} />;
  }

  return (
    <div className="flex flex-col gap-1.5">
      {Object.entries(data).map(([k, v]) => (
        <div key={k} className="flex flex-col gap-0.5">
          <span className="text-[10px] font-semibold text-muted-foreground">
            {fieldLabel(k)}
          </span>
          <div className="text-xs leading-5">
            {k === "references" || k === "sources" || k === "links" ? (
              <ReferenceLinks value={v} />
            ) : (
              <ValueView value={v} label={fieldLabel(k)} />
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
