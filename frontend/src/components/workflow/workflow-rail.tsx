"use client";

import * as React from "react";
import { Loader2, TriangleAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { MEMO_ANCHORS } from "@/components/workflow/memo-card";
import { findAgent } from "@/lib/agents/catalog";
import type { ModuleResultView } from "@/hooks/use-workflow-run";
import type { StepStatus, WorkflowInfo } from "@/lib/workflows/catalog";
import { cn } from "@/lib/utils";


const ANCHOR_BADGE: Record<string, string> = {
  "memo-summary": "✓",
  "memo-module-results": "表",
  "memo-m2": "M2",
  "memo-m4": "M4",
  "memo-m11": "M11",
};

const STATUS_DOT: Record<StepStatus, string> = {
  pending: "bg-muted-foreground/40",
  running: "bg-emerald-500 animate-pulse",
  done: "bg-emerald-500",
  failed: "bg-red-500",
  skipped: "bg-amber-500",
};

const SEVERITY_BADGE: Record<string, { label: string; cls: string }> = {
  critical: {
    label: "风险",
    cls: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
  },
  high: {
    label: "高风险",
    cls: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
  },
  medium: {
    label: "警告",
    cls: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  },
  warn: {
    label: "警告",
    cls: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  },
  low: {
    label: "提示",
    cls: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  },
  info: {
    label: "提示",
    cls: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  },
};

function severityRank(v: string): number {
  if (v === "critical") return 5;
  if (v === "high") return 4;
  if (v === "medium" || v === "warn") return 3;
  if (v === "low") return 2;
  return 1;
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function pct(v: unknown): string | null {
  const n = num(v);
  return n == null ? null : `${Math.round(n * 100)}%`;
}

function isObj(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function fmtNum(v: number | null | undefined): string {
  return v == null ? "—" : String(v);
}

function KvLine({ k, v, vCls }: { k: string; v: React.ReactNode; vCls?: string }) {
  return (
    <div className="flex items-baseline justify-between border-b border-dashed border-border/60 py-1.5 text-xs last:border-0">
      <span className="text-muted-foreground">{k}</span>
      <span className={cn("font-semibold tabular-nums", vCls)}>{v}</span>
    </div>
  );
}

export function WorkflowRail({
  workflow,
  statuses,
  running,
  sessionId,
  results,
  showResults,
  hasResults,
}: {
  workflow: WorkflowInfo;
  statuses: Record<string, StepStatus>;
  running: boolean;
  sessionId: string | null;
  results: Record<string, ModuleResultView>;
  showResults: boolean;
  hasResults: boolean;
}) {
  const doneCount = workflow.steps.filter(
    (s) => statuses[s.id] === "done" || statuses[s.id] === "skipped"
  ).length;
  const progress = workflow.steps.length
    ? Math.round((doneCount / workflow.steps.length) * 100)
    : 0;
  const currentStep = workflow.steps.find((s) => statuses[s.id] === "running");
  const currentAgent = currentStep ? findAgent(currentStep.agent) : undefined;

  const m10 = results.M10_decision?.outputs;
  const m4 = results.M4_valuation?.outputs;
  const m8 = results.M8_safety_margin?.outputs;
  const m9 = results.M9_risk?.outputs;
  const iv = isObj(m4?.intrinsic_value) ? m4.intrinsic_value : null;

  const conclusion = typeof m10?.conclusion === "string" ? m10.conclusion : null;
  const total = num(m10?.total);
  const position = pct(m10?.position);
  const vetoed = Array.isArray(m10?.vetoed) ? (m10.vetoed as unknown[]) : [];
  const ivMid = num(iv?.mid);
  const currentPrice = num(m4?.current_price);
  const discount = num(m8?.discount);
  const buyPrice = num(m8?.buy_price);
  const sellPrice = num(m8?.sell_price);
  const confidence = num(m4?.valuation_confidence);

  const riskItems = (Array.isArray(m9?.risk_items) ? m9.risk_items : [])
    .filter((r): r is Record<string, unknown> => isObj(r))
    .sort((a, b) => severityRank(String(b.severity)) - severityRank(String(a.severity)))
    .slice(0, 3);

  // 备忘录锚点：只在对应章节渲染后展示
  const [visibleAnchors, setVisibleAnchors] = React.useState<
    { id: string; label: string }[]
  >([]);
  const [activeAnchor, setActiveAnchor] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!hasResults) return;
    const t = setTimeout(() => {
      setActiveAnchor(null);
      setVisibleAnchors(
        MEMO_ANCHORS.filter((a) => document.getElementById(a.id)).map(
          ({ id, label }) => ({ id, label })
        )
      );
    }, 80);
    return () => clearTimeout(t);
  }, [hasResults]);

  // 滚动监听：高亮当前所在章节
  React.useEffect(() => {
    if (visibleAnchors.length === 0) return;
    const els = visibleAnchors
      .map((a) => document.getElementById(a.id))
      .filter((el): el is HTMLElement => Boolean(el));
    if (els.length === 0) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const hit = entries
          .filter((e) => e.isIntersecting)
          .sort(
            (a, b) => a.boundingClientRect.top - b.boundingClientRect.top
          )[0];
        if (hit) setActiveAnchor(hit.target.id);
      },
      { rootMargin: "-96px 0px -55% 0px", threshold: 0 }
    );
    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [visibleAnchors]);

  function scrollTo(id: string) {
    document
      .getElementById(id)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="flex flex-col gap-3">
      {/* 运行概览 */}
      {(!showResults || running) && (running || Object.keys(statuses).length > 0) && (
        <Card className="rounded-xl">
          <CardHeader className="pb-2">
            <div className="text-sm font-semibold">运行概览</div>
          </CardHeader>
          <CardContent className="flex flex-col gap-2.5">
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-extrabold tabular-nums">
                {progress}%
              </span>
              <span className="text-xs text-muted-foreground">
                · {doneCount} / {workflow.steps.length} 已完成
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
              <span>
                {currentAgent
                  ? `${currentAgent.code} ${currentAgent.name}`
                  : running
                    ? "步骤切换中"
                    : "等待开始"}
              </span>
              {running ? (
                <span className="flex items-center gap-1 font-medium text-emerald-600 dark:text-emerald-400">
                  <Loader2 className="size-3 animate-spin" />
                  分析中
                </span>
              ) : (
                <span className="font-medium text-emerald-600 dark:text-emerald-400">
                  已完成
                </span>
              )}
            </div>
            {sessionId && (
              <KvLine
                k="会话 ID"
                v={
                  <span className="font-mono text-[11px]">
                    {sessionId.slice(0, 18)}…
                  </span>
                }
              />
            )}
          </CardContent>
        </Card>
      )}

      {/* 模块状态（运行中） */}
      {!showResults && (running || Object.keys(statuses).length > 0) && (
        <Card className="rounded-xl">
          <CardHeader className="pb-2">
            <div className="text-sm font-semibold">
              模块状态
              <span className="ml-1 text-xs font-normal text-muted-foreground">
                （{workflow.steps.length}）
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
              {workflow.steps.map((s) => {
                const agent = findAgent(s.agent);
                const st = statuses[s.id] ?? "pending";
                return (
                  <div key={s.id} className="flex min-w-0 items-center gap-1.5 text-[11px] text-foreground/80">
                    <span className={cn("size-1.5 shrink-0 rounded-full", STATUS_DOT[st])} />
                    <span className="truncate">
                      {agent?.code ?? s.id} {agent?.name ?? ""}
                    </span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 关键指标占位（运行中） */}
      {!showResults && running && (
        <Card className="rounded-xl">
          <CardContent className="py-4 text-center text-xs leading-6 text-muted-foreground">
            ⏳ 结果生成中
            <br />
            <b className="text-emerald-700 dark:text-emerald-400">
              加权总分 · 建议仓位 · 内在价值
            </b>
            <br />
            完成后固定显示，不随滚动消失
          </CardContent>
        </Card>
      )}

      {/* 投资结论（已完成） */}
      {showResults && (conclusion || total != null || ivMid != null) && (
        <Card className="rounded-xl">
          <CardHeader className="pb-2">
            <div className="text-sm font-semibold">投资结论</div>
          </CardHeader>
          <CardContent className="flex flex-col gap-2.5">
            {conclusion && (
              <div className="rounded-xl border-l-4 border-l-primary bg-muted/40 px-3 py-2.5 text-xs leading-5">
                <b>结论：</b>
                {conclusion}
                {vetoed.length > 0 && (
                  <span className="mt-1 flex items-center gap-1 text-[11px] text-destructive">
                    <TriangleAlert className="size-3" />
                    触发否决：{vetoed.join("、")}
                  </span>
                )}
              </div>
            )}
            {(total != null || position != null) && (
              <div className="grid grid-cols-2 gap-2">
                {total != null && (
                  <div className="rounded-xl border bg-card px-3 py-2">
                    <div className="text-[10px] text-muted-foreground">
                      加权总分
                    </div>
                    <div className="mt-0.5 text-2xl font-extrabold tabular-nums">
                      {Math.round(total)}
                    </div>
                  </div>
                )}
                {position != null && (
                  <div className="rounded-xl border bg-card px-3 py-2">
                    <div className="text-[10px] text-muted-foreground">
                      建议仓位
                    </div>
                    <div className="mt-0.5 text-2xl font-extrabold tabular-nums">
                      {position}
                    </div>
                  </div>
                )}
              </div>
            )}
            <div className="flex flex-col">
              {ivMid != null && <KvLine k="内在价值中值" v={`${fmtNum(ivMid)} 元`} />}
              {(currentPrice != null || discount != null) && (
                <KvLine
                  k="当前价 / 折扣"
                  v={
                    <>
                      {fmtNum(currentPrice)} 元
                      {discount != null && (
                        <span className={discount >= 0 ? "text-emerald-600" : "text-amber-600"}>
                          {" "}
                          · {discount >= 0 ? "+" : ""}
                          {(discount * 100).toFixed(1)}%
                        </span>
                      )}
                    </>
                  }
                />
              )}
              {confidence != null && (
                <KvLine k="估值置信度" v={`${Math.round(confidence * 100)}%`} />
              )}
              {(buyPrice != null || sellPrice != null) && (
                <KvLine
                  k="买入 / 卖出区间"
                  v={`≤ ${fmtNum(buyPrice)} / ≥ ${fmtNum(sellPrice)}`}
                />
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 风险清单（已完成） */}
      {showResults && riskItems.length > 0 && (
        <Card className="rounded-xl">
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2 text-sm font-semibold">
              风险清单
              <Badge variant="outline" className="rounded-md border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300">
                {riskItems.length}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {riskItems.map((r, i) => {
              const sev = SEVERITY_BADGE[String(r.severity)] ?? SEVERITY_BADGE.info;
              return (
                <div key={i} className="flex items-start gap-2 rounded-lg border bg-card px-2.5 py-2 text-xs">
                  <Badge variant="outline" className={`shrink-0 rounded-md ${sev.cls}`}>
                    {sev.label}
                  </Badge>
                  <span className="leading-5 text-foreground/85">
                    {String(r.impact ?? r.description ?? "")}
                  </span>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {/* 备忘录导航 */}
      {hasResults && visibleAnchors.length > 0 && (
        <Card className="rounded-xl">
          <CardHeader className="pb-2">
            <div className="text-sm font-semibold">备忘录导航</div>
          </CardHeader>
          <CardContent className="flex flex-col gap-0.5">
            {visibleAnchors.map((a) => (
              <button
                key={a.id}
                type="button"
                onClick={() => scrollTo(a.id)}
                className={cn(
                  "flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-foreground/80 transition-colors hover:bg-muted",
                  activeAnchor === a.id &&
                    "bg-emerald-50/70 font-medium text-emerald-700 hover:bg-emerald-50/70 dark:bg-emerald-950/40 dark:text-emerald-300"
                )}
              >
                <span
                  className={cn(
                    "flex size-5 shrink-0 items-center justify-center rounded-md bg-muted font-mono text-[10px] font-bold text-muted-foreground",
                    activeAnchor === a.id && "bg-primary text-white"
                  )}
                >
                  {ANCHOR_BADGE[a.id] ?? "·"}
                </span>
                {a.label}
              </button>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
