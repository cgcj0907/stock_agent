"use client";

import * as React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock3,
  FileText,
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
import { ModuleOutputs, MODULE_OUTPUT_COMPONENTS } from "@/components/workflow/module-outputs";
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

/** 分析依据里命中这些关键词的条目按告警样式展示。 */
function isWarnEvidence(e: string): boolean {
  return /异常|降级|失败|⚠️|跳过|缺失/.test(e);
}

/** 按分数给评分条配色：高分绿 / 中分琥珀 / 低分红。 */
function scoreTone(score: number): { bar: string; text: string } {
  if (score >= 60) return { bar: "bg-emerald-500", text: "text-emerald-600 dark:text-emerald-400" };
  if (score >= 40) return { bar: "bg-amber-500", text: "text-amber-600 dark:text-amber-400" };
  return { bar: "bg-red-500", text: "text-red-600 dark:text-red-400" };
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
  const tone = score != null ? scoreTone(score) : null;
  const hasModuleView = result.module in MODULE_OUTPUT_COMPONENTS;
  const [showAllOutputs, setShowAllOutputs] = React.useState(false);
  // 分析依据默认折叠，卡片更清爽；有告警条目时在折叠头用角标提示
  const [showEvidence, setShowEvidence] = React.useState(false);

  const visibleOutputs = showAllOutputs
    ? entries
    : entries.slice(0, MAX_OUTPUTS);

  const warnEvidenceCount =
    result.evidence?.filter(isWarnEvidence).length ?? 0;

  const shortFields = visibleOutputs.filter(
    ([k, v]) => !isFullWidthValue(v, k) && k !== "signals" && k !== "risks" && k !== "risk_items",
  );
  const riskFields = visibleOutputs.filter(
    ([k]) => k === "signals" || k === "risks" || k === "risk_items",
  );
  const longFields = visibleOutputs.filter(
    ([k, v]) => isFullWidthValue(v, k) && k !== "signals" && k !== "risks" && k !== "risk_items",
  );

  return (
    <Card
      size="sm"
      className="flex flex-col rounded-2xl transition-shadow hover:shadow-sm"
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
                className={`h-full rounded-full ${tone?.bar ?? "bg-emerald-500"}`}
                style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
              />
            </div>
            <span className={`text-sm font-semibold tabular-nums ${tone?.text ?? ""}`}>
              {Math.round(score)}
            </span>
            <span className="text-xs text-muted-foreground">评分</span>
          </div>
        )}

        {hasModuleView ? (
          <ModuleOutputs module={result.module} outputs={result.outputs ?? {}} />
        ) : entries.length > 0 ? (
          <div className="flex flex-col gap-3">
            {/* 1. 常规短字段：紧凑网格 */}
            {shortFields.length > 0 && (
              <div className="grid grid-cols-2 gap-x-3 gap-y-3 pt-1">
                {shortFields.map(([k, v]) => (
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
            {riskFields.map(([k, v]) => (
              <div key={k} className="flex flex-col gap-1.5 border-t border-border/40 pt-3">
                <div className="flex items-center gap-1.5 text-rose-600/80 uppercase">
                  <AlertTriangle className="size-3.5 shrink-0" />
                  <span className="truncate text-[10px] font-semibold tracking-wide">
                    {fieldLabel(k)}
                  </span>
                </div>
                <div className="break-words text-sm leading-relaxed text-foreground/90">
                  <ValueView value={v} label={fieldLabel(k)} />
                </div>
              </div>
            ))}

            {/* 3. 长文本/复杂结构：使用分割线，不嵌套卡片 */}
            {longFields.map(([k, v]) => (
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
        ) : null}

        {result.llm_explanation &&
          (isMarkdownText(result.llm_explanation) ? (
            <MarkdownValue text={result.llm_explanation} label="LLM 解释" />
          ) : (
            <p className="text-xs italic leading-5 text-muted-foreground">
              {result.llm_explanation}
            </p>
          ))}

        {result.evidence && result.evidence.length > 0 && (
          <div className="flex flex-col gap-1.5 border-t border-border/40 pt-2.5">
            <button
              type="button"
              onClick={() => setShowEvidence((v) => !v)}
              className="flex w-full items-center justify-between gap-2 rounded-md px-1 py-0.5 text-left transition-colors hover:bg-muted"
            >
              <span className="flex min-w-0 items-center gap-1.5">
                <FileText className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="text-[10px] font-semibold tracking-wide text-muted-foreground">
                  分析依据
                </span>
                <span className="text-[10px] text-muted-foreground/70">
                  {result.evidence.length}
                </span>
                {warnEvidenceCount > 0 && (
                  <Badge
                    variant="outline"
                    className="gap-0.5 rounded-md border-amber-200 bg-amber-50 px-1 py-0 text-[9px] text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300"
                  >
                    <AlertTriangle className="size-2.5" />
                    {warnEvidenceCount}
                  </Badge>
                )}
              </span>
              {showEvidence ? (
                <ChevronUp className="size-3.5 shrink-0 text-muted-foreground" />
              ) : (
                <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
              )}
            </button>
            {showEvidence && (
              <ul className="flex flex-col gap-1 px-1 pb-0.5">
                {result.evidence.slice(0, 8).map((e, i) => (
                  <li
                    key={i}
                    className={
                      isWarnEvidence(e)
                        ? "text-[11px] leading-5 text-amber-600 dark:text-amber-400"
                        : "text-[11px] leading-5 text-muted-foreground"
                    }
                  >
                    {e}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
