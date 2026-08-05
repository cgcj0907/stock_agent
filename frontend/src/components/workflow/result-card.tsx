"use client";

import {
  CheckCircle2,
  Clock3,
  Loader2,
  Paperclip,
  SkipForward,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
} from "@/components/ui/card";
import { LlmResultView } from "@/components/workflow/llm-result-view";
import {
  isMarkdownText,
  MarkdownValue,
} from "@/components/workflow/markdown-value";
import { ValueView } from "@/components/workflow/value-view";
import { LinkedText } from "@/lib/linkify";
import type { AgentInfo } from "@/lib/agents/catalog";
import type { ModuleResultView } from "@/hooks/use-workflow-run";

const STATUS_BADGE: Record<
  string,
  { label: string; className: string; icon: React.ComponentType<{ className?: string }> }
> = {
  done: {
    label: "已完成",
    className:
      "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
    icon: CheckCircle2,
  },
  running: {
    label: "运行中",
    className:
      "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
    icon: Loader2,
  },
  failed: {
    label: "失败",
    className:
      "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
    icon: XCircle,
  },
  skipped: {
    label: "已跳过",
    className:
      "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
    icon: SkipForward,
  },
  pending: {
    label: "待运行",
    className: "border-border bg-muted/50 text-muted-foreground",
    icon: Clock3,
  },
};

const MAX_OUTPUTS = 8;
const MAX_EVIDENCE = 4;

/** 输出字段名含这些关键词时，按「LLM 结构化结果」占满整行渲染（JSON → TS 数据）。 */
const LLM_KEY_RE = /llm|qualitative|red_team/i;

/** 需要占满整行渲染的值：LLM 结构化结果，或含 Markdown 语法的长文本。 */
function isFullWidthValue(v: unknown, key: string): boolean {
  return (
    LLM_KEY_RE.test(key) ||
    (typeof v === "string" && isMarkdownText(v))
  );
}

export function ResultCard({
  agent,
  result,
}: {
  agent?: AgentInfo;
  result: ModuleResultView;
}) {
  const badge = STATUS_BADGE[result.status] ?? STATUS_BADGE.pending;
  const StatusIcon = badge.icon;
  const entries = Object.entries(result.outputs ?? {});
  const score = result.score;
  const showMoreOutputs = entries.length > MAX_OUTPUTS;
  const showMoreEvidence = result.evidence.length > MAX_EVIDENCE;

  return (
    <Card className="rounded-2xl transition-shadow hover:shadow-sm">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <div className="flex items-center gap-2.5">
          <span className="text-xl leading-none">
            {agent?.emoji ?? "🤖"}
          </span>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold">
                {agent?.name ?? result.module}
              </span>
              {agent && (
                <Badge variant="secondary" className="rounded-md px-1.5 text-[10px]">
                  {agent.code}
                </Badge>
              )}
            </div>
            <span className="font-mono text-[10px] text-muted-foreground">
              {result.module}
            </span>
          </div>
        </div>
        <Badge
          variant="outline"
          className={`gap-1 rounded-md ${badge.className}`}
        >
          <StatusIcon
            className={`size-3 ${result.status === "running" ? "animate-spin" : ""}`}
          />
          {badge.label}
        </Badge>
      </CardHeader>

      <CardContent className="flex flex-col gap-3">
        {score != null && (
          <div className="flex items-center gap-2.5">
            <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-emerald-500"
                style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
              />
            </div>
            <span className="text-sm font-semibold tabular-nums">
              {Math.round(score)}
            </span>
            <span className="text-xs text-muted-foreground">评分</span>
          </div>
        )}

        {entries.length > 0 && (
          <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 rounded-xl bg-muted/40 p-3">
            {entries.slice(0, MAX_OUTPUTS).map(([k, v]) => {
              const fullWidth = isFullWidthValue(v, k);
              return (
                <div
                  key={k}
                  className={fullWidth ? "col-span-2 min-w-0" : "min-w-0"}
                >
                  <div className="truncate text-[10px] text-muted-foreground">
                    {k}
                  </div>
                  <div
                    className={
                      fullWidth
                        ? "mt-1"
                        : "mt-0.5 break-words text-xs leading-5"
                    }
                  >
                    {LLM_KEY_RE.test(k) ? (
                      <LlmResultView value={v} />
                    ) : (
                      <ValueView value={v} label={k} />
                    )}
                  </div>
                </div>
              );
            })}
            {showMoreOutputs && (
              <div className="col-span-2 text-[10px] text-muted-foreground">
                另有 {entries.length - MAX_OUTPUTS} 个字段未展示
              </div>
            )}
          </div>
        )}

        {result.evidence.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              证据 / 数据来源
            </div>
            <ul className="flex flex-col gap-1">
              {result.evidence.slice(0, MAX_EVIDENCE).map((ev, i) => (
                <li
                  key={i}
                  className="flex items-start gap-1.5 text-xs leading-5 text-muted-foreground"
                >
                  <Paperclip className="mt-1 size-3 shrink-0" />
                  <span className="min-w-0 break-words">
                    <LinkedText text={ev} />
                  </span>
                </li>
              ))}
              {showMoreEvidence && (
                <li className="text-[10px] text-muted-foreground">
                  另有 {result.evidence.length - MAX_EVIDENCE} 条证据未展示
                </li>
              )}
            </ul>
          </div>
        )}

        {result.llm_explanation &&
          (isMarkdownText(result.llm_explanation) ? (
            <MarkdownValue
              text={result.llm_explanation}
              label="LLM 解释"
            />
          ) : (
            <p className="text-xs italic leading-5 text-muted-foreground">
              {result.llm_explanation}
            </p>
          ))}

      </CardContent>
    </Card>
  );
}
