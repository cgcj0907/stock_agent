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
  /** 模块元信息（如降级标记 meta.degraded，见 core/contracts.build_meta） */
  meta?: { degraded?: boolean; reason_codes?: string[]; [key: string]: unknown };
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
  /** 跨会话监控命中历史（I-2，会话 payload 含 monitor_hits） */
  monitor_hits?: unknown[];
  /** P1/P2（docs/13 §13）：连接覆盖警告 + 质量门禁（关键模块降级 → 不完整） */
  warnings?: Record<string, unknown>[];
  incomplete?: boolean;
  incomplete_reasons?: string[];
}

export type RunStatus = "idle" | "running" | "completed" | "failed";

export interface WorkflowStepLike {
  id: string;
  agent: string;
  deps: string[];
}

export interface WorkflowRunInitial {
  initialCompanyCode?: string;
  initialCompanyName?: string;
}

export function useWorkflowRun(
  workflowId: string,
  stepIds: string[],
  workflowSteps?: WorkflowStepLike[],
  initial?: WorkflowRunInitial
) {
  const [companyCode, setCompanyCode] = React.useState(
    initial?.initialCompanyCode ?? ""
  );
  const [companyName, setCompanyName] = React.useState(
    initial?.initialCompanyName ?? ""
  );
  const [running, setRunning] = React.useState(false);
  const [connected, setConnected] = React.useState(false);
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [conversationId, setConversationId] = React.useState<string | null>(null);
  const [runStatus, setRunStatus] = React.useState<RunStatus>("idle");
  const [error, setError] = React.useState<string | null>(null);
  const [statuses, setStatuses] = React.useState<Record<string, StepStatus>>(
    {}
  );
  // LLM 流式增量：step id -> 已累积正文（打字机渲染数据源）
  const [streams, setStreams] = React.useState<Record<string, string>>({});
  // LLM 思考过程增量：step id -> 已累积思考文本（灰字思考区，独立于正文）
  const [thinkings, setThinkings] = React.useState<Record<string, string>>({});
  const [results, setResults] = React.useState<
    Record<string, ModuleResultView>
  >({});
  const [memo, setMemo] = React.useState<string | null>(null);

  const start = React.useCallback(async () => {
    const code = companyCode.trim();
    if (!code || running) return;

    // 落库 conversations 时写入的会话 id（try/catch 里都可能用到，故提升到外层）
    let conversationId: string | null = null;

    setRunning(true);
    setConnected(false);
    setError(null);
    setMemo(null);
    setResults({});
    setStreams({});
    setThinkings({});
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
          setConversationId(conversationId);
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
        if (evt.type === "started") {
          // 长链接已建立：后端开始实时推送 session step 进度
          setConnected(true);
        } else if (evt.type === "step") {
          setStatuses((prev) => ({
            ...prev,
            [String(evt.step)]: (evt.status as StepStatus) ?? "done",
          }));
        } else if (evt.type === "llm_chunk") {
          const step = String(evt.step);
          const kind = String(evt.kind ?? "content");
          const chunk = String(evt.chunk ?? "");
          if (!chunk) return;
          if (kind === "thinking") {
            setThinkings((prev) => ({
              ...prev,
              [step]: (prev[step] ?? "") + chunk,
            }));
          } else {
            setStreams((prev) => ({
              ...prev,
              [step]: (prev[step] ?? "") + chunk,
            }));
          }
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
        // 对话状态先落库（不依赖 memo 是否生成）——修复「分析完成仍显示进行中」
        if (conversationId) {
          const supabase = createClient();
          const {
            data: { user },
          } = await supabase.auth.getUser();
          if (user) {
            await supabase
              .from("conversations")
              .update({
                status: status === "failed" ? "failed" : "completed",
                updated_at: new Date().toISOString(),
              })
              .eq("id", conversationId);
          }
        }

        // 同步消息/memo 到 Supabase（memos 按 conversation 覆盖最新版本；失败不影响状态）
        const memoRes = await api<{ memo?: string }>(
          `/api/sessions/${session.id}/memo`
        );
        if (memoRes.memo) setMemo(memoRes.memo);
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
          }
        }
      } catch {
        // 同步失败不影响结果展示
      }
    } catch (e) {
      setError((e as Error).message);
      setRunStatus("failed");
      // 运行失败也把对话状态同步为 failed（尽力而为，避免一直显示进行中）
      if (conversationId) {
        try {
          const supabase = createClient();
          await supabase
            .from("conversations")
            .update({
              status: "failed",
              updated_at: new Date().toISOString(),
            })
            .eq("id", conversationId);
        } catch {
          // 忽略
        }
      }
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
    connected,
    sessionId,
    conversationId,
    runStatus,
    error,
    statuses,
    streams,
    thinkings,
    results,
    memo,
    start,
  };
}
