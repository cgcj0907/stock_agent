"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Bot,
  FileText,
  Loader2,
  RefreshCcw,
  Send,
  Trash2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AnalysisProgress } from "@/components/workflow/analysis-progress";
import { StepActivityFeed } from "@/components/workflow/step-activity-feed";
import { WorkflowDag } from "@/components/workflow/workflow-dag";
import { ResultCard } from "@/components/workflow/result-card";
import { MemoCard } from "@/components/workflow/memo-card";
import { findAgent } from "@/lib/agents/catalog";
import { api, runSessionViaSse, watchSessionViaSse } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { getWorkflow, type StepStatus } from "@/lib/workflows/catalog";
import { timeAgo } from "@/lib/time";
import {
  CONVERSATION_STATUS,
  type Conversation,
} from "@/types/conversation";
import type { ModuleResultView, SessionView } from "@/hooks/use-workflow-run";

export interface ChatMessage {
  role: string;
  content: string;
  created_at?: string;
}

export interface LlmOption {
  id: string;
  name: string;
  provider: string;
  model: string;
  is_default: boolean;
}

export function ConversationDetailView({
  conversation,
  initialSession,
  initialMemo,
  initialMessages = [],
  initialLlmSettings = [],
}: {
  conversation: Conversation;
  initialSession: SessionView | null;
  initialMemo: string | null;
  initialMessages?: ChatMessage[];
  initialLlmSettings?: LlmOption[];
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
  const [liveConnected, setLiveConnected] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<ChatMessage[]>(
    initialMessages
  );
  const [chatInput, setChatInput] = React.useState("");
  const [chatBusy, setChatBusy] = React.useState(false);
  const [selectedLlmId, setSelectedLlmId] = React.useState<string | null>(
    initialLlmSettings.find((l) => l.is_default)?.id ??
      initialLlmSettings[0]?.id ??
      null
  );

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
      if (
        ["created", "in_progress", "awaiting_input"].includes(session.status) &&
        session.current_module
      ) {
        const runningStep = workflow.steps.find(
          (step) => step.agent === session.current_module
        );
        if (runningStep && next[runningStep.id] === "pending") {
          next[runningStep.id] = "running";
        }
      }
    }
    return next;
  }, [workflow, session]);

  const statuses = liveStatuses ?? derivedStatuses;
  // created：可能即将被其它设备启动，尝试 watch 观察；不参与轮询/进行中展示
  const sessionActive =
    !!session &&
    ["created", "in_progress", "awaiting_input"].includes(session.status);
  const sessionRunning =
    !!session && ["in_progress", "awaiting_input"].includes(session.status);
  const showRunning = running || sessionRunning;
  const progressConnected = running ? liveConnected : liveConnected || sessionRunning;

  const syncSession = React.useCallback(
    async (options?: { showToast?: boolean; showLoading?: boolean }) => {
      const { showToast = true, showLoading = true } = options ?? {};
      if (showLoading) setLoading(true);
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
        if (showLoading) setLoading(false);
      }
    },
    [conversation.session_id]
  );

  async function refresh(showToast = true) {
    await syncSession({ showToast, showLoading: true });
  }

  React.useEffect(() => {
    if (running || !sessionActive) return;

    const controller = new AbortController();
    void watchSessionViaSse(conversation.session_id, {
      signal: controller.signal,
      onStarted: () => setLiveConnected(true),
      // watch 连接时会先吐一批当前快照；用 prev ?? {} 避免依赖 derivedStatuses
      onStep: (step, status) =>
        setLiveStatuses((prev) => ({
          ...(prev ?? {}),
          [step]: status as StepStatus,
        })),
      onDone: async () => {
        setLiveConnected(false);
        await syncSession({ showToast: false, showLoading: false });
      },
      onError: (message) => {
        setLiveConnected(false);
        setError(message);
      },
    }).catch((e) => {
      if ((e as Error)?.name !== "AbortError") {
        setLiveConnected(false);
      }
    });

    return () => {
      controller.abort();
      setLiveConnected(false);
    };
  }, [conversation.session_id, running, sessionActive, syncSession]);

  React.useEffect(() => {
    if (running || !sessionRunning || liveConnected) return;

    let cancelled = false;
    let syncing = false;
    const tick = async () => {
      if (cancelled || syncing) return;
      syncing = true;
      try {
        const s = await api<SessionView>(`/api/sessions/${conversation.session_id}`);
        if (cancelled) return;
        setSession(s);
        try {
          const memoRes = await api<{ memo?: string }>(
            `/api/sessions/${conversation.session_id}/memo`
          );
          if (!cancelled && memoRes.memo) setMemo(memoRes.memo);
        } catch {
          // 无备忘录
        }
      } catch {
        // 轮询失败时静默，避免打断用户；下一轮继续尝试
      } finally {
        syncing = false;
      }
    };

    void tick();
    const timer = window.setInterval(tick, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [conversation.session_id, liveConnected, running, sessionRunning]);

  async function handleRerun() {
    setRunning(true);
    setLiveConnected(false);
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
        onStarted: () => setLiveConnected(true),
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
      // 保留 liveStatuses：分析完成后动作流继续留在对话中（Codex 风格）
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

  async function handleSend() {
    const content = chatInput.trim();
    if (!content || chatBusy) return;
    setChatBusy(true);
    // 乐观追加用户消息
    setMessages((prev) => [
      ...prev,
      { role: "user", content },
    ]);
    setChatInput("");
    try {
      const res = await fetch(`/api/sessions/${conversation.session_id}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content,
          conversation_id: conversation.id,
          llm_settings_id: selectedLlmId ?? undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "对话失败");
      // 服务端已把新消息写入 Supabase；这里把 assistant 回复追加到本地
      const assistant = (data.messages ?? []).find(
        (m: ChatMessage) => m.role === "assistant"
      );
      if (assistant) {
        setMessages((prev) => [...prev, assistant]);
      } else {
        throw new Error("未收到回复");
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setChatBusy(false);
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

      {showRunning && workflow && (
        <AnalysisProgress
          steps={workflow.steps}
          statuses={statuses}
          running={showRunning}
          connected={progressConnected}
          className="animate-in fade-in slide-in-from-top-2"
        />
      )}

      <section className="flex flex-col gap-3">
        <h2 className="text-base font-semibold">对话</h2>
        <Card className="rounded-2xl">
          <CardContent className="flex flex-col gap-3 p-4">
            {/* Codex 风格：在对话框中逐行展示每一步处理动作 */}
              {(showRunning || liveStatuses) && workflow && (
              <StepActivityFeed
                steps={workflow.steps}
                statuses={statuses}
                  running={showRunning}
                  connected={progressConnected}
                companyLabel={
                  conversation.company_name
                    ? `${conversation.company_name}（${conversation.company_code}）`
                    : conversation.company_code
                }
                className="animate-in fade-in slide-in-from-top-2"
              />
            )}
            {messages.length === 0 ? (
              <p className="py-2 text-center text-xs text-muted-foreground">
                基于本次分析结果，追问任意投资问题
              </p>
            ) : (
              messages.map((m, i) => (
                <div
                  key={i}
                  className={`flex gap-2.5 ${
                    m.role === "user" ? "flex-row-reverse" : ""
                  }`}
                >
                  <div
                    className={`flex size-7 shrink-0 items-center justify-center rounded-full text-xs text-white ${
                      m.role === "user"
                        ? "bg-emerald-600"
                        : "bg-muted-foreground/60"
                    }`}
                  >
                    {m.role === "user" ? (
                      "我"
                    ) : (
                      <Bot className="size-4" />
                    )}
                  </div>
                  <div
                    className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm leading-6 ${
                      m.role === "user"
                        ? "rounded-tr-sm bg-emerald-600 text-white"
                        : "rounded-tl-sm bg-muted/60"
                    }`}
                  >
                    {m.content}
                  </div>
                </div>
              ))
            )}

            {/* 追问输入 + LLM 选择 */}
            <div className="mt-1 flex flex-col gap-2 border-t pt-3 sm:flex-row sm:items-center">
              {initialLlmSettings.length > 0 && (
                <Select
                  value={selectedLlmId ?? undefined}
                  onValueChange={setSelectedLlmId}
                >
                  <SelectTrigger className="h-9 w-full sm:w-52">
                    <SelectValue placeholder="选择 LLM" />
                  </SelectTrigger>
                  <SelectContent>
                    {initialLlmSettings.map((l) => (
                      <SelectItem key={l.id} value={l.id}>
                        {l.name || l.provider} · {l.model}
                        {l.is_default ? "（默认）" : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <div className="flex flex-1 items-center gap-2">
                <Input
                  placeholder="追问：这个估值合理吗？"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                  disabled={chatBusy}
                  className="h-9 rounded-xl"
                />
                <Button
                  size="icon"
                  className="size-9 shrink-0 rounded-xl"
                  onClick={handleSend}
                  disabled={chatBusy || !chatInput.trim()}
                  aria-label="发送"
                >
                  {chatBusy ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Send className="size-4" />
                  )}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

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

      {(memo || (session && Object.keys(session.module_results ?? {}).length > 0)) && (
        <section className="flex flex-col gap-3">
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <FileText className="size-4 text-emerald-600 dark:text-emerald-400" />
            投资备忘录
          </h2>
          {session && Object.keys(session.module_results ?? {}).length > 0 ? (
            <MemoCard
              companyCode={conversation.company_code}
              companyName={conversation.company_name}
              workflowId={conversation.workflow_id}
              status={session.status}
              moduleResults={session.module_results ?? {}}
              sessionId={session.id}
              createdAt={conversation.created_at}
              assumptions={session.assumptions}
            />
          ) : memo ? (
            <Card className="rounded-2xl">
              <CardContent className="prose prose-sm max-w-none p-6 dark:prose-invert">
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
