/**
 * 前端客户端读 Supabase 的薄封装：会话（sessions.payload）与备忘录（memos 表）直读，
 * 供对话详情等客户端组件使用（减少后端 API 依赖，避免 FC 冷启动）。
 */
import type { SupabaseClient } from "@supabase/supabase-js";

import type { SessionView } from "@/hooks/use-workflow-run";
import {
  sessionFromPayload,
  type SessionRowFallback,
} from "@/lib/session-read";

export async function readSessionFromSupabase(
  supabase: SupabaseClient,
  sessionId: string,
  fallback: SessionRowFallback
): Promise<SessionView | null> {
  const { data } = await supabase
    .from("sessions")
    .select("payload")
    .eq("id", sessionId)
    .maybeSingle();
  return sessionFromPayload(data, fallback);
}

export async function readMemoFromSupabase(
  supabase: SupabaseClient,
  conversationId: string
): Promise<string | null> {
  const { data } = await supabase
    .from("memos")
    .select("content")
    .eq("conversation_id", conversationId)
    .order("version", { ascending: false })
    .limit(1)
    .maybeSingle();
  return (data?.content as string | undefined) ?? null;
}
