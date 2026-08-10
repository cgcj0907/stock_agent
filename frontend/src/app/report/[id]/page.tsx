import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { FileText } from "lucide-react";

import { ReportActions } from "@/components/report/report-actions";
import { Badge } from "@/components/ui/badge";
import { MemoCard } from "@/components/workflow/memo-card";
import { ResultCard } from "@/components/workflow/result-card";
import { findAgent } from "@/lib/agents/catalog";
import { backendAuthHeaders } from "@/lib/backend-auth";
import { orderedModuleResults } from "@/lib/report";
import { getCurrentUser } from "@/lib/supabase/auth";
import { createClient } from "@/lib/supabase/server";
import { getWorkflow } from "@/lib/workflows/catalog";
import { timeAgo } from "@/lib/time";
import {
  CONVERSATION_STATUS,
  type Conversation,
} from "@/types/conversation";
import type { SessionView } from "@/hooks/use-workflow-run";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const user = await getCurrentUser();
  if (!user) return { title: "分析报告" };
  try {
    const supabase = await createClient();
    const { data: conv } = await supabase
      .from("conversations")
      .select("company_name, company_code")
      .eq("id", id)
      .eq("user_id", user.id)
      .maybeSingle();
    const label = conv?.company_name || conv?.company_code || "分析报告";
    return { title: `${label} 分析报告` };
  } catch {
    return { title: "分析报告" };
  }
}

/**
 * 分析报告导出页（SSR）：
 * 需登录（RLS 只允许本人读取），以单列、打印友好的排版渲染「投资备忘录 + 全部模块结果卡」，
 * 浏览器打印 / 另存为 PDF 即得分析结果报告。
 */
export default async function ReportPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const user = await getCurrentUser();
  if (!user) redirect("/login");

  const supabase = await createClient();
  const { data: conv } = await supabase
    .from("conversations")
    .select("*")
    .eq("id", id)
    .eq("user_id", user.id)
    .maybeSingle();
  const conversation = (conv as Conversation) ?? null;
  if (!conversation) notFound();

  // 会话（模块结果）后端预取；后端不可用时降级为空态（头部仍可打印）
  let session: SessionView | null = null;
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
      if (res.ok) session = (await res.json()) as SessionView;
    } catch {
      // 后端不可用：保留头部与空态，供再次打印
    }
  }

  const wf = getWorkflow(conversation.workflow_id);
  const status =
    CONVERSATION_STATUS[conversation.status] ?? CONVERSATION_STATUS.created;
  const label = conversation.company_name || conversation.company_code;
  const moduleResults = session?.module_results ?? {};
  const ordered = orderedModuleResults(wf, moduleResults);
  const dateStr = conversation.created_at
    ? new Date(conversation.created_at).toLocaleDateString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      })
    : timeAgo(conversation.updated_at);

  return (
    <main className="min-h-full bg-background">
      <div className="mx-auto max-w-4xl px-4 py-8 md:py-12">
        {/* 顶部操作栏（打印时隐藏） */}
        <div className="mb-6 print:hidden">
          <ReportActions conversationId={conversation.id} />
        </div>

        {/* 报告头 */}
        <header className="mb-6 border-b pb-6">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
            <FileText className="size-3.5" />
            Value Agent · 分析报告
          </div>
          <h1 className="mt-2 text-2xl font-bold tracking-tight">{label}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="rounded-md font-mono text-[10px]">
              {conversation.company_code}
            </Badge>
            {wf && (
              <Badge variant="secondary" className="rounded-md text-[10px]">
                {wf.name}
              </Badge>
            )}
            <Badge variant="outline" className={`gap-1 rounded-md ${status.className}`}>
              {status.label}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {dateStr}
              {session ? ` · 会话 ${session.id.slice(0, 12)}…` : ""}
            </span>
          </div>
        </header>

        {/* 执行摘要（投资备忘录） */}
        {ordered.length > 0 && (
          <section className="mb-8 flex flex-col gap-3 print:break-inside-avoid">
            <h2 className="flex items-center gap-2 text-base font-semibold">
              <FileText className="size-4 text-emerald-600 dark:text-emerald-400" />
              投资备忘录
            </h2>
            <MemoCard
              companyCode={conversation.company_code}
              companyName={conversation.company_name}
              workflowId={conversation.workflow_id}
              status={conversation.status}
              moduleResults={moduleResults}
              sessionId={conversation.session_id}
              createdAt={conversation.created_at}
              assumptions={session?.assumptions}
            />
          </section>
        )}

        {/* 分析结果：模块卡片（单列，适配打印分页） */}
        <section className="flex flex-col gap-3">
          <h2 className="text-base font-semibold">分析结果</h2>
          {ordered.length === 0 ? (
            <p className="rounded-2xl border border-dashed px-6 py-12 text-center text-sm text-muted-foreground">
              该会话还没有可导出的分析结果
            </p>
          ) : (
            ordered.map(({ agent, result }) => (
              <div key={agent} className="print:break-inside-avoid">
                <ResultCard agent={findAgent(agent)} result={result} />
              </div>
            ))
          )}
        </section>

        <footer className="mt-10 border-t pt-4 text-center text-xs text-muted-foreground print:hidden">
          由 Value Agent 生成 · 数据源 AkShare（新浪/东财） · 不构成投资建议
        </footer>
      </div>
    </main>
  );
}
