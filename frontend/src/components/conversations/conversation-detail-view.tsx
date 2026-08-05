"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  FileText,
  Loader2,
  RefreshCcw,
  Trash2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { WorkflowDag } from "@/components/workflow/workflow-dag";
import { ResultCard } from "@/components/workflow/result-card";
import { findAgent } from "@/lib/agents/catalog";
import { api, runSessionViaSse } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { getWorkflow, type StepStatus } from "@/lib/workflows/catalog";
import { timeAgo } from "@/lib/time";
import {
  CONVERSATION_STATUS,
  type Conversation,
} from "@/types/conversation";
import type { ModuleResultView, SessionView } from "@/hooks/use-workflow-run";

export function ConversationDetailView({
  conversation,
  initialSession,
  initialMemo,
}: {
  conversation: Conversation;
  initialSession: SessionView | null;
  initialMemo: string | null;
}) {
  const router = useRouter();
  const workflow = getWorkflow(conversation.workflow_id);

  const [session, setSession] = React.useState<SessionView | null>(
    initialSession
  );
  const [memo, setMemo] = React.useState<string | null>(initialMemo);
  const [liveStatuses, setLiveStatuses] = React.useState<
    Record<string, StepStatus> | null
  >(null);
  const [loading, setLoading] = React.useState(false);
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // 从会话结果推导各步骤状态
  const derivedStatuses = React.useMemo(() => {
    const next: Record<string, StepStatus> = {};
    if (workflow && session) {
      for (const step of workflow.steps) {
        const r = session.module_results?.[step.agent];
        next[step.id] = r
          ? ((r.status as StepStatus) ?? "pending")
          : "pending";
      }
    }
    return next;
  }, [workflow, session]);

  const statuses = liveStatuses ?? derivedStatuses;

  async function refresh(showToast = true) {
    setLoading(true);
    setError(null);
    try {
      const s = await api<SessionView>(
        `/api/sessions/${conversation.session_id}`
      );
      setSession(s);
      try {
        const memoRes = await api<{ memo?: string }>(
          `/api/sessions/${conversation.session_id}/memo`
        );
        if (memoRes.memo) setMemo(memoRes.memo);
      } catch {
        // 无备忘录
      }
      if (showToast) toast.success("已刷新");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleRerun() {
    setRunning(true);
    setError(null);
    setLiveStatuses(
      Object.fromEntries(
        (workflow?.steps.map((s) => s.id) ?? []).map((id) => [
          id,
          "pending" as StepStatus,
        ])
      )
    );
    try {
      let finalStatus = "completed";
      await runSessionViaSse(conversation.session_id, {
        onStep: (step, status) =>
          setLiveStatuses((prev) => ({
            ...prev,
            [step]: status as StepStatus,
          })),
        onDone: (status) => {
          finalStatus = status;
        },
        onError: (message) => {
          finalStatus = "failed";
          setError(message);
        },
      });
      const s = await api<SessionView>(
        `/api/sessions/${conversation.session_id}`
      );
      setSession(s);
      setLiveStatuses(null);
      try {
        const memoRes = await api<{ memo?: string }>(
          `/api/sessions/${conversation.session_id}/memo`
        );
        if (memoRes.memo) setMemo(memoRes.memo);
      } catch {
        // 忽略
      }
      if (finalStatus === "failed") {
        toast.error("分析失败，请查看错误");
      } else {
        toast.success("分析完成");
      }
      try {
        const supabase = createClient();
        await supabase
          .from("conversations")
          .update({
            status: finalStatus === "failed" ? "failed" : "completed",
            updated_at: new Date().toISOString(),
          })
          .eq("id", conversation.id);
      } catch {
        // 忽略
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm("确定删除这条对话记录？")) return;
    try {
      try {
        await api(`/api/sessions/${conversation.session_id}`, {
          method: "DELETE",
        });
      } catch {
        // 忽略
      }
      const supabase = createClient();
      await supabase.from("conversations").delete().eq("id", conversation.id);
      toast.success("已删除");
      router.push("/conversations");
      router.refresh();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  const status =
    CONVERSATION_STATUS[conversation.status] ?? CONVERSATION_STATUS.created;
  const orderedResults = workflow
    ? workflow.steps
        .map((s) => ({
          step: s.id,
          agent: s.agent,
          result: session?.module_results?.[s.agent],
        }))
        .filter(
          (x): x is { step: string; agent: string; result: ModuleResultView } =>
            !!x.result
        )
    : [];

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      {/* 头部 */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Button
            asChild
            variant="ghost"
            size="sm"
            className="mb-2 w-fit rounded-lg"
          >
            <Link href="/conversations">
              <ArrowLeft className="size-4" />
              返回对话记录
            </Link>
          </Button>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">
              {conversation.company_name || conversation.company_code}
            </h1>
            <Badge variant="secondary" className="rounded-md font-mono">
              {conversation.company_code}
            </Badge>
            {workflow && (
              <Badge variant="outline" className="rounded-md">
                {workflow.name}
              </Badge>
            )}
            <Badge
              variant="outline"
              className={`gap-1 rounded-md ${status.className}`}
            >
              {status.label}
            </Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            创建于 {timeAgo(conversation.created_at)} · 会话{" "}
            <span className="font-mono">
              {conversation.session_id.slice(0, 18)}…
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            className="rounded-full"
            onClick={handleRerun}
            disabled={running || loading || !workflow || !session}
          >
            {running ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RefreshCcw className="size-4" />
            )}
            {running ? "分析中" : "重新分析"}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="size-9 rounded-lg text-muted-foreground hover:text-destructive"
            onClick={handleDelete}
            aria-label="删除"
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          加载会话…
        </div>
      )}

      {error && !session && (
        <Card className="rounded-2xl border-dashed">
          <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
            <p className="text-sm font-medium">无法加载会话</p>
            <p className="max-w-md text-xs text-muted-foreground">{error}</p>
            <Button
              variant="outline"
              size="sm"
              className="rounded-lg"
              onClick={() => refresh(false)}
            >
              重试
            </Button>
          </CardContent>
        </Card>
      )}

      {session && workflow && (
        <Card className="overflow-hidden rounded-2xl">
          <div className={`h-1 bg-gradient-to-r ${workflow.accent}`} />
          <div className="p-3 md:p-4">
            <WorkflowDag
              steps={workflow.steps}
              statuses={statuses}
              height={workflow.steps.length > 6 ? 300 : 220}
            />
          </div>
        </Card>
      )}

      {orderedResults.length > 0 && (
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

      {memo && (
        <section className="flex flex-col gap-3">
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <FileText className="size-4 text-emerald-600 dark:text-emerald-400" />
            投资备忘录
          </h2>
          <Card className="rounded-2xl">
            <CardContent className="prose prose-sm max-w-none p-6 dark:prose-invert">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {memo}
              </ReactMarkdown>
            </CardContent>
          </Card>
        </section>
      )}
    </div>
  );
}
