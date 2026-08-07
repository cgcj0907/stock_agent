"use client";

import * as React from "react";
import {
  Activity,
  AlertTriangle,
  BadgeCheck,
      Building2,
  Castle,
  ChartLine,
  ClipboardList,
  Gauge,
  GaugeCircle,
  HandCoins,
  Landmark,
    RadioTower,
    Scale,
  ShieldAlert,
  ShieldCheck,
    Target,
  TrendingUp,
  TriangleAlert,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { M4Outputs } from "@/components/workflow/m4-outputs";
import { fieldLabel } from "@/lib/labels";

// ---------- 通用工具 ----------

function isObj(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return Number.isFinite(v) ? String(Math.round(v * 100) / 100) : "—";
  if (typeof v === "boolean") return v ? "是" : "否";
  return String(v);
}

function fmtPct(v: unknown): string {
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(0)}%`;
}

/** 0~1 比例 → 0~100 进度值；非法输入返回 null。 */
function pct(v: unknown): number | null {
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  return Math.max(0, Math.min(100, v * 100));
}

function str(v: unknown): string {
  if (typeof v === "string") return v;
  return "";
}

function arr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

// ---------- 语义配色 ----------

const POSITION_TONE: Record<string, string> = {
  极低估: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  低估: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  合理: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  合理偏下: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  合理偏上: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  高估: "border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-800 dark:bg-orange-950/60 dark:text-orange-300",
  泡沫: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
  样本不足: "border-border bg-muted/50 text-muted-foreground",
};

const SEVERITY_TONE: Record<string, string> = {
  info: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  low: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  medium: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  warn: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  high: "border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-800 dark:bg-orange-950/60 dark:text-orange-300",
  critical: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
};

const MOS_TONE: Record<string, string> = {
  attractive: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  fair: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  expensive: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
  unavailable: "border-border bg-muted/50 text-muted-foreground",
};

const MOS_LABEL: Record<string, string> = {
  attractive: "安全边际充足",
  fair: "边际一般",
  expensive: "安全边际为负",
  unavailable: "数据不足",
};

const WIDTH_TONE: Record<string, string> = {
  宽: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  较宽: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  中: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  较窄: "border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-800 dark:bg-orange-950/60 dark:text-orange-300",
  窄: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
  无: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
};

function toneOf(map: Record<string, string>, key: unknown): string {
  const k = str(key);
  return map[k] ?? "border-border bg-muted/50 text-muted-foreground";
}

function ToneBadge({ text, tone, icon: Icon }: { text: unknown; tone: string; icon?: React.ComponentType<{ className?: string }> }) {
  const IconCmp = Icon ?? null;
  return (
    <Badge variant="outline" className={`gap-1 rounded-md px-1.5 py-0.5 text-[10px] ${tone}`}>
      {IconCmp && <IconCmp className="size-3" />}
      {fmt(text)}
    </Badge>
  );
}

/** 枚举值 → 中文展示（规则/LLM 输出为英文枚举，展示统一转中文）。 */
function labelOf(map: Record<string, string>, v: unknown): string {
  const k = str(v);
  return map[k] ?? k;
}

const SEVERITY_LABEL: Record<string, string> = {
  info: "提示",
  low: "低",
  medium: "中",
  warn: "警告",
  high: "高",
  critical: "严重",
};

const CONFIDENCE_LABEL: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

const WIDTH_SOURCE_LABEL: Record<string, string> = {
  rule_proxy: "规则代理",
  llm: "LLM 定性",
  degraded: "降级",
};

const WIDTH_SOURCE_TONE: Record<string, string> = {
  llm: "border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-800 dark:bg-violet-950/60 dark:text-violet-300",
  rule_proxy: "border-border bg-muted/50 text-muted-foreground",
  degraded: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
};

const CAP_ALLOC_LABEL: Record<string, string> = {
  good: "优秀",
  neutral: "中性",
  poor: "较差",
};

const MODULE_SHORT: Record<string, string> = {
  M1_business_model: "M1 商业模式",
  M2_financial_quality: "M2 财务质量",
  M3_growth: "M3 成长景气",
  M4_valuation: "M4 估值",
  M5_moat: "M5 护城河",
  M6_governance: "M6 治理",
  M7_market: "M7 市场",
  M8_safety_margin: "M8 安全边际",
  M9_risk: "M9 风险",
  M10_decision: "M10 决策",
  M11_monitor: "M11 监控",
};

const TRIGGER_WORDS: Array<[RegExp, string]> = [
  [/expensive/g, "安全边际为负"],
  [/attractive/g, "安全边际充足"],
  [/\bfair\b/g, "边际一般"],
  [/unavailable/g, "数据不足"],
  [/\bavoid\b/g, "回避"],
  [/\bbuy\b/g, "买入"],
  [/\bwatch\b/g, "观察"],
  [/\balert\b/g, "提醒"],
  [/\baction\b/g, "执行"],
  [/\bnarrow\b/g, "窄"],
  [/\bwide\b/g, "宽"],
  [/\berosion_risk\b/g, "护城河侵蚀"],
];

/** 监控/风险触发条件里的英文枚举转中文（展示层，不改后端规则）。 */
function translateEnumText(s: string): string {
  let out = s;
  for (const [re, zh] of TRIGGER_WORDS) out = out.replace(re, zh);
  return out;
}

export function moduleShort(id: string): string {
  return MODULE_SHORT[id] ?? id;
}

function Section({
  icon: Icon,
  title,
  tone = "primary",
  children,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: React.ReactNode;
  tone?: "primary" | "rose" | "violet";
  children: React.ReactNode;
}) {
  const titleCls =
    tone === "rose"
      ? "text-rose-600/80 dark:text-rose-400/80"
      : tone === "violet"
        ? "text-violet-600/80 dark:text-violet-300/80"
        : "text-primary/70";
  return (
    <div className="flex flex-col gap-1.5 border-t border-border/40 pt-2.5">
      <div className={`flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider ${titleCls}`}>
        {Icon && <Icon className="size-3.5 shrink-0" />}
        <span className="truncate">{title}</span>
      </div>
      {children}
    </div>
  );
}

function Metric({
  label,
  value,
  tone = "default",
  title,
}: {
  label: string;
  value: React.ReactNode;
  tone?: "default" | "warn" | "good" | "bad";
  title?: string;
}) {
  const toneCls =
    tone === "warn"
      ? "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-300"
      : tone === "good"
        ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300"
        : tone === "bad"
          ? "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/50 dark:text-red-300"
          : "border-border/60 bg-muted/30 text-foreground";
  return (
    <div title={title} className={`rounded-lg border px-2.5 py-2 ${toneCls}`}>
      <div className="text-[10px] font-semibold tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 break-words text-sm font-bold tabular-nums">{value}</div>
    </div>
  );
}

/** 0~100 水平条，按位置自动配色。 */
function LevelBar({ value, className }: { value: number | null; className?: string }) {
  const color =
    value == null
      ? "bg-muted-foreground/30"
      : value < 20
        ? "bg-emerald-500"
        : value < 40
          ? "bg-emerald-400"
          : value < 60
            ? "bg-amber-400"
            : value < 80
              ? "bg-orange-400"
              : "bg-red-500";
  return (
    <div className={`h-1.5 w-full overflow-hidden rounded-full bg-muted ${className ?? ""}`}>
      <div
        className={`h-full rounded-full ${color}`}
        style={{ width: `${value == null ? 0 : Math.max(2, Math.min(100, value))}%` }}
      />
    </div>
  );
}

/** 分位条：0~1 比例 → 进度 + 百分比文本。 */
function PercentileRow({ label, value }: { label: string; value: unknown }) {
  const v = pct(value);
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-[11px]">
        <span className="font-medium text-foreground/70">{label}</span>
        <span className="font-semibold tabular-nums text-foreground/90">{v == null ? "—" : `${v.toFixed(0)}%`}</span>
      </div>
      <LevelBar value={v} />
    </div>
  );
}

function KVGrid({ items, cols = 2 }: { items: Array<[string, unknown]>; cols?: 1 | 2 }) {
  if (items.length === 0) return null;
  return (
    <div className={`grid gap-x-3 gap-y-2 ${cols === 2 ? "grid-cols-2" : "grid-cols-1"}`}>
      {items.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <div className="truncate text-[10px] font-semibold tracking-wide text-muted-foreground">{fieldLabel(k)}</div>
          <div className="mt-0.5 break-words text-xs leading-5 font-medium text-foreground/80">{fmt(v)}</div>
        </div>
      ))}
    </div>
  );
}

function isReference(v: unknown): v is Record<string, unknown> {
  return isObj(v) && (str(v.title) !== "" || str(v.url) !== "");
}

/** 参考文章条目：标题可点击跳转真实来源，附带日期/来源/摘要。 */
function ReferenceLink({ item }: { item: Record<string, unknown> }) {
  const url = str(item.url);
  const title = str(item.title) || url || "参考文章";
  const meta = str(item.meta);
  const date = str(item.date);
  const snippet = str(item.snippet);
  const metaLine = [date, meta].filter(Boolean).join(" · ");
  return (
    <li className="flex flex-col gap-0.5">
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="break-words text-xs leading-5 font-medium text-emerald-700 hover:underline dark:text-emerald-400"
        >
          {title}
        </a>
      ) : (
        <span className="break-words text-xs leading-5 font-medium text-foreground/85">{title}</span>
      )}
      {metaLine && <span className="text-[10px] leading-4 text-muted-foreground">{metaLine}</span>}
      {snippet && <span className="text-[11px] leading-4 text-muted-foreground/80">{snippet}</span>}
    </li>
  );
}

function BulletList({ items }: { items: unknown[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="flex flex-col gap-1">
      {items.map((it, i) =>
        isReference(it) ? (
          <ReferenceLink key={i} item={it} />
        ) : (
          <li key={i} className="flex items-start gap-1.5 text-xs leading-5 text-foreground/80">
            <span className="mt-[5px] size-1 shrink-0 rounded-full bg-muted-foreground/50" />
            <span className="min-w-0 break-words">{fmt(it)}</span>
          </li>
        ),
      )}
    </ul>
  );
}

function QualBlock({
  qual,
  excludeKeys = [],
}: {
  qual: Record<string, unknown>;
  excludeKeys?: string[];
}) {
  const entries = Object.entries(qual).filter(([k, v]) => {
    if (excludeKeys.includes(k)) return false;
    if (Array.isArray(v)) return v.length > 0;
    if (isObj(v)) return Object.keys(v).length > 0;
    return v !== null && v !== undefined && v !== "";
  });
  if (entries.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      {entries.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <div className="text-[10px] font-semibold tracking-wide text-violet-600/80 dark:text-violet-300/80">
            {fieldLabel(k)}
          </div>
          {Array.isArray(v) ? (
            <BulletList items={v} />
          ) : isObj(v) ? (
            <KVGrid items={Object.entries(v)} cols={1} />
          ) : (
            <div className="mt-0.5 break-words text-xs leading-5 text-foreground/80">{fmt(v)}</div>
          )}
        </div>
      ))}
    </div>
  );
}


function riskRowValue(items: unknown[]): Array<Record<string, unknown>> {
  return items.filter(isObj);
}

// ---------- M1 商业模式 ----------

function M1Outputs({ outputs }: { outputs: Record<string, unknown> }) {
  const qual = isObj(outputs.llm_qualitative) ? outputs.llm_qualitative : null;
  const oneLiner = str(outputs.business_model) || str(qual?.business_model);
  const reasons = arr(qual?.reasons);
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        <Metric label="生意类型" value={fmt(outputs.business_type)} />
        <Metric label="可理解性" value={fmt(outputs.understandability)} />
        <Metric label="行业" value={fmt(outputs.industry)} />
        <Metric label="能力圈" value={fmt(qual?.understandability ?? "—")} />
      </div>
      {oneLiner && (
        <Section icon={Building2} title="生意本质">
          <p className="break-words text-xs leading-5 text-foreground/80">{oneLiner}</p>
        </Section>
      )}
      {reasons.length > 0 && (
        <Section icon={ClipboardList} title="判断理由" tone="violet">
          <BulletList items={reasons} />
        </Section>
      )}
    </div>
  );
}

// ---------- M2 财务质量 ----------

function M2Outputs({ outputs }: { outputs: Record<string, unknown> }) {
  const metrics = isObj(outputs.metrics) ? outputs.metrics : {};
  const signals = riskRowValue(arr(outputs.signals));
  const summary = isObj(outputs.summary) ? outputs.summary : null;
  const metricEntries = Object.entries(metrics).filter(([, v]) => v !== null && v !== undefined && v !== "");
  return (
    <div className="flex flex-col gap-3">
      {metricEntries.length > 0 && (
        <Section icon={Activity} title="核心指标">
          <KVGrid items={metricEntries} />
        </Section>
      )}
      {signals.length > 0 && (
        <Section icon={AlertTriangle} title="风险信号" tone="rose">
          <ul className="flex flex-col gap-1.5">
            {signals.map((sig, i) => (
              <li key={i} className="flex items-start gap-2 text-xs leading-5">
                <ToneBadge text={labelOf(SEVERITY_LABEL, sig.severity ?? "warn")} tone={toneOf(SEVERITY_TONE, sig.severity)} />
                <span className="min-w-0 flex-1 break-words text-foreground/80">
                  {fmt(sig.message ?? sig.desc ?? sig)}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}
      {summary && Object.keys(summary).length > 0 && (
        <Section icon={BadgeCheck} title="摘要">
          <KVGrid items={Object.entries(summary)} cols={1} />
        </Section>
      )}
    </div>
  );
}

// ---------- M3 成长景气 ----------

function M3Outputs({ outputs }: { outputs: Record<string, unknown> }) {
  const handoff = isObj(outputs.handoff) ? outputs.handoff : {};
  const scenarios = isObj(handoff.growth_scenarios) ? handoff.growth_scenarios : null;
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        <Metric label="增速估计" value={fmtPct(outputs.growth_estimate)} tone="good" />
        <Metric label="景气度" value={fmt(outputs.prosperity)} />
        <Metric label="增长信心" value={labelOf(CONFIDENCE_LABEL, handoff.growth_confidence)} />
        <Metric
          label="周期属性"
          value={handoff.cyclicality_flag === true ? "周期行业" : handoff.cyclicality_flag === false ? "非周期" : "—"}
        />
      </div>
      {scenarios && Object.keys(scenarios).length > 0 && (
        <Section icon={TrendingUp} title="增速情景">
          <KVGrid items={Object.entries(scenarios)} cols={1} />
        </Section>
      )}
    </div>
  );
}

// ---------- M5 护城河 ----------

function M5Outputs({ outputs }: { outputs: Record<string, unknown> }) {
  const ruleProxy = isObj(outputs.rule_proxy) ? outputs.rule_proxy : {};
  const signals = arr(outputs.signals);
  const qual = isObj(outputs.llm_qualitative) ? outputs.llm_qualitative : null;
  const widthSource = labelOf(WIDTH_SOURCE_LABEL, outputs.width_source);
  const widthConflict = outputs.width_conflict === true;
  const llmWidth = str(qual?.width);
  const qualList = qual ? (
    <QualBlock qual={qual} excludeKeys={["width"]} />
  ) : typeof outputs.llm_qualitative === "string" ? (
    <p className="break-words whitespace-pre-wrap text-xs leading-5 text-foreground/80">{outputs.llm_qualitative}</p>
  ) : null;

  return (
    <div className="flex flex-col gap-3">
      {/* 主结论：最终护城河宽度（LLM 层优先） */}
      <div className="flex items-center gap-2.5 rounded-lg border border-border/60 bg-muted/20 px-3 py-2.5">
        <Castle className="size-4 shrink-0 text-primary/70" />
        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            最终护城河宽度
          </div>
          <div className={`text-lg leading-7 font-bold ${toneOf(WIDTH_TONE, outputs.width)}`}>{fmt(outputs.width) || "—"}</div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <ToneBadge text={widthSource} tone={toneOf(WIDTH_SOURCE_TONE, outputs.width_source)} />
          {widthConflict && (
            <span className="text-[10px] text-amber-600 dark:text-amber-400">规则/LLM 冲突</span>
          )}
        </div>
      </div>

      {widthConflict && (
        <p className="rounded-lg border border-amber-200/70 bg-amber-50/60 px-2.5 py-1.5 text-[11px] leading-5 text-amber-800 dark:border-amber-800/50 dark:bg-amber-950/30 dark:text-amber-300">
          规则层={fmt(ruleProxy.tier)}（{fmt(ruleProxy.score)} 分）vs LLM 定性={llmWidth || "—"}，
          最终采用 <span className="font-semibold">{fmt(outputs.width)}</span>
          {outputs.width_source === "llm" && "（LLM 已附竞争优势证据）"}
        </p>
      )}

      {/* 规则层参考（财务代理，不作为主结论） */}
      <div className="flex flex-col gap-1.5 border-t border-border/40 pt-2.5">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          规则层参考（财务代理）
        </div>
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
          <Metric label="代理档位" value={fmt(ruleProxy.tier)} />
          <Metric label="代理评分" value={fmt(ruleProxy.score)} />
          <Metric label="来源信号" value={arr(ruleProxy.sources).length} />
          <Metric
            label="侵蚀信号"
            value={arr(ruleProxy.erosion_signals).length}
            tone={arr(ruleProxy.erosion_signals).length > 0 ? "warn" : "default"}
          />
        </div>
      </div>

      {signals.length > 0 && (
        <Section icon={ShieldAlert} title="信号" tone="rose">
          <BulletList items={signals} />
        </Section>
      )}

      {qualList && (
        <Section icon={BadgeCheck} title="LLM 定性" tone="violet">
          {qualList}
        </Section>
      )}
    </div>
  );
}

// ---------- M6 治理 ----------

function M6Outputs({ outputs }: { outputs: Record<string, unknown> }) {
  const handoff = isObj(outputs.handoff) ? outputs.handoff : {};
  const signals = riskRowValue(arr(outputs.signals));
  const qual = isObj(outputs.llm_qualitative) ? outputs.llm_qualitative : null;
  const dividendYield = typeof outputs.dividend_yield === "number" ? outputs.dividend_yield : null;
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        <Metric label="治理评分" value={fmt(handoff.governance_score)} />
        <Metric label="资本配置" value={labelOf(CAP_ALLOC_LABEL, handoff.capital_allocation_flag)} />
        <Metric label="连续分红年数" value={fmt(outputs.dividend_years)} />
        <Metric label="每股派息" value={outputs.payout_latest != null ? `${fmt(outputs.payout_latest)} 元` : "—"} />
        <Metric
          label="股息率"
          value={dividendYield != null ? `${(dividendYield * 100).toFixed(1)}%` : "—"}
          tone={
            dividendYield != null && dividendYield >= 0.04
              ? "good"
              : dividendYield != null && dividendYield < 0.02
                ? "warn"
                : "default"
          }
          title="TTM 每股派息 ÷ 现价"
        />
      </div>
      {str(outputs.note) && str(outputs.note) !== "—" && (
        <p className="text-xs leading-5 text-muted-foreground">{fmt(outputs.note)}</p>
      )}
      {signals.length > 0 && (
        <Section icon={AlertTriangle} title="治理风险信号" tone="rose">
          <ul className="flex flex-col gap-1.5">
            {signals.map((sig, i) => (
              <li key={i} className="flex items-start gap-2 text-xs leading-5">
                <ToneBadge text={labelOf(SEVERITY_LABEL, sig.severity ?? "warn")} tone={toneOf(SEVERITY_TONE, sig.severity)} />
                <span className="min-w-0 flex-1 break-words text-foreground/80">{fmt(sig.message ?? sig.desc ?? sig)}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
      {qual && Object.keys(qual).length > 0 && (
        <Section icon={Landmark} title="LLM 定性" tone="violet">
          <QualBlock qual={qual} />
        </Section>
      )}
    </div>
  );
}

// ---------- M7 市场情绪 ----------

function M7Outputs({ outputs }: { outputs: Record<string, unknown> }) {
  const heat = pct(outputs.sentiment_heat);
  const sentimentSignals = arr(outputs.sentiment_signals);
  const heatLabel = heat == null ? "—" : heat >= 66 ? "偏热" : heat <= 33 ? "偏冷" : "中性";
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <ToneBadge text={outputs.position ?? "—"} tone={toneOf(POSITION_TONE, outputs.position)} icon={ChartLine} />
        <span className="text-[10px] text-muted-foreground">
          情绪热度 {heat == null ? "—" : `${heat.toFixed(0)}%`}（{heatLabel}）
        </span>
      </div>
      <div className="flex flex-col gap-2.5 rounded-lg border border-border/60 bg-muted/20 p-2.5">
        <PercentileRow label="PE 分位" value={outputs.pe_percentile} />
        <PercentileRow label="PB 分位" value={outputs.pb_percentile} />
        <PercentileRow label="情绪综合热度" value={outputs.sentiment_heat} />
      </div>
      {sentimentSignals.length > 0 && (
        <Section icon={Gauge} title="情绪信号">
          <BulletList items={sentimentSignals} />
        </Section>
      )}
    </div>
  );
}

// ---------- M8 安全边际 ----------

function M8Outputs({ outputs }: { outputs: Record<string, unknown> }) {
  const mos = str(outputs.mos_state);
  const discount = typeof outputs.discount === "number" ? outputs.discount : null;
  const required = typeof outputs.required_discount === "number" ? outputs.required_discount : null;
  const tranches = riskRowValue(arr(outputs.buy_tranches));
  const marginOk = discount != null && required != null && discount >= required;
  const barPct = discount != null ? Math.max(0, Math.min(100, 50 + discount * 100)) : null;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <ToneBadge
          text={str(outputs.status) || MOS_LABEL[mos] || "—"}
          tone={toneOf(MOS_TONE, mos)}
          icon={Scale}
        />
        {mos && (
          <span className="text-[10px] text-muted-foreground">{MOS_LABEL[mos] ?? mos}</span>
        )}
        {outputs.sell_reference === true && (
          <ToneBadge text="卖出参考" tone={toneOf(SEVERITY_TONE, "warn")} icon={HandCoins} />
        )}
      </div>

      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        <Metric label="现价" value={fmt(outputs.price)} />
        <Metric
          label="折扣率"
          value={discount != null ? `${(discount * 100).toFixed(1)}%` : "—"}
          tone={marginOk ? "good" : "bad"}
          title="1 − 现价/内在价值下沿"
        />
        <Metric label="要求折扣" value={required != null ? `${(required * 100).toFixed(1)}%` : "—"} />
        <Metric label="卖出参考" value={outputs.sell_reference === true ? "触发" : "否"} />
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        <Metric label="买入价（≤）" value={fmt(outputs.buy_price)} tone="good" />
        <Metric label="卖出价（≥）" value={fmt(outputs.sell_price)} tone="warn" />
      </div>

      {discount != null && required != null && (
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between text-[11px]">
            <span className="font-medium text-foreground/70">安全边际</span>
            <span className="tabular-nums text-muted-foreground">
              要求 {(required * 100).toFixed(0)}% · 当前 {marginOk ? "达标" : "未达标"}
            </span>
          </div>
          <LevelBar value={barPct} />
        </div>
      )}

      {tranches.length > 0 && (
        <Section icon={GaugeCircle} title="分批建仓档位">
          <ul className="flex flex-col gap-1.5">
            {tranches.map((t, i) => (
              <li key={i} className="flex items-center justify-between gap-2 rounded-lg border border-border/60 bg-muted/20 px-2.5 py-1.5 text-xs">
                <span className="min-w-0 flex-1 truncate text-foreground/80">{fmt(t.label ?? `档位 ${i + 1}`)}</span>
                <span className="shrink-0 font-bold tabular-nums text-emerald-600 dark:text-emerald-400">{fmt(t.price)} 元</span>
                <span className="shrink-0 text-muted-foreground">{fmtPct(t.weight)}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

// ---------- M9 风险与否决 ----------

function M9Outputs({ outputs }: { outputs: Record<string, unknown> }) {
  const vetoes = riskRowValue(arr(outputs.vetoes));
  const riskItems = riskRowValue(arr(outputs.risk_items));
  const monitorCandidates = arr(outputs.monitor_candidates);
  const scenario = isObj(outputs.max_loss_scenario) ? outputs.max_loss_scenario : null;
  const redTeam = isObj(outputs.llm_red_team) ? outputs.llm_red_team : null;
  const paths = riskRowValue(arr(redTeam?.permanent_loss_paths));
  const assumptions = arr(redTeam?.key_assumptions);
  const drivers = arr(scenario?.drivers);

  return (
    <div className="flex flex-col gap-3">
      {vetoes.length > 0 && (
        <Section icon={ShieldAlert} title="一票否决" tone="rose">
          <ul className="flex flex-col gap-1.5">
            {vetoes.map((v, i) => (
              <li key={i} className="rounded-lg border border-red-200 bg-red-50/60 px-2.5 py-1.5 text-xs leading-5 text-red-700 dark:border-red-800/50 dark:bg-red-950/30 dark:text-red-300">
                <span className="font-semibold">{fmt(v.id)}</span> {fmt(v.reason)}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {riskItems.length > 0 && (
        <Section icon={TriangleAlert} title={`风险清单（${riskItems.length}）`} tone="rose">
          <ul className="flex flex-col gap-1.5">
            {riskItems.map((it, i) => (
              <li key={i} className="rounded-lg border border-border/60 bg-muted/20 px-2.5 py-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-mono text-[10px] font-semibold text-muted-foreground">{fmt(it.id)}</span>
                  <ToneBadge text={it.category} tone={toneOf(SEVERITY_TONE, "warn")} />
                  <ToneBadge text={labelOf(SEVERITY_LABEL, it.severity)} tone={toneOf(SEVERITY_TONE, it.severity)} />
                  <span className="text-[10px] text-muted-foreground">{labelOf(MODULE_SHORT, it.source_module)}</span>
                </div>
                <p className="mt-1 break-words text-xs leading-5 text-foreground/80">{fmt(it.impact)}</p>
                {str(it.mitigation) && (
                  <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">缓解：{fmt(it.mitigation)}</p>
                )}
                {it.expected_loss != null && (
                  <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">
                    期望损失 {fmt(it.expected_loss)} · 触发 {translateEnumText(fmt(it.trigger))}
                    {it.veto_candidate === true && " · 否决候选"}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {scenario && (
        <Section icon={TrendingUp} title="压力情景">
          <div className="rounded-lg border border-border/60 bg-muted/20 p-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold text-foreground/90">{fmt(scenario.scenario)}</span>
              {scenario.estimated_downside_pct != null && (
                <ToneBadge
                  text={`最大回撤 ${fmt(scenario.estimated_downside_pct)}%`}
                  tone={toneOf(SEVERITY_TONE, "critical")}
                />
              )}
            </div>
            <p className="mt-1.5 text-[11px] leading-5 text-muted-foreground">{fmt(scenario.assumptions)}</p>
            {drivers.length > 0 && <BulletList items={drivers} />}
            {(scenario.current_price != null || scenario.suggested_position_cap != null) && (
              <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-foreground/70">
                {scenario.current_price != null && <span>现价 {fmt(scenario.current_price)}</span>}
                {scenario.intrinsic_low != null && <span>内在下沿 {fmt(scenario.intrinsic_low)}</span>}
                {scenario.estimated_downside_amount != null && (
                  <span>回撤金额 {fmt(scenario.estimated_downside_amount)}</span>
                )}
                {scenario.suggested_position_cap != null && (
                  <span>建议仓位上限 {fmtPct(scenario.suggested_position_cap)}</span>
                )}
              </div>
            )}
            {monitorCandidates.length > 0 && (
              <div className="mt-1.5 flex flex-wrap items-center gap-1">
                <span className="text-[10px] font-semibold text-muted-foreground">监控候选</span>
                {monitorCandidates.map((c, i) => (
                  <span key={i} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-foreground/70">{fmt(c)}</span>
                ))}
              </div>
            )}
          </div>
        </Section>
      )}

      {redTeam && (
        <Section icon={ShieldCheck} title="LLM 红队批判" tone="violet">
          <div className="flex flex-col gap-2.5">
            {assumptions.length > 0 && (
              <div>
                <div className="mb-1 text-[10px] font-semibold text-violet-600/80 dark:text-violet-300/80">关键假设</div>
                <BulletList items={assumptions} />
              </div>
            )}
            {paths.length > 0 && (
              <div>
                <div className="mb-1 text-[10px] font-semibold text-violet-600/80 dark:text-violet-300/80">永久损失路径</div>
                <ul className="flex flex-col gap-1.5">
                  {paths.map((p, i) => (
                    <li key={i} className="rounded-lg border border-border/60 bg-muted/20 px-2.5 py-1.5">
                      <div className="flex items-center gap-1.5">
                        <ToneBadge text={labelOf(CONFIDENCE_LABEL, p.confidence)} tone={toneOf(SEVERITY_TONE, p.confidence)} />
                        {p.veto_candidate === true && (
                          <ToneBadge text="否决候选" tone={toneOf(SEVERITY_TONE, "critical")} />
                        )}
                      </div>
                      <p className="mt-1 break-words text-[11px] leading-5 text-foreground/80">{fmt(p.path)}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {str(redTeam.verdict) && (
              <div className="rounded-lg border border-amber-200/70 bg-amber-50/60 px-2.5 py-2 text-[11px] leading-5 text-amber-800 dark:border-amber-800/50 dark:bg-amber-950/30 dark:text-amber-300">
                <span className="font-semibold">反方结论：</span>
                {fmt(redTeam.verdict)}
              </div>
            )}
            {Array.isArray(redTeam.references) && redTeam.references.length > 0 && (
              <div className="flex flex-col gap-1">
                <div className="text-[10px] font-semibold text-violet-600/80 dark:text-violet-300/80">参考文章</div>
                <BulletList items={redTeam.references} />
              </div>
            )}
          </div>
        </Section>
      )}
    </div>
  );
}

// ---------- M10 决策 ----------

const DIM_LABELS: Array<{ key: string; label: string; bar: string }> = [
  { key: "business_moat", label: "护城河", bar: "bg-emerald-500" },
  { key: "financial_quality", label: "财务质量", bar: "bg-sky-500" },
  { key: "growth_prosperity", label: "成长景气", bar: "bg-violet-500" },
  { key: "valuation_margin", label: "估值边际", bar: "bg-amber-500" },
  { key: "governance_risk", label: "治理风险", bar: "bg-rose-500" },
];

const CONCLUSION_TONE: Record<string, string> = {
  强烈关注: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  关注: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
  中性: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  回避: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
};

function M10Outputs({ outputs }: { outputs: Record<string, unknown> }) {
  const dims = isObj(outputs.dimensions) ? outputs.dimensions : {};
  const qualitative = isObj(outputs.qualitative) ? outputs.qualitative : null;
  const reasons = arr(qualitative?.decision_reasons ?? outputs.decision_reasons);
  const total = typeof outputs.total === "number" ? outputs.total : null;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <ToneBadge
          text={outputs.conclusion ?? "—"}
          tone={toneOf(CONCLUSION_TONE, outputs.conclusion)}
          icon={Target}
        />
        {total != null && (
          <Badge variant="outline" className="gap-1 rounded-md border-border bg-muted/50 px-1.5 py-0.5 text-[10px]">
            加权总分 <span className="font-bold tabular-nums">{Math.round(total)}</span>
          </Badge>
        )}
        {outputs.blocked_by_veto === true && (
          <ToneBadge text="被否决" tone={toneOf(SEVERITY_TONE, "critical")} icon={ShieldAlert} />
        )}
      </div>

      <Section icon={GaugeCircle} title="五维评分">
        <div className="flex flex-col gap-2">
          {DIM_LABELS.map((d) => {
            const v = typeof dims[d.key] === "number" ? (dims[d.key] as number) : null;
            return (
              <div key={d.key} className="flex items-center gap-2.5">
                <span className="w-14 shrink-0 text-[11px] text-foreground/70">{d.label}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className={`h-full rounded-full ${d.bar}`}
                    style={{ width: `${v == null ? 0 : Math.max(0, Math.min(100, v))}%` }}
                  />
                </div>
                <span className="w-7 shrink-0 text-right text-[11px] font-semibold tabular-nums text-foreground/90">
                  {v == null ? "—" : Math.round(v)}
                </span>
              </div>
            );
          })}
        </div>
      </Section>

      {reasons.length > 0 && (
        <Section icon={ClipboardList} title="决策理由">
          <BulletList items={reasons} />
        </Section>
      )}
    </div>
  );
}

// ---------- M11 监控 ----------

const RULE_TYPE_LABEL: Record<string, string> = {
  price_buy: "买入触发",
  price_sell: "卖出触发",
  valuation_sell: "估值卖出",
  mos_watch: "安全边际",
  prosperity_watch: "景气监控",
  fundamental_watch: "基本面监控",
  risk_watch: "风险监控",
  decision_watch: "决策监控",
  prior_hit_review: "历史命中",
  sentiment_watch: "情绪监控",
};

const ACTION_LABEL: Record<string, string> = {
  watch: "观察",
  alert: "提醒",
  action: "执行",
};

function M11Outputs({ outputs }: { outputs: Record<string, unknown> }) {
  const rules = riskRowValue(arr(outputs.monitor_rules));
  const priorHits = arr(outputs.prior_hits);
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        <Metric label="规则数" value={fmt(outputs.rule_count)} />
        <Metric label="历史命中" value={priorHits.length} tone={priorHits.length > 0 ? "warn" : "default"} />
        <Metric label="买入档" value={rules.filter((r) => r.rule_type === "price_buy").length} />
        <Metric label="告警规则" value={rules.filter((r) => r.severity !== "info").length} tone={rules.some((r) => r.severity !== "info") ? "warn" : "default"} />
      </div>

      {rules.length > 0 && (
        <Section icon={RadioTower} title="监控规则">
          <ul className="flex flex-col gap-1.5">
            {rules.map((r, i) => (
              <li key={i} className="rounded-lg border border-border/60 bg-muted/20 px-2.5 py-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <ToneBadge
                    text={RULE_TYPE_LABEL[str(r.rule_type)] ?? str(r.rule_type)}
                    tone={toneOf(SEVERITY_TONE, r.severity)}
                  />
                  <ToneBadge text={labelOf(SEVERITY_LABEL, r.severity)} tone={toneOf(SEVERITY_TONE, r.severity)} />
                  <span className="text-[10px] text-muted-foreground">{labelOf(MODULE_SHORT, r.source_module)}</span>
                  <span className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] text-foreground/70">
                    {ACTION_LABEL[str(r.action)] ?? str(r.action)}
                  </span>
                </div>
                <p className="mt-1 font-mono text-[11px] font-medium text-foreground/85">{translateEnumText(fmt(r.trigger))}</p>
                {str(r.message || r.description) && (
                  <p className="mt-0.5 text-[11px] leading-4 text-muted-foreground">{fmt(r.message || r.description)}</p>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

// ---------- 注册表 ----------

export const MODULE_OUTPUT_COMPONENTS: Record<string, React.ComponentType<{ outputs: Record<string, unknown> }>> = {
  M1_business_model: M1Outputs,
  M2_financial_quality: M2Outputs,
  M3_growth: M3Outputs,
  M4_valuation: M4Outputs,
  M5_moat: M5Outputs,
  M6_governance: M6Outputs,
  M7_market: M7Outputs,
  M8_safety_margin: M8Outputs,
  M9_risk: M9Outputs,
  M10_decision: M10Outputs,
  M11_monitor: M11Outputs,
};

export function ModuleOutputs({ module, outputs }: { module: string; outputs: Record<string, unknown> }) {
  const View = MODULE_OUTPUT_COMPONENTS[module];
  if (!View) return null;
  return <View outputs={outputs} />;
}
