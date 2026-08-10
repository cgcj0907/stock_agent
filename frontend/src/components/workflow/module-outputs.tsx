"use client";

import * as React from "react";
import {
  Activity,
  AlertTriangle,
  BadgeCheck,
      Building2,
  ChartLine,
  ClipboardList,
  Gauge,
  GaugeCircle,
  HandCoins,
  Info,
  Landmark,
    RadioTower,
    Scale,
  ShieldAlert,
  ShieldCheck,
    Target,
  TrendingUp,
  TriangleAlert,
  UserRound,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Collapsible } from "@/components/workflow/collapsible";
import { Metric } from "@/components/workflow/metric";
import { M4Outputs } from "@/components/workflow/m4-outputs";
import { getSectionTitleClass } from "@/components/workflow/section-tone";
import { fieldLabel } from "@/lib/labels";
import { groupSignals } from "@/lib/signal-polarity";
import {
  CONCLUSION_TONE,
  MOS_LABEL,
  MOS_TONE,
  POSITION_TONE,
  SEVERITY_TONE,
  WIDTH_TEXT_TONE,
  labelOf,
  toneOf,
} from "@/lib/tone";

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


function ToneBadge({ text, tone, icon: Icon }: { text: unknown; tone: string; icon?: React.ComponentType<{ className?: string }> }) {
  const IconCmp = Icon ?? null;
  return (
    <Badge variant="outline" className={`gap-1 rounded-md px-1.5 py-0.5 text-[11px] ${tone}`}>
      {IconCmp && <IconCmp className="size-3" />}
      {fmt(text)}
    </Badge>
  );
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

const CAP_ALLOC_LABEL: Record<string, string> = {
  good: "优秀",
  neutral: "中性",
  poor: "较差",
};

const BUSINESS_TYPE_LABEL: Record<string, string> = {
  consumer_monopoly: "消费垄断",
  growth: "成长",
  cyclical: "周期",
  financial: "金融",
  asset_based: "资产型",
  stable_dividend: "高分红稳定",
};

const MODULE_SHORT: Record<string, string> = {
  M0_investor_profile: "M0 投资者画像",
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
  // M11 监控规则类型（evidence/触发器文案里出现时转中文）
  [/price_buy/g, "买入触发"],
  [/price_sell/g, "卖出触发"],
  [/valuation_sell/g, "估值卖出"],
  [/mos_watch/g, "安全边际监控"],
  [/prosperity_watch/g, "景气监控"],
  [/fundamental_watch/g, "基本面监控"],
  [/risk_watch/g, "风险监控"],
  [/decision_watch/g, "决策监控"],
  [/prior_hit_review/g, "历史命中"],
  [/sentiment_watch/g, "情绪监控"],
];

/** 监控/风险触发条件里的英文枚举转中文（展示层，不改后端规则）。 */
export function translateEnumText(s: string): string {
  let out = s;
  for (const [re, zh] of TRIGGER_WORDS) out = out.replace(re, zh);
  out = out.replace(/跨周期均值/g, "过去几年平均");
  out = out.replace(/\b均值\b/g, "平均");
  out = out.replace(/\b最新\b/g, "最近一年");
  for (const [id, zh] of Object.entries(MODULE_SHORT)) {
    if (out.includes(id)) out = out.split(id).join(zh);
  }
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
  const titleCls = getSectionTitleClass(title, tone);
  return (
    <div className="flex flex-col gap-1.5 border-t border-border/40 pt-2.5">
      <div className={`flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider ${titleCls}`}>
        {Icon && <Icon className="size-3.5 shrink-0" />}
        <span className="truncate">{title}</span>
      </div>
      {children}
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
      <div className="flex items-center justify-between text-xs">
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
          <div className="truncate text-[11px] font-semibold tracking-wide text-muted-foreground">{fieldLabel(k)}</div>
          <div className="mt-0.5 break-words text-[13px] leading-5 font-medium text-foreground/80">{fmt(v)}</div>
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
          className="break-words text-[13px] leading-5 font-medium text-emerald-700 hover:underline dark:text-emerald-400"
        >
          {title}
        </a>
      ) : (
        <span className="break-words text-[13px] leading-5 font-medium text-foreground/85">{title}</span>
      )}
      {metaLine && <span className="text-[11px] leading-4 text-muted-foreground">{metaLine}</span>}
      {snippet && <span className="text-xs leading-4 text-muted-foreground/80">{snippet}</span>}
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
        ) : isObj(it) ? (
          <li key={i} className="flex items-start gap-1.5 text-[13px] leading-5 text-foreground/80">
            <span className="mt-[5px] size-1 shrink-0 rounded-full bg-muted-foreground/50" />
            <span className="min-w-0 break-words">{objectListText(it)}</span>
          </li>
        ) : (
          <li key={i} className="flex items-start gap-1.5 text-[13px] leading-5 text-foreground/80">
            <span className="mt-[5px] size-1 shrink-0 rounded-full bg-muted-foreground/50" />
            <span className="min-w-0 break-words">{fmt(it)}</span>
          </li>
        ),
      )}
    </ul>
  );
}

