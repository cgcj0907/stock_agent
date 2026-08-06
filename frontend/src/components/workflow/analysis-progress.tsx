"use client";

import * as React from "react";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { AgentIcon } from "@/components/agent-icon";
import { findAgent } from "@/lib/agents/catalog";
import type { StepStatus, WorkflowStep } from "@/lib/workflows/catalog";
import { cn } from "@/lib/utils";

const STEP_STATE: Record<
  StepStatus,
  { dot: string; chip: string }
> = {
  done: {
    dot: "bg-emerald-500",
    chip: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  },
  running: {
    dot: "bg-emerald-400 animate-pulse",
    chip: "border-emerald-300 bg-emerald-100 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-200",
  },
  failed: {
    dot: "bg-red-500",
    chip: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
  },
  skipped: {
    dot: "bg-amber-500",
    chip: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  },
  pending: {
    dot: "bg-muted-foreground/30",
    chip: "border-border bg-muted/40 text-muted-foreground",
  },
};

/**
 * 分析进度条：总体进度百分比 + 当前执行模块 + 各步骤状态标签，
 * 让用户在 1–2 分钟的分析过程中有明确感知。
 *
 * `connected`：SSE 长链接是否已建立（后端实时推送 session step 进度）。
 */
export function AnalysisProgress({
  steps,
  statuses,
  running,
  connected,
  className,
}: {
  steps: WorkflowStep[];
  statuses: Record<string, StepStatus>;
  running: boolean;
  connected?: boolean;
  className?: string;
}) {
  const total = steps.length;
  const doneCount = steps.filter(
    (s) => statuses[s.id] === "done" || statuses[s.id] === "skipped"
  ).length;
  const runningStep = steps.find((s) => statuses[s.id] === "running");
  const failed = steps.some((s) => statuses[s.id] === "failed");
  const pct = total ? Math.round((doneCount / total) * 100) : 0;
  const runningAgent = runningStep
    ? findAgent(runningStep.agent)
    : undefined;

  return (
    <div
      className={cn(
        "rounded-2xl border bg-card p-4 shadow-sm",
        className
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          {running ? (
            <>
              <Loader2 className="size-4 animate-spin text-emerald-600 dark:text-emerald-400" />
              正在分析…
            </>
          ) : failed ? (
            <>
              <XCircle className="size-4 text-red-500" />
              分析未完成
            </>
          ) : (
            <>
              <CheckCircle2 className="size-4 text-emerald-600 dark:text-emerald-400" />
              分析完成
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {running && (
            <span
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium",
                connected
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                  : "border-border bg-muted/40 text-muted-foreground"
              )}
              title={
                connected
                  ? "已建立 SSE 长链接，后端实时推送步骤进度"
                  : "正在建立实时进度连接…"
              }
            >
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  connected ? "bg-emerald-500 animate-pulse" : "bg-muted-foreground/40"
                )}
              />
              {connected ? "实时更新中" : "连接中…"}
            </span>
          )}
          <div className="flex items-baseline gap-2">
            <span className="text-xs text-muted-foreground tabular-nums">
              已完成 {doneCount}/{total}
            </span>
            <span className="text-sm font-bold tabular-nums text-emerald-600 dark:text-emerald-400">
              {pct}%
            </span>
          </div>
        </div>
      </div>

      <div className="mt-2.5 h-2 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            failed
              ? "bg-gradient-to-r from-red-400 to-red-500"
              : "bg-gradient-to-r from-emerald-500 to-teal-500"
          )}
          style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
        />
      </div>

      <div className="mt-2 min-h-[1.25rem] text-xs text-muted-foreground">
        {running && runningAgent ? (
          <>
            正在执行：
            <span className="inline-flex items-center gap-1 font-medium text-foreground">
              <AgentIcon icon={runningAgent.icon} className="size-3.5" />
              {runningAgent.name}
            </span>
          </>
        ) : running ? (
          "正在初始化…"
        ) : failed ? (
          "部分模块执行失败，请查看下方结果与错误信息"
        ) : (
          "全部模块执行完毕"
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {steps.map((s) => {
          const st = statuses[s.id] ?? "pending";
          const agent = findAgent(s.agent);
          const state = STEP_STATE[st] ?? STEP_STATE.pending;
          return (
            <span
              key={s.id}
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                state.chip
              )}
            >
              <span className={cn("size-1.5 rounded-full", state.dot)} />
              <AgentIcon icon={agent?.icon} className="size-3.5" />
              {agent?.name ?? s.id}
            </span>
          );
        })}
      </div>
    </div>
  );
}
