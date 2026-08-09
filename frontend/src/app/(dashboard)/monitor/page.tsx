import { redirect } from "next/navigation";

import { MonitorClient } from "./monitor-client";
import { getCurrentUser } from "@/lib/supabase/auth";
import { createClient } from "@/lib/supabase/server";
import { backendAuthHeaders } from "@/lib/backend-auth";
import type { Conversation } from "@/types/conversation";

export const metadata = { title: "监控中心" };

interface RuleRow {
  id: string;
  session_id: string;
  company_code: string;
  company_name: string;
  rule_type: string;
  source_module: string;
  trigger: string;
  message: string;
  severity: string;
  action: string;
  active: boolean;
  created_at: string;
}

export interface MonitorHit {
  code?: string;
  rule_type?: string;
  message?: string;
  severity?: string;
  occurred_at?: string;
  company?: string;
  company_code?: string;
}

export default async function MonitorPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  const supabase = await createClient();

  // 1) 通知渠道状态（user_webhooks，RLS 仅本人）
  let webhooks: Record<string, string> = {};
  try {
    const { data } = await supabase
      .from("user_webhooks")
      .select("channel, webhook_url")
      .eq("user_id", user.id);
    webhooks = Object.fromEntries(
      (data ?? []).map((r) => [r.channel, r.webhook_url]),
    ) as Record<string, string>;
  } catch {
    // 表未创建时忽略
  }

  // 2) 最近会话（取 session_id 用于规则/命中关联）
  let conversations: Conversation[] = [];
  try {
    const { data } = await supabase
      .from("conversations")
      .select("*")
      .eq("user_id", user.id)
      .order("updated_at", { ascending: false })
      .limit(20);
    conversations = (data ?? []) as Conversation[];
  } catch {
    // ignore
  }
  const sessionIds = conversations.map((c) => c.session_id);

  // 3) 监控规则（M11 物化的 monitor_rules：本人规则 + 本次会话规则）
  const rules: RuleRow[] = [];
  try {
    const own: { data: RuleRow[] | null } = await supabase
      .from("monitor_rules")
      .select("*")
      .eq("user_id", user.id)
      .order("created_at", { ascending: false })
      .limit(100);
    let sessionRules: { data: RuleRow[] | null } = { data: [] };
    if (sessionIds.length > 0) {
      sessionRules = await supabase
        .from("monitor_rules")
        .select("*")
        .in("session_id", sessionIds)
        .order("created_at", { ascending: false })
        .limit(200);
    }
    const seen = new Set<string>();
    for (const r of [...(own.data ?? []), ...(sessionRules.data ?? [])]) {
      if (seen.has(r.id)) continue;
      seen.add(r.id);
      rules.push(r);
    }
  } catch {
    // ignore
  }

  // 4) 命中时间线：最近 5 个已完成会话的 monitor_hits（后端会话 JSON；后端不可用时降级为空）
  const completed = conversations.filter((c) => c.status === "completed");
  const base =
    process.env.API_BASE_SERVER || process.env.NEXT_PUBLIC_API_BASE || "";
  const hits: MonitorHit[] = [];
  if (base) {
    const root = base.replace(/\/+$/, "");
    for (const c of completed.slice(0, 5)) {
      try {
        const res = await fetch(`${root}/api/sessions/${c.session_id}`, {
          headers: await backendAuthHeaders(),
          cache: "no-store",
          signal: AbortSignal.timeout(5000),
        });
        if (!res.ok) continue;
        const s = (await res.json()) as { monitor_hits?: MonitorHit[] };
        for (const h of s.monitor_hits ?? []) {
          hits.push({
            ...h,
            company: c.company_name || c.company_code,
            company_code: c.company_code,
          });
        }
      } catch {
        // 后端不可用，跳过该会话
      }
    }
  }
  hits.sort((a, b) =>
    String(b.occurred_at ?? "").localeCompare(String(a.occurred_at ?? "")),
  );

  return (
    <MonitorClient
      webhooks={webhooks}
      rules={rules}
      hits={hits}
      backendUnavailable={!base}
    />
  );
}
