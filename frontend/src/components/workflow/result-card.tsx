"use client";

import * as React from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock3,
  Loader2,
  SkipForward,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
} from "@/components/ui/card";
import { AgentIcon } from "@/components/agent-icon";
import { LlmResultView } from "@/components/workflow/llm-result-view";
import {
  isMarkdownText,
  MarkdownValue,
} from "@/components/workflow/markdown-value";
import { ValueView } from "@/components/workflow/value-view";
import { fieldLabel } from "@/lib/labels";
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

/** 默认折叠展示的字段条数，超出后可展开。 */
const MAX_OUTPUTS = 8;

/** 内部契约字段（如下游 handoff），只供模块间传递，不展示给用户。 */
const HIDDEN_OUTPUT_KEYS = new Set(["handoff"]);

/** 输出字段名含这些关键词时，按「LLM 结构化结果」占满整行渲染（JSON → TS 数据）。 */
const LLM_KEY_RE = /llm|qualitative|red_team|reasons|business_model|references/i;

/** 需要占满整行渲染的值：嵌套对象/数组，LLM 结构化结果，或含 Markdown 语法的长文本。 */
function isFullWidthValue(v: unknown, key: string): boolean {
  if (v !== null && typeof v === "object") {
    // 空数组或空对象不强制全宽
    if (Array.isArray(v) && v.length === 0) return false;
    if (!Array.isArray(v) && Object.keys(v as Record<string, unknown>).length === 0) return false;
    return true;
  }
  return (
    LLM_KEY_RE.test(key) ||
    (typeof v === "string" && (isMarkdownText(v) || v.length > 30))
  );
}

function ExpandToggle({
  expanded,
  label,
  onClick,
}: {
  expanded: boolean;
  label: string;
  onClick: () => void;
}) {
  const Icon = expanded ? ChevronUp : ChevronDown;
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 rounded-md px-1 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
    >
      <Icon className="size-3" />
      {expanded ? "收起" : label}
    </button>
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
  const entries = Object.entries(result.outputs ?? {}).filter(
    ([k]) => !HIDDEN_OUTPUT_KEYS.has(k),
  );
  const score = result.score;
  const [showAllOutputs, setShowAllOutputs] = React.useState(false);

  const visibleOutputs = showAllOutputs
    ? entries
    : entries.slice(0, MAX_OUTPUTS);

  return (
    <Card
      size="sm"
      className="flex h-full flex-col rounded-2xl transition-shadow hover:shadow-sm"
    >
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-1">
        <div className="flex items-center gap-2.5">
          <AgentIcon icon={agent?.icon} className="size-5" />
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
        <div className="flex shrink-0 items-center gap-1.5">
          {result.meta?.degraded && (
            <Badge
              variant="outline"
              className="gap-1 rounded-md border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300"
            >
              降级
            </Badge>
          )}
          <Badge
            variant="outline"
            className={`gap-1 rounded-md ${badge.className}`}
          >
            <StatusIcon
              className={`size-3 ${result.status === "running" ? "animate-spin" : ""}`}
            />
            {badge.label}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-2.5">
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
          <div className="flex flex-col gap-3">
            {/* 1. 常规短字段：紧凑网格 */}
            {visibleOutputs.filter(([k, v]) => !isFullWidthValue(v, k) && k !== "signals" && k !== "risks" && k !== "risk_items").length > 0 && (
              <div className="grid grid-cols-2 gap-x-3 gap-y-3 pt-1">
                {visibleOutputs
                  .filter(([k, v]) => !isFullWidthValue(v, k) && k !== "signals" && k !== "risks" && k !== "risk_items")
                  .map(([k, v]) => (
                    <div key={k} className="min-w-0">
                      <div className="truncate text-[10px] font-semibold tracking-wide text-muted-foreground">
                        {fieldLabel(k)}
                      </div>
                      <div className="mt-0.5 break-words text-xs leading-5 font-medium text-foreground/80">
                        {LLM_KEY_RE.test(k) ? (
                          <LlmResultView value={v} />
                        ) : (
                          <ValueView value={v} label={fieldLabel(k)} />
                        )}
                      </div>
                    </div>
                  ))}
              </div>
            )}

            {/* 2. 风险信号列表：特别的展示区块 */}
            {visibleOutputs
              .filter(([k]) => k === "signals" || k === "risks" || k === "risk_items")
              .map(([k, v]) => (
                <div key={k} className="flex flex-col gap-1.5 border-t border-border/40 pt-3">
                  <div className="truncate text-[10px] font-semibold tracking-wide text-rose-600/80 uppercase">
                    {fieldLabel(k)}
                  </div>
                  <div className="break-words text-sm leading-relaxed text-foreground/90">
                    <ValueView value={v} label={fieldLabel(k)} />
                  </div>
                </div>
              ))}

            {/* 3. 长文本/复杂结构：使用分割线，不嵌套卡片 */}
            {visibleOutputs
              .filter(([k, v]) => isFullWidthValue(v, k) && k !== "signals" && k !== "risks" && k !== "risk_items")
              .map(([k, v]) => (
                <div
                  key={k}
                  className="flex flex-col gap-1.5 border-t border-border/40 pt-3"
                >
                  <div className="truncate text-[10px] font-semibold tracking-wide text-primary/70 uppercase">
                    {fieldLabel(k)}
                  </div>
                  <div className="break-words text-sm leading-relaxed text-foreground/90">
                    {LLM_KEY_RE.test(k) ? (
                      <LlmResultView value={v} />
                    ) : (
                      <ValueView value={v} label={fieldLabel(k)} />
                    )}
                  </div>
                </div>
              ))}

            {entries.length > MAX_OUTPUTS && (
              <div className="flex justify-end pt-1">
                <ExpandToggle
                  expanded={showAllOutputs}
                  label={`展开全部 ${entries.length} 个字段`}
                  onClick={() => setShowAllOutputs((v) => !v)}
                />
              </div>
            )}
          </div>
        )}

        {result.llm_explanation &&
          (isMarkdownText(result.llm_explanation) ? (
            <MarkdownValue text={result.llm_explanation} label="LLM 解释" />
          ) : (
            <p className="text-xs italic leading-5 text-muted-foreground">
              {result.llm_explanation}
            </p>
          ))}

        {result.evidence && result.evidence.length > 0 && (
          <div className="flex flex-col gap-1 border-t border-border/40 pt-2.5">
            <div className="text-[10px] font-semibold tracking-wide text-muted-foreground">
              分析依据
            </div>
            <ul className="flex flex-col gap-1">
              {result.evidence.slice(0, 8).map((e, i) => {
                const warn = /异常|降级|失败|⚠️|跳过|缺失/.test(e);
                return (
                  <li
                    key={i}
                    className={
                      warn
                        ? "text-[11px] leading-5 text-amber-600 dark:text-amber-400"
                        : "text-[11px] leading-5 text-muted-foreground"
                    }
                  >
                    {e}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
