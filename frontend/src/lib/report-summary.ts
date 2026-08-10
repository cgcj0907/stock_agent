/**
 * 分析结果区摘要条（展示层纯函数）：模块总数 / 含风险模块数 / 一票否决数，
 * 供「分析结果」标题下先给全局感再下钻。
 *
 * 注意：node --test 直接加载本文件，运行时不能依赖 `@/` 别名，
 * 因此风险判定逻辑与 lib/module-risk.hasRiskContent 内联保持一致（两侧改动需同步）。
 */
import type { ModuleResultView } from "../hooks/use-workflow-run";

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

function hasRiskContent(result: ModuleResultView): boolean {
  const outputs = result.outputs ?? {};
  for (const k of Object.keys(outputs)) {
    if (RISK_KEYS.has(k)) return true;
  }
  const signals = outputs.signals;
  if (Array.isArray(signals)) return signals.some(signalIsRisk);
  return false;
}

export interface ResultSummary {
  total: number;
  risk: number;
  veto: number;
}

export function summarizeResults(results: ModuleResultView[]): ResultSummary {
  let risk = 0;
  let veto = 0;
  for (const r of results) {
    if (hasRiskContent(r)) risk += 1;
    const o = r.outputs ?? {};
    const vetoes = Array.isArray(o.vetoes) ? o.vetoes.length : 0;
    const blocked = o.blocked_by_veto === true ? 1 : 0;
    if (vetoes > 0 || blocked > 0) veto += 1;
  }
  return { total: results.length, risk, veto };
}
