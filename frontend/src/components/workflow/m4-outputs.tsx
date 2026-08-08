"use client";

import * as React from "react";
import { AlertTriangle, BadgeCheck, Gauge, Scale } from "lucide-react";
import { fieldLabel } from "@/lib/labels";

interface MethodView {
  method?: string;
  applicable?: boolean;
  value?: number | null;
  low?: number | null;
  high?: number | null;
  reason?: string;
  note?: string;
  confidence?: number;
  /** v2.3：估值时点口径——null/undefined=现值；3=三年后估值（唐朝法，不进入当前内在价值区间） */
  horizon_years?: number | null;
}

interface IntrinsicView {
  low?: number | null;
  mid?: number | null;
  high?: number | null;
  std?: number | null;
  method_agreement?: number | null;
}

interface CalibrationView {
  parameter_adjustments?: Record<string, number>;
  method_weight_adjustments?: Record<string, number>;
  valuation_confidence_delta?: number;
  industry_notes?: string[];
  risk_notes?: string[];
  reasons?: string[];
  calibrated_intrinsic?: IntrinsicView;
}

interface M4OutputsShape {
  business_type?: string;
  current_price?: number | null;
  valuation_confidence?: number;
  quality_multiplier?: number | null;
  risk_multiplier?: number | null;
  total_multiplier?: number | null;
  quality_tier?: string | null;
  quality_score?: number | null;
  kill_switches?: string[];
  method_agreement?: number | null;
  methods?: MethodView[];
  intrinsic_value?: IntrinsicView;
  params?: Record<string, unknown>;
  weights?: Record<string, number>;
  llm_qualitative?: { calibration?: CalibrationView } | null;
}

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return Number.isFinite(v) ? String(Math.round(v * 100) / 100) : "—";
  if (typeof v === "boolean") return v ? "是" : "否";
  return String(v);
}

function Metric({
  label,
  value,
  tone = "default",
  title,
}: {
  label: string;
  value: React.ReactNode;
  tone?: "default" | "warn" | "good";
  title?: string;
}) {
  const toneCls =
    tone === "warn"
      ? "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-300"
      : tone === "good"
        ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300"
        : "border-border/60 bg-muted/30 text-foreground";
  return (
    <div title={title} className={`rounded-lg border px-2.5 py-2 ${toneCls}`}>
      <div className="text-[11px] font-semibold tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 text-sm font-bold tabular-nums">{value}</div>
    </div>
  );
}

function SectionTitle({
  icon: Icon,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-primary/70">
      <Icon className="size-3.5" />
      {children}
    </div>
  );
}

function IntrinsicBand({ iv, price }: { iv: IntrinsicView; price?: number | null }) {
  const low = iv.low ?? null;
  const mid = iv.mid ?? null;
  const high = iv.high ?? null;
  if (low == null || mid == null || high == null || high <= low) {
    return (
      <div className="text-xs text-muted-foreground">
        数据不足，无法给出内在价值区间
      </div>
    );
  }
  const bandPct =
    price != null
      ? Math.max(0, Math.min(100, ((price - low) / (high - low)) * 100))
      : null;
  return (
    <div className="rounded-xl border p-3.5">
      <div className="relative mx-1 mt-4 h-2 rounded-full bg-gradient-to-r from-emerald-200 via-emerald-300 to-amber-300">
        {bandPct != null && (
          <span
            className="absolute -top-[5px] h-[18px] w-[3px] rounded bg-sky-500 shadow-[0_0_0_3px_#e0f2fe]"
            style={{ left: `calc(${bandPct}% - 1px)` }}
            title={`现价 ${price}`}
          />
        )}
      </div>
      <div className="mt-2 flex justify-between text-xs text-muted-foreground tabular-nums">
        <span>低 {fmt(low)}</span>
        <span className="font-bold text-foreground">中 {fmt(mid)}</span>
        <span>高 {fmt(high)}</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {iv.std != null && <span>离散度 ±{fmt(iv.std)}</span>}
        {iv.method_agreement != null && (
          <span>方法一致性 {fmt(iv.method_agreement)}</span>
        )}
        {price != null && <span>现价 {fmt(price)}</span>}
      </div>
    </div>
  );
}

