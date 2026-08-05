"use client";

import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { SourceLinks } from "@/components/workflow/source-links";
import type { ModuleResultView } from "@/hooks/use-workflow-run";

const DIM_LABELS: Record<string, string> = {
  business_moat: "护城河",
  financial_quality: "财务质量",
  growth_prosperity: "成长景气",
  valuation_margin: "估值边际",
  governance_risk: "治理风险",
};
const DIM_BARS: Record<string, string> = {
  business_moat: "bg-emerald-500",
  financial_quality: "bg-sky-500",
  growth_prosperity: "bg-violet-500",
  valuation_margin: "bg-amber-500",
  governance_risk: "bg-rose-500",
};

const SEVERITY: Record<string, { label: string; cls: string }> = {
  info: {
    label: "提示",
    cls: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  },
  warn: {
    label: "警告",
    cls: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  },
  critical: {
    label: "风险",
    cls: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
  },
};

const STATUS_DOT: Record<string, string> = {
  done: "bg-emerald-500",
  failed: "bg-red-500",
  skipped: "bg-amber-500",
  running: "bg-emerald-400 animate-pulse",
  pending: "bg-muted-foreground/40",
};

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isFinite(v) ? String(v) : "—";
  return String(v);
}

function fmtPct(v: unknown): string {
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(0)}%`;
}

export function MemoCard({
  companyCode,
  companyName,
  workflowId,
  status,
  moduleResults,
  sessionId,
  createdAt,
  assumptions,
}: {
  companyCode: string;
  companyName: string;
  workflowId: string;
  status: string;
  moduleResults: Record<string, ModuleResultView>;
  sessionId?: string;
  createdAt?: string;
  assumptions?: Record<string, unknown>;
}) {
  const m10 = moduleResults.M10_decision?.outputs as
    | { conclusion?: string; total?: number; position?: number; dimensions?: Record<string, number>; vetoed?: string[] }
    | undefined;
  const m4 = moduleResults.M4_valuation?.outputs as
    | {
        business_type?: string;
        intrinsic_value?: { low?: number; high?: number; mid?: number };
        current_price?: number;
        methods?: Record<string, { value?: number | null; low?: number | null; high?: number | null; note?: string }>;
      }
    | undefined;
  const m8 = moduleResults.M8_safety_margin?.outputs as
    | { buy_price?: number; sell_price?: number; status?: string; discount?: number; required_discount?: number }
    | undefined;
  const m2 = moduleResults.M2_financial_quality?.outputs as
    | { metrics?: Record<string, unknown>; signals?: string[]; summary?: Record<string, unknown> }
    | undefined;
  const m11 = moduleResults.M11_monitor?.outputs as
    | { monitor_rules?: { severity?: string; description?: string; trigger?: string }[] }
    | undefined;

  const iv = m4?.intrinsic_value;
  const dims = m10?.dimensions ?? {};
  const rules = m11?.monitor_rules ?? [];
  const metrics = m2?.metrics ?? {};

  const bandPct =
    iv && iv.low != null && iv.high != null && iv.high > iv.low && m4?.current_price != null
      ? Math.max(
          0,
          Math.min(100, ((m4.current_price - iv.low) / (iv.high - iv.low)) * 100)
        )
      : null;

  const dateStr = createdAt
    ? new Date(createdAt).toLocaleDateString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      })
    : null;

  const doneModules = Object.entries(moduleResults)
    .filter(([, r]) => r.status !== "pending")
    .sort(([a], [b]) => a.localeCompare(b));

  return (
    <Card className="overflow-hidden rounded-2xl">
      {/* Hero */}
      <div className="relative bg-gradient-to-r from-emerald-600 via-teal-600 to-teal-700 px-6 py-6 text-white">
        <div className="pointer-events-none absolute inset-0 opacity-10 bg-grid-faint" />
        <div className="relative flex flex-wrap items-center gap-2.5">
          <h3 className="text-xl font-bold tracking-wide">{companyName || companyCode}</h3>
          <Badge className="rounded-full border border-white/30 bg-white/15 text-white">
            {companyCode}
          </Badge>
          <Badge className="ml-auto rounded-full bg-white text-emerald-700 shadow-sm">
            {status === "completed" ? "已完成" : status}
          </Badge>
        </div>
        <div className="relative mt-4 flex flex-wrap items-end gap-7">
          {m10?.total != null && (
            <div>
              <div className="text-3xl font-extrabold tabular-nums leading-none">
                {m10.total}
              </div>
              <div className="mt-1 text-xs text-white/80">加权总分</div>
            </div>
          )}
          {m10?.position != null && (
            <div>
              <div className="text-3xl font-extrabold tabular-nums leading-none">
                {fmtPct(m10.position)}
              </div>
              <div className="mt-1 text-xs text-white/80">建议仓位</div>
            </div>
          )}
          {iv?.mid != null && (
            <div>
              <div className="text-3xl font-extrabold tabular-nums leading-none">
                {iv.mid}
              </div>
              <div className="mt-1 text-xs text-white/80">内在价值中值（元）</div>
            </div>
          )}
          {dateStr && <div className="ml-auto text-xs text-white/70">{dateStr}</div>}
        </div>
      </div>

      {/* meta */}
      <div className="flex flex-wrap gap-2 border-b bg-muted/30 px-6 py-3">
        {sessionId && (
          <span className="rounded-lg border bg-card px-2.5 py-1 font-mono text-[11px] text-muted-foreground">
            会话 <b className="text-foreground">{sessionId.slice(0, 18)}…</b>
          </span>
        )}
        <span className="rounded-lg border bg-card px-2.5 py-1 font-mono text-[11px] text-muted-foreground">
          工作流 <b className="text-foreground">{workflowId}</b>
        </span>
        {m4?.business_type && (
          <span className="rounded-lg border bg-card px-2.5 py-1 text-[11px] text-muted-foreground">
            类型 <b className="text-foreground">{m4.business_type}</b>
          </span>
        )}
      </div>

      {/* 执行摘要 */}
      {(m10 || iv) && (
        <div className="border-b px-6 py-5">
          <SectionTitle icon="📋" title="执行摘要" />
          {m10?.conclusion && (
            <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 dark:border-emerald-800 dark:bg-emerald-950/40">
              <span className="text-sm font-bold text-emerald-800 dark:text-emerald-300">
                结论：{m10.conclusion}
              </span>
              {m10?.vetoed && m10.vetoed.length > 0 && (
                <span className="text-xs text-red-600 dark:text-red-400">
                  ⚠️ 触发否决：{m10.vetoed.join("、")}
                </span>
              )}
            </div>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            {Object.keys(dims).length > 0 && (
              <div className="rounded-xl border p-4">
                <div className="mb-3 text-xs font-semibold text-muted-foreground">
                  五维评分
                </div>
                {Object.entries(dims).map(([k, v]) => (
                  <div key={k} className="mb-2 flex items-center gap-2 text-xs">
                    <span className="w-[74px] text-muted-foreground">
                      {DIM_LABELS[k] ?? k}
                    </span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                      <div
                        className={`h-full rounded-full ${DIM_BARS[k] ?? "bg-emerald-500"}`}
                        style={{ width: `${Math.max(0, Math.min(100, v))}%` }}
                      />
                    </div>
                    <span className="w-9 text-right font-semibold tabular-nums">
                      {v}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {iv && (
              <div className="rounded-xl border p-4">
                <div className="mb-3 text-xs font-semibold text-muted-foreground">
                  内在价值区间
                </div>
                <div className="relative mx-1 mt-5 h-2 rounded-full bg-gradient-to-r from-emerald-200 via-emerald-300 to-amber-300">
                  {bandPct != null && (
                    <span
                      className="absolute -top-[5px] h-[18px] w-[3px] rounded bg-sky-500 shadow-[0_0_0_3px_#e0f2fe]"
                      style={{ left: `calc(${bandPct}% - 1px)` }}
                      title={`现价 ${m4.current_price}`}
                    />
                  )}
                </div>
                <div className="mt-2 flex justify-between text-[11px] text-muted-foreground tabular-nums">
                  <span>低 {iv.low}</span>
                  <span>中 {iv.mid}</span>
                  <span>高 {iv.high}</span>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 dark:border-emerald-800 dark:bg-emerald-950/40">
                    <div className="text-[11px] text-emerald-700 dark:text-emerald-300">
                      买入区间
                    </div>
                    <div className="text-lg font-extrabold tabular-nums text-emerald-700 dark:text-emerald-300">
                      ≤ {m8?.buy_price ?? "—"}
                    </div>
                  </div>
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-800 dark:bg-amber-950/40">
                    <div className="text-[11px] text-amber-700 dark:text-amber-300">
                      卖出区间
                    </div>
                    <div className="text-lg font-extrabold tabular-nums text-amber-700 dark:text-amber-300">
                      ≥ {m8?.sell_price ?? "—"}
                    </div>
                  </div>
                </div>
                {m8?.status && (
                  <div className="mt-2 text-[11px] text-muted-foreground">
                    安全边际：{m8.status}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 模块结果 */}
      {doneModules.length > 0 && (
        <div className="border-b px-6 py-5">
          <SectionTitle icon="📊" title="模块执行结果" />
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b text-left text-[11px] text-muted-foreground">
                  <th className="py-2 pr-3 font-semibold">模块</th>
                  <th className="py-2 pr-3 font-semibold">状态</th>
                  <th className="py-2 pr-3 font-semibold">评分</th>
                  <th className="py-2 pr-3 font-semibold">证据</th>
                </tr>
              </thead>
              <tbody>
                {doneModules.map(([id, r]) => (
                  <tr key={id} className="border-b last:border-0">
                    <td className="py-2 pr-3 font-medium">
                      {MODULE_SHORT[id] ?? id}
                    </td>
                    <td className="py-2 pr-3">
                      <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                        <span className={`size-2 rounded-full ${STATUS_DOT[r.status] ?? "bg-muted-foreground/40"}`} />
                        {STATUS_LABEL[r.status] ?? r.status}
                      </span>
                    </td>
                    <td className="py-2 pr-3 tabular-nums">
                      {r.score != null ? (
                        <span className="inline-flex items-center gap-2">
                          <span className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
                            <span
                              className="block h-full rounded-full bg-emerald-500"
                              style={{ width: `${Math.max(0, Math.min(100, r.score))}%` }}
                            />
                          </span>
                          {Math.round(r.score)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-2 text-muted-foreground tabular-nums">
                      {r.evidence.length}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* M2 财务质量 */}
      {metrics && Object.keys(metrics).length > 0 && (
        <div className="border-b px-6 py-5">
          <SectionTitle icon="🧮" title="财务质量（M2）" />
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Kpi label="ROE 最新" value={metrics.roe_latest != null ? `${fmt(metrics.roe_latest)}%` : "—"} />
            <Kpi label="ROE 均值" value={metrics.roe_mean != null ? `${fmt(metrics.roe_mean)}%` : "—"} />
            <Kpi label="净利率" value={metrics.net_margin != null ? `${fmt(metrics.net_margin)}%` : "—"} />
            <Kpi label="负债率" value={metrics.debt_to_assets_latest != null ? `${fmtPct(metrics.debt_to_assets_latest)}` : "—"} />
          </div>
          {m2?.signals && m2.signals.length > 0 && (
            <ul className="mt-3 flex flex-col gap-1.5 text-xs text-muted-foreground">
              {m2.signals.map((sig, i) => (
                <li key={i}>⚠️ {sig}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* M4 方法 */}
      {m4?.methods && Object.keys(m4.methods).length > 0 && (
        <div className="border-b px-6 py-5">
          <SectionTitle icon="💹" title="估值方法（M4）" />
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {Object.entries(m4.methods).map(([k, m]) => (
              <div key={k} className="rounded-xl border bg-muted/30 px-3 py-2">
                <div className="text-[11px] text-muted-foreground">{METHOD_LABELS[k] ?? k}</div>
                <div className="mt-0.5 text-base font-bold tabular-nums">
                  {m.value ?? "—"}
                </div>
                {m.note && <div className="mt-0.5 text-[10px] text-muted-foreground">{m.note}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* M11 监控规则 */}
      {rules.length > 0 && (
        <div className="border-b px-6 py-5">
          <SectionTitle icon="📡" title="监控规则（M11）" />
          <div className="flex flex-col gap-2">
            {rules.map((r, i) => {
              const sev = SEVERITY[r.severity ?? "info"] ?? SEVERITY.info;
              return (
                <div
                  key={i}
                  className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border bg-card px-3.5 py-2.5 text-xs"
                >
                  <Badge variant="outline" className={`rounded-full ${sev.cls}`}>
                    {sev.label}
                  </Badge>
                  <span className="font-medium">{r.description}</span>
                  <span className="ml-auto text-[11px] text-muted-foreground">
                    触发：{r.trigger}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 假设 */}
      {assumptions && Object.keys(assumptions).length > 0 && (
        <div className="border-b px-6 py-5">
          <SectionTitle icon="⚙️" title="假设（assumptions）" />
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {Object.entries(assumptions).map(([k, v]) => (
              <div key={k} className="rounded-xl border bg-card px-3 py-2">
                <div className="text-[11px] text-muted-foreground">{k}</div>
                <div className="mt-0.5 text-sm font-bold tabular-nums">{fmt(v)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* footer */}
      <div className="flex flex-col gap-2 px-6 py-4 text-[11px] text-muted-foreground">
        <SourceLinks code={companyCode} />
        <div>
          数据快照与模块证据见各模块输出 · 本备忘录不构成投资建议
        </div>
      </div>
    </Card>
  );
}

const MODULE_SHORT: Record<string, string> = {
  M1_business_model: "M1 商业模式认知",
  M2_financial_quality: "M2 财务质量",
  M3_growth: "M3 成长与再投资",
  M4_valuation: "M4 估值引擎",
  M5_moat: "M5 护城河",
  M6_governance: "M6 治理与资本配置",
  M7_market: "M7 价格与情绪",
  M8_safety_margin: "M8 安全边际",
  M9_risk: "M9 风险与否决",
  M10_decision: "M10 决策输出",
  M11_monitor: "M11 跟踪监控",
};

const STATUS_LABEL: Record<string, string> = {
  done: "完成",
  failed: "失败",
  skipped: "跳过",
  running: "运行中",
  pending: "待运行",
};

const METHOD_LABELS: Record<string, string> = {
  dcf: "DCF",
  tang: "唐朝法",
  graham_number: "格雷厄姆数",
  graham_formula: "格雷厄姆公式",
  ddm: "股利贴现",
  relative_median_pe: "相对中位 PE",
};

function SectionTitle({ icon, title }: { icon: string; title: string }) {
  return (
    <div className="mb-3.5 flex items-center gap-2 text-sm font-bold">
      <span className="flex size-6 items-center justify-center rounded-lg bg-muted text-sm">
        {icon}
      </span>
      {title}
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border bg-card px-3 py-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-base font-bold tabular-nums">{value}</div>
    </div>
  );
}
