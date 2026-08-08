/**
 * 模块卡片「结论层」：展示层派生的一句话判断，不改后端。
 *
 * 优先消费各模块已有的结论型字段（M5 width / M7 position / M8 mos_state /
 * M9 risk_items / M10 conclusion），其余模块退回 score 分档。
 */

import type { ModuleResultView } from "@/hooks/use-workflow-run";

export type VerdictTone = "positive" | "neutral" | "negative" | "muted";

export interface ModuleVerdict {
  text: string;
  tone: VerdictTone;
}

function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}

function arr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

function isObj(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

const POSITIVE_WIDTH = new Set(["宽", "较宽"]);
const NEGATIVE_WIDTH = new Set(["较窄", "窄", "无"]);
const POSITIVE_POSITION = new Set(["极低估", "低估"]);
const NEUTRAL_POSITION = new Set(["合理", "合理偏下", "合理偏上"]);

export function verdictFor(result: ModuleResultView): ModuleVerdict | null {
  if (result.status !== "done") return null;
  const o = result.outputs ?? {};

  switch (result.module) {
    case "M5_moat": {
      const width = str(o.width);
      if (POSITIVE_WIDTH.has(width)) return { text: "护城河较宽，竞争优势明确", tone: "positive" };
      if (width === "中") return { text: "护城河中等，优势一般", tone: "neutral" };
      if (NEGATIVE_WIDTH.has(width)) return { text: "护城河偏窄，竞争优势有限", tone: "negative" };
      break;
    }
    case "M7_market": {
      const position = str(o.position);
      if (POSITIVE_POSITION.has(position)) return { text: `估值${position}，处于低位`, tone: "positive" };
      if (NEUTRAL_POSITION.has(position)) return { text: "估值合理", tone: "neutral" };
      if (position === "高估") return { text: "估值偏高，需谨慎", tone: "negative" };
      if (position === "泡沫") return { text: "估值泡沫风险", tone: "negative" };
      if (position === "样本不足") return { text: "估值样本不足", tone: "muted" };
      break;
    }
    case "M8_safety_margin": {
      const mos = str(o.mos_state);
      if (mos === "attractive") return { text: "安全边际充足，进入买入区间", tone: "positive" };
      if (mos === "fair") return { text: "安全边际一般，可观望", tone: "neutral" };
      if (mos === "expensive") return { text: "安全边际为负", tone: "negative" };
      if (mos === "unavailable") return { text: "安全边际数据不足", tone: "muted" };
      break;
    }
    case "M9_risk": {
      const vetoes = arr(o.vetoes).filter(isObj);
      if (vetoes.length > 0 || str(o.veto)) {
        return { text: `触发一票否决（${Math.max(vetoes.length, 1)} 项）`, tone: "negative" };
      }
      const items = arr(o.risk_items).filter(isObj);
      if (items.length === 0) return { text: "未发现明显风险", tone: "positive" };
      const severe = items.filter((it) => {
        const sev = str(it.severity);
        return sev === "high" || sev === "critical" || it.veto_candidate === true;
      });
      if (severe.length > 0) return { text: `存在 ${severe.length} 项高风险，需重点跟踪`, tone: "negative" };
      return { text: `存在 ${items.length} 项风险，需持续跟踪`, tone: "neutral" };
    }
    case "M10_decision": {
      const conclusion = str(o.conclusion);
      if (o.blocked_by_veto === true || /否决/.test(conclusion)) {
        return { text: "被一票否决，回避", tone: "negative" };
      }
      if (/强烈关注/.test(conclusion)) return { text: "强烈关注，可重点跟踪", tone: "positive" };
      if (/回避/.test(conclusion)) return { text: "回避，不建议参与", tone: "negative" };
      if (/关注/.test(conclusion)) return { text: "关注，需持续验证", tone: "neutral" };
      if (/中性/.test(conclusion)) return { text: "中性，暂不行动", tone: "neutral" };
      break;
    }
    case "M4_valuation": {
      const kill = arr(o.kill_switches);
      if (kill.length > 0) return { text: `触发风险开关（${kill.length} 项），估值需保守`, tone: "negative" };
      break;
    }
  }

  const score = result.score;
  if (score == null) return null;
  if (score >= 60) return { text: "整体偏正面", tone: "positive" };
  if (score >= 40) return { text: "整体偏中性", tone: "neutral" };
  return { text: "整体偏负面", tone: "negative" };
}
