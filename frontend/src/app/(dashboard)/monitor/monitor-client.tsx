"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Activity,
  BellRing,
  RadioTower,
  ShieldAlert,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { timeAgo } from "@/lib/time";
import { createClient } from "@/lib/supabase/client";
import type { MonitorHit } from "./page";

const SEVERITY: Record<string, { label: string; cls: string }> = {
  critical: {
    label: "风险",
    cls: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
  },
  warn: {
    label: "警告",
    cls: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  },
  info: {
    label: "提示",
    cls: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  },
};

const ACTION_LABEL: Record<string, string> = {
  watch: "观察",
  alert: "告警",
  action: "动作",
};

function sev(v: string | undefined) {
  return SEVERITY[v ?? ""] ?? SEVERITY.info;
}

function maskUrl(url: string): string {
  try {
    const u = new URL(url);
    return `${u.host}${u.pathname.slice(0, 24)}${u.pathname.length > 24 ? "…" : ""}`;
  } catch {
    return url.length > 32 ? `${url.slice(0, 32)}…` : url;
  }
}

export function MonitorClient({
  webhooks,
  rules: initialRules,
  hits,
  backendUnavailable,
}: {
  webhooks: Record<string, string>;
  rules: {
    id: string;
    session_id: string;
    company_code: string;
    company_name: string;
    rule_type: string;
    trigger: string;
    message: string;
    severity: string;
    action: string;
    active: boolean;
    created_at: string;
    canDelete: boolean;
  }[];
  hits: MonitorHit[];
  backendUnavailable: boolean;
}) {
  const [rules, setRules] = useState(initialRules);

  const channels = [
    { key: "feishu", label: "飞书", icon: BellRing },
    { key: "wechat", label: "企业微信", icon: RadioTower },
  ];

  /** 删除单条规则（RLS 保证只能删本人规则） */
  async function deleteRule(id: string) {
    try {
      const supabase = createClient();
      const { error } = await supabase
        .from("monitor_rules")
        .delete()
        .eq("id", id);
      if (error) throw error;
      setRules((prev) => prev.filter((r) => r.id !== id));
      toast.success("已删除该监控规则");
    } catch (e) {
      toast.error((e as Error).message || "删除失败（系统规则不可删除）");
    }
  }

  /** 清空某公司的本人规则（全局系统规则保留） */
  async function clearCompanyRules(code: string) {
    const targets = rules.filter((r) => r.company_code === code && r.canDelete);
    if (targets.length === 0) return;
    try {
      const supabase = createClient();
      const { error } = await supabase
        .from("monitor_rules")
        .delete()
        .in("id", targets.map((r) => r.id));
      if (error) throw error;
      setRules((prev) =>
        prev.filter((r) => !(r.company_code === code && r.canDelete)),
      );
      toast.success(`已清空「${targets[0]?.company_name || code}」的 ${targets.length} 条本人规则`);
    } catch (e) {
      toast.error((e as Error).message || "清空失败");
    }
  }

  const rulesByCompany = new Map<string, typeof rules>();
  for (const r of rules) {
    const key = r.company_code || r.session_id;
    const list = rulesByCompany.get(key) ?? [];
    list.push(r);
    rulesByCompany.set(key, list);
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">监控中心</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          查看已分析的公司的监控规则与每日价格命中记录
        </p>
      </div>

      {/* 告警渠道状态 */}
      <section className="grid gap-4 sm:grid-cols-2">
        {channels.map(({ key, label, icon: Icon }) => {
          const url = webhooks[key] ?? "";
          const configured = Boolean(url);
          return (
            <Card key={key} className="rounded-2xl">
              <CardHeader className="gap-2 pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Icon className="size-4 text-emerald-600 dark:text-emerald-400" />
                    {label} 通知
                  </CardTitle>
                  {configured ? (
                    <ShieldCheck className="size-5 text-emerald-500" />
                  ) : (
                    <ShieldAlert className="size-5 text-muted-foreground/50" />
                  )}
                </div>
                <CardDescription>
                  {configured ? (
                    <>
                      已配置 · <span className="font-mono">{maskUrl(url)}</span>
                    </>
                  ) : (
                    "未配置，监控命中将不会推送"
                  )}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild variant="outline" size="sm" className="rounded-lg">
                  <Link href="/settings">
                    {configured ? "管理" : "去配置"}
                  </Link>
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </section>

      {/* 命中时间线 */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center gap-2 text-base font-semibold">
          <Activity className="size-4 text-muted-foreground" />
          命中记录
        </div>
        <Card className="rounded-2xl">
          <CardContent className="p-4">
            {hits.length === 0 ? (
              <div className="flex flex-col items-center gap-1.5 py-8 text-center">
                <Activity className="size-6 text-muted-foreground/40" />
                <p className="text-sm font-medium">暂无命中记录</p>
                <p className="max-w-md text-xs text-muted-foreground">
                  {backendUnavailable
                    ? "后端未配置，无法加载每日监控命中。"
                    : "每日定时监控尚未触发命中；价格进入买入/卖出区间或触发规则时会记录在这里。"}
                </p>
              </div>
            ) : (
              <ol className="flex flex-col divide-y divide-border/60">
                {hits.map((h, i) => {
                  const s = sev(h.severity);
                  return (
                    <li key={i} className="flex items-start gap-3 py-2.5">
                      <Badge variant="outline" className={`shrink-0 rounded-md ${s.cls}`}>
                        {s.label}
                      </Badge>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm">
                          <span className="font-medium">
                            {h.company || h.company_code || "—"}
                          </span>
                          <span className="ml-2 text-muted-foreground">
                            {h.message || h.rule_type}
                          </span>
                        </div>
                        {h.occurred_at && (
                          <div className="mt-0.5 text-xs text-muted-foreground">
                            {timeAgo(h.occurred_at)}
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </CardContent>
        </Card>
      </section>

      {/* 监控规则 */}
      <section className="flex flex-col gap-3">
        <div className="flex items-center gap-2 text-base font-semibold">
          <BellRing className="size-4 text-muted-foreground" />
          监控规则
          <Badge variant="secondary" className="rounded-md text-[10px]">
            {rules.length}
          </Badge>
        </div>
        {rulesByCompany.size === 0 ? (
          <Card className="rounded-2xl border-dashed">
            <CardContent className="flex flex-col items-center gap-1.5 py-10 text-center">
              <BellRing className="size-6 text-muted-foreground/40" />
              <p className="text-sm font-medium">还没有监控规则</p>
              <p className="max-w-md text-xs text-muted-foreground">
                完成一次包含 M11 监控模块的分析后，规则会出现在这里
              </p>
            </CardContent>
          </Card>
        ) : (
          Array.from(rulesByCompany.entries()).map(([code, list]) => {
            const deletableCount = list.filter((r) => r.canDelete).length;
            return (
            <Card key={code} className="rounded-2xl">
              <CardHeader className="flex-row items-center justify-between pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  {list[0]?.company_name || code}
                  <Badge variant="secondary" className="rounded-md font-mono text-[10px]">
                    {code}
                  </Badge>
                </CardTitle>
                {deletableCount > 0 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 rounded-lg px-2 text-xs text-muted-foreground hover:text-destructive"
                    onClick={() => {
                      if (
                        window.confirm(
                          `清空「${list[0]?.company_name || code}」的 ${deletableCount} 条本人监控规则？系统规则会保留。`,
                        )
                      ) {
                        void clearCompanyRules(code);
                      }
                    }}
                  >
                    <Trash2 className="size-3.5" />
                    清空
                  </Button>
                )}
              </CardHeader>
              <CardContent className="flex flex-col divide-y divide-border/60">
                {list.map((r) => {
                  const s = sev(r.severity);
                  return (
                    <div key={r.id} className="flex items-start gap-2 py-2 text-xs">
                      <Badge variant="outline" className={`shrink-0 rounded-md ${s.cls}`}>
                        {s.label}
                      </Badge>
                      <div className="min-w-0 flex-1 leading-5">
                        <span className="text-foreground/85">{r.message || r.rule_type}</span>
                        {r.trigger && (
                          <span className="ml-1 text-muted-foreground">（{r.trigger}）</span>
                        )}
                        {!r.canDelete && (
                          <span className="ml-1 text-[10px] text-muted-foreground/60">
                            · 系统规则
                          </span>
                        )}
                      </div>
                      <Badge variant="outline" className="shrink-0 rounded-md text-muted-foreground">
                        {ACTION_LABEL[r.action] ?? r.action}
                      </Badge>
                      {r.canDelete && (
                        <button
                          type="button"
                          onClick={() => {
                            if (window.confirm("删除这条监控规则？")) {
                              void deleteRule(r.id);
                            }
                          }}
                          aria-label="删除规则"
                          title="删除规则"
                          className="shrink-0 rounded-md p-1 text-muted-foreground/60 transition-colors hover:bg-red-50 hover:text-destructive dark:hover:bg-red-950/40"
                        >
                          <Trash2 className="size-3.5" />
                        </button>
                      )}
                    </div>
                  );
                })}
              </CardContent>
            </Card>
            );
          })
        )}
      </section>
    </div>
  );
}
