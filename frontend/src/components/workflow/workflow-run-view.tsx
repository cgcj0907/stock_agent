"use client";

import * as React from "react";
import Link from "next/link";
import { FileDown, FileText, Loader2, Play } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { MasonryGrid } from "@/components/ui/masonry-grid";
import { RightRailShell } from "@/components/ui/right-rail";
import { StepActivityFeed } from "@/components/workflow/step-activity-feed";
import { StatusIndicator, WorkflowDag } from "@/components/workflow/workflow-dag";
import { ResultCard } from "@/components/workflow/result-card";
import { ResultCardSkeleton } from "@/components/ui/result-skeleton";
import { CardEntrance } from "@/components/motion/card-entrance";
import { hasRiskContent } from "@/lib/module-risk";
import { summarizeResults } from "@/lib/report-summary";
import { MemoCard } from "@/components/workflow/memo-card";
import { RailMiniSummary, WorkflowRail } from "@/components/workflow/workflow-rail";
import { findAgent } from "@/lib/agents/catalog";
import { useWorkflowRun } from "@/hooks/use-workflow-run";
import type { StepStatus, WorkflowInfo } from "@/lib/workflows/catalog";

const LEGEND: { label: string; status: StepStatus }[] = [
  { label: "待运行", status: "pending" },
  { label: "运行中", status: "running" },
  { label: "完成", status: "done" },
  { label: "跳过", status: "skipped" },
  { label: "失败", status: "failed" },
];