function MethodTable({ methods }: { methods: MethodView[] }) {
  return (
    <div className="overflow-hidden rounded-lg border">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b bg-muted/40 text-left text-[11px] text-muted-foreground">
            <th className="px-2.5 py-1.5 font-semibold">方法</th>
            <th className="px-2.5 py-1.5 text-right font-semibold">估值（元）</th>
            <th className="px-2.5 py-1.5 text-right font-semibold">置信度</th>
            <th className="px-2.5 py-1.5 font-semibold">说明</th>
          </tr>
        </thead>
        <tbody>
          {methods.map((m) => (
            <tr
              key={m.method}
              className="border-b border-border/40 last:border-0"
            >
              <td className="px-2.5 py-1.5 font-semibold">
                <span className="flex items-center gap-1.5">
                  {fieldLabel(m.method ?? "")}
                  {m.applicable && m.horizon_years != null && (
                    <span className="rounded bg-amber-500/15 px-1 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300">
                      {m.horizon_years}年后
                    </span>
                  )}
                </span>
              </td>
              <td className="px-2.5 py-1.5 text-right tabular-nums">
                {m.applicable ? fmt(m.value) : "跳过"}
                {m.applicable && m.horizon_years != null && (
                  <span className="ml-1 text-[10px] text-muted-foreground">未来值</span>
                )}
              </td>
              <td className="px-2.5 py-1.5 text-right tabular-nums text-muted-foreground">
                {m.applicable ? fmt(m.confidence) : "—"}
              </td>
              <td className="px-2.5 py-1.5 text-muted-foreground">
                {m.reason || m.note || ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Chips({ title, data }: { title: string; data: Record<string, unknown> }) {
  const entries = Object.entries(data ?? {});
  if (entries.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <div className="text-[11px] font-semibold text-muted-foreground">{title}</div>
      <div className="flex flex-wrap gap-1.5">
        {entries.map(([k, v]) => (
          <span
            key={k}
            className="rounded-md border border-border/60 bg-muted/30 px-2 py-0.5 text-xs tabular-nums"
          >
            <span className="text-muted-foreground">{fieldLabel(k)}</span>{" "}
            <span className="font-semibold">{fmt(v)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function CalibrationBlock({ calib }: { calib: CalibrationView }) {
  const delta = calib.valuation_confidence_delta;
  return (
    <div className="flex flex-col gap-2.5 rounded-xl border border-violet-200/60 bg-violet-50/40 p-3 dark:border-violet-800/50 dark:bg-violet-950/20">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-[11px] font-bold uppercase tracking-wider text-violet-600/80 dark:text-violet-300/80">
          LLM 行业校准
        </span>
        {delta != null && delta !== 0 && (
          <span className="rounded-md border border-violet-300/60 bg-violet-100/60 px-2 py-0.5 text-xs font-semibold dark:border-violet-700 dark:bg-violet-900/40">
            置信度 {delta > 0 ? "+" : ""}
            {fmt(delta)}
          </span>
        )}
      </div>

      {(calib.parameter_adjustments && Object.keys(calib.parameter_adjustments).length > 0) ||
      (calib.method_weight_adjustments &&
        Object.keys(calib.method_weight_adjustments).length > 0) ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {calib.parameter_adjustments &&
            Object.keys(calib.parameter_adjustments).length > 0 && (
              <Chips title="参数校准" data={calib.parameter_adjustments} />
            )}
          {calib.method_weight_adjustments &&
            Object.keys(calib.method_weight_adjustments).length > 0 && (
              <Chips title="权重校准" data={calib.method_weight_adjustments} />
            )}
        </div>
      ) : null}

      {calib.industry_notes && calib.industry_notes.length > 0 && (
        <div className="text-[13px] leading-5 text-foreground/80">
          <div className="mb-0.5 text-[11px] font-semibold text-violet-600/80 dark:text-violet-300/80">
            行业判断
          </div>
          {calib.industry_notes.map((n, i) => (
            <p key={i}>{n}</p>
          ))}
        </div>
      )}

      {calib.risk_notes && calib.risk_notes.length > 0 && (
        <div className="flex flex-col gap-0.5 rounded-lg border border-amber-200/70 bg-amber-50/60 px-2.5 py-2 text-[13px] leading-5 text-amber-800 dark:border-amber-800/50 dark:bg-amber-950/30 dark:text-amber-300">
          <div className="flex items-center gap-1 font-semibold">
            <AlertTriangle className="size-3" /> 行业风险
          </div>
          {calib.risk_notes.map((n, i) => (
            <p key={i}>{n}</p>
          ))}
        </div>
      )}

      {calib.reasons && calib.reasons.length > 0 && (
        <div className="text-xs leading-5 text-muted-foreground">
          <div className="mb-0.5 text-[11px] font-semibold">判断理由</div>
          {calib.reasons.map((n, i) => (
            <p key={i}>{n}</p>
          ))}
        </div>
      )}
    </div>
  );
}

/** M4 估值引擎专用输出视图：分组展示，替代通用字段平铺。 */
export function M4Outputs({ outputs }: { outputs: Record<string, unknown> }) {
  const o = outputs as M4OutputsShape;
  const iv = o.intrinsic_value;
  const methods = (o.methods ?? []) as MethodView[];
  const kill = o.kill_switches ?? [];
  const llm = o.llm_qualitative;
  const hasCalibration =
    llm && llm.calibration && Object.keys(llm.calibration).length > 0;

  const paramsWithoutConfidence = Object.fromEntries(
    Object.entries(o.params ?? {}).filter(([k]) => k !== "growth_confidence"),
  );

  return (
    <div className="flex flex-col gap-3">
      {/* 信号条 */}
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        <Metric
          label="估值置信度"
          value={o.valuation_confidence != null ? `${Math.round(o.valuation_confidence * 100)}%` : "—"}
          tone="good"
        />
        <Metric label="质量乘数" value={fmt(o.quality_multiplier)} />
        <Metric label="风险折扣" value={fmt(o.risk_multiplier)} />
        <Metric label="综合乘数" value={fmt(o.total_multiplier)} />
        <Metric label="质量档位" value={fmt(o.quality_tier)} />
        <Metric label="质量分" value={fmt(o.quality_score)} />
        <Metric
          label="方法一致性"
          value={fmt(o.method_agreement)}
          title="跨方法结论的一致性（0-1），越高越可信"
        />
        <Metric
          label="风险开关"
          value={
            kill.length > 0 ? (
              <span className="flex flex-wrap gap-1">
                {kill.map((k) => (
                  <span
                    key={k}
                    className="rounded bg-amber-500/15 px-1 py-0.5 text-[11px] font-semibold"
                  >
                    {k}
                  </span>
                ))}
              </span>
            ) : (
              "无"
            )
          }
          tone={kill.length > 0 ? "warn" : "default"}
        />
      </div>

      {/* 内在价值区间 */}
      {iv && (
        <div className="flex flex-col gap-1.5 border-t border-border/40 pt-2.5">
          <SectionTitle icon={Gauge}>内在价值区间（现值口径）</SectionTitle>
          <IntrinsicBand iv={iv} price={o.current_price} />
        </div>
      )}

      {/* 估值方法 */}
      {methods.length > 0 && (
        <div className="flex flex-col gap-1.5 border-t border-border/40 pt-2.5">
          <SectionTitle icon={Scale}>估值方法</SectionTitle>
          <MethodTable methods={methods} />
        </div>
      )}

      {/* 参数 & 权重 */}
      {(Object.keys(paramsWithoutConfidence).length > 0 ||
        Object.keys(o.weights ?? {}).length > 0) && (
        <div className="flex flex-col gap-2 border-t border-border/40 pt-2.5">
          <SectionTitle icon={BadgeCheck}>参数与方法权重</SectionTitle>
          <div className="grid gap-2 sm:grid-cols-2">
            <Chips title="估值参数" data={paramsWithoutConfidence} />
            <Chips title="方法权重" data={o.weights ?? {}} />
          </div>
        </div>
      )}

      {/* LLM 行业校准 */}
      {hasCalibration && (
        <div className="border-t border-border/40 pt-2.5">
          <CalibrationBlock calib={llm?.calibration as CalibrationView} />
        </div>
      )}
    </div>
  );
}
