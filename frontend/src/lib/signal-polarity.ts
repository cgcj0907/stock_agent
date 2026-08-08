/**
 * 信号极性判定（展示层）。
 *
 * 后端契约里 `signals` 字段同时承载正向信号（如 M5 "ROE 稳定（变异系数 ≤0.15）"）
 * 与风险信号（如 M2/M6 的 RiskSignal），但早期前端统一按风险块渲染。
 * 这里按内容/severity 做展示层分类，不改后端数据。
 */

export type SignalPolarity = "positive" | "risk" | "neutral";

function textOf(v: unknown): string {
  if (typeof v === "string") return v;
  if (v !== null && typeof v === "object" && !Array.isArray(v)) {
    const rec = v as Record<string, unknown>;
    const msg = rec.message ?? rec.desc ?? rec.text ?? rec.impact;
    if (typeof msg === "string") return msg;
  }
  return "";
}

/** 明确表示「没有风险」的措辞优先判为正向，避免被风险关键词误伤。 */
const NO_RISK_RE = /未发现|无明显|无风险|没有发现|未触发/i;

/** 结构化 RiskSignal 对象（含 severity 字段）一律按契约视为风险信号。 */
function hasSeverity(v: unknown): boolean {
  if (v === null || typeof v !== "object" || Array.isArray(v)) return false;
  const sev = (v as Record<string, unknown>).severity;
  return typeof sev === "string" && sev !== "";
}

const RISK_RE =
  /风险|下降|下滑|恶化|亏损|背离|异常|降级|失败|缺失|回避|侵蚀|窄|无|泡沫|高估|否决|触发|预警|警戒|不足|承压|受限|踩雷|低于|为负|负增长|expensive|avoid|narrow|erosion|alert|critical|high|warn/i;

const POSITIVE_RE =
  /稳定|可控|改善|向好|提升|增长|充足|宽|较宽|优秀|优势|净流入|正常|达标|健康|买入|strong|improve|stable|wide|attractive|good/i;

/** 单条信号 → 极性：正向 / 风险 / 中性。 */
export function classifySignal(v: unknown): SignalPolarity {
  const text = textOf(v);
  if (!text) return "neutral";
  if (NO_RISK_RE.test(text)) return "positive";
  if (hasSeverity(v)) return "risk";
  if (RISK_RE.test(text)) return "risk";
  if (POSITIVE_RE.test(text)) return "positive";
  return "neutral";
}

export interface SignalGroups {
  positive: unknown[];
  risk: unknown[];
  neutral: unknown[];
}

/** 按极性分组，保持组内原顺序。 */
export function groupSignals(items: unknown[]): SignalGroups {
  const groups: SignalGroups = { positive: [], risk: [], neutral: [] };
  for (const it of items) groups[classifySignal(it)].push(it);
  return groups;
}
