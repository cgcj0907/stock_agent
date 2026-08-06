"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowRight, Bot, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { AgentIcon } from "@/components/agent-icon";
import { FavoriteButton } from "@/components/agents/favorite-button";
import type { AgentInfo } from "@/lib/agents/catalog";

export function AgentsClient({
  agents,
  initialFavorites,
}: {
  agents: AgentInfo[];
  initialFavorites: string[];
}) {
  const [query, setQuery] = React.useState("");
  const [category, setCategory] = React.useState("全部");
  const favorites = React.useMemo(
    () => new Set(initialFavorites),
    [initialFavorites]
  );

  const categories = React.useMemo(
    () => ["全部", ...Array.from(new Set(agents.map((a) => a.category)))],
    [agents]
  );

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    return agents.filter((a) => {
      const matchCategory = category === "全部" || a.category === category;
      const matchQuery =
        !q ||
        a.name.toLowerCase().includes(q) ||
        a.tagline.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q) ||
        a.code.toLowerCase().includes(q) ||
        a.id.toLowerCase().includes(q);
      return matchCategory && matchQuery;
    });
  }, [agents, query, category]);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">智能体广场</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {agents.length} 个专业分析智能体，可自由编排成工作流
        </p>
      </div>

      <div className="flex flex-col gap-3 md:flex-row md:items-center">
        <div className="relative md:w-80">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="搜索智能体 / 能力 / M编号…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="h-9 rounded-xl bg-muted/50 pl-8"
          />
        </div>
        <div className="flex gap-1.5 overflow-x-auto pb-1">
          {categories.map((c) => (
            <Button
              key={c}
              variant={category === c ? "default" : "outline"}
              size="sm"
              className="rounded-full px-3 text-xs"
              onClick={() => setCategory(c)}
            >
              {c}
            </Button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <Card className="rounded-2xl border-dashed">
          <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
            <div className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <Bot className="size-6" />
            </div>
            <div>
              <p className="text-sm font-medium">没有匹配的智能体</p>
              <p className="text-xs text-muted-foreground">
                换个关键词或分类试试
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((agent) => (
            <Card
              key={agent.id}
              className="group relative overflow-hidden rounded-2xl transition-all hover:-translate-y-0.5 hover:shadow-md"
            >
              <div
                className={`h-1.5 w-full bg-gradient-to-r ${agent.gradient}`}
              />
              <CardContent className="flex flex-col gap-3 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-3">
                    <div
                      className={`flex size-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-lg text-white shadow-sm ${agent.gradient}`}
                    >
                      <AgentIcon icon={agent.icon} className="size-6" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate text-sm font-semibold">
                          {agent.name}
                        </span>
                        <Badge
                          variant="secondary"
                          className="rounded-md px-1.5 py-0 text-[10px]"
                        >
                          {agent.code}
                        </Badge>
                      </div>
                      <p className="truncate text-xs text-muted-foreground">
                        {agent.tagline}
                      </p>
                    </div>
                  </div>
                  <FavoriteButton
                    agentId={agent.id}
                    initial={favorites.has(agent.id)}
                  />
                </div>

                <p className="line-clamp-2 text-xs leading-5 text-muted-foreground">
                  {agent.description}
                </p>

                <div className="mt-auto flex items-center gap-2 pt-1">
                  {agent.requires_llm && (
                    <Badge
                      variant="outline"
                      className="rounded-md border-violet-200 bg-violet-50 text-violet-600 dark:border-violet-800 dark:bg-violet-950/60 dark:text-violet-300"
                    >
                      LLM
                    </Badge>
                  )}
                  {agent.inputs.length > 0 && (
                    <Badge
                      variant="outline"
                      className="rounded-md text-muted-foreground"
                    >
                      依赖 {agent.inputs.length} 个
                    </Badge>
                  )}
                  <Button
                    asChild
                    variant="ghost"
                    size="sm"
                    className="ml-auto rounded-lg text-xs"
                  >
                    <Link href={`/agents/${agent.id}`}>
                      详情
                      <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
                    </Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
