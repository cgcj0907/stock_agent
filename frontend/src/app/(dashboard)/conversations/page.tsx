import { ConversationsClient } from "./conversations-client";
import { createClient } from "@/lib/supabase/server";
import { getCurrentUser } from "@/lib/supabase/auth";
import type { Conversation } from "@/types/conversation";

export default async function ConversationsPage() {
  const user = await getCurrentUser();
  let conversations: Conversation[] = [];

  if (user) {
    try {
      const supabase = await createClient();
      const { data } = await supabase
        .from("conversations")
        .select("*")
        .eq("user_id", user.id)
        .order("updated_at", { ascending: false });
      conversations = (data ?? []) as Conversation[];

      // 对账：把「进行中」但后端会话已完成/失败的历史记录纠正状态（修复已卡住的旧数据）
      const pending = conversations.filter((c) => c.status === "in_progress");
      if (pending.length > 0) {
        const base =
          process.env.API_BASE_SERVER ||
          process.env.NEXT_PUBLIC_API_BASE ||
          "";
        if (base) {
          const root = base.replace(/\/+$/, "");
          const res = await fetch(`${root}/api/sessions`, {
            cache: "no-store",
            signal: AbortSignal.timeout(8000),
          });
          if (res.ok) {
            const j = (await res.json()) as {
              sessions: Array<{ id: string; status: string }>;
            };
            const statusById = new Map(
              j.sessions.map((s) => [s.id, s.status])
            );
            for (const c of pending) {
              const sStatus = statusById.get(c.session_id);
              const target =
                sStatus === "failed"
                  ? "failed"
                  : sStatus === "completed"
                    ? "completed"
                    : null;
              if (target) {
                await supabase
                  .from("conversations")
                  .update({
                    status: target,
                    updated_at: new Date().toISOString(),
                  })
                  .eq("id", c.id);
                c.status = target; // 内存同步，本次渲染即显示正确状态
              }
            }
          }
        }
      }
    } catch {
      // conversations 表未创建时显示空态
    }
  }

  return <ConversationsClient initial={conversations} />;
}