function objectValueText(key: string, value: unknown): string {
  if (Array.isArray(value)) {
    return value
      .map((it) => (isObj(it) ? objectListText(it) : translateEnumText(fmt(it))))
      .filter(Boolean)
      .join("、");
  }
  if (isObj(value)) {
    return objectListText(value);
  }
  if (key === "confidence") {
    return labelOf(CONFIDENCE_LABEL, value);
  }
  return translateEnumText(fmt(value));
}

function objectListText(item: Record<string, unknown>): string {
  const entries = Object.entries(item).filter(([, v]) => {
    if (v === null || v === undefined || v === "") return false;
    if (Array.isArray(v)) return v.length > 0;
    if (isObj(v)) return Object.keys(v).length > 0;
    return true;
  });
  if (entries.length === 0) return "—";

  const primaryKey = ["path", "title", "message", "desc", "text", "reason", "name", "label"].find(
    (key) => item[key] !== null && item[key] !== undefined && item[key] !== "",
  );
  const primary = primaryKey ? objectValueText(primaryKey, item[primaryKey]) : "";
  const rest = entries
    .filter(([k]) => k !== primaryKey)
    .map(([k, v]) => `${fieldLabel(k)}：${objectValueText(k, v)}`);

  return [primary, ...rest].filter(Boolean).join(" · ");
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
          <div className="text-[11px] font-semibold tracking-wide text-violet-600/80 dark:text-violet-300/80">
            {fieldLabel(k)}
          </div>
          {Array.isArray(v) ? (
            <BulletList items={v} />
          ) : isObj(v) ? (
            <KVGrid items={Object.entries(v)} cols={1} />
          ) : (
            <div className="mt-0.5 break-words text-[13px] leading-5 text-foreground/80">{fmt(v)}</div>
          )}
        </div>
      ))}
    </div>
  );
}


function signalText(it: unknown): string {
  if (isObj(it)) return translateEnumText(str(it.message ?? it.desc ?? it.text ?? it.impact));
  return translateEnumText(str(it));
}

function SignalItems({ items, showSeverity }: { items: unknown[]; showSeverity?: boolean }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {items.map((sig, i) => (
        <li key={i} className="flex items-start gap-2 text-[13px] leading-5">
          {showSeverity && isObj(sig) && str(sig.severity) && (
            <ToneBadge
              text={labelOf(SEVERITY_LABEL, sig.severity)}
              tone={toneOf(SEVERITY_TONE, sig.severity)}
            />
          )}
          <span className="min-w-0 flex-1 break-words text-foreground/80">{signalText(sig)}</span>
        </li>
      ))}
    </ul>
  );
}

/** 按极性分组渲染 signals：正向 / 风险 / 提示，避免把正向信号当风险块展示。 */
export function SignalGroups({ items }: { items: unknown[] }) {
  const groups = groupSignals(items);
  return (
    <>
      {groups.positive.length > 0 && (
        <Section icon={TrendingUp} title="正向信号" tone="primary">
          <SignalItems items={groups.positive} />
        </Section>
      )}
      {groups.risk.length > 0 && (
        <Section icon={AlertTriangle} title="风险信号" tone="rose">
          <SignalItems items={groups.risk} showSeverity />
        </Section>
      )}
      {groups.neutral.length > 0 && (
        <Section icon={Info} title="提示" tone="primary">
          <SignalItems items={groups.neutral} />
        </Section>
      )}
    </>
  );
}


function riskRowValue(items: unknown[]): Array<Record<string, unknown>> {
  return items.filter(isObj);
}

