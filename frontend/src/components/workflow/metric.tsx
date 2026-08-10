import * as React from "react";

export type MetricTone = "default" | "warn" | "good" | "bad";

/**
 * 关键指标卡：模块输出（module-outputs）/ 估值引擎（m4-outputs）统一复用，
 * 统一圆角 / 间距 / 字号节奏，避免两份 Metric 视觉漂移。
 */
export function Metric({
  label,
  value,
  tone = "default",
  title,
}: {
  label: string;
  value: React.ReactNode;
  tone?: MetricTone;
  title?: string;
}) {
  const toneCls =
    tone === "warn"
      ? "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-300"
      : tone === "good"
        ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300"
        : tone === "bad"
          ? "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-300"
          : "border-border/60 bg-muted/30 text-foreground";
  return (
    <div title={title} className={`rounded-lg border px-2.5 py-2 ${toneCls}`}>
      <div className="text-[11px] font-semibold tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 min-w-0 break-words text-sm font-bold tabular-nums">
        {value}
      </div>
    </div>
  );
}
