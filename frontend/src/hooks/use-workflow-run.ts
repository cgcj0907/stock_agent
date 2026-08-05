"use client";

import * as React from "react";

import { api, API_BASE, streamSse } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import type { StepStatus } from "@/lib/workflows/catalog";

export interface ModuleResultView {
  module: string;
  status: string;
  score: number | null;
  outputs: Record<string, unknown>;
  evidence: string[];
  llm_explanation: string | null;
}

export interface SessionView {
  id: string;
  company_code: string;
  company_name: string;
  status: string;
  current_module: string | null;
  module_results: Record<string, ModuleResultView>;
  workflow_id: string;
  assumptions?: Record<string, unknown>;
  memo_versions: string[];
}

export type RunStatus = "idle" | "running" | "completed" | "failed";

export interface WorkflowStepLike {
  id: string;
  agent: string;
  deps: string[];
}

export function useWorkflowRun(
  workflowId: string,
  stepIds: string[],
  workflowSteps?: WorkflowStepLike[]
) {
  const [companyCode, setCompanyCode] = React.useState("");
  const [companyName, setCompanyName] = React.useState("");
  const [running, setRunning] = React.useState(false);
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [runStatus, setRunStatus] = React.useState<RunStatus>("idle");
  const [error, setError] = React.useState<string | null>(null);
  const [statuses, setStatuses] = React.useState<Record<string, StepStatus>>(
    {}
  );
  const [results, setResults] = React.useState<
    Record<string, ModuleResultView>
  >({});
  const [memo, setMemo] = React.useState<string | null>(null);

  const start = React.useCallback(async () => {
    const code = companyCode.trim();
    if (!code || running) return;

    setRunning(true);
    setError(null);
    setMemo(null);
    setResults({});
    setStatuses(Object.fromEntries(stepIds.map((id) => [id, "pending"])));
    setRunStatus("running");

    try {
      // 走前端 BFF：自动附加用户默认 LLM 配置（服务端解密，Key 不落地浏览器）
      const res = await fetch("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company_code: code,
          company_name: companyName.trim(),
          workflow_id: workflowId,
          workflow_steps: workflowSteps,
        }),
      });
      if (!res.ok) {
        const j = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(j.error || `创建会话失败（${res.status}）`);
      }
      const session = (await res.json()) as SessionView;
      setSessionId(session.id);

      // 落库 conversations + 用户消息（M5 对话记录数据源；表未创建时忽略）
      let conversationId: string | null = null;
      try {
        const supabase = createClient();
        const {
          data: { user },
        } = await supabase.auth.getUser();
        if (user) {
          const conv = await supabase
            .from("conversations")
            .insert({
              user_id: user.id,
              session_id: session.id,
              company_code: code,
              company_name: companyName.trim(),
              workflow_id: workflowId,
              status: "in_progress",
            })
            .select("id")
            .single();
          conversationId = conv.data?.id ?? null;
          if (conversationId) {
            await supabase.from("messages").insert({
              conversation_id: conversationId,
              user_id: user.id,
              role: "user",
              content: `发起分析：${companyName.trim() || code}（${code}）· 工作流 ${workflowId}`,
            });
          }
        }
      } catch {
        // ignore
      }

      let finalStatus = "completed";
      await streamSse(`${API_BASE}/api/sessions/${session.id}/events`, (evt) => {
        if (evt.type === "step") {
          setStatuses((prev) => ({
            ...prev,
            [String(evt.step)]: (evt.status as StepStatus) ?? "done",
          }));
        } else if (evt.type === "done") {
          finalStatus = String(evt.status ?? "completed");
        } else if (evt.type === "error") {
          finalStatus = "failed";
          setError(String(evt.message ?? "运行失败"));
        }
      });

      const final = await api<SessionView>(`/api/sessions/${session.id}`);
      setResults(final.module_results ?? {});
      const status = final.status === "failed" ? "failed" : finalStatus;
      setRunStatus(status === "failed" ? "failed" : "completed");

      try {
        const memoRes = await api<{ memo?: string }>(
          `/api/sessions/${session.id}/memo`
        );
        if (memoRes.memo) setMemo(memoRes.memo);
        // 同步消息/memo 到 Supabase（memos 按 conversation 覆盖最新版本）
        if (memoRes.memo && conversationId) {
          const supabase = createClient();
          const {
            data: { user },
          } = await supabase.auth.getUser();
          if (user) {
            const doneCount = Object.values(final.module_results ?? {}).filter(
              (r) => r.status === "done"
            ).length;
            await supabase.from("messages").insert({
              conversation_id: conversationId,
              user_id: user.id,
              role: "assistant",
              content: `分析完成：${doneCount} 个模块执行完毕，已生成投资备忘录。`,
            });
            const { data: existing } = await supabase
              .from("memos")
              .select("id, version")
              .eq("conversation_id", conversationId)
              .order("version", { ascending: false })
              .limit(1)
              .maybeSingle();
            if (existing) {
              await supabase
                .from("memos")
                .update({ content: memoRes.memo, session_id: session.id })
                .eq("id", existing.id);
            } else {
              await supabase
                .from("memos")
                .insert({
                  conversation_id: conversationId,
                  user_id: user.id,
                  session_id: session.id,
                  version: 1,
                  content: memoRes.memo,
                });
            }
            await supabase
              .from("conversations")
              .update({
                status: status === "failed" ? "failed" : "completed",
                updated_at: new Date().toISOString(),
              })
              .eq("id", conversationId);
          }
        }
      } catch {
        // 同步失败不影响结果展示
      }
    } catch (e) {
      setError((e as Error).message);
      setRunStatus("failed");
    } finally {
      setRunning(false);
    }
  }, [companyCode, companyName, running, stepIds, workflowId, workflowSteps]);

  return {
    companyCode,
    setCompanyCode,
    companyName,
    setCompanyName,
    running,
    sessionId,
    runStatus,
    error,
    statuses,
    results,
    memo,
    start,
  };
}
