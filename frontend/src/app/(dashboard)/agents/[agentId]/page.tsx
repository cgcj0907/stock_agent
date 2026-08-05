import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight, Boxes, Cpu, GitBranch, Layers } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FavoriteButton } from "@/components/agents/favorite-button";
import { fetchAgents } from "@/lib/agents/data";
import { findAgent } from "@/lib/agents/catalog";
import { getCurrentUser } from "@/lib/supabase/auth";
import { createClient } from "@/lib/supabase/server";

export default async function AgentDetailPage({
  params,
}: {
  params: Promise<{ agentId: string }>;
}) {
  const { agentId } = await params;
  const agents = await fetchAgents();
  const agent =
    agents.find((a) => a.id === agentId) ?? findAgent(agentId);
  if (!agent) notFound();

  const user = await getCurrentUser();
  let isFavorite = false;
  if (user) {
    try {
      const supabase = await createClient();
      const { data } = await supabase
        .from("agent_favorites")
        .select("agent_id")
        .eq("user_id", user.id)
        .eq("agent_id", agent.id)
        .maybeSingle();
      isFavorite = !!data;
    } catch {
      // 表未创建时忽略
    }
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      {/* 头部 */}
      <section className="relative overflow-hidden rounded-2xl border p-6 md:p-8">
        <div
          className={`pointer-events-none absolute inset-x-0 top-0 h-1.5 bg-gradient-to-r ${agent.gradient}`}
        />
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <div
              className={`flex size-16 items-center justify-center rounded-2xl bg-gradient-to-br text-3xl text-white shadow-md ${agent.gradient}`}
            >
              {agent.emoji}
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-2xl font-semibold tracking-tight">
                  {agent.name}
                </h1>
                <Badge variant="secondary" className="rounded-md">
                  {agent.code}
                </Badge>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {agent.tagline}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Layers className="size-3.5" />
                  {agent.category}
                </span>
                <span className="flex items-center gap-1">
                  <GitBranch className="size-3.5" />
                  v{agent.version}
                </span>
                {agent.requires_llm && (
                  <span className="flex items-center gap-1 text-violet-600 dark:text-violet-400">
                    <Cpu className="size-3.5" />
                    需要 LLM
                  </span>
                )}
              </div>
            </div>
          </div>
          <FavoriteButton agentId={agent.id} initial={isFavorite} />
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-3">
        {/* 描述 */}
        <Card className="rounded-2xl md:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">能力说明</CardTitle>
          </CardHeader>
          <CardContent className="text-sm leading-6 text-muted-foreground">
            {agent.description}
          </CardContent>
        </Card>

        {/* 依赖与元信息 */}
        <div className="flex flex-col gap-4">
          <Card className="rounded-2xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <GitBranch className="size-4 text-emerald-600 dark:text-emerald-400" />
                依赖输入
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {agent.inputs.length === 0 ? (
                <p className="text-xs text-muted-foreground">无前置依赖</p>
              ) : (
                agent.inputs.map((input) => (
                  <div key={input} className="flex items-center gap-2">
                    <Boxes className="size-3.5 text-muted-foreground" />
                    <Link
                      href={`/agents/${input}`}
                      className="text-xs font-mono text-emerald-600 underline-offset-4 hover:underline dark:text-emerald-400"
                    >
                      {input}
                    </Link>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card className="rounded-2xl">
            <CardContent className="flex flex-col gap-2 p-4">
              <Button asChild size="lg" className="rounded-xl">
                <Link href={`/workflows?agent=${agent.id}`}>
                  发起分析 <ArrowRight className="size-4" />
                </Link>
              </Button>
              <Button asChild variant="outline" className="rounded-xl">
                <Link href="/agents">返回广场</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