// ---------- M1 商业模式 ----------

const COMPETENCE_TONE: Record<string, string> = {
  high: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  medium: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  low: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
  in_circle: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  edge: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  out_circle: "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/60 dark:text-red-300",
};

const COMPETENCE_LABEL: Record<string, string> = {
  high: "可理解",
  medium: "边缘",
  low: "难理解",
  in_circle: "圈内",
  edge: "边缘",
  out_circle: "圈外",
};

const DIM_LABEL: Record<string, string> = {
  consumer: "消费",
  finance: "金融",
  technology: "科技",
  healthcare: "医药医疗",
  manufacturing: "制造业",
  energy: "能源材料",
  internet: "互联网平台",
  utilities: "公用事业",
  real_estate: "地产链",
  overseas: "海外市场",
};

/** M0 投资者画像：个人可理解性 + 能力圈匹配 + 安全边际/风险注入摘要。 */
function M0Outputs({ outputs }: { outputs: Record<string, unknown> }) {
  const competence = isObj(outputs.competence) ? outputs.competence : {};
  const dims = isObj(competence.dimensions) ? competence.dimensions : {};
  const handoff = isObj(outputs.handoff) ? outputs.handoff : {};
  const level = str(handoff.competence_level) || str(competence.overall_level);
  const adj = typeof handoff.required_discount_adjustment === "number" ? handoff.required_discount_adjustment : 0;
  const amp = isObj(handoff.risk_amplification) ? handoff.risk_amplification : {};
  const flags = Array.isArray(amp.flags) ? amp.flags.filter((f): f is string => typeof f === "string") : [];
  const used = Array.isArray(handoff.profile_used)
    ? handoff.profile_used.filter((x): x is string => typeof x === "string")
    : [];
  const dimEntries = Object.entries(dims);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <ToneBadge
          text={str(outputs.persona_summary) || "投资者画像"}
          tone={toneOf(COMPETENCE_TONE, level)}
          icon={UserRound}
        />
        {level && (
          <ToneBadge
            text={`个人可理解性：${COMPETENCE_LABEL[level] ?? level}`}
            tone={toneOf(COMPETENCE_TONE, level)}
          />
        )}
      </div>

      {dimEntries.length > 0 && (
        <Section icon={UserRound} title="能力圈匹配（个人胜任分）">
          <ul className="flex flex-col gap-1.5">
            {dimEntries.map(([dim, v]) => {
              const info = isObj(v) ? v : {};
              const lv = str(info.level);
              return (
                <li
                  key={dim}
                  className="flex items-center justify-between gap-2 rounded-lg border border-border/60 bg-muted/20 px-2.5 py-1.5 text-[13px]"
                >
                  <span className="min-w-0 flex-1 truncate text-foreground/80">{DIM_LABEL[dim] ?? dim}</span>
                  <span className="shrink-0 text-muted-foreground">{fmt(info.score)} 分</span>
                  <ToneBadge text={COMPETENCE_LABEL[lv] ?? lv} tone={toneOf(COMPETENCE_TONE, lv)} />
                </li>
              );
            })}
          </ul>
        </Section>
      )}

      {adj > 0 && (
        <Section icon={ShieldCheck} title="安全边际注入">
          <p className="text-[13px] leading-5 text-foreground/80">
            要求折扣上调{" "}
            <span className="font-bold text-amber-600 dark:text-amber-400">
              {(adj * 100).toFixed(1)}%
            </span>
            {Array.isArray(handoff.discount_reasons) &&
              (handoff.discount_reasons as string[]).length > 0 && (
                <>（{(handoff.discount_reasons as string[]).join("、")}）</>
              )}
          </p>
        </Section>
      )}

      {flags.length > 0 && (
        <Section icon={AlertTriangle} title="个人风险提示" tone="rose">
          <ul className="flex flex-col gap-1.5">
            {flags.map((f, i) => (
              <li
                key={i}
                className="flex items-start gap-2 rounded-lg border border-amber-200/60 bg-amber-50/50 px-2.5 py-1.5 text-[13px] text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200"
              >
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {used.length > 0 && (
        <Section icon={Info} title="消费字段（审计）">
          <div className="flex flex-wrap gap-1">
            {used.map((u) => (
              <Badge key={u} variant="outline" className="text-[11px] font-normal text-muted-foreground">
                {u}
              </Badge>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

function M1Outputs({ outputs }: { outputs: Record<string, unknown> }) {
  const qual = isObj(outputs.llm_qualitative) ? outputs.llm_qualitative : null;
  const oneLiner = str(outputs.business_model) || str(qual?.business_model);
  // 优先读顶层 outputs（后端始终回填规则/LLM 有效值），llm_qualitative 仅作兜底
  const reasons = arr(outputs.reasons).length ? arr(outputs.reasons) : arr(qual?.reasons);
  const understandability =
    str(outputs.understandability) || str(qual?.understandability) || "—";
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        <Metric label="生意类型" value={labelOf(BUSINESS_TYPE_LABEL, outputs.business_type)} />
        <Metric label="可理解性" value={fmt(understandability)} />
        <Metric label="行业" value={fmt(outputs.industry)} />
      </div>
      {oneLiner && (
        <Section icon={Building2} title="生意本质">
          <p className="break-words text-[13px] leading-5 text-foreground/80">{oneLiner}</p>
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
              <li key={i} className="flex items-start gap-2 text-[13px] leading-5">
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
  const signals = arr(outputs.signals);
  const qual = isObj(outputs.llm_qualitative) ? outputs.llm_qualitative : null;
  const qualList = qual ? (
    <QualBlock qual={qual} excludeKeys={["width"]} />
  ) : typeof outputs.llm_qualitative === "string" ? (
    <p className="break-words whitespace-pre-wrap text-[13px] leading-5 text-foreground/80">{outputs.llm_qualitative}</p>
  ) : null;

  return (
    <div className="flex flex-col gap-3">
      {/* 主结论：护城河宽度 */}
      <div className="flex items-center gap-2.5 rounded-lg border border-border/60 bg-muted/20 px-3 py-2.5">
        <GaugeCircle className="size-4 shrink-0 text-primary/70" />
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            护城河宽度
          </div>
          <div className={`text-lg leading-7 font-bold ${toneOf(WIDTH_TEXT_TONE, outputs.width)}`}>
            {fmt(outputs.width) || "—"}
          </div>
        </div>
      </div>

      {signals.length > 0 && <SignalGroups items={signals} />}

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
      {signals.length > 0 && (
        <Section icon={AlertTriangle} title="治理风险信号" tone="rose">
          <ul className="flex flex-col gap-1.5">
            {signals.map((sig, i) => (
              <li key={i} className="flex items-start gap-2 text-[13px] leading-5">
                <ToneBadge text={labelOf(SEVERITY_LABEL, sig.severity ?? "warn")} tone={toneOf(SEVERITY_TONE, sig.severity)} />
                <span className="min-w-0 flex-1 break-words text-foreground/80">{fmt(sig.message ?? sig.desc ?? sig)}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
      {qual && Object.keys(qual).length > 0 && (
        <Section icon={Landmark} title="LLM 定性" tone="violet">
          <QualBlock qual={qual} excludeKeys={["governance_risks"]} />
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
        <span className="text-[11px] text-muted-foreground">
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
          <span className="text-[11px] text-muted-foreground">{MOS_LABEL[mos] ?? mos}</span>
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
          <div className="flex items-center justify-between text-xs">
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
              <li key={i} className="flex items-center justify-between gap-2 rounded-lg border border-border/60 bg-muted/20 px-2.5 py-1.5 text-[13px]">
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
              <li key={i} className="rounded-lg border border-red-200 bg-red-50/60 px-2.5 py-1.5 text-[13px] leading-5 text-red-700 dark:border-red-800/50 dark:bg-red-950/30 dark:text-red-300">
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
                  <span className="font-mono text-[11px] font-semibold text-muted-foreground">{fmt(it.id)}</span>
                  <ToneBadge text={it.category} tone={toneOf(SEVERITY_TONE, "warn")} />
                  <ToneBadge text={labelOf(SEVERITY_LABEL, it.severity)} tone={toneOf(SEVERITY_TONE, it.severity)} />
                  <span className="text-[11px] text-muted-foreground">{labelOf(MODULE_SHORT, it.source_module)}</span>
                </div>
                <p className="mt-1 break-words text-[13px] leading-5 text-foreground/80">{fmt(it.impact)}</p>
                {str(it.mitigation) && (
                  <p className="mt-0.5 text-xs leading-4 text-muted-foreground">缓解：{fmt(it.mitigation)}</p>
                )}
                {it.expected_loss != null && (
                  <p className="mt-0.5 text-xs leading-4 text-muted-foreground">
                    期望损失 {fmt(it.expected_loss)} · 触发 {translateEnumText(fmt(it.trigger))}
                    {it.veto_candidate === true && " · 否决候选"}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {(scenario || redTeam) && (
        <Collapsible title="深度风险分析">
          {scenario && (
            <Section icon={TrendingUp} title="压力情景">
          <div className="rounded-lg border border-border/60 bg-muted/20 p-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[13px] font-semibold text-foreground/90">{fmt(scenario.scenario)}</span>
              {scenario.estimated_downside_pct != null && (
                <ToneBadge
                  text={`最大回撤 ${fmt(scenario.estimated_downside_pct)}%`}
                  tone={toneOf(SEVERITY_TONE, "critical")}
                />
              )}
            </div>
            <p className="mt-1.5 text-xs leading-5 text-muted-foreground">{fmt(scenario.assumptions)}</p>
            {drivers.length > 0 && <BulletList items={drivers} />}
            {(scenario.current_price != null || scenario.suggested_position_cap != null) && (
              <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-foreground/70">
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
                <span className="text-[11px] font-semibold text-muted-foreground">监控候选</span>
                {monitorCandidates.map((c, i) => (
                  <span key={i} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground/70">{fmt(c)}</span>
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
                <div className="mb-1 text-[11px] font-semibold text-violet-600/80 dark:text-violet-300/80">关键假设</div>
                <BulletList items={assumptions} />
              </div>
            )}
            {paths.length > 0 && (
              <div>
                <div className="mb-1 text-[11px] font-semibold text-violet-600/80 dark:text-violet-300/80">永久损失路径</div>
                <ul className="flex flex-col gap-1.5">
                  {paths.map((p, i) => (
                    <li key={i} className="rounded-lg border border-border/60 bg-muted/20 px-2.5 py-1.5">
                      <div className="flex items-center gap-1.5">
                        <ToneBadge text={labelOf(CONFIDENCE_LABEL, p.confidence)} tone={toneOf(SEVERITY_TONE, p.confidence)} />
                        {p.veto_candidate === true && (
                          <ToneBadge text="否决候选" tone={toneOf(SEVERITY_TONE, "critical")} />
                        )}
                      </div>
                      <p className="mt-1 break-words text-xs leading-5 text-foreground/80">{fmt(p.path)}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {str(redTeam.verdict) && (
              <div className="rounded-lg border border-amber-200/70 bg-amber-50/60 px-2.5 py-2 text-xs leading-5 text-amber-800 dark:border-amber-800/50 dark:bg-amber-950/30 dark:text-amber-300">
                <span className="font-semibold">反方结论：</span>
                {fmt(redTeam.verdict)}
              </div>
            )}
            {Array.isArray(redTeam.references) && redTeam.references.length > 0 && (
              <div className="flex flex-col gap-1">
                <div className="text-[11px] font-semibold text-violet-600/80 dark:text-violet-300/80">参考文章</div>
                <BulletList items={redTeam.references} />
              </div>
            )}
          </div>
          </Section>
          )}
        </Collapsible>
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
          <Badge variant="outline" className="gap-1 rounded-md border-border bg-muted/50 px-1.5 py-0.5 text-[11px]">
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
                <span className="w-14 shrink-0 text-xs text-foreground/70">{d.label}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className={`h-full rounded-full ${d.bar}`}
                    style={{ width: `${v == null ? 0 : Math.max(0, Math.min(100, v))}%` }}
                  />
                </div>
                <span className="w-7 shrink-0 text-right text-xs font-semibold tabular-nums text-foreground/90">
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
                  <span className="text-[11px] text-muted-foreground">{labelOf(MODULE_SHORT, r.source_module)}</span>
                  <span className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[11px] text-foreground/70">
                    {ACTION_LABEL[str(r.action)] ?? str(r.action)}
                  </span>
                </div>
                <p className="mt-1 font-mono text-xs font-medium text-foreground/85">{translateEnumText(fmt(r.trigger))}</p>
                {str(r.message || r.description) && (
                  <p className="mt-0.5 text-xs leading-4 text-muted-foreground">{fmt(r.message || r.description)}</p>
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
  M0_investor_profile: M0Outputs,
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
