"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import { useQuery } from "@tanstack/react-query";
import {
  BellRing,
  Bot,
  History,
  LayoutDashboard,
  Search,
  Settings,
  TrendingUp,
  Workflow,
  type LucideIcon,
} from "lucide-react";

import { AgentIcon } from "@/components/agent-icon";
import { createClient } from "@/lib/supabase/client";
import { LOCAL_AGENTS } from "@/lib/agents/catalog";
import { getWorkflow, WORKFLOWS } from "@/lib/workflows/catalog";
import { timeAgo } from "@/lib/time";
import type { Conversation } from "@/types/conversation";
import type { CustomWorkflow } from "@/types/custom-workflow";

/** AppHeader 顶部搜索框点击时派发该事件打开面板 */
export const OPEN_PALETTE_EVENT = "va:open-palette";

const ITEM_CLS =
  "flex cursor-default select-none items-center gap-2.5 rounded-md px-2 py-2 text-sm outline-none " +
  "data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground " +
  "[&[aria-selected=true]]:bg-accent [&[aria-selected=true]]:text-accent-foreground";

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  // 会话与自定义工作流（TanStack Query 缓存，60s 内不重复拉取）
  const { data: paletteData } = useQuery({
    queryKey: ["palette", "recent"],
    queryFn: async (): Promise<{
      recent: Conversation[];
      custom: CustomWorkflow[];
    }> => {
      try {
        const supabase = createClient();
        const {
          data: { user },
        } = await supabase.auth.getUser();
        if (!user) return { recent: [], custom: [] };
        const [convRes, cwfRes] = await Promise.all([
          supabase
            .from("conversations")
            .select("*")
            .eq("user_id", user.id)
            .order("updated_at", { ascending: false })
            .limit(8),
          supabase
            .from("custom_workflows")
            .select("*")
            .eq("user_id", user.id)
            .order("updated_at", { ascending: false }),
        ]);
        return {
          recent: (convRes.data ?? []) as Conversation[],
          custom: (cwfRes.data ?? []) as CustomWorkflow[],
        };
      } catch {
        // 表未创建时忽略
        return { recent: [], custom: [] };
      }
    },
    staleTime: 60_000,
  });
  const recent = paletteData?.recent ?? [];
  const custom = paletteData?.custom ?? [];

  // ⌘K / Ctrl+K 唤起 + 顶部搜索框点击
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_PALETTE_EVENT, () => setOpen(true));
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_PALETTE_EVENT, () => setOpen(true));
    };
  }, []);

  function run(href: string) {
    setOpen(false);
    router.push(href);
  }

  const pageItems: { id: string; label: string; sub: string; href: string; icon: LucideIcon }[] = [
    { id: "page-dash", label: "仪表盘", sub: "工作台", href: "/", icon: LayoutDashboard },
    { id: "page-agents", label: "智能体广场", sub: "M1–M11 模块目录", href: "/agents", icon: Bot },
    { id: "page-workflows", label: "工作流", sub: "发起分析", href: "/workflows", icon: Workflow },
    { id: "page-conversations", label: "对话记录", sub: "历史分析", href: "/conversations", icon: History },
    { id: "page-monitor", label: "监控中心", sub: "规则与命中", href: "/monitor", icon: BellRing },
    { id: "page-settings", label: "通用设置", sub: "LLM 与个人资料", href: "/settings", icon: Settings },
  ];

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[12vh]">
          <div
            className="absolute inset-0 bg-slate-900/45 backdrop-blur-[2px]"
            onClick={() => setOpen(false)}
          />
          <Command
            loop
            className="relative z-10 w-full max-w-xl overflow-hidden rounded-2xl border border-border bg-popover text-popover-foreground shadow-2xl"
            onKeyDown={(e) => {
              if (e.key === "Escape") setOpen(false);
            }}
          >
            <div className="flex items-center gap-2.5 border-b border-border px-4">
              <Search className="size-4 shrink-0 text-muted-foreground" />
              <Command.Input
                autoFocus
                placeholder="搜索公司、会话、工作流、模块…"
                className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              />
              <kbd className="shrink-0 rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                esc
              </kbd>
            </div>

            <Command.List className="max-h-[min(60vh,420px)] overflow-y-auto p-1.5">
              <Command.Empty className="py-10 text-center text-sm text-muted-foreground">
                没有匹配的结果，试试公司代码 / 模块名 / 页面名
              </Command.Empty>

              {recent.length > 0 && (
                <Command.Group heading="最近分析">
                  {recent.map((c) => {
                    const wf = getWorkflow(c.workflow_id);
                    return (
                      <Command.Item
                        key={c.id}
                        value={`${c.company_name} ${c.company_code} ${c.session_id} 会话 分析`}
                        onSelect={() => run(`/conversations/${c.id}`)}
                        className={ITEM_CLS}
                      >
                        <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                          <TrendingUp className="size-4" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium">
                            {c.company_name || c.company_code}
                          </div>
                          <div className="truncate text-xs text-muted-foreground">
                            {c.company_code}
                            {wf ? ` · ${wf.name}` : ""} · {timeAgo(c.updated_at)}
                          </div>
                        </div>
                      </Command.Item>
                    );
                  })}
                </Command.Group>
              )}

              <Command.Group heading="工作流">
                {[...WORKFLOWS, ...custom].map((wf, i) => {
                  const isCustom = i >= WORKFLOWS.length;
                  const href = isCustom
                    ? `/workflows/custom/${(wf as CustomWorkflow).id}`
                    : `/workflows/${wf.id}`;
                  const steps = isCustom ? (wf as CustomWorkflow).steps : wf.steps;
                  return (
                    <Command.Item
                      key={href}
                      value={`${wf.name} 工作流 ${steps.map((s) => s.id).join(" ")}`}
                      onSelect={() => run(href)}
                      className={ITEM_CLS}
                    >
                      <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-violet-50 text-violet-600">
                        <Workflow className="size-4" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">
                          {wf.name}
                          {isCustom && (
                            <span className="ml-1.5 text-[10px] text-muted-foreground">
                              自定义
                            </span>
                          )}
                        </div>
                        <div className="truncate text-xs text-muted-foreground">
                          {steps.length} 个智能体 · {steps.map((s) => s.id).join(" → ")}
                        </div>
                      </div>
                    </Command.Item>
                  );
                })}
              </Command.Group>

              <Command.Group heading="智能体模块">
                {LOCAL_AGENTS.map((a) => (
                  <Command.Item
                    key={a.id}
                    value={`${a.code} ${a.name} ${a.tagline} 智能体 模块`}
                    onSelect={() => run(`/agents/${a.id}`)}
                    className={ITEM_CLS}
                  >
                    <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-foreground/70">
                      <AgentIcon icon={a.icon} className="size-4" />
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">
                      {a.code} {a.name}
                    </span>
                    <span className="truncate text-xs text-muted-foreground">
                      {a.tagline}
                    </span>
                  </Command.Item>
                ))}
              </Command.Group>

              <Command.Group heading="页面">
                {pageItems.map((p) => (
                  <Command.Item
                    key={p.id}
                    value={`${p.label} ${p.sub} 页面 跳转`}
                    onSelect={() => run(p.href)}
                    className={ITEM_CLS}
                  >
                    <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-foreground/70">
                      <p.icon className="size-4" />
                    </span>
                    <span className="flex-1 text-sm font-medium">{p.label}</span>
                    <span className="text-xs text-muted-foreground">{p.sub}</span>
                  </Command.Item>
                ))}
              </Command.Group>
            </Command.List>

            <div className="flex items-center gap-4 border-t border-border bg-muted/40 px-4 py-2 text-[11px] text-muted-foreground">
              <span className="flex items-center gap-1">
                <kbd className="rounded border border-border bg-card px-1 font-mono">↑↓</kbd>
                导航
              </span>
              <span className="flex items-center gap-1">
                <kbd className="rounded border border-border bg-card px-1 font-mono">↵</kbd>
                打开
              </span>
              <span className="flex items-center gap-1">
                <kbd className="rounded border border-border bg-card px-1 font-mono">esc</kbd>
                关闭
              </span>
              <span className="ml-auto">⌘K 随时唤起</span>
            </div>
          </Command>
        </div>
      )}
    </>
  );
}