export function WorkflowRunView({
  workflow,
  initialCode,
  initialName,
}: {
  workflow: WorkflowInfo;
  initialCode?: string;
  initialName?: string;
}) {
  const stepIds = React.useMemo(
    () => workflow.steps.map((s) => s.id),
    [workflow]
  );
  const {
    companyCode,
    setCompanyCode,
    companyName,
    setCompanyName,
    running,
    connected,
    conversationId,
    runStatus,
    error,
    statuses,
    streams,
    thinkings,
    results,
    memo,
    sessionId,
    start,
  } = useWorkflowRun(
    workflow.id,
    stepIds,
    workflow.id === "custom" ? workflow.steps : undefined,
    { initialCompanyCode: initialCode, initialCompanyName: initialName }
  );

  const feedRef = React.useRef<HTMLDivElement>(null);
  const [riskOnly, setRiskOnly] = React.useState(false);

  const doneCount = stepIds.filter(
    (id) => statuses[id] === "done" || statuses[id] === "skipped"
  ).length;
  const progress = stepIds.length
    ? Math.round((doneCount / stepIds.length) * 100)
    : 0;

  // 开始分析后自动滚动到实时进度流，避免用户停留在顶部看不到过程
  React.useEffect(() => {
    if (running) {
      feedRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [running]);

  // module_results 以 agent id 为键（如 M2_financial_quality）
  const orderedResults = workflow.steps
    .map((s) => ({
      step: s.id,
      agent: s.agent,
      result: results[s.agent],
    }))
    .filter((x) => x.result);

  const showResults =
    orderedResults.length > 0 &&
    (runStatus === "completed" || runStatus === "failed");
  const visibleResults = riskOnly
    ? orderedResults.filter((x) => hasRiskContent(x.result))
    : orderedResults;
  // 摘要条：模块/风险/否决计数（轻量，内联即可）
  const summary = summarizeResults(orderedResults.map((x) => x.result));

  const hasRun = running || Object.keys(statuses).length > 0;
  const hasResults = Object.keys(results).length > 0;

  return (
    <div className="mx-auto flex max-w-7xl gap-6">
      {/* 左列：过程 + 结果 + 备忘录 */}
      <div className="flex min-w-0 flex-1 flex-col gap-6">
      {/* 头部 */}
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {workflow.name}
          </h1>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
            {workflow.description}
          </p>
        </div>
        <Badge variant="secondary" className="rounded-full">
          {workflow.steps.length} 个智能体
        </Badge>
      </header>

      {/* DAG 可视化 */}
      <Card className="overflow-hidden rounded-2xl">
        <div className="p-3 md:p-4">
          <WorkflowDag steps={workflow.steps} statuses={statuses} />
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t px-4 py-2.5 text-xs text-muted-foreground">
          {LEGEND.map((item) => (
            <span key={item.label} className="flex items-center gap-1.5">
              <StatusIndicator status={item.status} />
              {item.label}
            </span>
          ))}
          {running && (
            <span className="ml-auto flex items-center gap-1.5 font-medium text-emerald-600 dark:text-emerald-400">
              <Loader2 className="size-3.5 animate-spin" />
              分析中 {progress}%
            </span>
          )}
        </div>
      </Card>

      {/* 输入区（ChatGPT 风格） */}
      <div className="rounded-2xl border bg-card p-2 shadow-sm transition-all focus-within:border-ring focus-within:ring-4 focus-within:ring-ring/10">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <input
            value={companyCode}
            onChange={(e) => setCompanyCode(e.target.value)}
            placeholder="输入 A 股代码，如 600519"
            disabled={running}
            className="min-w-0 flex-1 rounded-xl bg-transparent px-3 py-2.5 text-sm outline-none placeholder:text-muted-foreground disabled:opacity-60"
          />
          <input
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            placeholder="公司名称（可选）"
            disabled={running}
            className="min-w-0 rounded-xl bg-muted/40 px-3 py-2.5 text-sm outline-none placeholder:text-muted-foreground disabled:opacity-60 sm:w-48"
          />
          <Button
            onClick={start}
            disabled={running || !companyCode.trim()}
            className="rounded-full px-5"
          >
            {running ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Play className="size-4" />
            )}
            {running ? "分析中" : "开始分析"}
          </Button>
        </div>
        <p className="px-3 pb-1 pt-1.5 text-xs text-muted-foreground">
          免费数据源（AkShare）+ 规则引擎；完整分析约 1–2 分钟，DAG
          中实时查看进度
        </p>
      </div>

      {/* Codex 风格：对话中逐行展示每一步处理动作 */}
      {running && !connected && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-300">
          <Loader2 className="size-3.5 animate-spin" />
          正在建立实时连接，进度稍后同步…
        </div>
      )}
      <div ref={feedRef}>
      {(running || Object.keys(statuses).length > 0) && (
        <StepActivityFeed
          steps={workflow.steps}
          statuses={statuses}
          running={running}
          connected={connected}
          streams={streams}
          thinkings={thinkings}
          companyLabel={
            companyName ? `${companyName}（${companyCode}）` : companyCode
          }
          className="animate-in fade-in slide-in-from-top-2"
        />
      )}
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-300">
          {error}
        </div>
      )}

      {/* 结果（运行中占位骨架） */}
      {running && (
        <section className="flex flex-col gap-3" aria-hidden={true}>
          <h2 className="text-base font-semibold">分析结果</h2>
          <MasonryGrid>
            {Array.from({ length: 3 }).map((_, i) => (
              <ResultCardSkeleton key={i} />
            ))}
          </MasonryGrid>
        </section>
      )}

      {/* 结果 */}
      {showResults && (
        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 flex-col gap-0.5">
              <h2 className="text-base font-semibold">分析结果</h2>
              {summary.total > 0 && (
                <p className="text-xs text-muted-foreground">
                  {summary.total} 个模块 · {summary.risk} 个含风险
                  {summary.veto > 0 ? ` · ${summary.veto} 个否决` : " · 无否决"}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2">
              {sessionId && conversationId && (
                <Button asChild variant="outline" size="sm" className="rounded-lg">
                  <Link href={`/report/${conversationId}`}>
                    <FileDown className="size-3.5" />
                    导出 PDF
                  </Link>
                </Button>
              )}
              <div className="flex items-center gap-1 rounded-full border bg-muted/40 p-0.5 text-xs">
                <button
                  type="button"
                  onClick={() => setRiskOnly(false)}
                  className={`rounded-full px-3 py-1 font-medium transition-colors ${
                    !riskOnly
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  全部
                </button>
                <button
                  type="button"
                  onClick={() => setRiskOnly(true)}
                  className={`rounded-full px-3 py-1 font-medium transition-colors ${
                    riskOnly
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  只看风险
                </button>
              </div>
            </div>
          </div>
          {visibleResults.length === 0 ? (
            <p className="rounded-xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
              该工作流结果中没有风险条目
            </p>
          ) : (
            <MasonryGrid>
              {visibleResults.map(({ step, agent, result }, i) => (
                <CardEntrance key={step} index={i}>
                  <ResultCard
                    agent={agent ? findAgent(agent) : undefined}
                    result={result}
                  />
                </CardEntrance>
              ))}
            </MasonryGrid>
          )}
        </section>
      )}

      {/* 备忘录 */}
      {(memo || Object.keys(results).length > 0) && (
        <section className="flex flex-col gap-3">
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <FileText className="size-4 text-emerald-600 dark:text-emerald-400" />
            投资备忘录
          </h2>
          {Object.keys(results).length > 0 ? (
            <MemoCard
              companyCode={companyCode}
              companyName={companyName}
              workflowId={workflow.id}
              status={runStatus}
              moduleResults={results}
              sessionId={sessionId ?? undefined}
              assumptions={undefined}
            />
          ) : memo ? (
            <Card className="rounded-2xl">
              <CardContent className="prose prose-sm max-w-none p-6 dark:prose-invert prose-headings:scroll-mt-6">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {memo}
                </ReactMarkdown>
              </CardContent>
            </Card>
          ) : null}
        </section>
      )}
      </div>

      {hasRun && (
        <RightRailShell collapsedContent={<RailMiniSummary running={running} results={results} />}>
          <WorkflowRail
            workflow={workflow}
            statuses={statuses}
            running={running}
            sessionId={sessionId}
            results={results}
            showResults={showResults}
            hasResults={hasResults}
          />
        </RightRailShell>
      )}
    </div>
  );
}
