import { notFound } from "next/navigation";

import { ConversationDetailView } from "@/components/conversations/conversation-detail-view";
import { createClient } from "@/lib/supabase/server";
import { getCurrentUser } from "@/lib/supabase/auth";
import { backendAuthHeaders } from "@/lib/backend-auth";
import type { SessionView } from "@/hooks/use-workflow-run";
import type { Conversation } from "@/types/conversation";

export default async function ConversationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const user = await getCurrentUser();
  if (!user) notFound();

  let conversation: Conversation | null = null;
  try {
    const supabase = await createClient();
    const { data } = await supabase
      .from("conversations")
      .select("*")
      .eq("id", id)
      .eq("user_id", user.id)
      .maybeSingle();
    conversation = (data as Conversation) ?? null;
  } catch {
    conversation = null;
  }
  if (!conversation) notFound();

  // 从 Supabase 读消息与备忘录（优先；后端不可用时仍可展示历史）
  let initialMessages: { role: string; content: string; created_at: string }[] = [];
  let supabaseMemo: string | null = null;
  try {
    const supabase = await createClient();
    const { data: msgs } = await supabase
      .from("messages")
      .select("role, content, created_at")
      .eq("conversation_id", id)
      .order("created_at", { ascending: true });
    initialMessages = (msgs ?? []) as typeof initialMessages;
    const { data: memo } = await supabase
      .from("memos")
      .select("content")
      .eq("conversation_id", id)
      .order("version", { ascending: false })
      .limit(1)
      .maybeSingle();
    supabaseMemo = memo?.content ?? null;
  } catch {
    // 表未创建时忽略
  }

  // 用户的 LLM 配置列表（对话时可选服务商）
  let initialLlmSettings: {
    id: string;
    name: string;
    provider: string;
    model: string;
    is_default: boolean;
  }[] = [];
  try {
    const supabase = await createClient();
    const { data } = await supabase
      .from("user_llm_settings")
      .select("id, name, provider, model, is_default")
      .eq("user_id", user.id)
      .order("created_at", { ascending: true });
    initialLlmSettings = (data ?? []) as typeof initialLlmSettings;
  } catch {
    // 表未创建时忽略
  }

  // 服务端预取后端会话与备忘录（后端不可用时由客户端重试）
  let initialSession: SessionView | null = null;
  let initialMemo: string | null = null;
  const base =
    process.env.API_BASE_SERVER || process.env.NEXT_PUBLIC_API_BASE || "";
  if (base) {
    const root = base.replace(/\/+$/, "");
    try {
      const res = await fetch(`${root}/api/sessions/${conversation.session_id}`, {
        headers: await backendAuthHeaders(),
        cache: "no-store",
        signal: AbortSignal.timeout(8000),
      });
      if (res.ok) initialSession = (await res.json()) as SessionView;
    } catch {
      // 后端不可用，客户端提供重试
    }
    try {
      const res = await fetch(
        `${root}/api/sessions/${conversation.session_id}/memo`,
        {
          headers: await backendAuthHeaders(),
          cache: "no-store",
          signal: AbortSignal.timeout(8000),
        }
      );
      if (res.ok) {
        const j = (await res.json()) as { memo?: string };
        initialMemo = j.memo ?? null;
      }
    } catch {
      // 忽略
    }
  }

  return (
    <ConversationDetailView
      conversation={conversation}
      initialSession={initialSession}
      initialMemo={supabaseMemo ?? initialMemo}
      initialMessages={initialMessages}
      initialLlmSettings={initialLlmSettings}
    />
  );
}
