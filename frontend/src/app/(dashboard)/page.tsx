import Link from "next/link";
import {
  ArrowRight,
  Bot,
  Cpu,
  History,
  Layers,
  Sparkles,
  TrendingUp,
  Workflow,
  type LucideIcon,
} from "lucide-react";

import { AgentIcon } from "@/components/agent-icon";
import { QuickStart } from "@/components/dashboard/quick-start";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { LOCAL_AGENTS } from "@/lib/agents/catalog";
import { resolveProfileIdentity } from "@/lib/profile";
import { getProfile } from "@/lib/profile-store";
import { createClient } from "@/lib/supabase/server";
import { getCurrentUser } from "@/lib/supabase/auth";
import { getWorkflow, WORKFLOWS } from "@/lib/workflows/catalog";
import { timeAgo } from "@/lib/time";
import { CONVERSATION_STATUS, type Conversation } from "@/types/conversation";
import type { CustomWorkflow } from "@/types/custom-workflow";

/** 未收藏任何智能体时展示的默认推荐 */
const DEFAULT_FEATURED = [
  "M2_financial_quality",
  "M4_valuation",
  "M8_safety_margin",
];

function StatLink({
  href,
  icon: Icon,
  label,
  value,
}: {
  href: string;
  icon: LucideIcon;
  label: string;
  value: number;
}) {
  return (
    <Link href={href} className="group">
      <Card className="rounded-xl transition-colors group-hover:border-foreground/20 group-hover:bg-muted/30">
        <CardContent className="flex items-center gap-3 p-4 md:p-5">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground transition-colors group-hover:text-primary">
            <Icon className="size-5" />
          </div>
          <div>
            <div className="text-2xl font-semibold tabular-nums">{value}</div>
            <div className="text-xs text-muted-foreground">{label}</div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

export default async function DashboardPage() {
  const user = await getCurrentUser();
  let name = "用户";

  let recent: Conversation[] = [];
  let conversationCount = 0;
  let custom: CustomWorkflow[] = [];
  let llmCount = 0;
  let favoriteIds: string[] = [];

  if (user) {
    const supabase = await createClient();
    try {
      const profile = await getProfile(user.id);
      name = resolveProfileIdentity({
        email: user.email,
        authDisplayName: user.user_metadata?.display_name as string | undefined,
        authAvatarUrl: user.user_metadata?.avatar_url as string | undefined,
        profile,
      }).name;
    } catch {
      name = resolveProfileIdentity({
        email: user.email,
        authDisplayName: user.user_metadata?.display_name as string | undefined,
      }).name;
    }
    try {
      const { data, count } = await supabase
        .from("conversations")
        .select("*", { count: "exact" })
        .eq("user_id", user.id)
        .order("updated_at", { ascending: false })
        .limit(4);
      recent = (data ?? []) as Conversation[];
      conversationCount = count ?? recent.length;
    } catch {
      // conversations 表未创建时忽略
    }
    try {
      const { data } = await supabase
        .from("custom_workflows")
        .select("*")
        .eq("user_id", user.id)
        .order("updated_at", { ascending: false });
      custom = (data ?? []) as CustomWorkflow[];
    } catch {
      // custom_workflows 表未创建时忽略
    }
    try {
      const { data } = await supabase
        .from("user_llm_settings")
        .select("id")
        .eq("user_id", user.id);
      llmCount = (data ?? []).length;
    } catch {
      // user_llm_settings 表未创建时忽略
    }
    try {
      const { data } = await supabase
        .from("agent_favorites")
        .select("agent_id")
        .eq("user_id", user.id);
      favoriteIds = (data ?? []).map((r) => r.agent_id);
    } catch {
      // agent_favorites 表未创建时忽略
    }
  }

  const featuredIds =
    favoriteIds.length > 0 ? favoriteIds : DEFAULT_FEATURED;
  const featured = featuredIds
    .map((id) => LOCAL_AGENTS.find((a) => a.id === id))
    .filter((a): a is (typeof LOCAL_AGENTS)[number] => Boolean(a))
    .slice(0, 4);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      {/* 问候 */}
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">你好，{name}</h1>
        <p className="text-sm text-muted-foreground">
          今天想分析哪家公司？输入代码、选一个工作流即可开始。
        </p>
      </div>

      {/* 快速分析 */}
      <QuickStart workflows={WORKFLOWS} custom={custom} />

      {/* 真实统计 */}
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
        <StatLink href="/agents" icon={Bot} label="智能体" value={LOCAL_AGENTS.length} />
        <StatLink href="/workflows" icon={Workflow} label="工作流" value={WORKFLOWS.length + custom.length} />
        <StatLink href="/conversations" icon={History} label="对话记录" value={conversationCount} />
        <StatLink href="/settings" icon={Cpu} label="LLM 服务商" value={llmCount} />
      </section>

      {/* 最近会话 + 快捷工作流 */}
      <section className="grid gap-4 md:grid-cols-2">
        <Card className="rounded-xl">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-base">最近会话</CardTitle>
              <CardDescription>继续上次的分析或查看历史记录</CardDescription>
            </div>
            {recent.length > 0 && (
              <Button asChild variant="ghost" size="sm" className="rounded-lg">
                <Link href="/conversations">
                  查看全部 <ArrowRight className="ml-1 size-3.5" />
                </Link>
              </Button>
            )}
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {recent.length === 0 ? (
              <div className="flex min-h-40 flex-col items-center justify-center gap-3 rounded-xl border border-dashed text-center">
                <div className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <History className="size-6" />
                </div>
                <div>
                  <p className="text-sm font-medium">还没有对话记录</p>
                  <p className="text-xs text-muted-foreground">
                    在上方输入代码发起一次分析，会话会出现在这里
                  </p>
                </div>
                <Button asChild variant="outline" size="sm" className="rounded-lg">
                  <Link href="/workflows/default">发起分析</Link>
                </Button>
              </div>
            ) : (
              recent.map((c) => {
                const wf = getWorkflow(c.workflow_id);
                const status =
                  CONVERSATION_STATUS[c.status] ?? CONVERSATION_STATUS.created;
                return (
                  <Link
                    key={c.id}
                    href={`/conversations/${c.id}`}
                    className="group flex items-center gap-3 rounded-xl border p-3 transition-colors hover:border-foreground/20 hover:bg-muted/40"
                  >
                    <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground transition-colors group-hover:text-primary">
                      <TrendingUp className="size-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium">
                          {c.company_name || c.company_code}
                        </span>
                        <Badge variant="outline" className={`gap-1 rounded-md px-1.5 py-0 text-[10px] ${status.className}`}>
                          {status.label}
                        </Badge>
                      </div>
                      <div className="truncate text-xs text-muted-foreground">
                        {c.company_code}
                        {wf ? ` · ${wf.name}` : ""} · {timeAgo(c.updated_at)}
                      </div>
                    </div>
                    <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
                  </Link>
                );
              })
            )}
          </CardContent>
        </Card>

        <Card className="rounded-xl">
          <CardHeader>
            <CardTitle className="text-base">快捷工作流</CardTitle>
            <CardDescription>从一个内置或自定义工作流开始</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {[...WORKFLOWS, ...custom].map((wf, i) => {
              const isCustom = i >= WORKFLOWS.length;
              const href = isCustom
                ? `/workflows/custom/${(wf as CustomWorkflow).id}`
                : `/workflows/${wf.id}`;
              const steps = isCustom
                ? (wf as CustomWorkflow).steps
                : wf.steps;
              return (
                <Link
                  key={href}
                  href={href}
                  className="group flex items-center justify-between rounded-xl border px-4 py-3 transition-colors hover:border-foreground/20 hover:bg-muted/40"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground transition-colors group-hover:text-primary">
                      <Layers className="size-4.5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2 text-sm font-medium">
                        {wf.name}
                        {isCustom && (
                          <Badge variant="secondary" className="rounded-md px-1.5 py-0 text-[10px]">
                            自定义
                          </Badge>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {steps.length} 个智能体 · {steps.map((s) => s.id).join(" → ")}
                      </div>
                    </div>
                  </div>
                  <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
                </Link>
              );
            })}
          </CardContent>
        </Card>
      </section>

      {/* 常用智能体 */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <Sparkles className="size-4 text-muted-foreground" />
            {favoriteIds.length > 0 ? "我关注的智能体" : "常用智能体"}
          </h2>
          <Button asChild variant="ghost" size="sm" className="rounded-lg">
            <Link href="/agents">
              全部智能体 <ArrowRight className="ml-1 size-3.5" />
            </Link>
          </Button>
        </div>
        <div className="grid gap-3 md:grid-cols-4 sm:grid-cols-2">
          {featured.map((agent) => (
            <Link key={agent.id} href={`/agents/${agent.id}`} className="group">
              <Card className="rounded-xl transition-all hover:-translate-y-0.5 hover:border-foreground/20 hover:shadow-sm">
                <CardContent className="flex items-start gap-3 p-4">
                  <div
                    className={`flex size-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-lg text-white shadow-sm ${agent.gradient}`}
                  >
                    <AgentIcon icon={agent.icon} className="size-5" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium">
                        {agent.name}
                      </span>
                      <Badge
                        variant="secondary"
                        className="rounded-md px-1.5 py-0 text-[10px]"
                      >
                        {agent.code}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {agent.tagline}
                    </p>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      {/* Footer note */}
      <p className="flex items-center justify-center gap-1.5 pb-4 text-xs text-muted-foreground">
        Value Agent · 数据源 AkShare（新浪/东财） · 免费额度内运行
      </p>
    </div>
  );
}
