import type { ModuleResultView } from "../hooks/use-workflow-run";

/** 明确的风险字段名（M9 Risk Registry、M10 veto、M4 kill_switch、M11 监控等）。 */
const RISK_KEYS = new Set([
  "risks",
  "risk_items",
  "vetoed",
  "vetoes",
  "kill_switches",
  "monitor_rules",
  "monitor_hits",
  "warnings",
  "risk_notes",
  "risk",
]);

/** 风险信号判定关键词（展示层启发式，与 signal-polarity 口径一致）。 */
const RISK_WORD_RE =
  /风险|⚠️|隐患|侵蚀|恶化|背离|下降|下滑|高估|超卖|异常|警示|失效|缺失|不达标/;

function signalIsRisk(s: unknown): boolean {
  if (s && typeof s === "object") {
    const sev = String((s as { severity?: unknown }).severity ?? "").toLowerCase();
    return ["critical", "high", "warn", "medium", "risk"].includes(sev);
  }
  if (typeof s === "string") return RISK_WORD_RE.test(s);
  return false;
}

/** 判断模块结果是否包含风险内容（风险字段 / 风险信号），供「只看风险」过滤。 */
export function hasRiskContent(result: ModuleResultView): boolean {
  const outputs = result.outputs ?? {};
  for (const k of Object.keys(outputs)) {
    if (RISK_KEYS.has(k)) return true;
  }
  const signals = outputs.signals;
  if (Array.isArray(signals)) {
    return signals.some(signalIsRisk);
  }
  return false;
}
