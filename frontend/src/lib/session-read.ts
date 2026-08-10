/**
 * 从 Supabase `sessions.payload`（后端 session.to_dict() 序列化，已剔除 api_key）
 * 构造前端 SessionView 的纯函数，报告页 / 备忘录页 / 对话详情 / 仪表盘 / 监控中心共用。
 */
import type { ModuleResultView, SessionView } from "@/hooks/use-workflow-run";

export interface SessionRowFallback {
  id: string;
  company_code: string;
  company_name: string;
  status: string;
  workflow_id: string;
}

interface SessionPayload {
  module_results?: Record<string, ModuleResultView>;
  assumptions?: Record<string, unknown>;
  status?: string;
  current_module?: string | null;
  memo_versions?: string[];
  monitor_hits?: unknown[];
  warnings?: unknown[];
  incomplete?: boolean;
  incomplete_reasons?: string[];
}

/** 从 sessions 行（{ payload }）构造 SessionView；无 module_results 时返回 null。 */
export function sessionFromPayload(
  row: { payload?: unknown } | null | undefined,
  fallback: SessionRowFallback
): SessionView | null {
  const payload = (row?.payload ?? {}) as SessionPayload;
  if (
    !payload.module_results ||
    Object.keys(payload.module_results).length === 0
  ) {
    return null;
  }
  return {
    id: fallback.id,
    company_code: fallback.company_code,
    company_name: fallback.company_name,
    status: payload.status ?? fallback.status,
    current_module: payload.current_module ?? null,
    module_results: payload.module_results,
    workflow_id: fallback.workflow_id,
    assumptions: payload.assumptions,
    memo_versions: payload.memo_versions ?? [],
    monitor_hits: payload.monitor_hits as SessionView["monitor_hits"],
    warnings: payload.warnings as SessionView["warnings"],
    incomplete: payload.incomplete ?? false,
    incomplete_reasons: payload.incomplete_reasons ?? [],
  } as SessionView;
}
