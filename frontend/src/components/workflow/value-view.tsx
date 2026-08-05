"use client";

import * as React from "react";
import { LinkedText } from "@/lib/linkify";

function isPrimitive(v: unknown): boolean {
  return (
    v === null ||
    v === undefined ||
    typeof v === "string" ||
    typeof v === "number" ||
    typeof v === "boolean"
  );
}

function fmtNumber(n: number): string {
  return Number.isFinite(n) ? String(n) : "—";
}

function fmtPrimitive(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return fmtNumber(v);
  if (typeof v === "boolean") return v ? "是" : "否";
  return String(v);
}

/**
 * 把模块输出里的任意值渲染成可读形式：
 * - null / undefined / 空数组 / 空对象 → —
 * - 布尔 → 是/否
 * - 纯原始值数组 → 用「、」拼接（如 ["a","b"] → a、b）
 * - 纯原始值对象 → 用「 · 」拼接（如 {"low":1,"high":2} → low 1 · high 2）
 * - 嵌套结构 → 逐行 key: value 缩进列表，字符串自动识别链接
 */
export function ValueView({ value }: { value: unknown }) {
  // 原始值
  if (isPrimitive(value)) {
    const text = fmtPrimitive(value);
    if (typeof value === "string") {
      return text ? <LinkedText text={text} /> : <Dash />;
    }
    return <span className="tabular-nums">{text}</span>;
  }

  // 数组
  if (Array.isArray(value)) {
    if (value.length === 0) return <Dash />;
    if (value.every(isPrimitive)) {
      return (
        <span className="break-words">
          {value.map((item, i) => (
            <React.Fragment key={i}>
              {i > 0 && <span className="text-muted-foreground">、</span>}
              {typeof item === "string" ? (
                <LinkedText text={item} />
              ) : (
                <span className="tabular-nums">{fmtPrimitive(item)}</span>
              )}
            </React.Fragment>
          ))}
        </span>
      );
    }
    return (
      <ul className="flex flex-col gap-0.5">
        {value.map((item, i) => (
          <li key={i} className="flex items-start gap-1.5">
            <span className="mt-[5px] size-1 shrink-0 rounded-full bg-muted-foreground/50" />
            <span className="min-w-0 flex-1">
              <ValueView value={item} />
            </span>
          </li>
        ))}
      </ul>
    );
  }

  // 对象
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <Dash />;
    if (entries.every(([, v]) => isPrimitive(v))) {
      return (
        <span className="break-words">
          {entries.map(([k, v], i) => (
            <React.Fragment key={k}>
              {i > 0 && (
                <span className="mx-1 text-muted-foreground/60">·</span>
              )}
              <span className="text-muted-foreground">{k}</span>{" "}
              {typeof v === "string" ? (
                <LinkedText text={v} />
              ) : (
                <span className="tabular-nums">{fmtPrimitive(v)}</span>
              )}
            </React.Fragment>
          ))}
        </span>
      );
    }
    return (
      <div className="flex flex-col gap-0.5">
        {entries.map(([k, v]) => (
          <div key={k} className="flex items-baseline gap-1.5">
            <span className="shrink-0 text-muted-foreground">{k}</span>
            <span className="min-w-0 flex-1">
              <ValueView value={v} />
            </span>
          </div>
        ))}
      </div>
    );
  }

  return <span>{String(value)}</span>;
}

function Dash() {
  return <span className="text-muted-foreground">—</span>;
}
