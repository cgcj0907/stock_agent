import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { ArrowLeft, FileText } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { MemoShareActions } from "@/components/memo/memo-share-actions";
import { Badge } from "@/components/ui/badge";
import { getCurrentUser } from "@/lib/supabase/auth";
import { createClient } from "@/lib/supabase/server";
import { getWorkflow } from "@/lib/workflows/catalog";
import { timeAgo } from "@/lib/time";
import {
  CONVERSATION_STATUS,
  type Conversation,
} from "@/types/conversation";

export const metadata = { title: "投资备忘录" };

/**
 * 备忘录分享 / 打印页（SSR）：
 * 需登录（RLS 只允许本人读取），以干净的排版渲染最新版备忘录，支持复制 / 导出 / 打印 PDF。
 */
export default async function MemoSharePage({
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

  const { data: memo } = await supabase
    .from("memos")
    .select("content, created_at, version")
    .eq("conversation_id", id)
    .order("version", { ascending: false })
    .limit(1)
    .maybeSingle();

  const markdown = (memo?.content as string | undefined) ?? "";
  const wf = getWorkflow(conversation.workflow_id);
  const status =
    CONVERSATION_STATUS[conversation.status] ?? CONVERSATION_STATUS.created;
  const label = conversation.company_name || conversation.company_code;
  const fileName = `${label}-${conversation.company_code}-投资备忘录`;

  return (
    <main className="min-h-full bg-background">
      <div className="mx-auto max-w-3xl px-4 py-8 md:py-12">
        {/* 顶部操作栏（打印时隐藏） */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3 print:hidden">
          <Link
            href={`/conversations/${conversation.id}`}
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="size-4" />
            返回对话
          </Link>
          <MemoShareActions markdown={markdown} fileName={fileName} />
        </div>

        {/* 报告头 */}
        <header className="mb-6 border-b pb-6">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
            <FileText className="size-3.5" />
            Value Agent · 投资备忘录
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
              {timeAgo(conversation.updated_at)}
              {memo?.version != null && ` · 备忘录 v${memo.version}`}
            </span>
          </div>
        </header>

        {/* 备忘录正文 */}
        {markdown ? (
          <article className="prose prose-sm max-w-none dark:prose-invert prose-headings:scroll-mt-6">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
          </article>
        ) : (
          <div className="rounded-2xl border border-dashed px-6 py-12 text-center text-sm text-muted-foreground">
            该对话还没有生成备忘录
          </div>
        )}

        <footer className="mt-10 border-t pt-4 text-center text-xs text-muted-foreground print:hidden">
          由 Value Agent 生成 · 数据源 AkShare（新浪/东财） · 不构成投资建议
        </footer>
      </div>
    </main>
  );
}
