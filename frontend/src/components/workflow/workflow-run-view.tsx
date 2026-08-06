"use client";

import * as React from "react";
import { FileText, Loader2, Play } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StepActivityFeed } from "@/components/workflow/step-activity-feed";
import { WorkflowDag } from "@/components/workflow/workflow-dag";
import { ResultCard } from "@/components/workflow/result-card";
import { MemoCard } from "@/components/workflow/memo-card";
import { findAgent } from "@/lib/agents/catalog";
import { useWorkflowRun } from "@/hooks/use-workflow-run";
import type { WorkflowInfo } from "@/lib/workflows/catalog";

const LEGEND = [
  { label: "待运行", dot: "bg-muted-foreground/40" },
  { label: "运行中", dot: "bg-emerald-500 animate-pulse" },
  { label: "完成", dot: "bg-emerald-500" },
  { label: "跳过", dot: "bg-amber-500" },
  { label: "失败", dot: "bg-red-500" },
];

export function WorkflowRunView({ workflow }: { workflow: WorkflowInfo }) {
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
    workflow.id === "custom" ? workflow.steps : undefined
  );

  const doneCount = stepIds.filter(
    (id) => statuses[id] === "done" || statuses[id] === "skipped"
  ).length;
  const progress = stepIds.length
    ? Math.round((doneCount / stepIds.length) * 100)
    : 0;

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

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
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
        <div className={`h-1 bg-gradient-to-r ${workflow.accent}`} />
        <div className="p-3 md:p-4">
          <WorkflowDag
            steps={workflow.steps}
            statuses={statuses}
            height={workflow.steps.length > 6 ? 300 : 220}
          />
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t px-4 py-2.5 text-xs text-muted-foreground">
          {LEGEND.map((item) => (
            <span key={item.label} className="flex items-center gap-1.5">
              <span className={`size-2 rounded-full ${item.dot}`} />
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
      <div className="rounded-2xl border bg-card p-2 shadow-sm transition-all focus-within:border-emerald-300 focus-within:ring-4 focus-within:ring-emerald-500/10 dark:focus-within:border-emerald-700">
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

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-300">
          {error}
        </div>
      )}

      {/* 结果 */}
      {showResults && (
        <section className="flex flex-col gap-3">
          <h2 className="text-base font-semibold">分析结果</h2>
          <div className="grid gap-3 md:grid-cols-2">
            {orderedResults.map(({ step, agent, result }) => (
              <ResultCard
                key={step}
                agent={agent ? findAgent(agent) : undefined}
                result={result}
              />
            ))}
          </div>
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
  );
}
