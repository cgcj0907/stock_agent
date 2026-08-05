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
  memo_versions: string[];
}

export type RunStatus = "idle" | "running" | "completed" | "failed";

export function useWorkflowRun(workflowId: string, stepIds: string[]) {
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
      const session = await api<SessionView>("/api/sessions", {
        method: "POST",
        body: JSON.stringify({
          company_code: code,
          company_name: companyName.trim(),
          workflow_id: workflowId,
        }),
      });
      setSessionId(session.id);

      // 落库 conversations（M5 对话记录数据源；表未创建时忽略）
      try {
        const supabase = createClient();
        const {
          data: { user },
        } = await supabase.auth.getUser();
        if (user) {
          await supabase.from("conversations").insert({
            user_id: user.id,
            session_id: session.id,
            company_code: code,
            company_name: companyName.trim(),
            workflow_id: workflowId,
            status: "in_progress",
          });
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
      } catch {
        // 备忘录生成失败不影响结果展示
      }
    } catch (e) {
      setError((e as Error).message);
      setRunStatus("failed");
    } finally {
      setRunning(false);
    }
  }, [companyCode, companyName, running, stepIds, workflowId]);

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
