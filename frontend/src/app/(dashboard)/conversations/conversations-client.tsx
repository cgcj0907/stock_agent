"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { History, Search, Trash2, TrendingUp } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createClient } from "@/lib/supabase/client";
import { api } from "@/lib/api";
import { getWorkflow } from "@/lib/workflows/catalog";
import { timeAgo } from "@/lib/time";
import {
  CONVERSATION_STATUS,
  type Conversation,
} from "@/types/conversation";

const STATUS_FILTERS = ["全部", "进行中", "已完成", "失败"] as const;

const PAGE_SIZE = 15;

/** 日期分组：今天 / 昨天 / 更早 */
function dateBucket(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "更早";
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const t = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diffDays = Math.round((startOfToday - t) / 86_400_000);
  if (diffDays <= 0) return "今天";
  if (diffDays === 1) return "昨天";
  return "更早";
}

const BUCKET_ORDER = ["今天", "昨天", "更早"] as const;

export function ConversationsClient({
  initial,
}: {
  initial: Conversation[];
}) {
  const router = useRouter();
  const [query, setQuery] = React.useState("");
  const [statusFilter, setStatusFilter] =
    React.useState<(typeof STATUS_FILTERS)[number]>("全部");
  const [visibleCount, setVisibleCount] = React.useState(PAGE_SIZE);

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    return initial.filter((c) => {
      const matchStatus =
        statusFilter === "全部" ||
        CONVERSATION_STATUS[c.status]?.label === statusFilter;
      const matchQuery =
        !q ||
        c.company_code.toLowerCase().includes(q) ||
        c.company_name.toLowerCase().includes(q) ||
        c.session_id.toLowerCase().includes(q);
      return matchStatus && matchQuery;
    });
  }, [initial, query, statusFilter]);

  const visible = filtered.slice(0, visibleCount);
  const groups = React.useMemo(() => {
    const map = new Map<string, typeof visible>();
    for (const c of visible) {
      const key = dateBucket(c.updated_at);
      const list = map.get(key) ?? [];
      list.push(c);
      map.set(key, list);
    }
    return BUCKET_ORDER.map((k) => ({ bucket: k, items: map.get(k) ?? [] })).filter(
      (g) => g.items.length > 0,
    );
  }, [visible]);

  async function handleDelete(c: Conversation) {
    if (!window.confirm(`删除「${c.company_name || c.company_code}」的对话记录？`)) {
      return;
    }
    try {
      // 后端会话（尽力而为）
      try {
        await api(`/api/sessions/${c.session_id}`, { method: "DELETE" });
      } catch {
        // 后端不可用或会话已删除，忽略
      }
      const supabase = createClient();
      const { error } = await supabase
        .from("conversations")
        .delete()
        .eq("id", c.id);
      if (error) throw new Error(error.message);
      toast.success("已删除");
      router.refresh();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">对话记录</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          查看历史分析会话，继续或重新运行
        </p>
      </div>

      <div className="flex flex-col gap-3 md:flex-row md:items-center">
        <div className="relative md:w-80">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="搜索公司 / 代码 / 会话…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setVisibleCount(PAGE_SIZE);
            }}
            className="h-9 rounded-xl bg-muted/50 pl-8"
          />
        </div>
        <div className="flex gap-1.5">
          {STATUS_FILTERS.map((f) => (
            <Button
              key={f}
              variant={statusFilter === f ? "default" : "outline"}
              size="sm"
              className="rounded-full px-3 text-xs"
              onClick={() => {
                setStatusFilter(f);
                setVisibleCount(PAGE_SIZE);
              }}
            >
              {f}
            </Button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <Card className="rounded-2xl border-dashed">
          <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
            <div className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <History className="size-6" />
            </div>
            <div>
              <p className="text-sm font-medium">
                {initial.length === 0 ? "还没有对话记录" : "没有匹配的对话"}
              </p>
              <p className="text-xs text-muted-foreground">
                {initial.length === 0
                  ? "在「工作流」中发起一次分析后，记录会出现在这里"
                  : "换个关键词或筛选条件试试"}
              </p>
            </div>
            {initial.length === 0 && (
              <Button asChild variant="outline" size="sm" className="rounded-lg">
                <Link href="/workflows">去发起分析</Link>
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col gap-4">
          {groups.map(({ bucket, items }) => (
            <section key={bucket} className="flex flex-col gap-2.5">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {bucket}
              </h2>
              {items.map((c) => {
                const wf = getWorkflow(c.workflow_id);
                const status = CONVERSATION_STATUS[c.status] ?? CONVERSATION_STATUS.created;
                const label = c.company_name || c.company_code;
                return (
                  <div
                    key={c.id}
                    className="group flex items-center gap-3 rounded-2xl border bg-card px-4 py-3 transition-shadow hover:shadow-sm"
                  >
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 text-white shadow-sm">
                      <TrendingUp className="size-5" />
                    </div>
                    <Link
                      href={`/conversations/${c.id}`}
                      className="min-w-0 flex-1"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium">{label}</span>
                        <Badge variant="secondary" className="rounded-md font-mono text-[10px]">
                          {c.company_code}
                        </Badge>
                        {wf && (
                          <Badge variant="outline" className="rounded-md text-[10px]">
                            {wf.name}
                          </Badge>
                        )}
                      </div>
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        {timeAgo(c.updated_at)} · {c.session_id.slice(0, 18)}…
                      </div>
                    </Link>
                    <Badge variant="outline" className={`gap-1 rounded-md ${status.className}`}>
                      {status.label}
                    </Badge>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8 rounded-lg text-muted-foreground opacity-60 transition-opacity hover:text-destructive group-hover:opacity-100"
                      onClick={() => handleDelete(c)}
                      aria-label="删除"
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                );
              })}
            </section>
          ))}
          {filtered.length > visibleCount && (
            <Button
              variant="outline"
              size="sm"
              className="w-full rounded-xl"
              onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
            >
              加载更多（{filtered.length - visibleCount} 条）
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
